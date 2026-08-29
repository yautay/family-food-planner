"""Modele stagingu importera PDF — schemat wiążący: 03_DATABASE §9.

Cztery tabele opisują JEDEN proces: plik → job → surowe dania i składniki →
lista rzeczy, które musi rozstrzygnąć człowiek. Żadna z nich nie jest encją
domenową: nie ma tu kolumn wzorca scope (03_DATABASE §4), bo job należy do
KONKRETNEJ osoby, która wgrała plik, a nie do rodziny — dieta jest danymi
zdrowotnymi jednego pacjenta.

Trzy własności warte zapamiętania przed B16:

1. **Typy enumowe są od razu KOMPLETNE** — także wartości, których B15 nigdy
   nie zapisze (`in_review`, `approved`, `rejected`, `fuzzy`, `ai`, cztery
   rodzaje issues z review). Dołożenie wartości do typu enumowego w PG jest
   migracją łamiącą przy `downgrade`, więc płacimy tę cenę raz, teraz.
2. **`staged_*` kaskadują po jobie** (kompozycja, ADR-012): usunięcie joba to
   usunięcie całego stagingu. FK do encji domenowych (`canonical_products`,
   `recipes`) mają natomiast RESTRICT — produkt „użyty" przez wiersz stagingu
   nie może zniknąć spod ręki osoby, która jest w połowie review (niezmiennik
   02_DOMAIN §13.4); liczniki referencji rejestruje `service.py`.
3. **`recipes.import_job_id` dostaje FK dopiero teraz** (migracja `0014`),
   bo dopiero teraz istnieje tabela, na którą wskazuje — patrz komentarz przy
   kolumnie w `recipes/models.py` i bramka dryfu modeli z REVIEW R3.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin

__all__ = [
    "IMPORT_ISSUE_KIND_ENUM",
    "IMPORT_ISSUE_SEVERITY_ENUM",
    "IMPORT_JOB_STATUS_ENUM",
    "IMPORT_MATCH_KIND_ENUM",
    "STAGED_RECIPE_RESOLUTION_ENUM",
    "ImportIssue",
    "ImportIssueKind",
    "ImportIssueSeverity",
    "ImportJob",
    "ImportJobStatus",
    "MatchKind",
    "StagedIngredient",
    "StagedRecipe",
    "StagedRecipeResolution",
]


class ImportJobStatus(StrEnum):
    """Cykl życia joba (02_DOMAIN §10). B15 kończy na `PARSED` albo `FAILED`."""

    UPLOADED = "uploaded"
    PARSED = "parsed"
    #: Ustawia dopiero B16 (wejście w ekran review).
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class StagedRecipeResolution(StrEnum):
    """Decyzja człowieka o daniu ze stagingu — wypełnia WYŁĄCZNIE B16."""

    CREATE = "create"
    MERGE_INTO_EXISTING = "merge_into_existing"
    SKIP = "skip"


class MatchKind(StrEnum):
    """Skąd wzięła się propozycja produktu dla surowej nazwy (ADR-011).

    B15 zapisuje wyłącznie `EXACT` i `NONE` — `FUZZY` i `AI` to B16, i to
    zawsze jako PROPOZYCJA wymagająca zatwierdzenia w review.
    """

    EXACT = "exact"
    FUZZY = "fuzzy"
    AI = "ai"
    NONE = "none"


class ImportIssueKind(StrEnum):
    """Rodzaje rzeczy do rozstrzygnięcia (03_DATABASE §9 — komplet od razu)."""

    MULTI_PORTION_SUSPECT = "multi_portion_suspect"
    #: Poniżej: wykrywa dopiero B16 (wymagają mapowań albo wyliczenia kcal).
    KCAL_MISMATCH = "kcal_mismatch"
    UNMAPPED_PRODUCT = "unmapped_product"
    UNIT_CONFLICT = "unit_conflict"
    DUPLICATE_RECIPE = "duplicate_recipe"
    PARSE_WARNING = "parse_warning"


class ImportIssueSeverity(StrEnum):
    """`BLOCKER` blokuje zatwierdzenie joba (ADR-011), `WARNING` tylko informuje."""

    BLOCKER = "blocker"
    WARNING = "warning"


def _pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """Typ enumowy PG z WARTOŚCIAMI (nie nazwami) składowych — jak w `recipes`."""
    return Enum(enum, name=name, values_callable=lambda members: [m.value for m in members])


#: Jedna definicja nazw typów dla modeli i migracji `0014`.
IMPORT_JOB_STATUS_ENUM = _pg_enum(ImportJobStatus, "import_job_status")
STAGED_RECIPE_RESOLUTION_ENUM = _pg_enum(StagedRecipeResolution, "staged_recipe_resolution")
IMPORT_MATCH_KIND_ENUM = _pg_enum(MatchKind, "import_match_kind")
IMPORT_ISSUE_KIND_ENUM = _pg_enum(ImportIssueKind, "import_issue_kind")
IMPORT_ISSUE_SEVERITY_ENUM = _pg_enum(ImportIssueSeverity, "import_issue_severity")


class ImportJob(TimestampMixin, Base):
    """Jeden wgrany PDF razem z raportem parsowania (03_DATABASE §9)."""

    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: RESTRICT jak we wzorcu scope: konto z danymi kasuje się dopiero po nich.
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: ORYGINALNA nazwa pliku — wyłącznie jako metadana do pokazania człowiekowi.
    #: Na dysk trafia losowa nazwa (`file_path`), 07_SECURITY §6.
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    #: Ścieżka WZGLĘDNA w katalogu uploadów (03_DATABASE §11), nie URL i nie
    #: ścieżka absolutna — katalog przenosi się razem z bind mountem.
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    #: Suma kontrolna treści: deduplikacja INFORMACYJNA (ten sam plik = ostrzeżenie
    #: w raporcie, nigdy blokada uploadu — karta B15 §Security).
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[ImportJobStatus] = mapped_column(
        IMPORT_JOB_STATUS_ENUM,
        nullable=False,
        default=ImportJobStatus.UPLOADED,
        server_default=ImportJobStatus.UPLOADED.value,
    )
    #: Liczby parsowania (kształt: `parser.build_parse_report`). `NULL` dopóki
    #: job nie został sparsowany.
    parse_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: Komunikat błędu przy `FAILED` — po polsku, bez stack trace'u.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    staged_recipes: Mapped[list[StagedRecipe]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )
    issues: Mapped[list[ImportIssue]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class StagedRecipe(TimestampMixin, Base):
    """Jedno DANIE z PDF-a (posiłek może mieć ich więcej niż jedno — §2.3)."""

    __tablename__ = "staged_recipes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    import_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Etykiety Z DOKUMENTU, nie daty: PDF nie niesie kalendarza, tylko
    #: „Poniedziałek/Wtorek/Środa" (01_PDF_AUDIT §2.3). Datę nadaje człowiek
    #: dopiero przy wstawianiu przepisu do planu.
    day_label: Mapped[str] = mapped_column(Text, nullable=False)
    meal_label: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Z sekcji „Przepis na N porcji"; `NULL` = w dokumencie nic nie napisano
    #: (i to jest właśnie przypadek, w którym parser NIE ZGADUJE — §5.1).
    declared_servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Wartości z PDF-a to METADANE WALIDACYJNE (ADR-011, niezmiennik §13.2) —
    #: prawdą aplikacji są wartości wyliczone z produktów kanonicznych.
    pdf_kcal: Mapped[Decimal | None] = mapped_column(Numeric(precision=7, scale=1), nullable=True)
    pdf_macros: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: Trzy pola poniżej wypełnia WYŁĄCZNIE B16 (rozstrzygnięcia review).
    resolution: Mapped[StagedRecipeResolution | None] = mapped_column(
        STAGED_RECIPE_RESOLUTION_ENUM, nullable=True
    )
    target_recipe_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("recipes.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    resolved_servings: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped[ImportJob] = relationship(back_populates="staged_recipes")
    ingredients: Mapped[list[StagedIngredient]] = relationship(
        back_populates="staged_recipe",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StagedIngredient.id",
    )


class StagedIngredient(TimestampMixin, Base):
    """Surowy wiersz składnika: dokładnie to, co stało w PDF, plus propozycja."""

    __tablename__ = "staged_ingredients"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    staged_recipe_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("staged_recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Para ilość + jednostka jest PREZENTACYJNA i zasili `product_unit_weights`
    #: próbkami dopiero przy approve (B16). Ilością jest `grams` (§8.3).
    raw_qty: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=3), nullable=True)
    raw_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Gramatura z nawiasu — JEDYNE źródło ilości przy imporcie (01_PDF_AUDIT §8.3).
    grams: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=3), nullable=False)
    suggested_product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    match_kind: Mapped[MatchKind] = mapped_column(
        IMPORT_MATCH_KIND_ENUM,
        nullable=False,
        default=MatchKind.NONE,
        server_default=MatchKind.NONE.value,
    )
    #: Poniżej: wypełnia B16 (zatwierdzenie mapowania w review).
    confirmed_product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    create_new_product: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    staged_recipe: Mapped[StagedRecipe] = relationship(back_populates="ingredients")


class ImportIssue(TimestampMixin, Base):
    """Rzecz do rozstrzygnięcia przez człowieka; `BLOCKER` blokuje approve."""

    __tablename__ = "import_issues"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    import_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: `NULL` = problem dotyczy CAŁEGO joba, nie pojedynczego dania.
    staged_recipe_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("staged_recipes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind: Mapped[ImportIssueKind] = mapped_column(IMPORT_ISSUE_KIND_ENUM, nullable=False)
    severity: Mapped[ImportIssueSeverity] = mapped_column(
        IMPORT_ISSUE_SEVERITY_ENUM, nullable=False
    )
    #: Kontekst dla człowieka (liczby, surowa linia) — nigdy treść pliku w całości.
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    #: Poniżej: wypełnia B16 (co człowiek zdecydował i kiedy).
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[ImportJob] = relationship(back_populates="issues")
