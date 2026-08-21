"""Kontrakt HTTP `/retail-products` — macierz uprawnień, walidacje, zdjęcia.

Produkty sklepowe są globalne i edytowalne przez USERA (02_DOMAIN §3.1 pkt 4),
więc macierz sprowadza się do: anonim 401, USER pełny zakres. Ilości wychodzą
jako STRINGI dziesiętne (ADR-008) — to też jest tu asercją, nie szczegółem.

Zdjęcia jadą tym samym pipeline'em co zdjęcia przepisów (B05), więc sprawdzamy
kontrakt (URL-e, sniffing, limit), a nie wnętrze Pillow — to ma własne testy.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.core.uploads import MAX_IMAGE_BYTES
from app.modules.catalog.models import MeasureKind
from tests.factories import (
    create_category,
    create_pantry_item,
    create_product,
    create_retail_product,
    create_store,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

RETAIL = f"{API}/retail-products"


def _payload(product_id: int, **overrides: Any) -> dict[str, Any]:
    """Minimalne poprawne wejście POST — ilość zawsze jako string dziesiętny."""
    return {
        "canonical_product_id": product_id,
        "name": "Pilos Jogurt naturalny 400 g",
        "package_amount": "400.00",
        "package_unit": "g",
        **overrides,
    }


def _png_bytes(size: tuple[int, int] = (800, 600)) -> bytes:
    """Poprawny PNG z kanałem alfa — sniffing dostaje realną treść pliku."""
    buffer = BytesIO()
    Image.new("RGBA", size, (63, 122, 94, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


# --- macierz uprawnień -------------------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Cały obszar siedzi za sesją (04_API §3 pkt 1)."""
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-anonima")
    headers = {CSRF_HEADER_NAME: "token-anonima"}

    assert (await db_client.get(RETAIL)).status_code == 401
    assert (await db_client.post(RETAIL, json=_payload(1), headers=headers)).status_code == 401
    assert (
        await db_client.patch(f"{RETAIL}/1", json={"name": "X"}, headers=headers)
    ).status_code == 401
    assert (await db_client.delete(f"{RETAIL}/1", headers=headers)).status_code == 401


