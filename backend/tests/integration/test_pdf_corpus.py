"""Parser na REALNYM korpusie — liczby z 01_PDF_AUDIT §1 jako asercje.

To jest test, który pilnuje, żeby importer nie „poprawił się" w stronę innych
liczb niż zmierzone. Pracuje na ośmiu plikach z `data/source_pdfs/` (żadnych
mocków, 08_TESTING §2.10) i nie dotyka bazy — jest `integration`, a nie `unit`,
wyłącznie dlatego, że czyta dysk i uruchamia pdfplumber.

Ekstrakcja liczy się RAZ na sesję testową (fixture `corpus`): osiem plików to
kilka sekund, a każdy test dostaje ten sam, gotowy wynik.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest

from app.modules.catalog.naming import normalize_name
from app.modules.importer.parser import Finding, ParsedDocument, ParsedMeal, parse_document

pytestmark = pytest.mark.integration

#: Korpus leży w repozytorium (`data/source_pdfs`), dwa poziomy nad `backend/`.
CORPUS_DIR = Path(__file__).resolve().parents[3] / "data" / "source_pdfs"

#: Sumy dni z tabeli 01_PDF_AUDIT §1 — plik → (Poniedziałek, Wtorek, Środa).
EXPECTED_DAY_TOTALS = {
    "dieta": (2021, 1953, 1919),
    "dieta (1)": (2078, 1992, 1977),
    "dieta (2)": (1959, 1987, 2030),
    "dieta (3)": (1970, 2049, 2036),
    "dieta (4)": (2098, 2059, 2029),
    "dieta (5)": (2158, 2020, 1953),
    "dieta (6)": (1997, 2025, 1962),
    "dieta (7)": (2044, 2054, 2095),
}

#: Liczba stron per plik (§1) — pilnuje, że korpus w repo się nie zmienił.
EXPECTED_PAGE_COUNTS = {
    "dieta": 10,
    "dieta (1)": 9,
    "dieta (2)": 9,
    "dieta (3)": 8,
    "dieta (4)": 8,
    "dieta (5)": 9,
    "dieta (6)": 8,
    "dieta (7)": 10,
}

#: Sumy z §1 dla całego korpusu.
EXPECTED_DAYS = 24
EXPECTED_MEALS = 96
EXPECTED_INGREDIENT_ROWS = 642
EXPECTED_PRODUCT_NAMES = 178


@pytest.fixture(scope="session")
def corpus() -> dict[str, ParsedDocument]:
    """Osiem plików sparsowanych raz na sesję: `{nazwa bez rozszerzenia: dokument}`."""
    documents: dict[str, ParsedDocument] = {}
    for path in sorted(CORPUS_DIR.glob("*.pdf")):
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        documents[path.stem] = parse_document(pages)
    return documents


def _meal(document: ParsedDocument, day: str, label: str) -> ParsedMeal:
    """Posiłek po etykiecie dnia i nazwie — czytelniejsze niż indeksy w asercjach."""
    return next(
        meal
        for parsed_day in document.days
        if parsed_day.label == day
        for meal in parsed_day.meals
        if meal.label == label
    )


# --- inwentarz (§1) --------------------------------------------------------------


def test_korpus_ma_osiem_plikow_o_zmierzonej_liczbie_stron() -> None:
    """Punkt wyjścia: gdyby korpus podmieniono, reszta asercji nic by nie znaczyła."""
    counts = {}
    for path in sorted(CORPUS_DIR.glob("*.pdf")):
        with pdfplumber.open(path) as pdf:
            counts[path.stem] = len(pdf.pages)

    assert counts == EXPECTED_PAGE_COUNTS


def test_caly_korpus_parsuje_sie_do_liczb_z_audytu(corpus: dict[str, ParsedDocument]) -> None:
    """24 dni, 96 posiłków, 642 wiersze składników, 178 nazw produktów (§1)."""
    days = sum(len(document.days) for document in corpus.values())
    meals = sum(len(document.meals) for document in corpus.values())
    ingredients = sum(
        len(dish.ingredients) for document in corpus.values() for dish in document.dishes
    )
    names = {
        normalize_name(item.raw_name)
        for document in corpus.values()
        for dish in document.dishes
        for item in dish.ingredients
    }

    assert days == EXPECTED_DAYS
    assert meals == EXPECTED_MEALS
    assert ingredients == EXPECTED_INGREDIENT_ROWS
    assert len(names) == EXPECTED_PRODUCT_NAMES


def test_kazdy_wiersz_skladnika_ma_gramature(corpus: dict[str, ParsedDocument]) -> None:
    """§3.2: gramatura jest podana zawsze (642/642) i zawsze dodatnia."""
    grams = [
        item.grams
        for document in corpus.values()
        for dish in document.dishes
        for item in dish.ingredients
    ]

    assert len(grams) == EXPECTED_INGREDIENT_ROWS
    assert all(value > Decimal(0) for value in grams)


def test_kazde_danie_ma_nazwe_i_nalezy_do_posilku(corpus: dict[str, ParsedDocument]) -> None:
    """`staged_recipes.name` jest NOT NULL — puste nazwy zabiłyby zapis stagingu."""
    for stem, document in corpus.items():
        for day in document.days:
            assert day.label, f"{stem}: dzień bez etykiety"
            for meal in day.meals:
                assert meal.dishes, f"{stem}/{day.label}/{meal.label}: posiłek bez dania"
                for dish in meal.dishes:
                    assert dish.name.strip(), f"{stem}/{day.label}/{meal.label}: danie bez nazwy"


# --- sumy kontrolne (§4) ---------------------------------------------------------


def test_wszystkie_sumy_dni_zgadzaja_sie_z_dokumentem(
    corpus: dict[str, ParsedDocument],
) -> None:
    """24/24 dni w tolerancji ±2 kcal — dokument jest wewnętrznie spójny (§4)."""
    checksums = [checksum for document in corpus.values() for checksum in document.checksums]

    assert len(checksums) == EXPECTED_DAYS
    assert [checksum for checksum in checksums if not checksum.ok] == []


@pytest.mark.parametrize("stem", sorted(EXPECTED_DAY_TOTALS))
def test_sumy_dni_per_plik_zgadzaja_sie_z_tabela_audytu(
    corpus: dict[str, ParsedDocument], stem: str
) -> None:
    """Tabela §1: każdy plik ma trzy dni o dokładnie tych sumach kcal."""
    document = corpus[stem]

    assert tuple(int(day.declared_kcal or 0) for day in document.days) == EXPECTED_DAY_TOTALS[stem]


# --- pomijane sekcje (§2.5, §5.4, §6) --------------------------------------------


def test_lista_zakupow_i_wymienniki_sa_pominiete(corpus: dict[str, ParsedDocument]) -> None:
    """Każdy plik ma stronę wymienników i co najmniej jedną stronę listy zakupów."""
    for stem, document in corpus.items():
        kinds = [kind.value for kind in document.pages]
        assert "exchanges" in kinds, f"{stem}: nie rozpoznano strony wymienników"
        assert "shopping_list" in kinds, f"{stem}: nie rozpoznano listy zakupów"


def test_list_przewodni_w_dieta_2_nie_generuje_posilkow_ani_bledu(
    corpus: dict[str, ParsedDocument],
) -> None:
    """§6: `dieta (2).pdf` ma na s. 2 list dietetyczki zamiast podsumowania."""
    document = corpus["dieta (2)"]

    assert [kind.value for kind in document.pages[:3]] == ["title", "letter", "summary"]
    assert len(document.days) == 3
    assert len(document.meals) == 12


# --- anomalie §5.1 ---------------------------------------------------------------


def test_golabki_multi_portion_declared(corpus: dict[str, ParsedDocument]) -> None:
    """`dieta.pdf` OBIAD: 3305 g składników, 635 kcal, „Przepis na 7 porcji" — BEZ issue."""
    meal = _meal(corpus["dieta"], "Środa", "OBIAD")
    dish = meal.dishes[0]

    assert dish.name == "Gołąbki bez zawijania"
    assert dish.declared_servings == 7
    assert meal.pdf_kcal == Decimal("635")
    assert meal.grams_total == Decimal("3305")
    assert _suspects(corpus["dieta"]) == []


