"""goals + planning — cele żywieniowe i plan dnia (BATCH_06)

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-17

Zakres wg 03_DATABASE §2 (`user_nutrition_goals`) i §6 (`plan_days`,
`plan_meals`, `plan_meal_items`, `plan_item_servings`).

Typy enumowe `entity_scope` i `amount_unit` powstały w migracji `0006`
(recipes) — tutaj są WYŁĄCZNIE reużywane przez `postgresql.ENUM(...,
create_type=False)`. Bez tego `CREATE TABLE` próbowałby utworzyć typ, który
już istnieje, i migracja padłaby na „type already exists".

Kaskady: dzień → posiłki → pozycje → rozkład rodzinny (kompozycja, ADR-012).
Odwołania na zewnątrz (`recipe_id`, `product_id`) mają RESTRICT — przepis
i produkt użyte w planie są chronione przed usunięciem (02_DOMAIN §13.4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typy z migracji `0006` — TYLKO referencja, nigdy tworzenie ani kasowanie.
ENTITY_SCOPE = postgresql.ENUM("private", "household", name="entity_scope", create_type=False)
AMOUNT_UNIT = postgresql.ENUM("g", "ml", "piece", name="amount_unit", create_type=False)


def upgrade() -> None:
    """Tworzy cele żywieniowe i cztery tabele planu dnia."""
    op.create_table(
        "user_nutrition_goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # CASCADE: cel bez właściciela nie znaczy nic (kompozycja konta).
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("kcal", sa.Numeric(precision=6, scale=0), nullable=False),
        sa.Column("protein_g", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("fat_g", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("carbs_g", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_nutrition_goals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_nutrition_goals")),
        sa.UniqueConstraint(
            "user_id", "valid_from", name="uq_user_nutrition_goals_user_id_valid_from"
        ),
        sa.CheckConstraint("kcal > 0", name=op.f("ck_user_nutrition_goals_kcal_positive")),
        sa.CheckConstraint(
            "(protein_g IS NULL OR protein_g >= 0) "
            "AND (fat_g IS NULL OR fat_g >= 0) "
            "AND (carbs_g IS NULL OR carbs_g >= 0)",
            name=op.f("ck_user_nutrition_goals_macros_non_negative"),
        ),
    )
    op.create_index(
        "ix_user_nutrition_goals_user_id", "user_nutrition_goals", ["user_id"], unique=False
    )

    op.create_table(
        "plan_days",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        # Wzorzec scope (03_DATABASE §4): RESTRICT na obu FK, jak w `recipes`.
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", ENTITY_SCOPE, nullable=False, server_default="private"),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_plan_days_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_plan_days_household_id_households"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_days")),
        sa.UniqueConstraint("owner_user_id", "day", name="uq_plan_days_owner_user_id_day"),
        sa.CheckConstraint(
            "scope <> 'household' OR household_id IS NOT NULL",
            name=op.f("ck_plan_days_scope_requires_household"),
        ),
    )
    op.create_index("ix_plan_days_owner_user_id", "plan_days", ["owner_user_id"], unique=False)
    op.create_index("ix_plan_days_household_id", "plan_days", ["household_id"], unique=False)
    # Zakres dat (`GET /plan/days?from=&to=`) to najczęstsze zapytanie modułu.
    op.create_index("ix_plan_days_day", "plan_days", ["day"], unique=False)

    op.create_table(
        "plan_meals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("plan_day_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kcal_target", sa.Numeric(precision=6, scale=0), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["plan_day_id"],
            ["plan_days.id"],
            name=op.f("fk_plan_meals_plan_day_id_plan_days"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_meals")),
        sa.CheckConstraint(
            "kcal_target IS NULL OR kcal_target > 0",
            name=op.f("ck_plan_meals_kcal_target_positive"),
        ),
    )
    op.create_index("ix_plan_meals_plan_day_id", "plan_meals", ["plan_day_id"], unique=False)

    op.create_table(
        "plan_meal_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("plan_meal_id", sa.BigInteger(), nullable=False),
        sa.Column("recipe_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("amount_unit", AMOUNT_UNIT, nullable=True),
        sa.Column(
            "servings", sa.Numeric(precision=6, scale=2), nullable=False, server_default="1.0"
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["plan_meal_id"],
            ["plan_meals.id"],
            name=op.f("fk_plan_meal_items_plan_meal_id_plan_meals"),
            ondelete="CASCADE",
        ),
        # RESTRICT: przepis i produkt użyte w planie są chronione (02_DOMAIN §13.4).
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_plan_meal_items_recipe_id_recipes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["canonical_products.id"],
            name=op.f("fk_plan_meal_items_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_meal_items")),
        sa.CheckConstraint(
            "(recipe_id IS NOT NULL) <> (product_id IS NOT NULL)",
            name=op.f("ck_plan_meal_items_recipe_xor_product"),
        ),
        sa.CheckConstraint(
            "(product_id IS NULL AND amount IS NULL AND amount_unit IS NULL) "
            "OR (product_id IS NOT NULL AND amount IS NOT NULL AND amount_unit IS NOT NULL)",
            name=op.f("ck_plan_meal_items_product_requires_amount"),
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0", name=op.f("ck_plan_meal_items_amount_positive")
        ),
        sa.CheckConstraint("servings > 0", name=op.f("ck_plan_meal_items_servings_positive")),
    )
    op.create_index(
        "ix_plan_meal_items_plan_meal_id", "plan_meal_items", ["plan_meal_id"], unique=False
    )
    op.create_index("ix_plan_meal_items_recipe_id", "plan_meal_items", ["recipe_id"], unique=False)
    op.create_index(
        "ix_plan_meal_items_product_id", "plan_meal_items", ["product_id"], unique=False
    )

    op.create_table(
        "plan_item_servings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("plan_meal_item_id", sa.BigInteger(), nullable=False),
        sa.Column("member_profile_id", sa.BigInteger(), nullable=False),
        sa.Column("multiplier", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["plan_meal_item_id"],
            ["plan_meal_items.id"],
            name=op.f("fk_plan_item_servings_plan_meal_item_id_plan_meal_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["member_profile_id"],
            ["member_profiles.id"],
            name=op.f("fk_plan_item_servings_member_profile_id_member_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_item_servings")),
        sa.UniqueConstraint(
            "plan_meal_item_id",
            "member_profile_id",
            name="uq_plan_item_servings_plan_meal_item_id_member_profile_id",
        ),
        sa.CheckConstraint(
            "multiplier > 0", name=op.f("ck_plan_item_servings_multiplier_positive")
        ),
    )
    op.create_index(
        "ix_plan_item_servings_plan_meal_item_id",
        "plan_item_servings",
        ["plan_meal_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_plan_item_servings_member_profile_id",
        "plan_item_servings",
        ["member_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    """Cofa plan dnia i cele (kolejność: dzieci → rodzic).

    Typów `entity_scope` i `amount_unit` NIE kasujemy — należą do migracji `0006`,
    a tabele `recipes`/`recipe_ingredients` nadal ich używają.
    """
    op.drop_index("ix_plan_item_servings_member_profile_id", table_name="plan_item_servings")
    op.drop_index("ix_plan_item_servings_plan_meal_item_id", table_name="plan_item_servings")
    op.drop_table("plan_item_servings")

    op.drop_index("ix_plan_meal_items_product_id", table_name="plan_meal_items")
    op.drop_index("ix_plan_meal_items_recipe_id", table_name="plan_meal_items")
    op.drop_index("ix_plan_meal_items_plan_meal_id", table_name="plan_meal_items")
    op.drop_table("plan_meal_items")

    op.drop_index("ix_plan_meals_plan_day_id", table_name="plan_meals")
    op.drop_table("plan_meals")

    op.drop_index("ix_plan_days_day", table_name="plan_days")
    op.drop_index("ix_plan_days_household_id", table_name="plan_days")
    op.drop_index("ix_plan_days_owner_user_id", table_name="plan_days")
    op.drop_table("plan_days")

    op.drop_index("ix_user_nutrition_goals_user_id", table_name="user_nutrition_goals")
    op.drop_table("user_nutrition_goals")
