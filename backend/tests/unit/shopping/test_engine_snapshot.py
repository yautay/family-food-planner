"""Snapshot podglądu zakupów na danych seedu demo (08_TESTING §2.4-2.7 i §5).

Po co snapshot obok testów jednostkowych: te sprawdzają pojedyncze reguły, ten
pilnuje CAŁEGO wyniku na realistycznym tygodniu planu. Zmiana pliku
`snapshots/demo_week_preview.json` w diffie jest sygnałem „zmieniło się
zachowanie silnika" i wymaga świadomej decyzji w review (karta B10 §Tests).

Test jest CZYSTY — nie dotyka bazy. Wejście składamy z tych samych stałych,
które `scripts/seed_demo.py` zapisuje do bazy (`DEMO_PRODUCTS`, `DEMO_RETAIL`,
`DEMO_RECIPES`, `DEMO_PLAN`), a ilości normalizujemy TĄ SAMĄ funkcją
(`normalized_demo_amount` → `catalog/units.py`). Dzięki temu snapshot opisuje
faktyczny seed, a nie osobną, równoległą definicję danych.

Regeneracja po świadomej zmianie zachowania::

    FFP_UPDATE_SNAPSHOTS=1 task test-unit -- tests/unit/shopping/test_engine_snapshot.py
"""

from __future__ import annotations

import json
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.modules.catalog.models import Perishability
from app.modules.catalog.units import base_unit
from app.modules.shopping.engine import (
    EngineInput,
    IngredientInput,
    PlanItemInput,
    PreviewResult,
    ProductInput,
    RecipeInput,
    RetailInput,
    RoundInput,
    generate_preview,
    quantize_amount,
    quantize_package,
)
from app.modules.shopping.service import PRESET_ROUNDS
from scripts.seed_demo import (
    DEMO_PLAN,
    DEMO_PRODUCTS,
    DEMO_RECIPES,
    DEMO_RETAIL,
    DEMO_STORE_NAME,
    DEMO_WEEK_START,
    DemoIngredient,
    normalized_demo_amount,
)
from tests.integration.test_catalog_seed import EXPECTED_CATEGORIES

pytestmark = pytest.mark.unit

SNAPSHOT = Path(__file__).parent / "snapshots" / "demo_week_preview.json"

#: Kategorie z migracji `0005` — pozycja to indeks (od 1), jak w migracji.
#: Źródłem prawdy jest `EXPECTED_CATEGORIES` z testu seedu, żeby słownik nie
#: istniał w testach dwa razy.
_CATEGORIES = {
    name: (position, Perishability(value))
    for position, (name, value) in enumerate(EXPECTED_CATEGORIES.items(), start=1)
}

#: Syntetyczne identyfikatory: w bazie nadaje je sekwencja, tu liczymy je
#: z kolejności stałych demo — snapshot musi być odtwarzalny bez bazy.
_PRODUCT_IDS = {demo.name: index for index, demo in enumerate(DEMO_PRODUCTS, start=1)}
_RECIPE_IDS = {demo.name: index for index, demo in enumerate(DEMO_RECIPES, start=1)}
_RETAIL_IDS = {demo.name: index for index, demo in enumerate(DEMO_RETAIL, start=1)}


def _products() -> tuple[ProductInput, ...]:
    """Katalog demo w postaci wejścia silnika (trwałość z kategorii, jak serwis)."""
    products: list[ProductInput] = []
    for demo in DEMO_PRODUCTS:
        position, perishability = _CATEGORIES[demo.category]
        products.append(
            ProductInput(
                product_id=_PRODUCT_IDS[demo.name],
                name=demo.name,
                measure_kind=demo.measure_kind,
                piece_weight_g=demo.piece_weight_g,
                category_id=position,
                category_name=demo.category,
                category_position=position,
                perishability=perishability,
            )
        )
    return tuple(products)


def _recipes() -> tuple[RecipeInput, ...]:
    """Przepisy demo ze składnikami znormalizowanymi jak przy zapisie w bazie."""
    return tuple(
        RecipeInput(
            recipe_id=_RECIPE_IDS[demo.name],
            name=demo.name,
            base_servings=demo.base_servings,
            ingredients=tuple(_ingredient(ingredient) for ingredient in demo.ingredients),
        )
        for demo in DEMO_RECIPES
    )


def _ingredient(ingredient: DemoIngredient) -> IngredientInput:
    """Składnik demo → wejście silnika (ilość znormalizowana jak przy zapisie)."""
    normalized = normalized_demo_amount(ingredient.product, ingredient.quantity, ingredient.unit)
    return IngredientInput(
        product_id=_PRODUCT_IDS[ingredient.product],
        amount=normalized.amount,
        amount_unit=normalized.unit,
    )


def _items() -> tuple[PlanItemInput, ...]:
    """Tydzień planu demo — kolejność jak w `demand_rows` (dzień, potem pozycja)."""
    items: list[PlanItemInput] = []
    item_id = 1
    for demo_day in DEMO_PLAN:
        day = DEMO_WEEK_START + timedelta(days=demo_day.offset)
        for meal in demo_day.meals:
            for demo_item in meal.items:
                if demo_item.recipe is not None:
                    items.append(
                        PlanItemInput(
                            item_id=item_id,
                            day=day,
                            meal_name=meal.name,
                            servings=_decimal(demo_item.servings),
                            recipe_id=_RECIPE_IDS[demo_item.recipe],
                        )
                    )
                else:
                    assert demo_item.product is not None
                    assert demo_item.quantity is not None
                    assert demo_item.unit is not None
                    normalized = normalized_demo_amount(
                        demo_item.product, demo_item.quantity, demo_item.unit
                    )
                    items.append(
                        PlanItemInput(
                            item_id=item_id,
                            day=day,
                            meal_name=meal.name,
                            servings=_decimal(demo_item.servings),
                            product_id=_PRODUCT_IDS[demo_item.product],
                            amount=normalized.amount,
                            amount_unit=normalized.unit,
                        )
                    )
                item_id += 1
    return tuple(items)


