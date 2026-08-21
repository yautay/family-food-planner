"""Silnik zakupowy — agregacja zapotrzebowania (08_TESTING §2.4).

Cztery przypadki wymagane kartą B10: wiele przepisów i dni na jeden produkt,
jednostki mieszane, produkty luzem z planu, mnożnik porcji.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.units import AmountUnit, MeasureKind
from app.modules.shopping.engine import IssueKind, IssueSeverity, generate_preview
from tests.unit.shopping.helpers import (
    engine_input,
    ingredient,
    line_for,
    product,
    product_item,
    recipe,
    recipe_item,
)

pytestmark = pytest.mark.unit


def test_aggregates_same_product_across_recipes_and_days() -> None:
    """Ten sam produkt z dwóch przepisów i trzech dni daje JEDNĄ pozycję z sumą."""
    result = generate_preview(
        engine_input(
            products=(product(product_id=1, name="Cebula"),),
            recipes=(
                recipe(
                    recipe_id=100,
                    name="Zupa",
                    base_servings=2,
                    ingredients=(ingredient(1, "200"),),
                ),
                recipe(
                    recipe_id=101,
                    name="Sos",
                    base_servings=1,
                    ingredients=(ingredient(1, "50"),),
                ),
            ),
            items=(
                recipe_item(item_id=1, day_offset=0, recipe_id=100, servings="2"),
                recipe_item(item_id=2, day_offset=1, recipe_id=100, servings="2"),
                recipe_item(item_id=3, day_offset=2, recipe_id=101, servings="3"),
            ),
        )
    )

    line = line_for(result, product_id=1)
    # 2x(200/2x2) + 150 = 400 + 150
    assert line.needed_amount == Decimal("550")
    assert line.days == tuple(sorted(line.days))
    assert len(line.days) == 3


def test_aggregates_two_items_with_same_recipe_in_one_day() -> None:
    """Szablon DOPISUJE posiłki, więc jeden dzień ma prawo mieć ten sam przepis dwa razy.

    To nie duplikat do zdeduplikowania (karta B10 §Context, ustalenie po B07) —
    obie pozycje wnoszą zapotrzebowanie.
    """
    result = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            recipes=(recipe(recipe_id=100, base_servings=1, ingredients=(ingredient(1, "100"),)),),
            items=(
                recipe_item(item_id=1, day_offset=0, recipe_id=100),
                recipe_item(item_id=2, day_offset=0, recipe_id=100, meal_name="Kolacja"),
            ),
        )
    )

    assert line_for(result, product_id=1).needed_amount == Decimal("200")


def test_mixed_units_normalized_before_aggregation() -> None:
    """Sztuki i gramy tego samego produktu sumują się NA OSI PRODUKTU (szt.).

    Jednostka domowa produktu w sztukach daje gramy (`normalize_amount` →
    `basis_unit`), więc zakupy muszą je sprowadzić z powrotem na sztuki —
    inaczej sumowałyby jabłka z gramami.
    """
    result = generate_preview(
        engine_input(
            products=(
                product(
                    product_id=1,
                    name="Jajko",
                    measure_kind=MeasureKind.PIECE,
                    piece_weight_g=Decimal("60"),
                ),
            ),
            items=(
                product_item(item_id=1, day_offset=0, amount="3", unit=AmountUnit.PIECE),
                # 120 g „z opakowania" = 2 sztuki po 60 g.
                product_item(item_id=2, day_offset=1, amount="120", unit=AmountUnit.GRAM),
            ),
        )
    )

    line = line_for(result, product_id=1)
    assert line.unit is AmountUnit.PIECE
    assert line.needed_amount == Decimal("5")


def test_loose_plan_items_included() -> None:
    """Pozycja z produktem luzem wchodzi do zakupów jak składnik przepisu."""
    result = generate_preview(
        engine_input(
            products=(product(product_id=1, name="Chleb"), product(product_id=2, name="Ryż")),
            recipes=(recipe(recipe_id=100, base_servings=1, ingredients=(ingredient(2, "80"),)),),
            items=(
                product_item(item_id=1, day_offset=0, product_id=1, amount="70"),
                recipe_item(item_id=2, day_offset=0, recipe_id=100),
            ),
        )
    )

    assert line_for(result, product_id=1).needed_amount == Decimal("70")
    assert line_for(result, product_id=2).needed_amount == Decimal("80")


def test_multiplied_servings_scale_amounts() -> None:
    """Mnożnik skaluje zapotrzebowanie liniowo — dla przepisu i dla produktu luzem."""
    single = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            recipes=(recipe(recipe_id=100, base_servings=2, ingredients=(ingredient(1, "300"),)),),
            items=(
                recipe_item(item_id=1, day_offset=0, recipe_id=100, servings="1"),
                product_item(item_id=2, day_offset=0, amount="50", servings="1"),
            ),
        )
    )
    doubled = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            recipes=(recipe(recipe_id=100, base_servings=2, ingredients=(ingredient(1, "300"),)),),
            items=(
                recipe_item(item_id=1, day_offset=0, recipe_id=100, servings="2"),
                product_item(item_id=2, day_offset=0, amount="50", servings="2"),
            ),
        )
    )

    assert line_for(single, product_id=1).needed_amount == Decimal("200")
    assert line_for(doubled, product_id=1).needed_amount == Decimal("400")


def test_niepodzielny_mnoznik_nie_jest_kwantyzowany() -> None:
    """`servings/base_servings` = 1/3 nie jest zaokrąglane w kroku pośrednim (ADR-008).

    1/3 nie ma skończonego zapisu dziesiętnego, więc suma trzech takich porcji
    nie wróci DOKŁADNIE do 100 — ma jednak być dokładna do pełnej precyzji
    `Decimal` (28 cyfr znaczących), a nie zaokrąglona do gramów po drodze.
    Gdyby silnik kwantyzował kroki pośrednie, błąd byłby o rzędy wielkości
    większy i widoczny w liczbie opakowań.
    """
    result = generate_preview(
        engine_input(
            products=(product(product_id=1),),
            recipes=(recipe(recipe_id=100, base_servings=3, ingredients=(ingredient(1, "100"),)),),
            items=(
                recipe_item(item_id=1, day_offset=0, recipe_id=100, servings="1"),
                recipe_item(item_id=2, day_offset=1, recipe_id=100, servings="1"),
                recipe_item(item_id=3, day_offset=2, recipe_id=100, servings="1"),
            ),
        )
    )

    needed = line_for(result, product_id=1).needed_amount
    assert abs(needed - Decimal("100")) < Decimal("0.000000000000000000001")


def test_pozycja_w_jednostce_niezgodnej_z_produktem_to_bloker() -> None:
    """Zmiana `measure_kind` po zapisie pozycji (D15) daje bloker, nie 500 ani domysł."""
    result = generate_preview(
        engine_input(
            products=(product(product_id=1, name="Mleko", measure_kind=MeasureKind.VOLUME),),
            items=(product_item(item_id=7, day_offset=0, amount="200", unit=AmountUnit.GRAM),),
        )
    )

    assert [line.product_id for line in result.rounds[0].items] == []
    issue = result.issues[0]
    assert issue.kind is IssueKind.PLAN_ITEM_WITHOUT_AMOUNT
    assert issue.severity is IssueSeverity.BLOCKER
    assert issue.plan_item_id == 7
    assert "Mleko" in issue.message


def test_produkt_bez_kategorii_to_bloker_bez_pozycji() -> None:
    """Bez kategorii nie wiadomo, do której tury produkt trafia — zgłaszamy bloker."""
    result = generate_preview(
        engine_input(
            products=(
                product(
                    product_id=1,
                    name="Bez kategorii",
                    category_id=None,
                    category_name=None,
                    perishability=None,
                ),
            ),
            items=(product_item(item_id=1, day_offset=0, amount="100"),),
        )
    )

    assert result.rounds[0].items == ()
    assert result.issues[0].kind is IssueKind.PRODUCT_WITHOUT_CATEGORY
    assert result.issues[0].severity is IssueSeverity.BLOCKER
