"""Fabryki danych testowych (08_TESTING §5) — proste funkcje, bez factory-boy.

Hasła w testach są jawne i celowo trywialne; hash liczony jest raz na wartość
(argon2 kosztuje ~50 ms, a tworzymy dziesiątki kont).
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_password, session_expires_at, utcnow
from app.modules.accounts.models import Session, User, UserRole

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
) -> User:
    """Utwórz konto bezpośrednio w bazie (z pominięciem API)."""
    user = User(
        email=email.strip().lower(),
        password_hash=cached_password_hash(password),
        display_name=display_name,
        role=role,
        is_active=is_active,
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
