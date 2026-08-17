"""seed_system_tags — słownik tagów systemowych przepisów (BATCH_05)

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-17

Migracja DANYCH, oddzielona od schematu i idempotentna (03_DATABASE §1):
`ON CONFLICT (name) DO NOTHING` pozwala ją bezpiecznie powtórzyć.

Skład: seed z 02_DOMAIN §5 (śniadanie, obiad, kolacja, szybkie, warzywne,
do lunchboxa, do zamrożenia, dzieci lubią) plus **„ulubione"** — tag serca na
karcie przepisu (06_UIUX §4.2, karta B05). Tagi systemowe różnią się od
użytkowych wyłącznie flagą `is_system` — nie da się ich pomylić z inline create.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_TAGS: tuple[str, ...] = (
    "śniadanie",
    "obiad",
    "kolacja",
    "szybkie",
    "warzywne",
    "do lunchboxa",
    "do zamrożenia",
    "dzieci lubią",
    "ulubione",
)


def upgrade() -> None:
    """Wstawia tagi systemowe; powtórne uruchomienie nie zmienia niczego."""
    statement = sa.text(
        "INSERT INTO tags (name, is_system) VALUES (:name, true) ON CONFLICT (name) DO NOTHING"
    )
    op.get_bind().execute(statement, [{"name": name} for name in SYSTEM_TAGS])


def downgrade() -> None:
    """Usuwa tagi z seedu — po nazwach i tylko NIEUŻYWANE (lekcja U2 z review R1).

    FK `recipe_tags.tag_id` ma ON DELETE CASCADE, więc twardy DELETE by przeszedł,
    ale po cichu zdejmowałby przypisania z przepisów użytkownika. Tag przypisany
    do czegokolwiek zostaje; i tak zniknie razem z całą tabelą w `downgrade`
    migracji `0006`, więc nic nie osieroci.
    """
    op.get_bind().execute(
        sa.text(
            "DELETE FROM tags t"
            " WHERE t.name IN :names"
            "   AND t.is_system"
            "   AND NOT EXISTS (SELECT 1 FROM recipe_tags rt WHERE rt.tag_id = t.id)"
        ).bindparams(sa.bindparam("names", value=SYSTEM_TAGS, expanding=True))
    )
