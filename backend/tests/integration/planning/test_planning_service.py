"""Serwis planu dnia + baza: agregaty, rozkład rodzinny, kopiowanie, kaskady, blokady.

Scenariusze z karty B06 §Tests (integration). Wspólne motywy:
niezmiennik 02_DOMAIN §13.2 (żadna wartość odżywcza nie jest zapisana w bazie)
i §13.1 (ilość nieprzeliczalna wysadza zapis, nie „ratuje się" domysłem).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.scope import Scope
from app.modules.catalog.models import CanonicalProduct, VerificationStatus
from app.modules.catalog.service import CatalogService
from app.modules.catalog.units import AmountUnit, UnitConversionError
from app.modules.planning.models import PlanDay, PlanItemServing, PlanMeal, PlanMealItem
from app.modules.planning.schemas import (
    ItemCreateRequest,
    ItemUpdateRequest,
    MealCreateRequest,
    PlanCopyRequest,
    PlanServingSplitInput,
)
from app.modules.planning.service import PlanningService, PlanValidationError
from app.modules.recipes.service import RecipesService
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
    create_unit_weight,
    create_user,
)

pytestmark = pytest.mark.integration

DAY = date(2026, 8, 17)
NEXT_DAY = date(2026, 8, 18)


async def _count(session: AsyncSession, table: object) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(table))).scalar_one()  # type: ignore[arg-type]
    )


async def _full_product(session: AsyncSession, *, name: str = "Skyr naturalny") -> CanonicalProduct:
    """Produkt ze ZWERYFIKOWANYM kompletem wartości — 60 kcal / 10 g białka na 100 g."""
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


# --- agregaty ---------------------------------------------------------------------------


async def test_wartosci_dnia_sa_suma_posilkow_i_pozycji(db_session: AsyncSession) -> None:
    """Pozycja = porcja x mnożnik, posiłek = Σ pozycji, dzień = Σ posiłków (02 §13.3)."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Owsianka", base_servings=2)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=product,
        amount=Decimal("400"),
        amount_unit=AmountUnit.GRAM,
    )

    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    breakfast = await create_plan_meal(db_session, plan_day=plan_day, name="Śniadanie")
    lunch = await create_plan_meal(db_session, plan_day=plan_day, name="Obiad", position=1)
    # Porcja przepisu = 400 g / 2 = 200 g produktu = 120 kcal; x1,5 = 180 kcal.
    await create_plan_item(db_session, meal=breakfast, recipe=recipe, servings=Decimal("1.50"))
    # Produkt luzem 250 g = 150 kcal.
    await create_plan_item(
        db_session,
        meal=lunch,
        product=product,
        amount=Decimal("250"),
        amount_unit=AmountUnit.GRAM,
    )

    view = await PlanningService(db_session).get_day(user, DAY)

    assert [meal.nutrition.kcal for meal in view.meals] == [Decimal("180"), Decimal("150")]
    assert view.nutrition.kcal == Decimal("330")
    assert view.nutrition.complete is True


async def test_zmiana_mnoznika_przelicza_pozycje_posilek_i_dzien(
    db_session: AsyncSession,
) -> None:
    """Niezmiennik 02_DOMAIN §13.3 — jedno źródło, więc wszystko zmienia się razem."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Owsianka", base_servings=1)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=product,
        amount=Decimal("100"),
        amount_unit=AmountUnit.GRAM,
    )
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe, servings=Decimal("1.00"))

    service = PlanningService(db_session)
    view = await service.update_item(
        item.id, user=user, payload=ItemUpdateRequest(servings=Decimal("2.50"))
    )

    assert view.meals[0].items[0].nutrition.kcal == Decimal("150")
    assert view.meals[0].nutrition.kcal == Decimal("150")
    assert view.nutrition.kcal == Decimal("150")


async def test_produkt_niezweryfikowany_znaczy_dzien_jako_niepelny(
    db_session: AsyncSession,
) -> None:
    """Brak danych nigdy nie jest cichym zerem — dzień dostaje `complete=False`."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Bez wartości")
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session, meal=meal, product=product, amount=Decimal("100"), amount_unit=AmountUnit.GRAM
    )

    view = await PlanningService(db_session).get_day(user, DAY)

    assert view.nutrition.complete is False
    assert view.nutrition.missing != ()


