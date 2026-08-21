"""Silnik zakupowy — najcięższa logika programu, w całości czysta (ADR-008).

Pipeline z 02_DOMAIN §9.1, krok po kroku, każdy jako osobna funkcja składana
w `generate_preview`:

    plan → porcje → składniki → normalizacja(g/ml/szt.) → agregacja per produkt
    → [spiżarnia? — TYLKO gdy `use_pantry`] → „mam już w domu" → podział na tury
    → dobór opakowań retail → PREVIEW z niejasnościami

Zasady twarde:

- **zero I/O, zero ORM, zero zegara**: dane wchodzą jako dataclassy
  (`EngineInput`), czas jest zawarty w zakresie dat wejścia,
- **`Decimal` end-to-end**; jedyne zaokrąglenie to `ceil` przy liczbie
  opakowań, bo opakowań nie kupuje się po pół (02_DOMAIN §9.3),
- **konwersje jednostek pochodzą z `catalog/units.py`** i nie są tu
  powtarzane — silnik woła `to_base_amount`, bo zakupy liczy się na osi
  PRZECHOWYWANIA produktu (masa → g, objętość → ml, sztuki → szt.),
- **determinizm**: identyczne wejście ⇒ identyczne wyjście. Wszystkie
  sortowania są jawne i stabilne (po id/nazwie/pozycji), żaden zbiór nie
  wychodzi na zewnątrz bez uporządkowania,
- **silnik nie decyduje za użytkownika**: brak wariantu sklepowego, brak
  kategorii i nieprzeliczalna ilość trafiają do `issues`, a nie do domysłu.

Dwie rzeczy, których w pipeline z 02_DOMAIN nie widać wprost, a są ustaleniami
tego batcha (opisane w karcie B10, Completion notes):

1. **Żadne zapotrzebowanie nie ginie.** Okna tur liczy się kursorami
   (`covers_days`/`fresh_days`), a ostatnie okno każdego rodzaju rozciąga się
   do końca zakresu. Gdyby okna kończyły się przed `date_to`, dni „za oknem"
   wypadłyby z listy zakupów po cichu — a cicha utrata pozycji jest gorsza niż
   tura kupująca o dwa dni więcej.
2. **Spiżarnia zjada dni po kolei** (FIFO od `date_from`). Dzięki temu
   `from_pantry_amount` da się przypisać konkretnej TURZE: to, co mamy w domu,
   pokrywa najbliższe dni, czyli pierwszą turę.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from app.core.errors import AppError
from app.modules.catalog.models import Perishability
from app.modules.catalog.units import (
    AmountUnit,
    MeasureKind,
    NormalizedAmount,
    ProductMeasure,
    UnitConversionError,
    base_unit,
    to_base_amount,
)

__all__ = [
    "AMOUNT_QUANTUM",
    "PACKAGE_QUANTUM",
    "PARAMS_VERSION",
    "EngineInput",
    "IngredientInput",
    "IssueKind",
    "IssueSeverity",
    "PantryInput",
    "PlanItemInput",
    "PreviewIssue",
    "PreviewLine",
    "PreviewResult",
    "PreviewRound",
    "ProductInput",
    "RecipeInput",
    "RetailInput",
    "RetailOptionView",
    "RoundInput",
    "RoundMode",
    "ShoppingParamsError",
    "blocking_issues",
    "dump_input",
    "generate_preview",
    "load_input",
    "quantize_amount",
    "quantize_package",
]

_ZERO = Decimal("0")


class RoundMode(StrEnum):
    """Co tura kupuje (02_DOMAIN §9.2).

    Enum mieszka w silniku, a nie w `models.py`, bo należy do LOGIKI podziału
    na tury — model bazy tylko go odwzorowuje w typie PG (tak samo jak
    `AmountUnit` mieszka w `catalog/units.py`).
    """

    ALL = "all"
    DURABLE_PLUS_FRESH_WINDOW = "durable_plus_fresh_window"
    FRESH_ONLY = "fresh_only"


class IssueKind(StrEnum):
    """Rodzaje niejasności preview (karta B10 §Backend pkt 8).

    `PANTRY_AMOUNT_NOT_CONVERTIBLE` to rozszerzenie względem trzech rodzajów
    z karty: pozycja spiżarni w jednostce niezgodnej z obecnym sposobem
    liczenia produktu NIE zostaje odjęta (kupimy z zapasem), ale użytkownik
    musi się o tym dowiedzieć — cicha rozbieżność między „mam w domu"
    a listą byłaby gorsza od ostrzeżenia.
    """

    MISSING_RETAIL = "missing_retail"
    PRODUCT_WITHOUT_CATEGORY = "product_without_category"
    PLAN_ITEM_WITHOUT_AMOUNT = "plan_item_without_amount"
    PANTRY_AMOUNT_NOT_CONVERTIBLE = "pantry_amount_not_convertible"


class IssueSeverity(StrEnum):
    """Waga niejasności: bloker wstrzymuje finalizację, ostrzeżenie tylko informuje."""

    BLOCKER = "blocker"
    WARNING = "warning"


class ShoppingParamsError(AppError):
    """409 — zapis `params` nie daje się odczytać obecną wersją silnika.

    To realny scenariusz, nie obrona przed cudzymi danymi: kolejne batche mogą
    zmienić kształt wejścia, a stara generacja zostaje w bazie (historii nie
    kasujemy — D10). Użytkownik ma wtedy dostać instrukcję, nie 500.
    """

    status_code = 409
    code = "conflict"


PARAMS_MESSAGE = (
    "Zapis tej generacji pochodzi z innej wersji aplikacji i nie da się go już odtworzyć. "
    "Wygeneruj zakupy ponownie."
)

#: Wersja kształtu `params` (03_DATABASE §8). Zmiana kształtu = nowy numer.
PARAMS_VERSION = 1


# --- wejście silnika ------------------------------------------------------------------


@dataclass(frozen=True)
class ProductInput:
    """Produkt kanoniczny w postaci, której potrzebują zakupy (bez ORM).

    `perishability` jest już ROZSTRZYGNIĘTA przez serwis (`override ?? kategoria`,
    karta B10 nota 2) — silnik nie zna kolumn produktu. `category_position`
    ustala kolejność pozycji w turze (profil sklepu nakłada B11).
    """

    product_id: int
    name: str
    measure_kind: MeasureKind
    piece_weight_g: Decimal | None = None
    category_id: int | None = None
    category_name: str | None = None
    category_position: int = 0
    perishability: Perishability | None = None

    @property
    def unit(self) -> AmountUnit:
        """Oś, na której liczymy zapotrzebowanie i opakowania tego produktu."""
        return base_unit(self.measure_kind)

    @property
    def measure(self) -> ProductMeasure:
        """Dane dla `catalog/units.py` — konwersje mają jedno miejsce (ADR-005)."""
        return ProductMeasure(measure_kind=self.measure_kind, piece_weight_g=self.piece_weight_g)


@dataclass(frozen=True)
class IngredientInput:
    """Składnik przepisu: ilość ZNORMALIZOWANA przy zapisie (02_DOMAIN §13.1)."""

    product_id: int
    amount: Decimal
    amount_unit: AmountUnit


@dataclass(frozen=True)
class RecipeInput:
    """Przepis rozwijany do składników. `base_servings` to dzielnik porcji."""

    recipe_id: int
    name: str
    base_servings: int
    ingredients: tuple[IngredientInput, ...] = ()


@dataclass(frozen=True)
class PlanItemInput:
    """Pozycja planu: przepis z mnożnikiem ALBO produkt luzem z ilością.

    Mnożnik działa w obu przypadkach tak samo (02_DOMAIN §13.3, ustalenie B06):
    dla przepisu skaluje porcję bazową, dla produktu — zapisaną ilość. Rozkład
    rodzinny NIE wchodzi do wejścia: jego suma jest równa `servings`, więc
    liczyłby to samo dwa razy.
    """

    item_id: int
    day: date
    meal_name: str
    servings: Decimal
    recipe_id: int | None = None
    product_id: int | None = None
    amount: Decimal | None = None
    amount_unit: AmountUnit | None = None


@dataclass(frozen=True)
class PantryInput:
    """Pozycja stanu domowego (kontrakt `PantryService.get_household_state`, B08).

    Pozycja może wskazywać produkt kanoniczny ALBO wariant sklepowy — w drugim
    przypadku silnik sprowadza ją do produktu kanonicznego wariantu, bo
    zapotrzebowanie agreguje się po produkcie (02_DOMAIN §9.1).
    """

    item_id: int
    amount: Decimal
    amount_unit: AmountUnit
    product_id: int | None = None
    retail_product_id: int | None = None


@dataclass(frozen=True)
class RetailInput:
    """Wariant sklepowy — opakowanie, z którego liczy się `ceil` i resztkę.

    `package_unit` jest z założenia na osi produktu kanonicznego (niezmiennik
    B09), ale silnik i tak porównuje jednostki: wariant zapisany przed zmianą
    `measure_kind` produktu (D15) nie ma prawa cicho zafałszować liczby
    opakowań. `is_archived=True` wariant NIE jest proponowany — służy tylko do
    sprowadzenia pozycji spiżarni do produktu kanonicznego.
    """

    retail_product_id: int
    product_id: int
    label: str
    package_amount: Decimal
    package_unit: AmountUnit
    store_id: int | None = None
    store_name: str | None = None
    is_archived: bool = False


@dataclass(frozen=True)
class RoundInput:
    """Jedna tura zakupowa (konfiguracja `shopping_round_configs`).

    `key` to stabilny identyfikator tury w obrębie generacji — pozycje preview
    i decyzje użytkownika odwołują się do niego, więc musi przetrwać zapis do
    `params` i ponowne policzenie preview.
    """

    key: str
    name: str
    mode: RoundMode
    covers_days: int
    fresh_days: int | None = None
    shopping_weekday: int | None = None


@dataclass(frozen=True)
class EngineInput:
    """PEŁNE wejście generacji — to jest treść `shopping_generations.params`.

    Dzięki temu, że wejście jest kompletne, `GET` generacji odtwarza preview
    bez ponownego czytania planu, a `resolve` zmienia wyłącznie trzy ostatnie
    pola (decyzje użytkownika) i przelicza to samo (karta B10 nota 3).
    """

    date_from: date
    date_to: date
    use_pantry: bool = False
    rounds: tuple[RoundInput, ...] = ()
    items: tuple[PlanItemInput, ...] = ()
    recipes: tuple[RecipeInput, ...] = ()
    products: tuple[ProductInput, ...] = ()
    pantry: tuple[PantryInput, ...] = ()
    retail: tuple[RetailInput, ...] = ()
    #: Produkty oznaczone „mam już w domu" — pozycja zostaje w preview.
    already_have: tuple[int, ...] = ()
    #: Wybór wariantu sklepowego użytkownika: (produkt, wariant).
    retail_choices: tuple[tuple[int, int], ...] = ()
    #: Klucze niejasności, które użytkownik świadomie odłożył (przestają blokować).
    dismissed_issues: tuple[str, ...] = ()

    @property
    def total_days(self) -> int:
        """Liczba dni zakresu (włącznie z oboma końcami)."""
        return (self.date_to - self.date_from).days + 1


# --- wyjście silnika ------------------------------------------------------------------


@dataclass(frozen=True)
class RetailOptionView:
    """Wariant do wyboru w preview — UI pokazuje go w selektorze pozycji."""

    retail_product_id: int
    label: str
    package_amount: Decimal
    package_unit: AmountUnit
    store_id: int | None
    store_name: str | None


@dataclass(frozen=True)
class PreviewLine:
    """Jedna pozycja preview: produkt w konkretnej turze.

    `needed_amount` to potrzeba PO odjęciu spiżarni (nigdy ujemna — 08_TESTING
    §2.5), `raw_amount` to potrzeba przed odjęciem, a `from_pantry_amount`
    różnica przypisana tej turze. `leftover_amount` (kupione - potrzeba) jest
    wyliczane zawsze, gdy znany jest wariant — resztka ma być widoczna
    (02_DOMAIN §9.3).
    """

    round_key: str
    product_id: int
    label: str
    unit: AmountUnit
    needed_amount: Decimal
    raw_amount: Decimal
    category_id: int | None
    category_name: str | None
    category_position: int
    perishability: Perishability | None
    days: tuple[date, ...]
    from_pantry_amount: Decimal | None = None
    already_have: bool = False
    retail_product_id: int | None = None
    retail_label: str | None = None
    package_amount: Decimal | None = None
    packages_count: int | None = None
    leftover_amount: Decimal | None = None
    retail_options: tuple[RetailOptionView, ...] = ()


@dataclass(frozen=True)
class PreviewRound:
    """Tura w preview razem z oknem, które faktycznie pokryła."""

    key: str
    name: str
    mode: RoundMode
    shopping_weekday: int | None
    shopping_date: date | None
    date_from: date | None
    date_to: date | None
    items: tuple[PreviewLine, ...] = ()


@dataclass(frozen=True)
class PreviewIssue:
    """Niejasność wymagająca decyzji człowieka (albo tylko jego wiedzy)."""

    key: str
    kind: IssueKind
    severity: IssueSeverity
    message: str
    dismissed: bool = False
    product_id: int | None = None
    plan_item_id: int | None = None
    pantry_item_id: int | None = None


@dataclass(frozen=True)
class PreviewResult:
    """Wynik silnika: tury z pozycjami + niejasności. Nic więcej nie istnieje."""

    date_from: date
    date_to: date
    use_pantry: bool
    rounds: tuple[PreviewRound, ...] = ()
    issues: tuple[PreviewIssue, ...] = ()
    #: Echo JAWNYCH wyborów wariantu (produkt → wariant) z wejścia.
    #: Bez tego konsument nie odróżnia wariantu wybranego PRZEZ CZŁOWIEKA od
    #: dobranego automatem, a `resolve` zastępuje cały zbiór — pierwsza dowolna
    #: decyzja zamroziłaby wszystkie auto-wybory jako „wolę ten".
    retail_choices: tuple[tuple[int, int], ...] = ()


def blocking_issues(result: PreviewResult) -> tuple[PreviewIssue, ...]:
    """Niejasności, które wstrzymują finalizację (blokery bez decyzji użytkownika)."""
    return tuple(
        issue
        for issue in result.issues
        if issue.severity is IssueSeverity.BLOCKER and not issue.dismissed
    )


# --- pipeline -------------------------------------------------------------------------


@dataclass
class _Demand:
    """Zapotrzebowanie jednego produktu: ile i na które dni (stan roboczy)."""

    per_day: dict[date, Decimal] = field(default_factory=dict)

    def add(self, day: date, amount: Decimal) -> None:
        self.per_day[day] = self.per_day.get(day, _ZERO) + amount

    @property
    def total(self) -> Decimal:
        return sum(self.per_day.values(), _ZERO)


def generate_preview(data: EngineInput) -> PreviewResult:
    """Pełny pipeline: `EngineInput` → `PreviewResult`. Czysta funkcja.

    Kolejność kroków jest wiążąca (02_DOMAIN §9.1) — w szczególności spiżarnia
    odejmuje się PRZED podziałem na tury, bo stan domowy dotyczy produktu,
    a nie tury, a „mam już w domu" jest decyzją o produkcie.
    """
    issues: list[PreviewIssue] = []
    products = {product.product_id: product for product in data.products}
    recipes = {recipe.recipe_id: recipe for recipe in data.recipes}
    retail_by_id = {variant.retail_product_id: variant for variant in data.retail}

    demand = _aggregate_demand(data, products, recipes, issues)
    pantry = _pantry_totals(data, products, retail_by_id, issues) if data.use_pantry else {}
    consumed, remaining = _apply_pantry(demand, pantry)

    windows = _round_windows(data)
    rounds = _build_rounds(
        data,
        windows=windows,
        remaining=remaining,
        consumed=consumed,
        products=products,
        issues=issues,
    )
    return PreviewResult(
        date_from=data.date_from,
        date_to=data.date_to,
        use_pantry=data.use_pantry,
        rounds=rounds,
        issues=_finalize_issues(issues, data.dismissed_issues),
        retail_choices=data.retail_choices,
    )


# --- krok 1-3: plan → porcje → składniki → normalizacja → agregacja -------------------


def _aggregate_demand(
    data: EngineInput,
    products: Mapping[int, ProductInput],
    recipes: Mapping[int, RecipeInput],
    issues: list[PreviewIssue],
) -> dict[int, _Demand]:
    """Pozycje planu → zapotrzebowanie per produkt i dzień, na osi produktu.

    Wkład pozycji z przepisem to `ilość_składnika x servings / base_servings`.
    Dzielenie `Decimal` bywa nieskończone (np. /3), więc kroków pośrednich NIE
    kwantyzujemy (ADR-008): zaokrągla dopiero liczba opakowań.
    """
    demand: dict[int, _Demand] = {}
    for item in sorted(data.items, key=lambda row: (row.day, row.item_id)):
        if not (data.date_from <= item.day <= data.date_to):  # pragma: no cover
            # Serwis pyta plan o dokładnie ten zakres — warunek chroni przed
            # cichym policzeniem dnia spoza generacji.
            continue
        for product_id, amount, unit in _item_contributions(item, recipes):
            product = products.get(product_id)
            if product is None:  # pragma: no cover — chroni FK RESTRICT
                continue
            try:
                normalized = to_base_amount(NormalizedAmount(amount, unit), product.measure)
            except UnitConversionError:
                issues.append(_amount_issue(item, product))
                continue
            demand.setdefault(product_id, _Demand()).add(item.day, normalized)
    return demand


def _item_contributions(
    item: PlanItemInput, recipes: Mapping[int, RecipeInput]
) -> list[tuple[int, Decimal, AmountUnit]]:
    """Wkład JEDNEJ pozycji planu: produkt luzem wprost, przepis po składnikach."""
    if item.recipe_id is not None:
        recipe = recipes.get(item.recipe_id)
        if recipe is None or recipe.base_servings <= 0:  # pragma: no cover — FK RESTRICT
            return []
        factor = item.servings / Decimal(recipe.base_servings)
        return [
            (ingredient.product_id, ingredient.amount * factor, ingredient.amount_unit)
            for ingredient in recipe.ingredients
        ]
    if item.product_id is None or item.amount is None or item.amount_unit is None:
        return []  # pragma: no cover — CHECK `product_requires_amount` w bazie
    return [(item.product_id, item.amount * item.servings, item.amount_unit)]


def _amount_issue(item: PlanItemInput, product: ProductInput) -> PreviewIssue:
    """Bloker: ilości pozycji planu nie da się przeliczyć na jednostkę produktu.

    Dzieje się to, gdy ADMIN zmienił `measure_kind` produktu PO zapisaniu
    pozycji (D15 nie przelicza ilości). Nie „ratujemy" tego domysłem
    (02_DOMAIN §13.1) — pozycja nie wchodzi do zapotrzebowania i użytkownik
    dowiaduje się, co poprawić.
    """
    return PreviewIssue(
        key=f"{IssueKind.PLAN_ITEM_WITHOUT_AMOUNT.value}:item:{item.item_id}",
        kind=IssueKind.PLAN_ITEM_WITHOUT_AMOUNT,
        severity=IssueSeverity.BLOCKER,
        message=(
            f"Pozycja planu z {item.day.strftime('%d.%m.%Y')} ({item.meal_name}) ma ilość "
            f"w jednostce niezgodnej ze sposobem liczenia produktu „{product.name}”. "
            "Popraw pozycję planu, żeby weszła do zakupów."
        ),
        product_id=product.product_id,
        plan_item_id=item.item_id,
    )


# --- krok 4: spiżarnia ----------------------------------------------------------------


def _pantry_totals(
    data: EngineInput,
    products: Mapping[int, ProductInput],
    retail_by_id: Mapping[int, RetailInput],
    issues: list[PreviewIssue],
) -> dict[int, Decimal]:
    """Stan domowy zagregowany per produkt kanoniczny, na osi produktu.

    Wejście to LISTA pozycji (jeden produkt = wiele partii z różnymi datami —
    kontrakt B08), więc agregacja należy tutaj. Kolejność pozycji z serwisu
    jest ustalona, ale wynik i tak nie zależy od niej: sumowanie `Decimal`
    jest łączne, a klucze sortujemy przy odczycie.
    """
    totals: dict[int, Decimal] = {}
    for row in data.pantry:
        product_id = row.product_id
        if product_id is None and row.retail_product_id is not None:
            variant = retail_by_id.get(row.retail_product_id)
            product_id = variant.product_id if variant is not None else None
        if product_id is None:
            continue  # pragma: no cover — CHECK `product_required` w bazie
        product = products.get(product_id)
        if product is None:
            # Produkt bez zapotrzebowania w tym zakresie — nie ma czego odejmować.
            continue
        try:
            amount = to_base_amount(NormalizedAmount(row.amount, row.amount_unit), product.measure)
        except UnitConversionError:
            issues.append(_pantry_issue(row, product))
            continue
        totals[product_id] = totals.get(product_id, _ZERO) + amount
    return totals


def _pantry_issue(row: PantryInput, product: ProductInput) -> PreviewIssue:
    """Ostrzeżenie: pozycji spiżarni nie da się odjąć, więc kupimy z zapasem."""
    return PreviewIssue(
        key=f"{IssueKind.PANTRY_AMOUNT_NOT_CONVERTIBLE.value}:item:{row.item_id}",
        kind=IssueKind.PANTRY_AMOUNT_NOT_CONVERTIBLE,
        severity=IssueSeverity.WARNING,
        message=(
            f"Stan domowy produktu „{product.name}” jest zapisany w jednostce niezgodnej "
            "z jego obecnym sposobem liczenia, więc nie został odjęty od zakupów. "
            "Popraw pozycję w spiżarni."
        ),
        product_id=product.product_id,
        pantry_item_id=row.item_id,
    )


def _apply_pantry(
    demand: Mapping[int, _Demand], pantry: Mapping[int, Decimal]
) -> tuple[dict[int, dict[date, Decimal]], dict[int, dict[date, Decimal]]]:
    """Odejmij stan domowy od zapotrzebowania — FIFO po dniach, nigdy poniżej zera.

    Zwraca dwie mapy per produkt i dzień: ile zostało do kupienia i ile pokryła
    spiżarnia. Rozdzielenie na dni jest tym, co pozwala pokazać
    `from_pantry_amount` przy KONKRETNEJ turze, a nie tylko w sumie generacji.
    """
    remaining: dict[int, dict[date, Decimal]] = {}
    consumed: dict[int, dict[date, Decimal]] = {}
    for product_id in sorted(demand):
        available = pantry.get(product_id, _ZERO)
        per_day_remaining: dict[date, Decimal] = {}
        per_day_consumed: dict[date, Decimal] = {}
        for day in sorted(demand[product_id].per_day):
            needed = demand[product_id].per_day[day]
            taken = min(needed, available) if available > _ZERO else _ZERO
            available -= taken
            per_day_remaining[day] = needed - taken
            per_day_consumed[day] = taken
        remaining[product_id] = per_day_remaining
        consumed[product_id] = per_day_consumed
    return consumed, remaining


# --- krok 6: podział na tury ----------------------------------------------------------


@dataclass(frozen=True)
class _Window:
    """Okno dni tury jako przesunięcia od `date_from` (koniec wyłączny)."""

    start: int
    end: int

    @property
    def is_empty(self) -> bool:
        return self.end <= self.start

    def contains(self, offset: int) -> bool:
        return self.start <= offset < self.end


def _round_windows(data: EngineInput) -> dict[str, tuple[_Window, _Window]]:
    """Okna (trwałe, świeże) każdej tury — kursory po zakresie dat.

    Tury konsumują zakres PO KOLEI, każda od miejsca, w którym skończyła
    poprzednia: `covers_days` przesuwa kursor trwałych, `fresh_days` (albo
    `covers_days`, gdy nie podano) kursor świeżych. Tak działa preset z
    02_DOMAIN §9.2: niedziela bierze trwałe na 7 dni i świeże na 4, a środa
    domyka świeże na resztę tygodnia.

    Ostatnie NIEPUSTE okno każdego rodzaju rozciągamy do końca zakresu —
    inaczej dni za oknami wypadłyby z zakupów bez śladu.
    """
    total = data.total_days
    durable_cursor = 0
    fresh_cursor = 0
    windows: dict[str, tuple[_Window, _Window]] = {}

    for round_input in data.rounds:
        covers = max(round_input.covers_days, 0)
        if round_input.mode is RoundMode.FRESH_ONLY:
            durable = _Window(durable_cursor, durable_cursor)
            fresh = _Window(fresh_cursor, min(fresh_cursor + covers, total))
            fresh_cursor = min(fresh_cursor + covers, total)
        elif round_input.mode is RoundMode.DURABLE_PLUS_FRESH_WINDOW:
            fresh_span = round_input.fresh_days if round_input.fresh_days is not None else covers
            durable = _Window(durable_cursor, min(durable_cursor + covers, total))
            fresh = _Window(fresh_cursor, min(fresh_cursor + max(fresh_span, 0), total))
            durable_cursor = min(durable_cursor + covers, total)
            fresh_cursor = min(fresh_cursor + max(fresh_span, 0), total)
        else:
            durable = _Window(durable_cursor, min(durable_cursor + covers, total))
            fresh = _Window(fresh_cursor, min(fresh_cursor + covers, total))
            durable_cursor = min(durable_cursor + covers, total)
            fresh_cursor = min(fresh_cursor + covers, total)
        windows[round_input.key] = (durable, fresh)

    return _extend_last_windows(data.rounds, windows, total)


def _extend_last_windows(
    rounds: Sequence[RoundInput], windows: dict[str, tuple[_Window, _Window]], total: int
) -> dict[str, tuple[_Window, _Window]]:
    """Domknij zakres: ostatnia tura każdego rodzaju kupuje do `date_to`.

    Gdy ŻADNA tura nie kupuje danego rodzaju (np. wszystkie są `fresh_only`,
    a plan ma produkty trwałe), rodzaj przypada pierwszej turze — zapotrzebowanie
    musi gdzieś trafić, a pierwsza tura jest najwcześniejszą okazją do zakupu.
    """
    if not rounds:
        return windows

    for index in (0, 1):
        last_key = next(
            (
                round_input.key
                for round_input in reversed(rounds)
                if not windows[round_input.key][index].is_empty
            ),
            None,
        )
        if last_key is None:
            first = rounds[0].key
            pair = list(windows[first])
            pair[index] = _Window(0, total)
            windows[first] = (pair[0], pair[1])
            continue
        pair = list(windows[last_key])
        window = pair[index]
        if window.end < total:
            pair[index] = _Window(window.start, total)
            windows[last_key] = (pair[0], pair[1])
    return windows


def _window_for(perishability: Perishability | None, pair: tuple[_Window, _Window]) -> _Window:
    """Okno właściwe dla trwałości produktu (świeże → drugie okno tury)."""
    return pair[1] if perishability is Perishability.FRESH else pair[0]


# --- kroki 5-8: pozycje tur, opakowania, preview --------------------------------------


def _build_rounds(
    data: EngineInput,
    *,
    windows: Mapping[str, tuple[_Window, _Window]],
    remaining: Mapping[int, Mapping[date, Decimal]],
    consumed: Mapping[int, Mapping[date, Decimal]],
    products: Mapping[int, ProductInput],
    issues: list[PreviewIssue],
) -> tuple[PreviewRound, ...]:
    """Rozdziel zapotrzebowanie na tury, dobierz opakowania i złóż preview."""
    already_have = set(data.already_have)
    choices = dict(data.retail_choices)
    options = _retail_options(data.retail)

    placed = _place_products(
        data, windows=windows, remaining=remaining, products=products, issues=issues
    )

    rounds: list[PreviewRound] = []
    for round_input in data.rounds:
        pair = windows[round_input.key]
        lines: list[PreviewLine] = []
        for product_id in placed.get(round_input.key, []):
            product = products[product_id]
            window = _window_for(product.perishability, pair)
            days = tuple(
                day
                for day in sorted(remaining.get(product_id, {}))
                if window.contains((day - data.date_from).days)
            )
            needed = sum((remaining[product_id][day] for day in days), _ZERO)
            from_pantry = (
                sum((consumed.get(product_id, {}).get(day, _ZERO) for day in days), _ZERO)
                if data.use_pantry
                else None
            )
            lines.append(
                _build_line(
                    round_key=round_input.key,
                    product=product,
                    days=days,
                    needed=needed,
                    from_pantry=from_pantry,
                    already_have=product_id in already_have,
                    options=options.get(product_id, ()),
                    chosen_id=choices.get(product_id),
                    issues=issues,
                )
            )
        rounds.append(_preview_round(round_input, pair, data, tuple(lines)))
    return tuple(rounds)


def _place_products(
    data: EngineInput,
    *,
    windows: Mapping[str, tuple[_Window, _Window]],
    remaining: Mapping[int, Mapping[date, Decimal]],
    products: Mapping[int, ProductInput],
    issues: list[PreviewIssue],
) -> dict[str, list[int]]:
    """Które produkty trafiają do której tury — w kolejności renderu.

    Produkt bez kategorii NIE dostaje pozycji: bez trwałości nie wiadomo, do
    której tury należy, a bez kategorii nie ma gdzie go pokazać na liście.
    Zamiast zgadywać, zgłaszamy bloker (karta B10 §Backend pkt 8).
    """
    placed: dict[str, list[int]] = {round_input.key: [] for round_input in data.rounds}
    for product_id in sorted(remaining):
        product = products[product_id]
        if product.category_id is None or product.perishability is None:
            issues.append(_category_issue(product))
            continue
        for round_input in data.rounds:
            window = _window_for(product.perishability, windows[round_input.key])
            if any(window.contains((day - data.date_from).days) for day in remaining[product_id]):
                placed[round_input.key].append(product_id)
    for key in placed:
        placed[key].sort(
            key=lambda product_id: (
                products[product_id].category_position,
                products[product_id].category_name or "",
                products[product_id].name,
                product_id,
            )
        )
    return placed


def _category_issue(product: ProductInput) -> PreviewIssue:
    """Bloker: produkt bez kategorii/trwałości nie ma miejsca w żadnej turze."""
    return PreviewIssue(
        key=f"{IssueKind.PRODUCT_WITHOUT_CATEGORY.value}:product:{product.product_id}",
        kind=IssueKind.PRODUCT_WITHOUT_CATEGORY,
        severity=IssueSeverity.BLOCKER,
        message=(
            f"Produkt „{product.name}” nie ma kategorii, więc nie wiadomo, w której turze "
            "go kupić ani gdzie pokazać go na liście. Uzupełnij kategorię produktu."
        ),
        product_id=product.product_id,
    )


def _retail_options(retail: Iterable[RetailInput]) -> dict[int, tuple[RetailInput, ...]]:
    """Warianty do zaproponowania per produkt — bez archiwalnych, stabilnie posortowane."""
    grouped: dict[int, list[RetailInput]] = {}
    for variant in retail:
        if variant.is_archived:
            continue
        grouped.setdefault(variant.product_id, []).append(variant)
    return {
        product_id: tuple(
            sorted(items, key=lambda item: (item.package_amount, item.retail_product_id))
        )
        for product_id, items in grouped.items()
    }


def _build_line(
    *,
    round_key: str,
    product: ProductInput,
    days: tuple[date, ...],
    needed: Decimal,
    from_pantry: Decimal | None,
    already_have: bool,
    options: tuple[RetailInput, ...],
    chosen_id: int | None,
    issues: list[PreviewIssue],
) -> PreviewLine:
    """Jedna pozycja preview razem z doborem opakowania i resztką."""
    usable = tuple(option for option in options if option.package_unit is product.unit)
    raw = needed + (from_pantry or _ZERO)
    chosen = _choose_variant(usable, needed=needed, chosen_id=chosen_id)

    packages: int | None = None
    leftover: Decimal | None = None
    if chosen is not None and not already_have and needed > _ZERO:
        packages = _packages_count(needed, chosen.package_amount)
        leftover = chosen.package_amount * Decimal(packages) - needed
    if chosen is None and not already_have and needed > _ZERO:
        issues.append(_missing_retail_issue(product))

    return PreviewLine(
        round_key=round_key,
        product_id=product.product_id,
        label=chosen.label if chosen is not None else product.name,
        unit=product.unit,
        needed_amount=needed,
        raw_amount=raw,
        category_id=product.category_id,
        category_name=product.category_name,
        category_position=product.category_position,
        perishability=product.perishability,
        days=days,
        from_pantry_amount=from_pantry,
        already_have=already_have,
        retail_product_id=chosen.retail_product_id if chosen is not None else None,
        retail_label=chosen.label if chosen is not None else None,
        package_amount=chosen.package_amount if chosen is not None else None,
        packages_count=packages,
        leftover_amount=leftover,
        retail_options=tuple(
            RetailOptionView(
                retail_product_id=option.retail_product_id,
                label=option.label,
                package_amount=option.package_amount,
                package_unit=option.package_unit,
                store_id=option.store_id,
                store_name=option.store_name,
            )
            for option in usable
        ),
    )


def _choose_variant(
    options: tuple[RetailInput, ...], *, needed: Decimal, chosen_id: int | None
) -> RetailInput | None:
    """Wybór wariantu: decyzja użytkownika, a bez niej najmniejsza resztka.

    Remis rozstrzyga MNIEJSZE opakowanie (08_TESTING §2.6) — łatwiej dokupić
    drugie niż zmieścić nadmiar. Drugi remis rozstrzyga id, żeby wynik nie
    zależał od kolejności wejścia (determinizm, ADR-008).
    """
    if chosen_id is not None:
        explicit = next(
            (option for option in options if option.retail_product_id == chosen_id), None
        )
        if explicit is not None:
            return explicit
    if not options or needed <= _ZERO:
        # Potrzeba zerowa (spiżarnia pokryła wszystko) nie potrzebuje opakowania —
        # pozycja zostaje w preview, żeby pokazać, co odjęliśmy.
        return None
    return min(
        options,
        key=lambda option: (
            option.package_amount * Decimal(_packages_count(needed, option.package_amount))
            - needed,
            option.package_amount,
            option.retail_product_id,
        ),
    )


def _packages_count(needed: Decimal, package_amount: Decimal) -> int:
    """`ceil(potrzeba / wielkość opakowania)` — opakowań nie kupuje się po pół."""
    if package_amount <= _ZERO:  # pragma: no cover — walidacja serwisu B09
        return 1
    return int((needed / package_amount).to_integral_value(rounding=ROUND_CEILING))


def _missing_retail_issue(product: ProductInput) -> PreviewIssue:
    """Ostrzeżenie (NIE bloker): pozycja pójdzie na listę w g/ml/szt. (02_DOMAIN §9.3)."""
    return PreviewIssue(
        key=f"{IssueKind.MISSING_RETAIL.value}:product:{product.product_id}",
        kind=IssueKind.MISSING_RETAIL,
        severity=IssueSeverity.WARNING,
        message=(
            f"„{product.name}” nie ma produktu sklepowego, więc pozycja pójdzie na listę "
            "w jednostce podstawowej, bez liczby opakowań. Dodaj produkt sklepowy, "
            "jeśli chcesz widzieć opakowania i resztki."
        ),
        product_id=product.product_id,
    )


def _preview_round(
    round_input: RoundInput,
    pair: tuple[_Window, _Window],
    data: EngineInput,
    lines: tuple[PreviewLine, ...],
) -> PreviewRound:
    """Tura z policzonym oknem dat i sugerowanym dniem zakupów."""
    starts = [window.start for window in pair if not window.is_empty]
    ends = [window.end for window in pair if not window.is_empty]
    if starts and ends:
        date_from = data.date_from + timedelta(days=min(starts))
        date_to = data.date_from + timedelta(days=max(ends) - 1)
    else:
        date_from = None
        date_to = None
    return PreviewRound(
        key=round_input.key,
        name=round_input.name,
        mode=round_input.mode,
        shopping_weekday=round_input.shopping_weekday,
        shopping_date=_shopping_date(date_from or data.date_from, round_input.shopping_weekday),
        date_from=date_from,
        date_to=date_to,
        items=lines,
    )


def _shopping_date(window_start: date, weekday: int | None) -> date:
    """Ostatni dzień o zadanym dniu tygodnia NIE PÓŹNIEJSZY niż start okna.

    „Kupuję w niedzielę na poniedziałek-niedzielę" znaczy niedzielę POPRZEDNIĄ,
    a nie tę na końcu tygodnia — dlatego cofamy się, nigdy nie idziemy w przód.
    Bez ustalonego dnia tury (`NULL`) dniem zakupów jest start okna.
    """
    if weekday is None:
        return window_start
    return window_start - timedelta(days=(window_start.weekday() - weekday) % 7)


def _finalize_issues(
    issues: Sequence[PreviewIssue], dismissed: Sequence[str]
) -> tuple[PreviewIssue, ...]:
    """Deduplikacja po kluczu + oznaczenie odłożonych + stabilna kolejność.

    Deduplikacja jest konieczna, bo ta sama niejasność może wyjść z kilku tur
    (produkt świeży wpada do dwóch okien), a użytkownik ma ją zobaczyć raz.
    """
    dismissed_keys = set(dismissed)
    unique: dict[str, PreviewIssue] = {}
    for issue in issues:
        if issue.key not in unique:
            unique[issue.key] = issue if issue.key not in dismissed_keys else _dismissed(issue)
    # Blokery na górze panelu „Do rozstrzygnięcia" — kolejność jawna, nie alfabetyczna.
    return tuple(
        sorted(
            unique.values(),
            key=lambda issue: (
                0 if issue.severity is IssueSeverity.BLOCKER else 1,
                issue.kind.value,
                issue.key,
            ),
        )
    )


def _dismissed(issue: PreviewIssue) -> PreviewIssue:
    """Ta sama niejasność, oznaczona jako świadomie odłożona przez użytkownika."""
    return PreviewIssue(
        key=issue.key,
        kind=issue.kind,
        severity=issue.severity,
        message=issue.message,
        dismissed=True,
        product_id=issue.product_id,
        plan_item_id=issue.plan_item_id,
        pantry_item_id=issue.pantry_item_id,
    )


# --- serializacja wejścia (`shopping_generations.params`) -----------------------------


#: Kwant ilości na wyjściu — skala kolumn NUMERIC(10,3) (`needed_amount` i sąsiedzi).
AMOUNT_QUANTUM = Decimal("0.001")
#: Kwant wielkości opakowania — skala `retail_products.package_amount` NUMERIC(8,2).
PACKAGE_QUANTUM = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Ilość na KRAWĘDZI wyjścia (JSON i zapis do bazy) — 3 miejsca, ROUND_HALF_UP.

    To jedyne zaokrąglenie ilości w całym module obok `ceil` opakowań (ADR-008):
    kroki pośrednie zostają w pełnej precyzji `Decimal`, bo dzielenie porcji
    (`/3`) i tak nie ma skończonego zapisu.
    """
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def quantize_package(value: Decimal) -> Decimal:
    """Wielkość opakowania na krawędzi wyjścia — 2 miejsca, jak kolumna w bazie."""
    return value.quantize(PACKAGE_QUANTUM, rounding=ROUND_HALF_UP)


