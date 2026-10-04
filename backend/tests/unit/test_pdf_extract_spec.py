"""Schemat `spec.json` narzędzia `/pdf-extract` (BATCH_22, D31).

Kontrakt jest zamknięty: żadnych pól spoza schematu, żadnych pól na dane osobowe (D27),
liczby jako stringi dziesiętne mieszczące się w kolumnach bazy (ADR-008).
"""

from __future__ import annotations

import copy
import json
import types
import typing
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel

from scripts.pdf_extract import spec as spec_module
from scripts.pdf_extract.spec import Spec, SpecError, dump_spec, load_spec, parse_spec
from tests.pdf_extract_fixtures import version_one_payload, version_two_payload

pytestmark = pytest.mark.unit

#: Fragmenty nazw pól, które oznaczałyby dane osobowe (pacjent, dietetyk, kontakt).
PERSONAL_FIELD_MARKERS = (
    "patient",
    "pacjent",
    "surname",
    "nazwisko",
    "firstname",
    "first_name",
    "imie",
    "email",
    "e_mail",
    "phone",
    "telefon",
    "contact",
    "kontakt",
    "address",
    "adres",
    "dietit",
    "dietet",
    "pesel",
)


def _models_in(annotation: Any, seen: set[type[BaseModel]]) -> None:
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType, list, dict, typing.Annotated):
        for arg in get_args(annotation):
            _models_in(arg, seen)
    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return
        seen.add(annotation)
        for field in annotation.model_fields.values():
            _models_in(field.annotation, seen)


def test_schemat_nie_ma_pol_na_dane_osobowe() -> None:
    """Żaden model schematu (rekurencyjnie) nie ma pola o nazwie sugerującej dane osobowe."""
    models: set[type[BaseModel]] = set()
    _models_in(Spec, models)
    assert len(models) >= 8  # sanity: przeszliśmy przez całe drzewo modeli
    offenders = [
        f"{model.__name__}.{name}"
        for model in models
        for name in model.model_fields
        if any(marker in name.lower() for marker in PERSONAL_FIELD_MARKERS)
    ]
    assert offenders == []


def test_kazdy_model_schematu_zabrania_dodatkowych_pol() -> None:
    """`extra="forbid"` wszędzie — nowe pole jest decyzją kontraktową, nie wpisem „przy okazji”."""
    models: set[type[BaseModel]] = set()
    _models_in(Spec, models)
    assert {model.model_config.get("extra") for model in models} == {"forbid"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update({"pacjent": "X"}),
        lambda p: p["products"][0].update({"producent": "X"}),
        lambda p: p["recipes"][0].update({"dietetyk": "X"}),
        lambda p: p["recipes"][0]["ingredients"][0].update({"uwagi": "X"}),
    ],
    ids=["spec", "produkt", "przepis", "skladnik"],
)
def test_schemat_odrzuca_pola_spoza_kontraktu(mutate: Any) -> None:
    """Dodatkowe pole na dowolnym poziomie = błąd schematu."""
    payload = version_one_payload()
    mutate(payload)
    with pytest.raises(SpecError):
        parse_spec(payload)


def test_liczby_float_sa_odrzucane_a_stringi_przyjmowane() -> None:
    """ADR-008: JSON-owy `float` w danych Pythona to błąd; string dziesiętny jest dokładny."""
    payload = version_one_payload()
    payload["products"][0]["per_100"]["kcal"] = 350.0
    with pytest.raises(SpecError, match="float"):
        parse_spec(payload)

    payload["products"][0]["per_100"]["kcal"] = "350.00"
    assert parse_spec(payload).products[0].per_100.kcal == Decimal("350.00")


