"""Wydajność widoku tygodnia — licznik zapytań SQL i pomiar czasu (audyt R2).

Po co ten plik: `GET /plan/days?from=&to=` czyta 7 dni x posiłki x pozycje
i dla każdej pozycji potrzebuje wartości odżywczych z przepisu albo produktu.
To pierwsze miejsce w systemie, w którym łatwo o N+1 — a niezmiennik
02_DOMAIN §13.2 ZABRANIA ratowania wydajności cache'owaniem wartości w encjach,
więc jedyną dopuszczalną obroną jest stała liczba zapytań.

Test mierzy tę liczbę licznikiem zdarzeń SQLAlchemy (`before_cursor_execute`),
a nie „na oko": tydzień pełnego planu musi kosztować DOKŁADNIE tyle zapytań,
co jeden dzień. Rośnie objętość danych, nie liczba round-tripów.

Czas wykonania też jest mierzony i raportowany (`--durations` nie wystarcza,
bo mierzyłby też seedowanie), ale asercja czasu jest ŚWIADOMIE luźna: budżet
z karty R2 (<500 ms) dotyczy realnego środowiska, a tu mierzymy bazę w Dockerze
na maszynie deweloperskiej razem z narzutem testu.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.catalog.models import VerificationStatus
from app.modules.catalog.units import AmountUnit
from app.modules.planning.service import PlanningService
from tests.factories import (
    create_category,
    create_goal,
    create_household,
    create_ingredient,
    create_item_split,
    create_member_profile,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_user,
)
from tests.helpers import API, login

pytestmark = pytest.mark.integration

#: Poniedziałek tygodnia mierzonego przez ten test.
WEEK_START = date(2026, 9, 7)

#: Kształt „pełnego" tygodnia: tyle posiłków w dniu i tyle pozycji w posiłku.
MEALS_PER_DAY = 4
RECIPE_ITEMS_PER_MEAL = 2
PRODUCT_ITEMS_PER_MEAL = 2
INGREDIENTS_PER_RECIPE = 5

#: Ile pozycji ma tydzień takiego planu — liczba trafia do raportu pomiaru.
ITEMS_PER_WEEK = 7 * MEALS_PER_DAY * (RECIPE_ITEMS_PER_MEAL + PRODUCT_ITEMS_PER_MEAL)

#: Budżet zapytań: dni, posiłki, pozycje, rozkłady, przepisy, składniki
#: przepisów, produkty składników, produkty luzem, profile rozkładu, cele.
#: Zapas jest mały z rozmysłem — każde dodatkowe zapytanie ma tu być widoczne.
MAX_QUERIES = 12


@dataclass
class _Seeded:
    """To, co test potrzebuje po zaseedowaniu tygodnia."""

    user: Any
    dates: list[date]


@contextmanager
def count_queries(engine: AsyncEngine) -> Iterator[list[str]]:
    """Zbiera treści zapytań wykonanych w bloku (licznik N+1).

    Podpinamy się pod SYNCHRONICZNY silnik pod maską (`engine.sync_engine`) —
    to tam psycopg wykonuje kursory, więc zdarzenie widzi każde zapytanie,
    również te wywołane przez ORM w tle.
    """
    statements: list[str] = []

    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


async def _seed_week(session: AsyncSession, *, days: int) -> _Seeded:
    """Pełny plan na `days` dni: posiłki, pozycje z przepisów i produkty luzem.

    Dane są celowo „grube": każdy dzień ma cztery posiłki, każdy posiłek dwie
    pozycje z przepisu (a każdy przepis pięć składników) i dwie pozycje
    z produktem luzem, a każda pozycja z przepisu ma rozkład rodzinny. Bez
    rozkładów i bez produktów luzem część zapytań w `_build_days` odpadłaby
    przez pusty zbiór id i test przestałby pilnować tego, co ma pilnować.
    """
    household = await create_household(session, name="Wydajni")
    user = await create_user(session, email="wydajnosc@example.com", household=household)
    profile = await create_member_profile(session, household=household, name="Ania", owner=user)
    await create_goal(session, user=user, valid_from=WEEK_START, kcal=Decimal("2200"))

    category = await create_category(session, name="Kategoria wydajności")
    products = [
        await create_product(
            session,
            category=category,
            name=f"Produkt wydajnościowy {index}",
            kcal_100=Decimal("60.00"),
            protein_100=Decimal("10.00"),
            fat_100=Decimal("0.20"),
            carbs_100=Decimal("4.00"),
            fiber_100=Decimal("0.00"),
            sugars_100=Decimal("4.00"),
            glycemic_index=Decimal("11.0"),
            verification_status=VerificationStatus.VERIFIED,
        )
        for index in range(INGREDIENTS_PER_RECIPE)
    ]

    recipes = []
    for index in range(MEALS_PER_DAY * RECIPE_ITEMS_PER_MEAL):
        recipe = await create_recipe(
            session, owner=user, name=f"Przepis wydajnościowy {index}", base_servings=2
        )
        for position, product in enumerate(products):
            await create_ingredient(
                session,
                recipe=recipe,
                product=product,
                amount=Decimal("100.000"),
                amount_unit=AmountUnit.GRAM,
                position=position,
            )
        recipes.append(recipe)

    dates = [WEEK_START + timedelta(days=offset) for offset in range(days)]
    for day in dates:
        plan_day = await create_plan_day(session, owner=user, day=day)
        for meal_index in range(MEALS_PER_DAY):
            meal = await create_plan_meal(
                session,
                plan_day=plan_day,
                name=f"Posiłek {meal_index}",
                position=meal_index,
            )
            for item_index in range(RECIPE_ITEMS_PER_MEAL):
                item = await create_plan_item(
                    session,
                    meal=meal,
                    recipe=recipes[meal_index * RECIPE_ITEMS_PER_MEAL + item_index],
                    servings=Decimal("1.50"),
                    position=item_index,
                )
                await create_item_split(
                    session, item=item, profile=profile, multiplier=Decimal("1.50")
                )
            for item_index in range(PRODUCT_ITEMS_PER_MEAL):
                await create_plan_item(
                    session,
                    meal=meal,
                    product=products[item_index],
                    amount=Decimal("150.000"),
                    amount_unit=AmountUnit.GRAM,
                    servings=Decimal("1.00"),
                    position=RECIPE_ITEMS_PER_MEAL + item_index,
                )

    return _Seeded(user=user, dates=dates)


async def test_widok_tygodnia_nie_ma_n_plus_1(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Tydzień pełnego planu kosztuje tyle samo zapytań, co jeden dzień.

    To jest właściwa asercja przeciw N+1: nie „mało zapytań", a „liczba
    zapytań nie zależy od liczby dni, posiłków ani pozycji".
    """
    seeded = await _seed_week(db_session, days=7)
    service = PlanningService(db_session)

    with count_queries(db_engine) as one_day:
        await service.list_days(seeded.user, date_from=seeded.dates[0], date_to=seeded.dates[0])
    with count_queries(db_engine) as full_week:
        views = await service.list_days(
            seeded.user, date_from=seeded.dates[0], date_to=seeded.dates[-1]
        )

    assert len(views) == 7
    items_in_week = sum(len(meal.items) for view in views for meal in view.meals)
    assert items_in_week == ITEMS_PER_WEEK

    print(
        f"\n[R2] zapytania SQL: 1 dzień = {len(one_day)}, "
        f"7 dni ({items_in_week} pozycji) = {len(full_week)}"
    )

    assert len(full_week) == len(one_day), (
        f"Liczba zapytań rośnie z zakresem dat: 1 dzień = {len(one_day)}, "
        f"7 dni = {len(full_week)}.\n" + "\n".join(full_week)
    )
    assert len(full_week) <= MAX_QUERIES, (
        f"Widok tygodnia wykonał {len(full_week)} zapytań (budżet {MAX_QUERIES}).\n"
        + "\n".join(full_week)
    )


