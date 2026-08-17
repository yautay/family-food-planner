"""Seed tagów systemowych — migracja danych `0007` (03_DATABASE §1).

Wzorzec z `test_catalog_seed.py`: testujemy MIGRACJĘ, więc stan początkowy
ustawiamy alembikiem, nie fixture `db_session`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings
from app.core.db import normalize_database_url

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[3]

#: Seed z 02_DOMAIN §5 + „ulubione" (serce na karcie, 06_UIUX §4.2).
EXPECTED_TAGS = {
    "śniadanie",
    "obiad",
    "kolacja",
    "szybkie",
    "warzywne",
    "do lunchboxa",
    "do zamrożenia",
    "dzieci lubią",
    "ulubione",
}


@pytest.fixture
def alembic_config(test_database_url: str) -> Config:
    """Alembic wskazujący WYŁĄCZNIE na bazę testową."""
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url == test_database_url, (
        "Testy migracji ruszają dane — DATABASE_URL musi wskazywać db-test "
        f"(jest: {settings.database_url})"
    )
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


@pytest.fixture
def engine(test_database_url: str) -> Iterator[Engine]:
    engine = create_engine(normalize_database_url(test_database_url))
    try:
        yield engine
    finally:
        engine.dispose()


def _rerun_seed(alembic_config: Config) -> None:
    """Ponów WYŁĄCZNIE migrację danych `0007` (stamp cofa znacznik, nie dane).

    Upgrade celuje w `0007`, a nie w `head` — ta sama lekcja co w
    `test_catalog_seed._rerun_seed`: gdy nad seedem stanie migracja SCHEMATU
    (pierwsza z B06), `upgrade head` powtórzyłby ją na bazie, która ten
    schemat już ma (`DuplicateObject`). Końcowy `stamp head` przywraca
    znacznik do stanu faktycznego.
    """
    command.stamp(alembic_config, "0006")
    command.upgrade(alembic_config, "0007")
    command.stamp(alembic_config, "head")


@pytest.fixture
def seeded(alembic_config: Config, engine: Engine) -> None:
    """Czysta tabela tagów + jedno wykonanie seedu."""
    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE recipe_tags, tags RESTART IDENTITY CASCADE"))
    _rerun_seed(alembic_config)


def _tags(engine: Engine) -> dict[str, bool]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT name, is_system FROM tags")).fetchall()
    return {str(row[0]): bool(row[1]) for row in rows}


@pytest.mark.usefixtures("seeded")
def test_seed_zaklada_tagi_systemowe(engine: Engine) -> None:
    """Po migracji stoi dokładnie uzgodniony słownik, wszystko z `is_system=true`."""
    tags = _tags(engine)

    assert set(tags) == EXPECTED_TAGS
    assert all(tags.values())


@pytest.mark.usefixtures("seeded")
def test_seed_jest_idempotentny(alembic_config: Config, engine: Engine) -> None:
    """Powtórzony seed nie duplikuje tagów (ON CONFLICT DO NOTHING)."""
    before = _tags(engine)

    _rerun_seed(alembic_config)

    assert _tags(engine) == before
    with engine.connect() as connection:
        total = connection.execute(text("SELECT count(*) FROM tags")).scalar_one()
    assert total == len(EXPECTED_TAGS)


@pytest.mark.usefixtures("seeded")
def test_downgrade_seedu_oszczedza_tagi_w_uzyciu(alembic_config: Config, engine: Engine) -> None:
    """Rollback usuwa tylko NIEUŻYWANE tagi seedu (lekcja U2 z review R1)."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (email, password_hash, display_name, role, is_active)"
                " VALUES ('seed-tagi@example.com', 'hash', 'Test', 'user', true)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO recipes (owner_user_id, scope, name)"
                " SELECT id, 'private', 'Gołąbki' FROM users"
                " WHERE email = 'seed-tagi@example.com'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO recipe_tags (recipe_id, tag_id)"
                " SELECT r.id, t.id FROM recipes r, tags t"
                " WHERE r.name = 'Gołąbki' AND t.name = 'ulubione'"
            )
        )

    try:
        command.downgrade(alembic_config, "0006")

        remaining = _tags(engine)
        assert set(remaining) == {"ulubione"}
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("TRUNCATE TABLE recipe_tags, recipe_ratings, recipe_ingredients CASCADE")
            )
            connection.execute(text("DELETE FROM recipes WHERE name = 'Gołąbki'"))
            connection.execute(text("DELETE FROM users WHERE email = 'seed-tagi@example.com'"))
            connection.execute(text("TRUNCATE TABLE tags CASCADE"))
        _rerun_seed(alembic_config)

    assert set(_tags(engine)) == EXPECTED_TAGS
