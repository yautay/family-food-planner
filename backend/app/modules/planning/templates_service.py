"""Szablony dnia/tygodnia i cykle tygodni (BATCH_07, 02_DOMAIN §7, 03_DATABASE §6).

Osobny plik, a nie kolejne 600 linii w `service.py` — uzasadnienie (karta B07
pozostawiła tę decyzję implementującemu):

- `PlanningService` operuje na dniu i jego wnętrzu; tutaj agregatem jest SZABLON,
  czyli encja ze scope o zupełnie innym cyklu życia (payload nadpisywany całością),
- zapisy do planu i tak przechodzą przez `PlanningService.append_day_payload`,
  więc nie ma tu drugiego mechanizmu kopiowania (wymóg karty B07 §Context),
- rejestry blokad usuwania dla payloadów JSONB są tematem samym w sobie (ADR-012)
  i lepiej czytają się obok zapytań, których dotyczą.

Granice odpowiedzialności:

- **Widoczność** — wyłącznie `ScopedQuery` (`_DAY_TEMPLATES`, `_WEEK_TEMPLATES`,
  `_CYCLES`); cudzy szablon PRYWATNY daje 404, nie 403 (07_SECURITY §4).
- **Instancjacja = KOPIA bez live-sync** (02_DOMAIN §7): tworzy zwykłe wiersze
  planu z payloadu. Późniejsza edycja szablonu nie rusza planu i odwrotnie —
  jedynym łącznikiem są `recipe_id`/`product_id`, czyli referencje do słowników.
- **Jedna transakcja na operację** — tydzień to siedem dni, a apply cyklu bywa
  i pięcioma tygodniami; częściowa instancjacja nie może zostać w bazie po błędzie
  (karta B07 §Implementation Notes).
- **Zliczanie referencji w JSONB** — patrz koniec pliku: containment `@>` po
  indeksie GIN `jsonb_path_ops` (ADR-012).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deletion import USED_IN_LIMIT, UsedInRef, assert_deletable
from app.core.scope import Scope, ScopedQuery
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct
from app.modules.catalog.service import register_product_reference_finder
from app.modules.planning.models import DayTemplate, WeekCycle, WeekTemplate
from app.modules.planning.schemas import (
    CycleApplyRequest,
    CycleWriteRequest,
    DayTemplatePayload,
    DayTemplateWriteRequest,
    WeekTemplatePayload,
    WeekTemplateWriteRequest,
)
from app.modules.planning.sequences import cycle_week_plan, is_week_start
from app.modules.planning.service import DayView, PlanningService, PlanValidationError
from app.modules.recipes.models import Recipe
from app.modules.recipes.service import register_recipe_reference_finder

DAY_TEMPLATE_NOT_FOUND = "Nie znaleziono szablonu dnia."
WEEK_TEMPLATE_NOT_FOUND = "Nie znaleziono szablonu tygodnia."
CYCLE_NOT_FOUND = "Nie znaleziono cyklu tygodni."
SOURCE_DAY_EMPTY = (
    "Ten dzień planu jest pusty — nie ma z czego zrobić szablonu. Dodaj przynajmniej jeden posiłek."
)
SOURCE_WEEK_EMPTY = (
    "Ten tydzień planu jest pusty — nie ma z czego zrobić szablonu. "
    "Zbuduj przynajmniej jeden dzień."
)
NOT_A_MONDAY = "Tydzień zaczyna się w poniedziałek — podaj datę poniedziałku."
CYCLE_TEMPLATES_UNKNOWN = (
    "Cykl wskazuje szablony tygodnia, których nie ma albo nie są dla Ciebie widoczne."
)
DEAD_RECIPES = (
    "Szablon wskazuje przepisy, których nie ma albo nie są dla Ciebie widoczne. "
    "Popraw szablon i spróbuj ponownie."
)
DEAD_PRODUCTS = (
    "Szablon wskazuje produkty, których już nie ma. Popraw szablon albo odtwórz brakujące produkty."
)
WEEK_TEMPLATE_IN_USE = "Ten szablon tygodnia jest używany w cyklu — najpierw wypnij go z cyklu."

#: Widoczność przepisu wskazanego w payloadzie — TEN SAM mechanizm, co przy
#: dodawaniu pozycji planu (`PlanningService._assert_recipe_available`). Bez tego
#: payload szablonu byłby obejściem scope: użytkownik mógłby wpisać `recipe_id`
#: cudzego PRYWATNEGO przepisu, zinstancjonować szablon i odczytać jego nazwę
#: oraz wartości odżywcze przez `GET /plan/days` (ustalenie /security-review).
_VISIBLE_RECIPES = ScopedQuery(Recipe, not_found_message=DEAD_RECIPES)

_DAY_TEMPLATES = ScopedQuery(DayTemplate, not_found_message=DAY_TEMPLATE_NOT_FOUND)
_WEEK_TEMPLATES = ScopedQuery(WeekTemplate, not_found_message=WEEK_TEMPLATE_NOT_FOUND)
_CYCLES = ScopedQuery(WeekCycle, not_found_message=CYCLE_NOT_FOUND)

#: Ile dni obejmuje tydzień szablonu — offsety payloadu to 0..6 od poniedziałku.
DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class InstantiateResult:
    """Dni utworzone przez instancjację + miękkie ostrzeżenia (np. archiwalny przepis)."""

    days: list[DayView]
    warnings: list[str]


@dataclass(frozen=True)
class CycleView:
    """Cykl razem z nazwami szablonów w kolejności rotacji (`None` = szablon zniknął)."""

    cycle: WeekCycle
    template_names: list[str | None]


class TemplatesService:
    """Szablony dnia/tygodnia i cykle. Jedyne miejsce I/O dla tych agregatów."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Zapisy do planu idą przez serwis planu — nie duplikujemy ani reguły
        # rozstrzygania dnia dla daty, ani mechanizmu dopisywania posiłków.
        self._planning = PlanningService(session)

    # --- szablony dnia ---------------------------------------------------------------

    async def list_day_templates(self, user: User) -> list[DayTemplate]:
        """Widoczne szablony dnia, alfabetycznie (lista nie zwraca payloadów)."""
        rows = (
            await self._session.execute(
                _DAY_TEMPLATES.select_visible(user).order_by(DayTemplate.name, DayTemplate.id)
            )
        ).scalars()
        return list(rows)

    async def get_day_template(self, template_id: int, *, user: User) -> DayTemplate:
        return await _DAY_TEMPLATES.get_or_404(self._session, template_id, user)

    async def create_day_template(
        self, *, user: User, payload: DayTemplateWriteRequest
    ) -> DayTemplate:
        """Nowy szablon dnia — z payloadu wprost albo zbudowany z dnia planu."""
        content = await self._day_payload_for(user, payload)
        template = DayTemplate(
            name=payload.name,
            payload=_dump(content),
            **ScopedQuery.ownership_for_create(user, payload.scope),
        )
        self._session.add(template)
        await self._session.commit()
        return template

    async def update_day_template(
        self, template_id: int, *, user: User, payload: DayTemplateWriteRequest
    ) -> DayTemplate:
        """PUT = nadpisanie CAŁEGO payloadu (03_DATABASE §6) — edycji per posiłek nie ma."""
        template = await _DAY_TEMPLATES.get_or_404(self._session, template_id, user)
        content = await self._day_payload_for(user, payload)
        self._apply_common_fields(template, name=payload.name, scope=payload.scope, user=user)
        template.payload = _dump(content)
        await self._session.commit()
        return template

    async def delete_day_template(self, template_id: int, *, user: User) -> None:
        """Usunięcie: właściciel albo ADMIN (macierz 08_TESTING §4)."""
        template = await _DAY_TEMPLATES.get_or_404(self._session, template_id, user)
        _DAY_TEMPLATES.assert_can_manage(template, user)
        await self._session.execute(delete(DayTemplate).where(DayTemplate.id == template.id))
        await self._session.commit()

    async def instantiate_day_template(
        self, template_id: int, *, user: User, dates: Sequence[date]
    ) -> InstantiateResult:
        """Szablon dnia → wiersze planu na wskazane daty (dopisuje, jak `/plan/copy`)."""
        template = await _DAY_TEMPLATES.get_or_404(self._session, template_id, user)
        content = _load_day(template.payload)
        warnings = await self._assert_references_alive(user, [content])

        for target in sorted(set(dates)):
            await self._planning.append_day_payload(user, target, content, scope=template.scope)
        await self._session.commit()

        days = [await self._planning.get_day(user, target) for target in sorted(set(dates))]
        return InstantiateResult(days=days, warnings=warnings)

    # --- szablony tygodnia -----------------------------------------------------------

    async def list_week_templates(self, user: User) -> list[WeekTemplate]:
        rows = (
            await self._session.execute(
                _WEEK_TEMPLATES.select_visible(user).order_by(WeekTemplate.name, WeekTemplate.id)
            )
        ).scalars()
        return list(rows)

    async def get_week_template(self, template_id: int, *, user: User) -> WeekTemplate:
        return await _WEEK_TEMPLATES.get_or_404(self._session, template_id, user)

    async def create_week_template(
        self, *, user: User, payload: WeekTemplateWriteRequest
    ) -> WeekTemplate:
        content = await self._week_payload_for(user, payload)
        template = WeekTemplate(
            name=payload.name,
            payload=_dump(content),
            **ScopedQuery.ownership_for_create(user, payload.scope),
        )
        self._session.add(template)
        await self._session.commit()
        return template

    async def update_week_template(
        self, template_id: int, *, user: User, payload: WeekTemplateWriteRequest
    ) -> WeekTemplate:
        template = await _WEEK_TEMPLATES.get_or_404(self._session, template_id, user)
        content = await self._week_payload_for(user, payload)
        self._apply_common_fields(template, name=payload.name, scope=payload.scope, user=user)
        template.payload = _dump(content)
        await self._session.commit()
        return template

    async def delete_week_template(self, template_id: int, *, user: User) -> None:
        """Usunięcie: 409, jeśli szablon jest używany w cyklu (tablica bez FK — 03_DB §6)."""
        template = await _WEEK_TEMPLATES.get_or_404(self._session, template_id, user)
        _WEEK_TEMPLATES.assert_can_manage(template, user)
        assert_deletable(WEEK_TEMPLATE_IN_USE, await self._cycles_using_template(template.id))
        await self._session.execute(delete(WeekTemplate).where(WeekTemplate.id == template.id))
        await self._session.commit()

    async def instantiate_week_template(
        self, template_id: int, *, user: User, week_start: date
    ) -> InstantiateResult:
        """Szablon tygodnia → 7 dni planu od poniedziałku (jedna transakcja)."""
        if not is_week_start(week_start):
            raise PlanValidationError(NOT_A_MONDAY, details={"week_start": week_start.isoformat()})

        template = await _WEEK_TEMPLATES.get_or_404(self._session, template_id, user)
        content = _load_week(template.payload)
        warnings = await self._assert_references_alive(user, [entry.day for entry in content.days])

        touched = await self._append_week(
            user, content, week_start=week_start, scope=template.scope
        )
        await self._session.commit()

        days = [await self._planning.get_day(user, target) for target in touched]
        return InstantiateResult(days=days, warnings=warnings)

    # --- cykle -----------------------------------------------------------------------

    async def list_cycles(self, user: User) -> list[CycleView]:
        rows = (
            (
                await self._session.execute(
                    _CYCLES.select_visible(user).order_by(WeekCycle.name, WeekCycle.id)
                )
            )
            .scalars()
            .all()
        )
        names = await self._week_template_names(
            {template_id for cycle in rows for template_id in cycle.template_ids}
        )
        return [
            CycleView(
                cycle=cycle,
                template_names=[names.get(template_id) for template_id in cycle.template_ids],
            )
            for cycle in rows
        ]

    async def create_cycle(self, *, user: User, payload: CycleWriteRequest) -> CycleView:
        await self._assert_templates_visible(user, payload.template_ids)
        cycle = WeekCycle(
            name=payload.name,
            template_ids=list(payload.template_ids),
            start_date=payload.start_date,
            **ScopedQuery.ownership_for_create(user, payload.scope),
        )
        self._session.add(cycle)
        await self._session.commit()
        return await self._cycle_view(cycle)

    async def update_cycle(
        self, cycle_id: int, *, user: User, payload: CycleWriteRequest
    ) -> CycleView:
        cycle = await _CYCLES.get_or_404(self._session, cycle_id, user)
        await self._assert_templates_visible(user, payload.template_ids)
        self._apply_common_fields(cycle, name=payload.name, scope=payload.scope, user=user)
        cycle.template_ids = list(payload.template_ids)
        cycle.start_date = payload.start_date
        await self._session.commit()
        return await self._cycle_view(cycle)

    async def delete_cycle(self, cycle_id: int, *, user: User) -> None:
        cycle = await _CYCLES.get_or_404(self._session, cycle_id, user)
        _CYCLES.assert_can_manage(cycle, user)
        await self._session.execute(delete(WeekCycle).where(WeekCycle.id == cycle.id))
        await self._session.commit()

    async def apply_cycle(
        self, cycle_id: int, *, user: User, payload: CycleApplyRequest
    ) -> InstantiateResult:
        """Rotacyjna instancjacja szablonów cyklu na zakres dat — JEDNA transakcja.

        `date_from` musi być poniedziałkiem: cykl operuje tygodniami, a „zastosuj
        od środy" nie ma jednoznacznego znaczenia (czy środa to dzień 1 tygodnia A,
        czy dzień 3?). Zamiast zgadywać — 422 z prośbą o poniedziałek.

        Ostatni tydzień zakresu może być niepełny: instancjujemy z niego tylko dni
        mieszczące się w `date_to` (karta B07 §Backend).
        """
        if not is_week_start(payload.date_from):
            raise PlanValidationError(
                NOT_A_MONDAY, details={"date_from": payload.date_from.isoformat()}
            )

        cycle = await _CYCLES.get_or_404(self._session, cycle_id, user)
        # ISTNIENIE i widoczność szablonów sprawdzamy dla CAŁEJ listy cyklu, także
        # dla tygodni poza zakresem: cykl z martwym id jest po prostu zepsuty i lepiej
        # powiedzieć to wprost, niż zinstancjonować „część cyklu" i milczeć. Nie da
        # się tu wpaść normalną ścieżką (`delete_week_template` zwraca 409, gdy
        # szablon jest w cyklu) — pułapka czeka na import transferu B14, który
        # przepisuje `template_ids` bez FK. Węższa jest walidacja REFERENCJI
        # W PAYLOADACH (niżej): tam liczą się tylko szablony faktycznie użyte.
        templates = await self._week_templates_by_id(user, cycle.template_ids)
        missing = [
            template_id for template_id in cycle.template_ids if template_id not in templates
        ]
        if missing:
            raise PlanValidationError(
                CYCLE_TEMPLATES_UNKNOWN, details={"template_ids": sorted(missing)}
            )

        week_plan = cycle_week_plan(
            list(cycle.template_ids), cycle.start_date, payload.date_from, payload.date_to
        )

        # PAYLOADY czytamy WYŁĄCZNIE z szablonów, które faktycznie wypadają w tym
        # zakresie. Cykl [A, B, C] zastosowany na jeden tydzień używa tylko A, więc
        # zarchiwizowany przepis w C nie ma prawa zablokować całej operacji ani
        # dorzucić ostrzeżenia o pozycji, która nigdy nie trafi do planu
        # (/code-review B07). To NIE to samo, co sprawdzenie istnienia samych
        # szablonów wyżej — tam zakres jest szerszy z rozmysłem.
        used_template_ids = {template_id for _week, template_id in week_plan}
        contents = {
            template_id: _load_week(templates[template_id].payload)
            for template_id in used_template_ids
        }
        warnings = await self._assert_references_alive(
            user, [entry.day for content in contents.values() for entry in content.days]
        )

        touched: list[date] = []
        for week_start, template_id in week_plan:
            touched.extend(
                await self._append_week(
                    user,
                    contents[template_id],
                    week_start=week_start,
                    scope=templates[template_id].scope,
                    date_to=payload.date_to,
                    date_from=payload.date_from,
                )
            )
        await self._session.commit()

        ordered = sorted(set(touched))
        days = [await self._planning.get_day(user, target) for target in ordered]
        return InstantiateResult(days=days, warnings=warnings)

    # --- pomocnicze: budowa payloadu -------------------------------------------------

    async def _day_payload_for(
        self, user: User, payload: DayTemplateWriteRequest
    ) -> DayTemplatePayload:
        """Payload z żądania albo zbudowany z dnia planu (`from_date`).

        Payload podany WPROST jest wejściem użytkownika, więc referencje
        sprawdzamy już przy zapisie (fail fast) — instancjacja i tak zrobi to
        ponownie, bo widoczność mogła się w międzyczasie zmienić.
        """
        if payload.payload is not None:
            await self._assert_references_alive(user, [payload.payload])
            return payload.payload

        assert payload.from_date is not None  # gwarantuje walidator schematu
        content = await self._day_payload_from_plan(user, payload.from_date)
        if not content.meals:
            raise PlanValidationError(
                SOURCE_DAY_EMPTY, details={"from_date": payload.from_date.isoformat()}
            )
        return content

    async def _day_payload_from_plan(self, user: User, day: date) -> DayTemplatePayload:
        """Dzień planu → payload. Ta sama reguła rozstrzygania dnia, co w `/plan/*`."""
        day_entity = await self._planning.resolve_day(user, day)
        if day_entity is None:
            return DayTemplatePayload()
        meals = await self._planning.meals_of(day_entity.id)
        return await self._planning.day_payload_from_meals(meals, title=day_entity.title)

    async def _week_payload_for(
        self, user: User, payload: WeekTemplateWriteRequest
    ) -> WeekTemplatePayload:
        """Jak `_day_payload_for` — payload wprost jest walidowany od razu."""
        if payload.payload is not None:
            await self._assert_references_alive(user, [entry.day for entry in payload.payload.days])
            return payload.payload

        assert payload.from_week_start is not None
        if not is_week_start(payload.from_week_start):
            raise PlanValidationError(
                NOT_A_MONDAY, details={"from_week_start": payload.from_week_start.isoformat()}
            )

        days = []
        for offset in range(DAYS_PER_WEEK):
            content = await self._day_payload_from_plan(
                user, payload.from_week_start + timedelta(days=offset)
            )
            if content.meals:
                # Puste dni pomijamy: szablon tygodnia z pustą środą ma po prostu
                # nie mieć środy, a nie dokładać do planu pustego dnia.
                days.append({"offset": offset, "day": content})

        if not days:
            raise PlanValidationError(
                SOURCE_WEEK_EMPTY,
                details={"from_week_start": payload.from_week_start.isoformat()},
            )
        return WeekTemplatePayload.model_validate({"v": 1, "days": days})

    async def _append_week(
        self,
        user: User,
        content: WeekTemplatePayload,
        *,
        week_start: date,
        scope: Scope,
        date_to: date | None = None,
        date_from: date | None = None,
    ) -> list[date]:
        """Dopisz dni szablonu tygodnia; zwróć daty, które faktycznie dotknięto.

        `date_from`/`date_to` obcinają niepełny tydzień na krańcach zakresu apply
        cyklu — bez nich „zastosuj do piątku" dosypałoby jeszcze sobotę i niedzielę.
        """
        touched: list[date] = []
        for entry in sorted(content.days, key=lambda row: row.offset):
            target = week_start + timedelta(days=entry.offset)
            if date_from is not None and target < date_from:
                continue
            if date_to is not None and target > date_to:
                continue
            await self._planning.append_day_payload(user, target, entry.day, scope=scope)
            touched.append(target)
        return touched

    # --- pomocnicze: walidacja referencji --------------------------------------------

    async def _assert_references_alive(
        self, user: User, contents: Sequence[DayTemplatePayload]
    ) -> list[str]:
        """Nieznany/niewidoczny przepis ⇒ 422; zarchiwizowany ⇒ ostrzeżenie.

        Payload trzyma same identyfikatory, więc szablon MOŻE się rozjechać ze
        słownikiem — przez import transferu (B14) albo usunięcie wykonane, gdy
        szablon jeszcze nie istniał. Instancjacja z martwym id padłaby na FK
        RESTRICT `plan_meal_items` gołym 500, a archiwalny przepis jest legalny,
        tylko wart wzmianki.

        **Przepisy sprawdzamy PRZEZ SCOPE, nie przez samo istnienie.** Payload
        przychodzi od użytkownika, więc bez filtru widoczności byłby ścieżką
        obejścia `ScopedQuery`: wystarczyłoby wpisać `recipe_id` cudzego
        prywatnego przepisu, zinstancjonować szablon i odczytać nazwę oraz
        wartości odżywcze z `GET /plan/days` (`RecipesService.portion_values`
        świadomie nie filtruje scope — widoczność pilnuje strona zapisu, tak jak
        w `add_item`). Cudzy i nieistniejący przepis dają IDENTYCZNY komunikat,
        więc endpoint nie jest też oracle'em istnienia.

        Produkty kanoniczne są słownikiem GLOBALNYM (04_API §2: odczyt dla
        każdego zalogowanego), więc tam wystarcza sprawdzenie istnienia.
        """
        recipe_ids = {
            item.recipe_id
            for content in contents
            for meal in content.meals
            for item in meal.items
            if item.recipe_id is not None
        }
        product_ids = {
            item.product_id
            for content in contents
            for meal in content.meals
            for item in meal.items
            if item.product_id is not None
        }

        warnings: list[str] = []
        if recipe_ids:
            rows = (
                await self._session.execute(
                    select(Recipe.id, Recipe.name, Recipe.is_archived).where(
                        Recipe.id.in_(recipe_ids),
                        _VISIBLE_RECIPES.visible_condition(user),
                    )
                )
            ).all()
            found = {int(row[0]) for row in rows}
            if missing := sorted(recipe_ids - found):
                raise PlanValidationError(DEAD_RECIPES, details={"recipe_ids": missing})
            warnings.extend(
                f"Przepis „{row[1]}” jest zarchiwizowany, ale trafił do planu."
                for row in rows
                if row[2]
            )

        if product_ids:
            rows = (
                await self._session.execute(
                    select(
                        CanonicalProduct.id, CanonicalProduct.name, CanonicalProduct.is_archived
                    ).where(CanonicalProduct.id.in_(product_ids))
                )
            ).all()
            found = {int(row[0]) for row in rows}
            if missing := sorted(product_ids - found):
                raise PlanValidationError(DEAD_PRODUCTS, details={"product_ids": missing})
            warnings.extend(
                f"Produkt „{row[1]}” jest zarchiwizowany, ale trafił do planu."
                for row in rows
                if row[2]
            )

        return warnings

    async def _assert_templates_visible(self, user: User, template_ids: Sequence[int]) -> None:
        """Cykl może wskazywać wyłącznie szablony widoczne dla użytkownika (anty-IDOR)."""
        templates = await self._week_templates_by_id(user, template_ids)
        if missing := sorted(set(template_ids) - set(templates)):
            raise PlanValidationError(CYCLE_TEMPLATES_UNKNOWN, details={"template_ids": missing})

    async def _week_templates_by_id(
        self, user: User, template_ids: Sequence[int]
    ) -> dict[int, WeekTemplate]:
        if not template_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    _WEEK_TEMPLATES.select_visible(user).where(
                        WeekTemplate.id.in_(set(template_ids))
                    )
                )
            )
            .scalars()
            .all()
        )
        return {template.id: template for template in rows}

    async def _week_template_names(self, template_ids: set[int]) -> dict[int, str]:
        if not template_ids:
            return {}
        rows = (
            await self._session.execute(
                select(WeekTemplate.id, WeekTemplate.name).where(WeekTemplate.id.in_(template_ids))
            )
        ).all()
        return {int(row[0]): row[1] for row in rows}

    async def _cycles_using_template(self, template_id: int) -> list[UsedInRef]:
        """Cykle zawierające szablon — `template_ids` to tablica, więc containment `@>`.

        `contains([id])` daje `template_ids @> ARRAY[id]`; wariant z `ANY` też by
        działał, ale nie przechodzi typowania (`PropComparator.any` oczekuje
        kryterium relacji, nie wartości elementu tablicy).
        """
        rows = (
            await self._session.execute(
                select(WeekCycle.id, WeekCycle.name)
                .where(WeekCycle.template_ids.contains([template_id]))
                .order_by(WeekCycle.name, WeekCycle.id)
                .limit(USED_IN_LIMIT)
            )
        ).all()
        return [UsedInRef(type="week_cycle", id=int(row[0]), name=row[1]) for row in rows]

    async def _cycle_view(self, cycle: WeekCycle) -> CycleView:
        names = await self._week_template_names(set(cycle.template_ids))
        return CycleView(
            cycle=cycle,
            template_names=[names.get(template_id) for template_id in cycle.template_ids],
        )

    def _apply_common_fields(
        self, entity: DayTemplate | WeekTemplate | WeekCycle, *, name: str, scope: Scope, user: User
    ) -> None:
        """Nazwa + widoczność. Zmiana scope wymaga właściciela/ADMIN-a (02_DOMAIN §3.1)."""
        entity.name = name
        if scope is not entity.scope:
            if isinstance(entity, DayTemplate):
                _DAY_TEMPLATES.assert_can_manage(entity, user)
            elif isinstance(entity, WeekTemplate):
                _WEEK_TEMPLATES.assert_can_manage(entity, user)
            else:
                _CYCLES.assert_can_manage(entity, user)
            ScopedQuery.assert_scope_allowed(user, scope)
            if scope is Scope.HOUSEHOLD and entity.household_id is None:
                entity.household_id = user.household_id
            entity.scope = scope


