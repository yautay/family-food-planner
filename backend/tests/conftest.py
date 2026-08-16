"""Wspólna konfiguracja testów backendu.

Poziomy (08_TESTING §1): `unit` (czyste funkcje), `integration` (baza db-test
z compose), `api` (kontrakt HTTP przez httpx AsyncClient + ASGITransport).
Uruchamiać przez `task test-unit|test-int|test-api|check` — Taskfile wstrzykuje
zmienne z `.env` (m.in. TEST_DATABASE_URL).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Środowisko testowe ustawiane PRZED importem aplikacji (config czyta env).
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-nieuzywany-do-prawdziwych-sesji")
os.environ.setdefault("APP_VERSION", "0.1.0-test")

# Testy NIGDY nie dotykają bazy deweloperskiej: DATABASE_URL na czas sesji
# testowej wskazuje db-test (downgrade base w testach migracji kasuje schemat).
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if _TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
else:
    # Testy unit/api nie łączą się z bazą — wystarczy poprawny składniowo URL.
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+psycopg://tests:tests@localhost:5432/brak-bazy-testowej"
    )

from app.core.config import Settings, get_settings  # noqa: E402  (po ustawieniu env)
from app.main import create_app  # noqa: E402


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """Windows: psycopg async nie działa na ProactorEventLoop (patrz app.core.db)."""
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


@pytest.fixture
def settings() -> Settings:
    """Ustawienia zbudowane ze środowiska testowego."""
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Aplikacja zbudowana przez app factory (bez uruchamiania serwera)."""
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Klient HTTP rozmawiający z aplikacją w pamięci (bez sieci)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """URL bazy testowej. Brak = błąd, nie pominięcie testu (08_TESTING §6)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Brak TEST_DATABASE_URL. Podnieś bazę testową (`task dev` lub "
            "`docker compose --env-file .env -f docker/compose.dev.yml up -d db-test`) "
            "i uruchamiaj testy przez `task test-int`."
        )
    return url