def _num(value: Decimal | None) -> str | None:
    """`Decimal` → string dziesiętny bez notacji wykładniczej (ADR-008)."""
    return None if value is None else format(value, "f")


def dump_input(data: EngineInput) -> dict[str, Any]:
    """`EngineInput` → JSON-owalny słownik do `shopping_generations.params`.

    Zapisujemy PEŁNE wejście (03_DATABASE §8), bo tylko wtedy `GET` generacji
    i `resolve` liczą preview z tego samego materiału, co `generate` — bez
    ponownego odpytywania planu, który mógł się w międzyczasie zmienić.
    """
    return {
        "v": PARAMS_VERSION,
        "date_from": data.date_from.isoformat(),
        "date_to": data.date_to.isoformat(),
        "use_pantry": data.use_pantry,
        "rounds": [
            {
                "key": row.key,
                "name": row.name,
                "mode": row.mode.value,
                "covers_days": row.covers_days,
                "fresh_days": row.fresh_days,
                "shopping_weekday": row.shopping_weekday,
            }
            for row in data.rounds
        ],
        "items": [
            {
                "item_id": row.item_id,
                "day": row.day.isoformat(),
                "meal_name": row.meal_name,
                "servings": _num(row.servings),
                "recipe_id": row.recipe_id,
                "product_id": row.product_id,
                "amount": _num(row.amount),
                "amount_unit": None if row.amount_unit is None else row.amount_unit.value,
            }
            for row in data.items
        ],
        "recipes": [
            {
                "recipe_id": row.recipe_id,
                "name": row.name,
                "base_servings": row.base_servings,
                "ingredients": [
                    {
                        "product_id": ingredient.product_id,
                        "amount": _num(ingredient.amount),
                        "amount_unit": ingredient.amount_unit.value,
                    }
                    for ingredient in row.ingredients
                ],
            }
            for row in data.recipes
        ],
        "products": [
            {
                "product_id": row.product_id,
                "name": row.name,
                "measure_kind": row.measure_kind.value,
                "piece_weight_g": _num(row.piece_weight_g),
                "category_id": row.category_id,
                "category_name": row.category_name,
                "category_position": row.category_position,
                "perishability": None if row.perishability is None else row.perishability.value,
            }
            for row in data.products
        ],
        "pantry": [
            {
                "item_id": row.item_id,
                "amount": _num(row.amount),
                "amount_unit": row.amount_unit.value,
                "product_id": row.product_id,
                "retail_product_id": row.retail_product_id,
            }
            for row in data.pantry
        ],
        "retail": [
            {
                "retail_product_id": row.retail_product_id,
                "product_id": row.product_id,
                "label": row.label,
                "package_amount": _num(row.package_amount),
                "package_unit": row.package_unit.value,
                "store_id": row.store_id,
                "store_name": row.store_name,
                "is_archived": row.is_archived,
            }
            for row in data.retail
        ],
        "already_have": list(data.already_have),
        "retail_choices": [
            {"product_id": product_id, "retail_product_id": retail_id}
            for product_id, retail_id in data.retail_choices
        ],
        "dismissed_issues": list(data.dismissed_issues),
    }


