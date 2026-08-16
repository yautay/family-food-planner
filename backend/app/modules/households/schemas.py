"""Schematy request/response modułu households (04_API §1 i §2).

`default_multiplier` i `kcal_goal` wychodzą jako stringi dziesiętne
(`DecimalString`, ADR-008) — frontend parsuje je parserem dziesiętnym, nigdy
przez `Number()`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.schemas import DecimalString
from app.modules.accounts.models import UserRole

#: Mnożnik porcji: NUMERIC(4,2), zawsze dodatni (0 porcji to usunięcie pozycji,
#: a nie profil); górna granica wynika z precyzji kolumny.
Multiplier = Annotated[
    Decimal,
    Field(gt=Decimal("0"), le=Decimal("99.99"), max_digits=4, decimal_places=2),
]
#: Dzienny cel kcal: NUMERIC(6,0), dodatni, bez części ułamkowej.
KcalGoal = Annotated[
    Decimal,
    Field(gt=Decimal("0"), le=Decimal("999999"), max_digits=6, decimal_places=0),
]

#: Nazwa rodziny/profilu: obcinana z białych znaków PRZED sprawdzeniem długości,
#: więc `"   "` jest odrzucane, a nie zapisywane jako pusty string.
NonEmptyName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class HouseholdSummary(BaseModel):
    """Rodzina w skrócie — tyle o niej wie sesja (`GET /auth/me`)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class HouseholdMember(BaseModel):
    """Konto należące do rodziny.

    `email` jako zwykły `str` (nie `EmailStr`) — jak w `UserRead`: walidacja
    adresu należy do wejścia, odczyt nie może się wywalić na starszym wierszu.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: UserRole
    is_active: bool


class MemberProfileRead(BaseModel):
    """Profil członka rodziny (może istnieć bez konta — 02_DOMAIN §3)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    household_id: int | None
    owner_user_id: int | None
    name: str
    default_multiplier: DecimalString
    kcal_goal: DecimalString | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MemberProfileListResponse(BaseModel):
    """Lista profili z paginacją (04_API §1)."""

    items: list[MemberProfileRead]
    total: int


class MemberProfileCreateRequest(BaseModel):
    """Nowy profil w rodzinie zalogowanego użytkownika."""

    name: NonEmptyName
    default_multiplier: Multiplier = Decimal("1.00")
    kcal_goal: KcalGoal | None = None
    is_active: bool = True


#: Pola, dla których `null` w PATCH-u znaczy „wyczyść wartość". Pozostałe są
#: w bazie NOT NULL, więc `null` jest dla nich błędem wejścia, a nie życzeniem.
NULLABLE_ON_UPDATE = frozenset({"kcal_goal"})


class MemberProfileUpdateRequest(BaseModel):
    """Częściowa edycja profilu.

    Pole POMINIĘTE zostaje bez zmian, a `kcal_goal: null` **czyści** cel —
    rozróżnienie robi `model_fields_set` po stronie routera, bo samo `None`
    nie niesie tej informacji.
    """

    name: NonEmptyName | None = None
    default_multiplier: Multiplier | None = None
    kcal_goal: KcalGoal | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> MemberProfileUpdateRequest:
        """`null` wolno przysłać wyłącznie dla kolumn NULLABLE.

        Bez tego `{"name": null}` przeszłoby walidację i wysadziło zapis
        naruszeniem NOT NULL — użytkownik dostałby 500 zamiast czytelnego 422.
        """
        empty = sorted(
            field
            for field in self.model_fields_set
            if field not in NULLABLE_ON_UPDATE and getattr(self, field) is None
        )
        if empty:
            raise ValueError(f"Te pola nie mogą być puste: {', '.join(empty)}.")
        return self


class MyHouseholdResponse(BaseModel):
    """`GET /households/my` — brak rodziny to legalny stan, a nie 404."""

    household: HouseholdSummary | None
    members: list[HouseholdMember]
    profiles: list[MemberProfileRead]


class HouseholdRead(BaseModel):
    """Rodzina na liście administratora (z licznikami, żeby lista miała treść)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    members_count: int
    profiles_count: int


class HouseholdDetail(HouseholdRead):
    """Szczegóły rodziny: konta i profile członków."""

    members: list[HouseholdMember]
    profiles: list[MemberProfileRead]


class HouseholdListResponse(BaseModel):
    """Lista rodzin z paginacją (04_API §1)."""

    items: list[HouseholdRead]
    total: int


class HouseholdCreateRequest(BaseModel):
    """Utworzenie rodziny (wyłącznie ADMIN — 02_DOMAIN §3)."""

    name: NonEmptyName


class HouseholdUpdateRequest(BaseModel):
    """Zmiana nazwy rodziny."""

    name: NonEmptyName | None = None


class HouseholdMembersRequest(BaseModel):
    """Pełna podmiana składu rodziny: konta spoza listy zostają odpięte."""

    user_ids: list[int] = Field(default_factory=list, max_length=100)
