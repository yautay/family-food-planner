"""Rate limit na endpointach uploadu (BATCH_17, ustalenie REVIEW R4 pkt 3).

Każdy test wysyła plik o ZŁEJ treści (sniffing → 422): licznik slowapi zlicza
żądania niezależnie od wyniku, a bez poprawnego pliku test nie zapisuje nic na
dysku. Limiter jest per aplikacja (fixture `app` na test), więc testy nie
zatruwają się nawzajem.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimits import FILE_UPLOAD_RATE_LIMIT, PHOTO_UPLOAD_RATE_LIMIT
from tests.factories import (
    create_category,
    create_product,
    create_recipe,
    create_retail_product,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

PHOTO_LIMIT = int(PHOTO_UPLOAD_RATE_LIMIT.split("/")[0])
FILE_LIMIT = int(FILE_UPLOAD_RATE_LIMIT.split("/")[0])


def _files(name: str, mime: str) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, b"to nie jest ten format", mime)}


async def _hammer(
    client: AsyncClient,
    method: str,
    url: str,
    *,
    times: int,
    files: dict[str, tuple[str, bytes, str]],
) -> list[int]:
    statuses = []
    for _ in range(times):
        response = await client.request(method, url, files=files, headers=csrf_headers(client))
        statuses.append(response.status_code)
    return statuses


async def test_zdjecie_przepisu_31_w_minucie_daje_429(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)
    url = f"{API}/recipes/{recipe.id}/photo"

    statuses = await _hammer(
        db_client, "POST", url, times=PHOTO_LIMIT + 1, files=_files("a.jpg", "image/jpeg")
    )

    assert statuses[:PHOTO_LIMIT] == [422] * PHOTO_LIMIT
    assert statuses[-1] == 429


async def test_zdjecie_wariantu_sklepowego_31_w_minucie_daje_429(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product)
    await login(db_client, user.email)
    url = f"{API}/retail-products/{retail.id}/photo"

    statuses = await _hammer(
        db_client, "PUT", url, times=PHOTO_LIMIT + 1, files=_files("a.jpg", "image/jpeg")
    )

    assert statuses[:PHOTO_LIMIT] == [422] * PHOTO_LIMIT
    assert statuses[-1] == 429


async def test_import_pdf_11_w_minucie_daje_429(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    statuses = await _hammer(
        db_client,
        "POST",
        f"{API}/import/pdf",
        times=FILE_LIMIT + 1,
        files=_files("j.pdf", "application/pdf"),
    )

    assert statuses[:FILE_LIMIT] == [422] * FILE_LIMIT
    assert statuses[-1] == 429


async def test_import_paczki_transferu_11_w_minucie_daje_429(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    statuses = await _hammer(
        db_client,
        "POST",
        f"{API}/transfer/import",
        times=FILE_LIMIT + 1,
        files=_files("e.zip", "application/zip"),
    )

    assert statuses[:FILE_LIMIT] == [422] * FILE_LIMIT
    assert statuses[-1] == 429


async def test_odpowiedz_429_ma_ksztalt_kontraktu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)
    files = _files("j.pdf", "application/pdf")
    for _ in range(FILE_LIMIT):
        await db_client.post(f"{API}/import/pdf", files=files, headers=csrf_headers(db_client))

    response = await db_client.post(
        f"{API}/import/pdf", files=files, headers=csrf_headers(db_client)
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "Zbyt wiele" in response.json()["error"]["message"]
