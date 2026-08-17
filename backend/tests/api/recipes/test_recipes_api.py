"""Kontrakt HTTP `/recipes`: macierz uprawnień 08_TESTING §4, filtry, servings, oceny.

`recipes` to pierwsza produkcyjna encja ze scope — macierz jest tu dowodzona
kodami HTTP (anonim 401 / obcy 404 / członek 200 / delete członka 403).
Wiersz ADMIN-a asertuje wprost decyzję D16 (stan faktyczny `ScopedQuery`:
ADMIN widzi wszystko także na ścieżkach użytkownika).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.modules.catalog.models import VerificationStatus
from tests.factories import (
    attach_tag,
    create_admin,
    create_category,
    create_household,
    create_ingredient,
    create_product,
    create_rating,
    create_recipe,
    create_tag,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

RECIPES = f"{API}/recipes"
TAGS = f"{API}/tags"

MINIMAL_PAYLOAD: dict[str, Any] = {"name": "Gołąbki"}


# --- macierz uprawnień (08_TESTING §4) --------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Wszystko poza /health, /auth/login i /public/* wymaga sesji (04_API §3)."""
    assert (await db_client.get(RECIPES)).status_code == 401
    assert (await db_client.get(f"{RECIPES}/1")).status_code == 401


async def test_cudzy_private_to_404(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Obcy USER i członek rodziny właściciela: PRIVATE nie istnieje (anty-IDOR)."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    outsider = await create_user(db_session, email="obcy@example.com")
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.PRIVATE)

    await login(db_client, member.email)
    assert (await db_client.get(f"{RECIPES}/{recipe.id}")).status_code == 404

    await login(db_client, outsider.email)
    assert (await db_client.get(f"{RECIPES}/{recipe.id}")).status_code == 404


