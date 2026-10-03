"""Import: bezpieczne czytanie archiwum, raport DRY-RUN i przygotowanie wierszy.

Wszystko tutaj jest CZYSTE albo dotyka wyłącznie plików — bazy nie widzi
(zapytania i transakcję prowadzi `service.py`). Podział jest celowy: raport
dry-run musi dać się policzyć i przetestować bez sesji, bo jego cała wartość
polega na tym, że NIC nie zapisuje (04_API, Acceptance Criteria 3 karty B14).

Bezpieczeństwo archiwum (07_SECURITY §6) — kolejność jest częścią kontraktu:

1. limit rozmiaru pliku PRZED otwarciem (`zipfile` nie dostaje gigabajtów),
2. sygnatura `PK\\x03\\x04` — sniffing treści, nie rozszerzenia,
3. lista wpisów: tylko `export.json` i `photos/<nazwa>`; żadnych ścieżek
   absolutnych, `..`, backslashy ani dowiązań (path traversal),
4. sumaryczny rozmiar PO DEKOMPRESJI i liczba wpisów (zip-bomba) — liczone
   z nagłówków, więc bomba pada przed rozpakowaniem czegokolwiek.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from app.core.errors import AppError
from app.core.scope import RecipeScope, Scope
from app.core.uploads import UploadTooLargeError
from app.modules.transfer.schemas import (
    COPY_SUFFIX,
    DATA_ENTRY_NAME,
    PHOTOS_PREFIX,
    SCHEMA_VERSION,
    CollisionAction,
    CollisionRead,
    ExportFile,
    ExportHeader,
    TransferScope,
)
from app.modules.transfer.serializer import (
    SECTIONS_BY_NAME,
    Section,
    section_references,
    sections_for,
)

#: Ile wpisów może mieć archiwum (jedno zdjęcie = jeden wpis).
MAX_ARCHIVE_ENTRIES = 20_000
#: Sufit rozmiaru po dekompresji — ochrona przed zip-bombą.
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
#: Sufit samego `export.json` (rozpakowywany do pamięci, więc własny limit).
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
#: Sygnatura lokalnego nagłówka ZIP.
ZIP_SIGNATURE = b"PK\x03\x04"

NOT_A_ZIP = "Przesłany plik nie jest archiwum ZIP z eksportem danych."
BROKEN_ARCHIVE = "Archiwum jest uszkodzone i nie da się go odczytać."
NO_DATA_ENTRY = f"W archiwum brakuje pliku {DATA_ENTRY_NAME} z danymi eksportu."
BAD_ENTRY_NAME = (
    "Archiwum zawiera wpis o niedozwolonej ścieżce. "
    f"Dopuszczalne są wyłącznie {DATA_ENTRY_NAME} i katalog {PHOTOS_PREFIX}."
)
ARCHIVE_TOO_BIG = "Zawartość archiwum jest zbyt duża — odrzucono je bez rozpakowywania."
BROKEN_JSON = f"Plik {DATA_ENTRY_NAME} nie zawiera poprawnego JSON-a."
WRONG_VERSION = (
    "Plik pochodzi z nowszej lub innej wersji aplikacji ({found}) niż obsługiwana ({supported}). "
    "Zaktualizuj aplikację albo użyj pliku wyeksportowanego z tej wersji."
)
BROKEN_STRUCTURE = "Struktura pliku eksportu jest niezgodna z formatem — import przerwany."
IMPORT_NOT_FOUND = "Nie znaleziono wgranego pliku importu. Wgraj go ponownie."
INSTANCE_FILE_FOR_USER = (
    "To jest eksport całej instancji — zaimportować go może wyłącznie administrator "
    "w sekcji „Instancja”."
)


def too_large_message(limit_mb: int) -> str:
    """Komunikat 413 z limitem, który realnie obowiązuje w tej instalacji."""
    return f"Plik jest za duży — paczka transferu może mieć najwyżej {limit_mb} MB."


class TransferValidationError(AppError):
    """422 — plik nie spełnia kontraktu formatu (wersja, struktura, referencje)."""

    status_code = 422
    code = "validation_error"


# --- czytanie archiwum ---------------------------------------------------------------


def assert_within_limit(size: int, *, limit_mb: int) -> None:
    """Limit rozmiaru paczki — sprawdzany, ZANIM `zipfile` cokolwiek otworzy."""
    if size > limit_mb * 1024 * 1024:
        raise UploadTooLargeError(too_large_message(limit_mb))


def assert_zip_signature(data: bytes) -> None:
    """Sniffing treści: brak sygnatury ZIP = 422 niezależnie od nazwy pliku."""
    if not data.startswith(ZIP_SIGNATURE):
        raise TransferValidationError(NOT_A_ZIP)


def safe_photo_name(entry_name: str) -> str | None:
    """`photos/x/y.jpg` → `x/y.jpg`; wpis podejrzany (`..`, absolutny) → `None`."""
    if entry_name.endswith("/"):
        return None
    if "\\" in entry_name or entry_name.startswith("/"):
        return None
    if not entry_name.startswith(PHOTOS_PREFIX):
        return None
    relative = entry_name[len(PHOTOS_PREFIX) :]
    if not relative:
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or pure.drive:
        return None
    return str(pure)


def assert_archive_entries(archive: zipfile.ZipFile) -> None:
    """Lista wpisów i rozmiary po dekompresji — zanim cokolwiek rozpakujemy."""
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise TransferValidationError(ARCHIVE_TOO_BIG)

    total = 0
    for info in infos:
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise TransferValidationError(ARCHIVE_TOO_BIG)
        if info.filename == DATA_ENTRY_NAME:
            if info.file_size > MAX_DOCUMENT_BYTES:
                raise TransferValidationError(ARCHIVE_TOO_BIG)
            continue
        if info.is_dir() and info.filename.rstrip("/") == PHOTOS_PREFIX.rstrip("/"):
            continue
        if safe_photo_name(info.filename) is None:
            raise TransferValidationError(BAD_ENTRY_NAME)


def photo_names(archive: zipfile.ZipFile) -> set[str]:
    """Ścieżki względne zdjęć obecnych w archiwum (po walidacji wpisów)."""
    return {
        name for info in archive.infolist() if (name := safe_photo_name(info.filename)) is not None
    }


def read_document(archive: zipfile.ZipFile) -> ExportFile:
    """`export.json` → zwalidowany model. Zła wersja i zły kształt = 422 po polsku."""
    try:
        raw = archive.read(DATA_ENTRY_NAME)
    except KeyError as exc:
        raise TransferValidationError(NO_DATA_ENTRY) from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransferValidationError(BROKEN_JSON) from exc

    if not isinstance(payload, dict):
        raise TransferValidationError(BROKEN_STRUCTURE)

    # Wersję sprawdzamy PRZED pełną walidacją: plik z przyszłości ma dostać
    # komunikat o wersji, a nie listę pól, których nasz model nie zna.
    try:
        header = ExportHeader.model_validate(payload)
    except ValidationError as exc:
        raise TransferValidationError(BROKEN_STRUCTURE) from exc
    if header.schema_version != SCHEMA_VERSION:
        raise TransferValidationError(
            WRONG_VERSION.format(found=header.schema_version, supported=SCHEMA_VERSION)
        )

    try:
        return ExportFile.model_validate(payload)
    except ValidationError as exc:
        raise TransferValidationError(BROKEN_STRUCTURE) from exc


def open_archive(path: Path) -> zipfile.ZipFile:
    """Otwórz zwalidowane archiwum. Wołający zamyka je (`with`)."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise TransferValidationError(BROKEN_ARCHIVE) from exc
    try:
        assert_archive_entries(archive)
    except Exception:
        archive.close()
        raise
    return archive


