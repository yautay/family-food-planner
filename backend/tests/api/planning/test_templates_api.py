"""Kontrakt HTTP `/templates/*` i `/cycles`: macierz uprawnień 08_TESTING §4.

Szablony i cykle są encjami ze scope, więc macierz dowodzimy KODAMI HTTP
(anonim 401 / obcy 404 / członek rodziny 200 / zmiana scope przez członka 403).
Osobno sprawdzamy to, co przy payloadzie JSONB kusi najbardziej: przyjęcie
dowolnego JSON-a. Kontrakt `v:1` musi odrzucać wszystko, co się w nim nie mieści
(karta B07 §Security), bo payload jedzie potem prosto do wiersza planu.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from tests.factories import (
    create_admin,
    create_day_template,
    create_household,
    create_recipe,
    create_user,
    create_week_cycle,
    create_week_template,
    day_payload,
    template_meal,
    template_recipe_item,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

TEMPLATES = f"{API}/templates"
CYCLES = f"{API}/cycles"
MONDAY = "2026-08-17"
TUESDAY = "2026-08-18"


# --- macierz uprawnień: szablon dnia -----------------------------------------------


async def test_anonim_nie_widzi_szablonow(db_client: AsyncClient) -> None:
    """Wszystko poza /health, /auth/login i /public/* wymaga sesji (04_API §3.1)."""
    for url in (f"{TEMPLATES}/days", f"{TEMPLATES}/weeks", CYCLES):
        assert (await db_client.get(url)).status_code == 401


async def test_obcy_uzytkownik_dostaje_404_na_cudzym_szablonie(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Cudzy PRIVATE to 404, nie 403 — nie potwierdzamy istnienia (07_SECURITY §4)."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    template = await create_day_template(db_session, owner=owner, name="Prywatny")

    await login(db_client, stranger.email)

    assert (await db_client.get(f"{TEMPLATES}/days/{template.id}")).status_code == 404
    response = await db_client.delete(
        f"{TEMPLATES}/days/{template.id}", headers=csrf_headers(db_client)
    )
    assert response.status_code == 404


async def test_czlonek_rodziny_widzi_szablon_household(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    template = await create_day_template(
        db_session, owner=owner, name="Rodzinny", scope=Scope.HOUSEHOLD
    )

    await login(db_client, member.email)
    response = await db_client.get(f"{TEMPLATES}/days/{template.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Rodzinny"


async def test_czlonek_rodziny_nie_zmieni_scope_ani_nie_usunie(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Zmiana scope i usunięcie: właściciel albo ADMIN (macierz 08_TESTING §4)."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    template = await create_day_template(
        db_session, owner=owner, name="Rodzinny", scope=Scope.HOUSEHOLD
    )

    await login(db_client, member.email)
    headers = csrf_headers(db_client)

    scope_change = await db_client.put(
        f"{TEMPLATES}/days/{template.id}",
        json={"name": "Rodzinny", "scope": "private", "payload": day_payload()},
        headers=headers,
    )
    assert scope_change.status_code == 403

    removal = await db_client.delete(f"{TEMPLATES}/days/{template.id}", headers=headers)
    assert removal.status_code == 403


async def test_wlasciciel_zarzadza_swoim_szablonem(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    user = await create_user(db_session)
    template = await create_day_template(db_session, owner=user)

    await login(db_client, user.email)
    response = await db_client.delete(
        f"{TEMPLATES}/days/{template.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 204


async def test_admin_widzi_cudzy_szablon_na_sciezkach_uzytkownika(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Stan faktyczny D16 (jak w B06) — asercja, nie preferencja."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    admin = await create_admin(db_session, email="admin@example.com")
    template = await create_day_template(db_session, owner=owner, name="Cudzy")

    await login(db_client, admin.email)
    response = await db_client.get(f"{TEMPLATES}/days/{template.id}")

    assert response.status_code == 200


async def test_mutacja_bez_naglowka_csrf_jest_odrzucana(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """CSRF double-submit obowiązuje każdą niebezpieczną metodę (07_SECURITY §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{TEMPLATES}/days", json={"name": "Bez CSRF", "payload": day_payload()}
    )

    assert response.status_code == 403


# --- kontrakt payloadu -------------------------------------------------------------


async def test_payload_spoza_kontraktu_konczy_sie_422(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Nie przyjmujemy dowolnego JSON-a — kontrakt `v:1` jest wiążący."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    warianty = [
        {"v": 2, "meals": []},
        {"v": 1, "meals": [{"name": "Obiad", "items": [{"servings": "1"}]}]},
        {"v": 1, "meals": [], "cokolwiek": True},
        {"v": 1, "meals": [{"name": "", "items": []}]},
    ]
    for payload in warianty:
        response = await db_client.post(
            f"{TEMPLATES}/days",
            json={"name": "Zły payload", "payload": payload},
            headers=headers,
        )
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "validation_error"


async def test_szablon_wymaga_payloadu_albo_daty_zrodlowej(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Podanie obu albo żadnego to 422 — serwis nie zgaduje intencji."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    brak = await db_client.post(f"{TEMPLATES}/days", json={"name": "Nic"}, headers=headers)
    assert brak.status_code == 422

    oba = await db_client.post(
        f"{TEMPLATES}/days",
        json={"name": "Oba", "payload": day_payload(), "from_date": MONDAY},
        headers=headers,
    )
    assert oba.status_code == 422


async def test_pelny_obieg_szablonu_dnia(db_session: AsyncSession, db_client: AsyncClient) -> None:
    """POST → GET → instantiate: payload wraca stringami dziesiętnymi (ADR-008)."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Danie")
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        f"{TEMPLATES}/days",
        json={
            "name": "Szablon dnia",
            "payload": day_payload(
                meals=[
                    template_meal(
                        name="Obiad",
                        kcal_target="600",
                        items=[template_recipe_item(recipe.id, servings="2.5")],
                    )
                ]
            ),
        },
        headers=headers,
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert created.json()["summary"] == "1 posiłek, 1 pozycja"

    fetched = await db_client.get(f"{TEMPLATES}/days/{template_id}")
    item = fetched.json()["payload"]["meals"][0]["items"][0]
    assert item["servings"] == "2.5"
    assert fetched.json()["payload"]["meals"][0]["kcal_target"] == "600"

    instantiated = await db_client.post(
        f"{TEMPLATES}/days/{template_id}/instantiate",
        json={"dates": [MONDAY, TUESDAY]},
        headers=headers,
    )
    assert instantiated.status_code == 200
    body = instantiated.json()
    assert body["total"] == 2
    assert [day["day"] for day in body["items"]] == [MONDAY, TUESDAY]
    assert body["items"][0]["meals"][0]["items"][0]["servings"] == "2.50"


async def test_lista_szablonow_nie_zwraca_payloadow(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Lista jest listą — payload jedzie tylko przy odczycie pojedynczego szablonu."""
    user = await create_user(db_session)
    await create_day_template(db_session, owner=user, name="A")
    await login(db_client, user.email)

    response = await db_client.get(f"{TEMPLATES}/days")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert "payload" not in response.json()["items"][0]


# --- szablon tygodnia ---------------------------------------------------------------


async def test_instancjacja_tygodnia_od_nie_poniedzialku_daje_422(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    user = await create_user(db_session)
    template = await create_week_template(db_session, owner=user)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{TEMPLATES}/weeks/{template.id}/instantiate",
        json={"week_start": TUESDAY},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert "poniedziałek" in response.json()["error"]["message"]


async def test_cudzy_szablon_tygodnia_daje_404_takze_przy_instancjacji(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Anty-IDOR na akcji, nie tylko na odczycie."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    template = await create_week_template(db_session, owner=owner)

    await login(db_client, stranger.email)
    response = await db_client.post(
        f"{TEMPLATES}/weeks/{template.id}/instantiate",
        json={"week_start": MONDAY},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404


# --- cykle --------------------------------------------------------------------------


async def test_pelny_obieg_cyklu(db_session: AsyncSession, db_client: AsyncClient) -> None:
    """POST cyklu → apply na zakres; odpowiedź niesie nazwy szablonów dla UI."""
    user = await create_user(db_session)
    template = await create_week_template(
        db_session,
        owner=user,
        name="Tydzień A",
        payload={
            "v": 1,
            "days": [{"offset": 0, "day": day_payload(meals=[template_meal(name="Obiad")])}],
        },
    )
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        CYCLES,
        json={"name": "Cykl A", "template_ids": [template.id], "start_date": MONDAY},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["template_names"] == ["Tydzień A"]
    cycle_id = created.json()["id"]

    applied = await db_client.post(
        f"{CYCLES}/{cycle_id}/apply",
        json={"date_from": MONDAY, "date_to": "2026-08-23"},
        headers=headers,
    )
    assert applied.status_code == 200
    assert [day["day"] for day in applied.json()["items"]] == [MONDAY]


async def test_apply_cyklu_od_nie_poniedzialku_daje_422(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    user = await create_user(db_session)
    template = await create_week_template(db_session, owner=user)
    cycle = await create_week_cycle(db_session, owner=user, template_ids=[template.id])
    await login(db_client, user.email)

    response = await db_client.post(
        f"{CYCLES}/{cycle.id}/apply",
        json={"date_from": TUESDAY, "date_to": "2026-08-25"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_cykl_bez_szablonow_jest_odrzucany(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Cykl bez rotacji nie ma sensu — walidacja schematu, nie 500 przy apply."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        CYCLES, json={"name": "Pusty", "template_ids": []}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 422


async def test_usuniecie_szablonu_uzytego_w_cyklu_daje_409_z_used_in(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Kontrakt 409: `details.used_in` z nazwą cyklu (ADR-012, 06_UIUX §3.3)."""
    user = await create_user(db_session)
    template = await create_week_template(db_session, owner=user, name="Tydzień A")
    cycle = await create_week_cycle(
        db_session, owner=user, name="Cykl A", template_ids=[template.id]
    )
    await login(db_client, user.email)

    response = await db_client.delete(
        f"{TEMPLATES}/weeks/{template.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "conflict"
    assert body["details"]["used_in"] == [{"type": "week_cycle", "id": cycle.id, "name": "Cykl A"}]


async def test_obcy_cykl_daje_404(db_session: AsyncSession, db_client: AsyncClient) -> None:
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    template = await create_week_template(db_session, owner=owner)
    cycle = await create_week_cycle(db_session, owner=owner, template_ids=[template.id])

    await login(db_client, stranger.email)
    headers = csrf_headers(db_client)

    apply_response = await db_client.post(
        f"{CYCLES}/{cycle.id}/apply",
        json={"date_from": MONDAY, "date_to": "2026-08-23"},
        headers=headers,
    )
    assert apply_response.status_code == 404

    delete_response = await db_client.delete(f"{CYCLES}/{cycle.id}", headers=headers)
    assert delete_response.status_code == 404


# --- powielenie bloku przez /plan/copy ---------------------------------------------


async def test_copy_block_wymaga_pelnego_zestawu_pol(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """`what="block"` bez `repeat_each` to 422, nie domyślne 1."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{API}/plan/copy",
        json={
            "what": "block",
            "source_from": MONDAY,
            "source_days": 3,
            "target_start": "2026-09-07",
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_copy_block_odrzuca_zbyt_duzy_wynik(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Sufit dni docelowych obowiązuje też blok (30 x 7 to nie plan, to import)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{API}/plan/copy",
        json={
            "what": "block",
            "source_from": MONDAY,
            "source_days": 30,
            "repeat_each": 7,
            "target_start": "2026-09-07",
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_copy_block_kopiuje_dni_parami(
    db_session: AsyncSession, db_client: AsyncClient
) -> None:
    """Preset 2+2+2 przez HTTP: 3 dni źródłowe ⇒ 6 dni docelowych."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)

    for offset, name in enumerate(("Poniedziałek", "Wtorek", "Środa")):
        day = f"2026-08-{17 + offset}"
        created = await db_client.post(
            f"{API}/plan/days/{day}/meals", json={"name": name}, headers=headers
        )
        assert created.status_code == 201

    response = await db_client.post(
        f"{API}/plan/copy",
        json={
            "what": "block",
            "source_from": MONDAY,
            "source_days": 3,
            "repeat_each": 2,
            "target_start": "2026-09-07",
        },
        headers=headers,
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [day["day"] for day in items] == [f"2026-09-{7 + offset:02d}" for offset in range(6)]
    assert [day["meals"][0]["name"] for day in items] == [
        "Poniedziałek",
        "Poniedziałek",
        "Wtorek",
        "Wtorek",
        "Środa",
        "Środa",
    ]