# --- payload: serializacja do JSONB i z powrotem -------------------------------------


def _dump(content: DayTemplatePayload | WeekTemplatePayload) -> dict[str, Any]:
    """Payload → JSONB. `mode="json"` zamienia Decimale na STRINGI (ADR-008).

    To nie kosmetyka: `json` zapisałby Decimal jako float i „0.30" wróciłoby
    z bazy jako 0.29999999999999998, cicho psując ilości w szablonie.
    """
    return content.model_dump(mode="json")


def _load_day(raw: Any) -> DayTemplatePayload:
    """JSONB → payload dnia (walidacja kontraktu `v:1` również przy ODCZYCIE)."""
    return DayTemplatePayload.model_validate(raw)


def _load_week(raw: Any) -> WeekTemplatePayload:
    return WeekTemplatePayload.model_validate(raw)


def day_summary(content: DayTemplatePayload) -> str:
    """Podpowiedź na liście szablonów dnia („3 posiłki, 7 pozycji")."""
    meals = len(content.meals)
    items = sum(len(meal.items) for meal in content.meals)
    meals_text = _plural(meals, "posiłek", "posiłki", "posiłków")
    items_text = _plural(items, "pozycja", "pozycje", "pozycji")
    return f"{meals} {meals_text}, {items} {items_text}"


