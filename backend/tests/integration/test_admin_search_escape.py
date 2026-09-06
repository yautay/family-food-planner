"""Wyszukiwarki ADMIN-a escapują `%` i `_` (dług U14 z R1, wykonany w BATCH_17).

Katalog produktów naprawił to w B04; `list_users` i `list_households` budowały
`ilike(f"%{q}%")` bez `autoescape` — szukanie „50%" zwracało wszystko od „50".
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.service import AccountsService
from app.modules.households.service import HouseholdsService
from tests.factories import create_household, create_user

pytestmark = pytest.mark.integration


async def test_procent_w_szukajce_kont_jest_znakiem_a_nie_wzorcem(db_session: AsyncSession) -> None:
    await create_user(db_session, email="a@example.com", display_name="Rabat 50%")
    await create_user(db_session, email="b@example.com", display_name="Rabat 500 zł")

    users, total = await AccountsService(db_session).list_users(limit=50, offset=0, query="50%")

    assert total == 1
    assert [u.display_name for u in users] == ["Rabat 50%"]


async def test_podkreslnik_w_szukajce_kont_nie_zastepuje_dowolnego_znaku(
    db_session: AsyncSession,
) -> None:
    await create_user(db_session, email="jan_k@example.com", display_name="Jan")
    await create_user(db_session, email="janek@example.com", display_name="Janek")

    users, total = await AccountsService(db_session).list_users(limit=50, offset=0, query="jan_")

    assert total == 1
    assert users[0].email == "jan_k@example.com"


async def test_procent_w_szukajce_rodzin_jest_znakiem_a_nie_wzorcem(
    db_session: AsyncSession,
) -> None:
    await create_household(db_session, name="Rodzina 100%")
    await create_household(db_session, name="Rodzina 1000")

    rows, total = await HouseholdsService(db_session).list_households(
        limit=50, offset=0, query="100%"
    )

    assert total == 1
    assert rows[0].household.name == "Rodzina 100%"
