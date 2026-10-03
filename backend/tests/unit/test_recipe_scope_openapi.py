"""Kontrakt OpenAPI zakresu przepisów (BATCH_21, D32): `Scope` dwuwartościowy, `RecipeScope` trzy.

Frontend generuje typy z OpenAPI (`task fe-types`); komponent `Scope` jest użyty
przez dni planu, szablony, cykle, tury, generacje i listy — jego rozszerzenie o
`global` wpuściłoby tę wartość do ~18 typów TS i do formularzy, które jej nie obsługują.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def schemas() -> dict[str, Any]:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/pasnik",
        secret_key="sekret",
        app_env="test",
    )
    components: dict[str, Any] = create_app(settings).openapi()["components"]["schemas"]
    return components


def test_komponent_scope_zostaje_dwuwartosciowy(schemas: dict[str, Any]) -> None:
    assert schemas["Scope"]["enum"] == ["private", "household"]


def test_komponent_recipescope_ma_trzy_wartosci(schemas: dict[str, Any]) -> None:
    assert schemas["RecipeScope"]["enum"] == ["private", "household", "global"]


def test_tylko_przepisy_uzywaja_recipescope(schemas: dict[str, Any]) -> None:
    users = sorted(
        name
        for name, schema in schemas.items()
        if "RecipeScope" in str(schema.get("properties", {}))
    )

    assert users == ["RecipeDetail", "RecipePayload", "RecipeSummary"]


def test_kopia_przyjmuje_scope_dwuwartosciowy(schemas: dict[str, Any]) -> None:
    """Kopia jest zawsze własnością wywołującego — `global` odpada walidacją (422)."""
    prop = schemas["RecipeCopyRequest"]["properties"]["scope"]

    assert "Scope" in str(prop) and "RecipeScope" not in str(prop)
