"""Fabryki danych testowych (08_TESTING §5) — proste funkcje, bez factory-boy.

Hasła w testach są jawne i celowo trywialne; hash liczony jest raz na wartość
(argon2 kosztuje ~50 ms, a tworzymy dziesiątki kont).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_password, session_expires_at, utcnow
from app.modules.accounts.models import Session, User, UserRole
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    Perishability,
    ProductCategory,
    ProductUnitWeight,
    VerificationStatus,
)
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import normalize_unit_label
from app.modules.households.models import Household, MemberProfile

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


async def assign_to_household(
    session: AsyncSession, *, user: User, household: Household | None
) -> User:
    """Przypnij konto do rodziny (albo odepnij, gdy `household is None`)."""
    user.household_id = household.id if household is not None else None
    await session.commit()
    await session.refresh(user)
    return user
