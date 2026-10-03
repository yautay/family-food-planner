"""CHECK-i zakresu `global`: tylko przepisy i bez rodziny (BATCH_21, D32)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-03

Wartość `global` w `entity_scope` (rewizja `0017`, zatwierdzona w osobnej
transakcji) dostaje w bazie dwa ograniczenia:

- `recipes`: `scope <> 'global' OR household_id IS NULL` — przepis globalny nie
  należy do rodziny. Adres rodziny admina blokowałby jej usunięcie, a przy
  obniżeniu zakresu przepis wpadłby po cichu do tej rodziny,
- siedem pozostałych tabel ze scope (`plan_days`, `day_templates`,
  `week_templates`, `week_cycles`, `shopping_round_configs`,
  `shopping_generations`, `shopping_lists`): `scope <> 'global'`. Dziś wartość
  jest dla nich niemożliwa przez typ Pythona (`Scope` ma dwie wartości) i
  walidację Pydantica; CHECK czyni ją niemożliwą także dla surowego SQL-a.

Nazwy wg konwencji `ck_<tabela>_<nazwa>`. Rewizja wykonuje się na bazie z
istniejącymi wierszami bez `NOT VALID`/`VALIDATE`: żaden istniejący wiersz nie
ma `global`, więc skan tabel jest tani, a constraint od razu zwalidowany.

Rewizja MUSI być osobnym plikiem po `0017`: używa wartości `global`, która
jest użyteczna dopiero po commicie transakcji dodającej ją (patrz `0017`).
`downgrade` zdejmuje CHECK-i; wartość enuma zostaje (nie da się jej usunąć).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tabele ze scope POZA `recipes` — `global` jest dla nich niedozwolone.
NON_RECIPE_SCOPED_TABLES = (
    "plan_days",
    "day_templates",
    "week_templates",
    "week_cycles",
    "shopping_round_configs",
    "shopping_generations",
    "shopping_lists",
)


def upgrade() -> None:
    """Dołóż CHECK-i używające wartości `global` (już zatwierdzonej przez `0017`)."""
    op.create_check_constraint(
        op.f("ck_recipes_global_without_household"),
        "recipes",
        "scope <> 'global' OR household_id IS NULL",
    )
    for table in NON_RECIPE_SCOPED_TABLES:
        op.create_check_constraint(
            op.f(f"ck_{table}_scope_not_global"),
            table,
            "scope <> 'global'",
        )


def downgrade() -> None:
    """Zdejmij CHECK-i; wartość `global` w typie zostaje (patrz `0017`)."""
    for table in reversed(NON_RECIPE_SCOPED_TABLES):
        op.drop_constraint(op.f(f"ck_{table}_scope_not_global"), table, type_="check")
    op.drop_constraint(op.f("ck_recipes_global_without_household"), "recipes", type_="check")
