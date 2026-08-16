"""Modele modułu accounts: User i Session (03_DATABASE §2 — schemat wiążący).

`users.household_id` NIE powstaje w tym batchu — kolumnę razem z tabelą
`households` dodaje BATCH_03 (nie tworzymy FK do nieistniejącej tabeli).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class UserRole(StrEnum):
    """Role systemowe (02_DOMAIN §2). ADMIN zarządza kontami i danymi globalnymi."""

    ADMIN = "admin"
    USER = "user"


#: Typ enumowy w PG współdzielony przez model i migrację — jedna definicja nazw.
USER_ROLE_ENUM = Enum(
    UserRole,
    name="user_role",
    values_callable=lambda enum: [member.value for member in enum],
)


class User(TimestampMixin, Base):
    """Konto użytkownika. Zakłada je wyłącznie ADMIN (brak samorejestracji, ADR-003)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(USER_ROLE_ENUM, nullable=False, default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: Ustawienia UI (m.in. progi wskaźników żywieniowych — edycja w BATCH_06).
    ui_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Blokada po serii nieudanych logowań (07_SECURITY §2). Stan trzymamy w bazie,
    # a nie w pamięci procesu — restart aplikacji nie może zerować blokady.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Session(Base):
    """Sesja server-side (ADR-003). `id` = `secrets.token_urlsafe(32)` w cookie HttpOnly.

    Bez `updated_at` — 03_DATABASE §2 wylicza kolumny tej tabeli wprost, a rolę
    znacznika „ostatnio używana" pełni przesuwane `expires_at`.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        # Sprzątanie wygasłych sesji (03_DATABASE §12) i lista sesji użytkownika.
        Index("ix_sessions_expires_at", "expires_at"),
        Index("ix_sessions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
