"""Fixture'y SYNTETYCZNE narzędzia `/pdf-extract` — nie dane pacjenta (BATCH_22, D27).

Dwie wersje jadłospisu o częściowo wspólnych produktach: wersja 0001 definiuje
mąkę, jajko, mleko i pieczarki, wersja 0002 REUŻYWA mąkę i jajko i dokłada masło.
Wartości są dobrane tak, żeby energia zgadzała się z 4B+4W+9T, a sumy z „PDF-a”
z silnikiem co do grosza — scenariusze odstępstw buduje się w testach przez
modyfikację tych słowników, a nie przez osobne dane.
"""

from __future__ import annotations

import copy
from typing import Any

from scripts.pdf_extract.spec import Spec, parse_spec

SOURCE = "syntetyczny jadłospis testowy (nie dane pacjenta)"


def product(
    key: str,
    name: str,
    category: str,
    kind: str,
    *,
    kcal: str,
    protein: str,
    fat: str,
    carbs: str,
    piece_weight: str | None = None,
    unit_weights: dict[str, str] | None = None,
    merged_from: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "category": category,
        "measure_kind": kind,
        "piece_weight_g": piece_weight,
        "per_100": {
            "basis": "ml" if kind == "volume" else "g",
            "kcal": kcal,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "fiber": "0",
            "sugars": "0",
        },
        "glycemic_index": "50",
        "unit_weights": unit_weights or {},
        "merged_from": merged_from or [],
        "nutrition_source": "fixture testowy",
    }


def ingredient(key: str, qty: str, unit: str, grams: str | None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"product": key, "pdf_qty": qty, "pdf_unit": unit, "pdf_grams": grams}
    payload.update(extra)
    return payload


def recipe(
    day: str,
    meal: str,
    name: str,
    ingredients: list[dict[str, Any]],
    *,
    instructions: str = "Wymieszać i podgrzać.",
    kcal: str | None = None,
) -> dict[str, Any]:
    return {
        "day": day,
        "meal": meal,
        "name": name,
        "base_servings": 1,
        "instructions": instructions,
        "comment": "",
        "pdf_totals": {"kcal": kcal} if kcal else {},
        "ingredients": ingredients,
    }


FLOUR = product(
    "maka",
    "Mąka testowa",
    "Makarony, ryż i kasze",
    "mass",
    kcal="350",
    protein="10",
    fat="1.5",
    carbs="72",
    unit_weights={"łyżka": "10"},
)
EGG = product(
    "jajko",
    "Jajko testowe",
    "Nabiał i jaja",
    "piece",
    kcal="140",
    protein="12",
    fat="10",
    carbs="1",
    piece_weight="50",
)
MILK = product(
    "mleko",
    "Mleko testowe",
    "Nabiał i jaja",
    "volume",
    kcal="46",
    protein="3.4",
    fat="1.5",
    carbs="4.8",
    unit_weights={"szklanka": "250"},
)
MUSHROOMS = product(
    "pieczarki",
    "Pieczarki testowe",
    "Grzyby",
    "mass",
    kcal="22",
    protein="3.1",
    fat="0.3",
    carbs="3.3",
)
BUTTER = product(
    "maslo",
    "Masło testowe",
    "Tłuszcze",
    "mass",
    kcal="740",
    protein="0.7",
    fat="82",
    carbs="0.6",
)


def version_one_payload() -> dict[str, Any]:
    """Wersja 0001: dwa przepisy; trzy składniki wymuszają gramy (sztuka przy MASS, łyżka 50%)."""
    return {
        "version": "0001",
        "slug": "syntetyczny",
        "analyzed_on": "2026-10-03",
        "source": SOURCE,
        "decisions": ["Fixture: bez scaleń."],
        "products": [copy.deepcopy(p) for p in (FLOUR, EGG, MILK, MUSHROOMS)],
        "recipes": [
            recipe(
                "pon",
                "śniadanie",
                "Naleśniki testowe",
                [
                    ingredient("maka", "4", "Łyżka", "40"),
                    ingredient("jajko", "1", "Sztuka", "50"),
                    ingredient("mleko", "1", "Szklanka", "250"),
                ],
                kcal="325",
            ),
            recipe(
                "pon",
                "obiad",
                "Omlet z pieczarkami testowy",
                [
                    ingredient("jajko", "2", "Sztuka", "100"),
                    ingredient("pieczarki", "3", "Sztuka", "60"),
                    ingredient("maka", "1", "Łyżka", "20"),
                ],
                instructions="Pieczarki podsmażyć, dodać jajka i mąkę.",
                kcal="223",
            ),
        ],
        "pdf_day_totals": {"pon": {"kcal": "548"}},
        "pdf_shopping_list_grams": {
            "maka": "60",
            "jajko": "150",
            "mleko": "250",
            "pieczarki": "60",
        },
    }


def version_two_payload() -> dict[str, Any]:
    """Wersja 0002: REUŻYWA mąkę i jajko z 0001, nowe jest tylko masło (obiad innego dnia)."""
    return {
        "version": "0002",
        "slug": "syntetyczny-ii",
        "analyzed_on": "2026-10-04",
        "source": SOURCE,
        "decisions": ["Fixture: reużycie mąki i jajka."],
        "products": [copy.deepcopy(BUTTER)],
        "reused": [
            {"key": "maka", "name": "Mąka testowa"},
            {"key": "jajko", "name": "Jajko testowe"},
        ],
        "recipes": [
            recipe(
                "wt",
                "kolacja",
                "Naleśnik z masłem testowy",
                [
                    ingredient("maka", "2", "Łyżka", "20"),
                    ingredient("jajko", "1", "Sztuka", "50"),
                    ingredient("maslo", "10", "g", "10"),
                ],
                instructions="Mąkę, jajko i masło usmażyć.",
                kcal="214",
            )
        ],
        "pdf_day_totals": {"wt": {"kcal": "214"}},
        "pdf_shopping_list_grams": {"maka": "20", "jajko": "50", "maslo": "10"},
    }


def version_one() -> Spec:
    return parse_spec(version_one_payload())


def version_two() -> Spec:
    return parse_spec(version_two_payload())
