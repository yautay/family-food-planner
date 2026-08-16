"""Kontrakt HTTP uwierzytelniania: logowanie, sesja, CSRF, rate limit, nagłówki."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.db import get_session
from app.core.security import (
    CSRF_COOKIE_NAME,
    MAX_FAILED_LOGINS,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
)
from app.main import create_app
from app.modules.accounts.service import INVALID_CREDENTIALS
from tests.factories import TEST_PASSWORD, create_session, create_user
from tests.helpers import API, csrf_headers, login, set_cookie_header

pytestmark = pytest.mark.api


@pytest.fixture
async def prod_client(
    settings: Settings, db_sessions: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    """Klient aplikacji uruchomionej jak na produkcji (cookies z flagą Secure)."""
    app: FastAPI = create_app(settings.model_copy(update={"app_env": "prod"}))

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with db_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# --- logowanie ----------------------------------------------------------------


async def test_logowanie_ustawia_cookie_sesji_i_csrf(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cookie sesji jest HttpOnly, cookie CSRF musi być czytelne dla JS (07 §3)."""
    user = await create_user(db_session, email="anna@example.com", display_name="Anna")

    response = await login(db_client, user.email)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": user.id,
        "email": "anna@example.com",
        "display_name": "Anna",
        "role": "user",
        "ui_settings": {},
        "household": None,
    }

    session_cookie = set_cookie_header(response, SESSION_COOKIE_NAME)
    assert "HttpOnly" in session_cookie
    assert "samesite=lax" in session_cookie.lower()
    assert "path=/" in session_cookie.lower()

    csrf_cookie = set_cookie_header(response, CSRF_COOKIE_NAME)
    assert "HttpOnly" not in csrf_cookie


