"""Kontrakt błędu 04_API §1 — mapowanie wyjątków na odpowiedź."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.errors import (
    ConflictError,
    NotFoundError,
    app_error_handler,
    http_exception_handler,
)
from app.core.logging import mask_path

pytestmark = pytest.mark.unit


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/v1/test", "headers": []})


def _body(response: Any) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(response.body)
    return parsed


async def test_appError_mapuje_sie_na_kod_i_status() -> None:
    response = await app_error_handler(_request(), NotFoundError())

    assert response.status_code == 404
    assert _body(response)["error"]["code"] == "not_found"


async def test_konflikt_przenosi_liste_uzyc() -> None:
    """409 przy blokadzie usunięcia niesie `details.used_in` (04_API §1)."""
    error = ConflictError(
        "Nie można usunąć produktu — jest używany.",
        details={"used_in": [{"type": "recipe", "id": 7, "name": "Gołąbki"}]},
    )

    response = await app_error_handler(_request(), error)

    body = _body(response)
    assert response.status_code == 409
    assert body["error"]["details"]["used_in"][0]["name"] == "Gołąbki"


async def test_wlasny_komunikat_httpexception_trafia_do_odpowiedzi() -> None:
    """Gdy ktoś poda własny `detail`, użytkownik ma zobaczyć właśnie jego."""
    exc = HTTPException(status_code=404, detail="Przepis nie istnieje albo został usunięty.")

    response = await http_exception_handler(_request(), exc)

    assert _body(response)["error"]["message"] == "Przepis nie istnieje albo został usunięty."


async def test_domyslna_fraza_starlette_jest_zastapiona_polskim_komunikatem() -> None:
    """Bez własnego detailu Starlette wstawia angielskie „Not Found" — UI jest PL."""
    response = await http_exception_handler(_request(), HTTPException(status_code=404))

    assert _body(response)["error"]["message"] == "Nie znaleziono zasobu."


def test_maskowanie_sciezki_z_publicznym_tokenem() -> None:
    """Token listy nie może trafić do logów (07_SECURITY §5)."""
    assert mask_path("/api/v1/public/lists/AbCdEf123") == "/api/v1/public/lists/***"
    assert mask_path("/api/v1/health") == "/api/v1/health"
