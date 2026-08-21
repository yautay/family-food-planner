"""Kontrakt HTTP `/shopping/*`: macierz uprawnień 08_TESTING §4, anty-IDOR, CSRF.

Trzy rzeczy, których pilnuje ten plik poza zwykłym kontraktem:

1. **Żadna odpowiedź nie zawiera `public_token`** — kolumna istnieje od migracji
   `0012`, ale udostępnianie należy do BATCH_11 (karta B10 §Security).
2. **`use_pantry` domyślnie fałszywe**: żądanie bez tego pola nie odejmuje stanu
   domowego (02_DOMAIN §8).
3. **Ilości wychodzą jako stringi dziesiętne** (ADR-008, 04_API §1).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.modules.catalog.models import Perishability
from app.modules.catalog.units import AmountUnit
from tests.factories import (
    create_admin,
    create_category,
    create_household,
    create_pantry_item,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_retail_product,
    create_round_config,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

SHOPPING = f"{API}/shopping"
CONFIGS = f"{SHOPPING}/round-configs"
WEEK_START = date(2030, 1, 7)
WEEK_END = date(2030, 1, 13)


def _generate_payload(**overrides: Any) -> dict[str, Any]:
    """Minimalne poprawne wejście `/generate` — bez `use_pantry` z rozmysłem."""
    return {
        "date_from": WEEK_START.isoformat(),
        "date_to": WEEK_END.isoformat(),
        **overrides,
    }


async def _plan_with_products(
    session: AsyncSession, owner: object, *, with_retail: bool = False
) -> dict[str, Any]:
    """Tydzień planu z produktem świeżym i trwałym — materiał na dwie tury."""
    fresh = await create_category(
        session, name="Warzywa", perishability=Perishability.FRESH, position=0
    )
    durable = await create_category(
        session, name="Sypkie", perishability=Perishability.DURABLE, position=5
    )
    tomato = await create_product(session, category=fresh, name="Pomidor")
    flour = await create_product(session, category=durable, name="Mąka")
    variant = None
    if with_retail:
        variant = await create_retail_product(
            session, product=flour, name="Mąka 1 kg", package_amount=Decimal("1000.00")
        )
    for offset in range(7):
        plan_day = await create_plan_day(
            session,
            owner=owner,  # type: ignore[arg-type]
            day=WEEK_START + timedelta(days=offset),
        )
        meal = await create_plan_meal(session, plan_day=plan_day, name="Obiad")
        await create_plan_item(
            session,
            meal=meal,
            product=tomato,
            amount=Decimal("100"),
            amount_unit=AmountUnit.GRAM,
        )
        await create_plan_item(
            session,
            meal=meal,
            product=flour,
            amount=Decimal("200"),
            amount_unit=AmountUnit.GRAM,
            position=1,
        )
    return {"tomato": tomato, "flour": flour, "variant": variant}


# --- macierz uprawnień (08_TESTING §4) --------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Cały obszar zakupów siedzi za sesją (04_API §3 pkt 1).

    Mutacje dostają własny token CSRF: bez niego middleware odpowiada 403
    JESZCZE PRZED autoryzacją, a tu testujemy brak sesji, nie brak tokenu.
    """
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-anonima")
    headers = {CSRF_HEADER_NAME: "token-anonima"}

    assert (await db_client.get(CONFIGS)).status_code == 401
    assert (await db_client.post(CONFIGS, json={}, headers=headers)).status_code == 401
    assert (
        await db_client.post(f"{SHOPPING}/generate", json=_generate_payload(), headers=headers)
    ).status_code == 401
    assert (await db_client.get(f"{SHOPPING}/generations/1")).status_code == 401
    assert (
        await db_client.post(f"{SHOPPING}/generations/1/resolve", json={}, headers=headers)
    ).status_code == 401
    assert (
        await db_client.post(f"{SHOPPING}/generations/1/finalize", json={}, headers=headers)
    ).status_code == 401
    assert (await db_client.delete(f"{SHOPPING}/generations/1", headers=headers)).status_code == 401


