"""Model dziennika operacji (03_DATABASE §10).

Tabela jest **append-only**: nie ma serwisu ani endpointu, który zmienia lub
kasuje wiersz. Stąd brak `updated_at` — kolumna, której nikt nigdy nie ruszy,
tylko sugerowałaby, że wpis wolno edytować.

Audit log ≠ logi techniczne (07_SECURITY §8): tu trafiają operacje biznesowe
(kto, co, na czym), nigdy hasła, hashe ani tokeny.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditEntry(Base):
    """Pojedynczy wpis dziennika: kto, kiedy, jaka operacja i na jakiej encji."""

    __tablename__ = "audit_entries"
    __table_args__ = (
        # Przegląd historii jednej encji („co się działo z tym przepisem").
        Index("ix_audit_entries_entity_type_entity_id", "entity_type", "entity_id"),
        # Domyślny widok dziennika to „ostatnie operacje" — sortowanie malejące.
        Index("ix_audit_entries_created_at", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: Usunięcie konta nie może kasować historii jego operacji — zostaje NULL.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
