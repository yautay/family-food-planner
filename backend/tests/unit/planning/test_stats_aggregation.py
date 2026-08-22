"""Składanie agregatów statystyk (karta B13 §Tests, 08_TESTING §2.1).

Testujemy czyste funkcje z `planning/stats_service.py` — bez bazy i bez planu
w niej. Cztery reguły, które muszą trzymać:

1. cel dnia to cel HISTORYCZNY (największy `valid_from <= dzień`),
2. statusy na progach 89,9/90/110/110,1% celu (oba progi to jeszcze „ok"),
3. dzień bez planu jest LUKĄ — dzielnikiem średniej jest liczba dni z planem,
4. zmiana celu w środku zakresu daje różne statusy dzienne w jednym zakresie.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.nutrition.models import UserNutritionGoal
from app.modules.nutrition.types import (
    DEFAULT_THRESHOLDS,
    GoalStatus,
    GoalThresholds,
    NutritionValues,
)
from app.modules.planning.stats_service import (
    average_targets,
    average_values,
    build_daily_stats,
    day_statuses,
    range_dates,
)

pytestmark = pytest.mark.unit


def values(kcal: str, *, protein: str = "0", fat: str = "0", carbs: str = "0") -> NutritionValues:
    """Wartości dnia — tylko pola, które biorą udział w asercjach."""
    return NutritionValues(
        kcal=Decimal(kcal),
        protein_g=Decimal(protein),
        fat_g=Decimal(fat),
        carbs_g=Decimal(carbs),
        fiber_g=Decimal("0"),
        sugars_g=Decimal("0"),
        glycemic_load=Decimal("0"),
        complete=True,
        missing=(),
    )


def goal(valid_from: date, kcal: str, *, protein: str | None = None) -> UserNutritionGoal:
    """Cel obowiązujący od daty — obiekt ORM budowany w pamięci, bez sesji."""
    return UserNutritionGoal(
        user_id=1,
        valid_from=valid_from,
        kcal=Decimal(kcal),
        protein_g=None if protein is None else Decimal(protein),
    )


# --- zakres dat ---------------------------------------------------------------------


def test_zakres_zawiera_wszystkie_daty_wlacznie() -> None:
    """Zakres jednodniowy to jeden dzień, tygodniowy — siedem (granice włącznie)."""
    assert range_dates(date(2026, 8, 10), date(2026, 8, 10)) == [date(2026, 8, 10)]
    assert len(range_dates(date(2026, 8, 10), date(2026, 8, 16))) == 7


# --- cel historyczny ----------------------------------------------------------------


def test_dzien_przed_pierwszym_celem_nie_ma_celu() -> None:
    """Zanim użytkownik ustawił pierwszy cel, statystyki nie zmyślają celu."""
    stats = build_daily_stats(
        dates=[date(2026, 7, 31)],
        nutrition_by_day={date(2026, 7, 31): values("1500")},
        goals=[goal(date(2026, 8, 1), "2000")],
        thresholds=DEFAULT_THRESHOLDS,
    )

    day = stats.days[0]
    assert day.goal is None
    assert day.status["kcal"] is None


def test_cel_dnia_to_ostatnia_zmiana_przed_ta_data() -> None:
    """Między zmianami obowiązuje cel starszy; od dnia zmiany — nowy."""
    goals = [goal(date(2026, 8, 1), "2000"), goal(date(2026, 8, 10), "2400")]
    stats = build_daily_stats(
        dates=range_dates(date(2026, 8, 8), date(2026, 8, 11)),
        nutrition_by_day={},
        goals=goals,
        thresholds=DEFAULT_THRESHOLDS,
    )

    targets = [None if day.goal is None else day.goal.kcal for day in stats.days]
    assert targets == [Decimal("2000"), Decimal("2000"), Decimal("2400"), Decimal("2400")]


def test_po_ostatniej_zmianie_obowiazuje_najnowszy_cel() -> None:
    """Cel nie „wygasa": po ostatnim `valid_from` obowiązuje bez końca."""
    stats = build_daily_stats(
        dates=[date(2030, 1, 1)],
        nutrition_by_day={},
        goals=[goal(date(2026, 8, 1), "2000"), goal(date(2026, 8, 10), "2400")],
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert stats.days[0].goal is not None
    assert stats.days[0].goal.kcal == Decimal("2400")


def test_zmiana_celu_w_srodku_zakresu_zmienia_statusy_dzienne() -> None:
    """Ta sama liczba kcal jest „prawidłowo" przy celu 2000 i „za mało" przy 2400."""
    day_a, day_b = date(2026, 8, 9), date(2026, 8, 10)
    stats = build_daily_stats(
        dates=[day_a, day_b],
        nutrition_by_day={day_a: values("2000"), day_b: values("2000")},
        goals=[goal(date(2026, 8, 1), "2000"), goal(day_b, "2400")],
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert stats.days[0].status["kcal"] is GoalStatus.OK
    assert stats.days[1].status["kcal"] is GoalStatus.BELOW


# --- statusy na progach -------------------------------------------------------------


@pytest.mark.parametrize(
    ("kcal", "expected"),
    [
        ("1798", GoalStatus.BELOW),  # 89,9% celu
        ("1800", GoalStatus.OK),  # dokładnie 90% — jeszcze „prawidłowo" (D9)
        ("2200", GoalStatus.OK),  # dokładnie 110% — wciąż „prawidłowo"
        ("2202", GoalStatus.ABOVE),  # 110,1% celu
    ],
)
def test_statusy_dnia_na_progach(kcal: str, expected: GoalStatus) -> None:
    """Progi 90/110% należą do przedziału „prawidłowo"; poza nimi status się zmienia."""
    statuses = day_statuses(values(kcal), goal(date(2026, 8, 1), "2000"), DEFAULT_THRESHOLDS)

    assert statuses["kcal"] is expected


def test_progi_z_ustawien_uzytkownika_przesuwaja_granice() -> None:
    """Progi 95/105 zmieniają status tej samej wartości (D9 — konfigurowalne)."""
    strict = GoalThresholds(low=Decimal("95"), high=Decimal("105"))

    assert (
        day_statuses(values("1850"), goal(date(2026, 8, 1), "2000"), strict)["kcal"]
        is GoalStatus.BELOW
    )


def test_dzien_bez_planu_nie_ma_statusu_mimo_ustawionego_celu() -> None:
    """Luka nie jest „za mało": brak danych i zero to dwie różne informacje."""
    statuses = day_statuses(None, goal(date(2026, 8, 1), "2000"), DEFAULT_THRESHOLDS)

    assert set(statuses.values()) == {None}


def test_pole_bez_celu_nie_ma_statusu() -> None:
    """Cel makra jest opcjonalny — bez niego status białka to `null`, nie `below`."""
    statuses = day_statuses(
        values("2000", protein="50"), goal(date(2026, 8, 1), "2000"), DEFAULT_THRESHOLDS
    )

    assert statuses["kcal"] is GoalStatus.OK
    assert statuses["protein_g"] is None


# --- średnie z lukami ---------------------------------------------------------------


def test_srednia_dzieli_przez_dni_z_planem_a_nie_przez_zakres() -> None:
    """3 dni planu w zakresie 7 dni ⇒ dzielnik 3 (karta B13, Acceptance Criteria 4)."""
    dates = range_dates(date(2026, 8, 10), date(2026, 8, 16))
    planned = {
        date(2026, 8, 10): values("1800"),
        date(2026, 8, 12): values("2100"),
        date(2026, 8, 14): values("2400"),
    }

    stats = build_daily_stats(
        dates=dates,
        nutrition_by_day=planned,
        goals=[goal(date(2026, 8, 1), "2100")],
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert stats.summary.days_in_range == 7
    assert stats.summary.days_with_plan == 3
    assert stats.summary.avg is not None
    # (1800 + 2100 + 2400) / 3 = 2100; przy dzielniku 7 wyszłoby 900 i status „za mało".
    assert stats.summary.avg.kcal == Decimal("2100")
    assert stats.summary.progress["kcal"].status is GoalStatus.OK


def test_dni_bez_planu_sa_lukami_a_nie_zerami() -> None:
    """Dzień bez planu ma `has_plan=False` i `nutrition=None` — nie zerowe wartości."""
    dates = range_dates(date(2026, 8, 10), date(2026, 8, 11))
    stats = build_daily_stats(
        dates=dates,
        nutrition_by_day={date(2026, 8, 10): values("2000")},
        goals=[],
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert [day.has_plan for day in stats.days] == [True, False]
    assert stats.days[1].nutrition is None


def test_zakres_bez_ani_jednego_dnia_z_planem_nie_ma_sredniej() -> None:
    """Pusty zakres nie dostaje statusu — nie ma czego oceniać (06_UIUX §3.2)."""
    stats = build_daily_stats(
        dates=range_dates(date(2026, 8, 10), date(2026, 8, 16)),
        nutrition_by_day={},
        goals=[goal(date(2026, 8, 1), "2000")],
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert stats.summary.days_with_plan == 0
    assert stats.summary.avg is None
    assert stats.summary.progress["kcal"].status is None


def test_srednia_bez_dni_nie_istnieje() -> None:
    """`average_values([])` to `None`, nie zerowy wynik."""
    assert average_values([]) is None


def test_srednia_zaokragla_sie_na_wyjsciu() -> None:
    """kcal do 1, makra do 0,1 (02_DOMAIN §6) — dzielenie nie zostawia ogona."""
    avg = average_values([values("2000", protein="100"), values("2001", protein="101")])

    assert avg is not None
    assert avg.kcal == Decimal("2001")  # 2000,5 → ROUND_HALF_UP
    assert avg.protein_g == Decimal("100.5")


def test_srednia_niesie_flage_niepelnych_danych() -> None:
    """Niekompletny dzień zakresu widać też w podsumowaniu (plakietka „niepełne dane")."""
    incomplete = NutritionValues(
        **{
            **{field: Decimal("0") for field in ("fat_g", "carbs_g", "fiber_g", "sugars_g")},
            "kcal": Decimal("1000"),
            "protein_g": Decimal("0"),
            "glycemic_load": Decimal("0"),
        },
        complete=False,
        missing=("Cebula: brak IG",),
    )

    avg = average_values([values("2000"), incomplete])

    assert avg is not None
    assert avg.complete is False
    assert avg.missing == ("Cebula: brak IG",)


# --- średnia celów ------------------------------------------------------------------


def test_srednia_celow_liczy_sie_ze_zmiany_w_srodku_zakresu() -> None:
    """Cel zmieniony w środku zakresu daje średnią celów, nie „ostatni cel"."""
    targets = average_targets(
        [
            goal(date(2026, 8, 1), "2000"),
            goal(date(2026, 8, 1), "2000"),
            goal(date(2026, 8, 10), "2600"),
        ]
    )

    assert targets["kcal"] == Decimal("2200")


def test_srednia_celu_makra_liczy_sie_tylko_z_dni_ktore_ten_cel_mialy() -> None:
    """Brak celu białka nie wchodzi do średniej jako zero (zaniżyłby cel)."""
    targets = average_targets(
        [goal(date(2026, 8, 1), "2000"), goal(date(2026, 8, 5), "2000", protein="120")]
    )

    assert targets["protein_g"] == Decimal("120")
    assert targets["fat_g"] is None


def test_dni_bez_celu_nie_daja_sredniej_celu() -> None:
    """Bez ani jednego celu w zakresie kafelek nie ma celu ani delty."""
    stats = build_daily_stats(
        dates=[date(2026, 8, 10)],
        nutrition_by_day={date(2026, 8, 10): values("2000")},
        goals=[],
        thresholds=DEFAULT_THRESHOLDS,
    )

    metric = stats.summary.progress["kcal"]
    assert metric.target is None
    assert metric.delta is None
    assert metric.status is None


def test_delta_podsumowania_to_srednia_minus_srednia_celu() -> None:
    """Kafelek zakresu ma to samo trio, co kafelek planu dnia (06_UIUX §3.5)."""
    stats = build_daily_stats(
        dates=[date(2026, 8, 10), date(2026, 8, 11)],
        nutrition_by_day={date(2026, 8, 10): values("1800"), date(2026, 8, 11): values("2000")},
        goals=[goal(date(2026, 8, 1), "2000")],
        thresholds=DEFAULT_THRESHOLDS,
    )

    metric = stats.summary.progress["kcal"]
    assert metric.value == Decimal("1900")
    assert metric.target == Decimal("2000")
    assert metric.delta == Decimal("-100")
    assert metric.status is GoalStatus.OK
