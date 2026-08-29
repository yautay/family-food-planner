"""Schematy HTTP importera PDF (04_API §1-2).

BATCH_15 dostarczył upload, listę jobów, szczegóły z raportem parsowania
i usunięcie; BATCH_16 dołożył **review**: stan stagingu, rozstrzygnięcia,
zatwierdzenie i odrzucenie.

Dwie rzeczy, które warto tu zauważyć:

- `parse_report` wychodzi jako surowy obiekt JSON, a nie model: jego kształt
  opisuje `parser.build_parse_report`, a każde pole ma tam własny komentarz.
  Zamrożenie go w Pydantic oznaczałoby dwie definicje tej samej rzeczy.
- Każda liczba dziesiętna używa `DecimalString` (ADR-008), więc `task fe-types`
  generuje po stronie frontendu `string`, a nie `number` — także `confidence`
  propozycji AI i kalorie wyliczone przez silnik.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.schemas import DecimalString
from app.core.scope import Scope
from app.modules.importer.models import (
    ImportIssueKind,
    ImportIssueSeverity,
    ImportJobStatus,
    MatchKind,
    StagedRecipeResolution,
)

__all__ = [
    "ApproveBlockerRead",
    "ImportApproveRequest",
    "ImportApproveResponse",
    "ImportIssueRead",
    "ImportJobDetail",
    "ImportJobListResponse",
    "ImportJobSummary",
    "ImportResolveRequest",
    "MealNutritionRead",
    "ResolveIngredientRequest",
    "ResolveIssueRequest",
    "ResolveRecipeRequest",
    "StagedIngredientRead",
    "StagedJobResponse",
    "StagedRecipeRead",
]

#: Nazwa dania poprawiana w review (errata §9.5 — 3 ze 103 nazw są ucięte).
StagedRecipeName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class ImportJobSummary(BaseModel):
    """Job na liście: tyle, ile potrzeba do wiersza tabeli i plakietki statusu."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: ImportJobStatus
    created_at: datetime
    updated_at: datetime
    #: Komunikat błędu przy `failed` — bez niego lista pokazywałaby samą
    #: czerwoną plakietkę i nikt by nie wiedział, co poprawić.
    error: str | None = None
    #: Skróty z raportu: dni / posiłki / dania / składniki / issues. Pola są
    #: opcjonalne, bo job `uploaded` i `failed` nie ma jeszcze raportu.
    days: int | None = None
    meals: int | None = None
    staged_recipes: int | None = None
    ingredients: int | None = None
    blockers: int | None = None
    warnings: int | None = None


class ImportJobDetail(ImportJobSummary):
    """Job razem z pełnym raportem parsowania (podgląd w UI)."""

    parse_report: dict[str, Any] | None = None


class ImportJobListResponse(BaseModel):
    """Lista jobów z paginacją — kształt jak w pozostałych zasobach (04_API §1)."""

    items: list[ImportJobSummary] = Field(default_factory=list)
    total: int


# --- review (BATCH_16) -------------------------------------------------------------


class StagedIngredientRead(BaseModel):
    """Wiersz składnika w review: surowe dane z PDF + stan mapowania."""

    id: int
    raw_name: str
    #: Para ilość + jednostka bywa pusta — dwa z trzech wariantów wiersza §3.2
    #: jej nie niosą (decyzja D20).
    raw_qty: DecimalString | None = None
    raw_unit: str | None = None
    grams: DecimalString
    #: Wiersz z sekcji `Produkty`: dodatek podany NA PORCJĘ, nie na całość (U22).
    from_extras_section: bool
    match_kind: MatchKind
    #: Pewność propozycji AI (0-1); `null` dla EXACT i dla braku propozycji.
    confidence: DecimalString | None = None
    suggested_product_id: int | None = None
    suggested_product_name: str | None = None
    confirmed_product_id: int | None = None
    confirmed_product_name: str | None = None
    create_new_product: bool


