"""Kontrakt HTTP `/plan/*`: macierz uprawnień 08_TESTING §4, agregaty, kopiowanie.

Plan dnia jest encją ze scope, więc macierz dowodzona jest kodami HTTP
(anonim 401 / obcy 404 / członek rodziny 200 / zmiana scope przez członka 403).
Osobno sprawdzany jest anty-IDOR na zagnieżdżonych id: `/plan/meals/{id}`
i `/plan/items/{id}` weryfikują CAŁY łańcuch aż do dnia, nie samo istnienie id.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.modules.catalog.models import CanonicalProduct, VerificationStatus
from app.modules.catalog.units import AmountUnit
from tests.factories import (
    create_admin,
    create_category,
    create_goal,
    create_household,
    create_ingredient,
    create_member_profile,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

PLAN = f"{API}/plan"
DAY = "2026-08-17"
NEXT_DAY = "2026-08-18"
#: Te same daty jako obiekty — fabryki przyjmują `date`, URL-e tekst.
DAY_DATE = date(2026, 8, 17)
NEXT_DAY_DATE = date(2026, 8, 18)


async def _verified_product(session: AsyncSession, *, name: str = "Skyr") -> CanonicalProduct:
    """Produkt 60 kcal / 100 g z kompletem wartości — wyniki liczą się „na czysto"."""
    category = await create_category(session, name=f"Kategoria {name}")
    return await create_product(
        session,
        category=category,
        name=name,
        kcal_100=Decimal("60.00"),
        protein_100=Decimal("10.00"),
        fat_100=Decimal("0.20"),
        carbs_100=Decimal("4.00"),
        fiber_100=Decimal("0.00"),
        sugars_100=Decimal("4.00"),
        glycemic_index=Decimal("11.0"),
        verification_status=VerificationStatus.VERIFIED,
    )


# --- macierz uprawnień (08_TESTING §4) ------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Plan wymaga sesji na każdej ścieżce (04_API §3 pkt 1)."""
    assert (await db_client.get(f"{PLAN}/days?from={DAY}&to={DAY}")).status_code == 401
    assert (await db_client.get(f"{PLAN}/days/{DAY}")).status_code == 401


async def test_mutacja_bez_csrf_to_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Middleware CSRF działa przed routingiem (07_SECURITY §3)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(f"{PLAN}/days/{DAY}/meals", json={"name": "Obiad"})

    assert response.status_code == 403


