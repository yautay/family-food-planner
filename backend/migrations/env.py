"""Alembic — środowisko migracji.

URL bazy pochodzi WYŁĄCZNIE z konfiguracji aplikacji (pydantic-settings →
`DATABASE_URL`); w `alembic.ini` nie ma i nie może być poświadczeń
(07_SECURITY §7). Testy i skrypty mogą wskazać inną bazę przez
`alembic -x db_url=postgresql+psycopg://...` (tak działa `task test-int`).

Metadata = `app.core.db.Base.metadata` z naming convention (03_DATABASE §1) —
spójne nazwy constraintów są warunkiem czystych downgrade'ów.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.db import Base, normalize_database_url, selector_loop_factory

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Kolejność: `-x db_url=...` → `DATABASE_URL` z konfiguracji aplikacji."""
    x_args = context.get_x_argument(as_dictionary=True)
    url = x_args.get("db_url") or get_settings().database_url
    return normalize_database_url(url)


def run_migrations_offline() -> None:
    """Tryb offline — generowanie SQL bez połączenia z bazą."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Tryb online — silnik async (psycopg 3), migracje przez `run_sync`."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    # loop_factory: na Windows wymusza SelectorEventLoop (wymóg psycopg async).
    asyncio.run(run_async_migrations(), loop_factory=selector_loop_factory())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