async def test_wartosci_nie_sa_zapisywane_w_bazie(db_session: AsyncSession) -> None:
    """Inspekcja schematu: w tabelach planu nie ma ANI JEDNEJ kolumny z wynikiem."""
    columns = set(PlanMealItem.__table__.columns.keys()) | set(PlanMeal.__table__.columns.keys())
    columns |= set(PlanDay.__table__.columns.keys())

    assert not columns & {"kcal", "protein_g", "fat_g", "carbs_g", "nutrition", "glycemic_load"}


# --- cel dnia ------------------------------------------------------------------------------


async def test_status_dnia_liczy_sie_wg_celu_z_daty_dnia(db_session: AsyncSession) -> None:
    """Cel zmieniony od nowej daty nie zmienia statusów dni sprzed tej daty."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("300"))
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

    service = PlanningService(db_session)
    before = await service.get_day(user, DAY)
    after = await service.get_day(user, NEXT_DAY)

    # 500 g x 60 kcal/100 g = 300 kcal: dokładnie cel starego dnia, 10% celu nowego.
    assert before.progress["kcal"].target == Decimal("300")
    assert before.progress["kcal"].status is not None
    assert before.progress["kcal"].status.value == "ok"
    assert after.progress["kcal"].target == Decimal("3000")
    assert after.progress["kcal"].status is not None
    assert after.progress["kcal"].status.value == "below"


async def test_dzien_bez_planu_zwraca_pusty_widok_a_nie_blad(db_session: AsyncSession) -> None:
    """Otwarcie daty bez planu to normalna sytuacja (dzień powstaje przy 1. posiłku)."""
    user = await create_user(db_session)

    view = await PlanningService(db_session).get_day(user, DAY)

    assert view.entity is None
    assert view.meals == []
    assert view.nutrition.kcal == Decimal("0")
    assert view.progress["kcal"].status is None


# --- posiłki i pozycje ------------------------------------------------------------------


async def test_pierwszy_posilek_tworzy_dzien_implicite(db_session: AsyncSession) -> None:
    """Mniej kliknięć od intencji do efektu (06_UIUX §2) — dzień powstaje sam."""
    user = await create_user(db_session)

    view = await PlanningService(db_session).create_meal(
        user, DAY, MealCreateRequest(name="II śniadanie")
    )

    assert view.entity is not None
    assert [meal.meal.name for meal in view.meals] == ["II śniadanie"]
    assert await _count(db_session, PlanDay) == 1


async def test_kolejne_posilki_ladują_na_koncu_listy(db_session: AsyncSession) -> None:
    """Pozycja domyślna to `max + 1` — nowy posiłek nie wpada w środek dnia."""
    user = await create_user(db_session)
    service = PlanningService(db_session)

    await service.create_meal(user, DAY, MealCreateRequest(name="Śniadanie"))
    await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))
    view = await service.create_meal(user, DAY, MealCreateRequest(name="Kolacja"))

    assert [meal.meal.position for meal in view.meals] == [0, 1, 2]
    assert [meal.meal.name for meal in view.meals] == ["Śniadanie", "Obiad", "Kolacja"]


async def test_produkt_luzem_zapisuje_sie_znormalizowany(db_session: AsyncSession) -> None:
    """0,25 kg → 250 g na osi produktu (ADR-005); w bazie nie ma „kg"."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))
    meal_id = day_view.meals[0].meal.id

    view = await service.add_item(
        meal_id,
        user=user,
        payload=ItemCreateRequest(product_id=product.id, quantity=Decimal("0.25"), unit="kg"),
    )

    item = view.meals[0].items[0].item
    assert item.amount == Decimal("250.000")
    assert item.amount_unit is AmountUnit.GRAM


async def test_ilosc_nieprzeliczalna_odrzuca_zapis_bez_sladu(db_session: AsyncSession) -> None:
    """Niezmiennik 02_DOMAIN §13.1: brak przelicznika ⇒ 422 i ZERO wierszy pozycji."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))
    meal_id = day_view.meals[0].meal.id

    with pytest.raises(UnitConversionError) as error:
        await service.add_item(
            meal_id,
            user=user,
            payload=ItemCreateRequest(product_id=product.id, quantity=Decimal("2"), unit="garść"),
        )

    assert error.value.status_code == 422
    await db_session.rollback()
    assert await _count(db_session, PlanMealItem) == 0


async def test_jednostka_domowa_produktu_przechodzi(db_session: AsyncSession) -> None:
    """Ten sam „garść" z przelicznikiem PRZY PRODUKCIE zapisuje się bez problemu."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    await create_unit_weight(
        db_session, product=product, unit_label="garść", grams_per_unit=Decimal("30.00")
    )
    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))

    view = await service.add_item(
        day_view.meals[0].meal.id,
        user=user,
        payload=ItemCreateRequest(product_id=product.id, quantity=Decimal("2"), unit="garść"),
    )

    assert view.meals[0].items[0].item.amount == Decimal("60.000")


