"""Przepis `global` używany przez OBCĄ rodzinę: plan, szablon, cykl i lista zakupów (D32).

Odczyty (`portion_values`, `ingredient_amounts`) nie filtrują scope, a walidacje
zapisu (`_assert_recipe_available`, `_assert_references_alive`) biorą widoczność
z `ScopedQuery(Recipe, allow_global=True)` — ten plik dowodzi, że całość zgadza
się end-to-end, a nie tylko w jednostkach.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import RecipeScope
from app.modules.catalog.models import MeasureKind, Perishability, VerificationStatus
from app.modules.catalog.units import AmountUnit
from tests.factories import (
    create_admin,
    create_category,
    create_household,
    create_ingredient,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_user,
    create_week_template,
    day_payload,
    template_meal,
    template_recipe_item,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

MONDAY = date(2030, 1, 7)
PLAN = f"{API}/plan"
TEMPLATES = f"{API}/templates"


async def _foreign_family_with_global_recipe(session: AsyncSession) -> dict[str, Any]:
    """Użytkownik OBCEJ rodziny + przepis `global` z jednym składnikiem (400 g pomidora)."""
    admin = await create_admin(session, email="admin-global@example.com")
    user = await create_user(
        session,
        email="obca-rodzina@example.com",
        household=await create_household(session, name="Obca"),
    )
    category = await create_category(session, name="Warzywa", perishability=Perishability.FRESH)
    tomato = await create_product(
        session,
        category=category,
        name="Pomidor",
        measure_kind=MeasureKind.MASS,
        kcal_100=Decimal("20.00"),
        protein_100=Decimal("1.00"),
        fat_100=Decimal("0.00"),
        carbs_100=Decimal("4.00"),
        verification_status=VerificationStatus.VERIFIED,
    )
    recipe = await create_recipe(
        session, owner=admin, name="Zupa pomidorowa", scope=RecipeScope.GLOBAL, base_servings=2
    )
    await create_ingredient(
        session, recipe=recipe, product=tomato, amount=Decimal("400"), amount_unit=AmountUnit.GRAM
    )
    return {"user": user, "recipe": recipe, "tomato": tomato}


async def test_pozycja_planu_obcej_rodziny_z_przepisem_global_liczy_wartosci(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _foreign_family_with_global_recipe(db_session)
    await login(db_client, world["user"].email)
    headers = csrf_headers(db_client)

    meal = await db_client.post(
        f"{PLAN}/days/{MONDAY.isoformat()}/meals", json={"name": "Obiad"}, headers=headers
    )
    meal_id = meal.json()["meals"][0]["id"]
    added = await db_client.post(
        f"{PLAN}/meals/{meal_id}/items",
        json={"recipe_id": world["recipe"].id, "servings": "1"},
        headers=headers,
    )

    assert added.status_code == 201
    item = added.json()["meals"][0]["items"][0]
    # 400 g / 2 porcje = 200 g x 20 kcal / 100 g = 40 kcal.
    assert Decimal(item["nutrition"]["kcal"]) == Decimal("40")
    assert item["recipe_name"] == "Zupa pomidorowa"


async def test_szablon_dnia_i_cykl_obcej_rodziny_wskazuja_przepis_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zapis szablonu z przepisem globalnym przechodzi; instancjacja i apply też."""
    world = await _foreign_family_with_global_recipe(db_session)
    recipe_id = world["recipe"].id
    await login(db_client, world["user"].email)
    headers = csrf_headers(db_client)

    day_template = await db_client.post(
        f"{TEMPLATES}/days",
        json={
            "name": "Dzień z globalnym",
            "payload": day_payload(
                meals=[template_meal(name="Obiad", items=[template_recipe_item(recipe_id)])]
            ),
        },
        headers=headers,
    )
    assert day_template.status_code == 201
    instantiated = await db_client.post(
        f"{TEMPLATES}/days/{day_template.json()['id']}/instantiate",
        json={"dates": [MONDAY.isoformat()]},
        headers=headers,
    )
    assert instantiated.status_code == 200
    assert instantiated.json()["items"][0]["meals"][0]["items"][0]["recipe_name"] == (
        "Zupa pomidorowa"
    )

    week = await create_week_template(
        db_session,
        owner=world["user"],
        name="Tydzień z globalnym",
        payload={
            "v": 1,
            "days": [
                {
                    "offset": 0,
                    "day": day_payload(
                        meals=[template_meal(name="Obiad", items=[template_recipe_item(recipe_id)])]
                    ),
                }
            ],
        },
    )
    week_monday = MONDAY + timedelta(days=7)
    cycle = await db_client.post(
        f"{API}/cycles",
        json={
            "name": "Cykl globalny",
            "template_ids": [week.id],
            "start_date": week_monday.isoformat(),
        },
        headers=headers,
    )
    assert cycle.status_code == 201
    applied = await db_client.post(
        f"{API}/cycles/{cycle.json()['id']}/apply",
        json={
            "date_from": week_monday.isoformat(),
            "date_to": (week_monday + timedelta(days=6)).isoformat(),
        },
        headers=headers,
    )
    assert applied.status_code == 200
    assert applied.json()["items"][0]["meals"][0]["items"][0]["recipe_name"] == "Zupa pomidorowa"


async def test_cudzy_prywatny_przepis_w_szablonie_nadal_odrzucony(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`allow_global` nie otwiera szablonów na przepisy PRYWATNE innych kont."""
    world = await _foreign_family_with_global_recipe(db_session)
    admin_secret = await create_recipe(
        db_session,
        owner=await create_admin(db_session, email="inny-admin@example.com"),
        name="Sekret",
    )
    await login(db_client, world["user"].email)

    response = await db_client.post(
        f"{TEMPLATES}/days",
        json={
            "name": "Z sekretem",
            "payload": day_payload(
                meals=[template_meal(name="Obiad", items=[template_recipe_item(admin_secret.id)])]
            ),
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_lista_zakupow_obcej_rodziny_zawiera_skladniki_przepisu_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _foreign_family_with_global_recipe(db_session)
    day = await create_plan_day(db_session, owner=world["user"], day=MONDAY)
    meal = await create_plan_meal(db_session, plan_day=day, name="Obiad")
    # 2 porcje x (400 g / 2 porcje) = 400 g pomidora.
    await create_plan_item(db_session, meal=meal, recipe=world["recipe"], servings=Decimal("2"))
    await login(db_client, world["user"].email)

    response = await db_client.post(
        f"{API}/shopping/generate",
        json={"date_from": MONDAY.isoformat(), "date_to": (MONDAY + timedelta(days=6)).isoformat()},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    lines = [item for round_view in response.json()["rounds"] for item in round_view["items"]]
    tomato = next(item for item in lines if item["label"] == "Pomidor")
    assert Decimal(tomato["needed_amount"]) == Decimal("400")
