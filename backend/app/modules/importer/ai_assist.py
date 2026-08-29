"""AI-asysta review importu — WYŁĄCZNIE propozycje (ADR-011, decyzja D5).

Trzy zdania, które rządzą tym modułem:

1. **AI niczego nie zapisuje do danych aplikacji.** Wynik ląduje w polach
   `suggested_product_id` / `match_kind=ai` / `confidence` stagingu oraz
   w `details` issues. Do `recipes` i `canonical_products` prowadzi jedna
   droga: zatwierdzenie przez człowieka (02_DOMAIN §13.6).
2. **Brak klucza = pełnosprawny tryb deterministyczny.** `ANTHROPIC_API_KEY`
   może być pusty; wtedy `available` jest `False`, endpoint `ai-suggest`
   odpowiada 503 z komunikatem po polsku, a cała reszta importu działa bez
   zmian. AI jest ulepszeniem, nie zależnością.
3. **Odpowiedź niezgodna ze schematem to odrzucona propozycja, nie 500.**
   Model może zwrócić id produktu, którego nie ma, albo `confidence` spoza
   [0, 1] — takie pozycje wypadają po cichu w `parse_*`, bo alternatywą byłby
   błąd serwera w miejscu, gdzie nie stało się nic groźnego.

Co WOLNO wysłać do Claude API (D5, 07_SECURITY): treść wyciągniętą z PDF-a
(surowe nazwy składników, nazwy dań) i nazwy produktów z GLOBALNEGO katalogu.
Nigdy: e-maili, nazw rodzin, identyfikatorów użytkowników, treści planów.
Zapytania budują wyłącznie funkcje z tego pliku i to jest miejsce, w którym
review bezpieczeństwa sprawdza tę granicę.

Podział na czyste funkcje (budowa promptu, walidacja odpowiedzi) i cienką
warstwę I/O (`AiAssistant`) jest celowy: testy mockują klienta i nie robią ANI
JEDNEGO realnego wywołania (karta B16 §Tests).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = [
    "AI_UNAVAILABLE",
    "CANDIDATES_PER_NAME",
    "AiAssistant",
    "AiSuggestions",
    "CatalogCandidate",
    "DuplicateSuggestion",
    "MappingSuggestion",
    "RecipeToMatch",
    "ServingsSuggestion",
    "UnmappedName",
    "build_duplicate_prompt",
    "build_mapping_prompt",
    "parse_duplicates",
    "parse_mappings",
    "parse_servings",
]

logger = logging.getLogger(__name__)

AI_UNAVAILABLE = (
    "Asysta AI jest wyłączona — instancja nie ma skonfigurowanego klucza API. "
    "Mapowania i porcje ustawisz ręcznie; reszta importu działa normalnie."
)
AI_CALL_FAILED = (
    "Nie udało się pobrać propozycji od AI. Spróbuj ponownie za chwilę albo "
    "ustaw mapowania ręcznie — import działa bez asysty."
)

#: Sufit liczby pozycji w jednym zapytaniu. Nie chodzi o cenę, tylko o jakość:
#: prompt z setką nazw i tysiącem kandydatów przestaje być zadaniem, a zaczyna
#: być stogiem siana. Reszta idzie w kolejnych partiach.
MAPPING_BATCH_SIZE = 40
#: Ilu kandydatów katalogu pokazujemy dla JEDNEJ surowej nazwy.
CANDIDATES_PER_NAME = 12
#: Poniżej tego progu propozycja nie trafia do stagingu — „może to to"
#: kosztuje człowieka więcej czasu niż wybranie produktu z pickera.
MIN_CONFIDENCE = Decimal("0.5")

SYSTEM_PROMPT = (
    "Jesteś asystentem importu jadłospisów do aplikacji kuchennej. "
    "Twoje odpowiedzi są WYŁĄCZNIE propozycjami — zatwierdza je człowiek. "
    "Nigdy nie zgaduj na siłę: jeśli nie masz pewności, pomiń pozycję. "
    "Odpowiadaj wyłącznie danymi w podanym formacie."
)

#: Pary z 01_PDF_AUDIT §5.3 — few-shot pokazujący, że część nazw to ODRĘBNE
#: produkty, a nie warianty zapisu tego samego. To jest właśnie ta wiedza,
#: której deterministyczne dopasowanie EXACT nie ma.
FEW_SHOT = (
    "Przykłady rozstrzygnięć z tego materiału:\n"
    "- „Skyr naturalny” i „Skyr naturalny pitny” to DWA różne produkty.\n"
    "- „Maliny” i „Maliny mrożone” to DWA różne produkty.\n"
    "- „Ser parmezan” i „Ser parmezan tarty” to zwykle TEN SAM produkt.\n"
    "- „Serek kanapkowy ” (ze spacją na końcu) to ten sam produkt "
    "co „Serek kanapkowy”.\n"
    "- „Masło”, „Masło klarowane” i „Masło orzechowe” to TRZY różne produkty."
)


@dataclass(frozen=True)
class UnmappedName:
    """Surowa nazwa z PDF-a, dla której nie ma dopasowania dokładnego."""

    raw_name: str
    #: Id produktów katalogu, które mogą być tym produktem (kandydaci z bazy).
    candidates: tuple[CatalogCandidate, ...]


@dataclass(frozen=True)
class CatalogCandidate:
    """Produkt katalogu pokazywany modelowi jako możliwe dopasowanie."""

    product_id: int
    name: str


@dataclass(frozen=True)
class RecipeToMatch:
    """Danie ze stagingu, dla którego szukamy duplikatu."""

    staged_recipe_id: int
    name: str


@dataclass(frozen=True)
class MappingSuggestion:
    """Propozycja mapowania surowej nazwy na produkt kanoniczny."""

    raw_name: str
    product_id: int
    confidence: Decimal


@dataclass(frozen=True)
class DuplicateSuggestion:
    """Propozycja scalenia dania ze stagingu z istniejącym przepisem."""

    staged_recipe_id: int
    recipe_id: int
    recipe_name: str
    confidence: Decimal


@dataclass(frozen=True)
class ServingsSuggestion:
    """Podpowiedź liczby porcji wyczytana z treści instrukcji.

    Trafia WYŁĄCZNIE do `details` issue `multi_portion_suspect` — nigdy do
    `resolved_servings`. „Około 21 sztuk" to zdanie o kotletach, a nie decyzja
    o mianowniku przepisu; tę podejmuje człowiek (ADR-011).
    """

    staged_recipe_id: int
    servings: int
    rationale: str


@dataclass(frozen=True)
class AiSuggestions:
    """Komplet propozycji jednego uruchomienia asysty."""

    mappings: tuple[MappingSuggestion, ...] = ()
    duplicates: tuple[DuplicateSuggestion, ...] = ()
    servings: tuple[ServingsSuggestion, ...] = ()


# --- schematy odpowiedzi (walidacja Pydantic) ------------------------------------


class _MappingItem(BaseModel):
    """Jedna propozycja mapowania w odpowiedzi modelu."""

    model_config = ConfigDict(extra="forbid")

    raw_name: str
    product_id: int
    confidence: float = Field(ge=0, le=1)


class _MappingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[_MappingItem] = Field(default_factory=list)


class _DuplicateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staged_recipe_id: int
    recipe_id: int
    confidence: float = Field(ge=0, le=1)


class _ServingsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staged_recipe_id: int
    servings: int = Field(ge=1, le=100)
    rationale: str = ""


class _DuplicateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duplicates: list[_DuplicateItem] = Field(default_factory=list)
    servings: list[_ServingsItem] = Field(default_factory=list)


MAPPING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_name": {"type": "string"},
                    "product_id": {"type": "integer"},
                    "confidence": {"type": "number"},
                },
                "required": ["raw_name", "product_id", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mappings"],
    "additionalProperties": False,
}

DUPLICATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "duplicates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "staged_recipe_id": {"type": "integer"},
                    "recipe_id": {"type": "integer"},
                    "confidence": {"type": "number"},
                },
                "required": ["staged_recipe_id", "recipe_id", "confidence"],
                "additionalProperties": False,
            },
        },
        "servings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "staged_recipe_id": {"type": "integer"},
                    "servings": {"type": "integer"},
                    "rationale": {"type": "string"},
                },
                "required": ["staged_recipe_id", "servings", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["duplicates", "servings"],
    "additionalProperties": False,
}


# --- budowa promptów (czyste funkcje) --------------------------------------------


def build_mapping_prompt(names: Sequence[UnmappedName]) -> str:
    """Prompt zadania „dopasuj surowe nazwy do produktów katalogu".

    Do modelu idą WYŁĄCZNIE surowe nazwy z PDF-a i nazwy produktów globalnego
    katalogu — granica z D5 jest tu, w jednej funkcji, żeby dało się ją
    sprawdzić wzrokiem podczas `/security-review`.
    """
    lines = [
        "Poniżej surowe nazwy składników z jadłospisu i kandydaci z katalogu produktów aplikacji.",
        "Dla każdej nazwy wskaż JEDEN produkt, jeśli jesteś pewien, że to ten sam "
        "produkt spożywczy. Nazwę bez dobrego kandydata POMIŃ.",
        "",
        FEW_SHOT,
        "",
        "Nazwy do dopasowania:",
    ]
    for entry in names:
        lines.append(f"- „{entry.raw_name}”")
        for candidate in entry.candidates:
            lines.append(f"    * id={candidate.product_id}: „{candidate.name}”")
        if not entry.candidates:
            lines.append("    * (brak kandydatów — pomiń tę nazwę)")
    return "\n".join(lines)


def build_duplicate_prompt(
    staged: Sequence[RecipeToMatch],
    existing: Sequence[CatalogCandidate],
    instructions: dict[int, str],
) -> str:
    """Prompt zadania „znajdź duplikaty dań i podpowiedz liczbę porcji"."""
    lines = [
        "Poniżej nazwy dań z importowanego jadłospisu oraz przepisy, które już są w aplikacji.",
        "Zadanie 1: wskaż pary (danie z importu, istniejący przepis), które są "
        "TYM SAMYM daniem. Pary niepewne pomiń.",
        "Zadanie 2: jeśli treść przygotowania mówi, na ile porcji jest danie "
        "(np. „około 21 sztuk”, „wyjdzie 6 kotletów”), podaj tę liczbę jako "
        "PODPOWIEDŹ. Nie zgaduj z samej masy składników.",
        "",
        "Dania z importu:",
    ]
    for item in staged:
        lines.append(f"- id={item.staged_recipe_id}: „{item.name}”")
        text = instructions.get(item.staged_recipe_id, "").strip()
        if text:
            lines.append(f"    przygotowanie: {text[:600]}")
    lines.append("")
    lines.append("Przepisy już w aplikacji:")
    if existing:
        lines.extend(f"- id={row.product_id}: „{row.name}”" for row in existing)
    else:
        lines.append("- (brak — zadanie 1 nie ma czego szukać)")
    return "\n".join(lines)