@dataclass
class IdMap:
    """Mapa stary→nowy identyfikator: z pliku na bazę docelową.

    Buduje ją sekcja po sekcji `apply`, ale używa jej też raport DRY-RUN —
    kolumny `merge_key` bywają kluczami obcymi, więc bez tego tłumaczenia
    raport nie umiałby sprawdzić, czy wiersz już w bazie jest (BATCH_20).

    `users` i `households` mają FALLBACK na konto wykonujące import: plik
    użytkownika nie niesie tych sekcji, a wiersze i tak trzymają identyfikatory
    z instancji źródłowej. Bez fallbacku import USERA próbowałby wstawić encje
    z cudzym `owner_user_id`, czyli dokładnie to, czego zabrania §Security karty.
    """

    actor_user_id: int
    actor_household_id: int | None
    maps: dict[str, dict[Any, Any]] = field(default_factory=dict)

    def record(self, section: str, old: Any, new: Any) -> None:
        self.maps.setdefault(section, {})[old] = new

    def get(self, section: str, old: Any) -> Any | None:
        """Nowy identyfikator albo `None`, gdy referencja nie ma pokrycia."""
        if old is None:
            return None
        mapped = self.maps.get(section, {}).get(old)
        if mapped is not None:
            return mapped
        if section == "users":
            return self.actor_user_id
        if section == "households":
            return self.actor_household_id
        return None


