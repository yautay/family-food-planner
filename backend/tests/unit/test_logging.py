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


def test_w_prod_rekordy_stdlib_wychodza_jako_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """BATCH_17: access log Uvicorna i biblioteki renderują się tym samym JSON-em co structlog.

    Sprawdzamy jednocześnie, że maskowanie tokenu działa PRZED renderowaniem —
    w JSON-ie nie ma pełnego tokenu, jest `***`.
    """
    import io
    import json
    import logging

    from app.core.logging import configure_logging

    stream = io.StringIO()
    configure_logging(app_env="prod", log_level="INFO", stream=stream)
    try:
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:1",
            "GET",
            "/api/v1/public/lists/" + "T" * 43,
            "1.1",
            200,
        )
    finally:
        # Przywracamy konfigurację testową, żeby nie zmieniać wyjścia pozostałych testów.
        configure_logging(app_env="test", log_level="INFO")

    line = stream.getvalue().strip().splitlines()[-1]
    record = json.loads(line)
    assert record["logger"] == "uvicorn.access"
    assert record["level"] == "info"
    assert "/api/v1/public/lists/***" in record["event"]
    assert "T" * 43 not in line


def test_w_dev_rekordy_stdlib_zostaja_czytelnym_tekstem() -> None:
    import io
    import logging

    from app.core.logging import configure_logging

    stream = io.StringIO()
    configure_logging(app_env="dev", log_level="INFO", stream=stream)
    try:
        logging.getLogger("uvicorn.error").info("Application startup complete.")
    finally:
        configure_logging(app_env="test", log_level="INFO")

    assert stream.getvalue().strip() == "Application startup complete."


def test_w_prod_traceback_rekordu_stdlib_trafia_do_json() -> None:
    """`exc_info` z „Exception in ASGI application" ma być czytelnym tekstem, nie krotką."""
    import io
    import json
    import logging

    from app.core.logging import configure_logging

    stream = io.StringIO()
    configure_logging(app_env="prod", log_level="INFO", stream=stream)
    try:
        try:
            1 / 0
        except ZeroDivisionError:
            logging.getLogger("uvicorn.error").exception("Exception in ASGI application")
    finally:
        configure_logging(app_env="test", log_level="INFO")

    record = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert record["level"] == "error"
    assert "ZeroDivisionError" in record["exception"]
    assert "Traceback" in record["exception"]
    assert "exc_info" not in record


def test_mask_path_ukrywa_token_takze_w_trasie_spa() -> None:
    """Od B17 backend serwuje SPA, więc `GET /l/<token>` trafia do obu logów (07_SECURITY §5)."""
    token = "T" * 43

    assert mask_path(f"/l/{token}") == "/l/***"
    assert mask_path(f"/l/{token}?x=1") == "/l/***"
    assert mask_path("/login") == "/login"
    assert mask_path("/plan-dnia") == "/plan-dnia"


def test_filtr_access_logu_maskuje_token_trasy_spa() -> None:
    """Access log Uvicorna widzi też trasę SPA — od B17 serwuje ją backend."""
    record = _access_record(f"/l/{TOKEN}")

    assert MaskPublicTokenFilter().filter(record) is True
    assert record.args is not None
    assert record.args[2] == "/l/***"  # type: ignore[index]
    assert TOKEN not in record.getMessage()
