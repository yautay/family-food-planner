"""Serwis statystyk + baza: agregacja z realnego planu, scope i luki (karta B13).

Motywy przewodnie:

- statystyki są POCHODNĄ planu i celów — nic nie jest zapisywane ani cache'owane
  (niezmiennik 02_DOMAIN §13.2),
- widoczność jest ta sama, co w widoku planu: cudzy dzień prywatny nie wchodzi
  do agregatów, dzień rodzinny wchodzi (04_API §3, anty-IDOR),
- dzień bez planu to luka, nie zero (Acceptance Criteria 4).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.modules.catalog.models import CanonicalProduct, VerificationStatus
from app.modules.catalog.units import AmountUnit
from app.modules.nutrition.types import GoalStatus
from app.modules.planning.service import PlanningService, PlanValidationError
from app.modules.planning.stats_service import MAX_STATS_RANGE_DAYS, StatsService
from tests.factories import (
    assign_to_household,
    create_category,
    create_goal,
    create_household,
    create_ingredient,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_user,
)

pytestmark = pytest.mark.integration

DAY = date(2026, 8, 17)
NEXT_DAY = date(2026, 8, 18)
WEEK_END = date(2026, 8, 23)


async def _full_product(session: AsyncSession, *, name: str = "Skyr naturalny") -> CanonicalProduct:
    """Produkt ZWERYFIKOWANY: 60 kcal / 10 g białka na 100 g — liczby wychodzą „na czysto"."""
    category = await create_category(session, name=f"Kategoria {name}")
    return await create_product(
        session,
        category=category,
        name=name,
        kcal_100=Decimal("60.00"),
        protein_100=Decimal("10.00"),
        fat_100=Decimal("0.20"),
        carbs_100=Decimal("4.00"),
        fiber_100=Decimal("0.00"),
        sugars_100=Decimal("4.00"),
        glycemic_index=Decimal("11.0"),
        verification_status=VerificationStatus.VERIFIED,
    )


# --- agregacja z realnego planu -------------------------------------------------------


async def test_agregacja_z_planu_przepisy_i_produkt_luzem(db_session: AsyncSession) -> None:
    """Dwa przepisy z mnożnikami + produkt luzem: statystyki liczą to, co plan dnia."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    porridge = await create_recipe(db_session, owner=user, name="Owsianka", base_servings=2)
    await create_ingredient(
        db_session,
        recipe=porridge,
        product=product,
        amount=Decimal("400"),
        amount_unit=AmountUnit.GRAM,
    )
    salad = await create_recipe(db_session, owner=user, name="Sałatka", base_servings=1)
    await create_ingredient(
        db_session,
        recipe=salad,
        product=product,
        amount=Decimal("100"),
        amount_unit=AmountUnit.GRAM,
    )

    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    breakfast = await create_plan_meal(db_session, plan_day=plan_day, name="Śniadanie")
    lunch = await create_plan_meal(db_session, plan_day=plan_day, name="Obiad", position=1)
    # Porcja owsianki = 400 g / 2 = 200 g = 120 kcal; x1,5 = 180 kcal.
    await create_plan_item(db_session, meal=breakfast, recipe=porridge, servings=Decimal("1.50"))
    # Sałatka: 100 g = 60 kcal.
    await create_plan_item(db_session, meal=lunch, recipe=salad, servings=Decimal("1.00"))
    # Produkt luzem 250 g = 150 kcal.
    await create_plan_item(
        db_session,
        meal=lunch,
        product=product,
        amount=Decimal("250"),
        amount_unit=AmountUnit.GRAM,
        position=1,
    )

    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=DAY)

    assert stats.days[0].has_plan is True
    assert stats.days[0].nutrition is not None
    assert stats.days[0].nutrition.kcal == Decimal("390")
    assert stats.summary.days_with_plan == 1
    assert stats.summary.avg is not None
    assert stats.summary.avg.kcal == Decimal("390")


async def test_slupki_zgadzaja_sie_z_widokiem_planu_dnia(db_session: AsyncSession) -> None:
    """Jedno źródło prawdy (Acceptance Criteria 2): ten sam silnik, te same liczby."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("333"),
        amount_unit=AmountUnit.GRAM,
    )

    plan_view = await PlanningService(db_session).get_day(user, DAY)
    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=DAY)

    assert stats.days[0].nutrition is not None
    assert stats.days[0].nutrition.kcal == plan_view.nutrition.kcal
    assert stats.days[0].nutrition.protein_g == plan_view.nutrition.protein_g