async def test_mutacja_bez_naglowka_csrf_to_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Double-submit obowiązuje każdą mutację (07_SECURITY §3)."""
    user = await create_user(db_session, email="csrf@example.com")
    await login(db_client, user.email)

    response = await db_client.post(f"{SHOPPING}/generate", json=_generate_payload())

    assert response.status_code == 403


async def test_obcy_uzytkownik_nie_widzi_cudzej_generacji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Anty-IDOR: cudza generacja i nieistniejąca dają identyczne 404."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    await _plan_with_products(db_session, owner)

    await login(db_client, owner.email)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=csrf_headers(db_client)
    )
    assert created.status_code == 201
    generation_id = created.json()["id"]

    await login(db_client, stranger.email)
    headers = csrf_headers(db_client)
    assert (await db_client.get(f"{SHOPPING}/generations/{generation_id}")).status_code == 404
    assert (
        await db_client.post(
            f"{SHOPPING}/generations/{generation_id}/resolve", json={}, headers=headers
        )
    ).status_code == 404
    assert (
        await db_client.post(
            f"{SHOPPING}/generations/{generation_id}/finalize", json={}, headers=headers
        )
    ).status_code == 404
    assert (await db_client.get(f"{SHOPPING}/generations/999999")).status_code == 404


async def test_czlonek_rodziny_widzi_generacje_rodzinna(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Generacja użytkownika z rodziną jest HOUSEHOLD, więc widzi ją drugi członek."""
    household = await create_household(db_session)
    author = await create_user(db_session, email="autor@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    await _plan_with_products(db_session, author)

    await login(db_client, author.email)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=csrf_headers(db_client)
    )
    generation_id = created.json()["id"]
    assert created.json()["scope"] == "household"

    await login(db_client, member.email)
    assert (await db_client.get(f"{SHOPPING}/generations/{generation_id}")).status_code == 200


async def test_admin_widzi_cudza_generacje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D16: ADMIN widzi encje ze scope także na ścieżkach użytkownika."""
    owner = await create_user(db_session, email="user-gen@example.com")
    admin = await create_admin(db_session, email="admin-gen@example.com")
    await _plan_with_products(db_session, owner)

    await login(db_client, owner.email)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=csrf_headers(db_client)
    )
    generation_id = created.json()["id"]

    await login(db_client, admin.email)
    assert (await db_client.get(f"{SHOPPING}/generations/{generation_id}")).status_code == 200


async def test_czlonek_rodziny_nie_usuwa_cudzej_tury(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wiersz „zmiana scope / delete" macierzy: członek rodziny dostaje 403."""
    household = await create_household(db_session)
    author = await create_user(db_session, email="tura-autor@example.com", household=household)
    member = await create_user(db_session, email="tura-czlonek@example.com", household=household)
    config = await create_round_config(db_session, owner=author, scope=Scope.HOUSEHOLD)

    await login(db_client, member.email)
    headers = csrf_headers(db_client)

    # Edycja treści: wolno każdemu członkowi rodziny.
    assert (
        await db_client.patch(f"{CONFIGS}/{config.id}", json={"name": "Sobota"}, headers=headers)
    ).status_code == 200
    # Usunięcie: wyłącznie właściciel albo ADMIN.
    assert (await db_client.delete(f"{CONFIGS}/{config.id}", headers=headers)).status_code == 403


# --- konfiguracja tur -------------------------------------------------------------