class ImportIssueRead(BaseModel):
    """Uwaga do rozstrzygnięcia albo do wiadomości."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    staged_recipe_id: int | None = None
    kind: ImportIssueKind
    severity: ImportIssueSeverity
    details: dict[str, Any] = Field(default_factory=dict)
    resolution: str | None = None
    resolved_at: datetime | None = None


class MealNutritionRead(BaseModel):
    """Kalorie POSIŁKU: wyliczone przez silnik obok podanych w jadłospisie.

    Wartości są per POSIŁEK, nie per danie — `pdf_kcal` w dokumencie opisuje
    posiłek, a posiłek bywa dwudaniowy (01_PDF_AUDIT §3.1, errata §9.1).
    """

    computed_kcal: DecimalString | None = None
    pdf_kcal: DecimalString | None = None
    delta_pct: DecimalString | None = None
    #: Pusty string = policzono; inaczej gotowy komunikat, czemu się nie da.
    reason: str = ""


class StagedRecipeRead(BaseModel):
    """Jedno danie ze stagingu — karta w ekranie review."""

    id: int
    name: str
    day_label: str
    meal_label: str
    instructions: str
    comment: str
    declared_servings: int | None = None
    resolved_servings: int | None = None
    resolution: StagedRecipeResolution | None = None
    target_recipe_id: int | None = None
    pdf_macros: dict[str, Any] | None = None
    meal: MealNutritionRead
    ingredients: list[StagedIngredientRead] = Field(default_factory=list)
    issues: list[ImportIssueRead] = Field(default_factory=list)


class ApproveBlockerRead(BaseModel):
    """Jedna blokada zatwierdzenia — ten sam kształt, co w `details` odpowiedzi 409."""

    staged_recipe_id: int | None = None
    recipe_name: str = ""
    kind: ImportIssueKind
    message: str = ""


class StagedJobResponse(BaseModel):
    """Kompletny stan review jednego importu."""

    job: ImportJobDetail
    recipes: list[StagedRecipeRead] = Field(default_factory=list)
    #: Uwagi dotyczące CAŁEGO pliku (bez wskazania dania), np. `parse_warning`.
    job_issues: list[ImportIssueRead] = Field(default_factory=list)
    blockers: list[ApproveBlockerRead] = Field(default_factory=list)
    #: `false` = instancja nie ma klucza API; UI chowa przyciski AI (ADR-011).
    ai_available: bool


class ResolveIngredientRequest(BaseModel):
    """Decyzja o mapowaniu jednego składnika.

    `confirmed_product_id` i `create_new_product` wykluczają się: wskazanie
    produktu wygrywa, bo jest konkretniejsze niż „załóż coś nowego".
    """

    ingredient_id: int = Field(ge=1)
    confirmed_product_id: int | None = Field(default=None, ge=1)
    create_new_product: bool = False


class ResolveRecipeRequest(BaseModel):
    """Decyzje o jednym daniu: nazwa, porcje, co z nim zrobić."""

    staged_recipe_id: int = Field(ge=1)
    #: Poprawka nazwy uciętej przez zawijanie kolumn (errata §9.5).
    name: StagedRecipeName | None = None
    resolution: StagedRecipeResolution | None = None
    target_recipe_id: int | None = Field(default=None, ge=1)
    #: Liczba porcji bazowych przepisu — rozstrzygnięcie `multi_portion_suspect`.
    resolved_servings: int | None = Field(default=None, ge=1, le=100)


class ResolveIssueRequest(BaseModel):
    """Ręczne zamknięcie uwagi z krótkim uzasadnieniem."""

    issue_id: int = Field(ge=1)
    resolution: str = Field(min_length=1, max_length=500)


class ImportResolveRequest(BaseModel):
    """Paczka decyzji jednego zapisu review (wszystkie sekcje opcjonalne).

    Nazwa ma prefiks `Import`, bo moduł shopping ma własne `ResolveRequest`
    (rozstrzyganie niejasności podglądu zakupów). Dwa schematy o tej samej
    nazwie zmuszają FastAPI do kwalifikowania OBU pełną ścieżką modułu
    w OpenAPI, co zmienia klucz w `generated.ts` także temu, który był
    pierwszy — czyli psuje CUDZY moduł frontendu.
    """

    recipes: list[ResolveRecipeRequest] = Field(default_factory=list)
    ingredients: list[ResolveIngredientRequest] = Field(default_factory=list)
    issues: list[ResolveIssueRequest] = Field(default_factory=list)


class ImportApproveRequest(BaseModel):
    """Zatwierdzenie importu. Scope wybiera się RAZ dla całego joba, nie per danie."""

    scope: Scope = Scope.HOUSEHOLD


class ImportApproveResponse(BaseModel):
    """Podsumowanie zatwierdzenia — liczby do ekranu „gotowe"."""

    job: ImportJobDetail
    created_recipe_ids: list[int] = Field(default_factory=list)
    created_product_ids: list[int] = Field(default_factory=list)
    merged_count: int
    skipped_count: int
    unit_weight_rows: int
