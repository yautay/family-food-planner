"""Kontrakt HTTP przepisów `global` (BATCH_21, D32): macierz ról, kopiowanie, archiwizacja.

Przepis `global` widzi KAŻDY zalogowany, a zarządza nim wyłącznie ADMIN. Odmowa to
**403** (przepis jest widoczny), nie 404 — cudzy PRYWATNY przepis zostaje 404
(ADR-006 bez zmian). Rolę sprawdza się jawnie, nie przez `owner_user_id`:
zdegradowany były admin jest nadal właścicielem wiersza i nie może go ruszać.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.scope import RecipeScope, Scope
from app.modules.accounts.models import UserRole
from app.modules.audit.models import AuditEntry
from app.modules.catalog.units import AmountUnit
from app.modules.recipes.models import Recipe
from tests.factories import (
    create_admin,
    create_category,
    create_household,
    create_ingredient,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_rating,
    create_recipe,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

RECIPES = f"{API}/recipes"
GLOBAL_PAYLOAD: dict[str, Any] = {"name": "Barszcz ukraiński", "scope": "global"}
DAY = date(2030, 5, 6)


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (400, 300), (30, 140, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _world(
    session: AsyncSession,
) -> dict[str, Any]:
    """Admin w swojej rodzinie, USER z INNEJ rodziny i przepis `global` admina."""
    admin_home = await create_household(session, name="Rodzina admina")
    other_home = await create_household(session, name="Obca rodzina")
    admin = await create_admin(session, email="admin@example.com")
    admin.household_id = admin_home.id
    await session.commit()
    user = await create_user(session, email="obcy@example.com", household=other_home)
    shared = await create_recipe(
        session, owner=admin, name="Wspólny żurek", scope=RecipeScope.GLOBAL, base_servings=2
    )
    return {
        "admin": admin,
        "user": user,
        "recipe": shared,
        "admin_home": admin_home,
        "other_home": other_home,
    }


# --- odczyt -------------------------------------------------------------------------


async def test_anonim_nie_czyta_przepisu_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)

    assert (await db_client.get(f"{RECIPES}/{world['recipe'].id}")).status_code == 401
    assert (await db_client.get(RECIPES)).status_code == 401


async def test_user_innej_rodziny_widzi_global_na_liscie_w_szukajce_i_w_szczegole(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2: lista, `?q=`, filtr `?scope=global` i szczegół — bez bycia właścicielem."""
    world = await _world(db_session)
    await login(db_client, world["user"].email)

    listing = await db_client.get(RECIPES)
    assert [item["name"] for item in listing.json()["items"]] == ["Wspólny żurek"]
    assert listing.json()["items"][0]["scope"] == "global"

    search = await db_client.get(RECIPES, params={"q": "żurek"})
    assert search.json()["total"] == 1
    only_global = await db_client.get(RECIPES, params={"scope": "global"})
    assert only_global.json()["total"] == 1
    only_private = await db_client.get(RECIPES, params={"scope": "private"})
    assert only_private.json()["total"] == 0

    detail = await db_client.get(f"{RECIPES}/{world['recipe'].id}")
    assert detail.status_code == 200
    assert detail.json()["scope"] == "global"


