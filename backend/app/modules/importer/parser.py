"""Deterministyczny parser PDF-ów dietetyczki — CZYSTE funkcje, zero I/O.

Wejście: lista tekstów stron (`pdfplumber.Page.extract_text()`). Wyjście:
dataclassy. Dzięki temu cały parser testuje się na wyciętych fragmentach tekstu
(`tests/unit/test_pdf_parser.py`), a plik z dysku dotyka wyłącznie `service.py`.

Kontrakt struktury jest WIĄŻĄCY i pochodzi z pomiaru na realnym korpusie:
`docs/implementation-plan/01_PDF_AUDIT.md` (8 plików, 24 dni, 96 posiłków,
642 wiersze składników, 178 nazw produktów). Ten moduł nie „ulepsza" regexów
na zapas: linia, która nie pasuje do kontraktu, zostaje ZGŁOSZONA
(`parse_warning`), a nie po cichu dopasowana innym wzorcem.

Trzy pułapki ekstrakcji, które kształtują ten kod (§3.2, §5.4, §2.5):

1. **pdfplumber skleja kolumny.** Instrukcja przygotowania z prawej kolumny
   ląduje w tej samej linii, co składnik z lewej — czasem BEZ spacji po nawiasie
   (`(45 g)mozzarellą`). Regex składnika kotwiczy od początku linii i wszystko
   po nawiasie traktuje jako urwek instrukcji.
2. **Strona listy zakupów bywa kontynuowana bez nagłówka.** Klasyfikacja jest
   więc STANOWA: po „Lista zakupów" wszystkie kolejne strony należą do listy
   zakupów, aż do „Wymienniki".
3. **Nazwa dania też potrafi się zawinąć** między kolumnami. Bierzemy część
   linii przed znacznikiem „Przepis"; reszta idzie do instrukcji. Doprecyzowanie
   nazwy należy do review (B16) — perfekcyjny skład nie jest celem parsera.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

__all__ = [
    "DAY_TOTAL_RE",
    "DISH_TITLE_RE",
    "INGREDIENT_RE",
    "MEAL_HEADER_RE",
    "MEAL_ORDER",
    "MULTI_PORTION_THRESHOLD_G",
    "DayChecksum",
    "Finding",
    "PageKind",
    "ParsedDay",
    "ParsedDish",
    "ParsedDocument",
    "ParsedIngredient",
    "ParsedMeal",
    "build_parse_report",
    "classify_pages",
    "parse_decimal",
    "parse_document",
]

#: Liczba w dokumencie: separator dziesiętny to PRZECINEK (§3.2), ale nagłówki
#: posiłków używają kropki (`W: 31.3`) — akceptujemy oba i normalizujemy.
_NUM = r"\d+(?:[.,]\d+)?"

#: Nagłówek posiłku (§3.1): `ŚNIADANIE Kcal: 468 W: 31.3 B: 17.9 T: 30.4 Bł: 9.0 ŁG: 4.3`.
MEAL_HEADER_RE = re.compile(
    rf"^(?P<meal>ŚNIADANIE|OBIAD|PODWIECZOREK|KOLACJA)\s+"
    rf"Kcal:\s*(?P<kcal>{_NUM})\s+W:\s*(?P<carbs>{_NUM})\s+B:\s*(?P<protein>{_NUM})\s+"
    rf"T:\s*(?P<fat>{_NUM})\s+Bł:\s*(?P<fiber>{_NUM})\s+ŁG:\s*(?P<glycemic>{_NUM})"
)

#: Wiersz składnika (§3.2): `Cebula, 0,3 x Sztuka (31,5 g)` + tolerancja
#: doklejonego tekstu instrukcji po nawiasie (także bez spacji).
INGREDIENT_RE = re.compile(
    rf"^(?P<name>.+?),\s*(?P<qty>{_NUM})\s*x\s*(?P<unit>\S+?)\s*"
    rf"\((?P<grams>{_NUM})\s*g\)(?P<rest>.*)$"
)

#: Suma kontrolna dnia (§4): `SUMA DNIA Kcal: 2021 W: 179.3g …`.
DAY_TOTAL_RE = re.compile(rf"^SUMA DNIA\s+Kcal:\s*(?P<kcal>{_NUM})")

#: Tytuł dania: nazwa + znacznik prawej kolumny „Przepis" (opcjonalnie
#: „Przepis na N porcji/porcje/porcję" — dokument odmienia liczebnik).
DISH_TITLE_RE = re.compile(r"^(?P<name>.*?)\s*Przepis(?:\s+na\s+(?P<servings>\d+)\s+porcj\w*)?\s*$")

#: Potwierdzenie porcji (§3.3): `Zjedz 1 z 7 porcji`.
_EAT_ONE_OF_RE = re.compile(r"^Zjedz\s+1\s+z\s+(?P<servings>\d+)\s+porcj\w*\s*$")
#: Inne warianty tej sekcji (w korpusie: `Zjedz 2 porcję`) — rozpoznajemy je,
#: żeby nie wpadły do bufora instrukcji, ale niczego z nich nie wnioskujemy.
_EAT_OTHER_RE = re.compile(r"^Zjedz\s+.*porcj\w*\s*$")

#: Stopka strony (`3/10`) — nigdy treść.
_FOOTER_RE = re.compile(r"^\d+\s*/\s*\d+$")

#: Linia WYGLĄDAJĄCA na składnik, która nie pasuje do kontraktu §3.2. Służy
#: WYŁĄCZNIE do zgłaszania `parse_warning` — nie do parsowania (patrz errata
#: 01_PDF_AUDIT §9: 7 takich wierszy w korpusie, decyzja D20).
_INGREDIENT_SHAPED_RE = re.compile(
    rf"^(?P<name>.+?),\s*(?:{_NUM}\s*x\s*\S*\s*|)\(?\s*(?P<grams>{_NUM})\s*g\)?\s*$"
)
#: Urwana pierwsza połowa zawiniętego wiersza składnika (`…, 2 x` / `Kostka (16 g)`).
_INGREDIENT_WRAPPED_HEAD_RE = re.compile(rf"^(?P<name>.+?),\s*{_NUM}\s*x\s*$")

#: Nagłówki stron, po których klasyfikacja przechodzi w tryb „pomijamy resztę".
_SHOPPING_LIST_HEADING = "Lista zakupów"
_EXCHANGES_HEADING = "Wymienniki"
_SUMMARY_HEADING = "Podsumowanie jadłospisu"

#: Etykiety dni tygodnia stojące samodzielnie w linii (§2.3).
_DAY_LABELS = (
    "Poniedziałek",
    "Wtorek",
    "Środa",
    "Czwartek",
    "Piątek",
    "Sobota",
    "Niedziela",
)

#: Stała kolejność posiłków w dniu (§2.3) — do walidacji, nie do sortowania:
#: dokument sam ją trzyma, a odstępstwo jest sygnałem błędu ekstrakcji.
MEAL_ORDER = ("ŚNIADANIE", "OBIAD", "PODWIECZOREK", "KOLACJA")

#: Sekcje tekstowe posiłku (§3.3).
_SECTION_RECIPE_MARKER = "Przepis"
_SECTION_COMMENT = "Komentarz"
_SECTION_PRODUCTS = "Produkty"

#: Próg masy, powyżej którego danie bez jawnej liczby porcji jest podejrzane
#: o wieloporcyjność (§5.1 — „proponowane 800 g"). Masa liczy się PER POSIŁEK,
#: bo `pdf_kcal` też jest per posiłek — uzasadnienie i pomiar: errata §9.
MULTI_PORTION_THRESHOLD_G = Decimal("800")

#: Dopuszczalny rozjazd sumy kcal posiłków wobec `SUMA DNIA` (§4).
DAY_CHECKSUM_TOLERANCE_KCAL = Decimal("2")


class PageKind(StrEnum):
    """Rodzaj strony (§2). `SHOPPING_LIST` i `EXCHANGES` są POMIJANE."""

    TITLE = "title"
    SUMMARY = "summary"
    #: List przewodni dietetyczki zamiast podsumowania — `dieta (2).pdf` (§6).
    LETTER = "letter"
    DAY = "day"
    SHOPPING_LIST = "shopping_list"
    EXCHANGES = "exchanges"


class FindingKind(StrEnum):
    """Rodzaj ustalenia parsera; odwzorowuje `ImportIssueKind` bez zależności od ORM."""

    MULTI_PORTION_SUSPECT = "multi_portion_suspect"
    PARSE_WARNING = "parse_warning"


class FindingSeverity(StrEnum):
    """Waga ustalenia; odwzorowuje `ImportIssueSeverity`."""

    BLOCKER = "blocker"
    WARNING = "warning"


def parse_decimal(raw: str) -> Decimal:
    """`"31,5"` → `Decimal("31.5")`. Nigdy `float` (ADR-008)."""
    return Decimal(raw.replace(",", ".").strip())


@dataclass(frozen=True)
class ParsedIngredient:
    """Jeden wiersz składnika. `grams` to jedyne źródło ilości (§8.3)."""

    raw_name: str
    raw_qty: Decimal
    raw_unit: str
    grams: Decimal


@dataclass
class ParsedDish:
    """Jedno danie posiłku — przyszły `staged_recipe`."""

    name: str
    declared_servings: int | None = None
    instructions: str = ""
    comment: str = ""
    ingredients: list[ParsedIngredient] = field(default_factory=list)

    @property
    def grams_total(self) -> Decimal:
        """Suma gramatur składników dania (razem z sekcją `Produkty`)."""
        return sum((item.grams for item in self.ingredients), Decimal(0))


@dataclass
class ParsedMeal:
    """Posiłek: nagłówek z makro + co najmniej jedno danie (§2.3)."""

    label: str
    pdf_kcal: Decimal
    pdf_macros: dict[str, str]
    dishes: list[ParsedDish] = field(default_factory=list)

    @property
    def grams_total(self) -> Decimal:
        """Masa CAŁEGO posiłku — na niej liczy się próg wieloporcyjności."""
        return sum((dish.grams_total for dish in self.dishes), Decimal(0))

    @property
    def has_declared_servings(self) -> bool:
        """Czy którekolwiek danie posiłku niesie jawne „Przepis na N porcji"."""
        return any(dish.declared_servings is not None for dish in self.dishes)