def _retail() -> tuple[RetailInput, ...]:
    """Opakowania demo — wszystkie z jednego sklepu (jak w seedzie)."""
    return tuple(
        RetailInput(
            retail_product_id=_RETAIL_IDS[demo.name],
            product_id=_PRODUCT_IDS[demo.product],
            label=demo.name,
            package_amount=_decimal(demo.package_amount),
            package_unit=_base_unit_of(demo.product),
            store_id=1,
            store_name=DEMO_STORE_NAME,
        )
        for demo in DEMO_RETAIL
    )


def _rounds() -> tuple[RoundInput, ...]:
    """Preset tur z serwisu — klucze jak dla zapisanych konfiguracji (`cfg-<id>`)."""
    return tuple(
        RoundInput(
            key=f"cfg-{index}",
            name=str(preset["name"]),
            mode=preset["mode"],  # type: ignore[arg-type]
            covers_days=int(preset["covers_days"]),  # type: ignore[call-overload]
            fresh_days=(
                None if preset["fresh_days"] is None else int(preset["fresh_days"])  # type: ignore[call-overload]
            ),
            shopping_weekday=int(preset["shopping_weekday"]),  # type: ignore[call-overload]
        )
        for index, preset in enumerate(PRESET_ROUNDS, start=1)
    )


def demo_engine_input() -> EngineInput:
    """Pełne wejście silnika dla tygodnia demo (bez spiżarni — seed jej nie ma)."""
    return EngineInput(
        date_from=DEMO_WEEK_START,
        date_to=DEMO_WEEK_START + timedelta(days=6),
        use_pantry=False,
        rounds=_rounds(),
        items=_items(),
        recipes=_recipes(),
        products=_products(),
        retail=_retail(),
    )


def _decimal(value: str) -> Decimal:
    """Literał dziesiętny — nigdy `Decimal(float)` (ADR-008)."""
    return Decimal(value)


def _base_unit_of(product_name: str) -> Any:
    """Oś ilości produktu demo — ta sama, na której leżą jego opakowania (B09)."""
    return base_unit(next(demo for demo in DEMO_PRODUCTS if demo.name == product_name).measure_kind)


def _dump(result: PreviewResult) -> dict[str, Any]:
    """Wynik silnika → JSON. Ilości zaokrąglone jak na krawędzi API (ADR-008)."""
    return {
        "date_from": result.date_from.isoformat(),
        "date_to": result.date_to.isoformat(),
        "use_pantry": result.use_pantry,
        "rounds": [
            {
                "key": round_view.key,
                "name": round_view.name,
                "mode": round_view.mode.value,
                "shopping_date": (
                    None
                    if round_view.shopping_date is None
                    else round_view.shopping_date.isoformat()
                ),
                "date_from": (
                    None if round_view.date_from is None else round_view.date_from.isoformat()
                ),
                "date_to": None if round_view.date_to is None else round_view.date_to.isoformat(),
                "items": [
                    {
                        "product_id": line.product_id,
                        "label": line.label,
                        "amount_unit": line.unit.value,
                        "needed_amount": format(quantize_amount(line.needed_amount), "f"),
                        "category_name": line.category_name,
                        "perishability": (
                            None if line.perishability is None else line.perishability.value
                        ),
                        "days": [day.isoformat() for day in line.days],
                        "retail_product_id": line.retail_product_id,
                        "packages_count": line.packages_count,
                        "package_amount": (
                            None
                            if line.package_amount is None
                            else format(quantize_package(line.package_amount), "f")
                        ),
                        "leftover_amount": (
                            None
                            if line.leftover_amount is None
                            else format(quantize_amount(line.leftover_amount), "f")
                        ),
                        "already_have": line.already_have,
                        "from_pantry_amount": (
                            None
                            if line.from_pantry_amount is None
                            else format(quantize_amount(line.from_pantry_amount), "f")
                        ),
                    }
                    for line in round_view.items
                ],
            }
            for round_view in result.rounds
        ],
        "issues": [
            {
                "key": issue.key,
                "kind": issue.kind.value,
                "severity": issue.severity.value,
                "message": issue.message,
            }
            for issue in result.issues
        ],
    }


def test_snapshot_podgladu_na_seedzie_demo() -> None:
    """Podgląd zakupów dla tygodnia demo zgadza się ze zapisanym snapshotem.

    Czerwony test znaczy jedno z dwojga: zmienił się silnik albo zmienił się
    seed. Oba przypadki wymagają decyzji człowieka, nie regeneracji w biegu.
    """
    payload = _dump(generate_preview(demo_engine_input()))

    if os.environ.get("FFP_UPDATE_SNAPSHOTS") == "1":  # pragma: no cover - narzędzie
        SNAPSHOT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    assert SNAPSHOT.is_file(), (
        f"Brak snapshotu {SNAPSHOT.name}. Wygeneruj go świadomie: "
        "FFP_UPDATE_SNAPSHOTS=1 task test-unit -- tests/unit/shopping/test_engine_snapshot.py"
    )
    assert payload == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_jest_deterministyczny() -> None:
    """Dwa przebiegi na tym samym wejściu dają identyczny wynik (ADR-008)."""
    assert _dump(generate_preview(demo_engine_input())) == _dump(
        generate_preview(demo_engine_input())
    )