async def test_pozycja_z_niewidocznym_przepisem_jest_odrzucana(db_session: AsyncSession) -> None:
    """Cudzy prywatny przepis nie może wejść do planu — 422 z komunikatem PL."""
    user = await create_user(db_session, email="user@example.com")
    stranger = await create_user(db_session, email="stranger@example.com")
    foreign = await create_recipe(db_session, owner=stranger, name="Cudze danie")

    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))

    with pytest.raises(PlanValidationError):
        await service.add_item(
            day_view.meals[0].meal.id,
            user=user,
            payload=ItemCreateRequest(recipe_id=foreign.id),
        )


# --- rozkład rodzinny -----------------------------------------------------------------------


async def test_rozklad_rodzinny_musi_sumowac_sie_do_liczby_porcji(
    db_session: AsyncSession,
) -> None:
    """Suma 2x1,0 + 2x0,8 + 2x1,3 = 6,2 przechodzi; ta sama lista przy 6,0 — nie."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profiles = [
        await create_member_profile(db_session, household=household, name=f"Osoba {index}")
        for index in range(3)
    ]
    recipe = await create_recipe(db_session, owner=user, name="Zapiekanka")

    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))
    meal_id = day_view.meals[0].meal.id
    split = [
        PlanServingSplitInput(member_profile_id=profiles[0].id, multiplier=Decimal("2.0")),
        PlanServingSplitInput(member_profile_id=profiles[1].id, multiplier=Decimal("1.6")),
        PlanServingSplitInput(member_profile_id=profiles[2].id, multiplier=Decimal("2.6")),
    ]

    view = await service.add_item(
        meal_id,
        user=user,
        payload=ItemCreateRequest(
            recipe_id=recipe.id, servings=Decimal("6.2"), servings_split=split
        ),
    )
    assert len(view.meals[0].items[0].split) == 3

    with pytest.raises(PlanValidationError):
        await service.add_item(
            meal_id,
            user=user,
            payload=ItemCreateRequest(
                recipe_id=recipe.id, servings=Decimal("6.0"), servings_split=split
            ),
        )


async def test_prosty_przypadek_dziala_bez_rozkladu(db_session: AsyncSession) -> None:
    """„7 porcji" bez rozkładu nie wymaga żadnego dodatkowego kroku (02_DOMAIN §7)."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))

    view = await service.add_item(
        day_view.meals[0].meal.id,
        user=user,
        payload=ItemCreateRequest(recipe_id=recipe.id, servings=Decimal("7")),
    )

    assert view.meals[0].items[0].item.servings == Decimal("7.00")
    assert view.meals[0].items[0].split == []


async def test_profil_spoza_rodziny_wlasciciela_jest_odrzucany(
    db_session: AsyncSession,
) -> None:
    """Rozkład nie może wskazać cudzego profilu — 422, bez ujawniania, że istnieje."""
    household = await create_household(db_session, name="Kowalscy")
    other = await create_household(db_session, name="Nowakowie")
    user = await create_user(db_session, household=household)
    foreign_profile = await create_member_profile(db_session, household=other, name="Obcy")
    recipe = await create_recipe(db_session, owner=user)

    service = PlanningService(db_session)
    day_view = await service.create_meal(user, DAY, MealCreateRequest(name="Obiad"))

    with pytest.raises(PlanValidationError):
        await service.add_item(
            day_view.meals[0].meal.id,
            user=user,
            payload=ItemCreateRequest(
                recipe_id=recipe.id,
                servings=Decimal("1"),
                servings_split=[
                    PlanServingSplitInput(
                        member_profile_id=foreign_profile.id, multiplier=Decimal("1")
                    )
                ],
            ),
        )