def load_input(params: Mapping[str, Any]) -> EngineInput:
    """`params` → `EngineInput`. Niezgodna wersja albo kształt = 409 z instrukcją."""
    try:
        if int(params["v"]) != PARAMS_VERSION:
            raise ShoppingParamsError(PARAMS_MESSAGE)
        return EngineInput(
            date_from=date.fromisoformat(str(params["date_from"])),
            date_to=date.fromisoformat(str(params["date_to"])),
            use_pantry=bool(params["use_pantry"]),
            rounds=tuple(
                RoundInput(
                    key=str(row["key"]),
                    name=str(row["name"]),
                    mode=RoundMode(row["mode"]),
                    covers_days=int(row["covers_days"]),
                    fresh_days=None if row["fresh_days"] is None else int(row["fresh_days"]),
                    shopping_weekday=(
                        None if row["shopping_weekday"] is None else int(row["shopping_weekday"])
                    ),
                )
                for row in params["rounds"]
            ),
            items=tuple(
                PlanItemInput(
                    item_id=int(row["item_id"]),
                    day=date.fromisoformat(str(row["day"])),
                    meal_name=str(row["meal_name"]),
                    servings=Decimal(str(row["servings"])),
                    recipe_id=None if row["recipe_id"] is None else int(row["recipe_id"]),
                    product_id=None if row["product_id"] is None else int(row["product_id"]),
                    amount=None if row["amount"] is None else Decimal(str(row["amount"])),
                    amount_unit=(
                        None if row["amount_unit"] is None else AmountUnit(row["amount_unit"])
                    ),
                )
                for row in params["items"]
            ),
            recipes=tuple(
                RecipeInput(
                    recipe_id=int(row["recipe_id"]),
                    name=str(row["name"]),
                    base_servings=int(row["base_servings"]),
                    ingredients=tuple(
                        IngredientInput(
                            product_id=int(ingredient["product_id"]),
                            amount=Decimal(str(ingredient["amount"])),
                            amount_unit=AmountUnit(ingredient["amount_unit"]),
                        )
                        for ingredient in row["ingredients"]
                    ),
                )
                for row in params["recipes"]
            ),
            products=tuple(
                ProductInput(
                    product_id=int(row["product_id"]),
                    name=str(row["name"]),
                    measure_kind=MeasureKind(row["measure_kind"]),
                    piece_weight_g=(
                        None
                        if row["piece_weight_g"] is None
                        else Decimal(str(row["piece_weight_g"]))
                    ),
                    category_id=None if row["category_id"] is None else int(row["category_id"]),
                    category_name=row["category_name"],
                    category_position=int(row["category_position"]),
                    perishability=(
                        None
                        if row["perishability"] is None
                        else Perishability(row["perishability"])
                    ),
                )
                for row in params["products"]
            ),
            pantry=tuple(
                PantryInput(
                    item_id=int(row["item_id"]),
                    amount=Decimal(str(row["amount"])),
                    amount_unit=AmountUnit(row["amount_unit"]),
                    product_id=None if row["product_id"] is None else int(row["product_id"]),
                    retail_product_id=(
                        None if row["retail_product_id"] is None else int(row["retail_product_id"])
                    ),
                )
                for row in params["pantry"]
            ),
            retail=tuple(
                RetailInput(
                    retail_product_id=int(row["retail_product_id"]),
                    product_id=int(row["product_id"]),
                    label=str(row["label"]),
                    package_amount=Decimal(str(row["package_amount"])),
                    package_unit=AmountUnit(row["package_unit"]),
                    store_id=None if row["store_id"] is None else int(row["store_id"]),
                    store_name=row["store_name"],
                    is_archived=bool(row["is_archived"]),
                )
                for row in params["retail"]
            ),
            already_have=tuple(int(value) for value in params["already_have"]),
            retail_choices=tuple(
                (int(row["product_id"]), int(row["retail_product_id"]))
                for row in params["retail_choices"]
            ),
            dismissed_issues=tuple(str(value) for value in params["dismissed_issues"]),
        )
    except ShoppingParamsError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise ShoppingParamsError(PARAMS_MESSAGE) from exc