async def test_cudzy_dzien_prywatny_jest_niewidoczny(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PRIVATE właściciela = dla członka rodziny pusty dzień, nie cudza treść."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    await create_plan_day(db_session, owner=owner, day=DAY_DATE, title="Tajny")

    await login(db_client, member.email)
    body = (await db_client.get(f"{PLAN}/days/{DAY}")).json()

    assert body["id"] is None
    assert body["title"] is None
    assert (await db_client.get(f"{PLAN}/days?from={DAY}&to={DAY}")).json()["total"] == 0


async def test_dzien_household_widzi_i_edytuje_kazdy_czlonek(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odczyt i edycja treści HOUSEHOLD: każdy członek rodziny (02_DOMAIN §3.1)."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    plan_day = await create_plan_day(
        db_session,
        owner=owner,
        day=DAY_DATE,
        scope=Scope.HOUSEHOLD,
        title="Wspólny",
    )

    await login(db_client, member.email)
    assert (await db_client.get(f"{PLAN}/days/{DAY}")).json()["id"] == plan_day.id

    added = await db_client.post(
        f"{PLAN}/days/{DAY}/meals", json={"name": "Obiad"}, headers=csrf_headers(db_client)
    )
    assert added.status_code == 201
    assert [meal["name"] for meal in added.json()["meals"]] == ["Obiad"]


async def test_zmiana_scope_przez_czlonka_to_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zmiana widoczności to `assert_can_manage` — właściciel albo ADMIN."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    await create_plan_day(
        db_session,
        owner=owner,
        day=DAY_DATE,
        scope=Scope.HOUSEHOLD,
    )

    await login(db_client, member.email)
    response = await db_client.put(
        f"{PLAN}/days/{DAY}", json={"scope": "private"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 403


async def test_d16_admin_widzi_cudzy_plan_na_sciezkach_uzytkownika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stan faktyczny `ScopedQuery` (D16): ADMIN ma 200 w każdym wierszu macierzy.

    Rozstrzygnięcie odwrotne (ADMIN bez wyjątku na ścieżkach użytkownika)
    zaczyna się od `app/core/scope.py:visible_condition` i wywrócenia tego testu
    razem z jego odpowiednikiem w `tests/api/recipes/test_recipes_api.py`.
    """
    owner = await create_user(db_session, email="owner@example.com")
    admin = await create_admin(db_session)
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY_DATE, title="Cudzy")

    await login(db_client, admin.email)

    assert (await db_client.get(f"{PLAN}/days/{DAY}")).json()["id"] == plan_day.id


async def test_anty_idor_na_zagniezdzonym_id_posilku_i_pozycji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cudzy posiłek/pozycja to 404 — sprawdzany jest łańcuch, nie samo id."""
    owner = await create_user(db_session, email="owner@example.com")
    stranger = await create_user(db_session, email="stranger@example.com")
    recipe = await create_recipe(db_session, owner=owner)
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)

    await login(db_client, stranger.email)
    headers = csrf_headers(db_client)

    assert (
        await db_client.patch(f"{PLAN}/meals/{meal.id}", json={"name": "X"}, headers=headers)
    ).status_code == 404
    assert (
        await db_client.patch(f"{PLAN}/items/{item.id}", json={"servings": "2"}, headers=headers)
    ).status_code == 404
    assert (await db_client.delete(f"{PLAN}/items/{item.id}", headers=headers)).status_code == 404
    assert (
        await db_client.post(f"{PLAN}/items/{item.id}/fit-to-target", headers=headers)
    ).status_code == 404


# --- odczyt dnia ---------------------------------------------------------------------------


async def test_pusta_data_zwraca_pusty_dzien_z_zerami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Data bez planu to 200 z pustym dniem — 404 zmuszałoby UI do udawania błędu."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    body = (await db_client.get(f"{PLAN}/days/{DAY}")).json()

    assert body["id"] is None
    assert body["meals"] == []
    assert body["nutrition"]["kcal"] == "0"
    assert body["goal_progress"]["kcal"] == {
        "value": "0",
        "target": None,
        "delta": None,
        "status": None,
    }


async def test_kafelki_dnia_licza_wartosc_cel_delte_i_status(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Trio wartość/cel/delta + status słowny wg progów z `ui_settings` (06_UIUX §3.5)."""
    user = await create_user(db_session)
    await create_goal(
        db_session,
        user=user,
        valid_from=date(2026, 1, 1),
        kcal=Decimal("1000"),
        protein_g=Decimal("50.0"),
    )
    product = await _verified_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session, meal=meal, product=product, amount=Decimal("1000"), amount_unit=AmountUnit.GRAM
    )

    await login(db_client, user.email)
    body = (await db_client.get(f"{PLAN}/days/{DAY}")).json()

    # 1000 g x 60 kcal/100 g = 600 kcal wobec celu 1000 kcal → 60% celu.
    assert body["goal_progress"]["kcal"] == {
        "value": "600",
        "target": "1000",
        "delta": "-400",
        "status": "below",
    }
    assert body["goal_valid_from"] == "2026-01-01"
    # 1000 g x 10 g białka/100 g = 100 g wobec celu 50 g → 200% celu.
    assert body["goal_progress"]["protein_g"]["status"] == "above"


async def test_status_uwzglednia_progi_uzytkownika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Te same liczby, inne progi (D9): 60% celu jest „ok" przy progach 50/150."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("1000"))
    product = await _verified_product(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session, meal=meal, product=product, amount=Decimal("1000"), amount_unit=AmountUnit.GRAM
    )

    await login(db_client, user.email)
    await db_client.patch(
        f"{API}/auth/me/ui-settings",
        json={"nutrition_thresholds": {"low": 50, "high": 150}},
        headers=csrf_headers(db_client),
    )
    body = (await db_client.get(f"{PLAN}/days/{DAY}")).json()

    assert body["goal_progress"]["kcal"]["status"] == "ok"


async def test_zakres_dat_zwraca_tylko_istniejace_dni(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`GET /plan/days?from=&to=` — dni istniejące, posortowane po dacie."""
    user = await create_user(db_session)
    await create_plan_day(db_session, owner=user, day=NEXT_DAY_DATE)
    await create_plan_day(db_session, owner=user, day=DAY_DATE)

    await login(db_client, user.email)
    body = (await db_client.get(f"{PLAN}/days?from=2026-08-16&to=2026-08-22")).json()

    assert [item["day"] for item in body["items"]] == [DAY, NEXT_DAY]
    assert body["total"] == 2


async def test_odwrocony_zakres_dat_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`from` po `to` to błąd wejścia, nie pusta lista udająca poprawny wynik."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(f"{PLAN}/days?from={NEXT_DAY}&to={DAY}")

    assert response.status_code == 422


# --- posiłki i pozycje ----------------------------------------------------------------------


async def test_pelny_przeplyw_dodawania_posilku_i_pozycji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Smoke kontraktu: posiłek (tworzy dzień) → pozycja z przepisu → wartości w dniu."""
    user = await create_user(db_session)
    product = await _verified_product(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Owsianka", base_servings=2)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=product,
        amount=Decimal("400"),
        amount_unit=AmountUnit.GRAM,
    )

    await login(db_client, user.email)
    created = await db_client.post(
        f"{PLAN}/days/{DAY}/meals",
        json={"name": "II śniadanie", "kcal_target": "300"},
        headers=csrf_headers(db_client),
    )
    assert created.status_code == 201
    meal_id = created.json()["meals"][0]["id"]

    added = await db_client.post(
        f"{PLAN}/meals/{meal_id}/items",
        json={"recipe_id": recipe.id, "servings": "1"},
        headers=csrf_headers(db_client),
    )

    assert added.status_code == 201
    body = added.json()
    # Porcja = 400 g / 2 = 200 g x 60 kcal/100 g = 120 kcal.
    assert body["meals"][0]["items"][0]["nutrition"]["kcal"] == "120"
    assert body["meals"][0]["nutrition"]["kcal"] == "120"
    assert body["nutrition"]["kcal"] == "120"
    assert body["meals"][0]["kcal_status"] == "below"
    assert body["meals"][0]["items"][0]["recipe_name"] == "Owsianka"


async def test_patch_mnoznika_zmienia_pozycje_posilek_i_dzien_w_jednej_odpowiedzi(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Niezmiennik 02_DOMAIN §13.3 widziany przez API — jedna odpowiedź GET, trzy poziomy."""
    user = await create_user(db_session)
    product = await _verified_product(db_session)
    recipe = await create_recipe(db_session, owner=user, base_servings=1)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=product,
        amount=Decimal("100"),
        amount_unit=AmountUnit.GRAM,
    )
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)

    await login(db_client, user.email)
    patched = await db_client.patch(
        f"{PLAN}/items/{item.id}", json={"servings": "3"}, headers=csrf_headers(db_client)
    )
    assert patched.status_code == 200

    body = (await db_client.get(f"{PLAN}/days/{DAY}")).json()
    assert body["meals"][0]["items"][0]["nutrition"]["kcal"] == "180"
    assert body["meals"][0]["nutrition"]["kcal"] == "180"
    assert body["nutrition"]["kcal"] == "180"