@dataclass
class ParsedDay:
    """Dzień dokumentu: cztery posiłki i suma kontrolna."""

    label: str
    meals: list[ParsedMeal] = field(default_factory=list)
    declared_kcal: Decimal | None = None

    @property
    def computed_kcal(self) -> Decimal:
        """Suma `pdf_kcal` posiłków — druga strona sumy kontrolnej (§4)."""
        return sum((meal.pdf_kcal for meal in self.meals), Decimal(0))


@dataclass(frozen=True)
class DayChecksum:
    """Wynik sumy kontrolnej jednego dnia — wchodzi wprost do `parse_report`."""

    day: str
    expected: Decimal | None
    computed: Decimal
    ok: bool


@dataclass(frozen=True)
class Finding:
    """Ustalenie parsera → wiersz `import_issues` (mapuje `service.py`).

    `day_label`/`meal_label`/`dish_index` adresują miejsce w dokumencie; serwis
    zamienia je na `staged_recipe_id` już po zapisie stagingu, bo parser nie ma
    prawa znać identyfikatorów z bazy.
    """

    kind: FindingKind
    severity: FindingSeverity
    details: dict[str, Any]
    day_label: str | None = None
    meal_label: str | None = None
    dish_index: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    """Wynik parsowania całego pliku."""

    pages: tuple[PageKind, ...]
    days: tuple[ParsedDay, ...]
    findings: tuple[Finding, ...]
    checksums: tuple[DayChecksum, ...]

    @property
    def meals(self) -> list[ParsedMeal]:
        """Posiłki wszystkich dni, w kolejności dokumentu."""
        return [meal for day in self.days for meal in day.meals]

    @property
    def dishes(self) -> list[ParsedDish]:
        """Dania wszystkich posiłków, w kolejności dokumentu."""
        return [dish for meal in self.meals for dish in meal.dishes]


