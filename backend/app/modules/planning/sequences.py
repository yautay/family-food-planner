"""Czysta arytmetyka planowania: tygodnie, rotacja cyklu, sekwencja bloku.

Ten plik nie ma ANI JEDNEGO wywołania I/O (ADR-008) — wyłącznie funkcje na datach
i listach identyfikatorów. Dzięki temu reguły, które najłatwiej pomylić („który
szablon wypada w trzecim tygodniu?", „ile dat docelowych daje 3 dni x 2?"), są
testowalne bez bazy i bez aplikacji.

Tydzień jest zawsze poniedziałkowy (PL) — jedna funkcja normalizująca dla całego
backendu, bliźniaczo do `frontend/src/lib/dates.ts::startOfWeek`.
"""

from __future__ import annotations

from datetime import date, timedelta

__all__ = [
    "DAYS_PER_WEEK",
    "block_copy_sequence",
    "cycle_rotation_index",
    "cycle_week_plan",
    "is_week_start",
    "week_start_of",
]

DAYS_PER_WEEK = 7


def week_start_of(day: date) -> date:
    """Poniedziałek tygodnia, do którego należy data (`isoweekday()` 1 = poniedziałek)."""
    return day - timedelta(days=day.isoweekday() - 1)


def is_week_start(day: date) -> bool:
    """Czy data jest poniedziałkiem — warunek wejścia instancjacji tygodnia i apply cyklu."""
    return day.isoweekday() == 1


def cycle_rotation_index(template_count: int, anchor_week: date, week_start: date) -> int:
    """Który szablon cyklu wypada w tygodniu `week_start` (rotacja A→B→C→A…).

    `anchor_week` to poniedziałek tygodnia, w którym rotacja stoi na PIERWSZYM
    szablonie. Wyznacza go `cycle_week_plan` — z `start_date` cyklu, a gdy go nie
    ma, z początku zakresu (patrz tam).

    Tygodnie PRZED anchorem też dostają poprawny indeks: dzielenie całkowite
    w Pythonie zaokrągla w dół, a `%` zwraca wartość nieujemną, więc tydzień
    wcześniejszy o jeden trafia na OSTATNI szablon listy — rotacja jest cykliczna
    w obie strony i nie ma „dziury" przed datą startu.
    """
    if template_count <= 0:
        raise ValueError("Cykl bez szablonów nie ma rotacji.")
    weeks_elapsed = (week_start - anchor_week).days // DAYS_PER_WEEK
    return weeks_elapsed % template_count


def cycle_week_plan(
    template_ids: list[int],
    start_date: date | None,
    date_from: date,
    date_to: date,
) -> list[tuple[date, int]]:
    """Pary (poniedziałek tygodnia, id szablonu) dla zakresu dat.

    `date_from` MUSI być poniedziałkiem — walidację robi serwis (422), tutaj jest
    tylko asercja kontraktu. Ostatni tydzień zakresu może być niepełny: zwracamy
    go normalnie, a odsiewanie dni wychodzących za `date_to` należy do serwisu,
    bo tylko on wie, które dni szablonu faktycznie istnieją.

    Gdy cykl nie ma `start_date`, anchorem rotacji jest POCZĄTEK ZAKRESU: „NULL ⇒
    od pierwszego" (karta B07 §Backend) znaczy „pierwszy tydzień zakresu dostaje
    pierwszy szablon", a nie „każdy tydzień dostaje pierwszy szablon" — inaczej
    cykl bez daty startu w ogóle by nie rotował.
    """
    if not is_week_start(date_from):
        raise ValueError("Zakres cyklu musi zaczynać się w poniedziałek.")

    anchor = week_start_of(start_date) if start_date is not None else date_from

    plan: list[tuple[date, int]] = []
    week = date_from
    while week <= date_to:
        index = cycle_rotation_index(len(template_ids), anchor, week)
        plan.append((week, template_ids[index]))
        week += timedelta(days=DAYS_PER_WEEK)
    return plan


def block_copy_sequence(
    source_from: date, source_days: int, repeat_each: int, target_start: date
) -> list[tuple[date, date]]:
    """Pary (dzień źródłowy, dzień docelowy) dla „powiel blok" — model 2+2+2.

    Każdy dzień bloku powtarza się `repeat_each` razy pod rząd, więc 3 dni x 2
    dają kolejność d1,d1,d2,d2,d3,d3 (a NIE d1,d2,d3,d1,d2,d3). Tak działa
    zalecenie dietetyczki „każdą dietę stosuje się 2 dni pod rząd"
    (model 2+2+2 z listu dietetyczki): dni tej samej diety muszą sąsiadować, bo to one
    upraszczają zakupy i pozwalają ugotować podwójną porcję.
    """
    if source_days < 1 or repeat_each < 1:
        raise ValueError("Blok wymaga co najmniej jednego dnia i jednego powtórzenia.")

    sequence: list[tuple[date, date]] = []
    for day_index in range(source_days):
        source = source_from + timedelta(days=day_index)
        for repeat_index in range(repeat_each):
            offset = day_index * repeat_each + repeat_index
            sequence.append((source, target_start + timedelta(days=offset)))
    return sequence
