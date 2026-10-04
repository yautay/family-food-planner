"""Cienka warstwa I/O narzędzia `/pdf-extract` (D31): czyta pliki, woła czyste funkcje, zapisuje.

Komendy (przez Taskfile — `task pdfx-*`):

- `index [SPEC]` — katalog znanych produktów albo zestawienie produktów SPEC z katalogiem
  (trafienia, aliasy, podobne = materiał BRAMKI 1);
- `verify SPEC [--report]` — weryfikacja silnikiem aplikacji; z `--report` zapisuje `report.md`
  (materiał BRAMKI 2); kod wyjścia 1 przy błędach do rozstrzygnięcia;
- `package SPEC` — `export.zip` obok spec (po udanej weryfikacji);
- `roundtrip ZIP` — dwukrotny import na bazie TESTOWEJ.

Ścieżki względne liczone są od KORZENIA REPO (Taskfile uruchamia komendy w `backend/`),
więc `data/diet-imports/0001-dieta-2000/spec.json` działa tak samo z każdego katalogu.
Narzędzie niczego nie wgrywa na produkcję i nie łączy się z żadną bazą poza testową (D31).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path

from app.modules.catalog.naming import normalize_name
from scripts.pdf_extract import roundtrip as roundtrip_module
from scripts.pdf_extract.catalog_index import (
    CatalogIndex,
    ResolvedCatalog,
    build_index,
    demo_names,
    load_instance_export,
    load_versions,
    resolve_catalog,
    similar_groups,
    version_label,
)
from scripts.pdf_extract.package import (
    PackageError,
    RecipeScopeChoice,
    build_archive,
    build_document,
    section_counts,
)
from scripts.pdf_extract.report import fmt, render_report
from scripts.pdf_extract.spec import SPEC_FILENAME, Spec, SpecError, load_spec
from scripts.pdf_extract.verify import Issue, VerificationReport, verify_spec

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO_ROOT / "data" / "diet-imports"
REPORT_FILENAME = "report.md"
ARCHIVE_FILENAME = "export.zip"


def resolve_path(raw: str) -> Path:
    """Ścieżka względna → od korzenia repo (nie od katalogu, w którym biegnie Taskfile)."""
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def _build_index(spec_path: Path | None, args: argparse.Namespace) -> tuple[CatalogIndex, Path]:
    root = resolve_path(args.root) if args.root else DEFAULT_ROOT
    exclude = version_label(spec_path) if spec_path is not None else None
    instance = (
        load_instance_export(resolve_path(args.instance_export)) if args.instance_export else []
    )
    index = build_index(load_versions(root, exclude=exclude), instance=instance, demo=demo_names())
    return index, root


def _analyze(
    spec_path: Path, args: argparse.Namespace
) -> tuple[Spec, CatalogIndex, ResolvedCatalog, VerificationReport]:
    spec = load_spec(spec_path)
    index, _ = _build_index(spec_path, args)
    resolved = resolve_catalog(spec, index)
    extra = [Issue("warning", "catalog", "katalog", text) for text in resolved.warnings]
    verification = verify_spec(
        spec, resolved.products, known_recipe_names=index.recipe_names, extra_issues=extra
    )
    return spec, index, resolved, verification


# --- komendy ---------------------------------------------------------------------------------


def cmd_index(args: argparse.Namespace) -> int:
    spec_path = resolve_path(args.spec) if args.spec else None
    index, root = _build_index(spec_path, args)

    if spec_path is None:
        print(f"Katalog z {len(index.versions)} wersji w {root} + seed demo:")
        for entry in sorted(index.entries.values(), key=lambda item: item.normalized):
            print(f"  [{entry.origin}] {entry.name} ({entry.measure_kind})")
        return 0

    spec = load_spec(spec_path)
    resolved = resolve_catalog(spec, index)
    print(
        f"Wersja {version_label(spec_path)}: {len(spec.products)} nowych, "
        f"{len(spec.reused)} reużytych."
    )
    print("\nNowe produkty vs katalog:")
    for match in resolved.matches:
        if match.kind == "similar":
            names = ", ".join(
                f"{c.entry.name} [{c.entry.origin}, {c.score:.2f}]" for c in match.candidates
            )
            print(f"  PODOBNE  {match.name} ~ {names}")
        else:
            print(f"  {match.kind.upper():8} {match.name}")
    for text in resolved.warnings:
        print(f"  UWAGA    {text}")
    groups = similar_groups([product.name for product in spec.products])
    if groups:
        print("\nPodobne WEWNĄTRZ tej wersji (kandydaci do scalenia — BRAMKA 1):")
        for group in groups:
            print("  - " + " | ".join(group))
    clashes = [
        (recipe.name, index.recipe_names[key])
        for recipe in spec.recipes
        if (key := normalize_name(recipe.name)) in index.recipe_names
    ]
    for name, label in clashes:
        print(f"  PRZEPIS „{name}” już istnieje w wersji {label}")
    return 0


def _print_issues(report: VerificationReport) -> None:
    for issue in report.issues:
        if issue.level != "info":
            print(f"  [{issue.level}] {issue.code}: {issue.subject}: {issue.message}")


def cmd_verify(args: argparse.Namespace) -> int:
    spec_path = resolve_path(args.spec)
    spec, _index, resolved, verification = _analyze(spec_path, args)
    grams = sum(1 for item in verification.ingredients if item.mode == "grams")
    print(f"Składników: {len(verification.ingredients)} (w gramach: {grams}).")
    for day in verification.days:
        kcal = next(check for check in day.fields if check.field == "kcal")
        print(
            f"  dzień {day.day}: kcal {fmt(kcal.computed)} / PDF {fmt(kcal.pdf)} "
            f"({fmt(kcal.deviation_pct)}%)"
        )
    _print_issues(verification)
    print(f"Błędy: {len(verification.errors)}, ostrzeżenia: {len(verification.warnings)}.")

    if args.report:
        scope = RecipeScopeChoice(args.recipe_scope)
        text = render_report(
            spec, resolved, verification, recipe_scope=scope, version_label=version_label(spec_path)
        )
        target = spec_path.parent / REPORT_FILENAME
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"Zapisano {target}")
    return 0 if verification.ok else 1


def cmd_package(args: argparse.Namespace) -> int:
    spec_path = resolve_path(args.spec)
    spec, _index, resolved, verification = _analyze(spec_path, args)
    if not verification.ok:
        _print_issues(verification)
        print("Weryfikacja ma błędy do rozstrzygnięcia — paczki nie budujemy.")
        return 1
    document = build_document(
        spec,
        resolved.products,
        recipe_scope=RecipeScopeChoice(args.recipe_scope),
        owner_email=args.owner_email,
    )
    _print_issues(verification)  # ostrzeżenia (np. konflikt z seedem demo) nie giną przy sukcesie
    payload = build_archive(document)
    target = resolve_path(args.out) if args.out else spec_path.parent / ARCHIVE_FILENAME
    target.write_bytes(payload)
    print(
        f"Zapisano {target} ({len(payload)} B, sha256 {hashlib.sha256(payload).hexdigest()[:16]}…)."
    )
    print("Zakres paczki:", document["scope"], "| sekcje:", section_counts(document))
    print("Paczkę WGRYWA WŁAŚCICIEL (`/admin/dane`) — agent niczego nie wgrywa na produkcję.")
    return 0


def cmd_roundtrip(args: argparse.Namespace) -> int:
    result = roundtrip_module.run(resolve_path(args.zip))
    print("Import 1: utworzono", result.first_created)
    print("          reużyto  ", result.first_reused)
    for warning in result.first_warnings:
        print("          uwaga:", warning)
    print("Import 2: utworzono", result.second_created)
    print("          reużyto  ", result.second_reused)
    for problem in result.problems:
        print("  PROBLEM:", problem)
    if result.ok:
        print("Roundtrip OK: drugi import nie dublował produktów ani przepisów.")
    return 0 if result.ok else 1


# --- parser -----------------------------------------------------------------------------------


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="katalog wersji (domyślnie data/diet-imports)")
    parser.add_argument(
        "--instance-export", help="eksport instancji ADMIN-a (produkty założone w UI)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_extract", description=__doc__.splitlines()[0] if __doc__ else ""
    )
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="katalog produktów / zestawienie wersji z katalogiem")
    index.add_argument(
        "spec", nargs="?", help=f"ścieżka do {SPEC_FILENAME} (bez niej: cały katalog)"
    )
    _common(index)
    index.set_defaults(handler=cmd_index)

    verify = sub.add_parser("verify", help="weryfikacja silnikiem aplikacji")
    verify.add_argument("spec")
    verify.add_argument("--report", action="store_true", help=f"zapisz {REPORT_FILENAME} obok spec")
    verify.add_argument(
        "--recipe-scope", choices=[s.value for s in RecipeScopeChoice], default="household"
    )
    _common(verify)
    verify.set_defaults(handler=cmd_verify)

    package = sub.add_parser("package", help=f"zbuduj {ARCHIVE_FILENAME} (paczka transferu v1)")
    package.add_argument("spec")
    package.add_argument(
        "--recipe-scope", choices=[s.value for s in RecipeScopeChoice], default="household"
    )
    package.add_argument(
        "--owner-email", help="e-mail ADMIN-a wczytującego (tylko z --recipe-scope global)"
    )
    package.add_argument("--out", help="ścieżka pliku wynikowego (domyślnie obok spec)")
    _common(package)
    package.set_defaults(handler=cmd_package)

    roundtrip = sub.add_parser("roundtrip", help="dwukrotny import paczki na bazie TESTOWEJ")
    roundtrip.add_argument("zip")
    roundtrip.set_defaults(handler=cmd_roundtrip)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Punkt wejścia `python -m scripts.pdf_extract`. Błędy kontraktu → komunikat, kod 2."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (SpecError, PackageError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2
