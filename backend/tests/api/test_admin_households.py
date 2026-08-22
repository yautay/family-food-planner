"""Kontrakt HTTP `/admin/households`: macierz ról, CRUD i skład rodziny."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deletion import USED_IN_LIMIT
from tests.factories import (
    assign_to_household,
    create_admin,
    create_category,
    create_day_template,
    create_household,
    create_member_profile,
    create_pantry_item,
    create_plan_day,
    create_product,
    create_recipe,
    create_round_config,
    create_shopping_list,
    create_user,
    day_payload,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

HOUSEHOLDS = f"{API}/admin/households"


# --- macierz ról (08_TESTING §4) ----------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    assert (await db_client.get(HOUSEHOLDS)).status_code == 401


async def test_zwykly_uzytkownik_dostaje_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zarządzanie rodzinami to wyłącznie ADMIN (02_DOMAIN §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(HOUSEHOLDS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", HOUSEHOLDS),
        ("GET", f"{HOUSEHOLDS}/1"),
        ("PATCH", f"{HOUSEHOLDS}/1"),
        ("DELETE", f"{HOUSEHOLDS}/1"),
        ("PUT", f"{HOUSEHOLDS}/1/members"),
    ],
)
async def test_wszystkie_operacje_zamkniete_dla_usera(
    db_client: AsyncClient, db_session: AsyncSession, method: str, path: str
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.request(method, path, json={}, headers=csrf_headers(db_client))

    assert response.status_code == 403


async def test_mutacja_bez_csrf_daje_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(HOUSEHOLDS, json={"name": "Kowalscy"})

    assert response.status_code == 403


# --- CRUD ----------------------------------------------------------------------


async def test_admin_tworzy_rodzine(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(
        HOUSEHOLDS, json={"name": "  Kowalscy  "}, headers=csrf_headers(db_client)
    )

    body = response.json()
    assert response.status_code == 201
    assert body["name"] == "Kowalscy"
    assert body["members"] == []
    assert body["members_count"] == 0


async def test_lista_zwraca_items_total_i_liczniki(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session, name="Kowalscy")
    await create_household(db_session, name="Nowakowie")
    await create_user(db_session, email="czlonek@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, admin.email)

    response = await db_client.get(HOUSEHOLDS, params={"limit": 50, "offset": 0})

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 2
    kowalscy = next(item for item in body["items"] if item["name"] == "Kowalscy")
    assert kowalscy["members_count"] == 1
    assert kowalscy["profiles_count"] == 1


async def test_szczegoly_zawieraja_czlonkow_i_profile(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await create_user(db_session, email="czlonek@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, admin.email)

    response = await db_client.get(f"{HOUSEHOLDS}/{household.id}")

    body = response.json()
    assert response.status_code == 200
    assert [member["email"] for member in body["members"]] == ["czlonek@example.com"]
    assert [profile["name"] for profile in body["profiles"]] == ["Ania"]


async def test_nieistniejaca_rodzina_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.get(f"{HOUSEHOLDS}/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_admin_zmienia_nazwe_rodziny(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session, name="Kowalscy")
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{HOUSEHOLDS}/{household.id}",
        json={"name": "Kowalscy i Nowakowie"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Kowalscy i Nowakowie"


async def test_pusta_nazwa_jest_odrzucana(db_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await create_admin(db_session)
    await login(db_client, admin.email)

    response = await db_client.post(HOUSEHOLDS, json={"name": ""}, headers=csrf_headers(db_client))

    assert response.status_code == 422


# --- usuwanie ------------------------------------------------------------------


async def test_usuniecie_pustej_rodziny_dziala(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 204
    assert (await db_client.get(f"{HOUSEHOLDS}/{household.id}")).status_code == 404


async def test_usuniecie_rodziny_z_czlonkami_daje_409_z_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Blokada usunięcia z czytelną listą użyć (ADR-012, 04_API §1)."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    profile = await create_member_profile(db_session, household=household, name="Ania")
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    body = response.json()
    assert response.status_code == 409
    assert body["error"]["code"] == "conflict"
    assert {"type": "user", "id": member.id, "name": member.display_name} in body["error"][
        "details"
    ]["used_in"]
    assert {"type": "member_profile", "id": profile.id, "name": "Ania"} in body["error"]["details"][
        "used_in"
    ]


async def test_odpiete_konto_pozwala_usunac_rodzine(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pełna ścieżka naprawy 409: odepnij konta → usuń rodzinę."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await create_user(db_session, email="czlonek@example.com", household=household)
    await login(db_client, admin.email)

    await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": []},
        headers=csrf_headers(db_client),
    )
    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 204


async def test_u16_rodzine_trzymaja_encje_ze_scope_i_widac_je_w_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ustalenie REVIEW R3 (dług U16): 409 wymienia encje ze scope, nie pustą listę.

    Konto zostaje ODPIĘTE od rodziny, więc członków ani profili już nie ma —
    blokują wyłącznie encje ze scope, które zapisują `household_id` także dla
    `private` (ADR-006). Przed R3 ADMIN dostawał tu 409 z `used_in: []`
    (druga linia obrony na `IntegrityError`) i nie wiedział, co blokuje.
    """
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    category = await create_category(db_session, name="Warzywa R3")
    product = await create_product(db_session, category=category, name="Marchew R3")
    recipe = await create_recipe(db_session, owner=member, name="Zupa R3")
    plan_day = await create_plan_day(db_session, owner=member, day=date(2030, 5, 6))
    template = await create_day_template(
        db_session, owner=member, name="Szablon R3", payload=day_payload()
    )
    pantry_item = await create_pantry_item(db_session, owner=member, product=product)
    config = await create_round_config(db_session, owner=member, name="Tura R3")
    shopping_list = await create_shopping_list(db_session, owner=member, name="Zakupy R3")
    await assign_to_household(db_session, user=member, household=None)
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    body = response.json()
    assert response.status_code == 409
    used_in = body["error"]["details"]["used_in"]
    assert used_in, "409 bez listy użyć nie mówi ADMIN-owi, co blokuje rodzinę"
    assert {"type": "recipe", "id": recipe.id, "name": "Zupa R3"} in used_in
    assert {"type": "plan_day", "id": plan_day.id, "name": "Plan dnia 06.05.2030"} in used_in
    assert {"type": "day_template", "id": template.id, "name": "Szablon R3"} in used_in
    assert {"type": "pantry_item", "id": pantry_item.id, "name": "Marchew R3"} in used_in
    assert {
        "type": "shopping_round_config",
        "id": config.id,
        "name": "Tura R3",
    } in used_in
    assert {"type": "shopping_list", "id": shopping_list.id, "name": "Zakupy R3"} in used_in


