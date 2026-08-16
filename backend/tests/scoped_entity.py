"""Encja testowa konsumująca `ScopedQuery` — wyłącznie na potrzeby macierzy §4.

Dlaczego encja sztuczna, a nie produkcyjna: BATCH_03 dostarcza sam mechanizm
scope, a pierwsza produkcyjna tabela z tymi kolumnami (`recipes`) powstaje
dopiero w BATCH_05. Macierz uprawnień musi być przetestowana TERAZ, bo to ona
jest produktem tego batcha.

Dlaczego wspólna `Base`, a nie osobne `MetaData`: kolumny wzorca mają FK do
`users` i `households`, więc `create_all` na osobnym metadata nie umiałby
rozwiązać referencji (`NoReferencedTableError`). Kryterium z karty batcha jest
spełnione inaczej — tabela NIE istnieje w żadnej migracji, a fixture
`scoped_notes_table` tworzy ją i kasuje w obrębie pojedynczego testu, więc
`alembic upgrade head` na bazie produkcyjnej nigdy jej nie utworzy (pilnuje
tego asercja `EXPECTED_TABLES` w `tests/integration/test_migrations.py`).
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import Table, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.core.scope import Scope, ScopedMixin, ScopedQuery
from app.modules.accounts.models import User


class ScopedNote(TimestampMixin, ScopedMixin, Base):
    """Minimalna encja współdzielna: PK, kolumny scope i jedno pole treści."""

    __tablename__ = "scoped_notes"

    title: Mapped[str] = mapped_column(Text, nullable=False)


#: Tak samo, jak zrobi to serwis przepisów w BATCH_05 — jedna instancja na encję.
SCOPED_NOTES = ScopedQuery(ScopedNote, not_found_message="Nie znaleziono notatki.")

#: `__table__` jest typowane jako `FromClause`; DDL w conftest potrzebuje `Table`.
SCOPED_NOTES_TABLE = cast(Table, ScopedNote.__table__)


async def create_scoped_note(
    session: AsyncSession,
    *,
    owner: User,
    scope: Scope = Scope.PRIVATE,
    title: str = "Notatka",
) -> ScopedNote:
    """Notatka utworzona tak, jak zrobiłby to serwis — przez `ownership_for_create`."""
    note = ScopedNote(title=title, **ScopedQuery.ownership_for_create(owner, scope))
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note