async def test_produkt_luzem_z_jednostka_nieprzeliczalna_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Brak przelicznika „garść" przy produkcie ⇒ 422 i pozycja nie powstaje."""
    user = await create_user(db_session)
    product = await _verified_product(db_session)
    await login(db_client, user.email)
    meal_id = (
        await db_client.post(
            f"{PLAN}/days/{DAY}/meals", json={"name": "Obiad"}, headers=csrf_headers(db_client)
        )
    ).json()["meals"][0]["id"]

    response = await db_client.post(
        f"{PLAN}/meals/{meal_id}/items",
        json={"product_id": product.id, "quantity": "2", "unit": "garść"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert (await db_client.get(f"{PLAN}/days/{DAY}")).json()["meals"][0]["items"] == []


async def test_pozycja_bez_przepisu_i_bez_produktu_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """CHECK „przepis XOR produkt" zaczyna się już na walidatorze schematu."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    meal_id = (
        await db_client.post(
            f"{PLAN}/days/{DAY}/meals", json={"name": "Obiad"}, headers=csrf_headers(db_client)
        )
    ).json()["meals"][0]["id"]

    response = await db_client.post(
        f"{PLAN}/meals/{meal_id}/items", json={"servings": "1"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 422


async def test_rozklad_rodzinny_wychodzi_z_imionami_profili(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Drawer rozkładu dostaje imiona od razu — bez dodatkowego zapytania."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    ania = await create_member_profile(db_session, household=household, name="Ania")
    olek = await create_member_profile(db_session, household=household, name="Olek")
    recipe = await create_recipe(db_session, owner=user)

    await login(db_client, user.email)
    meal_id = (
        await db_client.post(
            f"{PLAN}/days/{DAY}/meals", json={"name": "Obiad"}, headers=csrf_headers(db_client)
        )
    ).json()["meals"][0]["id"]

    response = await db_client.post(
        f"{PLAN}/meals/{meal_id}/items",
        json={
            "recipe_id": recipe.id,
            "servings": "1.8",
            "servings_split": [
                {"member_profile_id": ania.id, "multiplier": "1"},
                {"member_profile_id": olek.id, "multiplier": "0.8"},
            ],
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    split = response.json()["meals"][0]["items"][0]["servings_split"]
    assert [row["member_name"] for row in split] == ["Ania", "Olek"]
    assert [row["multiplier"] for row in split] == ["1.00", "0.80"]


async def test_niezgodna_suma_rozkladu_to_422_z_liczbami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Komunikat mówi, ile powinno być i ile jest — użytkownik ma co poprawić."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household)
    recipe = await create_recipe(db_session, owner=user)

    await login(db_client, user.email)
    meal_id = (
        await db_client.post(
            f"{PLAN}/days/{DAY}/meals", json={"name": "Obiad"}, headers=csrf_headers(db_client)
        )
    ).json()["meals"][0]["id"]

    response = await db_client.post(
        f"{PLAN}/meals/{meal_id}/items",
        json={
            "recipe_id": recipe.id,
            "servings": "2",
            "servings_split": [{"member_profile_id": profile.id, "multiplier": "1"}],
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    # Porównujemy WARTOŚCI, nie zapis: „2" i „2.00" to ta sama liczba, a test
    # nie ma pilnować formatowania kwoty w komunikacie.
    assert Decimal(details["expected"]) == Decimal("2")
    assert Decimal(details["actual"]) == Decimal("1")


# --- dopasuj porcję do celu -------------------------------------------------------------------


async def test_fit_to_target_zwraca_propozycje_i_niczego_nie_zapisuje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Akcja jest JAWNA: GET po `fit-to-target` pokazuje stan sprzed (02_DOMAIN §6)."""
    user = await create_user(db_session)
    product = await _verified_product(db_session)
    recipe = await create_recipe(db_session, owner=user, base_servings=1)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=product,
        amount=Decimal("200"),
        amount_unit=AmountUnit.GRAM,
    )
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day, kcal_target=Decimal("500"))
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)

    await login(db_client, user.email)
    response = await db_client.post(
        f"{PLAN}/items/{item.id}/fit-to-target", headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "item_id": item.id,
        "target_kcal": "500",
        "current_servings": "1.00",
        "proposed_servings": "4.16",
        "resulting_nutrition": body["resulting_nutrition"],
    }
    assert body["resulting_nutrition"]["kcal"] == "499"

    after = (await db_client.get(f"{PLAN}/days/{DAY}")).json()
    assert after["meals"][0]["items"][0]["servings"] == "1.00"
    assert after["nutrition"]["kcal"] == "120"