async def test_zmiana_mnoznika_bez_rozkladu_nie_moze_rozjechac_sumy(
    db_session: AsyncSession,
) -> None:
    """PATCH samego `servings` przy istniejącym rozkładzie kończy się 422."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    recipe = await create_recipe(db_session, owner=user)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe, servings=Decimal("1.00"))
    await create_item_split(db_session, item=item, profile=profile, multiplier=Decimal("1.00"))

    with pytest.raises(PlanValidationError):
        await PlanningService(db_session).update_item(
            item.id, user=user, payload=ItemUpdateRequest(servings=Decimal("2.00"))
        )


# --- kopiowanie ----------------------------------------------------------------------------


async def test_kopia_dnia_jest_gleboka_i_niezalezna(db_session: AsyncSession) -> None:
    """Nowe id posiłków/pozycji, równe wartości, edycja kopii nie rusza oryginału."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY, title="Poniedziałek")
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Obiad")
    item = await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("200"),
        amount_unit=AmountUnit.GRAM,
        servings=Decimal("2.00"),
    )
    await create_item_split(db_session, item=item, profile=profile, multiplier=Decimal("2.00"))

    service = PlanningService(db_session)
    copies = await service.copy(
        user=user,
        payload=PlanCopyRequest(what="day", source_date=DAY, target_dates=[NEXT_DAY]),
    )

    copy_view = copies[0]
    copied_item = copy_view.meals[0].items[0]
    assert copied_item.item.id != item.id
    assert copy_view.meals[0].meal.id != meal.id
    assert copy_view.nutrition.kcal == (await service.get_day(user, DAY)).nutrition.kcal
    assert [row.multiplier for row in copied_item.split] == [Decimal("2.00")]

    await service.update_item(
        copied_item.item.id, user=user, payload=ItemUpdateRequest(quantity=Decimal("50"), unit="g")
    )
    original = await service.get_day(user, DAY)
    assert original.meals[0].items[0].item.amount == Decimal("200.000")


async def test_kopiowanie_na_zajeta_date_dopisuje_posilki(db_session: AsyncSession) -> None:
    """Kopia nigdy nie nadpisuje — istniejący plan zostaje, nowe posiłki idą na koniec."""
    user = await create_user(db_session)
    source = await create_plan_day(db_session, owner=user, day=DAY)
    await create_plan_meal(db_session, plan_day=source, name="Obiad")
    target = await create_plan_day(db_session, owner=user, day=NEXT_DAY)
    await create_plan_meal(db_session, plan_day=target, name="Śniadanie")

    views = await PlanningService(db_session).copy(
        user=user,
        payload=PlanCopyRequest(what="day", source_date=DAY, target_dates=[NEXT_DAY]),
    )

    assert [meal.meal.name for meal in views[0].meals] == ["Śniadanie", "Obiad"]
    assert [meal.meal.position for meal in views[0].meals] == [0, 1]


async def test_kopiowanie_dnia_na_wiele_dat_naraz(db_session: AsyncSession) -> None:
    """Jedna akcja, kilka dat — „skopiuj poniedziałek na cały tydzień"."""
    user = await create_user(db_session)
    source = await create_plan_day(db_session, owner=user, day=DAY)
    await create_plan_meal(db_session, plan_day=source, name="Obiad")
    targets = [date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21)]

    views = await PlanningService(db_session).copy(
        user=user, payload=PlanCopyRequest(what="day", source_date=DAY, target_dates=targets)
    )

    assert [view.day for view in views] == targets
    assert all(len(view.meals) == 1 for view in views)
    assert await _count(db_session, PlanDay) == 4


