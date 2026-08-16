"""Modele modułu households: Household i MemberProfile (03_DATABASE §2 — wiążące).

Reguła nadrzędna (ADR-006): użytkownik należy do MAKSYMALNIE jednej rodziny,
co gwarantuje pojedyncza kolumna `users.household_id` — tabeli łączącej nie ma
i nie może być, bo wtedy scope przestałby być jednym warunkiem SQL.

`member_profiles` NIE jest kopią kont: profil może istnieć bez użytkownika
(dzieci — 02_DOMAIN §3), dlatego `owner_user_id` jest opcjonalne.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover — tylko dla typów, bez cyklu importów
    from app.modules.accounts.models import User


class Household(TimestampMixin, Base):
    """Rodzina. Tworzy ją i przypisuje do niej konta wyłącznie ADMIN (02_DOMAIN §3)."""

    __tablename__ = "households"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Obie kolekcje istnieją dla spójności mapowania i konfiguracji kaskad —
    # NIE do odczytu w serwisie ani (tym bardziej) w routerze. Skład rodziny
    # czyta się jawnym `select` (patrz `HouseholdsService._views`): leniwa
    # kolekcja tknięta poza kontekstem greenletu to `MissingGreenlet` i 500.
    # `passive_deletes` — o czyszczeniu decyduje FK (`users.household_id`
    # ON DELETE SET NULL, `member_profiles.household_id` ON DELETE CASCADE).
    users: Mapped[list[User]] = relationship(back_populates="household", passive_deletes=True)
    profiles: Mapped[list[MemberProfile]] = relationship(
        back_populates="household", passive_deletes=True
    )


class MemberProfile(TimestampMixin, Base):
    """Profil członka rodziny — jednostka skalowania porcji i celów (02_DOMAIN §3).

    `default_multiplier` i `kcal_goal` to NUMERIC ↔ Decimal (ADR-008); `float`
    w tym miejscu byłby błędem blokującym review.
    """

    __tablename__ = "member_profiles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    household_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    #: Powiązanie z kontem jest opcjonalne, a usunięcie konta nie kasuje profilu
    #: (osoba nadal je w tej rodzinie) — stąd SET NULL zamiast RESTRICT.
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
        default=Decimal("1.00"),
        server_default=text("1.0"),
    )
    kcal_goal: Mapped[Decimal | None] = mapped_column(Numeric(6, 0), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    household: Mapped[Household | None] = relationship(back_populates="profiles")
