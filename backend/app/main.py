"""Composition root aplikacji: app factory, middleware, routery, handlery błędów.

Zero logiki domenowej — moduły domenowe (`app/modules/...`) dostarczają
kolejne batche i rejestrują tu swoje routery.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse, register_error_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging

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

    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)

    app.include_router(build_health_router(settings), prefix=API_V1_PREFIX)

    return app


# Aplikacja NIE jest tworzona na poziomie modułu: import `app.main` nie może
# wymagać kompletnej konfiguracji (eksport OpenAPI, testy jednostkowe).
# Uruchomienie: `uvicorn app.main:create_app --factory`.
