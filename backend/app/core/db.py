"""Dostęp do bazy: silnik async, fabryka sesji, deklaratywna baza modeli.

Konwencje (03_DATABASE §1):
- driver: psycopg 3 w trybie async (`postgresql+psycopg://`) — ADR-015,
- nazwy constraintów przez `naming_convention` (warunek czystych downgrade'ów),
- czas: timestamptz w UTC (kolumny dostarczają batche domenowe),
- ilości i wartości odżywcze: NUMERIC ↔ Decimal, nigdy float (ADR-008).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from functools import lru_cache

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Wspólna baza modeli SQLAlchemy 2.0 (styl `Mapped[...]` / `mapped_column`)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def selector_loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """Fabryka pętli dla `asyncio.run(...)` na Windows — inaczej psycopg async nie wystartuje.

    Windows domyślnie używa `ProactorEventLoop`, którego psycopg 3 w trybie async
    nie obsługuje. Aplikacja produkcyjna i kontener dev pracują na Linuksie, ale
    narzędzia uruchamiane na hoście dewelopera (alembic, pytest) muszą jawnie
    wymusić `SelectorEventLoop`. Poza Windows zwraca `None` = pętla domyślna.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop
    return None


def normalize_database_url(url: str) -> str:
    """Wymuś driver psycopg async — `postgresql://` z env działa tak samo jak jawny wariant."""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Silnik procesu (jeden na aplikację)."""
    settings = get_settings()
    return create_async_engine(
        normalize_database_url(settings.database_url),
        pool_pre_ping=True,
        echo=False,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Fabryka sesji — `expire_on_commit=False`, żeby obiekty żyły po commicie."""
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI: sesja na request. Serwisy commitują jawnie; wyjątek = rollback."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