async def test_duplikacja_posilku_w_tym_samym_dniu(db_session: AsyncSession) -> None:
    """Menu ⋮ „duplikuj" = `/plan/copy what=meal` na tę samą datę (karta B06)."""
    user = await create_user(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Przekąska")

    views = await PlanningService(db_session).copy(
        user=user,
        payload=PlanCopyRequest(what="meal", source_meal_id=meal.id, target_dates=[DAY]),
    )

    assert [item.meal.name for item in views[0].meals] == ["Przekąska", "Przekąska"]


async def test_kopiowanie_nieistniejacego_dnia_daje_404(db_session: AsyncSession) -> None:
    """Źródło musi istnieć — pusty dzień nie jest „czymś do skopiowania"."""
    user = await create_user(db_session)

    with pytest.raises(NotFoundError):
        await PlanningService(db_session).copy(
            user=user,
            payload=PlanCopyRequest(what="day", source_date=DAY, target_dates=[NEXT_DAY]),
        )


# --- sprzątanie pustego dnia (ustalenie REVIEW R3, dług U17) ------------------------------


async def test_usuniecie_ostatniego_posilku_kasuje_pusty_dzien(db_session: AsyncSession) -> None:
    """Dzień bez posiłków i bez tytułu przestaje istnieć razem z ostatnim posiłkiem.

    Wiersz `plan_days` powstaje implicite, a puste UI pokazuje jako „brak planu" —
    zostawiony trzymał `household_id` z FK RESTRICT i blokował usunięcie rodziny
    bez śladu w interfejsie (U17).
    """
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    first = await create_plan_meal(db_session, plan_day=plan_day, name="Obiad", position=0)
    second = await create_plan_meal(db_session, plan_day=plan_day, name="Kolacja", position=1)
    service = PlanningService(db_session)

    await service.delete_meal(first.id, user=user)
    assert await _count(db_session, PlanDay) == 1, "dzień z jednym posiłkiem musi zostać"

    view = await service.delete_meal(second.id, user=user)

    assert await _count(db_session, PlanDay) == 0
    assert view.meals == []
    assert view.day == DAY


async def test_pusty_dzien_z_tytulem_zostaje(db_session: AsyncSession) -> None:
    """Tytuł to jawna decyzja użytkownika, więc sprzątanie go nie dotyczy."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY, title="Urodziny Zosi")
    meal = await create_plan_meal(db_session, plan_day=plan_day)

    await PlanningService(db_session).delete_meal(meal.id, user=user)

    assert await _count(db_session, PlanDay) == 1


async def test_pusty_dzien_udostepniony_rodzinie_zostaje(db_session: AsyncSession) -> None:
    """`scope='household'` też jest decyzją — sprzątanie nie może jej cofnąć."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY, scope=Scope.HOUSEHOLD)
    meal = await create_plan_meal(db_session, plan_day=plan_day)

    await PlanningService(db_session).delete_meal(meal.id, user=user)

    assert await _count(db_session, PlanDay) == 1


# --- kaskady i blokady usuwania -----------------------------------------------------------


async def test_usuniecie_dnia_kasuje_posilki_pozycje_i_rozklady(
    db_session: AsyncSession,
) -> None:
    """Kompozycja dzień → posiłki → pozycje → rozkład znika w całości (ADR-012)."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    recipe = await create_recipe(db_session, owner=user)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)
    await create_item_split(db_session, item=item, profile=profile)

    await db_session.delete(plan_day)
    await db_session.commit()

    assert await _count(db_session, PlanMeal) == 0
    assert await _count(db_session, PlanMealItem) == 0
    assert await _count(db_session, PlanItemServing) == 0


async def test_usuniecie_profilu_kasuje_jego_rozklady(db_session: AsyncSession) -> None:
    """Rozkład bez osoby przy stole nie znaczy nic — CASCADE na `member_profiles`."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    recipe = await create_recipe(db_session, owner=user)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)
    await create_item_split(db_session, item=item, profile=profile)

    await db_session.delete(profile)
    await db_session.commit()

    assert await _count(db_session, PlanItemServing) == 0
    assert await _count(db_session, PlanMealItem) == 1


async def test_usuniecie_przepisu_uzytego_w_planie_daje_409_z_dniem(
    db_session: AsyncSession,
) -> None:
    """RESTRICT + rejestr referencji: 409 z nazwą/datą dnia w `details.used_in`."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Gołąbki")
    plan_day = await create_plan_day(db_session, owner=user, day=DAY, title="Poniedziałek")
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(db_session, meal=meal, recipe=recipe)

    with pytest.raises(ConflictError) as error:
        await RecipesService(db_session).delete_recipe(recipe.id, actor=user)

    used_in = error.value.details["used_in"]
    assert used_in == [{"type": "plan_day", "id": plan_day.id, "name": "Poniedziałek"}]


async def test_dzien_bez_tytulu_pokazuje_date_w_used_in(db_session: AsyncSession) -> None:
    """Bez tytułu użytkownik i tak wie, o który dzień chodzi — pokazujemy datę."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(db_session, meal=meal, recipe=recipe)

    references = await RecipesService(db_session).recipe_references(recipe.id)

    assert [reference.name for reference in references] == ["Plan dnia 17.08.2026"]


async def test_produkt_uzyty_w_planie_tez_blokuje_usuniecie(db_session: AsyncSession) -> None:
    """Rejestr referencji katalogu (B04) dostaje od planningu własny licznik."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY, title="Wtorek")
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session, meal=meal, product=product, amount=Decimal("100"), amount_unit=AmountUnit.GRAM
    )

    references = await CatalogService(db_session).product_references(product.id)

    assert [reference.name for reference in references] == ["Wtorek"]
    assert all(reference.type == "plan_day" for reference in references)


# --- widoczność (scope) ----------------------------------------------------------------------


async def test_dzien_rodzinny_widzi_kazdy_czlonek(db_session: AsyncSession) -> None:
    """Scope HOUSEHOLD: dzień właściciela jest widoczny dla reszty rodziny."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    await create_plan_day(db_session, owner=owner, day=DAY, scope=Scope.HOUSEHOLD, title="Wspólny")

    view = await PlanningService(db_session).get_day(member, DAY)

    assert view.entity is not None
    assert view.entity.title == "Wspólny"


async def test_cudzy_dzien_prywatny_jest_niewidoczny(db_session: AsyncSession) -> None:
    """PRIVATE innego użytkownika = pusty dzień, dokładnie jak brak planu."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    await create_plan_day(db_session, owner=owner, day=DAY, title="Tajny")

    view = await PlanningService(db_session).get_day(member, DAY)

    assert view.entity is None


async def test_wlasny_dzien_wygrywa_z_rodzinnym_na_tej_samej_dacie(
    db_session: AsyncSession,
) -> None:
    """Reguła rozstrzygania: własny plan przed planem rodzinnym (jedna dla całego modułu)."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    await create_plan_day(db_session, owner=owner, day=DAY, scope=Scope.HOUSEHOLD, title="Rodzinny")
    await create_plan_day(db_session, owner=member, day=DAY, title="Mój")

    service = PlanningService(db_session)
    detail = await service.get_day(member, DAY)
    listed = await service.list_days(member, date_from=DAY, date_to=DAY)

    assert detail.entity is not None and detail.entity.title == "Mój"
    assert [view.entity.title for view in listed if view.entity is not None] == ["Mój"]


async def test_pozycja_w_cudzym_dniu_nie_da_sie_ruszyc_po_id(
    db_session: AsyncSession,
) -> None:
    """Anty-IDOR: sprawdzany jest łańcuch pozycja → posiłek → dzień, nie samo id."""
    owner = await create_user(db_session, email="owner@example.com")
    stranger = await create_user(db_session, email="stranger@example.com")
    recipe = await create_recipe(db_session, owner=owner)
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)

    service = PlanningService(db_session)
    with pytest.raises(NotFoundError):
        await service.update_item(
            item.id, user=stranger, payload=ItemUpdateRequest(servings=Decimal("5"))
        )
    with pytest.raises(NotFoundError):
        await service.delete_meal(meal.id, user=stranger)


