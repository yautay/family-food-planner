"""Po wycofaniu importu PDF (D25, BATCH_20) po jego HTTP nie ma śladu.

Test regresyjny, nie „test usunięcia": trasy `/import/*` mają NIE WRÓCIĆ
przypadkiem razem z odtworzonym routerem, a plik zostawiony na dysku w katalogu
po wycofanej funkcji ma NIE STAĆ SIĘ pobieralny. To drugie jest realnym
zagrożeniem, a nie hipotezą — jadłospis niósł imię i nazwisko pacjenta na
stronie tytułowej, a `/uploads/{path}` sprawdza wyłącznie sesję, więc przy
liście ZAKAZANYCH podkatalogów zdjęcie wpisu z listy udostępniłoby te pliki
każdemu zalogowanemu. Stąd allowlista w `core/uploads.SERVED_SUBDIRS`.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from tests.factories import create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{API}/import/jobs"),
        ("GET", f"{API}/import/jobs/1"),
        ("DELETE", f"{API}/import/jobs/1"),
        ("POST", f"{API}/import/pdf"),
        ("GET", f"{API}/import/jobs/1/staged"),
        ("POST", f"{API}/import/jobs/1/resolve"),
        ("POST", f"{API}/import/jobs/1/ai-suggest"),
        ("POST", f"{API}/import/jobs/1/approve"),
        ("POST", f"{API}/import/jobs/1/reject"),
    ],
)
async def test_trasy_importu_pdf_nie_istnieja(
    db_client: AsyncClient, db_session: AsyncSession, method: str, path: str
) -> None:
    """404, nie 410: nikt poza naszym frontendem tych tras nie wołał (karta B20)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.request(method, path, headers=csrf_headers(db_client))

    assert response.status_code == 404


async def test_plik_z_katalogu_spoza_allowlisty_nie_jest_serwowany(
    db_client: AsyncClient, db_session: AsyncSession, settings: Settings
) -> None:
    """Plik zostawiony na dysku po wycofanej funkcji = 404, mimo poprawnej sesji."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    uploads_root = Path(settings.uploads_dir)
    leftover = uploads_root / "wycofany-modul"
    leftover.mkdir(parents=True, exist_ok=True)
    plik = leftover / "jadlospis.pdf"
    plik.write_bytes(b"%PDF-1.7 tresc")

    try:
        response = await db_client.get("/uploads/wycofany-modul/jadlospis.pdf")
        assert response.status_code == 404
        # Serwowany katalog działa dalej — allowlista nie jest globalną blokadą.
        assert (await db_client.get("/uploads/recipes/nie-ma.jpg")).status_code == 404
    finally:
        # Sprzątanie nie ma prawa wywrócić testu: katalog mógł istnieć przed nim
        # (to realny katalog uploadów instalacji, nie `tmp_path`).
        plik.unlink(missing_ok=True)
        with suppress(OSError):
            leftover.rmdir()
