"""Serwis kont na realnej bazie: sesje, kaskady, unikalność, blokada konta."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    MAX_FAILED_LOGINS,
    SESSION_REFRESH_AFTER,
    SESSION_TTL,
    session_expires_at,
    utcnow,
)
from app.modules.accounts.models import Session, User, UserRole
from app.modules.accounts.service import AccountsService
from tests.factories import TEST_PASSWORD, create_session, create_user

pytestmark = pytest.mark.integration


async def _session_count(db_session: AsyncSession) -> int:
    return (await db_session.execute(select(func.count()).select_from(Session))).scalar_one()


async def test_logowanie_tworzy_sesje_z_ttl_30_dni(db_session: AsyncSession) -> None:
    """Nowa sesja żyje 30 dni (ADR-003) i zapamiętuje IP oraz user agenta."""
    user = await create_user(db_session)
    service = AccountsService(db_session)

    logged_in, session_id = await service.login(
        email=user.email, password=TEST_PASSWORD, ip="10.0.0.7", user_agent="pytest"
    )

    assert logged_in.id == user.id
    row = await db_session.get(Session, session_id)
    assert row is not None
    assert row.ip == "10.0.0.7"
    assert row.user_agent == "pytest"
    assert abs((row.expires_at - session_expires_at(utcnow())).total_seconds()) < 5


async def test_email_porownywany_bez_wielkosci_liter(db_session: AsyncSession) -> None:
    await create_user(db_session, email="Anna@Example.com")
    service = AccountsService(db_session)

    user, _ = await service.login(
        email="  ANNA@example.COM ", password=TEST_PASSWORD, ip=None, user_agent=None
    )

    assert user.email == "anna@example.com"


async def test_ttl_przesuwa_sie_przy_uzyciu_sesji(db_session: AsyncSession) -> None:
    """Sesja bliska końca dostaje nowy termin ważności (TTL przesuwne)."""
    user = await create_user(db_session)
    stara = await create_session(db_session, user=user, expires_in=timedelta(days=2))
    poprzedni_termin = stara.expires_at
    service = AccountsService(db_session)

    _, refreshed = await service.resolve_session(stara.id)

    assert refreshed is True, "warstwa HTTP musi wiedzieć, że trzeba odświeżyć cookie"
    await db_session.refresh(stara)
    assert stara.expires_at > poprzedni_termin
    assert abs((stara.expires_at - (utcnow() + SESSION_TTL)).total_seconds()) < 5


async def test_swieza_sesja_nie_jest_zapisywana_ponownie(db_session: AsyncSession) -> None:
    """Bez progu `SESSION_REFRESH_AFTER` każdy request zapisywałby wiersz sesji."""
    user = await create_user(db_session)
    swieza = await create_session(
        db_session, user=user, expires_in=SESSION_TTL - SESSION_REFRESH_AFTER / 2
    )
    termin = swieza.expires_at

    _, refreshed = await AccountsService(db_session).resolve_session(swieza.id)

    assert refreshed is False
    await db_session.refresh(swieza)
    assert swieza.expires_at == termin


async def test_wygasla_sesja_jest_odrzucana_i_kasowana(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    wygasla = await create_session(db_session, user=user, expires_in=timedelta(seconds=-1))
    service = AccountsService(db_session)

    with pytest.raises(UnauthorizedError):
        await service.resolve_session(wygasla.id)

    assert await db_session.get(Session, wygasla.id) is None


async def test_logowanie_sprzata_wygasle_sesje(db_session: AsyncSession) -> None:
    """03_DATABASE §12: przy logowaniu usuwamy przeterminowane wiersze."""
    user = await create_user(db_session)
    await create_session(db_session, user=user, expires_in=timedelta(days=-1))
    await create_session(db_session, user=user, expires_in=timedelta(days=-30))
    zywa = await create_session(db_session, user=user)

    _, nowa = await AccountsService(db_session).login(
        email=user.email, password=TEST_PASSWORD, ip=None, user_agent=None
    )

    pozostale = (await db_session.execute(select(Session.id))).scalars().all()
    assert set(pozostale) == {zywa.id, nowa}


async def test_sesja_wylaczonego_konta_przestaje_dzialac(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    session = await create_session(db_session, user=user)
    user.is_active = False
    await db_session.commit()

    with pytest.raises(UnauthorizedError):
        await AccountsService(db_session).resolve_session(session.id)

    assert await db_session.get(Session, session.id) is None


async def test_usuniecie_konta_kasuje_jego_sesje(db_session: AsyncSession) -> None:
    """FK ON DELETE CASCADE — sesje nie mogą przeżyć swojego konta."""
    admin = await create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = await create_user(db_session, email="do-usuniecia@example.com")
    await create_session(db_session, user=user)
    await create_session(db_session, user=admin)

    await AccountsService(db_session).delete_user(user.id, actor=admin)

    assert await _session_count(db_session) == 1


async def test_wylogowanie_kasuje_wylacznie_wlasna_sesje(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    pierwsza = await create_session(db_session, user=user)
    druga = await create_session(db_session, user=user)

    await AccountsService(db_session).logout(pierwsza.id)

    assert await db_session.get(Session, pierwsza.id) is None
    assert await db_session.get(Session, druga.id) is not None


async def test_email_jest_unikalny(db_session: AsyncSession) -> None:
    await create_user(db_session, email="zajety@example.com")
    service = AccountsService(db_session)

    with pytest.raises(ConflictError):
        await service.create_user(
            email="Zajety@Example.com",
            password=TEST_PASSWORD,
            display_name="Duplikat",
            role=UserRole.USER,
            is_active=True,
        )


async def test_blokada_konta_po_dziesieciu_porazkach(db_session: AsyncSession) -> None:
    """Po 10 błędnych próbach nawet poprawne hasło daje 401 (07_SECURITY §2)."""
    user = await create_user(db_session)
    service = AccountsService(db_session)

    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(UnauthorizedError):
            await service.login(
                email=user.email, password="zle-haslo-2026", ip=None, user_agent=None
            )

    await db_session.refresh(user)
    assert user.locked_until is not None

    with pytest.raises(UnauthorizedError):
        await service.login(email=user.email, password=TEST_PASSWORD, ip=None, user_agent=None)


async def test_blokada_zyje_w_bazie_a_nie_w_pamieci_procesu(db_session: AsyncSession) -> None:
    """Restart aplikacji nie może zerować blokady — stan jest w wierszu `users`."""
    user = await create_user(db_session)
    service = AccountsService(db_session)

    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(UnauthorizedError):
            await service.login(
                email=user.email, password="zle-haslo-2026", ip=None, user_agent=None
            )

    zapisany = (await db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert zapisany.locked_until is not None
    assert zapisany.locked_until > utcnow()


async def test_udane_logowanie_zeruje_licznik_porazek(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = AccountsService(db_session)

    for _ in range(3):
        with pytest.raises(UnauthorizedError):
            await service.login(
                email=user.email, password="zle-haslo-2026", ip=None, user_agent=None
            )
    await db_session.refresh(user)
    assert user.failed_login_count == 3

    await service.login(email=user.email, password=TEST_PASSWORD, ip=None, user_agent=None)

    await db_session.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None


async def test_zmiana_hasla_uniewaznia_sesje_uzytkownika(db_session: AsyncSession) -> None:
    """Reset hasła przez ADMIN-a wylogowuje konto ze wszystkich urządzeń."""
    admin = await create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = await create_user(db_session, email="user@example.com")
    await create_session(db_session, user=user)
    await create_session(db_session, user=admin)

    await AccountsService(db_session).update_user(user.id, actor=admin, password="nowe-haslo-2026")

    zostale = (await db_session.execute(select(Session.user_id))).scalars().all()
    assert list(zostale) == [admin.id]


async def test_dezaktywacja_konta_uniewaznia_sesje(db_session: AsyncSession) -> None:
    admin = await create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = await create_user(db_session, email="user@example.com")
    await create_session(db_session, user=user)

    await AccountsService(db_session).update_user(user.id, actor=admin, is_active=False)

    assert await _session_count(db_session) == 0
