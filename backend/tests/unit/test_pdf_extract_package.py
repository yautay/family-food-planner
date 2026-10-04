"""Generator paczki transferu narzędzia `/pdf-extract` (BATCH_22, D31 pkt 3, D33).

Testy czyste (bez bazy): kształt dokumentu z `serializer.SECTIONS`, determinizm bajtów,
zakresy przepisów, kierunek zależności i brak `float` w pakiecie.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from app.modules.transfer.importer import open_archive, read_document
from app.modules.transfer.schemas import TransferScope
from app.modules.transfer.serializer import (
    SECTIONS_BY_NAME,
    section_columns,
    section_references,
    sections_for,
)
from scripts.pdf_extract import package as package_module
from scripts.pdf_extract.catalog_index import build_index, resolve_catalog
from scripts.pdf_extract.package import (
    KNOWN_CATEGORIES,
    PackageError,
    RecipeScopeChoice,
    build_archive,
    build_document,
    normalize_email,
    section_counts,
)
from tests.pdf_extract_fixtures import version_one, version_one_payload

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]
PACKAGE_DIR = BACKEND_DIR / "scripts" / "pdf_extract"


def _document(**kwargs: Any) -> dict[str, Any]:
    spec = version_one()
    return build_document(spec, resolve_catalog(spec, build_index({})).products, **kwargs)


def test_ta_sama_spec_daje_te_same_bajty() -> None:
    """Determinizm: dwa wywołania = identyczna paczka (znaczniki czasu ZIP-a są stałe)."""
    first = build_archive(_document())
    second = build_archive(_document())
    assert first == second
    with zipfile.ZipFile(BytesIO(first)) as archive:
        (info,) = archive.infolist()
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.create_system == 3


def test_zmiana_spec_zmienia_bajty() -> None:
    payload = version_one_payload()
    payload["recipes"][0]["instructions"] = "Inaczej."
    from scripts.pdf_extract.spec import parse_spec

    spec = parse_spec(payload)
    changed = build_document(spec, resolve_catalog(spec, build_index({})).products)
    assert build_archive(changed) != build_archive(_document())


def test_dokument_ma_sekcje_zgodne_z_serializerem_i_sam_czyta_go_import(tmp_path: Path) -> None:
    """Każdy wiersz ma dokładnie kolumny i referencje sekcji; import odczytuje paczkę."""
    document = _document()
    assert list(document["data"]) == [s.name for s in sections_for(TransferScope.USER)]
    for name, rows in document["data"].items():
        section = SECTIONS_BY_NAME[name]
        expected = set(section_columns(section)) | set(section_references(section))
        if section.pk is not None:
            expected.add(section.pk)
        for row in rows:
            assert set(row) == expected, name

    path = tmp_path / "export.zip"
    path.write_bytes(build_archive(document))
    with open_archive(path) as archive:
        parsed = read_document(archive)
    assert parsed.schema_version == 1
    assert parsed.scope is TransferScope.USER
    assert parsed.app_version == "pdf-extract/0001"
    assert parsed.exported_at.startswith("2026-10-03")


def test_produkty_sa_unverified_a_liczby_stringami_dziesietnymi() -> None:
    document = _document()
    products = {row["name"]: row for row in document["data"]["canonical_products"]}
    assert {row["verification_status"] for row in products.values()} == {"unverified"}
    assert products["Mąka testowa"]["kcal_100"] == "350"
    assert products["Jajko testowe"]["piece_weight_g"] == "50"
    assert products["Mąka testowa"]["normalized_name"] == "mąka testowa"
    for row in document["data"]["recipe_ingredients"]:
        assert isinstance(row["amount"], str) and isinstance(row["display_qty"], str)
    payload = json.dumps(document)
    assert "e+" not in payload.lower()


def test_skladniki_niosa_decyzje_zapisu_z_reguly_jednostek() -> None:
    """Pieczarki „3 x sztuka” → 60 g + note; jajko 2 szt. zostaje w sztukach."""
    rows = _document()["data"]["recipe_ingredients"]
    by_note = {row["note"]: row for row in rows if row["note"]}
    assert set(by_note) == {"3 x sztuka", "1 x łyżka"}
    assert by_note["3 x sztuka"]["display_unit"] == "g"
    assert Decimal(by_note["3 x sztuka"]["amount"]) == 60
    pieces = [row for row in rows if row["amount_unit"] == "piece"]
    assert {Decimal(row["amount"]) for row in pieces} == {1, 2}


def test_przepisy_household_maja_placeholdery_do_mapowania_na_importujacego() -> None:
    """`null` w `household_id` zamieniłby przepis po cichu na prywatny — placeholder go mapuje."""
    recipes = _document()["data"]["recipes"]
    assert {row["scope"] for row in recipes} == {"household"}
    assert {(row["owner_user_id"], row["household_id"]) for row in recipes} == {(1, 1)}


def test_przepisy_private_nie_niosa_rodziny() -> None:
    recipes = _document(recipe_scope=RecipeScopeChoice.PRIVATE)["data"]["recipes"]
    assert {(row["scope"], row["household_id"]) for row in recipes} == {("private", None)}


def test_global_wymaga_owner_email_i_daje_paczke_instancji_z_kontem_bez_uprawnien() -> None:
    """D33: `global` = scope=instance + users; rola `user`, brak aktywności (literówka ≠ admin)."""
    with pytest.raises(PackageError, match="--owner-email"):
        _document(recipe_scope=RecipeScopeChoice.GLOBAL)

    document = _document(recipe_scope=RecipeScopeChoice.GLOBAL, owner_email="  Admin@Example.COM ")
    assert document["scope"] == "instance"
    (user,) = document["data"]["users"]
    assert (user["email"], user["role"], user["is_active"]) == ("admin@example.com", "user", False)
    assert user["household_id"] is None
    recipes = document["data"]["recipes"]
    assert {(r["scope"], r["household_id"], r["owner_user_id"]) for r in recipes} == {
        ("global", None, 1)
    }
    assert "households" in document["data"] and document["data"]["households"] == []


def test_owner_email_bez_global_i_zly_email_sa_bledami() -> None:
    with pytest.raises(PackageError, match="global"):
        _document(owner_email="a@b.pl")
    with pytest.raises(PackageError, match="e-mail"):
        normalize_email("to nie jest adres")


def test_kategoria_spoza_slownika_migracji_jest_bledem() -> None:
    """Import założyłby nową kategorię w słowniku globalnym — nie jest to zadanie jadłospisu."""
    payload = version_one_payload()
    payload["products"][0]["category"] = "Kategoria wymyślona"
    from scripts.pdf_extract.spec import parse_spec

    spec = parse_spec(payload)
    with pytest.raises(PackageError, match="spoza słownika"):
        build_document(spec, resolve_catalog(spec, build_index({})).products)


def test_slownik_kategorii_generatora_zgadza_sie_z_migracja_0005() -> None:
    """Kopia listy kategorii jest dozwolona tylko przy teście, który wykryje rozjazd."""
    migration = BACKEND_DIR / "migrations" / "versions" / "0005_seed_product_categories.py"
    spec = importlib.util.spec_from_file_location("migration_0005", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert KNOWN_CATEGORIES == module.CATEGORIES


def test_tagi_posilkow_systemowe_i_podwieczorek() -> None:
    tags = {row["name"]: row["is_system"] for row in _document()["data"]["tags"]}
    assert tags == {"śniadanie": True, "obiad": True}
    assert package_module.MEAL_TAGS["podwieczorek"] == ("podwieczorek", False)


def test_komentarz_dietetyka_wchodzi_na_koniec_instrukcji() -> None:
    payload = version_one_payload()
    payload["recipes"][0]["comment"] = "Można użyć innej mąki"
    from scripts.pdf_extract.spec import parse_spec

    spec = parse_spec(payload)
    document = build_document(spec, resolve_catalog(spec, build_index({})).products)
    assert document["data"]["recipes"][0]["instructions"].endswith("Uwaga: Można użyć innej mąki")


def test_liczniki_sekcji_do_podsumowania() -> None:
    counts = section_counts(_document())
    assert counts["recipes"] == 2 and counts["canonical_products"] == 4
    assert "audit_entries" not in counts


# --- statyczne strażniki kontraktu pakietu -------------------------------------------------


def _python_files() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def test_pakiet_nie_uzywa_float_dla_ilosci_i_wartosci() -> None:
    """ADR-008: `float` wolno wymienić wyłącznie w `isinstance(...)`, który go odrzuca."""
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
            ):
                allowed.update(id(child) for child in ast.walk(node))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "float" and id(node) not in allowed:
                offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                offenders.append(f"{path.name}:{node.lineno} (literał float)")
    assert offenders == []


def test_aplikacja_nie_importuje_narzedzia_pdf_extract() -> None:
    """Kierunek zależności: skrypt → aplikacja, nigdy odwrotnie (D31, ADR-016)."""
    offenders = [
        str(path.relative_to(BACKEND_DIR))
        for path in sorted((BACKEND_DIR / "app").rglob("*.py"))
        if "pdf_extract" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_pakiet_nie_dodaje_zaleznosci_runtime() -> None:
    """Importy pakietu to stdlib, pydantic, sqlalchemy, `app` i `scripts` — nic poza pyproject."""
    allowed = {"app", "scripts", "pydantic", "sqlalchemy", "__future__"}
    stdlib = set(__import__("sys").stdlib_module_names)
    foreign: set[str] = set()
    for path in _python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                if root not in allowed and root not in stdlib:
                    foreign.add(root)
    assert foreign == set()
    pyproject = (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "pdfplumber" not in pyproject and "anthropic" not in pyproject


def test_generator_nie_przepisuje_listy_kolumn_sekcji() -> None:
    """Kolumny z `serializer.SECTIONS` (`_row`); zmiana sekcji w formacie wywala generator."""
    with pytest.raises(PackageError, match="Format transferu zmienił sekcję"):
        package_module._row("tags", 1, name="x")


def test_roundtrip_dotyka_tylko_lokalnej_bazy_testowej() -> None:
    """TRUNCATE na zdalnym hoście albo bazie nie-testowej jest zabroniony przed połączeniem."""
    from scripts.pdf_extract.roundtrip import RoundtripError, assert_test_database

    ok = "postgresql+psycopg://u:p@127.0.0.1:5433/pasnik_test"
    assert assert_test_database(ok, "postgresql+psycopg://u:p@127.0.0.1:5434/pasnik") == ok
    for bad in (
        None,
        "postgresql+psycopg://u:p@127.0.0.1:5434/pasnik",  # nie `_test`
        "postgresql+psycopg://u:p@10.0.0.121:5432/ffp_test",  # zdalny host
    ):
        with pytest.raises(RoundtripError):
            assert_test_database(bad, None)
    with pytest.raises(RoundtripError, match="tę samą bazę"):
        assert_test_database(ok, ok)