def week_summary(content: WeekTemplatePayload) -> str:
    """Podpowiedź na liście szablonów tygodnia („5 dni, 14 posiłków")."""
    days = len(content.days)
    meals = sum(len(entry.day.meals) for entry in content.days)
    days_text = _plural(days, "dzień", "dni", "dni")
    meals_text = _plural(meals, "posiłek", "posiłki", "posiłków")
    return f"{days} {days_text}, {meals} {meals_text}"


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Polska odmiana liczebnika — „1 posiłek", „2 posiłki", „5 posiłków"."""
    if count == 1:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


# --- zliczanie referencji w payloadach JSONB (ADR-012) ------------------------------
#
# Forma zapytania jest WYBOREM WIĄŻĄCYM, nie stylistyką: indeks GIN założony
# klasą `jsonb_path_ops` obsługuje wyłącznie operatory `@>`, `@?` i `@@`.
# Containment `@>` z niego korzysta, a np. `payload -> 'meals' @? '...'`
# albo `jsonb_path_exists(payload, ...)` — już nie (funkcja nie jest operatorem
# indeksowanym, więc planner zrobiłby seq scan po wszystkich szablonach).
#
# Kształt wzorca odwzorowuje strukturę payloadu: containment JSONB dopasowuje
# obiekt zawarty na tej samej ścieżce, a elementy tablic sprawdza „którykolwiek",
# więc `{"meals":[{"items":[{"recipe_id": 7}]}]}` pasuje do dowolnego posiłku
# i dowolnej pozycji w payloadzie.


