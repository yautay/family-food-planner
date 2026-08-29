"""Format transferu v1 — KONTRAKT pliku eksportu i schematy API (04_API §2).

Plik eksportu to ZIP z dwoma rodzajami wpisów:

- `export.json` — nagłówek (`schema_version`, `app_version`, `exported_at`,
  `scope`) + `data` z sekcjami per tabela,
- `photos/<nazwa>` — zdjęcia przepisów i wariantów sklepowych, po ścieżkach
  względnych z bazy (miniatury NIE wchodzą: import re-enkoduje oryginał
  i generuje je od nowa, `app/core/uploads.py`).

Dwie rzeczy w tym module są WIĄŻĄCE dla obu stron transferu:

1. **`SECTION_ORDER`** — jedna, wspólna kolejność sekcji. Eksport zapisuje
   w niej sekcje, import je w niej wstawia, bo FK z RESTRICT nie wybaczają
   innej kolejności (ustalenie REVIEW R3: kategorie → produkty kanoniczne →
   sklepy → warianty retail → spiżarnia → tury → listy).
2. **ID w pliku to referencje WEWNĘTRZNE** — import nigdy ich nie wstawia,
   tylko buduje mapę stary→nowy. Dlatego każda sekcja niesie własne `id`.

Liczby (ilości, wartości odżywcze) są stringami dziesiętnymi (ADR-008): float
w pliku cicho zmieniłby ilości w przepisach i na listach.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Wersja formatu. Zmiana kształtu = `2` + konwersja przy odczycie; dopóki jest
#: tylko `1`, plik z inną wersją kończy się 422 (Out of Scope karty B14).
SCHEMA_VERSION = 1

#: Nazwa pliku z danymi wewnątrz archiwum.
DATA_ENTRY_NAME = "export.json"
#: Katalog zdjęć wewnątrz archiwum (jedyny dozwolony prefiks poza `export.json`).
PHOTOS_PREFIX = "photos/"


class TransferScope(StrEnum):
    """Zakres eksportu: dane jednego użytkownika albo cała instancja."""

    USER = "user"
    INSTANCE = "instance"


#: Kolejność sekcji = kolejność importu. Sekcje `instance`-only są w niej
#: na swoich miejscach; przy `scope=user` po prostu nie powstają.
SECTION_ORDER: tuple[str, ...] = (
    # --- słowniki globalne ---------------------------------------------------
    "product_categories",
    "nutrients",
    "tags",
    "stores",
    "store_category_order",
    "canonical_products",
    "product_unit_weights",
    "product_nutrient_values",
    "retail_products",
    # --- konta i rodziny (tylko `scope=instance`) ----------------------------
    "households",
    "users",
    # --- dane użytkownika ----------------------------------------------------
    "member_profiles",
    "user_nutrition_goals",
    "recipes",
    "recipe_ingredients",
    "recipe_tags",
    "recipe_ratings",
    "plan_days",
    "plan_meals",
    "plan_meal_items",
    "plan_item_servings",
    "day_templates",
    "week_templates",
    "week_cycles",
    "pantry_items",
    "shopping_round_configs",
    "shopping_generations",
    "shopping_lists",
    "shopping_list_items",
    # --- dziennik (tylko `scope=instance`) -----------------------------------
    "audit_entries",
)


class CollisionAction(StrEnum):
    """Decyzja użytkownika dla kolizji nazw przy imporcie."""

    #: Nic nie twórz — referencje z pliku wskaż na encję, która JUŻ jest.
    USE_EXISTING = "use_existing"
    #: Utwórz kopię z sufiksem „(import)"; dane z pliku żyją obok istniejących.
    CREATE_COPY = "create_copy"


#: Sufiks nazwy kopii. Trzymany tutaj, bo widzi go użytkownik w raporcie
#: dry-run i musi zobaczyć dokładnie to, co potem powstanie w bazie.
COPY_SUFFIX = " (import)"


class ExportHeader(BaseModel):
    """Nagłówek pliku — czytany PRZED czymkolwiek innym (walidacja wersji)."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int
    app_version: str = ""
    exported_at: str = ""
    scope: TransferScope = TransferScope.USER


class ExportFile(BaseModel):
    """Cały `export.json`. `data` zostaje surowe — kształt sekcji pilnuje importer."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[1]
    app_version: str = ""
    exported_at: str = ""
    scope: TransferScope = TransferScope.USER
    data: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


# --- API: raport dry-run ------------------------------------------------------------


class CollisionRead(BaseModel):
    """Jedna kolizja nazwy: co w pliku, co już jest w bazie, co zrobimy domyślnie."""

    entity: str
    #: ID z PLIKU — klucz decyzji w `apply` (nie ma nic wspólnego z bazą).
    source_id: int
    name: str
    existing_id: int
    existing_name: str
    default: CollisionAction = CollisionAction.USE_EXISTING


class DryRunReport(BaseModel):
    """Co powstanie i co koliduje — ZANIM cokolwiek dotknie bazy (AC 3)."""

    #: Identyfikator paczki odłożonej w scratchu; wchodzi do URL-a `apply`.
    import_id: str
    schema_version: int
    scope: TransferScope
    exported_at: str
    app_version: str
    #: Liczba wierszy do utworzenia per sekcja (bez sekcji pustych).
    to_create: dict[str, int]
    collisions: list[CollisionRead]
    #: Ostrzeżenia niewymagające decyzji (np. brak zdjęcia w archiwum).
    warnings: list[str]
    photos: int


# --- API: apply ---------------------------------------------------------------------


class CollisionDecision(BaseModel):
    """Decyzja per kolizja. Pominięta kolizja dostaje `default` z raportu."""

    model_config = ConfigDict(extra="forbid")

    entity: str
    source_id: int = Field(ge=1)
    action: CollisionAction


class ImportApplyRequest(BaseModel):
    """Body `apply`: wyłącznie decyzje kolizyjne (reszta jest w odłożonej paczce)."""

    model_config = ConfigDict(extra="forbid")

    decisions: list[CollisionDecision] = Field(default_factory=list, max_length=5000)


class ImportSummary(BaseModel):
    """Podsumowanie zastosowania: ile czego powstało (AC 4 i 5)."""

    created: dict[str, int]
    reused: dict[str, int]
    photos_imported: int
    warnings: list[str]
