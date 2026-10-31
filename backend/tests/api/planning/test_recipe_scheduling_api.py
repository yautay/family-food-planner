"""UX03 HTTP: scope/role, CSRF, walidacja i atomowy zapis przepisu."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cookies import session_cookie_name
from app.core.scope import RecipeScope, Scope
from app.modules.catalog.units import AmountUnit
from app.modules.planning.models import PlanDay, PlanMeal, PlanMealItem
from tests.factories import (
    create_admin,
    create_category,
    create_household,
    create_item_split,
    create_member_profile,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api
DAY = "2031-01-07"
DAY_DATE = date(2031, 1, 7)
PLAN = f"{API}/plan"


@pytest.mark.parametrize("scope", [Scope.PRIVATE, Scope.HOUSEHOLD])
@pytest.mark.parametrize("actor", ["owner", "member", "stranger", "admin"])
async def test_macierz_jawnego_posilku_i_zamiany_z_globalnym_przepisem(
    db_client: AsyncClient, db_session: AsyncSession, scope: Scope, actor: str
) -> None:
    """Obie operacje sprawdzają cały łańcuch scope; jawna treść ADMIN-a zachowuje D16."""
    home = await create_household(db_session)
    owner = await create_user(db_session, household=home)
    member = await create_user(db_session, email="member@example.com", household=home)
    stranger = await create_user(db_session, email="stranger@example.com")
    admin = await create_admin(db_session)
    recipe = await create_recipe(db_session, owner=admin, scope=RecipeScope.GLOBAL)
    replacement = await create_recipe(
        db_session, owner=admin, scope=RecipeScope.GLOBAL, name="Zamiennik"
    )
    day = await create_plan_day(db_session, owner=owner, day=DAY_DATE, scope=scope)
    meal = await create_plan_meal(db_session, plan_day=day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)
    user = {"owner": owner, "member": member, "stranger": stranger, "admin": admin}[actor]
    allowed = actor in {"owner", "admin"} or (actor == "member" and scope == Scope.HOUSEHOLD)
    # Dwa widoczne dni tej samej daty: nie można potwierdzić zapisu własnym dniem ADMIN-a.
    if actor == "admin":
        await create_plan_day(db_session, owner=admin, day=DAY_DATE)
    await login(db_client, user.email)
    added = await db_client.post(
        f"{PLAN}/days/{DAY}/recipe-items",
        json={"meal_id": meal.id, "recipe_id": recipe.id},
        headers=csrf_headers(db_client),
    )
    assert added.status_code == (201 if allowed else 404)
    updated = await db_client.patch(
        f"{PLAN}/items/{item.id}",
        json={"recipe_id": replacement.id},
        headers=csrf_headers(db_client),
    )
    assert updated.status_code == (200 if allowed else 404)
    if allowed:
        body = added.json()
        assert body["day"]["id"] == day.id
        assert body["meal_id"] == meal.id
        assert any(row["id"] == body["item_id"] for row in body["day"]["meals"][0]["items"])
        assert updated.json()["id"] == day.id
        assert (
            next(row for row in updated.json()["meals"][0]["items"] if row["id"] == item.id)[
                "recipe_id"
            ]
            == replacement.id
        )


async def test_bez_sesji_401_i_bez_csrf_403(
    db_client: AsyncClient, db_session: AsyncSession, settings: Settings
) -> None:
    """Nowa ścieżka i addytywny PATCH dziedziczą sesję i ochronę CSRF."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    url = f"{PLAN}/days/{DAY}/recipe-items"
    assert (
        await db_client.post(url, json={"recipe_id": 1, "new_meal_name": "Obiad"})
    ).status_code == 403
    assert (await db_client.patch(f"{PLAN}/items/1", json={"recipe_id": 2})).status_code == 403
    headers = csrf_headers(db_client)
    db_client.cookies.delete(session_cookie_name(settings))
    assert (
        await db_client.post(url, json={"recipe_id": 1, "new_meal_name": "Obiad"}, headers=headers)
    ).status_code == 401
    assert (
        await db_client.patch(f"{PLAN}/items/1", json={"recipe_id": 2}, headers=headers)
    ).status_code == 401