async def test_uzytkownik_bez_rodziny_nie_ustawi_scope_household(
    db_session: AsyncSession,
) -> None:
    """Stan „bez rodziny" jest legalny, ale scope HOUSEHOLD nie — 409 z instrukcją."""
    user = await create_user(db_session)

    with pytest.raises(ConflictError):
        await PlanningService(db_session).upsert_day(user, DAY, title=None, scope=Scope.HOUSEHOLD)


# --- dopasuj porcję do celu ----------------------------------------------------------------


async def test_fit_to_target_proponuje_mnoznik_i_nic_nie_zapisuje(
    db_session: AsyncSession,
) -> None:
    """500 kcal celu / 120 kcal porcji = 4,16 (w dół); pozycja zostaje przy 1,00."""
    user = await create_user(db_session)
    product = await _full_product(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Owsianka", base_servings=1)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=product,
        amount=Decimal("200"),
        amount_unit=AmountUnit.GRAM,
    )
    plan_day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=plan_day, kcal_target=Decimal("500"))
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)

    service = PlanningService(db_session)
    proposal = await service.fit_to_target(item.id, user=user)

    assert proposal.proposed_servings == Decimal("4.16")
    assert proposal.resulting_nutrition.kcal == Decimal("499")
    after = await service.get_day(user, DAY)
    assert after.meals[0].items[0].item.servings == Decimal("1.00")
