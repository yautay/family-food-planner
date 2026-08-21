"""Deterministyczny seed danych demo (`task db-seed-demo`, 08_TESTING §5).

Po co: żeby dało się kliknąć aplikację i uruchomić E2E bez ręcznego wklepywania
katalogu. Seed jest **idempotentny** — kluczem tożsamości produktu jest
`normalized_name`, więc powtórne uruchomienie niczego nie duplikuje i nie
nadpisuje wartości poprawionych ręcznie.

Zakres:

- **BATCH_04** — produkty kanoniczne i przeliczniki jednostek domowych.
- **BATCH_10** — sklep, produkty sklepowe (opakowania!), przepisy i TYDZIEŃ
  PLANU, czyli materiał, na którym da się wygenerować zakupy i na którym stoi
  snapshot silnika zakupowego (08_TESTING §5).

Encje ze scope (przepisy, plan) potrzebują właściciela, a seed nie zna żadnego
konta — konta powstają przez `task create-admin`. **Decyzja B10: dopisujemy je
do PIERWSZEGO konta ADMIN** (najstarsze `users.id` z rolą admin). Uzasadnienie:
osobne konto demo wymagałoby hasła z env i kolejnej zmiennej konfiguracji,
a instancja i tak startuje od `task create-admin`. Gdy konta ADMIN nie ma, seed
robi część globalną (katalog, sklep, warianty) i mówi, czego nie dołożył —
zamiast tworzyć konto po cichu (07_SECURITY §2).

Tydzień planu leży na STAŁEJ dacie (`DEMO_WEEK_START`), a nie „od dziś": seed
musi być deterministyczny, bo z tych samych danych liczony jest snapshot
podglądu zakupów. Data jest świadomie poza okresem zarezerwowanym dla E2E
(lata 2030+, 08_TESTING §3.1) — `purgeE2eLeftovers` czyści tamto okno w całości
i zabrałby plan demo.

Dane są ŚWIADOMIE mieszane pod względem kompletności: część produktów jest
zweryfikowana z pełnymi wartościami, część czeka w kolejce `UNVERIFIED` bez
kalorii. Bez tego nie da się obejrzeć ani plakietki „niepełne dane"
(06_UIUX §3.5), ani ekranu `/admin/weryfikacja`.

Użycie:
    task db-seed-demo
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ConfigurationError, get_settings
from app.core.db import get_session_factory, selector_loop_factory
from app.core.scope import Scope, ScopedQuery

# Rejestr modeli MUSI być zaimportowany, choć nic z niego tu nie wołamy: seed omija
# `create_app()`, więc bez tej linii `Base.registry` nie zna `Household` i relacja
# `User.household` (adnotowana stringiem) wywala `InvalidRequestError` przy
# pierwszym zapytaniu o użytkownika. Ten sam wzorzec stosuje `app/cli.py`.
from app.models import Base  # noqa: F401
from app.modules.accounts.models import User, UserRole
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    ProductCategory,
    ProductUnitWeight,
    RetailProduct,
    Store,
    VerificationStatus,
)
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import (
    NormalizedAmount,
    ProductMeasure,
    UnitWeight,
    base_unit,
    normalize_amount,
    normalize_unit_label,
)
from app.modules.planning.models import PlanDay, PlanMeal, PlanMealItem
from app.modules.recipes.models import Recipe, RecipeIngredient

#: Źródło wartości w danych demo — od razu widać, że nie są to dane referencyjne.
DEMO_SOURCE = "demo"


@dataclass(frozen=True)
class DemoProduct:
    """Produkt demo. `None` w wartościach = świadomy brak (nie zero — ADR-004)."""

    name: str
    category: str
    measure_kind: MeasureKind = MeasureKind.MASS
    piece_weight_g: Decimal | None = None
    kcal_100: Decimal | None = None
    protein_100: Decimal | None = None
    fat_100: Decimal | None = None
    carbs_100: Decimal | None = None
    fiber_100: Decimal | None = None
    sugars_100: Decimal | None = None
    glycemic_index: Decimal | None = None
    #: Etykieta jednostki domowej → gramy na jednostkę (01_PDF_AUDIT §5.2).
    unit_weights: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def is_verified(self) -> bool:
        """Zweryfikowany = ma komplet rdzenia; resztę zostawiamy w kolejce admina."""
        return None not in (self.kcal_100, self.protein_100, self.fat_100, self.carbs_100)


def _d(value: str) -> Decimal:
    """Literał dziesiętny — nigdy `Decimal(float)` (ADR-008)."""
    return Decimal(value)


#: 15 produktów pokrywających wszystkie typy miary i oba stany weryfikacji.
DEMO_PRODUCTS: tuple[DemoProduct, ...] = (
    DemoProduct(
        name="Cebula",
        category="Warzywa",
        kcal_100=_d("40.00"),
        protein_100=_d("1.10"),
        fat_100=_d("0.10"),
        carbs_100=_d("9.30"),
        fiber_100=_d("1.70"),
        sugars_100=_d("4.20"),
        glycemic_index=_d("15.0"),
        unit_weights=(("sztuka średnia", "105.00"),),
    ),
    DemoProduct(
        name="Marchew",
        category="Warzywa",
        kcal_100=_d("41.00"),
        protein_100=_d("0.90"),
        fat_100=_d("0.20"),
        carbs_100=_d("9.60"),
        fiber_100=_d("2.80"),
        sugars_100=_d("4.70"),
        glycemic_index=_d("35.0"),
        unit_weights=(("sztuka średnia", "80.00"),),
    ),
    DemoProduct(
        name="Pomidor",
        category="Warzywa",
        kcal_100=_d("18.00"),
        protein_100=_d("0.90"),
        fat_100=_d("0.20"),
        carbs_100=_d("3.90"),
        fiber_100=_d("1.20"),
        sugars_100=_d("2.60"),
        glycemic_index=_d("30.0"),
    ),
    DemoProduct(
        name="Banan",
        category="Owoce",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=_d("120.00"),
        kcal_100=_d("89.00"),
        protein_100=_d("1.10"),
        fat_100=_d("0.30"),
        carbs_100=_d("22.80"),
        fiber_100=_d("2.60"),
        sugars_100=_d("12.20"),
        glycemic_index=_d("51.0"),
    ),
    DemoProduct(
        name="Jabłko",
        category="Owoce",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=_d("180.00"),
        kcal_100=_d("52.00"),
        protein_100=_d("0.30"),
        fat_100=_d("0.20"),
        carbs_100=_d("13.80"),
        fiber_100=_d("2.40"),
        sugars_100=_d("10.40"),
        glycemic_index=_d("36.0"),
    ),
    DemoProduct(
        name="Pieczarki",
        category="Grzyby",
        kcal_100=_d("22.00"),
        protein_100=_d("3.10"),
        fat_100=_d("0.30"),
        carbs_100=_d("3.30"),
        fiber_100=_d("1.00"),
        glycemic_index=_d("15.0"),
    ),
    DemoProduct(
        name="Jajko",
        category="Nabiał i jaja",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=_d("60.00"),
        kcal_100=_d("143.00"),
        protein_100=_d("12.60"),
        fat_100=_d("9.50"),
        carbs_100=_d("0.70"),
        glycemic_index=_d("0.0"),
    ),
    DemoProduct(
        name="Skyr naturalny",
        category="Nabiał i jaja",
        kcal_100=_d("63.00"),
        protein_100=_d("11.00"),
        fat_100=_d("0.20"),
        carbs_100=_d("4.00"),
        sugars_100=_d("4.00"),
        glycemic_index=_d("11.0"),
        unit_weights=(("opakowanie", "150.00"),),
    ),
    DemoProduct(
        name="Mleko 2%",
        category="Nabiał i jaja",
        measure_kind=MeasureKind.VOLUME,
        kcal_100=_d("51.00"),
        protein_100=_d("3.30"),
        fat_100=_d("2.00"),
        carbs_100=_d("4.80"),
        sugars_100=_d("4.80"),
        glycemic_index=_d("30.0"),
        unit_weights=(("szklanka", "250.00"),),
    ),
    DemoProduct(
        name="Pierś z kurczaka",
        category="Mięso i produkty mięsne",
        kcal_100=_d("110.00"),
        protein_100=_d("23.10"),
        fat_100=_d("1.30"),
        carbs_100=_d("0.00"),
        glycemic_index=_d("0.0"),
        unit_weights=(("porcja", "150.00"),),
    ),
    DemoProduct(
        name="Chleb żytni razowy",
        category="Pieczywo",
        kcal_100=_d("223.00"),
        protein_100=_d("7.50"),
        fat_100=_d("1.20"),
        carbs_100=_d("42.50"),
        fiber_100=_d("8.00"),
        glycemic_index=_d("58.0"),
        unit_weights=(("kromka", "35.00"),),
    ),
    DemoProduct(
        name="Ryż brązowy",
        category="Makarony, ryż i kasze",
        kcal_100=_d("353.00"),
        protein_100=_d("7.10"),
        fat_100=_d("2.50"),
        carbs_100=_d("72.10"),
        fiber_100=_d("3.40"),
        glycemic_index=_d("50.0"),
        unit_weights=(("szklanka", "180.00"), ("opakowanie", "1000.00")),
    ),
    DemoProduct(
        name="Mąka pszenna typ 500",
        category="Makarony, ryż i kasze",
        kcal_100=_d("341.00"),
        protein_100=_d("9.90"),
        fat_100=_d("1.00"),
        carbs_100=_d("70.60"),
        fiber_100=_d("2.50"),
        glycemic_index=_d("70.0"),
        # Ta sama łyżka waży w audycie PDF 5, 12 albo 15 g — demo pokazuje jedną
        # ustaloną wartość, edytowalną przy produkcie (01_PDF_AUDIT §5.2).
        unit_weights=(("łyżka", "12.00"), ("szklanka", "130.00")),
    ),
    # Dwa produkty świadomie NIEZWERYFIKOWANE i bez wartości — tak wygląda
    # katalog po inline create USERA i tym żyje ekran `/admin/weryfikacja`.
    DemoProduct(name="Oliwa z oliwek", category="Tłuszcze", measure_kind=MeasureKind.VOLUME),
    DemoProduct(name="Orzechy włoskie", category="Orzechy i nasiona"),
)


# --- BATCH_10: sklep, opakowania, przepisy i tydzień planu ----------------------------

#: Sklep demo — jeden, żeby dało się obejrzeć profil kolejności kategorii (B09).
DEMO_STORE_NAME = "Biedronka"

#: Poniedziałek POZA okienkiem E2E (lata 2030+): `purgeE2eLeftovers` czyści tamto
#: okno w całości i zabrałby plan demo. Data jest stała, bo z tych samych danych
#: liczony jest snapshot podglądu zakupów (08_TESTING §5).
DEMO_WEEK_START = date(2026, 8, 24)


@dataclass(frozen=True)
class DemoRetail:
    """Opakowanie sklepowe produktu demo. `package_amount` na osi produktu (B09)."""

    product: str
    name: str
    brand: str | None
    package_amount: str


@dataclass(frozen=True)
class DemoIngredient:
    """Składnik przepisu demo — ilość w jednostce, którą wpisałby człowiek."""

    product: str
    quantity: str
    unit: str


@dataclass(frozen=True)
class DemoRecipe:
    """Przepis demo: porcje bazowe + składniki (ilości normalizuje `catalog/units`)."""

    name: str
    base_servings: int
    instructions: str
    ingredients: tuple[DemoIngredient, ...]


@dataclass(frozen=True)
class DemoPlanItem:
    """Pozycja posiłku demo: przepis z mnożnikiem ALBO produkt luzem z ilością."""

    recipe: str | None = None
    product: str | None = None
    quantity: str | None = None
    unit: str | None = None
    servings: str = "1"


@dataclass(frozen=True)
class DemoMeal:
    """Posiłek dnia demo."""

    name: str
    items: tuple[DemoPlanItem, ...]


@dataclass(frozen=True)
class DemoDay:
    """Dzień planu demo — `offset` liczony od `DEMO_WEEK_START` (0 = poniedziałek)."""

    offset: int
    meals: tuple[DemoMeal, ...]


#: Opakowania: część produktów ma po dwa warianty, żeby było widać wybór
#: „najmniejsza resztka, remis -> mniejsze opakowanie" (08_TESTING §2.6).
DEMO_RETAIL: tuple[DemoRetail, ...] = (
    DemoRetail(
        product="Mąka pszenna typ 500",
        name="Mąka pszenna 1 kg",
        brand="Basia",
        package_amount="1000.00",
    ),
    DemoRetail(
        product="Mąka pszenna typ 500",
        name="Mąka pszenna 2 kg",
        brand="Basia",
        package_amount="2000.00",
    ),
    DemoRetail(
        product="Ryż brązowy", name="Ryż brązowy 1 kg", brand="Kupiec", package_amount="1000.00"
    ),
    DemoRetail(
        product="Ryż brązowy", name="Ryż brązowy 400 g", brand="Kupiec", package_amount="400.00"
    ),
    DemoRetail(product="Mleko 2%", name="Mleko 2% 1 l", brand="Łaciate", package_amount="1000.00"),
    DemoRetail(product="Jajko", name="Jajka 10 szt.", brand="Zielona Wieś", package_amount="10.00"),
    DemoRetail(
        product="Skyr naturalny",
        name="Skyr naturalny 150 g",
        brand="Pilos",
        package_amount="150.00",
    ),
    DemoRetail(
        product="Chleb żytni razowy",
        name="Chleb żytni razowy 500 g",
        brand="Piekarnia",
        package_amount="500.00",
    ),
    DemoRetail(
        product="Pierś z kurczaka",
        name="Pierś z kurczaka 700 g",
        brand=None,
        package_amount="700.00",
    ),
    DemoRetail(product="Marchew", name="Marchew 1 kg", brand=None, package_amount="1000.00"),
)

#: Pięć przepisów (08_TESTING §5) — świadomie proste, na produktach z katalogu demo.
DEMO_RECIPES: tuple[DemoRecipe, ...] = (
    DemoRecipe(
        name="Naleśniki",
        base_servings=4,
        instructions="Zmiksuj mąkę, mleko i jajka. Odstaw na 15 minut i smaż na patelni.",
        ingredients=(
            DemoIngredient(product="Mąka pszenna typ 500", quantity="2", unit="szklanka"),
            DemoIngredient(product="Mleko 2%", quantity="500", unit="ml"),
            DemoIngredient(product="Jajko", quantity="3", unit="szt."),
        ),
    ),
    DemoRecipe(
        name="Zupa jarzynowa",
        base_servings=4,
        instructions="Warzywa pokrój, zalej wodą i gotuj 25 minut.",
        ingredients=(
            DemoIngredient(product="Marchew", quantity="3", unit="sztuka średnia"),
            DemoIngredient(product="Cebula", quantity="1", unit="sztuka średnia"),
            DemoIngredient(product="Pieczarki", quantity="200", unit="g"),
        ),
    ),
    DemoRecipe(
        name="Kurczak z ryżem",
        base_servings=2,
        instructions="Ryż ugotuj, pierś podsmaż z cebulą i połącz.",
        ingredients=(
            DemoIngredient(product="Pierś z kurczaka", quantity="2", unit="porcja"),
            DemoIngredient(product="Ryż brązowy", quantity="1", unit="szklanka"),
            DemoIngredient(product="Cebula", quantity="1", unit="sztuka średnia"),
        ),
    ),
    DemoRecipe(
        name="Owsianka na mleku",
        base_servings=1,
        instructions="Zalej płatki mlekiem, dodaj banana i orzechy.",
        ingredients=(
            DemoIngredient(product="Mleko 2%", quantity="250", unit="ml"),
            DemoIngredient(product="Banan", quantity="1", unit="szt."),
            DemoIngredient(product="Orzechy włoskie", quantity="20", unit="g"),
        ),
    ),
    DemoRecipe(
        name="Kanapki z jajkiem",
        base_servings=2,
        instructions="Jajka ugotuj, pokrój i ułóż na kromkach chleba z pomidorem.",
        ingredients=(
            DemoIngredient(product="Chleb żytni razowy", quantity="4", unit="kromka"),
            DemoIngredient(product="Jajko", quantity="2", unit="szt."),
            DemoIngredient(product="Pomidor", quantity="150", unit="g"),
        ),
    ),
)

#: Tydzień planu: dwa-trzy posiłki dziennie, mieszanka przepisów i produktów
#: luzem — tak, żeby zakupy miały i agregację po dniach, i pozycje luzem.
DEMO_PLAN: tuple[DemoDay, ...] = (
    DemoDay(
        offset=0,
        meals=(
            DemoMeal(
                name="Śniadanie",
                items=(DemoPlanItem(recipe="Owsianka na mleku", servings="2"),),
            ),
            DemoMeal(name="Obiad", items=(DemoPlanItem(recipe="Kurczak z ryżem", servings="2"),)),
            DemoMeal(
                name="Kolacja",
                items=(DemoPlanItem(product="Skyr naturalny", quantity="1", unit="opakowanie"),),
            ),
        ),
    ),
    DemoDay(
        offset=1,
        meals=(
            DemoMeal(
                name="Śniadanie",
                items=(DemoPlanItem(recipe="Kanapki z jajkiem", servings="2"),),
            ),
            DemoMeal(name="Obiad", items=(DemoPlanItem(recipe="Zupa jarzynowa", servings="4"),)),
        ),
    ),
    DemoDay(
        offset=2,
        meals=(
            DemoMeal(
                name="Śniadanie",
                items=(DemoPlanItem(recipe="Owsianka na mleku", servings="1"),),
            ),
            DemoMeal(name="Obiad", items=(DemoPlanItem(recipe="Naleśniki", servings="4"),)),
        ),
    ),
    DemoDay(
        offset=3,
        meals=(
            DemoMeal(
                name="Śniadanie",
                items=(DemoPlanItem(recipe="Kanapki z jajkiem", servings="2"),),
            ),
            DemoMeal(
                name="Obiad",
                items=(
                    DemoPlanItem(recipe="Kurczak z ryżem", servings="2"),
                    DemoPlanItem(product="Pomidor", quantity="200", unit="g"),
                ),
            ),
        ),
    ),
    DemoDay(
        offset=4,
        meals=(
            DemoMeal(
                name="Śniadanie",
                items=(DemoPlanItem(recipe="Owsianka na mleku", servings="2"),),
            ),
            DemoMeal(name="Obiad", items=(DemoPlanItem(recipe="Zupa jarzynowa", servings="2"),)),
        ),
    ),
    DemoDay(
        offset=5,
        meals=(
            DemoMeal(name="Śniadanie", items=(DemoPlanItem(recipe="Naleśniki", servings="2"),)),
            DemoMeal(
                name="Kolacja",
                items=(DemoPlanItem(product="Chleb żytni razowy", quantity="2", unit="kromka"),),
            ),
        ),
    ),
    DemoDay(
        offset=6,
        meals=(
            DemoMeal(
                name="Śniadanie",
                items=(DemoPlanItem(recipe="Kanapki z jajkiem", servings="3"),),
            ),
            DemoMeal(name="Obiad", items=(DemoPlanItem(recipe="Kurczak z ryżem", servings="3"),)),
        ),
    ),
)


def measure_of(demo: DemoProduct) -> ProductMeasure:
    """`ProductMeasure` produktu demo — wejście `catalog/units.py` bez ORM.

    Dzięki temu ta sama funkcja normalizuje ilości w seedzie i w teście
    snapshotu silnika: „2 szklanki mąki" znaczy w obu miejscach dokładnie tyle
    samo gramów (ADR-005).
    """
    return ProductMeasure(
        measure_kind=demo.measure_kind,
        piece_weight_g=demo.piece_weight_g,
        unit_weights=tuple(
            UnitWeight(unit_label=label, grams_per_unit=Decimal(grams))
            for label, grams in demo.unit_weights
        ),
    )


def demo_products_by_name() -> dict[str, DemoProduct]:
    """Katalog demo po nazwie — wspólny indeks dla seedu i testów silnika."""
    return {demo.name: demo for demo in DEMO_PRODUCTS}


def normalized_demo_amount(product_name: str, quantity: str, unit: str) -> NormalizedAmount:
    """Ilość demo sprowadzona na oś produktu przez `catalog/units.py`.

    Seed NIE ma własnej arytmetyki jednostek — korzysta z tej samej funkcji, co
    serwisy (niezmiennik 02_DOMAIN §13.1).
    """
    demo = demo_products_by_name()[product_name]
    return normalize_amount(Decimal(quantity), unit, measure_of(demo))


async def seed_products(session: AsyncSession) -> tuple[int, int]:
    """Wstaw brakujące produkty demo. Zwraca (dodane, pominięte)."""
    categories = {
        category.name: category
        for category in (await session.execute(select(ProductCategory))).scalars().all()
    }
    if not categories:
        raise SeedError(
            "Brak kategorii w bazie. Uruchom najpierw migracje (`task db-migrate`) — "
            "słownik kategorii pochodzi z migracji danych 0005."
        )

    existing = set(
        (await session.execute(select(CanonicalProduct.normalized_name))).scalars().all()
    )

    added = 0
    for demo in DEMO_PRODUCTS:
        normalized = normalize_name(demo.name)
        if normalized in existing:
            continue
        category = categories.get(demo.category)
        if category is None:
            raise SeedError(
                f"Kategoria „{demo.category}” nie istnieje w słowniku. "
                "Seed demo zakłada kategorie z migracji 0005."
            )

        product = CanonicalProduct(
            name=demo.name,
            normalized_name=normalized,
            category_id=category.id,
            measure_kind=demo.measure_kind,
            piece_weight_g=demo.piece_weight_g,
            kcal_100=demo.kcal_100,
            protein_100=demo.protein_100,
            fat_100=demo.fat_100,
            carbs_100=demo.carbs_100,
            fiber_100=demo.fiber_100,
            sugars_100=demo.sugars_100,
            glycemic_index=demo.glycemic_index,
            nutrition_source=DEMO_SOURCE if demo.is_verified else None,
            verification_status=(
                VerificationStatus.VERIFIED if demo.is_verified else VerificationStatus.UNVERIFIED
            ),
        )
        session.add(product)
        await session.flush()

        for label, grams in demo.unit_weights:
            session.add(
                ProductUnitWeight(
                    product_id=product.id,
                    unit_label=normalize_unit_label(label),
                    grams_per_unit=Decimal(grams),
                    source=DEMO_SOURCE,
                )
            )
        added += 1

    await session.commit()
    return added, len(DEMO_PRODUCTS) - added


async def seed_store_and_retail(session: AsyncSession) -> tuple[int, int]:
    """Sklep demo + opakowania produktów. Zwraca (dodane warianty, pominięte).

    Tożsamość wariantu to para (produkt kanoniczny, nazwa) — powtórne
    uruchomienie nie duplikuje i nie nadpisuje ręcznych poprawek.
    """
    store = (
        await session.execute(select(Store).where(Store.name == DEMO_STORE_NAME))
    ).scalar_one_or_none()
    if store is None:
        store = Store(name=DEMO_STORE_NAME)
        session.add(store)
        await session.flush()

    products = {
        product.normalized_name: product
        for product in (await session.execute(select(CanonicalProduct))).scalars().all()
    }
    existing = {
        (row.canonical_product_id, row.name)
        for row in (await session.execute(select(RetailProduct))).scalars().all()
    }

    added = 0
    for demo in DEMO_RETAIL:
        product = products.get(normalize_name(demo.product))
        if product is None:
            raise SeedError(
                f"Produkt „{demo.product}” nie istnieje w katalogu, a ma mieć opakowanie. "
                "Uruchom seed produktów (ta sama komenda) na czystej bazie."
            )
        if (product.id, demo.name) in existing:
            continue
        session.add(
            RetailProduct(
                canonical_product_id=product.id,
                name=demo.name,
                brand=demo.brand,
                store_id=store.id,
                package_amount=Decimal(demo.package_amount),
                # Jednostka opakowania jest ZAWSZE na osi produktu (niezmiennik B09).
                package_unit=base_unit(product.measure_kind),
            )
        )
        added += 1

    await session.commit()
    return added, len(DEMO_RETAIL) - added


async def _first_admin(session: AsyncSession) -> User | None:
    """Najstarsze konto ADMIN — właściciel danych demo ze scope (decyzja B10)."""
    return (
        await session.execute(
            select(User).where(User.role == UserRole.ADMIN).order_by(User.id).limit(1)
        )
    ).scalar_one_or_none()


async def seed_recipes(session: AsyncSession, owner: User) -> tuple[int, int]:
    """Przepisy demo właściciela. Tożsamość: (właściciel, nazwa)."""
    products = {
        product.normalized_name: product
        for product in (await session.execute(select(CanonicalProduct))).scalars().all()
    }
    existing = {
        recipe.name
        for recipe in (
            await session.execute(select(Recipe).where(Recipe.owner_user_id == owner.id))
        )
        .scalars()
        .all()
    }

    added = 0
    for demo in DEMO_RECIPES:
        if demo.name in existing:
            continue
        recipe = Recipe(
            name=demo.name,
            instructions=demo.instructions,
            base_servings=demo.base_servings,
            **ScopedQuery.ownership_for_create(owner, _demo_scope(owner)),
        )
        session.add(recipe)
        await session.flush()
        for position, ingredient in enumerate(demo.ingredients):
            product = products[normalize_name(ingredient.product)]
            normalized = normalized_demo_amount(
                ingredient.product, ingredient.quantity, ingredient.unit
            )
            session.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    product_id=product.id,
                    display_qty=Decimal(ingredient.quantity),
                    display_unit=ingredient.unit,
                    amount=normalized.amount,
                    amount_unit=normalized.unit,
                    position=position,
                )
            )
        added += 1

    await session.commit()
    return added, len(DEMO_RECIPES) - added


async def seed_plan(session: AsyncSession, owner: User) -> tuple[int, int]:
    """Tydzień planu właściciela od `DEMO_WEEK_START`. Tożsamość: (właściciel, data).

    Dzień, który już istnieje, jest pomijany W CAŁOŚCI — dopisywanie posiłków
    podwajałoby plan przy każdym uruchomieniu, a seed ma być idempotentny
    (08_TESTING §5).
    """
    products = {
        product.normalized_name: product
        for product in (await session.execute(select(CanonicalProduct))).scalars().all()
    }
    recipes = {
        recipe.name: recipe
        for recipe in (
            await session.execute(select(Recipe).where(Recipe.owner_user_id == owner.id))
        )
        .scalars()
        .all()
    }
    existing = {
        row.day
        for row in (await session.execute(select(PlanDay).where(PlanDay.owner_user_id == owner.id)))
        .scalars()
        .all()
    }

    added = 0
    for demo_day in DEMO_PLAN:
        day = DEMO_WEEK_START + timedelta(days=demo_day.offset)
        if day in existing:
            continue
        plan_day = PlanDay(day=day, **ScopedQuery.ownership_for_create(owner, _demo_scope(owner)))
        session.add(plan_day)
        await session.flush()
        for meal_position, demo_meal in enumerate(demo_day.meals):
            meal = PlanMeal(plan_day_id=plan_day.id, name=demo_meal.name, position=meal_position)
            session.add(meal)
            await session.flush()
            for item_position, demo_item in enumerate(demo_meal.items):
                session.add(_plan_item(meal.id, demo_item, item_position, products, recipes))
        added += 1

    await session.commit()
    return added, len(DEMO_PLAN) - added


def _plan_item(
    meal_id: int,
    demo: DemoPlanItem,
    position: int,
    products: dict[str, CanonicalProduct],
    recipes: dict[str, Recipe],
) -> PlanMealItem:
    """Pozycja planu demo: przepis z mnożnikiem albo produkt luzem ze ilością."""
    if demo.recipe is not None:
        recipe = recipes.get(demo.recipe)
        if recipe is None:
            raise SeedError(
                f"Przepis demo „{demo.recipe}” nie istnieje w danych konta demo, "
                "a plan demo się na niego powołuje. Przywróć przepis albo usuń "
                "jego dni planu i uruchom seed ponownie."
            )
        return PlanMealItem(
            plan_meal_id=meal_id,
            recipe_id=recipe.id,
            servings=Decimal(demo.servings),
            position=position,
        )
    assert demo.product is not None and demo.quantity is not None and demo.unit is not None
    normalized = normalized_demo_amount(demo.product, demo.quantity, demo.unit)
    return PlanMealItem(
        plan_meal_id=meal_id,
        product_id=products[normalize_name(demo.product)].id,
        amount=normalized.amount,
        amount_unit=normalized.unit,
        servings=Decimal(demo.servings),
        position=position,
    )


def _demo_scope(owner: User) -> Scope:
    """Dane demo są domowe, gdy właściciel ma rodzinę (03_DATABASE §4)."""
    return Scope.HOUSEHOLD if owner.household_id is not None else Scope.PRIVATE


class SeedError(RuntimeError):
    """Seed nie ma na czym pracować — komunikat po polsku, bez stacktrace'u."""