async def test_pierwsze_wejscie_zasiewa_preset_tur(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 1: GET bez konfiguracji tworzy edytowalny preset niedziela/środa."""
    user = await create_user(db_session, email="preset@example.com")
    await login(db_client, user.email)

    first = await db_client.get(CONFIGS)
    second = await db_client.get(CONFIGS)

    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 2
    assert [row["name"] for row in body["items"]] == ["Niedziela", "Środa"]
    assert body["items"][0]["shopping_weekday"] == 6
    assert body["items"][0]["mode"] == "durable_plus_fresh_window"
    assert body["items"][0]["fresh_days"] == 4
    assert body["items"][1]["mode"] == "fresh_only"
    # Idempotencja: drugi odczyt nie dokłada kolejnych tur.
    assert second.json()["total"] == 2


async def test_crud_tury_zakupowej(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """AC 1: dodanie, edycja i usunięcie tury działa na własnej konfiguracji."""
    user = await create_user(db_session, email="crud-tur@example.com")
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        CONFIGS,
        json={"name": "Sobota", "mode": "all", "covers_days": 5, "shopping_weekday": 5},
        headers=headers,
    )
    assert created.status_code == 201
    config_id = created.json()["id"]
    assert created.json()["fresh_days"] is None

    updated = await db_client.patch(
        f"{CONFIGS}/{config_id}",
        json={"covers_days": 4, "clear_shopping_weekday": True},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["covers_days"] == 4
    assert updated.json()["shopping_weekday"] is None

    removed = await db_client.delete(f"{CONFIGS}/{config_id}", headers=headers)
    assert removed.status_code == 204


async def test_okno_swiezych_w_zlym_trybie_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Martwe ustawienie nie ma prawa się zapisać (walidacja schematu)."""
    user = await create_user(db_session, email="zle-okno@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        CONFIGS,
        json={"name": "Środa", "mode": "fresh_only", "covers_days": 3, "fresh_days": 2},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


# --- generacja, resolve, finalize -------------------------------------------------


async def test_generate_zwraca_preview_bez_tokenu_publicznego(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2 + §Security: odpowiedź ma podgląd i ani śladu `public_token`."""
    user = await create_user(db_session, email="preview@example.com")
    await _plan_with_products(db_session, user, with_retail=True)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=csrf_headers(db_client)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "preview"
    assert body["use_pantry"] is False
    assert body["has_blockers"] is False
    assert [round_view["name"] for round_view in body["rounds"]] == ["Niedziela", "Środa"]

    sunday = body["rounds"][0]
    assert sunday["shopping_weekday"] == 6
    assert sunday["shopping_date"] == "2030-01-06"
    flour = next(item for item in sunday["items"] if item["label"] == "Mąka 1 kg")
    # Ilości i opakowania to STRINGI dziesiętne (ADR-008).
    assert flour["needed_amount"] == "1400.000"
    assert flour["packages_count"] == 2
    assert flour["package_amount"] == "1000.00"
    assert flour["leftover_amount"] == "600.000"
    assert flour["from_pantry_amount"] is None
    assert flour["retail_options"][0]["package_amount"] == "1000.00"

    assert "public_token" not in response.text
    assert "token_revoked" not in response.text
    assert "params" not in body


async def test_generate_bez_use_pantry_nie_odejmuje_stanu_domowego(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 3: brak pola = brak odejmowania; z `true` odjęcie jest widoczne."""
    user = await create_user(db_session, email="pantry-api@example.com")
    products = await _plan_with_products(db_session, user)
    await create_pantry_item(
        db_session, owner=user, product=products["flour"], amount=Decimal("500.000")
    )
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    without = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=headers
    )
    with_pantry = await db_client.post(
        f"{SHOPPING}/generate",
        json=_generate_payload(use_pantry=True),
        headers=headers,
    )

    def _flour(body: dict[str, Any]) -> dict[str, Any]:
        return next(item for item in body["rounds"][0]["items"] if item["label"] == "Mąka")

    assert _flour(without.json())["needed_amount"] == "1400.000"
    assert _flour(without.json())["from_pantry_amount"] is None
    assert with_pantry.json()["use_pantry"] is True
    assert _flour(with_pantry.json())["needed_amount"] == "900.000"
    assert _flour(with_pantry.json())["from_pantry_amount"] == "500.000"


async def test_get_generacji_odtwarza_ten_sam_preview(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2: odczyt generacji daje identyczny podgląd co jej utworzenie."""
    user = await create_user(db_session, email="get-gen@example.com")
    await _plan_with_products(db_session, user, with_retail=True)
    await login(db_client, user.email)

    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=csrf_headers(db_client)
    )
    fetched = await db_client.get(f"{SHOPPING}/generations/{created.json()['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["rounds"] == created.json()["rounds"]
    assert fetched.json()["issues"] == created.json()["issues"]


async def test_resolve_oznacza_mam_w_domu_i_wybiera_wariant(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 4 + 6: decyzje zmieniają podgląd, a pozycja zostaje widoczna."""
    user = await create_user(db_session, email="resolve-api@example.com")
    products = await _plan_with_products(db_session, user, with_retail=True)
    big = await create_retail_product(
        db_session,
        product=products["flour"],
        name="Mąka 5 kg",
        package_amount=Decimal("5000.00"),
    )
    await login(db_client, user.email)
    headers = csrf_headers(db_client)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=headers
    )
    generation_id = created.json()["id"]

    resolved = await db_client.post(
        f"{SHOPPING}/generations/{generation_id}/resolve",
        json={
            "already_have": [products["tomato"].id],
            "retail_choices": [{"product_id": products["flour"].id, "retail_product_id": big.id}],
        },
        headers=headers,
    )

    assert resolved.status_code == 200
    items = resolved.json()["rounds"][0]["items"]
    tomato = next(item for item in items if item["product_id"] == products["tomato"].id)
    flour = next(item for item in items if item["product_id"] == products["flour"].id)
    assert tomato["already_have"] is True
    assert tomato["needed_amount"] == "400.000"
    assert flour["retail_product_id"] == big.id
    assert flour["packages_count"] == 1
    assert flour["leftover_amount"] == "3600.000"
    # Odpowiedź niesie WYŁĄCZNIE jawny wybór użytkownika — automat (pomidor bez
    # wariantu, mąka 1 kg dobrana samoczynnie w `generate`) tu nie wchodzi.
    assert resolved.json()["retail_choices"] == [
        {"product_id": products["flour"].id, "retail_product_id": big.id}
    ]
    assert created.json()["retail_choices"] == []


async def test_resolve_z_nieznanym_produktem_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Decyzja o produkcie spoza generacji to błąd wejścia, nie ciche pominięcie."""
    user = await create_user(db_session, email="resolve-422@example.com")
    await _plan_with_products(db_session, user)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=headers
    )

    response = await db_client.post(
        f"{SHOPPING}/generations/{created.json()['id']}/resolve",
        json={"already_have": [999999]},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_finalize_tworzy_listy_per_tura(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 6: finalizacja zwraca listy per tura z kompletem pozycji, bez tokenów."""
    user = await create_user(db_session, email="finalize-api@example.com")
    await _plan_with_products(db_session, user, with_retail=True)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=headers
    )

    response = await db_client.post(
        f"{SHOPPING}/generations/{created.json()['id']}/finalize", headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["total"] == 2
    assert [row["round_name"] for row in body["items"]] == ["Niedziela", "Środa"]
    assert body["items"][0]["name"] == "Zakupy 07.01-13.01.2030"
    assert body["items"][0]["store_id"] is None
    first_item = body["items"][0]["items"][0]
    assert first_item["needed_amount"] == "400.000"
    assert first_item["checked"] is False
    assert "public_token" not in response.text
    assert "token_revoked" not in response.text

    # Powtórna finalizacja tej samej generacji jest konfliktem, nie duplikatem.
    again = await db_client.post(
        f"{SHOPPING}/generations/{created.json()['id']}/finalize", headers=headers
    )
    assert again.status_code == 409


async def test_finalize_z_blokerem_to_409_z_powodami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 6: bloker zatrzymuje finalizację i mówi, co rozstrzygnąć."""
    user = await create_user(db_session, email="bloker-api@example.com")
    category = await create_category(db_session, name="Napoje", position=1)
    milk = await create_product(db_session, category=category, name="Mleko")
    plan_day = await create_plan_day(db_session, owner=user, day=WEEK_START)
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Śniadanie")
    await create_plan_item(
        db_session,
        meal=meal,
        product=milk,
        amount=Decimal("200"),
        amount_unit=AmountUnit.PIECE,
    )
    await login(db_client, user.email)
    headers = csrf_headers(db_client)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=headers
    )
    assert created.json()["has_blockers"] is True

    response = await db_client.post(
        f"{SHOPPING}/generations/{created.json()['id']}/finalize", headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert response.json()["error"]["details"]["issues"][0]["kind"] == "plan_item_without_amount"


async def test_odrzucenie_generacji_jest_miekkie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE zmienia status na `discarded` — wiersz zostaje (D10)."""
    user = await create_user(db_session, email="discard-api@example.com")
    await _plan_with_products(db_session, user)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)
    created = await db_client.post(
        f"{SHOPPING}/generate", json=_generate_payload(), headers=headers
    )
    generation_id = created.json()["id"]

    removed = await db_client.delete(f"{SHOPPING}/generations/{generation_id}", headers=headers)

    assert removed.status_code == 204
    fetched = await db_client.get(f"{SHOPPING}/generations/{generation_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "discarded"


async def test_odwrocony_zakres_dat_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zakres „od" późniejszy niż „do" nie ma sensu — 422 z walidacji schematu."""
    user = await create_user(db_session, email="zakres@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        f"{SHOPPING}/generate",
        json={"date_from": WEEK_END.isoformat(), "date_to": WEEK_START.isoformat()},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
