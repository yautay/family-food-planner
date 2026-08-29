"""Composition root aplikacji: app factory, middleware, routery, handlery błędów.

Zero logiki domenowej — moduły domenowe (`app/modules/...`) dostarczają
kolejne batche i rejestrują tu swoje routery.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import Settings, get_settings
from app.core.deps import CurrentUser
from app.core.errors import (
    ErrorResponse,
    NotFoundError,
    register_error_handlers,
    register_rate_limit_handler,
)
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.middleware import CsrfMiddleware, SecurityHeadersMiddleware
from app.core.uploads import FILE_NOT_FOUND_MESSAGE, resolve_upload_path
from app.modules.accounts.router import build_admin_users_router, build_auth_router
from app.modules.audit.router import build_audit_router
from app.modules.catalog.router import (
    build_categories_router,
    build_products_router,
    build_retail_products_router,
    build_stores_router,
)
from app.modules.households.router import build_admin_households_router, build_households_router
from app.modules.importer.router import build_import_router
from app.modules.nutrition.router import build_goals_router
from app.modules.pantry.router import build_pantry_router
from app.modules.planning.router import (
    build_cycles_router,
    build_plan_router,
    build_stats_router,
    build_templates_router,
)
from app.modules.recipes.router import build_recipes_router, build_tags_router
from app.modules.shopping.lists_router import build_shopping_lists_router
from app.modules.shopping.public_router import build_public_lists_router
from app.modules.shopping.router import build_shopping_router
from app.modules.transfer.router import build_transfer_router

API_V1_PREFIX = "/api/v1"


class HealthResponse(BaseModel):
    """Odpowiedź healthchecku — świadomie nie ujawnia niczego poza statusem i wersją."""

    status: str
    version: str


def build_health_router(settings: Settings) -> APIRouter:
    """Router `/health` — publiczny, bez sesji (04_API §3 pkt 1)."""
    router = APIRouter(tags=["health"])

    @router.get("/health", response_model=HealthResponse, summary="Stan aplikacji")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=settings.app_version)

    return router


def build_uploads_router(settings: Settings) -> APIRouter:
    """Serwowanie uploadów — POZA `/api/v1` (01_ARCH §1), ZAWSZE z sesją.

    Świadomie nie StaticFiles: montowanie katalogu omijałoby autoryzację
    (07_SECURITY §6). `resolve_upload_path` odrzuca ścieżki spoza katalogu
    uploadów identycznym 404 jak dla pliku, którego nie ma.
    """
    router = APIRouter(tags=["uploads"])
    uploads_root = Path(settings.uploads_dir)

    @router.get("/uploads/{file_path:path}", summary="Plik uploadu (wymaga sesji)")
    async def serve_upload(file_path: str, user: CurrentUser) -> FileResponse:
        resolved = resolve_upload_path(file_path, uploads_root=uploads_root)
        if not resolved.is_file():
            raise NotFoundError(FILE_NOT_FOUND_MESSAGE)
        # Nazwy plików to uuid4 — treść pod URL-em nigdy się nie zmienia, więc
        # przeglądarka może cache'ować agresywnie (private: odpowiedź za sesją).
        return FileResponse(
            resolved, headers={"Cache-Control": "private, max-age=31536000, immutable"}
        )

    return router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Zbuduj aplikację FastAPI. Jedyne miejsce składania zależności."""
    settings = settings or get_settings()
    configure_logging(app_env=settings.app_env, log_level=settings.log_level)

    app = FastAPI(
        title="Family Food Planner API",
        version=settings.app_version,
        description="API planera żywienia rodzinnego. Kontrakt dla frontendu (task fe-types).",
        docs_url="/api/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.app_env != "prod" else None,
        responses={"default": {"model": ErrorResponse, "description": "Błąd"}},
    )
    app.state.settings = settings

    # Limiter per aplikacja (nie globalny): każda instancja ma własny licznik,
    # więc testy nie zatruwają się nawzajem, a slowapi wymaga go w `app.state`.
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter

    # Kolejność ma znaczenie: dodane później są bardziej „na zewnątrz". Nagłówki
    # bezpieczeństwa muszą objąć także odpowiedzi odrzucone przez CSRF.
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    register_error_handlers(app)
    register_rate_limit_handler(app)

    app.include_router(build_health_router(settings), prefix=API_V1_PREFIX)
    app.include_router(build_auth_router(settings, limiter), prefix=API_V1_PREFIX)
    app.include_router(build_admin_users_router(), prefix=API_V1_PREFIX)
    app.include_router(build_households_router(), prefix=API_V1_PREFIX)
    app.include_router(build_admin_households_router(), prefix=API_V1_PREFIX)
    app.include_router(build_products_router(), prefix=API_V1_PREFIX)
    app.include_router(build_categories_router(), prefix=API_V1_PREFIX)
    app.include_router(build_stores_router(), prefix=API_V1_PREFIX)
    app.include_router(build_retail_products_router(), prefix=API_V1_PREFIX)
    app.include_router(build_recipes_router(), prefix=API_V1_PREFIX)
    app.include_router(build_tags_router(), prefix=API_V1_PREFIX)
    app.include_router(build_goals_router(), prefix=API_V1_PREFIX)
    app.include_router(build_plan_router(), prefix=API_V1_PREFIX)
    app.include_router(build_templates_router(), prefix=API_V1_PREFIX)
    app.include_router(build_cycles_router(), prefix=API_V1_PREFIX)
    app.include_router(build_stats_router(), prefix=API_V1_PREFIX)
    app.include_router(build_pantry_router(), prefix=API_V1_PREFIX)
    app.include_router(build_shopping_router(), prefix=API_V1_PREFIX)
    app.include_router(build_shopping_lists_router(), prefix=API_V1_PREFIX)
    # Router publiczny MUSI siedzieć pod `/api/v1/public/` — dokładnie ten prefiks
    # jest zwolniony z CSRF (`CSRF_EXEMPT_PREFIXES`) i tylko on jest maskowany
    # w logach (`mask_path`). Limiter wstrzykujemy jak w `/auth` (ADR-010).
    app.include_router(build_public_lists_router(limiter), prefix=API_V1_PREFIX)
    app.include_router(build_import_router(), prefix=API_V1_PREFIX)
    app.include_router(build_transfer_router(), prefix=API_V1_PREFIX)
    app.include_router(build_audit_router(), prefix=API_V1_PREFIX)
    # Uploady poza /api/v1 (01_ARCH §1) — endpoint z sesją, nie StaticFiles.
    app.include_router(build_uploads_router(settings))

    return app


# Aplikacja NIE jest tworzona na poziomie modułu: import `app.main` nie może
# wymagać kompletnej konfiguracji (eksport OpenAPI, testy jednostkowe).
# Uruchomienie: `uvicorn app.main:create_app --factory`.