def _lines(text: str) -> list[str]:
    """Linie strony bez pustych — zachowuje ORYGINALNE wcięcia (regexy kotwiczą)."""
    return [line for line in text.splitlines() if line.strip()]


def _looks_like_day_page(lines: Sequence[str]) -> bool:
    """Czy na stronie stoi cokolwiek z treści dnia (nagłówek, dzień, składnik).

    Świadomie szeroki warunek: strona z samą kontynuacją listy składników
    (bez nagłówka posiłku i bez nazwy dnia) też jest stroną dnia, a pominięcie
    jej oznaczałoby cichą utratę składników.
    """
    for line in lines:
        stripped = line.strip()
        if stripped in _DAY_LABELS:
            return True
        if MEAL_HEADER_RE.match(stripped) or DAY_TOTAL_RE.match(stripped):
            return True
        if INGREDIENT_RE.match(line):
            return True
        if stripped.endswith(_SECTION_RECIPE_MARKER) and DISH_TITLE_RE.match(stripped):
            return True
    return False


def classify_pages(pages: Sequence[str]) -> tuple[PageKind, ...]:
    """Rodzaj każdej strony dokumentu (§2), z zachowaniem kolejności.

    Klasyfikacja jest STANOWA z jednego powodu zmierzonego na korpusie: lista
    zakupów potrafi zająć dwie strony, a nagłówek „Lista zakupów" stoi tylko na
    pierwszej z nich (`dieta.pdf` s. 8—9). Bez pamięci trybu druga strona
    wyglądałaby na stronę dnia i zasypała raport ostrzeżeniami.
    """
    kinds: list[PageKind] = []
    tail_mode: PageKind | None = None

    for index, text in enumerate(pages):
        lines = _lines(text)
        stripped = [line.strip() for line in lines]

        if _EXCHANGES_HEADING in stripped:
            tail_mode = PageKind.EXCHANGES
        elif _SHOPPING_LIST_HEADING in stripped:
            tail_mode = PageKind.SHOPPING_LIST

        if tail_mode is not None:
            kinds.append(tail_mode)
            continue
        if any(line.startswith(_SUMMARY_HEADING) for line in stripped):
            kinds.append(PageKind.SUMMARY)
            continue
        if _looks_like_day_page(lines):
            kinds.append(PageKind.DAY)
            continue
        kinds.append(PageKind.TITLE if index == 0 else PageKind.LETTER)

    return tuple(kinds)


