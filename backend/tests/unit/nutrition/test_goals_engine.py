"""Cele w silniku: `goal_status` i `fit_servings_to_target` (08_TESTING §2.1-2.2).

Progi statusów pochodzą z decyzji D9 (domyślnie 90-110% celu, konfigurowalne
per użytkownik). Wszystkie asercje na `Decimal` — porównania float w tym
obszarze są błędem samym w sobie.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.nutrition.engine import (
    MAX_SERVINGS,
    MIN_SERVINGS,
    NutritionTargetError,
    fit_servings_to_target,
    goal_status,
)
from app.modules.nutrition.types import (
    DEFAULT_THRESHOLDS,
    NUTRITION_THRESHOLDS_KEY,
    GoalStatus,
    GoalThresholds,
    thresholds_from_ui_settings,
)

pytestmark = pytest.mark.unit


# --- goal_status --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1799"), GoalStatus.BELOW),
        (Decimal("1800"), GoalStatus.OK),  # dokładnie 90% celu to jeszcze „ok"
        (Decimal("2000"), GoalStatus.OK),
        (Decimal("2200"), GoalStatus.OK),  # dokładnie 110% celu to wciąż „ok"
        (Decimal("2201"), GoalStatus.ABOVE),
    ],
)
def test_progi_brzegowe_naleza_do_przedzialu_prawidlowo(
    value: Decimal, expected: GoalStatus
) -> None:
    """Przy celu 2000 kcal i progach 90/110: 1800 i 2200 to wciąż „prawidłowo" (D9)."""
    assert goal_status(value, Decimal("2000"), DEFAULT_THRESHOLDS) is expected


def test_progi_niestandardowe_przesuwaja_granice() -> None:
    """Progi z `ui_settings` (80/120) zmieniają wynik dla tej samej wartości."""
    strict = GoalThresholds(low=Decimal("95"), high=Decimal("105"))
    loose = GoalThresholds(low=Decimal("80"), high=Decimal("120"))

    assert goal_status(Decimal("1850"), Decimal("2000"), strict) is GoalStatus.BELOW
    assert goal_status(Decimal("1850"), Decimal("2000"), loose) is GoalStatus.OK


def test_brak_celu_daje_brak_statusu_a_nie_za_malo() -> None:
    """„Nie wiem" to inna informacja niż „za mało" (06_UIUX §3.5)."""
    assert goal_status(Decimal("1200"), None, DEFAULT_THRESHOLDS) is None
    assert goal_status(Decimal("1200"), Decimal("0"), DEFAULT_THRESHOLDS) is None


def test_zero_przy_ustawionym_celu_to_za_malo() -> None:
    """Pusty dzień z celem 2000 kcal ma status „za mało", nie brak statusu."""
    assert goal_status(Decimal("0"), Decimal("2000"), DEFAULT_THRESHOLDS) is GoalStatus.BELOW


# --- thresholds_from_ui_settings ------------------------------------------------------


def test_progi_czytane_sa_z_ustawien_uzytkownika() -> None:
    """Klucz `nutrition_thresholds` z JSONB trafia wprost do progów silnika."""
    settings = {NUTRITION_THRESHOLDS_KEY: {"low": 85, "high": 115}}

    assert thresholds_from_ui_settings(settings) == GoalThresholds(
        low=Decimal("85"), high=Decimal("115")
    )


@pytest.mark.parametrize(
    "settings",
    [
        None,
        {},
        {NUTRITION_THRESHOLDS_KEY: None},
        {NUTRITION_THRESHOLDS_KEY: {"low": 90}},
        {NUTRITION_THRESHOLDS_KEY: {"low": 120, "high": 100}},
        {NUTRITION_THRESHOLDS_KEY: {"low": 0, "high": 100}},
        {NUTRITION_THRESHOLDS_KEY: {"low": "abc", "high": "def"}},
    ],
)
def test_wpis_spoza_kontraktu_daje_progi_domyslne(settings: dict[str, object] | None) -> None:
    """Uszkodzony JSONB nie może wywalić widoku planu — wracamy do 90/110."""
    assert thresholds_from_ui_settings(settings) == DEFAULT_THRESHOLDS


# --- fit_servings_to_target -----------------------------------------------------------


def test_dokladny_cel_daje_dokladny_mnoznik() -> None:
    """Cel 600 kcal przy porcji 300 kcal to dokładnie 2,00 porcji."""
    assert fit_servings_to_target(Decimal("600"), Decimal("300")) == Decimal("2.00")


def test_mnoznik_zaokragla_sie_w_dol_zeby_nie_przekroczyc_celu() -> None:
    """500/300 = 1,666… → 1,66 (w dół), bo 1,67 x 300 = 501 kcal przekracza cel."""
    proposed = fit_servings_to_target(Decimal("500"), Decimal("300"))

    assert proposed == Decimal("1.66")
    assert proposed * Decimal("300") <= Decimal("500")


def test_porcja_bez_kalorii_to_blad_domenowy() -> None:
    """Bez kalorii porcji nie ma czego dopasowywać — 422 z komunikatem po polsku."""
    with pytest.raises(NutritionTargetError) as error:
        fit_servings_to_target(Decimal("600"), Decimal("0"))

    assert error.value.status_code == 422
    assert "wartości odżywcze" in error.value.message


def test_brak_celu_to_blad_domenowy() -> None:
    """Posiłek bez `kcal_target` nie ma do czego dopasować porcji."""
    with pytest.raises(NutritionTargetError) as error:
        fit_servings_to_target(None, Decimal("300"))

    assert error.value.status_code == 422
    assert "cel" in error.value.message.lower()


def test_propozycja_nigdy_nie_schodzi_do_zera() -> None:
    """Cel 1 kcal przy porcji 1000 kcal: 0,00 nie jest odpowiedzią — minimum to 0,01."""
    assert fit_servings_to_target(Decimal("1"), Decimal("1000")) == MIN_SERVINGS


def test_propozycja_miesci_sie_w_skali_kolumny_servings() -> None:
    """Wynik nie może wyjść poza NUMERIC(6,2), bo nie dałoby się go zapisać."""
    assert fit_servings_to_target(Decimal("99999"), Decimal("0.001")) == MAX_SERVINGS
