"""Walidacja kcal w review importu — próg 10% i przypadki „nie da się policzyć".

Testowane są CZYSTE funkcje `review_service`: `_meal_result` dostaje gotowe
encje (bez sesji) i zwraca dataclassę, więc scenariusz zapisuje się w kilku
linijkach zamiast w pełnym round-tripie przez bazę.

Dwie reguły, których pilnują te testy:

1. **Porównanie jest PER POSIŁEK.** `pdf_kcal` w jadłospisie opisuje posiłek,
   a BATCH_15 skopiował tę wartość do każdego dania posiłku — kolacja złożona
   z zupy i kanapki musi więc porównać SUMĘ obu dań (01_PDF_AUDIT §3.1,
   errata §9.1).
2. **Brak wartości produktu to „nie wiem", nie rozjazd.** Import zakłada
   produkty UNVERIFIED bez kalorii; zgłaszanie przy nich mismatchu byłoby
   generowaniem szumu przy każdym pierwszym imporcie (Implementation Notes B16).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.models import CanonicalProduct, MeasureKind
from app.modules.importer.models import StagedIngredient, StagedRecipe, StagedRecipeResolution
from app.modules.importer.review_service import KCAL_TOLERANCE, _meal_result

pytestmark = pytest.mark.unit


def _product(product_id: int, *, kcal_100: Decimal | None) -> CanonicalProduct:
    """Produkt kanoniczny bez sesji — testujemy funkcję, nie mapowanie ORM."""
    return CanonicalProduct(
        id=product_id,
        name=f"Produkt {product_id}",
        normalized_name=f"produkt {product_id}",
        category_id=1,
        measure_kind=MeasureKind.MASS,
        kcal_100=kcal_100,
    )


def _dish(
    *,
    pdf_kcal: Decimal | None,
    grams: Decimal,
    product_id: int | None = 1,
    servings: int | None = None,
    from_extras: bool = False,
    resolution: StagedRecipeResolution | None = None,
) -> StagedRecipe:
    """Danie z JEDNYM składnikiem — tyle wystarcza, żeby ustawić kalorie."""
    dish = StagedRecipe(
        id=1,
        import_job_id=1,
        name="Danie",
        day_label="Poniedziałek",
        meal_label="OBIAD",
        pdf_kcal=pdf_kcal,
        resolved_servings=servings,
        resolution=resolution,
    )
    dish.ingredients = [
        StagedIngredient(
            id=1,
            staged_recipe_id=1,
            raw_name="Składnik",
            grams=grams,
            confirmed_product_id=product_id,
            create_new_product=False,
            from_extras_section=from_extras,
        )
    ]
    return dish


def test_prog_wynosi_dziesiec_procent() -> None:
    """Wartość progu jest kontraktem z ADR-011 — zmiana wymaga decyzji, nie commita."""
    percent = KCAL_TOLERANCE * 100

    assert percent == Decimal("10")


def test_rozjazd_ponizej_progu_nie_jest_rozjazdem() -> None:
    """9,9% mieści się w tolerancji: 901 kcal wyliczone wobec 1000 kcal z PDF."""
    dish = _dish(pdf_kcal=Decimal("1000"), grams=Decimal("1000"))

    result = _meal_result([dish], {1: _product(1, kcal_100=Decimal("90.1"))})

    assert result.computed_kcal == Decimal("901")
    assert result.delta_pct == Decimal("-9.9")
    assert abs(result.delta_pct) < KCAL_TOLERANCE * 100


def test_rozjazd_powyzej_progu_jest_widoczny_w_procentach() -> None:
    """10,1% już wychodzi poza tolerancję i to ta liczba trafia do issue."""
    dish = _dish(pdf_kcal=Decimal("1000"), grams=Decimal("1000"))

    result = _meal_result([dish], {1: _product(1, kcal_100=Decimal("89.9"))})

    assert result.computed_kcal == Decimal("899")
    assert result.delta_pct == Decimal("-10.1")
    assert abs(result.delta_pct) > KCAL_TOLERANCE * 100


def test_kalorie_licza_sie_na_porcje_a_nie_na_caly_przepis() -> None:
    """Przepis na 7 porcji: 700 g składników to 100 g na porcję (§5.1)."""
    dish = _dish(pdf_kcal=Decimal("100"), grams=Decimal("700"), servings=7)

    result = _meal_result([dish], {1: _product(1, kcal_100=Decimal("100"))})

    assert result.computed_kcal == Decimal("100")
    assert result.delta_pct == Decimal("0.0")


def test_sekcja_produkty_nie_dzieli_sie_przez_liczbe_porcji() -> None:
    """Dodatek z sekcji `Produkty` jest podany NA PORCJĘ (dług U22, §7).

    Bez tego rozróżnienia ziemniaki do gołąbków weszłyby do wyliczenia
    siedmiokrotnie mniejsze i mismatch pojawiłby się tam, gdzie go nie ma.
    """
    dish = _dish(pdf_kcal=Decimal("100"), grams=Decimal("100"), servings=7, from_extras=True)

    result = _meal_result([dish], {1: _product(1, kcal_100=Decimal("100"))})

    assert result.computed_kcal == Decimal("100")


def test_posilek_dwudaniowy_porownuje_sume_obu_dan() -> None:
    """`pdf_kcal` opisuje POSIŁEK — jedno danie kolacji nie ma z czym się równać."""
    zupa = _dish(pdf_kcal=Decimal("200"), grams=Decimal("100"))
    kanapka = _dish(pdf_kcal=Decimal("200"), grams=Decimal("100"))
    kanapka.id = 2

    result = _meal_result([zupa, kanapka], {1: _product(1, kcal_100=Decimal("100"))})

    assert result.computed_kcal == Decimal("200")
    assert result.delta_pct == Decimal("0.0")


def test_niezmapowany_skladnik_wstrzymuje_walidacje() -> None:
    """Dopóki nie wiadomo, co to za produkt, nie ma czego porównywać."""
    dish = _dish(pdf_kcal=Decimal("100"), grams=Decimal("100"), product_id=None)

    result = _meal_result([dish], {})

    assert result.computed_kcal is None
    assert result.delta_pct is None
    assert "wskazany produkt" in result.reason


def test_produkt_bez_kalorii_daje_komunikat_a_nie_falszywy_rozjazd() -> None:
    """Świeżo założony produkt UNVERIFIED nie ma wartości — to nie jest mismatch."""
    dish = _dish(pdf_kcal=Decimal("100"), grams=Decimal("100"))

    result = _meal_result([dish], {1: _product(1, kcal_100=None)})

    assert result.computed_kcal is None
    assert result.delta_pct is None
    assert "bez wartości odżywczych" in result.reason


def test_pominiete_danie_nie_wchodzi_do_wyliczenia() -> None:
    """`skip` znaczy „tego nie importujemy" — także dla walidacji kalorii."""
    dish = _dish(
        pdf_kcal=Decimal("100"),
        grams=Decimal("100"),
        resolution=StagedRecipeResolution.SKIP,
    )

    result = _meal_result([dish], {1: _product(1, kcal_100=Decimal("100"))})

    assert result.computed_kcal is None
    assert "pominięte" in result.reason


def test_brak_kalorii_w_dokumencie_nie_blokuje_wyliczenia() -> None:
    """Kalorie wyliczone pokazujemy nawet bez wartości z PDF — nie ma tylko delty."""
    dish = _dish(pdf_kcal=None, grams=Decimal("100"))

    result = _meal_result([dish], {1: _product(1, kcal_100=Decimal("100"))})

    assert result.computed_kcal == Decimal("100")
    assert result.delta_pct is None
