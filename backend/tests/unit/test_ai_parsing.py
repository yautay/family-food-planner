"""Walidacja odpowiedzi AI — propozycja niezgodna z kontraktem MA być odrzucona.

Zero wywołań sieciowych: testowane są czyste funkcje `ai_assist`, które
dostają gotowy tekst odpowiedzi. To jest właśnie ta granica, dla której moduł
został podzielony na budowę promptu, walidację i cienką warstwę I/O.

Reguła nadrzędna (ADR-011): odpowiedź, której nie da się zaufać, znika po cichu.
Zignorowana propozycja kosztuje jedno kliknięcie w pickerze; zaakceptowana
bzdura kosztuje błędny przepis, którego nikt już nie skojarzy z importem.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.modules.importer.ai_assist import (
    MIN_CONFIDENCE,
    CatalogCandidate,
    RecipeToMatch,
    UnmappedName,
    build_duplicate_prompt,
    build_mapping_prompt,
    parse_duplicates,
    parse_mappings,
    parse_servings,
)

pytestmark = pytest.mark.unit

ALLOWED_NAMES = {"Skyr naturalny", "Maliny"}
ALLOWED_IDS = {11, 22}


def _mapping(**item: object) -> str:
    return json.dumps({"mappings": [item]})


# --- mapowania ---------------------------------------------------------------------


def test_poprawna_propozycja_przechodzi_z_pewnoscia_w_decimalu() -> None:
    """`confidence` wchodzi do NUMERIC(3,2), więc od razu jest `Decimal`, nie float."""
    raw = _mapping(raw_name="Skyr naturalny", product_id=11, confidence=0.87)

    result = parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS)

    assert len(result) == 1
    assert result[0].product_id == 11
    assert result[0].confidence == Decimal("0.87")


def test_uszkodzony_json_daje_zero_propozycji_a_nie_wyjatek() -> None:
    """Model potrafi dokleić zdanie przed JSON-em — to nie jest błąd serwera."""
    assert (
        parse_mappings(
            "Oczywiście! {mappings: [", allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS
        )
        == ()
    )


def test_odpowiedz_niezgodna_ze_schematem_jest_ignorowana() -> None:
    """Brak wymaganego pola = cała paczka odrzucona, bo nie wiadomo, czego brakuje."""
    raw = json.dumps({"mappings": [{"raw_name": "Maliny"}]})

    assert parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS) == ()


def test_pewnosc_spoza_zakresu_jest_odrzucana() -> None:
    """`confidence` poza [0, 1] łamie CHECK w bazie — lepiej odsiać to tutaj."""
    raw = _mapping(raw_name="Maliny", product_id=22, confidence=1.4)

    assert parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS) == ()


def test_propozycja_ponizej_progu_pewnosci_nie_trafia_do_stagingu() -> None:
    """„Może to to" kosztuje człowieka więcej niż wybranie produktu samemu."""
    raw = _mapping(raw_name="Maliny", product_id=22, confidence=float(MIN_CONFIDENCE) - 0.01)

    assert parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS) == ()


def test_produkt_spoza_listy_kandydatow_jest_odrzucany() -> None:
    """Halucynowane id produktu wysadziłoby FK — odsiewamy je przed zapisem."""
    raw = _mapping(raw_name="Maliny", product_id=999, confidence=0.99)

    assert parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS) == ()


def test_nazwa_o_ktora_nie_pytalismy_jest_odrzucana() -> None:
    """Model bywa uczynny i dokłada pozycje — staging nie jest od tego."""
    raw = _mapping(raw_name="Czekolada", product_id=11, confidence=0.99)

    assert parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS) == ()


def test_dwie_propozycje_dla_jednej_nazwy_daja_pierwsza() -> None:
    """Jedna surowa nazwa ma jedno pole `suggested_product_id` — druga byłaby stratą."""
    raw = json.dumps(
        {
            "mappings": [
                {"raw_name": "Maliny", "product_id": 22, "confidence": 0.9},
                {"raw_name": "Maliny", "product_id": 11, "confidence": 0.8},
            ]
        }
    )

    result = parse_mappings(raw, allowed_names=ALLOWED_NAMES, allowed_product_ids=ALLOWED_IDS)

    assert [item.product_id for item in result] == [22]


# --- duplikaty i porcje --------------------------------------------------------------


def test_duplikat_dostaje_nazwe_przepisu_z_naszej_bazy() -> None:
    """Nazwę bierzemy ZE SWOICH danych, nie z odpowiedzi modelu — model może zmyślić."""
    raw = json.dumps(
        {
            "duplicates": [{"staged_recipe_id": 5, "recipe_id": 3, "confidence": 0.9}],
            "servings": [],
        }
    )

    duplicates, _ = parse_duplicates(
        raw, allowed_staged_ids={5}, allowed_recipes={3: "Gołąbki bez zawijania"}
    )

    assert len(duplicates) == 1
    assert duplicates[0].recipe_name == "Gołąbki bez zawijania"


def test_duplikat_wskazujacy_nieznany_przepis_jest_odrzucany() -> None:
    """Przepis spoza listy kandydatów mógłby należeć do CUDZEJ rodziny."""
    raw = json.dumps(
        {
            "duplicates": [{"staged_recipe_id": 5, "recipe_id": 404, "confidence": 0.99}],
            "servings": [],
        }
    )

    duplicates, _ = parse_duplicates(raw, allowed_staged_ids={5}, allowed_recipes={3: "Gołąbki"})

    assert duplicates == ()


def test_podpowiedz_porcji_przechodzi_razem_z_uzasadnieniem() -> None:
    """Podpowiedź trafia do `details` issue — nigdy do `resolved_servings` (ADR-011)."""
    raw = json.dumps(
        {
            "duplicates": [],
            "servings": [{"staged_recipe_id": 5, "servings": 21, "rationale": "„około 21 szt"}],
        }
    )

    hints = parse_servings(raw, allowed_staged_ids={5})

    assert len(hints) == 1
    assert hints[0].servings == 21
    assert "21" in hints[0].rationale


def test_absurdalna_liczba_porcji_jest_odrzucana() -> None:
    """Schemat trzyma porcje w [1, 100] — „0 porcji" nie jest podpowiedzią."""
    raw = json.dumps(
        {"duplicates": [], "servings": [{"staged_recipe_id": 5, "servings": 0, "rationale": ""}]}
    )

    assert parse_servings(raw, allowed_staged_ids={5}) == ()


# --- prompty -------------------------------------------------------------------------


def test_prompt_mapowania_niesie_tylko_nazwy_i_kandydatow() -> None:
    """Granica D5: do modelu idzie treść PDF-a i katalog, nigdy dane użytkowników."""
    prompt = build_mapping_prompt(
        [
            UnmappedName(
                raw_name="Skyr naturalny",
                candidates=(CatalogCandidate(product_id=11, name="Skyr naturalny pitny"),),
            )
        ]
    )

    assert "Skyr naturalny" in prompt
    assert "id=11" in prompt
    # Few-shot z 01_PDF_AUDIT §5.3 — bez niego model sklejałby odrębne produkty.
    assert "Skyr naturalny pitny" in prompt


def test_prompt_duplikatow_dziala_takze_bez_istniejacych_przepisow() -> None:
    """Pierwszy import leci na pustą bazę — prompt ma to powiedzieć wprost."""
    prompt = build_duplicate_prompt(
        [RecipeToMatch(staged_recipe_id=5, name="Gołąbki")], [], {5: "Kapustę poszatkować."}
    )

    assert "brak" in prompt
    assert "Kapustę poszatkować." in prompt