# --- raport dry-run ------------------------------------------------------------------


@dataclass(frozen=True)
class ExistingEntity:
    """Wiersz, który JUŻ jest w bazie i nosi ten sam klucz naturalny."""

    id: Any
    name: str


#: Sekcja → {klucz → istniejący wiersz}. Buduje to `service.py`. Kluczem jest
#: albo klucz NATURALNY sekcji (`Section.key` — kolizje nazw), albo klucz
#: SCALANIA (`Section.merge_key` — wiersze, które `apply` scali albo pominie).
#: Żadna sekcja nie ma obu naraz, więc jedna mapa wystarcza na oba przypadki.
ExistingIndex = Mapping[str, Mapping[str, ExistingEntity]]

#: Separator części klucza złożonego. Znak sterujący, żeby wartość kolumny
#: („Wołowina|mielona") nie mogła udać granicy między kolumnami.
KEY_SEPARATOR = "\x1f"


def natural_key(section: Section, row: Mapping[str, Any]) -> str | None:
    """Wartość klucza naturalnego wiersza z pliku (albo `None`, gdy sekcja go nie ma)."""
    if section.key is None:
        return None
    value = row.get(section.key)
    return None if value is None else str(value)


def merge_index_key(values: Iterable[Any]) -> str:
    """Wartości kolumn `merge_key` → jeden klucz mapy. Jedno miejsce na obie strony."""
    return KEY_SEPARATOR.join("" if value is None else str(value) for value in values)


def merge_lookup_key(section: Section, row: Mapping[str, Any], id_map: IdMap) -> str | None:
    """Klucz scalania wiersza Z PLIKU wyrażony w identyfikatorach BAZY DOCELOWEJ.

    Kolumny `merge_key` bywają kluczami obcymi (`product_id`, `user_id`), a plik
    niesie w nich identyfikatory instancji ŹRÓDŁOWEJ — bez przetłumaczenia ich
    przez `id_map` porównanie z bazą nie znaczyłoby nic.

    `None` = wiersza nie da się dopasować do niczego, co już jest, bo jego
    rodzic dopiero powstanie w tym imporcie. Taki wiersz na pewno zostanie
    utworzony i tak ma go policzyć raport.
    """
    if section.merge_key is None:
        return None
    references = section_references(section)
    parts: list[Any] = []
    for column in section.merge_key:
        target = references.get(column)
        if target is None:
            parts.append(row.get(column))
            continue
        mapped = id_map.get(target, row.get(column))
        if mapped is None:
            return None
        parts.append(mapped)
    return merge_index_key(parts)


def display_name(section: Section, row: Mapping[str, Any]) -> str:
    """Nazwa pokazywana człowiekowi w raporcie kolizji."""
    column = section.label or section.key
    if column is None:
        return ""
    return str(row.get(column, ""))


@dataclass(frozen=True)
class DryRunResult:
    """Wynik analizy pliku: co powstanie, co koliduje, o czym ostrzegamy."""

    scope: TransferScope
    exported_at: str
    app_version: str
    to_create: dict[str, int]
    collisions: list[CollisionRead]
    warnings: list[str]
    photos: int


def parent_blocked(
    section: Section, row: Mapping[str, Any], blocked: Mapping[str, set[Any]]
) -> bool:
    """Czy rodzic kompozycji tego wiersza jest reużyty albo pominięty (decyzja D22).

    Wspólne dla raportu DRY-RUN i dla zapisu — inaczej raport obiecywałby wiersze,
    których `apply` nie utworzy.
    """
    if section.parent is None:
        return False
    target = section_references(section).get(section.parent)
    if target is None:
        return False
    source_id = row.get(section.parent)
    return source_id is not None and source_id in blocked.get(target, set())


