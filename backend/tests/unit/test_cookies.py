"""Nazwy i atrybuty cookies sesji/CSRF zależne od środowiska (BATCH_17, REVIEW R4 pkt 6)."""

from __future__ import annotations

import pytest
from starlette.responses import Response

from app.core.config import AppEnv, Settings
from app.core.cookies import (
    HOST_PREFIX,
    clear_session_cookies,
    csrf_cookie_name,
    session_cookie_name,
    set_session_cookies,
)
from app.core.db import get_engine
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME

pytestmark = pytest.mark.unit


def _settings(app_env: AppEnv) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/x", secret_key="x", app_env=app_env
    )


@pytest.mark.parametrize("app_env", ["dev", "test"])
def test_bez_tls_cookies_maja_gole_nazwy(app_env: AppEnv) -> None:
    """`__Host-` WYMAGA `Secure`, a http://localhost go nie ma — prefiks by wyłączył logowanie."""
    settings = _settings(app_env)

    assert session_cookie_name(settings) == SESSION_COOKIE_NAME
    assert csrf_cookie_name(settings) == CSRF_COOKIE_NAME


def test_w_prod_cookies_maja_prefiks_host() -> None:
    """Prefiks wiąże cookie z jednym hostem: bez `Domain`, `Path=/`, `Secure` (07_SECURITY §3)."""
    settings = _settings("prod")

    assert session_cookie_name(settings) == f"{HOST_PREFIX}{SESSION_COOKIE_NAME}"
    assert csrf_cookie_name(settings) == f"{HOST_PREFIX}{CSRF_COOKIE_NAME}"


def test_set_cookie_w_prod_spelnia_wymagania_prefiksu_host() -> None:
    """`__Host-` jest odrzucane przez przeglądarkę bez `Secure`, z `Domain` albo `Path` ≠ `/`."""
    response = Response()
    set_session_cookies(response, session_id="sid", csrf_token="csrf", settings=_settings("prod"))

    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 2
    for header in headers:
        assert header.startswith(HOST_PREFIX)
        assert "Secure" in header
        assert "Path=/" in header
        assert "Domain=" not in header
    session_header = next(h for h in headers if h.startswith(f"{HOST_PREFIX}{SESSION_COOKIE_NAME}"))
    assert "HttpOnly" in session_header


def test_wylogowanie_kasuje_cookies_pod_ta_sama_nazwa() -> None:
    """Rozjazd nazw między set i clear zostawiłby żywe cookie po wylogowaniu."""
    response = Response()
    clear_session_cookies(response, settings=_settings("prod"))

    names = {h.split("=", 1)[0] for h in response.headers.getlist("set-cookie")}
    assert names == {f"{HOST_PREFIX}{SESSION_COOKIE_NAME}", f"{HOST_PREFIX}{CSRF_COOKIE_NAME}"}


def test_silnik_bazy_ukrywa_parametry_w_komunikatach_bledow() -> None:
    """REVIEW R4 pkt 7: `DBAPIError` bez `[parameters: ...]` — inaczej INSERT do `sessions`
    wypisałby token sesji do logu razem z tracebackiem (07_SECURITY §8)."""
    engine = get_engine()

    assert engine.sync_engine.hide_parameters is True
