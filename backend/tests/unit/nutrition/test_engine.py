"""Silnik nutrition — przykłady liczbowe i przypadki brzegowe (08_TESTING §2.1).

Wszystkie asercje na `Decimal` — porównania float są w tym obszarze błędem
samym w sobie (pułapka z 08_TESTING §2.1). Wyniki przykładów policzone ręcznie.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.models import VerificationStatus
from app.modules.nutrition.engine import (
    UNVERIFIED_LABEL,
    aggregate,
    glycemic_load,
    ingredient_nutrition,
    portion_nutrition,
    recipe_nutrition,
    round_for_output,
    scale,
)
from app.modules.nutrition.types import ZERO_VALUES, NutritionValues
from tests.unit.nutrition.helpers import full_product, product, values_of

pytestmark = pytest.mark.unit


# --- glycemic_load -----------------------------------------------------------------


def test_lg_liczy_sie_z_weglowodanow_przyswajalnych() -> None:
    """ŁG = IG x (węglowodany - błonnik) / 100: 55 x (30-5) / 100 = 13,75."""
    assert glycemic_load(Decimal("55"), Decimal("30"), Decimal("5")) == Decimal("13.75")


def test_blonnik_wiekszy_od_weglowodanow_daje_lg_zero() -> None:
    """Przyswajalne nie schodzą poniżej zera (02_DOMAIN §6) — ŁG = 0, nie ujemne."""
    assert glycemic_load(Decimal("55"), Decimal("3"), Decimal("10")) == Decimal("0")


def test_brak_blonnika_liczy_sie_jak_zero_blonnika() -> None:
    """Najostrożniejsze założenie: bez błonnika całe węglowodany są przyswajalne."""
    assert glycemic_load(Decimal("50"), Decimal("20"), None) == Decimal("10")


# --- ingredient_nutrition -----------------------------------------------------------


def test_wartosci_skladnika_to_ilosc_przez_100_razy_wartosci_produktu() -> None:
    """250 g produktu „na 100": kcal 50→125, białko 1,5→3,75, ŁG 40x(25-5)/100=8."""
    result = ingredient_nutrition(Decimal("250"), full_product())

    assert values_of(result) == {
        "kcal": Decimal("125.0000"),
        "protein_g": Decimal("3.7500"),
        "fat_g": Decimal("0.5000"),
        "carbs_g": Decimal("25.0000"),
        "fiber_g": Decimal("5.0000"),
        "sugars_g": Decimal("15.0000"),
        "glycemic_load": Decimal("8.000000"),
    }
    assert result.complete is True
    assert result.missing == ()


def test_brak_makra_nie_jest_zerem_po_cichu() -> None:
    """Produkt bez kcal: suma liczy się z dostępnych, ale flaga i `missing` mówią prawdę."""
    incomplete = full_product(name="Mąka bez kcal", kcal_100=None)

    result = ingredient_nutrition(Decimal("100"), incomplete)

    assert result.kcal == Decimal("0")
    assert result.protein_g == Decimal("1.5000")
    assert result.complete is False
    assert "Mąka bez kcal: brak kalorii" in result.missing


def test_brak_ig_daje_lg_zero_i_wpis_w_missing() -> None:
    """Bez IG nie ma ŁG — wynik częściowy z flagą, nigdy zgadywany (D11)."""
    no_gi = full_product(name="Twaróg", glycemic_index=None)

    result = ingredient_nutrition(Decimal("200"), no_gi)

    assert result.glycemic_load == Decimal("0")
    assert result.kcal == Decimal("100.0000")
    assert result.complete is False
    assert "Twaróg: brak indeksu glikemicznego" in result.missing


def test_produkt_niezweryfikowany_obniza_complete() -> None:
    """02_DOMAIN §4.9: UNVERIFIED w wyliczeniu ⇒ ostrzeżenie w widokach."""
    unverified = full_product(name="Nowość", verification_status=VerificationStatus.UNVERIFIED)

    result = ingredient_nutrition(Decimal("100"), unverified)

    assert result.complete is False
    assert f"Nowość: {UNVERIFIED_LABEL}" in result.missing


def test_produkt_bez_zadnych_wartosci_daje_zera_i_pelna_liste_brakow() -> None:
    """Produkt świeżo po inline create: wszystkie rdzenie NULL (03_DATABASE §3)."""
    empty = product(name="Cebula", verification_status=VerificationStatus.UNVERIFIED)

    result = ingredient_nutrition(Decimal("150"), empty)

    assert all(value == Decimal("0") for value in values_of(result).values())
    assert result.complete is False
    assert result.missing == (
        "Cebula: brak kalorii",
        "Cebula: brak białka",
        "Cebula: brak tłuszczu",
        "Cebula: brak węglowodanów",
        "Cebula: brak indeksu glikemicznego",
        f"Cebula: {UNVERIFIED_LABEL}",
    )


def test_blonnik_wiekszy_od_weglowodanow_w_skladniku_daje_lg_zero() -> None:
    """Brzeg z 08_TESTING §2.1: przyswajalne 0 ⇒ ŁG 0 (dane z etykiet bywają niespójne)."""
    fibrous = full_product(carbs_100=Decimal("4.00"), fiber_100=Decimal("9.00"))

    result = ingredient_nutrition(Decimal("100"), fibrous)

    assert result.glycemic_load == Decimal("0")
    assert result.complete is True