async def test_logowanie_nie_zwraca_hasha_hasla(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hash hasła nie opuszcza serwera w żadnej formie."""
    user = await create_user(db_session)

    response = await login(db_client, user.email)

    assert "password" not in response.text
    assert "argon2" not in response.text


async def test_zle_haslo_daje_401_z_neutralnym_komunikatem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)

    response = await login(db_client, user.email, password="zupelnie-inne-haslo")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.json()["error"]["message"] == INVALID_CREDENTIALS


async def test_nieistniejace_konto_daje_identyczna_odpowiedz(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Anty-enumeracja: nie wolno rozróżnić „nie ma konta" od „złe hasło"."""
    user = await create_user(db_session)
    istniejace = await login(db_client, user.email, password="zupelnie-inne-haslo")

    nieistniejace = await login(db_client, "nikt@example.com", password="zupelnie-inne-haslo")

    assert nieistniejace.status_code == istniejace.status_code == 401
    assert nieistniejace.json() == istniejace.json()


async def test_konto_nieaktywne_daje_401(db_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session, is_active=False)

    response = await login(db_client, user.email)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == INVALID_CREDENTIALS
    assert SESSION_COOKIE_NAME not in db_client.cookies, "nieaktywne konto nie dostaje sesji"


async def test_niepoprawny_email_to_422(db_client: AsyncClient) -> None:
    response = await db_client.post(
        f"{API}/auth/login", json={"email": "to-nie-email", "password": "cokolwiek-dluzsze"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_logowanie_w_prod_ustawia_cookies_secure(
    prod_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Na produkcji cookies muszą być Secure; w dev http://localhost nie ma TLS."""
    user = await create_user(db_session)

    response = await login(prod_client, user.email)

    assert response.status_code == 200
    assert "Secure" in set_cookie_header(response, SESSION_COOKIE_NAME)
    assert "Secure" in set_cookie_header(response, CSRF_COOKIE_NAME)


# --- sesja --------------------------------------------------------------------


async def test_me_bez_cookie_daje_401(db_client: AsyncClient) -> None:
    response = await db_client.get(f"{API}/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_z_sesja_zwraca_uzytkownika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)

    response = await db_client.get(f"{API}/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "anna@example.com"
    assert response.json()["household"] is None


async def test_przesuniecie_ttl_odswieza_takze_cookies(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Bez ponownego `Set-Cookie` przeglądarka skasowałaby sesję po 30 dniach od logowania."""
    user = await create_user(db_session)
    session = await create_session(db_session, user=user, expires_in=timedelta(days=2))
    db_client.cookies.set(SESSION_COOKIE_NAME, session.id)
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-csrf-do-odswiezenia")

    response = await db_client.get(f"{API}/auth/me")

    assert response.status_code == 200
    odswiezone = set_cookie_header(response, SESSION_COOKIE_NAME)
    assert f"{SESSION_COOKIE_NAME}={session.id}" in odswiezone, "wartość sesji bez zmian"
    assert f"max-age={int(SESSION_TTL.total_seconds())}" in odswiezone.lower()
    assert "HttpOnly" in odswiezone
    assert "token-csrf-do-odswiezenia" in set_cookie_header(response, CSRF_COOKIE_NAME)


async def test_swieza_sesja_nie_odswieza_cookies(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Bez potrzeby nie wysyłamy `Set-Cookie` przy każdym żądaniu."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(f"{API}/auth/me")

    assert response.status_code == 200
    assert response.headers.get_list("set-cookie") == []


async def test_podrobione_cookie_sesji_daje_401(db_client: AsyncClient) -> None:
    db_client.cookies.set(SESSION_COOKIE_NAME, "zmyslony-identyfikator-sesji")

    response = await db_client.get(f"{API}/auth/me")

    assert response.status_code == 401


async def test_wylogowanie_uniewaznia_sesje_natychmiast(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stare cookie po logout musi dawać 401 (ADR-003: delete row)."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    stare_cookie = db_client.cookies[SESSION_COOKIE_NAME]

    response = await db_client.post(f"{API}/auth/logout", headers=csrf_headers(db_client))

    assert response.status_code == 204
    db_client.cookies.set(SESSION_COOKIE_NAME, stare_cookie)
    assert (await db_client.get(f"{API}/auth/me")).status_code == 401


# --- CSRF ---------------------------------------------------------------------


async def test_mutacja_bez_naglowka_csrf_daje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(f"{API}/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_mutacja_ze_zlym_naglowkiem_csrf_daje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(f"{API}/auth/logout", headers={"X-CSRF-Token": "nie-ten-token"})

    assert response.status_code == 403


async def test_mutacja_z_poprawnym_csrf_przechodzi(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(f"{API}/auth/logout", headers=csrf_headers(db_client))

    assert response.status_code == 204


async def test_logowanie_jest_zwolnione_z_csrf(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Przy logowaniu nie ma jeszcze cookie CSRF — chroni rate limit (07 §2)."""
    user = await create_user(db_session)

    assert (await login(db_client, user.email)).status_code == 200


async def test_odczyt_nie_wymaga_csrf(db_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.get(f"{API}/auth/me")).status_code == 200


# --- rate limit i blokada konta ------------------------------------------------


async def test_szosta_proba_logowania_w_minucie_daje_429(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """5/min/IP na `/auth/login` (07_SECURITY §2)."""
    user = await create_user(db_session)

    statusy = [
        (await login(db_client, user.email, password="zle-haslo-2026")).status_code
        for _ in range(5)
    ]
    szosta = await login(db_client, user.email, password="zle-haslo-2026")

    assert statusy == [401] * 5
    assert szosta.status_code == 429
    assert szosta.json()["error"]["code"] == "rate_limited"
    assert "Zbyt wiele" in szosta.json()["error"]["message"]


async def test_blokada_konta_po_dziesieciu_porazkach_jest_neutralna(
    app: FastAPI, db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Limit IP wyłączony celowo — sprawdzamy DRUGI mechanizm: blokadę konta."""
    app.state.limiter.enabled = False
    user = await create_user(db_session)

    for _ in range(MAX_FAILED_LOGINS):
        assert (await login(db_client, user.email, password="zle-haslo-2026")).status_code == 401

    zablokowane = await login(db_client, user.email, password=TEST_PASSWORD)

    assert zablokowane.status_code == 401
    assert zablokowane.json()["error"]["message"] == INVALID_CREDENTIALS


# --- nagłówki bezpieczeństwa ---------------------------------------------------


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "same-origin"),
        ("X-Frame-Options", "DENY"),
        (
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'",
        ),
    ],
)
async def test_naglowki_bezpieczenstwa_w_odpowiedzi(
    db_client: AsyncClient, header: str, value: str
) -> None:
    """07_SECURITY §3 — nagłówki obecne na każdej odpowiedzi."""
    response = await db_client.get(f"{API}/health")

    assert response.headers[header] == value


async def test_naglowki_bezpieczenstwa_takze_na_odpowiedzi_bledu(
    db_client: AsyncClient,
) -> None:
    """Odrzucenie przez CSRF też musi nieść nagłówki (middleware jest na zewnątrz)."""
    response = await db_client.post(f"{API}/auth/logout")

    assert response.status_code == 403
    assert response.headers["X-Frame-Options"] == "DENY"
