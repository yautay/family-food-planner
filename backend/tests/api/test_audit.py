"""Kontrakt HTTP `GET /audit` oraz faktyczne zapisy dziennika (02_DOMAIN §12).

Wpisy weryfikujemy asercjami na treści (action / entity_type / user_id), a nie
„na oko" — dziennik bez sprawdzonej zawartości jest wart tyle, co jego brak.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_admin, create_household, create_member_profile, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

AUDIT = f"{API}/audit"
USERS = f"{API}/admin/users"
HOUSEHOLDS = f"{API}/admin/households"
NEW_PASSWORD = "nowe-haslo-2026"


async def _entries(client: AsyncClient, **params: str | int) -> list[dict[str, Any]]:
    response = await client.get(AUDIT, params=params)
    assert response.status_code == 200
    items = response.json()["items"]
    assert isinstance(items, list)
    return items


# --- macierz ról ----------------------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    assert (await db_client.get(AUDIT)).status_code == 401


async def test_zwykly_uzytkownik_dostaje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(AUDIT)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_dostaje_200_i_pusta_liste(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.get(AUDIT)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


async def test_dziennika_nie_da_sie_edytowac_ani_usunac(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Append-only: poza GET nie ma żadnej metody (karta B03 §Security)."""
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    for method in ("POST", "PATCH", "DELETE", "PUT"):
        response = await db_client.request(method, AUDIT, json={}, headers=csrf_headers(db_client))
        assert response.status_code == 405, method


# --- zapisy przy operacjach na kontach (dopięcie wsteczne do BATCH_02) ------------


async def test_utworzenie_konta_zostawia_wpis(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    utworzone = await db_client.post(
        USERS,
        json={"email": "nowy@example.com", "password": NEW_PASSWORD, "display_name": "Nowy"},
        headers=csrf_headers(db_client),
    )
    wpisy = await _entries(db_client, action="user.create")

    assert utworzone.status_code == 201
    assert len(wpisy) == 1
    assert wpisy[0]["entity_type"] == "user"
    assert wpisy[0]["entity_id"] == utworzone.json()["id"]
    assert wpisy[0]["user_id"] == admin.id
    assert wpisy[0]["payload"] == {"email": "nowy@example.com", "role": "user"}


async def test_zmiana_hasla_nie_trafia_do_payloadu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """W dzienniku jest SAM FAKT zmiany hasła — nigdy hasło ani hash (07 §8)."""
    admin = await create_admin(db_session)
    user = await create_user(db_session)
    await login(db_client, admin.email)

    await db_client.patch(
        f"{USERS}/{user.id}",
        json={"password": NEW_PASSWORD, "is_active": False},
        headers=csrf_headers(db_client),
    )
    wpisy = await _entries(db_client, action="user.update")

    payload = wpisy[0]["payload"]
    assert payload == {
        "email": user.email,
        "changed": {
            "is_active": {"before": True, "after": False},
            "password": {"changed": True},
        },
    }
    assert NEW_PASSWORD not in str(payload)


async def test_usuniecie_konta_zostawia_wpis(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    user = await create_user(db_session)
    await login(db_client, admin.email)

    await db_client.delete(f"{USERS}/{user.id}", headers=csrf_headers(db_client))
    wpisy = await _entries(db_client, action="user.delete")

    assert len(wpisy) == 1
    assert wpisy[0]["entity_id"] == user.id
    assert wpisy[0]["user_id"] == admin.id


async def test_edycja_bez_zmian_nie_zasmieca_dziennika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    user = await create_user(db_session, display_name="Anna")
    await login(db_client, admin.email)

    await db_client.patch(
        f"{USERS}/{user.id}", json={"display_name": "Anna"}, headers=csrf_headers(db_client)
    )

    assert await _entries(db_client, action="user.update") == []


# --- zapisy przy operacjach na rodzinach i profilach --------------------------------


async def test_operacje_na_rodzinie_zostawiaja_wpisy(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    anna = await create_user(db_session, email="anna@example.com")
    await login(db_client, admin.email)

    utworzona = await db_client.post(
        HOUSEHOLDS, json={"name": "Kowalscy"}, headers=csrf_headers(db_client)
    )
    household_id = utworzona.json()["id"]
    await db_client.patch(
        f"{HOUSEHOLDS}/{household_id}",
        json={"name": "Kowalscy i spółka"},
        headers=csrf_headers(db_client),
    )
    await db_client.put(
        f"{HOUSEHOLDS}/{household_id}/members",
        json={"user_ids": [anna.id]},
        headers=csrf_headers(db_client),
    )

    wpisy = await _entries(db_client, entity_type="household")
    akcje = [wpis["action"] for wpis in wpisy]

    assert akcje == [
        "household.members_update",
        "household.update",
        "household.create",
    ], "dziennik zwraca najnowsze wpisy jako pierwsze"
    assert all(wpis["user_id"] == admin.id for wpis in wpisy)
    assert all(wpis["entity_id"] == household_id for wpis in wpisy)
    members = next(wpis for wpis in wpisy if wpis["action"] == "household.members_update")
    assert members["payload"] == {"before": [], "after": [anna.id]}


async def test_edycja_profilu_zapisuje_kto_zmienil_i_co(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Edytuje każdy członek rodziny, więc dziennik musi mówić KTO (02_DOMAIN §3.1)."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    anna = await create_user(db_session, email="anna@example.com", household=household)
    profile = await create_member_profile(db_session, household=household, name="Zosia")
    await login(db_client, anna.email)
    await db_client.patch(
        f"{API}/households/my/profiles/{profile.id}",
        json={"name": "Zofia"},
        headers=csrf_headers(db_client),
    )
    await db_client.post(f"{API}/auth/logout", headers=csrf_headers(db_client))

    await login(db_client, admin.email)
    wpisy = await _entries(db_client, entity_type="member_profile")

    assert len(wpisy) == 1
    assert wpisy[0]["action"] == "member_profile.update"
    assert wpisy[0]["user_id"] == anna.id
    assert wpisy[0]["payload"]["before"]["name"] == "Zosia"
    assert wpisy[0]["payload"]["after"]["name"] == "Zofia"


async def test_nieudana_operacja_nie_zostawia_wpisu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wpis powstaje w tej samej transakcji: brak operacji ⇒ brak wpisu."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await create_user(db_session, email="czlonek@example.com", household=household)
    await login(db_client, admin.email)

    odmowa = await db_client.delete(f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client))

    assert odmowa.status_code == 409
    assert await _entries(db_client, action="household.delete") == []


# --- paginacja i filtry -------------------------------------------------------------


async def test_paginacja_i_filtry(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)
    for index in range(3):
        await db_client.post(
            HOUSEHOLDS, json={"name": f"Rodzina {index}"}, headers=csrf_headers(db_client)
        )
    await db_client.post(
        USERS,
        json={"email": "nowy@example.com", "password": NEW_PASSWORD, "display_name": "Nowy"},
        headers=csrf_headers(db_client),
    )

    strona = await db_client.get(AUDIT, params={"limit": 2, "offset": 1})
    po_userze = await db_client.get(AUDIT, params={"user_id": admin.id})
    po_encji = await db_client.get(AUDIT, params={"entity_type": "household"})

    assert strona.json()["total"] == 4
    assert len(strona.json()["items"]) == 2
    assert po_userze.json()["total"] == 4
    assert po_encji.json()["total"] == 3


async def test_limit_ponad_200_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    assert (await db_client.get(AUDIT, params={"limit": 500})).status_code == 422
