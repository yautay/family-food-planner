"""Healthcheck (BATCH_17, 09_DEPLOYMENT §2) — czyste reguły checków, bez bazy i HTTP."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.health import (
    MIGRATIONS_DIR,
    HealthChecks,
    check_disk,
    compare_migrations,
    expected_head,
    overall_status,
)

pytestmark = pytest.mark.unit


def test_head_skryptow_to_najwyzszy_numer_migracji() -> None:
    """Head liczony ze skryptów (bez env.py i bez bazy) = ostatni plik w `migrations/versions/`."""
    numbers = sorted(
        m.group(1)
        for p in (MIGRATIONS_DIR / "versions").glob("*.py")
        if (m := re.match(r"^(\d{4})_", p.name))
    )

    assert expected_head() == numbers[-1]


@pytest.mark.parametrize(
    ("expected", "actual", "status"),
    [
        ("0015", "0015", "ok"),
        ("0015", "0014", "fail"),  # kontener wstał na starym schemacie
        ("0015", None, "fail"),  # czysta baza bez `alembic_version`
        ("", "0015", "fail"),  # obraz bez migracji — coś jest bardzo nie tak
    ],
)
def test_porownanie_migracji(expected: str, actual: str | None, status: str) -> None:
    assert compare_migrations(expected, actual) == status


def test_dysk_ok_przy_progu_zero_i_fail_przy_progu_nieosiagalnym(tmp_path: Path) -> None:
    """Próg z env: 0 MB zawsze przechodzi, petabajt zawsze pada — bez zależności od maszyny."""
    assert check_disk(tmp_path, min_free_mb=0) == "ok"
    assert check_disk(tmp_path, min_free_mb=10**9) == "fail"


def test_dysk_mierzony_na_najblizszym_istniejacym_przodku(tmp_path: Path) -> None:
    """Katalog uploadów może jeszcze nie istnieć (świeży bind mount) — to nie jest awaria."""
    assert check_disk(tmp_path / "jeszcze" / "nie" / "ma", min_free_mb=0) == "ok"


def test_status_zbiorczy_degraded_gdy_ktorykolwiek_check_nie_ok() -> None:
    assert overall_status(HealthChecks(db="ok", migrations="ok", disk="ok")) == "ok"
    assert overall_status(HealthChecks(db="ok", migrations="fail", disk="ok")) == "degraded"
    assert overall_status(HealthChecks(db="fail", migrations="skipped", disk="ok")) == "degraded"
    assert overall_status(HealthChecks(db="ok", migrations="ok", disk="fail")) == "degraded"


def test_odpowiedz_nie_ma_pol_poza_statusami() -> None:
    """Bez ścieżek, hostów, rewizji i bajtów — wyłącznie ok/fail/skipped (07_SECURITY)."""
    assert set(HealthChecks.model_fields) == {"db", "migrations", "disk"}
