"""Sufit rozmiaru ciała żądania (BATCH_17) — dobór limitu per ścieżka, bez HTTP."""

from __future__ import annotations

import pytest

from app.core.body_limit import (
    MIB,
    UPLOAD_BODY_MARGIN_BYTES,
    BodyLimitMiddleware,
    build_body_limit_rules,
    too_large_message,
)
from app.core.config import Settings

pytestmark = pytest.mark.unit


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/x",
        secret_key="x",
        transfer_max_zip_mb=100,
        image_max_upload_mb=10,
        request_max_body_mb=2,
    )


def _middleware() -> BodyLimitMiddleware:
    settings = _settings()

    async def noop(scope: object, receive: object, send: object) -> None:  # pragma: no cover
        return None

    return BodyLimitMiddleware(
        noop,
        default_limit_mb=settings.request_max_body_mb,
        rules=build_body_limit_rules(settings),
    )


@pytest.mark.parametrize(
    ("path", "limit_mb"),
    [
        ("/api/v1/transfer/import", 100),
        ("/api/v1/recipes/7/photo", 10),
        ("/api/v1/retail-products/12/photo", 10),
    ],
)
def test_endpointy_uploadu_maja_wlasny_limit_z_marginesem_multiparta(
    path: str, limit_mb: int
) -> None:
    """Limit = wartość z `Settings` + margines na nagłówki multiparta (07_SECURITY §6)."""
    declared, in_bytes = _middleware().limit_for(path)

    assert declared == limit_mb
    assert in_bytes == limit_mb * MIB + UPLOAD_BODY_MARGIN_BYTES


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/login",
        "/api/v1/recipes",
        "/api/v1/recipes/7",  # nie `/photo`
        "/api/v1/recipes/abc/photo",  # id musi być liczbą
        "/api/v1/transfer/import/3/apply",  # apply nie jest uploadem
        "/api/v1/transfer/importx",  # prefiks to nie ta sama trasa
    ],
)
def test_pozostale_sciezki_dostaja_sufit_domyslny(path: str) -> None:
    declared, in_bytes = _middleware().limit_for(path)

    assert declared == 2
    assert in_bytes == 2 * MIB


def test_komunikat_413_podaje_limit_w_megabajtach_po_polsku() -> None:
    assert too_large_message(25) == "Żądanie jest za duże — limit dla tej operacji to 25 MB."


def test_reguly_pochodza_z_konfiguracji_a_nie_z_drugiej_listy() -> None:
    """Zmiana `TRANSFER_MAX_ZIP_MB` w env musi przestawić sufit middleware bez zmiany kodu."""
    settings = _settings().model_copy(update={"transfer_max_zip_mb": 40})

    zip_rule = next(
        r for r in build_body_limit_rules(settings) if "transfer/import" in r.pattern.pattern
    )

    assert zip_rule.limit_mb == 40


def test_kazdy_endpoint_z_uploadfile_ma_regule_limitu() -> None:
    """Reguły w `build_body_limit_rules` to druga tabela tras — ten test pilnuje,
    żeby nowy endpoint uploadu (multipart z plikiem) nie został z sufitem 2 MB.

    Źródłem prawdy jest OpenAPI aplikacji: operacja z `requestBody` typu
    `multipart/form-data` to upload (niezależnie od wewnętrznej struktury tras
    FastAPI, która zmienia się między wersjami).
    """
    import re

    from app.main import create_app

    settings = _settings()
    schema = create_app(settings).openapi()
    middleware = BodyLimitMiddleware(
        lambda s, r, se: None,  # type: ignore[arg-type,return-value]
        default_limit_mb=settings.request_max_body_mb,
        rules=build_body_limit_rules(settings),
    )
    upload_paths = sorted(
        re.sub(r"\{[^}]+\}", "1", path)
        for path, operations in schema["paths"].items()
        for operation in operations.values()
        if "multipart/form-data" in operation.get("requestBody", {}).get("content", {})
    )

    assert len(upload_paths) == 3, upload_paths
    for path in upload_paths:
        declared, _ = middleware.limit_for(path)
        assert declared != settings.request_max_body_mb, f"{path} bez reguły uploadu"
