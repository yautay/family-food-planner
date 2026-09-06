"""Testy jednostkowe formatu transferu v1 (BATCH_14).

Zakres: kontrakt sekcji (kolejność = kolejność importu), serializacja wartości
(ADR-008: Decimal jako string), bezpieczeństwo nazw wpisów archiwum, walidacja
wersji pliku, wykrywanie kolizji po kluczu naturalnym i remapowanie referencji
wewnątrz payloadów szablonów.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.errors import NotFoundError
from app.core.uploads import UploadTooLargeError, resolve_upload_path
from app.modules.catalog.models import MeasureKind
from app.modules.transfer.importer import (
    ExistingEntity,
    IdMap,
    TransferValidationError,
    analyze,
    assert_archive_entries,
    assert_within_limit,
    assert_zip_signature,
    natural_key,
    read_document,
    remap_cycle_templates,
    remap_template_payload,
    remap_week_payload,
    resolve_references,
    safe_photo_name,
    unique_name,
)
from app.modules.transfer.schemas import (
    DATA_ENTRY_NAME,
    SCHEMA_VERSION,
    SECTION_ORDER,
    CollisionAction,
    ExportFile,
    TransferScope,
)
from app.modules.transfer.serializer import (
    SECTIONS_BY_NAME,
    Section,
    build_document,
    json_value,
    section_references,
    sections_for,
)

pytestmark = pytest.mark.unit


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _document(**data: list[dict[str, object]]) -> ExportFile:
    return ExportFile(
        schema_version=1,
        app_version="test",
        exported_at="2026-08-29T10:00:00+00:00",
        scope=TransferScope.USER,
        data=data,
    )


# --- kontrakt sekcji ----------------------------------------------------------------


def test_kazda_sekcja_kolejnosci_ma_opis_i_odwrotnie() -> None:
    """`SECTION_ORDER` i tabela `SECTIONS` opisują DOKŁADNIE ten sam zbiór sekcji."""
    assert set(SECTION_ORDER) == set(SECTIONS_BY_NAME)
    assert len(SECTION_ORDER) == len(set(SECTION_ORDER))


def test_referencje_wskazuja_sekcje_wczesniejsza_w_kolejnosci() -> None:
    """Kolejność importu musi wystarczyć do rozwiązania każdej referencji (FK RESTRICT)."""
    position = {name: index for index, name in enumerate(SECTION_ORDER)}
    for section in SECTIONS_BY_NAME.values():
        for column, target in section_references(section).items():
            assert position[target] < position[section.name], (
                f"{section.name}.{column} wskazuje {target}, który wchodzi później"
            )


def test_eksport_uzytkownika_pomija_sekcje_instancji() -> None:
    """Plik użytkownika nie zawiera kont, rodzin ani dziennika."""
    names = {section.name for section in sections_for(TransferScope.USER)}
    assert "users" not in names
    assert "households" not in names
    assert "audit_entries" not in names
    assert "users" in {section.name for section in sections_for(TransferScope.INSTANCE)}


def test_zadna_sekcja_nie_niesie_hasla_ani_tokenu() -> None:
    """Kolumny wrażliwe NIGDY nie wchodzą do formatu (07_SECURITY, ustalenie R3)."""
    forbidden = {"password_hash", "public_token", "token_revoked"}
    for section in SECTIONS_BY_NAME.values():
        assert not forbidden & set(section.columns)


# --- serializacja wartości ------------------------------------------------------------


def test_liczby_ida_do_pliku_jako_stringi_dziesietne() -> None:
    """ADR-008: `Decimal` nigdy nie zamienia się w float po drodze do JSON-a."""
    assert json_value(Decimal("1.500")) == "1.500"
    assert json_value(Decimal("1E+2")) == "100"
    assert json_value(MeasureKind.MASS) == "mass"
    assert json_value(date(2030, 1, 2)) == "2030-01-02"
    assert json_value([Decimal("0.1"), None]) == ["0.1", None]


def test_dokument_ma_naglowek_i_sekcje_w_ustalonej_kolejnosci() -> None:
    """Nagłówek niesie wersję i zakres, a klucze `data` idą w `SECTION_ORDER`."""
    document = build_document(
        scope=TransferScope.USER,
        app_version="0.1.0",
        exported_at=datetime(2026, 8, 29, 12, 0, 0),
        data={"tags": [{"id": 1, "name": "obiad", "is_system": False}]},
    )
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["scope"] == "user"
    keys = list(document["data"])
    assert keys == [section.name for section in sections_for(TransferScope.USER)]


# --- bezpieczeństwo archiwum ----------------------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        "photos/../../etc/passwd",
        "/etc/passwd",
        "photos\\..\\x.jpg",
        "inne/plik.txt",
        "export.json.bak",
    ],
)
def test_wpis_o_podejrzanej_sciezce_nie_jest_zdjeciem(entry: str) -> None:
    """Path traversal i wpisy spoza `photos/` są odrzucane po NAZWIE, przed odczytem."""
    assert safe_photo_name(entry) is None


def test_zdjecie_w_podkatalogu_jest_dozwolone() -> None:
    """Ścieżki z bazy bywają zagnieżdżone (`recipes/abc.jpg`) — te przechodzą."""
    assert safe_photo_name("photos/recipes/abc.jpg") == "recipes/abc.jpg"


def test_archiwum_z_wpisem_spoza_photos_konczy_sie_422() -> None:
    """Wpis o niedozwolonej ścieżce wywala archiwum, zanim cokolwiek rozpakujemy."""
    data = _zip_bytes({DATA_ENTRY_NAME: b"{}", "../zlo.txt": b"x"})
    with zipfile.ZipFile(io.BytesIO(data)) as archive, pytest.raises(TransferValidationError):
        assert_archive_entries(archive)


def test_zip_bomba_pada_na_rozmiarze_po_dekompresji() -> None:
    """Sumaryczny rozmiar po dekompresji liczymy z nagłówków, nie z rozpakowania."""
    data = _zip_bytes({DATA_ENTRY_NAME: b"{}", "photos/a.jpg": b"0" * 1024})
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.infolist()[1].file_size = 10 * 1024 * 1024 * 1024
        with pytest.raises(TransferValidationError):
            assert_archive_entries(archive)


def test_plik_bez_sygnatury_zip_nie_jest_archiwum() -> None:
    """Sniffing treści, nie rozszerzenia (07_SECURITY §6)."""
    with pytest.raises(TransferValidationError):
        assert_zip_signature(b"%PDF-1.7 udaje eksport")
    assert_zip_signature(b"PK\x03\x04reszta")


def test_paczka_ponad_limit_konczy_sie_413() -> None:
    """Limit rozmiaru sprawdzamy PRZED otwarciem archiwum."""
    with pytest.raises(UploadTooLargeError):
        assert_within_limit(2 * 1024 * 1024, limit_mb=1)
    assert_within_limit(1024, limit_mb=1)


def test_prywatny_podkatalog_jest_zamkniety_niezaleznie_od_wielkosci_liter(tmp_path: Any) -> None:
    """REVIEW R4 pkt 8: na Windows/macOS `Transfer/` trafia w ten sam plik co `transfer/`."""
    for variant in ("Transfer/abc.zip", "TRANSFER/abc.zip", "Import-PDF/x.pdf", "IMPORT-PDF/x.pdf"):
        with pytest.raises(NotFoundError):
            resolve_upload_path(variant, uploads_root=tmp_path)


def test_katalog_paczek_transferu_nie_jest_serwowany(tmp_path: Any) -> None:
    """`/uploads/*` sprawdza tylko sesję, więc paczka z KOMPLETEM danych konta
    nie ma prawa leżeć w serwowanym drzewie (ustalenie /code-review B14).

    Zdjęcia importu (`transfer-import/`) muszą zostać serwowane — prywatny jest
    wyłącznie katalog paczek, nie wszystko, co zaczyna się na „transfer".
    """
    with pytest.raises(NotFoundError):
        resolve_upload_path("transfer/abc.zip", uploads_root=tmp_path)
    with pytest.raises(NotFoundError):
        resolve_upload_path("transfer/abc.json", uploads_root=tmp_path)
    assert resolve_upload_path("transfer-import/x.jpg", uploads_root=tmp_path).name == "x.jpg"


# --- walidacja wersji -----------------------------------------------------------------


def test_plik_z_inna_wersja_schematu_daje_czytelny_komunikat() -> None:
    """`schema_version: 999` = 422 po polsku, nie 500 (Acceptance Criterion 7)."""
    payload = json.dumps({"schema_version": 999, "scope": "user", "data": {}}).encode()
    with (
        zipfile.ZipFile(io.BytesIO(_zip_bytes({DATA_ENTRY_NAME: payload}))) as archive,
        pytest.raises(TransferValidationError) as error,
    ):
        read_document(archive)
    assert "wersji aplikacji" in error.value.message
    assert error.value.status_code == 422


def test_plik_bez_export_json_konczy_sie_422() -> None:
    """Archiwum bez danych nie jest eksportem."""
    with (
        zipfile.ZipFile(io.BytesIO(_zip_bytes({"photos/a.jpg": b"x"}))) as archive,
        pytest.raises(TransferValidationError),
    ):
        read_document(archive)


# --- kolizje --------------------------------------------------------------------------


def test_kolizja_produktu_wykrywa_sie_po_normalized_name() -> None:
    """Ten sam produkt pisany inaczej to KOLIZJA, bo klucz liczy `normalize_name`."""
    document = _document(
        canonical_products=[
            {"id": 7, "name": "Cebula", "normalized_name": "cebula", "category_id": 1},
            {"id": 8, "name": "Marchew", "normalized_name": "marchew", "category_id": 1},
        ]
    )
    result = analyze(
        document,
        existing={"canonical_products": {"cebula": ExistingEntity(id=99, name="Cebula")}},
        archive_photos=[],
    )
    assert result.to_create["canonical_products"] == 1
    assert [(c.entity, c.source_id, c.existing_id) for c in result.collisions] == [
        ("canonical_products", 7, 99)
    ]
    assert result.collisions[0].default is CollisionAction.USE_EXISTING


def test_brak_zdjecia_w_archiwum_jest_ostrzezeniem_a_nie_bledem() -> None:
    """Encja bez pliku zdjęcia i tak wchodzi — z notką w raporcie (Implementation Notes)."""
    document = _document(recipes=[{"id": 1, "name": "Gołąbki", "photo_path": "recipes/brak.jpg"}])
    result = analyze(document, existing={}, archive_photos=[])
    assert result.to_create["recipes"] == 1
    assert any("brakuje" in warning for warning in result.warnings)


def test_klucz_naturalny_sekcji_bez_klucza_jest_pusty() -> None:
    """Sekcja bez kolizji (np. pozycje planu) nigdy nie trafia do raportu kolizji."""
    section = SECTIONS_BY_NAME["plan_meals"]
    assert section.key is None
    assert natural_key(section, {"id": 1, "name": "Obiad"}) is None


def test_nazwa_kopii_dostaje_sufiks_a_przy_zajetej_takze_licznik() -> None:
    """„Utwórz kopię" nie może wygenerować nazwy, która znowu koliduje."""
    assert unique_name("Cebula", set()) == "Cebula (import)"
    assert unique_name("Cebula", {"Cebula (import)"}) == "Cebula (import 2)"


