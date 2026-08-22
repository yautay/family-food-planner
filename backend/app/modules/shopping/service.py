"""Logika modułu shopping: konfiguracja tur, generacje, finalizacja list.

Granice odpowiedzialności (ADR-008, karta B10):

- **Silnik nie robi I/O, serwis nie liczy zakupów.** Serwis zbiera materiał
  (plan, przepisy, produkty, spiżarnia, warianty), buduje `EngineInput`
  i przekazuje go czystej funkcji `generate_preview`. Cała arytmetyka —
  agregacja, spiżarnia, tury, opakowania — mieszka w `engine.py`.
- **Moduł→moduł wyłącznie przez serwisy** (CLAUDE.md §4): plan przez
  `PlanningService.demand_rows`, przepisy przez `RecipesService.
  ingredient_amounts`, stan domowy przez `PantryService.get_household_state`,
  warianty przez `RetailService`. Katalog produktów czytamy JOIN-em, bo
  potrzebujemy pary produkt+kategoria, a nie logiki katalogu.
- **`params` to jedyne źródło prawdy o preview.** `generate` zapisuje pełne
  wejście, `GET` i `resolve` liczą preview z tego zapisu. Nie ma tabeli
  „pozycje preview" i nie będzie — inaczej istniałyby dwa stany, które
  mogłyby się rozjechać (karta B10, Implementation Notes pkt 3).
- **Widoczność wyłącznie przez `ScopedQuery`.** Cudza generacja to 404.
- **Czas wchodzi parametrem** (`now` z routera), nigdy `datetime.now()`
  w logice — jak `date.today()` w spiżarni (ustalenie review R2).

Spiżarnia jest odejmowana TYLKO wtedy, gdy `use_pantry=True` — decyzję
podejmuje użytkownik jawnie w formularzu (02_DOMAIN §8), a serwis nawet nie
pyta bazy o stan domowy, jeśli zgody nie ma.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deletion import USED_IN_LIMIT, UsedInRef
from app.core.errors import AppError, ConflictError
from app.core.scope import Scope, ScopedQuery
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, ProductCategory, RetailProduct, Store
from app.modules.catalog.retail_service import (
    RetailService,
    register_retail_reference_finder,
)
from app.modules.catalog.service import register_product_reference_finder
from app.modules.catalog.stores_service import register_store_reference_finder
from app.modules.households.service import register_household_reference_finder
from app.modules.pantry.service import PantryService
from app.modules.planning.service import PlanningService
from app.modules.recipes.service import RecipesService
from app.modules.shopping.engine import (
    EngineInput,
    IngredientInput,
    PantryInput,
    PlanItemInput,
    PreviewLine,
    PreviewResult,
    ProductInput,
    RecipeInput,
    RetailInput,
    RoundInput,
    RoundMode,
    blocking_issues,
    dump_input,
    generate_preview,
    load_input,
    quantize_amount,
    quantize_package,
)
from app.modules.shopping.models import (
    GenerationStatus,
    ShoppingGeneration,
    ShoppingList,
    ShoppingListItem,
    ShoppingRoundConfig,
)

ROUND_CONFIG_NOT_FOUND = "Nie znaleziono tury zakupowej."
GENERATION_NOT_FOUND = "Nie znaleziono generacji zakupów."
GENERATION_NOT_EDITABLE = (
    "Ta generacja nie jest już szkicem — jej listy zostały utworzone albo została odrzucona. "
    "Wygeneruj zakupy ponownie."
)
GENERATION_ALREADY_FINAL = (
    "Ta generacja ma już utworzone listy zakupowe. Odrzucić można wyłącznie szkic."
)
FINALIZE_BLOCKED = (
    "Zanim utworzymy listy, rozstrzygnij pozycje z panelu „Do rozstrzygnięcia”. "
    "Możesz poprawić dane albo świadomie odłożyć każdą z nich."
)
NOTHING_TO_FINALIZE = (
    "Nie ma z czego utworzyć list — w wybranym zakresie nie ma nic do kupienia. "
    "Sprawdź zakres dat i plan posiłków."
)
UNKNOWN_PRODUCT_IN_DECISION = (
    "Decyzja dotyczy produktu, którego nie ma w tej generacji. Odśwież podgląd i spróbuj ponownie."
)
RETAIL_NOT_FOR_PRODUCT = (
    "Wybrany produkt sklepowy nie należy do tego produktu. Odśwież podgląd i wybierz ponownie."
)
ROUND_CONFIG_UNKNOWN = (
    "Wskazana tura zakupowa nie istnieje albo nie należy do Ciebie. Odśwież listę tur."
)
#: Ile dni żyje lista zakupowa (02_DOMAIN §9.4, D10/ADR-010).
LIST_TTL_DAYS = 7
#: Sufit liczby tur w konfiguracji — więcej niż tyle to pomyłka, nie plan zakupów.
MAX_ROUND_CONFIGS = 10
ROUND_CONFIGS_LIMIT_REACHED = (
    f"Masz już maksymalną liczbę tur zakupowych ({MAX_ROUND_CONFIGS}). "
    "Usuń niepotrzebną turę, zamiast dodawać kolejną."
)

#: Klucz tury zastępczej, gdy użytkownik usunął całą konfigurację (silnik musi
#: mieć gdzie umieścić zapotrzebowanie — patrz `_round_inputs`).
FALLBACK_ROUND_KEY = "all"
FALLBACK_ROUND_NAME = "Zakupy"

_CONFIGS = ScopedQuery(ShoppingRoundConfig, not_found_message=ROUND_CONFIG_NOT_FOUND)
_GENERATIONS = ScopedQuery(ShoppingGeneration, not_found_message=GENERATION_NOT_FOUND)


class ShoppingValidationError(AppError):
    """422 — decyzje użytkownika nie trzymają się kształtu tej generacji."""

    status_code = 422
    code = "validation_error"


#: Preset tur z 02_DOMAIN §9.2 — SEED DANYCH, nie hardcode w silniku.
#: Powstaje przy pierwszym wejściu na Zakupy i od tej chwili jest edytowalny.
PRESET_ROUNDS: tuple[dict[str, object], ...] = (
    {
        "name": "Niedziela",
        "shopping_weekday": 6,
        "mode": RoundMode.DURABLE_PLUS_FRESH_WINDOW,
        "covers_days": 7,
        "fresh_days": 4,
        "position": 0,
    },
    {
        "name": "Środa",
        "shopping_weekday": 2,
        "mode": RoundMode.FRESH_ONLY,
        "covers_days": 3,
        "fresh_days": None,
        "position": 1,
    },
)


@dataclass(frozen=True)
class GenerationView:
    """Generacja razem z policzonym preview — to zwraca warstwa HTTP."""

    generation: ShoppingGeneration
    preview: PreviewResult


@dataclass(frozen=True)
class ShoppingListView:
    """Lista zakupowa z pozycjami — wynik finalizacji (pełny widok dostarcza B11)."""

    shopping_list: ShoppingList
    items: list[ShoppingListItem]


class ShoppingService:
    """Operacje zakupowe. Jedyne miejsce I/O tego modułu."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._planning = PlanningService(session)
        self._recipes = RecipesService(session)
        self._pantry = PantryService(session)
        self._retail = RetailService(session)

    # --- konfiguracja tur ----------------------------------------------------------

    async def list_round_configs(self, user: User) -> list[ShoppingRoundConfig]:
        """Tury użytkownika; przy PIERWSZYM użyciu zasiewa preset (02_DOMAIN §9.2).

        Seed jest DANYMI, nie stałą w kodzie: użytkownik ma móc zmienić nazwy,
        dni i okna. Dlatego zasiewamy raz — gdy w scope nie ma ani jednej tury —
        i nigdy nie „naprawiamy" konfiguracji, którą ktoś świadomie okrasił.
        """
        rows = await self._visible_configs(user)
        if rows:
            return rows

        scope = self._default_scope(user)
        for preset in PRESET_ROUNDS:
            self._session.add(
                ShoppingRoundConfig(**preset, **ScopedQuery.ownership_for_create(user, scope))
            )
        await self._session.commit()
        return await self._visible_configs(user)

    async def create_round_config(
        self,
        user: User,
        *,
        name: str,
        mode: RoundMode,
        covers_days: int,
        fresh_days: int | None,
        shopping_weekday: int | None,
        position: int | None,
    ) -> ShoppingRoundConfig:
        """Nowa tura zakupowa użytkownika (albo jego rodziny)."""
        existing = await self._visible_configs(user)
        if len(existing) >= MAX_ROUND_CONFIGS:
            raise ConflictError(ROUND_CONFIGS_LIMIT_REACHED)

        entity = ShoppingRoundConfig(
            name=name,
            mode=mode,
            covers_days=covers_days,
            fresh_days=fresh_days if mode is RoundMode.DURABLE_PLUS_FRESH_WINDOW else None,
            shopping_weekday=shopping_weekday,
            position=position if position is not None else len(existing),
            **ScopedQuery.ownership_for_create(user, self._default_scope(user)),
        )
        self._session.add(entity)
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def update_round_config(
        self, config_id: int, *, user: User, changes: dict[str, object]
    ) -> ShoppingRoundConfig:
        """Częściowa edycja tury. Pole pominięte zostaje bez zmian."""
        entity = await _CONFIGS.get_or_404(self._session, config_id, user)
        for field, value in changes.items():
            setattr(entity, field, value)
        # Okno świeżych ma sens wyłącznie w trybie „trwałe + okno świeżych";
        # w pozostałych trybach zostawienie starej wartości mieszałoby w UI.
        if entity.mode is not RoundMode.DURABLE_PLUS_FRESH_WINDOW:
            entity.fresh_days = None
        await self._session.commit()
        await self._session.refresh(entity)
        return entity

    async def delete_round_config(self, config_id: int, *, user: User) -> None:
        """Usunięcie tury — właściciel albo ADMIN (macierz 08_TESTING §4)."""
        entity = await _CONFIGS.get_or_404(self._session, config_id, user)
        _CONFIGS.assert_can_manage(entity, user)
        await self._session.execute(
            delete(ShoppingRoundConfig).where(ShoppingRoundConfig.id == config_id)
        )
        await self._session.commit()

    # --- generacja -----------------------------------------------------------------

    async def generate(
        self,
        user: User,
        *,
        date_from: date,
        date_to: date,
        # Wartość domyślna jest ŚWIADOMIE bezpieczna: pominięcie parametru
        # oznacza „nie odejmuj stanu domowego" (02_DOMAIN §8), a nie odwrotnie.
        use_pantry: bool = False,
        round_config_ids: Sequence[int] | None = None,
    ) -> GenerationView:
        """Zbuduj wejście, policz preview i ZAPISZ wyłącznie `shopping_generations`.

        Nic poza generacją nie powstaje (04_API §2): listy tworzy dopiero
        `finalize`. Dzięki temu użytkownik może wygenerować podgląd, rozstrzygnąć
        niejasności i porzucić szkic, nie zostawiając po sobie danych do
        sprzątania.
        """
        configs = await self._configs_for_generation(user, round_config_ids)
        data = await self._build_input(
            user,
            date_from=date_from,
            date_to=date_to,
            use_pantry=use_pantry,
            configs=configs,
        )
        generation = ShoppingGeneration(
            date_from=date_from,
            date_to=date_to,
            used_pantry=use_pantry,
            params=dump_input(data),
            status=GenerationStatus.PREVIEW,
            **ScopedQuery.ownership_for_create(user, self._default_scope(user)),
        )
        self._session.add(generation)
        await self._session.commit()
        await self._session.refresh(generation)
        return GenerationView(generation=generation, preview=generate_preview(data))

    async def get_generation(self, generation_id: int, *, user: User) -> GenerationView:
        """Odtworzenie preview z `params` — deterministycznie, bez pytania planu."""
        generation = await _GENERATIONS.get_or_404(self._session, generation_id, user)
        data = load_input(generation.params)
        return GenerationView(generation=generation, preview=generate_preview(data))

    async def resolve(
        self,
        generation_id: int,
        *,
        user: User,
        already_have: Sequence[int] | None = None,
        retail_choices: Sequence[tuple[int, int]] | None = None,
        dismissed_issues: Sequence[str] | None = None,
    ) -> GenerationView:
        """Zapisz decyzje użytkownika w `params` i przelicz preview tym samym silnikiem.

        Pole pominięte zostaje bez zmian; pole podane ZASTĘPUJE dotychczasowy
        zbiór (frontend wysyła pełny stan zaznaczeń, a nie różnicę — inaczej
        odznaczenie nie miałoby jak dojechać).

        Katalog wariantów odświeżamy z bazy przy każdym `resolve`, bo to tutaj
        wraca użytkownik po inline create produktu sklepowego (06_UIUX §3.1):
        wariant utworzony po `generate` musi dać się wybrać bez generowania
        zakupów od nowa.
        """
        generation = await self._editable_generation(generation_id, user)
        data = load_input(generation.params)

        product_ids = {product.product_id for product in data.products}
        if already_have is not None:
            unknown = sorted(set(already_have) - product_ids)
            if unknown:
                raise ShoppingValidationError(UNKNOWN_PRODUCT_IN_DECISION)
            data = _with_already_have(data, already_have)

        data = _with_retail(data, await self._retail_inputs(product_ids, data.pantry))

        if retail_choices is not None:
            data = _with_retail_choices(data, retail_choices)

        if dismissed_issues is not None:
            data = _with_dismissed(data, dismissed_issues)

        generation.params = dump_input(data)
        await self._session.commit()
        await self._session.refresh(generation)
        return GenerationView(generation=generation, preview=generate_preview(data))

    async def discard(self, generation_id: int, *, user: User) -> None:
        """Odrzucenie szkicu — status `discarded`, wiersz zostaje (D10, historia)."""
        generation = await _GENERATIONS.get_or_404(self._session, generation_id, user)
        if generation.status is GenerationStatus.FINAL:
            raise ConflictError(GENERATION_ALREADY_FINAL)
        generation.status = GenerationStatus.DISCARDED
        await self._session.commit()

    async def finalize(
        self, generation_id: int, *, user: User, now: datetime
    ) -> list[ShoppingListView]:
        """Utwórz listy zakupowe — po jednej na turę, która ma co kupić.

        Blokery bez decyzji użytkownika zatrzymują finalizację 409-ką z listą
        powodów (06_UIUX §3.3). Pozycje w całości pokryte spiżarnią NIE wchodzą
        na listę (nie ma czego kupować), ale pozycje oznaczone „mam już w domu"
        wchodzą — to świadoma decyzja człowieka i kolumna `already_have`
        istnieje właśnie po to, żeby ją pokazać.
        """
        generation = await self._editable_generation(generation_id, user)
        data = load_input(generation.params)
        preview = generate_preview(data)

        blockers = blocking_issues(preview)
        if blockers:
            raise ConflictError(
                FINALIZE_BLOCKED,
                details={
                    "issues": [
                        {"key": issue.key, "kind": issue.kind.value, "message": issue.message}
                        for issue in blockers
                    ]
                },
            )

        ownership = ScopedQuery.ownership_for_create(user, self._default_scope(user))
        expires_at = now + timedelta(days=LIST_TTL_DAYS)
        views: list[ShoppingListView] = []
        for round_view in preview.rounds:
            lines = [line for line in round_view.items if _goes_to_list(line)]
            if not lines:
                continue
            shopping_list = ShoppingList(
                generation_id=generation.id,
                name=_list_name(preview.date_from, preview.date_to),
                round_name=round_view.name,
                expires_at=expires_at,
                **ownership,
            )
            self._session.add(shopping_list)
            await self._session.flush()
            items = [
                _list_item(shopping_list.id, line, position, used_pantry=preview.use_pantry)
                for position, line in enumerate(lines)
            ]
            self._session.add_all(items)
            views.append(ShoppingListView(shopping_list=shopping_list, items=items))

        if not views:
            raise ConflictError(NOTHING_TO_FINALIZE)

        generation.status = GenerationStatus.FINAL
        await self._session.commit()
        for view in views:
            await self._session.refresh(view.shopping_list)
            for item in view.items:
                await self._session.refresh(item)
        return views

    # --- budowa wejścia silnika ----------------------------------------------------

    async def _build_input(
        self,
        user: User,
        *,
        date_from: date,
        date_to: date,
        use_pantry: bool,
        configs: Sequence[ShoppingRoundConfig],
    ) -> EngineInput:
        """Zbierz wszystko, czego potrzebuje silnik — stała liczba zapytań."""
        rows = await self._planning.demand_rows(user, date_from=date_from, date_to=date_to)
        recipes = await self._recipes.ingredient_amounts(
            [row.recipe_id for row in rows if row.recipe_id is not None]
        )

        product_ids = {row.product_id for row in rows if row.product_id is not None}
        for amounts in recipes.values():
            product_ids.update(ingredient.product_id for ingredient in amounts.ingredients)

        pantry = (
            [
                PantryInput(
                    item_id=item.item_id,
                    amount=item.amount,
                    amount_unit=item.amount_unit,
                    product_id=item.product_id,
                    retail_product_id=item.retail_product_id,
                )
                for item in await self._pantry.get_household_state(user)
            ]
            if use_pantry
            else []
        )

        return EngineInput(
            date_from=date_from,
            date_to=date_to,
            use_pantry=use_pantry,
            rounds=_round_inputs(configs, total_days=(date_to - date_from).days + 1),
            items=tuple(
                PlanItemInput(
                    item_id=row.item_id,
                    day=row.day,
                    meal_name=row.meal_name,
                    servings=row.servings,
                    recipe_id=row.recipe_id,
                    product_id=row.product_id,
                    amount=row.amount,
                    amount_unit=row.amount_unit,
                )
                for row in rows
            ),
            recipes=tuple(
                RecipeInput(
                    recipe_id=amounts.recipe_id,
                    name=amounts.name,
                    base_servings=amounts.base_servings,
                    ingredients=tuple(
                        IngredientInput(
                            product_id=ingredient.product_id,
                            amount=ingredient.amount,
                            amount_unit=ingredient.amount_unit,
                        )
                        for ingredient in amounts.ingredients
                    ),
                )
                for amounts in sorted(recipes.values(), key=lambda item: item.recipe_id)
            ),
            products=await self._product_inputs(product_ids),
            pantry=tuple(pantry),
            retail=await self._retail_inputs(product_ids, tuple(pantry)),
        )

    async def _product_inputs(self, product_ids: set[int]) -> tuple[ProductInput, ...]:
        """Produkty razem z kategorią i ROZSTRZYGNIĘTĄ trwałością (`override ?? kategoria`).

        Rozstrzygnięcie należy do serwisu (karta B10, Implementation Notes pkt 2):
        silnik dostaje gotowy atrybut pozycji i nie zna kolumn katalogu.
        """
        if not product_ids:
            return ()
        rows = (
            await self._session.execute(
                select(CanonicalProduct, ProductCategory)
                .join(ProductCategory, CanonicalProduct.category_id == ProductCategory.id)
                .where(CanonicalProduct.id.in_(sorted(product_ids)))
                .order_by(CanonicalProduct.id)
            )
        ).all()
        return tuple(
            ProductInput(
                product_id=product.id,
                name=product.name,
                measure_kind=product.measure_kind,
                piece_weight_g=product.piece_weight_g,
                category_id=category.id,
                category_name=category.name,
                category_position=category.position,
                perishability=product.perishability_override or category.perishability,
            )
            for product, category in rows
        )

    async def _retail_inputs(
        self, product_ids: set[int], pantry: Sequence[PantryInput]
    ) -> tuple[RetailInput, ...]:
        """Warianty do zaproponowania + warianty potrzebne do odczytania spiżarni.

        Dwa różne pytania, jedno wejście: warianty produktów z zapotrzebowania
        (bez archiwalnych — nie proponujemy tego, czego nie ma na półce) oraz
        warianty wskazane przez pozycje spiżarni (także archiwalne, bo taka
        pozycja opisuje realną zawartość szafki). Archiwalne są oznaczone
        `is_archived`, więc silnik ich nie zaproponuje.
        """
        variants: dict[int, RetailProduct] = {}
        for options in (await self._retail.options_for_products(sorted(product_ids))).values():
            for option in options:
                variants[option.id] = option

        pantry_ids = [
            row.retail_product_id
            for row in pantry
            if row.retail_product_id is not None and row.retail_product_id not in variants
        ]
        variants.update(await self._retail.variants_by_ids(pantry_ids))

        stores = await self._store_names(
            [variant.store_id for variant in variants.values() if variant.store_id is not None]
        )
        return tuple(
            RetailInput(
                retail_product_id=variant.id,
                product_id=variant.canonical_product_id,
                label=variant.name,
                package_amount=variant.package_amount,
                package_unit=variant.package_unit,
                store_id=variant.store_id,
                store_name=stores.get(variant.store_id) if variant.store_id else None,
                is_archived=variant.is_archived,
            )
            for variant in sorted(variants.values(), key=lambda row: row.id)
        )

    async def _store_names(self, store_ids: Sequence[int]) -> dict[int, str]:
        """Nazwy sklepów do etykiet wariantów — jedno zapytanie, nie N+1."""
        unique = sorted(set(store_ids))
        if not unique:
            return {}
        rows = (
            await self._session.execute(select(Store.id, Store.name).where(Store.id.in_(unique)))
        ).all()
        return {int(row[0]): str(row[1]) for row in rows}

    # --- pomocnicze ----------------------------------------------------------------

    async def _visible_configs(self, user: User) -> list[ShoppingRoundConfig]:
        """Tury widoczne dla użytkownika, w kolejności prezentacji i liczenia."""
        rows = (
            (
                await self._session.execute(
                    _CONFIGS.select_visible(user).order_by(
                        ShoppingRoundConfig.position, ShoppingRoundConfig.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _configs_for_generation(
        self, user: User, round_config_ids: Sequence[int] | None
    ) -> list[ShoppingRoundConfig]:
        """Tury użyte w generacji: wskazane przez użytkownika albo wszystkie jego."""
        available = await self.list_round_configs(user)
        if round_config_ids is None:
            return available
        wanted = list(dict.fromkeys(round_config_ids))
        by_id = {config.id: config for config in available}
        missing = [config_id for config_id in wanted if config_id not in by_id]
        if missing:
            raise ShoppingValidationError(ROUND_CONFIG_UNKNOWN)
        return [by_id[config_id] for config_id in wanted]

    async def _editable_generation(self, generation_id: int, user: User) -> ShoppingGeneration:
        """Generacja w stanie `preview` — inne stany to 409, cudza to 404."""
        generation = await _GENERATIONS.get_or_404(self._session, generation_id, user)
        if generation.status is not GenerationStatus.PREVIEW:
            raise ConflictError(GENERATION_NOT_EDITABLE)
        return generation

    @staticmethod
    def _default_scope(user: User) -> Scope:
        """Zakupy są sprawą domową — HOUSEHOLD, gdy użytkownik ma rodzinę.

        Bez rodziny scope HOUSEHOLD jest niedozwolony (03_DATABASE §4), więc
        wpis zostaje prywatny; po przypisaniu do rodziny kolejne generacje
        powstaną już jako domowe.
        """
        return Scope.HOUSEHOLD if user.household_id is not None else Scope.PRIVATE


# --- czyste funkcje pomocnicze ----------------------------------------------------------


def _round_inputs(
    configs: Sequence[ShoppingRoundConfig], *, total_days: int
) -> tuple[RoundInput, ...]:
    """Konfiguracja tur → wejście silnika; brak tur = jedna tura zastępcza.

    Tura zastępcza powstaje, gdy użytkownik usunął całą konfigurację (albo
    świadomie wybrał puste `round_config_ids`): zapotrzebowanie musi mieć gdzie
    trafić, a „jedne zakupy na cały zakres" jest najmniej zaskakującym
    domyślnym zachowaniem.
    """
    if not configs:
        return (
            RoundInput(
                key=FALLBACK_ROUND_KEY,
                name=FALLBACK_ROUND_NAME,
                mode=RoundMode.ALL,
                covers_days=max(total_days, 1),
            ),
        )
    return tuple(
        RoundInput(
            key=f"cfg-{config.id}",
            name=config.name,
            mode=config.mode,
            covers_days=config.covers_days,
            fresh_days=config.fresh_days,
            shopping_weekday=config.shopping_weekday,
        )
        for config in configs
    )


def _with_already_have(data: EngineInput, product_ids: Sequence[int]) -> EngineInput:
    """Nowy zbiór „mam już w domu" (posortowany — `params` musi być stabilny)."""
    return replace(data, already_have=tuple(sorted(set(product_ids))))


def _with_retail(data: EngineInput, retail: tuple[RetailInput, ...]) -> EngineInput:
    """Odświeżony katalog wariantów (po inline create produktu sklepowego)."""
    return replace(data, retail=retail)


def _with_retail_choices(data: EngineInput, choices: Sequence[tuple[int, int]]) -> EngineInput:
    """Wybory wariantów po walidacji: wariant musi należeć do swojego produktu."""
    by_id = {variant.retail_product_id: variant for variant in data.retail}
    products = {product.product_id for product in data.products}
    for product_id, retail_id in choices:
        if product_id not in products:
            raise ShoppingValidationError(UNKNOWN_PRODUCT_IN_DECISION)
        variant = by_id.get(retail_id)
        if variant is None or variant.product_id != product_id:
            raise ShoppingValidationError(RETAIL_NOT_FOR_PRODUCT)
    return replace(data, retail_choices=tuple(sorted(dict(choices).items())))


def _with_dismissed(data: EngineInput, keys: Sequence[str]) -> EngineInput:
    """Odłożone niejasności — klucze silnika, posortowane dla stabilności `params`."""
    return replace(data, dismissed_issues=tuple(sorted(set(keys))))


def _goes_to_list(line: PreviewLine) -> bool:
    """Czy pozycja preview ma trafić na listę zakupową.

    Pozycja w całości pokryta spiżarnią nie ma czego dołożyć do listy; pozycja
    oznaczona „mam już w domu" — owszem, bo jest decyzją człowieka i ma zostać
    widoczna (kolumna `already_have`).
    """
    return line.needed_amount > Decimal("0") or line.already_have


def _list_name(date_from: date, date_to: date) -> str:
    """Nazwa listy: zakres zakupów w formacie czytelnym po polsku."""
    return f"Zakupy {date_from.strftime('%d.%m')}-{date_to.strftime('%d.%m.%Y')}"


def _list_item(
    list_id: int, line: PreviewLine, position: int, *, used_pantry: bool
) -> ShoppingListItem:
    """Pozycja preview → wiersz listy. Tu (i tylko tu) ilości są kwantyzowane.

    `label` jest denormalizacją pod offline (B12): nazwa wariantu, a bez
    wariantu — nazwa produktu kanonicznego.
    """
    assert line.category_id is not None  # bloker `product_without_category` już przeszedł
    return ShoppingListItem(
        list_id=list_id,
        category_id=line.category_id,
        product_id=line.product_id,
        retail_product_id=line.retail_product_id,
        label=line.label,
        needed_amount=quantize_amount(line.needed_amount),
        amount_unit=line.unit,
        packages_count=line.packages_count,
        package_size=(
            quantize_package(line.package_amount) if line.package_amount is not None else None
        ),
        leftover_amount=(
            quantize_amount(line.leftover_amount) if line.leftover_amount is not None else None
        ),
        already_have=line.already_have,
        from_pantry_amount=(
            quantize_amount(line.from_pantry_amount)
            if used_pantry and line.from_pantry_amount is not None
            else None
        ),
        position=position,
    )


# --- liczniki referencji (409 z listą „Używane w:", ADR-012) ----------------------------


async def _lists_using_product(session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
    """Listy zakupowe, na których jest ten produkt — blokada usunięcia produktu."""
    rows = (
        await session.execute(
            select(ShoppingList.id, ShoppingList.name)
            .join(ShoppingListItem, ShoppingListItem.list_id == ShoppingList.id)
            .where(ShoppingListItem.product_id == product_id)
            .distinct()
            .order_by(ShoppingList.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="shopping_list", id=int(row[0]), name=str(row[1])) for row in rows]


async def _lists_using_retail_product(
    session: AsyncSession, retail_product_id: int
) -> Sequence[UsedInRef]:
    """To samo dla wariantu sklepowego (karta B09 §Context pkt 3)."""
    rows = (
        await session.execute(
            select(ShoppingList.id, ShoppingList.name)
            .join(ShoppingListItem, ShoppingListItem.list_id == ShoppingList.id)
            .where(ShoppingListItem.retail_product_id == retail_product_id)
            .distinct()
            .order_by(ShoppingList.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="shopping_list", id=int(row[0]), name=str(row[1])) for row in rows]


async def _lists_using_store(session: AsyncSession, store_id: int) -> Sequence[UsedInRef]:
    """Listy z profilem sortowania tego sklepu.

    FK ma SET NULL, więc baza sama nie obroni tej referencji — bez tego licznika
    usunięcie sklepu po cichu zabrałoby liście profil przejścia (karta B09 §2).
    """
    rows = (
        await session.execute(
            select(ShoppingList.id, ShoppingList.name)
            .where(ShoppingList.store_id == store_id)
            .order_by(ShoppingList.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="shopping_list", id=int(row[0]), name=str(row[1])) for row in rows]


async def _shopping_in_household(session: AsyncSession, household_id: int) -> Sequence[UsedInRef]:
    """Tury, generacje i listy rodziny — licznik dla `households` (REVIEW R3, U16).

    Trzy tabele modułu trzymają `household_id` z `ON DELETE RESTRICT`, więc
    każda z nich umie zablokować usunięcie rodziny. Generacja nie ma nazwy, więc
    identyfikujemy ją zakresem dat — inaczej ADMIN dostałby na liście gołe id.
    """
    references: list[UsedInRef] = []
    configs = (
        await session.execute(
            select(ShoppingRoundConfig.id, ShoppingRoundConfig.name)
            .where(ShoppingRoundConfig.household_id == household_id)
            .order_by(ShoppingRoundConfig.position, ShoppingRoundConfig.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    references.extend(
        UsedInRef(type="shopping_round_config", id=int(row[0]), name=str(row[1])) for row in configs
    )
    generations = (
        await session.execute(
            select(ShoppingGeneration.id, ShoppingGeneration.date_from, ShoppingGeneration.date_to)
            .where(ShoppingGeneration.household_id == household_id)
            .order_by(ShoppingGeneration.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    references.extend(
        UsedInRef(
            type="shopping_generation",
            id=int(row[0]),
            name=f"Generacja {row[1]:%d.%m.%Y}-{row[2]:%d.%m.%Y}",
        )
        for row in generations
    )
    lists = (
        await session.execute(
            select(ShoppingList.id, ShoppingList.name)
            .where(ShoppingList.household_id == household_id)
            .order_by(ShoppingList.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    references.extend(
        UsedInRef(type="shopping_list", id=int(row[0]), name=str(row[1])) for row in lists
    )
    return references


# Rejestracja przy imporcie modułu — jak w recipes (B05) i pantry (B08).
register_product_reference_finder(_lists_using_product)
register_retail_reference_finder(_lists_using_retail_product)
register_store_reference_finder(_lists_using_store)
register_household_reference_finder(_shopping_in_household)
