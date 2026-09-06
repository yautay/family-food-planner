"""Bramka świeżości kontraktu API (dług U12, BATCH_17) — `task fe-types-check`.

Pyta o jedno: czy `backend/openapi.json` i `frontend/src/api/generated.ts`
w repozytorium odpowiadają DZISIEJSZEMU kodowi. Robi to, generując oba pliki
do katalogu tymczasowego i porównując bajt w bajt — **bez gita**.

Dlaczego nie `task fe-types && git diff --exit-code`: `task check` jest bramką
DoD uruchamianą PRZED commitem, więc drzewo jest z definicji brudne. Porównanie
z HEAD pada wtedy w każdym batchu, który zmienia API — czyli dokładnie tam,
gdzie bramka ma być użyteczna, zamieniłaby się w rytuał „przegeneruj i zignoruj".

Użycie: `task fe-types-check` (albo `uv run python -m scripts.check_api_contract`).
Kod wyjścia 1 + komunikat po polsku, gdy któryś plik jest nieaktualny.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.core.config import ConfigurationError, Settings, load_settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
OPENAPI_FILE = BACKEND_DIR / "openapi.json"
GENERATED_TS = FRONTEND_DIR / "src" / "api" / "generated.ts"

STALE_MESSAGE = (
    "Kontrakt API jest nieaktualny: {files} nie odpowiada(ją) kodowi.\n"
    "Uruchom `task fe-types` i dołącz oba pliki do commita "
    "(CLAUDE.md §2: ręczne typy TS są zakazane, typy pochodzą z OpenAPI)."
)


def _settings_for_export() -> Settings:
    """Ta sama konfiguracja zastępcza co w `scripts/export_openapi.py`."""
    try:
        return load_settings()
    except ConfigurationError:
        return Settings(
            database_url="postgresql+psycopg://openapi:openapi@localhost:5432/openapi",
            secret_key="openapi-export-placeholder",
        )


def render_openapi() -> str:
    """Schemat OpenAPI z BIEŻĄCEGO kodu, w formacie zapisu `export_openapi.py`."""
    schema = create_app(_settings_for_export()).openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def render_types(openapi_path: Path, target: Path) -> None:
    """Wygeneruj typy TS z podanego schematu (to samo narzędzie co `npm run generate:api`)."""
    binary = shutil.which("openapi-typescript", path=str(FRONTEND_DIR / "node_modules" / ".bin"))
    if binary is None:
        raise FileNotFoundError(
            "Brak `openapi-typescript` w `frontend/node_modules/.bin` — uruchom `task install-fe`."
        )
    # Argumenty są ścieżkami własnymi (repo + katalog tymczasowy) — bez danych użytkownika.
    subprocess.run(
        [binary, str(openapi_path), "--output", str(target)],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
    )


def main() -> int:
    stale: list[str] = []

    fresh_openapi = render_openapi()
    if not OPENAPI_FILE.is_file() or OPENAPI_FILE.read_text(encoding="utf-8") != fresh_openapi:
        stale.append("backend/openapi.json")

    with tempfile.TemporaryDirectory(prefix="pasnik-contract-") as tmp:
        schema_path = Path(tmp) / "openapi.json"
        schema_path.write_text(fresh_openapi, encoding="utf-8")
        types_path = Path(tmp) / "generated.ts"
        render_types(schema_path, types_path)
        fresh_types = types_path.read_text(encoding="utf-8")

    if not GENERATED_TS.is_file() or GENERATED_TS.read_text(encoding="utf-8") != fresh_types:
        stale.append("frontend/src/api/generated.ts")

    if stale:
        print(STALE_MESSAGE.format(files=", ".join(stale)), file=sys.stderr)
        return 1
    print("Kontrakt API zgodny z kodem (openapi.json + generated.ts).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
