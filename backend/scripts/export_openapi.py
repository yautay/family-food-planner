"""Eksport kontraktu OpenAPI do pliku JSON (krok `task fe-types`).

Schemat OpenAPI jest źródłem typów TS frontendu (`frontend/src/api/generated.ts`)
oraz materiałem do porównań API w batchach Review (04_API §4). Plik wynikowy
jest commitowany — świeża sesja nie musi podnosić backendu, żeby typować UI.

Użycie:
    uv run python scripts/export_openapi.py [ścieżka/docelowa.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.config import ConfigurationError, Settings, load_settings
from app.main import create_app

DEFAULT_TARGET = Path("openapi.json")


def _settings_for_export() -> Settings:
    """Konfiguracja do wygenerowania schematu.

    Kształt API nie zależy od bazy ani sekretów, więc eksport działa też bez
    `.env` — wtedy używamy wartości zastępczych (nigdzie nie są zapisywane).
    """
    try:
        return load_settings()
    except ConfigurationError:
        return Settings(
            database_url="postgresql+psycopg://openapi:openapi@localhost:5432/openapi",
            secret_key="openapi-export-placeholder",
        )


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else DEFAULT_TARGET
    schema = create_app(_settings_for_export()).openapi()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI zapisany: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
