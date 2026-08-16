"""Łańcuch migracji — struktura, bez łączenia się z bazą.

Dwie głowy po merge'u gałęzi psują wszystko po cichu (03_AI_SKILLS §9), więc
warunek „dokładnie jedna głowa" jest testem, nie dobrą praktyką.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(config)


def test_dokladnie_jedna_glowa_migracji() -> None:
    heads = _script_directory().get_heads()

    assert len(heads) == 1, f"Oczekiwano jednej głowy migracji, są: {heads}"


def test_lancuch_rewizji_jest_spojny() -> None:
    """Każda rewizja da się przejść od bazy do głowy (brak sierot)."""
    script = _script_directory()
    head = script.get_heads()[0]

    revisions = list(script.walk_revisions("base", head))

    assert revisions, "Brak jakiejkolwiek migracji"
    assert revisions[-1].down_revision is None, "Najstarsza rewizja musi mieć down_revision=None"


def test_kazda_migracja_ma_downgrade() -> None:
    """Bez działającego downgrade nie ma bezpiecznego rollbacku (03_DATABASE §1)."""
    for path in sorted((BACKEND_DIR / "migrations" / "versions").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "def downgrade()" in source, f"{path.name}: brak funkcji downgrade()"
