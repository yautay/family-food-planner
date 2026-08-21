"""Silnik zakupowy — determinizm i odtwarzalność wejścia (ADR-008, karta B10).

Dwa niezmienniki: ten sam `EngineInput` daje IDENTYCZNY `PreviewResult`, a
`params` (`dump_input`/`load_input`) odtwarza wejście bez straty — bo z tego
zapisu liczą preview zarówno `GET` generacji, jak i `resolve`.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.modules.catalog.units import AmountUnit, MeasureKind
from app.modules.shopping.engine import (
    PARAMS_VERSION,
    EngineInput,
    ShoppingParamsError,
    dump_input,
    generate_preview,
    load_input,
)
from tests.unit.shopping.helpers import (
    engine_input,
    fresh_product,
    ingredient,
    pantry_item,
    preset_rounds,
    product,
    product_item,
    recipe,
    recipe_item,
    retail,
)

pytestmark = pytest.mark.unit


def _rich_input() -> EngineInput:
    """Wejście dotykające wszystkich gałęzi pipeline'u — jedno dla wszystkich testów."""
    return engine_input(
        rounds=preset_rounds(),
        use_pantry=True,
        products=(
            product(product_id=1, name="Mąka pszenna"),
            fresh_product(product_id=2, name="Pomidor"),
            product(
                product_id=3,
                name="Jajko",
                measure_kind=MeasureKind.PIECE,
                piece_weight_g=Decimal("60"),
                category_id=4,
                category_name="Nabiał i jaja",
                category_position=3,
            ),
        ),
        recipes=(
            recipe(
                recipe_id=100,
                name="Naleśniki",
                base_servings=3,
                ingredients=(
                    ingredient(1, "300"),
                    ingredient(3, "2", AmountUnit.PIECE),
                ),
            ),
        ),
        items=(
            recipe_item(item_id=1, day_offset=0, recipe_id=100, servings="2"),
            recipe_item(item_id=2, day_offset=5, recipe_id=100, servings="1.5"),
            product_item(item_id=3, day_offset=1, product_id=2, amount="250"),
            product_item(item_id=4, day_offset=6, product_id=2, amount="180"),
        ),
        pantry=(
            pantry_item(item_id=900, amount="150", product_id=1),
            pantry_item(item_id=901, amount="1", unit=AmountUnit.PIECE, product_id=3),
        ),
        retail_products=(
            retail(retail_product_id=500, product_id=1, label="Mąka 1 kg", package_amount="1000"),
            retail(retail_product_id=501, product_id=1, label="Mąka 500 g", package_amount="500"),
            retail(
                retail_product_id=502,
                product_id=3,
                label="Jajka 10 szt.",
                package_amount="10",
                package_unit=AmountUnit.PIECE,
            ),
        ),
        already_have=(2,),
        retail_choices=((1, 500),),
    )


def test_dwa_wywolania_na_tym_samym_wejsciu_daja_identyczny_wynik() -> None:
    """Determinizm: wynik jest równy pole po polu, także kolejnością tur i pozycji."""
    data = _rich_input()

    first = generate_preview(data)
    second = generate_preview(data)

    assert first == second
    # Równość dataclass nie sprawdza kolejności wewnątrz krotek osobno — dlatego
    # jeszcze raz, jawnie, po identyfikatorach.
    assert [
        (round_view.key, [line.product_id for line in round_view.items])
        for round_view in first.rounds
    ] == [
        (round_view.key, [line.product_id for line in round_view.items])
        for round_view in second.rounds
    ]


def test_params_odtwarzaja_identyczne_wejscie_i_identyczny_preview() -> None:
    """`dump_input` → JSON → `load_input` nie gubi ani `Decimal`, ani decyzji."""
    data = _rich_input()

    params = dump_input(data)
    assert params["v"] == PARAMS_VERSION

    restored = load_input(params)
    assert restored == data
    assert generate_preview(restored) == generate_preview(data)


def test_params_z_innej_wersji_daja_czytelny_409() -> None:
    """Zapis z przyszłej/innej wersji silnika nie wysadza odczytu generacji."""
    params = dump_input(_rich_input())
    params["v"] = PARAMS_VERSION + 1

    with pytest.raises(ShoppingParamsError) as exc:
        load_input(params)
    assert exc.value.status_code == 409
    assert "Wygeneruj zakupy ponownie" in str(exc.value)


def test_params_bez_wymaganego_pola_daja_czytelny_409() -> None:
    """Uszkodzony `params` to 409 z instrukcją, nigdy 500."""
    params = dump_input(_rich_input())
    del params["products"]

    with pytest.raises(ShoppingParamsError):
        load_input(params)


def test_kolejnosc_wejscia_nie_zmienia_wyniku() -> None:
    """Odwrócona kolejność pozycji, produktów i wariantów daje ten sam preview.

    To jest test SORTOWAŃ: gdyby gdziekolwiek został zbiór albo kolejność
    wstawiania, ten test by to złapał.
    """
    data = _rich_input()
    reversed_data = replace(
        data,
        items=tuple(reversed(data.items)),
        products=tuple(reversed(data.products)),
        pantry=tuple(reversed(data.pantry)),
        retail=tuple(reversed(data.retail)),
    )

    assert generate_preview(reversed_data) == generate_preview(data)
