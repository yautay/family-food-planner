"""Macierz uprawnień scope (08_TESTING §4) na encji testowej `ScopedNote`.

To jest produkt BATCH_03: KAŻDA encja współdzielna z kolejnych batchy (recipes,
plany, szablony, spiżarnia, listy zakupowe) konsumuje ten sam `ScopedQuery`,
więc reguły wystarczy udowodnić raz — tutaj — a w batchach domenowych powtarzać
jako testy API konkretnego zasobu.

Obsada testów:
- `owner`     — właściciel notatki, członek rodziny „Kowalscy",
- `member`    — inny członek tej samej rodziny,
- `outsider`  — użytkownik z innej rodziny,
- `loner`     — użytkownik bez rodziny,
- `admin`     — ADMIN (widzi wszystko, zarządza wszystkim).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.scope import Scope, ScopedQuery
from app.modules.accounts.models import User
from app.modules.households.models import Household, MemberProfile
from tests.factories import create_admin, create_household, create_member_profile, create_user
from tests.scoped_entity import SCOPED_NOTES, ScopedNote, create_scoped_note

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Cast:
    """Obsada jednego testu macierzy."""

    household: Household
    other_household: Household
    owner: User
    member: User
    outsider: User
    loner: User
    admin: User


@pytest.fixture
async def cast(scoped_notes_table: None, db_session: AsyncSession) -> Cast:
    """Dwie rodziny, czterech użytkowników i administrator."""
    household = await create_household(db_session, name="Kowalscy")
    other = await create_household(db_session, name="Nowakowie")
    return Cast(
        household=household,
        other_household=other,
        owner=await create_user(db_session, email="owner@example.com", household=household),
        member=await create_user(db_session, email="member@example.com", household=household),
        outsider=await create_user(db_session, email="outsider@example.com", household=other),
        loner=await create_user(db_session, email="loner@example.com"),
        admin=await create_admin(db_session, email="admin@example.com"),
    )


async def _visible_ids(session: AsyncSession, user: User) -> set[int]:
    rows = (await session.execute(SCOPED_NOTES.select_visible(user))).scalars().all()
    return {row.id for row in rows}


# --- odczyt PRIVATE ------------------------------------------------------------


async def test_private_widzi_wylacznie_wlasciciel_i_admin(
    db_session: AsyncSession, cast: Cast
) -> None:
    """Wiersz PRIVATE jest niewidoczny nawet dla członka tej samej rodziny."""
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.PRIVATE)

    assert await _visible_ids(db_session, cast.owner) == {note.id}
    assert await _visible_ids(db_session, cast.admin) == {note.id}
    for kto in (cast.member, cast.outsider, cast.loner):
        assert await _visible_ids(db_session, kto) == set(), f"{kto.email} widzi cudzy PRIVATE"


@pytest.mark.parametrize("aktor", ["member", "outsider", "loner"])
async def test_odczyt_cudzego_private_konczy_sie_404(
    db_session: AsyncSession, cast: Cast, aktor: str
) -> None:
    """Cudzy zasób to 404, nie 403 — nie potwierdzamy jego istnienia (07 §4)."""
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.PRIVATE)

    with pytest.raises(NotFoundError):
        await SCOPED_NOTES.get_or_404(db_session, note.id, getattr(cast, aktor))


async def test_wlasciciel_i_admin_odczytuja_private(db_session: AsyncSession, cast: Cast) -> None:
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.PRIVATE)

    assert (await SCOPED_NOTES.get_or_404(db_session, note.id, cast.owner)).id == note.id
    assert (await SCOPED_NOTES.get_or_404(db_session, note.id, cast.admin)).id == note.id


# --- odczyt i edycja HOUSEHOLD --------------------------------------------------


async def test_household_widzi_kazdy_czlonek_rodziny(db_session: AsyncSession, cast: Cast) -> None:
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)

    for kto in (cast.owner, cast.member, cast.admin):
        assert (await SCOPED_NOTES.get_or_404(db_session, note.id, kto)).id == note.id


async def test_household_jest_niewidoczne_spoza_rodziny(
    db_session: AsyncSession, cast: Cast
) -> None:
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)

    for kto in (cast.outsider, cast.loner):
        with pytest.raises(NotFoundError):
            await SCOPED_NOTES.get_or_404(db_session, note.id, kto)


async def test_czlonek_rodziny_edytuje_tresc_household(
    db_session: AsyncSession, cast: Cast
) -> None:
    """Edycja HOUSEHOLD przez każdego członka (02_DOMAIN §3.1 pkt 2) — bez 403."""
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)

    widziana = await SCOPED_NOTES.get_or_404(db_session, note.id, cast.member)
    widziana.title = "Zmienione przez członka rodziny"
    await db_session.commit()

    assert (await db_session.get(ScopedNote, note.id)) is not None
    assert (await SCOPED_NOTES.get_or_404(db_session, note.id, cast.owner)).title == (
        "Zmienione przez członka rodziny"
    )


# --- zmiana scope i usunięcie ---------------------------------------------------


async def test_czlonek_rodziny_nie_zmieni_scope_ani_nie_usunie(
    db_session: AsyncSession, cast: Cast
) -> None:
    """Widoczna encja, ale operacja zastrzeżona dla właściciela → 403 (nie 404)."""
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)
    widziana = await SCOPED_NOTES.get_or_404(db_session, note.id, cast.member)

    with pytest.raises(ForbiddenError):
        SCOPED_NOTES.assert_can_manage(widziana, cast.member)


async def test_wlasciciel_i_admin_zarzadzaja_encja(db_session: AsyncSession, cast: Cast) -> None:
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)

    SCOPED_NOTES.assert_can_manage(note, cast.owner)
    SCOPED_NOTES.assert_can_manage(note, cast.admin)


async def test_obcy_nie_dochodzi_nawet_do_sprawdzenia_uprawnien(
    db_session: AsyncSession, cast: Cast
) -> None:
    """Dla obcego ścieżka kończy się na 404 z `get_or_404` — 403 nigdy nie pada."""
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)

    with pytest.raises(NotFoundError):
        await SCOPED_NOTES.get_or_404(db_session, note.id, cast.outsider)


# --- walidacja scope ------------------------------------------------------------


async def test_uzytkownik_bez_rodziny_nie_nada_scope_household(
    db_session: AsyncSession, cast: Cast
) -> None:
    """Reguła serwisowa: bez rodziny nie ma czego udostępniać (03_DATABASE §4)."""
    with pytest.raises(ConflictError):
        ScopedQuery.ownership_for_create(cast.loner, Scope.HOUSEHOLD)


async def test_uzytkownik_bez_rodziny_tworzy_private(db_session: AsyncSession, cast: Cast) -> None:
    note = await create_scoped_note(db_session, owner=cast.loner, scope=Scope.PRIVATE)

    assert note.household_id is None
    assert await _visible_ids(db_session, cast.loner) == {note.id}


async def test_baza_odrzuca_household_bez_household_id(
    db_session: AsyncSession, cast: Cast
) -> None:
    """CHECK w bazie jest drugą linią obrony, gdy ktoś ominie serwis."""
    db_session.add(
        ScopedNote(
            title="Nielegalna",
            owner_user_id=cast.loner.id,
            household_id=None,
            scope=Scope.HOUSEHOLD,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_notatka_prywatna_zapisuje_household_wlasciciela(
    db_session: AsyncSession, cast: Cast
) -> None:
    """PRIVATE też trzyma `household_id` — późniejsza zmiana scope nie zgaduje rodziny."""
    note = await create_scoped_note(db_session, owner=cast.owner, scope=Scope.PRIVATE)

    assert note.household_id == cast.household.id
    assert await _visible_ids(db_session, cast.member) == set()


# --- konsekwencje kasowania rodziny ---------------------------------------------


async def test_usuniecie_rodziny_czysci_household_id_uzytkownika(
    db_session: AsyncSession, cast: Cast
) -> None:
    """`users.household_id` ON DELETE SET NULL — konto przeżywa rozwiązanie rodziny."""
    await db_session.execute(
        text("DELETE FROM households WHERE id = :id"), {"id": cast.other_household.id}
    )
    await db_session.commit()
    await db_session.refresh(cast.outsider)

    assert cast.outsider.household_id is None


async def test_usuniecie_rodziny_kasuje_profile_czlonkow(
    db_session: AsyncSession, cast: Cast
) -> None:
    """`member_profiles.household_id` ON DELETE CASCADE — profile są częścią rodziny."""
    await create_member_profile(db_session, household=cast.other_household, name="Zosia")

    await db_session.execute(
        text("DELETE FROM households WHERE id = :id"), {"id": cast.other_household.id}
    )
    await db_session.commit()

    pozostale = (await db_session.execute(select(MemberProfile))).scalars().all()
    assert pozostale == []


async def test_encja_ze_scope_blokuje_usuniecie_rodziny(
    db_session: AsyncSession, cast: Cast
) -> None:
    """`household_id` w encji ze scope ma RESTRICT — inaczej CHECK zostałby złamany."""
    await create_scoped_note(db_session, owner=cast.owner, scope=Scope.HOUSEHOLD)

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM households WHERE id = :id"), {"id": cast.household.id}
        )
        await db_session.commit()
    await db_session.rollback()
