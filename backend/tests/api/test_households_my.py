"""Kontrakt HTTP `/households/my` i `/households/my/profiles`.

Macierz z 08_TESTING §4 w wersji dla zasobu należącego do rodziny: anonim 401,
użytkownik spoza rodziny 404 (anty-IDOR — nie potwierdzamy istnienia profilu),
członek rodziny 200.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_admin, create_household, create_member_profile, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

MY = f"{API}/households/my"
PROFILES = f"{MY}/profiles"


# --- moja rodzina ---------------------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    assert (await db_client.get(MY)).status_code == 401
    assert (await db_client.get(PROFILES)).status_code == 401


async def test_uzytkownik_bez_rodziny_dostaje_pusta_strukture(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Brak rodziny to legalny stan — 200 z `household: null`, nie 404."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(MY)

    assert response.status_code == 200
    assert response.json() == {"household": None, "members": [], "profiles": []}


async def test_czlonek_widzi_rodzine_z_czlonkami_i_profilami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    household = await create_household(db_session, name="Kowalscy")
    anna = await create_user(db_session, email="anna@example.com", household=household)
    await create_user(db_session, email="piotr@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Zosia")
    await login(db_client, anna.email)

    response = await db_client.get(MY)

    body = response.json()
    assert response.status_code == 200
    assert body["household"] == {"id": household.id, "name": "Kowalscy"}
    assert {member["email"] for member in body["members"]} == {
        "anna@example.com",
        "piotr@example.com",
    }
    assert [profile["name"] for profile in body["profiles"]] == ["Zosia"]


async def test_auth_me_zawiera_rodzine_po_przypisaniu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kontrakt `/auth/me` wypełniony (karta B03 §Context)."""
    household = await create_household(db_session, name="Kowalscy")
    user = await create_user(db_session, household=household)
    await login(db_client, user.email)

    response = await db_client.get(f"{API}/auth/me")

    assert response.status_code == 200
    assert response.json()["household"] == {"id": household.id, "name": "Kowalscy"}


# --- profile: odczyt -------------------------------------------------------------


async def test_lista_profili_widoczna_dla_czlonka(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, user.email)

    response = await db_client.get(PROFILES)

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Ania"


