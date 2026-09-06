"""Sufit rozmiaru ciała żądania — 413 w kształcie błędu 04_API §1 (BATCH_17).

Druga połowa ochrony uploadów obok limitu częstości (`core/ratelimits.py`).
Serwisy sprawdzają rozmiar PLIKU (`save_image`, transfer), ale robią to
dopiero po wczytaniu multiparta do pamięci; ten middleware odcina żądanie
WCZEŚNIEJ i obejmuje też ścieżki, które uploadem nie są — bez niego `POST
/auth/login` z ciałem 500 MB byłby przyjmowany i parsowany.

Dwie warstwy:

1. `Content-Length` ponad limit → 413 natychmiast, zanim aplikacja przeczyta
   pierwszy bajt.
2. Ciało bez `Content-Length` (chunked) → licznik na `receive()`. Po
   przekroczeniu middleware SAM wysyła 413, przerywa odczyt wyjątkiem
   `PayloadTooLargeError` i wycisza odpowiedź, którą aplikacja spróbuje wysłać
   po tym wyjątku (FastAPI zamienia każdy błąd odczytu ciała w 400 „error
   parsing the body" — bez wyciszenia użytkownik dostałby ten 400 zamiast 413).

Limit zależy od ścieżki: endpointy uploadu dostają swój limit + margines na
nagłówki multiparta, reszta — `REQUEST_MAX_BODY_MB`. Reguły składa
`build_body_limit_rules` z `Settings`, żeby w kodzie nie było drugiej listy
limitów obok konfiguracji.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import PayloadTooLargeError, error_response

MIB = 1024 * 1024

#: Margines na nagłówki i granice multiparta ponad limit samego pliku. Serwis
#: i tak odrzuci plik większy niż jego limit — margines ma tylko nie ucinać
#: poprawnego uploadu o kilkaset bajtów za wcześnie.
UPLOAD_BODY_MARGIN_BYTES = 1 * MIB

#: Metody, które mogą nieść ciało. GET/HEAD/OPTIONS przechodzą bez sprawdzania —
#: żaden endpoint nie czyta tam ciała, a uvicorn i tak nie buforuje go w pamięci.
METHODS_WITH_BODY = frozenset({"POST", "PUT", "PATCH", "DELETE"})

TOO_LARGE_MESSAGE = "Żądanie jest za duże — limit dla tej operacji to {limit} MB."


@dataclass(frozen=True)
class BodyLimitRule:
    """Ścieżki pasujące do `pattern` mają limit `limit_mb` (+ margines multiparta)."""

    pattern: re.Pattern[str]
    limit_mb: int

    @property
    def limit_bytes(self) -> int:
        return self.limit_mb * MIB + UPLOAD_BODY_MARGIN_BYTES


def build_body_limit_rules(settings: Settings) -> tuple[BodyLimitRule, ...]:
    """Reguły per endpoint uploadu — limity z konfiguracji, nie z drugiej listy."""
    return (
        BodyLimitRule(re.compile(r"^/api/v1/transfer/import$"), settings.transfer_max_zip_mb),
        BodyLimitRule(re.compile(r"^/api/v1/recipes/\d+/photo$"), settings.image_max_upload_mb),
        BodyLimitRule(
            re.compile(r"^/api/v1/retail-products/\d+/photo$"), settings.image_max_upload_mb
        ),
    )


def too_large_message(limit_mb: int) -> str:
    return TOO_LARGE_MESSAGE.format(limit=limit_mb)


class BodyLimitMiddleware:
    """Czysty ASGI (bez BaseHTTPMiddleware): musi podmienić `receive`, nie tylko odpowiedź."""

    def __init__(
        self, app: ASGIApp, *, default_limit_mb: int, rules: Sequence[BodyLimitRule] = ()
    ) -> None:
        self.app = app
        self._default_limit_mb = default_limit_mb
        self._rules = tuple(rules)

    def limit_for(self, path: str) -> tuple[int, int]:
        """(limit w MB do komunikatu, limit w bajtach do porównania) dla ścieżki."""
        for rule in self._rules:
            if rule.pattern.match(path):
                return rule.limit_mb, rule.limit_bytes
        return self._default_limit_mb, self._default_limit_mb * MIB

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in METHODS_WITH_BODY:
            await self.app(scope, receive, send)
            return

        limit_mb, limit_bytes = self.limit_for(scope["path"])
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit():
            if int(declared) > limit_bytes:
                response = error_response(413, "payload_too_large", too_large_message(limit_mb))
                await response(scope, receive, send)
                return
            # Serwer HTTP (h11) nie przepuści więcej bajtów, niż zadeklarowano, więc
            # licznik jest zbędny — bez opakowywania `receive`/`send` na hot path.
            await self.app(scope, receive, send)
            return

        # Ciało bez `Content-Length` (chunked) — liczymy sami.
        received = 0
        responded = False

        async def limited_receive() -> Message:
            nonlocal received, responded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit_bytes and not responded:
                    responded = True
                    response = error_response(413, "payload_too_large", too_large_message(limit_mb))
                    await response(scope, receive, send)
                    raise PayloadTooLargeError(too_large_message(limit_mb))
            return message

        async def guarded_send(message: Message) -> None:
            # Po naszym 413 aplikacja i tak spróbuje odpowiedzieć (400 z FastAPI
            # albo handler AppError) — druga odpowiedź w jednym połączeniu byłaby
            # błędem protokołu, więc ją wyciszamy.
            if not responded:
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except PayloadTooLargeError:
            if not responded:
                raise