# --- mapowanie identyfikatorów --------------------------------------------------------


def test_referencja_bez_pokrycia_przerywa_import() -> None:
    """Surowe id z pliku wskazałoby w nowej bazie przypadkową encję — więc 422."""
    id_map = IdMap(actor_user_id=1, actor_household_id=None)
    section = SECTIONS_BY_NAME["recipe_ingredients"]
    with pytest.raises(TransferValidationError):
        resolve_references(
            section,
            {"recipe_id": 5, "product_id": 9},
            id_map,
            section_references(section),
        )


def test_konto_i_rodzina_maja_fallback_na_importujacego() -> None:
    """Plik użytkownika nie niesie kont, więc właścicielem zostaje importujący."""
    id_map = IdMap(actor_user_id=42, actor_household_id=7)
    id_map.record("recipes", 1, 100)
    section: Section = SECTIONS_BY_NAME["recipes"]
    resolved = resolve_references(
        section,
        {"owner_user_id": 999, "household_id": 888},
        id_map,
        section_references(section),
    )
    assert resolved == {"owner_user_id": 42, "household_id": 7}


def test_payload_szablonu_dostaje_nowe_identyfikatory() -> None:
    """Referencje w JSONB baza pilnuje ZERO razy — remapuje je import."""
    id_map = IdMap(actor_user_id=1, actor_household_id=None)
    id_map.record("recipes", 5, 55)
    id_map.record("canonical_products", 9, 99)
    id_map.record("member_profiles", 3, 33)
    warnings: list[str] = []
    payload = {
        "v": 1,
        "title": None,
        "meals": [
            {
                "name": "Obiad",
                "items": [
                    {
                        "recipe_id": 5,
                        "servings": "2",
                        "servings_split": [{"member_profile_id": 3, "multiplier": "2"}],
                    },
                    {"product_id": 9, "amount": "100.000", "amount_unit": "g"},
                ],
            }
        ],
    }
    result = remap_template_payload(payload, id_map, warnings=warnings)
    items = result["meals"][0]["items"]
    assert items[0]["recipe_id"] == 55
    assert items[0]["servings_split"][0]["member_profile_id"] == 33
    assert items[1]["product_id"] == 99
    assert warnings == []


