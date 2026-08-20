"""Kontrakt HTTP `/goals` i `/auth/me/ui-settings` (macierz 08_TESTING §4).

Cele nie mają scope — są ściśle prywatne, więc macierz sprowadza się do:
anonim 401 / obcy 404 / właściciel 200. ADMIN też nie dostaje tu wyjątku:
cel to ustawienie konta, a nie encja współdzielona (04_API §3 pkt 2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_admin, create_goal, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

GOALS = f"{API}/goals"
UI_SETTINGS = f"{API}/auth/me/ui-settings"

PAYLOAD: dict[str, Any] = {"valid_from": "2026-01-01", "kcal": "2000"}


# --- macierz uprawnień --------------------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Cele wymagają sesji (04_API §3 pkt 1)."""
    assert (await db_client.get(GOALS)).status_code == 401
    assert (await db_client.post(GOALS, json=PAYLOAD)).status_code in (401, 403)


async def test_mutacja_bez_csrf_to_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Double-submit działa przed routingiem — brak nagłówka to 403 (07_SECURITY §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.post(GOALS, json=PAYLOAD)).status_code == 403


async def test_cudzy_cel_to_404_takze_dla_admina(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cel innego konta jest niewidoczny; ADMIN ma do cudzych danych `/admin/*`."""
    owner = await create_user(db_session, email="owner@example.com")
    admin = await create_admin(db_session)
    goal = await create_goal(db_session, user=owner, valid_from=date(2026, 1, 1))

    await login(db_client, admin.email)
    response = await db_client.put(
        f"{GOALS}/{goal.id}", json=PAYLOAD, headers=csrf_headers(db_client)
    )

    assert response.status_code == 404


async def test_lista_pokazuje_wylacznie_wlasne_cele(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Historia jest prywatna — nie ma tu żadnego „widzę też cudze"."""
    owner = await create_user(db_session, email="owner@example.com")
    other = await create_user(db_session, email="other@example.com")
    await create_goal(db_session, user=other, valid_from=date(2026, 1, 1))

    await login(db_client, owner.email)
    body = (await db_client.get(GOALS)).json()

    assert body == {"items": [], "total": 0, "current": None}


# --- CRUD ------------------------------------------------------------------------------


async def test_cel_zapisuje_sie_i_wychodzi_jako_string_dziesietny(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Każde NUMERIC w odpowiedzi to string (ADR-008) — także cele makro."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        GOALS,
        json={"valid_from": "2026-01-01", "kcal": "2100", "protein_g": "120.5"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["kcal"] == "2100"
    assert body["protein_g"] == "120.5"
    assert body["fat_g"] is None


async def test_duplikat_daty_to_409(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """UNIQUE(user_id, valid_from) mapuje się na 409 z komunikatem po polsku."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    await db_client.post(GOALS, json=PAYLOAD, headers=csrf_headers(db_client))

    response = await db_client.post(GOALS, json=PAYLOAD, headers=csrf_headers(db_client))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_cel_niedodatni_odrzucany_walidacja(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """0 kcal nie jest celem — 422 zanim cokolwiek dotknie bazy."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        GOALS,
        json={"valid_from": "2026-01-01", "kcal": "0"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_pelny_cykl_edycji_i_usuniecia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST → PUT → DELETE na własnym celu; historia po drodze się nie gubi."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    created = (await db_client.post(GOALS, json=PAYLOAD, headers=csrf_headers(db_client))).json()

    updated = await db_client.put(
        f"{GOALS}/{created['id']}",
        json={"valid_from": "2026-02-01", "kcal": "2300", "carbs_g": "250.0"},
        headers=csrf_headers(db_client),
    )
    assert updated.status_code == 200
    assert updated.json()["valid_from"] == "2026-02-01"

    removed = await db_client.delete(f"{GOALS}/{created['id']}", headers=csrf_headers(db_client))
    assert removed.status_code == 204
    assert (await db_client.get(GOALS)).json()["total"] == 0


async def test_cel_biezacy_wskazuje_wpis_obowiazujacy_dzis(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`current` to cel z największym `valid_from <= dziś`, nie ostatni na liście."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2020, 1, 1), kcal=Decimal("1900"))
    await create_goal(db_session, user=user, valid_from=date(2099, 1, 1), kcal=Decimal("9000"))

    await login(db_client, user.email)
    body = (await db_client.get(GOALS)).json()

    assert body["total"] == 2
    assert body["current"]["kcal"] == "1900"


# --- progi statusów (D9) ------------------------------------------------------------------


async def test_progi_zapisuja_sie_w_ui_settings(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH ustawia `nutrition_thresholds`; odpowiedź to zaktualizowany `/auth/me`."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.patch(
        UI_SETTINGS,
        json={"nutrition_thresholds": {"low": 85, "high": 115}},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["ui_settings"]["nutrition_thresholds"] == {"low": 85, "high": 115}
    assert (await db_client.get(f"{API}/auth/me")).json()["ui_settings"][
        "nutrition_thresholds"
    ] == {"low": 85, "high": 115}


@pytest.mark.parametrize(
    "thresholds",
    [{"low": 110, "high": 90}, {"low": 100, "high": 100}, {"low": 0, "high": 110}],
)
async def test_progi_musza_spelniac_0_mniejsze_low_mniejsze_high(
    db_client: AsyncClient, db_session: AsyncSession, thresholds: dict[str, int]
) -> None:
    """Walidacja z karty B06: 0 < low < high, inaczej 422 z komunikatem PL."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.patch(
        UI_SETTINGS, json={"nutrition_thresholds": thresholds}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 422


async def test_patch_bez_pol_nie_kasuje_istniejacych_ustawien(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Scalanie jest płytkie i częściowe — pominięty klucz to „nie ruszaj"."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    await db_client.patch(
        UI_SETTINGS,
        json={"nutrition_thresholds": {"low": 80, "high": 120}},
        headers=csrf_headers(db_client),
    )

    response = await db_client.patch(UI_SETTINGS, json={}, headers=csrf_headers(db_client))

    assert response.json()["ui_settings"]["nutrition_thresholds"] == {"low": 80, "high": 120}


async def test_ui_settings_zmienia_tylko_wlasne_konto(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Konto bierzemy z sesji — w body nie ma `user_id` i nie da się go podstawić."""
    user = await create_user(db_session, email="user@example.com")
    other = await create_user(db_session, email="other@example.com")
    await login(db_client, user.email)

    await db_client.patch(
        UI_SETTINGS,
        json={"user_id": other.id, "nutrition_thresholds": {"low": 70, "high": 130}},
        headers=csrf_headers(db_client),
    )

    await db_session.refresh(other)
    assert other.ui_settings == {}
