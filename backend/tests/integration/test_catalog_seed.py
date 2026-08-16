"""Seed kategorii zakupowych — migracja danych `0005` (03_DATABASE §1).

Testy pracują na alembiku, a nie na fixture `db_session`: przedmiotem badania
jest MIGRACJA, więc stan początkowy ustawiamy sami (`_reset`), zamiast polegać
na czyszczeniu tabel przez `DB_TABLES`.
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

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: Kategorie wymagane przez 01_PDF_AUDIT §5.5 i 02_DOMAIN §4.3 po decyzji D14
#: i po scaleniu „przetworów" z „puszkami i słoikami" (uzasadnienie w migracji).
EXPECTED_CATEGORIES = {
    "Warzywa": "fresh",
    "Owoce": "fresh",
    "Grzyby": "fresh",
    "Nabiał i jaja": "fresh",
    "Mięso i produkty mięsne": "fresh",
    "Pieczywo": "fresh",
    "Mrożonki": "durable",
    "Makarony, ryż i kasze": "durable",
    "Suche i strączkowe": "durable",
    "Orzechy i nasiona": "durable",
    "Przetwory, puszki i słoiki": "durable",
    "Przyprawy i zioła": "durable",
    "Tłuszcze": "durable",
    "Inne": "durable",
}


@pytest.fixture
def alembic_config(test_database_url: str) -> Config:
    """Alembic wskazujący WYŁĄCZNIE na bazę testową (jak w `test_migrations`)."""
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
    """Silnik synchroniczny — testy migracji nie potrzebują pętli async."""
    engine = create_engine(normalize_database_url(test_database_url))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def seeded(alembic_config: Config, engine: Engine) -> None:
    """Czysta tabela kategorii + jedno wykonanie seedu, niezależnie od innych testów.

    `stamp` cofa sam ZNACZNIK wersji, bez ruszania danych, więc kolejny `upgrade`
    uruchamia migrację danych na wyczyszczonej tabeli.
    """
    command.upgrade(alembic_config, "head")
    _reset(engine)
    command.stamp(alembic_config, "0004")
    command.upgrade(alembic_config, "head")


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE product_categories RESTART IDENTITY CASCADE"))


def _categories(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT name, perishability::text FROM product_categories")
        ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


@pytest.mark.usefixtures("seeded")
def test_seed_zaklada_uzgodniony_slownik_kategorii(engine: Engine) -> None:
    """Po migracji w bazie stoi dokładnie ustalony słownik z trwałościami."""
    assert _categories(engine) == EXPECTED_CATEGORIES


@pytest.mark.usefixtures("seeded")
def test_zbozowe_nie_wchodza_do_slownika(engine: Engine) -> None:
    """D14: zamiast „zbożowych" są pieczywo (fresh) i makarony-ryż-kasze (durable)."""
    categories = _categories(engine)

    assert "Zbożowe" not in categories
    assert categories["Pieczywo"] == "fresh"
    assert categories["Makarony, ryż i kasze"] == "durable"


@pytest.mark.usefixtures("seeded")
def test_seed_jest_idempotentny(alembic_config: Config, engine: Engine) -> None:
    """Powtórzony seed nie duplikuje kategorii — dokładnie tak jak powtórzone wdrożenie."""
    before = _categories(engine)

    command.stamp(alembic_config, "0004")
    command.upgrade(alembic_config, "head")

    assert _categories(engine) == before
    with engine.connect() as connection:
        total = connection.execute(text("SELECT count(*) FROM product_categories")).scalar_one()
    assert total == len(EXPECTED_CATEGORIES)


@pytest.mark.usefixtures("seeded")
def test_downgrade_seedu_usuwa_kategorie_i_da_sie_powtorzyc(
    alembic_config: Config, engine: Engine
) -> None:
    """Rollback migracji danych czyści dokładnie to, co wstawiła — i można ją powtórzyć."""
    command.downgrade(alembic_config, "0004")
    assert _categories(engine) == {}

    command.upgrade(alembic_config, "head")
    assert _categories(engine) == EXPECTED_CATEGORIES
