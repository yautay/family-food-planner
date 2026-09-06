"""Retencja backupów: 7 dziennych + 4 tygodniowe (09_DEPLOYMENT §3, BATCH_17).

Czysta logika wyboru zestawów do usunięcia + cienki CLI. Plik jest kopiowany
do obrazu backupu (`docker/backup/Dockerfile` → `/opt/backup/prune.py`) i wołany
przez `backup.sh` po każdym udanym backupie — dlatego używa WYŁĄCZNIE biblioteki
standardowej (obraz backupu to `postgres:17` + `python3`, bez `app`).

Zestaw backupu = wszystkie pliki o wspólnym stemplu w nazwie:
`pasnik-<YYYYmmddTHHMMSSZ>.dump`, `pasnik-<stempel>-uploads.tar.gz`,
opcjonalnie `pasnik-<stempel>.env` i `pasnik-<stempel>.sha256`.

Reguła (borg-podobna, dni i tygodnie w UTC):

- DZIENNE: zostają WSZYSTKIE zestawy z `keep_daily` najnowszych dni
  kalendarzowych, które mają jakikolwiek backup. „Wszystkie", nie „najnowszy
  z dnia": ręczny backup przed migracją (09 §4) nie może zostać skasowany przez
  nocny backup z tej samej doby.
- TYGODNIOWE: dodatkowo zostaje NAJNOWSZY zestaw z każdego z `keep_weekly`
  najnowszych tygodni ISO, które mają backup (także tych już pokrytych
  dziennymi — liczymy tygodnie, nie „tygodnie poza dziennymi").
- Reszta idzie do usunięcia. Operacja jest idempotentna: drugi przebieg na tym
  samym katalogu nie usuwa nic.

Prune NIGDY nie dotyka plików, które nie pasują do wzorca nazwy — obce pliki
w katalogu backupów zostają nietknięte i są wypisywane jako ostrzeżenie.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
SET_NAME_RE = re.compile(
    r"^pasnik-(?P<stamp>\d{8}T\d{6}Z)(?:-uploads\.tar\.gz|\.dump|\.env|\.sha256)$"
)

DEFAULT_KEEP_DAILY = 7
DEFAULT_KEEP_WEEKLY = 4


def parse_stamp(stamp: str) -> datetime:
    """Stempel z nazwy pliku → moment w UTC."""
    return datetime.strptime(stamp, STAMP_FORMAT).replace(tzinfo=UTC)


def format_stamp(moment: datetime) -> str:
    """Moment → stempel do nazwy pliku (UTC, bez separatorów problematycznych dla FS)."""
    return moment.astimezone(UTC).strftime(STAMP_FORMAT)


def select_to_delete(
    stamps: Iterable[datetime],
    *,
    keep_daily: int = DEFAULT_KEEP_DAILY,
    keep_weekly: int = DEFAULT_KEEP_WEEKLY,
) -> set[datetime]:
    """Czysta reguła retencji — które stemple zestawów usunąć."""
    ordered = sorted(set(stamps), reverse=True)
    keep: set[datetime] = set()

    days_seen: list[tuple[int, int, int]] = []
    for stamp in ordered:
        day = (stamp.year, stamp.month, stamp.day)
        if day not in days_seen:
            if len(days_seen) >= keep_daily:
                break
            days_seen.append(day)
        keep.add(stamp)

    weeks_seen: list[tuple[int, int]] = []
    for stamp in ordered:
        iso = stamp.isocalendar()
        week = (iso.year, iso.week)
        if week in weeks_seen:
            continue
        if len(weeks_seen) >= keep_weekly:
            break
        weeks_seen.append(week)
        keep.add(stamp)  # najnowszy w tygodniu — `ordered` jest malejąco

    return set(ordered) - keep


def group_sets(paths: Iterable[Path]) -> tuple[dict[datetime, list[Path]], list[Path]]:
    """Pliki katalogu → zestawy po stemplu oraz pliki spoza konwencji (nietykane)."""
    sets: dict[datetime, list[Path]] = {}
    foreign: list[Path] = []
    for path in paths:
        match = SET_NAME_RE.match(path.name)
        if not match:
            foreign.append(path)
            continue
        sets.setdefault(parse_stamp(match.group("stamp")), []).append(path)
    return sets, foreign


def prune(
    backup_dir: Path,
    *,
    keep_daily: int = DEFAULT_KEEP_DAILY,
    keep_weekly: int = DEFAULT_KEEP_WEEKLY,
    dry_run: bool = False,
) -> list[Path]:
    """Usuń (albo tylko wskaż) pliki zestawów poza retencją. Zwraca listę usuniętych."""
    files = [p for p in backup_dir.iterdir() if p.is_file()]
    sets, foreign = group_sets(files)
    doomed = select_to_delete(sets, keep_daily=keep_daily, keep_weekly=keep_weekly)
    removed: list[Path] = []
    for stamp in sorted(doomed):
        for path in sorted(sets[stamp]):
            if not dry_run:
                path.unlink(missing_ok=True)
            removed.append(path)
    for path in sorted(foreign):
        print(f"prune: pomijam plik spoza konwencji nazw: {path.name}", file=sys.stderr)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prune.py", description="Retencja backupów Paśnika (7 dziennych + 4 tygodniowe)"
    )
    parser.add_argument("--dir", required=True, type=Path, help="katalog z backupami")
    parser.add_argument("--keep-daily", type=int, default=DEFAULT_KEEP_DAILY)
    parser.add_argument("--keep-weekly", type=int, default=DEFAULT_KEEP_WEEKLY)
    parser.add_argument("--dry-run", action="store_true", help="tylko wypisz, nic nie usuwaj")
    args = parser.parse_args(argv)

    if not args.dir.is_dir():
        print(f"prune: katalog nie istnieje: {args.dir}", file=sys.stderr)
        return 1
    removed = prune(
        args.dir, keep_daily=args.keep_daily, keep_weekly=args.keep_weekly, dry_run=args.dry_run
    )
    verb = "do usunięcia" if args.dry_run else "usunięto"
    print(f"prune: {verb} {len(removed)} plików")
    for path in removed:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