# --- walidacja odpowiedzi (czyste funkcje) ---------------------------------------


def _loads(raw: str) -> dict[str, Any] | None:
    """JSON z odpowiedzi modelu; śmieci = `None`, nigdy wyjątek na zewnątrz."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("ai_assist: odpowiedź nie jest poprawnym JSON-em")
        return None
    return data if isinstance(data, dict) else None


def parse_mappings(
    raw: str, *, allowed_names: set[str], allowed_product_ids: set[int]
) -> tuple[MappingSuggestion, ...]:
    """Odpowiedź modelu → propozycje mapowań, z odsianiem wszystkiego podejrzanego.

    Odsiewamy trzy rzeczy i każda z nich zdarza się modelom naprawdę: nazwę,
    o którą nie pytaliśmy; produkt, którego nie było wśród kandydatów (albo nie
    istnieje); pewność poniżej progu. Zignorowana propozycja kosztuje jedno
    kliknięcie w pickerze — zaakceptowana bzdura kosztuje błędny przepis.
    """
    data = _loads(raw)
    if data is None:
        return ()
    try:
        parsed = _MappingResponse.model_validate(data)
    except ValidationError:
        logger.warning("ai_assist: odpowiedź nie pasuje do schematu mapowań")
        return ()

    suggestions: list[MappingSuggestion] = []
    seen: set[str] = set()
    for item in parsed.mappings:
        if item.raw_name not in allowed_names or item.product_id not in allowed_product_ids:
            continue
        confidence = _confidence(item.confidence)
        if confidence < MIN_CONFIDENCE or item.raw_name in seen:
            continue
        seen.add(item.raw_name)
        suggestions.append(
            MappingSuggestion(
                raw_name=item.raw_name, product_id=item.product_id, confidence=confidence
            )
        )
    return tuple(suggestions)


def parse_duplicates(
    raw: str, *, allowed_staged_ids: set[int], allowed_recipes: dict[int, str]
) -> tuple[tuple[DuplicateSuggestion, ...], tuple[ServingsSuggestion, ...]]:
    """Odpowiedź modelu → propozycje scaleń i podpowiedzi porcji."""
    data = _loads(raw)
    if data is None:
        return (), ()
    try:
        parsed = _DuplicateResponse.model_validate(data)
    except ValidationError:
        logger.warning("ai_assist: odpowiedź nie pasuje do schematu duplikatów")
        return (), ()

    duplicates = tuple(
        DuplicateSuggestion(
            staged_recipe_id=item.staged_recipe_id,
            recipe_id=item.recipe_id,
            recipe_name=allowed_recipes[item.recipe_id],
            confidence=_confidence(item.confidence),
        )
        for item in parsed.duplicates
        if item.staged_recipe_id in allowed_staged_ids
        and item.recipe_id in allowed_recipes
        and _confidence(item.confidence) >= MIN_CONFIDENCE
    )
    servings = tuple(
        ServingsSuggestion(
            staged_recipe_id=item.staged_recipe_id,
            servings=item.servings,
            rationale=item.rationale.strip()[:300],
        )
        for item in parsed.servings
        if item.staged_recipe_id in allowed_staged_ids
    )
    return duplicates, servings


def parse_servings(raw: str, *, allowed_staged_ids: set[int]) -> tuple[ServingsSuggestion, ...]:
    """Sama część „porcje" tej samej odpowiedzi — wygodne wejście dla testów."""
    return parse_duplicates(raw, allowed_staged_ids=allowed_staged_ids, allowed_recipes={})[1]


