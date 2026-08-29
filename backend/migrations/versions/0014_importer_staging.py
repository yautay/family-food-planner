"""staging importera PDF + FK `recipes.import_job_id` (BATCH_15)

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-29

Zakres wg 03_DATABASE §9 — cztery tabele stagingu (`import_jobs`,
`staged_recipes`, `staged_ingredients`, `import_issues`) i pięć nowych typów
enumowych. Poza tym JEDNA zmiana w istniejącej tabeli: `recipes.import_job_id`
dostaje wreszcie klucz obcy, na który czekał od migracji `0006`.

Cztery decyzje warte zapisania:

1. **Typy enumowe są od razu KOMPLETNE.** `import_job_status` niesie także
   `in_review`, `approved` i `rejected`, `import_match_kind` — `fuzzy` i `ai`,
   a `import_issue_kind` wszystkie sześć rodzajów, choć BATCH_15 zapisuje tylko
   `multi_portion_suspect` i `parse_warning`. Dołożenie wartości do typu
   enumowego w PG jest tanie, ale JEJ USUNIĘCIE (czyli `downgrade` batcha B16)
   wymaga przepisania typu i wszystkich kolumn — płacimy raz, teraz.
2. **Staging kaskaduje po jobie, encje domenowe mają RESTRICT.** Usunięcie joba
   ma zabrać cały staging (kompozycja, ADR-012), ale produkt kanoniczny ani
   przepis wskazany przez wiersz stagingu nie mogą zniknąć spod ręki osoby
   w trakcie review (niezmiennik 02_DOMAIN §13.4). Liczniki referencji do listy
   „Używane w:" rejestruje `importer/service.py` (dług U16 z REVIEW R3).
3. **`recipes.import_job_id` → `SET NULL`, nie RESTRICT.** Usunięcie joba jest
   sprzątaniem PROCESU importu; przepis, który już powstał, żyje własnym życiem
   w danych aplikacji i nie ma prawa zniknąć razem z nim. Kolumna dostaje przy
   okazji indeks — B16 pyta o nią „co powstało z tego importu".
4. **Bez backfillu.** Wszystkie `recipes.import_job_id` są dziś `NULL` (importer
   nie istniał), więc nie ma czego uzupełniać, a wymyślona wartość byłaby
   kłamstwem o pochodzeniu przepisu.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typy własne tego batcha. `sa.Enum` (jak w `0012`): SQLAlchemy tworzy taki typ
#: przy pierwszym `create_table` z `checkfirst=True`, więc nie ma tu ręcznego
#: `CREATE TYPE`, którego druga tabela musiałaby unikać.
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

_NEW_ENUMS = (JOB_STATUS, RECIPE_RESOLUTION, MATCH_KIND, ISSUE_KIND, ISSUE_SEVERITY)


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
    """Tworzy cztery tabele stagingu i dopina FK w `recipes`."""
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
        *_timestamps(),
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

    # Dług z migracji `0006`: kolumna istniała bez constraintu, bo `import_jobs`
    # jeszcze nie było. Bramka dryfu modeli (REVIEW R3) wymaga, żeby model
    # `Recipe` dostał `ForeignKey` w TYM SAMYM commicie — i dostał.
    op.create_index("ix_recipes_import_job_id", "recipes", ["import_job_id"])
    op.create_foreign_key(
        op.f("fk_recipes_import_job_id_import_jobs"),
        "recipes",
        "import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Zdejmuje FK z `recipes`, kasuje tabele i — jawnie — typy enumowe."""
    op.drop_constraint(op.f("fk_recipes_import_job_id_import_jobs"), "recipes", type_="foreignkey")
    op.drop_index("ix_recipes_import_job_id", table_name="recipes")

    op.drop_table("import_issues")
    op.drop_table("staged_ingredients")
    op.drop_table("staged_recipes")
    op.drop_table("import_jobs")

    # `DROP TABLE` nie kasuje typów enumowych — bez tego ponowny `upgrade`
    # padłby na „type already exists" (test `test_downgrade_usuwa_takze_typy`).
    bind = op.get_bind()
    for enum in _NEW_ENUMS:
        enum.drop(bind, checkfirst=True)
