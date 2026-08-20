"""templates + cycles — szablony dnia/tygodnia i cykle tygodni (BATCH_07)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-20

Zakres wg 03_DATABASE §6: `day_templates`, `week_templates` (oba z `payload
JSONB`) i `week_cycles` (`template_ids BIGINT[]`, `start_date DATE NULL`).

Typ enumowy `entity_scope` powstał w migracji `0006` (recipes) — tutaj jest
WYŁĄCZNIE reużywany (`create_type=False`). Bez tego `CREATE TABLE` próbowałby
utworzyć typ, który już istnieje, i migracja padłaby na „type already exists";
downgrade świadomie go NIE kasuje.

Indeksy GIN na payloadach (ADR-012) są warunkiem sprawności blokady usuwania:
serwis liczy wystąpienia `recipe_id`/`product_id` wewnątrz JSONB, a bez indeksu
każdy DELETE przepisu robiłby seq scan po wszystkich szablonach. Klasa operatorów
to `jsonb_path_ops` — mniejsza i szybsza od domyślnej, ale obsługująca wyłącznie
`@>`, `@?` i `@@`, dlatego zapytania zliczające MUSZĄ używać containmentu `@>`.

Referencje do przepisów i produktów siedzą WEWNĄTRZ payloadu, więc nie ma tu FK
z RESTRICT — jedyną linią obrony jest serwis (inaczej niż w `plan_meal_items`).
To samo dotyczy `week_cycles.template_ids`: Postgres nie postawi klucza obcego na
elemencie tablicy, więc spójność pilnuje serwis (409 z nazwą cyklu w `used_in`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typ z migracji `0006` — TYLKO referencja, nigdy tworzenie ani kasowanie.
ENTITY_SCOPE = postgresql.ENUM("private", "household", name="entity_scope", create_type=False)

#: Klasa operatorów GIN dla payloadów (patrz docstring + `planning/models.py`).
PAYLOAD_GIN_OPS = "jsonb_path_ops"

#: Obie tabele szablonów mają identyczny kształt — różni je tylko nazwa i to,
#: czy payload opisuje jeden dzień, czy siedem. Pętla zamiast kopiuj-wklej.
TEMPLATE_TABLES = ("day_templates", "week_templates")


def _create_template_table(table_name: str) -> None:
    """Tabela szablonu: wzorzec scope (03_DATABASE §4) + `name` + `payload JSONB`."""
    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # Wzorzec scope: RESTRICT na obu FK, jak w `recipes` i `plan_days`.
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", ENTITY_SCOPE, nullable=False, server_default="private"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f(f"fk_{table_name}_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f(f"fk_{table_name}_household_id_households"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")),
        sa.CheckConstraint(
            "scope <> 'household' OR household_id IS NOT NULL",
            name=op.f(f"ck_{table_name}_scope_requires_household"),
        ),
    )
    op.create_index(f"ix_{table_name}_owner_user_id", table_name, ["owner_user_id"], unique=False)
    op.create_index(f"ix_{table_name}_household_id", table_name, ["household_id"], unique=False)
    # ADR-012: bez tego indeksu blokada usuwania przepisu/produktu użytego
    # w szablonie skanowałaby całą tabelę przy każdym DELETE.
    op.create_index(
        f"ix_{table_name}_payload_gin",
        table_name,
        ["payload"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"payload": PAYLOAD_GIN_OPS},
    )


def _drop_template_table(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_payload_gin", table_name=table_name)
    op.drop_index(f"ix_{table_name}_household_id", table_name=table_name)
    op.drop_index(f"ix_{table_name}_owner_user_id", table_name=table_name)
    op.drop_table(table_name)


def upgrade() -> None:
    """Tworzy szablony dnia/tygodnia (z indeksami GIN) i cykle tygodni."""
    for table_name in TEMPLATE_TABLES:
        _create_template_table(table_name)

    op.create_table(
        "week_cycles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", ENTITY_SCOPE, nullable=False, server_default="private"),
        sa.Column("name", sa.Text(), nullable=False),
        # Tablica BEZ FK (03_DATABASE §6) — spójności pilnuje serwis.
        sa.Column("template_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_week_cycles_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_week_cycles_household_id_households"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_week_cycles")),
        sa.CheckConstraint(
            "scope <> 'household' OR household_id IS NOT NULL",
            name=op.f("ck_week_cycles_scope_requires_household"),
        ),
    )
    op.create_index("ix_week_cycles_owner_user_id", "week_cycles", ["owner_user_id"], unique=False)
    op.create_index("ix_week_cycles_household_id", "week_cycles", ["household_id"], unique=False)


def downgrade() -> None:
    """Cofa cykle i szablony razem z indeksami (typu `entity_scope` nie rusza)."""
    op.drop_index("ix_week_cycles_household_id", table_name="week_cycles")
    op.drop_index("ix_week_cycles_owner_user_id", table_name="week_cycles")
    op.drop_table("week_cycles")

    for table_name in reversed(TEMPLATE_TABLES):
        _drop_template_table(table_name)
