"""Kontrakt payloadu szablonu `v:1`: plan → payload → JSONB → payload.

Scenariusze z karty B07 §Tests (unit): budowa payloadu z dnia planu (struktura,
pozycje, rozkłady) i droga powrotna. `day_payload_from_rows` jest czystą funkcją
nad wierszami ORM, więc test tworzy je w pamięci — bez bazy i bez aplikacji.

Motyw przewodni: payload NIE MOŻE zgubić ani precyzji Decimala (ADR-008), ani
mnożnika porcji (02_DOMAIN §13.3). Jedno i drugie po cichu zmieniłoby treść
szablonu, a użytkownik zobaczyłby to dopiero po instancjacji.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.modules.catalog.units import AmountUnit
from app.modules.planning.models import PlanItemServing, PlanMeal, PlanMealItem
from app.modules.planning.schemas import DayTemplatePayload, WeekTemplatePayload
from app.modules.planning.service import day_payload_from_rows

pytestmark = pytest.mark.unit


def _meal(meal_id: int, name: str, kcal_target: Decimal | None = None) -> PlanMeal:
    return PlanMeal(id=meal_id, plan_day_id=1, name=name, position=0, kcal_target=kcal_target)


def _recipe_item(item_id: int, recipe_id: int, servings: str, position: int = 0) -> PlanMealItem:
    return PlanMealItem(
        id=item_id,
        plan_meal_id=1,
        recipe_id=recipe_id,
        servings=Decimal(servings),
        position=position,
    )


def _product_item(
    item_id: int, product_id: int, amount: str, unit: AmountUnit, servings: str
) -> PlanMealItem:
    return PlanMealItem(
        id=item_id,
        plan_meal_id=1,
        product_id=product_id,
        amount=Decimal(amount),
        amount_unit=unit,
        servings=Decimal(servings),
        position=0,
    )


# --- budowa payloadu z wierszy planu -------------------------------------------------


def test_payload_odwzorowuje_strukture_dnia() -> None:
    """Tytuł, posiłki, cele kcal i pozycje trafiają do payloadu w tej samej kolejności."""
    meals = [_meal(1, "Śniadanie", Decimal("500")), _meal(2, "Obiad")]
    items = {1: [_recipe_item(11, recipe_id=7, servings="2")], 2: []}

    payload = day_payload_from_rows(meals, items, {}, title="Dzień warzywny")

    assert payload.v == 1
    assert payload.title == "Dzień warzywny"
    assert [meal.name for meal in payload.meals] == ["Śniadanie", "Obiad"]
    assert payload.meals[0].kcal_target == Decimal("500")
    assert payload.meals[1].kcal_target is None
    assert payload.meals[0].items[0].recipe_id == 7
    assert payload.meals[0].items[0].servings == Decimal("2")


def test_payload_nie_zawiera_ani_jednej_daty() -> None:
    """Szablon to przepis na dzień, nie dzień — data pojawia się dopiero w instancjacji."""
    payload = day_payload_from_rows([_meal(1, "Obiad")], {1: []}, {}, title=None)

    assert "date" not in json.dumps(payload.model_dump(mode="json"))
    assert "day" not in payload.model_dump(mode="json")


def test_pozycja_z_produktem_zachowuje_ilosc_jednostke_i_mnoznik() -> None:
    """Produkt luzem: ilość ZNORMALIZOWANA + mnożnik (02_DOMAIN §13.3).

    `servings` musi jechać razem z ilością, bo wartości pozycji to „wartości
    jednej porcji x servings" również dla produktu — pominięcie mnożnika
    zmieniłoby treść szablonu o tyle, ile wynosi mnożnik.
    """
    items = {
        1: [_product_item(11, product_id=3, amount="330.000", unit=AmountUnit.GRAM, servings="2")]
    }

    payload = day_payload_from_rows([_meal(1, "Kolacja")], items, {}, title=None)

    item = payload.meals[0].items[0]
    assert item.product_id == 3
    assert item.recipe_id is None
    assert item.amount == Decimal("330.000")
    assert item.amount_unit is AmountUnit.GRAM
    assert item.servings == Decimal("2")


def test_rozklad_rodzinny_wchodzi_do_payloadu_w_calosci() -> None:
    """Rozkład kopiuje się z profilami i mnożnikami — suma zostaje równa `servings`."""
    items = {1: [_recipe_item(11, recipe_id=7, servings="6.2")]}
    splits = {
        11: [
            PlanItemServing(plan_meal_item_id=11, member_profile_id=5, multiplier=Decimal("1.0")),
            PlanItemServing(plan_meal_item_id=11, member_profile_id=6, multiplier=Decimal("1.3")),
        ]
    }

    payload = day_payload_from_rows([_meal(1, "Obiad")], items, splits, title=None)

    split = payload.meals[0].items[0].servings_split
    assert [(row.member_profile_id, row.multiplier) for row in split] == [
        (5, Decimal("1.0")),
        (6, Decimal("1.3")),
    ]


def test_pozycje_dostaja_kolejne_pozycje_wedlug_kolejnosci_zrodla() -> None:
    """Payload numeruje pozycje od zera — kolejność źródła jest jedyną prawdą."""
    items = {
        1: [
            _recipe_item(11, recipe_id=7, servings="1", position=5),
            _recipe_item(12, recipe_id=8, servings="1", position=9),
        ]
    }

    payload = day_payload_from_rows([_meal(1, "Obiad")], items, {}, title=None)

    assert [item.position for item in payload.meals[0].items] == [0, 1]
    assert [item.recipe_id for item in payload.meals[0].items] == [7, 8]


def test_pusty_dzien_daje_payload_bez_posilkow() -> None:
    payload = day_payload_from_rows([], {}, {}, title=None)

    assert payload.meals == []
    assert payload.v == 1


# --- droga przez JSONB ---------------------------------------------------------------


def test_decimale_jada_przez_jsonb_jako_stringi() -> None:
    """ADR-008: `mode="json"` daje stringi, więc JSONB nie zamieni ich na float.

    Bez tego „0.30" wróciłoby z bazy jako 0.29999999999999998 i ilość w szablonie
    cicho przestałaby się zgadzać z ilością w planie, z którego szablon powstał.
    """
    items = {
        1: [_product_item(11, product_id=3, amount="0.300", unit=AmountUnit.GRAM, servings="1.5")]
    }
    payload = day_payload_from_rows([_meal(1, "Obiad", Decimal("450"))], items, {}, title=None)

    dumped = payload.model_dump(mode="json")
    item = dumped["meals"][0]["items"][0]

    assert item["amount"] == "0.300"
    # Skalę (NUMERIC(6,2)) nadaje KOLUMNA, nie payload: tu wiersze powstały
    # w pamięci, więc Decimal zachowuje skalę, z którą go zbudowano. Istotne
    # jest to, że wyszedł STRING — „1.5", a nie 1.5.
    assert item["servings"] == "1.5"
    assert dumped["meals"][0]["kcal_target"] == "450"
    # Żadna liczba dziesiętna nie wyszła jako float — inaczej test precyzji poniżej
    # przeszedłby przypadkiem, na zaokrągleniu.
    assert not isinstance(item["amount"], float)


def test_payload_wraca_z_jsonb_bez_utraty_precyzji() -> None:
    """Pełny obieg: wiersze → payload → JSON (jak w bazie) → payload."""
    items = {
        1: [
            _product_item(
                11,
                product_id=3,
                amount="1234.567",
                unit=AmountUnit.MILLILITER,
                servings="0.33",
            )
        ]
    }
    original = day_payload_from_rows([_meal(1, "Obiad")], items, {}, title="Poniedziałek")

    as_stored = json.loads(json.dumps(original.model_dump(mode="json")))
    round_trip = DayTemplatePayload.model_validate(as_stored)

    assert round_trip == original
    assert round_trip.meals[0].items[0].amount == Decimal("1234.567")
    assert round_trip.meals[0].items[0].servings == Decimal("0.33")


# --- walidacja kontraktu -------------------------------------------------------------


def test_payload_odrzuca_pozycje_bez_przepisu_i_bez_produktu() -> None:
    """Ten sam niezmiennik, co CHECK `recipe_xor_product` w bazie."""
    with pytest.raises(ValueError, match="albo przepis, albo produkt"):
        DayTemplatePayload.model_validate(
            {"v": 1, "meals": [{"name": "Obiad", "items": [{"servings": "1"}]}]}
        )


def test_payload_odrzuca_pozycje_z_przepisem_i_produktem_naraz() -> None:
    with pytest.raises(ValueError, match="albo przepis, albo produkt"):
        DayTemplatePayload.model_validate(
            {
                "v": 1,
                "meals": [
                    {"name": "Obiad", "items": [{"recipe_id": 1, "product_id": 2, "servings": "1"}]}
                ],
            }
        )


def test_payload_odrzuca_produkt_bez_ilosci() -> None:
    """Produkt luzem MUSI mieć ilość i jednostkę (02_DOMAIN §13.1)."""
    with pytest.raises(ValueError, match="ilość i jednostkę"):
        DayTemplatePayload.model_validate(
            {"v": 1, "meals": [{"name": "Obiad", "items": [{"product_id": 2, "servings": "1"}]}]}
        )


def test_payload_odrzuca_przepis_z_iloscia() -> None:
    """Pozycją z przepisem steruje mnożnik, nie gramy."""
    with pytest.raises(ValueError, match="nie ma ilości"):
        DayTemplatePayload.model_validate(
            {
                "v": 1,
                "meals": [
                    {
                        "name": "Obiad",
                        "items": [
                            {"recipe_id": 2, "amount": "100", "amount_unit": "g", "servings": "1"}
                        ],
                    }
                ],
            }
        )


def test_payload_odrzuca_obca_wersje_kontraktu() -> None:
    """`v` nie jest ozdobą: payload `v:2` ma paść, a nie zostać zinterpretowany jako `v:1`."""
    with pytest.raises(ValueError):
        DayTemplatePayload.model_validate({"v": 2, "meals": []})


def test_payload_odrzuca_nieznane_pola() -> None:
    """`extra="forbid"`: nie przyjmujemy dowolnego JSON-a (karta B07 §Security)."""
    with pytest.raises(ValueError):
        DayTemplatePayload.model_validate({"v": 1, "meals": [], "cokolwiek": True})


def test_szablon_tygodnia_odrzuca_dwa_dni_o_tym_samym_offsecie() -> None:
    """Ten sam dzień tygodnia dwa razy znaczyłby dwa plany na jedną datę."""
    with pytest.raises(ValueError, match="tylko raz"):
        WeekTemplatePayload.model_validate(
            {
                "v": 1,
                "days": [
                    {"offset": 0, "day": {"v": 1, "meals": []}},
                    {"offset": 0, "day": {"v": 1, "meals": []}},
                ],
            }
        )


@pytest.mark.parametrize("offset", [-1, 7, 99])
def test_szablon_tygodnia_przyjmuje_tylko_offsety_zero_do_szesc(offset: int) -> None:
    with pytest.raises(ValueError):
        WeekTemplatePayload.model_validate(
            {"v": 1, "days": [{"offset": offset, "day": {"v": 1, "meals": []}}]}
        )
