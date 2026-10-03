"""Zakres `global` na poziomie BAZY (BATCH_21, D32): CHECK-i z `0018` i licznik rodziny.

Pydantic i enumy zamykają `global` w kodzie; te testy dowodzą, że zamyka go także
SQL — surowy `UPDATE`/`INSERT` z pominięciem aplikacji nie wprowadzi `global` do
dnia planu ani listy zakupów i nie przypisze przepisu globalnego do rodziny.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import RecipeScope, Scope
from app.modules.recipes.service import _recipes_in_household
from tests.factories import (
    create_admin,
    create_day_template,
    create_household,
    create_plan_day,
    create_recipe,
    create_round_config,
    create_shopping_list,
    create_user,
    create_week_cycle,
    create_week_template,
)

pytestmark = pytest.mark.integration

#: Tabele ze scope POZA przepisami — `global` jest dla nich niedozwolone.
NON_RECIPE_SCOPED = (
    "plan_days",
    "day_templates",
    "week_templates",
    "week_cycles",
    "shopping_round_configs",
    "shopping_generations",
    "shopping_lists",
)


async def test_checki_zakresu_global_istnieja_na_wszystkich_osmiu_tabelach(
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.execute(
            text("SELECT conname FROM pg_constraint WHERE contype = 'c' AND conname LIKE 'ck_%'")
        )
    ).scalars()
    names = set(rows)

    assert "ck_recipes_global_without_household" in names
    for table in NON_RECIPE_SCOPED:
        assert f"ck_{table}_scope_not_global" in names, table


async def test_global_poza_przepisami_jest_niemozliwy_takze_dla_sqla(
    db_session: AsyncSession,
) -> None:
    """Surowy `UPDATE ... SET scope='global'` na każdej tabeli, którą da się zasiać fabryką."""
    owner = await create_user(db_session, email="sql@example.com")
    template = await create_week_template(db_session, owner=owner)
    seeded = {
        "plan_days": (await create_plan_day(db_session, owner=owner, day=date(2030, 2, 1))).id,
        "day_templates": (await create_day_template(db_session, owner=owner)).id,
        "week_templates": template.id,
        "week_cycles": (
            await create_week_cycle(db_session, owner=owner, template_ids=[template.id])
        ).id,
        "shopping_round_configs": (await create_round_config(db_session, owner=owner)).id,
        "shopping_lists": (await create_shopping_list(db_session, owner=owner)).id,
    }

    for table, row_id in seeded.items():
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(f"UPDATE {table} SET scope = 'global' WHERE id = :id"), {"id": row_id}
            )
        await db_session.rollback()


async def test_przepis_global_nie_moze_miec_rodziny(db_session: AsyncSession) -> None:
    household = await create_household(db_session, name="Rodzina")
    admin = await create_admin(db_session, email="admin-db@example.com")
    shared = await create_recipe(db_session, owner=admin, scope=RecipeScope.GLOBAL)
    assert shared.household_id is None  # `ownership_for_create` zeruje rodzinę

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("UPDATE recipes SET household_id = :hh WHERE id = :id"),
            {"hh": household.id, "id": shared.id},
        )
    await db_session.rollback()


async def test_przepis_global_nie_blokuje_usuniecia_rodziny_admina(
    db_session: AsyncSession,
) -> None:
    """`household_id = NULL`: licznik rodziny nie widzi przepisów globalnych."""
    household = await create_household(db_session, name="Rodzina admina")
    admin = await create_admin(db_session, email="admin-rodzina@example.com")
    admin.household_id = household.id
    await db_session.commit()
    await create_recipe(db_session, owner=admin, name="Globalny", scope=RecipeScope.GLOBAL)

    assert list(await _recipes_in_household(db_session, household.id)) == []

    # Kontrola: zwykły przepis rodzinny ten sam licznik ZLICZA.
    await create_recipe(db_session, owner=admin, name="Rodzinny", scope=Scope.HOUSEHOLD)
    references = list(await _recipes_in_household(db_session, household.id))
    assert [reference.name for reference in references] == ["Rodzinny"]