async def test_dzien_bez_planu_jest_luka_i_nie_zaniza_sredniej(
    db_session: AsyncSession,
) -> None:
    """Tydzień z jednym zaplanowanym dniem ma średnią równą temu dniu, nie 1/7."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("600"))
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("1000"),
        amount_unit=AmountUnit.GRAM,
    )

    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=WEEK_END)

    assert stats.summary.days_in_range == 7
    assert stats.summary.days_with_plan == 1
    assert stats.summary.avg is not None
    assert stats.summary.avg.kcal == Decimal("600")
    assert stats.summary.progress["kcal"].status is GoalStatus.OK
    assert [day.has_plan for day in stats.days] == [True] + [False] * 6


async def test_dzien_z_tytulem_bez_posilkow_nie_jest_dniem_z_planem(
    db_session: AsyncSession,
) -> None:
    """Pusty dzień z samym tytułem (jedyny, jaki zostaje po R3) to luka, nie 0 kcal."""
    user = await create_user(db_session)
    await create_plan_day(db_session, owner=user, day=DAY, title="Wyjazd")

    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=DAY)

    assert stats.days[0].has_plan is False
    assert stats.days[0].nutrition is None
    assert stats.summary.days_with_plan == 0
    assert stats.summary.avg is None


async def test_niepelne_dane_produktu_propaguja_sie_na_dzien_i_srednia(
    db_session: AsyncSession,
) -> None:
    """Brak wartości produktu ⇒ `complete=False` + `missing` (plakietka „niepełne dane")."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Bez wartości")
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("100"),
        amount_unit=AmountUnit.GRAM,
    )

    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=DAY)

    assert stats.days[0].nutrition is not None
    assert stats.days[0].nutrition.complete is False
    assert stats.days[0].nutrition.missing != ()
    assert stats.summary.avg is not None
    assert stats.summary.avg.complete is False


# --- cele historyczne -----------------------------------------------------------------


async def test_cel_dzienny_pochodzi_z_daty_dnia_nie_z_dzisiaj(
    db_session: AsyncSession,
) -> None:
    """Zmiana celu w środku zakresu zmienia poziom celu tylko od jej daty."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("200"))
    await create_goal(db_session, user=user, valid_from=NEXT_DAY, kcal=Decimal("3000"))
    product = await _full_product(db_session)
    for day in (DAY, NEXT_DAY):
        plan_day = await create_plan_day(db_session, owner=user, day=day)
        meal = await create_plan_meal(db_session, plan_day=plan_day)
        await create_plan_item(
            db_session,
            meal=meal,
            product=product,
            amount=Decimal("500"),
            amount_unit=AmountUnit.GRAM,
        )

    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=NEXT_DAY)

    assert stats.days[0].goal is not None
    assert stats.days[0].goal.kcal == Decimal("200")
    # Ten sam dzień (300 kcal) jest „za dużo" wobec celu 200 i „za mało" wobec 3000.
    assert stats.days[0].status["kcal"] is GoalStatus.ABOVE
    assert stats.days[1].goal is not None
    assert stats.days[1].goal.kcal == Decimal("3000")
    assert stats.days[1].status["kcal"] is GoalStatus.BELOW
    # Podsumowanie porównuje średnią (300 kcal) ze ŚREDNIĄ celów (1600 kcal).
    assert stats.summary.progress["kcal"].target == Decimal("1600")


async def test_progi_uzytkownika_decyduja_o_statusie(db_session: AsyncSession) -> None:
    """Progi z `ui_settings` (D9) — statystyki nie mają własnych granic."""
    user = await create_user(db_session)
    user.ui_settings = {"nutrition_thresholds": {"low": 99, "high": 101}}
    await db_session.commit()
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("650"))
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("1000"),
        amount_unit=AmountUnit.GRAM,
    )

    stats = await StatsService(db_session).daily(user, date_from=DAY, date_to=DAY)

    # 600 kcal wobec celu 650 to 92,3% — przy domyślnych progach „ok", przy 99/101 „za mało".
    assert stats.days[0].status["kcal"] is GoalStatus.BELOW


# --- scope (anty-IDOR) ----------------------------------------------------------------


async def test_cudzy_dzien_prywatny_nie_wchodzi_do_agregatow(
    db_session: AsyncSession,
) -> None:
    """User B nie zobaczy w swoich statystykach dnia PRIVATE usera A (karta B13 §Security)."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY, scope=Scope.PRIVATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("500"),
        amount_unit=AmountUnit.GRAM,
    )

    stats = await StatsService(db_session).daily(member, date_from=DAY, date_to=DAY)

    assert stats.days[0].has_plan is False
    assert stats.summary.days_with_plan == 0


