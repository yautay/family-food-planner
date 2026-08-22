"""Maskowanie publicznego tokenu listy w logach (07_SECURITY §5, ADR-010).

Dwie warstwy, obie muszą maskować, bo obie piszą do stdout kontenera:

1. `mask_path()` — ścieżka w naszym logu requestów (`RequestLoggingMiddleware`).
2. `MaskPublicTokenFilter` — **access log Uvicorna**, który formatuje linię sam,
   z `record.args`, i o naszym middleware nic nie wie. Brak tej warstwy oznaczał
   token w całości w `docker compose logs app` (znalezione ręcznie w BATCH_11).
"""

from __future__ import annotations

import logging

import pytest

from app.core.logging import MaskPublicTokenFilter, install_access_log_filter, mask_path

pytestmark = pytest.mark.unit

TOKEN = "s3kretny-token-listy-zakupowej-43-znaki-abc"


def _access_record(path: str) -> logging.LogRecord:
    """Rekord w kształcie, jaki produkuje access log Uvicorna."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("172.18.0.5:60308", "GET", path, "1.1", 200),
        exc_info=None,
    )


def test_mask_path_ukrywa_token_w_sciezce_odczytu() -> None:
    """`/api/v1/public/lists/<token>` → `.../***` (prefiks `/api/v1` zostaje)."""
    assert mask_path(f"/api/v1/public/lists/{TOKEN}") == "/api/v1/public/lists/***"


def test_mask_path_ukrywa_token_ale_zostawia_reszte_sciezki() -> None:
    """Publiczny PATCH pozycji: maskujemy TOKEN, nie identyfikator pozycji."""
    assert (
        mask_path(f"/api/v1/public/lists/{TOKEN}/items/42") == "/api/v1/public/lists/***/items/42"
    )


def test_mask_path_nie_rusza_pozostalych_sciezek() -> None:
    """Maskowanie jest chirurgiczne — reszta logu musi zostać czytelna."""
    assert mask_path("/api/v1/shopping/lists/7") == "/api/v1/shopping/lists/7"


def test_filtr_access_logu_maskuje_token_w_argumentach() -> None:
    """Access log Uvicorna dostaje ścieżkę już zamaskowaną."""
    record = _access_record(f"/api/v1/public/lists/{TOKEN}")

    assert MaskPublicTokenFilter().filter(record) is True
    assert record.args is not None
    assert record.args[2] == "/api/v1/public/lists/***"  # type: ignore[index]
    assert TOKEN not in record.getMessage()


def test_filtr_access_logu_nie_zmienia_innych_rekordow() -> None:
    """Bez tokenu w ścieżce rekord zostaje nietknięty (żadnych kosztów ubocznych)."""
    record = _access_record("/api/v1/health")
    oryginalne_args = record.args

    MaskPublicTokenFilter().filter(record)

    assert record.args is oryginalne_args


def test_filtr_access_logu_przezywa_rekord_bez_argumentow() -> None:
    """Rekord spoza access logu (np. `logger.info("tekst")`) nie może wysadzić filtra."""
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="serwer wystartował",
        args=None,
        exc_info=None,
    )

    assert MaskPublicTokenFilter().filter(record) is True


def test_instalacja_filtra_jest_idempotentna() -> None:
    """`create_app()` w każdym teście nie może narastać filtrami na loggerze."""
    access_logger = logging.getLogger("uvicorn.access")
    before = [f for f in access_logger.filters if isinstance(f, MaskPublicTokenFilter)]

    install_access_log_filter()
    install_access_log_filter()

    after = [f for f in access_logger.filters if isinstance(f, MaskPublicTokenFilter)]
    assert len(after) == 1
    assert before == [] or before == after
