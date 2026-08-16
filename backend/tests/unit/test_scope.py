"""Czyste reguły `ScopedQuery` — bez bazy i bez HTTP (08_TESTING §1).

Macierz na realnych wierszach żyje w `tests/integration/test_scope_matrix.py`;
tutaj sprawdzamy same decyzje, które da się podjąć bez I/O.
"""

from __future__ import annotations

import pytest

from app.core.errors import ConflictError, ForbiddenError
from app.core.scope import Scope, ScopedQuery
from app.modules.accounts.models import User, UserRole
from tests.scoped_entity import SCOPED_NOTES, ScopedNote

pytestmark = pytest.mark.unit


def _user(user_id: int, *, household_id: int | None = None, role: UserRole = UserRole.USER) -> User:
    """Użytkownik „na sucho" — model SQLAlchemy działa bez sesji."""
    return User(id=user_id, role=role, household_id=household_id)


def _note(owner_id: int, *, household_id: int | None, scope: Scope) -> ScopedNote:
    return ScopedNote(owner_user_id=owner_id, household_id=household_id, scope=scope)


# --- walidacja scope przy tworzeniu ----------------------------------------------


def test_uzytkownik_bez_rodziny_nie_nada_scope_household() -> None:
    """Kluczowa reguła 03_DATABASE §4 — bez rodziny nie ma komu udostępniać."""
    with pytest.raises(ConflictError) as blad:
        ScopedQuery.assert_scope_allowed(_user(1), Scope.HOUSEHOLD)

    assert "rodzin" in blad.value.message.lower()
    assert blad.value.status_code == 409


def test_uzytkownik_bez_rodziny_moze_nadac_scope_private() -> None:
    ScopedQuery.assert_scope_allowed(_user(1), Scope.PRIVATE)


def test_czlonek_rodziny_moze_nadac_oba_scope() -> None:
    czlonek = _user(1, household_id=7)

    ScopedQuery.assert_scope_allowed(czlonek, Scope.PRIVATE)
    ScopedQuery.assert_scope_allowed(czlonek, Scope.HOUSEHOLD)


@pytest.mark.parametrize("scope", [Scope.PRIVATE, Scope.HOUSEHOLD])
def test_kolumny_nowej_encji_biora_wlasciciela_i_rodzine(scope: Scope) -> None:
    """PRIVATE też zapisuje `household_id` — zmiana scope nie musi zgadywać rodziny."""
    kolumny = ScopedQuery.ownership_for_create(_user(3, household_id=7), scope)

    assert kolumny == {"owner_user_id": 3, "household_id": 7, "scope": scope}


def test_kolumny_encji_uzytkownika_bez_rodziny_maja_puste_household_id() -> None:
    kolumny = ScopedQuery.ownership_for_create(_user(3), Scope.PRIVATE)

    assert kolumny == {"owner_user_id": 3, "household_id": None, "scope": Scope.PRIVATE}


def test_ownership_for_create_waliduje_scope_przed_zwrotem() -> None:
    """Walidacja jest wbudowana — serwis nie może jej pominąć przez zapomnienie."""
    with pytest.raises(ConflictError):
        ScopedQuery.ownership_for_create(_user(3), Scope.HOUSEHOLD)


# --- uprawnienia do zmiany scope i usunięcia --------------------------------------


def test_wlasciciel_zarzadza_wlasna_encja() -> None:
    wlasciciel = _user(1, household_id=7)
    note = _note(1, household_id=7, scope=Scope.HOUSEHOLD)

    SCOPED_NOTES.assert_can_manage(note, wlasciciel)


def test_admin_zarzadza_cudza_encja() -> None:
    admin = _user(9, role=UserRole.ADMIN)
    note = _note(1, household_id=7, scope=Scope.HOUSEHOLD)

    SCOPED_NOTES.assert_can_manage(note, admin)


def test_czlonek_rodziny_nie_zarzadza_cudza_encja() -> None:
    """Widzieć i edytować treść wolno, zmienić scope albo usunąć — nie (02_DOMAIN §3.1)."""
    czlonek = _user(2, household_id=7)
    note = _note(1, household_id=7, scope=Scope.HOUSEHOLD)

    with pytest.raises(ForbiddenError) as blad:
        SCOPED_NOTES.assert_can_manage(note, czlonek)

    assert blad.value.status_code == 403


# --- warunek widoczności -----------------------------------------------------------


def test_admin_nie_dostaje_zadnego_ograniczenia() -> None:
    warunek = str(SCOPED_NOTES.visible_condition(_user(9, role=UserRole.ADMIN)))

    assert "scoped_notes.owner_user_id" not in warunek


def test_uzytkownik_bez_rodziny_widzi_wylacznie_swoje() -> None:
    """Bez tego warunku `household_id IS NULL` dopasowałoby cudze wiersze."""
    warunek = str(SCOPED_NOTES.visible_condition(_user(1)))

    assert "scoped_notes.owner_user_id" in warunek
    assert "scoped_notes.scope" not in warunek
    assert "scoped_notes.household_id" not in warunek


def test_czlonek_rodziny_widzi_swoje_i_rodzinne() -> None:
    warunek = str(SCOPED_NOTES.visible_condition(_user(1, household_id=7)))

    assert "scoped_notes.owner_user_id" in warunek
    assert "scoped_notes.scope" in warunek
    assert "scoped_notes.household_id" in warunek
