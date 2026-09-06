"""Kontrakt HTTP: /api/v1/health (ok/degraded, BATCH_17) i kształt błędu 404."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import health as health_module
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app

pytestmark = pytest.mark.api


def _client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_health_zwraca_status_i_wersje(db_client: AsyncClient) -> None:
    """Healthcheck compose polega na tej odpowiedzi; na zmigrowanej bazie testowej jest `ok`."""
    response = await db_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["checks"] == {"db": "ok", "migrations": "ok", "disk": "ok"}


async def test_health_nie_ujawnia_niczego_wiecej(db_client: AsyncClient) -> None:
    """Endpoint publiczny — statusy, wersja i trzy checki; zero ścieżek i hostów (07_SECURITY)."""
    body = (await db_client.get("/api/v1/health")).json()

    assert set(body) == {"status", "version", "checks"}
    assert set(body["checks"]) == {"db", "migrations", "disk"}
    assert set(body["checks"].values()) <= {"ok", "fail", "skipped"}


async def test_health_degraded_gdy_baza_niezmigrowana(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """09_DEPLOYMENT §2: kontener na starym schemacie zgłasza `degraded`, ale odpowiada 200.

    Head skryptów podstawiamy (zamiast cofać migrację na wspólnej bazie testowej):
    odczyt `alembic_version` z bazy jest prawdziwy, tylko oczekiwana rewizja inna.
    """
    monkeypatch.setattr(health_module, "expected_head", lambda: "9999")

    response = await db_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"db": "ok", "migrations": "fail", "disk": "ok"}


async def test_health_degraded_gdy_baza_nie_odpowiada(app: FastAPI) -> None:
    """Baza niedostępna → `db: fail`, migracje `skipped` (nie ma czego porównać), nadal 200."""
    engine = create_async_engine(
        "postgresql+psycopg://nikt:nic@127.0.0.1:1/brak", poolclass=NullPool
    )
    sessions = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def broken_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = broken_session
    try:
        async with _client_for(app) as client:
            response = await client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["db"] == "fail"
    assert body["checks"]["migrations"] == "skipped"


async def test_health_degraded_gdy_malo_miejsca_na_dysku(
    settings: Settings, db_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Próg z env ustawiony absurdalnie wysoko → `disk: fail`; reszta bez zmian."""
    app = create_app(settings.model_copy(update={"disk_min_free_mb": 10**9}))

    async def override() -> AsyncIterator[AsyncSession]:
        async with db_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override
    async with _client_for(app) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"db": "ok", "migrations": "ok", "disk": "fail"}


async def test_nieistniejaca_sciezka_zwraca_404_w_ksztalcie_kontraktu(client: AsyncClient) -> None:
    """04_API §1: {"error": {code, message, details}} — jeden kształt dla całego API."""
    response = await client.get("/api/v1/nope")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]
    assert body["error"]["details"] == {}


async def test_niedozwolona_metoda_tez_ma_ksztalt_kontraktu(client: AsyncClient) -> None:
    # Metoda BEZPIECZNA na endpointcie tylko-POST: gdyby użyć tu POST-a,
    # odpowiedź przechwyciłby wcześniej middleware CSRF (patrz test poniżej).
    response = await client.get("/api/v1/auth/login")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_mutacja_bez_csrf_jest_odrzucana_przed_routingiem(client: AsyncClient) -> None:
    """Middleware CSRF działa przed dopasowaniem trasy — 403 zamiast 404/405.

    Skutek uboczny jest pożądany: nieuwierzytelnione żądanie nie dowiaduje się,
    które ścieżki w ogóle istnieją (07_SECURITY §1).
    """
    response = await client.post("/api/v1/health")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_odpowiedz_niesie_identyfikator_requestu(db_client: AsyncClient) -> None:
    """Korelacja logów z odpowiedzią (07_SECURITY §8)."""
    response = await db_client.get("/api/v1/health")

    assert response.headers["X-Request-ID"]
