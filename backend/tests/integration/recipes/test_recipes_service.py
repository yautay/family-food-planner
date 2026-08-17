"""Serwis przepisów + baza: normalizacja, rollback, kaskady, oceny, blokady.

Scenariusze z karty B05 §Tests (integration). Wspólny motyw: niezmiennik
02_DOMAIN §13.1 — w bazie nie istnieje składnik bez znormalizowanego `amount`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.scope import Scope
from app.modules.catalog.models import MeasureKind, VerificationStatus
from app.modules.catalog.service import CatalogService
from app.modules.catalog.units import AmountUnit, UnitConversionError
from app.modules.recipes.models import Recipe, RecipeIngredient, RecipeRating, recipe_tags
from app.modules.recipes.schemas import RecipeIngredientInput, RecipePayload
from app.modules.recipes.service import RecipesService
from tests.factories import (
    attach_tag,
    create_admin,
    create_category,
    create_ingredient,
    create_product,
    create_rating,
    create_recipe,
    create_tag,
    create_unit_weight,
    create_user,
)

pytestmark = pytest.mark.integration


async def _count(session: AsyncSession, table: object) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(table))).scalar_one()  # type: ignore[arg-type]
    )


async def test_zapis_przepisu_normalizuje_kazdy_skladnik(db_session: AsyncSession) -> None:
    """kg → g, jednostka domowa → g, szt. → sztuki, l → ml; zapis użytkownika zostaje."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka pszenna")
    await create_unit_weight(
        db_session, product=flour, unit_label="łyżka", grams_per_unit=Decimal("12.00")
    )
    eggs = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )
    milk = await create_product(
        db_session, category=category, name="Mleko 2%", measure_kind=MeasureKind.VOLUME
    )

    service = RecipesService(db_session)
    detail = await service.create_recipe(
        actor=user,
        payload=RecipePayload(
            name="Naleśniki",
            base_servings=4,
            ingredients=[
                RecipeIngredientInput(product_id=flour.id, quantity=Decimal("0.5"), unit="kg"),
                RecipeIngredientInput(product_id=flour.id, quantity=Decimal("2"), unit="łyżka"),
                RecipeIngredientInput(product_id=eggs.id, quantity=Decimal("3"), unit="szt."),
                RecipeIngredientInput(product_id=milk.id, quantity=Decimal("1"), unit="l"),
            ],
        ),
    )

    rows = (
        (
            await db_session.execute(
                select(RecipeIngredient)
                .where(RecipeIngredient.recipe_id == detail.base.recipe.id)
                .order_by(RecipeIngredient.position)
            )
        )
        .scalars()
        .all()
    )
    assert [(row.amount, row.amount_unit) for row in rows] == [
        (Decimal("500.000"), AmountUnit.GRAM),
        (Decimal("24.000"), AmountUnit.GRAM),
        (Decimal("3.000"), AmountUnit.PIECE),
        (Decimal("1000.000"), AmountUnit.MILLILITER),
    ]
    # Zapis użytkownika przetrwał obok postaci znormalizowanej (02_DOMAIN §5).
    assert [(row.display_qty, row.display_unit) for row in rows] == [
        (Decimal("0.500"), "kg"),
        (Decimal("2.000"), "łyżka"),
        (Decimal("3.000"), "szt."),
        (Decimal("1.000"), "l"),
    ]


async def test_nieprzeliczalna_ilosc_wysadza_caly_zapis(db_session: AsyncSession) -> None:
    """Jednostka bez gramatury ⇒ 422 i ROLLBACK — w bazie nie ma ani przepisu, ani składników."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka pszenna")

    service = RecipesService(db_session)
    with pytest.raises(UnitConversionError) as excinfo:
        await service.create_recipe(
            actor=user,
            payload=RecipePayload(
                name="Ciasto",
                ingredients=[
                    RecipeIngredientInput(product_id=flour.id, quantity=Decimal("200"), unit="g"),
                    RecipeIngredientInput(
                        product_id=flour.id, quantity=Decimal("1"), unit="szklanka"
                    ),
                ],
            ),
        )

    assert excinfo.value.status_code == 422
    assert "Mąka pszenna" in excinfo.value.message
    assert "szklanka" in excinfo.value.message
    await db_session.rollback()
    assert await _count(db_session, Recipe.__table__) == 0
    assert await _count(db_session, RecipeIngredient.__table__) == 0


async def test_put_wymienia_skladniki_kompletem(db_session: AsyncSession) -> None:
    """Pełna podmiana: stare wiersze znikają, nowe dostają nowe id (decyzja z karty)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka pszenna")
    sugar = await create_product(db_session, category=category, name="Cukier")

    service = RecipesService(db_session)
    created = await service.create_recipe(
        actor=user,
        payload=RecipePayload(
            name="Ciasto",
            ingredients=[
                RecipeIngredientInput(product_id=flour.id, quantity=Decimal("200"), unit="g")
            ],
        ),
    )
    old_ids = {item.ingredient.id for item in created.ingredients}

    updated = await service.update_recipe(
        created.base.recipe.id,
        actor=user,
        payload=RecipePayload(
            name="Ciasto",
            ingredients=[
                RecipeIngredientInput(product_id=sugar.id, quantity=Decimal("50"), unit="g")
            ],
        ),
    )

    assert await _count(db_session, RecipeIngredient.__table__) == 1
    assert {item.ingredient.id for item in updated.ingredients}.isdisjoint(old_ids)
    assert updated.ingredients[0].product.id == sugar.id


