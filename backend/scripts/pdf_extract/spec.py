"""Schemat `spec.json` — jedyne źródło prawdy wersji jadłospisu (D31, BATCH_22).

`spec.json` opisuje wyłącznie FAKTY wyciągnięte z PDF-a i decyzje właściciela:
produkty, przepisy, składniki z ilością „jak w PDF-ie", sumy z PDF-a i listę zakupów.
Wszystko, co z nich wynika (jednostka zapisu składnika, sumy policzone silnikiem,
paczka transferu, raport), jest POCHODNE i liczy je kod — spec nie zawiera wyników.

Zasady (ADR-008, D27):

- liczby są stringami dziesiętnymi, nigdy `float` — walidator odrzuca `float`
  także w danych wczytanych z Pythona, a JSON czytamy z `parse_float=Decimal`
  (dokładna wartość z pliku, bez pośredniego `float`);
- precyzja wartości odżywczych i wag mieści się w kolumnach bazy
  (`NUMERIC(7,2)` itd.) — wartość z większą liczbą miejsc jest błędem schematu,
  a nie cicho zaokrąglana przy imporcie, bo wtedy liczby z raportu nie zgadzałyby
  się z bazą;
- `extra="forbid"` na każdym modelu i BRAK pól na dane osobowe (imię, nazwisko,
  kontakt): test `test_pdf_extract_spec.py` pilnuje, że nikt ich tu nie dołoży.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationError,
    model_validator,
)

from app.modules.catalog.naming import normalize_name

SPEC_FILENAME = "spec.json"

MealKind = Literal["śniadanie", "obiad", "podwieczorek", "kolacja"]
MeasureKindName = Literal["mass", "volume", "piece"]


class SpecError(ValueError):
    """Spec nie spełnia kontraktu (komunikat po polsku, bez stacktrace'u)."""


def _strict_decimal(value: Any) -> Decimal:
    """String/int/Decimal → Decimal. `float` i `bool` to błąd (ADR-008)."""
    if isinstance(value, bool | float):
        raise ValueError("liczby zapisuj jako stringi dziesiętne, nie float (ADR-008)")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip().replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError(f"„{value}” nie jest liczbą dziesiętną") from exc
    else:
        raise ValueError("oczekiwano stringa dziesiętnego")
    if not result.is_finite():
        raise ValueError("liczba musi być skończona")
    return result


def _non_negative(value: Decimal) -> Decimal:
    if value < 0:
        raise ValueError("wartość nie może być ujemna")
    return value


def _positive(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError("wartość musi być większa od zera")
    return value


def _fits(*, digits: int, places: int) -> Any:
    """Walidator mieszczenia się w `NUMERIC(digits, places)` — bez cichego zaokrąglania."""

    def check(value: Decimal) -> Decimal:
        _, digits_tuple, exponent = value.normalize().as_tuple()
        exp = int(exponent)  # liczba skończona (odfiltrowane przez `_strict_decimal`)
        # Zera końcowe nie są cyframi znaczącymi: "40.00" mieści się w NUMERIC(7,2).
        if max(-exp, 0) > places:
            raise ValueError(f"co najwyżej {places} miejsc po przecinku (kolumna NUMERIC)")
        integer_digits = max(len(digits_tuple) + exp, 0) if value != 0 else 0
        if integer_digits > digits - places:
            raise ValueError(f"co najwyżej {digits - places} cyfr przed przecinkiem")
        return value

    return AfterValidator(check)


def _serialize(value: Decimal) -> str:
    return format(value, "f")


_DECIMAL_BASE = (BeforeValidator(_strict_decimal), PlainSerializer(_serialize, return_type=str))

#: Dowolna nieujemna liczba dziesiętna (sumy i ilości z PDF-a).
Dec = Annotated[Decimal, *_DECIMAL_BASE, AfterValidator(_non_negative)]
#: Dodatnia liczba dziesiętna (ilość składnika w PDF-ie).
PositiveDec = Annotated[Decimal, *_DECIMAL_BASE, AfterValidator(_positive)]
#: kcal na 100 g — `NUMERIC(7,2)`.
Kcal100 = Annotated[
    Decimal, *_DECIMAL_BASE, AfterValidator(_non_negative), _fits(digits=7, places=2)
]
#: białko/tłuszcz/węglowodany/błonnik/cukry na 100 g — `NUMERIC(6,2)`.
Macro100 = Annotated[
    Decimal, *_DECIMAL_BASE, AfterValidator(_non_negative), _fits(digits=6, places=2)
]
#: indeks glikemiczny — `NUMERIC(5,1)`, CHECK 0..110.
GlycemicIndex = Annotated[
    Decimal, *_DECIMAL_BASE, AfterValidator(_non_negative), _fits(digits=5, places=1)
]
#: waga sztuki i gramy na jednostkę domową — `NUMERIC(8,2)`.
WeightG = Annotated[Decimal, *_DECIMAL_BASE, AfterValidator(_positive), _fits(digits=8, places=2)]


class _Strict(BaseModel):
    """Baza: żadnych dodatkowych pól (`extra="forbid"`) — kontrakt jest zamknięty."""

    model_config = ConfigDict(extra="forbid")


class Per100(_Strict):
    """Wartości odżywcze na 100 g (VOLUME: na 100 ml) — jak kolumny `*_100` produktu."""

    basis: Literal["g", "ml"]
    kcal: Kcal100
    protein: Macro100
    fat: Macro100
    carbs: Macro100
    fiber: Macro100
    sugars: Macro100


class MergedFrom(_Strict):
    """Produkt z PDF-a scalony w ten (decyzja właściciela, BRAMKA 1).

    `per_100` jest opcjonalne: gdy jest, raport liczy skutek scalenia (różnica
    kcal posiłku przed/po) dla składników z `pdf_name` równym `name`. Wersje
    sprzed narzędzia (0001) go nie mają i raport mówi o tym wprost.
    """

    name: str = Field(min_length=1, max_length=200)
    per_100: Per100 | None = None


class SourceRange(_Strict):
    """Rozrzut jednej wartości w źródłach internetowych (D31 pkt 7)."""

    field: Literal["kcal", "protein", "fat", "carbs", "fiber", "sugars"]
    low: Dec
    high: Dec
    sources: list[str] = Field(default_factory=list, max_length=10)


class ProductSpec(_Strict):
    """Produkt DEFINIOWANY przez tę wersję (nowy w katalogu)."""

    key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    measure_kind: MeasureKindName
    piece_weight_g: WeightG | None = None
    per_100: Per100
    glycemic_index: GlycemicIndex | None = None
    #: etykieta jednostki domowej → gramy (dla VOLUME: mililitry) na jednostkę
    unit_weights: dict[str, WeightG] = Field(default_factory=dict)
    merged_from: list[MergedFrom] = Field(default_factory=list)
    nutrition_source: str = Field(min_length=1, max_length=500)
    nutrition_range: list[SourceRange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> ProductSpec:
        if (self.measure_kind == "volume") != (self.per_100.basis == "ml"):
            raise ValueError("`basis` musi być `ml` dla produktu VOLUME i `g` dla pozostałych")
        if (self.measure_kind == "piece") != (self.piece_weight_g is not None):
            raise ValueError("`piece_weight_g` jest wymagane dokładnie dla produktu PIECE")
        if self.glycemic_index is not None and self.glycemic_index > 110:
            raise ValueError("indeks glikemiczny mieści się w 0..110")
        return self


class ReusedProduct(_Strict):
    """Produkt, który JUŻ jest w katalogu (wcześniejsza wersja albo eksport instancji)."""

    key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=200)


class PdfTotals(_Strict):
    """Sumy z PDF-a (posiłku albo dnia). Brak wartości = PDF jej nie podaje."""

    kcal: Dec | None = None
    protein: Dec | None = None
    fat: Dec | None = None
    carbs: Dec | None = None
    fiber: Dec | None = None
    glycemic_load: Dec | None = None


class IngredientSpec(_Strict):
    """Składnik „jak w PDF-ie" + opcjonalny ręczny nakaz zapisu w gramach.

    Decyzja zapisu (jednostka domowa czy gramy) NIE jest polem spec: liczy ją
    `verify.resolve_ingredient` z reguł D31 pkt 8; `write_as="grams"` to wyłącznie
    ręczne wymuszenie przez właściciela.
    """

    product: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    #: nazwa produktu dokładnie jak w PDF-ie (przed scaleniem) — potrzebna raportowi scaleń
    pdf_name: str | None = Field(default=None, max_length=200)
    pdf_qty: PositiveDec
    pdf_unit: str = Field(min_length=1, max_length=50)
    pdf_grams: Dec | None = None
    write_as: Literal["auto", "grams"] = "auto"


class RecipeSpec(_Strict):
    """Przepis = jeden posiłek jadłospisu."""

    day: str = Field(min_length=1, max_length=20)
    meal: MealKind
    name: str = Field(min_length=1, max_length=200)
    base_servings: int = Field(default=1, ge=1, le=100)
    instructions: str = ""
    comment: str = ""
    pdf_totals: PdfTotals = Field(default_factory=PdfTotals)
    ingredients: list[IngredientSpec] = Field(min_length=1)


class Thresholds(_Strict):
    """Progi weryfikacji w % (D31, karta B22 — wartości domyślne konfigurowalne w spec)."""

    #: odchyłka `ilość x przelicznik` od gramów z PDF-a, po której zapisujemy gramy
    unit_deviation_pct: Dec = Decimal("10")
    #: posiłek: odchyłka kcal powyżej = ostrzeżenie, powyżej `meal_error_pct` = błąd
    meal_warning_pct: Dec = Decimal("10")
    meal_error_pct: Dec = Decimal("15")
    #: dzień: kcal powyżej = błąd, makro powyżej `day_macro_pct` = ostrzeżenie
    day_kcal_pct: Dec = Decimal("5")
    day_macro_pct: Dec = Decimal("10")
    #: suma gramów produktu z przepisów vs lista zakupów z PDF-a
    shopping_pct: Dec = Decimal("5")

    @model_validator(mode="after")
    def _ordered(self) -> Thresholds:
        if self.meal_warning_pct > self.meal_error_pct:
            raise ValueError("`meal_warning_pct` nie może być większe niż `meal_error_pct`")
        return self


class Spec(_Strict):
    """Wersja jadłospisu: `data/diet-imports/NNNN-slug/spec.json`."""

    version: str = Field(pattern=r"^\d{4}$")
    slug: str = Field(pattern=r"^[a-z0-9-]{1,60}$")
    #: data analizy — wchodzi do paczki jako `exported_at` (ta sama spec = te same bajty)
    analyzed_on: date
    #: opis pochodzenia BEZ danych osobowych (D27)
    source: str = Field(min_length=1, max_length=500)
    decisions: list[str] = Field(default_factory=list)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    products: list[ProductSpec] = Field(default_factory=list)
    reused: list[ReusedProduct] = Field(default_factory=list)
    recipes: list[RecipeSpec] = Field(min_length=1)
    pdf_day_totals: dict[str, PdfTotals] = Field(default_factory=dict)
    #: gramy produktów z listy zakupów PDF-a, po kluczu produktu
    pdf_shopping_list_grams: dict[str, Dec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _references(self) -> Spec:
        keys = [product.key for product in self.products] + [item.key for item in self.reused]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"klucze produktów muszą być unikalne: {', '.join(duplicates)}")
        names = [normalize_name(product.name) for product in self.products]
        names += [normalize_name(item.name) for item in self.reused]
        if len(set(names)) != len(names):
            raise ValueError("nazwy produktów (po normalizacji) muszą być unikalne w jednej wersji")

        known = set(keys)
        for recipe in self.recipes:
            for ingredient in recipe.ingredients:
                if ingredient.product not in known:
                    raise ValueError(
                        f"przepis „{recipe.name}”: składnik wskazuje nieznany produkt "
                        f"„{ingredient.product}” (dodaj go do `products` albo `reused`)"
                    )
        recipe_names = [normalize_name(recipe.name) for recipe in self.recipes]
        if len(set(recipe_names)) != len(recipe_names):
            raise ValueError("nazwy przepisów (po normalizacji) muszą być unikalne w jednej wersji")

        unknown = sorted(set(self.pdf_shopping_list_grams) - known)
        if unknown:
            raise ValueError(f"lista zakupów wskazuje nieznane produkty: {', '.join(unknown)}")
        days = {recipe.day for recipe in self.recipes}
        orphan_days = sorted(set(self.pdf_day_totals) - days)
        if orphan_days:
            raise ValueError(f"sumy dnia dla dni bez przepisów: {', '.join(orphan_days)}")
        return self


def parse_spec(payload: Any) -> Spec:
    """Zwalidowany `Spec` z obiektu JSON-a; błąd schematu → `SpecError` po polsku."""
    try:
        return Spec.model_validate(payload)
    except ValidationError as exc:
        lines = []
        for error in exc.errors():
            where = ".".join(str(part) for part in error["loc"])
            lines.append(f"  {where}: {error['msg']}")
        raise SpecError("spec.json niezgodny ze schematem:\n" + "\n".join(lines)) from exc


def load_spec(path: Path) -> Spec:
    """Wczytaj `spec.json`. JSON czytamy z `parse_float=Decimal` (bez pośredniego float)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"Nie da się odczytać {path}: {exc.strerror}") from exc
    try:
        payload = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise SpecError(f"{path}: niepoprawny JSON ({exc.msg}, linia {exc.lineno})") from exc
    return parse_spec(payload)


def dump_spec(spec: Spec) -> str:
    """Kanoniczny zapis spec (ten sam obiekt = te same bajty; liczby jako stringi)."""
    payload = spec.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
