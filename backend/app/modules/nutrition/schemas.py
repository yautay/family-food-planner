"""Schematy modułu nutrition: kontrakt pola `nutrition` (04_API §1) i cele.

`NutritionRead` mieszka TUTAJ, a nie w module przepisów, bo kształt wyniku
obliczeń należy do domeny żywienia — konsumują go przepisy (B05), plan dnia
(B06), szablony (B07) i statystyki (B13). Jedna definicja = jeden komponent
w OpenAPI = jeden typ w `generated.ts`.

Wszystkie liczby wychodzą jako stringi dziesiętne (`DecimalString`, ADR-008).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import DecimalString
from app.modules.nutrition.types import GoalStatus, NutritionValues

__all__ = [
    "GoalListResponse",
    "GoalMetricRead",
    "GoalPayload",
    "GoalRead",
    "NutritionRead",
    "nutrition_read",
]

#: Dzienny cel kcal — NUMERIC(6,0), zawsze dodatni (02_DOMAIN §6).
GoalKcal = Annotated[Decimal, Field(gt=Decimal("0"), le=Decimal("99999"), decimal_places=0)]
#: Cel makroskładnika — NUMERIC(6,1), opcjonalny i nieujemny.
GoalMacro = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("99999.9"), decimal_places=1)]


class NutritionRead(BaseModel):
    """Wartości wyliczone przez silnik — nigdy przechowywane (02_DOMAIN §13.2)."""

    kcal: DecimalString
    protein_g: DecimalString
    fat_g: DecimalString
    carbs_g: DecimalString
    fiber_g: DecimalString
    sugars_g: DecimalString
    glycemic_load: DecimalString
    complete: bool
    missing: list[str]


def nutrition_read(values: NutritionValues) -> NutritionRead:
    """`NutritionValues` z silnika → schemat odpowiedzi (jedno miejsce mapowania)."""
    return NutritionRead(
        kcal=values.kcal,
        protein_g=values.protein_g,
        fat_g=values.fat_g,
        carbs_g=values.carbs_g,
        fiber_g=values.fiber_g,
        sugars_g=values.sugars_g,
        glycemic_load=values.glycemic_load,
        complete=values.complete,
        missing=list(values.missing),
    )


class GoalMetricRead(BaseModel):
    """Trio wartość/cel/delta + status słowny — kafelek widoku 1 (06_UIUX §3.5).

    `target`, `delta` i `status` są `null`, gdy cel nie jest ustawiony: „nie wiem"
    to inna informacja niż „za mało", a UI pokazuje je inaczej.
    """

    value: DecimalString
    target: DecimalString | None
    #: `value - target`; ujemna = brakuje do celu, dodatnia = ponad cel.
    delta: DecimalString | None
    status: GoalStatus | None


class GoalPayload(BaseModel):
    """Cel obowiązujący od daty — wejście POST i PUT (04_API §1)."""

    valid_from: date
    kcal: GoalKcal
    protein_g: GoalMacro | None = None
    fat_g: GoalMacro | None = None
    carbs_g: GoalMacro | None = None


class GoalRead(BaseModel):
    """Cel w odczycie. Historia jest pełna — nic nie znika samo (D10)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    valid_from: date
    kcal: DecimalString
    protein_g: DecimalString | None
    fat_g: DecimalString | None
    carbs_g: DecimalString | None
    created_at: datetime
    updated_at: datetime


class GoalListResponse(BaseModel):
    """Historia celów (najnowszy `valid_from` pierwszy) + cel obowiązujący dziś."""

    items: list[GoalRead]
    total: int
    #: Cel z największym `valid_from <= dziś`; `null`, gdy użytkownik nie ma celu.
    current: GoalRead | None
