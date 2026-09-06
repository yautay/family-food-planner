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
    merge_index_key,
    merged_days_warning,
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


def test_allowlista_katalogow_dziala_niezaleznie_od_wielkosci_liter(tmp_path: Any) -> None:
    """REVIEW R4 pkt 8: na Windows/macOS `Recipes/` trafia w ten sam plik co `recipes/`.

    Allowlista musi więc porównywać niezależnie od systemu — inaczej ta sama
    ścieżka byłaby raz serwowana, raz nie, zależnie od hosta.
    """
    for variant in ("Recipes/a.jpg", "RECIPES/a.jpg", "Retail/b.jpg"):
        assert resolve_upload_path(variant, uploads_root=tmp_path).name in {"a.jpg", "b.jpg"}
    for variant in ("Transfer/abc.zip", "TRANSFER/abc.zip"):
        with pytest.raises(NotFoundError):
            resolve_upload_path(variant, uploads_root=tmp_path)


def test_serwowane_sa_wylacznie_katalogi_z_allowlisty(tmp_path: Any) -> None:
    """`/uploads/*` sprawdza tylko sesję, więc lista ZAKAZANYCH była pułapką (BATCH_20).

    Katalog, o którym kod już nie wie — bo funkcja, która do niego pisała,
    została wycofana — musi być zamknięty SAM Z SIEBIE. Przy liście zakazanych
    stawał się pobieralny dla każdego zalogowanego w chwili, gdy znikał z niej
    wpis. Paczka transferu (KOMPLET danych konta) jest tu przypadkiem
    szczególnym: leży w katalogu uploadów i nadal nie może być serwowana,
    a zdjęcia rozpakowane z niej (`transfer-import/`) — muszą.
    """
    for closed in (
        "transfer/abc.zip",
        "transfer/abc.json",
        "wycofany-modul/x.pdf",
        "x.jpg",  # plik w korzeniu uploadów nie należy do żadnego katalogu
    ):
        with pytest.raises(NotFoundError):
            resolve_upload_path(closed, uploads_root=tmp_path)
    assert resolve_upload_path("transfer-import/x.jpg", uploads_root=tmp_path).name == "x.jpg"
    assert resolve_upload_path("recipes/x.jpg", uploads_root=tmp_path).name == "x.jpg"
    assert resolve_upload_path("retail/x.jpg", uploads_root=tmp_path).name == "x.jpg"


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


def _analyze(document: Any, *, existing: Any, archive_photos: Any = (), actor_id: int = 1) -> Any:
    """`analyze` z domyślnym kontem importującym — testy kolizji go nie badają.

    `actor_*` są w sygnaturze od BATCH_20: `analyze` tłumaczy przez nie klucze
    scalania (`plan_days.owner_user_id`), tak samo jak robi to `apply`.
    """
    return analyze(
        document,
        existing=existing,
        archive_photos=archive_photos,
        actor_user_id=actor_id,
        actor_household_id=None,
    )


def test_kolizja_produktu_wykrywa_sie_po_normalized_name() -> None:
    """Ten sam produkt pisany inaczej to KOLIZJA, bo klucz liczy `normalize_name`."""
    document = _document(
        canonical_products=[
            {"id": 7, "name": "Cebula", "normalized_name": "cebula", "category_id": 1},
            {"id": 8, "name": "Marchew", "normalized_name": "marchew", "category_id": 1},
        ]
    )
    result = _analyze(
        document,
        existing={"canonical_products": {"cebula": ExistingEntity(id=99, name="Cebula")}},
    )
    assert result.to_create["canonical_products"] == 1
    assert [(c.entity, c.source_id, c.existing_id) for c in result.collisions] == [
        ("canonical_products", 7, 99)
    ]
    assert result.collisions[0].default is CollisionAction.USE_EXISTING


def test_brak_zdjecia_w_archiwum_jest_ostrzezeniem_a_nie_bledem() -> None:
    """Encja bez pliku zdjęcia i tak wchodzi — z notką w raporcie (Implementation Notes)."""
    document = _document(recipes=[{"id": 1, "name": "Gołąbki", "photo_path": "recipes/brak.jpg"}])
    result = _analyze(document, existing={})
    assert result.to_create["recipes"] == 1
    assert any("brakuje" in warning for warning in result.warnings)


def test_scalany_dzien_planu_nie_wchodzi_do_to_create_i_dostaje_ostrzezenie() -> None:
    """D24 + dług U21: raport mówi PRAWDĘ o dniu planu, który `apply` scali.

    Do BATCH_20 `analyze` nie znało kluczy scalania, więc obiecywało utworzenie
    dnia, którego `apply` nie tworzy (`UNIQUE(owner_user_id, day)`), a razem
    z nim jego posiłków — a te przy scaleniu są pomijane w całości (D22).
    """
    document = _document(
        plan_days=[
            {"id": 1, "owner_user_id": 5, "day": "2030-03-04", "title": None, "scope": "private"},
            {"id": 2, "owner_user_id": 5, "day": "2030-03-05", "title": None, "scope": "private"},
        ],
        plan_meals=[{"id": 11, "plan_day_id": 1, "name": "Obiad", "position": 0}],
    )
    # Klucz indeksu jest w identyfikatorach BAZY: dzień należy do importującego.
    existing = {"plan_days": {merge_index_key([7, "2030-03-04"]): ExistingEntity(id=42, name="")}}

    result = _analyze(document, existing=existing, actor_id=7)

    assert result.to_create["plan_days"] == 1
    assert "plan_meals" not in result.to_create
    assert [w for w in result.warnings if "scalony" in w] == [
        "1 dzień planu zostanie scalony z tym, co już masz — "
        "posiłki, które już tam są, zostaną nietknięte."
    ]


def test_odmiana_liczebnika_w_ostrzezeniu_o_scaleniu() -> None:
    """Tekst czyta człowiek, a UI nie ma warstwy i18n (D3) — odmianę robimy sami."""
    assert merged_days_warning(1).startswith("1 dzień planu zostanie scalony")
    assert merged_days_warning(3).startswith("3 dni planu zostaną scalone")
    assert merged_days_warning(7).startswith("7 dni planu zostanie scalonych")
    assert merged_days_warning(13).startswith("13 dni planu zostanie scalonych")
    assert merged_days_warning(22).startswith("22 dni planu zostaną scalone")


def test_wiersz_idempotentny_ktory_juz_jest_nie_wchodzi_do_to_create() -> None:
    """U21: `ON CONFLICT DO NOTHING` nic nie tworzy, więc raport nie ma tego obiecywać.

    Cel żywieniowy jest tu przypadkiem GRANICZNYM i dlatego wybranym: nie ma
    rodzica kompozycji, więc nie chroni go pomijanie dzieci reużytego wiersza
    (D22) — jedyne, co powstrzymuje raport przed zawyżeniem, to klucz scalania
    `(user_id, valid_from)`. Plik użytkownika nie niesie sekcji `users`, więc
    `user_id` rozwiązuje się na konto wykonujące import.
    """
    document = _document(
        user_nutrition_goals=[
            {"id": 1, "user_id": 5, "valid_from": "2030-01-01", "kcal": "2000"},
            {"id": 2, "user_id": 5, "valid_from": "2030-06-01", "kcal": "2100"},
        ]
    )
    existing = {
        "user_nutrition_goals": {
            merge_index_key([7, "2030-01-01"]): ExistingEntity(id=99, name=""),
        }
    }

    result = _analyze(document, existing=existing, actor_id=7)

    assert result.to_create["user_nutrition_goals"] == 1


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