async def test_cudzy_prywatny_przepis_nadal_404_obok_globalnego(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zakres `global` nie rozluźnia ADR-006: cudzy PRYWATNY przepis to 404, nie 403."""
    world = await _world(db_session)
    secret = await create_recipe(
        db_session, owner=world["admin"], name="Prywatne admina", scope=Scope.PRIVATE
    )
    await login(db_client, world["user"].email)

    assert (await db_client.get(f"{RECIPES}/{secret.id}")).status_code == 404
    listing = await db_client.get(RECIPES)
    assert [item["name"] for item in listing.json()["items"]] == ["Wspólny żurek"]


# --- zapis: USER dostaje 403 ----------------------------------------------------------


async def test_user_nie_tworzy_przepisu_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    await login(db_client, world["user"].email)

    response = await db_client.post(RECIPES, json=GLOBAL_PAYLOAD, headers=csrf_headers(db_client))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert (await db_client.get(RECIPES, params={"q": "Barszcz ukraiński"})).json()["total"] == 0


async def test_user_nie_edytuje_tresci_zdjecia_zakresu_ani_nie_usuwa_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Edycja, zmiana zakresu, zdjęcie (POST/DELETE) i usunięcie: 403, przepis bez zmian."""
    world = await _world(db_session)
    recipe = world["recipe"]
    await login(db_client, world["user"].email)
    headers = csrf_headers(db_client)

    edit = await db_client.put(
        f"{RECIPES}/{recipe.id}", json={"name": "Podmieniony", "scope": "global"}, headers=headers
    )
    demote = await db_client.put(
        f"{RECIPES}/{recipe.id}",
        json={"name": "Wspólny żurek", "scope": "household"},
        headers=headers,
    )
    photo = await db_client.post(
        f"{RECIPES}/{recipe.id}/photo",
        files={"file": ("a.png", _png(), "image/png")},
        headers=headers,
    )
    photo_delete = await db_client.delete(f"{RECIPES}/{recipe.id}/photo", headers=headers)
    remove = await db_client.delete(f"{RECIPES}/{recipe.id}", headers=headers)
    archive = await db_client.post(f"{RECIPES}/{recipe.id}/archive", headers=headers)
    unarchive = await db_client.delete(f"{RECIPES}/{recipe.id}/archive", headers=headers)

    assert [
        r.status_code for r in (edit, demote, photo, photo_delete, remove, archive, unarchive)
    ] == [403] * 7
    await db_session.refresh(recipe)
    assert recipe.name == "Wspólny żurek"
    assert recipe.scope == RecipeScope.GLOBAL
    assert recipe.is_archived is False


async def test_user_nie_awansuje_wlasnego_przepisu_do_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Właściciel zwykłego przepisu NIE może go uczynić globalnym (luka z przeglądu wpływu)."""
    world = await _world(db_session)
    mine = await create_recipe(
        db_session, owner=world["user"], name="Moja zupa", scope=Scope.HOUSEHOLD
    )
    await login(db_client, world["user"].email)

    response = await db_client.put(
        f"{RECIPES}/{mine.id}",
        json={"name": "Moja zupa", "scope": "global"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 403
    await db_session.refresh(mine)
    assert mine.scope == RecipeScope.HOUSEHOLD


async def test_zdegradowany_byly_admin_nie_rusza_przepisu_ktory_opublikowal(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rola, nie `owner_user_id`: były admin jest nadal właścicielem wiersza i dostaje 403."""
    world = await _world(db_session)
    former_admin = world["admin"]
    former_admin.role = UserRole.USER
    await db_session.commit()
    recipe = world["recipe"]
    assert recipe.owner_user_id == former_admin.id
    await login(db_client, former_admin.email)
    headers = csrf_headers(db_client)

    edit = await db_client.put(
        f"{RECIPES}/{recipe.id}", json={"name": "X", "scope": "global"}, headers=headers
    )
    scope = await db_client.put(
        f"{RECIPES}/{recipe.id}", json={"name": "X", "scope": "private"}, headers=headers
    )
    remove = await db_client.delete(f"{RECIPES}/{recipe.id}", headers=headers)
    photo = await db_client.post(
        f"{RECIPES}/{recipe.id}/photo",
        files={"file": ("a.png", _png(), "image/png")},
        headers=headers,
    )
    create = await db_client.post(RECIPES, json=GLOBAL_PAYLOAD, headers=headers)

    assert [r.status_code for r in (edit, scope, remove, photo, create)] == [403] * 5


# --- zapis: ADMIN ---------------------------------------------------------------------


async def test_admin_tworzy_edytuje_fotografuje_archiwizuje_i_usuwa_global(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pełny cykl ADMIN-a; przepis globalny nie niesie rodziny (CHECK z `0018`)."""
    world = await _world(db_session)
    await login(db_client, world["admin"].email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        RECIPES, json={**GLOBAL_PAYLOAD, "base_servings": 4}, headers=headers
    )
    assert created.status_code == 201
    recipe_id = created.json()["id"]
    assert created.json()["scope"] == "global"
    row = await db_session.get(Recipe, recipe_id)
    assert row is not None and row.household_id is None

    edited = await db_client.put(
        f"{RECIPES}/{recipe_id}",
        json={**GLOBAL_PAYLOAD, "name": "Barszcz ukraiński 2"},
        headers=headers,
    )
    assert edited.status_code == 200 and edited.json()["name"] == "Barszcz ukraiński 2"

    photo = await db_client.post(
        f"{RECIPES}/{recipe_id}/photo",
        files={"file": ("a.png", _png(), "image/png")},
        headers=headers,
    )
    assert photo.status_code == 200 and photo.json()["photo_url"]
    assert (
        await db_client.delete(f"{RECIPES}/{recipe_id}/photo", headers=headers)
    ).status_code == 200

    archived = await db_client.post(f"{RECIPES}/{recipe_id}/archive", headers=headers)
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    assert (await db_client.get(RECIPES, params={"q": "Barszcz ukraiński 2"})).json()["total"] == 0
    restored = await db_client.delete(f"{RECIPES}/{recipe_id}/archive", headers=headers)
    assert restored.json()["is_archived"] is False

    assert (await db_client.delete(f"{RECIPES}/{recipe_id}", headers=headers)).status_code == 204
    assert (await db_client.get(f"{RECIPES}/{recipe_id}")).status_code == 404


async def test_admin_przenosi_przepis_do_global_i_z_powrotem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Awans zeruje rodzinę; obniżenie przekazuje przepis ADMIN-owi i jego rodzinie."""
    world = await _world(db_session)
    mine = await create_recipe(
        db_session, owner=world["admin"], name="Do publikacji", scope=Scope.HOUSEHOLD
    )
    await login(db_client, world["admin"].email)
    headers = csrf_headers(db_client)

    up = await db_client.put(
        f"{RECIPES}/{mine.id}", json={"name": "Do publikacji", "scope": "global"}, headers=headers
    )
    assert up.status_code == 200 and up.json()["scope"] == "global"
    await db_session.refresh(mine)
    assert mine.household_id is None

    down = await db_client.put(
        f"{RECIPES}/{mine.id}",
        json={"name": "Do publikacji", "scope": "household"},
        headers=headers,
    )
    assert down.status_code == 200 and down.json()["scope"] == "household"
    await db_session.refresh(mine)
    assert mine.household_id == world["admin_home"].id
    assert mine.owner_user_id == world["admin"].id


async def test_admin_bez_rodziny_nie_obniza_global_do_household(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session, email="solo@example.com")
    shared = await create_recipe(db_session, owner=admin, name="Wspólne", scope=RecipeScope.GLOBAL)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{RECIPES}/{shared.id}",
        json={"name": "Wspólne", "scope": "household"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409
    await db_session.refresh(shared)
    assert shared.scope == RecipeScope.GLOBAL


async def test_user_bez_rodziny_dostaje_409_nie_500_przy_household(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pułapka `is`: `RecipeScope.HOUSEHOLD` to inny obiekt niż `Scope.HOUSEHOLD`."""
    loner = await create_user(db_session, email="solo-user@example.com")
    await login(db_client, loner.email)

    response = await db_client.post(
        RECIPES,
        json={"name": "Rodzinny bez rodziny", "scope": "household"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409


# --- zakres global odrzucony dla innych encji -------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", f"{API}/plan/days/{DAY.isoformat()}", {"scope": "global"}),
        (
            "POST",
            f"{API}/templates/days",
            {"name": "Szablon", "scope": "global", "payload": {"v": 1, "meals": []}},
        ),
        (
            "POST",
            f"{API}/templates/weeks",
            {"name": "Tydzień", "scope": "global", "payload": {"v": 1, "days": []}},
        ),
        ("POST", f"{API}/cycles", {"name": "Cykl", "scope": "global", "template_ids": [1]}),
    ],
)
async def test_scope_global_jest_odrzucony_dla_plan_szablonow_i_cykli(
    db_client: AsyncClient, db_session: AsyncSession, method: str, path: str, body: dict[str, Any]
) -> None:
    """`Scope` zostaje dwuwartościowy: 422 z wskazaniem pola `scope`, nie zapis."""
    admin = await create_admin(db_session, email="a2@example.com")
    await login(db_client, admin.email)

    response = await db_client.request(method, path, json=body, headers=csrf_headers(db_client))

    assert response.status_code == 422
    assert "scope" in response.text


# --- kopiowanie -------------------------------------------------------------------------


async def test_kopia_przepisu_global_jest_niezalezna_od_oryginalu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 5: własne składniki, tagi i plik zdjęcia; edycja kopii nie rusza oryginału."""
    world = await _world(db_session)
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(db_session, category=category, name="Pietruszka")
    original = world["recipe"]
    await create_ingredient(db_session, recipe=original, product=product, amount=Decimal("250"))
    await create_rating(db_session, recipe=original, user=world["admin"], rating=5)

    await login(db_client, world["admin"].email)
    headers = csrf_headers(db_client)
    with_photo = await db_client.post(
        f"{RECIPES}/{original.id}/photo",
        files={"file": ("a.png", _png(), "image/png")},
        headers=headers,
    )
    original_photo = with_photo.json()["photo_url"]

    db_client.cookies.clear()
    await login(db_client, world["user"].email)
    headers = csrf_headers(db_client)
    copied = await db_client.post(f"{RECIPES}/{original.id}/copy", json={}, headers=headers)

    assert copied.status_code == 201
    body = copied.json()
    assert body["id"] != original.id
    assert body["scope"] == "household"  # członek rodziny: domyślnie rodzinny
    assert body["name"] == "Wspólny żurek"  # wywołujący nie ma jeszcze takiego przepisu
    assert body["avg_rating"] is None and body["ratings_count"] == 0  # oceny nie wędrują
    assert [i["product_name"] for i in body["ingredients"]] == ["Pietruszka"]
    assert Decimal(body["ingredients"][0]["amount"]) == Decimal("250")
    assert body["photo_url"] and body["photo_url"] != original_photo
    row = await db_session.get(Recipe, body["id"])
    assert row is not None
    assert row.owner_user_id == world["user"].id
    assert row.household_id == world["other_home"].id

    # Edycja kopii: oryginał bez zmian.
    edited = await db_client.put(
        f"{RECIPES}/{body['id']}",
        json={"name": "Mój żurek", "scope": "household", "ingredients": []},
        headers=headers,
    )
    assert edited.status_code == 200
    await db_session.refresh(original)
    assert original.name == "Wspólny żurek"
    original_detail = await db_client.get(f"{RECIPES}/{original.id}")
    assert len(original_detail.json()["ingredients"]) == 1

    # Usunięcie zdjęcia kopii nie kasuje pliku oryginału.
    uploads_root = Path(get_settings().uploads_dir)
    original_file = uploads_root / original_photo.removeprefix("/uploads/")
    copy_file = uploads_root / body["photo_url"].removeprefix("/uploads/")
    assert original_file.is_file() and copy_file.is_file()
    assert (
        await db_client.delete(f"{RECIPES}/{body['id']}/photo", headers=headers)
    ).status_code == 200
    assert original_file.is_file()
    assert not copy_file.exists()


async def test_kopia_dostaje_sufiks_gdy_wywolujacy_ma_juz_taka_nazwe(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    await create_recipe(db_session, owner=world["user"], name="Wspólny żurek", scope=Scope.PRIVATE)
    await login(db_client, world["user"].email)
    headers = csrf_headers(db_client)

    first = await db_client.post(
        f"{RECIPES}/{world['recipe'].id}/copy", json={"scope": "private"}, headers=headers
    )
    second = await db_client.post(f"{RECIPES}/{world['recipe'].id}/copy", json={}, headers=headers)

    assert first.json()["name"] == "Wspólny żurek (kopia)"
    assert first.json()["scope"] == "private"
    assert second.json()["name"] == "Wspólny żurek (kopia 2)"


async def test_kopia_nie_przyjmuje_global_i_wymaga_rodziny_dla_household(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    loner = await create_user(db_session, email="solo2@example.com")
    await login(db_client, loner.email)
    headers = csrf_headers(db_client)
    url = f"{RECIPES}/{world['recipe'].id}/copy"

    assert (await db_client.post(url, json={"scope": "global"}, headers=headers)).status_code == 422
    assert (
        await db_client.post(url, json={"scope": "household"}, headers=headers)
    ).status_code == 409
    default = await db_client.post(url, headers=headers)  # bez body: prywatna (brak rodziny)
    assert default.status_code == 201 and default.json()["scope"] == "private"


async def test_kopia_cudzego_prywatnego_przepisu_to_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    secret = await create_recipe(db_session, owner=world["admin"], scope=Scope.PRIVATE)
    await login(db_client, world["user"].email)

    response = await db_client.post(
        f"{RECIPES}/{secret.id}/copy", json={}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 404


async def test_kopiowanie_wymaga_sesji_i_csrf(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    url = f"{RECIPES}/{world['recipe'].id}/copy"
    assert (await db_client.post(url, json={})).status_code in (401, 403)
    await login(db_client, world["user"].email)
    assert (await db_client.post(url, json={})).status_code == 403  # brak X-CSRF-Token


# --- użycie w cudzych planach: usuwanie, obniżanie, archiwizacja --------------------------


async def _plan_of_other_family(world: dict[str, Any], session: AsyncSession) -> None:
    """Dzień planu OBCEJ rodziny z przepisem globalnym."""
    day = await create_plan_day(session, owner=world["user"], day=DAY)
    meal = await create_plan_meal(session, plan_day=day, name="Obiad")
    await create_plan_item(session, meal=meal, recipe=world["recipe"])


async def test_usuniecie_uzywanego_global_to_409_z_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    await _plan_of_other_family(world, db_session)
    await login(db_client, world["admin"].email)

    response = await db_client.delete(
        f"{RECIPES}/{world['recipe'].id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    used_in = response.json()["error"]["details"]["used_in"]
    assert used_in and used_in[0]["type"] == "plan_day"


async def test_obnizenie_global_blokowane_gdy_uzywa_go_inna_rodzina(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """409 z `used_in`: po zawężeniu przepis zniknąłby obcej rodzinie z widoku."""
    world = await _world(db_session)
    await _plan_of_other_family(world, db_session)
    await login(db_client, world["admin"].email)
    headers = csrf_headers(db_client)

    for target in ("household", "private"):
        response = await db_client.put(
            f"{RECIPES}/{world['recipe'].id}",
            json={"name": "Wspólny żurek", "scope": target},
            headers=headers,
        )
        assert response.status_code == 409, target
        assert response.json()["error"]["details"]["used_in"], target
    await db_session.refresh(world["recipe"])
    assert world["recipe"].scope == RecipeScope.GLOBAL


async def test_obnizenie_global_przechodzi_gdy_uzywa_go_tylko_rodzina_admina(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    other = await create_user(
        db_session, email="domownik@example.com", household=world["admin_home"]
    )
    day = await create_plan_day(db_session, owner=other, day=DAY)
    meal = await create_plan_meal(db_session, plan_day=day, name="Obiad")
    await create_plan_item(db_session, meal=meal, recipe=world["recipe"])
    await login(db_client, world["admin"].email)

    response = await db_client.put(
        f"{RECIPES}/{world['recipe'].id}",
        json={"name": "Wspólny żurek", "scope": "household"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["scope"] == "household"


async def test_archiwizacja_uzywanego_global_przechodzi_a_plan_dalej_sie_liczy(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Jedyna droga wycofania zużytego przepisu; istniejące plany dalej go liczą."""
    world = await _world(db_session)
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(
        db_session, category=category, name="Marchew", kcal_100=Decimal("40.00")
    )
    await create_ingredient(
        db_session,
        recipe=world["recipe"],
        product=product,
        amount=Decimal("200"),
        amount_unit=AmountUnit.GRAM,
    )
    await _plan_of_other_family(world, db_session)

    await login(db_client, world["admin"].email)
    archived = await db_client.post(
        f"{RECIPES}/{world['recipe'].id}/archive", headers=csrf_headers(db_client)
    )
    assert archived.status_code == 200

    db_client.cookies.clear()
    await login(db_client, world["user"].email)
    assert (await db_client.get(RECIPES)).json()["total"] == 0  # znika z listy
    plan = await db_client.get(f"{API}/plan/days/{DAY.isoformat()}")
    item = plan.json()["meals"][0]["items"][0]
    assert item["recipe_name"] == "Wspólny żurek"
    # 200 g x 40 kcal/100 g, base_servings=2 → 40 kcal na porcję.
    assert Decimal(item["nutrition"]["kcal"]) == Decimal("40")


# --- audyt ----------------------------------------------------------------------------------


async def test_operacje_na_przepisie_global_trafiaja_do_dziennika_bez_tresci(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    await login(db_client, world["admin"].email)
    headers = csrf_headers(db_client)

    created = await db_client.post(
        RECIPES, json={**GLOBAL_PAYLOAD, "instructions": "TAJNA TREŚĆ"}, headers=headers
    )
    recipe_id = created.json()["id"]
    await db_client.put(
        f"{RECIPES}/{recipe_id}",
        json={**GLOBAL_PAYLOAD, "instructions": "TAJNA 2"},
        headers=headers,
    )
    await db_client.post(f"{RECIPES}/{recipe_id}/archive", headers=headers)
    await db_client.delete(f"{RECIPES}/{recipe_id}/archive", headers=headers)
    await db_client.delete(f"{RECIPES}/{recipe_id}", headers=headers)

    entries = (await db_session.execute(select(AuditEntry).order_by(AuditEntry.id))).scalars().all()
    assert [entry.action for entry in entries] == [
        "recipe.global_create",
        "recipe.global_update",
        "recipe.archive",
        "recipe.unarchive",
        "recipe.global_delete",
    ]
    assert all(entry.entity_type == "recipe" for entry in entries)
    assert "TAJNA" not in str([entry.payload for entry in entries])


async def test_zwykle_przepisy_nie_zasmiecaja_dziennika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    world = await _world(db_session)
    await login(db_client, world["user"].email)
    await db_client.post(
        RECIPES, json={"name": "Zwykły", "scope": "private"}, headers=csrf_headers(db_client)
    )

    assert (await db_session.execute(select(AuditEntry))).scalars().all() == []


async def test_kopia_przepisu_z_uszkodzonym_plikiem_zdjecia_przechodzi_bez_zdjecia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Uszkodzony plik oryginału nie karze kopiującego 422 — kopia powstaje bez zdjęcia."""
    world = await _world(db_session)
    uploads_root = Path(get_settings().uploads_dir)
    broken = uploads_root / "recipes" / "uszkodzony-b21.jpg"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"to nie jest obraz")
    world["recipe"].photo_path = "recipes/uszkodzony-b21.jpg"
    await db_session.commit()
    await login(db_client, world["user"].email)

    try:
        response = await db_client.post(
            f"{RECIPES}/{world['recipe'].id}/copy", json={}, headers=csrf_headers(db_client)
        )
    finally:
        broken.unlink(missing_ok=True)

    assert response.status_code == 201
    assert response.json()["photo_url"] is None


async def test_audyt_obnizenia_global_niesie_poprzedniego_wlasciciela(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Obniżenie przekazuje przepis wykonującemu ADMIN-owi — dziennik zachowuje, czyj był."""
    world = await _world(db_session)
    second = await create_admin(db_session, email="admin2@example.com")
    second.household_id = world["admin_home"].id
    await db_session.commit()
    await login(db_client, second.email)

    response = await db_client.put(
        f"{RECIPES}/{world['recipe'].id}",
        json={"name": "Wspólny żurek", "scope": "household"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    entry = (await db_session.execute(select(AuditEntry))).scalars().one()
    assert entry.action == "recipe.global_update"
    assert entry.payload["owner_before"] == world["admin"].id
    assert entry.payload["owner_after"] == second.id
