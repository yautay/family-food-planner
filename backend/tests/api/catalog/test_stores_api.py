"""Kontrakt HTTP `/stores` i `/stores/{id}/category-order` (BATCH_09).

Macierz uprawnień (08_TESTING §4) jest tu krótka i taka ma być: sklepy to
słownik globalny edytowalny przez USERA (02_DOMAIN §3.1 pkt 3), więc dowodzimy
dwóch rzeczy — anonim nie widzi niczego (401), a zwykły użytkownik może
wszystko (200/201/204). Rola ADMIN nie daje tu żadnych dodatkowych praw.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from tests.factories import (
    create_category,
    create_product,
    create_retail_product,
    create_store,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

STORES = f"{API}/stores"


# --- macierz uprawnień -------------------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Cały obszar siedzi za sesją (04_API §3 pkt 1).

    Mutacja dostaje własny token CSRF: bez niego middleware odpowiada 403 JESZCZE
    PRZED autoryzacją, a testowany jest tu brak sesji, nie brak tokenu.
    """
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-anonima")
    headers = {CSRF_HEADER_NAME: "token-anonima"}

    assert (await db_client.get(STORES)).status_code == 401
    assert (await db_client.post(STORES, json={"name": "Lidl"}, headers=headers)).status_code == 401
    assert (await db_client.get(f"{STORES}/1/category-order")).status_code == 401
    assert (
        await db_client.put(
            f"{STORES}/1/category-order", json={"category_ids": []}, headers=headers
        )
    ).status_code == 401


async def test_uzytkownik_zarzadza_sklepami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 3: USER tworzy, edytuje i usuwa sklep — bez pomocy administratora."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        STORES, json={"name": "Lidl", "color": "primary"}, headers=headers
    )
    assert created.status_code == 201
    store = created.json()
    assert (store["name"], store["color"], store["is_archived"]) == ("Lidl", "primary", False)

    renamed = await db_client.patch(
        f"{STORES}/{store['id']}", json={"name": "Lidl Centrum"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Lidl Centrum"

    assert (await db_client.delete(f"{STORES}/{store['id']}", headers=headers)).status_code == 204
    assert (await db_client.get(STORES)).json()["total"] == 0


async def test_mutacja_bez_csrf_daje_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Double-submit CSRF obowiązuje każdą mutację (07_SECURITY §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.post(STORES, json={"name": "Lidl"})).status_code == 403


# --- walidacje i konflikty ----------------------------------------------------------


async def test_duplikat_nazwy_daje_409_z_podpowiedzia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Inline create ma z czego zaproponować istniejący sklep (06_UIUX §3.1)."""
    user = await create_user(db_session)
    existing = await create_store(db_session, name="Lidl")
    await login(db_client, user.email)

    response = await db_client.post(STORES, json={"name": "lidl"}, headers=csrf_headers(db_client))

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["details"]["existing"]["id"] == existing.id


async def test_pusta_nazwa_z_samych_spacji_jest_odrzucana(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nazwa jest przycinana PRZED sprawdzeniem długości — `"   "` to 422."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(STORES, json={"name": "   "}, headers=csrf_headers(db_client))

    assert response.status_code == 422


async def test_usuniecie_uzywanego_sklepu_zwraca_kontrakt_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 3: 409 z listą użyć, żeby UI pokazało „Używane w: …" (06_UIUX §3.3)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    store = await create_store(db_session, name="Lidl")
    await create_retail_product(db_session, product=product, store=store, name="Jogurt Pilos")
    await login(db_client, user.email)

    response = await db_client.delete(f"{STORES}/{store.id}", headers=csrf_headers(db_client))

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    used_in = error["details"]["used_in"]
    assert [(entry["type"], entry["name"]) for entry in used_in] == [
        ("retail_product", "Jogurt Pilos")
    ]
    assert isinstance(used_in[0]["id"], int)


async def test_archiwizacja_ukrywa_sklep_i_da_sie_cofnac(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odwracalna alternatywa usuwania (ADR-012)."""
    user = await create_user(db_session)
    store = await create_store(db_session, name="Lidl")
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    await db_client.patch(f"{STORES}/{store.id}", json={"is_archived": True}, headers=headers)
    assert (await db_client.get(STORES)).json()["total"] == 0
    assert (await db_client.get(f"{STORES}?include_archived=true")).json()["total"] == 1

    await db_client.patch(f"{STORES}/{store.id}", json={"is_archived": False}, headers=headers)
    assert (await db_client.get(STORES)).json()["total"] == 1


async def test_nieistniejacy_sklep_to_404(db_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.get(f"{STORES}/999999/category-order")).status_code == 404
    assert (
        await db_client.patch(
            f"{STORES}/999999", json={"name": "Nowa"}, headers=csrf_headers(db_client)
        )
    ).status_code == 404


# --- profil kolejności kategorii ----------------------------------------------------


async def _order(client: AsyncClient, store_id: int) -> list[dict[str, Any]]:
    response = await client.get(f"{STORES}/{store_id}/category-order")
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_put_kolejnosci_podmienia_calosc_i_zwraca_pozycje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 4: kolejność zapisuje się w całości, a pozycje liczy serwer."""
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    nabial = await create_category(db_session, name="Nabiał")
    store = await create_store(db_session, name="Lidl")
    await login(db_client, user.email)

    response = await db_client.put(
        f"{STORES}/{store.id}/category-order",
        json={"category_ids": [nabial.id, warzywa.id]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert [(item["category_id"], item["position"]) for item in response.json()["items"]] == [
        (nabial.id, 0),
        (warzywa.id, 1),
    ]
    # Kolejność jest TRWAŁA: kolejny odczyt widzi to samo.
    assert [item["category_name"] for item in await _order(db_client, store.id)] == [
        "Nabiał",
        "Warzywa",
    ]


async def test_duplikat_kategorii_w_put_daje_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    store = await create_store(db_session, name="Lidl")
    await login(db_client, user.email)

    response = await db_client.put(
        f"{STORES}/{store.id}/category-order",
        json={"category_ids": [warzywa.id, warzywa.id]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert await _order(db_client, store.id) == []


async def test_nieznana_kategoria_w_put_daje_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nieznane id w liście to błąd DANYCH WEJŚCIOWYCH, nie brak zasobu."""
    user = await create_user(db_session)
    store = await create_store(db_session, name="Lidl")
    await login(db_client, user.email)

    response = await db_client.put(
        f"{STORES}/{store.id}/category-order",
        json={"category_ids": [999_999]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["unknown_category_ids"] == [999_999]
