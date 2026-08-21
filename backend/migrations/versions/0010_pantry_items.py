"""pantry — stan domowy produktów (BATCH_08)

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-21

Zakres wg 03_DATABASE §7 (`pantry_items`). Tabela NIE ma kolumny `scope`:
spiżarnia jest zawsze domowa (02_DOMAIN §3.1 pkt 1), a użytkownik bez rodziny
trzyma ją na sobie (`household_id IS NULL`). Dlatego nie ma tu też CHECK-a
`scope_requires_household` — nie ma czego pilnować.

Typ enumowy `amount_unit` powstał w migracji `0006` (recipes); tutaj jest
WYŁĄCZNIE reużywany przez `postgresql.ENUM(..., create_type=False)`.

`retail_product_id` celowo bez FK: tabela `retail_products` powstaje dopiero
w BATCH_09 (karta B08, Implementation Notes pkt 1). Constraint dopina batch
mergowany jako drugi — do tego czasu kolumna jest zwykłym `BIGINT NULL`,
a CHECK „produkt kanoniczny ALBO sklepowy" i tak działa.

CHECK `amount >= 0` świadomie NIE istnieje: 03_DATABASE §7 go nie definiuje,
a schemat bazy jest wiążący. Nieujemności pilnują schemat Pydantic i serwis
(karta B08, Implementation Notes pkt 3).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typ z migracji `0006` — TYLKO referencja, nigdy tworzenie ani kasowanie.
AMOUNT_UNIT = postgresql.ENUM("g", "ml", "piece", name="amount_unit", create_type=False)


def upgrade() -> None:
    """Tworzy `pantry_items` z kolumnami właścicielskimi wariantu household."""
    op.create_table(
        "pantry_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # RESTRICT na obu FK jak we wzorcu scope: konto i rodzina z danymi
        # kasują się dopiero po ich uprzątnięciu (ADR-012).
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("retail_product_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("amount_unit", AMOUNT_UNIT, nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_pantry_items_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_pantry_items_household_id_households"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            name=op.f("fk_pantry_items_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pantry_items")),
        sa.CheckConstraint(
            "product_id IS NOT NULL OR retail_product_id IS NOT NULL",
            name=op.f("ck_pantry_items_product_required"),
        ),
    )
    op.create_index("ix_pantry_items_owner_user_id", "pantry_items", ["owner_user_id"])
    op.create_index("ix_pantry_items_household_id", "pantry_items", ["household_id"])
    # Bez tego indeksu licznik referencji katalogu (409 „Używane w:") i sam
    # RESTRICT skanowałyby całą spiżarnię przy każdym usuwaniu produktu.
    op.create_index("ix_pantry_items_product_id", "pantry_items", ["product_id"])
    op.create_index("ix_pantry_items_retail_product_id", "pantry_items", ["retail_product_id"])
    # Domyślny porządek widoku 6 to data ważności (06_UIUX §4 pkt 6).
    op.create_index("ix_pantry_items_expiry_date", "pantry_items", ["expiry_date"])


def downgrade() -> None:
    """Kasuje `pantry_items`. Typ `amount_unit` zostaje — należy do `0006`."""
    op.drop_index("ix_pantry_items_expiry_date", table_name="pantry_items")
    op.drop_index("ix_pantry_items_retail_product_id", table_name="pantry_items")
    op.drop_index("ix_pantry_items_product_id", table_name="pantry_items")
    op.drop_index("ix_pantry_items_household_id", table_name="pantry_items")
    op.drop_index("ix_pantry_items_owner_user_id", table_name="pantry_items")
    op.drop_table("pantry_items")
