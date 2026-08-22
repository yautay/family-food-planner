"""LWW checkboxa listy zakupowej: `checked_at` od klienta (ADR-009, karta B12).

Dlaczego to jest osobny plik testów, a nie kilka asercji dopiętych do
`test_shopping_lists_api.py`: `checked_at` przysyła WYŁĄCZNIE kolejka offline,
a jej kontrakt ma cztery reguły, które muszą obowiązywać razem i na OBU
ścieżkach (zalogowanej i publicznej):

1. brak `checked_at` w żądaniu = czas serwera (zachowanie z B11 nietknięte),
2. znacznik STARSZY niż zapisany przegrywa — 200 ze stanem serwera, bez zmiany,
3. znacznik z przyszłości poza tolerancją jest przycinany do czasu serwera
   (rozjechany zegar telefonu nie może zabetonować pozycji),
4. powtórka tego samego żądania nie przesuwa znacznika (idempotencja z R3, na
   której stoi ponawianie z kolejki po utracie odpowiedzi).

Czas czytamy z bazy, a nie z odpowiedzi API tam, gdzie chodzi o „czy w ogóle
drgnął": odpowiedź pokazuje wartość, ale to kolumna jest kontraktem LWW.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token
from app.modules.catalog.models import Perishability
from app.modules.shopping.models import ShoppingListItem
from tests.factories import (
    create_category,
    create_product,
    create_shopping_list,
    create_shopping_list_item,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

LISTS = f"{API}/shopping/lists"
PUBLIC = f"{API}/public/lists"

EMAIL = "lww@example.com"


async def _list_with_item(session: AsyncSession, *, token: str | None = None) -> dict[str, Any]:
    """Lista jednego użytkownika z jedną pozycją; opcjonalnie z publicznym tokenem."""
    owner = await create_user(session, email=EMAIL)
    category = await create_category(
        session, name="Sypkie", perishability=Perishability.DURABLE, position=3
    )
    product = await create_product(session, category=category, name="Mąka pszenna")
    shopping_list = await create_shopping_list(session, owner=owner, public_token=token)
    item = await create_shopping_list_item(
        session,
        shopping_list=shopping_list,
        category=category,
        product=product,
        label="Mąka pszenna 1 kg",
        needed_amount=Decimal("1000.000"),
    )
    return {"owner": owner, "list": shopping_list, "item": item}


async def _item_row(session: AsyncSession, item_id: int) -> ShoppingListItem:
    """Świeży odczyt pozycji z bazy — bez śladu obiektu z fabryki."""
    session.expire_all()
    return (
        await session.execute(select(ShoppingListItem).where(ShoppingListItem.id == item_id))
    ).scalar_one()


# --- ścieżka zalogowana ------------------------------------------------------------


async def test_checked_at_od_klienta_zapisuje_sie_gdy_jest_nowszy(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Znacznik z kolejki offline jest młodszy niż zapisany, więc wygrywa."""
    data = await _list_with_item(db_session)
    await login(db_client, EMAIL)
    list_id = data["list"].id
    item_id = data["item"].id
    path = f"{LISTS}/{list_id}/items/{item_id}"

    # Pierwsze odhaczenie: bez znacznika, więc czas ustawia serwer.
    first = await db_client.patch(path, json={"checked": True}, headers=csrf_headers(db_client))
    assert first.status_code == 200
    server_stamp = datetime.fromisoformat(first.json()["checked_at"])

    # Odznaczenie z telefonu, decyzja PÓŹNIEJSZA niż zapisana.
    nowszy = server_stamp + timedelta(minutes=3)
    second = await db_client.patch(
        path,
        json={"checked": False, "checked_at": nowszy.isoformat()},
        headers=csrf_headers(db_client),
    )

    assert second.status_code == 200
    assert second.json()["checked"] is False
    row = await _item_row(db_session, item_id)
    assert row.checked is False
    assert row.checked_at == nowszy


