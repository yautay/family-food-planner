"""UX03: transakcja planowania, zachowanie tożsamości i odpowiedź po ID dnia."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.models import PlanDay, PlanItemServing, PlanMeal, PlanMealItem
from app.modules.planning.schemas import ItemUpdateRequest, RecipeItemCreateRequest
from app.modules.planning.service import PlanningService, PlanValidationError
from tests.factories import (
    create_admin,
    create_household,
    create_item_split,
    create_member_profile,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_recipe,
    create_user,
)

pytestmark = pytest.mark.integration
DAY = date(2031, 1, 7)


@pytest.mark.parametrize("failure", ["recipe", "split", "profile", "duplicate"])
async def test_blad_wycofuje_nowy_dzien_i_posilek(db_session: AsyncSession, failure: str) -> None:
    """Odmowa po flush nie zostawia pustego dnia, posiłku ani części podziału."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    recipe = await create_recipe(db_session, owner=user)
    profile = await create_member_profile(db_session, household=household)
    split = [{"member_profile_id": profile.id, "multiplier": "1.10"}]
    if failure == "profile":
        split[0]["member_profile_id"] = 999_999
    if failure == "duplicate":
        split *= 2
    payload = RecipeItemCreateRequest.model_validate(
        {
            "recipe_id": 999_999 if failure == "recipe" else recipe.id,
            "new_meal_name": "Po spacerze",
            "servings": "3.30",
            "servings_split": split,
        }
    )
    with pytest.raises(PlanValidationError):
        await PlanningService(db_session).create_recipe_item(user, DAY, payload)
    for table in (PlanDay, PlanMeal, PlanMealItem, PlanItemServing):
        assert (await db_session.execute(select(func.count()).select_from(table))).scalar_one() == 0
    # Serwis sam wycofał odmowę: późniejszy commit nie utrwala żadnego artefaktu.
    await db_session.commit()
    assert (await db_session.execute(select(func.count()).select_from(PlanDay))).scalar_one() == 0


async def test_jeden_commit_i_prawdziwe_id_nowego_dania(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cała decyzja zapisuje się raz, bez wołania commitujących create_meal/add_item."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    from unittest.mock import AsyncMock

    original = db_session.commit
    commit = AsyncMock(wraps=original)
    monkeypatch.setattr(db_session, "commit", commit)
    view, meal_id, item_id = await PlanningService(db_session).create_recipe_item(
        user, DAY, RecipeItemCreateRequest(recipe_id=recipe.id, new_meal_name="Późny obiad")
    )
    assert commit.await_count == 1
    assert view.entity is not None
    assert view.meals[0].meal.id == meal_id
    assert view.meals[0].items[0].item.id == item_id
    assert view.meals[0].meal.kcal_target is None


async def test_zamiana_zachowuje_czesciowy_i_historyczny_podzial(db_session: AsyncSession) -> None:
    """Dwie osoby po 1,1 przy trzech profilach pozostają dwiema osobami i sumą 2,2."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profiles = [
        await create_member_profile(
            db_session, household=household, name=f"Osoba {i}", is_active=i != 1
        )
        for i in range(3)
    ]
    first = await create_recipe(db_session, owner=user, name="Pierwszy")
    second = await create_recipe(db_session, owner=user, name="Drugi")
    day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=day)
    item = await create_plan_item(
        db_session, meal=meal, recipe=first, servings=Decimal("2.20"), position=4
    )
    for profile in profiles[:2]:
        await create_item_split(db_session, item=item, profile=profile, multiplier=Decimal("1.10"))
    result = await PlanningService(db_session).update_item(
        item.id, user=user, payload=ItemUpdateRequest(recipe_id=second.id)
    )
    stored = result.meals[0].items[0]
    assert (
        stored.item.id,
        stored.item.plan_meal_id,
        stored.item.position,
        stored.item.servings,
    ) == (item.id, meal.id, 4, Decimal("2.20"))
    assert stored.item.recipe_id == second.id
    assert [(row.member_profile_id, row.multiplier) for row in stored.split] == [
        (p.id, Decimal("1.10")) for p in profiles[:2]
    ]


async def test_blad_zamiany_wycofuje_takze_edytowane_porcje(db_session: AsyncSession) -> None:
    """Niepoprawny split w PATCH pozostawia poprzedni przepis, liczbę i podział."""
    user = await create_user(db_session)
    first = await create_recipe(db_session, owner=user, name="Pierwszy")
    second = await create_recipe(db_session, owner=user, name="Drugi")
    day = await create_plan_day(db_session, owner=user, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=day)
    item = await create_plan_item(db_session, meal=meal, recipe=first)
    item_id, first_id, second_id = item.id, first.id, second.id
    with pytest.raises(PlanValidationError):
        await PlanningService(db_session).update_item(
            item_id,
            user=user,
            payload=ItemUpdateRequest.model_validate(
                {
                    "recipe_id": second_id,
                    "servings": "3",
                    "servings_split": [{"member_profile_id": 999999, "multiplier": "3"}],
                }
            ),
        )
    stored = await db_session.get(PlanMealItem, item_id)
    assert stored is not None
    assert stored.recipe_id == first_id
    assert stored.servings == Decimal("1")


async def test_admin_dwa_dni_tego_samego_dnia_odpowiada_zmienionym_id(
    db_session: AsyncSession,
) -> None:
    """Jawny cudzy meal/item ID zachowuje D16 i nie zwraca własnego dnia ADMIN-a."""
    admin = await create_admin(db_session)
    owner = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=owner)
    other = await create_recipe(db_session, owner=owner, name="Zamiennik")
    own_day = await create_plan_day(db_session, owner=admin, day=DAY)
    foreign_day = await create_plan_day(db_session, owner=owner, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=foreign_day)
    service = PlanningService(db_session)
    result, meal_id, item_id = await service.create_recipe_item(
        admin, DAY, RecipeItemCreateRequest(meal_id=meal.id, recipe_id=recipe.id)
    )
    assert result.entity is not None and result.entity.id == foreign_day.id
    assert meal_id == meal.id
    updated = await service.update_item(
        item_id, user=admin, payload=ItemUpdateRequest(recipe_id=other.id)
    )
    assert updated.entity is not None and updated.entity.id == foreign_day.id
    assert updated.meals[0].items[0].item.recipe_id == other.id
    assert (await service.get_day(admin, DAY)).entity.id == own_day.id  # type: ignore[union-attr]
