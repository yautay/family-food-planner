"""catalog — kategorie, produkty kanoniczne, jednostki i rejestr nutrientów (BATCH_04)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

Zakres wg 03_DATABASE §3: `product_categories`, `canonical_products`,
`product_unit_weights`, `nutrients`, `product_nutrient_values`. Świadomie BEZ
`stores`, `store_category_order` i `retail_products` — te tabele dokłada
BATCH_09 razem z modułem sklepów.

Rozszerzenie `pg_trgm` powstaje tutaj, bo wyszukiwarka produktów (`?q=`) ma
tolerować literówki (04_API §1) i potrzebuje indeksu GIN po `name`.

Kolumny rdzenia wartości odżywczych (`kcal_100` … `carbs_100`) są NULLOWALNE:
USER tworzy produkt inline, nie znając wartości, a ADMIN uzupełnia je później
(02_DOMAIN §4.9). Wpisywanie zer byłoby zapisem nieprawdy — patrz docstring
`app/modules/catalog/models.py` i 03_DATABASE §3.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERISHABILITY = sa.Enum("fresh", "durable", name="perishability")
MEASURE_KIND = sa.Enum("mass", "volume", "piece", name="measure_kind")
VERIFICATION_STATUS = sa.Enum("unverified", "verified", name="verification_status")


def upgrade() -> None:
    """Tworzy schemat katalogu wraz z typami enumowymi i indeksem trigramowym."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "product_categories",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("perishability", PERISHABILITY, nullable=False, server_default="durable"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_product_categories_name")),
    )

    op.create_table(
        "canonical_products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("measure_kind", MEASURE_KIND, nullable=False),
        sa.Column("piece_weight_g", sa.Numeric(precision=8, scale=2), nullable=True),
        # NUMERIC, nigdy float (ADR-008). NULL = wartość nieznana, nie zero.
        sa.Column("kcal_100", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("protein_100", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("fat_100", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("carbs_100", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("fiber_100", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("sugars_100", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("glycemic_index", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column(
            "verification_status", VERIFICATION_STATUS, nullable=False, server_default="unverified"
        ),
        sa.Column("nutrition_source", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("perishability_override", PERISHABILITY, nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # RESTRICT: kategoria z produktami nie znika po cichu (ADR-012).
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_canonical_products_category_id_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_canonical_products")),
        sa.UniqueConstraint("normalized_name", name="uq_canonical_products_normalized_name"),
        sa.CheckConstraint(
            "(measure_kind = 'piece' AND piece_weight_g IS NOT NULL AND piece_weight_g > 0)"
            " OR (measure_kind <> 'piece' AND piece_weight_g IS NULL)",
            name=op.f("ck_canonical_products_piece_weight_matches_measure_kind"),
        ),
        sa.CheckConstraint(
            "glycemic_index IS NULL OR (glycemic_index >= 0 AND glycemic_index <= 110)",
            name=op.f("ck_canonical_products_glycemic_index_range"),
        ),
        sa.CheckConstraint(
            "(kcal_100 IS NULL OR kcal_100 >= 0)"
            " AND (protein_100 IS NULL OR protein_100 >= 0)"
            " AND (fat_100 IS NULL OR fat_100 >= 0)"
            " AND (carbs_100 IS NULL OR carbs_100 >= 0)"
            " AND (fiber_100 IS NULL OR fiber_100 >= 0)"
            " AND (sugars_100 IS NULL OR sugars_100 >= 0)",
            name=op.f("ck_canonical_products_nutrition_non_negative"),
        ),
    )
    op.create_index(
        "ix_canonical_products_category_id", "canonical_products", ["category_id"], unique=False
    )
    # Wyszukiwarka tolerująca literówki: similarity po `name` (04_API §1).
    op.create_index(
        "ix_canonical_products_name_trgm",
        "canonical_products",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "product_unit_weights",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_label", sa.Text(), nullable=False),
        sa.Column("grams_per_unit", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("samples_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # CASCADE: przelicznik jest częścią produktu, nie osobnym bytem (ADR-012).
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            name=op.f("fk_product_unit_weights_product_id_canonical_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_unit_weights")),
        sa.UniqueConstraint(
            "product_id", "unit_label", name="uq_product_unit_weights_product_id_unit_label"
        ),
        sa.CheckConstraint(
            "grams_per_unit > 0", name=op.f("ck_product_unit_weights_grams_per_unit_positive")
        ),
        sa.CheckConstraint(
            "samples_count >= 1", name=op.f("ck_product_unit_weights_samples_count_positive")
        ),
    )
    op.create_index(
        "ix_product_unit_weights_product_id", "product_unit_weights", ["product_id"], unique=False
    )

    # Rejestr rozszerzeń wartości odżywczych — w MVP seedowany PUSTO (ADR-004).
    op.create_table(
        "nutrients",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_nutrients")),
    )

    op.create_table(
        "product_nutrient_values",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("nutrient_code", sa.Text(), nullable=False),
        sa.Column("amount_per_100", sa.Numeric(precision=9, scale=3), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            name=op.f("fk_product_nutrient_values_product_id_canonical_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["nutrient_code"],
            ["nutrients.code"],
            name=op.f("fk_product_nutrient_values_nutrient_code_nutrients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_nutrient_values")),
        sa.UniqueConstraint(
            "product_id",
            "nutrient_code",
            name="uq_product_nutrient_values_product_id_nutrient_code",
        ),
        sa.CheckConstraint(
            "amount_per_100 >= 0",
            name=op.f("ck_product_nutrient_values_amount_per_100_non_negative"),
        ),
    )
    op.create_index(
        "ix_product_nutrient_values_product_id",
        "product_nutrient_values",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    """Cofa cały schemat katalogu razem z typami enumowymi.

    `pg_trgm` zostaje: rozszerzenie jest własnością bazy, a nie tej migracji —
    mogą z niego korzystać inne obiekty, a `DROP EXTENSION` w rollbacku jednego
    batcha byłby efektem ubocznym poza jego zakresem.
    """
    op.drop_index("ix_product_nutrient_values_product_id", table_name="product_nutrient_values")
    op.drop_table("product_nutrient_values")
    op.drop_table("nutrients")

    op.drop_index("ix_product_unit_weights_product_id", table_name="product_unit_weights")
    op.drop_table("product_unit_weights")

    op.drop_index("ix_canonical_products_name_trgm", table_name="canonical_products")
    op.drop_index("ix_canonical_products_category_id", table_name="canonical_products")
    op.drop_table("canonical_products")
    op.drop_table("product_categories")

    # DROP TABLE nie usuwa typów enumowych (lekcja z migracji 0002).
    bind = op.get_bind()
    VERIFICATION_STATUS.drop(bind, checkfirst=False)
    MEASURE_KIND.drop(bind, checkfirst=False)
    PERISHABILITY.drop(bind, checkfirst=False)
