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

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from app.modules.catalog.nutrition_adapter import ProductNutrition

__all__ = [
    "DEFAULT_THRESHOLDS",
    "NUTRITION_NUMERIC_FIELDS",
    "NUTRITION_THRESHOLDS_KEY",
    "ZERO_VALUES",
    "GoalStatus",
    "GoalThresholds",
    "NutritionValues",
    "ProductNutrition",
    "thresholds_from_ui_settings",
]

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


class GoalStatus(StrEnum):
    """Status wartości względem celu dnia/posiłku (02_DOMAIN §6, D9)."""

    BELOW = "below"
    OK = "ok"
    ABOVE = "above"


@dataclass(frozen=True)
class GoalThresholds:
    """Progi statusów w PROCENTACH celu (D9: domyślnie 90-110%, edytowalne).

    Trzymamy je jako `Decimal`, bo cała arytmetyka domenowa jest na `Decimal`
    (ADR-008) — procent wchodzi do porównania `wartość / cel x 100`.
    """

    low: Decimal
    high: Decimal


#: Klucz progów w `users.ui_settings` (JSONB) — jedna nazwa dla API i silnika.
NUTRITION_THRESHOLDS_KEY = "nutrition_thresholds"

#: Domyślne progi z decyzji D9. Batch B06 przyjmuje je bez osobnego zatwierdzenia.
DEFAULT_THRESHOLDS = GoalThresholds(low=Decimal("90"), high=Decimal("110"))


def thresholds_from_ui_settings(ui_settings: Mapping[str, Any] | None) -> GoalThresholds:
    """Progi użytkownika z `ui_settings` albo domyślne 90/110 (D9).

    Funkcja jest czysta i CELOWO pobłażliwa: JSONB może zawierać wpis sprzed
    zmiany kontraktu albo ręcznie zmieniony w bazie, a widok planu nie może się
    z tego powodu wywalić na 500. Wartość spoza kontraktu ⇒ domyślne progi;
    walidacją wejścia zajmuje się schemat `PATCH /auth/me/ui-settings`.
    """
    raw = (ui_settings or {}).get(NUTRITION_THRESHOLDS_KEY)
    if not isinstance(raw, Mapping):
        return DEFAULT_THRESHOLDS
    try:
        low = Decimal(str(raw["low"]))
        high = Decimal(str(raw["high"]))
    except (KeyError, TypeError, InvalidOperation):
        return DEFAULT_THRESHOLDS
    if low <= 0 or high <= low:
        return DEFAULT_THRESHOLDS
    return GoalThresholds(low=low, high=high)
