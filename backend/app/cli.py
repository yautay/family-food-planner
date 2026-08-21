"""CLI administracyjne backendu — uruchamiane przez `task create-admin`.

Pierwszy administrator powstaje TYLKO tutaj: hasło podaje człowiek (prompt
albo zmienna środowiskowa), nigdy seed ani kod w repozytorium (07_SECURITY §2,
lekcja netQArnera). Skrypt jest idempotentny: zajęty email = komunikat, nie
awaria.

Użycie:
    task create-admin
    FFP_ADMIN_EMAIL=... FFP_ADMIN_PASSWORD=... task create-admin
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import ConfigurationError, get_settings
from app.core.db import get_session_factory, selector_loop_factory
from app.core.errors import AppError
from app.core.security import MIN_PASSWORD_LENGTH

# Rejestr modeli MUSI być zaimportowany, choć nic z niego tu nie wołamy:
# CLI omija `create_app()`, które ładuje wszystkie moduły przez routery, więc bez
# tej linii `Base.registry` zna tylko `User`. Relacja `User.household` jest
# adnotowana stringiem (`from __future__ import annotations`), więc SQLAlchemy
# szuka klasy `Household` w rejestrze i wywala `InvalidRequestError: expression
# 'Household' failed to locate a name` przy PIERWSZYM zapytaniu o użytkownika.
# Ten sam wzorzec stosuje `migrations/env.py` (CLAUDE.md §4: rejestr modeli).
from app.models import Base  # noqa: F401
from app.modules.accounts.models import UserRole
from app.modules.accounts.service import AccountsService

ENV_EMAIL = "FFP_ADMIN_EMAIL"
ENV_PASSWORD = "FFP_ADMIN_PASSWORD"
ENV_DISPLAY_NAME = "FFP_ADMIN_DISPLAY_NAME"


class CliError(RuntimeError):
    """Błąd obsługi CLI — komunikat po polsku, bez stacktrace'u dla użytkownika."""


def _prompt_email() -> str:
    """Email walidowany TĄ SAMĄ regułą co API — inaczej dałoby się założyć konto,
    którym nie da się zalogować (`EmailStr` odrzuca np. domeny `.test`)."""
    email = (os.environ.get(ENV_EMAIL) or input("Adres e-mail administratora: ")).strip()
    try:
        return str(TypeAdapter(EmailStr).validate_python(email))
    except ValidationError as exc:
        raise CliError(f"Podaj poprawny adres e-mail (podano: {email!r}).") from exc


def _prompt_password() -> str:
    """Hasło ze zmiennej środowiskowej albo z ukrytego promptu (dwukrotnie)."""
    from_env = os.environ.get(ENV_PASSWORD)
    if from_env:
        password = from_env
    else:
        if not sys.stdin.isatty():
            raise CliError(
                "Brak terminala interaktywnego. Podaj hasło zmienną "
                f"{ENV_PASSWORD} albo uruchom komendę w terminalu."
            )
        password = getpass.getpass("Hasło (min. 10 znaków): ")
        if password != getpass.getpass("Powtórz hasło: "):
            raise CliError("Hasła nie są identyczne.")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise CliError(f"Hasło musi mieć co najmniej {MIN_PASSWORD_LENGTH} znaków.")
    return password


async def _create_admin(email: str, password: str, display_name: str) -> str:
    factory = get_session_factory()
    async with factory() as session:
        service = AccountsService(session)
        user = await service.create_user(
            email=email,
            password=password,
            display_name=display_name,
            role=UserRole.ADMIN,
            is_active=True,
        )
        return f"Utworzono konto administratora: {user.email} (id {user.id})."


def create_admin_command() -> int:
    """Interaktywne utworzenie konta ADMIN. Zwraca kod wyjścia procesu."""
    email = _prompt_email()
    display_name = os.environ.get(ENV_DISPLAY_NAME, "").strip() or email.split("@")[0]
    password = _prompt_password()

    try:
        # loop_factory: na Windows psycopg async wymaga SelectorEventLoop.
        message = asyncio.run(
            _create_admin(email, password, display_name),
            loop_factory=selector_loop_factory(),
        )
    except AppError as exc:
        # Zajęty email (409) — powtórne uruchomienie ma być bezpieczne.
        print(exc.message)
        return 0
    print(message)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Punkt wejścia `python -m app.cli`."""
    parser = argparse.ArgumentParser(prog="app.cli", description="Narzędzia administracyjne FFP")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin", help="Tworzy konto administratora")

    args = parser.parse_args(argv)
    try:
        get_settings()  # czytelny błąd, gdy brakuje DATABASE_URL/SECRET_KEY
        if args.command == "create-admin":
            return create_admin_command()
    except (CliError, ConfigurationError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nPrzerwano.", file=sys.stderr)
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
