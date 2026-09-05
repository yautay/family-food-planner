"""Agregaty dzienne widoku Statystyki (karta B13, 06_UIUX §4.7).

Serwis NIE liczy niczego sam i NIE zapisuje niczego: dane bierze z
`PlanningService.list_days` (wartości policzone silnikiem nutrition) oraz
z `GoalsService` (historia celów), a składanie odpowiedzi robią czyste funkcje
z tego pliku. Cache agregatów w bazie jest ZAKAZANY (niezmiennik 02_DOMAIN
§13.2) — statystyki są zawsze pochodną planu i celów.

Trzy reguły wiążące (karta B13 §Backend):

1. **Dzień bez planu to LUKA, nie zero.** Element odpowiedzi istnieje
   (`has_plan: false`, `nutrition: null`), ale nie wchodzi do średnich:
   dzielnikiem jest `days_with_plan`, nie długość zakresu. Zero kcal
   zaniżyłoby średnią i zmieniło status na „za mało" bez powodu.
2. **Cel jest HISTORYCZNY.** Cel dnia to wiersz z największym
   `valid_from <= day` (`goal_for_day` z modułu nutrition) — zmiana celu
   w środku zakresu daje różne cele dla różnych dni tego samego zakresu.
   Nie interpolujemy: linia celu jest funkcją schodkową.
3. **Status liczy silnik.** `goal_status` z progami użytkownika
   (`users.ui_settings`, D9) — statystyki nie mają własnych progów.

Podsumowanie zakresu porównuje średnią wartość ze średnią CELÓW dni z planem:
cel mógł się zmienić w środku zakresu, więc jeden „cel zakresu" nie istnieje.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import User
from app.modules.nutrition.engine import (
    aggregate,
    goal_status,
    portion_nutrition,
    round_field_for_output,
    round_for_output,
)
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.nutrition.service import GoalsService, goal_for_day
from app.modules.nutrition.types import (
    GOAL_NUMERIC_FIELDS,
    GoalStatus,
    GoalThresholds,
    NutritionValues,
    thresholds_from_ui_settings,
)
from app.modules.planning.service import (
    RANGE_REVERSED,
    GoalMetric,
    PlanningService,
    PlanValidationError,
)

__all__ = [
    "MAX_STATS_RANGE_DAYS",
    "STATS_RANGE_TOO_LONG",
    "DailyStats",
    "DayStat",
    "StatsService",
    "StatsSummary",
    "average_targets",
    "average_values",
    "build_daily_stats",
    "day_statuses",
    "range_dates",
    "summarize",
]

#: Sufit zakresu statystyk: kwartał dziennych słupków to granica czytelności
#: wykresu i zarazem tanie zapytanie (karta B13 §Backend).
MAX_STATS_RANGE_DAYS = 92
STATS_RANGE_TOO_LONG = (
    f"Zakres statystyk może obejmować maksymalnie {MAX_STATS_RANGE_DAYS} dni. "
    "Zawęź daty i spróbuj ponownie."
)


# --- wyniki (dane zmaterializowane dla warstwy HTTP) --------------------------------


@dataclass(frozen=True)
class DayStat:
    """Jeden dzień zakresu. `nutrition=None` znaczy „brak planu", nie „zero"."""

    day: date
    has_plan: bool
    nutrition: NutritionValues | None
    #: Cel obowiązujący W TYM dniu (`valid_from` jedzie do UI dla linii schodkowej).
    goal: UserNutritionGoal | None
    #: Status per pole celu; `None` dla pola bez celu i dla dnia bez planu.
    status: dict[str, GoalStatus | None]


@dataclass(frozen=True)
class StatsSummary:
    """Podsumowanie zakresu: średnie dzienne i trio wartość/cel/delta/status."""

    days_in_range: int
    days_with_plan: int
    #: Średnia dzienna z dni Z PLANEM; `None`, gdy takich dni nie ma.
    avg: NutritionValues | None
    #: Kafelki kcal/białko/tłuszcz/węglowodany — ten sam kształt co w planie dnia.
    progress: dict[str, GoalMetric]


@dataclass(frozen=True)
class DailyStats:
    """Odpowiedź `GET /stats/daily`: dni zakresu + podsumowanie."""

    days: list[DayStat]
    summary: StatsSummary


# --- czyste funkcje składania odpowiedzi -------------------------------------------


def range_dates(date_from: date, date_to: date) -> list[date]:
    """Wszystkie daty zakresu włącznie — także te bez planu (to one są lukami)."""
    span = (date_to - date_from).days
    return [date_from + timedelta(days=offset) for offset in range(span + 1)]


def day_statuses(
    values: NutritionValues | None,
    goal: UserNutritionGoal | None,
    thresholds: GoalThresholds,
) -> dict[str, GoalStatus | None]:
    """Statusy dnia per pole celu — bez planu albo bez celu status nie istnieje.

    „Nie wiem" i „za mało" to dwie różne informacje (06_UIUX §3.5), więc dzień
    bez planu nie dostaje `below` tylko dlatego, że nie ma wartości.
    """
    if values is None or goal is None:
        return dict.fromkeys(GOAL_NUMERIC_FIELDS)
    return {
        field: goal_status(getattr(values, field), getattr(goal, field), thresholds)
        for field in GOAL_NUMERIC_FIELDS
    }


def average_values(values: Sequence[NutritionValues]) -> NutritionValues | None:
    """Średnia dzienna z dni Z PLANEM (dzielnik = liczba tych dni, nie zakresu).

    Dzielenie sumy przez liczbę dni to dokładnie ta sama operacja, co „porcja
    z całości", więc reużywamy `portion_nutrition` zamiast pisać drugie
    dzielenie (ADR-008: jedno miejsce na regułę). Flagi `complete`/`missing`
    przechodzą przez `aggregate`, więc niekompletny dzień zakresu jest widoczny
    także w podsumowaniu.
    """
    if not values:
        return None
    return round_for_output(portion_nutrition(aggregate(values), len(values)))


def average_targets(goals: Sequence[UserNutritionGoal | None]) -> dict[str, Decimal | None]:
    """Średnia celów per pole — liczona z dni, które CEL DLA TEGO POLA miały.

    Makra są opcjonalne (02_DOMAIN §6), więc dzielnik jest per pole: cel białka
    ustawiony w połowie zakresu nie może udawać, że obowiązywał od początku,
    a wliczenie go jako zera zaniżyłoby cel i przekłamało status.
    """
    averages: dict[str, Decimal | None] = {}
    for field in GOAL_NUMERIC_FIELDS:
        targets = [
            getattr(goal, field)
            for goal in goals
            if goal is not None and getattr(goal, field) is not None
        ]
        averages[field] = sum(targets, Decimal("0")) / len(targets) if targets else None
    return averages


def summarize(days: Sequence[DayStat], thresholds: GoalThresholds) -> StatsSummary:
    """Podsumowanie zakresu: średnie dzienne vs średnia celów dni z planem."""
    planned = [day for day in days if day.nutrition is not None]
    avg = average_values([day.nutrition for day in planned if day.nutrition is not None])
    targets = average_targets([day.goal for day in planned])

    progress: dict[str, GoalMetric] = {}
    for field in GOAL_NUMERIC_FIELDS:
        value = Decimal("0") if avg is None else getattr(avg, field)
        # `avg` przeszło już przez `round_for_output`, ale ŚREDNIA CELÓW nie —
        # a siedem dni w mianowniku daje `2085.714285714285714285714286`, które
        # frontend pokazuje w całości (obcina tylko końcowe zera). Zaokrąglamy
        # tą samą regułą, co resztę wyjścia (02_DOMAIN §6, ustalenie REVIEW R4).
        target = round_field_for_output(field, targets[field])
        progress[field] = GoalMetric(
            value=value,
            target=target,
            delta=None if target is None else round_field_for_output(field, value - target),
            # Bez ani jednego dnia z planem nie ma czego oceniać: status „za mało"
            # przy pustym zakresie byłby zarzutem wobec użytkownika, nie informacją.
            status=None if avg is None else goal_status(value, target, thresholds),
        )

    return StatsSummary(
        days_in_range=len(days),
        days_with_plan=len(planned),
        avg=avg,
        progress=progress,
    )


def build_daily_stats(
    *,
    dates: Sequence[date],
    nutrition_by_day: Mapping[date, NutritionValues],
    goals: Sequence[UserNutritionGoal],
    thresholds: GoalThresholds,
) -> DailyStats:
    """Złożenie odpowiedzi z gotowych składników — czysta funkcja, zero I/O.

    Wejście jest celowo „głupie" (daty, wartości per dzień, historia celów,
    progi): dzięki temu reguła luk, celów historycznych i statusów da się
    sprawdzić testem jednostkowym bez bazy i bez planu w niej.
    """
    day_stats: list[DayStat] = []
    for day in dates:
        values = nutrition_by_day.get(day)
        goal = goal_for_day(goals, day)
        day_stats.append(
            DayStat(
                day=day,
                has_plan=values is not None,
                nutrition=values,
                goal=goal,
                status=day_statuses(values, goal, thresholds),
            )
        )
    return DailyStats(days=day_stats, summary=summarize(day_stats, thresholds))


# --- serwis ------------------------------------------------------------------------


class StatsService:
    """Agregaty dzienne dla bieżącego użytkownika. Wyłącznie odczyt."""

    def __init__(self, session: AsyncSession) -> None:
        # Moduł→moduł wyłącznie przez serwis (CLAUDE.md §4): dni bierzemy
        # z `PlanningService` (ten sam filtr scope i ta sama reguła
        # rozstrzygania dnia, co widok planu), cele z serwisu nutrition.
        self._planning = PlanningService(session)
        self._goals = GoalsService(session)

    async def daily(self, user: User, *, date_from: date, date_to: date) -> DailyStats:
        """Dni zakresu z wartościami, celem z dnia i statusami + podsumowanie.

        Widoczność egzekwuje `PlanningService.list_days` (`ScopedQuery`), więc
        cudzy dzień prywatny nie wchodzi do agregatów — statystyki nie mają
        własnego filtra, który mógłby się z tym rozjechać (04_API §3).

        Dzień, który ISTNIEJE, ale nie ma ani jednego posiłku (po ustaleniu R3
        zostaje w bazie tylko taki z tytułem), jest traktowany jak brak planu:
        nie ma z czego liczyć wartości, a zero kcal zaniżyłoby średnią zakresu.
        """
        if date_from > date_to:
            raise PlanValidationError(RANGE_REVERSED)
        if (date_to - date_from).days + 1 > MAX_STATS_RANGE_DAYS:
            raise PlanValidationError(STATS_RANGE_TOO_LONG)

        views = await self._planning.list_days(user, date_from=date_from, date_to=date_to)
        return build_daily_stats(
            dates=range_dates(date_from, date_to),
            nutrition_by_day={view.day: view.nutrition for view in views if view.meals},
            goals=await self._goals.goals_of(user.id),
            thresholds=thresholds_from_ui_settings(user.ui_settings),
        )
