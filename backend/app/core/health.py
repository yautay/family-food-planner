"""Healthcheck `/api/v1/health` — stan procesu, bazy, migracji i dysku (09_DEPLOYMENT §2).

Do BATCH_17 endpoint świadomie nie dotykał bazy (B01) i odpowiadał dosłownie
`{"status": "ok", "version": ...}`. Procedura update z 09 §4 NIE migruje
automatycznie, więc jedyną rzeczą, która wykryje „kontener wstał na starym
schemacie", jest właśnie ten endpoint (ustalenie REVIEW R4 pkt 1).

Kontrakt:

- `status`: `ok` gdy wszystkie checki przeszły, inaczej `degraded`. Odpowiedź
  ma ZAWSZE kod 200 — `degraded` to informacja dla operatora, nie powód do
  restartu. Healthcheck compose/Dockera testuje sam kod HTTP: kontener, który
  odpowiada, jest „healthy" nawet niezmigrowany, bo restart w pętli niczego by
  nie naprawił (migracje są jawnym krokiem), a zamaskowałby przyczynę.
  `down` = brak odpowiedzi w ogóle.
- `checks.db`: JEDNO zapytanie (`SELECT version_num FROM alembic_version`)
  z limitem czasu rozstrzyga oba checki: odpowiedź = baza żyje; brak tabeli
  (`ProgrammingError`) = baza żyje, ale nie jest zmigrowana; inny błąd albo
  timeout = baza nie odpowiada. Worst case to JEDEN timeout (3 s), mniej niż
  `--timeout` healthchecku obrazu (5 s).
- `checks.migrations`: wersja z bazy == head skryptów w obrazie; `skipped`,
  gdy baza nie odpowiada (nie ma czego porównać).
- `checks.disk`: wolne miejsce w katalogu uploadów ≥ `DISK_MIN_FREE_MB`.
  Mierzone `shutil.disk_usage` na najbliższym istniejącym przodku katalogu —
  w kontenerze to bind mount `/data/uploads`, czyli dysk danych.

Bez uwierzytelnienia i bez szczegółów infrastruktury: żadnych ścieżek, hostów,
numerów rewizji ani liczb bajtów — wyłącznie `ok`/`fail`/`skipped` (07_SECURITY).
Pusty `ANTHROPIC_API_KEY` jest poprawną konfiguracją prod i NIE jest checkiem.
"""

from __future__ import annotations

import asyncio
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session

CheckStatus = Literal["ok", "fail", "skipped"]
HealthStatus = Literal["ok", "degraded"]

#: Sufit czasu na `SELECT 1` — healthcheck ma odpowiadać, nie wisieć na bazie.
DB_CHECK_TIMEOUT_S = 3.0

#: Katalog migracji tego obrazu (`backend/migrations`) — head liczony ze skryptów,
#: bez `alembic.ini` i bez `env.py` (ten wymaga `DATABASE_URL` i łączy się z bazą).
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class HealthChecks(BaseModel):
    """Wynik trzech sprawdzeń — tylko statusy, żadnych szczegółów infrastruktury."""

    db: CheckStatus
    migrations: CheckStatus
    disk: CheckStatus


class HealthResponse(BaseModel):
    """Odpowiedź healthchecku: status zbiorczy, wersja obrazu, statusy checków."""

    status: HealthStatus
    version: str
    checks: HealthChecks


@lru_cache(maxsize=1)
def expected_head() -> str:
    """Rewizja `head` skryptów Alembica w tym obrazie (stała na czas życia procesu)."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    head = ScriptDirectory.from_config(config).get_current_head()
    return head or ""


def compare_migrations(expected: str, actual: str | None) -> CheckStatus:
    """Czysta reguła: baza zmigrowana ⇔ `alembic_version` == head skryptów."""
    if not actual or not expected:
        return "fail"
    return "ok" if actual == expected else "fail"


def check_disk(path: Path, *, min_free_mb: int) -> CheckStatus:
    """Wolne miejsce na dysku, na którym leży `path` (albo jego najbliższy istniejący przodek)."""
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            return "fail"
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return "fail"
    return "ok" if free >= min_free_mb * 1024 * 1024 else "fail"


async def check_database(session: AsyncSession) -> tuple[CheckStatus, str | None]:
    """(`db`, wersja z `alembic_version` albo None) z JEDNEGO zapytania.

    `ProgrammingError` (brak tabeli `alembic_version` — czysta baza) znaczy, że
    baza ODPOWIADA, tylko nie jest zmigrowana; każdy inny błąd i timeout = `fail`.
    """
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_S):
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            row = result.scalars().first()
    except ProgrammingError:
        return "ok", None
    except (TimeoutError, SQLAlchemyError, OSError):
        return "fail", None
    return "ok", str(row) if row is not None else None


def overall_status(checks: HealthChecks) -> HealthStatus:
    values = (checks.db, checks.migrations, checks.disk)
    return "ok" if all(value == "ok" for value in values) else "degraded"


async def run_health_checks(session: AsyncSession, settings: Settings) -> HealthResponse:
    """Złóż odpowiedź z trzech checków; `migrations` jest `skipped`, gdy baza nie odpowiada."""
    db_status, db_version = await check_database(session)
    migrations: CheckStatus = (
        compare_migrations(expected_head(), db_version) if db_status == "ok" else "skipped"
    )
    disk = check_disk(Path(settings.uploads_dir), min_free_mb=settings.disk_min_free_mb)
    checks = HealthChecks(db=db_status, migrations=migrations, disk=disk)
    return HealthResponse(
        status=overall_status(checks), version=settings.app_version, checks=checks
    )


def build_health_router(settings: Settings) -> APIRouter:
    """Router `/health` — publiczny, bez sesji (04_API §3 pkt 1), zawsze 200."""
    router = APIRouter(tags=["health"])
    # Rozgrzewka: pierwsze wywołanie importuje skrypty migracji (synchroniczne,
    # setki ms na Odroidzie) — lepiej przy składaniu aplikacji niż w pętli zdarzeń
    # pierwszego żądania.
    expected_head()

    @router.get("/health", response_model=HealthResponse, summary="Stan aplikacji")
    async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> HealthResponse:
        return await run_health_checks(session, settings)

    return router
