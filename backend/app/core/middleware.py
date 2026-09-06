"""Middleware bezpieczeństwa: nagłówki odpowiedzi i ochrona CSRF (07_SECURITY §3).

Obie warstwy działają dla CAŁEJ aplikacji — nie da się ich pominąć, dodając
nowy router. Nowy endpoint publiczny = wpis w `CSRF_EXEMPT_PREFIXES`, świadomy
i widoczny w diffie.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import request_settings
from app.core.cookies import csrf_cookie_name
from app.core.errors import error_response
from app.core.security import CSRF_HEADER_NAME, tokens_match

#: Metody zmieniające stan wymagają nagłówka CSRF (04_API §1).
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Ścieżki bez CSRF:
#: - `/auth/login` — sesji jeszcze nie ma, żądanie chroni rate limit (07 §2),
#: - `/public/` — autoryzuje token w URL, rate limit dokłada BATCH_11 (ADR-010).
CSRF_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/public/",
)

CSRF_ERROR_MESSAGE = (
    "Żądanie odrzucone ze względów bezpieczeństwa (brak lub niezgodny token CSRF). "
    "Odśwież stronę i spróbuj ponownie."
)

#: Nagłówki z 07_SECURITY §3 — przepisane dosłownie, bez „ulepszania".
#:
#: CSP (BATCH_17, ustalenie REVIEW R4 pkt 2): `base-uri`, `form-action`
#: i `frame-ancestors` NIE dziedziczą po `default-src`, więc bez nich
#: wstrzyknięty `<base>` przestawiłby wszystkie ścieżki względne, a przejęty
#: formularz mógłby wysłać dane na obcy host. `object-src 'none'` zamyka wtyczki
#: jawnie (dziedziczyłoby `'self'`). `worker-src` świadomie NIE jest wymieniony:
#: dziedziczy `'self'`, a dokładnie tego potrzebuje service worker (`/sw.js`
#: i `workbox-*.js` z tego samego originu, ADR-009) — zweryfikowane na buildzie
#: produkcyjnym w B17. `X-Frame-Options: DENY` zostaje dla starszych klientów.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Dokłada nagłówki bezpieczeństwa do każdej odpowiedzi, również błędnej."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        skip_csp = self._csp_exempt(request)
        for header, value in SECURITY_HEADERS.items():
            if header == "Content-Security-Policy" and skip_csp:
                continue
            response.headers.setdefault(header, value)
        return response

    @staticmethod
    def _csp_exempt(request: Request) -> bool:
        """Wyjątek CSP dla Swagger UI (skrypty z CDN) — istnieje DOKŁADNIE tam, gdzie
        istnieje dokumentacja. Ścieżki bierzemy z aplikacji (`docs_url`,
        `openapi_url`), a nie z literałów ani z `APP_ENV`: w prod `create_app`
        wyłącza docs (`None`), więc żaden adres nie jest zwolniony — także 404
        pod dawnym `/api/docs` (07_SECURITY §3)."""
        app = request.app
        exempt = {getattr(app, "docs_url", None), getattr(app, "openapi_url", None)} - {None}
        return request.url.path in exempt


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie: cookie CSRF musi zgadzać się z `X-CSRF-Token`."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in UNSAFE_METHODS and not self._is_exempt(request.url.path):
            cookie_token = request.cookies.get(csrf_cookie_name(request_settings(request)))
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if not tokens_match(cookie_token, header_token):
                return error_response(403, "forbidden", CSRF_ERROR_MESSAGE)
        return await call_next(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        return path.startswith(CSRF_EXEMPT_PREFIXES)
