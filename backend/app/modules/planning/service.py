"""Logika planu dnia: dni, posiłki, pozycje, rozkład rodzinny, kopiowanie.

Granice odpowiedzialności (ADR-008, karta B06):

- **Widoczność** — wyłącznie `ScopedQuery` na `PlanDay` (`_DAYS`). Posiłek
  i pozycja nie mają własnego scope: ich widoczność to widoczność DNIA, więc
  każdy dostęp po zagnieżdżonym id przechodzi łańcuchem
  `item → meal → day → warunek scope` (anty-IDOR, karta B06 §Security).
- **Wartości odżywcze** — liczy silnik B05 z danych podanych przez adapter
  `ProductNutrition` i przez `RecipesService.portion_values`. W bazie nie ma
  ani jednej kolumny z wynikiem (02_DOMAIN §13.2), więc zmiana mnożnika zmienia
  wszystko spójnie (§13.3).
- **Ilości** — produkt luzem przechodzi przez `catalog/units.py` przy zapisie;
  ilość nieprzeliczalna wysadza zapis (422) i nic nie trafia do bazy (§13.1).
- **Rozkład rodzinny** — suma multiplierów musi równać się `servings` pozycji;
  pilnuje tego serwis, bo baza nie widzi całej kolekcji przy pojedynczym INSERT.
- **Blokady usuwania** — moduł rejestruje liczniki referencji do przepisów
  (rejestr B05) i produktów (rejestr B04), żeby DELETE zwracał 409 z czytelną
  listą „Używane w:", a nie goły konflikt FK.

Rozstrzyganie dnia dla daty: najpierw WŁASNY dzień użytkownika, potem widoczny
dzień rodzinny. Reguła jest jedna dla odczytu, dopisywania posiłków i kopiowania
— inaczej ta sama data znaczyłaby co innego w każdej operacji.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deletion import USED_IN_LIMIT, UsedInRef
from app.core.errors import AppError, NotFoundError
from app.core.scope import Scope, ScopedQuery, outside_audience_condition
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, ProductUnitWeight
from app.modules.catalog.nutrition_adapter import measure_for, nutrition_for
from app.modules.catalog.service import register_product_reference_finder
from app.modules.catalog.units import (
    AmountUnit,
    NormalizedAmount,
    ProductMeasure,
    UnitConversionError,
    UnitWeight,
    normalize_amount,
    to_basis_amount,
)
from app.modules.households.models import MemberProfile
from app.modules.households.service import register_household_reference_finder
from app.modules.nutrition.engine import (
    aggregate,
    fit_servings_to_target,
    goal_status,
    ingredient_nutrition,
    round_for_output,
    scale,
)
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.nutrition.service import GoalsService, goal_for_day
from app.modules.nutrition.types import (
    GOAL_NUMERIC_FIELDS,
    ZERO_VALUES,
    GoalStatus,
    GoalThresholds,
    NutritionValues,
    thresholds_from_ui_settings,
)
from app.modules.planning.models import PlanDay, PlanItemServing, PlanMeal, PlanMealItem
from app.modules.planning.schemas import (
    MEALS_PER_DAY_LIMIT,
    DayTemplatePayload,
    ItemCreateRequest,
    ItemUpdateRequest,
    MealCreateRequest,
    MealUpdateRequest,
    PlanCopyRequest,
    PlanServingSplitInput,
    TemplateItemPayload,
    TemplateMealPayload,
    TemplateSplitPayload,
)
from app.modules.planning.sequences import block_copy_sequence
from app.modules.recipes.models import Recipe
from app.modules.recipes.service import (
    RecipePortion,
    RecipesService,
    recipe_visibility_query,
    register_recipe_foreign_use_finder,
    register_recipe_reference_finder,
)

DAY_NOT_FOUND = "Nie znaleziono planu dnia dla tej daty."
MEAL_NOT_FOUND = "Nie znaleziono posiłku."
ITEM_NOT_FOUND = "Nie znaleziono pozycji planu."
RECIPE_NOT_AVAILABLE = (
    "Nie znaleziono przepisu. Odśwież listę przepisów i wybierz pozycję ponownie."
)
PRODUCT_NOT_AVAILABLE = "Nie znaleziono produktu. Odśwież formularz i wybierz produkt ponownie."
AMOUNT_ONLY_FOR_PRODUCT = "Pozycja z przepisem nie ma ilości — steruje nią mnożnik porcji."
MEALS_LIMIT_REACHED = (
    f"Dzień ma już maksymalną liczbę posiłków ({MEALS_PER_DAY_LIMIT}). "
    "Usuń niepotrzebny posiłek albo rozłóż plan na dwa dni."
)
UNKNOWN_PROFILE = (
    "Rozkład porcji wskazuje profil spoza rodziny właściciela planu. "
    "Odśwież listę profili i spróbuj ponownie."
)
DUPLICATE_PROFILE = "Ten sam profil występuje w rozkładzie porcji dwa razy."
MEASURE_KIND_MISMATCH = (
    "ilość zapisano w jednostce niezgodnej z obecnym sposobem liczenia produktu — "
    "popraw pozycję planu"
)
RANGE_REVERSED = "Data „od” nie może być późniejsza niż data „do”."
#: Sufit zakresu `GET /plan/days` — rok planu na raz wystarcza statystykom (B13).
MAX_RANGE_DAYS = 366
RANGE_TOO_LONG = f"Zakres dat jest zbyt szeroki — maksimum {MAX_RANGE_DAYS} dni."

_DAYS = ScopedQuery(PlanDay, not_found_message=DAY_NOT_FOUND)
#: Widoczność przepisu przy DODAWANIU pozycji — ten sam mechanizm, co w recipes.
# Fabryka z recipes: przepis `global` (D32) można dodać do planu dowolnej rodziny.
_VISIBLE_RECIPES = recipe_visibility_query(RECIPE_NOT_AVAILABLE)


class PlanValidationError(AppError):
    """422 — dane pozycji planu są niespójne (nieznany przepis, zły rozkład porcji)."""

    status_code = 422
    code = "validation_error"


# --- widoki (dane zmaterializowane dla warstwy HTTP) ---------------------------------


@dataclass(frozen=True)
class SplitView:
    """Jedna osoba w rozkładzie porcji razem z imieniem profilu."""

    member_profile_id: int
    member_name: str
    multiplier: Decimal


@dataclass(frozen=True)
class ItemView:
    """Pozycja posiłku z policzonymi wartościami (zaokrąglonymi na wyjściu)."""

    item: PlanMealItem
    recipe: RecipePortion | None
    product: CanonicalProduct | None
    split: list[SplitView]
    nutrition: NutritionValues


@dataclass(frozen=True)
class MealView:
    """Posiłek z pozycjami, sumą wartości i statusem wobec własnego celu kcal."""

    meal: PlanMeal
    items: list[ItemView]
    nutrition: NutritionValues
    kcal_status: GoalStatus | None


@dataclass(frozen=True)
class GoalMetric:
    """Trio wartość/cel/delta + status — jeden kafelek widoku 1 (06_UIUX §3.5)."""

    value: Decimal
    target: Decimal | None
    delta: Decimal | None
    status: GoalStatus | None


@dataclass(frozen=True)
class DayView:
    """Dzień planu gotowy do serializacji. `entity=None` = dzień jeszcze nie istnieje."""

    day: date
    entity: PlanDay | None
    meals: list[MealView]
    nutrition: NutritionValues
    goal: UserNutritionGoal | None
    progress: dict[str, GoalMetric]


@dataclass(frozen=True)
class PlanDemandRow:
    """Pozycja planu w postaci potrzebnej silnikowi zakupowemu (karta B10 §Context).

    Ilości są dokładnie takie, jak w bazie: znormalizowane przy zapisie na osi
    PRZECHOWYWANIA produktu (`amount_unit` ∈ g|ml|szt.). Przeliczeniem na
    potrzeby agregacji zajmuje się silnik przez `catalog/units.py` — tutaj nie
    ma żadnej arytmetyki, żeby nie było drugiego miejsca z regułami jednostek.
    """

    item_id: int
    day: date
    meal_name: str
    servings: Decimal
    recipe_id: int | None
    product_id: int | None
    amount: Decimal | None
    amount_unit: AmountUnit | None


@dataclass(frozen=True)
class FitProposal:
    """Propozycja mnożnika porcji — nic nie zapisuje (02_DOMAIN §6)."""

    item: PlanMealItem
    target_kcal: Decimal
    proposed_servings: Decimal
    resulting_nutrition: NutritionValues


class PlanningService:
    """Operacje na planie dnia. Jedyne miejsce I/O modułu planning."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Moduł→moduł wyłącznie przez serwis (CLAUDE.md §4): wartości przepisów
        # bierzemy z publicznego wejścia recipes, cele — z serwisu nutrition.
        self._recipes = RecipesService(session)
        self._goals = GoalsService(session)

    # --- odczyt -------------------------------------------------------------------

    async def list_days(self, user: User, *, date_from: date, date_to: date) -> list[DayView]:
        """Widoczne dni z zakresu (wraz z posiłkami, pozycjami i wartościami).

        Zwracane są WYŁĄCZNIE dni istniejące w bazie — pustych dat nie
        wymyślamy, bo „brak planu" to informacja, a nie pusty obiekt do zapisu.
        """
        if date_from > date_to:
            raise PlanValidationError(RANGE_REVERSED)
        if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
            raise PlanValidationError(RANGE_TOO_LONG)

        resolved = await self._resolved_days(user, date_from=date_from, date_to=date_to)
        return await self._build_days(list(resolved.values()), user, dates=sorted(resolved))

    async def demand_rows(
        self, user: User, *, date_from: date, date_to: date
    ) -> list[PlanDemandRow]:
        """Pozycje planu z zakresu — PUBLICZNE wejście silnika zakupowego (B10).

        Po co osobna metoda, a nie `list_days`: silnik nie potrzebuje wartości
        odżywczych ani rozkładu rodzinnego, a potrzebuje ilości — i nie wolno mu
        czytać `plan_meal_items` samemu (CLAUDE.md §4: moduł→moduł przez serwis).

        Dwie rzeczy są tu wiążące (ustalenia review R2):

        1. **Rozstrzyganie dnia jest TO SAMO co w `list_days`** (własny dzień
           przed widocznym rodzinnym). Zapytanie prosto do `plan_days` po
           zakresie dat policzyłoby zakupy podwójnie, bo ta sama data może mieć
           dwa widoczne wiersze.
        2. **Rozkład rodzinny NIE wchodzi do wyniku**: suma multiplierów jest
           równa `servings`, więc doliczanie go skalowałoby ilości dwa razy
           (02_DOMAIN §13.3).
        3. **Dni bierzemy zbiorem WŁASNYM, nie widocznym** (ustalenie REVIEW R4).
           Zakupy to stan domowy, a nie odczyt: `visible_condition` daje
           ADMIN-owi `true()` (D16), więc lista zakupowa administratora
           powstawałaby z planów WSZYSTKICH rodzin w instancji. To ta sama
           granica, którą R3 postawił po stronie spiżarni
           (`PantryService.receive_purchase` idzie po `select_own_household`,
           nie po widoczności) — bez niej obie strony silnika mówiłyby o innym
           domu. Dla nie-ADMIN-a warunek jest identyczny, więc nic się nie zmienia.

        Liczba zapytań jest stała (dni → posiłki → pozycje), niezależnie od
        rozmiaru zakresu.
        """
        if date_from > date_to:
            raise PlanValidationError(RANGE_REVERSED)
        if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
            raise PlanValidationError(RANGE_TOO_LONG)

        resolved = await self._resolved_days(user, date_from=date_from, date_to=date_to, owned=True)
        if not resolved:
            return []

        days_by_id = {entity.id: entity for entity in resolved.values()}
        meals: dict[int, PlanMeal] = {}
        for meal in (
            (
                await self._session.execute(
                    select(PlanMeal)
                    .where(PlanMeal.plan_day_id.in_(list(days_by_id)))
                    .order_by(PlanMeal.plan_day_id, PlanMeal.position, PlanMeal.id)
                )
            )
            .scalars()
            .all()
        ):
            meals[meal.id] = meal
        if not meals:
            return []

        items = (
            (
                await self._session.execute(
                    select(PlanMealItem)
                    .where(PlanMealItem.plan_meal_id.in_(list(meals)))
                    .order_by(PlanMealItem.plan_meal_id, PlanMealItem.position, PlanMealItem.id)
                )
            )
            .scalars()
            .all()
        )
        rows = [
            PlanDemandRow(
                item_id=item.id,
                day=days_by_id[meals[item.plan_meal_id].plan_day_id].day,
                meal_name=meals[item.plan_meal_id].name,
                recipe_id=item.recipe_id,
                product_id=item.product_id,
                amount=item.amount,
                amount_unit=item.amount_unit,
                servings=item.servings,
            )
            for item in items
        ]
        # Kolejność wyniku jest częścią kontraktu: silnik zakupowy musi być
        # deterministyczny, a plan zapytania PG nie jest gwarancją (ADR-008).
        rows.sort(key=lambda row: (row.day, row.item_id))
        return rows

    async def _resolved_days(
        self, user: User, *, date_from: date, date_to: date, owned: bool = False
    ) -> dict[date, PlanDay]:
        """Po JEDNYM dniu na datę: własny użytkownika przed widocznym rodzinnym.

        Ta sama data może mieć DWA widoczne wiersze `plan_days` (własny i cudzy
        rodzinny), więc `setdefault` po sortowaniu „własny pierwszy" jest tym,
        co czyni `list_days`, `demand_rows` i `_resolve_day` jedną regułą.

        `owned=True` zawęża zbiór do dni NALEŻĄCYCH do użytkownika — patrz
        `_resolve_day`, gdzie stoi uzasadnienie tej granicy.
        """
        rows = (
            (
                await self._session.execute(
                    (_DAYS.select_owned(user) if owned else _DAYS.select_visible(user))
                    .where(PlanDay.day >= date_from, PlanDay.day <= date_to)
                    .order_by(PlanDay.day, (PlanDay.owner_user_id == user.id).desc(), PlanDay.id)
                )
            )
            .scalars()
            .all()
        )
        resolved: dict[date, PlanDay] = {}
        for entity in rows:
            resolved.setdefault(entity.day, entity)
        return resolved

    async def get_day(self, user: User, day: date) -> DayView:
        """Dzień dla daty — własny przed rodzinnym; brak dnia to pusty plan, nie 404."""
        entity = await self._resolve_day(user, day)
        views = await self._build_days([entity] if entity is not None else [], user, dates=[day])
        return views[0]

    # --- dzień --------------------------------------------------------------------

    async def upsert_day(
        self, user: User, day: date, *, title: str | None, scope: Scope
    ) -> DayView:
        """PUT dnia: utworzenie albo aktualizacja tytułu i widoczności.

        Zmiana scope wymaga uprawnień właściciela (`assert_can_manage`); sam
        tytuł to zwykła edycja treści, którą może zrobić każdy członek rodziny
        widzący ten dzień (02_DOMAIN §3.1 pkt 2).
        """
        entity = await self._resolve_day(user, day, for_write=True)
        if entity is None:
            entity = PlanDay(day=day, title=title, **ScopedQuery.ownership_for_create(user, scope))
            self._session.add(entity)
        else:
            if scope is not entity.scope:
                _DAYS.assert_can_manage(entity, user)
                ScopedQuery.assert_scope_allowed(user, scope)
                if scope is Scope.HOUSEHOLD and entity.household_id is None:
                    entity.household_id = user.household_id
                entity.scope = scope
            entity.title = title
        await self._session.commit()
        return await self.get_day(user, day)

    # --- posiłki ------------------------------------------------------------------

    async def create_meal(self, user: User, day: date, payload: MealCreateRequest) -> DayView:
        """Nowy posiłek; dzień powstaje IMPLICITE, gdy jeszcze go nie ma.

        Mniej kliknięć od intencji do efektu (06_UIUX §2): użytkownik chce dodać
        „II śniadanie", a nie najpierw „utworzyć dzień".
        """
        entity = await self._resolve_day(user, day, for_write=True)
        if entity is None:
            entity = PlanDay(day=day, **ScopedQuery.ownership_for_create(user, Scope.PRIVATE))
            self._session.add(entity)
            await self._session.flush()

        count = (
            await self._session.execute(
                select(func.count()).select_from(PlanMeal).where(PlanMeal.plan_day_id == entity.id)
            )
        ).scalar_one()
        if count >= MEALS_PER_DAY_LIMIT:
            raise PlanValidationError(MEALS_LIMIT_REACHED)

        position = (
            payload.position
            if payload.position is not None
            else await self._next_meal_position(entity.id)
        )
        self._session.add(
            PlanMeal(
                plan_day_id=entity.id,
                name=payload.name,
                kcal_target=payload.kcal_target,
                position=position,
            )
        )
        await self._session.commit()
        return await self.get_day(user, day)

    async def update_meal(self, meal_id: int, *, user: User, payload: MealUpdateRequest) -> DayView:
        """Częściowa edycja posiłku (nazwa, cel kcal, kolejność)."""
        meal, day_entity = await self._meal_or_404(meal_id, user)
        if payload.name is not None:
            meal.name = payload.name
        if payload.clear_kcal_target:
            meal.kcal_target = None
        elif payload.kcal_target is not None:
            meal.kcal_target = payload.kcal_target
        if payload.position is not None:
            meal.position = payload.position
        await self._session.commit()
        return await self.get_day(user, day_entity.day)

    async def delete_meal(self, meal_id: int, *, user: User) -> DayView:
        """Usunięcie posiłku razem z pozycjami i rozkładami (kaskada bazy).

        Ostatni posiłek zabiera ze sobą PUSTY dzień — ustalenie REVIEW R3
        (dług U17). Wiersz `plan_days` powstaje implicite przy pierwszym posiłku
        (`_day_for_write`), a po usunięciu wszystkich posiłków UI pokazuje „brak
        planu", więc dzień staje się niewidoczny — ale nadal trzyma
        `household_id` z `ON DELETE RESTRICT` i blokuje usunięcie rodziny bez
        żadnego śladu w interfejsie. Dzień z TYTUŁEM zostaje: tytuł jest jawną
        decyzją użytkownika („Urodziny Zosi"), a nie artefaktem zapisu.
        """
        meal, day_entity = await self._meal_or_404(meal_id, user)
        await self._session.execute(delete(PlanMeal).where(PlanMeal.id == meal.id))
        await self._delete_day_if_empty(day_entity)
        await self._session.commit()
        return await self.get_day(user, day_entity.day)

    async def _delete_day_if_empty(self, day_entity: PlanDay) -> None:
        """Skasuj wiersz dnia, jeśli nic w nim nie zostało z decyzji użytkownika.

        Sprzątamy WYŁĄCZNIE dzień bez posiłków, bez tytułu i z domyślną
        widocznością. Tytuł i `scope='household'` to jawne decyzje — ich cichy
        reset przy usuwaniu posiłku byłby utratą danych, a nie porządkami
        (a dzień udostępniony rodzinie ADMIN zobaczy w `used_in` z datą).
        """
        if day_entity.title is not None or day_entity.scope is not Scope.PRIVATE:
            return
        remaining = (
            await self._session.execute(
                select(func.count())
                .select_from(PlanMeal)
                .where(PlanMeal.plan_day_id == day_entity.id)
            )
        ).scalar_one()
        if int(remaining) == 0:
            await self._session.execute(delete(PlanDay).where(PlanDay.id == day_entity.id))

    # --- pozycje ------------------------------------------------------------------

    async def add_item(self, meal_id: int, *, user: User, payload: ItemCreateRequest) -> DayView:
        """Pozycja z przepisu (mnożnik porcji) albo produkt luzem (ilość → ADR-005)."""
        meal, day_entity = await self._meal_or_404(meal_id, user)

        amount: Decimal | None = None
        amount_unit = None
        if payload.recipe_id is not None:
            await self._assert_recipe_available(payload.recipe_id, user)
        else:
            assert payload.product_id is not None  # gwarantuje walidator schematu
            assert payload.quantity is not None
            assert payload.unit is not None
            normalized = await self._normalize_product_amount(
                payload.product_id, payload.quantity, payload.unit
            )
            amount, amount_unit = normalized.amount, normalized.unit

        position = (
            payload.position
            if payload.position is not None
            else await self._next_item_position(meal.id)
        )
        item = PlanMealItem(
            plan_meal_id=meal.id,
            recipe_id=payload.recipe_id,
            product_id=payload.product_id,
            amount=amount,
            amount_unit=amount_unit,
            servings=payload.servings,
            position=position,
        )
        self._session.add(item)
        await self._session.flush()

        await self._replace_split(item, payload.servings_split, day_entity, servings=item.servings)
        await self._session.commit()
        return await self.get_day(user, day_entity.day)

    async def update_item(self, item_id: int, *, user: User, payload: ItemUpdateRequest) -> DayView:
        """Zmiana mnożnika, ilości, kolejności albo rozkładu rodzinnego pozycji."""
        item, _meal, day_entity = await self._item_or_404(item_id, user)

        if payload.quantity is not None and payload.unit is not None:
            if item.product_id is None:
                raise PlanValidationError(AMOUNT_ONLY_FOR_PRODUCT)
            normalized = await self._normalize_product_amount(
                item.product_id, payload.quantity, payload.unit
            )
            item.amount, item.amount_unit = normalized.amount, normalized.unit
        if payload.servings is not None:
            item.servings = payload.servings
        if payload.position is not None:
            item.position = payload.position

        if payload.servings_split is not None:
            await self._replace_split(
                item, payload.servings_split, day_entity, servings=item.servings
            )
        elif payload.servings is not None:
            # Mnożnik zmieniony bez podania rozkładu — istniejący rozkład musi
            # nadal się sumować, inaczej zapis po cichu złamałby niezmiennik.
            await self._assert_existing_split_matches(item)

        await self._session.commit()
        return await self.get_day(user, day_entity.day)

    async def delete_item(self, item_id: int, *, user: User) -> DayView:
        """Usunięcie pozycji razem z jej rozkładem (kaskada bazy)."""
        item, _meal, day_entity = await self._item_or_404(item_id, user)
        await self._session.execute(delete(PlanMealItem).where(PlanMealItem.id == item.id))
        await self._session.commit()
        return await self.get_day(user, day_entity.day)

    async def fit_to_target(self, item_id: int, *, user: User) -> FitProposal:
        """Propozycja mnożnika: cel kcal POSIŁKU / kcal jednej porcji pozycji.

        Endpoint niczego nie zapisuje — zastosowanie propozycji to osobny PATCH
        pozycji, wykonany świadomie przez użytkownika (02_DOMAIN §6, karta B06).
        """
        item, meal, _day = await self._item_or_404(item_id, user)
        per_serving = await self._per_serving_values(item)
        proposed = fit_servings_to_target(meal.kcal_target, per_serving.kcal)
        # mypy: `fit_servings_to_target` rzuca dla braku celu, więc tu jest liczbą.
        assert meal.kcal_target is not None
        return FitProposal(
            item=item,
            target_kcal=meal.kcal_target,
            proposed_servings=proposed,
            resulting_nutrition=round_for_output(scale(per_serving, proposed)),
        )

    # --- kopiowanie ----------------------------------------------------------------

    async def copy(self, *, user: User, payload: PlanCopyRequest) -> list[DayView]:
        """Głęboka kopia dnia albo posiłku na wskazane daty (04_API §2).

        Kopia DOPISUJE się na koniec dnia docelowego: nadpisywanie cudzej pracy
        przy „skopiuj poniedziałek na cały tydzień" byłoby nieodwracalne, a plan
        i tak łatwiej skrócić niż odtworzyć (decyzja z karty B06).
        """
        if payload.what == "day":
            assert payload.source_date is not None  # gwarantuje walidator schematu
            source_day = await self._resolve_day(user, payload.source_date)
            if source_day is None:
                raise NotFoundError(DAY_NOT_FOUND)
            source_meals = await self._meals_of(source_day.id)
        else:
            assert payload.source_meal_id is not None
            meal, source_day = await self._meal_or_404(payload.source_meal_id, user)
            source_meals = [meal]

        blueprint = await self.day_payload_from_meals(
            source_meals, title=source_day.title if payload.what == "day" else None
        )

        targets = sorted(set(payload.target_dates))
        for target in targets:
            await self.append_day_payload(user, target, blueprint, scope=source_day.scope)

        await self._session.commit()
        return [await self.get_day(user, target) for target in targets]

    async def copy_block(self, *, user: User, payload: PlanCopyRequest) -> list[DayView]:
        """Powiel blok N dni z powtórzeniem K (model 2+2+2 z listu dietetyczki).

        Kolejność wyniku to d1,d1,d2,d2,d3,d3 — dieta stosowana „2 dni pod rząd”
        wymaga dni SĄSIADUJĄCYCH, nie przeplotu. Sekwencję liczy czysta funkcja
        `block_copy_sequence`, więc jest testowalna bez bazy.

        Dni źródłowe czytamy RAZ, przed zapisami: gdyby zakres docelowy nachodził
        na źródłowy, czytanie w pętli zobaczyłoby już dopisane posiłki i lawinowo
        by je multiplikowało.
        """
        assert payload.source_from is not None  # gwarantuje walidator schematu
        assert payload.source_days is not None
        assert payload.repeat_each is not None
        assert payload.target_start is not None

        sequence = block_copy_sequence(
            payload.source_from, payload.source_days, payload.repeat_each, payload.target_start
        )

        blueprints: dict[date, tuple[DayTemplatePayload, Scope]] = {}
        for source_date in sorted({source for source, _target in sequence}):
            source_day = await self._resolve_day(user, source_date)
            if source_day is None:
                # Dziura w bloku źródłowym nie jest błędem: „powiel 3 dni” przy
                # pustym środkowym dniu ma dać pusty dzień, nie 404 na całość.
                continue
            meals = await self._meals_of(source_day.id)
            blueprints[source_date] = (
                await self.day_payload_from_meals(meals, title=source_day.title),
                source_day.scope,
            )

        for source_date, target in sequence:
            blueprint = blueprints.get(source_date)
            if blueprint is None:
                continue
            await self.append_day_payload(user, target, blueprint[0], scope=blueprint[1])

        await self._session.commit()
        targets = sorted({target for _source, target in sequence})
        return [await self.get_day(user, target) for target in targets]

    # --- wspólny mechanizm „struktura dnia ↔ wiersze planu” -------------------------

    async def day_payload_from_meals(
        self, meals: Sequence[PlanMeal], *, title: str | None
    ) -> DayTemplatePayload:
        """Wiersze planu → payload `v:1` (kopiowanie, zapis szablonu, eksport B14).

        To JEDYNE miejsce zamieniające plan na payload — kopiowanie i szablony
        muszą widzieć dokładnie tę samą strukturę, inaczej „zapisz jako szablon”
        dawałoby co innego niż „kopiuj dzień”.
        """
        items_by_meal = await self._items_of([meal.id for meal in meals])
        splits_by_item = await self._splits_of(
            [item.id for items in items_by_meal.values() for item in items]
        )
        return day_payload_from_rows(meals, items_by_meal, splits_by_item, title=title)

    async def append_day_payload(
        self,
        user: User,
        target: date,
        payload: DayTemplatePayload,
        *,
        scope: Scope,
    ) -> PlanDay:
        """Payload → wiersze planu, DOPISANE na koniec dnia docelowego.

        NIE commituje — instancjacja tygodnia i apply cyklu robią wiele dni
        w jednej transakcji, więc częściowy wynik nie może zostać w bazie po
        błędzie (karta B07 §Implementation Notes).

        Dzień docelowy powstaje jako własność WYKONUJĄCEGO użytkownika (owner
        z sesji) — nie da się instancjować „na cudzy plan” (karta B07 §Security).
        Tytuł ustawiamy tylko przy TWORZENIU dnia: dopisanie szablonu do dnia,
        który użytkownik już nazwał, nie ma prawa tej nazwy nadpisać.
        """
        day_entity = await self._resolve_day(user, target, for_write=True)
        if day_entity is None:
            day_entity = PlanDay(
                day=target,
                title=payload.title,
                **ScopedQuery.ownership_for_create(user, scope),
            )
            self._session.add(day_entity)
            await self._session.flush()

        allowed_profiles = await self._household_profile_ids(day_entity)
        offset = await self._next_meal_position(day_entity.id)
        for index, meal in enumerate(sorted(payload.meals, key=lambda entry: entry.position)):
            created_meal = PlanMeal(
                plan_day_id=day_entity.id,
                name=meal.name,
                kcal_target=meal.kcal_target,
                position=offset + index,
            )
            self._session.add(created_meal)
            await self._session.flush()

            for item in sorted(meal.items, key=lambda entry: entry.position):
                created_item = PlanMealItem(
                    plan_meal_id=created_meal.id,
                    recipe_id=item.recipe_id,
                    product_id=item.product_id,
                    amount=item.amount,
                    amount_unit=item.amount_unit,
                    servings=item.servings,
                    position=item.position,
                )
                self._session.add(created_item)
                await self._session.flush()

                # Rozklad kopiujemy tylko w komplecie: profil spoza rodziny
                # wlasciciela dnia docelowego zlamalby sume = servings, wiec
                # wtedy zostaje sam mnoznik (kopiowanie miedzy rodzinami).
                split = item.servings_split
                if split and all(row.member_profile_id in allowed_profiles for row in split):
                    for row in split:
                        self._session.add(
                            PlanItemServing(
                                plan_meal_item_id=created_item.id,
                                member_profile_id=row.member_profile_id,
                                multiplier=row.multiplier,
                            )
                        )
        return day_entity

    # --- wejścia publiczne dla szablonów (BATCH_07) ---------------------------------

    async def resolve_day(self, user: User, day: date) -> PlanDay | None:
        """Reguła „dzień dla daty" udostępniona szablonom.

        `TemplatesService` MUSI rozstrzygać datę identycznie jak `/plan/*`
        (najpierw własny dzień, potem widoczny rodzinny) — inaczej ta sama data
        znaczyłaby co innego w widoku tygodnia i w instancjacji szablonu
        (karta B07 §Context).
        """
        return await self._resolve_day(user, day)

    async def meals_of(self, day_id: int) -> list[PlanMeal]:
        """Posiłki dnia w kolejności pozycji — wejście budowy payloadu szablonu."""
        return await self._meals_of(day_id)

    # --- pomocnicze: dostęp z kontrolą scope ----------------------------------------

    async def _resolve_day(
        self, user: User, day: date, *, for_write: bool = False
    ) -> PlanDay | None:
        """Dzień dla daty: WŁASNY przed rodzinnym, potem najstarszy id.

        Jedna reguła dla odczytu, dopisywania i kopiowania — bez niej ta sama
        data znaczyłaby co innego w każdej operacji.

        **`for_write=True` zawęża zbiór z `visible` do `owned` i to NIE jest
        kosmetyka** (ustalenie REVIEW R4). Dzień planu nie ma id w URL-u —
        adresuje go DATA — więc ten resolver jest jednocześnie celem ZAPISU dla
        `upsert_day`, `create_meal` i `append_day_payload`. `visible_condition`
        zwraca ADMIN-owi `true()` (D16), a D16 mówi wprost, że wyjątek dotyczy
        ODCZYTU i „nie rozciąga się na mutacje reguł właścicielskich". Bez tego
        zawężenia ADMIN, który nie ma własnego dnia na daną datę, trafiał
        w NAJSTARSZY wiersz dowolnego użytkownika z dowolnej rodziny: dodanie
        posiłku lądowało w cudzym planie, a `PUT /plan/days/{date}` kasowało mu
        tytuł i przestawiało `scope` na `private`, wypychając dzień z widoku
        jego własnej rodziny. Odtworzone realnie w R4 na działającym stacku.
        Dla nie-ADMIN-a `owned_condition` jest DOKŁADNIE tym samym warunkiem,
        co `visible_condition` (`core/scope.py`), więc członek rodziny nadal
        dopisuje posiłki do wspólnego dnia rodzinnego — reguła z B07 bez zmian.
        """
        rows = (
            (
                await self._session.execute(
                    (_DAYS.select_owned(user) if for_write else _DAYS.select_visible(user))
                    .where(PlanDay.day == day)
                    .order_by((PlanDay.owner_user_id == user.id).desc(), PlanDay.id)
                    .limit(1)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return rows[0] if rows else None

    async def _meal_or_404(self, meal_id: int, user: User) -> tuple[PlanMeal, PlanDay]:
        """Posiłek razem z jego dniem — cudzy albo nieistniejący daje to samo 404."""
        row = (
            await self._session.execute(
                select(PlanMeal, PlanDay)
                .join(PlanDay, PlanDay.id == PlanMeal.plan_day_id)
                .where(PlanMeal.id == meal_id, _DAYS.visible_condition(user))
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError(MEAL_NOT_FOUND)
        return row[0], row[1]

    async def _item_or_404(
        self, item_id: int, user: User
    ) -> tuple[PlanMealItem, PlanMeal, PlanDay]:
        """Pozycja + posiłek + dzień; sprawdzany jest CAŁY łańcuch, nie samo id."""
        row = (
            await self._session.execute(
                select(PlanMealItem, PlanMeal, PlanDay)
                .join(PlanMeal, PlanMeal.id == PlanMealItem.plan_meal_id)
                .join(PlanDay, PlanDay.id == PlanMeal.plan_day_id)
                .where(PlanMealItem.id == item_id, _DAYS.visible_condition(user))
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError(ITEM_NOT_FOUND)
        return row[0], row[1], row[2]

    # --- pomocnicze: zapis ----------------------------------------------------------

    async def _next_meal_position(self, day_id: int) -> int:
        """Kolejna wolna pozycja posiłku — nowy posiłek ląduje na końcu dnia."""
        current = (
            await self._session.execute(
                select(func.max(PlanMeal.position)).where(PlanMeal.plan_day_id == day_id)
            )
        ).scalar_one()
        return 0 if current is None else int(current) + 1

    async def _next_item_position(self, meal_id: int) -> int:
        """Kolejna wolna pozycja w posiłku — nowa pozycja ląduje na końcu listy."""
        current = (
            await self._session.execute(
                select(func.max(PlanMealItem.position)).where(PlanMealItem.plan_meal_id == meal_id)
            )
        ).scalar_one()
        return 0 if current is None else int(current) + 1

    async def _assert_recipe_available(self, recipe_id: int, user: User) -> None:
        """Przepis musi być widoczny dla dodającego — inaczej 422 z komunikatem PL."""
        found = (
            await self._session.execute(
                _VISIBLE_RECIPES.select_visible(user).where(Recipe.id == recipe_id)
            )
        ).scalar_one_or_none()
        if found is None:
            raise PlanValidationError(RECIPE_NOT_AVAILABLE, details={"recipe_id": recipe_id})

    async def _normalize_product_amount(
        self, product_id: int, quantity: Decimal, unit: str
    ) -> NormalizedAmount:
        """Ilość użytkownika → oś produktu (ADR-005); nieprzeliczalna = 422 i brak zapisu."""
        product = await self._session.get(CanonicalProduct, product_id)
        if product is None:
            raise PlanValidationError(PRODUCT_NOT_AVAILABLE, details={"product_id": product_id})

        weights = (
            (
                await self._session.execute(
                    select(ProductUnitWeight).where(ProductUnitWeight.product_id == product_id)
                )
            )
            .scalars()
            .all()
        )
        # `measure_for` przyjmuje dataclassy `UnitWeight`, nie wiersze ORM —
        # przepakowanie jest obowiązkiem serwisu (ustalenie review R1).
        measure = measure_for(
            product,
            [
                UnitWeight(unit_label=row.unit_label, grams_per_unit=row.grams_per_unit)
                for row in weights
            ],
        )
        try:
            return normalize_amount(quantity, unit, measure)
        except UnitConversionError as exc:
            raise UnitConversionError(
                f"„{product.name}”: {exc.message}",
                details={"product_id": product.id, "unit": unit, **exc.details},
            ) from exc

    async def _replace_split(
        self,
        item: PlanMealItem,
        split: Sequence[PlanServingSplitInput],
        day_entity: PlanDay,
        *,
        servings: Decimal,
    ) -> None:
        """Podmień rozkład rodzinny kompletem, pilnując sumy = `servings`.

        Suma porównywana jest na `Decimal` DOKŁADNIE (przykład z 02_DOMAIN §7:
        3x1,0 + 2x0,8 + 2x1,3 = 6,2). Na floatach ta suma nie byłaby równa 6,2
        i walidacja odrzucałaby poprawne dane.
        """
        await self._session.execute(
            delete(PlanItemServing).where(PlanItemServing.plan_meal_item_id == item.id)
        )
        if not split:
            return

        profile_ids = [row.member_profile_id for row in split]
        assert_unique_profiles(profile_ids)

        allowed = await self._household_profile_ids(day_entity)
        unknown = sorted(set(profile_ids) - allowed)
        if unknown:
            # Nie ujawniamy, czy taki profil w ogóle istnieje (karta B06 §Security).
            raise PlanValidationError(UNKNOWN_PROFILE, details={"member_profile_ids": unknown})

        assert_split_matches_servings([row.multiplier for row in split], servings)

        for row in split:
            self._session.add(
                PlanItemServing(
                    plan_meal_item_id=item.id,
                    member_profile_id=row.member_profile_id,
                    multiplier=row.multiplier,
                )
            )

    async def _assert_existing_split_matches(self, item: PlanMealItem) -> None:
        """Po zmianie samego mnożnika istniejący rozkład musi nadal się sumować."""
        rows = (
            (
                await self._session.execute(
                    select(PlanItemServing).where(PlanItemServing.plan_meal_item_id == item.id)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return
        assert_split_matches_servings([row.multiplier for row in rows], item.servings)

    async def _household_profile_ids(self, day_entity: PlanDay) -> set[int]:
        """Profile członków rodziny WŁAŚCICIELA dnia — jedyny dozwolony zbiór rozkładu."""
        if day_entity.household_id is None:
            return set()
        rows = (
            await self._session.execute(
                select(MemberProfile.id).where(
                    MemberProfile.household_id == day_entity.household_id
                )
            )
        ).scalars()
        return set(rows)

    # --- pomocnicze: odczyt zbiorczy -------------------------------------------------

    async def _meals_of(self, day_id: int) -> list[PlanMeal]:
        rows = (
            (
                await self._session.execute(
                    select(PlanMeal)
                    .where(PlanMeal.plan_day_id == day_id)
                    .order_by(PlanMeal.position, PlanMeal.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _items_of(self, meal_ids: Sequence[int]) -> dict[int, list[PlanMealItem]]:
        grouped: dict[int, list[PlanMealItem]] = {meal_id: [] for meal_id in meal_ids}
        if not meal_ids:
            return grouped
        for item in (
            (
                await self._session.execute(
                    select(PlanMealItem)
                    .where(PlanMealItem.plan_meal_id.in_(meal_ids))
                    .order_by(PlanMealItem.position, PlanMealItem.id)
                )
            )
            .scalars()
            .all()
        ):
            grouped[item.plan_meal_id].append(item)
        return grouped

    async def _splits_of(self, item_ids: Sequence[int]) -> dict[int, list[PlanItemServing]]:
        grouped: dict[int, list[PlanItemServing]] = {item_id: [] for item_id in item_ids}
        if not item_ids:
            return grouped
        for row in (
            (
                await self._session.execute(
                    select(PlanItemServing)
                    .where(PlanItemServing.plan_meal_item_id.in_(item_ids))
                    .order_by(PlanItemServing.id)
                )
            )
            .scalars()
            .all()
        ):
            grouped[row.plan_meal_item_id].append(row)
        return grouped

    async def _per_serving_values(self, item: PlanMealItem) -> NutritionValues:
        """Wartości JEDNEJ porcji pozycji (bez mnożnika) — wejście „dopasuj do celu"."""
        if item.recipe_id is not None:
            portions = await self._recipes.portion_values([item.recipe_id])
            portion = portions.get(item.recipe_id)
            return ZERO_VALUES if portion is None else portion.portion

        product = await self._session.get(CanonicalProduct, item.product_id)
        if product is None:  # pragma: no cover — chroni FK RESTRICT
            return ZERO_VALUES
        return _product_values(item, product)

    # --- pomocnicze: budowa widoków ---------------------------------------------------

    async def _build_days(
        self, days: Sequence[PlanDay], user: User, *, dates: Sequence[date]
    ) -> list[DayView]:
        """Dni → widoki: stała liczba zapytań i JEDNO przejście silnikiem (karta B06)."""
        by_date = {entity.day: entity for entity in days}

        meals_by_day: dict[int, list[PlanMeal]] = {entity.id: [] for entity in days}
        if days:
            for meal in (
                (
                    await self._session.execute(
                        select(PlanMeal)
                        .where(PlanMeal.plan_day_id.in_([entity.id for entity in days]))
                        .order_by(PlanMeal.position, PlanMeal.id)
                    )
                )
                .scalars()
                .all()
            ):
                meals_by_day[meal.plan_day_id].append(meal)

        meal_ids = [meal.id for meals in meals_by_day.values() for meal in meals]
        items_by_meal = await self._items_of(meal_ids)
        items = [item for group in items_by_meal.values() for item in group]
        splits_by_item = await self._splits_of([item.id for item in items])

        portions = await self._recipes.portion_values(
            [item.recipe_id for item in items if item.recipe_id is not None]
        )
        products = await self._products_by_id(
            {item.product_id for item in items if item.product_id is not None}
        )
        profiles = await self._profiles_by_id(
            {row.member_profile_id for rows in splits_by_item.values() for row in rows}
        )

        goals = await self._goals.goals_of(user.id)
        thresholds = thresholds_from_ui_settings(user.ui_settings)

        views: list[DayView] = []
        for day in sorted(dates):
            entity = by_date.get(day)
            meal_views: list[MealView] = []
            meal_raw: list[NutritionValues] = []
            for meal in meals_by_day.get(entity.id, []) if entity is not None else []:
                item_views: list[ItemView] = []
                item_raw: list[NutritionValues] = []
                for item in items_by_meal.get(meal.id, []):
                    values = _item_values(item, portions, products)
                    item_raw.append(values)
                    item_views.append(
                        ItemView(
                            item=item,
                            recipe=portions.get(item.recipe_id) if item.recipe_id else None,
                            product=products.get(item.product_id) if item.product_id else None,
                            split=[
                                SplitView(
                                    member_profile_id=row.member_profile_id,
                                    member_name=profiles.get(row.member_profile_id, "—"),
                                    multiplier=row.multiplier,
                                )
                                for row in splits_by_item.get(item.id, [])
                            ],
                            nutrition=round_for_output(values),
                        )
                    )

                total = aggregate(item_raw)
                meal_raw.append(total)
                rounded = round_for_output(total)
                meal_views.append(
                    MealView(
                        meal=meal,
                        items=item_views,
                        nutrition=rounded,
                        kcal_status=goal_status(rounded.kcal, meal.kcal_target, thresholds),
                    )
                )

            day_total = round_for_output(aggregate(meal_raw))
            goal = goal_for_day(goals, day)
            views.append(
                DayView(
                    day=day,
                    entity=entity,
                    meals=meal_views,
                    nutrition=day_total,
                    goal=goal,
                    progress=_progress(day_total, goal, thresholds),
                )
            )
        return views

    async def _products_by_id(self, product_ids: set[int]) -> dict[int, CanonicalProduct]:
        if not product_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    select(CanonicalProduct).where(CanonicalProduct.id.in_(product_ids))
                )
            )
            .scalars()
            .all()
        )
        return {product.id: product for product in rows}

    async def _profiles_by_id(self, profile_ids: set[int]) -> dict[int, str]:
        if not profile_ids:
            return {}
        rows = (
            await self._session.execute(
                select(MemberProfile.id, MemberProfile.name).where(
                    MemberProfile.id.in_(profile_ids)
                )
            )
        ).all()
        return {int(row[0]): str(row[1]) for row in rows}


# --- czyste funkcje pomocnicze ----------------------------------------------------------


def _plain(value: Decimal) -> str:
    """`Decimal` w komunikacie błędu bez notacji wykładniczej (jak `DecimalString`)."""
    return format(value, "f")


def assert_unique_profiles(profile_ids: Sequence[int]) -> None:
    """Ten sam profil nie może wystąpić w rozkładzie dwa razy (czysta reguła)."""
    if len(set(profile_ids)) != len(profile_ids):
        raise PlanValidationError(DUPLICATE_PROFILE)


def assert_split_matches_servings(multipliers: Sequence[Decimal], servings: Decimal) -> None:
    """Suma mnożników rozkładu MUSI równać się `servings` pozycji (02_DOMAIN §7).

    Przykład z dokumentu: 3x1,0 + 2x0,8 + 2x1,3 = 6,2 porcji. Porównanie jest
    DOKŁADNE i na `Decimal` — na floatach ta suma wyszłaby 6,199999999999999
    i walidacja odrzucałaby poprawne dane (ADR-008).

    Czysta funkcja (bez I/O), bo to jedyna reguła tego modułu, którą warto
    sprawdzić testem jednostkowym bez bazy (karta B06 §Tests).
    """
    total = sum(multipliers, Decimal("0"))
    if total != servings:
        raise PlanValidationError(
            "Suma mnożników w rozkładzie porcji musi równać się liczbie porcji pozycji "
            f"({_plain(servings)}). Teraz wynosi {_plain(total)}.",
            details={"expected": _plain(servings), "actual": _plain(total)},
        )


def _product_values(item: PlanMealItem, product: CanonicalProduct) -> NutritionValues:
    """Wartości JEDNEJ porcji pozycji z produktem luzem (bez mnożnika porcji).

    Gdy `measure_kind` produktu zmieniono PO zapisaniu pozycji, stara ilość może
    nie dać się sprowadzić na nową oś „na 100" — wtedy pozycja nie wnosi wartości,
    a wynik dostaje `complete=False` z czytelnym komunikatem (zamiast 500 na
    odczycie). Ten sam wzorzec, co `recipes/service.py::_ingredient_values`.
    """

    assert item.amount is not None and item.amount_unit is not None  # CHECK w bazie
    measure = ProductMeasure(
        measure_kind=product.measure_kind, piece_weight_g=product.piece_weight_g
    )
    try:
        basis_amount = to_basis_amount(NormalizedAmount(item.amount, item.amount_unit), measure)
    except UnitConversionError:
        return replace(
            ZERO_VALUES,
            complete=False,
            missing=(f"{product.name}: {MEASURE_KIND_MISMATCH}",),
        )
    return ingredient_nutrition(basis_amount, nutrition_for(product))


def _item_values(
    item: PlanMealItem,
    portions: dict[int, RecipePortion],
    products: dict[int, CanonicalProduct],
) -> NutritionValues:
    """Wartości pozycji = wartości jednej porcji x mnożnik (02_DOMAIN §6 i §13.3).

    Dla przepisu „porcja" to porcja bazowa przepisu, dla produktu luzem —
    zapisana ilość. Mnożnik działa w obu przypadkach tak samo, bo inaczej
    zmiana mnożnika nie zmieniałaby „wszystkiego spójnie".
    """
    if item.recipe_id is not None:
        portion = portions.get(item.recipe_id)
        if portion is None:  # pragma: no cover — chroni FK RESTRICT
            return ZERO_VALUES
        return scale(portion.portion, item.servings)

    product = products.get(item.product_id) if item.product_id is not None else None
    if product is None:  # pragma: no cover — chroni FK RESTRICT
        return ZERO_VALUES
    return scale(_product_values(item, product), item.servings)


def _progress(
    values: NutritionValues, goal: UserNutritionGoal | None, thresholds: GoalThresholds
) -> dict[str, GoalMetric]:
    """Kafelki wartość/cel/delta/status dla kcal i trzech makroskładników.

    Lista pól przychodzi z `nutrition/types.GOAL_NUMERIC_FIELDS` — jedno źródło
    dla kafelków planu dnia i dla statusów statystyk (dług zgłoszony w BATCH_13,
    domknięty w REVIEW R4). Nazwa pola wyniku i nazwa pola celu są tu ZAWSZE
    identyczne, więc mapa par była tylko drugą kopią tej samej prawdy.
    """
    progress: dict[str, GoalMetric] = {}
    for field in GOAL_NUMERIC_FIELDS:
        value = getattr(values, field)
        target = None if goal is None else getattr(goal, field)
        progress[field] = GoalMetric(
            value=value,
            target=target,
            delta=None if target is None else value - target,
            status=goal_status(value, target, thresholds),
        )
    return progress


# --- wiersze planu -> payload szablonu (czysta funkcja, BATCH_07) -------------------


def day_payload_from_rows(
    meals: Sequence[PlanMeal],
    items_by_meal: dict[int, list[PlanMealItem]],
    splits_by_item: dict[int, list[PlanItemServing]],
    *,
    title: str | None,
) -> DayTemplatePayload:
    """Struktura dnia jako payload `v:1` — bez dat i bez ani jednej wartości odżywczej.

    Payload jest ZAMROŻONĄ KOPIĄ STRUKTURY (02_DOMAIN §7): kopiujemy `recipe_id`
    i `product_id` jako referencje, a nie policzone kcal. Liczby powstają przy
    odczycie planu, więc szablon zapisany dziś i użyty za miesiąc uwzględni
    poprawione wartości produktu (niezmiennik 02_DOMAIN §13.2).

    `servings` jedzie razem z ilością również dla produktu luzem: wartości
    pozycji to „wartości jednej porcji x servings” także tam (02_DOMAIN §13.3),
    więc pominięcie mnożnika zmieniłoby treść szablonu.
    """
    return DayTemplatePayload(
        title=title,
        meals=[
            TemplateMealPayload(
                name=meal.name,
                kcal_target=meal.kcal_target,
                position=position,
                items=[
                    TemplateItemPayload(
                        recipe_id=item.recipe_id,
                        product_id=item.product_id,
                        amount=item.amount,
                        amount_unit=item.amount_unit,
                        servings=item.servings,
                        position=item_position,
                        servings_split=[
                            TemplateSplitPayload(
                                member_profile_id=row.member_profile_id,
                                multiplier=row.multiplier,
                            )
                            for row in splits_by_item.get(item.id, [])
                        ],
                    )
                    for item_position, item in enumerate(items_by_meal.get(meal.id, []))
                ],
            )
            for position, meal in enumerate(meals)
        ],
    )


# --- rejestry blokad usuwania (ADR-012) ---------------------------------------------------


def _day_label(day: date, title: str | None) -> str:
    """Etykieta dnia w liście „Używane w:" — tytuł, a gdy go brak, sama data."""
    return title or f"Plan dnia {day.strftime('%d.%m.%Y')}"


def _used_in_days(rows: Iterable[tuple[int, date, str | None]]) -> list[UsedInRef]:
    return [
        UsedInRef(type="plan_day", id=int(day_id), name=_day_label(day, title))
        for day_id, day, title in rows
    ]


def _days_using(
    *conditions: ColumnElement[bool],
) -> Select[tuple[int, date, str | None]]:
    """Zapytanie „dni planu, w których użyto wskazanej encji" (wspólne dla obu rejestrów)."""
    return (
        select(PlanDay.id, PlanDay.day, PlanDay.title)
        .join(PlanMeal, PlanMeal.plan_day_id == PlanDay.id)
        .join(PlanMealItem, PlanMealItem.plan_meal_id == PlanMeal.id)
        .where(*conditions)
        .distinct()
        .order_by(PlanDay.day, PlanDay.id)
        .limit(USED_IN_LIMIT)
    )


async def _plans_using_recipe(session: AsyncSession, recipe_id: int) -> Sequence[UsedInRef]:
    """Licznik referencji dla modułu recipes: dni planu, w których jest ten przepis.

    Bez tego DELETE przepisu użytego w planie dawałby gołe 409 z FK RESTRICT,
    zamiast listy „Używane w: Plan dnia 17.08.2026" (karta B06 §Context).
    """
    rows = (await session.execute(_days_using(PlanMealItem.recipe_id == recipe_id))).all()
    return _used_in_days((int(row[0]), row[1], row[2]) for row in rows)


async def _plans_using_recipe_outside(
    session: AsyncSession, recipe_id: int, keep_household_id: int | None, keep_owner_id: int
) -> Sequence[UsedInRef]:
    """Dni planu spoza wskazanego grona, w których jest ten przepis (D32).

    Blokuje obniżenie zakresu przepisu `global`: po zawężeniu przepis zniknąłby
    z widoku właścicielom tych dni.
    """
    rows = (
        await session.execute(
            _days_using(
                PlanMealItem.recipe_id == recipe_id,
                outside_audience_condition(
                    PlanDay, keep_household_id=keep_household_id, keep_owner_id=keep_owner_id
                ),
            )
        )
    ).all()
    return _used_in_days((int(row[0]), row[1], row[2]) for row in rows)


async def _plans_using_product(session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
    """Ten sam licznik dla katalogu: produkt luzem użyty w planie blokuje usunięcie."""
    rows = (await session.execute(_days_using(PlanMealItem.product_id == product_id))).all()
    return _used_in_days((int(row[0]), row[1], row[2]) for row in rows)


async def _plan_days_in_household(session: AsyncSession, household_id: int) -> Sequence[UsedInRef]:
    """Licznik referencji dla modułu households (ustalenie REVIEW R3, dług U16/U17).

    Dni planu są NAJCZĘSTSZYM blokerem usunięcia rodziny i najmniej oczywistym:
    wiersz `plan_days` powstaje implicite przy pierwszym posiłku, a UI pokazuje
    „brak planu", gdy dzień jest pusty. Od R3 pusty dzień sprząta samo usunięcie
    ostatniego posiłku (`delete_meal`), a te, które zostały, ADMIN widzi tutaj
    z datą — zamiast 409 z pustą listą.
    """
    rows = (
        await session.execute(
            select(PlanDay.id, PlanDay.day, PlanDay.title)
            .where(PlanDay.household_id == household_id)
            .order_by(PlanDay.day, PlanDay.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return _used_in_days((int(row[0]), row[1], row[2]) for row in rows)


# Rejestracja przy imporcie modułu: każdy proces budujący aplikację
# (create_app → deps → PlanningService) ma oba liczniki wpięte automatycznie.
register_recipe_reference_finder(_plans_using_recipe)
register_recipe_foreign_use_finder(_plans_using_recipe_outside)
register_product_reference_finder(_plans_using_product)
register_household_reference_finder(_plan_days_in_household)
