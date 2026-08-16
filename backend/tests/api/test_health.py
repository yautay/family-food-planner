"""Kontrakt HTTP: /api/v1/health i kształt błędu 404."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.api


async def test_health_zwraca_status_i_wersje(client: AsyncClient) -> None:
    """Healthcheck compose polega na tej odpowiedzi."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


async def test_health_nie_ujawnia_niczego_wiecej(client: AsyncClient) -> None:
    """Endpoint publiczny — poza statusem i wersją nic nie wychodzi (07_SECURITY)."""
    body = await client.get("/api/v1/health")

    assert set(body.json()) == {"status", "version"}


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


async def test_odpowiedz_niesie_identyfikator_requestu(client: AsyncClient) -> None:
    """Korelacja logów z odpowiedzią (07_SECURITY §8)."""
    response = await client.get("/api/v1/health")

    assert response.headers["X-Request-ID"]
