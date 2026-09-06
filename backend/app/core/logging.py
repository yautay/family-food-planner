"""Logowanie strukturalne (structlog) — konfiguracja + middleware requestów.

07_SECURITY §8: w logach request id, ścieżka, status, czas, docelowo user id
(NIE email). NIGDY hasła, tokeny ani payloady. Ścieżki z publicznym tokenem
listy maskowane do `/public/lists/***` i `/l/***` (ADR-010) — **także w access logu
Uvicorna** (07_SECURITY §5), który formatuje ścieżkę sam i o naszym middleware
nic nie wie.

Dev: czytelna konsola. Prod/test: JSON na stdout (zbiera Docker) — od BATCH_17
dotyczy to również rekordów stdlib (`uvicorn`, `uvicorn.access`, biblioteki):
przechodzą przez `structlog.stdlib.ProcessorFormatter` z tym samym rendererem.
Wyjątek, którego stąd nie da się usunąć: linie SUPERVISORA uvicorna
(`Started parent process`, `Child process died`) — proces nadrzędny nigdy nie
wykonuje `create_app()`, więc pisze domyślnym formatem tekstowym (09 §6).
Poziom: `LOG_LEVEL`.
"""

from __future__ import annotations

import logging
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TextIO

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

#: Dwie ścieżki niosą publiczny token listy: API (`/api/v1/public/lists/<token>`)
#: i trasa SPA (`/l/<token>`), którą od BATCH_17 serwuje BACKEND (ADR-014) — bez
#: drugiej alternatywy każde otwarcie linku wpisywałoby token do obu logów
#: (ustalenie /security-review B17).
_PUBLIC_TOKEN_PATH = re.compile(r"(/public/lists/|/l/)[^/]+")

#: Loggery Uvicorna mają WŁASNE handlery z `propagate=False` (jego `dictConfig`),
#: więc sama konfiguracja roota ich nie obejmuje — trzeba je przepiąć jawnie.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def mask_path(path: str) -> str:
    """Usuń z logowanej ścieżki publiczny token listy — token jest sekretem (07 §5)."""
    return _PUBLIC_TOKEN_PATH.sub(r"\1***", path)


class MaskPublicTokenFilter(logging.Filter):
    """Maskuje publiczny token listy w access logu Uvicorna (07_SECURITY §5).

    Nasze middleware loguje ścieżkę już zamaskowaną, ale Uvicorn ma WŁASNY
    access log i składa linię z `record.args` (`client_addr`, `method`,
    `full_path`, `http_version`, `status_code`). Bez tego filtra token wychodził
    w logach kontenera w całości — a token jest sekretem równym hasłu do listy
    (znalezione ręcznie w BATCH_11 na logach `docker compose logs app`).

    Filtr podmienia WYŁĄCZNIE ścieżkę i tylko wtedy, gdy maskowanie coś zmienia,
    więc dla pozostałych żądań rekord zostaje bitowo taki sam.
    """

    #: Pozycja `full_path` w `record.args` access logu Uvicorna.
    PATH_INDEX = 2

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) <= self.PATH_INDEX:
            return True
        path = args[self.PATH_INDEX]
        if not isinstance(path, str):
            return True
        masked = mask_path(path)
        if masked != path:
            record.args = (
                *args[: self.PATH_INDEX],
                masked,
                *args[self.PATH_INDEX + 1 :],
            )
        return True


def install_access_log_filter() -> None:
    """Podłącz maskowanie do `uvicorn.access`. Idempotentne (wołane z `create_app`).

    Bez sprawdzenia typu filtry narastałyby przy każdym `create_app()` — a testy
    tworzą aplikację dla każdego testu z osobna.
    """
    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(existing, MaskPublicTokenFilter) for existing in access_logger.filters):
        return
    access_logger.addFilter(MaskPublicTokenFilter())


#: Wspólne procesory OBU strumieni (structlog i stdlib) — jedna definicja, żeby
#: `docker logs` miało jeden kształt znacznika czasu i wyjątku.
_TIMESTAMPER = structlog.processors.TimeStamper(fmt="iso", utc=True)


def _renderer(app_env: str) -> structlog.typing.Processor:
    if app_env == "dev":
        return structlog.dev.ConsoleRenderer()
    return structlog.processors.JSONRenderer()


def _stdlib_handler(app_env: str, level: int, stream: TextIO) -> logging.Handler:
    """Handler dla rekordów stdlib: w prod/test JSON tym samym rendererem co structlog."""
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    if app_env == "dev":
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _renderer(app_env),
            ],
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                _TIMESTAMPER,
                # Bez tego `exc_info` rekordu (np. „Exception in ASGI application")
                # trafiłoby do JSON-a jako surowa krotka z adresem obiektu traceback,
                # a jedyny ślad awarii protokołu/middleware znikałby z `docker logs`.
                structlog.processors.format_exc_info,
            ],
        )
    )
    return handler


def configure_logging(
    *, app_env: str, log_level: str = "INFO", stream: TextIO | None = None
) -> None:
    """Skonfiguruj structlog i stdlib logging. Idempotentne — wołane z `create_app`.

    `stream` istnieje dla testów (przechwycenie wyjścia); produkcja pisze na stdout.
    """
    level = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)
    out = stream or sys.stdout

    handler = _stdlib_handler(app_env, level, out)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    install_access_log_filter()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _TIMESTAMPER,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _renderer(app_env),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=out),
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
