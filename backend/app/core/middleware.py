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

from app.core.errors import error_response
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, tokens_match

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
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'"
    ),
}

#: Interaktywna dokumentacja ładuje Swagger UI z CDN, więc CSP `default-src 'self'`
#: by ją wygasiła. W prod `docs_url` jest wyłączony (`app/main.py`), więc wyjątek
#: nie istnieje tam, gdzie ma znaczenie.
CSP_EXEMPT_PATHS: frozenset[str] = frozenset({"/api/docs", "/api/openapi.json"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Dokłada nagłówki bezpieczeństwa do każdej odpowiedzi, również błędnej."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            if header == "Content-Security-Policy" and request.url.path in CSP_EXEMPT_PATHS:
                continue
            response.headers.setdefault(header, value)
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie: `csrf_token` musi zgadzać się z `X-CSRF-Token`."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in UNSAFE_METHODS and not self._is_exempt(request.url.path):
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if not tokens_match(cookie_token, header_token):
                return error_response(403, "forbidden", CSRF_ERROR_MESSAGE)
        return await call_next(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        return path.startswith(CSRF_EXEMPT_PREFIXES)
