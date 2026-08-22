"""Kontrakt HTTP `/shopping/lists/*`: macierz uprawnień, sortowanie, odhaczanie.

Cztery obszary, które ten plik zamyka:

1. **Macierz 08_TESTING §4** dla nowego zasobu: odczyt i edycja HOUSEHOLD dla
   członka rodziny, usunięcie tylko dla właściciela/ADMIN-a, cudza lista = 404
   (anty-IDOR), anonim = 401.
2. **Sortowanie sekcji wg profilu sklepu** — z API, nie z serwisu: zmiana sklepu
   na liście MA przesortować sekcje (AC 1), a kategorie spoza profilu idą na
   koniec (kontrakt B09).
3. **Trwałość checkboxów**: stan przetrwa ponowne pobranie listy (AC 1).
4. **Blokada usuwania sklepu** użytego jako profil listy: 409 z `used_in`
   (Cross-Batch Impact B09 — FK ma SET NULL, więc bez licznika lista po cichu
   straciłaby profil).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.modules.catalog.models import Perishability
from tests.factories import (
    assign_to_household,
    create_admin,
    create_category,
    create_category_order,
    create_household,
    create_product,
    create_shopping_list,
    create_shopping_list_item,
    create_store,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

LISTS = f"{API}/shopping/lists"
STORES = f"{API}/stores"


async def _household_list(
    db_session: AsyncSession, *, scope: Scope = Scope.HOUSEHOLD
) -> dict[str, Any]:
    """Właściciel + członek rodziny + obcy + lista z dwiema pozycjami w dwóch kategoriach."""
    household = await create_household(db_session, name="Kowalscy")
    owner = await create_user(db_session, email="wlasciciel@example.com")
    member = await create_user(db_session, email="czlonek@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    admin = await create_admin(db_session, email="admin@example.com")
    await assign_to_household(db_session, user=owner, household=household)
    await assign_to_household(db_session, user=member, household=household)

    warzywa = await create_category(
        db_session, name="Warzywa", perishability=Perishability.FRESH, position=0
    )
    sypkie = await create_category(
        db_session, name="Sypkie", perishability=Perishability.DURABLE, position=5
    )
    pomidor = await create_product(db_session, category=warzywa, name="Pomidor")
    maka = await create_product(db_session, category=sypkie, name="Mąka pszenna")

    shopping_list = await create_shopping_list(db_session, owner=owner, scope=scope)
    pozycja_warzywa = await create_shopping_list_item(
        db_session,
        shopping_list=shopping_list,
        category=warzywa,
        product=pomidor,
        label="Pomidor",
        needed_amount=Decimal("700.000"),
        position=0,
    )
    pozycja_sypkie = await create_shopping_list_item(
        db_session,
        shopping_list=shopping_list,
        category=sypkie,
        product=maka,
        label="Mąka pszenna 1 kg",
        needed_amount=Decimal("1400.000"),
        packages_count=2,
        package_size=Decimal("1000.00"),
        leftover_amount=Decimal("600.000"),
        position=1,
    )
    return {
        "household": household,
        "owner": owner,
        "member": member,
        "stranger": stranger,
        "admin": admin,
        "list": shopping_list,
        "warzywa": warzywa,
        "sypkie": sypkie,
        "item_warzywa": pozycja_warzywa,
        "item_sypkie": pozycja_sypkie,
    }


# --- macierz uprawnień (08_TESTING §4) --------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Listy zakupowe siedzą za sesją; publiczny jest wyłącznie link tokenowy."""
    data = await _household_list(db_session)
    list_id = data["list"].id
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-anonima")
    headers = {CSRF_HEADER_NAME: "token-anonima"}

    assert (await db_client.get(LISTS)).status_code == 401
    assert (await db_client.get(f"{LISTS}/{list_id}")).status_code == 401
    assert (
        await db_client.patch(f"{LISTS}/{list_id}", json={"name": "X"}, headers=headers)
    ).status_code == 401
    assert (await db_client.delete(f"{LISTS}/{list_id}", headers=headers)).status_code == 401
    assert (
        await db_client.post(f"{LISTS}/{list_id}/share", json={}, headers=headers)
    ).status_code == 401


