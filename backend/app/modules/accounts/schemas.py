"""Schematy request/response modułu accounts (04_API §1 i §2).

Modele ORM nigdy nie wychodzą na zewnątrz — tu jest granica kontraktu, z
której `task fe-types` generuje typy dla frontendu.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.modules.accounts.models import UserRole
from app.modules.households.schemas import HouseholdSummary

#: Górny limit długości hasła — argon2 nie ma limitu, ale nieograniczone
#: wejście to darmowy DoS (hash liczy się tym dłużej, im dłuższe hasło).
MAX_PASSWORD_LENGTH = 200

PasswordField = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    """Dane logowania. Hasło bez dolnego limitu — złe dane to 401, nie 422."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class CurrentUser(BaseModel):
    """Odpowiedź `GET /auth/me` — to, co frontend wie o zalogowanym użytkowniku.

    `email` jako zwykły `str` (nie `EmailStr`) świadomie: walidacja adresu
    należy do wejścia. Gdyby reguły `email-validator` się zaostrzyły, wiersz
    zapisany wcześniej wysadzałby ODCZYT (500) zamiast po prostu się wyświetlić.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: UserRole
    ui_settings: dict[str, object]
    #: Rodzina użytkownika albo `null` — brak rodziny to legalny stan (ADR-006).
    household: HouseholdSummary | None = None


class UserRead(BaseModel):
    """Konto widziane przez ADMIN-a (bez hasha hasła — ten nie opuszcza serwera)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    #: Jak w `CurrentUser` — odczyt nie waliduje adresu ponownie.
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Lista kont z paginacją (04_API §1)."""

    items: list[UserRead]
    total: int


class UserCreateRequest(BaseModel):
    """Utworzenie konta przez ADMIN-a (samorejestracji nie ma — ADR-003)."""

    email: EmailStr
    password: str = PasswordField
    display_name: str = Field(min_length=1, max_length=200)
    role: UserRole = UserRole.USER
    is_active: bool = True


class NutritionThresholdsPayload(BaseModel):
    """Progi statusów żywieniowych w PROCENTACH celu (D9: domyślnie 90 i 110).

    Walidacja `0 < low < high` jest tu, a nie w silniku: silnik dostaje progi
    już poprawne, a użytkownik ma zobaczyć czytelny komunikat przy formularzu.
    """

    low: int = Field(ge=1, le=1000)
    high: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def _low_below_high(self) -> Self:
        if self.low >= self.high:
            raise ValueError("Próg „za mało” musi być mniejszy od progu „za dużo”.")
        return self


class UiSettingsPatchRequest(BaseModel):
    """Częściowa zmiana ustawień UI zalogowanego użytkownika (04_API §2).

    Pola pominięte zostają bez zmian. Dziś jedynym kluczem są progi statusów;
    kolejne preferencje widoku dokładają następne batche — kształt jest
    świadomie rozszerzalny, bo `users.ui_settings` to JSONB (03_DATABASE §2).
    """

    nutrition_thresholds: NutritionThresholdsPayload | None = None


class UserUpdateRequest(BaseModel):
    """Częściowa edycja konta. Pola pominięte pozostają bez zmian."""

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(
        default=None, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )
