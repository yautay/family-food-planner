"""Kontrakt HTTP `/pantry`: macierz uprawnień 08_TESTING §4, walidacje, filtry.

Spiżarnia jest zasobem HOUSEHOLD bez kolumny `scope`, więc macierz dowodzimy tu
kodami HTTP: anonim 401 / obcy 404 / członek 200 (odczyt i edycja) / usunięcie
cudzej pozycji 403 / ADMIN 200 (D16). Obszar krytyczny 08_TESTING §2.5: ilość
ujemna nie ma prawa się zapisać.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.modules.catalog.models import MeasureKind
from tests.factories import (
    create_admin,
    create_category,
    create_household,
    create_pantry_item,
    create_product,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

PANTRY = f"{API}/pantry"


def _payload(product_id: int, **overrides: Any) -> dict[str, Any]:
    """Minimalne poprawne wejście POST — ilość zawsze jako string dziesiętny."""
    return {"product_id": product_id, "amount": "500.000", **overrides}


# --- macierz uprawnień (08_TESTING §4) --------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Spiżarnia w całości siedzi za sesją (04_API §3 pkt 1).

    Mutacje dostają własny token CSRF: bez niego middleware odpowiada 403
    JESZCZE PRZED autoryzacją, a testowany jest tu brak sesji, nie brak tokenu
    (ten pilnuje osobny test).
    """
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-anonima")
    headers = {CSRF_HEADER_NAME: "token-anonima"}

    assert (await db_client.get(PANTRY)).status_code == 401
    assert (
        await db_client.post(PANTRY, json={"product_id": 1, "amount": "1"}, headers=headers)
    ).status_code == 401
    assert (
        await db_client.patch(f"{PANTRY}/1", json={"amount": "0"}, headers=headers)
    ).status_code == 401
    assert (await db_client.delete(f"{PANTRY}/1", headers=headers)).status_code == 401


async def test_czlonek_rodziny_widzi_i_edytuje_pozycje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odczyt i edycja stanu domowego: każdy członek rodziny (AC 3)."""
    household = await create_household(db_session)
    author = await create_user(db_session, email="autor@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Mąka")
    item = await create_pantry_item(db_session, owner=author, product=product)

    await login(db_client, member.email)
    listing = await db_client.get(PANTRY)
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()["items"]] == [item.id]

    changed = await db_client.patch(
        f"{PANTRY}/{item.id}", json={"amount": "120.5"}, headers=csrf_headers(db_client)
    )
    assert changed.status_code == 200
    assert changed.json()["amount"] == "120.500"


async def test_obcy_uzytkownik_dostaje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Anty-IDOR: cudza pozycja i nieistniejąca są nieodróżnialne (07_SECURITY §4)."""
    ours = await create_household(db_session, name="Kowalscy")
    theirs = await create_household(db_session, name="Nowakowie")
    owner = await create_user(db_session, email="my@example.com", household=ours)
    outsider = await create_user(db_session, email="obcy@example.com", household=theirs)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=owner, product=product)

    await login(db_client, outsider.email)
    headers = csrf_headers(db_client)

    assert (await db_client.get(PANTRY)).json()["items"] == []
    assert (
        await db_client.patch(f"{PANTRY}/{item.id}", json={"amount": "1"}, headers=headers)
    ).status_code == 404
    assert (await db_client.delete(f"{PANTRY}/{item.id}", headers=headers)).status_code == 404
    assert (await db_client.delete(f"{PANTRY}/999999", headers=headers)).status_code == 404


