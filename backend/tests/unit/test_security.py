"""Prymitywy bezpieczeństwa: hasła argon2id, tokeny, TTL sesji, blokada konta."""

from __future__ import annotations

from datetime import timedelta

import pytest
from argon2 import PasswordHasher

from app.core import security
from app.core.security import (
    ACCOUNT_LOCK_DURATION,
    MAX_FAILED_LOGINS,
    SESSION_TTL,
    LockoutState,
    generate_token,
    hash_password,
    is_locked,
    register_failure,
    register_success,
    session_expires_at,
    session_is_expired,
    session_needs_refresh,
    tokens_match,
    utcnow,
    verify_password,
)

pytestmark = pytest.mark.unit

PASSWORD = "haslo-testowe-2026"


def test_hash_jest_argon2id_i_nie_zawiera_hasla() -> None:
    """Hash musi być argon2id (07_SECURITY §2) i nie może ujawniać hasła."""
    digest = hash_password(PASSWORD)

    assert digest.startswith("$argon2id$")
    assert PASSWORD not in digest


def test_ten_sam_lancuch_daje_rozne_hashe() -> None:
    """Losowa sól — dwa hashe tego samego hasła nie są identyczne."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_weryfikacja_akceptuje_poprawne_haslo() -> None:
    check = verify_password(hash_password(PASSWORD), PASSWORD)

    assert check.valid is True
    assert check.new_hash is None


@pytest.mark.parametrize("wrong", ["haslo-testowe-2027", "", "HASLO-TESTOWE-2026"])
def test_weryfikacja_odrzuca_bledne_haslo(wrong: str) -> None:
    check = verify_password(hash_password(PASSWORD), wrong)

    assert check.valid is False
    assert check.new_hash is None


def test_uszkodzony_hash_nie_wysadza_weryfikacji() -> None:
    """Wiersz z popsutym hashem (np. po ręcznej edycji) daje odmowę, nie 500."""
    assert verify_password("to-nie-jest-hash", PASSWORD).valid is False


def test_rehash_po_podbiciu_parametrow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Po zaostrzeniu parametrów logowanie zwraca hash do zapisania (07_SECURITY §2)."""
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    monkeypatch.setattr(security, "_hasher", weak)
    old_hash = weak.hash(PASSWORD)

    monkeypatch.setattr(security, "_hasher", PasswordHasher())
    check = verify_password(old_hash, PASSWORD)

    assert check.valid is True
    assert check.new_hash is not None
    assert check.new_hash != old_hash
    assert verify_password(check.new_hash, PASSWORD).valid is True


def test_burn_password_time_nigdy_nie_rzuca() -> None:
    """Ścieżka „nie ma takiego konta" nie może różnić się wyjątkiem."""
    security.burn_password_time("cokolwiek")


# --- tokeny -------------------------------------------------------------------


def test_token_ma_256_bitow_entropii_i_jest_urlsafe() -> None:
    """43 znaki base64url = 32 bajty losowości (07_SECURITY §2)."""
    token = generate_token()

    assert len(token) == 43
    assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_kolejne_tokeny_sa_rozne() -> None:
    assert len({generate_token() for _ in range(50)}) == 50


def test_porownanie_tokenow_csrf() -> None:
    """Double-submit: zgodne tokeny przechodzą, wszystko inne nie."""
    token = generate_token()

    assert tokens_match(token, token) is True
    assert tokens_match(token, generate_token()) is False
    assert tokens_match(token, token + "x") is False


@pytest.mark.parametrize(("left", "right"), [(None, "x"), ("x", None), (None, None), ("", "")])
def test_brak_tokenu_nie_jest_zgodnoscia(left: str | None, right: str | None) -> None:
    """Pusty cookie i pusty nagłówek nie mogą „pasować do siebie"."""
    assert tokens_match(left, right) is False


# --- czas życia sesji ---------------------------------------------------------


def test_nowa_sesja_wygasa_po_ttl() -> None:
    now = utcnow()

    assert session_expires_at(now) - now == SESSION_TTL


def test_sesja_wygasla_i_swieza() -> None:
    now = utcnow()

    assert session_is_expired(now - timedelta(seconds=1), now) is True
    assert session_is_expired(now, now) is True, "równość traktujemy jako wygaśnięcie"
    assert session_is_expired(now + timedelta(seconds=1), now) is False


def test_ttl_przesuwa_sie_dopiero_po_dobie() -> None:
    """Zapis wiersza sesji przy każdym requeście byłby marnotrawstwem."""
    now = utcnow()
    swiezo_odswiezona = session_expires_at(now) - timedelta(hours=1)
    stara = session_expires_at(now) - timedelta(days=2)

    assert session_needs_refresh(swiezo_odswiezona, now) is False
    assert session_needs_refresh(stara, now) is True


# --- blokada konta ------------------------------------------------------------


def test_kolejne_porazki_zwiekszaja_licznik() -> None:
    now = utcnow()
    state = LockoutState()

    for expected in range(1, MAX_FAILED_LOGINS):
        state = register_failure(state, now)
        assert state.failed_count == expected
        assert is_locked(state, now) is False


def test_dziesiata_porazka_blokuje_konto_na_15_minut() -> None:
    """07_SECURITY §2: 10 nieudanych prób = blokada konta na 15 minut."""
    now = utcnow()
    state = LockoutState()

    for _ in range(MAX_FAILED_LOGINS):
        state = register_failure(state, now)

    assert is_locked(state, now) is True
    assert state.locked_until == now + ACCOUNT_LOCK_DURATION
    assert state.failed_count == 0, "po nałożeniu blokady licznik startuje od zera"


def test_blokada_wygasa_po_czasie() -> None:
    now = utcnow()
    state = LockoutState(failed_count=0, locked_until=now + ACCOUNT_LOCK_DURATION)

    assert is_locked(state, now + ACCOUNT_LOCK_DURATION - timedelta(seconds=1)) is True
    assert is_locked(state, now + ACCOUNT_LOCK_DURATION) is False


def test_udane_logowanie_kasuje_licznik_i_blokade() -> None:
    assert register_success() == LockoutState(failed_count=0, locked_until=None)


def test_brak_blokady_dla_swiezego_konta() -> None:
    assert is_locked(LockoutState(), utcnow()) is False
