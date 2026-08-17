"""Typy silnika nutrition (ADR-008): wynik obliczeń i wejście z adaptera.

Wejściem silnika jest `ProductNutrition` z `catalog/nutrition_adapter.py` —
JEDYNE miejsce, które zna kolumny wartości odżywczych (ADR-004). Ten moduł
świadomie go re-eksportuje zamiast definiować drugi raz: silnik i jego
konsumenci importują wszystko z `app.modules.nutrition.types`, a tożsamość
typu pozostaje jedna.

`NutritionValues` to KONTRAKT między batchami (karta B05, Cross-Batch Impact):
B06/B07/B10/B13 budują na tym kształcie — zmiany wyłącznie addytywne.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.catalog.nutrition_adapter import ProductNutrition

__all__ = ["NUTRITION_NUMERIC_FIELDS", "ZERO_VALUES", "NutritionValues", "ProductNutrition"]

#: Pola liczbowe wyniku — jedno źródło dla agregacji, skalowania i zaokrągleń.
NUTRITION_NUMERIC_FIELDS: tuple[str, ...] = (
    "kcal",
    "protein_g",
    "fat_g",
    "carbs_g",
    "fiber_g",
    "sugars_g",
    "glycemic_load",
)


@dataclass(frozen=True)
class NutritionValues:
    """Wynik obliczeń żywieniowych — kształt pola `nutrition` z 04_API §1.

    Liczby są SUMĄ Z DOSTĘPNYCH danych (02_DOMAIN §6): brakująca wartość
    produktu nie wnosi nic do sumy, ale wynik dostaje `complete=False`
    i pozycję w `missing` — brak danych NIGDY nie udaje zera bez flagi.
    Wartości bez zaokrągleń; zaokrągla wyłącznie `round_for_output` na
    krawędzi serializacji.
    """

    kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal
    fiber_g: Decimal
    sugars_g: Decimal
    glycemic_load: Decimal
    #: Czy w obliczeniu wzięły udział komplety wartości ZWERYFIKOWANYCH produktów.
    complete: bool
    #: Komunikaty PL „<produkt>: brak …" — wprost do tooltipa „niepełne dane".
    missing: tuple[str, ...]


#: Element neutralny agregacji (pusta lista składników / pusty posiłek).
ZERO_VALUES = NutritionValues(
    kcal=Decimal("0"),
    protein_g=Decimal("0"),
    fat_g=Decimal("0"),
    carbs_g=Decimal("0"),
    fiber_g=Decimal("0"),
    sugars_g=Decimal("0"),
    glycemic_load=Decimal("0"),
    complete=True,
    missing=(),
)