async def test_uzytkownik_tworzy_i_edytuje_wariant(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 1 i 2: pełny wariant z marką, sklepem i opakowaniem — zwykłym USEREM."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Jogurt naturalny")
    store = await create_store(db_session, name="Lidl")
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        RETAIL,
        json=_payload(product.id, brand="Pilos", store_id=store.id),
        headers=headers,
    )

    assert created.status_code == 201
    body = created.json()
    assert body["canonical_product_id"] == product.id
    assert body["canonical_product_name"] == "Jogurt naturalny"
    assert body["store_name"] == "Lidl"
    assert body["brand"] == "Pilos"
    # ADR-008: NUMERIC w JSON to string dziesiętny ze skalą kolumny.
    assert body["package_amount"] == "400.00"
    assert body["photo_url"] is None

    updated = await db_client.patch(
        f"{RETAIL}/{body['id']}",
        json={"package_amount": "500.00", "brand": None},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["package_amount"] == "500.00"
    assert updated.json()["brand"] is None


async def test_mutacja_bez_csrf_daje_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Double-submit CSRF obowiązuje każdą mutację (07_SECURITY §3)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    assert (await db_client.post(RETAIL, json=_payload(product.id))).status_code == 403


# --- walidacje opakowania ----------------------------------------------------------


async def test_brak_produktu_kanonicznego_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 1: bez `canonical_product_id` żądanie nie ma prawa przejść."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    bez_pola = await db_client.post(
        RETAIL,
        json={"name": "Widmo", "package_amount": "400.00", "package_unit": "g"},
        headers=headers,
    )
    assert bez_pola.status_code == 422

    nieistniejacy = await db_client.post(RETAIL, json=_payload(999_999), headers=headers)
    assert nieistniejacy.status_code == 422
    assert nieistniejacy.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "override",
    [
        {"package_amount": "0.00"},
        {"package_amount": "-5.00"},
        {"pieces_per_package": 0},
        {"package_unit": "kg"},
    ],
)
async def test_niepoprawne_opakowanie_jest_odrzucane(
    db_client: AsyncClient, db_session: AsyncSession, override: dict[str, Any]
) -> None:
    """Opakowanie „0 g" ani „0 sztuk w opakowaniu" nie istnieje w rzeczywistości."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    response = await db_client.post(
        RETAIL, json=_payload(product.id, **override), headers=csrf_headers(db_client)
    )

    assert response.status_code == 422


async def test_jednostka_niezgodna_z_measure_kind_daje_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Opakowanie w mililitrach dla produktu liczonego na wagę → 422 z komunikatem PL."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session, category=category, name="Mąka", measure_kind=MeasureKind.MASS
    )
    await login(db_client, user.email)

    response = await db_client.post(
        RETAIL,
        json=_payload(product.id, package_unit="ml"),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "gramach" in error["message"]


async def test_liczba_zmiennoprzecinkowa_spoza_precyzji_kolumny_jest_odrzucana(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """NUMERIC(8,2): trzecia cyfra po przecinku to błąd, nie zaokrąglenie (ADR-008)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    response = await db_client.post(
        RETAIL,
        json=_payload(product.id, package_amount="400.001"),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


# --- filtry, archiwizacja, usuwanie ------------------------------------------------


async def test_filtr_po_produkcie_i_archiwum(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Karta produktu pyta o warianty jednego produktu; archiwalne są ukryte."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    jogurt = await create_product(db_session, category=category, name="Jogurt")
    maka = await create_product(db_session, category=category, name="Mąka")
    await create_retail_product(db_session, product=jogurt, name="Jogurt Pilos 400 g")
    archiwalny = await create_retail_product(
        db_session, product=jogurt, name="Jogurt stary", is_archived=True
    )
    await create_retail_product(db_session, product=maka, name="Mąka Castello 1 kg")
    await login(db_client, user.email)

    aktywne = await db_client.get(f"{RETAIL}?canonical_product_id={jogurt.id}")
    assert aktywne.json()["total"] == 1
    assert aktywne.json()["items"][0]["name"] == "Jogurt Pilos 400 g"

    z_archiwum = await db_client.get(
        f"{RETAIL}?canonical_product_id={jogurt.id}&include_archived=true"
    )
    assert {item["id"] for item in z_archiwum.json()["items"]} >= {archiwalny.id}


async def test_usuniecie_uzywanego_wariantu_zwraca_kontrakt_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pozycja spiżarni blokuje usunięcie wariantu (FK z migracji `0011`, ADR-012)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product, name="Jogurt Pilos 400 g")
    await create_pantry_item(db_session, owner=user, product=product, retail_product_id=retail.id)
    await login(db_client, user.email)

    response = await db_client.delete(f"{RETAIL}/{retail.id}", headers=csrf_headers(db_client))

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert [(entry["type"], entry["name"]) for entry in error["details"]["used_in"]] == [
        ("pantry_item", "Jogurt Pilos 400 g")
    ]


async def test_archiwizacja_zamiast_usuwania(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2 i ADR-012: `is_archived` to odwracalna ścieżka wyjścia."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product)
    await login(db_client, user.email)

    response = await db_client.patch(
        f"{RETAIL}/{retail.id}", json={"is_archived": True}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is True
    assert (await db_client.get(RETAIL)).json()["total"] == 0


async def test_nieistniejacy_wariant_to_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (
        await db_client.patch(
            f"{RETAIL}/999999", json={"name": "X"}, headers=csrf_headers(db_client)
        )
    ).status_code == 404
    assert (
        await db_client.delete(f"{RETAIL}/999999", headers=csrf_headers(db_client))
    ).status_code == 404


# --- zdjęcie opakowania ------------------------------------------------------------


async def test_upload_zdjecia_uzywa_pipeline_z_b05(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2: zdjęcie ląduje w `uploads/retail/` jako JPEG z miniaturą (07_SECURITY §6)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product)
    await login(db_client, user.email)

    response = await db_client.put(
        f"{RETAIL}/{retail.id}/photo",
        files={"file": ("opakowanie.png", _png_bytes(), "image/png")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["photo_url"].startswith("/uploads/retail/")
    assert body["photo_url"].endswith(".jpg")
    assert body["photo_thumb_url"].endswith("_thumb.jpg")

    uploads_root = Path(get_settings().uploads_dir)
    stored = uploads_root / body["photo_url"].removeprefix("/uploads/")
    thumb = uploads_root / body["photo_thumb_url"].removeprefix("/uploads/")
    assert stored.is_file() and thumb.is_file()
    with Image.open(stored) as image:
        # Re-encode: na dysku leży JPEG wyrenderowany przez nas, nie oryginalny PNG.
        assert image.format == "JPEG"

    usuniete = await db_client.delete(
        f"{RETAIL}/{retail.id}/photo", headers=csrf_headers(db_client)
    )
    assert usuniete.status_code == 200
    assert usuniete.json()["photo_url"] is None
    assert not stored.exists() and not thumb.exists()


async def test_nie_obraz_to_422(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Sniffing po TREŚCI, nie po rozszerzeniu (07_SECURITY §6)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product)
    await login(db_client, user.email)

    response = await db_client.put(
        f"{RETAIL}/{retail.id}/photo",
        files={"file": ("opakowanie.png", b"%PDF-1.7 nie-obraz", "image/png")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_za_duzy_plik_to_413(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Limit 10 MB sprawdzany PRZED parsowaniem obrazu."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product)
    await login(db_client, user.email)

    response = await db_client.put(
        f"{RETAIL}/{retail.id}/photo",
        files={"file": ("duze.jpg", b"\x00" * (MAX_IMAGE_BYTES + 1), "image/jpeg")},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 413


async def test_usuniecie_zdjecia_ktorego_nie_ma_to_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product, photo_path=None)
    await login(db_client, user.email)

    response = await db_client.delete(
        f"{RETAIL}/{retail.id}/photo", headers=csrf_headers(db_client)
    )

    assert response.status_code == 404


async def test_wariant_dla_produktu_w_sztukach(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2: opakowanie wielosztukowe (jajka 10 szt.) przechodzi walidację osi."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )
    await login(db_client, user.email)

    response = await db_client.post(
        RETAIL,
        json=_payload(
            product.id,
            name="Jaja z wolnego wybiegu 10 szt.",
            package_amount="10.00",
            package_unit="piece",
            pieces_per_package=10,
        ),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["package_unit"] == "piece"
    assert body["pieces_per_package"] == 10
