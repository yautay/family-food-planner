"""Czysta arytmetyka planowania: rotacja cyklu i sekwencja „powiel blok".

Scenariusze z karty B07 §Tests (unit). Te reguły najłatwiej pomylić i najdrożej
debugować przez API, więc mieszkają w funkcjach bez I/O (ADR-008) i są sprawdzane
na gołych datach.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.planning.sequences import (
    block_copy_sequence,
    cycle_rotation_index,
    cycle_week_plan,
    is_week_start,
    week_start_of,
)

pytestmark = pytest.mark.unit

#: 2026-08-17 to poniedziałek — punkt odniesienia wszystkich scenariuszy.
MONDAY = date(2026, 8, 17)
NEXT_MONDAY = date(2026, 8, 24)


def _days(count: int) -> timedelta:
    """Skrót na przesunięcie daty — czyta się lepiej niż `timedelta` w asercji."""
    return timedelta(days=count)


# --- tydzień poniedziałkowy ----------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 8, 17), date(2026, 8, 17)),  # poniedziałek → sam siebie
        (date(2026, 8, 19), date(2026, 8, 17)),  # środa
        (date(2026, 8, 23), date(2026, 8, 17)),  # NIEDZIELA należy do tego tygodnia
        (date(2026, 8, 24), date(2026, 8, 24)),  # kolejny poniedziałek
    ],
)
def test_week_start_of_liczy_tydzien_poniedzialkowy(day: date, expected: date) -> None:
    """Tydzień PL biegnie pon-nd, więc niedziela NIE zaczyna nowego tygodnia."""
    assert week_start_of(day) == expected


def test_is_week_start_rozpoznaje_tylko_poniedzialek() -> None:
    """Warunek wejścia instancjacji tygodnia i apply cyklu."""
    assert is_week_start(MONDAY) is True
    assert is_week_start(date(2026, 8, 18)) is False
    assert is_week_start(date(2026, 8, 23)) is False


# --- rotacja cyklu -------------------------------------------------------------------


def test_rotacja_trzech_szablonow_na_piec_tygodni_daje_abcab() -> None:
    """Scenariusz z karty: 3 szablony na 5 tygodni ⇒ A,B,C,A,B."""
    plan = cycle_week_plan([10, 20, 30], MONDAY, MONDAY, MONDAY + _days(4 * 7 + 6))

    assert [template_id for _week, template_id in plan] == [10, 20, 30, 10, 20]
    assert [week for week, _template_id in plan] == [
        MONDAY,
        MONDAY + _days(7),
        MONDAY + _days(14),
        MONDAY + _days(21),
        MONDAY + _days(28),
    ]


def test_rotacja_startuje_od_szablonu_wskazanego_data_startu() -> None:
    """Scenariusz z karty: „start od B" — `start_date` o tydzień wcześniej niż zakres."""
    plan = cycle_week_plan([10, 20, 30], MONDAY, NEXT_MONDAY, NEXT_MONDAY + _days(13))

    assert [template_id for _week, template_id in plan] == [20, 30]


def test_brak_daty_startu_zaczyna_rotacje_od_poczatku_zakresu() -> None:
    """`start_date=None` ⇒ pierwszy tydzień ZAKRESU dostaje pierwszy szablon.

    Regresja z implementacji: „NULL ⇒ od pierwszego" dało się przeczytać jako
    „zawsze pierwszy", co znieruchomiłoby rotację i każdy tydzień dostałby
    szablon A. Cykl bez daty startu musi rotować tak samo jak z datą.
    """
    plan = cycle_week_plan([10, 20], None, NEXT_MONDAY, NEXT_MONDAY + _days(20))

    assert [template_id for _week, template_id in plan] == [10, 20, 10]


def test_rotacja_jest_cykliczna_takze_przed_data_startu() -> None:
    """Tydzień PRZED startem trafia na ostatni szablon — rotacja nie ma dziury.

    Bez tego „zastosuj cykl na poprzedni tydzień" musiałoby być błędem albo
    po cichu dawało pierwszy szablon, czyli dwa tygodnie A pod rząd.
    """
    assert cycle_rotation_index(3, NEXT_MONDAY, MONDAY) == 2
    assert cycle_rotation_index(3, NEXT_MONDAY, MONDAY - _days(7)) == 1