def test_golabki_produkty_section(corpus: dict[str, ParsedDocument]) -> None:
    """§7: sekcja `Produkty` (Ziemniak 225 g) dołącza się do dania posiłku."""
    dish = _meal(corpus["dieta"], "Środa", "OBIAD").dishes[0]

    assert dish.ingredients[-1].raw_name == "Ziemniak"
    assert dish.ingredients[-1].grams == Decimal("225")
    # 3305 g z tabeli §5.1 = 3080 g przepisu + 225 g dodatku.
    assert dish.grams_total == Decimal("3305")


def test_dieta5_obiad_declared_2(corpus: dict[str, ParsedDocument]) -> None:
    """`dieta (5).pdf` OBIAD: 1018 g, „Przepis na 2 porcje" + „Zjedz 1 z 2" — bez issue."""
    meal = _meal(corpus["dieta (5)"], "Środa", "OBIAD")

    assert meal.grams_total == Decimal("1017.5")
    assert meal.dishes[0].name == "Pulpety z dorsza"
    assert meal.dishes[0].declared_servings == 2
    assert meal.has_declared_servings is True


def test_multi_portion_suspect_unmarked(corpus: dict[str, ParsedDocument]) -> None:
    """Cztery nieoznaczone przypadki z tabeli §5.1 — każdy z issue `blocker`.

    Masy różnią się od tabeli audytu o zaokrąglenie do pełnych gramów
    (827,5 vs 828; 1245,8 vs 1246; 806,3 vs 806) — audyt podawał je zaokrąglone.
    """
    found = sorted(
        (stem, finding.day_label, finding.meal_label, finding.details["masa_g"])
        for stem, document in corpus.items()
        for finding in _suspects(document)
    )

    assert found == [
        ("dieta (3)", "Środa", "OBIAD", "827.5"),
        ("dieta (5)", "Poniedziałek", "ŚNIADANIE", "946"),
        ("dieta (5)", "Wtorek", "KOLACJA", "1245.8"),
        ("dieta (7)", "Poniedziałek", "KOLACJA", "806.3"),
    ]


