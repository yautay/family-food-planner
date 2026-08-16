"""Konfiguracja aplikacji — czytanie env i zachowanie przy brakach."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import ConfigurationError, load_settings

pytestmark = pytest.mark.unit


def test_czyta_wymagane_zmienne_ze_srodowiska(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE_URL i SECRET_KEY pochodzą wyłącznie ze środowiska."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/ffp")
    monkeypatch.setenv("SECRET_KEY", "sekret-z-env")

    settings = load_settings()

    assert settings.database_url == "postgresql+psycopg://u:p@localhost:5432/ffp"
    assert settings.secret_key == "sekret-z-env"


def test_ma_bezpieczne_wartosci_domyslne(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Zmienne opcjonalne mają wartości domyślne — dev startuje bez pełnego .env."""
    # Katalog bez .env i czyste środowisko — inaczej test sprawdzałby zawartość
    # lokalnego pliku, a nie wartości domyślne w kodzie.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/ffp")
    monkeypatch.setenv("SECRET_KEY", "sekret")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = load_settings()

    assert settings.app_env == "dev"
    assert settings.app_version == "0.1.0"
    assert settings.log_level == "INFO"


def test_brak_wymaganych_zmiennych_wybucha_czytelnie(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Komunikat po polsku wymienia BRAKUJĄCE zmienne i podpowiada .env.example."""
    # Katalog bez .env — inaczej Settings dociągnąłby wartości z pliku repo.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    message = str(excinfo.value)
    assert "DATABASE_URL" in message
    assert "SECRET_KEY" in message
    assert ".env.example" in message


def test_odrzuca_nieznane_srodowisko(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """APP_ENV spoza dev/test/prod to błąd konfiguracji, nie cicha akceptacja."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/ffp")
    monkeypatch.setenv("SECRET_KEY", "sekret")
    monkeypatch.setenv("APP_ENV", "produkcja")

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    assert "app_env" in str(excinfo.value).lower()