def test_niepelny_tydzien_na_koncu_zakresu_nadal_wchodzi_do_planu() -> None:
    """Zakres kończący się w środę obejmuje tydzień, w którym ta środa leży."""
    plan = cycle_week_plan([10, 20], MONDAY, MONDAY, MONDAY + _days(9))

    assert [week for week, _template_id in plan] == [MONDAY, NEXT_MONDAY]


def test_zakres_krotszy_niz_tydzien_daje_jeden_tydzien() -> None:
    plan = cycle_week_plan([10], MONDAY, MONDAY, MONDAY + _days(2))

    assert plan == [(MONDAY, 10)]


def test_zakres_od_nie_poniedzialku_jest_bledem_kontraktu() -> None:
    """Serwis odrzuca to 422; funkcja czysta pilnuje własnego kontraktu asercją."""
    with pytest.raises(ValueError, match="poniedziałek"):
        cycle_week_plan([10], None, date(2026, 8, 18), date(2026, 8, 25))


def test_cykl_bez_szablonow_nie_ma_rotacji() -> None:
    with pytest.raises(ValueError, match="bez szablonów"):
        cycle_rotation_index(0, MONDAY, MONDAY)


# --- sekwencja „powiel blok" ---------------------------------------------------------


def test_blok_trzy_dni_razy_dwa_daje_szesc_dat_parami() -> None:
    """Model 2+2+2 z 01_PDF_AUDIT §6: kolejność d1,d1,d2,d2,d3,d3.

    To jest sedno całej funkcji: dni tej samej diety MUSZĄ sąsiadować. Przeplot
    (d1,d2,d3,d1,d2,d3) dawałby te same 6 dat i te same posiłki, ale niweczyłby
    powód istnienia bloku — wspólne zakupy i gotowanie podwójnej porcji.
    """
    target = date(2026, 9, 1)
    sequence = block_copy_sequence(MONDAY, 3, 2, target)

    assert sequence == [
        (MONDAY, target),
        (MONDAY, target + _days(1)),
        (MONDAY + _days(1), target + _days(2)),
        (MONDAY + _days(1), target + _days(3)),
        (MONDAY + _days(2), target + _days(4)),
        (MONDAY + _days(2), target + _days(5)),
    ]


def test_blok_bez_powtorzen_jest_zwyklym_kopiowaniem_dzien_po_dniu() -> None:
    """`repeat_each=1` ⇒ przesunięcie bloku bez multiplikacji."""
    target = date(2026, 9, 1)
    sequence = block_copy_sequence(MONDAY, 3, 1, target)

    assert sequence == [
        (MONDAY, target),
        (MONDAY + _days(1), target + _days(1)),
        (MONDAY + _days(2), target + _days(2)),
    ]


def test_blok_jednego_dnia_powtarza_ten_sam_dzien() -> None:
    target = date(2026, 9, 1)
    sequence = block_copy_sequence(MONDAY, 1, 3, target)

    assert sequence == [(MONDAY, target + _days(offset)) for offset in range(3)]


def test_daty_docelowe_bloku_sa_kolejne_i_bez_powtorzen() -> None:
    """Blok nigdy nie celuje dwa razy w tę samą datę — inaczej dublowałby posiłki."""
    sequence = block_copy_sequence(MONDAY, 4, 3, date(2026, 9, 1))
    targets = [target for _source, target in sequence]

    assert len(targets) == len(set(targets)) == 12
    assert targets == sorted(targets)


@pytest.mark.parametrize(("days", "repeat"), [(0, 2), (3, 0), (-1, 1)])
def test_blok_wymaga_dodatnich_parametrow(days: int, repeat: int) -> None:
    with pytest.raises(ValueError, match="co najmniej"):
        block_copy_sequence(MONDAY, days, repeat, date(2026, 9, 1))
