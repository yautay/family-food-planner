"""Silnik zakupowy — opakowania i resztki (08_TESTING §2.6).

`packages = ceil(potrzeba / wielkość)`, resztka = kupione - potrzeba i ZAWSZE
jest zwracana (02_DOMAIN §9.3). Wybór wariantu: najmniejsza resztka, remis →
mniejsze opakowanie.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.units import AmountUnit, MeasureKind
from app.modules.shopping.engine import (
    IssueKind,
    IssueSeverity,
    PreviewResult,
    RetailInput,
    generate_preview,
)
from tests.unit.shopping.helpers import engine_input, line_for, product, product_item, retail

pytestmark = pytest.mark.unit


def _preview(
    *,
    amount: str,
    variants: tuple[RetailInput, ...],
    unit: AmountUnit = AmountUnit.GRAM,
    **product_kwargs: object,
) -> PreviewResult:
    """Preview jednego produktu luzem z podanymi wariantami opakowań."""
    return generate_preview(
        engine_input(
            products=(product(product_id=1, **product_kwargs),),  # type: ignore[arg-type]
            items=(product_item(item_id=1, day_offset=0, amount=amount, unit=unit),),
            retail_products=variants,
        )
    )


def test_ceil_packages_count() -> None:
    """1400 g potrzeby przy opakowaniu 500 g to 3 opakowania, nie 2,8."""
    result = _preview(
        amount="1400", variants=(retail(retail_product_id=500, package_amount="500"),)
    )

    line = line_for(result, product_id=1)
    assert line.packages_count == 3
    assert line.package_amount == Decimal("500")


def test_potrzeba_mniejsza_niz_opakowanie_to_jedno_opakowanie() -> None:
    """Przypadek brzegowy z 08_TESTING §2: potrzeba < najmniejsze opakowanie."""
    result = _preview(amount="120", variants=(retail(retail_product_id=500, package_amount="500"),))

    line = line_for(result, product_id=1)
    assert line.packages_count == 1
    assert line.leftover_amount == Decimal("380")


def test_leftover_computed_and_exposed() -> None:
    """Resztka jest wyliczana zawsze, także gdy wypada dokładnie zero."""
    exact = _preview(amount="1000", variants=(retail(retail_product_id=500, package_amount="500"),))
    over = _preview(amount="1050", variants=(retail(retail_product_id=500, package_amount="500"),))

    assert line_for(exact, product_id=1).packages_count == 2
    assert line_for(exact, product_id=1).leftover_amount == Decimal("0")
    assert line_for(over, product_id=1).packages_count == 3
    assert line_for(over, product_id=1).leftover_amount == Decimal("450")


def test_no_retail_falls_back_to_grams() -> None:
    """Brak wariantu = pozycja w jednostce podstawowej + ostrzeżenie (nie bloker)."""
    result = _preview(amount="250", variants=())

    line = line_for(result, product_id=1)
    assert line.unit is AmountUnit.GRAM
    assert line.needed_amount == Decimal("250")
    assert line.retail_product_id is None
    assert line.packages_count is None
    assert line.leftover_amount is None
    assert line.label == "Mąka pszenna"

    issue = result.issues[0]
    assert issue.kind is IssueKind.MISSING_RETAIL
    assert issue.severity is IssueSeverity.WARNING
    assert issue.product_id == 1


def test_variant_choice_smallest_leftover() -> None:
    """Z trzech opakowań wybieramy to, które zostawia najmniej."""
    result = _preview(
        amount="900",
        variants=(
            retail(retail_product_id=501, label="Mąka 500 g", package_amount="500"),
            retail(retail_product_id=502, label="Mąka 1 kg", package_amount="1000"),
            retail(retail_product_id=503, label="Mąka 2 kg", package_amount="2000"),
        ),
    )

    line = line_for(result, product_id=1)
    # 500 g → 2 opak. = 1000 (resztka 100), 1 kg → 1 opak. (resztka 100),
    # 2 kg → 1 opak. (resztka 1100). Remis 100 rozstrzyga MNIEJSZE opakowanie.
    assert line.retail_product_id == 501
    assert line.leftover_amount == Decimal("100")
    # Selektor pokazuje wszystkie warianty, posortowane po wielkości.
    assert [option.retail_product_id for option in line.retail_options] == [501, 502, 503]


def test_variant_tie_prefers_smaller_package() -> None:
    """Przy identycznej resztce wygrywa mniejsze opakowanie (08_TESTING §2.6)."""
    result = _preview(
        amount="400",
        variants=(
            retail(retail_product_id=601, label="Duże 800 g", package_amount="800"),
            retail(retail_product_id=602, label="Małe 400 g", package_amount="400"),
        ),
    )

    line = line_for(result, product_id=1)
    assert line.retail_product_id == 602
    assert line.packages_count == 1
    assert line.leftover_amount == Decimal("0")


def test_wybor_uzytkownika_wygrywa_z_automatem() -> None:
    """Wariant wskazany w `/resolve` jest używany nawet przy większej resztce."""
    result = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount="400"),),
            retail_products=(
                retail(retail_product_id=601, label="Małe 400 g", package_amount="400"),
                retail(retail_product_id=602, label="Duże 1 kg", package_amount="1000"),
            ),
            retail_choices=((1, 602),),
        )
    )

    line = line_for(result, product_id=1)
    assert line.retail_product_id == 602
    assert line.leftover_amount == Decimal("600")
    assert line.label == "Duże 1 kg"


def test_wariant_archiwalny_nie_jest_proponowany() -> None:
    """Silnik nie proponuje opakowań, których nie ma już na półce (ADR-012)."""
    result = _preview(
        amount="400",
        variants=(retail(retail_product_id=601, package_amount="400", is_archived=True),),
    )

    line = line_for(result, product_id=1)
    assert line.retail_options == ()
    assert line.retail_product_id is None
    assert IssueKind.MISSING_RETAIL.value in [issue.kind.value for issue in result.issues]


def test_wariant_w_innej_jednostce_niz_produkt_jest_pomijany() -> None:
    """Opakowanie na innej osi niż produkt nie ma prawa policzyć opakowań (D15)."""
    result = _preview(
        amount="400",
        measure_kind=MeasureKind.MASS,
        variants=(
            retail(retail_product_id=601, package_amount="400", package_unit=AmountUnit.MILLILITER),
        ),
    )

    assert line_for(result, product_id=1).retail_options == ()
    assert line_for(result, product_id=1).packages_count is None


def test_opakowanie_w_sztukach_dla_produktu_na_sztuki() -> None:
    """Produkt mierzony w sztukach liczy opakowania w sztukach, nie w gramach."""
    result = _preview(
        amount="7",
        unit=AmountUnit.PIECE,
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60"),
        variants=(
            retail(
                retail_product_id=700,
                label="Jajka 10 szt.",
                package_amount="10",
                package_unit=AmountUnit.PIECE,
            ),
        ),
    )

    line = line_for(result, product_id=1)
    assert line.unit is AmountUnit.PIECE
    assert line.packages_count == 1
    assert line.leftover_amount == Decimal("3")
