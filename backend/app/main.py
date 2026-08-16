"""Composition root aplikacji: app factory, middleware, routery, handlery błędów.

Zero logiki domenowej — moduły domenowe (`app/modules/...`) dostarczają
kolejne batche i rejestrują tu swoje routery.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse, register_error_handlers, register_rate_limit_handler
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.middleware import CsrfMiddleware, SecurityHeadersMiddleware
from app.modules.accounts.router import build_admin_users_router, build_auth_router
from app.modules.audit.router import build_audit_router
from app.modules.catalog.router import build_categories_router, build_products_router
from app.modules.households.router import build_admin_households_router, build_households_router

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
    app.include_router(build_audit_router(), prefix=API_V1_PREFIX)

    return app


# Aplikacja NIE jest tworzona na poziomie modułu: import `app.main` nie może
# wymagać kompletnej konfiguracji (eksport OpenAPI, testy jednostkowe).
# Uruchomienie: `uvicorn app.main:create_app --factory`.