def mark_blocked(section: Section, row: Mapping[str, Any], blocked: dict[str, set[Any]]) -> None:
    """Zapamiętaj, że zawartości TEGO wiersza z pliku import nie tyka (D22)."""
    if section.pk is None:
        return
    source_id = row.get(section.pk)
    if source_id is not None:
        blocked.setdefault(section.name, set()).add(source_id)


def merged_days_warning(count: int) -> str:
    """Zbiorcze ostrzeżenie o scalanych dniach planu (decyzja **D24**).

    Zbiorcze, nie per dzień: raport ma być czytelny na telefonie, a lista
    kilkudziesięciu dat niczego nie dodaje — po imporcie widać je w planie.
    Odmiana liczebnika jest wypisana, bo to tekst dla człowieka (D3: PL, bez
    warstwy i18n, więc nie ma komu jej policzyć za nas).
    """
    if count == 1:
        phrase = "1 dzień planu zostanie scalony"
    elif 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        phrase = f"{count} dni planu zostaną scalone"
    else:
        phrase = f"{count} dni planu zostanie scalonych"
    return f"{phrase} z tym, co już masz — posiłki, które już tam są, zostaną nietknięte."


UNKNOWN_SCOPE = (
    "Plik zawiera nieznany zakres widoczności „{value}” w sekcji {section} — import przerwany."
)


def validate_row_scope(section: Section, row: Mapping[str, Any]) -> None:
    """Zakres wiersza musi być wartością, którą ta sekcja zna (422, nie `ValueError`).

    Przepisy znają `private`/`household`/`global` (D32), reszta encji ze scope
    tylko `private`/`household` — `global` w pliku dla dnia planu, szablonu, tury,
    generacji albo listy to plik niezgodny z formatem, a nie „obcięty do rodziny".
    Sprawdzenie jest CZYSTE i wspólne dla raportu DRY-RUN i dla zapisu: bez tego
    raport meldowałby sukces, a `apply` wywracał się dopiero na `coerce_value`.
    """
    if not section.scoped or "scope" not in row:
        return
    allowed = RecipeScope if section.name == "recipes" else Scope
    value = row["scope"]
    if value is not None and (
        not isinstance(value, str) or value not in {member.value for member in allowed}
    ):
        raise TransferValidationError(UNKNOWN_SCOPE.format(value=value, section=section.name))


def global_recipes_warning(count: int) -> str:
    """Ostrzeżenie DRY-RUN: przepisy „dla wszystkich" wchodzą jako kopie importującego (D32)."""
    if count == 1:
        phrase = "1 przepis był dostępny dla wszystkich rodzin"
    elif 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        phrase = f"{count} przepisy były dostępne dla wszystkich rodzin"
    else:
        phrase = f"{count} przepisów było dostępnych dla wszystkich rodzin"
    return (
        f"{phrase} — po wczytaniu staną się Twoimi kopiami (rodzinnymi albo prywatnymi). "
        "Wspólne przepisy dla wszystkich rodzin publikuje wyłącznie administrator."
    )