async def test_lista_profili_pokazuje_wylacznie_wlasna_rodzine(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    moja = await create_household(db_session, name="Kowalscy")
    obca = await create_household(db_session, name="Nowakowie")
    user = await create_user(db_session, household=moja)
    await create_member_profile(db_session, household=moja, name="Ania")
    await create_member_profile(db_session, household=obca, name="Zosia")
    await login(db_client, user.email)

    response = await db_client.get(PROFILES)

    assert [profile["name"] for profile in response.json()["items"]] == ["Ania"]


async def test_ilosci_wychodza_jako_stringi_dziesietne(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ADR-008 / 04_API §1: NUMERIC w JSON to string, nigdy float."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    await create_member_profile(
        db_session,
        household=household,
        name="Ania",
        default_multiplier=Decimal("0.80"),
        kcal_goal=Decimal("1800"),
    )
    await login(db_client, user.email)

    profile = (await db_client.get(PROFILES)).json()["items"][0]

    assert profile["default_multiplier"] == "0.80"
    assert profile["kcal_goal"] == "1800"


# --- profile: anty-IDOR ----------------------------------------------------------


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
async def test_obcy_nie_zmieni_cudzego_profilu(
    db_client: AsyncClient, db_session: AsyncSession, method: str
) -> None:
    """Cudzy profil → 404, nie 403 (07_SECURITY §4)."""
    obca = await create_household(db_session, name="Nowakowie")
    profile = await create_member_profile(db_session, household=obca, name="Zosia")
    intruz = await create_user(
        db_session,
        email="intruz@example.com",
        household=await create_household(db_session, name="Kowalscy"),
    )
    await login(db_client, intruz.email)

    response = await db_client.request(
        method,
        f"{PROFILES}/{profile.id}",
        json={"name": "Przejęte"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_uzytkownik_bez_rodziny_nie_widzi_zadnego_profilu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    obca = await create_household(db_session)
    profile = await create_member_profile(db_session, household=obca, name="Zosia")
    loner = await create_user(db_session, email="loner@example.com")
    await login(db_client, loner.email)

    response = await db_client.patch(
        f"{PROFILES}/{profile.id}", json={"name": "X"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 404
    assert (await db_client.get(PROFILES)).json() == {"items": [], "total": 0}


async def test_admin_nie_dostaje_wyjatku_na_sciezce_uzytkownika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ADMIN ma własne `/admin/*`; na `/households/my` widzi tylko swoją rodzinę."""
    obca = await create_household(db_session)
    profile = await create_member_profile(db_session, household=obca, name="Zosia")
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{PROFILES}/{profile.id}", json={"name": "X"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 404


# --- profile: CRUD ---------------------------------------------------------------


async def test_czlonek_dodaje_profil_bez_konta(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Profil dziecka — bez powiązanego konta (02_DOMAIN §3)."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    await login(db_client, user.email)

    response = await db_client.post(
        PROFILES,
        json={"name": "Zosia", "default_multiplier": "0.8", "kcal_goal": "1400"},
        headers=csrf_headers(db_client),
    )

    body = response.json()
    assert response.status_code == 201
    assert body["name"] == "Zosia"
    assert body["owner_user_id"] is None
    # Odpowiedź ma precyzję kolumny NUMERIC(4,2), a nie zapisu z żądania.
    assert body["default_multiplier"] == "0.80"
    assert body["kcal_goal"] == "1400"
    assert body["household_id"] == household.id


async def test_kazdy_czlonek_rodziny_edytuje_profil(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rodzina sobie ufa — edytuje każdy członek, audit rejestruje kto (02_DOMAIN §3.1)."""
    household = await create_household(db_session)
    await create_user(db_session, email="anna@example.com", household=household)
    piotr = await create_user(db_session, email="piotr@example.com", household=household)
    profile = await create_member_profile(db_session, household=household, name="Zosia")
    await login(db_client, piotr.email)

    response = await db_client.patch(
        f"{PROFILES}/{profile.id}",
        json={"name": "Zofia", "kcal_goal": "1600", "is_active": False},
        headers=csrf_headers(db_client),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Zofia"
    assert body["kcal_goal"] == "1600"
    assert body["is_active"] is False


async def test_pusty_cel_kcal_czysci_wartosc(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`kcal_goal: null` CZYŚCI cel — kolumna jest NULLABLE, więc to legalne życzenie."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(
        db_session, household=household, name="Zosia", kcal_goal=Decimal("1400")
    )
    await login(db_client, user.email)

    response = await db_client.patch(
        f"{PROFILES}/{profile.id}", json={"kcal_goal": None}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.json()["kcal_goal"] is None
    assert (await db_client.get(PROFILES)).json()["items"][0]["kcal_goal"] is None


async def test_pominiete_pola_zostaja_bez_zmian(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH z jednym polem nie może wyzerować pozostałych."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(
        db_session,
        household=household,
        name="Zosia",
        default_multiplier=Decimal("0.80"),
        kcal_goal=Decimal("1400"),
    )
    await login(db_client, user.email)

    response = await db_client.patch(
        f"{PROFILES}/{profile.id}", json={"name": "Zofia"}, headers=csrf_headers(db_client)
    )

    body = response.json()
    assert body["name"] == "Zofia"
    assert body["default_multiplier"] == "0.80"
    assert body["kcal_goal"] == "1400"


@pytest.mark.parametrize("pole", ["name", "default_multiplier", "is_active"])
async def test_jawny_null_w_polu_not_null_daje_422(
    db_client: AsyncClient, db_session: AsyncSession, pole: str
) -> None:
    """Kolumny NOT NULL nie przyjmują `null` — 422, nigdy 500 z bazy."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    await login(db_client, user.email)

    response = await db_client.patch(
        f"{PROFILES}/{profile.id}", json={pole: None}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 422


async def test_czlonek_usuwa_profil(db_client: AsyncClient, db_session: AsyncSession) -> None:
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    await login(db_client, user.email)

    response = await db_client.delete(f"{PROFILES}/{profile.id}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert (await db_client.get(PROFILES)).json()["total"] == 0


async def test_uzytkownik_bez_rodziny_nie_doda_profilu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nie ma do czego dodać profilu — 409 z instrukcją, nie 500."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        PROFILES, json={"name": "Zosia"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    ("payload", "pole"),
    [
        ({"name": "Zosia", "default_multiplier": "0"}, "default_multiplier"),
        ({"name": "Zosia", "default_multiplier": "-1"}, "default_multiplier"),
        ({"name": "Zosia", "default_multiplier": "1.005"}, "default_multiplier"),
        ({"name": "Zosia", "kcal_goal": "0"}, "kcal_goal"),
        ({"name": "Zosia", "kcal_goal": "-100"}, "kcal_goal"),
        ({"name": "", "default_multiplier": "1"}, "name"),
    ],
)
async def test_walidacja_profilu_odrzuca_bledne_wartosci(
    db_client: AsyncClient, db_session: AsyncSession, payload: dict[str, str], pole: str
) -> None:
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    await login(db_client, user.email)

    response = await db_client.post(PROFILES, json=payload, headers=csrf_headers(db_client))

    assert response.status_code == 422
    assert pole in [field["field"] for field in response.json()["error"]["details"]["fields"]]


async def test_mutacja_profilu_bez_csrf_daje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    await login(db_client, user.email)

    response = await db_client.post(PROFILES, json={"name": "Zosia"})

    assert response.status_code == 403
