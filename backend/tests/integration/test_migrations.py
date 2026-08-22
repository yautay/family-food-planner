"""Infrastruktura migracji na realnej bazie (db-test).

Test procedury z 03_DATABASE §1: upgrade → downgrade → upgrade na czystej
bazie. Pusta migracja bazowa `0001` też MUSI przechodzić downgrade — bez tego
rollback wdrożenia jest teorią (ADR-002, 09_DEPLOYMENT §4).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

# Import rejestru modeli: bez niego `Base.metadata` nie zna tabel i porównanie
# ze schematem raportowałoby usunięcie wszystkiego (app/models.py, BATCH_01).
import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, normalize_database_url

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
    "shopping_round_configs",
    "shopping_generations",
    "shopping_lists",
    "shopping_list_items",
}


def test_upgrade_downgrade_upgrade_na_czystej_bazie(
    alembic_config: Config, test_database_url: str
) -> None:
    """Pełny cykl migracji przechodzi i kończy się na jednej, właściwej głowie."""
    command.downgrade(alembic_config, "base")
    assert _current_revision(test_database_url) is None

    command.upgrade(alembic_config, "head")
    after_upgrade = _current_revision(test_database_url)
    assert after_upgrade == "0013"

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
    "shopping_round_mode",
    "shopping_generation_status",
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


#: Tabele, których migracje produkcyjne świadomie NIE tworzą — encja testowa
#: `scoped_notes` (BATCH_03) żyje wyłącznie w fixture na czas jednego testu,
#: a jej model siedzi na tym samym `Base`, więc porównanie metadanych ze
#: schematem musi ją pominąć.
DRIFT_IGNORED_TABLES = {"scoped_notes"}


def _drift_after_head(alembic_config: Config, test_database_url: str) -> list[object]:
    """Różnice między `Base.metadata` a schematem po `upgrade head`."""
    command.upgrade(alembic_config, "head")

    engine = create_engine(normalize_database_url(test_database_url))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_name": lambda name, type_, parent: (
                        type_ != "table" or name not in DRIFT_IGNORED_TABLES
                    )
                },
            )
            return [
                difference
                for difference in compare_metadata(context, Base.metadata)
                if not _touches_ignored_table(difference)
            ]
    finally:
        engine.dispose()


def _touches_ignored_table(difference: object) -> bool:
    """Czy różnica dotyczy encji testowej (krotka albo obiekt operacji)."""
    return any(name in repr(difference) for name in DRIFT_IGNORED_TABLES)


def test_modele_nie_dryfuja_od_schematu_po_migracjach(
    alembic_config: Config, test_database_url: str
) -> None:
    """Model bez `ForeignKey`, którego constraint dopina migracja, to CICHY dryf.

    Ustalenie REVIEW R3: `pantry_items.retail_product_id` przez dwa batche nie
    miało `ForeignKey` w modelu (constraint dopięła migracja `0011`), więc
    pierwszy `--autogenerate` po tamtej migracji SKASOWAŁBY ten constraint.
    `task migrations-check` tego nie widzi, bo bada wyłącznie liczbę głów —
    dlatego bramka porównuje metadane modeli ze schematem realnej bazy.
    """
    differences = _drift_after_head(alembic_config, test_database_url)

    assert differences == [], (
        "Modele rozjechały się ze schematem migracji — uzupełnij model albo "
        f"dopisz migrację: {differences}"
    )
