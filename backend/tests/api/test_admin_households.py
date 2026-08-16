"""Kontrakt HTTP `/admin/households`: macierz ról, CRUD i skład rodziny."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    assign_to_household,
    create_admin,
    create_household,
    create_member_profile,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

HOUSEHOLDS = f"{API}/admin/households"


# --- macierz ról (08_TESTING §4) ----------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    assert (await db_client.get(HOUSEHOLDS)).status_code == 401


async def test_zwykly_uzytkownik_dostaje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zarządzanie rodzinami to wyłącznie ADMIN (02_DOMAIN §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(HOUSEHOLDS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", HOUSEHOLDS),
        ("GET", f"{HOUSEHOLDS}/1"),
        ("PATCH", f"{HOUSEHOLDS}/1"),
        ("DELETE", f"{HOUSEHOLDS}/1"),
        ("PUT", f"{HOUSEHOLDS}/1/members"),
    ],
)
async def test_wszystkie_operacje_zamkniete_dla_usera(
    db_client: AsyncClient, db_session: AsyncSession, method: str, path: str
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.request(method, path, json={}, headers=csrf_headers(db_client))

    assert response.status_code == 403


async def test_mutacja_bez_csrf_daje_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(HOUSEHOLDS, json={"name": "Kowalscy"})

    assert response.status_code == 403


# --- CRUD ----------------------------------------------------------------------


async def test_admin_tworzy_rodzine(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(
        HOUSEHOLDS, json={"name": "  Kowalscy  "}, headers=csrf_headers(db_client)
    )

    body = response.json()
    assert response.status_code == 201
    assert body["name"] == "Kowalscy"
    assert body["members"] == []
    assert body["members_count"] == 0


async def test_lista_zwraca_items_total_i_liczniki(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session, name="Kowalscy")
    await create_household(db_session, name="Nowakowie")
    await create_user(db_session, email="czlonek@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, admin.email)

    response = await db_client.get(HOUSEHOLDS, params={"limit": 50, "offset": 0})

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 2
    kowalscy = next(item for item in body["items"] if item["name"] == "Kowalscy")
    assert kowalscy["members_count"] == 1
    assert kowalscy["profiles_count"] == 1


async def test_szczegoly_zawieraja_czlonkow_i_profile(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await create_user(db_session, email="czlonek@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, admin.email)

    response = await db_client.get(f"{HOUSEHOLDS}/{household.id}")

    body = response.json()
    assert response.status_code == 200
    assert [member["email"] for member in body["members"]] == ["czlonek@example.com"]
    assert [profile["name"] for profile in body["profiles"]] == ["Ania"]


async def test_nieistniejaca_rodzina_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.get(f"{HOUSEHOLDS}/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_admin_zmienia_nazwe_rodziny(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session, name="Kowalscy")
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{HOUSEHOLDS}/{household.id}",
        json={"name": "Kowalscy i Nowakowie"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Kowalscy i Nowakowie"


async def test_pusta_nazwa_jest_odrzucana(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(HOUSEHOLDS, json={"name": ""}, headers=csrf_headers(db_client))

    assert response.status_code == 422


# --- usuwanie ------------------------------------------------------------------


async def test_usuniecie_pustej_rodziny_dziala(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 204
    assert (await db_client.get(f"{HOUSEHOLDS}/{household.id}")).status_code == 404


async def test_usuniecie_rodziny_z_czlonkami_daje_409_z_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Blokada usunięcia z czytelną listą użyć (ADR-012, 04_API §1)."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    profile = await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    body = response.json()
    assert response.status_code == 409
    assert body["error"]["code"] == "conflict"
    assert {"type": "user", "id": member.id, "name": member.display_name} in body["error"][
        "details"
    ]["used_in"]
    assert {"type": "member_profile", "id": profile.id, "name": "Ania"} in body["error"]["details"][
        "used_in"
    ]


async def test_odpiete_konto_pozwala_usunac_rodzine(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pełna ścieżka naprawy 409: odepnij konta → usuń rodzinę."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await create_user(db_session, email="czlonek@example.com", household=household)
    await login(db_client, admin.email)

    await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": []},
        headers=csrf_headers(db_client),
    )
    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 204


# --- skład rodziny --------------------------------------------------------------


async def test_przypisanie_i_odpiecie_kont(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    anna = await create_user(db_session, email="anna@example.com")
    piotr = await create_user(db_session, email="piotr@example.com")
    await login(db_client, admin.email)

    przypisanie = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [anna.id, piotr.id]},
        headers=csrf_headers(db_client),
    )
    odpiecie = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [anna.id]},
        headers=csrf_headers(db_client),
    )

    assert przypisanie.status_code == 200
    assert {member["email"] for member in przypisanie.json()["members"]} == {
        "anna@example.com",
        "piotr@example.com",
    }
    assert [member["email"] for member in odpiecie.json()["members"]] == ["anna@example.com"]


async def test_przypisanie_do_nowej_rodziny_odpina_od_poprzedniej(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Konto należy do MAKSYMALNIE jednej rodziny (ADR-006)."""
    admin = await create_admin(db_session)
    stara = await create_household(db_session, name="Kowalscy")
    nowa = await create_household(db_session, name="Nowakowie")
    anna = await create_user(db_session, email="anna@example.com", household=stara)
    await login(db_client, admin.email)

    await db_client.put(
        f"{HOUSEHOLDS}/{nowa.id}/members",
        json={"user_ids": [anna.id]},
        headers=csrf_headers(db_client),
    )

    assert (await db_client.get(f"{HOUSEHOLDS}/{stara.id}")).json()["members"] == []
    assert len((await db_client.get(f"{HOUSEHOLDS}/{nowa.id}")).json()["members"]) == 1


async def test_odpiecie_konta_nie_kasuje_profilu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Profil wisi na rodzinie, nie na koncie (karta B03 §Implementation Notes)."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    anna = await create_user(db_session, email="anna@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Ania", owner=anna)
    await login(db_client, admin.email)

    await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": []},
        headers=csrf_headers(db_client),
    )

    body = (await db_client.get(f"{HOUSEHOLDS}/{household.id}")).json()
    assert [profile["name"] for profile in body["profiles"]] == ["Ania"]


async def test_admin_moze_przypisac_do_rodziny_samego_siebie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Konto wykonujące operację siedzi już w sesji ORM — to inna ścieżka niż cudze."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [admin.id]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert [member["email"] for member in response.json()["members"]] == [admin.email]
    assert (await db_client.get(f"{API}/auth/me")).json()["household"] == {
        "id": household.id,
        "name": household.name,
    }


async def test_admin_przenosi_sam_siebie_miedzy_rodzinami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Przenosiny aktora: stara rodzina traci członka, nowa go zyskuje (ADR-006)."""
    stara = await create_household(db_session, name="Kowalscy")
    nowa = await create_household(db_session, name="Nowakowie")
    admin = await create_admin(db_session, email="admin@example.com")
    await assign_to_household(db_session, user=admin, household=stara)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{HOUSEHOLDS}/{nowa.id}/members",
        json={"user_ids": [admin.id]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert (await db_client.get(f"{HOUSEHOLDS}/{stara.id}")).json()["members"] == []
    assert [member["id"] for member in response.json()["members"]] == [admin.id]


async def test_nieistniejace_konto_w_skladzie_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [999999]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404
    assert response.json()["error"]["details"]["user_ids"] == [999999]
