"""Sekcje formatu v1: co dokładnie wchodzi do pliku i jak wygląda wiersz.

Ten moduł jest WSPÓLNY dla eksportu i importu — jedna tabela `SECTIONS` opisuje
kolumny, referencje i klucz naturalny każdej sekcji, więc obie strony transferu
nie mogą się rozjechać (Implementation Notes karty B14).

Funkcje są czyste: wiersz ORM → słownik JSON-owalny. Zapytania do bazy robi
`service.py`, pakowanie ZIP-a — `write_archive` niżej (I/O na plik tymczasowy,
nie do pamięci: paczka ze zdjęciami nie ma prawa wejść do RAM Odroida).

Czego w pliku ŚWIADOMIE NIE MA (ustalenia REVIEW R3 i 07_SECURITY):

- `users.password_hash` — plik eksportu nie może być materiałem do credential
  stuffingu; po imporcie instancji ADMIN nadaje hasła (`PATCH /admin/users/{id}`),
- `sessions` — żywe sesje to nie dane domenowe,
- `shopping_lists.public_token` i `token_revoked` — żywy token dostępu bez
  logowania (ADR-010) w pliku, który ląduje w mailu i w kopii zapasowej, jest
  wyciekiem niezależnie od tego, jak nieciekawa jest lista,
- `created_at`/`updated_at` (poza `audit_entries`, gdzie czas JEST treścią),
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.uploads import resolve_upload_path
from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.catalog.models import (
    CanonicalProduct,
    Nutrient,
    ProductCategory,
    ProductNutrientValue,
    ProductUnitWeight,
    RetailProduct,
    Store,
    StoreCategoryOrder,
)
from app.modules.households.models import Household, MemberProfile
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.pantry.models import PantryItem
from app.modules.planning.models import (
    DayTemplate,
    PlanDay,
    PlanItemServing,
    PlanMeal,
    PlanMealItem,
    WeekCycle,
    WeekTemplate,
)
from app.modules.recipes.models import Recipe, RecipeIngredient, RecipeRating, Tag, recipe_tags
from app.modules.shopping.models import (
    ShoppingGeneration,
    ShoppingList,
    ShoppingListItem,
    ShoppingRoundConfig,
)
from app.modules.transfer.schemas import (
    DATA_ENTRY_NAME,
    PHOTOS_PREFIX,
    SCHEMA_VERSION,
    SECTION_ORDER,
    TransferScope,
)

#: Sekcje, których wiersz jest identyfikowany parą kluczy obcych, a nie własnym
#: `id` (tabele asocjacyjne). Import wstawia je na końcu swojej grupy i pomija
#: duplikaty, bo para (rodzic, dziecko) jest tam całym kluczem głównym.
ASSOCIATION_SECTIONS = frozenset({"recipe_tags", "store_category_order"})


@dataclass(frozen=True)
class Section:
    """Opis jednej sekcji formatu — wiążący dla eksportu i importu."""

    name: str
    model: Any
    #: Kolumny kopiowane dosłownie (już bez `id`, kluczy obcych i znaczników czasu).
    columns: tuple[str, ...] = ()
    #: Kolumna klucza obcego → nazwa sekcji, w której mapie szukamy nowego id.
    references: Mapping[str, str] = field(default_factory=dict)
    #: Klucz naturalny do wykrywania kolizji (`None` = sekcja bez kolizji).
    key: str | None = None
    #: Kolumna pokazywana człowiekowi w raporcie (domyślnie ta sama, co klucz).
    label: str | None = None
    #: Kolizji nie da się rozstrzygnąć „utwórz kopię" (unikalny e-mail, kod
    #: składnika) — import zawsze reużywa istniejącego wiersza i tylko ostrzega.
    auto_reuse: bool = False
    #: Sekcja wchodzi WYŁĄCZNIE do eksportu instancji.
    instance_only: bool = False
    #: Kolumna ze ścieżką zdjęcia (plik ląduje w `photos/` archiwum).
    photo: str | None = None
    #: Klucz główny w pliku; `None` = tabela asocjacyjna bez własnego id.
    pk: str | None = "id"
    #: Encja z kolumnami wzorca scope (03_DATABASE §4).
    scoped: bool = False
    #: Wiersz niosący FAKT o encji nadrzędnej (przelicznik jednostki, ocena,
    #: cel na datę). Ma w bazie UNIQUE, którego reużyty rodzic już spełnia, więc
    #: import wstawia go `ON CONFLICT DO NOTHING` i nie potrzebuje jego id.
    idempotent: bool = False
    #: Kolumny UNIQUE wiersza — jedna deklaracja obsługująca DWA zastosowania
    #: (BATCH_20): `apply` scala po nich wiersz z istniejącym zamiast wywalać
    #: import (`plan_days`) albo pomija go `ON CONFLICT DO NOTHING` (sekcje
    #: `idempotent`), a raport DRY-RUN sprawdza po nich, czy wiersz JUŻ jest
    #: w bazie — bez tego `to_create` obiecywałoby wiersze, których `apply`
    #: nie utworzy (dług U21), a scalane dni planu przechodziłyby w milczeniu
    #: (decyzja **D24**). Sekcja `idempotent` MUSI mieć `merge_key` równy
    #: swojemu UNIQUE-owi z bazy — inaczej raport ją zawyży.
    merge_key: tuple[str, ...] | None = None
    #: Kolumna referencji do RODZICA KOMPOZYCJI — tego jednego wiersza, którego
    #: częścią jest ta sekcja (ADR-012: FK `ON DELETE CASCADE` rodzic→dziecko).
    #: Gdy import REUŻYWA rodzica, jego dzieci POMIJA (decyzja **D22**):
    #: „użyj istniejącego" znaczy „zostaw ten wiersz i jego zawartość w spokoju",
    #: więc reużyty przepis nie dostaje drugiego kompletu składników, a reużyty
    #: dzień planu — drugiego kompletu posiłków. Bez tego ten sam plik
    #: zaimportowany dwa razy podwaja zawartość rodzica, a przy pętli
    #: eksport→import rośnie ona wykładniczo (zmierzone w B16: 1536 składników
    #: w daniu o trzech).
    #: Referencja do SŁOWNIKA (produkt kanoniczny, kategoria, tag, sklep) tym
    #: NIE JEST — reużycie produktu nie ma prawa skasować składnika, który go
    #: używa. Kryterium jest jedno i sprawdzalne: `ON DELETE CASCADE` w bazie.
    parent: str | None = None


SECTIONS: tuple[Section, ...] = (
    Section(
        name="product_categories",
        model=ProductCategory,
        columns=("name", "position", "perishability"),
        key="name",
    ),
    Section(
        name="nutrients",
        model=Nutrient,
        columns=("name", "unit", "display_order"),
        key="code",
        auto_reuse=True,
        pk="code",
    ),
    Section(name="tags", model=Tag, columns=("name", "is_system"), key="name"),
    Section(name="stores", model=Store, columns=("name", "color", "is_archived"), key="name"),
    Section(
        name="store_category_order",
        model=StoreCategoryOrder,
        columns=("position",),
        references={"store_id": "stores", "category_id": "product_categories"},
        pk=None,
    ),
    Section(
        name="canonical_products",
        model=CanonicalProduct,
        columns=(
            "name",
            "normalized_name",
            "measure_kind",
            "piece_weight_g",
            "kcal_100",
            "protein_100",
            "fat_100",
            "carbs_100",
            "fiber_100",
            "sugars_100",
            "glycemic_index",
            "verification_status",
            "nutrition_source",
            "verified_at",
            "perishability_override",
            "is_archived",
        ),
        references={"category_id": "product_categories"},
        key="normalized_name",
        label="name",
    ),
    Section(
        name="product_unit_weights",
        model=ProductUnitWeight,
        columns=("unit_label", "grams_per_unit", "source", "samples_count"),
        references={"product_id": "canonical_products"},
        idempotent=True,
        merge_key=("product_id", "unit_label"),
        parent="product_id",
    ),
    Section(
        name="product_nutrient_values",
        model=ProductNutrientValue,
        columns=("amount_per_100",),
        references={"product_id": "canonical_products", "nutrient_code": "nutrients"},
        idempotent=True,
        merge_key=("product_id", "nutrient_code"),
        parent="product_id",
    ),
    Section(
        name="retail_products",
        model=RetailProduct,
        columns=(
            "name",
            "brand",
            "package_amount",
            "package_unit",
            "pieces_per_package",
            "photo_path",
            "is_archived",
        ),
        references={"canonical_product_id": "canonical_products", "store_id": "stores"},
        photo="photo_path",
    ),
    Section(
        name="households",
        model=Household,
        columns=("name",),
        key="name",
        instance_only=True,
    ),
    Section(
        name="users",
        model=User,
        columns=("email", "display_name", "role", "is_active", "ui_settings"),
        references={"household_id": "households"},
        key="email",
        auto_reuse=True,
        instance_only=True,
    ),
    Section(
        name="member_profiles",
        model=MemberProfile,
        columns=("name", "default_multiplier", "kcal_goal", "is_active"),
        references={"household_id": "households", "owner_user_id": "users"},
    ),
    Section(
        name="user_nutrition_goals",
        model=UserNutritionGoal,
        # CAŁA historia celów, nie tylko cel bieżący: `/stats/daily` wybiera cel
        # dnia po `valid_from`, więc utrata historii po cichu przepisałaby statusy
        # dni sprzed zmiany celu (ustalenie BATCH_13).
        columns=("valid_from", "kcal", "protein_g", "fat_g", "carbs_g"),
        references={"user_id": "users"},
        idempotent=True,
        merge_key=("user_id", "valid_from"),
    ),
    Section(
        name="recipes",
        model=Recipe,
        columns=(
            "name",
            "instructions",
            "base_servings",
            "prep_time_min",
            "difficulty",
            "photo_path",
            "is_archived",
        ),
        key="name",
        photo="photo_path",
        scoped=True,
    ),
    Section(
        name="recipe_ingredients",
        model=RecipeIngredient,
        columns=("display_qty", "display_unit", "amount", "amount_unit", "note", "position"),
        references={"recipe_id": "recipes", "product_id": "canonical_products"},
        parent="recipe_id",
    ),
    Section(
        name="recipe_tags",
        model=recipe_tags,
        references={"recipe_id": "recipes", "tag_id": "tags"},
        pk=None,
        parent="recipe_id",
    ),
    Section(
        name="recipe_ratings",
        model=RecipeRating,
        columns=("rating",),
        references={"recipe_id": "recipes", "user_id": "users"},
        idempotent=True,
        merge_key=("recipe_id", "user_id"),
        parent="recipe_id",
    ),
    Section(
        name="plan_days",
        model=PlanDay,
        columns=("day", "title"),
        scoped=True,
        # UNIQUE(owner_user_id, day): import własnego eksportu na to samo konto
        # ma dopisać posiłki do istniejącego dnia, a nie wywrócić całej operacji.
        merge_key=("owner_user_id", "day"),
    ),
    Section(
        name="plan_meals",
        model=PlanMeal,
        columns=("name", "position", "kcal_target"),
        references={"plan_day_id": "plan_days"},
        parent="plan_day_id",
    ),
    Section(
        name="plan_meal_items",
        model=PlanMealItem,
        columns=("amount", "amount_unit", "servings", "position"),
        references={
            "plan_meal_id": "plan_meals",
            "recipe_id": "recipes",
            "product_id": "canonical_products",
        },
        parent="plan_meal_id",
    ),
    Section(
        name="plan_item_servings",
        model=PlanItemServing,
        columns=("multiplier",),
        references={
            "plan_meal_item_id": "plan_meal_items",
            "member_profile_id": "member_profiles",
        },
        parent="plan_meal_item_id",
    ),
    Section(
        name="day_templates",
        model=DayTemplate,
        columns=("name", "payload"),
        key="name",
        scoped=True,
    ),
    Section(
        name="week_templates",
        model=WeekTemplate,
        columns=("name", "payload"),
        key="name",
        scoped=True,
    ),
    Section(
        name="week_cycles",
        model=WeekCycle,
        columns=("name", "template_ids", "start_date"),
        scoped=True,
    ),
    Section(
        name="pantry_items",
        model=PantryItem,
        columns=("amount", "amount_unit", "expiry_date", "location", "note"),
        references={
            "product_id": "canonical_products",
            "retail_product_id": "retail_products",
            "owner_user_id": "users",
            "household_id": "households",
        },
    ),
    Section(
        name="shopping_round_configs",
        model=ShoppingRoundConfig,
        columns=("name", "shopping_weekday", "covers_days", "fresh_days", "mode", "position"),
        scoped=True,
    ),
    Section(
        name="shopping_generations",
        model=ShoppingGeneration,
        # `params` przenosimy DOSŁOWNIE (ustalenie REVIEW R3): to wersjonowane
        # wejście silnika, a nie wynik — przepisanie kluczy „po swojemu" dałoby
        # po imporcie 409 przy pierwszym otwarciu generacji.
        columns=("date_from", "date_to", "used_pantry", "params", "status"),
        scoped=True,
    ),
    Section(
        name="shopping_lists",
        model=ShoppingList,
        columns=("name", "round_name", "expires_at"),
        references={"generation_id": "shopping_generations", "store_id": "stores"},
        scoped=True,
        parent="generation_id",
    ),
    Section(
        name="shopping_list_items",
        model=ShoppingListItem,
        columns=(
            "label",
            "needed_amount",
            "amount_unit",
            "packages_count",
            "package_size",
            "leftover_amount",
            "already_have",
            "from_pantry_amount",
            "checked",
            "checked_at",
            "received_at",
            "position",
        ),
        references={
            "list_id": "shopping_lists",
            "category_id": "product_categories",
            "product_id": "canonical_products",
            "retail_product_id": "retail_products",
        },
        parent="list_id",
    ),
    Section(
        name="audit_entries",
        model=AuditEntry,
        # `entity_id` zostaje surowe: to historyczny ślad po encji, której w nowej
        # bazie może już nie być. Remapowanie go kłamałoby o tym, czego dotyczył wpis.
        columns=("action", "entity_type", "entity_id", "payload", "created_at"),
        references={"user_id": "users"},
        instance_only=True,
    ),
)

SECTIONS_BY_NAME: Mapping[str, Section] = {section.name: section for section in SECTIONS}

#: Kolumny wzorca scope dopisywane do sekcji `scoped=True` — jedno miejsce,
#: żeby eksport i import nie rozjechały się co do ich nazw.
SCOPE_COLUMNS = ("owner_user_id", "household_id", "scope")
SCOPE_REFERENCES: Mapping[str, str] = {"owner_user_id": "users", "household_id": "households"}


def section_columns(section: Section) -> tuple[str, ...]:
    """Kolumny skalarne sekcji razem z kolumną `scope` encji scope'owanej."""
    return section.columns + (("scope",) if section.scoped else ())


