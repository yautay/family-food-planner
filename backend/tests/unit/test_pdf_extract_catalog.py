"""Indeks katalogu narzędzia `/pdf-extract` (BATCH_22, D31 pkt 5).

Klucz tożsamości to `normalize_name` z aplikacji; konflikt miary wobec wersji albo
eksportu instancji zatrzymuje, wobec seedu demo tylko ostrzega.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.catalog.naming import normalize_name
from scripts.pdf_extract.catalog_index import (
    CatalogConflictError,
    CatalogEntry,
    build_index,
    classify,
    entries_from_export,
    load_instance_export,
    load_versions,
    resolve_catalog,
    similar_groups,
    similarity,
)
from scripts.pdf_extract.spec import SPEC_FILENAME, SpecError, dump_spec, parse_spec
from tests.pdf_extract_fixtures import (
    version_one,
    version_one_payload,
    version_two,
    version_two_payload,
)

pytestmark = pytest.mark.unit


def test_trafienie_dokladne_po_normalize_name_z_aplikacji() -> None:
    """„  mąka   TESTOWA ” to ten sam produkt — ta sama normalizacja co w bazie."""
    index = build_index({"0001-syntetyczny": version_one()})
    match = classify(index, "  mąka   TESTOWA ", "mass")
    assert match.kind == "exact"
    assert match.entry is not None
    assert match.entry.normalized == normalize_name("Mąka testowa")
    assert match.entry.origin == "0001-syntetyczny"


def test_produkt_nowy_i_podobny() -> None:
    """Brak trafienia = „nowy”; „Mleko testowe 2%” jest podobne do „Mleko testowe”."""
    index = build_index({"0001-syntetyczny": version_one()})
    assert classify(index, "Kasza gryczana", "mass").kind == "new"
    similar = classify(index, "Mleko testowe 2%", "volume")
    assert similar.kind == "similar"
    assert similar.candidates[0].entry.name == "Mleko testowe"


def test_alias_ze_scalenia_rozpoznaje_nazwe_z_pdf() -> None:
    """Nazwa scalona decyzją właściciela w wersji 0001 trafia w produkt wynikowy (`alias`)."""
    payload = version_one_payload()
    payload["products"][0]["merged_from"] = [{"name": "Mąka pszenna testowa"}]
    index = build_index({"0001-syntetyczny": parse_spec(payload)})
    match = classify(index, "mąka pszenna testowa")
    assert match.kind == "alias"
    assert match.entry is not None and match.entry.name == "Mąka testowa"


def test_konflikt_miary_wobec_wersji_jest_bledem_zatrzymujacym() -> None:
    """Ta sama nazwa, inny `measure_kind`: import reużyłby produkt, a ilości by nie działały."""
    index = build_index({"0001-syntetyczny": version_one()})
    with pytest.raises(CatalogConflictError, match="Konflikt definicji"):
        classify(index, "Mąka testowa", "piece")


def test_konflikt_miary_wobec_seedu_demo_jest_tylko_ostrzezeniem() -> None:
    """Demo to dane deweloperskie: ostrzeżenie z zakazem importu do bazy z seedem."""
    index = build_index({}, demo=[("Cebula", "mass")])
    match = classify(index, "Cebula", "piece")
    assert match.kind == "exact"
    assert any("seed demo" in text.lower() for text in match.warnings)


def test_konflikt_miary_miedzy_dwoma_zrodlami_przy_budowie_indeksu() -> None:
    """Wersja i eksport instancji o tej samej nazwie i różnej miarze nie dają się złożyć."""
    instance = CatalogEntry(
        name="Mąka testowa",
        normalized=normalize_name("Mąka testowa"),
        measure_kind="volume",
        kind="instance",
        origin="instancja",
    )
    with pytest.raises(CatalogConflictError):
        build_index({"0001-syntetyczny": version_one()}, instance=[instance])


def test_ten_sam_produkt_w_dwoch_wersjach_to_redefinicja() -> None:
    """Kolejna wersja ma produkt REUŻYĆ, nie definiować go drugi raz."""
    second = version_two_payload()
    second["products"].append(copy.deepcopy(version_one_payload()["products"][0]))
    second["products"][-1]["key"] = "maka_ii"
    second["reused"] = [item for item in second["reused"] if item["key"] != "maka"]
    second["recipes"][0]["ingredients"][0]["product"] = "maka_ii"
    second["pdf_shopping_list_grams"]["maka_ii"] = second["pdf_shopping_list_grams"].pop("maka")
    with pytest.raises(CatalogConflictError, match="dwóch wersjach"):
        build_index({"0001-a": version_one(), "0002-b": parse_spec(second)})


def test_reused_wymaga_istnienia_w_katalogu_i_pelnej_definicji() -> None:
    """`reused` na nieznany produkt albo na wpis demo (bez definicji) to błąd z wyjaśnieniem."""
    second = version_two()
    with pytest.raises(SpecError, match="nie ma w katalogu"):
        resolve_catalog(second, build_index({}))

    index = build_index({}, demo=[("Mąka testowa", "mass"), ("Jajko testowe", "piece")])
    with pytest.raises(SpecError, match="pełnej definicji"):
        resolve_catalog(second, index)


def test_redefinicja_produktu_z_wczesniejszej_wersji_jest_bledem() -> None:
    """Własny produkt wersji, który już istnieje w katalogu, ma iść przez `reused`."""
    payload = version_two_payload()
    payload["products"].append(copy.deepcopy(version_one_payload()["products"][0]))
    payload["products"][-1]["key"] = "maka_ii"
    payload["recipes"][0]["ingredients"][0]["product"] = "maka_ii"
    payload["reused"] = [item for item in payload["reused"] if item["key"] != "maka"]
    del payload["pdf_shopping_list_grams"]["maka"]
    with pytest.raises(SpecError, match="już istnieje"):
        resolve_catalog(parse_spec(payload), build_index({"0001-syntetyczny": version_one()}))


def test_reuzycie_bierze_pelna_definicje_z_wczesniejszej_wersji() -> None:
    """Katalog wersji 0002 zawiera mąkę i jajko z 0001 — z ich wartościami, bez redefinicji."""
    index = build_index({"0001-syntetyczny": version_one()})
    resolved = resolve_catalog(version_two(), index)
    assert resolved.products["maka"].per_100.kcal == version_one().products[0].per_100.kcal
    assert resolved.origins["maka"] == "0001-syntetyczny"
    assert resolved.origins["maslo"] == "0002"


def test_nazwy_przepisow_z_wersji_trafiaja_do_indeksu() -> None:
    index = build_index({"0001-syntetyczny": version_one()})
    assert index.recipe_names[normalize_name("Naleśniki testowe")] == "0001-syntetyczny"


def test_podobienstwo_i_grupy_scalen() -> None:
    """Skyr ⊂ Skyr naturalny; drób i indyk w jednej grupie; passata osobno."""
    assert similarity("Skyr", "Skyr naturalny") >= Decimal("0.9")
    groups = similar_groups(
        ["Pierś z kurczaka", "Pierś z indyka", "Skyr naturalny", "Skyr waniliowy", "Passata"]
    )
    assert ("Pierś z kurczaka", "Pierś z indyka") in groups
    assert ("Skyr naturalny", "Skyr waniliowy") in groups
    assert all("Passata" not in group for group in groups)


def test_wczytanie_wersji_z_dysku_i_pomijanie_analizowanej(tmp_path: Path) -> None:
    """`load_versions` czyta `*/spec.json`; wersja analizowana jest wyłączona z indeksu."""
    for label, spec in (
        ("0001-syntetyczny", version_one()),
        ("0002-syntetyczny-ii", version_two()),
    ):
        directory = tmp_path / label
        directory.mkdir()
        (directory / SPEC_FILENAME).write_text(dump_spec(spec), encoding="utf-8")
    assert sorted(load_versions(tmp_path)) == ["0001-syntetyczny", "0002-syntetyczny-ii"]
    assert sorted(load_versions(tmp_path, exclude="0002-syntetyczny-ii")) == ["0001-syntetyczny"]


def test_katalog_z_numerem_niezgodnym_ze_spec_jest_bledem(tmp_path: Path) -> None:
    directory = tmp_path / "0009-zly"
    directory.mkdir()
    (directory / SPEC_FILENAME).write_text(dump_spec(version_one()), encoding="utf-8")
    with pytest.raises(SpecError, match="nie pasuje"):
        load_versions(tmp_path)


def test_produkty_z_eksportu_instancji_maja_definicje_tylko_przy_kompletnych_wartosciach() -> None:
    """Wiersz bez kcal (jak „niepełne” produkty demo) trafia do indeksu bez definicji."""
    data = {
        "product_categories": [{"id": 7, "name": "Warzywa"}],
        "canonical_products": [
            {
                "id": 1,
                "name": "Burak",
                "measure_kind": "mass",
                "category_id": 7,
                "piece_weight_g": None,
                "kcal_100": "43.00",
                "protein_100": "1.60",
                "fat_100": "0.20",
                "carbs_100": "9.60",
                "fiber_100": "2.80",
                "sugars_100": "6.80",
                "glycemic_index": "64.0",
                "nutrition_source": "ręcznie",
            },
            {
                "id": 2,
                "name": "Rzodkiewka",
                "measure_kind": "mass",
                "category_id": 7,
                "piece_weight_g": None,
                "kcal_100": None,
                "protein_100": None,
                "fat_100": None,
                "carbs_100": None,
                "fiber_100": None,
                "sugars_100": None,
                "glycemic_index": None,
            },
        ],
        "product_unit_weights": [
            {"product_id": 1, "unit_label": "sztuka", "grams_per_unit": "80.00"}
        ],
    }
    entries = {entry.name: entry for entry in entries_from_export(data)}
    assert entries["Burak"].definition is not None
    assert dict(entries["Burak"].definition.unit_weights) == {"sztuka": 80}
    assert entries["Rzodkiewka"].definition is None
    assert entries["Burak"].kind == "instance"


def test_load_instance_export_odrzuca_plik_nie_w_formacie_v1(tmp_path: Path) -> None:
    path = tmp_path / "export.json"
    path.write_text('{"schema_version": 2, "data": {}}', encoding="utf-8")
    with pytest.raises(SpecError, match="transferu v1"):
        load_instance_export(path)


def test_klucz_lokalny_reused_nie_musi_byc_kluczem_z_wersji() -> None:
    """Wersja kolejna może nazwać produkt po swojemu — rozstrzyga nazwa, nie klucz."""
    payload = version_two_payload()
    payload["reused"][0]["key"] = "maka_wt"
    payload["recipes"][0]["ingredients"][0]["product"] = "maka_wt"
    payload["pdf_shopping_list_grams"]["maka_wt"] = payload["pdf_shopping_list_grams"].pop("maka")
    resolved = resolve_catalog(
        parse_spec(payload), build_index({"0001-syntetyczny": version_one()})
    )
    assert resolved.products["maka_wt"].name == "Mąka testowa"
    assert resolved.products["maka_wt"].key == "maka_wt"
