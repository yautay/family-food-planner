"""Reguły bramki zatwierdzenia importu — czyste funkcje `review_service`.

Macierz z karty B16 ma trzy osie: czy składnik ma potwierdzony produkt, czy ma
flagę „załóż nowy" i czy danie jest pominięte. Wszystkie trzy rozstrzyga
`_is_mapped` razem z decyzją o pominięciu — pełny przebieg przez bazę (409
z listą blokad) sprawdzają testy integracyjne.

Drugi temat pliku to skalowanie ilości przy zapisie: mianownik przepisu
(`_servings_for`) i wyjątek dla sekcji `Produkty` (`_imported_ingredients`).
Ta arytmetyka decyduje o tym, ile realnie waży porcja gołąbków, więc ma własne,
nazwane przypadki zamiast być sprawdzana „przy okazji" testu round-tripu.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.importer.models import StagedIngredient, StagedRecipe
from app.modules.importer.review_service import (
    _imported_ingredients,
    _instructions_for,
    _is_mapped,
    _servings_for,
)

pytestmark = pytest.mark.unit


def _ingredient(
    *,
    confirmed_product_id: int | None = None,
    create_new_product: bool = False,
    grams: Decimal = Decimal("100"),
    from_extras: bool = False,
    raw_qty: Decimal | None = None,
    raw_unit: str | None = None,
) -> StagedIngredient:
    return StagedIngredient(
        id=1,
        staged_recipe_id=1,
        raw_name="Cebula",
        raw_qty=raw_qty,
        raw_unit=raw_unit,
        grams=grams,
        confirmed_product_id=confirmed_product_id,
        create_new_product=create_new_product,
        from_extras_section=from_extras,
    )


# --- macierz mapowania -------------------------------------------------------------


@pytest.mark.parametrize(
    ("confirmed", "create_new", "mapped"),
    [
        (None, False, False),  # nic nie zdecydowano → blocker `unmapped_product`
        (7, False, True),  # wskazany produkt z katalogu
        (None, True, True),  # świadoma decyzja „załóż nowy" (UNVERIFIED przy approve)
        (7, True, True),  # wskazanie wygrywa — jest konkretniejsze
    ],
)
def test_macierz_rozstrzygniecia_mapowania(
    confirmed: int | None, create_new: bool, mapped: bool
) -> None:
    """Składnik jest rozstrzygnięty, gdy wiadomo, DOKĄD ma trafić jego gramatura."""
    item = _ingredient(confirmed_product_id=confirmed, create_new_product=create_new)

    assert _is_mapped(item) is mapped


# --- mianownik przepisu -------------------------------------------------------------


@pytest.mark.parametrize(
    ("resolved", "declared", "expected"),
    [
        (7, None, 7),  # rozstrzygnięcie człowieka
        (3, 7, 3),  # …wygrywa z dokumentem, bo jest nowsze i świadome
        (None, 2, 2),  # „Przepis na 2 porcje" z dokumentu
        (None, None, 1),  # brak informacji = przepis jednoporcjowy
    ],
)
def test_mianownik_przepisu_bierze_najlepsza_dostepna_informacje(
    resolved: int | None, declared: int | None, expected: int
) -> None:
    """`resolved_servings` > `declared_servings` > 1 (karta B16 §Backend)."""
    row = StagedRecipe(
        id=1,
        import_job_id=1,
        name="Gołąbki",
        day_label="Środa",
        meal_label="OBIAD",
        resolved_servings=resolved,
        declared_servings=declared,
    )

    assert _servings_for(row) == expected


# --- skalowanie ilości ---------------------------------------------------------------


def _dish(servings: int, ingredients: list[StagedIngredient]) -> StagedRecipe:
    row = StagedRecipe(
        id=1,
        import_job_id=1,
        name="Gołąbki bez zawijania",
        day_label="Środa",
        meal_label="OBIAD",
        instructions="Kapustę poszatkować.",
        comment="",
        resolved_servings=servings,
    )
    row.ingredients = ingredients
    return row


def test_zwykly_skladnik_wchodzi_do_przepisu_w_gramaturze_z_dokumentu() -> None:
    """Składniki przepisu wieloporcjowego są w PDF podane na całość (§5.1)."""
    dish = _dish(7, [_ingredient(confirmed_product_id=1, grams=Decimal("3080"))])

    assert _imported_ingredients(dish)[0].grams == Decimal("3080")


def test_skladnik_z_sekcji_produkty_mnozy_sie_przez_liczbe_porcji() -> None:
    """Dodatek jest podany NA PORCJĘ, a przepis trzyma ilości na całość (dług U22).

    225 g ziemniaków do gołąbków musi wejść do przepisu jako 1575 g, żeby po
    podzieleniu przez 7 porcji wróciło do 225 g na talerzu.
    """
    dish = _dish(
        7,
        [_ingredient(confirmed_product_id=1, grams=Decimal("225"), from_extras=True)],
    )

    assert _imported_ingredients(dish)[0].grams == Decimal("1575")


def test_przepis_jednoporcjowy_nie_zmienia_zadnej_gramatury() -> None:
    """Przy jednej porcji obie ścieżki dają to samo — brak przypadku szczególnego."""
    dish = _dish(
        1,
        [
            _ingredient(confirmed_product_id=1, grams=Decimal("60")),
            _ingredient(confirmed_product_id=2, grams=Decimal("40"), from_extras=True),
        ],
    )

    assert [item.grams for item in _imported_ingredients(dish)] == [
        Decimal("60"),
        Decimal("40"),
    ]


def test_skladnik_bez_produktu_nie_wchodzi_do_przepisu() -> None:
    """Do tego miejsca dojeżdżają wyłącznie dania bez blokad — asercja obronna."""
    dish = _dish(1, [_ingredient(confirmed_product_id=None)])

    assert _imported_ingredients(dish) == []


def test_para_ilosc_jednostka_zostaje_jako_zapis_uzytkownika() -> None:
    """`display_qty`/`display_unit` mają pokazać to, co widział człowiek (§8.3)."""
    dish = _dish(
        1,
        [
            _ingredient(
                confirmed_product_id=1,
                grams=Decimal("210"),
                raw_qty=Decimal("2"),
                raw_unit="Sztuka",
            )
        ],
    )
    item = _imported_ingredients(dish)[0]

    assert (item.display_qty, item.display_unit) == (Decimal("2"), "Sztuka")


def test_komentarz_dietetyczki_doklejamy_do_instrukcji() -> None:
    """Uwaga „proszę dać szklankę fasoli" (§3.3) nie może zniknąć przy imporcie."""
    row = StagedRecipe(
        id=1,
        import_job_id=1,
        name="Danie",
        day_label="Środa",
        meal_label="OBIAD",
        instructions="Ugotować.",
        comment="Jeżeli danie okaże się zbyt duże, proszę dać szklankę fasoli.",
    )

    assert _instructions_for(row) == (
        "Ugotować.\n\nJeżeli danie okaże się zbyt duże, proszę dać szklankę fasoli."
    )
