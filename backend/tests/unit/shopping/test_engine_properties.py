"""Silnik zakupowy — własności (hypothesis, 08_TESTING §2.4-2.6).

Trzy niezmienniki z karty B10:

1. suma ilości po agregacji = suma zapotrzebowań przed agregacją,
2. odejmowanie spiżarni nigdy nie schodzi poniżej zera,
3. `packages_count x package_size >= potrzeba` (i mniej niż jedno opakowanie
   zapasu — inaczej `ceil` liczyłby o jedno za dużo).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.catalog.units import AmountUnit
from app.modules.shopping.engine import generate_preview
from tests.unit.shopping.helpers import (
    all_lines,
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

#: Ilości z realnego zakresu kolumny NUMERIC(10,3).
amounts = st.decimals(
    min_value=Decimal("0.001"), max_value=Decimal("99999.999"), places=3, allow_nan=False
)
#: Wielkości opakowań z zakresu NUMERIC(8,2), zawsze dodatnie.
package_sizes = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("99999.99"), places=2, allow_nan=False
)
day_offsets = st.integers(min_value=0, max_value=6)


@given(rows=st.lists(st.tuples(day_offsets, amounts), min_size=1, max_size=12))
def test_suma_po_agregacji_rowna_sumie_przed(rows: list[tuple[int, Decimal]]) -> None:
    """Agregacja i podział na tury nie zmieniają SUMY zapotrzebowania."""
    items = tuple(
        product_item(item_id=index + 1, day_offset=offset, product_id=1, amount=str(amount))
        for index, (offset, amount) in enumerate(rows)
    )
    result = generate_preview(
        engine_input(
            rounds=preset_rounds(),
            products=(fresh_product(product_id=1),),
            items=items,
        )
    )

    assert sum((line.needed_amount for line in all_lines(result)), Decimal("0")) == sum(
        (amount for _, amount in rows), Decimal("0")
    )


@given(need=amounts, at_home=amounts)
def test_odejmowanie_spizarni_nigdy_ponizej_zera(need: Decimal, at_home: Decimal) -> None:
    """Potrzeba po odjęciu stanu domowego jest zawsze ≥ 0, a odjęto ≤ potrzeba."""
    result = generate_preview(
        engine_input(
            use_pantry=True,
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount=str(need)),),
            pantry=(pantry_item(amount=str(at_home)),),
        )
    )

    line = line_for(result, product_id=1)
    assert line.needed_amount >= Decimal("0")
    assert line.from_pantry_amount is not None
    assert line.from_pantry_amount <= need
    assert line.needed_amount + line.from_pantry_amount == need


@given(need=amounts, package=package_sizes)
def test_opakowania_pokrywaja_potrzebe_i_nie_kupuja_za_duzo(
    need: Decimal, package: Decimal
) -> None:
    """`ceil`: kupione ≥ potrzeba, a zapas mniejszy niż jedno opakowanie."""
    result = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount=str(need)),),
            retail_products=(retail(retail_product_id=500, package_amount=str(package)),),
        )
    )

    line = line_for(result, product_id=1)
    assert line.packages_count is not None
    assert line.packages_count >= 1
    bought = package * line.packages_count
    assert bought >= line.needed_amount
    assert bought - line.needed_amount < package
    assert line.leftover_amount == bought - line.needed_amount


@given(
    rows=st.lists(st.tuples(day_offsets, amounts), min_size=1, max_size=8),
    at_home=st.decimals(min_value=Decimal("0.001"), max_value=Decimal("500"), places=3),
    package=package_sizes,
)
def test_calosc_pipeline_zachowuje_bilans(
    rows: list[tuple[int, Decimal]], at_home: Decimal, package: Decimal
) -> None:
    """Suma (potrzeba + odjęte ze spiżarni) po wszystkich turach = suma zapotrzebowania.

    To niezmiennik CAŁEGO pipeline'u: podział na tury i odjęcie spiżarni mogą
    przenosić ilości między pozycjami, ale nie mogą ich tworzyć ani gubić.
    """
    items = tuple(
        product_item(
            item_id=index + 1,
            day_offset=offset,
            product_id=1,
            amount=str(amount),
            unit=AmountUnit.GRAM,
        )
        for index, (offset, amount) in enumerate(rows)
    )
    result = generate_preview(
        engine_input(
            use_pantry=True,
            rounds=preset_rounds(),
            products=(fresh_product(product_id=1),),
            items=items,
            pantry=(pantry_item(amount=str(at_home)),),
            retail_products=(retail(retail_product_id=500, package_amount=str(package)),),
        )
    )

    lines = all_lines(result)
    total_needed = sum((line.needed_amount for line in lines), Decimal("0"))
    total_pantry = sum((line.from_pantry_amount or Decimal("0") for line in lines), Decimal("0"))
    assert total_needed + total_pantry == sum((amount for _, amount in rows), Decimal("0"))
