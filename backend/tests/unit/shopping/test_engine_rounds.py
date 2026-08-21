"""Silnik zakupowy — podział na tury (08_TESTING §2.7).

Preset z 02_DOMAIN §9.2: „Niedziela" bierze trwałe na cały tydzień i świeże na
pierwsze 4 dni, „Środa" domyka świeże na resztę. Okna liczą się kursorami po
zakresie dat, a ostatnie okno każdego rodzaju sięga do `date_to` — żadne
zapotrzebowanie nie ginie.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.shopping.engine import RoundInput, RoundMode, generate_preview
from tests.unit.shopping.helpers import (
    WEEK_END,
    WEEK_START,
    all_lines,
    day,
    engine_input,
    fresh_product,
    line_for,
    preset_rounds,
    product,
    product_item,
)

pytestmark = pytest.mark.unit


def _week_of_items() -> tuple[object, ...]:
    """Tydzień planu: co dnia 100 g produktu trwałego i 100 g świeżego."""
    items: list[object] = []
    for offset in range(7):
        items.append(
            product_item(item_id=offset + 1, day_offset=offset, product_id=1, amount="100")
        )
        items.append(
            product_item(item_id=offset + 11, day_offset=offset, product_id=2, amount="100")
        )
    return tuple(items)


def test_preset_sunday_wednesday_split() -> None:
    """Trwałe całe w niedzielę; świeże 4 dni w niedzielę, 3 dni w środę."""
    result = generate_preview(
        engine_input(
            rounds=preset_rounds(),
            products=(product(product_id=1), fresh_product(product_id=2)),
            items=_week_of_items(),  # type: ignore[arg-type]
        )
    )

    assert [round_view.name for round_view in result.rounds] == ["Niedziela", "Środa"]
    assert line_for(result, product_id=1, round_key="cfg-1").needed_amount == Decimal("700")
    assert line_for(result, product_id=2, round_key="cfg-1").needed_amount == Decimal("400")
    assert line_for(result, product_id=2, round_key="cfg-2").needed_amount == Decimal("300")
    # Produkt trwały pojawia się TYLKO w turze, która trwałe kupuje.
    assert [line.product_id for line in result.rounds[1].items] == [2]


def test_fresh_vs_durable_assignment() -> None:
    """Tura `fresh_only` NIGDY nie dostaje produktu trwałego, choćby jej okno sięgało dalej.

    Konfiguracja: tura 1 kupuje trwałe (okno domknięte do końca zakresu) i świeże
    na 1 dzień, tura 2 tylko świeże na resztę. Produkt trwały ma zapotrzebowanie
    także w dniach należących do okna świeżych tury 2 — i mimo to zostaje w turze 1.
    """
    result = generate_preview(
        engine_input(
            rounds=(
                RoundInput(
                    key="cfg-1",
                    name="Duże zakupy",
                    mode=RoundMode.DURABLE_PLUS_FRESH_WINDOW,
                    covers_days=3,
                    fresh_days=1,
                ),
                RoundInput(key="cfg-2", name="Świeże", mode=RoundMode.FRESH_ONLY, covers_days=6),
            ),
            products=(product(product_id=1), fresh_product(product_id=2)),
            items=_week_of_items(),  # type: ignore[arg-type]
        )
    )

    assert [line.product_id for line in result.rounds[0].items] == [2, 1]
    assert [line.product_id for line in result.rounds[1].items] == [2]
    assert line_for(result, product_id=1, round_key="cfg-1").needed_amount == Decimal("700")
    assert line_for(result, product_id=2, round_key="cfg-1").needed_amount == Decimal("100")
    assert line_for(result, product_id=2, round_key="cfg-2").needed_amount == Decimal("600")


def test_tura_bez_wlasnego_okna_jest_pusta_ale_widoczna() -> None:
    """Gdy poprzednia tura zjadła cały zakres, kolejna zostaje w preview jako pusta.

    Pusta sekcja jest informacją („w środę nie ma po co jechać"), a nie błędem —
    dlatego tury nie ukrywamy (plan krótszy niż okno, 08_TESTING §2.7).
    """
    result = generate_preview(
        engine_input(
            rounds=(
                RoundInput(key="cfg-1", name="Wszystko", mode=RoundMode.ALL, covers_days=7),
                RoundInput(key="cfg-2", name="Świeże", mode=RoundMode.FRESH_ONLY, covers_days=7),
            ),
            products=(product(product_id=1), fresh_product(product_id=2)),
            items=_week_of_items(),  # type: ignore[arg-type]
        )
    )

    assert [line.product_id for line in result.rounds[0].items] == [2, 1]
    assert result.rounds[1].items == ()
    assert result.rounds[1].date_from is None


def test_round_day_windows() -> None:
    """Okna dat tur wynikają z `covers_days`/`fresh_days`, nie z dnia tygodnia."""
    result = generate_preview(
        engine_input(
            rounds=preset_rounds(),
            products=(product(product_id=1), fresh_product(product_id=2)),
            items=_week_of_items(),  # type: ignore[arg-type]
        )
    )

    sunday, wednesday = result.rounds
    assert (sunday.date_from, sunday.date_to) == (WEEK_START, WEEK_END)
    assert (wednesday.date_from, wednesday.date_to) == (day(4), WEEK_END)
    # Dzień zakupów cofa się do wskazanego dnia tygodnia (nigdy w przód):
    # niedziela PRZED tygodniem planu i środa przed weekendem.
    assert sunday.shopping_date == date(2030, 1, 6)
    assert wednesday.shopping_date == date(2030, 1, 9)
    # Dni pozycji zgadzają się z oknem tury.
    assert line_for(result, product_id=2, round_key="cfg-1").days == tuple(
        day(offset) for offset in range(4)
    )
    assert line_for(result, product_id=2, round_key="cfg-2").days == tuple(
        day(offset) for offset in range(4, 7)
    )


def test_plan_shorter_than_round_window() -> None:
    """Plan krótszy niż okno tury: druga tura jest pusta, nic nie wypada z zakupów."""
    result = generate_preview(
        engine_input(
            date_from=WEEK_START,
            date_to=day(2),
            rounds=preset_rounds(),
            products=(product(product_id=1), fresh_product(product_id=2)),
            items=(
                product_item(item_id=1, day_offset=0, product_id=1, amount="100"),
                product_item(item_id=2, day_offset=2, product_id=2, amount="150"),
            ),
        )
    )

    assert line_for(result, product_id=1, round_key="cfg-1").needed_amount == Decimal("100")
    assert line_for(result, product_id=2, round_key="cfg-1").needed_amount == Decimal("150")
    assert result.rounds[1].items == ()
    assert sum(line.needed_amount for line in all_lines(result)) == Decimal("250")


def test_plan_dluzszy_niz_okna_tur_nie_gubi_dni() -> None:
    """Zakres szerszy niż suma okien: ostatnia tura każdego rodzaju domyka resztę."""
    result = generate_preview(
        engine_input(
            date_from=WEEK_START,
            date_to=day(9),
            rounds=preset_rounds(),
            products=(product(product_id=1), fresh_product(product_id=2)),
            items=tuple(
                product_item(item_id=offset + 1, day_offset=offset, product_id=1, amount="100")
                for offset in range(10)
            )
            + tuple(
                product_item(item_id=offset + 21, day_offset=offset, product_id=2, amount="10")
                for offset in range(10)
            ),
        )
    )

    assert sum(line.needed_amount for line in all_lines(result)) == Decimal("1100")
    assert line_for(result, product_id=1, round_key="cfg-1").needed_amount == Decimal("1000")
    assert line_for(result, product_id=2, round_key="cfg-2").needed_amount == Decimal("60")


def test_konfiguracja_bez_tury_trwalej_oddaje_trwale_pierwszej_turze() -> None:
    """Same tury `fresh_only`: produkty trwałe trafiają do pierwszej z nich."""
    result = generate_preview(
        engine_input(
            rounds=(
                RoundInput(
                    key="cfg-1", name="Poniedziałek", mode=RoundMode.FRESH_ONLY, covers_days=4
                ),
                RoundInput(key="cfg-2", name="Piątek", mode=RoundMode.FRESH_ONLY, covers_days=3),
            ),
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=5, product_id=1, amount="100"),),
        )
    )

    assert line_for(result, product_id=1, round_key="cfg-1").needed_amount == Decimal("100")


def test_brak_tur_w_konfiguracji_nie_wysadza_silnika() -> None:
    """Wejście bez tur daje puste preview, a nie wyjątek (serwis dokłada turę zastępczą)."""
    result = generate_preview(
        engine_input(
            rounds=(),
            products=(product(product_id=1),),
            items=(product_item(item_id=1, day_offset=0, amount="100"),),
        )
    )

    assert result.rounds == ()
    assert all_lines(result) == []
