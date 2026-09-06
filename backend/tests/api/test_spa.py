"""Serwowanie SPA przez backend (ADR-014, `core/spa.py`) — kontrakt cache i 404/405.

Aplikacja z `SPA_DIST_DIR` wskazującym tymczasowy `dist/`: index, hashowane
assety, manifest, service worker, trasy Vue, nieznane ścieżki API i uploadów
oraz metody inne niż GET/HEAD. W dev/test catch-all nie jest zarejestrowany
(`spa_dist_dir` puste), więc bez tego testu prod-only różnice byłyby niewidoczne.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.api

API = "/api/v1"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=app></div>", encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "sw.js").write_text("self.addEventListener('fetch', () => {})", encoding="utf-8")
    (tmp_path / "manifest.webmanifest").write_text('{"name": "Paśnik"}', encoding="utf-8")
    return tmp_path


@pytest.fixture
async def spa_client(settings: Settings, dist: Path) -> AsyncClient:
    app = create_app(settings.model_copy(update={"spa_dist_dir": str(dist)}))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_index_i_trasy_vue_dostaja_index_html_bez_cache(spa_client: AsyncClient) -> None:
    async with spa_client as client:
        root = await client.get("/")
        route = await client.get("/plan-dnia")
        deep = await client.get("/l/" + "T" * 43)

    for response in (root, route, deep):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"
        assert "id=app" in response.text


async def test_head_na_spa_dziala(spa_client: AsyncClient) -> None:
    """Sondy (Caddy, monitoring) pytają HEAD — catch-all tylko-GET dawałby 405."""
    async with spa_client as client:
        response = await client.head("/")

    assert response.status_code == 200
    assert response.content == b""


async def test_assety_z_hashem_sa_immutable_a_sw_i_manifest_nie(spa_client: AsyncClient) -> None:
    """Kontrakt PWA (ADR-009): stary `sw.js` w cache = użytkownik zostaje ze starą wersją."""
    async with spa_client as client:
        asset = await client.get("/assets/index-abc123.js")
        sw = await client.get("/sw.js")
        manifest = await client.get("/manifest.webmanifest")

    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert asset.headers["content-type"].startswith("text/javascript")
    assert sw.headers["cache-control"] == "no-cache"
    assert sw.headers["content-type"].startswith("text/javascript")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.headers["cache-control"] == "no-cache"


async def test_nieznane_api_i_uploady_to_404_json_dla_kazdej_metody(
    spa_client: AsyncClient,
) -> None:
    """`/api/*` i `/uploads/*` nigdy nie dostają `index.html` — także POST/PATCH (nie 405)."""
    async with spa_client as client:
        # CSRF (double-submit) przechodzi PRZED routingiem — bez niego PATCH
        # skończyłby się 403 i nie sprawdzilibyśmy catch-alla.
        client.cookies.set("csrf_token", "x")
        get_api = await client.get(f"{API}/nope")
        patch_api = await client.patch(
            f"{API}/shopping/lists/999/itemz", headers={"X-CSRF-Token": "x"}
        )
        upload = await client.get("/uploads/recipes/nie-ma.jpg")

    for response in (get_api, patch_api):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    # `/uploads/*` istnieje jako endpoint z sesją — bez cookie to 401, nie HTML.
    assert upload.status_code == 401


async def test_mutacja_na_trasie_spa_to_405_nie_index(spa_client: AsyncClient) -> None:
    async with spa_client as client:
        client.cookies.set("csrf_token", "x")
        response = await client.post("/plan-dnia", headers={"X-CSRF-Token": "x"})

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_traversal_konczy_sie_index_html_a_nie_plikiem_spoza_dist(
    spa_client: AsyncClient,
) -> None:
    """Zbiór plików liczony przy starcie: ścieżka spoza `dist/` nigdy nie trafi w plik."""
    async with spa_client as client:
        response = await client.get("/..%2f..%2fetc/passwd")

    assert response.status_code in (200, 404)
    assert b"root:" not in response.content


def test_brak_index_html_to_blad_konfiguracji(settings: Settings, tmp_path: Path) -> None:
    """Obraz bez zbudowanego frontendu ma paść na starcie, nie pustą stroną."""
    from app.core.config import ConfigurationError

    with pytest.raises(ConfigurationError):
        create_app(settings.model_copy(update={"spa_dist_dir": str(tmp_path)}))
