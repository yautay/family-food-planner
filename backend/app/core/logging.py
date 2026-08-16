"""Logowanie strukturalne (structlog) — konfiguracja + middleware requestów.

07_SECURITY §8: w logach request id, ścieżka, status, czas, docelowo user id
(NIE email). NIGDY hasła, tokeny ani payloady. Ścieżki z publicznym tokenem
listy maskowane do `/public/lists/***` (ADR-010).
Dev: czytelna konsola. Prod/test: JSON na stdout (zbiera Docker).
"""

from __future__ import annotations

import logging
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

_PUBLIC_TOKEN_PATH = re.compile(r"(/public/lists/)[^/]+")


def mask_path(path: str) -> str:
    """Usuń z logowanej ścieżki publiczny token listy — token jest sekretem (07 §5)."""
    return _PUBLIC_TOKEN_PATH.sub(r"\1***", path)


def configure_logging(*, app_env: str, log_level: str = "INFO") -> None:
    """Skonfiguruj structlog i stdlib logging. Idempotentne — wołane z `create_app`."""
    level = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)

    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer() if app_env == "dev" else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Jedna linia logu na request: metoda, ścieżka (maskowana), status, czas."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        logger = structlog.get_logger("app.request")
        started = time.perf_counter()
        path = mask_path(request.url.path)

        # bound_contextvars (a nie clear_contextvars) — sprząta wyłącznie własne
        # klucze, więc nie kasuje np. user_id wiązanego przez auth (B02).
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "request_failed",
                    method=request.method,
                    path=path,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                raise
            logger.info(
                "request",
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
