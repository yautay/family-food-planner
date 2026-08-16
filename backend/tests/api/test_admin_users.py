"""Kontrakt HTTP `/admin/users`: macierz ról i zarządzanie kontami."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import UserRole
from tests.factories import TEST_PASSWORD, create_admin, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

USERS = f"{API}/admin/users"
NEW_PASSWORD = "nowe-haslo-2026"


# --- macierz ról (08_TESTING §4) ----------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    assert (await db_client.get(USERS)).status_code == 401


async def test_zwykly_uzytkownik_dostaje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """USER widzi, że endpoint istnieje, ale nie ma do niego prawa (04_API §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(USERS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_dostaje_200(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.get(USERS)

    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", USERS),
        ("GET", f"{USERS}/1"),
        ("PATCH", f"{USERS}/1"),
        ("DELETE", f"{USERS}/1"),
    ],
)
async def test_wszystkie_operacje_admina_zamkniete_dla_usera(
    db_client: AsyncClient, db_session: AsyncSession, method: str, path: str
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.request(method, path, json={}, headers=csrf_headers(db_client))

    assert response.status_code == 403


# --- lista i wyszukiwanie ------------------------------------------------------


async def test_lista_zwraca_items_i_total_z_paginacja(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kontrakt paginacji z 04_API §1: `{items, total}` + limit/offset."""
    admin = await create_admin(db_session)
    for index in range(3):
        await create_user(db_session, email=f"user{index}@example.com")
    await login(db_client, admin.email)

    response = await db_client.get(USERS, params={"limit": 2, "offset": 1})

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 4
    assert len(body["items"]) == 2
    assert "password_hash" not in body["items"][0]


async def test_lista_nie_wywraca_sie_na_nietypowym_emailu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odczyt nie waliduje adresu ponownie — inaczej starszy wiersz dawałby 500.

    `admin@local.test` przechodzi zapis, ale `EmailStr` odrzuca domeny
    specjalnego przeznaczenia; schemat odpowiedzi nie może na tym polegać.
    """
    admin = await create_admin(db_session)
    await create_user(db_session, email="stare-konto@local.test")
    await login(db_client, admin.email)

    response = await db_client.get(USERS)

    assert response.status_code == 200
    assert "stare-konto@local.test" in [item["email"] for item in response.json()["items"]]


async def test_wyszukiwanie_po_emailu_i_nazwie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await create_user(db_session, email="anna.kowalska@example.com", display_name="Anna")
    await create_user(db_session, email="piotr@example.com", display_name="Piotr")
    await login(db_client, admin.email)

    po_emailu = await db_client.get(USERS, params={"q": "kowalska"})
    po_nazwie = await db_client.get(USERS, params={"q": "Piotr"})

    assert [item["email"] for item in po_emailu.json()["items"]] == ["anna.kowalska@example.com"]
    assert [item["email"] for item in po_nazwie.json()["items"]] == ["piotr@example.com"]


async def test_limit_ponad_200_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.get(USERS, params={"limit": 500})

    assert response.status_code == 422


# --- tworzenie kont ------------------------------------------------------------


async def test_admin_tworzy_konto(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(
        USERS,
        json={
            "email": "Nowy@Example.com",
            "password": NEW_PASSWORD,
            "display_name": "Nowy",
            "role": "user",
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    assert response.json()["email"] == "nowy@example.com"
    assert response.json()["is_active"] is True


async def test_nowe_konto_moze_sie_zalogowac(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pełna pętla: ADMIN zakłada konto → użytkownik loguje się tym hasłem."""
    admin = await create_admin(db_session)
    await login(db_client, admin.email)
    await db_client.post(
        USERS,
        json={"email": "nowy@example.com", "password": NEW_PASSWORD, "display_name": "Nowy"},
        headers=csrf_headers(db_client),
    )
    await db_client.post(f"{API}/auth/logout", headers=csrf_headers(db_client))

    response = await login(db_client, "nowy@example.com", password=NEW_PASSWORD)

    assert response.status_code == 200
    assert response.json()["role"] == "user"


async def test_zajety_email_daje_409(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await create_user(db_session, email="zajety@example.com")
    await login(db_client, admin.email)

    response = await db_client.post(
        USERS,
        json={"email": "zajety@example.com", "password": NEW_PASSWORD, "display_name": "X"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_za_krotkie_haslo_daje_422(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Minimum 10 znaków (07_SECURITY §2)."""
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(
        USERS,
        json={"email": "krotkie@example.com", "password": "krotkie", "display_name": "X"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    pola = [field["field"] for field in response.json()["error"]["details"]["fields"]]
    assert "password" in pola


async def test_tworzenie_bez_csrf_daje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(
        USERS,
        json={"email": "nowy@example.com", "password": NEW_PASSWORD, "display_name": "Nowy"},
    )

    assert response.status_code == 403


# --- edycja i usuwanie ----------------------------------------------------------


async def test_nieistniejace_konto_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.get(f"{USERS}/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_admin_zmienia_role_i_aktywnosc(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    user = await create_user(db_session)
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{USERS}/{user.id}",
        json={"role": "admin", "is_active": False},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["is_active"] is False


async def test_reset_hasla_przez_admina_dziala(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    user = await create_user(db_session)
    await login(db_client, admin.email)
    await db_client.patch(
        f"{USERS}/{user.id}", json={"password": NEW_PASSWORD}, headers=csrf_headers(db_client)
    )
    await db_client.post(f"{API}/auth/logout", headers=csrf_headers(db_client))

    stare = await login(db_client, user.email, password=TEST_PASSWORD)
    nowe = await login(db_client, user.email, password=NEW_PASSWORD)

    assert stare.status_code == 401
    assert nowe.status_code == 200


async def test_admin_nie_zdegraduje_wlasnego_konta(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ochrona przed odcięciem sobie dostępu do administracji (karta B02 §6)."""
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{USERS}/{admin.id}", json={"role": "user"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_admin_nie_dezaktywuje_wlasnego_konta(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{USERS}/{admin.id}", json={"is_active": False}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 409


async def test_admin_nie_usunie_wlasnego_konta(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.delete(f"{USERS}/{admin.id}", headers=csrf_headers(db_client))

    assert response.status_code == 409


async def test_admin_moze_zmienic_wlasna_nazwe(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Blokada dotyczy roli i aktywności, nie całej edycji własnego konta."""
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{USERS}/{admin.id}", json={"display_name": "Szef"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Szef"


async def test_admin_usuwa_cudze_konto(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    user = await create_user(db_session, role=UserRole.USER)
    await login(db_client, admin.email)

    response = await db_client.delete(f"{USERS}/{user.id}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert (await db_client.get(f"{USERS}/{user.id}")).status_code == 404
