"""Schematy modułu planning (04_API §1-2): plan dnia, posiłki, pozycje, kopiowanie.

Zasady kontraktu:

- każda liczba NUMERIC wychodzi jako string dziesiętny (`DecimalString`, ADR-008),
- pole `nutrition` ma jeden kształt w całym API (`NutritionRead` z modułu
  nutrition) — wartości ZAWSZE liczy silnik, nigdy baza (02_DOMAIN §13.2),
- pozycja to przepis ALBO produkt luzem: pilnuje tego walidator schematu,
  a niezależnie od niego CHECK w bazie,
- ilość produktu luzem podaje się tak, jak w przepisie: `quantity` + `unit`
  (etykieta użytkownika); normalizację na g/ml/szt. robi serwis (ADR-005).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.core.schemas import DecimalString
from app.core.scope import Scope
from app.modules.catalog.units import AmountUnit
from app.modules.nutrition.schemas import GoalMetricRead, NutritionRead
from app.modules.nutrition.types import GoalStatus

__all__ = [
    "MEALS_PER_DAY_LIMIT",
    "DayGoalProgressRead",
    "DayRead",
    "DaysResponse",
    "FitToTargetResponse",
    "ItemCreateRequest",
    "ItemUpdateRequest",
    "MealCreateRequest",
    "MealRead",
    "MealUpdateRequest",
    "PlanCopyRequest",
    "PlanDayUpsertRequest",
    "PlanItemRead",
    "PlanServingSplitInput",
    "PlanServingSplitRead",
]

MealName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
DayTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
UnitLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

#: Mnożnik porcji — skala kolumny `plan_meal_items.servings` NUMERIC(6,2).
Servings = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("9999.99"), max_digits=6, decimal_places=2)
]
#: Mnożnik jednej osoby w rozkładzie rodzinnym — NUMERIC(4,2).
SplitMultiplier = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("99.99"), max_digits=4, decimal_places=2)
]
#: Ilość produktu luzem w jednostce użytkownika — jak `quantity` składnika przepisu.
ItemQuantity = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("99999.999"), max_digits=8, decimal_places=3)
]
#: Cel kcal posiłku — NUMERIC(6,0).
MealKcalTarget = Annotated[Decimal, Field(gt=Decimal("0"), le=Decimal("99999"), decimal_places=0)]
Position = Annotated[int, Field(ge=0, le=10_000)]

#: Sufit posiłków dnia i pozycji posiłku — plan dnia to plan, nie import danych.
MEALS_PER_DAY_LIMIT = 50
#: Ile dat naraz przyjmuje `/plan/copy` (miesiąc z zapasem).
COPY_TARGETS_LIMIT = 62


# --- rozkład rodzinny ---------------------------------------------------------------


class PlanServingSplitInput(BaseModel):
    """Jedna osoba w rozkładzie porcji. Suma multiplierów musi równać się `servings`."""

    member_profile_id: int = Field(ge=1)
    multiplier: SplitMultiplier


class PlanServingSplitRead(BaseModel):
    """Rozkład w odczycie — z imieniem profilu, żeby UI nie dociągał go osobno."""

    member_profile_id: int
    member_name: str
    multiplier: DecimalString


# --- pozycje ------------------------------------------------------------------------


class ItemCreateRequest(BaseModel):
    """Nowa pozycja posiłku: przepis z mnożnikiem ALBO produkt luzem z ilością."""

    recipe_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)
    #: Ilość produktu luzem w jednostce użytkownika (g/kg/ml/l/szt./jednostka domowa).
    quantity: ItemQuantity | None = None
    unit: UnitLabel | None = None
    servings: Servings = Decimal("1")
    servings_split: list[PlanServingSplitInput] = Field(default_factory=list, max_length=20)
    position: Position | None = None

    @model_validator(mode="after")
    def _recipe_xor_product(self) -> Self:
        if (self.recipe_id is None) == (self.product_id is None):
            raise ValueError("Pozycja planu wskazuje albo przepis, albo produkt — dokładnie jedno.")
        if self.product_id is not None and (self.quantity is None or self.unit is None):
            raise ValueError("Podaj ilość i jednostkę produktu.")
        if self.recipe_id is not None and (self.quantity is not None or self.unit is not None):
            raise ValueError("Pozycja z przepisem nie ma ilości — steruje nią mnożnik porcji.")
        return self


class ItemUpdateRequest(BaseModel):
    """Częściowa edycja pozycji. Pola pominięte zostają bez zmian.

    `servings_split` podane jawnie ZASTĘPUJE cały rozkład (pusta lista = brak
    rozkładu); pominięte zostawia go nietkniętym.
    """

    servings: Servings | None = None
    servings_split: list[PlanServingSplitInput] | None = Field(default=None, max_length=20)
    quantity: ItemQuantity | None = None
    unit: UnitLabel | None = None
    position: Position | None = None

    @model_validator(mode="after")
    def _amount_needs_both_parts(self) -> Self:
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("Zmiana ilości wymaga podania i liczby, i jednostki.")
        return self


class PlanItemRead(BaseModel):
    """Pozycja posiłku z wartościami policzonymi przez silnik."""

    id: int
    position: int
    recipe_id: int | None
    recipe_name: str | None
    recipe_photo_thumb_url: str | None
    product_id: int | None
    product_name: str | None
    amount: DecimalString | None
    amount_unit: AmountUnit | None
    servings: DecimalString
    servings_split: list[PlanServingSplitRead]
    nutrition: NutritionRead


# --- posiłki ------------------------------------------------------------------------


class MealCreateRequest(BaseModel):
    """Nowy posiłek dnia — nazwa własna (02_DOMAIN §7), opcjonalny cel kcal."""

    name: MealName
    kcal_target: MealKcalTarget | None = None
    position: Position | None = None


class MealUpdateRequest(BaseModel):
    """Częściowa edycja posiłku. `kcal_target` można wyzerować, podając `null`."""

    name: MealName | None = None
    kcal_target: MealKcalTarget | None = None
    position: Position | None = None
    #: Jawne „usuń cel" — bez tego `null` nie odróżniłby się od „nie ruszaj".
    clear_kcal_target: bool = False


class MealRead(BaseModel):
    """Posiłek z pozycjami, sumą wartości i statusem względem własnego celu kcal."""

    id: int
    name: str
    position: int
    kcal_target: DecimalString | None
    kcal_status: GoalStatus | None
    items: list[PlanItemRead]
    nutrition: NutritionRead


# --- dzień --------------------------------------------------------------------------


class PlanDayUpsertRequest(BaseModel):
    """PUT dnia: tworzy go albo aktualizuje tytuł i widoczność (04_API §2)."""

    title: DayTitle | None = None
    scope: Scope = Scope.PRIVATE


class DayGoalProgressRead(BaseModel):
    """Cztery kafelki widoku 1: wartość/cel/delta/status dla kcal i makro."""

    kcal: GoalMetricRead
    protein_g: GoalMetricRead
    fat_g: GoalMetricRead
    carbs_g: GoalMetricRead


class DayRead(BaseModel):
    """Dzień planu razem z posiłkami, wartościami i postępem względem celu.

    `id` jest `null` dla dnia, którego jeszcze nie ma w bazie: otwarcie pustej
    daty to normalna sytuacja, nie błąd 404 (dzień powstaje przy pierwszym
    posiłku albo przez PUT).
    """

    id: int | None
    day: date
    title: str | None
    scope: Scope
    owner_user_id: int | None
    meals: list[MealRead]
    nutrition: NutritionRead
    goal_progress: DayGoalProgressRead
    #: Data obowiązywania celu użytego do statusów (`null`, gdy celu brak).
    goal_valid_from: date | None
    created_at: datetime | None
    updated_at: datetime | None


class DaysResponse(BaseModel):
    """Dni z zakresu `from`-`to`. Zwracane są WYŁĄCZNIE dni istniejące w bazie."""

    items: list[DayRead]
    total: int


# --- akcje ---------------------------------------------------------------------------


class FitToTargetResponse(BaseModel):
    """Propozycja „dopasuj porcję do celu" — sama propozycja, bez zapisu.

    Zastosowanie jest osobną, jawną akcją użytkownika (`PATCH` pozycji) —
    nic nie zmienia się samo (02_DOMAIN §6).
    """

    item_id: int
    #: Cel kcal posiłku, względem którego liczono propozycję.
    target_kcal: DecimalString
    current_servings: DecimalString
    proposed_servings: DecimalString
    #: Wartości pozycji PO zastosowaniu propozycji (zaokrąglone na wyjściu).
    resulting_nutrition: NutritionRead


class PlanCopyRequest(BaseModel):
    """Kopiowanie dnia na datę/daty albo posiłku do dnia (04_API §2).

    Kopia jest GŁĘBOKA (nowe id posiłków, pozycji i rozkładów) i DOPISUJE się
    do dnia docelowego — istniejących posiłków nie nadpisuje (karta B06).
    """

    what: Literal["day", "meal"]
    #: Wymagane dla `what="day"` — data dnia źródłowego.
    source_date: date | None = None
    #: Wymagane dla `what="meal"` — identyfikator kopiowanego posiłku.
    source_meal_id: int | None = Field(default=None, ge=1)
    target_dates: list[date] = Field(min_length=1, max_length=COPY_TARGETS_LIMIT)

    @model_validator(mode="after")
    def _source_matches_kind(self) -> Self:
        if self.what == "day" and self.source_date is None:
            raise ValueError("Podaj datę dnia, który chcesz skopiować.")
        if self.what == "meal" and self.source_meal_id is None:
            raise ValueError("Podaj posiłek, który chcesz skopiować.")
        return self