# --- agregacja i przepis -------------------------------------------------------------


def test_przepis_to_suma_skladnikow() -> None:
    """Σ per pole; komplety obu składników dają komplet przepisu."""
    first = ingredient_nutrition(Decimal("100"), full_product())
    second = ingredient_nutrition(Decimal("50"), full_product(name="Drugi"))

    total = recipe_nutrition([first, second])

    assert total.kcal == Decimal("75.0000")
    assert total.carbs_g == Decimal("15.0000")
    assert total.complete is True


def test_agregacja_pustej_listy_daje_element_neutralny() -> None:
    """Pusty posiłek/przepis = zera i complete=True (nie ma czego brakować)."""
    assert aggregate([]) == ZERO_VALUES


def test_agregacja_deduplikuje_komunikaty_missing() -> None:
    """Ten sam produkt w dwóch pozycjach dnia to jeden wpis w tooltipie, nie dwa."""
    no_gi = full_product(name="Ryż", glycemic_index=None)
    one = ingredient_nutrition(Decimal("100"), no_gi)
    two = ingredient_nutrition(Decimal("50"), no_gi)

    total = aggregate([one, two])

    assert total.complete is False
    assert total.missing.count("Ryż: brak indeksu glikemicznego") == 1


# --- porcja i skalowanie -------------------------------------------------------------


def test_porcja_dzieli_calosc_przez_base_servings() -> None:
    """Gołąbki na 7 porcji: 700 kcal całości → 100 kcal porcji."""
    total = NutritionValues(
        kcal=Decimal("700"),
        protein_g=Decimal("35"),
        fat_g=Decimal("21"),
        carbs_g=Decimal("70"),
        fiber_g=Decimal("14"),
        sugars_g=Decimal("7"),
        glycemic_load=Decimal("28"),
        complete=True,
        missing=(),
    )

    portion = portion_nutrition(total, 7)

    assert portion.kcal == Decimal("100")
    assert portion.glycemic_load == Decimal("4")


def test_base_servings_1_niczego_nie_zmienia() -> None:
    """Brzeg z 08_TESTING §2.1: dzielenie przez 1 to identyczność."""
    total = ingredient_nutrition(Decimal("123"), full_product())

    assert values_of(portion_nutrition(total, 1)) == values_of(total)


def test_dzielenie_nie_gubi_precyzji_przed_wyjsciem() -> None:
    """100/3 kcal niesie pełną precyzję Decimal — zaokrągla dopiero round_for_output."""
    total = NutritionValues(
        kcal=Decimal("100"),
        protein_g=Decimal("0"),
        fat_g=Decimal("0"),
        carbs_g=Decimal("0"),
        fiber_g=Decimal("0"),
        sugars_g=Decimal("0"),
        glycemic_load=Decimal("0"),
        complete=True,
        missing=(),
    )

    portion = portion_nutrition(total, 3)

    assert portion.kcal == Decimal("100") / Decimal("3")
    assert portion.kcal != Decimal("33.3")
    assert round_for_output(portion).kcal == Decimal("33")


def test_mnoznik_cwierc_porcji_jest_dokladny() -> None:
    """Brzeg z karty: mnożnik 0.25 — na Decimal dokładny, bez residuów floata."""
    portion = ingredient_nutrition(Decimal("100"), full_product())

    quarter = scale(portion, Decimal("0.25"))

    assert quarter.kcal == Decimal("12.500000")
    assert quarter.carbs_g == Decimal("2.500000")


def test_skalowanie_zachowuje_flagi_kompletnosci() -> None:
    """Mnożnik zmienia liczby, nie wiedzę o brakach."""
    partial = ingredient_nutrition(Decimal("100"), full_product(glycemic_index=None))

    doubled = scale(partial, Decimal("2"))

    assert doubled.complete is False
    assert doubled.missing == partial.missing


# --- round_for_output ----------------------------------------------------------------


def test_zaokraglenie_wyjsciowe_kcal_do_1_makra_do_01() -> None:
    """02_DOMAIN §6: kcal → 1, makra i ŁG → 0,1, ROUND_HALF_UP."""
    raw = NutritionValues(
        kcal=Decimal("123.5"),
        protein_g=Decimal("3.75"),
        fat_g=Decimal("0.04"),
        carbs_g=Decimal("25.049"),
        fiber_g=Decimal("4.96"),
        sugars_g=Decimal("15.25"),
        glycemic_load=Decimal("8.05"),
        complete=True,
        missing=(),
    )

    rounded = round_for_output(raw)

    assert rounded.kcal == Decimal("124")
    assert rounded.protein_g == Decimal("3.8")
    assert rounded.fat_g == Decimal("0.0")
    assert rounded.carbs_g == Decimal("25.0")
    assert rounded.fiber_g == Decimal("5.0")
    assert rounded.sugars_g == Decimal("15.3")
    assert rounded.glycemic_load == Decimal("8.1")


def test_zaokraglenie_nie_dotyka_flag() -> None:
    partial = ingredient_nutrition(Decimal("33"), full_product(fat_100=None))

    rounded = round_for_output(partial)

    assert rounded.complete is False
    assert rounded.missing == partial.missing