def section_references(section: Section) -> Mapping[str, str]:
    """Referencje sekcji razem z kolumnami właścicielskimi encji scope'owanej."""
    if not section.scoped:
        return section.references
    return {**section.references, **SCOPE_REFERENCES}


def sections_for(scope: TransferScope) -> tuple[Section, ...]:
    """Sekcje wchodzące do pliku o danym zakresie, w kolejności `SECTION_ORDER`."""
    wanted = [
        SECTIONS_BY_NAME[name]
        for name in SECTION_ORDER
        if scope is TransferScope.INSTANCE or not SECTIONS_BY_NAME[name].instance_only
    ]
    return tuple(wanted)


def json_value(value: Any) -> Any:
    """Wartość kolumny → wartość JSON-owalna (ADR-008: Decimal jako string)."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def row_to_dict(section: Section, row: Any) -> dict[str, Any]:
    """Wiersz ORM (albo krotka tabeli asocjacyjnej) → słownik sekcji."""
    payload: dict[str, Any] = {}
    if section.pk is not None:
        payload[section.pk] = getattr(row, section.pk)
    for column in section_columns(section):
        payload[column] = json_value(getattr(row, column))
    for column in section_references(section):
        payload[column] = getattr(row, column)
    return payload


def photo_paths(section: Section, rows: Iterable[Any]) -> list[str]:
    """Ścieżki zdjęć (względne, z bazy) dla wierszy sekcji — bez miniatur."""
    if section.photo is None:
        return []
    return [path for row in rows if (path := getattr(row, section.photo))]


def build_document(
    *,
    scope: TransferScope,
    app_version: str,
    exported_at: datetime,
    data: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Kompletna treść `export.json` — nagłówek + sekcje w `SECTION_ORDER`."""
    ordered = {section.name: list(data.get(section.name, ())) for section in sections_for(scope)}
    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": app_version,
        "exported_at": exported_at.isoformat(),
        "scope": scope.value,
        "data": ordered,
    }


def write_archive(
    document: Mapping[str, Any],
    *,
    photos: Iterable[str],
    uploads_root: Path,
    target: Path,
) -> list[str]:
    """Zapisz ZIP (JSON + zdjęcia) na dysk. Zwraca ostrzeżenia o brakach plików.

    Budujemy do PLIKU, nie do pamięci (karta B14, Implementation Notes) —
    a odpowiedź wysyła `FileResponse`, więc paczka nigdy nie mieszka w RAM.
    """
    warnings: list[str] = []
    target.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            DATA_ENTRY_NAME, json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        )
        for relative in photos:
            if relative in seen:
                continue
            seen.add(relative)
            try:
                source = resolve_upload_path(relative, uploads_root=uploads_root)
            except Exception:
                warnings.append(f"Pominięto zdjęcie o nietypowej ścieżce: {relative}")
                continue
            if not source.is_file():
                warnings.append(f"Brak pliku zdjęcia w magazynie: {relative}")
                continue
            archive.write(source, f"{PHOTOS_PREFIX}{PurePosixPath(relative)}")
    return warnings
