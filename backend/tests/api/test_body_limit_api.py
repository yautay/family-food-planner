"""Sufit rozmiaru ciała żądania — 413 w kształcie błędu 04_API §1 (BATCH_17, Stage 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

MIB = 1024 * 1024


async def test_zwykle_zadanie_ponad_2_mb_dostaje_413_przed_routingiem(client: AsyncClient) -> None:
    """`Content-Length` ponad sufit domyślny → 413 zanim aplikacja przeczyta bajt."""
    response = await client.post(
        f"{API}/auth/login",
        content=b"x" * (2 * MIB + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "payload_too_large"
    assert "2 MB" in body["error"]["message"]
    assert response.headers["X-Frame-Options"] == "DENY", "nagłówki bezpieczeństwa także na 413"


async def test_cialo_bez_content_length_tez_jest_ucinane(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Strumień (chunked) bez deklaracji długości — licznik na `receive()` daje to samo 413."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    async def stream() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"y" * MIB

    response = await db_client.post(
        f"{API}/recipes",
        content=stream(),
        headers={"Content-Type": "application/json", **csrf_headers(db_client)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_zadanie_ponizej_sufitu_dociera_do_aplikacji(client: AsyncClient) -> None:
    """Sufit nie może ucinać poprawnych żądań: 1 MB JSON-a przechodzi do walidacji (422)."""
    response = await client.post(
        f"{API}/auth/login",
        content=b'{"email": "' + b"a" * MIB + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


async def test_upload_pdf_ma_wyzszy_sufit_niz_reszta_api(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """3 MB na `/import/pdf` mija middleware (limit 25 MB + margines) i pada dopiero
    na sniffingu treści (422) — czyli sufit per endpoint działa."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{API}/import/pdf",
        files={"file": ("nie-pdf.pdf", b"\x00" * (3 * MIB), "application/pdf")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_upload_pdf_ponad_limit_plus_margines_dostaje_413(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ciało ponad 25 MB + 1 MB marginesu → 413 z komunikatem o limicie 25 MB."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{API}/import/pdf",
        files={"file": ("duzy.pdf", b"\x00" * (26 * MIB + 1024), "application/pdf")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert "25 MB" in response.json()["error"]["message"]
