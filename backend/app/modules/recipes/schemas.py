"""Schematy request/response modułu recipes (04_API §1-2).

Wszystkie ilości i wartości wyliczane wychodzą jako stringi dziesiętne
(`DecimalString`, ADR-008). Kształt pola `nutrition` jest kontraktem z 04_API §1:
`{kcal, protein_g, fat_g, carbs_g, fiber_g, sugars_g, glycemic_load, complete,
missing[]}` — wartości zaokrąglone WYŁĄCZNIE przez `round_for_output` silnika.

Składnik ma dwa oblicza: wejście (`quantity` + `unit` — to, co wpisał
użytkownik) i odczyt (`display_*` + znormalizowane `amount`/`amount_unit`
+ `scaled_amount` policzone dla żądanej liczby porcji — frontend nie liczy
ilości sam, 05_FRONTEND §7).

`NutritionRead` jest importowany z modułu nutrition (BATCH_06): kształt wyniku
obliczeń należy do domeny żywienia i konsumuje go też plan dnia — dwie kopie
oznaczałyby dwa komponenty w OpenAPI o identycznej treści.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.schemas import DecimalString
from app.core.scope import Scope
from app.modules.catalog.models import MeasureKind
from app.modules.catalog.units import AmountUnit
from app.modules.nutrition.schemas import NutritionRead

__all__ = [
    "NutritionRead",
    "RatingRequest",
    "RatingResponse",
    "RecipeDetail",
    "RecipeIngredientInput",
    "RecipeIngredientRead",
    "RecipeListResponse",
    "RecipePayload",
    "RecipeSummary",
    "TagCreateRequest",
    "TagListResponse",
    "TagRead",
]

RecipeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
UnitLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
#: Ilość wpisana przez użytkownika — NUMERIC(8,3), zawsze dodatnia.
IngredientQuantity = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("99999.999"), max_digits=8, decimal_places=3)
]

# --- tagi -----------------------------------------------------------------------------


class TagRead(BaseModel):
    """Tag ze słownika globalnego."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_system: bool


class TagListResponse(BaseModel):
    items: list[TagRead]
    total: int


class TagCreateRequest(BaseModel):
    """Inline create tagu użytkowego (`is_system=false`) z multi-pickera."""

    name: TagName


# --- składniki --------------------------------------------------------------------------


class RecipeIngredientInput(BaseModel):
    """Pozycja składnika przy zapisie — ilość W JEDNOSTCE użytkownika.

    Normalizację do g/ml/szt. robi serwis (ADR-005); pozycja na liście wynika
    z kolejności w tablicy, nie z osobnego pola.
    """

    product_id: int = Field(ge=1)
    quantity: IngredientQuantity
    unit: UnitLabel
    note: str = Field(default="", max_length=500)


class RecipeIngredientRead(BaseModel):
    """Składnik w odczycie: zapis użytkownika + postać znormalizowana + przeskalowana."""

    id: int
    product_id: int
    product_name: str
    measure_kind: MeasureKind
    display_qty: DecimalString | None
    display_unit: str | None
    amount: DecimalString
    amount_unit: AmountUnit
    #: Ilość dla żądanej liczby porcji (amount x servings / base_servings) —
    #: liczona przez backend, frontend tylko formatuje (05_FRONTEND §7).
    scaled_amount: DecimalString
    note: str
    position: int


# --- przepisy ---------------------------------------------------------------------------


class RecipePayload(BaseModel):
    """Jeden model wejścia dla POST (create) i PUT (pełna podmiana — 04_API §1).

    Świadomie BEZ pustych podklas per metoda: dwa bit-identyczne schematy
    w OpenAPI maskowałyby, który jest „prawdziwy", i podwajały diff
    `generated.ts` (ustalenie review B05).
    """

    name: RecipeName
    instructions: str = Field(default="", max_length=20000)
    base_servings: int = Field(default=1, ge=1, le=100)
    prep_time_min: int | None = Field(default=None, ge=1, le=6000)
    difficulty: int | None = Field(default=None, ge=1, le=10)
    scope: Scope = Scope.PRIVATE
    ingredients: list[RecipeIngredientInput] = Field(default_factory=list, max_length=100)
    tag_ids: list[int] = Field(default_factory=list, max_length=50)


class RecipeSummary(BaseModel):
    """Przepis na liście (widok 2): karta z kcal/porcję, oceną i tagami."""

    id: int
    name: str
    scope: Scope
    owner_user_id: int
    base_servings: int
    prep_time_min: int | None
    difficulty: int | None
    is_archived: bool
    photo_url: str | None
    photo_thumb_url: str | None
    tags: list[TagRead]
    avg_rating: DecimalString | None
    ratings_count: int
    my_rating: int | None
    #: Wartości JEDNEJ porcji bazowej (zaokrąglone na wyjściu).
    nutrition: NutritionRead
    created_at: datetime
    updated_at: datetime


class RecipeDetail(RecipeSummary):
    """Szczegóły (widok 3): instrukcja, składniki i nutrition x mnożnik porcji."""

    instructions: str
    #: Mnożnik, dla którego policzono `nutrition` i `scaled_amount` składników.
    servings: DecimalString
    ingredients: list[RecipeIngredientRead]


class RecipeListResponse(BaseModel):
    items: list[RecipeSummary]
    total: int


# --- oceny ------------------------------------------------------------------------------


class RatingRequest(BaseModel):
    """Własna ocena 1-5; `user_id` pochodzi z sesji, nigdy z body (karta B05)."""

    rating: int = Field(ge=1, le=5)


class RatingResponse(BaseModel):
    my_rating: int
    avg_rating: DecimalString
    ratings_count: int
