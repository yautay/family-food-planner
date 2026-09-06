"""Cookies sesji i CSRF — jedno miejsce ustawiania NAZW i atrybutów (07_SECURITY §2 i §3).

Router używa tego przy logowaniu i wylogowaniu, dependency `current_user` —
przy odczycie i przesuwaniu TTL, middleware CSRF — przy porównaniu double-submit.
Rozjazd atrybutów między tymi ścieżkami kasowałby cookie zamiast je odświeżać,
a rozjazd NAZW wylogowałby wszystkich, więc mieszkają razem.

**Prefiks `__Host-` (BATCH_17, ustalenie REVIEW R4 pkt 6).** Double-submit
czyta PIERWSZE cookie o danej nazwie z `document.cookie`, więc subdomena albo
sąsiad na tej samej domenie rejestrowalnej mógłby przypiąć własną parę
cookie + nagłówek. Prefiks `__Host-` każe przeglądarce odrzucić cookie, które
nie ma `Secure`, ma `Domain` albo `Path` inny niż `/` — czyli wiąże je
z dokładnie jednym hostem. `__Host-` WYMAGA `Secure`, a `http://localhost` go
nie ma, więc prefiks włącza się razem z flagą `Secure` (`APP_ENV=prod`).
Frontend nie zna nazwy z literału: sprawdza obie kandydatki (`client.ts`).
"""

from __future__ import annotations

from typing import Literal

from starlette.responses import Response

from app.core.config import Settings
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, SESSION_TTL

COOKIE_PATH = "/"
COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

#: Prefiks nazwy cookie wiążący je z jednym hostem (RFC 6265bis §4.1.3.2).
HOST_PREFIX = "__Host-"


def cookies_are_secure(settings: Settings) -> bool:
    """Flaga `Secure` — w prod zawsze, w dev nie (http://localhost nie ma TLS)."""
    return settings.app_env == "prod"


def _prefixed(name: str, settings: Settings) -> str:
    return f"{HOST_PREFIX}{name}" if cookies_are_secure(settings) else name


def session_cookie_name(settings: Settings) -> str:
    """Nazwa cookie sesji dla tej instancji: `__Host-pasnik_session` w prod."""
    return _prefixed(SESSION_COOKIE_NAME, settings)


def csrf_cookie_name(settings: Settings) -> str:
    """Nazwa cookie CSRF dla tej instancji: `__Host-csrf_token` w prod."""
    return _prefixed(CSRF_COOKIE_NAME, settings)


def set_session_cookies(
    response: Response, *, session_id: str, csrf_token: str, settings: Settings
) -> None:
    """Cookie sesji (HttpOnly) + cookie CSRF (czytelne dla JS, double-submit)."""
    secure = cookies_are_secure(settings)
    max_age = int(SESSION_TTL.total_seconds())
    response.set_cookie(
        session_cookie_name(settings),
        session_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )
    response.set_cookie(
        csrf_cookie_name(settings),
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
    for name in (session_cookie_name(settings), csrf_cookie_name(settings)):
        response.delete_cookie(
            name,
            path=COOKIE_PATH,
            httponly=False,
            secure=secure,
            samesite=COOKIE_SAMESITE,
        )
