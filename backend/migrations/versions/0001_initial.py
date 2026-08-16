"""initial — pusta migracja bazowa (bez tabel).

Revision ID: 0001
Revises:
Create Date: 2026-08-16

BATCH_01 nie tworzy żadnych tabel. Ta rewizja istnieje po to, by:
- każdy kolejny batch miał jednoznaczny `down_revision` (ADR-002),
- pipeline migracji był przetestowany (upgrade → downgrade → upgrade)
  zanim pojawi się pierwszy schemat (03_DATABASE §1).

Downgrade MUSI przechodzić — to test procedury, nie formalność.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Brak zmian schematu — łańcuch rewizji startuje pusty."""


def downgrade() -> None:
    """Brak zmian do cofnięcia."""