async def test_rating_upsert_nadpisuje_wlasna_ocene(db_session: AsyncSession) -> None:
    """Druga ocena tej samej pary (przepis, user) nadpisuje wiersz, nie dokłada."""
    owner = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=owner)

    service = RecipesService(db_session)
    first = await service.rate_recipe(recipe.id, actor=owner, rating=3)
    second = await service.rate_recipe(recipe.id, actor=owner, rating=5)

    assert first.my_rating == 3
    assert second.my_rating == 5
    assert second.ratings_count == 1
    assert second.avg_rating == Decimal("5.0")
    assert await _count(db_session, RecipeRating.__table__) == 1


async def test_srednia_liczy_sie_z_ocen_wielu_osob(db_session: AsyncSession) -> None:
    """Średnia per przepis: 4 i 5 daje 4,5 (Decimal, zaokrąglenie do 0,1)."""
    owner = await create_user(db_session)
    other = await create_user(db_session, email="drugi@example.com")
    recipe = await create_recipe(db_session, owner=owner)
    await create_rating(db_session, recipe=recipe, user=other, rating=4)

    service = RecipesService(db_session)
    result = await service.rate_recipe(recipe.id, actor=owner, rating=5)

    assert result.ratings_count == 2
    assert result.avg_rating == Decimal("4.5")


async def test_usuniecie_produktu_uzytego_w_przepisie_daje_409_z_nazwa(
    db_session: AsyncSession,
) -> None:
    """Rejestr referencji z karty B05: 409 zawiera CZYTELNĄ nazwę przepisu."""
    admin = await create_admin(db_session)
    owner = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Kapusta")
    recipe = await create_recipe(db_session, owner=owner, name="Gołąbki")
    await create_ingredient(db_session, recipe=recipe, product=product)

    catalog = CatalogService(db_session)
    with pytest.raises(ConflictError) as excinfo:
        await catalog.delete_product(product.id, actor=admin)

    used_in = excinfo.value.details["used_in"]
    assert {"type": "recipe", "id": recipe.id, "name": "Gołąbki"} in used_in


async def test_kaskada_usuwa_skladniki_tagi_i_oceny(db_session: AsyncSession) -> None:
    """recipe → ingredients/tags/ratings znikają; produkt i tag słownikowy zostają."""
    owner = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    recipe = await create_recipe(db_session, owner=owner)
    await create_ingredient(db_session, recipe=recipe, product=product)
    tag = await create_tag(db_session, name="obiad")
    await attach_tag(db_session, recipe=recipe, tag=tag)
    await create_rating(db_session, recipe=recipe, user=owner, rating=4)

    service = RecipesService(db_session)
    await service.delete_recipe(recipe.id, actor=owner)

    assert await _count(db_session, Recipe.__table__) == 0
    assert await _count(db_session, RecipeIngredient.__table__) == 0
    assert await _count(db_session, recipe_tags) == 0
    assert await _count(db_session, RecipeRating.__table__) == 0
    # Słowniki globalne nietknięte (ADR-012: CASCADE tylko w dół kompozycji).
    assert (await db_session.get(type(product), product.id)) is not None
    assert (await db_session.get(type(tag), tag.id)) is not None


async def test_zmiana_scope_na_household_wymaga_rodziny(db_session: AsyncSession) -> None:
    """Użytkownik bez rodziny nie nada HOUSEHOLD — 409 z instrukcją (04_API §3 pkt 2b)."""
    owner = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=owner, scope=Scope.PRIVATE)

    service = RecipesService(db_session)
    with pytest.raises(ConflictError):
        await service.update_recipe(
            recipe.id,
            actor=owner,
            payload=RecipePayload(name=recipe.name, scope=Scope.HOUSEHOLD),
        )


async def test_d15_zmiana_measure_kind_zbija_weryfikacje(db_session: AsyncSession) -> None:
    """D15 (02_DECISIONS): zmiana osi wartości unieważnia weryfikację produktu.

    Silnik liczy „na 100 g" albo „na 100 ml" — po przestawieniu `measure_kind`
    te same liczby znaczą co innego, więc VERIFIED nie może przetrwać.
    """
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Mleko 2%",
        measure_kind=MeasureKind.VOLUME,
        kcal_100=Decimal("50.00"),
        protein_100=Decimal("3.30"),
        fat_100=Decimal("2.00"),
        carbs_100=Decimal("4.80"),
        nutrition_source="producent:etykieta",
        verification_status=VerificationStatus.VERIFIED,
    )

    catalog = CatalogService(db_session)
    view = await catalog.update_product(
        product.id, actor=admin, changes={"measure_kind": MeasureKind.MASS}
    )

    assert view.product.verification_status is VerificationStatus.UNVERIFIED
    assert view.product.verified_at is None


async def test_d15_edycja_bez_zmiany_miary_nie_rusza_weryfikacji(
    db_session: AsyncSession,
) -> None:
    """Kontrprzykład D15: zmiana nazwy nie zbija VERIFIED."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Mleko 2%",
        measure_kind=MeasureKind.VOLUME,
        kcal_100=Decimal("50.00"),
        nutrition_source="producent:etykieta",
        verification_status=VerificationStatus.VERIFIED,
    )

    catalog = CatalogService(db_session)
    view = await catalog.update_product(product.id, actor=admin, changes={"name": "Mleko 2,0%"})

    assert view.product.verification_status is VerificationStatus.VERIFIED
