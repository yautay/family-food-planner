"""Indeks katalogu: co JUŻ istnieje, zanim nowy PDF założy kolejny produkt (D31 pkt 5).

Źródła wiedzy o istniejących produktach:

- **wersje** — `data/diet-imports/*/spec.json` (suma wszystkich wersji = katalog
  produktów tego narzędzia); to źródło ma PEŁNE definicje, więc z niego paczka
  kolejnej wersji bierze produkty do reużycia;
- **eksport instancji** (`--instance-export`) — produkty założone ręcznie w UI,
  których nie ma w żadnej wersji; pełna definicja, gdy wiersz ma komplet wartości;
- **seed demo** (`scripts/seed_demo.py`) — wyłącznie NAZWY: to dane deweloperskie,
  nie katalog produkcji i nie mają kompletnych wartości.

Klucz tożsamości = `catalog.naming.normalize_name` (ta sama funkcja, którą liczy
baza i import transferu). Własna normalizacja rozjechałaby się z bazą dokładnie
tam, gdzie import widzi kolizję, a narzędzie nie.

Konflikt definicji (ta sama nazwa, inny `measure_kind`) wobec wersji albo eksportu
instancji to BŁĄD zatrzymujący: import REUŻYWA produkt po nazwie, więc składnik
zapisany w sztukach trafiłby na produkt liczony w gramach i `normalize_amount`
rzucałby wyjątek przy pierwszej edycji w UI. Konflikt z seedem demo to głośne
OSTRZEŻENIE (nie błąd): demo jest tylko na bazach deweloperskich, ale paczka
zaimportowana do bazy z seedem skończyłaby się dokładnie tym samym.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import normalize_unit_label
from scripts.pdf_extract.spec import (
    SPEC_FILENAME,
    Per100,
    ProductSpec,
    Spec,
    SpecError,
    load_spec,
)

EntryKind = Literal["version", "instance", "demo"]
MatchKind = Literal["exact", "alias", "similar", "new"]

#: Próg podobieństwa nazw (SequenceMatcher) i odrzucenia szumu przy podobieństwie tokenów.
SIMILARITY_THRESHOLD = Decimal("0.72")
_SUBSET_SCORE = Decimal("0.9")
_SAME_HEAD_SCORE = Decimal("0.75")
_MIN_TOKEN_LENGTH = 3


class CatalogConflictError(SpecError):
    """Ta sama nazwa produktu, ale inna definicja miary — błąd zatrzymujący (D31)."""


@dataclass(frozen=True)
class CatalogEntry:
    """Jeden produkt, który już istnieje (w wersji, w instancji albo w seedzie demo)."""

    name: str
    normalized: str
    measure_kind: str
    kind: EntryKind
    #: etykieta źródła, np. `0001-dieta-2000`, `instancja`, `demo`
    origin: str
    #: pełna definicja (do paczki); `None` dla demo i niekompletnych wierszy instancji
    definition: ProductSpec | None = None
    #: nazwy scalone w ten produkt (decyzje właściciela z wcześniejszych wersji)
    aliases: tuple[str, ...] = ()

    @property
    def hard(self) -> bool:
        """Czy konflikt miary z tym wpisem jest błędem (wersje i instancja), a nie ostrzeżeniem."""
        return self.kind != "demo"


@dataclass(frozen=True)
class Candidate:
    """Podobny produkt z katalogu — materiał propozycji scalenia (BRAMKA 1)."""

    entry: CatalogEntry
    score: Decimal


@dataclass(frozen=True)
class Match:
    """Wynik zestawienia jednej nazwy z katalogiem."""

    name: str
    kind: MatchKind
    entry: CatalogEntry | None = None
    candidates: tuple[Candidate, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogIndex:
    """Wszystkie znane produkty po `normalize_name` oraz nazwy przepisów z wersji."""

    entries: Mapping[str, CatalogEntry]
    aliases: Mapping[str, CatalogEntry]
    #: znormalizowana nazwa przepisu → etykieta wersji (import reużywa przepis po nazwie)
    recipe_names: Mapping[str, str] = field(default_factory=dict)
    versions: Mapping[str, Spec] = field(default_factory=dict)


# --- podobieństwo ---------------------------------------------------------------------


def _tokens(name: str) -> set[str]:
    return {token for token in normalize_name(name).split() if len(token) >= _MIN_TOKEN_LENGTH}


def _ratio(left: str, right: str) -> Decimal:
    """Podobieństwo znakowe 2·M/T jak `SequenceMatcher.ratio`, ale na `Decimal` (ADR-008)."""
    total = len(left) + len(right)
    if total == 0:
        return Decimal(1)
    matched = sum(block.size for block in SequenceMatcher(None, left, right).get_matching_blocks())
    return Decimal(2 * matched) / Decimal(total)


def similarity(left: str, right: str) -> Decimal:
    """Podobieństwo dwóch nazw 0..1: SequenceMatcher albo zawieranie się tokenów.

    „Skyr" ⊂ „Skyr naturalny" daje 0.9 (to ten sam produkt w innej odmianie),
    „Pierś z kurczaka" vs „Pierś z indyka" łapie wspólny pierwszy wyraz. Funkcja jest
    deterministyczna i czysta — kolejność kandydatów nie zależy od uruchomienia.
    """
    a, b = normalize_name(left), normalize_name(right)
    if a == b:
        return Decimal(1)
    ratio = _ratio(a, b)
    tokens_a, tokens_b = _tokens(left), _tokens(right)
    if tokens_a and tokens_b and (tokens_a <= tokens_b or tokens_b <= tokens_a):
        ratio = max(ratio, _SUBSET_SCORE)
    head_a, head_b = (a.split() or [""])[0], (b.split() or [""])[0]
    if len(head_a) >= _MIN_TOKEN_LENGTH and head_a == head_b:
        # Ten sam „rzeczownik główny” („pierś z kurczaka”/„pierś z indyka”, „skyr …”):
        # odmiana tego samego produktu — kandydat do scalenia, decyduje człowiek.
        ratio = max(ratio, _SAME_HEAD_SCORE)
    return ratio


# --- budowa indeksu --------------------------------------------------------------------


def build_index(
    versions: Mapping[str, Spec],
    *,
    instance: Iterable[CatalogEntry] = (),
    demo: Iterable[tuple[str, str]] = (),
) -> CatalogIndex:
    """Zbuduj indeks z wersji (`etykieta → Spec`), wpisów instancji i nazw demo (nazwa, miara).

    Błędy zatrzymujące: ten sam produkt (po `normalize_name`) w dwóch źródłach
    z różnym `measure_kind`; ten sam produkt zdefiniowany w dwóch wersjach
    (kolejna wersja ma go REUŻYĆ, nie redefiniować); ten sam klucz dla dwóch
    różnych produktów.
    """
    entries: dict[str, CatalogEntry] = {}
    aliases: dict[str, CatalogEntry] = {}
    recipe_names: dict[str, str] = {}
    keys: dict[str, str] = {}

    def add(entry: CatalogEntry) -> None:
        existing = entries.get(entry.normalized)
        if existing is None:
            entries[entry.normalized] = entry
            return
        if existing.hard and entry.hard and existing.measure_kind != entry.measure_kind:
            raise CatalogConflictError(
                f"Konflikt definicji produktu „{entry.name}”: {existing.origin} ma miarę "
                f"{existing.measure_kind}, {entry.origin} — {entry.measure_kind}. "
                "Rozstrzygnij ręcznie (import reużywa produkt po nazwie)."
            )
        if existing.kind == "version" and entry.kind == "version":
            raise CatalogConflictError(
                f"Produkt „{entry.name}” jest zdefiniowany w dwóch wersjach "
                f"({existing.origin} i {entry.origin}) — późniejsza ma go REUŻYĆ (`reused`)."
            )
        # wersja wygrywa z instancją (pełna definicja), instancja z demo
        if entry.kind == "version" or (existing.kind == "demo" and entry.kind == "instance"):
            entries[entry.normalized] = entry

    for label in sorted(versions):
        spec = versions[label]
        for product in spec.products:
            previous_key = keys.get(product.key)
            if previous_key is not None and previous_key != normalize_name(product.name):
                raise CatalogConflictError(
                    f"Klucz „{product.key}” oznacza różne produkty w różnych wersjach "
                    f"({label} i wcześniejsza)."
                )
            keys[product.key] = normalize_name(product.name)
            entry = CatalogEntry(
                name=product.name,
                normalized=normalize_name(product.name),
                measure_kind=product.measure_kind,
                kind="version",
                origin=label,
                definition=product,
                aliases=tuple(merged.name for merged in product.merged_from),
            )
            add(entry)
            for merged in product.merged_from:
                aliases.setdefault(normalize_name(merged.name), entry)
        for recipe in spec.recipes:
            recipe_names.setdefault(normalize_name(recipe.name), label)

    for entry in instance:
        add(entry)
    for name, measure_kind in demo:
        add(
            CatalogEntry(
                name=name,
                normalized=normalize_name(name),
                measure_kind=measure_kind,
                kind="demo",
                origin="demo",
            )
        )
    return CatalogIndex(
        entries=entries, aliases=aliases, recipe_names=recipe_names, versions=dict(versions)
    )


def classify(index: CatalogIndex, name: str, measure_kind: str | None = None) -> Match:
    """Zestaw nazwę z katalogiem: trafienie dokładne / alias / podobne / nowy."""
    normalized = normalize_name(name)
    warnings: list[str] = []

    entry = index.entries.get(normalized)
    if entry is not None:
        if measure_kind is not None and entry.measure_kind != measure_kind:
            message = (
                f"„{name}” ma miarę {measure_kind}, a {entry.origin} definiuje ją jako "
                f"{entry.measure_kind}."
            )
            if entry.hard:
                raise CatalogConflictError(
                    "Konflikt definicji: " + message + " Import reużywa produkt po nazwie, "
                    "więc zapisane ilości nie dałyby się przeliczyć."
                )
            warnings.append(
                "Seed demo ma inną miarę: " + message + " NIE importuj paczki do bazy "
                "z seedem demo (produkt zostałby reużyty z demo)."
            )
        return Match(name=name, kind="exact", entry=entry, warnings=tuple(warnings))

    alias_entry = index.aliases.get(normalized)
    if alias_entry is not None:
        return Match(name=name, kind="alias", entry=alias_entry)

    scored = [
        Candidate(entry=candidate, score=score)
        for candidate in index.entries.values()
        if (score := similarity(name, candidate.name)) >= SIMILARITY_THRESHOLD
    ]
    scored.sort(key=lambda item: (-item.score, item.entry.normalized))
    if scored:
        return Match(name=name, kind="similar", candidates=tuple(scored))
    return Match(name=name, kind="new")


def similar_groups(names: Sequence[str]) -> list[tuple[str, ...]]:
    """Grupy podobnych nazw WEWNĄTRZ jednego zbioru (propozycje scaleń w obrębie PDF-a).

    Spójne składowe grafu „podobieństwo ≥ próg"; grupy jednoelementowe odpadają.
    Kolejność: wg pierwszego wystąpienia nazwy — wynik jest deterministyczny.
    """
    parent = list(range(len(names)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            if similarity(names[left], names[right]) >= SIMILARITY_THRESHOLD:
                parent[find(right)] = find(left)

    groups: dict[int, list[str]] = {}
    for position, name in enumerate(names):
        groups.setdefault(find(position), []).append(name)
    return [tuple(group) for group in groups.values() if len(group) > 1]


# --- wczytywanie (I/O) -----------------------------------------------------------------


def version_label(path: Path) -> str:
    """Etykieta wersji = nazwa katalogu `NNNN-slug`."""
    return path.parent.name


def load_versions(root: Path, *, exclude: str | None = None) -> dict[str, Spec]:
    """Wszystkie `root/*/spec.json` (poza `exclude` — wersją, którą właśnie analizujemy)."""
    versions: dict[str, Spec] = {}
    if not root.is_dir():
        return versions
    for path in sorted(root.glob(f"*/{SPEC_FILENAME}")):
        label = version_label(path)
        if label == exclude:
            continue
        spec = load_spec(path)
        if not label.startswith(f"{spec.version}-"):
            raise SpecError(
                f"Katalog „{label}” nie pasuje do wersji {spec.version} zapisanej w spec.json."
            )
        versions[label] = spec
    return versions


def demo_names() -> list[tuple[str, str]]:
    """Nazwy i miary produktów seedu demo — z tej samej tabeli, której używa seed."""
    from scripts.seed_demo import DEMO_PRODUCTS

    return [(demo.name, demo.measure_kind.value) for demo in DEMO_PRODUCTS]


def load_instance_export(path: Path) -> list[CatalogEntry]:
    """Produkty z eksportu instancji (`export.json` albo ZIP z nim) jako wpisy indeksu.

    Czytamy WYŁĄCZNIE sekcje katalogu: kategorie, produkty, przeliczniki. Reszta
    pliku (konta, plany) nas nie dotyczy i nie jest nigdzie kopiowana.
    """
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                raw = archive.read("export.json")
        else:
            raw = path.read_bytes()
        document: Any = json.loads(raw.decode("utf-8"), parse_float=Decimal)
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"Nie da się odczytać eksportu instancji {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise SpecError(f"{path}: to nie jest eksport w formacie transferu v1.")
    return entries_from_export(document.get("data") or {})


def entries_from_export(data: Mapping[str, Any]) -> list[CatalogEntry]:
    """Sekcje `data` eksportu → wpisy indeksu (czyste; osobno dla testów)."""
    categories = {row["id"]: row["name"] for row in data.get("product_categories") or []}
    weights: dict[Any, dict[str, Decimal]] = {}
    for row in data.get("product_unit_weights") or []:
        weights.setdefault(row["product_id"], {})[normalize_unit_label(row["unit_label"])] = (
            Decimal(str(row["grams_per_unit"]))
        )

    result: list[CatalogEntry] = []
    for row in data.get("canonical_products") or []:
        definition = _definition_from_row(row, categories, weights.get(row["id"], {}))
        result.append(
            CatalogEntry(
                name=row["name"],
                normalized=normalize_name(row["name"]),
                measure_kind=str(row["measure_kind"]),
                kind="instance",
                origin="instancja",
                definition=definition,
            )
        )
    return result


def _definition_from_row(
    row: Mapping[str, Any], categories: Mapping[Any, str], unit_weights: Mapping[str, Decimal]
) -> ProductSpec | None:
    """Wiersz produktu → `ProductSpec`, o ile ma komplet wartości (inaczej `None`)."""
    fields = ("kcal_100", "protein_100", "fat_100", "carbs_100", "fiber_100", "sugars_100")
    if any(row.get(name) is None for name in fields):
        return None
    category = categories.get(row.get("category_id"))
    if category is None:
        return None
    measure_kind = str(row["measure_kind"])
    try:
        return ProductSpec.model_validate(
            {
                "key": f"i{row['id']}",
                "name": row["name"],
                "category": category,
                "measure_kind": measure_kind,
                "piece_weight_g": row.get("piece_weight_g"),
                "per_100": Per100.model_validate(
                    {
                        "basis": "ml" if measure_kind == "volume" else "g",
                        "kcal": row["kcal_100"],
                        "protein": row["protein_100"],
                        "fat": row["fat_100"],
                        "carbs": row["carbs_100"],
                        "fiber": row["fiber_100"],
                        "sugars": row["sugars_100"],
                    }
                ),
                "glycemic_index": row.get("glycemic_index"),
                "unit_weights": dict(unit_weights),
                "nutrition_source": str(row.get("nutrition_source") or "eksport instancji"),
            }
        )
    except ValueError:
        return None


# --- rozwiązanie katalogu dla jednej wersji ---------------------------------------------


@dataclass(frozen=True)
class ResolvedCatalog:
    """Produkty dostępne dla jednej wersji: klucz lokalny → definicja + skąd pochodzi."""

    products: Mapping[str, ProductSpec]
    origins: Mapping[str, str]
    #: ostrzeżenia z zestawienia (np. konflikt miary z seedem demo)
    warnings: tuple[str, ...] = ()
    #: dla każdego NOWEGO produktu wersji — wynik zestawienia (do raportu/propozycji)
    matches: tuple[Match, ...] = ()


def resolve_catalog(spec: Spec, index: CatalogIndex) -> ResolvedCatalog:
    """Złóż katalog wersji: własne produkty + reużyte z indeksu.

    Własny produkt NIE MOŻE redefiniować istniejącego (trafienie dokładne albo alias
    to błąd — ma iść przez `reused`); konflikt miary wobec wersji/instancji to
    `CatalogConflictError`. Reużyty produkt musi mieć pełną definicję, bo paczka
    musi być samowystarczalna (na bazie bez tego produktu zostałby założony z niej).
    """
    products: dict[str, ProductSpec] = {}
    origins: dict[str, str] = {}
    warnings: list[str] = []
    matches: list[Match] = []

    for product in spec.products:
        match = classify(index, product.name, product.measure_kind)
        matches.append(match)
        warnings.extend(match.warnings)
        if match.kind in ("exact", "alias") and match.entry is not None and match.entry.hard:
            raise SpecError(
                f"Produkt „{product.name}” już istnieje ({match.entry.origin}) — "
                "zadeklaruj go w `reused` zamiast definiować ponownie."
            )
        products[product.key] = product
        origins[product.key] = spec.version

    for item in spec.reused:
        match = classify(index, item.name)
        entry = match.entry
        if entry is None or match.kind not in ("exact", "alias"):
            raise SpecError(
                f"`reused`: produktu „{item.name}” nie ma w katalogu (wersje, eksport instancji)."
            )
        if entry.definition is None:
            raise SpecError(
                f"`reused`: „{item.name}” ({entry.origin}) nie ma pełnej definicji — "
                "paczka musi być samowystarczalna. Zdefiniuj produkt w `products` "
                "albo uzupełnij wartości w instancji."
            )
        products[item.key] = entry.definition.model_copy(update={"key": item.key})
        origins[item.key] = entry.origin
    return ResolvedCatalog(
        products=products, origins=origins, warnings=tuple(warnings), matches=tuple(matches)
    )
