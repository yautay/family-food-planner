"""Cookies sesji i CSRF — jedno miejsce ustawiania atrybutów (07_SECURITY §2 i §3).

Router używa tego przy logowaniu i wylogowaniu, dependency `current_user` —
przy przesuwaniu TTL. Rozjazd atrybutów między tymi ścieżkami kasowałby cookie
zamiast je odświeżać, więc mieszkają razem.
"""

from __future__ import annotations

from typing import Literal

from starlette.responses import Response

from app.core.config import Settings
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, SESSION_TTL

COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"


def cookies_are_secure(settings: Settings) -> bool:
    """Flaga `Secure` — w prod zawsze, w dev nie (http://localhost nie ma TLS)."""
    return settings.app_env == "prod"


def set_session_cookies(
    response: Response, *, session_id: str, csrf_token: str, settings: Settings
) -> None:
    """Cookie sesji (HttpOnly) + cookie CSRF (czytelne dla JS, double-submit)."""
    secure = cookies_are_secure(settings)
    max_age = int(SESSION_TTL.total_seconds())
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )


def clear_session_cookies(response: Response, *, settings: Settings) -> None:
    """Wylogowanie — kasujemy oba cookies po stronie przeglądarki."""
    secure = cookies_are_secure(settings)
    for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(
            name,
            path=COOKIE_PATH,
            httponly=False,
            secure=secure,
            samesite=COOKIE_SAMESITE,
        )
