"""Pomocnicze funkcje testów API (logowanie, CSRF, odczyt cookies)."""

from __future__ import annotations

from httpx import AsyncClient, Response

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from tests.factories import TEST_PASSWORD

API = "/api/v1"


async def login(client: AsyncClient, email: str, password: str = TEST_PASSWORD) -> Response:
    """Zaloguj klienta; cookies zostają w jego „słoiku" na kolejne żądania."""
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    """Nagłówek CSRF przepisany z cookie — dokładnie to, co robi frontend."""
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}


def set_cookie_header(response: Response, name: str) -> str:
    """Surowy nagłówek `Set-Cookie` danego cookie (atrybuty HttpOnly/Secure)."""
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header
    wyslane = response.headers.get_list("set-cookie")
    raise AssertionError(f"Brak cookie {name} w odpowiedzi: {wyslane}")