async def test_dzien_rodzinny_wchodzi_do_agregatow_czlonka(db_session: AsyncSession) -> None:
    """Dzień HOUSEHOLD jest wspólny — statystyki członka rodziny go widzą."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner2@example.com", household=household)
    member = await create_user(db_session, email="member2@example.com", household=household)
    await assign_to_household(db_session, user=member, household=household)
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY, scope=Scope.HOUSEHOLD)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("500"),
        amount_unit=AmountUnit.GRAM,
    )

    stats = await StatsService(db_session).daily(member, date_from=DAY, date_to=DAY)

    assert stats.days[0].has_plan is True
    assert stats.days[0].nutrition is not None
    assert stats.days[0].nutrition.kcal == Decimal("300")


async def test_cele_sa_wlasnoscia_konta_nie_rodziny(db_session: AsyncSession) -> None:
    """Cel właściciela dnia rodzinnego nie ustawia statusu członkowi rodziny."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner3@example.com", household=household)
    member = await create_user(db_session, email="member3@example.com", household=household)
    await create_goal(db_session, user=owner, valid_from=date(2026, 1, 1), kcal=Decimal("2000"))
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY, scope=Scope.HOUSEHOLD)
    await create_plan_meal(db_session, plan_day=plan_day)

    stats = await StatsService(db_session).daily(member, date_from=DAY, date_to=DAY)

    assert stats.days[0].goal is None


# --- walidacja zakresu ----------------------------------------------------------------


async def test_zakres_odwrocony_konczy_sie_bledem_walidacji(db_session: AsyncSession) -> None:
    """`from > to` to 422, nie pusty wynik (04_API §1)."""
    user = await create_user(db_session)

    with pytest.raises(PlanValidationError):
        await StatsService(db_session).daily(user, date_from=NEXT_DAY, date_to=DAY)


async def test_zakres_ponad_92_dni_konczy_sie_bledem_walidacji(
    db_session: AsyncSession,
) -> None:
    """Sufit zakresu jest twardy; dokładnie 92 dni jeszcze przechodzi."""
    user = await create_user(db_session)
    service = StatsService(db_session)
    date_from = date(2026, 1, 1)
    last_allowed = date_from + timedelta(days=MAX_STATS_RANGE_DAYS - 1)

    allowed = await service.daily(user, date_from=date_from, date_to=last_allowed)
    assert allowed.summary.days_in_range == MAX_STATS_RANGE_DAYS

    with pytest.raises(PlanValidationError):
        await service.daily(user, date_from=date_from, date_to=last_allowed + timedelta(days=1))