def analyze(
    document: ExportFile,
    *,
    existing: ExistingIndex,
    archive_photos: Iterable[str],
    actor_user_id: int,
    actor_household_id: int | None,
) -> DryRunResult:
    """Policz raport DRY-RUN. Funkcja czysta — nie zapisuje ani nie czyta bazy.

    Liczby są liczone dla decyzji DOMYŚLNYCH (`USE_EXISTING` przy każdej kolizji),
    bo tak samo zachowa się `apply`, gdy użytkownik niczego nie zmieni — łącznie
    z pomijaniem dzieci reużytego rodzica (D22) i z wierszami, które `apply`
    scali albo pominie po `merge_key` (D24 + dług U21, BATCH_20).

    `actor_*` nie łamią czystości: to dane WEJŚCIOWE konta wykonującego import,
    potrzebne `IdMap` dokładnie tak samo jak w `apply` — plik użytkownika nie
    niesie sekcji `users`, a wiersze i tak trzymają identyfikatory z instancji
    źródłowej.
    """
    available = set(archive_photos)
    to_create: dict[str, int] = {}
    collisions: list[CollisionRead] = []
    warnings: list[str] = []
    missing_photos = 0
    merged_days = 0
    global_recipes = 0
    blocked: dict[str, set[Any]] = {}
    # Tłumaczenie identyfikatorów z pliku na te z bazy — wypełniane wierszami,
    # które import ROZPOZNAŁ jako już istniejące. Wiersz dopiero tworzony nie ma
    # jeszcze id, więc jego dzieci trafiają do `to_create` i to jest poprawne.
    id_map = IdMap(actor_user_id=actor_user_id, actor_household_id=actor_household_id)

    for section in sections_for(document.scope):
        rows = document.data.get(section.name) or []
        if not rows:
            continue
        section_existing = existing.get(section.name, {})
        creating = 0
        for row in rows:
            validate_row_scope(section, row)
            if (
                section.name == "recipes"
                and document.scope is TransferScope.USER
                and row.get("scope") == RecipeScope.GLOBAL.value
            ):
                global_recipes += 1
            if parent_blocked(section, row, blocked):
                mark_blocked(section, row, blocked)
                continue
            if section.photo is not None:
                path = row.get(section.photo)
                if path and str(path) not in available:
                    missing_photos += 1

            key = natural_key(section, row)
            if key is None and section.merge_key is not None:
                # Sekcja bez kolizji, ale z UNIQUE-iem: `apply` scali ją
                # (`plan_days`) albo pominie (`ON CONFLICT DO NOTHING`).
                # W obu razach NIC nie powstaje i raport ma to powiedzieć.
                merge_key = merge_lookup_key(section, row, id_map)
                hit = section_existing.get(merge_key) if merge_key is not None else None
                if hit is None:
                    creating += 1
                    continue
                mark_blocked(section, row, blocked)
                if section.pk is not None:
                    id_map.record(section.name, row.get(section.pk), hit.id)
                if section.name == "plan_days":
                    merged_days += 1
                continue

            match = section_existing.get(key) if key is not None else None
            if match is None:
                creating += 1
                continue
            mark_blocked(section, row, blocked)
            if section.pk is not None:
                # Domyślną decyzją jest „użyj istniejącego", więc dzieci i klucze
                # scalania mają się rozwiązywać na TEN wiersz — jak w `apply`.
                id_map.record(section.name, row.get(section.pk), match.id)
            if section.auto_reuse:
                warnings.append(
                    f"„{display_name(section, row)}” już istnieje — użyto istniejącego wpisu."
                )
                continue
            source_id = row.get(section.pk) if section.pk else None
            if not isinstance(source_id, int):
                # Sekcja z kluczem naturalnym ZAWSZE ma własne id w pliku;
                # jego brak znaczy, że plik nie trzyma się formatu.
                raise TransferValidationError(BROKEN_STRUCTURE)
            collisions.append(
                CollisionRead(
                    entity=section.name,
                    source_id=source_id,
                    name=display_name(section, row),
                    existing_id=int(match.id) if isinstance(match.id, int) else 0,
                    existing_name=match.name,
                    default=CollisionAction.USE_EXISTING,
                )
            )
        if creating:
            to_create[section.name] = creating

    if merged_days:
        warnings.append(merged_days_warning(merged_days))
    if global_recipes:
        warnings.append(global_recipes_warning(global_recipes))
    if missing_photos:
        warnings.append(
            f"W archiwum brakuje {missing_photos} zdjęć — te pozycje powstaną bez zdjęcia."
        )

    return DryRunResult(
        scope=document.scope,
        exported_at=document.exported_at,
        app_version=document.app_version,
        to_create=to_create,
        collisions=collisions,
        warnings=warnings,
        photos=len(available),
    )


# --- przygotowanie wierszy do zapisu --------------------------------------------------


DEAD_REFERENCE = (
    "Plik wskazuje wiersz, którego nie ma w tym samym pliku "
    "({section}.{column} = {value}) — import przerwany, baza nietknięta."
)


def resolve_references(
    section: Section,
    row: Mapping[str, Any],
    id_map: IdMap,
    references: Mapping[str, str],
) -> dict[str, Any]:
    """Klucze obce z pliku → identyfikatory z bazy docelowej.

    Referencja bez pokrycia to BŁĄD, nie ostrzeżenie: zostawienie surowego id
    z pliku wskazałoby w nowej bazie przypadkową, cudzą encję o tym numerze.
    """
    resolved: dict[str, Any] = {}
    for column, target in references.items():
        raw = row.get(column)
        if raw is None:
            resolved[column] = None
            continue
        mapped = id_map.get(target, raw)
        if mapped is None and target != "households":
            raise TransferValidationError(
                DEAD_REFERENCE.format(section=section.name, column=column, value=raw)
            )
        resolved[column] = mapped
    return resolved


