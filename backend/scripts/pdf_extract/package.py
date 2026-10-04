"""Paczka transferu v1 z `spec.json` (D31 pkt 3): `export.json` w ZIP-ie.

Czyste funkcje (bez I/O): `build_document` składa dokument, `build_archive` pakuje go
do bajtów. Zapis pliku robi `cli.py`.

Nośnikiem jest ZWYKŁY format transferu (`app/modules/transfer`), więc wgrywa go
właściciel zwykłym importem (`/admin/dane` albo „Kopia danych rodziny”): import
scala produkty po `normalized_name` (D22), pokazuje raport DRY-RUN (D24), przypisuje
własność kontu importującemu i przechodzi przez serwisy. Narzędzie niczego nie wgrywa.

Struktury sekcji budowane są z `serializer.SECTIONS` (`_row`): kolumny i referencje
sekcji nie są tu przepisane, więc zmiana formatu transferu, której generator nie
nadąży obsłużyć, wywróci się głośnym błędem, a nie wygeneruje plik, który import
zrozumie inaczej.

**Zakresy przepisów** (`--recipe-scope`, D32/D33):

- `household` (domyślny) i `private` — plik `scope=user`; ID właściciela i rodziny
  w pliku są PLACEHOLDERAMI (`1`) — import tłumaczy je na konto wczytujące
  (`IdMap` z fallbackiem na aktora); `null` w `household_id` zamieniłby przepis
  po cichu na prywatny;
- `global` — plik `scope=instance` z sekcją `users` (konto ADMIN-a, `--owner-email`)
  jako właścicielem przepisów. Paczka `scope=user` z `global` zostałaby obcięta do
  `household` (D33: stan z B21 zostaje). Wiersz konta ma rolę `user` i
  `is_active=false`: gdy e-mail nie pasuje do istniejącego konta (literówka),
  import założy konto BEZ uprawnień zamiast kolejnego ADMIN-a; rolę istniejącego
  konta import czyta z bazy i ona decyduje o zachowaniu `global`.

Determinizm: ta sama spec = te same bajty (stałe `exported_at`, `app_version`,
znaczniki czasu wpisu ZIP i atrybuty). Test sprawdza to wprost.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import normalize_unit_label
from app.modules.transfer.schemas import DATA_ENTRY_NAME, TransferScope
from app.modules.transfer.serializer import (
    SECTIONS_BY_NAME,
    section_columns,
    section_references,
)
from app.modules.transfer.serializer import (
    build_document as build_transfer_document,
)
from scripts.pdf_extract.spec import ProductSpec, Spec, SpecError
from scripts.pdf_extract.verify import IngredientError, resolve_ingredient

#: Kategorie z migracji `0005` (nazwa, trwałość) — kolejność = `position` od 1.
#: Paczka niesie wiersze kategorii, bo kategoria jest kluczem obcym produktu;
#: na instancji one JUŻ SĄ i import reużywa je po nazwie. Nazwa spoza listy założyłaby
#: nową kategorię w słowniku globalnym, więc jest błędem (test pilnuje zgodności z `0005`).
KNOWN_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Warzywa", "fresh"),
    ("Owoce", "fresh"),
    ("Grzyby", "fresh"),
    ("Nabiał i jaja", "fresh"),
    ("Mięso i produkty mięsne", "fresh"),
    ("Pieczywo", "fresh"),
    ("Mrożonki", "durable"),
    ("Makarony, ryż i kasze", "durable"),
    ("Suche i strączkowe", "durable"),
    ("Orzechy i nasiona", "durable"),
    ("Przetwory, puszki i słoiki", "durable"),
    ("Przyprawy i zioła", "durable"),
    ("Tłuszcze", "durable"),
    ("Inne", "durable"),
)

#: Posiłek → (nazwa tagu, czy systemowy). Trzy pierwsze to tagi z migracji `0007`,
#: „podwieczorek” jest niesystemowy i import go założy.
MEAL_TAGS: Mapping[str, tuple[str, bool]] = {
    "śniadanie": ("śniadanie", True),
    "obiad": ("obiad", True),
    "podwieczorek": ("podwieczorek", False),
    "kolacja": ("kolacja", True),
}

#: Stałe znaczniki ZIP-a — bez nich bajty zależałyby od chwili budowy.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_PLACEHOLDER_ID = 1


class PackageError(SpecError):
    """Z tej spec nie da się zbudować poprawnej paczki."""


class RecipeScopeChoice(StrEnum):
    """Zakres przepisów w paczce (`--recipe-scope`)."""

    HOUSEHOLD = "household"
    PRIVATE = "private"
    GLOBAL = "global"


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _row(section_name: str, pk: int | None, **values: Any) -> dict[str, Any]:
    """Wiersz sekcji w kształcie `serializer.row_to_dict` — kolumny z `SECTIONS`, nie z głowy."""
    section = SECTIONS_BY_NAME[section_name]
    expected = set(section_columns(section)) | set(section_references(section))
    if set(values) != expected:
        raise PackageError(
            f"Format transferu zmienił sekcję {section_name}: generator ma "
            f"{sorted(values)}, a serializer wymaga {sorted(expected)}."
        )
    payload: dict[str, Any] = {}
    if section.pk is not None:
        payload[section.pk] = pk
    for column in section_columns(section):
        payload[column] = values[column]
    for column in section_references(section):
        payload[column] = values[column]
    return payload


def normalize_email(email: str) -> str:
    """E-mail jak zapisuje go aplikacja (`strip().lower()`) — indeks dopasowuje dokładny string."""
    cleaned = email.strip().lower()
    local, _, domain = cleaned.partition("@")
    if not local or "." not in domain or " " in cleaned:
        raise PackageError(f"„{email}” nie wygląda na adres e-mail (--owner-email).")
    return cleaned


def build_document(
    spec: Spec,
    catalog: Mapping[str, ProductSpec],
    *,
    recipe_scope: RecipeScopeChoice = RecipeScopeChoice.HOUSEHOLD,
    owner_email: str | None = None,
) -> dict[str, Any]:
    """`spec` + katalog wersji → dokument `export.json` v1 (jeszcze nie bajty)."""
    is_global = recipe_scope is RecipeScopeChoice.GLOBAL
    if is_global and not owner_email:
        raise PackageError(
            "Zakres `global` wymaga --owner-email: e-mail konta ADMIN-a, które wczyta paczkę "
            "i zostanie właścicielem przepisów (D33)."
        )
    if owner_email and not is_global:
        raise PackageError("--owner-email ma sens wyłącznie z --recipe-scope global.")

    used_keys = sorted(
        {ingredient.product for recipe in spec.recipes for ingredient in recipe.ingredients}
    )
    products = [catalog[key] for key in used_keys]

    category_names = {
        name: (position, kind) for position, (name, kind) in enumerate(KNOWN_CATEGORIES, 1)
    }
    unknown = sorted({p.category for p in products if p.category not in category_names})
    if unknown:
        raise PackageError(
            "Kategorie spoza słownika migracji 0005: " + ", ".join(unknown) + ". "
            "Import założyłby nową kategorię w słowniku globalnym — wybierz istniejącą."
        )
    used_categories = [
        name for name, _ in KNOWN_CATEGORIES if name in {p.category for p in products}
    ]
    category_ids = {name: position for position, name in enumerate(used_categories, 1)}

    used_meals = [meal for meal in MEAL_TAGS if any(r.meal == meal for r in spec.recipes)]
    tag_ids = {meal: position for position, meal in enumerate(used_meals, 1)}
    product_ids = {key: position for position, key in enumerate(used_keys, 1)}

    data: dict[str, list[dict[str, Any]]] = {
        "product_categories": [
            _row(
                "product_categories",
                category_ids[name],
                name=name,
                position=category_names[name][0],
                perishability=category_names[name][1],
            )
            for name in used_categories
        ],
        "tags": [
            _row(
                "tags",
                tag_ids[meal],
                name=MEAL_TAGS[meal][0],
                is_system=MEAL_TAGS[meal][1],
            )
            for meal in used_meals
        ],
        "canonical_products": [],
        "product_unit_weights": [],
        "recipes": [],
        "recipe_ingredients": [],
        "recipe_tags": [],
    }

    for key in used_keys:
        product = catalog[key]
        per = product.per_100
        data["canonical_products"].append(
            _row(
                "canonical_products",
                product_ids[key],
                name=product.name.strip(),
                normalized_name=normalize_name(product.name),
                measure_kind=product.measure_kind,
                piece_weight_g=_decimal(product.piece_weight_g),
                kcal_100=_decimal(per.kcal),
                protein_100=_decimal(per.protein),
                fat_100=_decimal(per.fat),
                carbs_100=_decimal(per.carbs),
                fiber_100=_decimal(per.fiber),
                sugars_100=_decimal(per.sugars),
                glycemic_index=_decimal(product.glycemic_index),
                # ZAWSZE `unverified` (D31 pkt 7): ADMIN weryfikuje w /admin/weryfikacja.
                verification_status="unverified",
                nutrition_source=product.nutrition_source,
                verified_at=None,
                perishability_override=None,
                is_archived=False,
                category_id=category_ids[product.category],
            )
        )

    weight_id = 0
    for key in used_keys:
        for label, grams in sorted(catalog[key].unit_weights.items()):
            weight_id += 1
            data["product_unit_weights"].append(
                _row(
                    "product_unit_weights",
                    weight_id,
                    unit_label=normalize_unit_label(label),
                    grams_per_unit=_decimal(grams),
                    source=f"pdf-extract {spec.version}",
                    samples_count=1,
                    product_id=product_ids[key],
                )
            )

    ingredient_id = 0
    for recipe_position, recipe in enumerate(spec.recipes, 1):
        instructions = recipe.instructions.strip()
        if recipe.comment.strip():
            instructions = f"{instructions}\n\nUwaga: {recipe.comment.strip()}".strip()
        data["recipes"].append(
            _row(
                "recipes",
                recipe_position,
                name=recipe.name.strip(),
                instructions=instructions,
                base_servings=recipe.base_servings,
                prep_time_min=None,
                difficulty=None,
                photo_path=None,
                is_archived=False,
                scope=recipe_scope.value,
                owner_user_id=_PLACEHOLDER_ID,
                household_id=_PLACEHOLDER_ID
                if recipe_scope is RecipeScopeChoice.HOUSEHOLD
                else None,
            )
        )
        for position, ingredient in enumerate(recipe.ingredients):
            try:
                resolution = resolve_ingredient(
                    recipe.name, ingredient, catalog[ingredient.product], spec.thresholds
                )
            except IngredientError as exc:
                raise PackageError(str(exc)) from exc
            ingredient_id += 1
            data["recipe_ingredients"].append(
                _row(
                    "recipe_ingredients",
                    ingredient_id,
                    display_qty=_decimal(resolution.display_qty),
                    display_unit=resolution.display_unit,
                    amount=_decimal(resolution.amount),
                    amount_unit=resolution.amount_unit.value,
                    note=resolution.note,
                    position=position,
                    recipe_id=recipe_position,
                    product_id=product_ids[ingredient.product],
                )
            )
        data["recipe_tags"].append(
            _row(
                "recipe_tags",
                None,
                recipe_id=recipe_position,
                tag_id=tag_ids[recipe.meal],
            )
        )

    scope = TransferScope.INSTANCE if is_global else TransferScope.USER
    if is_global:
        assert owner_email is not None
        data["users"] = [
            _row(
                "users",
                _PLACEHOLDER_ID,
                email=normalize_email(owner_email),
                display_name="Administrator",
                role="user",
                is_active=False,
                ui_settings={},
                household_id=None,
            )
        ]

    return build_transfer_document(
        scope=scope,
        app_version=f"pdf-extract/{spec.version}",
        exported_at=datetime.combine(spec.analyzed_on, time(0, 0), tzinfo=UTC),
        data=data,
    )


def build_archive(document: Mapping[str, Any]) -> bytes:
    """`export.json` w ZIP-ie — bajtowo deterministycznie (stałe znaczniki czasu i atrybuty)."""
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    info = zipfile.ZipInfo(DATA_ENTRY_NAME, date_time=ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # Unix — niezależnie od platformy budującej
    info.external_attr = 0o644 << 16
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    return buffer.getvalue()


def section_counts(document: Mapping[str, Any]) -> dict[str, int]:
    """Liczba wierszy per sekcja (bez pustych) — do podsumowania w CLI i raporcie."""
    data = document.get("data") or {}
    return {name: len(rows) for name, rows in data.items() if rows}
