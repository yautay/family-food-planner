"""Reguły middleware bezpieczeństwa bez podnoszenia aplikacji."""

from __future__ import annotations

import pytest

from app.core.middleware import (
    CSRF_EXEMPT_PREFIXES,
    SECURITY_HEADERS,
    UNSAFE_METHODS,
    CsrfMiddleware,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_metody_zmieniajace_stan_wymagaja_csrf(method: str) -> None:
    assert method in UNSAFE_METHODS


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_metody_odczytu_nie_wymagaja_csrf(method: str) -> None:
    assert method not in UNSAFE_METHODS


def test_logowanie_i_endpointy_publiczne_sa_zwolnione_z_csrf() -> None:
    """Login nie ma jeszcze sesji, `/public/*` autoryzuje token w URL (ADR-010)."""
    assert CsrfMiddleware._is_exempt("/api/v1/auth/login") is True
    assert CsrfMiddleware._is_exempt("/api/v1/public/lists/abc") is True


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/logout", "/api/v1/admin/users", "/api/v1/admin/users/1", "/api/v1/publiczne"],
)
def test_pozostale_sciezki_wymagaja_csrf(path: str) -> None:
    assert CsrfMiddleware._is_exempt(path) is False


def test_wyjatki_csrf_sa_lista_prefiksow() -> None:
    """BATCH_11 dokłada `/public/*` przez dopisanie prefiksu, nie przez if-a."""
    assert isinstance(CSRF_EXEMPT_PREFIXES, tuple)
    assert all(prefix.startswith("/api/v1/") for prefix in CSRF_EXEMPT_PREFIXES)


def test_naglowki_bezpieczenstwa_zgodne_z_07_security() -> None:
    """Wartości przepisane dosłownie z 07_SECURITY §3 — bez „ulepszania"."""
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["Referrer-Policy"] == "same-origin"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
    assert SECURITY_HEADERS["Content-Security-Policy"] == (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )


def test_csp_ma_dyrektywy_niedziedziczace_po_default_src() -> None:
    """REVIEW R4 pkt 2: `base-uri`, `form-action` i `frame-ancestors` NIE dziedziczą.

    Bez nich wstrzyknięty `<base>` przestawia ścieżki względne, a przejęty
    formularz wysyła dane na obcy host. `worker-src` świadomie NIE jest wymieniony:
    dziedziczy `'self'`, czego wymaga service worker (ADR-009).
    """
    csp = SECURITY_HEADERS["Content-Security-Policy"]
    directives = {part.strip().split(" ")[0] for part in csp.split(";") if part.strip()}

    assert {"base-uri", "form-action", "frame-ancestors", "object-src"} <= directives
    assert "base-uri 'none'" in csp
    assert "form-action 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "worker-src" not in directives
    assert "http" not in csp, "CSP bez zewnętrznych źródeł"
