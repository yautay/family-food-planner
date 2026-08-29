"""dwie kolumny stagingu potrzebne ekranowi review (BATCH_16)

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-29

Karta BATCH_16 zakładała „docelowo bez migracji", bo BATCH_15 utworzył pełny
schemat z kompletnymi ENUM-ami. Dwie kolumny jednak brakowały i obie są
wymuszone przez dokumenty nadrzędne, nie przez wygodę implementacji:

1. `staged_ingredients.confidence NUMERIC(3,2) NULL` — **02_DOMAIN §10 wymienia
   `confidence` jako część StagedIngredient** („propozycja mapowania na produkt
   kanoniczny + confidence"), a szkic schematu 03_DATABASE §9 go pominął.
   ADR-011 mówi to samo: „wynik AI zawsze `match_kind=ai` + confidence".
   Bez kolumny propozycja AI nie mogłaby nieść swojej pewności, a review nie
   miałby czym odróżnić trafienia „prawie pewnego" od strzału.

2. `staged_ingredients.from_extras_section BOOL NOT NULL DEFAULT false` — dług
   **U22** z BATCH_15. Sekcja `Produkty` (01_PDF_AUDIT §3.3/§7) to dodatek
   podany NA JEDNĄ PORCJĘ, podczas gdy reszta wiersza przepisu jest na CAŁOŚĆ.
   Przy zatwierdzeniu przepisu wieloporcjowego (gołąbki: 7 porcji) ilości
   z tej sekcji trzeba przemnożyć przez liczbę porcji, żeby po podzieleniu
   przez `base_servings` wróciły do gramatury z dokumentu. Bez znacznika
   ziemniaki do gołąbków skurczyłyby się z 225 g do 32 g na porcję — po cichu.

Backfill: **żaden**. `confidence` jest z definicji puste do pierwszego
uruchomienia AI. `from_extras_section` dałoby się teoretycznie odtworzyć,
ale tylko przez ponowne sparsowanie plików PDF — a joby sprzed tej migracji
i tak nie mają rozstrzygnięć review, więc wartość domyślna `false` jest dla
nich prawdziwa (nic nie skalują).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Nazwa CHECK-a zgodna z `NAMING_CONVENTION` (`ck_%(table)s_%(constraint_name)s`)
#: — model deklaruje go jako `confidence_range`, więc w bazie MUSI stać dokładnie
#: to; inaczej bramka dryfu modeli (REVIEW R3) zapaliłaby się na różnicy nazw.
CONFIDENCE_CHECK = "ck_staged_ingredients_confidence_range"


def upgrade() -> None:
    op.add_column(
        "staged_ingredients",
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "staged_ingredients",
        sa.Column(
            "from_extras_section",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Pewność jest ułamkiem z przedziału [0, 1] (ADR-011). CHECK, a nie sama
    # skala kolumny: NUMERIC(3,2) przyjąłby też 9,99.
    op.create_check_constraint(
        op.f(CONFIDENCE_CHECK),
        "staged_ingredients",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CONFIDENCE_CHECK), "staged_ingredients", type_="check")
    op.drop_column("staged_ingredients", "from_extras_section")
    op.drop_column("staged_ingredients", "confidence")
