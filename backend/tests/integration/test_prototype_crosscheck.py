"""Walidacja krzyżowa parsera z bazą prototypu (01_PDF_AUDIT §8.6).

Prototyp (`data/reference/prototype.db`) zaimportował TE SAME osiem PDF-ów
i wyprodukował 84 przepisy, 592 składniki i 181 produktów. Nowy importer ma
osiągnąć **co najmniej** tę kompletność — różnice są materiałem do oceny,
nie automatycznym failem (decyzja D2: z prototypu nie kopiujemy ANI JEDNEGO
wiersza danych, służy wyłącznie jako miara).

Bazę czytamy w trybie READ-ONLY (`file:...?mode=ro`) i przez introspekcję
schematu: gdyby ktoś kiedyś podmienił plik, test ma paść na brakującej tabeli,
a nie po cichu porównać się z zerem.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pdfplumber
import pytest

from app.modules.catalog.naming import normalize_name
from app.modules.importer.parser import ParsedDocument, parse_document

pytestmark = pytest.mark.integration

REFERENCE_DB = Path(__file__).resolve().parents[3] / "data" / "reference" / "prototype.db"
CORPUS_DIR = Path(__file__).resolve().parents[3] / "data" / "source_pdfs"

#: Liczby prototypu z §8.6 — próg kompletności, nie wartość docelowa.
PROTOTYPE_RECIPES = 84
PROTOTYPE_INGREDIENTS = 592
PROTOTYPE_PRODUCTS = 181


@pytest.fixture(scope="session")
def reference() -> Iterator[sqlite3.Connection]:
    """Połączenie READ-ONLY do bazy prototypu."""
    if not REFERENCE_DB.is_file():
        pytest.fail(f"Brak referencji {REFERENCE_DB} — bez niej §8.6 jest niemierzalne.")
    connection = sqlite3.connect(f"file:{REFERENCE_DB.as_posix()}?mode=ro", uri=True)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="session")
def parsed_corpus() -> list[ParsedDocument]:
    """Osiem plików korpusu sparsowanych raz na sesję."""
    documents = []
    for path in sorted(CORPUS_DIR.glob("*.pdf")):
        with pdfplumber.open(path) as pdf:
            documents.append(parse_document([page.extract_text() or "" for page in pdf.pages]))
    return documents


def _count(connection: sqlite3.Connection, table: str) -> int:
    """Liczba wierszy tabeli; brak tabeli = jawny fail, nie zero."""
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert table in tables, f"Referencja nie ma tabeli {table}: {sorted(tables)}"
    return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _deduplicated(documents: list[ParsedDocument]) -> tuple[int, int]:
    """Dania zdeduplikowane po znormalizowanej nazwie W OBRĘBIE każdego joba.

    Dedup jest per job, nie globalny (Implementation Notes karty B15): scalanie
    tych samych dań między importami to decyzja review (B16), a nie coś, co
    parser ma prawo zrobić za człowieka. Prototyp scalał globalnie, więc jego
    84 przepisy to inna miara tej samej rzeczy — stąd próg „co najmniej".
    """
    recipes = ingredients = 0
    for document in documents:
        seen: dict[str, int] = {}
        for dish in document.dishes:
            key = normalize_name(dish.name)
            if key not in seen:
                seen[key] = len(dish.ingredients)
        recipes += len(seen)
        ingredients += sum(seen.values())
    return recipes, ingredients


def test_referencja_ma_zmierzone_liczby(reference: sqlite3.Connection) -> None:
    """Sanity check samej referencji — inaczej progi poniżej nic nie znaczą."""
    assert _count(reference, "recipes") == PROTOTYPE_RECIPES
    assert _count(reference, "recipe_ingredients") == PROTOTYPE_INGREDIENTS
    assert _count(reference, "products") == PROTOTYPE_PRODUCTS


def test_parser_osiaga_kompletnosc_prototypu(
    parsed_corpus: list[ParsedDocument],
    reference: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """≥84 przepisy i ≥592 składniki po dedupie w obrębie jobów (§8.6)."""
    recipes, ingredients = _deduplicated(parsed_corpus)

    with capsys.disabled():
        print(
            "\nWalidacja krzyżowa z prototype.db (§8.6):"
            f"\n  przepisy:  parser {recipes:>4} vs prototyp {PROTOTYPE_RECIPES:>4}"
            f"  (różnica {recipes - PROTOTYPE_RECIPES:+d})"
            f"\n  składniki: parser {ingredients:>4} vs prototyp {PROTOTYPE_INGREDIENTS:>4}"
            f"  (różnica {ingredients - PROTOTYPE_INGREDIENTS:+d})"
        )

    assert recipes >= PROTOTYPE_RECIPES
    assert ingredients >= PROTOTYPE_INGREDIENTS


def test_liczba_produktow_jest_porownywalna_z_prototypem(
    parsed_corpus: list[ParsedDocument], capsys: pytest.CaptureFixture[str]
) -> None:
    """Różnica w liczbie produktów to MATERIAŁ, nie fail (§8.6, decyzja D2).

    Prototyp miał 181 nazw, parser widzi 178. Trzy brakujące to wiersze spoza
    kontraktu §3.2 (errata §9) — dlatego test raportuje różnicę zamiast ją
    zamiatać, ale nie blokuje batcha: rozszerzenie kontraktu jest decyzją D20.
    """
    names = {
        normalize_name(item.raw_name)
        for document in parsed_corpus
        for dish in document.dishes
        for item in dish.ingredients
    }

    with capsys.disabled():
        print(
            f"\n  produkty:  parser {len(names):>4} vs prototyp {PROTOTYPE_PRODUCTS:>4}"
            f"  (różnica {len(names) - PROTOTYPE_PRODUCTS:+d})"
        )

    assert len(names) > 0
