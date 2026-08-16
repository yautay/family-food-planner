"""Kontrakt HTTP `/categories`: odczyt dla każdego, mutacje wyłącznie dla ADMIN-a."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Perishability
from tests.factories import create_admin, create_category, create_product, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

CATEGORIES = f"{API}/categories"


async def test_anonim_nie_widzi_slownika(db_client: AsyncClient) -> None:
    assert (await db_client.get(CATEGORIES)).status_code == 401


async def test_uzytkownik_czyta_slownik_w_kolejnosci_pozycji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kolejność kategorii to domyślna kolejność sekcji listy zakupów (02_DOMAIN §4.3)."""
    user = await create_user(db_session)
    await create_category(db_session, name="Inne", position=9)
    await create_category(db_session, name="Warzywa", position=1)
    await login(db_client, user.email)

    body = (await db_client.get(CATEGORIES)).json()

    assert [item["name"] for item in body["items"]] == ["Warzywa", "Inne"]
    assert body["total"] == 2


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", CATEGORIES, {"name": "Nowa"}),
        ("PATCH", f"{CATEGORIES}/1", {"name": "Zmieniona"}),
        ("DELETE", f"{CATEGORIES}/1", None),
    ],
)
async def test_uzytkownik_nie_zmienia_slownika(
    db_client: AsyncClient,
    db_session: AsyncSession,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    """Słownik jest wspólny dla całej instancji — zmienia go wyłącznie ADMIN."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.request(method, path, json=payload, headers=csrf_headers(db_client))

    assert response.status_code == 403


async def test_admin_dodaje_kategorie_z_trwaloscia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(
        CATEGORIES,
        json={"name": "Pieczywo", "position": 6, "perishability": "fresh"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    assert response.json()["perishability"] == Perishability.FRESH.value


async def test_duplikat_nazwy_kategorii_daje_409(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await create_category(db_session, name="Warzywa")
    await login(db_client, admin.email)

    response = await db_client.post(
        CATEGORIES, json={"name": "Warzywa"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 409


async def test_admin_zmienia_trwalosc_kategorii(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    category = await create_category(db_session, name="Mrożonki", perishability=Perishability.FRESH)
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{CATEGORIES}/{category.id}",
        json={"perishability": "durable"},
        headers=csrf_headers(db_client),
    )

    assert response.json()["perishability"] == Perishability.DURABLE.value


async def test_kategoria_z_produktami_nie_znika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """409 z listą produktów — UI pokazuje „Używane w:" (06_UIUX §3.3)."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Cebula")
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{CATEGORIES}/{category.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["used_in"] == [
        {"type": "product", "id": product.id, "name": "Cebula"}
    ]


async def test_admin_usuwa_pusta_kategorie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    category = await create_category(db_session, name="Do usunięcia")
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{CATEGORIES}/{category.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 204
    assert (await db_client.get(CATEGORIES)).json()["total"] == 0
