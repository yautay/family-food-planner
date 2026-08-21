"""Fabryki danych testowych (08_TESTING §5) — proste funkcje, bez factory-boy.

Hasła w testach są jawne i celowo trywialne; hash liczony jest raz na wartość
(argon2 kosztuje ~50 ms, a tworzymy dziesiątki kont).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import HouseholdScopedQuery, Scope, ScopedQuery
from app.core.security import generate_token, hash_password, session_expires_at, utcnow
from app.modules.accounts.models import Session, User, UserRole
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    Perishability,
    ProductCategory,
    ProductUnitWeight,
    RetailProduct,
    Store,
    StoreCategoryOrder,
    VerificationStatus,
)
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import AmountUnit, base_unit, normalize_unit_label
from app.modules.households.models import Household, MemberProfile
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.pantry.models import PantryItem
from app.modules.planning.models import (
    DayTemplate,
    PlanDay,
    PlanItemServing,
    PlanMeal,
    PlanMealItem,
    WeekCycle,
    WeekTemplate,
)
from app.modules.recipes.models import Recipe, RecipeIngredient, RecipeRating, Tag, recipe_tags
from app.modules.shopping.engine import RoundMode
from app.modules.shopping.models import ShoppingRoundConfig

#: Hasło używane przez fabryki. Nie jest sekretem — istnieje wyłącznie w testach.
TEST_PASSWORD = "haslo-testowe-2026"


@lru_cache(maxsize=8)
def cached_password_hash(password: str) -> str:
    """Hash argon2 liczony raz na proces testowy."""
    return hash_password(password)


async def create_user(
    session: AsyncSession,
    *,
    email: str = "user@example.com",
    password: str = TEST_PASSWORD,
    display_name: str = "Testowy Użytkownik",
    role: UserRole = UserRole.USER,
    is_active: bool = True,
    household: Household | None = None,
) -> User:
    """Utwórz konto bezpośrednio w bazie (z pominięciem API)."""
    user = User(
        email=email.strip().lower(),
        password_hash=cached_password_hash(password),
        display_name=display_name,
        role=role,
        is_active=is_active,
        household_id=household.id if household is not None else None,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_admin(
    session: AsyncSession,
    *,
    email: str = "admin@example.com",
    password: str = TEST_PASSWORD,
    display_name: str = "Administrator",
    is_active: bool = True,
) -> User:
    """Konto z rolą ADMIN."""
    return await create_user(
        session,
        email=email,
        password=password,
        display_name=display_name,
        role=UserRole.ADMIN,
        is_active=is_active,
    )


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    expires_in: timedelta | None = None,
) -> Session:
    """Sesja użytkownika; `expires_in` ujemne = sesja już wygasła."""
    now = utcnow()
    expires_at = now + expires_in if expires_in is not None else session_expires_at(now)
    row = Session(id=generate_token(), user_id=user.id, created_at=now, expires_at=expires_at)
    session.add(row)
    await session.commit()
    return row


async def create_household(session: AsyncSession, *, name: str = "Kowalscy") -> Household:
    """Rodzina bez członków — przypisanie kont robi się osobno."""
    household = Household(name=name)
    session.add(household)
    await session.commit()
    await session.refresh(household)
    return household


async def create_member_profile(
    session: AsyncSession,
    *,
    household: Household,
    name: str = "Ania",
    default_multiplier: Decimal = Decimal("1.00"),
    kcal_goal: Decimal | None = None,
    owner: User | None = None,
    is_active: bool = True,
) -> MemberProfile:
    """Profil członka rodziny (opcjonalnie powiązany z kontem)."""
    profile = MemberProfile(
        household_id=household.id,
        owner_user_id=owner.id if owner is not None else None,
        name=name,
        default_multiplier=default_multiplier,
        kcal_goal=kcal_goal,
        is_active=is_active,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def create_category(
    session: AsyncSession,
    *,
    name: str = "Warzywa",
    position: int = 1,
    perishability: Perishability = Perishability.FRESH,
) -> ProductCategory:
    """Kategoria zakupowa. Testy zakładają własne — seed migracji jest czyszczony."""
    category = ProductCategory(name=name, position=position, perishability=perishability)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def create_product(
    session: AsyncSession,
    *,
    category: ProductCategory,
    name: str = "Cebula",
    measure_kind: MeasureKind = MeasureKind.MASS,
    piece_weight_g: Decimal | None = None,
    kcal_100: Decimal | None = None,
    protein_100: Decimal | None = None,
    fat_100: Decimal | None = None,
    carbs_100: Decimal | None = None,
    fiber_100: Decimal | None = None,
    sugars_100: Decimal | None = None,
    glycemic_index: Decimal | None = None,
    nutrition_source: str | None = None,
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
    is_archived: bool = False,
) -> CanonicalProduct:
    """Produkt kanoniczny; domyślnie bez wartości odżywczych (jak po inline create)."""
    product = CanonicalProduct(
        name=name,
        normalized_name=normalize_name(name),
        category_id=category.id,
        measure_kind=measure_kind,
        piece_weight_g=piece_weight_g,
        kcal_100=kcal_100,
        protein_100=protein_100,
        fat_100=fat_100,
        carbs_100=carbs_100,
        fiber_100=fiber_100,
        sugars_100=sugars_100,
        glycemic_index=glycemic_index,
        nutrition_source=nutrition_source,
        verification_status=verification_status,
        is_archived=is_archived,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def create_unit_weight(
    session: AsyncSession,
    *,
    product: CanonicalProduct,
    unit_label: str = "łyżka",
    grams_per_unit: Decimal = Decimal("15.00"),
    source: str | None = None,
    samples_count: int = 1,
) -> ProductUnitWeight:
    """Przelicznik jednostki domowej (etykieta znormalizowana jak w serwisie)."""
    weight = ProductUnitWeight(
        product_id=product.id,
        unit_label=normalize_unit_label(unit_label),
        grams_per_unit=grams_per_unit,
        source=source,
        samples_count=samples_count,
    )
    session.add(weight)
    await session.commit()
    await session.refresh(weight)
    return weight


async def create_store(
    session: AsyncSession,
    *,
    name: str = "Biedronka",
    color: str | None = None,
    is_archived: bool = False,
) -> Store:
    """Sklep ze słownika globalnego (bez profilu kolejności kategorii)."""
    store = Store(name=name, color=color, is_archived=is_archived)
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store


async def create_category_order(
    session: AsyncSession,
    *,
    store: Store,
    categories: Sequence[ProductCategory],
) -> list[StoreCategoryOrder]:
    """Profil sklepu: kategorie w podanej kolejności (pozycje z indeksów listy)."""
    rows = [
        StoreCategoryOrder(store_id=store.id, category_id=category.id, position=position)
        for position, category in enumerate(categories)
    ]
    session.add_all(rows)
    await session.commit()
    return rows


async def create_retail_product(
    session: AsyncSession,
    *,
    product: CanonicalProduct,
    name: str = "Pilos Jogurt naturalny 400 g",
    brand: str | None = "Pilos",
    store: Store | None = None,
    package_amount: Decimal = Decimal("400.00"),
    package_unit: AmountUnit | None = None,
    pieces_per_package: int | None = None,
    photo_path: str | None = None,
    is_archived: bool = False,
) -> RetailProduct:
    """Wariant sklepowy produktu kanonicznego (fabryka omija serwis).

    `package_unit` domyślnie bierze oś produktu (`base_unit`), więc fabryka nie
    tworzy danych, których serwis by nie przyjął (g dla masy, ml dla objętości,
    sztuki dla sztuk).
    """
    retail = RetailProduct(
        canonical_product_id=product.id,
        name=name,
        brand=brand,
        store_id=store.id if store is not None else None,
        package_amount=package_amount,
        package_unit=package_unit or base_unit(product.measure_kind),
        pieces_per_package=pieces_per_package,
        photo_path=photo_path,
        is_archived=is_archived,
    )
    session.add(retail)
    await session.commit()
    await session.refresh(retail)
    return retail


async def create_recipe(
    session: AsyncSession,
    *,
    owner: User,
    name: str = "Gołąbki",
    scope: Scope = Scope.PRIVATE,
    instructions: str = "",
    base_servings: int = 1,
    prep_time_min: int | None = None,
    difficulty: int | None = None,
    photo_path: str | None = None,
    is_archived: bool = False,
) -> Recipe:
    """Przepis utworzony tak, jak zrobiłby to serwis — przez `ownership_for_create`."""
    recipe = Recipe(
        name=name,
        instructions=instructions,
        base_servings=base_servings,
        prep_time_min=prep_time_min,
        difficulty=difficulty,
        photo_path=photo_path,
        is_archived=is_archived,
        **ScopedQuery.ownership_for_create(owner, scope),
    )
    session.add(recipe)
    await session.commit()
    await session.refresh(recipe)
    return recipe


async def create_ingredient(
    session: AsyncSession,
    *,
    recipe: Recipe,
    product: CanonicalProduct,
    amount: Decimal = Decimal("100.000"),
    amount_unit: AmountUnit = AmountUnit.GRAM,
    display_qty: Decimal | None = None,
    display_unit: str | None = None,
    note: str = "",
    position: int = 0,
) -> RecipeIngredient:
    """Składnik z ilością już znormalizowaną (fabryka omija serwis świadomie)."""
    ingredient = RecipeIngredient(
        recipe_id=recipe.id,
        product_id=product.id,
        amount=amount,
        amount_unit=amount_unit,
        display_qty=display_qty,
        display_unit=display_unit,
        note=note,
        position=position,
    )
    session.add(ingredient)
    await session.commit()
    await session.refresh(ingredient)
    return ingredient


async def create_tag(session: AsyncSession, *, name: str = "obiad", is_system: bool = False) -> Tag:
    """Tag słownika globalnego."""
    tag = Tag(name=name, is_system=is_system)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


async def attach_tag(session: AsyncSession, *, recipe: Recipe, tag: Tag) -> None:
    """Przypisanie N:M przepis↔tag."""
    await session.execute(recipe_tags.insert().values(recipe_id=recipe.id, tag_id=tag.id))
    await session.commit()


async def create_rating(
    session: AsyncSession, *, recipe: Recipe, user: User, rating: int = 5
) -> RecipeRating:
    """Ocena 1-5 pary (przepis, użytkownik)."""
    row = RecipeRating(recipe_id=recipe.id, user_id=user.id, rating=rating)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def create_goal(
    session: AsyncSession,
    *,
    user: User,
    valid_from: date,
    kcal: Decimal = Decimal("2000"),
    protein_g: Decimal | None = None,
    fat_g: Decimal | None = None,
    carbs_g: Decimal | None = None,
) -> UserNutritionGoal:
    """Cel żywieniowy obowiązujący od wskazanej daty (BATCH_06)."""
    goal = UserNutritionGoal(
        user_id=user.id,
        valid_from=valid_from,
        kcal=kcal,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_g,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


async def create_plan_day(
    session: AsyncSession,
    *,
    owner: User,
    day: date,
    title: str | None = None,
    scope: Scope = Scope.PRIVATE,
) -> PlanDay:
    """Dzień planu utworzony tak, jak zrobiłby to serwis (`ownership_for_create`)."""
    entity = PlanDay(day=day, title=title, **ScopedQuery.ownership_for_create(owner, scope))
    session.add(entity)
    await session.commit()
    await session.refresh(entity)
    return entity


async def create_plan_meal(
    session: AsyncSession,
    *,
    plan_day: PlanDay,
    name: str = "Śniadanie",
    position: int = 0,
    kcal_target: Decimal | None = None,
) -> PlanMeal:
    """Posiłek dnia planu."""
    meal = PlanMeal(plan_day_id=plan_day.id, name=name, position=position, kcal_target=kcal_target)
    session.add(meal)
    await session.commit()
    await session.refresh(meal)
    return meal


async def create_plan_item(
    session: AsyncSession,
    *,
    meal: PlanMeal,
    recipe: Recipe | None = None,
    product: CanonicalProduct | None = None,
    amount: Decimal | None = None,
    amount_unit: AmountUnit | None = None,
    servings: Decimal = Decimal("1.00"),
    position: int = 0,
) -> PlanMealItem:
    """Pozycja posiłku z ilością JUŻ znormalizowaną (fabryka omija serwis świadomie)."""
    item = PlanMealItem(
        plan_meal_id=meal.id,
        recipe_id=recipe.id if recipe is not None else None,
        product_id=product.id if product is not None else None,
        amount=amount,
        amount_unit=amount_unit,
        servings=servings,
        position=position,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def create_item_split(
    session: AsyncSession,
    *,
    item: PlanMealItem,
    profile: MemberProfile,
    multiplier: Decimal = Decimal("1.00"),
) -> PlanItemServing:
    """Wiersz rozkładu rodzinnego pozycji planu."""
    row = PlanItemServing(
        plan_meal_item_id=item.id, member_profile_id=profile.id, multiplier=multiplier
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def create_pantry_item(
    session: AsyncSession,
    *,
    owner: User,
    product: CanonicalProduct | None = None,
    retail_product_id: int | None = None,
    amount: Decimal = Decimal("500.000"),
    amount_unit: AmountUnit = AmountUnit.GRAM,
    expiry_date: date | None = None,
    location: str | None = None,
    note: str = "",
) -> PantryItem:
    """Pozycja spiżarni z ilością JUŻ na osi produktu (fabryka omija serwis).

    Kolumny właścicielskie bierze z `HouseholdScopedQuery.ownership_for_create`,
    czyli dokładnie tak, jak robi to serwis: rodzina autora albo — gdy jej nie ma
    — sam autor.
    """
    item = PantryItem(
        product_id=product.id if product is not None else None,
        retail_product_id=retail_product_id,
        amount=amount,
        amount_unit=amount_unit,
        expiry_date=expiry_date,
        location=location,
        note=note,
        **HouseholdScopedQuery.ownership_for_create(owner),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def assign_to_household(
    session: AsyncSession, *, user: User, household: Household | None
) -> User:
    """Przypnij konto do rodziny (albo odepnij, gdy `household is None`)."""
    user.household_id = household.id if household is not None else None
    await session.commit()
    await session.refresh(user)
    return user


async def create_day_template(
    session: AsyncSession,
    *,
    owner: User,
    name: str = "Dzień warzywny",
    payload: dict[str, object] | None = None,
    scope: Scope = Scope.PRIVATE,
) -> DayTemplate:
    """Szablon dnia z payloadem `v:1` (domyślnie pusty — testy scope go nie potrzebują).

    Fabryka zapisuje payload TAK, JAK ROBI TO SERWIS: Decimale jako stringi
    dziesiętne (ADR-008). Podanie floatów w teście złamałoby ten kontrakt cicho.
    """
    template = DayTemplate(
        name=name,
        payload=payload if payload is not None else {"v": 1, "title": None, "meals": []},
        **ScopedQuery.ownership_for_create(owner, scope),
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def create_week_template(
    session: AsyncSession,
    *,
    owner: User,
    name: str = "Tydzień bazowy",
    payload: dict[str, object] | None = None,
    scope: Scope = Scope.PRIVATE,
) -> WeekTemplate:
    """Szablon tygodnia z payloadem `v:1`."""
    template = WeekTemplate(
        name=name,
        payload=payload if payload is not None else {"v": 1, "days": []},
        **ScopedQuery.ownership_for_create(owner, scope),
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def create_week_cycle(
    session: AsyncSession,
    *,
    owner: User,
    name: str = "Cykl A-B",
    template_ids: list[int] | None = None,
    start_date: date | None = None,
    scope: Scope = Scope.PRIVATE,
) -> WeekCycle:
    """Cykl tygodni — kolejność `template_ids` JEST rotacją."""
    cycle = WeekCycle(
        name=name,
        template_ids=template_ids if template_ids is not None else [],
        start_date=start_date,
        **ScopedQuery.ownership_for_create(owner, scope),
    )
    session.add(cycle)
    await session.commit()
    await session.refresh(cycle)
    return cycle


def day_payload(
    *,
    title: str | None = None,
    meals: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Payload szablonu dnia w kształcie kontraktu `v:1` (skrót dla testów)."""
    return {"v": 1, "title": title, "meals": meals if meals is not None else []}


