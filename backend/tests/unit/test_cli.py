"""CLI administracyjne (`task create-admin`) — spójność rejestru modeli.

CLI jest jedyną ścieżką, która dotyka bazy BEZ przechodzenia przez
`create_app()`. Aplikacja ładuje wszystkie moduły domenowe przy rejestracji
routerów, więc `Base.registry` jest tam kompletny „samo z siebie"; w CLI nie ma
tego efektu ubocznego i rejestr trzeba zaimportować jawnie (CLAUDE.md §4).

Bez tego importu relacja `User.household` — adnotowana STRINGIEM, bo moduł ma
`from __future__ import annotations` — nie ma czego rozwiązać i PIERWSZE
zapytanie o użytkownika kończy się `InvalidRequestError: expression 'Household'
failed to locate a name`. Objawiało się to dopiero w runtime, na produkcyjnej
ścieżce zakładania pierwszego administratora.

**Dlaczego OSOBNY PROCES, a nie zwykły import w teście**: `tests/conftest.py`
importuje `app.main`, co ładuje wszystkie moduły domenowe, więc w obrębie sesji
testowej rejestr jest kompletny NIEZALEŻNIE od zawartości `app/cli.py`. Test
robiący `import app.cli` w tym procesie przechodziłby także z błędem — czyli
byłby wart tyle, co jego brak. Dopiero świeży interpreter odtwarza warunki
`python -m app.cli`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: To samo, co robi pierwsze zapytanie CLI o użytkownika — bez bazy i bez zapisu.
_CHECK = (
    "import app.cli\n"
    "from sqlalchemy.orm import configure_mappers\n"
    "configure_mappers()\n"
    "print('OK')\n"
)


def test_import_cli_daje_kompletny_rejestr_modeli() -> None:
    """`python -m app.cli` musi mieć rozwiązywalne WSZYSTKIE relacje ORM."""
    result = subprocess.run(
        [sys.executable, "-c", _CHECK],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "Import `app.cli` nie daje kompletnego rejestru modeli — dodaj "
        "`from app.models import Base` do `app/cli.py`.\n"
        f"stderr:\n{result.stderr}"
    )
    assert "OK" in result.stdout


def test_cli_bez_podkomendy_konczy_sie_kodem_bledu() -> None:
    """Brak podkomendy = kod wyjścia, nie stacktrace (kontrakt CLI)."""
    from app.cli import main

    with pytest.raises(SystemExit):
        main([])