async def _run() -> str:
    factory = get_session_factory()
    async with factory() as session:
        added, skipped = await seed_products(session)
        retail_added, retail_skipped = await seed_store_and_retail(session)
        lines = [
            f"Seed demo: dodano {added} produktów, pominięto {skipped} (już istniały).",
            f"Produkty sklepowe: dodano {retail_added}, pominięto {retail_skipped}.",
        ]

        owner = await _first_admin(session)
        if owner is None:
            lines.append(
                "Przepisy i tydzień planu POMINIĘTE: nie ma konta ADMIN, a te dane "
                "muszą mieć właściciela. Utwórz konto (`task create-admin`) "
                "i uruchom seed ponownie."
            )
        else:
            recipes_added, recipes_skipped = await seed_recipes(session, owner)
            plan_added, plan_skipped = await seed_plan(session, owner)
            lines.append(
                f"Przepisy: dodano {recipes_added}, pominięto {recipes_skipped}. "
                f"Dni planu (od {DEMO_WEEK_START.isoformat()}): dodano {plan_added}, "
                f"pominięto {plan_skipped}. Właściciel: {owner.email}."
            )
    return "\n".join(lines)


def main() -> int:
    """Punkt wejścia `python -m scripts.seed_demo`."""
    try:
        get_settings()
        # loop_factory: na Windows psycopg async wymaga SelectorEventLoop.
        message = asyncio.run(_run(), loop_factory=selector_loop_factory())
    except (ConfigurationError, SeedError) as exc:
        print(f"Błąd: {exc}")
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
