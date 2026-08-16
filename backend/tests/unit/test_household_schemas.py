"""Walidacja schematów modułu households — bez bazy i bez HTTP.

Reguły odzwierciedlają kolumny z 03_DATABASE §2: `default_multiplier`
NUMERIC(4,2) dodatni, `kcal_goal` NUMERIC(6,0) dodatni. Wartości wchodzą jako
stringi dziesiętne (ADR-008) i takie same wychodzą.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.households.schemas import (
    HouseholdCreateRequest,
    HouseholdMembersRequest,
    MemberProfileCreateRequest,
    MemberProfileUpdateRequest,
)

pytestmark = pytest.mark.unit


def _fields(error: ValidationError) -> set[str]:
    return {str(detail["loc"][0]) for detail in error.errors()}


# --- mnożnik porcji ---------------------------------------------------------------


def test_domyslny_mnoznik_to_jeden() -> None:
    profil = MemberProfileCreateRequest(name="Zosia")

    assert profil.default_multiplier == Decimal("1.00")
    assert profil.kcal_goal is None
    assert profil.is_active is True


def test_mnoznik_przyjmuje_string_dziesietny() -> None:
    """Kwoty w JSON są stringami — parsowanie musi być bezstratne (ADR-008)."""
    profil = MemberProfileCreateRequest.model_validate(
        {"name": "Zosia", "default_multiplier": "0.8"}
    )

    assert profil.default_multiplier == Decimal("0.8")


@pytest.mark.parametrize("wartosc", ["0", "-1", "-0.5"])
def test_mnoznik_musi_byc_dodatni(wartosc: str) -> None:
    with pytest.raises(ValidationError) as blad:
        MemberProfileCreateRequest.model_validate({"name": "Zosia", "default_multiplier": wartosc})

    assert "default_multiplier" in _fields(blad.value)


def test_mnoznik_nie_moze_miec_wiecej_niz_dwie_cyfry_po_przecinku() -> None:
    """NUMERIC(4,2) — trzecia cyfra zostałaby po cichu zaokrąglona przez bazę."""
    with pytest.raises(ValidationError) as blad:
        MemberProfileCreateRequest.model_validate({"name": "Zosia", "default_multiplier": "1.005"})

    assert "default_multiplier" in _fields(blad.value)


def test_mnoznik_nie_moze_przekroczyc_precyzji_kolumny() -> None:
    with pytest.raises(ValidationError):
        MemberProfileCreateRequest.model_validate({"name": "Zosia", "default_multiplier": "100.00"})


# --- cel kcal ----------------------------------------------------------------------


@pytest.mark.parametrize("wartosc", ["0", "-100"])
def test_cel_kcal_musi_byc_dodatni(wartosc: str) -> None:
    with pytest.raises(ValidationError) as blad:
        MemberProfileCreateRequest.model_validate({"name": "Zosia", "kcal_goal": wartosc})

    assert "kcal_goal" in _fields(blad.value)


def test_cel_kcal_bez_czesci_ulamkowej() -> None:
    """NUMERIC(6,0) — kalorie liczymy w pełnych jednostkach."""
    with pytest.raises(ValidationError):
        MemberProfileCreateRequest.model_validate({"name": "Zosia", "kcal_goal": "1800.5"})


def test_cel_kcal_moze_byc_pusty() -> None:
    assert MemberProfileCreateRequest(name="Zosia", kcal_goal=None).kcal_goal is None


# --- nazwy ---------------------------------------------------------------------------


@pytest.mark.parametrize("nazwa", ["", "   ", "\t\n"])
def test_profil_wymaga_niepustej_nazwy(nazwa: str) -> None:
    """Same białe znaki też są puste — schemat obcina je PRZED sprawdzeniem długości."""
    with pytest.raises(ValidationError) as blad:
        MemberProfileCreateRequest.model_validate({"name": nazwa})

    assert "name" in _fields(blad.value)


def test_nazwa_profilu_jest_obcinana_z_bialych_znakow() -> None:
    assert MemberProfileCreateRequest.model_validate({"name": "  Zosia  "}).name == "Zosia"


@pytest.mark.parametrize("nazwa", ["", "   "])
def test_rodzina_wymaga_niepustej_nazwy(nazwa: str) -> None:
    with pytest.raises(ValidationError):
        HouseholdCreateRequest.model_validate({"name": nazwa})


# --- edycja częściowa ------------------------------------------------------------------


def test_pusta_edycja_nie_zmienia_niczego() -> None:
    """Wszystkie pola opcjonalne: PATCH bez pól to poprawne żądanie bez skutku."""
    zmiana = MemberProfileUpdateRequest()

    assert zmiana.model_dump(exclude_unset=True) == {}


def test_edycja_waliduje_te_same_reguly_co_utworzenie() -> None:
    with pytest.raises(ValidationError) as blad:
        MemberProfileUpdateRequest.model_validate({"default_multiplier": "0"})

    assert "default_multiplier" in _fields(blad.value)


def test_jawny_null_celu_kcal_jest_zyczeniem_wyczyszczenia() -> None:
    """`kcal_goal` jest NULLABLE, więc `null` to poprawne wejście — i musi być
    odróżnialne od pominięcia pola."""
    zmiana = MemberProfileUpdateRequest.model_validate({"kcal_goal": None})

    assert zmiana.model_dump(exclude_unset=True) == {"kcal_goal": None}
    assert MemberProfileUpdateRequest().model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("pole", ["name", "default_multiplier", "is_active"])
def test_jawny_null_w_polu_not_null_jest_odrzucany(pole: str) -> None:
    """Bez tej reguły `{"name": null}` doszłoby do bazy i wysadziło zapis (500)."""
    with pytest.raises(ValidationError):
        MemberProfileUpdateRequest.model_validate({pole: None})


# --- skład rodziny ------------------------------------------------------------------


def test_pusty_sklad_oznacza_odpiecie_wszystkich() -> None:
    assert HouseholdMembersRequest().user_ids == []


def test_sklad_ma_gorny_limit_dlugosci() -> None:
    """Bez limitu jedno żądanie mogłoby przepisać wszystkie konta w instancji."""
    with pytest.raises(ValidationError):
        HouseholdMembersRequest.model_validate({"user_ids": list(range(101))})
