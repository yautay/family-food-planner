"""Reguły rozkładu rodzinnego — czyste funkcje serwisu planning (08_TESTING §2.2).

Testy pracują na strukturach, bez bazy: sprawdzana jest sama arytmetyka sumy
mnożników, która decyduje o przyjęciu albo odrzuceniu zapisu (422).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.planning.service import (
    PlanValidationError,
    assert_split_matches_servings,
    assert_unique_profiles,
)

pytestmark = pytest.mark.unit


#: Przykład z 02_DOMAIN §7: 2x1,0 + 2x0,8 + 2x1,3 = 6,2 porcji.
#: (Dokument miał w tym miejscu „3x1,0", co daje 7,2 — literówka poprawiona
#: w B06 razem z tym testem; sama REGUŁA „suma = servings" jest bez zmian.)
DOMAIN_EXAMPLE = [Decimal("1.0")] * 2 + [Decimal("0.8")] * 2 + [Decimal("1.3")] * 2


def test_przyklad_z_dokumentu_domenowego_sumuje_sie_do_6_2() -> None:
    """Rozkład rodzinny 2x1,0 + 2x0,8 + 2x1,3 przechodzi przy servings 6,2."""
    assert_split_matches_servings(DOMAIN_EXAMPLE, Decimal("6.2"))


def test_suma_liczona_jest_na_decimal_a_nie_na_float() -> None:
    """Trzy osoby po 1,1 porcji to dokładnie 3,3 — na floatach 3,3000000000000003.

    Gdyby walidacja liczyła na floatach, ten poprawny rozkład zostałby odrzucony
    (ADR-008: `Decimal` end-to-end nie jest formalnością).
    """
    multipliers = [Decimal("1.1")] * 3

    assert_split_matches_servings(multipliers, Decimal("3.3"))
    assert sum(float(value) for value in multipliers) != 3.3


def test_rozne_zapisy_tej_samej_liczby_sa_rowne() -> None:
    """`6.20` z kolumny NUMERIC(6,2) i `6.2` z wejścia to ta sama wartość."""
    assert_split_matches_servings([Decimal("6.20")], Decimal("6.2"))


def test_niezgodna_suma_konczy_sie_bledem_422_z_liczbami_w_komunikacie() -> None:
    """Rozkład 2,0 przy 3 porcjach to 422 — z podaniem oczekiwanej i faktycznej sumy."""
    with pytest.raises(PlanValidationError) as error:
        assert_split_matches_servings([Decimal("1.0"), Decimal("1.0")], Decimal("3"))

    assert error.value.status_code == 422
    assert error.value.details == {"expected": "3", "actual": "2.0"}


def test_pusty_rozklad_przy_niezerowych_porcjach_jest_bledem() -> None:
    """Wywołanie z pustą listą oznacza „rozkład istnieje, ale nic nie zawiera"."""
    with pytest.raises(PlanValidationError):
        assert_split_matches_servings([], Decimal("1"))


def test_ten_sam_profil_dwa_razy_jest_odrzucany() -> None:
    """Duplikat profilu w rozkładzie łamie UNIQUE i myli sumę — 422 przed zapisem."""
    with pytest.raises(PlanValidationError):
        assert_unique_profiles([7, 7])


def test_rozne_profile_przechodza() -> None:
    assert_unique_profiles([7, 8, 9])
