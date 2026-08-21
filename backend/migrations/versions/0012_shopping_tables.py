"""zakupy — konfiguracja tur, generacje, listy i pozycje list (BATCH_10)

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-21

Zakres wg 03_DATABASE §8: `shopping_round_configs`, `shopping_generations`,
`shopping_lists`, `shopping_list_items`. Trzy pierwsze noszą kolumny wzorca
scope (03_DATABASE §4) razem z CHECK-iem `scope_requires_household`; pozycje
listy scope'u nie mają — dziedziczą go po liście (04_API §3 pkt 2c).

Cztery decyzje warte zapisania:

1. **Dwa nowe typy enumowe**: `shopping_round_mode` i
   `shopping_generation_status`. `entity_scope` i `amount_unit` są tu WYŁĄCZNIE
   referencją (`create_type=False`) — należą do migracji `0006` i downgrade ich
   nie kasuje.
2. **Kolumny tokenu publicznego powstają TERAZ, ale nikt ich nie wypełnia.**
   `public_token`/`token_revoked` konsumuje BATCH_11 (ADR-010); ten batch nie ma
   endpointu, który by je czytał albo wystawiał — pilnuje tego test API.
3. **`shopping_lists.store_id` ma SET NULL** (03_DATABASE §8): lista bez profilu
   sklepu jest poprawna. Fizyczne usunięcie używanego sklepu blokuje serwis
   409-ką (licznik referencji w `shopping/service.py`).
4. **CHECK-i ograniczone do tych, które wynikają z domeny** (`date_from <=
   date_to`, dodatnie okna tur, nieujemna potrzeba). Reszta reguł — jak
   w `0010`/`0011` — należy do schematów Pydantic i serwisu, bo 03_DATABASE §8
   ich nie definiuje.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typy z migracji `0006` — TYLKO referencja, nigdy tworzenie ani kasowanie.
ENTITY_SCOPE = postgresql.ENUM("private", "household", name="entity_scope", create_type=False)
AMOUNT_UNIT = postgresql.ENUM("g", "ml", "piece", name="amount_unit", create_type=False)

#: Typy własne tego batcha. `sa.Enum` (jak w `0006`), nie `postgresql.ENUM`:
#: SQLAlchemy tworzy taki typ przy pierwszym `create_table` z `checkfirst=True`,
#: więc nie ma tu ręcznego `CREATE TYPE`, którego druga tabela by powtórzyła.
ROUND_MODE = sa.Enum("all", "durable_plus_fresh_window", "fresh_only", name="shopping_round_mode")
GENERATION_STATUS = sa.Enum("preview", "final", "discarded", name="shopping_generation_status")

SCOPE_CHECK = "scope <> 'household' OR household_id IS NOT NULL"


def _scope_columns() -> list[sa.Column[object]]:
    """Kolumny wzorca scope (03_DATABASE §4) — identyczne w trzech tabelach."""
    return [
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", ENTITY_SCOPE, nullable=False, server_default="private"),
    ]


def _scope_constraints(table: str) -> list[sa.schema.SchemaItem]:
    """FK właścicielskie (RESTRICT) + CHECK spójności scope."""
    return [
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f(f"fk_{table}_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f(f"fk_{table}_household_id_households"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(SCOPE_CHECK, name=op.f(f"ck_{table}_scope_requires_household")),
    ]


def _timestamps() -> list[sa.Column[object]]:
    """`created_at`/`updated_at` — wszędzie (03_DATABASE §1)."""
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    """Tworzy tabele zakupowe razem z dwoma nowymi typami enumowymi."""
    op.create_table(
        "shopping_round_configs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        *_scope_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("shopping_weekday", sa.Integer(), nullable=True),
        sa.Column("covers_days", sa.Integer(), nullable=False),
        sa.Column("fresh_days", sa.Integer(), nullable=True),
        sa.Column("mode", ROUND_MODE, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        *_scope_constraints("shopping_round_configs"),
        sa.CheckConstraint(
            "shopping_weekday IS NULL OR (shopping_weekday >= 0 AND shopping_weekday <= 6)",
            name=op.f("ck_shopping_round_configs_shopping_weekday_in_week"),
        ),
        sa.CheckConstraint(
            "covers_days > 0", name=op.f("ck_shopping_round_configs_covers_days_positive")
        ),
        sa.CheckConstraint(
            "fresh_days IS NULL OR fresh_days > 0",
            name=op.f("ck_shopping_round_configs_fresh_days_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_round_configs")),
    )
    op.create_index(
        "ix_shopping_round_configs_owner_user_id", "shopping_round_configs", ["owner_user_id"]
    )
    op.create_index(
        "ix_shopping_round_configs_household_id", "shopping_round_configs", ["household_id"]
    )

    op.create_table(
        "shopping_generations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        *_scope_columns(),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("used_pantry", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", GENERATION_STATUS, nullable=False, server_default="preview"),
        *_timestamps(),
        *_scope_constraints("shopping_generations"),
        sa.CheckConstraint(
            "date_from <= date_to", name=op.f("ck_shopping_generations_date_range_ordered")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_generations")),
    )
    op.create_index(
        "ix_shopping_generations_owner_user_id", "shopping_generations", ["owner_user_id"]
    )
    op.create_index(
        "ix_shopping_generations_household_id", "shopping_generations", ["household_id"]
    )

    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("generation_id", sa.BigInteger(), nullable=True),
        *_scope_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("round_name", sa.Text(), nullable=True),
        sa.Column("store_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("public_token", sa.Text(), nullable=True),
        sa.Column("token_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        *_scope_constraints("shopping_lists"),
        # CASCADE: lista z generacji jest jej dzieckiem (ADR-012); lista ręczna
        # (B11) ma `generation_id IS NULL` i kaskada jej nie dotyczy.
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["shopping_generations.id"],
            name=op.f("fk_shopping_lists_generation_id_shopping_generations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_shopping_lists_store_id_stores"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_lists")),
        sa.UniqueConstraint("public_token", name=op.f("uq_shopping_lists_public_token")),
    )
    op.create_index("ix_shopping_lists_owner_user_id", "shopping_lists", ["owner_user_id"])
    op.create_index("ix_shopping_lists_household_id", "shopping_lists", ["household_id"])
    op.create_index("ix_shopping_lists_generation_id", "shopping_lists", ["generation_id"])
    op.create_index("ix_shopping_lists_store_id", "shopping_lists", ["store_id"])

    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("list_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("retail_product_id", sa.BigInteger(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("needed_amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("amount_unit", AMOUNT_UNIT, nullable=False),
        sa.Column("packages_count", sa.Integer(), nullable=True),
        sa.Column("package_size", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("leftover_amount", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("already_have", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("from_pantry_amount", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_shopping_list_items_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_shopping_list_items_category_id_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            name=op.f("fk_shopping_list_items_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retail_product_id"],
            ["retail_products.id"],
            name=op.f("fk_shopping_list_items_retail_product_id_retail_products"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "needed_amount >= 0",
            name=op.f("ck_shopping_list_items_needed_amount_not_negative"),
        ),
        sa.CheckConstraint(
            "packages_count IS NULL OR packages_count > 0",
            name=op.f("ck_shopping_list_items_packages_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_list_items")),
    )
    op.create_index("ix_shopping_list_items_list_id", "shopping_list_items", ["list_id"])
    op.create_index("ix_shopping_list_items_category_id", "shopping_list_items", ["category_id"])
    op.create_index("ix_shopping_list_items_product_id", "shopping_list_items", ["product_id"])
    op.create_index(
        "ix_shopping_list_items_retail_product_id", "shopping_list_items", ["retail_product_id"]
    )


def downgrade() -> None:
    """Kasuje tabele zakupowe i WŁASNE typy enumowe (`entity_scope` zostaje)."""
    op.drop_index("ix_shopping_list_items_retail_product_id", table_name="shopping_list_items")
    op.drop_index("ix_shopping_list_items_product_id", table_name="shopping_list_items")
    op.drop_index("ix_shopping_list_items_category_id", table_name="shopping_list_items")
    op.drop_index("ix_shopping_list_items_list_id", table_name="shopping_list_items")
    op.drop_table("shopping_list_items")

    op.drop_index("ix_shopping_lists_store_id", table_name="shopping_lists")
    op.drop_index("ix_shopping_lists_generation_id", table_name="shopping_lists")
    op.drop_index("ix_shopping_lists_household_id", table_name="shopping_lists")
    op.drop_index("ix_shopping_lists_owner_user_id", table_name="shopping_lists")
    op.drop_table("shopping_lists")

    op.drop_index("ix_shopping_generations_household_id", table_name="shopping_generations")
    op.drop_index("ix_shopping_generations_owner_user_id", table_name="shopping_generations")
    op.drop_table("shopping_generations")

    op.drop_index("ix_shopping_round_configs_household_id", table_name="shopping_round_configs")
    op.drop_index("ix_shopping_round_configs_owner_user_id", table_name="shopping_round_configs")
    op.drop_table("shopping_round_configs")

    bind = op.get_bind()
    GENERATION_STATUS.drop(bind, checkfirst=False)
    ROUND_MODE.drop(bind, checkfirst=False)
