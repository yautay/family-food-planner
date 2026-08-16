"""Wspólna konfiguracja testów backendu.

Poziomy (08_TESTING §1): `unit` (czyste funkcje), `integration` (baza db-test
z compose), `api` (kontrakt HTTP przez httpx AsyncClient + ASGITransport).
Uruchamiać przez `task test-unit|test-int|test-api|check` — Taskfile wstrzykuje
zmienne z `.env` (m.in. TEST_DATABASE_URL).

Od BATCH_02 część testów `api` dotyka bazy (logowanie, konta) — korzystają
z fixture'u `db_client`, który podmienia dependency `get_session` na sesje
wpięte w bazę db-test. Fixture `client` (bez bazy) zostaje dla endpointów
publicznych typu `/health`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

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
from app.core.db import get_session, normalize_database_url  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: Tabele czyszczone między testami korzystającymi z bazy. Nowy moduł domenowy
#: dopisuje tu swoje tabele (kolejność nieistotna — TRUNCATE ... CASCADE).
DB_TABLES = (
    "audit_entries",
    "member_profiles",
    "sessions",
    "users",
    "households",
    "product_nutrient_values",
    "nutrients",
    "product_unit_weights",
    "canonical_products",
    # Kategorie też czyścimy, mimo że w normalnej bazie pochodzą z seedu migracji
    # `0005`: test ma widzieć dokładnie te dane, które sam założył. Weryfikacją
    # samego seedu zajmuje się `tests/integration/test_catalog_seed.py`, który
    # pracuje na alembiku, a nie na tym fixture.
    "product_categories",
)


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


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    """Schemat bazy testowej doprowadzony do `head` raz na sesję testową."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    # env.py bez `-x db_url` bierze DATABASE_URL, a ten wskazuje już db-test.
    command.upgrade(config, "head")
    return test_database_url


@pytest.fixture
async def db_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    """Silnik na czas jednego testu — pula nie może przeżyć pętli zdarzeń."""
    engine = create_async_engine(normalize_database_url(migrated_database), poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_sessions(db_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Fabryka sesji + czyszczenie tabel przed testem (izolacja bez współdzielonej transakcji)."""
    async with db_engine.begin() as connection:
        await connection.execute(
            text(f"TRUNCATE TABLE {', '.join(DB_TABLES)} RESTART IDENTITY CASCADE")
        )
    yield async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def db_session(db_sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Sesja dla testów integracyjnych serwisów."""
    async with db_sessions() as session:
        yield session


@pytest.fixture
async def scoped_notes_table(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> AsyncIterator[None]:
    """Tabela encji testowej `scoped_notes` na czas JEDNEGO testu.

    Nie ma jej w żadnej migracji (karta BATCH_03): `alembic upgrade head` na
    bazie produkcyjnej nie może tworzyć tabel testowych.

    `db_session` w sygnaturze nie jest ozdobą: sesja testu trzyma otwartą
    transakcję czytelnika (ACCESS SHARE) na `scoped_notes`, a `DROP TABLE`
    potrzebuje ACCESS EXCLUSIVE — bez jawnego `rollback()` przed sprzątaniem
    teardown czekałby na tę blokadę w nieskończoność.
    """
    from app.core.scope import SCOPE_ENUM
    from tests.scoped_entity import SCOPED_NOTES_TABLE as table

    async def reset(connection: AsyncConnection) -> None:
        # Gdyby jakaś sesja jednak trzymała blokadę, chcemy czytelnego błędu
        # po pięciu sekundach, a nie zawieszonego przebiegu testów.
        await connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        await connection.run_sync(table.drop, checkfirst=True)
        # DROP TABLE nie usuwa typu enumowego (lekcja z migracji 0002).
        await connection.run_sync(SCOPE_ENUM.drop, checkfirst=True)

    async with db_engine.begin() as connection:
        await reset(connection)
        await connection.run_sync(table.create)
    try:
        yield
    finally:
        await db_session.rollback()
        async with db_engine.begin() as connection:
            await reset(connection)


@pytest.fixture
async def db_client(
    app: FastAPI, db_sessions: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    """Klient HTTP aplikacji wpiętej w bazę testową (logowanie, konta)."""

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with db_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    app.dependency_overrides.clear()