def unique_name(base: str, taken: set[str], *, normalize: Any = None) -> str:
    """Nazwa kopii z sufiksem „(import)"; przy dalszej kolizji — z licznikiem."""
    candidate = f"{base}{COPY_SUFFIX}"
    counter = 2
    key = normalize(candidate) if normalize else candidate
    while key in taken:
        candidate = f"{base}{COPY_SUFFIX[:-1]} {counter})"
        key = normalize(candidate) if normalize else candidate
        counter += 1
    return candidate


def decisions_by_key(
    decisions: Sequence[Any],
) -> dict[tuple[str, int], CollisionAction]:
    """Lista decyzji z żądania → słownik `(sekcja, id z pliku) → akcja`."""
    return {(item.entity, item.source_id): item.action for item in decisions}


# --- remapowanie referencji wewnątrz payloadów szablonów -----------------------------


def remap_template_payload(
    payload: Mapping[str, Any], id_map: IdMap, *, warnings: list[str]
) -> dict[str, Any]:
    """Payload szablonu DNIA (`v:1`) z przemapowanymi `recipe_id`/`product_id`.

    Baza nie pilnuje tych referencji (siedzą w JSONB), więc robi to import.
    Pozycja, której referencji nie da się przemapować, jest USUWANA razem
    z ostrzeżeniem — zostawienie surowego id wskazałoby w nowej bazie
    przypadkowy przepis o tym numerze, co jest gorsze niż brak pozycji.
    """
    result = dict(payload)
    meals = []
    for meal in payload.get("meals") or []:
        meal_copy = dict(meal)
        items = []
        for item in meal.get("items") or []:
            item_copy = dict(item)
            dropped = False
            for column, target in (("recipe_id", "recipes"), ("product_id", "canonical_products")):
                raw = item_copy.get(column)
                if raw is None:
                    continue
                mapped = id_map.get(target, raw)
                if mapped is None:
                    dropped = True
                    break
                item_copy[column] = mapped
            if dropped:
                warnings.append("Pominięto pozycję szablonu wskazującą nieistniejący wpis.")
                continue
            splits = []
            for split in item_copy.get("servings_split") or []:
                mapped_profile = id_map.get("member_profiles", split.get("member_profile_id"))
                if mapped_profile is None:
                    warnings.append("Pominięto rozkład porcji dla nieistniejącego profilu.")
                    continue
                splits.append({**split, "member_profile_id": mapped_profile})
            item_copy["servings_split"] = splits
            items.append(item_copy)
        meal_copy["items"] = items
        meals.append(meal_copy)
    result["meals"] = meals
    return result


def remap_week_payload(
    payload: Mapping[str, Any], id_map: IdMap, *, warnings: list[str]
) -> dict[str, Any]:
    """Payload szablonu TYGODNIA — ten sam zabieg, co dla dnia, w `days[].day`."""
    result = dict(payload)
    result["days"] = [
        {**entry, "day": remap_template_payload(entry.get("day") or {}, id_map, warnings=warnings)}
        for entry in payload.get("days") or []
    ]
    return result


def remap_cycle_templates(
    template_ids: Sequence[int], id_map: IdMap, *, warnings: list[str]
) -> list[int]:
    """`week_cycles.template_ids` → nowe identyfikatory; martwe pozycje wypadają.

    Cykl z JEDNYM martwym id jest niesprawny CAŁY (`apply_cycle` sprawdza
    wszystkie id przed instancjacją, doprecyzowanie REVIEW R2), więc martwe
    wpisy trzeba usunąć, a nie przepisać.
    """
    mapped: list[int] = []
    for template_id in template_ids:
        new_id = id_map.get("week_templates", template_id)
        if new_id is None:
            warnings.append("Pominięto w cyklu szablon tygodnia, którego nie ma w pliku.")
            continue
        mapped.append(int(new_id))
    return mapped


def sections_present(document: ExportFile) -> list[Section]:
    """Sekcje pliku w kolejności importu; nieznane nazwy są ignorowane."""
    return [
        SECTIONS_BY_NAME[section.name]
        for section in sections_for(document.scope)
        if document.data.get(section.name)
    ]
