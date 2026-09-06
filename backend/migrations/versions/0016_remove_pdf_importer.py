"""usunięcie stagingu importera PDF i śladów po nim w `recipes` (BATCH_20, D25)

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-06

Właściciel wycofał import PDF w całości (decyzja **D25**, ADR-016). Ze schematu
znikają: cztery tabele stagingu (`import_jobs`, `staged_recipes`,
`staged_ingredients`, `import_issues`), pięć typów enumowych z `0014` oraz
kolumny `recipes.source` i `recipes.import_job_id` razem z typem `recipe_source`
z `0006` — po usunięciu importera jedyną możliwą wartością `source` byłoby
`manual`, a `import_job_id` wskazywałby tabelę, której nie ma.

**Migracja jest DESTRUKCYJNA dla stagingu i tak ma być**: `downgrade` odtwarza
PUSTE struktury w kształcie po `0015`, ale treści jobów i rozstrzygnięć review
nie da się odzyskać (koszt przyjęty świadomie w D25). Dane domenowe wniesione
importerem — przepisy, produkty, przeliczniki jednostek — ZOSTAJĄ nietknięte:
to zwykłe encje, a nie staging. Zostaje też `product_unit_weights.source`
(wolny tekst, wpisywany również ręcznie w formularzu produktu), więc wiersze
z wartością `pdf_import` są dalej czytelne jako historia.

Kolejność w `upgrade` wymuszają zależności: najpierw FK z `recipes` (inaczej
`DROP TABLE import_jobs` pada), potem tabele od dzieci do rodzica, a typy
enumowe na końcu — `DROP TABLE` ich nie kasuje, bo powstały przez
`sa.Enum(...)` wewnątrz `create_table`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typy enumowe stagingu (`0014`) i pochodzenia przepisu (`0006`). Definicje są
#: powtórzone tutaj, bo `downgrade` musi je odtworzyć bez sięgania do modeli —
#: modeli tych encji po tym batchu w kodzie nie ma.
JOB_STATUS = sa.Enum(
    "uploaded",
    "parsed",
    "in_review",
    "approved",
    "rejected",
    "failed",
    name="import_job_status",
)
RECIPE_RESOLUTION = sa.Enum(
    "create",
    "merge_into_existing",
    "skip",
    name="staged_recipe_resolution",
)
MATCH_KIND = sa.Enum("exact", "fuzzy", "ai", "none", name="import_match_kind")
ISSUE_KIND = sa.Enum(
    "multi_portion_suspect",
    "kcal_mismatch",
    "unmapped_product",
    "unit_conflict",
    "duplicate_recipe",
    "parse_warning",
    name="import_issue_kind",
)
ISSUE_SEVERITY = sa.Enum("blocker", "warning", name="import_issue_severity")
RECIPE_SOURCE = sa.Enum("manual", "pdf_import", name="recipe_source")

_STAGING_ENUMS = (JOB_STATUS, RECIPE_RESOLUTION, MATCH_KIND, ISSUE_KIND, ISSUE_SEVERITY)

CONFIDENCE_CHECK = "ck_staged_ingredients_confidence_range"


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
    """Zdejmuje ślady importera z `recipes`, kasuje staging i jego typy."""
    bind = op.get_bind()

    op.drop_constraint(op.f("fk_recipes_import_job_id_import_jobs"), "recipes", type_="foreignkey")
    op.drop_index("ix_recipes_import_job_id", table_name="recipes")
    op.drop_column("recipes", "import_job_id")
    op.drop_column("recipes", "source")
    RECIPE_SOURCE.drop(bind, checkfirst=True)

    op.drop_table("import_issues")
    op.drop_table("staged_ingredients")
    op.drop_table("staged_recipes")
    op.drop_table("import_jobs")

    for enum in _STAGING_ENUMS:
        enum.drop(bind, checkfirst=True)


def downgrade() -> None:
    """Odtwarza PUSTE struktury w kształcie po `0015`. Treści stagingu nie ma."""
    bind = op.get_bind()

    RECIPE_SOURCE.create(bind, checkfirst=True)
    op.add_column(
        "recipes",
        sa.Column("source", RECIPE_SOURCE, nullable=False, server_default="manual"),
    )
    op.add_column("recipes", sa.Column("import_job_id", sa.BigInteger(), nullable=True))

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("status", JOB_STATUS, nullable=False, server_default="uploaded"),
        sa.Column("parse_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_import_jobs_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_jobs")),
    )
    op.create_index("ix_import_jobs_owner_user_id", "import_jobs", ["owner_user_id"])
    op.create_index("ix_import_jobs_file_sha256", "import_jobs", ["file_sha256"])

    op.create_table(
        "staged_recipes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("import_job_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("day_label", sa.Text(), nullable=False),
        sa.Column("meal_label", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("declared_servings", sa.Integer(), nullable=True),
        sa.Column("pdf_kcal", sa.Numeric(precision=7, scale=1), nullable=True),
        sa.Column("pdf_macros", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolution", RECIPE_RESOLUTION, nullable=True),
        sa.Column("target_recipe_id", sa.BigInteger(), nullable=True),
        sa.Column("resolved_servings", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["import_jobs.id"],
            name=op.f("fk_staged_recipes_import_job_id_import_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_recipe_id"],
            ["recipes.id"],
            name=op.f("fk_staged_recipes_target_recipe_id_recipes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staged_recipes")),
    )
    op.create_index("ix_staged_recipes_import_job_id", "staged_recipes", ["import_job_id"])
    op.create_index("ix_staged_recipes_target_recipe_id", "staged_recipes", ["target_recipe_id"])

    op.create_table(
        "staged_ingredients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("staged_recipe_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("raw_qty", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("raw_unit", sa.Text(), nullable=True),
        sa.Column("grams", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("suggested_product_id", sa.BigInteger(), nullable=True),
        sa.Column("match_kind", MATCH_KIND, nullable=False, server_default="none"),
        sa.Column("confirmed_product_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "create_new_product", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column(
            "from_extras_section", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f(CONFIDENCE_CHECK),
        ),
        sa.ForeignKeyConstraint(
            ["staged_recipe_id"],
            ["staged_recipes.id"],
            name=op.f("fk_staged_ingredients_staged_recipe_id_staged_recipes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_product_id"],
            ["canonical_products.id"],
            name=op.f("fk_staged_ingredients_suggested_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_product_id"],
            ["canonical_products.id"],
            name=op.f("fk_staged_ingredients_confirmed_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staged_ingredients")),
    )
    op.create_index(
        "ix_staged_ingredients_staged_recipe_id", "staged_ingredients", ["staged_recipe_id"]
    )
    op.create_index(
        "ix_staged_ingredients_suggested_product_id",
        "staged_ingredients",
        ["suggested_product_id"],
    )
    op.create_index(
        "ix_staged_ingredients_confirmed_product_id",
        "staged_ingredients",
        ["confirmed_product_id"],
    )

    op.create_table(
        "import_issues",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("import_job_id", sa.BigInteger(), nullable=False),
        sa.Column("staged_recipe_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", ISSUE_KIND, nullable=False),
        sa.Column("severity", ISSUE_SEVERITY, nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["import_jobs.id"],
            name=op.f("fk_import_issues_import_job_id_import_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["staged_recipe_id"],
            ["staged_recipes.id"],
            name=op.f("fk_import_issues_staged_recipe_id_staged_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_issues")),
    )
    op.create_index("ix_import_issues_import_job_id", "import_issues", ["import_job_id"])
    op.create_index("ix_import_issues_staged_recipe_id", "import_issues", ["staged_recipe_id"])

    op.create_index("ix_recipes_import_job_id", "recipes", ["import_job_id"])
    op.create_foreign_key(
        op.f("fk_recipes_import_job_id_import_jobs"),
        "recipes",
        "import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
