"""recipes — przepisy, składniki, tagi i oceny (BATCH_05)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-17

Zakres wg 03_DATABASE §5: `recipes`, `recipe_ingredients`, `tags`,
`recipe_tags`, `recipe_ratings`.

Ta migracja tworzy typ enumowy **`entity_scope`** — `recipes` to pierwsza
produkcyjna tabela ze scope (BATCH_03 dostarczył sam mechanizm). Każda kolejna
tabela ze scope (B06+) musi użyć `postgresql.ENUM(..., create_type=False)`.
To samo dotyczy **`amount_unit`** (reużyją go planning/pantry/shopping)
i `recipe_source`.

`recipes.import_job_id` jest kolumną BEZ klucza obcego: tabela `import_jobs`
powstaje dopiero w BATCH_15 i dopiero tamta migracja dopina constraint —
alternatywą byłby FK do nieistniejącej tabeli albo pusta tabela „na zapas",
a pustych struktur na zapas nie tworzymy (ADR-001).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITY_SCOPE = sa.Enum("private", "household", name="entity_scope")
RECIPE_SOURCE = sa.Enum("manual", "pdf_import", name="recipe_source")
AMOUNT_UNIT = sa.Enum("g", "ml", "piece", name="amount_unit")


def upgrade() -> None:
    """Tworzy schemat przepisów wraz z typami enumowymi i indeksem trigramowym."""
    op.create_table(
        "recipes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # Wzorzec scope (03_DATABASE §4): RESTRICT na obu FK — właściciel
        # z danymi nie znika po cichu, a SET NULL łamałby CHECK-a household.
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", ENTITY_SCOPE, nullable=False, server_default="private"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("base_servings", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prep_time_min", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("photo_path", sa.Text(), nullable=True),
        sa.Column("source", RECIPE_SOURCE, nullable=False, server_default="manual"),
        # FK dopnie migracja BATCH_15 razem z tabelą import_jobs.
        sa.Column("import_job_id", sa.BigInteger(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_recipes_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_recipes_household_id_households"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.CheckConstraint(
            "scope <> 'household' OR household_id IS NOT NULL",
            name=op.f("ck_recipes_scope_requires_household"),
        ),
        sa.CheckConstraint("base_servings >= 1", name=op.f("ck_recipes_base_servings_positive")),
        sa.CheckConstraint(
            "difficulty IS NULL OR (difficulty >= 1 AND difficulty <= 10)",
            name=op.f("ck_recipes_difficulty_range"),
        ),
    )
    op.create_index("ix_recipes_owner_user_id", "recipes", ["owner_user_id"], unique=False)
    op.create_index("ix_recipes_household_id", "recipes", ["household_id"], unique=False)
    # Wyszukiwarka `?q=` tolerująca literówki — pg_trgm istnieje od migracji 0004.
    op.create_index(
        "ix_recipes_name_trgm",
        "recipes",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("recipe_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        # To, co wpisał użytkownik („2 x łyżka") — do wyświetlania i edycji.
        sa.Column("display_qty", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column("display_unit", sa.Text(), nullable=True),
        # Ilość znormalizowana na oś produktu (ADR-005) — NOT NULL, bo zapis
        # składnika bez przeliczenia jest niemożliwy (02_DOMAIN §13.1).
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("amount_unit", AMOUNT_UNIT, nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # CASCADE: składnik jest częścią przepisu (kompozycja, ADR-012).
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_ingredients_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        # RESTRICT: produkt użyty w przepisie nie może zostać usunięty (02 §13.4).
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            name=op.f("fk_recipe_ingredients_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_ingredients")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_recipe_ingredients_amount_positive")),
    )
    op.create_index(
        "ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"], unique=False
    )
    op.create_index(
        "ix_recipe_ingredients_product_id", "recipe_ingredients", ["product_id"], unique=False
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )

    op.create_table(
        "recipe_tags",
        sa.Column("recipe_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_tags_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name=op.f("fk_recipe_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recipe_id", "tag_id", name=op.f("pk_recipe_tags")),
    )

    op.create_table(
        "recipe_ratings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("recipe_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_ratings_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recipe_ratings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_ratings")),
        sa.UniqueConstraint("recipe_id", "user_id", name="uq_recipe_ratings_recipe_id_user_id"),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5", name=op.f("ck_recipe_ratings_rating_range")
        ),
    )
    op.create_index("ix_recipe_ratings_recipe_id", "recipe_ratings", ["recipe_id"], unique=False)
    op.create_index("ix_recipe_ratings_user_id", "recipe_ratings", ["user_id"], unique=False)


def downgrade() -> None:
    """Cofa schemat przepisów razem z typami enumowymi (kolejność: dzieci → rodzic)."""
    op.drop_index("ix_recipe_ratings_user_id", table_name="recipe_ratings")
    op.drop_index("ix_recipe_ratings_recipe_id", table_name="recipe_ratings")
    op.drop_table("recipe_ratings")

    op.drop_table("recipe_tags")
    op.drop_table("tags")

    op.drop_index("ix_recipe_ingredients_product_id", table_name="recipe_ingredients")
    op.drop_index("ix_recipe_ingredients_recipe_id", table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")

    op.drop_index("ix_recipes_name_trgm", table_name="recipes")
    op.drop_index("ix_recipes_household_id", table_name="recipes")
    op.drop_index("ix_recipes_owner_user_id", table_name="recipes")
    op.drop_table("recipes")

    # DROP TABLE nie usuwa typów enumowych (lekcja z migracji 0002).
    bind = op.get_bind()
    AMOUNT_UNIT.drop(bind, checkfirst=False)
    RECIPE_SOURCE.drop(bind, checkfirst=False)
    ENTITY_SCOPE.drop(bind, checkfirst=False)