def _day_contains(field: str, entity_id: int) -> dict[str, Any]:
    """Wzorzec containment dla payloadu DNIA."""
    return {"meals": [{"items": [{field: entity_id}]}]}


def _week_contains(field: str, entity_id: int) -> dict[str, Any]:
    """Ten sam wzorzec zagnieżdżony o poziom `days[].day` (payload TYGODNIA)."""
    return {"days": [{"day": _day_contains(field, entity_id)}]}


def _templates_using(
    model: type[DayTemplate] | type[WeekTemplate], pattern: dict[str, Any]
) -> Select[tuple[int, str]]:
    return (
        select(model.id, model.name)
        # `.contains()` na kolumnie JSONB to dokładnie operator `@>` — jedyny
        # containment, który potrafi użyć indeksu `jsonb_path_ops` (ADR-012).
        .where(model.payload.contains(pattern))
        .order_by(model.name, model.id)
        .limit(USED_IN_LIMIT)
    )


async def _references_in_templates(
    session: AsyncSession, field: str, entity_id: int
) -> list[UsedInRef]:
    """Szablony dnia i tygodnia, w których payload wskazuje encję o tym id."""
    references: list[UsedInRef] = []

    day_rows = (
        await session.execute(_templates_using(DayTemplate, _day_contains(field, entity_id)))
    ).all()
    references.extend(
        UsedInRef(type="day_template", id=int(row[0]), name=row[1]) for row in day_rows
    )

    week_rows = (
        await session.execute(_templates_using(WeekTemplate, _week_contains(field, entity_id)))
    ).all()
    references.extend(
        UsedInRef(type="week_template", id=int(row[0]), name=row[1]) for row in week_rows
    )

    return references[:USED_IN_LIMIT]