def _confidence(value: float) -> Decimal:
    """`float` z JSON-a → `Decimal` w skali kolumny `confidence` NUMERIC(3,2).

    `Decimal(str(value))`, nie `Decimal(value)`: konstruktor z float wciąga
    binarne przybliżenie (0.85 → 0.8500000000000000888…) i kwantyzacja
    zaczynałaby od nieprawdy.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"))


class AiAssistant:
    """Cienka warstwa I/O nad Claude API. Bez klucza nie tworzy klienta w ogóle."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout_s: float,
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s

    @property
    def available(self) -> bool:
        """Czy asysta jest w ogóle skonfigurowana (ADR-011: brak klucza = tryb offline)."""
        return bool(self._api_key)

    async def suggest_mappings(
        self, names: Sequence[UnmappedName]
    ) -> tuple[MappingSuggestion, ...]:
        """Fuzzy mapowanie surowych nazw na produkty katalogu — same propozycje."""
        if not names or not self.available:
            return ()

        allowed_names = {entry.raw_name for entry in names}
        allowed_ids = {candidate.product_id for entry in names for candidate in entry.candidates}
        suggestions: list[MappingSuggestion] = []
        for start in range(0, len(names), MAPPING_BATCH_SIZE):
            chunk = names[start : start + MAPPING_BATCH_SIZE]
            raw = await self._ask(build_mapping_prompt(chunk), MAPPING_SCHEMA)
            if raw is None:
                continue
            suggestions.extend(
                parse_mappings(
                    raw,
                    allowed_names=allowed_names,
                    allowed_product_ids=allowed_ids,
                )
            )
        return tuple(suggestions)

    async def suggest_duplicates_and_servings(
        self,
        staged: Sequence[RecipeToMatch],
        existing: Sequence[CatalogCandidate],
        instructions: dict[int, str],
    ) -> tuple[tuple[DuplicateSuggestion, ...], tuple[ServingsSuggestion, ...]]:
        """Duplikaty przepisów + podpowiedzi liczby porcji w jednym zapytaniu."""
        if not staged or not self.available:
            return (), ()
        raw = await self._ask(
            build_duplicate_prompt(staged, existing, instructions), DUPLICATE_SCHEMA
        )
        if raw is None:
            return (), ()
        return parse_duplicates(
            raw,
            allowed_staged_ids={item.staged_recipe_id for item in staged},
            allowed_recipes={row.product_id: row.name for row in existing},
        )

    async def _ask(self, prompt: str, schema: dict[str, Any]) -> str | None:
        """Jedno wywołanie API z wymuszonym kształtem odpowiedzi; błąd = `None`.

        Import SDK jest LOKALNY: instancja bez klucza nigdy tu nie wchodzi
        i nie ma powodu płacić za import przy starcie aplikacji.

        Świadomie NIE ustawiamy `temperature` — parametry losowości zostały
        usunięte z API bieżących modeli i ich podanie kończy się błędem 400.
        Determinizm bierze się stąd, skąd powinien: z wymuszonego schematu
        odpowiedzi i z tego, że każdą propozycję i tak zatwierdza człowiek.
        """
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._timeout_s)
        try:
            message = await client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except Exception:
            # Nie logujemy treści promptu ani odpowiedzi (07_SECURITY §8) — ani
            # tym bardziej wyjątku, który potrafi nieść nagłówki żądania.
            logger.warning("ai_assist: wywołanie Claude API nie powiodło się")
            return None
        finally:
            await client.close()

        for block in message.content:
            # Odpowiedź może zawierać także bloki myślenia albo użycia narzędzi —
            # wymuszony schemat gwarantuje, że TREŚĆ stoi w pierwszym bloku
            # tekstowym, ale nie że jest on jedynym blokiem.
            text = getattr(block, "text", None)
            if getattr(block, "type", None) == "text" and isinstance(text, str):
                return text
        return None