async def test_czlonek_rodziny_usuwa_cudza_pozycje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D17: usuwa każdy członek rodziny — spiżarnia to jeden stan domowy.

    Wyjątek od wiersza „zmiana scope / delete" w macierzy 08_TESTING §4:
    encja „zawsze household" nie ma scope'u do zmiany, a „kto dodał" jest tu
    informacją, nie przywilejem.
    """
    household = await create_household(db_session)
    author = await create_user(db_session, email="autor@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=author, product=product)

    await login(db_client, member.email)
    response = await db_client.delete(f"{PANTRY}/{item.id}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert (await db_client.get(PANTRY)).json()["total"] == 0


async def test_wlasciciel_usuwa_swoja_pozycje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Autor wpisu usuwa go bez przeszkód (AC 2)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=user, product=product)

    await login(db_client, user.email)
    response = await db_client.delete(f"{PANTRY}/{item.id}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert (await db_client.get(PANTRY)).json()["total"] == 0


async def test_d16_admin_widzi_i_usuwa_cudze_pozycje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D16: encja ze scope jest widoczna dla ADMIN-a także na ścieżce użytkownika."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=user, product=product)

    await login(db_client, admin.email)
    listing = await db_client.get(PANTRY)
    assert [row["id"] for row in listing.json()["items"]] == [item.id]
    assert (
        await db_client.delete(f"{PANTRY}/{item.id}", headers=csrf_headers(db_client))
    ).status_code == 204


async def test_mutacja_bez_csrf_to_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Double-submit cookie obowiązuje każdą mutację (07_SECURITY §3)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    await login(db_client, user.email)
    response = await db_client.post(PANTRY, json=_payload(product.id))

    assert response.status_code == 403


# --- walidacje (08_TESTING §2.5) ---------------------------------------------------


async def test_ilosc_ujemna_to_422(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Ujemny stan domowy nie istnieje — ani przy dodaniu, ani przy edycji."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=user, product=product)

    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    assert (
        await db_client.post(PANTRY, json=_payload(product.id, amount="-1"), headers=headers)
    ).status_code == 422
    assert (
        await db_client.patch(f"{PANTRY}/{item.id}", json={"amount": "-0.001"}, headers=headers)
    ).status_code == 422
    assert (await db_client.get(PANTRY)).json()["items"][0]["amount"] == "500.000"


async def test_jednostka_piece_dla_produktu_mass_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`amount_unit` musi zgadzać się z `measure_kind` produktu (02_DOMAIN §13.1)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka")

    await login(db_client, user.email)
    response = await db_client.post(
        PANTRY,
        json=_payload(flour.id, amount_unit="piece"),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"]["expected_unit"] == "g"


async def test_dodanie_pozycji_zwraca_dane_produktu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST zwraca 201 z ilością jako stringiem dziesiętnym i danymi produktu (04_API §1)."""
    user = await create_user(db_session)
    category = await create_category(db_session, name="Nabiał")
    eggs = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )

    await login(db_client, user.email)
    response = await db_client.post(
        PANTRY,
        json=_payload(eggs.id, amount="10", expiry_date="2030-01-31", location="lodówka"),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "10.000"
    assert body["amount_unit"] == "piece"
    assert body["product_name"] == "Jajko"
    assert body["category_name"] == "Nabiał"
    assert body["measure_kind"] == "piece"
    assert body["expiry_date"] == "2030-01-31"
    assert body["location"] == "lodówka"


async def test_wyzerowanie_zostawia_pozycje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`{"amount": "0"}` to wyzerowanie, nie usunięcie (AC 2)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=user, product=product)

    await login(db_client, user.email)
    response = await db_client.patch(
        f"{PANTRY}/{item.id}", json={"amount": "0"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.json()["amount"] == "0.000"
    assert (await db_client.get(PANTRY)).json()["total"] == 1


async def test_patch_nie_pozwala_wyzerowac_notatki_nullem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`null` wolno przysłać tylko dla kolumn NULLABLE — notatka jest NOT NULL."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=user, product=product, note="do zupy")

    await login(db_client, user.email)
    response = await db_client.patch(
        f"{PANTRY}/{item.id}", json={"note": None}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 422


# --- lista: sortowanie, filtry, szukajka -------------------------------------------


async def test_lista_sortuje_filtruje_i_szuka(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Domyślnie po dacie ważności (bez daty na końcu) + `?q=`, kategoria, `?sort=name`."""
    user = await create_user(db_session)
    today = date.today()
    dairy = await create_category(db_session, name="Nabiał", position=1)
    dry = await create_category(db_session, name="Suche", position=2)
    yoghurt = await create_product(db_session, category=dairy, name="Jogurt naturalny")
    milk = await create_product(db_session, category=dairy, name="Mleko")
    rice = await create_product(db_session, category=dry, name="Ryż biały")

    await create_pantry_item(db_session, owner=user, product=rice)
    await create_pantry_item(
        db_session, owner=user, product=milk, expiry_date=today + timedelta(days=10)
    )
    await create_pantry_item(
        db_session, owner=user, product=yoghurt, expiry_date=today + timedelta(days=2)
    )

    await login(db_client, user.email)

    default_sort = await db_client.get(PANTRY)
    assert [row["product_name"] for row in default_sort.json()["items"]] == [
        "Jogurt naturalny",
        "Mleko",
        "Ryż biały",
    ]

    by_name = await db_client.get(PANTRY, params={"sort": "name"})
    assert [row["product_name"] for row in by_name.json()["items"]] == [
        "Jogurt naturalny",
        "Mleko",
        "Ryż biały",
    ]

    by_category = await db_client.get(PANTRY, params={"category_id": dry.id})
    assert [row["product_name"] for row in by_category.json()["items"]] == ["Ryż biały"]

    by_query = await db_client.get(PANTRY, params={"q": "jogurt"})
    assert [row["product_name"] for row in by_query.json()["items"]] == ["Jogurt naturalny"]

    expiring = await db_client.get(PANTRY, params={"expires_within_days": 7})
    assert [row["product_name"] for row in expiring.json()["items"]] == ["Jogurt naturalny"]


async def test_paginacja_zwraca_total_calej_listy(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`{items, total}` z 04_API §1: `total` liczy wszystko, `items` tylko stronę."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    for index in range(3):
        product = await create_product(db_session, category=category, name=f"Produkt {index}")
        await create_pantry_item(db_session, owner=user, product=product)

    await login(db_client, user.email)
    response = await db_client.get(PANTRY, params={"limit": 2, "offset": 0})

    assert response.json()["total"] == 3
    assert len(response.json()["items"]) == 2