async def test_fit_to_target_bez_celu_posilku_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Bez `kcal_target` nie ma do czego dopasować — komunikat mówi, co zrobić."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    item = await create_plan_item(db_session, meal=meal, recipe=recipe)

    await login(db_client, user.email)
    response = await db_client.post(
        f"{PLAN}/items/{item.id}/fit-to-target", headers=csrf_headers(db_client)
    )

    assert response.status_code == 422
    assert "cel" in response.json()["error"]["message"].lower()


# --- kopiowanie -----------------------------------------------------------------------------


async def test_kopiowanie_dnia_na_dwie_daty(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`/plan/copy` zwraca dni docelowe po kopii — FE nie musi dopytywać."""
    user = await create_user(db_session)
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    await create_plan_meal(db_session, plan_day=plan_day, name="Obiad")

    await login(db_client, user.email)
    response = await db_client.post(
        f"{PLAN}/copy",
        json={"what": "day", "source_date": DAY, "target_dates": [NEXT_DAY, "2026-08-19"]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["day"] for item in body["items"]] == [NEXT_DAY, "2026-08-19"]
    assert all(len(item["meals"]) == 1 for item in body["items"])


async def test_kopiowanie_bez_zrodla_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`what=day` bez `source_date` odpada na walidatorze schematu."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{PLAN}/copy",
        json={"what": "day", "target_dates": [NEXT_DAY]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_kopiowanie_cudzego_posilku_to_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nie da się skopiować do siebie posiłku, którego się nie widzi."""
    owner = await create_user(db_session, email="owner@example.com")
    stranger = await create_user(db_session, email="stranger@example.com")
    plan_day = await create_plan_day(db_session, owner=owner, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)

    await login(db_client, stranger.email)
    response = await db_client.post(
        f"{PLAN}/copy",
        json={"what": "meal", "source_meal_id": meal.id, "target_dates": [NEXT_DAY]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404