async def test_checked_at_starszy_niz_w_bazie_nie_zmienia_stanu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Konflikt LWW: odhaczenie sprzed pół godziny NIE cofa świeższej decyzji.

    To jest sedno ADR-009: telefon, który pierwszy złapał sieć, nie może wygrać
    tylko dlatego, że pierwszy złapał sieć. Odpowiedź jest 200 ze stanem
    AKTUALNYM — klient ma go przyjąć, a nie ponawiać żądanie w kółko.
    """
    data = await _list_with_item(db_session)
    await login(db_client, EMAIL)
    list_id = data["list"].id
    item_id = data["item"].id
    path = f"{LISTS}/{list_id}/items/{item_id}"

    first = await db_client.patch(path, json={"checked": True}, headers=csrf_headers(db_client))
    server_stamp = datetime.fromisoformat(first.json()["checked_at"])
    starszy = server_stamp - timedelta(minutes=30)

    response = await db_client.patch(
        path,
        json={"checked": False, "checked_at": starszy.isoformat()},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["checked"] is True, "starszy znacznik nie może cofnąć decyzji"
    row = await _item_row(db_session, item_id)
    assert row.checked is True
    assert row.checked_at == server_stamp


async def test_checked_at_z_przyszlosci_jest_przycinany_do_czasu_serwera(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rozjechany zegar telefonu nie może zabetonować pozycji.

    Bez przycinania znacznik z jutra sprawiłby, że żadna prawdziwa decyzja nie
    byłaby od niego młodsza — checkbox przestałby reagować do jutra.
    """
    data = await _list_with_item(db_session)
    await login(db_client, EMAIL)
    path = f"{LISTS}/{data['list'].id}/items/{data['item'].id}"
    z_przyszlosci = datetime.now(UTC) + timedelta(days=1)

    response = await db_client.patch(
        path,
        json={"checked": True, "checked_at": z_przyszlosci.isoformat()},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    zapisany = datetime.fromisoformat(response.json()["checked_at"])
    assert zapisany < z_przyszlosci - timedelta(hours=1)
    # A skoro znacznik jest z teraz, kolejna decyzja normalnie przechodzi.
    kolejna = await db_client.patch(
        path,
        json={"checked": False, "checked_at": (zapisany + timedelta(seconds=30)).isoformat()},
        headers=csrf_headers(db_client),
    )
    assert kolejna.json()["checked"] is False


async def test_checked_at_bez_strefy_czasowej_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Naiwna data to 422: porównanie z `timestamptz` musi mieć punkt w czasie.

    „14:03" bez strefy znaczy co innego w Warszawie i w UTC, a LWW rozstrzyga
    właśnie na porównaniu — zgadywanie strefy byłoby zgadywaniem wyniku.
    """
    data = await _list_with_item(db_session)
    await login(db_client, EMAIL)

    response = await db_client.patch(
        f"{LISTS}/{data['list'].id}/items/{data['item'].id}",
        json={"checked": True, "checked_at": "2030-01-06T14:03:00"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_powtorzony_patch_nie_przesuwa_znacznika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Idempotencja (R3): kolejka po utracie odpowiedzi wyśle to samo żądanie.

    Gdyby powtórka przesuwała `checked_at`, każde ponowienie z kolejki offline
    „odmładzało" decyzję i wygrywało LWW z późniejszą, prawdziwą zmianą
    z drugiego telefonu.
    """
    data = await _list_with_item(db_session)
    await login(db_client, EMAIL)
    path = f"{LISTS}/{data['list'].id}/items/{data['item'].id}"
    stamp = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    payload = {"checked": True, "checked_at": stamp}

    first = await db_client.patch(path, json=payload, headers=csrf_headers(db_client))
    second = await db_client.patch(path, json=payload, headers=csrf_headers(db_client))

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["checked_at"] == second.json()["checked_at"]
    assert second.json()["checked"] is True


# --- ścieżka publiczna -------------------------------------------------------------


async def test_publiczny_patch_przyjmuje_checked_at(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kolejka offline działa też pod linkiem `/l/:token` — bez sesji i bez CSRF."""
    token = generate_token()
    data = await _list_with_item(db_session, token=token)
    item_id = data["item"].id
    stamp = datetime.now(UTC) - timedelta(minutes=2)

    response = await db_client.patch(
        f"{PUBLIC}/{token}/items/{item_id}",
        json={"checked": True, "checked_at": stamp.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["checked"] is True
    row = await _item_row(db_session, item_id)
    assert row.checked_at == stamp


async def test_publiczny_patch_starszym_znacznikiem_nie_cofa_decyzji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """LWW obowiązuje pod publicznym linkiem tak samo jak u zalogowanego."""
    token = generate_token()
    data = await _list_with_item(db_session, token=token)
    item_id = data["item"].id
    path = f"{PUBLIC}/{token}/items/{item_id}"

    first = await db_client.patch(path, json={"checked": True})
    assert first.status_code == 200
    # Odpowiedź publiczna nie wystawia `checked_at` (biała lista pól), więc
    # znacznik serwera czytamy z bazy.
    server_stamp = (await _item_row(db_session, item_id)).checked_at
    assert server_stamp is not None

    response = await db_client.patch(
        path,
        json={"checked": False, "checked_at": (server_stamp - timedelta(hours=1)).isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["checked"] is True
    row = await _item_row(db_session, item_id)
    assert row.checked is True
    assert row.checked_at == server_stamp


async def test_publiczny_patch_z_checked_at_na_wygaslym_tokenie_daje_410(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Token wygasł, gdy telefon był offline: flush dostaje 410, nie 200.

    Kolejka ma wtedy przestać ponawiać i pokazać ekran „lista wygasła" — dlatego
    ten scenariusz jest w testach kontraktu, a nie tylko w vitest.
    """
    token = generate_token()
    owner = await create_user(db_session, email="wygasla@example.com")
    category = await create_category(
        db_session, name="Sypkie", perishability=Perishability.DURABLE, position=3
    )
    product = await create_product(db_session, category=category, name="Mąka pszenna")
    shopping_list = await create_shopping_list(
        db_session,
        owner=owner,
        public_token=token,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    item = await create_shopping_list_item(
        db_session,
        shopping_list=shopping_list,
        category=category,
        product=product,
        label="Mąka pszenna 1 kg",
        needed_amount=Decimal("1000.000"),
    )

    response = await db_client.patch(
        f"{PUBLIC}/{token}/items/{item.id}",
        json={"checked": True, "checked_at": datetime.now(UTC).isoformat()},
    )

    assert response.status_code == 410
    row = await _item_row(db_session, item.id)
    assert row.checked is False


async def test_publiczna_odpowiedz_nie_zawiera_received_at(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D19: osoba z linkiem nie ma nic wiedzieć o spiżarni rodziny.

    Zbioru kluczy pilnuje `test_public_response_has_no_pii`; ten test nazywa
    powód wprost, żeby przy dokładaniu pól do `PublicListItemRead` nie trzeba
    było go szukać w historii decyzji.
    """
    token = generate_token()
    data = await _list_with_item(db_session, token=token)

    lista = await db_client.get(f"{PUBLIC}/{token}")
    odhaczenie = await db_client.patch(
        f"{PUBLIC}/{token}/items/{data['item'].id}", json={"checked": True}
    )

    assert "received_at" not in lista.json()["items"][0]
    assert "received_at" not in odhaczenie.json()
