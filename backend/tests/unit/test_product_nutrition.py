"""Adapter `ProductNutrition` — rdzeń, rozszerzenia i flagi kompletności (ADR-004).

Reguła, którą te testy utrwalają: **brak danych to nie zero**. Produkt bez IG
nie ma „IG = 0", tylko `complete=False` i pozycję w `missing` — bo ŁG liczone
z zerowego IG wyszłoby zerowe i wyglądałoby na prawdę.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    ProductNutrientValue,
    VerificationStatus,
)
from app.modules.catalog.nutrition_adapter import measure_for, nutrition_for
from app.modules.catalog.units import AmountUnit, UnitWeight

pytestmark = pytest.mark.unit


def product(**overrides: object) -> CanonicalProduct:
    """Encja produktu zbudowana w pamięci — adapter nie dotyka bazy."""
    values: dict[str, object] = {
        "id": 1,
        "name": "Cebula",
        "normalized_name": "cebula",
        "category_id": 1,
        "measure_kind": MeasureKind.MASS,
        "piece_weight_g": None,
        "kcal_100": Decimal("40.00"),
        "protein_100": Decimal("1.10"),
        "fat_100": Decimal("0.10"),
        "carbs_100": Decimal("9.30"),
        "fiber_100": Decimal("1.70"),
        "sugars_100": Decimal("4.20"),
        "glycemic_index": Decimal("15.0"),
        "nutrition_source": "usda:11282",
        "verification_status": VerificationStatus.VERIFIED,
        "is_archived": False,
    }
    values.update(overrides)
    return CanonicalProduct(**values)


def test_rdzen_wartosci_przepisuje_sie_z_kolumn() -> None:
    """Kolumny `canonical_products` to rdzeń modelu wartości (ADR-004)."""
    nutrition = nutrition_for(product())

    assert nutrition.product_id == 1
    assert nutrition.kcal_100 == Decimal("40.00")
    assert nutrition.carbs_100 == Decimal("9.30")
    assert nutrition.glycemic_index == Decimal("15.0")
    assert nutrition.basis_unit is AmountUnit.GRAM


def test_produkt_objetosciowy_ma_wartosci_na_100_ml() -> None:
    nutrition = nutrition_for(product(measure_kind=MeasureKind.VOLUME))

    assert nutrition.basis_unit is AmountUnit.MILLILITER


def test_rozszerzenia_pochodza_z_rejestru_nutrientow() -> None:
    """Mikroelementy dokłada się bez migracji — adapter je scala z rdzeniem."""
    extras = [
        ProductNutrientValue(product_id=1, nutrient_code="vit_c", amount_per_100=Decimal("7.400")),
        ProductNutrientValue(product_id=1, nutrient_code="iron", amount_per_100=Decimal("0.210")),
    ]

    nutrition = nutrition_for(product(), extras)

    assert nutrition.extra("vit_c") == Decimal("7.400")
    assert nutrition.extra("iron") == Decimal("0.210")
    assert nutrition.extra("magnez") is None


def test_komplet_wartosci_daje_flage_kompletnosci() -> None:
    nutrition = nutrition_for(product())

    assert nutrition.is_complete is True
    assert nutrition.missing == ()


def test_brak_indeksu_glikemicznego_oznacza_wynik_niekompletny() -> None:
    """Bez IG nie policzymy ŁG — 02_DOMAIN §6 każe to zgłosić, nie zgadywać."""
    nutrition = nutrition_for(product(glycemic_index=None))

    assert nutrition.has_core_macros is True
    assert nutrition.has_glycemic_index is False
    assert nutrition.is_complete is False
    assert nutrition.missing == ("Cebula: brak indeksu glikemicznego",)


def test_brak_makro_wymienia_kazda_brakujaca_wartosc() -> None:
    """Komunikaty trafiają wprost do `nutrition.missing` w API (04_API §1)."""
    nutrition = nutrition_for(product(kcal_100=None, protein_100=None, glycemic_index=None))

    assert nutrition.has_core_macros is False
    assert nutrition.missing == (
        "Cebula: brak kalorii",
        "Cebula: brak białka",
        "Cebula: brak indeksu glikemicznego",
    )


def test_swiezo_utworzony_produkt_nie_ma_zadnych_wartosci() -> None:
    """Tak wygląda produkt po inline create USERA — pusty, ale legalny."""
    nutrition = nutrition_for(
        product(
            kcal_100=None,
            protein_100=None,
            fat_100=None,
            carbs_100=None,
            fiber_100=None,
            sugars_100=None,
            glycemic_index=None,
            nutrition_source=None,
            verification_status=VerificationStatus.UNVERIFIED,
        )
    )

    assert nutrition.is_complete is False
    assert nutrition.is_verified is False
    assert len(nutrition.missing) == 5


def test_weglowodany_przyswajalne_odejmuja_blonnik() -> None:
    """`max(carbs minus fiber, 0)` — podstawa ładunku glikemicznego (02_DOMAIN §6)."""
    nutrition = nutrition_for(product())

    assert nutrition.digestible_carbs_100 == Decimal("7.60")


def test_weglowodany_przyswajalne_nie_schodza_ponizej_zera() -> None:
    """Dane z etykiet bywają niespójne (błonnik > węglowodany) — wynik nie może być ujemny."""
    nutrition = nutrition_for(product(carbs_100=Decimal("2.00"), fiber_100=Decimal("3.00")))

    assert nutrition.digestible_carbs_100 == Decimal("0")


def test_brak_blonnika_nie_jest_traktowany_jak_zero_weglowodanow() -> None:
    """Bez błonnika przyswajalne = całość węglowodanów; brak węglowodanów = brak wyniku."""
    assert nutrition_for(product(fiber_100=None)).digestible_carbs_100 == Decimal("9.30")
    assert nutrition_for(product(carbs_100=None)).digestible_carbs_100 is None


def test_adapter_buduje_tez_dane_dla_konwersji_jednostek() -> None:
    """`measure_for` to ten sam most encja → dataclass, tyle że dla `units.py`."""
    measure = measure_for(
        product(measure_kind=MeasureKind.PIECE, piece_weight_g=Decimal("105.00")),
        [UnitWeight(unit_label="garść", grams_per_unit=Decimal("30.00"))],
    )

    assert measure.measure_kind is MeasureKind.PIECE
    assert measure.piece_weight_g == Decimal("105.00")
    assert measure.unit_weights[0].unit_label == "garść"
