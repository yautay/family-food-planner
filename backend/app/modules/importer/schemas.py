"""Schematy HTTP importera PDF (04_API §1-2).

Zakres BATCH_15: upload, lista jobów, szczegóły joba z raportem parsowania,
usunięcie joba. Staging (`/import/jobs/{id}/staged`) i rozstrzyganie należą
do BATCH_16 i świadomie NIE mają tu schematów — pusty kontrakt „na zapas"
wchodziłby do `generated.ts` i sugerował frontendowi endpoint, którego nie ma.

`parse_report` wychodzi jako surowy obiekt JSON, a nie model: jego kształt
opisuje `parser.build_parse_report`, a każde pole ma tam własny komentarz.
Zamrożenie go w Pydantic oznaczałoby dwie definicje tej samej rzeczy —
i pewność, że B16 zmieni tylko jedną.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.importer.models import ImportJobStatus

__all__ = [
    "ImportJobDetail",
    "ImportJobListResponse",
    "ImportJobSummary",
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
