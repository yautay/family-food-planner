"""Wspólne fabryki wejścia silnika zakupowego — bez ORM i bez bazy (ADR-008).

Wzorowane na `tests/unit/nutrition/helpers.py`: testy silnika budują dataclassy
wprost, dokładnie takie, jakie podaje serwis. Domyślny tydzień testowy to
poniedziałek 2030-01-07 - niedziela 2030-01-13 (konwencja E2E „daty z lat
2030+" obowiązuje też tutaj, żeby przykłady dały się porównać z E2E).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.modules.catalog.models import Perishability
from app.modules.catalog.units import AmountUnit, MeasureKind
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
)

#: Poniedziałek — pierwszy dzień testowego tygodnia planu.
WEEK_START = date(2030, 1, 7)
#: Niedziela tego samego tygodnia.
WEEK_END = date(2030, 1, 13)


def day(offset: int) -> date:
    """Dzień tygodnia testowego liczony od poniedziałku (0 = poniedziałek)."""
    return WEEK_START + timedelta(days=offset)


def product(
    *,
    product_id: int = 1,
    name: str = "Mąka pszenna",
    measure_kind: MeasureKind = MeasureKind.MASS,
    piece_weight_g: Decimal | None = None,
    category_id: int | None = 10,
    category_name: str | None = "Makarony, ryż i kasze",
    category_position: int = 5,
    perishability: Perishability | None = Perishability.DURABLE,
) -> ProductInput:
    """Produkt trwały mierzony w masie — najczęstszy przypadek w testach."""
    return ProductInput(
        product_id=product_id,
        name=name,
        measure_kind=measure_kind,
        piece_weight_g=piece_weight_g,
        category_id=category_id,
        category_name=category_name,
        category_position=category_position,
        perishability=perishability,
    )


def fresh_product(**overrides: object) -> ProductInput:
    """Produkt ŚWIEŻY (kategoria z `perishability=fresh`) — wejście testów tur."""
    values: dict[str, object] = {
        "product_id": 2,
        "name": "Pomidor",
        "category_id": 1,
        "category_name": "Warzywa",
        "category_position": 0,
        "perishability": Perishability.FRESH,
    }
    values.update(overrides)
    return product(**values)  # type: ignore[arg-type]


def ingredient(product_id: int, amount: str, unit: AmountUnit = AmountUnit.GRAM) -> IngredientInput:
    """Składnik przepisu z ilością znormalizowaną (jak po zapisie w B05)."""
    return IngredientInput(product_id=product_id, amount=Decimal(amount), amount_unit=unit)


def recipe(
    *,
    recipe_id: int = 100,
    name: str = "Zupa",
    base_servings: int = 2,
    ingredients: tuple[IngredientInput, ...] = (),
) -> RecipeInput:
    """Przepis o `base_servings` porcjach bazowych."""
    return RecipeInput(
        recipe_id=recipe_id, name=name, base_servings=base_servings, ingredients=ingredients
    )


def recipe_item(
    *,
    item_id: int,
    day_offset: int,
    recipe_id: int = 100,
    servings: str = "1",
    meal_name: str = "Obiad",
) -> PlanItemInput:
    """Pozycja planu z przepisem i mnożnikiem porcji."""
    return PlanItemInput(
        item_id=item_id,
        day=day(day_offset),
        meal_name=meal_name,
        servings=Decimal(servings),
        recipe_id=recipe_id,
    )


def product_item(
    *,
    item_id: int,
    day_offset: int,
    product_id: int = 1,
    amount: str = "100",
    unit: AmountUnit = AmountUnit.GRAM,
    servings: str = "1",
    meal_name: str = "Śniadanie",
) -> PlanItemInput:
    """Pozycja planu z produktem luzem (ilość x mnożnik — 02_DOMAIN §13.3)."""
    return PlanItemInput(
        item_id=item_id,
        day=day(day_offset),
        meal_name=meal_name,
        servings=Decimal(servings),
        product_id=product_id,
        amount=Decimal(amount),
        amount_unit=unit,
    )


def pantry_item(
    *,
    item_id: int = 900,
    amount: str = "500",
    unit: AmountUnit = AmountUnit.GRAM,
    product_id: int | None = 1,
    retail_product_id: int | None = None,
) -> PantryInput:
    """Pozycja stanu domowego (kontrakt B08: ilość już na osi produktu)."""
    return PantryInput(
        item_id=item_id,
        amount=Decimal(amount),
        amount_unit=unit,
        product_id=product_id,
        retail_product_id=retail_product_id,
    )


def retail(
    *,
    retail_product_id: int = 500,
    product_id: int = 1,
    label: str = "Mąka 1 kg",
    package_amount: str = "1000",
    package_unit: AmountUnit = AmountUnit.GRAM,
    store_id: int | None = None,
    store_name: str | None = None,
    is_archived: bool = False,
) -> RetailInput:
    """Wariant sklepowy z opakowaniem na osi produktu (niezmiennik B09)."""
    return RetailInput(
        retail_product_id=retail_product_id,
        product_id=product_id,
        label=label,
        package_amount=Decimal(package_amount),
        package_unit=package_unit,
        store_id=store_id,
        store_name=store_name,
        is_archived=is_archived,
    )


def single_round(
    *, key: str = "all", name: str = "Zakupy", covers_days: int = 7
) -> tuple[RoundInput, ...]:
    """Jedna tura kupująca wszystko na cały zakres — najprostsza konfiguracja."""
    return (RoundInput(key=key, name=name, mode=RoundMode.ALL, covers_days=covers_days),)


def preset_rounds() -> tuple[RoundInput, ...]:
    """Preset z 02_DOMAIN §9.2: „Niedziela" (7 dni + świeże na 4) i „Środa" (3 dni)."""
    return (
        RoundInput(
            key="cfg-1",
            name="Niedziela",
            mode=RoundMode.DURABLE_PLUS_FRESH_WINDOW,
            covers_days=7,
            fresh_days=4,
            shopping_weekday=6,
        ),
        RoundInput(
            key="cfg-2",
            name="Środa",
            mode=RoundMode.FRESH_ONLY,
            covers_days=3,
            shopping_weekday=2,
        ),
    )


def engine_input(
    *,
    date_from: date = WEEK_START,
    date_to: date = WEEK_END,
    use_pantry: bool = False,
    rounds: tuple[RoundInput, ...] | None = None,
    items: tuple[PlanItemInput, ...] = (),
    recipes: tuple[RecipeInput, ...] = (),
    products: tuple[ProductInput, ...] = (),
    pantry: tuple[PantryInput, ...] = (),
    retail_products: tuple[RetailInput, ...] = (),
    already_have: tuple[int, ...] = (),
    retail_choices: tuple[tuple[int, int], ...] = (),
    dismissed_issues: tuple[str, ...] = (),
) -> EngineInput:
    """Kompletne wejście silnika; domyślnie jedna tura na cały tydzień."""
    return EngineInput(
        date_from=date_from,
        date_to=date_to,
        use_pantry=use_pantry,
        rounds=single_round() if rounds is None else rounds,
        items=items,
        recipes=recipes,
        products=products,
        pantry=pantry,
        retail=retail_products,
        already_have=already_have,
        retail_choices=retail_choices,
        dismissed_issues=dismissed_issues,
    )


def all_lines(result: PreviewResult) -> list[PreviewLine]:
    """Wszystkie pozycje preview, w kolejności tur."""
    return [line for round_view in result.rounds for line in round_view.items]


def line_for(
    result: PreviewResult, product_id: int, *, round_key: str | None = None
) -> PreviewLine:
    """Jedna pozycja preview — asercje czyta się wtedy jak zdanie."""
    matches = [
        line
        for line in all_lines(result)
        if line.product_id == product_id and (round_key is None or line.round_key == round_key)
    ]
    assert len(matches) == 1, (
        f"Oczekiwano jednej pozycji produktu {product_id}, jest {len(matches)}"
    )
    return matches[0]


def issue_kinds(result: PreviewResult) -> list[str]:
    """Rodzaje niejasności w kolejności zwróconej przez silnik."""
    return [issue.kind.value for issue in result.issues]
