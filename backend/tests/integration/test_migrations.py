"""Infrastruktura migracji na realnej bazie (db-test).

Test procedury z 03_DATABASE §1: upgrade → downgrade → upgrade na czystej
bazie. Pusta migracja bazowa `0001` też MUSI przechodzić downgrade — bez tego
rollback wdrożenia jest teorią (ADR-002, 09_DEPLOYMENT §4).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.core.db import normalize_database_url

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_config(test_database_url: str) -> Config:
    """Konfiguracja Alembica wskazująca WYŁĄCZNIE na bazę testową."""
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url == test_database_url, (
        "Testy migracji kasują schemat — DATABASE_URL musi wskazywać db-test "
        f"(jest: {settings.database_url})"
    )

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def _current_revision(url: str) -> str | None:
    # psycopg 3 obsługuje ten sam URL synchronicznie — test nie potrzebuje pętli async.
    engine = create_engine(normalize_database_url(url))
    try:
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names():
                return None
            row = connection.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            return None if row is None else str(row[0])
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_na_czystej_bazie(
    alembic_config: Config, test_database_url: str
) -> None:
    """Pełny cykl migracji przechodzi i kończy się na jednej, właściwej głowie."""
    command.downgrade(alembic_config, "base")
    assert _current_revision(test_database_url) is None

    command.upgrade(alembic_config, "head")
    after_upgrade = _current_revision(test_database_url)
    assert after_upgrade == "0001"

    command.downgrade(alembic_config, "base")
    assert _current_revision(test_database_url) is None

    command.upgrade(alembic_config, "head")
    assert _current_revision(test_database_url) == after_upgrade


def test_migracja_bazowa_nie_tworzy_tabel_domenowych(
    alembic_config: Config, test_database_url: str
) -> None:
    """BATCH_01 nie wnosi schematu — poza tabelą wersji baza jest pusta."""
    command.upgrade(alembic_config, "head")

    engine = create_engine(normalize_database_url(test_database_url))
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
    finally:
        engine.dispose()

    assert tables == {"alembic_version"}, f"Nieoczekiwane tabele w bazie: {sorted(tables)}"
