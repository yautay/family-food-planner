"""Silnik nutrition — serce systemu (ADR-008, 02_DOMAIN §6).

Czyste funkcje na `Decimal`: zero I/O, zero ORM, zero zegara i losowości.
Dane wchodzą parametrami (`ProductNutrition` z adaptera ADR-004, ilości na osi
wartości produktu), wynik wychodzi jako `NutritionValues`.

Wzory (02_DOMAIN §6):

    wartości(ilość, produkt)  = ilość/100 x wartości_100 produktu
    przepis (całość)          = Σ składników
    porcja                    = całość / base_servings
    pozycja planu             = porcja x mnożnik (Decimal)
    węglow. przyswajalne      = max(carbs - fiber, 0)
    ŁG                        = IG x węglow._przyswajalne_g / 100

Zasady twarde:

- kroki pośrednie BEZ zaokrągleń; zaokrągla wyłącznie `round_for_output`
  na krawędzi serializacji (kcal → 1, makra → 0,1 g, ŁG → 0,1, ROUND_HALF_UP),
- brak wartości/IG produktu i produkt UNVERIFIED ⇒ `complete=False` + wpis
  w `missing`; suma liczy się z dostępnych danych, nigdy ze zgadywanych zer,
- ilość składnika jest podawana na osi WARTOŚCI produktu (`basis_unit`:
  gramy dla masy i sztuk, mililitry dla objętości) — przeliczeniem zajmuje
  się `catalog/units.py`, silnik go nie powtarza.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from app.modules.nutrition.types import (
    NUTRITION_NUMERIC_FIELDS,
    ZERO_VALUES,
    NutritionValues,
    ProductNutrition,
)

__all__ = [
    "aggregate",
    "glycemic_load",
    "ingredient_nutrition",
    "portion_nutrition",
    "recipe_nutrition",
    "round_for_output",
    "scale",
]

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

#: Dopisek do `missing` dla produktu bez weryfikacji (02_DOMAIN §4.9).
UNVERIFIED_LABEL = "produkt niezweryfikowany"

#: Kwanty zaokrągleń wyjściowych (02_DOMAIN §6): kcal → 1, reszta → 0,1.
_OUTPUT_QUANTA: dict[str, Decimal] = {
    "kcal": Decimal("1"),
    "protein_g": Decimal("0.1"),
    "fat_g": Decimal("0.1"),
    "carbs_g": Decimal("0.1"),
    "fiber_g": Decimal("0.1"),
    "sugars_g": Decimal("0.1"),
    "glycemic_load": Decimal("0.1"),
}


def glycemic_load(glycemic_index: Decimal, carbs_g: Decimal, fiber_g: Decimal | None) -> Decimal:
    """ŁG = IG x węglowodany przyswajalne / 100 (02_DOMAIN §6, ADR-004).

    Węglowodany przyswajalne = max(carbs - fiber, 0); błonnik większy od
    węglowodanów (dane z etykiet bywają niespójne) daje 0, nie wartość ujemną.
    Brak błonnika liczy się jak zero błonnika — to założenie najostrożniejsze
    (zawyża ŁG), a o niekompletności danych mówi flaga, nie wynik.
    """
    digestible = max(carbs_g - (fiber_g if fiber_g is not None else _ZERO), _ZERO)
    return glycemic_index * digestible / _HUNDRED


def ingredient_nutrition(basis_amount: Decimal, product: ProductNutrition) -> NutritionValues:
    """Wartości porcji `basis_amount` produktu (na osi jego wartości „na 100").

    Braki NIE są zerami-po-cichu: pole bez danych nie wnosi nic do sumy,
    a wynik dostaje `complete=False` i komunikaty z adaptera (ADR-004).
    Produkt UNVERIFIED też obniża `complete` — widoki liczące żywienie mają
    ostrzegać, gdy w wyliczeniu biorą udział dane niesprawdzone (02_DOMAIN §4.9).
    """
    factor = basis_amount / _HUNDRED

    def scaled(value_100: Decimal | None) -> Decimal:
        return _ZERO if value_100 is None else value_100 * factor

    load = _ZERO
    if product.glycemic_index is not None and product.carbs_100 is not None:
        fiber = None if product.fiber_100 is None else product.fiber_100 * factor
        load = glycemic_load(product.glycemic_index, scaled(product.carbs_100), fiber)

    missing = list(product.missing)
    if not product.is_verified:
        missing.append(f"{product.name}: {UNVERIFIED_LABEL}")

    return NutritionValues(
        kcal=scaled(product.kcal_100),
        protein_g=scaled(product.protein_100),
        fat_g=scaled(product.fat_100),
        carbs_g=scaled(product.carbs_100),
        fiber_g=scaled(product.fiber_100),
        sugars_g=scaled(product.sugars_100),
        glycemic_load=load,
        complete=product.is_complete and product.is_verified,
        missing=tuple(missing),
    )


def aggregate(items: Sequence[NutritionValues]) -> NutritionValues:
    """Suma pozycji (składniki → przepis, pozycje → posiłek, posiłki → dzień).

    `complete` jest prawdziwe tylko, gdy KAŻDA pozycja jest kompletna; `missing`
    skleja komunikaty z zachowaniem kolejności i bez duplikatów (ten sam produkt
    w dwóch posiłkach dnia to jeden wpis, nie dwa).
    """
    if not items:
        return ZERO_VALUES

    totals = {
        field: sum((getattr(item, field) for item in items), _ZERO)
        for field in NUTRITION_NUMERIC_FIELDS
    }
    missing: list[str] = []
    for item in items:
        for entry in item.missing:
            if entry not in missing:
                missing.append(entry)

    return NutritionValues(
        **totals,
        complete=all(item.complete for item in items),
        missing=tuple(missing),
    )


def recipe_nutrition(ingredients: Sequence[NutritionValues]) -> NutritionValues:
    """Wartości CAŁEGO przepisu = suma składników (02_DOMAIN §6)."""
    return aggregate(ingredients)


def scale(values: NutritionValues, multiplier: Decimal) -> NutritionValues:
    """Przeskaluj wynik mnożnikiem porcji (Decimal — mnożnik 0.25 jest dokładny)."""
    return NutritionValues(
        **{field: getattr(values, field) * multiplier for field in NUTRITION_NUMERIC_FIELDS},
        complete=values.complete,
        missing=values.missing,
    )


def portion_nutrition(total: NutritionValues, base_servings: int) -> NutritionValues:
    """Wartości JEDNEJ porcji bazowej = całość / base_servings (int ≥ 1).

    Dzielenie Decimal nie zaokrągla do kwantu wyjściowego — 100/3 kcal niesie
    pełną precyzję kontekstu aż do `round_for_output`.
    """
    divisor = Decimal(base_servings)
    return NutritionValues(
        **{field: getattr(total, field) / divisor for field in NUTRITION_NUMERIC_FIELDS},
        complete=total.complete,
        missing=total.missing,
    )


def round_for_output(values: NutritionValues) -> NutritionValues:
    """Zaokrąglenie WYŁĄCZNIE na wyjściu (02_DOMAIN §6): kcal → 1, reszta → 0,1.

    `ROUND_HALF_UP`, bo tak zaokrągla człowiek przy etykiecie; wynik nadaje się
    prosto do serializacji `DecimalString`.
    """
    return NutritionValues(
        **{
            field: getattr(values, field).quantize(_OUTPUT_QUANTA[field], rounding=ROUND_HALF_UP)
            for field in NUTRITION_NUMERIC_FIELDS
        },
        complete=values.complete,
        missing=values.missing,
    )
