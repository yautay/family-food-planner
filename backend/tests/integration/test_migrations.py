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


#: Tabele oczekiwane po `upgrade head`. Batch dodający migrację dopisuje swoje —
#: dzięki temu „przypadkowa" tabela albo zapomniany downgrade są widoczne od razu.
#: `scoped_notes` (encja testowa BATCH_03) świadomie NIE jest tu wymieniona:
#: migracje produkcyjne nie mogą tworzyć tabel testowych.
EXPECTED_TABLES = {
    "alembic_version",
    "users",
    "sessions",
    "households",
    "member_profiles",
    "audit_entries",
    "product_categories",
    "canonical_products",
    "product_unit_weights",
    "nutrients",
    "product_nutrient_values",
    "recipes",
    "recipe_ingredients",
    "tags",
    "recipe_tags",
    "recipe_ratings",
    "user_nutrition_goals",
    "plan_days",
    "plan_meals",
    "plan_meal_items",
    "plan_item_servings",
    "day_templates",
    "week_templates",
    "week_cycles",
    "pantry_items",
    "stores",
    "store_category_order",
    "retail_products",
}


def test_upgrade_downgrade_upgrade_na_czystej_bazie(
    alembic_config: Config, test_database_url: str
) -> None:
    """Pełny cykl migracji przechodzi i kończy się na jednej, właściwej głowie."""
    command.downgrade(alembic_config, "base")
    assert _current_revision(test_database_url) is None

    command.upgrade(alembic_config, "head")
    after_upgrade = _current_revision(test_database_url)
    assert after_upgrade == "0011"

    command.downgrade(alembic_config, "base")
    assert _current_revision(test_database_url) is None

    command.upgrade(alembic_config, "head")
    assert _current_revision(test_database_url) == after_upgrade


def test_schemat_po_migracjach_zawiera_dokladnie_oczekiwane_tabele(
    alembic_config: Config, test_database_url: str
) -> None:
    """Po `head` w bazie stoją wyłącznie tabele wynikające z migracji."""
    command.upgrade(alembic_config, "head")

    engine = create_engine(normalize_database_url(test_database_url))
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
    finally:
        engine.dispose()

    assert tables == EXPECTED_TABLES, f"Nieoczekiwany zestaw tabel: {sorted(tables)}"


#: Typy enumowe tworzone przez migracje. Każda migracja z enumem dopisuje tu swój.
EXPECTED_ENUM_TYPES = (
    "user_role",
    "perishability",
    "measure_kind",
    "verification_status",
    "entity_scope",
    "recipe_source",
    "amount_unit",
)


def test_downgrade_usuwa_takze_typy_enumowe(alembic_config: Config, test_database_url: str) -> None:
    """DROP TABLE nie kasuje typów enumowych — bez jawnego DROP-a ponowny upgrade pada."""
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    engine = create_engine(normalize_database_url(test_database_url))
    try:
        with engine.connect() as connection:
            typy = connection.execute(
                text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
                {"names": list(EXPECTED_ENUM_TYPES)},
            ).fetchall()
    finally:
        engine.dispose()

    assert typy == [], f"Typy enumowe przetrwały downgrade: {typy}"

    command.upgrade(alembic_config, "head")
