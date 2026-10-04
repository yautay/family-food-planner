"""Raport `report.md` — materiał BRAMKI 2 (akceptacja właściciela przed paczką).

Czysta funkcja: dostaje już policzone struktury (spec, katalog, wynik weryfikacji,
wyniki zestawienia z katalogiem) i zwraca tekst Markdown. Niczego nie liczy po swojemu
— liczby pochodzą z `verify.py` (czyli z silnika aplikacji) — i niczego nie czyta z dysku.

Raport NIE zawiera danych osobowych (D27): tylko to, co jest w `spec.json`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.modules.catalog.naming import normalize_name
from scripts.pdf_extract.catalog_index import Match, ResolvedCatalog
from scripts.pdf_extract.package import RecipeScopeChoice
from scripts.pdf_extract.spec import Spec
from scripts.pdf_extract.verify import (
    FieldCheck,
    IngredientResolution,
    TotalsCheck,
    VerificationReport,
)

_SEVERITY_MARK = {"error": "BŁĄD", "warning": "uwaga", "info": "info"}
_FIELD_LABELS = {
    "kcal": "kcal",
    "protein": "białko",
    "fat": "tłuszcz",
    "carbs": "węgl.",
    "fiber": "błonnik",
    "glycemic_load": "ŁG",
}


def fmt(value: Decimal | None) -> str:
    """Liczba po polsku: bez zer końcowych, z przecinkiem; `None` → „—”."""
    if value is None:
        return "—"
    return format(value.normalize(), "f").replace(".", ",")


def _signed(value: Decimal | None) -> str:
    if value is None:
        return ""
    prefix = "+" if value > 0 else ""
    return f"{prefix}{fmt(value)}%"


def _cell(check: FieldCheck) -> str:
    if check.pdf is None:
        return f"{fmt(check.computed)} / —"
    return f"{fmt(check.computed)} / {fmt(check.pdf)} ({_signed(check.deviation_pct)})"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    if not rows:
        return ["_brak_", ""]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows)
    lines.append("")
    return lines


def merge_impacts(
    spec: Spec, resolutions: Sequence[IngredientResolution]
) -> dict[str, dict[str, Decimal]]:
    """Skutek scaleń: produkt → {przepis → zmiana kcal posiłku „po - przed”}.

    Liczone tylko tam, gdzie spec zna wartości źródłowe scalonego produktu
    (`merged_from[].per_100`) i nazwę z PDF-a składnika (`pdf_name`). Zmiana to
    `gramy/100 x (kcal produktu wynikowego - kcal produktu źródłowego)`.
    """
    impacts: dict[str, dict[str, Decimal]] = {}
    for product in spec.products:
        sources = {
            normalize_name(item.name): item.per_100
            for item in product.merged_from
            if item.per_100 is not None
        }
        if not sources:
            continue
        for item in resolutions:
            if item.product != product.key or item.pdf_name is None:
                continue
            source = sources.get(normalize_name(item.pdf_name))
            if source is None:
                continue
            delta = item.basis_amount / Decimal(100) * (product.per_100.kcal - source.kcal)
            per_recipe = impacts.setdefault(product.key, {})
            per_recipe[item.recipe] = per_recipe.get(item.recipe, Decimal(0)) + delta
    return impacts


def render_report(
    spec: Spec,
    resolved: ResolvedCatalog,
    verification: VerificationReport,
    *,
    recipe_scope: RecipeScopeChoice = RecipeScopeChoice.HOUSEHOLD,
    version_label: str | None = None,
) -> str:
    """Złóż `report.md`. Kolejność sekcji = kolejność czytania przy akceptacji."""
    label = version_label or f"{spec.version}-{spec.slug}"
    lines: list[str] = [
        f"# Raport wersji {label}",
        "",
        f"Źródło: {spec.source}. Data analizy: {spec.analyzed_on.isoformat()}.",
        "",
        "> Raport powstał z `spec.json` i został policzony kodem aplikacji "
        "(`normalize_amount` → `to_basis_amount` → `nutrition/engine.py`). "
        "Nie zawiera danych osobowych.",
        "",
        "## Podsumowanie",
        "",
        f"- Przepisów: **{len(spec.recipes)}**, składników: **{len(verification.ingredients)}**.",
        f"- Produktów nowych: **{len(spec.products)}**, reużytych z katalogu: "
        f"**{len(spec.reused)}**.",
        f"- Błędy do rozstrzygnięcia: **{len(verification.errors)}**, "
        f"ostrzeżenia: **{len(verification.warnings)}**.",
        "- Wynik weryfikacji: **"
        + ("OK — można budować paczkę" if verification.ok else "BŁĘDY — paczki nie budujemy")
        + "**.",
        "",
    ]

    lines += ["## Decyzje właściciela", ""]
    lines += [f"- {text}" for text in spec.decisions] or ["_brak_"]
    lines.append("")

    lines += _products_section(spec, resolved, verification)
    lines += _units_section(verification)
    lines += _verification_section(spec, verification)
    lines += _sources_section(spec)
    lines += _issues_section(verification)
    lines += _upload_section(spec, recipe_scope)
    return "\n".join(lines).rstrip() + "\n"


def _products_section(
    spec: Spec, resolved: ResolvedCatalog, verification: VerificationReport
) -> list[str]:
    lines = ["## Produkty", "", "### Nowe", ""]
    matches: Mapping[str, Match] = {match.name: match for match in resolved.matches}
    rows = []
    for product in spec.products:
        match = matches.get(product.name)
        note = ""
        if match is not None and match.kind == "similar":
            names = ", ".join(candidate.entry.name for candidate in match.candidates[:3])
            note = f"podobne w katalogu: {names}"
        rows.append(
            [product.name, product.category, product.measure_kind, fmt(product.per_100.kcal), note]
        )
    lines += _table(["Produkt", "Kategoria", "Miara", "kcal/100", "Uwagi"], rows)

    lines += ["### Reużyte z katalogu", ""]
    lines += _table(
        ["Produkt", "Źródło definicji"],
        [[item.name, resolved.origins.get(item.key, "?")] for item in spec.reused],
    )

    lines += ["### Scalenia (decyzje właściciela) i ich skutek", ""]
    impacts = merge_impacts(spec, verification.ingredients)
    rows = []
    for product in spec.products:
        if not product.merged_from:
            continue
        names = ", ".join(item.name for item in product.merged_from)
        if product.key in impacts:
            effect = "; ".join(
                f"{recipe}: {'+' if delta > 0 else ''}{fmt(delta.quantize(Decimal('0.1')))} kcal"
                for recipe, delta in sorted(impacts[product.key].items())
            )
        else:
            effect = "brak wartości źródłowych w spec (wersja sprzed narzędzia) — skutek nieznany"
        rows.append([product.name, names, effect])
    lines += _table(
        ["Produkt wynikowy", "Scalone nazwy z PDF-a", "Skutek kcal posiłku (po - przed)"], rows
    )
    return lines


def _units_section(verification: VerificationReport) -> list[str]:
    lines = ["## Jednostki składników", ""]
    grams = [item for item in verification.ingredients if item.mode == "grams"]
    lines += [
        f"Zapisane w jednostce z PDF-a: **{len(verification.ingredients) - len(grams)}**, "
        f"zapisane jako gramy (albo ml): **{len(grams)}**.",
        "",
        "### Składniki zapisane jako gramy i dlaczego",
        "",
    ]
    lines += _table(
        ["Przepis", "Produkt", "W PDF-ie", "Zapis", "Powód"],
        [
            [
                item.recipe,
                item.product,
                item.note or f"{fmt(item.pdf_grams)} g",
                f"{fmt(item.display_qty)} {item.display_unit}",
                item.reason or "",
            ]
            for item in grams
        ],
    )

    lines += ["### Odstępstwa wag względem PDF-a (przelicznik vs gramy z PDF-a)", ""]
    rows = []
    for item in verification.ingredients:
        if item.deviation_pct is None or item.mode == "direct" or abs(item.deviation_pct) < 1:
            continue
        rows.append(
            [
                item.recipe,
                item.product,
                f"{fmt(item.display_qty)} {item.display_unit}"
                if item.mode == "pdf_unit"
                else item.note,
                f"{fmt(item.home_basis)} g",
                f"{fmt(item.pdf_grams)} g",
                _signed(item.deviation_pct),
                "gramy" if item.mode == "grams" else "jednostka z PDF-a",
            ]
        )
    lines += _table(
        ["Przepis", "Produkt", "Ilość", "Przelicznik", "PDF", "Odchyłka", "Zapis"], rows
    )
    return lines


def _totals_table(title: str, checks: Sequence[TotalsCheck]) -> list[str]:
    fields = list(_FIELD_LABELS)
    header = ["Pozycja", *(f"{_FIELD_LABELS[name]} (silnik / PDF)" for name in fields), "Status"]
    rows = []
    for item in checks:
        by_field = {check.field: check for check in item.fields}
        rows.append(
            [
                f"{item.day}: {item.label}" if item.label != item.day else item.day,
                *(_cell(by_field[name]) for name in fields),
                _SEVERITY_MARK.get(item.severity or "", "ok"),
            ]
        )
    return [f"### {title}", "", *_table(header, rows)]


def _verification_section(spec: Spec, verification: VerificationReport) -> list[str]:
    lines = ["## Weryfikacja obliczeń silnikiem aplikacji", ""]
    thresholds = spec.thresholds
    lines += [
        f"Progi: posiłek kcal > {fmt(thresholds.meal_warning_pct)}% = uwaga, "
        f"> {fmt(thresholds.meal_error_pct)}% = błąd; dzień kcal > {fmt(thresholds.day_kcal_pct)}% "
        f"= błąd, makro > {fmt(thresholds.day_macro_pct)}% = uwaga; "
        f"lista zakupów ±{fmt(thresholds.shopping_pct)}%. ŁG jest informacyjny (IG z tabel "
        "jest zbyt niepewny).",
        "",
    ]
    lines += _totals_table("Posiłki", verification.meals)
    lines += _totals_table("Dni", verification.days)
    lines += ["### Lista zakupów: suma gramów produktu", ""]
    lines += _table(
        [
            "Produkt",
            "Σ składników z PDF-a",
            "Σ silnik",
            "Lista PDF-a",
            "Odchyłka silnik↔lista",
            "Status",
        ],
        [
            [
                item.product,
                fmt(item.pdf_ingredient_grams),
                fmt(item.engine_grams),
                fmt(item.pdf_list_grams),
                _signed(item.engine_deviation_pct),
                _SEVERITY_MARK.get(item.severity or "", "ok"),
            ]
            for item in verification.shopping
        ],
    )
    return lines


def _sources_section(spec: Spec) -> list[str]:
    lines = ["## Źródła wartości odżywczych", ""]
    lines.append(
        "Wszystkie produkty z paczki wchodzą jako `unverified` - ADMIN weryfikuje je "
        "w `/admin/weryfikacja` (D11, D31)."
    )
    lines.append("")
    groups: dict[tuple[str, str], list[str]] = {}
    for product in spec.products:
        spread = (
            "; ".join(
                f"{_FIELD_LABELS.get(item.field, item.field)} {fmt(item.low)}-{fmt(item.high)}"
                + (f" ({', '.join(item.sources)})" if item.sources else "")
                for item in product.nutrition_range
            )
            or "brak zapisanego rozrzutu"
        )
        groups.setdefault((product.nutrition_source, spread), []).append(product.name)
    rows = [[source, spread, ", ".join(names)] for (source, spread), names in groups.items()]
    lines += _table(["Źródło", "Zakres źródeł", "Produkty"], rows)
    return lines


def _issues_section(verification: VerificationReport) -> list[str]:
    lines = ["## Ostrzeżenia i błędy", ""]
    rows = [
        [_SEVERITY_MARK[issue.level], issue.code, issue.subject, issue.message]
        for issue in verification.issues
    ]
    lines += _table(["Poziom", "Kod", "Dotyczy", "Opis"], rows)
    return lines


def _upload_section(spec: Spec, recipe_scope: RecipeScopeChoice) -> list[str]:
    lines = ["## Wgrywanie paczki (robi właściciel, nie agent)", ""]
    if recipe_scope is RecipeScopeChoice.GLOBAL:
        lines += [
            "Paczka ma zakres `instance` i przepisy z zakresem „Wszyscy” (D32/D33). "
            "Wgrywa ją **wyłącznie ADMIN**, w `/admin/dane` w sekcji „Instancja”, "
            "z konta, którego e-mail podano w `--owner-email`. W podglądzie DRY-RUN sprawdź, "
            "że `users` NIE ma w „Nowe” — jeśli jest, e-mail nie pasuje do istniejącego konta: "
            "przerwij.",
        ]
    else:
        lines += [
            f"Paczka ma zakres `user`; przepisy wejdą jako `{recipe_scope.value}` konta "
            "wczytującego. "
            "Wgrywa się ją w Ustawieniach („Kopia danych rodziny”) albo w `/admin/dane`.",
        ]
    lines += [
        "",
        "Produkty trafiają jako `unverified`; powtórne wczytanie tej samej paczki niczego nie "
        "dubluje (produkty po nazwie, przepisy po nazwie — D22).",
        "",
    ]
    return lines