def test_wczytanie_json_nie_przechodzi_przez_float(tmp_path: Path) -> None:
    """`load_spec` czyta liczby JSON jako `Decimal` — 0.1 zostaje dokładnie 0.1."""
    payload = version_one_payload()
    payload["pdf_shopping_list_grams"]["pieczarki"] = "0.1"
    text = json.dumps(payload).replace('"0.1"', "0.1")
    path = tmp_path / "spec.json"
    path.write_text(text, encoding="utf-8")
    assert load_spec(path).pdf_shopping_list_grams["pieczarki"] == Decimal("0.1")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("per_100", "kcal"), "350.123"),  # NUMERIC(7,2): trzy miejsca
        (("per_100", "protein"), "10000"),  # NUMERIC(6,2): pięć cyfr całkowitych
        (("glycemic_index",), "50.55"),  # NUMERIC(5,1)
        (("per_100", "fat"), "-1"),
    ],
)
def test_precyzja_i_znak_wartosci_odpowiadaja_kolumnom_bazy(
    path: tuple[str, ...], value: str
) -> None:
    """Wartość, którą baza zaokrągliłaby po cichu albo odrzuciła CHECK-iem, to błąd schematu."""
    payload = version_one_payload()
    target = payload["products"][0]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(SpecError):
        parse_spec(payload)


def test_waga_sztuki_wymagana_dokladnie_dla_produktu_piece() -> None:
    """Jak CHECK `piece_weight_matches_measure_kind` w bazie."""
    payload = version_one_payload()
    egg = next(p for p in payload["products"] if p["key"] == "jajko")
    egg["piece_weight_g"] = None
    with pytest.raises(SpecError, match="piece_weight_g"):
        parse_spec(payload)

    payload = version_one_payload()
    flour = next(p for p in payload["products"] if p["key"] == "maka")
    flour["piece_weight_g"] = "10"
    with pytest.raises(SpecError, match="piece_weight_g"):
        parse_spec(payload)


def test_basis_musi_pasowac_do_miary() -> None:
    """VOLUME liczone na 100 ml, reszta na 100 g (ADR-004)."""
    payload = version_one_payload()
    milk = next(p for p in payload["products"] if p["key"] == "mleko")
    milk["per_100"]["basis"] = "g"
    with pytest.raises(SpecError, match="basis"):
        parse_spec(payload)


def test_skladnik_musi_wskazywac_znany_produkt() -> None:
    payload = version_one_payload()
    payload["recipes"][0]["ingredients"][0]["product"] = "nieznany"
    with pytest.raises(SpecError, match="nieznany produkt"):
        parse_spec(payload)


def test_klucze_i_nazwy_musza_byc_unikalne() -> None:
    payload = version_one_payload()
    payload["products"].append(copy.deepcopy(payload["products"][0]))
    with pytest.raises(SpecError, match="unikalne"):
        parse_spec(payload)

    payload = version_one_payload()
    payload["recipes"].append(copy.deepcopy(payload["recipes"][0]))
    with pytest.raises(SpecError, match="unikalne"):
        parse_spec(payload)


def test_lista_zakupow_i_sumy_dnia_musza_odwolywac_sie_do_istniejacych_rzeczy() -> None:
    payload = version_one_payload()
    payload["pdf_shopping_list_grams"]["widmo"] = "10"
    with pytest.raises(SpecError, match="nieznane produkty"):
        parse_spec(payload)

    payload = version_one_payload()
    payload["pdf_day_totals"]["sob"] = {"kcal": "1"}
    with pytest.raises(SpecError, match="dni bez przepisów"):
        parse_spec(payload)


def test_zapis_spec_jest_kanoniczny_i_stabilny(tmp_path: Path) -> None:
    """dump → load → dump daje te same bajty; liczby wychodzą jako stringi."""
    spec = parse_spec(version_two_payload())
    first = dump_spec(spec)
    path = tmp_path / "spec.json"
    path.write_text(first, encoding="utf-8")
    assert dump_spec(load_spec(path)) == first
    document = json.loads(first)
    assert document["products"][0]["per_100"]["kcal"] == "740"
    assert document["analyzed_on"] == "2026-10-04"


def test_modul_spec_nie_importuje_zadnych_zaleznosci_runtime_spoza_projektu() -> None:
    """Pakiet używa wyłącznie tego, co jest w `pyproject.toml` (pydantic, stdlib, app)."""
    source = Path(spec_module.__file__).read_text(encoding="utf-8")
    forbidden = ("pdfplumber", "anthropic", "fitz", "PyPDF", "pypdf", "requests", "httpx")
    assert [name for name in forbidden if name in source] == []