@pytest.mark.parametrize("failure", ["recipe", "profile", "sum", "date", "xor"])
async def test_odmowa_nie_tworzypustego_posilku(
    db_client: AsyncClient, db_session: AsyncSession, failure: str
) -> None:
    """422 przy złym przepisie/profilu/sumie/dacie/XOR nie utrwala części decyzji."""
    home = await create_household(db_session)
    owner = await create_user(db_session, household=home)
    outsider = await create_user(db_session, email="outsider@example.com")
    visible = await create_recipe(db_session, owner=owner)
    hidden = await create_recipe(db_session, owner=outsider, name="Niewidoczny")
    other_home = await create_household(db_session, name="Drugi dom")
    wrong_profile = await create_member_profile(db_session, household=other_home)
    profile = await create_member_profile(db_session, household=home)
    payload: dict[str, object] = {"new_meal_name": "Obiad", "recipe_id": visible.id}
    if failure == "recipe":
        payload["recipe_id"] = hidden.id
    if failure in {"profile", "sum"}:
        payload["servings_split"] = [
            {
                "member_profile_id": wrong_profile.id if failure == "profile" else profile.id,
                "multiplier": "2",
            }
        ]
    if failure in {"date", "xor"}:
        day = await create_plan_day(db_session, owner=owner, day=date(2031, 1, 8))
        meal = await create_plan_meal(db_session, plan_day=day)
        payload["meal_id"] = meal.id
        if failure == "date":
            del payload["new_meal_name"]
    before = (await db_session.execute(select(func.count()).select_from(PlanMeal))).scalar_one()
    await login(db_client, owner.email)
    response = await db_client.post(
        f"{PLAN}/days/{DAY}/recipe-items", json=payload, headers=csrf_headers(db_client)
    )
    assert response.status_code == 422
    assert (
        await db_session.execute(select(func.count()).select_from(PlanMeal))
    ).scalar_one() == before
    assert (
        await db_session.execute(select(PlanDay).where(PlanDay.day == DAY_DATE))
    ).scalar_one_or_none() is None


async def test_sam_przepis_zachowuje_id_kolejnosc_dwie_osoby_i_historie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zamiana nie dołącza trzeciego profilu ani nie usuwa nieaktywnego wpisu."""
    home = await create_household(db_session)
    owner = await create_user(db_session, household=home)
    profiles = [
        await create_member_profile(
            db_session, household=home, name=f"Profil {i}", is_active=i != 1
        )
        for i in range(3)
    ]
    first = await create_recipe(db_session, owner=owner)
    second = await create_recipe(db_session, owner=owner, name="Nowy")
    day = await create_plan_day(db_session, owner=owner, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=day)
    item = await create_plan_item(
        db_session, meal=meal, recipe=first, servings=Decimal("2.20"), position=3
    )
    for profile in profiles[:2]:
        await create_item_split(db_session, item=item, profile=profile, multiplier=Decimal("1.10"))
    await login(db_client, owner.email)
    response = await db_client.patch(
        f"{PLAN}/items/{item.id}", json={"recipe_id": second.id}, headers=csrf_headers(db_client)
    )
    assert response.status_code == 200
    stored = response.json()["meals"][0]["items"][0]
    assert (stored["id"], stored["position"], stored["servings"]) == (item.id, 3, "2.20")
    assert [row["member_profile_id"] for row in stored["servings_split"]] == [
        p.id for p in profiles[:2]
    ]
    assert [row["multiplier"] for row in stored["servings_split"]] == ["1.10", "1.10"]


async def test_zamiana_produktu_i_null_sa_odrzucane(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Przepis nie służy do konwersji produktu luzem, a null do kasowania przepisu."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    recipe = await create_recipe(db_session, owner=user)
    day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=day)
    item = await create_plan_item(
        db_session, meal=meal, product=product, amount=Decimal("100"), amount_unit=AmountUnit.GRAM
    )
    await login(db_client, user.email)
    for recipe_id in [recipe.id, None]:
        response = await db_client.patch(
            f"{PLAN}/items/{item.id}",
            json={"recipe_id": recipe_id},
            headers=csrf_headers(db_client),
        )
        assert response.status_code == 422
    await db_session.refresh(item)
    assert item.product_id == product.id and item.recipe_id is None


async def test_admin_bez_meal_id_zapisuje_wlasny_dzien(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Data bez jawnego ID nie wybiera cudzego widocznego dnia ADMIN-a (R4)."""
    owner = await create_user(db_session)
    admin = await create_admin(db_session)
    recipe = await create_recipe(db_session, owner=admin)
    foreign = await create_plan_day(db_session, owner=owner, day=DAY_DATE)
    await login(db_client, admin.email)
    response = await db_client.post(
        f"{PLAN}/days/{DAY}/recipe-items",
        json={"recipe_id": recipe.id, "new_meal_name": "Mój obiad"},
        headers=csrf_headers(db_client),
    )
    assert response.status_code == 201
    body = response.json()["day"]
    assert body["id"] != foreign.id and body["owner_user_id"] == admin.id
    assert (
        await db_session.execute(
            select(func.count()).select_from(PlanMeal).where(PlanMeal.plan_day_id == foreign.id)
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(select(func.count()).select_from(PlanMealItem))
    ).scalar_one() == 1
