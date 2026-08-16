"""seed_product_categories — słownik kategorii zakupowych (BATCH_04)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16

Migracja DANYCH, oddzielona od schematu i idempotentna (03_DATABASE §1):
`ON CONFLICT (name) DO NOTHING` pozwala ją bezpiecznie powtórzyć na bazie,
w której kategorie już są.

Skład słownika (02_DOMAIN §4.3): lista dietetyczki z 01_PDF_AUDIT §5.5
uzupełniona o kategorie wymagane przez wymagania (pieczywo, suche/strączkowe,
makarony-ryż-kasze, puszki-słoiki). Dwie decyzje o nakładaniu się znaczeń:

- **„Zbożowe" nie wchodzi do słownika** (D14, 02_DECISIONS): kategoria niesie
  `perishability`, a pieczywo jest świeże, podczas gdy makarony, ryż i kasze
  są trwałe. Wspólna kategoria nie uniosłaby obu wartości i zepsułaby podział
  na tury w silniku zakupowym (B10).
- **„Przetwory" i „puszki-słoiki" scalone w jedną kategorię**: to ten sam
  regał i ta sama trwałość, a rozdzielenie zmuszałoby użytkownika do zgadywania,
  czy pomidory z puszki są przetworem. Reguła, z której wynikają obie decyzje:
  dzielimy kategorie, gdy różni je `perishability`; scalamy, gdy różni je tylko
  nazwa.

Trwałość wg karty BATCH_04: świeże to warzywa, owoce, grzyby, nabiał, mięso
i pieczywo; reszta trwała.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (nazwa, trwałość) w kolejności przejścia po sklepie; `position` = indeks.
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Warzywa", "fresh"),
    ("Owoce", "fresh"),
    ("Grzyby", "fresh"),
    ("Nabiał i jaja", "fresh"),
    ("Mięso i produkty mięsne", "fresh"),
    ("Pieczywo", "fresh"),
    ("Mrożonki", "durable"),
    ("Makarony, ryż i kasze", "durable"),
    ("Suche i strączkowe", "durable"),
    ("Orzechy i nasiona", "durable"),
    ("Przetwory, puszki i słoiki", "durable"),
    ("Przyprawy i zioła", "durable"),
    ("Tłuszcze", "durable"),
    ("Inne", "durable"),
)


def upgrade() -> None:
    """Wstawia kategorie; powtórne uruchomienie nie zmienia niczego."""
    statement = sa.text(
        "INSERT INTO product_categories (name, position, perishability)"
        " VALUES (:name, :position, CAST(:perishability AS perishability))"
        " ON CONFLICT (name) DO NOTHING"
    )
    op.get_bind().execute(
        statement,
        [
            {"name": name, "position": position, "perishability": perishability}
            for position, (name, perishability) in enumerate(CATEGORIES, start=1)
        ],
    )


def downgrade() -> None:
    """Usuwa dokładnie te kategorie, które wstawił upgrade — po nazwach.

    Kategoria z produktami nie zniknie: FK `canonical_products.category_id` ma
    ON DELETE RESTRICT (ADR-012), więc rollback na bazie z danymi zatrzyma się
    z błędem zamiast osierocić produkty. To zachowanie zamierzone.
    """
    op.get_bind().execute(
        sa.text("DELETE FROM product_categories WHERE name IN :names").bindparams(
            sa.bindparam("names", value=tuple(name for name, _ in CATEGORIES), expanding=True)
        )
    )
