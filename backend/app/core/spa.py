"""Serwowanie zbudowanego SPA przez backend (ADR-014) — obraz prod (BATCH_17).

Jeden kontener `app`: FastAPI obsługuje `/api/v1/*`, `/uploads/*` (z sesją)
i resztę ścieżek jako pliki z `dist/` z fallbackiem na `index.html` dla tras
routera Vue. Świadomie NIE `StaticFiles(html=True)`: montowanie katalogu pod `/`
odpowiadałoby `index.html` także na nieznane `/api/v1/...` i `/uploads/...`,
zamieniając kontraktowe 404 JSON w stronę HTML.

Nagłówki cache są częścią kontraktu PWA (ADR-009, karta B18 „trzy
sprawdzenia"): pliki z `assets/` mają hash w nazwie i mogą być `immutable`,
ale `index.html`, `sw.js`, `workbox-*.js` i `manifest.webmanifest` MUSZĄ być
`no-cache` — inaczej po wdrożeniu użytkownicy zostają ze starym service
workerem i starą wersją aplikacji.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.core.config import ConfigurationError
from app.core.errors import AppError, NotFoundError

# Starlette zgaduje typ po rozszerzeniu z rejestru `mimetypes`; `.webmanifest`
# nie ma w nim wpisu, a przeglądarka bez `application/manifest+json` nie
# zaproponuje instalacji PWA (karta B17, „Do przeglądu z B12" pkt 2).
mimetypes.add_type("application/manifest+json", ".webmanifest")
# Na hostach z egzotycznym rejestrem (Windows) `.js` bywa `text/plain` — moduły
# ES wymagają typu JavaScript, inaczej przeglądarka odmawia ich wykonania.
mimetypes.add_type("text/javascript", ".js")

#: Prefiksy obsługiwane przez API — nigdy fallback na `index.html`.
RESERVED_PREFIXES = ("api", "uploads")

#: Podkatalog z plikami o nazwach z hashem (Vite) — jedyne, co wolno cache'ować agresywnie.
IMMUTABLE_SUBDIR = "assets"

CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "no-cache"

#: Catch-all jest rejestrowany dla WSZYSTKICH metod: route tylko-GET dawałby
#: 405 zamiast kontraktowego 404 dla `POST /api/v1/nieznane` (Starlette traktuje
#: dopasowaną ścieżkę z inną metodą jako 405) i 405 dla `HEAD /` (sondy).
ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


class MethodNotAllowedError(AppError):
    """405 — ścieżka SPA istnieje, ale przyjmuje tylko GET/HEAD."""

    status_code = 405
    code = "method_not_allowed"


def build_spa_router(dist_dir: Path) -> APIRouter:
    """Router catch-all — rejestrować JAKO OSTATNI, po wszystkich routerach API.

    Zawartość `dist/` jest niezmienna przez życie procesu (siedzi w obrazie), więc
    zbiór plików liczymy RAZ przy starcie: obsługa żądania to sprawdzenie
    w `frozenset`, bez `resolve()`/`stat()` na pętli zdarzeń i bez własnej
    logiki anty-traversal — ścieżki spoza zbioru dostają `index.html`.
    """
    root = dist_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise ConfigurationError(
            "SPA_DIST_DIR wskazuje katalog bez index.html — zbuduj frontend "
            "(`task fe-build`) albo wyczyść zmienną, jeśli backend ma nie serwować SPA."
        )
    files = frozenset(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    router = APIRouter(include_in_schema=False)

    @router.api_route("/{full_path:path}", methods=ALL_METHODS)
    async def serve_spa(full_path: str, request: Request) -> FileResponse:
        first = PurePosixPath(full_path).parts[0] if full_path else ""
        if first in RESERVED_PREFIXES:
            # Nieznana ścieżka API/uploadów — 404 w kształcie kontraktu, nie HTML.
            raise NotFoundError()
        if request.method not in ("GET", "HEAD"):
            raise MethodNotAllowedError()
        if full_path in files:
            cache = CACHE_IMMUTABLE if first == IMMUTABLE_SUBDIR else CACHE_REVALIDATE
            return FileResponse(root / full_path, headers={"Cache-Control": cache})
        # Trasa routera Vue (`/plan-dnia`, `/l/<token>`) — SPA rozstrzyga ją sama.
        return FileResponse(index, headers={"Cache-Control": CACHE_REVALIDATE})

    return router
