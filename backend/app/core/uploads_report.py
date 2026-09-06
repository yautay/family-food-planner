"""Raport plików uploadów bez referencji w bazie (BATCH_17, ustalenie REVIEW R4 pkt 4).

Katalog uploadów to JEDYNA oś, która rośnie bez ograniczenia (D10): zdjęcia
przepisów i wariantów oraz jadłospisy PDF zatwierdzonych importów zostają na
zawsze — i tak ma być (audyt pochodzenia przepisu). Ale plik traci właściciela,
gdy testy dziedziczą `UPLOADS_DIR` z `.env` (dług U26), gdy baza zostaje
zresetowana albo gdy nieudany import zostawi PDF bez wiersza. Ta komenda
WYŁĄCZNIE RAPORTUJE — nic nie kasuje (D10: nic nie usuwamy automatycznie);
decyzję podejmuje człowiek z runbookiem w ręku (B18).

Podział katalogu:

- `recipes/`, `retail/`, `transfer-import/` — zdjęcia; referencją jest
  `recipes.photo_path` / `retail_products.photo_path` (miniatura `_thumb`
  wynika z konwencji nazwy, więc liczy się razem z oryginałem);
- `import-pdf/` — jadłospisy; referencją jest `import_jobs.file_path`;
- `transfer/` — SCRATCH paczek eksportu/importu z TTL 24 h (kasuje je serwis
  transferu przy kolejnym dry-runie) — raportowany osobno, nigdy jako „osierocony".

Klasyfikacja jest czystą funkcją (`classify`), więc testuje się bez bazy;
`collect_references` to jedyne I/O bazodanowe, `scan_files` — jedyne dyskowe.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uploads import thumbnail_path_for
from app.modules.catalog.models import RetailProduct
from app.modules.importer.models import ImportJob
from app.modules.recipes.models import Recipe

#: Podkatalog tymczasowy (TTL w `transfer/service.py`), raportowany osobno.
SCRATCH_SUBDIR = "transfer"


@dataclass(frozen=True)
class FileEntry:
    """Plik w katalogu uploadów: ścieżka WZGLĘDNA (POSIX) i rozmiar."""

    path: str
    size: int


@dataclass
class UploadsReport:
    """Wynik klasyfikacji — liczby i listy gotowe do wydruku."""

    referenced: list[FileEntry] = field(default_factory=list)
    orphans: list[FileEntry] = field(default_factory=list)
    scratch: list[FileEntry] = field(default_factory=list)
    #: Ścieżki z bazy, których NIE MA na dysku — odwrotny problem (zdjęcie znika z karty).
    dead_references: list[str] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(e.size for e in (*self.referenced, *self.orphans, *self.scratch))

    @property
    def orphans_size(self) -> int:
        return sum(e.size for e in self.orphans)


def scan_files(uploads_root: Path) -> list[FileEntry]:
    """Wszystkie pliki pod katalogiem uploadów jako ścieżki względne POSIX."""
    if not uploads_root.is_dir():
        return []
    entries: list[FileEntry] = []
    for path in sorted(uploads_root.rglob("*")):
        if path.is_file():
            relative = PurePosixPath(path.relative_to(uploads_root).as_posix())
            entries.append(FileEntry(path=str(relative), size=path.stat().st_size))
    return entries


def expand_references(paths: Iterable[str | None]) -> set[str]:
    """Ścieżki z bazy → zbiór plików, których istnienia oczekujemy (zdjęcie + miniatura)."""
    expected: set[str] = set()
    for path in paths:
        if not path:
            continue
        expected.add(path)
        if path.lower().endswith(".jpg"):
            expected.add(thumbnail_path_for(path))
    return expected


async def collect_references(session: AsyncSession) -> set[str]:
    """Jedyne zapytania do bazy: kolumny ze ścieżkami plików w trzech tabelach."""
    recipe_paths = (await session.execute(select(Recipe.photo_path))).scalars().all()
    retail_paths = (await session.execute(select(RetailProduct.photo_path))).scalars().all()
    pdf_paths = (await session.execute(select(ImportJob.file_path))).scalars().all()
    return expand_references((*recipe_paths, *retail_paths, *pdf_paths))


def classify(files: Iterable[FileEntry], references: set[str]) -> UploadsReport:
    """Czysta klasyfikacja: plik jest referencjonowany, tymczasowy albo osierocony."""
    report = UploadsReport()
    seen: set[str] = set()
    for entry in files:
        seen.add(entry.path)
        first = PurePosixPath(entry.path).parts[0] if entry.path else ""
        if first == SCRATCH_SUBDIR:
            report.scratch.append(entry)
        elif entry.path in references:
            report.referenced.append(entry)
        else:
            report.orphans.append(entry)
    report.dead_references = sorted(references - seen)
    return report


def format_size(size: int) -> str:
    """Rozmiar po ludzku, z przecinkiem dziesiętnym (UI po polsku, D3)."""
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            text = f"{value:.1f}".replace(".", ",") if unit != "B" else str(size)
            return f"{text} {unit}"
        value /= 1024
    return f"{value:.1f}".replace(".", ",") + " GB"


def render_report(report: UploadsReport, *, uploads_root: Path) -> str:
    """Tekst raportu dla operatora — komenda drukuje go i kończy kodem 0."""
    lines = [
        f"Katalog uploadów: {uploads_root}",
        f"Razem: {len(report.referenced) + len(report.orphans) + len(report.scratch)} plików, "
        f"{format_size(report.total_size)}",
        f"  z referencją w bazie: {len(report.referenced)}",
        f"  tymczasowe ({SCRATCH_SUBDIR}/, TTL 24 h): {len(report.scratch)}",
        f"  BEZ REFERENCJI (osierocone): {len(report.orphans)}, {format_size(report.orphans_size)}",
    ]
    if report.orphans:
        lines.append("Pliki bez referencji (nic nie zostało usunięte — decyzja należy do Ciebie):")
        lines.extend(f"  {entry.path}  {format_size(entry.size)}" for entry in report.orphans)
    if report.dead_references:
        lines.append("Wiersze w bazie wskazujące plik, którego NIE MA na dysku:")
        lines.extend(f"  {path}" for path in report.dead_references)
    return "\n".join(lines)
