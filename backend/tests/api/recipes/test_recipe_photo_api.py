"""Upload i serwowanie zdjęć przepisów — pipeline 07_SECURITY §6.

Obraz testowy generuje Pillow (prawdziwy PNG), więc sniffing dostaje realną
treść, a nie spreparowane nagłówki.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from tests.factories import create_recipe, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

RECIPES = f"{API}/recipes"


def _png_bytes(size: tuple[int, int] = (800, 600)) -> bytes:
    """Poprawny PNG z kanałem alfa — sprawdza też spłaszczanie do JPEG."""
    buffer = BytesIO()
    Image.new("RGBA", size, (224, 122, 47, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_upload_sniffing_reencode_i_miniatura(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance 7: zapis pod losową nazwą .jpg, miniatura obok, URL-e w odpowiedzi."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{RECIPES}/{recipe.id}/photo",
        files={"file": ("zdjecie.png", _png_bytes(), "image/png")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["photo_url"].startswith("/uploads/recipes/")
    assert body["photo_url"].endswith(".jpg")
    assert body["photo_thumb_url"].endswith("_thumb.jpg")

    uploads_root = Path(get_settings().uploads_dir)
    stored = uploads_root / body["photo_url"].removeprefix("/uploads/")
    thumb = uploads_root / body["photo_thumb_url"].removeprefix("/uploads/")
    assert stored.is_file() and thumb.is_file()
    # Re-encode: na dysku leży JPEG wyrenderowany przez nas, nie oryginalny PNG.
    with Image.open(stored) as image:
        assert image.format == "JPEG"
    with Image.open(thumb) as image:
        assert max(image.size) <= 512


async def test_serving_uploadu_wymaga_sesji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance 7: plik dostępny wyłącznie po zalogowaniu (401 bez sesji)."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)
    body = (
        await db_client.post(
            f"{RECIPES}/{recipe.id}/photo",
            files={"file": ("zdjecie.png", _png_bytes(), "image/png")},
            headers=csrf_headers(db_client),
        )
    ).json()

    served = await db_client.get(body["photo_url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"

    db_client.cookies.clear()
    assert (await db_client.get(body["photo_url"])).status_code == 401


async def test_nie_obraz_to_422(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Sniffing po TREŚCI: PDF w przebraniu .png odpada, rozszerzenie nie ma znaczenia."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{RECIPES}/{recipe.id}/photo",
        files={"file": ("zdjecie.png", b"%PDF-1.7 nie-obraz", "image/png")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_za_duzy_plik_to_413(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Limit pochodzi z konfiguracji (`IMAGE_MAX_UPLOAD_MB`, B17), nie ze stałej modułu."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)

    oversized = b"\x00" * (get_settings().image_max_upload_mb * 1024 * 1024 + 1)
    response = await db_client.post(
        f"{RECIPES}/{recipe.id}/photo",
        files={"file": ("duze.jpg", oversized, "image/jpeg")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 413


async def test_sciezka_poza_katalogiem_uploadow_to_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Path traversal kończy się identycznym 404 jak brakujący plik."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.get("/uploads/recipes/nie-ma-takiego.jpg")).status_code == 404
    assert (await db_client.get("/uploads/..%2F..%2Fapp%2Fmain.py")).status_code == 404
    assert (await db_client.get("/uploads/recipes/%2E%2E/%2E%2E/pyproject.toml")).status_code == 404


async def test_usuniecie_zdjecia_czysci_pliki_i_pole(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)
    uploaded = (
        await db_client.post(
            f"{RECIPES}/{recipe.id}/photo",
            files={"file": ("zdjecie.png", _png_bytes(), "image/png")},
            headers=csrf_headers(db_client),
        )
    ).json()
    uploads_root = Path(get_settings().uploads_dir)
    stored = uploads_root / uploaded["photo_url"].removeprefix("/uploads/")

    removed = await db_client.delete(
        f"{RECIPES}/{recipe.id}/photo", headers=csrf_headers(db_client)
    )

    assert removed.status_code == 200
    assert removed.json()["photo_url"] is None
    assert not stored.exists()

    # Ponowne usunięcie: nie ma czego usuwać — 404.
    again = await db_client.delete(f"{RECIPES}/{recipe.id}/photo", headers=csrf_headers(db_client))
    assert again.status_code == 404


async def test_podmiana_zdjecia_usuwa_poprzednie_pliki(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Podmieniony oryginał i miniatura nie zostają na dysku jako sieroty."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    await login(db_client, user.email)
    uploads_root = Path(get_settings().uploads_dir)

    first = (
        await db_client.post(
            f"{RECIPES}/{recipe.id}/photo",
            files={"file": ("a.png", _png_bytes(), "image/png")},
            headers=csrf_headers(db_client),
        )
    ).json()
    first_file = uploads_root / first["photo_url"].removeprefix("/uploads/")

    second = (
        await db_client.post(
            f"{RECIPES}/{recipe.id}/photo",
            files={"file": ("b.png", _png_bytes((320, 240)), "image/png")},
            headers=csrf_headers(db_client),
        )
    ).json()

    assert second["photo_url"] != first["photo_url"]
    assert not first_file.exists()