async def test_widok_tygodnia_miesci_sie_w_budzecie_czasu(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Pomiar czasu `list_days` na pełnym tygodniu — budżet z karty R2.

    Mierzymy SAM odczyt (seedowanie jest poza pomiarem) i raportujemy wynik
    przez `print`, żeby liczba trafiła do dziennika review, a nie tylko do
    zielonej kropki. Asercja jest luźniejsza od budżetu 500 ms z karty,
    bo test dzieli maszynę z Dockerem i resztą suity — pilnuje rzędu
    wielkości (setki ms, nie sekundy), a nie milisekund.
    """
    seeded = await _seed_week(db_session, days=7)
    service = PlanningService(db_session)

    # Pierwszy przebieg rozgrzewa pulę połączeń i cache planów zapytań PG.
    await service.list_days(seeded.user, date_from=seeded.dates[0], date_to=seeded.dates[-1])

    started = time.perf_counter()
    views = await service.list_days(
        seeded.user, date_from=seeded.dates[0], date_to=seeded.dates[-1]
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    print(
        f"\n[R2] PlanningService.list_days (7 dni, {ITEMS_PER_WEEK} pozycji): {elapsed_ms:.1f} ms"
    )

    assert len(views) == 7
    assert elapsed_ms < 2000, f"Widok tygodnia trwał {elapsed_ms:.1f} ms"


async def test_endpoint_tygodnia_miesci_sie_w_budzecie_czasu(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Ten sam pomiar, ale przez HTTP — z walidacją Pydantica i serializacją.

    Serwis to nie cała cena: odpowiedź `GET /plan/days` przepakowuje każdą
    pozycję na schematy `DecimalString`, a to właśnie ten czas widzi
    przeglądarka. Bez tego pomiaru budżet z karty R2 byłby zmierzony
    w połowie.
    """
    seeded = await _seed_week(db_session, days=7)
    await login(db_client, seeded.user.email)
    url = f"{API}/plan/days?from={seeded.dates[0]}&to={seeded.dates[-1]}"

    warmup = await db_client.get(url)
    assert warmup.status_code == 200, warmup.text

    started = time.perf_counter()
    response = await db_client.get(url)
    elapsed_ms = (time.perf_counter() - started) * 1000

    print(f"\n[R2] GET /plan/days (7 dni, {ITEMS_PER_WEEK} pozycji): {elapsed_ms:.1f} ms")

    assert response.status_code == 200
    assert response.json()["total"] == 7
    assert elapsed_ms < 2000, f"Endpoint tygodnia trwał {elapsed_ms:.1f} ms"
