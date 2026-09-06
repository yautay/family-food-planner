"""Retencja backupów 7 dziennych + 4 tygodniowe (09_DEPLOYMENT §3, BATCH_17) — czysta reguła."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.backup_prune import (
    SET_NAME_RE,
    format_stamp,
    group_sets,
    parse_stamp,
    prune,
    select_to_delete,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 3, 0, tzinfo=UTC)  # sobota


def _daily(days: int) -> list[datetime]:
    """Nocne backupy 03:00 UTC z ostatnich `days` dni (włącznie z dzisiejszym)."""
    return [NOW - timedelta(days=i) for i in range(days)]


def test_dwa_tygodnie_codziennych_backupow_zostawia_7_dziennych_i_tygodniowe() -> None:
    """Po 14 dniach nocnych backupów: 7 najnowszych + najnowszy z każdego z 4 tygodni ISO."""
    stamps = _daily(14)

    doomed = select_to_delete(stamps, keep_daily=7, keep_weekly=4)
    kept = sorted(set(stamps) - doomed, reverse=True)

    assert kept[:7] == stamps[:7], "siedem najnowszych dni zostaje w całości"
    # 14 dni od soboty 5.09 wstecz sięga 23.08 (niedziela, tydzień 34): tygodnie
    # ISO 36 (31.08-5.09), 35 (24-30.08) i 34 (23.08) — trzy tygodnie, więc
    # tygodniowe dokładają najnowszy z tygodnia 35 (niedziela 30.08 — już w dziennych)
    # i z tygodnia 34 (23.08), a 24-29.08 idą do usunięcia.
    assert datetime(2026, 8, 23, 3, 0, tzinfo=UTC) not in doomed
    assert {d.day for d in doomed} == {24, 25, 26, 27, 28, 29}


def test_recznny_backup_z_tego_samego_dnia_nie_ginie() -> None:
    """Backup przed migracją (09 §4) o 10:00 i nocny o 03:00 tej samej doby — OBA zostają."""
    manual = NOW.replace(hour=10)
    stamps = [*_daily(9), manual]

    doomed = select_to_delete(stamps, keep_daily=7, keep_weekly=4)

    assert manual not in doomed
    assert NOW not in doomed


def test_dlugi_horyzont_zostawia_dokladnie_4_tygodnie() -> None:
    """Po 90 dniach nocnych backupów zostaje 7 dziennych + najwyżej 4 tygodniowe."""
    stamps = _daily(90)

    kept = set(stamps) - select_to_delete(stamps, keep_daily=7, keep_weekly=4)

    weeks = {(s.isocalendar().year, s.isocalendar().week) for s in kept}
    assert len(weeks) == 4
    assert len(kept) <= 7 + 4
    assert set(stamps[:7]) <= kept


def test_prune_jest_idempotentny() -> None:
    stamps = _daily(30)

    after_first = set(stamps) - select_to_delete(stamps, keep_daily=7, keep_weekly=4)

    assert select_to_delete(after_first, keep_daily=7, keep_weekly=4) == set()


def test_malo_backupow_nic_nie_usuwa() -> None:
    assert select_to_delete(_daily(3), keep_daily=7, keep_weekly=4) == set()


def test_stempel_jest_odwracalny_i_pasuje_do_nazw_zestawu() -> None:
    stamp = format_stamp(NOW)

    assert stamp == "20260905T030000Z"
    assert parse_stamp(stamp) == NOW
    for name in (f"pasnik-{stamp}.dump", f"pasnik-{stamp}-uploads.tar.gz", f"pasnik-{stamp}.env"):
        assert SET_NAME_RE.match(name)
    assert SET_NAME_RE.match("pasnik-20260905T030000Z.dump.tmp") is None


def test_prune_na_dysku_usuwa_cale_zestawy_i_nie_tyka_obcych_plikow(tmp_path: Path) -> None:
    """Zestaw = dump + tar (+ env); plik spoza konwencji (np. notatka) zostaje."""
    for stamp in _daily(10):
        (tmp_path / f"pasnik-{format_stamp(stamp)}.dump").write_bytes(b"d")
        (tmp_path / f"pasnik-{format_stamp(stamp)}-uploads.tar.gz").write_bytes(b"u")
    (tmp_path / "README-operator.txt").write_text("nie ruszać")

    removed = prune(tmp_path, keep_daily=7, keep_weekly=4)

    sets, foreign = group_sets(p for p in tmp_path.iterdir())
    assert [p.name for p in foreign] == ["README-operator.txt"]
    assert len(removed) % 2 == 0, "usuwamy komplet zestawu, nie pojedyncze pliki"
    assert all(len(files) == 2 for files in sets.values())
    assert prune(tmp_path, keep_daily=7, keep_weekly=4) == [], "idempotencja na dysku"


def test_dry_run_nic_nie_kasuje(tmp_path: Path) -> None:
    for stamp in _daily(12):
        (tmp_path / f"pasnik-{format_stamp(stamp)}.dump").write_bytes(b"d")

    planned = prune(tmp_path, keep_daily=7, keep_weekly=4, dry_run=True)

    assert planned
    assert all(p.exists() for p in planned)