class _DocumentBuilder:
    """Maszyna stanów stron dni (§2.3): dzień → posiłek → danie → składniki.

    Stanu nie trzymamy w enumie, tylko w „aktualnym dniu / posiłku / daniu":
    dokument nie ma znaczników zamknięcia sekcji, więc każdy rozpoznany nagłówek
    po prostu zamyka poprzedni kontekst. Bufory tekstu (`instructions`,
    `comment`) zbierają wszystko, czego nie rozpoznaliśmy jako strukturę —
    to świadomie „wystarczy do review", a nie idealna rekonstrukcja kolumn.
    """

    def __init__(self) -> None:
        self.days: list[ParsedDay] = []
        self.findings: list[Finding] = []
        self._day: ParsedDay | None = None
        self._meal: ParsedMeal | None = None
        self._dish: ParsedDish | None = None
        self._buffer: list[str] = []
        self._in_comment = False

    # --- pomocnicze -----------------------------------------------------------

    def _flush_buffer(self) -> None:
        """Zbierz urwki tekstu do właściwego pola bieżącego dania."""
        if not self._buffer or self._dish is None:
            self._buffer.clear()
            return
        text = " ".join(part.strip() for part in self._buffer if part.strip())
        self._buffer.clear()
        if not text:
            return
        if self._in_comment:
            self._dish.comment = f"{self._dish.comment} {text}".strip()
        else:
            self._dish.instructions = f"{self._dish.instructions} {text}".strip()

    def _warn(self, message: str, line: str) -> None:
        """Zgłoś `parse_warning` z SUROWĄ linią — review musi zobaczyć oryginał."""
        self.findings.append(
            Finding(
                kind=FindingKind.PARSE_WARNING,
                severity=FindingSeverity.WARNING,
                details={"powód": message, "linia": line.strip()},
                day_label=self._day.label if self._day else None,
                meal_label=self._meal.label if self._meal else None,
                dish_index=self._dish_index(),
            )
        )

    def _dish_index(self) -> int | None:
        """Pozycja bieżącego dania W CAŁYM dokumencie (adres dla `service.py`)."""
        if self._dish is None:
            return None
        index = 0
        for day in self.days:
            for meal in day.meals:
                for dish in meal.dishes:
                    if dish is self._dish:
                        return index
                    index += 1
        return None

    # --- przejścia ------------------------------------------------------------

    def _start_day(self, label: str) -> None:
        self._flush_buffer()
        self._day = ParsedDay(label=label)
        self.days.append(self._day)
        self._meal = None
        self._dish = None
        self._in_comment = False

    def _start_meal(self, match: re.Match[str]) -> None:
        self._flush_buffer()
        if self._day is None:
            # Posiłek przed nazwą dnia = uszkodzona ekstrakcja; nie zgadujemy dnia.
            self._start_day(label="")
        assert self._day is not None
        self._meal = ParsedMeal(
            label=match.group("meal"),
            pdf_kcal=parse_decimal(match.group("kcal")),
            pdf_macros={
                "W": str(parse_decimal(match.group("carbs"))),
                "B": str(parse_decimal(match.group("protein"))),
                "T": str(parse_decimal(match.group("fat"))),
                "Bł": str(parse_decimal(match.group("fiber"))),
                "ŁG": str(parse_decimal(match.group("glycemic"))),
            },
        )
        self._day.meals.append(self._meal)
        self._dish = None
        self._in_comment = False

    def _start_dish(self, name: str, declared_servings: int | None) -> None:
        self._flush_buffer()
        if self._meal is None:
            return
        self._dish = ParsedDish(name=name, declared_servings=declared_servings)
        self._meal.dishes.append(self._dish)
        self._in_comment = False

    def _ensure_dish(self) -> ParsedDish | None:
        """Danie bez rozpoznanego tytułu (np. urwana kolumna) i tak musi istnieć."""
        if self._dish is not None:
            return self._dish
        if self._meal is None:
            return None
        self._dish = ParsedDish(name=self._meal.label.capitalize())
        self._meal.dishes.append(self._dish)
        return self._dish

    def _close_day(self, declared_kcal: Decimal) -> None:
        self._flush_buffer()
        if self._day is not None:
            self._day.declared_kcal = declared_kcal
        self._day = None
        self._meal = None
        self._dish = None
        self._in_comment = False

    # --- pętla główna ---------------------------------------------------------

    def feed(self, line: str) -> None:
        """Jedna linia strony dnia."""
        stripped = line.strip()
        if not stripped or _FOOTER_RE.match(stripped):
            return

        if stripped in _DAY_LABELS:
            self._start_day(stripped)
            return

        meal_header = MEAL_HEADER_RE.match(stripped)
        if meal_header:
            self._start_meal(meal_header)
            return

        day_total = DAY_TOTAL_RE.match(stripped)
        if day_total:
            self._close_day(parse_decimal(day_total.group("kcal")))
            return

        ingredient = INGREDIENT_RE.match(line)
        if ingredient:
            self._add_ingredient(ingredient)
            return

        if stripped == _SECTION_COMMENT:
            self._flush_buffer()
            self._in_comment = True
            return

        if stripped == _SECTION_PRODUCTS:
            # Dodatkowe składniki POZA przepisem wieloporcjowym (§3.3/§7) —
            # trafiają do tego samego dania, bo są wliczone w jego makro.
            self._flush_buffer()
            self._in_comment = False
            return

        eaten = _EAT_ONE_OF_RE.match(stripped)
        if eaten:
            self._confirm_servings(int(eaten.group("servings")), line=stripped)
            return
        if _EAT_OTHER_RE.match(stripped):
            # Wariant spoza kontraktu (`Zjedz 2 porcję`) — rozpoznany, ale nic
            # z niego nie wnioskujemy; szczegóły w erracie 01_PDF_AUDIT §9.
            return

        title = DISH_TITLE_RE.match(stripped)
        if title and title.group("name") and self._meal is not None:
            servings = title.group("servings")
            self._start_dish(title.group("name").strip(), int(servings) if servings else None)
            return

        if self._is_unparsed_ingredient(line):
            self._warn("Linia wygląda na składnik, ale nie pasuje do formatu z §3.2", line)
            return

        self._buffer.append(stripped)

    def _add_ingredient(self, match: re.Match[str]) -> None:
        dish = self._ensure_dish()
        if dish is None:
            return
        dish.ingredients.append(
            ParsedIngredient(
                raw_name=match.group("name").strip(),
                raw_qty=parse_decimal(match.group("qty")),
                raw_unit=match.group("unit").strip(),
                grams=parse_decimal(match.group("grams")),
            )
        )
        rest = match.group("rest").strip()
        if rest:
            # Prawa kolumna doklejona do wiersza składnika — do bufora instrukcji.
            self._buffer.append(rest)

    def _confirm_servings(self, servings: int, *, line: str) -> None:
        """`Zjedz 1 z N porcji` potwierdza N; rozjazd z nagłówkiem to ostrzeżenie."""
        if self._dish is None:
            return
        declared = self._dish.declared_servings
        if declared is None:
            self._dish.declared_servings = servings
        elif declared != servings:
            self._warn(
                f"Potwierdzenie porcji nie zgadza się z nagłówkiem „Przepis na {declared} porcji”",
                line,
            )

    def _is_unparsed_ingredient(self, line: str) -> bool:
        """Czy linia WYGLĄDA na składnik mimo niedopasowania do kontraktu §3.2.

        Zawężone celowo: bez tego warunku ostrzeżeniem stałaby się każda linia
        instrukcji z prawej kolumny (w korpusie prawie 500 takich linii), a
        raport parsowania przestałby cokolwiek znaczyć.
        """
        if self._meal is None:
            return False
        stripped = line.strip()
        return bool(
            _INGREDIENT_SHAPED_RE.match(stripped) or _INGREDIENT_WRAPPED_HEAD_RE.match(stripped)
        )

    def finish(self) -> None:
        """Domknij bufory po ostatniej linii dokumentu."""
        self._flush_buffer()


