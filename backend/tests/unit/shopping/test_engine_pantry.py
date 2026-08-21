"""Silnik zakupowy — odejmowanie spiżarni (08_TESTING §2.5).

Reguła nadrzędna: spiżarnia odejmuje się WYŁĄCZNIE na jawne życzenie
(`use_pantry=True`, 02_DOMAIN §8), nigdy poniżej zera, a preview pokazuje, co
odjęto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.units import AmountUnit, MeasureKind
from app.modules.shopping.engine import IssueKind, IssueSeverity, generate_preview
from tests.unit.shopping.helpers import (
    engine_input,
    fresh_product,
    line_for,
    pantry_item,
    preset_rounds,
    product,
    product_item,
    retail,
)

pytestmark = pytest.mark.unit


def test_pantry_subtracted_only_when_use_pantry_true() -> None:
    """Ten sam stan domowy: bez zgody użytkownika nie zmienia zakupów o gram."""
    common = {
        "products": (product(product_id=1),),
        "items": (product_item(item_id=1, day_offset=0, amount="1000"),),
        "pantry": (pantry_item(amount="400"),),
    }

    without = generate_preview(engine_input(use_pantry=False, **common))  # type: ignore[arg-type]
    with_pantry = generate_preview(engine_input(use_pantry=True, **common))  # type: ignore[arg-type]

    assert line_for(without, product_id=1).needed_amount == Decimal("1000")
    assert line_for(without, product_id=1).from_pantry_amount is None
    assert line_for(with_pantry, product_id=1).needed_amount == Decimal("600")
    assert line_for(with_pantry, product_id=1).from_pantry_amount == Decimal("400")


def test_pantry_never_negative_result() -> None:
    """Spiżarnia większa niż potrzeba daje 0, nigdy wartości ujemnej."""
    result = generate_preview(
        engine_input(
            use_pantry=True,
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount="200"),),
            pantry=(pantry_item(amount="5000"),),
        )
    )

    line = line_for(result, product_id=1)
    assert line.needed_amount == Decimal("0")
    assert line.from_pantry_amount == Decimal("200")
    assert line.raw_amount == Decimal("200")
    # Nie ma czego kupować, więc nie ma opakowań ani resztki.
    assert line.packages_count is None
    assert line.leftover_amount is None


def test_pantry_retail_vs_canonical_items() -> None:
    """Pozycja spiżarni po wariancie sklepowym odejmuje się od produktu kanonicznego."""
    result = generate_preview(
        engine_input(
            use_pantry=True,
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount="1500"),),
            pantry=(
                pantry_item(item_id=900, amount="200", product_id=1),
                pantry_item(item_id=901, amount="300", product_id=None, retail_product_id=500),
            ),
            retail_products=(retail(retail_product_id=500, product_id=1),),
        )
    )

    line = line_for(result, product_id=1)
    assert line.from_pantry_amount == Decimal("500")
    assert line.needed_amount == Decimal("1000")


def test_pantry_deductions_reported_in_preview() -> None:
    """Odjęcie przypisuje się TURZE, która kupuje pokryte dni (FIFO od `date_from`)."""
    # Świeży produkt kupowany w obu turach: 4 dni w „Niedzielę", 3 w „Środę".
    result = generate_preview(
        engine_input(
            use_pantry=True,
            rounds=preset_rounds(),
            products=(fresh_product(product_id=2),),
            items=tuple(
                product_item(item_id=index + 1, day_offset=index, product_id=2, amount="100")
                for index in range(7)
            ),
            pantry=(pantry_item(item_id=900, amount="250", product_id=2),),
        )
    )

    sunday = line_for(result, product_id=2, round_key="cfg-1")
    wednesday = line_for(result, product_id=2, round_key="cfg-2")
    # Spiżarnia (250 g) pokrywa dzień 1, dzień 2 i połowę dnia 3 — wszystkie
    # w oknie pierwszej tury.
    assert sunday.from_pantry_amount == Decimal("250")
    assert sunday.needed_amount == Decimal("150")
    assert wednesday.from_pantry_amount == Decimal("0")
    assert wednesday.needed_amount == Decimal("300")


def test_pantry_w_jednostce_niezgodnej_z_produktem_daje_ostrzezenie() -> None:
    """Nieprzeliczalny stan domowy NIE jest odejmowany — kupimy z zapasem i ostrzeżemy."""
    result = generate_preview(
        engine_input(
            use_pantry=True,
            products=(product(product_id=1, name="Mleko", measure_kind=MeasureKind.VOLUME),),
            items=(
                product_item(item_id=1, day_offset=0, amount="500", unit=AmountUnit.MILLILITER),
            ),
            pantry=(pantry_item(item_id=900, amount="200", unit=AmountUnit.GRAM),),
        )
    )

    assert line_for(result, product_id=1).needed_amount == Decimal("500")
    issue = next(
        issue for issue in result.issues if issue.kind is IssueKind.PANTRY_AMOUNT_NOT_CONVERTIBLE
    )
    assert issue.severity is IssueSeverity.WARNING
    assert issue.pantry_item_id == 900


def test_already_have_zostaje_w_preview_jako_oznaczone() -> None:
    """„Mam już w domu" oznacza pozycję, ale jej nie usuwa (02_DOMAIN §9.1 krok 5)."""
    result = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount="600"),),
            retail_products=(retail(retail_product_id=500, product_id=1),),
            already_have=(1,),
        )
    )

    line = line_for(result, product_id=1)
    assert line.already_have is True
    assert line.needed_amount == Decimal("600")
    # Nic nie kupujemy, więc opakowań nie liczymy i nie marudzimy o wariant.
    assert line.packages_count is None
    assert result.issues == ()