async def test_obcy_user_nie_widzi_listy(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Cudza lista to 404, nie 403 — nie potwierdzamy istnienia (07_SECURITY §4)."""
    data = await _household_list(db_session)
    await login(db_client, data["stranger"].email)

    assert (await db_client.get(f"{LISTS}/{data['list'].id}")).status_code == 404
    assert (await db_client.get(LISTS)).json()["total"] == 0
    assert (
        await db_client.patch(
            f"{LISTS}/{data['list'].id}",
            json={"name": "Podmiana"},
            headers=csrf_headers(db_client),
        )
    ).status_code == 404


async def test_obcy_user_nie_widzi_pozycji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pozycja nie ma własnego scope — dziedziczy go po liście (04_API §2c)."""
    data = await _household_list(db_session)
    await login(db_client, data["stranger"].email)

    response = await db_client.patch(
        f"{LISTS}/{data['list'].id}/items/{data['item_warzywa'].id}",
        json={"checked": True},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404


async def test_czlonek_rodziny_czyta_i_edytuje_liste_household(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odczyt i edycja HOUSEHOLD: 200 dla członka rodziny (macierz 08_TESTING §4)."""
    data = await _household_list(db_session)
    await login(db_client, data["member"].email)

    assert (await db_client.get(f"{LISTS}/{data['list'].id}")).status_code == 200
    zmiana = await db_client.patch(
        f"{LISTS}/{data['list'].id}",
        json={"name": "Zakupy na weekend"},
        headers=csrf_headers(db_client),
    )
    assert zmiana.status_code == 200
    assert zmiana.json()["name"] == "Zakupy na weekend"


async def test_czlonek_rodziny_nie_usuwa_listy_a_wlasciciel_tak(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Usunięcie to wiersz „zmiana scope / delete": członek 403, właściciel 204."""
    data = await _household_list(db_session)

    await login(db_client, data["member"].email)
    odmowa = await db_client.delete(f"{LISTS}/{data['list'].id}", headers=csrf_headers(db_client))
    assert odmowa.status_code == 403

    await login(db_client, data["owner"].email)
    usuniecie = await db_client.delete(
        f"{LISTS}/{data['list'].id}", headers=csrf_headers(db_client)
    )
    assert usuniecie.status_code == 204
    assert (await db_client.get(f"{LISTS}/{data['list'].id}")).status_code == 404


async def test_admin_widzi_i_usuwa_cudza_liste(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ADMIN ma 200 w każdym wierszu macierzy, także na ścieżkach użytkownika (D16)."""
    data = await _household_list(db_session, scope=Scope.PRIVATE)
    await login(db_client, data["admin"].email)

    assert (await db_client.get(f"{LISTS}/{data['list'].id}")).status_code == 200
    assert (
        await db_client.delete(f"{LISTS}/{data['list'].id}", headers=csrf_headers(db_client))
    ).status_code == 204


async def test_lista_private_jest_niewidoczna_dla_czlonka_rodziny(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odczyt PRIVATE: 404 nawet dla członka rodziny (macierz 08_TESTING §4)."""
    data = await _household_list(db_session, scope=Scope.PRIVATE)
    await login(db_client, data["member"].email)

    assert (await db_client.get(f"{LISTS}/{data['list'].id}")).status_code == 404


# --- odhaczanie i „mam już w domu" ------------------------------------------------


async def test_odhaczenie_jest_trwale_i_ustawia_checked_at(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 1: stan checkboxa przetrwa ponowne pobranie listy; `checked_at` z serwera."""
    data = await _household_list(db_session)
    await login(db_client, data["owner"].email)
    item_id = data["item_sypkie"].id

    patch = await db_client.patch(
        f"{LISTS}/{data['list'].id}/items/{item_id}",
        json={"checked": True},
        headers=csrf_headers(db_client),
    )
    assert patch.status_code == 200
    assert patch.json()["checked"] is True
    assert patch.json()["checked_at"] is not None

    ponownie = await db_client.get(f"{LISTS}/{data['list'].id}")
    pozycje = [item for section in ponownie.json()["sections"] for item in section["items"]]
    assert [item["checked"] for item in pozycje if item["id"] == item_id] == [True]


async def test_patch_already_have_przenosi_pozycje_na_dol_sekcji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2: „mam już w domu" zostaje widoczne, ale spada na koniec swojej sekcji."""
    data = await _household_list(db_session)
    await login(db_client, data["owner"].email)
    # Druga pozycja w sekcji „Warzywa", żeby było co przesuwać.
    druga = await create_shopping_list_item(
        db_session,
        shopping_list=data["list"],
        category=data["warzywa"],
        product=await create_product(db_session, category=data["warzywa"], name="Ogórek"),
        label="Ogórek",
        position=2,
    )

    await db_client.patch(
        f"{LISTS}/{data['list'].id}/items/{data['item_warzywa'].id}",
        json={"already_have": True},
        headers=csrf_headers(db_client),
    )

    sekcje = (await db_client.get(f"{LISTS}/{data['list'].id}")).json()["sections"]
    warzywa = next(s for s in sekcje if s["category_id"] == data["warzywa"].id)
    assert [item["id"] for item in warzywa["items"]] == [druga.id, data["item_warzywa"].id]


async def test_patch_pozycji_bez_zadnego_pola_daje_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Puste ciało PATCH-a nie jest „operacją bez efektu", tylko błędem wejścia."""
    data = await _household_list(db_session)
    await login(db_client, data["owner"].email)

    response = await db_client.patch(
        f"{LISTS}/{data['list'].id}/items/{data['item_warzywa'].id}",
        json={},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


# --- sortowanie sekcji wg profilu sklepu ------------------------------------------


async def test_sekcje_bez_sklepu_ida_wg_globalnej_kolejnosci_kategorii(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Lista bez sklepu: kolejność ze słownika (`product_categories.position`)."""
    data = await _household_list(db_session)
    await login(db_client, data["owner"].email)

    sekcje = (await db_client.get(f"{LISTS}/{data['list'].id}")).json()["sections"]

    assert [s["category_name"] for s in sekcje] == ["Warzywa", "Sypkie"]


async def test_zmiana_sklepu_przesortowuje_sekcje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 1: przypisanie sklepu z profilem odwraca kolejność sekcji."""
    data = await _household_list(db_session)
    store = await create_store(db_session, name="Biedronka")
    # Profil: najpierw sypkie, potem warzywa — odwrotnie niż globalnie.
    await create_category_order(
        db_session, store=store, categories=[data["sypkie"], data["warzywa"]]
    )
    await login(db_client, data["owner"].email)

    patch = await db_client.patch(
        f"{LISTS}/{data['list'].id}",
        json={"store_id": store.id},
        headers=csrf_headers(db_client),
    )

    assert patch.status_code == 200
    assert patch.json()["store_name"] == "Biedronka"
    assert [s["category_name"] for s in patch.json()["sections"]] == ["Sypkie", "Warzywa"]


async def test_kategorie_spoza_profilu_ida_na_koniec(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Profil zawiera tylko dopisane kategorie — reszta na koniec wg słownika (B09)."""
    data = await _household_list(db_session)
    store = await create_store(db_session, name="Lidl")
    # W profilu WYŁĄCZNIE sypkie; warzywa są „poza sklepem".
    await create_category_order(db_session, store=store, categories=[data["sypkie"]])
    await login(db_client, data["owner"].email)

    patch = await db_client.patch(
        f"{LISTS}/{data['list'].id}",
        json={"store_id": store.id},
        headers=csrf_headers(db_client),
    )

    assert [s["category_name"] for s in patch.json()["sections"]] == ["Sypkie", "Warzywa"]


async def test_odpiecie_sklepu_wraca_do_kolejnosci_globalnej(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`clear_store` odpina profil; `null` w PATCH-u byłby nieodróżnialny od „bez zmian"."""
    data = await _household_list(db_session)
    store = await create_store(db_session, name="Auchan")
    await create_category_order(
        db_session, store=store, categories=[data["sypkie"], data["warzywa"]]
    )
    await login(db_client, data["owner"].email)
    headers = csrf_headers(db_client)

    await db_client.patch(
        f"{LISTS}/{data['list'].id}", json={"store_id": store.id}, headers=headers
    )
    odpiecie = await db_client.patch(
        f"{LISTS}/{data['list'].id}", json={"clear_store": True}, headers=headers
    )

    assert odpiecie.json()["store_id"] is None
    assert [s["category_name"] for s in odpiecie.json()["sections"]] == ["Warzywa", "Sypkie"]


async def test_nieistniejacy_sklep_w_patchu_daje_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """404 należy do zasobu z URL-a, nie do wartości jego pola (wzorzec z B08)."""
    data = await _household_list(db_session)
    await login(db_client, data["owner"].email)

    response = await db_client.patch(
        f"{LISTS}/{data['list'].id}",
        json={"store_id": 999_999},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_usuniecie_sklepu_uzytego_w_liscie_daje_409_z_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """FK ma SET NULL, więc 409 z `used_in` to JEDYNA obrona profilu listy (B09 pkt 2)."""
    data = await _household_list(db_session)
    store = await create_store(db_session, name="Kaufland")
    await login(db_client, data["owner"].email)
    headers = csrf_headers(db_client)
    await db_client.patch(
        f"{LISTS}/{data['list'].id}", json={"store_id": store.id}, headers=headers
    )

    response = await db_client.delete(f"{STORES}/{store.id}", headers=headers)

    assert response.status_code == 409
    used_in = response.json()["error"]["details"]["used_in"]
    assert {"type": "shopping_list", "id": data["list"].id, "name": data["list"].name} in used_in


# --- lista list -------------------------------------------------------------------


async def test_lista_list_filtruje_po_statusie_a_wygasle_zostaja(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D10: wygasła lista NIE znika z bazy — zmienia tylko kubełek filtra."""
    data = await _household_list(db_session)
    wygasla = await create_shopping_list(
        db_session,
        owner=data["owner"],
        name="Zakupy 01.01-07.01.2029",
        scope=Scope.HOUSEHOLD,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await login(db_client, data["owner"].email)

    wszystkie = (await db_client.get(LISTS)).json()
    aktywne = (await db_client.get(LISTS, params={"status": "active"})).json()
    przeterminowane = (await db_client.get(LISTS, params={"status": "expired"})).json()

    assert wszystkie["total"] == 2
    assert [row["id"] for row in aktywne["items"]] == [data["list"].id]
    assert [row["id"] for row in przeterminowane["items"]] == [wygasla.id]


async def test_lista_list_ma_liczniki_pozycji_i_stan_udostepnienia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Podsumowanie listy: ile pozycji, ile odhaczonych, czy link jest aktywny."""
    data = await _household_list(db_session)
    await login(db_client, data["owner"].email)
    headers = csrf_headers(db_client)
    await db_client.patch(
        f"{LISTS}/{data['list'].id}/items/{data['item_sypkie'].id}",
        json={"checked": True},
        headers=headers,
    )
    await db_client.post(f"{LISTS}/{data['list'].id}/share", json={}, headers=headers)

    wiersz = next(
        row for row in (await db_client.get(LISTS)).json()["items"] if row["id"] == data["list"].id
    )

    assert wiersz["items_total"] == 2
    assert wiersz["items_checked"] == 1
    assert wiersz["share"]["revoked"] is False
    assert wiersz["share"]["url"].startswith("/l/")