def _checksums(days: Iterable[ParsedDay]) -> tuple[list[DayChecksum], list[Finding]]:
    """Sumy kontrolne dni (§4) razem z ostrzeżeniami o rozjazdach."""
    checksums: list[DayChecksum] = []
    findings: list[Finding] = []
    for day in days:
        computed = day.computed_kcal
        expected = day.declared_kcal
        ok = expected is not None and abs(computed - expected) <= DAY_CHECKSUM_TOLERANCE_KCAL
        checksums.append(DayChecksum(day=day.label, expected=expected, computed=computed, ok=ok))
        if ok:
            continue
        findings.append(
            Finding(
                kind=FindingKind.PARSE_WARNING,
                severity=FindingSeverity.WARNING,
                details={
                    "powód": "Suma kcal posiłków nie zgadza się z „SUMA DNIA”",
                    "oczekiwane": str(expected) if expected is not None else None,
                    "otrzymane": str(computed),
                },
                day_label=day.label,
            )
        )
    return checksums, findings


def _multi_portion_findings(days: Sequence[ParsedDay]) -> list[Finding]:
    """Posiłki cięższe niż próg i BEZ jawnej liczby porcji (§5.1) — blocker.

    Masa liczy się PER POSIŁEK, nie per danie: `pdf_kcal` w dokumencie też jest
    per posiłek, więc „składniki ważą 806 g, a posiłek ma 554 kcal” to zdanie
    o posiłku. Ta reguła odtwarza dokładnie tabelę §5.1 (6 posiłków ponad próg:
    2 oznaczone, 4 nieoznaczone) — pomiar w erracie §9.
    """
    findings: list[Finding] = []
    dish_index = 0
    for day in days:
        for meal in day.meals:
            first_index = dish_index
            heaviest = first_index
            heaviest_grams = Decimal(-1)
            for offset, dish in enumerate(meal.dishes):
                if dish.grams_total > heaviest_grams:
                    heaviest_grams = dish.grams_total
                    heaviest = first_index + offset
            dish_index += len(meal.dishes)

            if meal.has_declared_servings or meal.grams_total <= MULTI_PORTION_THRESHOLD_G:
                continue
            findings.append(
                Finding(
                    kind=FindingKind.MULTI_PORTION_SUSPECT,
                    severity=FindingSeverity.BLOCKER,
                    details={
                        "powód": (
                            "Składniki ważą więcej niż próg, a dokument nie podaje "
                            "liczby porcji — trzeba ją ustalić w review"
                        ),
                        "masa_g": str(meal.grams_total),
                        "próg_g": str(MULTI_PORTION_THRESHOLD_G),
                        "pdf_kcal": str(meal.pdf_kcal),
                    },
                    day_label=day.label,
                    meal_label=meal.label,
                    dish_index=heaviest if meal.dishes else None,
                )
            )
    return findings


