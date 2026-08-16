"""Prymitywy bezpieczeństwa: hasła, tokeny, czas życia sesji, blokada konta.

Zasada z 07_SECURITY: żadnej własnej kryptografii — wyłącznie `argon2-cffi`,
`secrets` i `hmac`. Ten moduł jest czysty (bez I/O i bez zależności od bazy),
więc reguły blokady i wygasania sesji da się testować jednostkowo; stanem
zarządza `app.modules.accounts.service`.

Parametry (argon2 domyślne, TTL sesji, próg blokady) wracają do przeglądu
w BATCH_17 (hardening).
"""

from __future__ import annotations

import contextlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

#: Długość losowych identyfikatorów w bajtach — 256 bitów (07_SECURITY §2 i §5).
TOKEN_BYTES = 32

#: Cookie z id sesji — HttpOnly, nieczytelne dla JS.
SESSION_COOKIE_NAME = "ffp_session"
#: Cookie CSRF — celowo BEZ HttpOnly: frontend musi je przepisać do nagłówka.
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

#: Minimalna długość hasła (07_SECURITY §2).
MIN_PASSWORD_LENGTH = 10

#: Sesja żyje 30 dni od ostatniego użycia (TTL przesuwne, ADR-003).
SESSION_TTL = timedelta(days=30)

#: Przesunięcie `expires_at` dopiero, gdy sesja „zestarzała się" o ten okres —
#: bez tego każdy request zapisywałby wiersz sesji.
SESSION_REFRESH_AFTER = timedelta(days=1)

#: Po tylu nieudanych logowaniach konto jest blokowane…
MAX_FAILED_LOGINS = 10
#: …na taki czas (07_SECURITY §2).
ACCOUNT_LOCK_DURATION = timedelta(minutes=15)

_hasher = PasswordHasher()


def utcnow() -> datetime:
    """Teraz w UTC — jedno źródło czasu dla sesji i blokad."""
    return datetime.now(UTC)


# --- hasła -------------------------------------------------------------------


@dataclass(frozen=True)
class PasswordCheck:
    """Wynik weryfikacji hasła; `new_hash` != None ⇒ zapisz odświeżony hash."""

    valid: bool
    new_hash: str | None = None


def hash_password(password: str) -> str:
    """Zahashuj hasło argon2id (parametry domyślne biblioteki)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> PasswordCheck:
    """Sprawdź hasło; przy podbitych parametrach argon2 zwróć hash do zapisania.

    Rehash przy logowaniu to jedyny moment, w którym znamy hasło jawne —
    stąd wymóg z 07_SECURITY §2.
    """
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return PasswordCheck(valid=False)

    if _hasher.check_needs_rehash(password_hash):
        return PasswordCheck(valid=True, new_hash=hash_password(password))
    return PasswordCheck(valid=True)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Hash losowego sekretu — nigdy nie pasuje do żadnego hasła."""
    return hash_password(secrets.token_urlsafe(TOKEN_BYTES))


def burn_password_time(password: str) -> None:
    """Wykonaj weryfikację „na pusto" dla nieistniejącego/nieaktywnego konta.

    Bez tego czas odpowiedzi zdradza, czy email istnieje w bazie
    (enumeracja kont — 07_SECURITY §1).
    """
    with contextlib.suppress(VerifyMismatchError, VerificationError, InvalidHashError):
        _hasher.verify(_dummy_hash(), password)


# --- tokeny ------------------------------------------------------------------


def generate_token() -> str:
    """Losowy token URL-safe (256 bitów): id sesji, token CSRF, tokeny publiczne."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def tokens_match(left: str | None, right: str | None) -> bool:
    """Porównanie tokenów stałe czasowo; brak którejkolwiek wartości = brak zgody."""
    if not left or not right:
        return False
    return hmac.compare_digest(left, right)


# --- czas życia sesji --------------------------------------------------------


def session_expires_at(now: datetime) -> datetime:
    """Moment wygaśnięcia sesji tworzonej lub odświeżanej teraz."""
    return now + SESSION_TTL


def session_is_expired(expires_at: datetime, now: datetime) -> bool:
    """Sesja wygasła, gdy `expires_at` już minął (równość = wygasła)."""
    return expires_at <= now


def session_needs_refresh(expires_at: datetime, now: datetime) -> bool:
    """Czy przesunąć `expires_at` (TTL przesuwne) — patrz `SESSION_REFRESH_AFTER`."""
    return session_expires_at(now) - expires_at >= SESSION_REFRESH_AFTER


# --- blokada konta po serii nieudanych logowań --------------------------------


@dataclass(frozen=True)
class LockoutState:
    """Licznik porażek i termin końca blokady (trzymane w wierszu `users`)."""

    failed_count: int = 0
    locked_until: datetime | None = None


def is_locked(state: LockoutState, now: datetime) -> bool:
    """Czy konto jest w tej chwili zablokowane."""
    return state.locked_until is not None and state.locked_until > now


def register_failure(state: LockoutState, now: datetime) -> LockoutState:
    """Nieudane logowanie: zwiększ licznik, po progu ustaw blokadę i wyzeruj licznik."""
    failed = state.failed_count + 1
    if failed >= MAX_FAILED_LOGINS:
        return LockoutState(failed_count=0, locked_until=now + ACCOUNT_LOCK_DURATION)
    return LockoutState(failed_count=failed, locked_until=state.locked_until)


def register_success() -> LockoutState:
    """Udane logowanie kasuje zarówno licznik, jak i blokadę."""
    return LockoutState()
