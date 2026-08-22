"""znacznik przyjęcia pozycji listy do spiżarni (BATCH_12, decyzja D19)

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-22

Jedna kolumna: `shopping_list_items.received_at timestamptz NULL` — moment
przyjęcia TEJ pozycji do spiżarni (`NULL` = jeszcze nieprzyjęta).

Po co: do B12 `accept_to_pantry` dawało się wywołać wielokrotnie i za każdym
razem dolewało zakupy od nowa. Dopóki akcję odpalał człowiek przez dialog
potwierdzenia, było to teoretyczne; z kolejką offline (ADR-009) ponowienie
żądania po utracie odpowiedzi jest NORMALNĄ pracą, więc podwójne dolanie
zrobiłoby się samo — i to po cichu (spiżarnia pokazuje 4 l mleka zamiast 2 l).

Dlaczego per POZYCJA, a nie per lista: „doniosłem jeszcze dwie rzeczy z torby
i odhaczyłem je później" to uzasadniony przypadek, którego znacznik na liście
by zablokował (D19, odrzucony wariant b).

Czego migracja NIE robi: **nie backfilluje** istniejących list. Historyczne
przyjęcia nie są nigdzie zapisane, więc każda inna wartość byłaby wymyślona —
wszystkie pozycje zostają `NULL`, czyli „nieprzyjęte".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shopping_list_items",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shopping_list_items", "received_at")