def parse_document(pages: Sequence[str]) -> ParsedDocument:
    """Teksty stron → struktura dokumentu razem z ustaleniami do review."""
    kinds = classify_pages(pages)
    builder = _DocumentBuilder()
    for kind, text in zip(kinds, pages, strict=True):
        if kind is not PageKind.DAY:
            continue
        for line in text.splitlines():
            builder.feed(line)
    builder.finish()

    checksums, checksum_findings = _checksums(builder.days)
    findings = (
        *builder.findings,
        *checksum_findings,
        *_multi_portion_findings(builder.days),
    )
    return ParsedDocument(
        pages=kinds,
        days=tuple(builder.days),
        findings=findings,
        checksums=tuple(checksums),
    )


def build_parse_report(
    document: ParsedDocument,
    *,
    match_counts: Mapping[str, int],
    issue_counts: Mapping[str, int],
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Kształt `import_jobs.parse_report` (karta B15 §Backend).

    Liczby dziesiętne wchodzą jako STRINGI (ADR-008): JSONB przechowałby je
    jako `double precision` i suma kontrolna 2020,5 przestałaby być tą liczbą.
    """
    return {
        "pages": {
            "total": len(document.pages),
            "days": sum(1 for kind in document.pages if kind is PageKind.DAY),
            "skipped_shopping": sum(1 for kind in document.pages if kind is PageKind.SHOPPING_LIST),
            "skipped_exchanges": sum(1 for kind in document.pages if kind is PageKind.EXCHANGES),
        },
        "days": len(document.days),
        "meals": len(document.meals),
        "staged_recipes": len(document.dishes),
        "ingredients": sum(len(dish.ingredients) for dish in document.dishes),
        "issues": {
            "blocker": issue_counts.get("blocker", 0),
            "warning": issue_counts.get("warning", 0),
        },
        "match": {
            "exact": match_counts.get("exact", 0),
            "none": match_counts.get("none", 0),
        },
        "day_checksums": [
            {
                "day": checksum.day,
                "expected": None if checksum.expected is None else str(checksum.expected),
                "computed": str(checksum.computed),
                "ok": checksum.ok,
            }
            for checksum in document.checksums
        ],
        "warnings": list(warnings),
    }