def template_meal(
    *,
    name: str = "Obiad",
    position: int = 0,
    kcal_target: str | None = None,
    items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Posiłek w payloadzie szablonu."""
    return {
        "name": name,
        "kcal_target": kcal_target,
        "position": position,
        "items": items if items is not None else [],
    }


def template_recipe_item(
    recipe_id: int, *, servings: str = "1", position: int = 0
) -> dict[str, object]:
    """Pozycja szablonu z przepisem (bez ilości — steruje nią mnożnik)."""
    return {
        "recipe_id": recipe_id,
        "servings": servings,
        "position": position,
        "servings_split": [],
    }


def template_product_item(
    product_id: int,
    *,
    amount: str = "100.000",
    amount_unit: str = "g",
    servings: str = "1",
    position: int = 0,
) -> dict[str, object]:
    """Pozycja szablonu z produktem luzem (ilość ZNORMALIZOWANA, jak w planie)."""
    return {
        "product_id": product_id,
        "amount": amount,
        "amount_unit": amount_unit,
        "servings": servings,
        "position": position,
        "servings_split": [],
    }


async def create_round_config(
    session: AsyncSession,
    *,
    owner: User,
    name: str = "Niedziela",
    mode: RoundMode = RoundMode.DURABLE_PLUS_FRESH_WINDOW,
    covers_days: int = 7,
    fresh_days: int | None = 4,
    shopping_weekday: int | None = 6,
    position: int = 0,
    scope: Scope = Scope.PRIVATE,
) -> ShoppingRoundConfig:
    """Tura zakupowa utworzona tak, jak zrobiłby to serwis (`ownership_for_create`)."""
    config = ShoppingRoundConfig(
        name=name,
        mode=mode,
        covers_days=covers_days,
        fresh_days=fresh_days if mode is RoundMode.DURABLE_PLUS_FRESH_WINDOW else None,
        shopping_weekday=shopping_weekday,
        position=position,
        **ScopedQuery.ownership_for_create(owner, scope),
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config
