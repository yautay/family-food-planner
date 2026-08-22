"""Publiczne linki list zakupowych: `/public/lists/*` (08_TESTING §2.9 W KOMPLECIE).

Ten plik jest dowodem na ADR-010. Pięć rzeczy, których pilnuje ponad zwykły
kontrakt HTTP:

1. **Zbiór kluczy odpowiedzi jest DOKŁADNY** (`test_public_response_has_no_pii`),
   a nie „nie zawiera hasła". Biała lista pól to niezmiennik 02_DOMAIN §13.5,
   więc test pada także wtedy, gdy ktoś doda do odpowiedzi pole niewinne —
   bo to jedyny moment, w którym da się to zauważyć.
2. **404 i 410 mają IDENTYCZNY komunikat.** Kod odpowiedzi rozróżnia sytuacje
   dla API, treść nie ujawnia, czy token kiedykolwiek istniał.
3. **Publiczny PATCH działa BEZ tokenu CSRF** — ścieżka `/api/v1/public/` jest
   z niego zwolniona (07_SECURITY §3), a chroni ją rate limit i entropia tokenu.
4. **Token pozwala zmienić wyłącznie `checked`.** Każde inne pole w ciele
   żądania kończy się 422, nie cichym zignorowaniem.
5. **Rate limit 60/min/IP jest realny** — 61. żądanie w minucie dostaje 429.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token
from app.modules.catalog.models import Perishability
from app.modules.shopping.lists_service import LIST_GONE
from tests.factories import (
    create_category,
    create_product,
    create_shopping_list,
    create_shopping_list_item,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

PUBLIC = f"{API}/public/lists"
LISTS = f"{API}/shopping/lists"

#: Zbiór kluczy odpowiedzi publicznej — BIAŁA LISTA z ADR-010 i 04_API §3 pkt 3.
EXPECTED_LIST_KEYS = {"name", "expires_at", "items"}
EXPECTED_ITEM_KEYS = {
    "id",
    "label",
    "amount",
    "unit",
    "category_name",
    "checked",
    "leftover_amount",
    "already_have",
    "packages_count",
    "package_size",
}


async def _list_with_item(
    session: AsyncSession,
    *,
    token: str | None = None,
    token_revoked: bool = False,
    expires_at: datetime | None = None,
    suffix: str = "",
) -> dict[str, Any]:
    """Lista z jedną pozycją i (opcjonalnie) gotowym tokenem publicznym.

    `suffix` rozróżnia dane, gdy jeden test zakłada DWIE listy różnych
    właścicieli (email i nazwa produktu są unikalne w bazie).
    """
    owner = await create_user(session, email=f"wlasciciel{suffix}@example.com")
    category = await create_category(
        session, name=f"Sypkie{suffix}", perishability=Perishability.DURABLE, position=3
    )
    product = await create_product(session, category=category, name=f"Mąka pszenna{suffix}")
    shopping_list = await create_shopping_list(
        session,
        owner=owner,
        public_token=token,
        token_revoked=token_revoked,
        expires_at=expires_at,
    )
    item = await create_shopping_list_item(
        session,
        shopping_list=shopping_list,
        category=category,
        product=product,
        label="Mąka pszenna 1 kg",
        needed_amount=Decimal("1500.000"),
        packages_count=2,
        package_size=Decimal("1000.00"),
        leftover_amount=Decimal("500.000"),
    )
    return {"owner": owner, "list": shopping_list, "item": item, "product": product}


# --- odczyt: ważny / wygasły / odwołany / nieistniejący token ---------------------


async def test_public_get_valid_token_returns_list(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ważny token daje treść listy bez logowania (ADR-010)."""
    token = generate_token()
    data = await _list_with_item(db_session, token=token)

    response = await db_client.get(f"{PUBLIC}/{token}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == data["list"].name
    assert len(body["items"]) == 1
    assert body["items"][0]["label"] == "Mąka pszenna 1 kg"
    # Ilości jako stringi dziesiętne także tutaj (ADR-008).
    assert body["items"][0]["amount"] == "1500.000"
    assert body["items"][0]["leftover_amount"] == "500.000"
    assert body["items"][0]["category_name"] == "Sypkie"


async def test_public_get_expired_token_410(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wygasła lista: 410 z komunikatem DOSŁOWNIE z ADR-010."""
    token = generate_token()
    await _list_with_item(
        db_session, token=token, expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )

    response = await db_client.get(f"{PUBLIC}/{token}")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "gone"
    assert response.json()["error"]["message"] == LIST_GONE


async def test_public_get_revoked_token_410(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odwołany link przestaje działać natychmiast, choć lista jeszcze nie wygasła."""
    token = generate_token()
    await _list_with_item(db_session, token=token, token_revoked=True)

    response = await db_client.get(f"{PUBLIC}/{token}")

    assert response.status_code == 410
    assert response.json()["error"]["message"] == LIST_GONE


async def test_public_get_unknown_token_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nieznany token to 404 — z komunikatem IDENTYCZNYM jak dla 410.

    Rozróżnienie zostaje w kodzie odpowiedzi (dla API), a nie w treści: osoba
    z losowym tokenem nie dowiaduje się, czy trafiła w cokolwiek istniejącego
    (karta B11, Implementation Notes pkt 5).
    """
    await _list_with_item(db_session, token=generate_token())

    response = await db_client.get(f"{PUBLIC}/{generate_token()}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == LIST_GONE


async def test_public_get_malformed_token_nie_dotyka_bazy(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Token o złej długości/alfabecie odsiewa walidacja ścieżki (422), nie zapytanie."""
    response = await db_client.get(f"{PUBLIC}/za-krotki")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- brak PII (niezmiennik 02_DOMAIN §13.5) --------------------------------------


async def test_public_response_has_no_pii(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Odpowiedź publiczna ma DOKŁADNIE pola z białej listy — nic więcej.

    Asercja na zbiorze kluczy, nie na braku wybranych nazw: dołożenie kolumny
    do `shopping_list_items` nie może po cichu wypchnąć danych rodziny na
    publiczną stronę.
    """
    token = generate_token()
    data = await _list_with_item(db_session, token=token)

    response = await db_client.get(f"{PUBLIC}/{token}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == EXPECTED_LIST_KEYS
    assert set(body["items"][0]) == EXPECTED_ITEM_KEYS
    # Kontrola na surowym tekście: żadnych identyfikatorów właściciela ani produktu.
    raw = response.text
    assert "owner_user_id" not in raw
    assert "household_id" not in raw
    assert "product_id" not in raw
    assert data["owner"].email not in raw
    assert token not in raw


# --- PATCH checkboxa ------------------------------------------------------------


async def test_public_patch_checkbox_works_and_sets_checked_at(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odhaczenie bez logowania i bez CSRF; `checked_at` ustawia serwer (ADR-009)."""
    token = generate_token()
    data = await _list_with_item(db_session, token=token)
    item_id = data["item"].id

    response = await db_client.patch(f"{PUBLIC}/{token}/items/{item_id}", json={"checked": True})

    assert response.status_code == 200
    assert response.json()["checked"] is True

    await db_session.refresh(data["item"])
    assert data["item"].checked is True
    assert data["item"].checked_at is not None


async def test_public_patch_other_fields_rejected(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Token pozwala TYLKO na `checked` — inne pola to 422, nie ciche pominięcie."""
    token = generate_token()
    data = await _list_with_item(db_session, token=token)
    item_id = data["item"].id

    odrzucone = await db_client.patch(
        f"{PUBLIC}/{token}/items/{item_id}",
        json={"checked": True, "already_have": True},
    )

    assert odrzucone.status_code == 422
    await db_session.refresh(data["item"])
    assert data["item"].checked is False
    assert data["item"].already_have is False


async def test_public_patch_expired_token_410(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wygaśnięcie zamyka też odhaczanie, nie tylko odczyt."""
    token = generate_token()
    data = await _list_with_item(
        db_session, token=token, expires_at=datetime.now(UTC) - timedelta(days=1)
    )

    response = await db_client.patch(
        f"{PUBLIC}/{token}/items/{data['item'].id}", json={"checked": True}
    )

    assert response.status_code == 410


async def test_public_patch_cudzej_pozycji_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pozycja z INNEJ listy jest dla tego tokenu nieosiągalna (anty-IDOR)."""
    token = generate_token()
    await _list_with_item(db_session, token=token)
    obca = await _list_with_item(db_session, suffix="-obca")

    response = await db_client.patch(
        f"{PUBLIC}/{token}/items/{obca['item'].id}", json={"checked": True}
    )

    assert response.status_code == 404


# --- rate limit ------------------------------------------------------------------


async def test_public_rate_limit_429(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """60/min/IP na `/public/*` (07_SECURITY §5) — 61. żądanie dostaje 429.

    Licznik jest WSPÓLNY dla całej ścieżki publicznej (`shared_limit`), a nie
    per endpoint: limit dotyczy `/public/*`, więc PATCH po wyczerpaniu puli
    GET-ami też musi dostać 429. Osobne liczniki dawałyby faktycznie 120/min.
    """
    token = generate_token()
    data = await _list_with_item(db_session, token=token)

    statusy = [(await db_client.get(f"{PUBLIC}/{token}")).status_code for _ in range(60)]
    nadmiarowe = await db_client.get(f"{PUBLIC}/{token}")
    patch_po_limicie = await db_client.patch(
        f"{PUBLIC}/{token}/items/{data['item'].id}", json={"checked": True}
    )

    assert statusy == [200] * 60
    assert nadmiarowe.status_code == 429
    assert nadmiarowe.json()["error"]["code"] == "rate_limited"
    assert patch_po_limicie.status_code == 429


# --- udostępnianie i odwoływanie (ścieżka zalogowana) ---------------------------


async def test_share_generates_43_char_urlsafe_token_and_expiry(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST share: token 43 znaki base64url + ważność z żądania (ADR-010)."""
    owner = await create_user(db_session, email="share@example.com")
    shopping_list = await create_shopping_list(db_session, owner=owner)
    await login(db_client, owner.email)

    response = await db_client.post(
        f"{LISTS}/{shopping_list.id}/share",
        json={"expires_in_days": 30},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    body = response.json()
    token = body["url"].removeprefix("/l/")
    assert body["url"].startswith("/l/")
    assert len(token) == 43
    assert all(znak.isalnum() or znak in "-_" for znak in token)
    assert body["revoked"] is False

    # Ważność przestawiona na 30 dni (domyślne 7 z finalizacji zostało nadpisane).
    await db_session.refresh(shopping_list)
    assert shopping_list.expires_at > datetime.now(UTC) + timedelta(days=29)
    # Token działa od razu, bez logowania.
    assert (await db_client.get(f"{PUBLIC}/{token}")).status_code == 200


async def test_share_domyslna_waznosc_to_siedem_dni(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Body bez `expires_in_days` = 7 dni (ADR-010)."""
    owner = await create_user(db_session, email="default-share@example.com")
    shopping_list = await create_shopping_list(db_session, owner=owner)
    await login(db_client, owner.email)

    response = await db_client.post(
        f"{LISTS}/{shopping_list.id}/share", json={}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 201
    expires_at = datetime.fromisoformat(response.json()["expires_at"])
    assert timedelta(days=6) < expires_at - datetime.now(UTC) <= timedelta(days=7)


async def test_revoke_then_reshare_generates_new_token(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odwołanie unieważnia link NATYCHMIAST, a ponowne udostępnienie daje NOWY token.

    Stary link nie wraca do życia — mógł już trafić w obce ręce (ADR-010).
    """
    owner = await create_user(db_session, email="revoke@example.com")
    shopping_list = await create_shopping_list(db_session, owner=owner)
    await login(db_client, owner.email)
    headers = csrf_headers(db_client)

    pierwszy = (
        await db_client.post(f"{LISTS}/{shopping_list.id}/share", json={}, headers=headers)
    ).json()["url"]
    assert (await db_client.get(f"{PUBLIC}{pierwszy.removeprefix('/l')}")).status_code == 200

    revoke = await db_client.delete(f"{LISTS}/{shopping_list.id}/share", headers=headers)
    assert revoke.status_code == 204
    assert (await db_client.get(f"{PUBLIC}{pierwszy.removeprefix('/l')}")).status_code == 410

    drugi = (
        await db_client.post(f"{LISTS}/{shopping_list.id}/share", json={}, headers=headers)
    ).json()["url"]

    assert drugi != pierwszy
    assert (await db_client.get(f"{PUBLIC}{drugi.removeprefix('/l')}")).status_code == 200
    # Stary token zostaje unieważniony na zawsze — nowy go nie wskrzesza.
    assert (await db_client.get(f"{PUBLIC}{pierwszy.removeprefix('/l')}")).status_code == 404


async def test_share_cudzej_listy_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Udostępnić da się wyłącznie listę, którą się widzi (anty-IDOR)."""
    owner = await create_user(db_session, email="wlasciciel-share@example.com")
    obcy = await create_user(db_session, email="obcy-share@example.com")
    shopping_list = await create_shopping_list(db_session, owner=owner)
    await login(db_client, obcy.email)

    response = await db_client.post(
        f"{LISTS}/{shopping_list.id}/share", json={}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 404
    await db_session.refresh(shopping_list)
    assert shopping_list.public_token is None


async def test_share_wymaga_tokenu_csrf(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Mutacja ZALOGOWANA nie jest zwolniona z CSRF — zwolniona jest tylko `/public/`."""
    owner = await create_user(db_session, email="csrf-share@example.com")
    shopping_list = await create_shopping_list(db_session, owner=owner)
    await login(db_client, owner.email)

    response = await db_client.post(f"{LISTS}/{shopping_list.id}/share", json={})

    assert response.status_code == 403