async def test_household_widzi_i_edytuje_kazdy_czlonek(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odczyt i edycja treści HOUSEHOLD: każdy członek (rodzina sobie ufa)."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.HOUSEHOLD)

    await login(db_client, member.email)
    assert (await db_client.get(f"{RECIPES}/{recipe.id}")).status_code == 200

    response = await db_client.put(
        f"{RECIPES}/{recipe.id}",
        json={"name": "Gołąbki babci", "scope": "household"},
        headers=csrf_headers(db_client),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Gołąbki babci"


async def test_household_niewidoczne_spoza_rodziny(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    household = await create_household(db_session)
    other_household = await create_household(db_session, name="Nowakowie")
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    outsider = await create_user(db_session, email="obcy@example.com", household=other_household)
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.HOUSEHOLD)

    await login(db_client, outsider.email)
    assert (await db_client.get(f"{RECIPES}/{recipe.id}")).status_code == 404
    listed = (await db_client.get(RECIPES)).json()
    assert listed["total"] == 0


async def test_czlonek_nie_zmieni_scope_ani_nie_usunie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zmiana scope i usunięcie: wyłącznie właściciel/ADMIN — członek dostaje 403."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.HOUSEHOLD)

    await login(db_client, member.email)
    scope_change = await db_client.put(
        f"{RECIPES}/{recipe.id}",
        json={"name": recipe.name, "scope": "private"},
        headers=csrf_headers(db_client),
    )
    assert scope_change.status_code == 403

    delete = await db_client.delete(f"{RECIPES}/{recipe.id}", headers=csrf_headers(db_client))
    assert delete.status_code == 403


async def test_wlasciciel_zarzadza_pelnym_cyklem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """create → read → PUT (zmiana scope) → delete, wszystko 2xx dla właściciela."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    await login(db_client, owner.email)

    created = await db_client.post(RECIPES, json=MINIMAL_PAYLOAD, headers=csrf_headers(db_client))
    assert created.status_code == 201
    recipe_id = created.json()["id"]
    assert created.json()["scope"] == "private"

    updated = await db_client.put(
        f"{RECIPES}/{recipe_id}",
        json={"name": "Gołąbki", "scope": "household"},
        headers=csrf_headers(db_client),
    )
    assert updated.status_code == 200
    assert updated.json()["scope"] == "household"

    deleted = await db_client.delete(f"{RECIPES}/{recipe_id}", headers=csrf_headers(db_client))
    assert deleted.status_code == 204
    assert (await db_client.get(f"{RECIPES}/{recipe_id}")).status_code == 404


async def test_d16_admin_widzi_cudze_przepisy_na_sciezkach_uzytkownika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D16 (02_DECISIONS, stan faktyczny `ScopedQuery`): ADMIN ma 200 w każdym wierszu
    macierzy 08_TESTING §4 — widzi cudzy PRIVATE w szczegółach ORAZ na liście.

    Ta asercja istnieje po to, żeby decyzja była WIDOCZNA w kodzie: gdy
    właściciel rozstrzygnie D16 odwrotnie, ten test ma się wywrócić.
    """
    admin = await create_admin(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com")
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.PRIVATE)

    await login(db_client, admin.email)
    assert (await db_client.get(f"{RECIPES}/{recipe.id}")).status_code == 200
    listed = (await db_client.get(RECIPES)).json()
    assert [item["id"] for item in listed["items"]] == [recipe.id]

    deleted = await db_client.delete(f"{RECIPES}/{recipe.id}", headers=csrf_headers(db_client))
    assert deleted.status_code == 204


async def test_mutacja_bez_csrf_to_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.post(RECIPES, json=MINIMAL_PAYLOAD)).status_code == 403


# --- zapis i walidacje ----------------------------------------------------------------


async def test_zapis_z_nieprzeliczalna_jednostka_to_422_z_produktem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance 3: 422 wskazuje produkt i jednostkę; w DB nie ma składnika bez amount."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka pszenna")
    await login(db_client, user.email)

    response = await db_client.post(
        RECIPES,
        json={
            "name": "Ciasto",
            "ingredients": [{"product_id": flour.id, "quantity": "1", "unit": "szklanka"}],
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "Mąka pszenna" in error["message"]
    assert "szklanka" in error["message"]
    assert (await db_client.get(RECIPES)).json()["total"] == 0


async def test_ilosci_w_json_sa_stringami_dziesietnymi(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ADR-008/04_API §1: NUMERIC w odpowiedzi to string, nie float."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka pszenna")
    await login(db_client, user.email)

    created = await db_client.post(
        RECIPES,
        json={
            "name": "Ciasto",
            "ingredients": [{"product_id": flour.id, "quantity": "0.5", "unit": "kg"}],
        },
        headers=csrf_headers(db_client),
    )

    ingredient = created.json()["ingredients"][0]
    assert ingredient["amount"] == "500.000"
    assert ingredient["display_qty"] == "0.500"
    assert isinstance(created.json()["nutrition"]["kcal"], str)


# --- servings i nutrition ---------------------------------------------------------------


async def _create_full_recipe(db_client: AsyncClient, db_session: AsyncSession) -> int:
    """Przepis 250 g pełnowartościowego produktu, base_servings=2 (wyniki policzone ręcznie)."""
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Produkt pełny",
        kcal_100=Decimal("50.00"),
        protein_100=Decimal("1.50"),
        fat_100=Decimal("0.20"),
        carbs_100=Decimal("10.00"),
        fiber_100=Decimal("2.00"),
        sugars_100=Decimal("6.00"),
        glycemic_index=Decimal("40.0"),
        nutrition_source="usda:test",
        verification_status=VerificationStatus.VERIFIED,
    )
    response = await db_client.post(
        RECIPES,
        json={
            "name": "Danie testowe",
            "base_servings": 2,
            "ingredients": [{"product_id": product.id, "quantity": "250", "unit": "g"}],
        },
        headers=csrf_headers(db_client),
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def test_nutrition_na_porcje_i_mnoznik_servings(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance 4: `?servings=2.5` zwraca porcję x 2,5; zaokrąglenia z 02_DOMAIN §6.

    Całość: 125 kcal, B 3,75, T 0,5, W 25, błonnik 5, cukry 15, ŁG 8.
    Porcja (base 2): 62,5 / 1,875 / 0,25 / 12,5 / 2,5 / 7,5 / 4.
    x 2,5: 156,25→156 kcal; 4,6875→4,7; 0,625→0,6; 31,25→31,3; 6,25→6,3;
    18,75→18,8; 10→10,0.
    """
    user = await create_user(db_session)
    await login(db_client, user.email)
    recipe_id = await _create_full_recipe(db_client, db_session)

    portion = (await db_client.get(f"{RECIPES}/{recipe_id}")).json()
    assert portion["servings"] == "1"
    assert portion["nutrition"] == {
        "kcal": "63",
        "protein_g": "1.9",
        "fat_g": "0.3",
        "carbs_g": "12.5",
        "fiber_g": "2.5",
        "sugars_g": "7.5",
        "glycemic_load": "4.0",
        "complete": True,
        "missing": [],
    }

    scaled = (await db_client.get(f"{RECIPES}/{recipe_id}", params={"servings": "2.5"})).json()
    assert scaled["nutrition"] == {
        "kcal": "156",
        "protein_g": "4.7",
        "fat_g": "0.6",
        "carbs_g": "31.3",
        "fiber_g": "6.3",
        "sugars_g": "18.8",
        "glycemic_load": "10.0",
        "complete": True,
        "missing": [],
    }
    # Składniki przeliczone przez backend: 250 g x 2,5 / 2 = 312,5 g.
    assert scaled["ingredients"][0]["scaled_amount"] == "312.500"


async def test_braki_ig_i_weryfikacji_daja_complete_false(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance 4: braki wartości/IG i produkt UNVERIFIED ⇒ complete=false + missing."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Cebula")
    await login(db_client, user.email)

    created = await db_client.post(
        RECIPES,
        json={
            "name": "Surówka",
            "ingredients": [{"product_id": product.id, "quantity": "100", "unit": "g"}],
        },
        headers=csrf_headers(db_client),
    )

    nutrition = created.json()["nutrition"]
    assert nutrition["complete"] is False
    assert "Cebula: brak kalorii" in nutrition["missing"]
    assert "Cebula: produkt niezweryfikowany" in nutrition["missing"]


# --- filtry i paginacja -------------------------------------------------------------------


async def test_filtry_listy_przepisow(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Acceptance 5: tagi (AND), tekst, czas, trudność, ocena; paginacja {items,total}."""
    user = await create_user(db_session)
    quick = await create_tag(db_session, name="szybkie", is_system=True)
    dinner = await create_tag(db_session, name="obiad", is_system=True)

    fast_dinner = await create_recipe(
        db_session, owner=user, name="Omlet", prep_time_min=10, difficulty=2
    )
    await attach_tag(db_session, recipe=fast_dinner, tag=quick)
    await attach_tag(db_session, recipe=fast_dinner, tag=dinner)

    slow_dinner = await create_recipe(
        db_session, owner=user, name="Bigos", prep_time_min=180, difficulty=7
    )
    await attach_tag(db_session, recipe=slow_dinner, tag=dinner)

    rated = await create_recipe(db_session, owner=user, name="Gołąbki", prep_time_min=90)
    await create_rating(db_session, recipe=rated, user=user, rating=5)

    await login(db_client, user.email)

    async def names(**params: object) -> list[str]:
        response = await db_client.get(RECIPES, params=params)  # type: ignore[arg-type]
        assert response.status_code == 200
        return [item["name"] for item in response.json()["items"]]

    assert await names(q="omle") == ["Omlet"]
    assert await names(tag=[dinner.id]) == ["Bigos", "Omlet"]
    # Dwa tagi = koniunkcja: tylko przepis mający OBA.
    assert await names(tag=[dinner.id, quick.id]) == ["Omlet"]
    assert await names(prep_time_max=30) == ["Omlet"]
    assert await names(difficulty_max=5) == ["Omlet"]
    assert await names(rating_min=4) == ["Gołąbki"]

    page = (await db_client.get(RECIPES, params={"limit": 2, "offset": 0})).json()
    assert page["total"] == 3
    assert [item["name"] for item in page["items"]] == ["Bigos", "Gołąbki"]
    rest = (await db_client.get(RECIPES, params={"limit": 2, "offset": 2})).json()
    assert [item["name"] for item in rest["items"]] == ["Omlet"]


async def test_archiwalne_przepisy_sa_domyslnie_schowane(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await create_recipe(db_session, owner=user, name="Stary przepis", is_archived=True)
    await login(db_client, user.email)

    assert (await db_client.get(RECIPES)).json()["total"] == 0
    with_archived = await db_client.get(RECIPES, params={"include_archived": True})
    assert with_archived.json()["total"] == 1


# --- oceny -----------------------------------------------------------------------------


async def test_ocena_upsert_i_srednia_na_karcie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance 6: ocena per (przepis, user) z upsertem; średnia widoczna na liście."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.HOUSEHOLD)
    await create_rating(db_session, recipe=recipe, user=owner, rating=4)

    await login(db_client, member.email)
    first = await db_client.put(
        f"{RECIPES}/{recipe.id}/rating", json={"rating": 2}, headers=csrf_headers(db_client)
    )
    assert first.status_code == 200
    assert first.json() == {"my_rating": 2, "avg_rating": "3.0", "ratings_count": 2}

    second = await db_client.put(
        f"{RECIPES}/{recipe.id}/rating", json={"rating": 5}, headers=csrf_headers(db_client)
    )
    assert second.json() == {"my_rating": 5, "avg_rating": "4.5", "ratings_count": 2}

    listed = (await db_client.get(RECIPES)).json()["items"][0]
    assert listed["avg_rating"] == "4.5"
    assert listed["my_rating"] == 5

    out_of_range = await db_client.put(
        f"{RECIPES}/{recipe.id}/rating", json={"rating": 6}, headers=csrf_headers(db_client)
    )
    assert out_of_range.status_code == 422


# --- tagi -------------------------------------------------------------------------------


async def test_tagi_lista_i_inline_create(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """GET zwraca słownik (systemowe najpierw), POST tworzy tag użytkowy."""
    user = await create_user(db_session)
    await create_tag(db_session, name="obiad", is_system=True)
    await login(db_client, user.email)

    created = await db_client.post(
        TAGS, json={"name": "na imprezę"}, headers=csrf_headers(db_client)
    )
    assert created.status_code == 201
    assert created.json()["is_system"] is False

    listed = (await db_client.get(TAGS)).json()
    assert [item["name"] for item in listed["items"]] == ["obiad", "na imprezę"]

    duplicate = await db_client.post(
        TAGS, json={"name": "NA IMPREZĘ"}, headers=csrf_headers(db_client)
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["existing"]["name"] == "na imprezę"


async def test_przepis_z_tagami_i_nieistniejacy_tag(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    tag = await create_tag(db_session, name="obiad", is_system=True)
    await login(db_client, user.email)

    created = await db_client.post(
        RECIPES,
        json={"name": "Gołąbki", "tag_ids": [tag.id]},
        headers=csrf_headers(db_client),
    )
    assert created.status_code == 201
    assert [item["name"] for item in created.json()["tags"]] == ["obiad"]

    ghost = await db_client.post(
        RECIPES,
        json={"name": "Widmo", "tag_ids": [tag.id + 999]},
        headers=csrf_headers(db_client),
    )
    assert ghost.status_code == 422


# --- blokada usuwania produktu (kontrakt między modułami) ---------------------------------


async def test_delete_produktu_uzytego_w_przepisie_przez_api(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """409 z `details.used_in` zawierającym nazwę przepisu (ADR-012, karta B05)."""
    admin = await create_admin(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com")
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Kapusta")
    recipe = await create_recipe(db_session, owner=owner, name="Gołąbki")
    await create_ingredient(db_session, recipe=recipe, product=product)

    await login(db_client, admin.email)
    response = await db_client.delete(
        f"{API}/products/{product.id}", headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    used_in = response.json()["error"]["details"]["used_in"]
    assert {"type": "recipe", "id": recipe.id, "name": "Gołąbki"} in used_in


async def test_uzytkownik_bez_rodziny_nie_utworzy_household(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """04_API §3 pkt 2b: scope household bez rodziny ⇒ 409 z instrukcją."""
    loner = await create_user(db_session, email="samotnik@example.com")
    await login(db_client, loner.email)

    response = await db_client.post(
        RECIPES,
        json={"name": "Gołąbki", "scope": "household"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409


async def test_admin_bez_wyjatku_w_member_profiles_a_z_wyjatkiem_w_scoped(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Utrwalenie granicy D16: `ScopedQuery` daje ADMIN-owi wszystko, ale
    `/households/my` (zasób bez kolumn scope) wciąż pokazuje mu tylko własną
    rodzinę — dokładnie ta niesymetria czeka na decyzję właściciela."""
    admin = await create_admin(db_session)
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    await create_recipe(db_session, owner=owner, scope=Scope.HOUSEHOLD)

    await login(db_client, admin.email)
    assert (await db_client.get(RECIPES)).json()["total"] == 1
    my_household = (await db_client.get(f"{API}/households/my")).json()
    assert my_household["household"] is None
