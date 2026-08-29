"""Jeden kształt błędu dla całego API (04_API §1).

    {"error": {"code": "not_found", "message": "…po polsku…", "details": {...}}}

Kody: validation_error (422), unauthorized (401), forbidden (403),
not_found (404), conflict (409), rate_limited (429), internal_error (500).
Użytkownik nigdy nie dostaje stacktrace'u — do logów idzie wyjątek, do
odpowiedzi identyfikator błędu (07_SECURITY §8).
"""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)

STATUS_TO_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    422: "validation_error",
    429: "rate_limited",
}

DEFAULT_MESSAGES: dict[int, str] = {
    400: "Nieprawidłowe żądanie.",
    401: "Wymagane zalogowanie.",
    403: "Brak uprawnień do tej operacji.",
    404: "Nie znaleziono zasobu.",
    405: "Metoda niedozwolona dla tego zasobu.",
    409: "Operacja jest w konflikcie z aktualnym stanem danych.",
    410: "Ten zasób nie jest już dostępny.",
    422: "Dane w żądaniu są nieprawidłowe.",
    429: "Zbyt wiele żądań. Spróbuj ponownie za chwilę.",
    500: "Wystąpił nieoczekiwany błąd. Spróbuj ponownie później.",
}


class ErrorBody(BaseModel):
    """Treść błędu."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"code": "not_found", "message": "Nie znaleziono zasobu.", "details": {}}
        }
    )

    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    """Koperta błędu zwracana przez wszystkie endpointy."""

    error: ErrorBody


class AppError(Exception):
    """Błąd domenowy mapowany na kontrakt API. Serwisy rzucają podklasy, nie HTTPException."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.message = message or DEFAULT_MESSAGES.get(self.status_code, DEFAULT_MESSAGES[500])
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    """404 — zasób nie istnieje ALBO jest poza scope użytkownika (07_SECURITY §4)."""

    status_code = 404
    code = "not_found"


class ForbiddenError(AppError):
    """403 — zasób widoczny, ale operacja niedozwolona."""

    status_code = 403
    code = "forbidden"


class UnauthorizedError(AppError):
    """401 — brak ważnej sesji."""

    status_code = 401
    code = "unauthorized"


class ConflictError(AppError):
    """409 — np. blokada usunięcia; `details.used_in` z listą użyć (04_API §1)."""

    status_code = 409
    code = "conflict"


class GoneError(AppError):
    """410 — zasób ISTNIAŁ, ale przestał być dostępny (wygasły/odwołany token, ADR-010).

    Świadomie osobny kod od 404: publiczny link listy zakupowej musi umieć
    powiedzieć „to już wygasło" zamiast „nie ma czegoś takiego", bo pierwsze jest
    prawdą i podpowiada, co zrobić dalej (poprosić o nowy link). Sama TREŚĆ
    komunikatu jest dla 404 i 410 identyczna — użytkownik nie dowiaduje się, czy
    token kiedykolwiek istniał (karta B11, Implementation Notes pkt 5).
    """

    status_code = 410
    code = "gone"


class ServiceUnavailableError(AppError):
    """503 — funkcja istnieje, ale ta instancja jej nie ma włączonej (BATCH_16).

    Pierwszy konsument: AI-asysta importu PDF. Brak `ANTHROPIC_API_KEY` to
    świadomie wspierany tryb pracy (ADR-011), a nie awaria ani błąd żądania —
    stąd 503 z komunikatem, co użytkownik może zrobić zamiast tego, a nie 404
    (endpoint istnieje) ani 500 (nic się nie zepsuło).
    """

    status_code = 503
    code = "service_unavailable"


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Zbuduj odpowiedź w kontrakcie 04_API §1."""
    payload = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Błędy domenowe (AppError i podklasy)."""
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


def _standard_phrase(status_code: int) -> str | None:
    """Domyślny angielski `detail` Starlette dla danego statusu (albo None)."""
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return None


async def http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """HTTPException Starlette/FastAPI — w tym 404 dla nieistniejącej ścieżki."""
    assert isinstance(exc, StarletteHTTPException)
    code = STATUS_TO_CODE.get(exc.status_code, "error")
    # Własny komunikat z `HTTPException(detail=...)` wygrywa, ale angielskiej
    # frazy domyślnej Starlette nie przepuszczamy — UI jest po polsku.
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    if detail == _standard_phrase(exc.status_code):
        detail = None
    message = detail or DEFAULT_MESSAGES.get(exc.status_code) or DEFAULT_MESSAGES[500]
    return error_response(exc.status_code, code, message)


async def validation_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """422 — błędy walidacji Pydantic zmapowane na pola (frontend podpina je pod formularz)."""
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return error_response(
        422,
        "validation_error",
        DEFAULT_MESSAGES[422],
        {"fields": fields},
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """500 — stacktrace do logów, użytkownik dostaje identyfikator błędu."""
    error_id = uuid.uuid4().hex[:12]
    logger.exception("unhandled_exception", error_id=error_id, exc_type=type(exc).__name__)
    return error_response(500, "internal_error", DEFAULT_MESSAGES[500], {"error_id": error_id})


async def rate_limit_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """429 ze slowapi — komunikat po polsku zamiast surowego opisu limitu.

    `RateLimitExceeded` dziedziczy po `HTTPException`, więc bez tego handlera
    użytkownik dostałby w `message` angielskie „5 per 1 minute".
    """
    return error_response(429, "rate_limited", DEFAULT_MESSAGES[429])


def register_error_handlers(app: FastAPI) -> None:
    """Podłącz handlery do aplikacji (wołane z `create_app`)."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def register_rate_limit_handler(app: FastAPI) -> None:
    """Handler 429 dla slowapi — osobno, bo ma sens tylko z zainstalowanym limiterem."""
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