async def test_u16_lista_uzyc_nie_przekracza_limitu_kontraktu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`used_in` jest listą DLA CZŁOWIEKA — kontrakt `core/deletion` ją przycina."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    for index in range(USED_IN_LIMIT + 5):
        await create_recipe(db_session, owner=member, name=f"Przepis R3 {index:02d}")
    await assign_to_household(db_session, user=member, household=None)
    await login(db_client, admin.email)

    response = await db_client.delete(
        f"{HOUSEHOLDS}/{household.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    assert len(response.json()["error"]["details"]["used_in"]) == USED_IN_LIMIT


# --- skład rodziny --------------------------------------------------------------


async def test_przypisanie_i_odpiecie_kont(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    anna = await create_user(db_session, email="anna@example.com")
    piotr = await create_user(db_session, email="piotr@example.com")
    await login(db_client, admin.email)

    przypisanie = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [anna.id, piotr.id]},
        headers=csrf_headers(db_client),
    )
    odpiecie = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [anna.id]},
        headers=csrf_headers(db_client),
    )

    assert przypisanie.status_code == 200
    assert {member["email"] for member in przypisanie.json()["members"]} == {
        "anna@example.com",
        "piotr@example.com",
    }
    assert [member["email"] for member in odpiecie.json()["members"]] == ["anna@example.com"]


async def test_przypisanie_do_nowej_rodziny_odpina_od_poprzedniej(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Konto należy do MAKSYMALNIE jednej rodziny (ADR-006)."""
    admin = await create_admin(db_session)
    stara = await create_household(db_session, name="Kowalscy")
    nowa = await create_household(db_session, name="Nowakowie")
    anna = await create_user(db_session, email="anna@example.com", household=stara)
    await login(db_client, admin.email)

    await db_client.put(
        f"{HOUSEHOLDS}/{nowa.id}/members",
        json={"user_ids": [anna.id]},
        headers=csrf_headers(db_client),
    )

    assert (await db_client.get(f"{HOUSEHOLDS}/{stara.id}")).json()["members"] == []
    assert len((await db_client.get(f"{HOUSEHOLDS}/{nowa.id}")).json()["members"]) == 1


async def test_odpiecie_konta_nie_kasuje_profilu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Profil wisi na rodzinie, nie na koncie (karta B03 §Implementation Notes)."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    anna = await create_user(db_session, email="anna@example.com", household=household)
    await create_member_profile(db_session, household=household, name="Ania", owner=anna)
    await login(db_client, admin.email)

    await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": []},
        headers=csrf_headers(db_client),
    )

    body = (await db_client.get(f"{HOUSEHOLDS}/{household.id}")).json()
    assert [profile["name"] for profile in body["profiles"]] == ["Ania"]


async def test_admin_moze_przypisac_do_rodziny_samego_siebie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Konto wykonujące operację siedzi już w sesji ORM — to inna ścieżka niż cudze."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [admin.id]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert [member["email"] for member in response.json()["members"]] == [admin.email]
    assert (await db_client.get(f"{API}/auth/me")).json()["household"] == {
        "id": household.id,
        "name": household.name,
    }


async def test_admin_przenosi_sam_siebie_miedzy_rodzinami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Przenosiny aktora: stara rodzina traci członka, nowa go zyskuje (ADR-006)."""
    stara = await create_household(db_session, name="Kowalscy")
    nowa = await create_household(db_session, name="Nowakowie")
    admin = await create_admin(db_session, email="admin@example.com")
    await assign_to_household(db_session, user=admin, household=stara)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{HOUSEHOLDS}/{nowa.id}/members",
        json={"user_ids": [admin.id]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert (await db_client.get(f"{HOUSEHOLDS}/{stara.id}")).json()["members"] == []
    assert [member["id"] for member in response.json()["members"]] == [admin.id]


async def test_nieistniejace_konto_w_skladzie_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{HOUSEHOLDS}/{household.id}/members",
        json={"user_ids": [999999]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404
    assert response.json()["error"]["details"]["user_ids"] == [999999]
