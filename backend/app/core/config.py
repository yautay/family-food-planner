"""Konfiguracja aplikacji — JEDYNE źródło ustawień (07_SECURITY §7).

Wszystko wyłącznie ze zmiennych środowiskowych. Żadna wartość różnicująca
dev od prod nie może być zaszyta w kodzie. Nowa zmienna = wpis w
`.env.example` w tym samym commicie.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "prod"]


class ConfigurationError(RuntimeError):
    """Konfiguracja jest niekompletna lub niepoprawna — start aplikacji nie ma sensu."""


class Settings(BaseSettings):
    """Ustawienia ze środowiska; nazwa pola = nazwa zmiennej (wielkość liter bez znaczenia)."""

    model_config = SettingsConfigDict(
        # Zmienne procesu mają pierwszeństwo (compose, CI). Plik .env czytany
        # zarówno z katalogu backend/, jak i z korzenia repo — jeden plik na projekt.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Wymagane — brak = czytelny błąd startu.
    database_url: str
    secret_key: str

    # Opcjonalne, z bezpiecznymi wartościami domyślnymi.
    app_env: AppEnv = "dev"
    app_version: str = "0.1.0"
    log_level: str = "INFO"


def _format_missing(exc: ValidationError) -> str:
    missing = sorted(
        str(error["loc"][0]).upper() for error in exc.errors() if error["type"] == "missing"
    )
    if missing:
        return (
            "Brak wymaganych zmiennych środowiskowych: "
            + ", ".join(missing)
            + ". Skopiuj .env.example do .env i uzupełnij wartości."
        )
    details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return f"Niepoprawna konfiguracja środowiska: {details}"


def load_settings() -> Settings:
    """Zbuduj ustawienia; przy braku wymaganych zmiennych rzuć czytelny błąd po polsku."""
    try:
        return Settings()  # type: ignore[call-arg]  # wartości pochodzą ze środowiska
    except ValidationError as exc:
        raise ConfigurationError(_format_missing(exc)) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ustawienia procesu (cache) — używać w dependency FastAPI i w app factory."""
    return load_settings()