def test_martwa_referencja_w_payloadzie_usuwa_pozycje_z_ostrzezeniem() -> None:
    """Zostawienie surowego id trafiłoby w losowy przepis nowej bazy — więc wypada."""
    warnings: list[str] = []
    result = remap_template_payload(
        {"v": 1, "meals": [{"name": "Obiad", "items": [{"recipe_id": 5}]}]},
        IdMap(actor_user_id=1, actor_household_id=None),
        warnings=warnings,
    )
    assert result["meals"][0]["items"] == []
    assert warnings


def test_payload_tygodnia_remapuje_kazdy_dzien() -> None:
    """Szablon tygodnia to ten sam kształt dnia zagnieżdżony w `days[].day`."""
    id_map = IdMap(actor_user_id=1, actor_household_id=None)
    id_map.record("recipes", 5, 55)
    warnings: list[str] = []
    result = remap_week_payload(
        {
            "v": 1,
            "days": [
                {
                    "offset": 0,
                    "day": {"v": 1, "meals": [{"name": "O", "items": [{"recipe_id": 5}]}]},
                }
            ],
        },
        id_map,
        warnings=warnings,
    )
    assert result["days"][0]["day"]["meals"][0]["items"][0]["recipe_id"] == 55


def test_cykl_gubi_martwy_szablon_zamiast_wskazywac_w_pustke() -> None:
    """Cykl z jednym martwym id jest niesprawny CAŁY (doprecyzowanie R2) — id wypada."""
    id_map = IdMap(actor_user_id=1, actor_household_id=None)
    id_map.record("week_templates", 1, 11)
    warnings: list[str] = []
    assert remap_cycle_templates([1, 2], id_map, warnings=warnings) == [11]
    assert warnings