def test_kazdy_blocker_wskazuje_konkretne_danie(corpus: dict[str, ParsedDocument]) -> None:
    """Issue bez `staged_recipe_id` nie dałby się rozstrzygnąć w review (B16)."""
    for stem, document in corpus.items():
        for finding in _suspects(document):
            assert finding.dish_index is not None, f"{stem}: blocker bez wskazania dania"
            assert 0 <= finding.dish_index < len(document.dishes)


def test_kcal_posilkow_z_anomalii_zgadza_sie_z_tabela_audytu(
    corpus: dict[str, ParsedDocument],
) -> None:
    """Druga kolumna tabeli §5.1: kcal posiłku (per porcja zjadana, §4)."""
    assert _meal(corpus["dieta (3)"], "Środa", "OBIAD").pdf_kcal == Decimal("638")
    assert _meal(corpus["dieta (5)"], "Poniedziałek", "ŚNIADANIE").pdf_kcal == Decimal("612")
    assert _meal(corpus["dieta (5)"], "Wtorek", "KOLACJA").pdf_kcal == Decimal("486")
    assert _meal(corpus["dieta (7)"], "Poniedziałek", "KOLACJA").pdf_kcal == Decimal("554")


# --- ostrzeżenia parsera (errata §9) ---------------------------------------------


def test_niesparsowane_wiersze_skladnikow_sa_zgloszone_a_nie_zgadniete(
    corpus: dict[str, ParsedDocument],
) -> None:
    """Siedem wierszy spoza kontraktu §3.2 — errata §9, decyzja D20.

    Ten test jest DOWODEM pomiaru, na którym stoi errata: gdyby kontrakt
    rozszerzono (albo parser zaczął zgadywać), liczba by się zmieniła.
    """
    lines = sorted(
        finding.details["linia"]
        for document in corpus.values()
        for finding in document.findings
        if finding.kind == "parse_warning"
    )

    assert lines == [
        "Czekolada ciemna (60-69% masy kakaowej), 1 x",
        "Czekolada ciemna (60-69% masy kakaowej), 2 x",
        "Czekolada ciemna (60-69% masy kakaowej), 2 x",
        "Kapusta włoska, 200 g",
        "Kefir, 330 g",
        "Makaron pełnoziarnisty, 60 g",
        "Passata, 150 g",
    ]


def test_zaden_dzien_nie_zglasza_rozjazdu_sumy(corpus: dict[str, ParsedDocument]) -> None:
    """Rozjazd sumy dnia byłby sygnałem błędu parsera — w korpusie nie ma ani jednego."""
    mismatches = [
        finding
        for document in corpus.values()
        for finding in document.findings
        if finding.kind == "parse_warning" and "otrzymane" in finding.details
    ]

    assert mismatches == []


def _suspects(document: ParsedDocument) -> list[Finding]:
    """Ustalenia `multi_portion_suspect` dokumentu (kolejność dokumentu)."""
    return [finding for finding in document.findings if finding.kind == "multi_portion_suspect"]
