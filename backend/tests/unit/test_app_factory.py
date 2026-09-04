"""App factory — smoke: aplikacja składa się i ma zarejestrowany health."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import API_V1_PREFIX, create_app

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@localhost:5432/pasnik",
        "secret_key": "sekret",
        "app_env": "test",
        "app_version": "9.9.9",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_tworzy_aplikacje_fastapi() -> None:
    app = create_app(_settings())

    assert isinstance(app, FastAPI)
    assert app.version == "9.9.9"


def test_rejestruje_router_health_pod_prefiksem_v1() -> None:
    """Health musi być pod /api/v1/health — healthcheck compose zna ten adres."""
    schema = create_app(_settings()).openapi()

    assert f"{API_V1_PREFIX}/health" in schema["paths"]


def test_kontrakt_bledu_jest_w_openapi() -> None:
    """Frontend generuje typ błędu z OpenAPI (04_API §1) — schemat musi tam być."""
    schema = create_app(_settings()).openapi()

    assert "ErrorResponse" in schema["components"]["schemas"]


def test_dokumentacja_wylaczona_na_produkcji() -> None:
    """Prod nie wystawia /api/docs ani schematu OpenAPI."""
    app = create_app(_settings(app_env="prod"))

    assert app.docs_url is None
    assert app.openapi_url is None
