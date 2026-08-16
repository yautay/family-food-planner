"""Logika modułu accounts: logowanie, sesje, administracja kontami.

Jedyne miejsce I/O tego modułu (ADR-001). Router nie dotyka sesji DB, nie zna
argon2 i nie wie, kiedy sesja wygasa.

Anty-enumeracja (07_SECURITY §1): nieistniejący email, złe hasło, konto
nieaktywne i konto zablokowane dają DOKŁADNIE tę samą odpowiedź 401 z tym samym
komunikatem. Nie wolno tego „poprawiać" na czytelniejsze komunikaty.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    LockoutState,
    burn_password_time,
    generate_token,
    hash_password,
    is_locked,
    register_failure,
    register_success,
    session_expires_at,
    session_is_expired,
    session_needs_refresh,
    utcnow,
    verify_password,
)
from app.modules.accounts.models import Session, User, UserRole

#: Jeden komunikat na wszystkie powody odmowy logowania.
INVALID_CREDENTIALS = "Nieprawidłowy email lub hasło."
SESSION_REQUIRED = "Wymagane zalogowanie."


def normalize_email(email: str) -> str:
    """Email porównujemy bez uwzględniania wielkości liter i białych znaków."""
    return email.strip().lower()


class AccountsService:
    """Operacje na kontach i sesjach. Transakcje commitowane jawnie."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- uwierzytelnianie -----------------------------------------------------

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[User, str]:
        """Zweryfikuj dane i utwórz sesję. Zwraca (użytkownik, id sesji)."""
        now = utcnow()
        await self._purge_expired_sessions(now)

        user = await self._find_by_email(email)
        if user is None:
            # Nieistniejące konto ma kosztować tyle samo czasu, co istniejące.
            await run_in_threadpool(burn_password_time, password)
            await self._session.commit()
            raise UnauthorizedError(INVALID_CREDENTIALS)

        lockout = LockoutState(failed_count=user.failed_login_count, locked_until=user.locked_until)
        if is_locked(lockout, now):
            await run_in_threadpool(burn_password_time, password)
            await self._session.commit()
            raise UnauthorizedError(INVALID_CREDENTIALS)

        check = await run_in_threadpool(verify_password, user.password_hash, password)
        if not check.valid:
            self._apply_lockout(user, register_failure(lockout, now))
            await self._session.commit()
            raise UnauthorizedError(INVALID_CREDENTIALS)

        if not user.is_active:
            await self._session.commit()
            raise UnauthorizedError(INVALID_CREDENTIALS)

        if check.new_hash is not None:
            # Parametry argon2 wzrosły od czasu ostatniego logowania (07_SECURITY §2).
            user.password_hash = check.new_hash
        self._apply_lockout(user, register_success())

        session_id = generate_token()
        self._session.add(
            Session(
                id=session_id,
                user_id=user.id,
                created_at=now,
                expires_at=session_expires_at(now),
                ip=ip,
                user_agent=user_agent,
            )
        )
        await self._session.commit()
        return user, session_id

    async def resolve_session(self, session_id: str) -> tuple[User, bool]:
        """Zamień id sesji na użytkownika. Każdy błąd = 401.

        Zwraca `(użytkownik, czy_przesunięto_TTL)`. Flaga jest istotna dla
        warstwy HTTP: razem z terminem w bazie trzeba odświeżyć cookie, inaczej
        „przesuwne" 30 dni obowiązywałoby tylko po stronie serwera, a przeglądarka
        i tak skasowałaby cookie 30 dni po zalogowaniu.
        """
        now = utcnow()
        session = (
            await self._session.execute(select(Session).where(Session.id == session_id))
        ).scalar_one_or_none()
        if session is None:
            raise UnauthorizedError(SESSION_REQUIRED)

        user = await self._session.get(User, session.user_id)
        if user is None:  # praktycznie niemożliwe (FK CASCADE), ale nie zgadujemy
            await self._session.delete(session)
            await self._session.commit()
            raise UnauthorizedError(SESSION_REQUIRED)

        if session_is_expired(session.expires_at, now) or not user.is_active:
            # Wygasła albo należy do wyłączonego konta — usuwamy od razu.
            await self._session.delete(session)
            await self._session.commit()
            raise UnauthorizedError(SESSION_REQUIRED)

        refreshed = session_needs_refresh(session.expires_at, now)
        if refreshed:
            session.expires_at = session_expires_at(now)
            await self._session.commit()

        return user, refreshed

    async def logout(self, session_id: str) -> None:
        """Usuń sesję — odwołanie jest natychmiastowe (ADR-003)."""
        await self._session.execute(delete(Session).where(Session.id == session_id))
        await self._session.commit()

    async def _purge_expired_sessions(self, now: datetime) -> None:
        """Sprzątanie wygasłych sesji przy logowaniu (03_DATABASE §12)."""
        await self._session.execute(delete(Session).where(Session.expires_at <= now))

    @staticmethod
    def _apply_lockout(user: User, state: LockoutState) -> None:
        user.failed_login_count = state.failed_count
        user.locked_until = state.locked_until

    async def _find_by_email(self, email: str) -> User | None:
        return (
            await self._session.execute(select(User).where(User.email == normalize_email(email)))
        ).scalar_one_or_none()

    # --- administracja kontami ------------------------------------------------

    async def list_users(
        self, *, limit: int, offset: int, query: str | None = None
    ) -> tuple[list[User], int]:
        """Lista kont dla ADMIN-a; `query` filtruje po emailu i nazwie."""
        statement = select(User)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(User.email.ilike(pattern), User.display_name.ilike(pattern))
            )

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    statement.order_by(User.email).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def get_user(self, user_id: int) -> User:
        """Konto po id albo 404."""
        user = await self._session.get(User, user_id)
        if user is None:
            raise NotFoundError("Nie znaleziono konta o podanym identyfikatorze.")
        return user

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        role: UserRole,
        is_active: bool,
    ) -> User:
        """Utwórz konto. Zajęty email = 409 (04_API §1)."""
        normalized = normalize_email(email)
        if await self._find_by_email(normalized) is not None:
            raise ConflictError("Konto z tym adresem e-mail już istnieje.")

        user = User(
            email=normalized,
            password_hash=await run_in_threadpool(hash_password, password),
            display_name=display_name,
            role=role,
            is_active=is_active,
        )
        self._session.add(user)
        try:
            await self._session.commit()
        except IntegrityError as exc:  # wyścig dwóch równoczesnych tworzeń
            await self._session.rollback()
            raise ConflictError("Konto z tym adresem e-mail już istnieje.") from exc
        await self._session.refresh(user)
        return user

    async def update_user(
        self,
        user_id: int,
        *,
        actor: User,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        password: str | None = None,
    ) -> User:
        """Edycja konta przez ADMIN-a z ochroną przed odcięciem samego siebie."""
        user = await self.get_user(user_id)
        self._guard_self_lockout(user, actor, role=role, is_active=is_active)

        if display_name is not None:
            user.display_name = display_name
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if password is not None:
            user.password_hash = await run_in_threadpool(hash_password, password)
            self._apply_lockout(user, register_success())

        # Zmiana hasła albo wyłączenie konta unieważnia wszystkie jego sesje.
        if password is not None or is_active is False:
            await self._session.execute(delete(Session).where(Session.user_id == user.id))

        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def delete_user(self, user_id: int, *, actor: User) -> None:
        """Usuń konto bez powiązanych danych; konto z danymi → 409 (ADR-012)."""
        user = await self.get_user(user_id)
        if user.id == actor.id:
            raise ConflictError("Nie można usunąć własnego konta.")

        await self._session.delete(user)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # FK RESTRICT z modułów domenowych (przepisy, plany… od BATCH_03+).
            await self._session.rollback()
            raise ConflictError(
                "Konto ma powiązane dane i nie może zostać usunięte. Dezaktywuj je zamiast usuwać.",
                details={"used_in": []},
            ) from exc

    @staticmethod
    def _guard_self_lockout(
        user: User, actor: User, *, role: UserRole | None, is_active: bool | None
    ) -> None:
        """ADMIN nie może zdegradować ani wyłączyć własnego konta (karta B02 §6)."""
        if user.id != actor.id:
            return
        if role is not None and role is not UserRole.ADMIN:
            raise ConflictError("Nie można odebrać uprawnień administratora własnemu kontu.")
        if is_active is False:
            raise ConflictError("Nie można dezaktywować własnego konta.")
