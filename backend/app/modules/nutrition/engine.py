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
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.core.errors import AppError
from app.modules.nutrition.types import (
    NUTRITION_NUMERIC_FIELDS,
    ZERO_VALUES,
    GoalStatus,
    GoalThresholds,
    NutritionValues,
    ProductNutrition,
)

__all__ = [
    "NutritionTargetError",
    "aggregate",
    "fit_servings_to_target",
    "glycemic_load",
    "goal_status",
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

#: Kwant mnożnika porcji — skala kolumny `plan_meal_items.servings` NUMERIC(6,2).
SERVINGS_QUANTUM = Decimal("0.01")
#: Zakres mnożnika mieszczący się w NUMERIC(6,2); propozycja nigdy z niego nie wyjdzie.
MIN_SERVINGS = SERVINGS_QUANTUM
MAX_SERVINGS = Decimal("9999.99")

NO_TARGET_MESSAGE = (
    "Ten posiłek nie ma celu kalorii, więc nie ma do czego dopasować porcji. "
    "Ustaw cel kcal posiłku i spróbuj ponownie."
)
ZERO_PORTION_MESSAGE = (
    "Nie znamy kalorii tej pozycji, więc nie da się policzyć mnożnika porcji. "
    "Uzupełnij wartości odżywcze produktów i spróbuj ponownie."
)

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


class NutritionTargetError(AppError):
    """422 — nie da się policzyć propozycji mnożnika (brak celu albo zerowe kcal).

    Wyjątek mieszka przy silniku, bo to on rozpoznaje sytuację; klasa jest czystą
    strukturą danych (precedens: `UnitConversionError` w `catalog/units.py`),
    więc nie łamie zakazu I/O w silniku (ADR-008).
    """

    status_code = 422
    code = "validation_error"


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


def goal_status(
    value: Decimal, target: Decimal | None, thresholds: GoalThresholds
) -> GoalStatus | None:
    """Status wartości względem celu (02_DOMAIN §6, progi D9 z `ui_settings`).

    `below` poniżej `low`% celu, `above` powyżej `high`%, `ok` pomiędzy —
    OBA progi należą do przedziału „prawidłowo" (dokładnie 90% i dokładnie 110%
    przy domyślnych progach to jeszcze `ok`).

    Brak celu (albo cel niedodatni) daje `None`, nie `below`: „nie wiem" i „za
    mało" to dwie różne informacje, a UI pokazuje je inaczej (06_UIUX §3.5).
    """
    if target is None or target <= _ZERO:
        return None

    percent = value * _HUNDRED / target
    if percent < thresholds.low:
        return GoalStatus.BELOW
    if percent > thresholds.high:
        return GoalStatus.ABOVE
    return GoalStatus.OK


def fit_servings_to_target(target_kcal: Decimal | None, portion_kcal: Decimal) -> Decimal:
    """Propozycja mnożnika porcji: `cel / kcal_porcji`, kwantowana W DÓŁ do 0,01.

    W dół, bo „dopasuj porcję do celu" ma celu NIE przekraczać (02_DOMAIN §6).
    Funkcja tylko liczy — zapis jest osobną, jawną akcją użytkownika (karta B06).

    Wynik trzyma się zakresu kolumny `servings` NUMERIC(6,2) i nigdy nie schodzi
    do zera: „0 porcji" nie jest odpowiedzią na pytanie „ile porcji zjeść",
    a takiego mnożnika nie dałoby się nawet zapisać.
    """
    if target_kcal is None or target_kcal <= _ZERO:
        raise NutritionTargetError(NO_TARGET_MESSAGE)
    if portion_kcal <= _ZERO:
        raise NutritionTargetError(ZERO_PORTION_MESSAGE)

    proposed = (target_kcal / portion_kcal).quantize(SERVINGS_QUANTUM, rounding=ROUND_DOWN)
    return min(max(proposed, MIN_SERVINGS), MAX_SERVINGS)


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
