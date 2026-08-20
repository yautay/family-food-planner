"""Silnik nutrition — własności (hypothesis, 08_TESTING §2.1).

Cztery niezmienniki z karty B05: addytywność agregacji, liniowość skalowania,
nieujemność wyników i `complete` fałszywe przy jakimkolwiek braku.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.catalog.models import VerificationStatus
from app.modules.nutrition.engine import aggregate, ingredient_nutrition, scale
from app.modules.nutrition.types import NUTRITION_NUMERIC_FIELDS, NutritionValues
from tests.unit.nutrition.helpers import product, values_of

pytestmark = pytest.mark.unit

#: Wartości „na 100" z realnego zakresu kolumn NUMERIC (bez NaN/inf — Decimal
#: w bazie ich nie zna).
per_100 = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("9999.99"), places=2, allow_nan=False
)
glycemic_indexes = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("110"), places=1, allow_nan=False
)
amounts = st.decimals(
    min_value=Decimal("0.001"), max_value=Decimal("99999.999"), places=3, allow_nan=False
)
multipliers = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("99.99"), places=2, allow_nan=False
)


@st.composite
def complete_products(draw: st.DrawFn) -> object:
    """Produkt z KOMPLETEM wartości (zweryfikowany) — baza własności liczbowych."""
    carbs = draw(per_100.filter(lambda value: value <= Decimal("100")))
    return product(
        name="Produkt",
        kcal_100=draw(per_100),
        protein_100=draw(per_100.filter(lambda value: value <= Decimal("100"))),
        fat_100=draw(per_100.filter(lambda value: value <= Decimal("100"))),
        carbs_100=carbs,
        fiber_100=draw(st.one_of(st.none(), per_100.filter(lambda value: value <= Decimal("100")))),
        sugars_100=draw(
            st.one_of(st.none(), per_100.filter(lambda value: value <= Decimal("100")))
        ),
        glycemic_index=draw(glycemic_indexes),
        verification_status=VerificationStatus.VERIFIED,
    )


@st.composite
def nutrition_values(draw: st.DrawFn) -> NutritionValues:
    """Dowolny (poprawny) wynik silnika — wejście agregacji i skalowania."""
    numbers = {field: draw(per_100) for field in NUTRITION_NUMERIC_FIELDS}
    complete = draw(st.booleans())
    missing = () if complete else ("Produkt: brak kalorii",)
    return NutritionValues(**numbers, complete=complete, missing=missing)


@given(st.lists(nutrition_values(), max_size=8), st.lists(nutrition_values(), max_size=8))
def test_agregacja_jest_addytywna(
    first: list[NutritionValues], second: list[NutritionValues]
) -> None:
    """aggregate(a + b) = aggregate(a) + aggregate(b) per pole (08_TESTING §2.1)."""
    combined = aggregate([*first, *second])
    separate_first = aggregate(first)
    separate_second = aggregate(second)

    for field in NUTRITION_NUMERIC_FIELDS:
        assert getattr(combined, field) == getattr(separate_first, field) + getattr(
            separate_second, field
        )


@given(nutrition_values(), multipliers)
def test_skalowanie_jest_liniowe(values: NutritionValues, multiplier: Decimal) -> None:
    """scale(v, k) mnoży każde pole dokładnie przez k (2x porcji = 2x wartości)."""
    scaled = scale(values, multiplier)

    for field in NUTRITION_NUMERIC_FIELDS:
        assert getattr(scaled, field) == getattr(values, field) * multiplier


@given(complete_products(), amounts)
def test_wynik_skladnika_jest_nieujemny(prod: object, amount: Decimal) -> None:
    """Nieujemne wejścia (CHECK-i bazy) dają nieujemne wyniki — także ŁG."""
    result = ingredient_nutrition(amount, prod)  # type: ignore[arg-type]

    assert all(value >= 0 for value in values_of(result).values())


@given(complete_products(), amounts)
def test_komplet_zweryfikowany_daje_complete_true(prod: object, amount: Decimal) -> None:
    result = ingredient_nutrition(amount, prod)  # type: ignore[arg-type]

    assert result.complete is True
    assert result.missing == ()


@given(st.lists(nutrition_values(), min_size=1, max_size=8))
def test_complete_jest_falszywe_gdy_jakikolwiek_brak(items: list[NutritionValues]) -> None:
    """Jedna niekompletna pozycja psuje komplet całości — nigdy odwrotnie."""
    total = aggregate(items)

    assert total.complete == all(item.complete for item in items)
    if not total.complete:
        assert total.missing != ()


# --- plan dnia: dwa poziomy agregacji (BATCH_06) ---------------------------------------

#: Dzień = lista posiłków, posiłek = lista pozycji. Tak liczy `planning/service.py`.
day_of_meals = st.lists(st.lists(nutrition_values(), max_size=5), max_size=5)


@given(day_of_meals)
def test_dzien_rowna_sie_sumie_posilkow_i_sumie_pozycji(
    meals: list[list[NutritionValues]],
) -> None:
    """Niezmiennik 02_DOMAIN §13.3: dzień = Σ posiłków = Σ wszystkich pozycji.

    Właśnie na tym stoi widok 1: kafelki dnia, sumy posiłków i wartości pozycji
    pochodzą z tego samego przejścia silnikiem, więc nie mogą się rozjechać.
    """
    per_meal = [aggregate(items) for items in meals]
    day_from_meals = aggregate(per_meal)
    day_from_items = aggregate([item for items in meals for item in items])

    for field in NUTRITION_NUMERIC_FIELDS:
        assert getattr(day_from_meals, field) == getattr(day_from_items, field)


@given(day_of_meals, multipliers)
def test_zmiana_mnoznika_skaluje_caly_dzien_liniowo(
    meals: list[list[NutritionValues]], multiplier: Decimal
) -> None:
    """Przeskalowanie każdej pozycji przeskalowuje dzień o ten sam czynnik (§13.3)."""
    baseline = aggregate([item for items in meals for item in items])
    scaled = aggregate([scale(item, multiplier) for items in meals for item in items])

    for field in NUTRITION_NUMERIC_FIELDS:
        assert getattr(scaled, field) == getattr(baseline, field) * multiplier


@given(day_of_meals)
def test_niekompletnosc_pozycji_propaguje_sie_na_dzien(
    meals: list[list[NutritionValues]],
) -> None:
    """Brak danych w JEDNEJ pozycji oznacza „niepełne dane" na kafelku dnia."""
    day = aggregate([aggregate(items) for items in meals])
    every_item_complete = all(item.complete for items in meals for item in items)

    assert day.complete == every_item_complete
