"""Weryfikacja wersji jadłospisu PRAWDZIWYM kodem aplikacji (D31 pkt 4, ADR-008).

Czyste funkcje bez I/O. Liczby z PDF-a, policzone na gramach z PDF-a, nie dowodzą
niczego o aplikacji — dlatego każdy składnik przechodzi tu dokładnie tę drogę,
którą przejdzie po imporcie:

    `normalize_amount` → `to_basis_amount` → `nutrition/engine.py`

a wejściem silnika jest wyłącznie `ProductNutrition` (ADR-004). Nic tu nie
przelicza jednostek ani nie liczy kcal po swojemu.

**Reguła jednostek** (`resolve_ingredient`, wnioski z ręcznej analizy `dieta.pdf`):

1. jednostka domowa, której `normalize_amount` NIE umie rozwiązać dla tego produktu
   (np. „Sztuka” przy produkcie spoza `PIECE`, albo brak przelicznika) → GRAMY;
   surowy zapis kończyłby się 422 przy pierwszej edycji składnika w UI;
2. jednostka rozwiązywalna, ale `ilość x przelicznik` odbiega od gramów z PDF-a
   ponad próg (domyślnie 10%) → GRAMY, a oryginał („2 x łyżka”) w `note`;
3. w pozostałych przypadkach zostaje jednostka z PDF-a.

Dla produktu VOLUME „gramy” to mililitry (gęstość 1 — przybliżenie zapisane
w powodzie): `normalize_amount` nie przeliczy g → ml.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.modules.catalog.models import VerificationStatus
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import (
    MASS_FACTORS,
    VOLUME_FACTORS,
    AmountUnit,
    MeasureKind,
    NormalizedAmount,
    ProductMeasure,
    UnitConversionError,
    UnitWeight,
    basis_unit,
    canonical_unit_label,
    normalize_amount,
    normalize_unit_label,
    to_basis_amount,
)
from app.modules.nutrition import engine
from app.modules.nutrition.types import NutritionValues, ProductNutrition
from scripts.pdf_extract.spec import (
    IngredientSpec,
    PdfTotals,
    ProductSpec,
    RecipeSpec,
    Spec,
    Thresholds,
)

Level = Literal["error", "warning", "info"]
Mode = Literal["direct", "pdf_unit", "grams"]

_QTY_QUANTUM = Decimal("0.001")
_HUNDRED = Decimal("100")
#: Tolerancja zgodności sumy gramów z PDF-a z listą zakupów PDF-a (g) — dane wpisane
#: ręcznie, więc liczymy z zapasem na zaokrąglenia listy (cynamon: 0,3 g).
_PDF_LIST_TOLERANCE_G = Decimal("0.5")
#: Energia: wartość kcal produktu ≈ 4B + 4W + 9T (karta B22, Security) w ±20% albo ±10 kcal.
_ENERGY_TOLERANCE_PCT = Decimal("20")
_ENERGY_TOLERANCE_KCAL = Decimal("10")

#: Pola porównywane z PDF-em: pole `PdfTotals` → pole `NutritionValues`.
COMPARED_FIELDS: tuple[tuple[str, str], ...] = (
    ("kcal", "kcal"),
    ("protein", "protein_g"),
    ("fat", "fat_g"),
    ("carbs", "carbs_g"),
    ("fiber", "fiber_g"),
    ("glycemic_load", "glycemic_load"),
)
_MACRO_FIELDS = ("protein", "fat", "carbs", "fiber")


class IngredientError(ValueError):
    """Składnika nie da się zapisać w żadnej jednostce (np. brak gramów w PDF-ie)."""


@dataclass(frozen=True)
class Issue:
    """Pojedyncze ustalenie weryfikacji."""

    level: Level
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class IngredientResolution:
    """Jak składnik zostanie ZAPISANY w bazie (`recipe_ingredients`) i dlaczego."""

    recipe: str
    product: str
    pdf_name: str | None
    display_qty: Decimal
    display_unit: str
    amount: Decimal
    amount_unit: AmountUnit
    note: str
    #: ilość na osi wartości produktu (g albo ml) — wejście silnika nutrition
    basis_amount: Decimal
    mode: Mode
    reason: str | None
    pdf_grams: Decimal | None
    #: gramy, jakie dałby zapis w jednostce z PDF-a przez `normalize_amount` (gdy się dało)
    home_basis: Decimal | None = None
    deviation_pct: Decimal | None = None


@dataclass(frozen=True)
class FieldCheck:
    """Jedno pole: policzone silnikiem vs PDF."""

    field: str
    computed: Decimal
    pdf: Decimal | None
    deviation_pct: Decimal | None


@dataclass(frozen=True)
class TotalsCheck:
    """Posiłek albo dzień: sumy policzone silnikiem (zaokrąglone na wyjściu) vs PDF."""

    label: str
    day: str
    computed: NutritionValues
    fields: tuple[FieldCheck, ...]
    severity: Level | None


@dataclass(frozen=True)
class ShoppingCheck:
    """Suma gramów produktu z przepisów vs lista zakupów z PDF-a."""

    product: str
    pdf_ingredient_grams: Decimal
    engine_grams: Decimal
    pdf_list_grams: Decimal | None
    #: odchyłka sumy z silnika od listy PDF-a (%), `None` gdy listy brak
    engine_deviation_pct: Decimal | None
    severity: Level | None


@dataclass(frozen=True)
class VerificationReport:
    """Wynik weryfikacji wersji — struktura czysta, render robi `report.py`."""

    ingredients: tuple[IngredientResolution, ...]
    meals: tuple[TotalsCheck, ...]
    days: tuple[TotalsCheck, ...]
    shopping: tuple[ShoppingCheck, ...]
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "warning")

    @property
    def ok(self) -> bool:
        """Czy nie ma błędów do rozstrzygnięcia (ostrzeżenia nie blokują paczki)."""
        return not self.errors


# --- adaptery spec → typy aplikacji ------------------------------------------------------


def product_measure(product: ProductSpec) -> ProductMeasure:
    """`ProductMeasure` produktu — wejście `catalog/units.py` (etykiety jak w bazie)."""
    return ProductMeasure(
        measure_kind=MeasureKind(product.measure_kind),
        piece_weight_g=product.piece_weight_g,
        unit_weights=tuple(
            UnitWeight(unit_label=normalize_unit_label(label), grams_per_unit=grams)
            for label, grams in sorted(product.unit_weights.items())
        ),
    )


def product_nutrition(product: ProductSpec, product_id: int) -> ProductNutrition:
    """`ProductNutrition` produktu — JEDYNE wejście silnika do wartości (ADR-004).

    Produkty z paczki są zawsze `unverified` (D31 pkt 7), więc silnik zgłosi
    `complete=False` z komunikatem „produkt niezweryfikowany" — to oczekiwane,
    a liczby sumują się normalnie.
    """
    measure_kind = MeasureKind(product.measure_kind)
    per = product.per_100
    return ProductNutrition(
        product_id=product_id,
        name=product.name,
        measure_kind=measure_kind,
        basis_unit=basis_unit(measure_kind),
        piece_weight_g=product.piece_weight_g,
        kcal_100=per.kcal,
        protein_100=per.protein,
        fat_100=per.fat,
        carbs_100=per.carbs,
        fiber_100=per.fiber,
        sugars_100=per.sugars,
        glycemic_index=product.glycemic_index,
        verification_status=VerificationStatus.UNVERIFIED,
        extras={},
    )


# --- reguła jednostek ---------------------------------------------------------------------


def _format_qty(value: Decimal) -> str:
    """Ilość do `note`: bez zer końcowych, z polskim przecinkiem („0,2”, „5”)."""
    return format(value.normalize(), "f").replace(".", ",")


def pdf_note(ingredient: IngredientSpec) -> str:
    """Oryginalny zapis z PDF-a: „2 x łyżka” (trafia do `note` przy zapisie w gramach)."""
    return f"{_format_qty(ingredient.pdf_qty)} x {ingredient.pdf_unit.strip().casefold()}"


def _format_pct(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _pct(delta: Decimal, base: Decimal) -> Decimal:
    # `+ 0` zamienia ujemne zero (-0.0 po kwantyzacji) na zwykłe 0.0 — raport nie ma pisać „-0%”.
    return (delta / base * _HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) + 0


def _build_resolution(
    *,
    recipe: str,
    ingredient: IngredientSpec,
    product: ProductSpec,
    measure: ProductMeasure,
    display_qty: Decimal,
    display_unit: str,
    mode: Mode,
    reason: str | None,
    note: str,
    home_basis: Decimal | None,
    deviation: Decimal | None,
) -> IngredientResolution:
    """Zbuduj wynik z JEDNEGO przejścia przez `normalize_amount` — to, co zapisze import.

    Ilość wyświetlana jest kwantowana do skali kolumny (`NUMERIC(8,3)`), a ilość
    znormalizowana liczona z TEJ kwantowanej ilości (`NUMERIC(10,3)`): UI, które
    po imporcie przeliczy `display_qty` → `amount`, dostanie to samo.
    """
    qty = display_qty.quantize(_QTY_QUANTUM, rounding=ROUND_HALF_UP)
    try:
        normalized = normalize_amount(qty, display_unit, measure)
        amount = normalized.amount.quantize(_QTY_QUANTUM, rounding=ROUND_HALF_UP)
        basis = to_basis_amount(NormalizedAmount(amount, normalized.unit), measure)
    except UnitConversionError as exc:  # pragma: no cover — chronione wcześniejszymi gałęziami
        raise IngredientError(
            f"Składnik „{product.name}” ({recipe}): zapis „{qty} {display_unit}” "
            f"nie przechodzi przez normalize_amount: {exc.message}"
        ) from exc
    if amount <= 0:
        raise IngredientError(
            f"Składnik „{product.name}” ({recipe}): ilość po normalizacji wynosi 0 "
            f"(„{qty} {display_unit}”) — baza odrzuci ją CHECK-iem."
        )
    return IngredientResolution(
        recipe=recipe,
        product=ingredient.product,
        pdf_name=ingredient.pdf_name,
        display_qty=qty,
        display_unit=display_unit,
        amount=amount,
        amount_unit=normalized.unit,
        note=note,
        basis_amount=basis,
        mode=mode,
        reason=reason,
        pdf_grams=ingredient.pdf_grams,
        home_basis=home_basis,
        deviation_pct=deviation,
    )


def resolve_ingredient(
    recipe: str, ingredient: IngredientSpec, product: ProductSpec, thresholds: Thresholds
) -> IngredientResolution:
    """Decyzja zapisu składnika (reguła jednostek D31 pkt 8) — JEDYNE miejsce, które ją podejmuje.

    Wołają ją i weryfikacja, i generator paczki, więc raport mówi dokładnie to,
    co trafi do bazy. `IngredientError`, gdy nie da się zapisać w żadnej jednostce.
    """
    measure = product_measure(product)
    is_volume = product.measure_kind == "volume"
    fallback_unit = "ml" if is_volume else "g"
    label = canonical_unit_label(ingredient.pdf_unit)
    pdf_grams = ingredient.pdf_grams

    def fallback(
        reason: str, *, home_basis: Decimal | None = None, deviation: Decimal | None = None
    ) -> IngredientResolution:
        if pdf_grams is None or pdf_grams <= 0:
            raise IngredientError(
                f"Składnik „{product.name}” ({recipe}): zapis „{pdf_note(ingredient)}” "
                f"wymaga gramów (powód: {reason}), a PDF ich nie podaje."
            )
        why = reason
        if is_volume:
            why += "; gramy z PDF-a zapisane jako ml (gęstość ≈ 1)"
        keep_original = label not in MASS_FACTORS and label not in VOLUME_FACTORS
        return _build_resolution(
            recipe=recipe,
            ingredient=ingredient,
            product=product,
            measure=measure,
            display_qty=pdf_grams,
            display_unit=fallback_unit,
            mode="grams",
            reason=why,
            note=pdf_note(ingredient) if keep_original else "",
            home_basis=home_basis,
            deviation=deviation,
        )

    if ingredient.write_as == "grams":
        return fallback("ręczny nakaz właściciela (write_as=grams)")

    direct = label in MASS_FACTORS or label in VOLUME_FACTORS
    try:
        normalized = normalize_amount(ingredient.pdf_qty, ingredient.pdf_unit, measure)
        home_basis = to_basis_amount(normalized, measure)
    except UnitConversionError:
        if direct:
            return fallback(f"jednostka „{label}” nie pasuje do osi produktu ({product.name})")
        return fallback(_unit_reason(label, product))

    deviation: Decimal | None = None
    if pdf_grams is not None and pdf_grams > 0:
        deviation = _pct(home_basis - pdf_grams, pdf_grams)
        if not direct and abs(deviation) > thresholds.unit_deviation_pct:
            return fallback(
                f"ilość x przelicznik daje {format(home_basis.normalize(), 'f')} g, "
                f"PDF podaje {format(pdf_grams.normalize(), 'f')} g "
                f"(odchyłka {deviation}% > {_format_pct(thresholds.unit_deviation_pct)}%)",
                home_basis=home_basis,
                deviation=deviation,
            )

    display_unit = ingredient.pdf_unit.strip() if direct else label
    return _build_resolution(
        recipe=recipe,
        ingredient=ingredient,
        product=product,
        measure=measure,
        display_qty=ingredient.pdf_qty,
        display_unit=display_unit,
        mode="direct" if direct else "pdf_unit",
        reason=None,
        note="",
        home_basis=home_basis,
        deviation=deviation,
    )


def _unit_reason(label: str, product: ProductSpec) -> str:
    """Powód zapisu w gramach dla jednostki domowej nierozwiązywalnej przez `normalize_amount`."""
    if label == "szt." and product.measure_kind != "piece":
        return f"„sztuka” wymaga produktu mierzonego w sztukach, a {product.name} liczymy w gramach"
    if label == "szt.":
        return "produkt nie ma wagi sztuki"
    return f"brak przelicznika jednostki „{label}” przy produkcie {product.name}"


# --- weryfikacja produktów -----------------------------------------------------------------


def check_product_values(product: ProductSpec) -> list[Issue]:
    """Walidacja zakresu wartości z internetu zanim trafią do paczki (karta B22, Security).

    Nieujemność i precyzję pilnuje schemat; tu dochodzi spójność energetyczna
    (kcal ≈ 4B + 4W + 9T) i niesprzeczność składników (cukry ≤ węglowodany).
    """
    per = product.per_100
    issues: list[Issue] = []
    # Wzór z karty: 4B + 4W + 9T. Wariant Atwatera liczy błonnik po 2 kcal/g zamiast 4
    # (przyprawy z dużą ilością błonnika, np. cynamon, inaczej wychodzą ponad 40% za wysoko).
    digestible = max(per.carbs - per.fiber, Decimal(0))
    candidates = (
        per.protein * 4 + per.carbs * 4 + per.fat * 9,
        per.protein * 4 + digestible * 4 + min(per.fiber, per.carbs) * 2 + per.fat * 9,
    )
    expected = min(candidates, key=lambda value: abs(per.kcal - value))
    delta = abs(per.kcal - expected)
    allowed = max(expected * _ENERGY_TOLERANCE_PCT / _HUNDRED, _ENERGY_TOLERANCE_KCAL)
    if delta > allowed:
        issues.append(
            Issue(
                "error",
                "nutrition_energy",
                product.name,
                f"kcal {per.kcal} nie zgadza się z 4B+4W+9T = {candidates[0].normalize():f} "
                f"(ani z wariantem z błonnikiem po 2 kcal/g = {candidates[1].normalize():f}); "
                f"dopuszczalne +-{_ENERGY_TOLERANCE_PCT}% albo +-{_ENERGY_TOLERANCE_KCAL} kcal.",
            )
        )
    if per.sugars > per.carbs:
        issues.append(
            Issue(
                "warning",
                "nutrition_sugars",
                product.name,
                f"cukry ({per.sugars}) przekraczają węglowodany ({per.carbs}).",
            )
        )
    if per.fiber > per.carbs:
        issues.append(
            Issue(
                "warning",
                "nutrition_fiber",
                product.name,
                f"błonnik ({per.fiber}) przekracza węglowodany ({per.carbs}).",
            )
        )
    return issues


# --- sumy i porównanie z PDF-em --------------------------------------------------------------


def _field_checks(computed: NutritionValues, pdf: PdfTotals) -> tuple[FieldCheck, ...]:
    checks: list[FieldCheck] = []
    for pdf_field, nutrition_field in COMPARED_FIELDS:
        value: Decimal = getattr(computed, nutrition_field)
        expected: Decimal | None = getattr(pdf, pdf_field)
        deviation = (
            _pct(value - expected, expected) if expected is not None and expected > 0 else None
        )
        checks.append(FieldCheck(pdf_field, value, expected, deviation))
    return tuple(checks)


def _meal_severity(checks: Sequence[FieldCheck], thresholds: Thresholds) -> Level | None:
    kcal = next(check for check in checks if check.field == "kcal")
    if kcal.deviation_pct is None:
        return None
    if abs(kcal.deviation_pct) > thresholds.meal_error_pct:
        return "error"
    if abs(kcal.deviation_pct) > thresholds.meal_warning_pct:
        return "warning"
    return None


def _day_findings(
    checks: Sequence[FieldCheck], thresholds: Thresholds
) -> list[tuple[Level, FieldCheck, Decimal]]:
    """Odchyłki dnia ponad progi: (poziom, pole, próg) — jedna definicja dla statusu i issues."""
    found: list[tuple[Level, FieldCheck, Decimal]] = []
    for check in checks:
        if check.deviation_pct is None:
            continue
        if check.field == "kcal":
            level: Level = "error"
            limit = thresholds.day_kcal_pct
        elif check.field in _MACRO_FIELDS:
            level = "warning"
            limit = thresholds.day_macro_pct
        else:
            continue
        if abs(check.deviation_pct) > limit:
            found.append((level, check, limit))
    return found


def _day_severity(findings: Sequence[tuple[Level, FieldCheck, Decimal]]) -> Level | None:
    levels = {level for level, _, _ in findings}
    return "error" if "error" in levels else ("warning" if levels else None)


_WORD = re.compile(r"[^\W\d_]+")


def _mention_stem(name: str) -> str | None:
    """Rdzeń nazwy produktu do szukania wzmianki w instrukcji (odmiana: obcięcie końcówki)."""
    for token in normalize_name(name).split():
        word = "".join(_WORD.findall(token))
        if len(word) >= 4:
            return word[: max(3, min(5, len(word) - 1))]
    return None


def mentioned_but_missing(
    recipe: RecipeSpec, catalog: Mapping[str, ProductSpec]
) -> list[ProductSpec]:
    """Produkty, o których mówi instrukcja, a których nie ma na liście składników (heurystyka)."""
    present = {ingredient.product for ingredient in recipe.ingredients}
    words = [word.casefold() for word in _WORD.findall(recipe.instructions)]
    found: list[ProductSpec] = []
    for key in sorted(catalog):
        if key in present:
            continue
        stem = _mention_stem(catalog[key].name)
        if stem is not None and any(word.startswith(stem) for word in words):
            found.append(catalog[key])
    return found


def verify_spec(
    spec: Spec,
    catalog: Mapping[str, ProductSpec],
    *,
    known_recipe_names: Mapping[str, str] | None = None,
    extra_issues: Sequence[Issue] = (),
) -> VerificationReport:
    """Zweryfikuj wersję: zapis składników, sumy posiłków/dni i lista zakupów.

    `catalog` = produkty dostępne dla wersji (własne + reużyte, klucz lokalny →
    definicja). `known_recipe_names` — przepisy z INNYCH wersji (nazwa → wersja):
    import reużywa przepis po nazwie, więc ten sam tytuł w kolejnej wersji
    zostałby po cichu pominięty razem ze składnikami (D22) — to błąd.
    """
    thresholds = spec.thresholds
    issues: list[Issue] = list(extra_issues)

    for product in spec.products:
        issues.extend(check_product_values(product))

    nutrition = {
        key: product_nutrition(product, position)
        for position, (key, product) in enumerate(sorted(catalog.items()), start=1)
    }

    resolutions: list[IngredientResolution] = []
    meal_values: dict[int, NutritionValues] = {}
    failed_recipes: set[int] = set()
    for position, recipe in enumerate(spec.recipes):
        recipe_resolutions: list[IngredientResolution] = []
        for ingredient in recipe.ingredients:
            try:
                resolution = resolve_ingredient(
                    recipe.name, ingredient, catalog[ingredient.product], thresholds
                )
            except IngredientError as exc:
                issues.append(Issue("error", "ingredient", recipe.name, str(exc)))
                failed_recipes.add(position)
                continue
            recipe_resolutions.append(resolution)
        resolutions.extend(recipe_resolutions)
        total = engine.recipe_nutrition(
            [
                engine.ingredient_nutrition(item.basis_amount, nutrition[item.product])
                for item in recipe_resolutions
            ]
        )
        meal_values[position] = engine.portion_nutrition(total, recipe.base_servings)

        if not recipe.instructions.strip():
            issues.append(
                Issue("warning", "empty_instructions", recipe.name, "Przepis ma pustą instrukcję.")
            )
        for product in mentioned_but_missing(recipe, catalog):
            issues.append(
                Issue(
                    "warning",
                    "mentioned_not_listed",
                    recipe.name,
                    f"Instrukcja wspomina „{product.name}”, a składnika nie ma na liście.",
                )
            )
        known = (known_recipe_names or {}).get(normalize_name(recipe.name))
        if known is not None:
            issues.append(
                Issue(
                    "error",
                    "recipe_name_taken",
                    recipe.name,
                    f"Przepis o tej nazwie jest już w wersji {known}: import reużyłby go "
                    "i pominął nowe składniki (D22). Zmień nazwę.",
                )
            )

    meals: list[TotalsCheck] = []
    for position, recipe in enumerate(spec.recipes):
        rounded = engine.round_for_output(meal_values[position])
        checks = _field_checks(rounded, recipe.pdf_totals)
        severity = None if position in failed_recipes else _meal_severity(checks, thresholds)
        meals.append(
            TotalsCheck(f"{recipe.meal}: {recipe.name}", recipe.day, rounded, checks, severity)
        )
        if severity is not None:
            kcal = next(check for check in checks if check.field == "kcal")
            issues.append(
                Issue(
                    severity,
                    "meal_kcal",
                    f"{recipe.day} / {recipe.meal} / {recipe.name}",
                    f"kcal {kcal.computed} vs PDF {kcal.pdf} (odchyłka {kcal.deviation_pct}%).",
                )
            )

    failed_days = {spec.recipes[position].day for position in failed_recipes}
    days: list[TotalsCheck] = []
    for day in dict.fromkeys(recipe.day for recipe in spec.recipes):
        day_total = engine.aggregate(
            [
                meal_values[position]
                for position, recipe in enumerate(spec.recipes)
                if recipe.day == day
            ]
        )
        rounded_day = engine.round_for_output(day_total)
        pdf_day = spec.pdf_day_totals.get(day, PdfTotals())
        day_checks = _field_checks(rounded_day, pdf_day)
        # Dzień z przepisem, którego składnika nie dało się zapisać, ma niepełne sumy:
        # porównanie z PDF-em dałoby fałszywe błędy przesłaniające prawdziwą przyczynę.
        findings = [] if failed_days & {day} else _day_findings(day_checks, thresholds)
        days.append(TotalsCheck(day, day, rounded_day, day_checks, _day_severity(findings)))
        if day not in spec.pdf_day_totals:
            issues.append(Issue("info", "day_without_totals", day, "PDF nie podaje sum dnia."))
        for level, check, limit in findings:
            issues.append(
                Issue(
                    level,
                    "day_total",
                    day,
                    f"{check.field} {check.computed} vs PDF {check.pdf} "
                    f"(odchyłka {check.deviation_pct}%, próg {limit}%).",
                )
            )

    shopping = _shopping_checks(spec, resolutions, issues)

    used = {ingredient.product for recipe in spec.recipes for ingredient in recipe.ingredients}
    for product in spec.products:
        if product.key not in used:
            issues.append(
                Issue(
                    "warning",
                    "unused_product",
                    product.name,
                    "Produkt zdefiniowany, ale żaden przepis go nie używa (nie wejdzie do paczki).",
                )
            )

    return VerificationReport(
        ingredients=tuple(resolutions),
        meals=tuple(meals),
        days=tuple(days),
        shopping=tuple(shopping),
        issues=tuple(issues),
    )


def _shopping_checks(
    spec: Spec, resolutions: Sequence[IngredientResolution], issues: list[Issue]
) -> list[ShoppingCheck]:
    """Σ gramów per produkt: z PDF-a składników, z silnika, i lista zakupów PDF-a."""
    pdf_sums: dict[str, Decimal] = {}
    engine_sums: dict[str, Decimal] = {}
    for item in resolutions:
        engine_sums[item.product] = engine_sums.get(item.product, Decimal(0)) + item.basis_amount
        pdf_sums[item.product] = pdf_sums.get(item.product, Decimal(0)) + (
            item.pdf_grams or Decimal(0)
        )

    checks: list[ShoppingCheck] = []
    for key in sorted(set(engine_sums) | set(spec.pdf_shopping_list_grams)):
        listed = spec.pdf_shopping_list_grams.get(key)
        engine_grams = engine_sums.get(key, Decimal(0))
        pdf_grams = pdf_sums.get(key, Decimal(0))
        deviation: Decimal | None = None
        severity: Level | None = None
        if listed is not None:
            if abs(pdf_grams - listed) > _PDF_LIST_TOLERANCE_G:
                severity = "error"
                issues.append(
                    Issue(
                        "error",
                        "shopping_pdf_sum",
                        key,
                        f"suma gramów składników z PDF-a ({pdf_grams.normalize():f}) różni się od "
                        f"listy zakupów PDF-a ({listed.normalize():f}) — brakujący składnik?",
                    )
                )
            if listed > 0:
                deviation = _pct(engine_grams - listed, listed)
                if abs(deviation) > spec.thresholds.shopping_pct:
                    severity = "error"
                    issues.append(
                        Issue(
                            "error",
                            "shopping_engine_sum",
                            key,
                            f"suma z silnika ({engine_grams.normalize():f}) vs lista zakupów PDF-a "
                            f"({listed.normalize():f}): odchyłka {deviation}% "
                            f"(próg {spec.thresholds.shopping_pct}%).",
                        )
                    )
        elif key in engine_sums:
            issues.append(
                Issue(
                    "warning",
                    "not_on_shopping_list",
                    key,
                    "Produkt użyty w przepisach, a nie ma go na liście zakupów PDF-a.",
                )
            )
        checks.append(ShoppingCheck(key, pdf_grams, engine_grams, listed, deviation, severity))
    return checks
