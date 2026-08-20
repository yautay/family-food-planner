"""Model celów żywieniowych użytkownika (03_DATABASE §2 — schemat wiążący).

Cele mieszkają w module `nutrition`, bo tak dzieli domenę 02_DOMAIN §1
(„nutrition — deterministyczny silnik obliczeń (kcal/makro/IG→ŁG), **cele**").
Fizycznie tabela stoi obok kont (03_DATABASE §2), ale należy do domeny żywienia:
konsumentami są plan dnia (B06), statystyki (B13) i widoki celów, a nie
zarządzanie kontami. `engine.py` pozostaje czysty — modele i I/O żyją w osobnych
plikach modułu (ADR-008 wiąże PLIK silnika, nie cały moduł).

Historia celów jest zachowywana (D10 — nic nie usuwamy automatycznie):
cel obowiązujący w dniu D to wiersz z największym `valid_from <= D`, więc
zmiana celu od nowej daty NIE przepisuje statusów dni sprzed tej daty.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

__all__ = ["UserNutritionGoal"]


class UserNutritionGoal(TimestampMixin, Base):
    """Dzienny cel kcal (+ opcjonalne makra) obowiązujący od daty (02_DOMAIN §6)."""

    __tablename__ = "user_nutrition_goals"
    __table_args__ = (
        # Jeden cel na parę (użytkownik, data startu) — duplikat daty to 409,
        # a nie cicha nadpisana historia.
        UniqueConstraint(
            "user_id", "valid_from", name="uq_user_nutrition_goals_user_id_valid_from"
        ),
        CheckConstraint("kcal > 0", name="kcal_positive"),
        CheckConstraint(
            "(protein_g IS NULL OR protein_g >= 0) "
            "AND (fat_g IS NULL OR fat_g >= 0) "
            "AND (carbs_g IS NULL OR carbs_g >= 0)",
            name="macros_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: CASCADE: cel bez właściciela nie znaczy nic (kompozycja konta, ADR-012).
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    kcal: Mapped[Decimal] = mapped_column(Numeric(6, 0), nullable=False)
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