async def _templates_using_recipe(session: AsyncSession, recipe_id: int) -> Sequence[UsedInRef]:
    """Licznik dla modułu recipes: przepis w payloadzie szablonu blokuje usunięcie.

    Baza NIE pomoże — referencja siedzi w JSONB, więc nie ma tu FK RESTRICT.
    Bez tego licznika DELETE przepisu użytego tylko w szablonie przeszedłby,
    zostawiając szablon wskazujący w pustkę (ADR-012).
    """
    return await _references_in_templates(session, "recipe_id", recipe_id)


async def _templates_using_product(session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
    """To samo dla produktu luzem w payloadzie szablonu."""
    return await _references_in_templates(session, "product_id", product_id)


async def count_template_references(session: AsyncSession, field: str, entity_id: int) -> int:
    """Liczba szablonów wskazujących encję — używane przez testy planu zapytania."""
    total = 0
    for model, pattern in (
        (DayTemplate, _day_contains(field, entity_id)),
        (WeekTemplate, _week_contains(field, entity_id)),
    ):
        total += int(
            (
                await session.execute(
                    select(func.count()).select_from(model).where(model.payload.contains(pattern))
                )
            ).scalar_one()
        )
    return total


# Rejestracja przy imporcie modułu — dokładamy WŁASNE liczniki obok tych z planu
# (`_plans_using_recipe`/`_plans_using_product`), nie ruszając istniejących.
register_recipe_reference_finder(_templates_using_recipe)
register_product_reference_finder(_templates_using_product)
