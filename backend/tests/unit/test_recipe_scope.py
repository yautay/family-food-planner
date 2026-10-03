"""Zakres `global` przepisów — reguły czyste (BATCH_21, D32): bez bazy i bez HTTP.

Dowodzone tu rzeczy, które łatwo zepsuć po cichu:

- `Scope` zostaje DWUWARTOŚCIOWY, `RecipeScope` ma trzy — wspólny enum nie może
  wpuścić `global` do planu, szablonów, tur, generacji ani list,
- `is` na granicy dwóch enumów nie działa (inne obiekty) — walidacja scope używa `==`,
- `global` jest w `visible_condition` TYLKO przy `allow_global=True`, a w
  `owned_condition` (podstawa eksportu D26) nie ma go nigdy,
- każdy `ScopedQuery(Recipe, …)` w kodzie ma `allow_global=True` (poza transferem).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import ColumnElement
from sqlalchemy.dialects import postgresql

from app.core.errors import ConflictError, ForbiddenError
from app.core.scope import (
    GLOBAL_ADMIN_ONLY_MESSAGE,
    RecipeScope,
    Scope,
    ScopedQuery,
    outside_audience_condition,
)
from app.modules.accounts.models import User, UserRole
from app.modules.planning.models import PlanDay
from app.modules.recipes.models import Recipe

pytestmark = pytest.mark.unit

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _user(user_id: int, *, household_id: int | None = None, role: UserRole = UserRole.USER) -> User:
    return User(id=user_id, role=role, household_id=household_id)


def _sql(clause: ColumnElement[bool]) -> str:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    return str(clause.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def test_scope_ma_dwie_wartosci_a_recipescope_trzy() -> None:
    assert [member.value for member in Scope] == ["private", "household"]
    assert [member.value for member in RecipeScope] == ["private", "household", "global"]


def test_recipescope_rowna_sie_scope_po_wartosci_ale_nie_jest_tym_samym_obiektem() -> None:
    """Dlatego walidacja scope przepisu porównuje `==`, nie `is`."""
    assert RecipeScope.HOUSEHOLD == Scope.HOUSEHOLD  # type: ignore[comparison-overlap]
    assert RecipeScope.HOUSEHOLD is not Scope.HOUSEHOLD  # type: ignore[comparison-overlap]


def test_uzytkownik_bez_rodziny_nie_nada_recipescope_household() -> None:
    """Regresja pułapki `is`: z `scope is Scope.HOUSEHOLD` wychodził 500 z CHECK-a, nie 409."""
    with pytest.raises(ConflictError):
        ScopedQuery.assert_scope_allowed(_user(1), RecipeScope.HOUSEHOLD)


def test_przepis_global_nie_dostaje_rodziny_przy_tworzeniu() -> None:
    kolumny = ScopedQuery.ownership_for_create(
        _user(3, household_id=7, role=UserRole.ADMIN), RecipeScope.GLOBAL
    )

    assert kolumny == {"owner_user_id": 3, "household_id": None, "scope": RecipeScope.GLOBAL}


def test_global_jest_w_visible_condition_tylko_przy_allow_global() -> None:
    user = _user(5, household_id=2)
    recipes = ScopedQuery(Recipe, not_found_message="x", allow_global=True)
    plain = ScopedQuery(Recipe, not_found_message="x")

    assert "'global'" in _sql(recipes.visible_condition(user))
    assert "'global'" not in _sql(plain.visible_condition(user))


def test_owned_condition_nie_zawiera_global_nigdy() -> None:
    """Na przynależności stoi eksport rodziny (D26) — nie ma wciągać przepisów instancji."""
    recipes = ScopedQuery(Recipe, not_found_message="x", allow_global=True)

    assert "'global'" not in _sql(recipes.owned_condition(_user(5, household_id=2)))
    assert "'global'" not in _sql(recipes.owned_condition(_user(5)))


def test_admin_widzi_wszystko_wiec_global_nie_zmienia_jego_warunku() -> None:
    recipes = ScopedQuery(Recipe, not_found_message="x", allow_global=True)

    assert _sql(recipes.visible_condition(_user(1, role=UserRole.ADMIN))) == "true"


class _FakeRecipe:
    """Minimalny przepis „na sucho" — `assert_can_*` czyta tylko `scope` i `owner_user_id`."""

    def __init__(self, *, owner: int, scope: RecipeScope) -> None:
        self.owner_user_id = owner
        self.scope = scope


def test_edycja_tresci_global_dla_usera_to_403_nawet_dla_wlasciciela() -> None:
    """Rola, nie `owner_user_id`: zdegradowany były admin jest nadal właścicielem wiersza."""
    recipes = ScopedQuery(Recipe, not_found_message="x", allow_global=True)
    former_admin = _user(9, household_id=1)
    row = _FakeRecipe(owner=9, scope=RecipeScope.GLOBAL)

    with pytest.raises(ForbiddenError) as denied:
        recipes.assert_can_edit_content(row, former_admin)  # type: ignore[arg-type]
    with pytest.raises(ForbiddenError):
        recipes.assert_can_manage(row, former_admin)  # type: ignore[arg-type]

    assert denied.value.message == GLOBAL_ADMIN_ONLY_MESSAGE
    assert denied.value.status_code == 403


def test_admin_zarzadza_przepisem_global_a_zwykla_edycja_household_zostaje_bez_zmian() -> None:
    recipes = ScopedQuery(Recipe, not_found_message="x", allow_global=True)
    admin = _user(1, role=UserRole.ADMIN)
    member = _user(2, household_id=4)

    recipes.assert_can_manage(_FakeRecipe(owner=8, scope=RecipeScope.GLOBAL), admin)  # type: ignore[arg-type]
    # Edycja TREŚCI przepisu rodzinnego nie wymaga roli ani własności (02_DOMAIN §3.1 pkt 2).
    recipes.assert_can_edit_content(_FakeRecipe(owner=8, scope=RecipeScope.HOUSEHOLD), member)  # type: ignore[arg-type]


def test_outside_audience_condition_zaweza_do_wierszy_spoza_grona() -> None:
    with_household = _sql(outside_audience_condition(PlanDay, keep_household_id=7, keep_owner_id=3))
    without_household = _sql(
        outside_audience_condition(PlanDay, keep_household_id=None, keep_owner_id=3)
    )

    assert "owner_user_id != 3" in with_household and "household_id != 7" in with_household
    assert "household_id IS NULL" in with_household
    assert "household_id" not in without_household


def test_scopedquery_przepisu_powstaje_tylko_w_fabryce_i_w_transferze() -> None:
    """Strażnik źródeł: `ScopedQuery(Recipe, …)` składa JEDNA fabryka, a transfer ma własne.

    Widoczność przepisu globalnego dopisuje WYŁĄCZNIE flaga `allow_global`; moduł,
    który zbuduje własne zapytanie bez niej, odrzuci przepis globalny z planu/szablonu
    obcej rodziny (422), mimo że lista przepisów go pokazuje. Dlatego planowanie i
    szablony wołają `recipes.service.recipe_visibility_query`. Wyjątek: transfer czyta
    `select_owned` (przynależność) i celowo NIE ma flagi.
    """
    constructor = re.compile(r"ScopedQuery\(\s*Recipe\b")
    found: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        relative = path.relative_to(APP_DIR).as_posix()
        # `core/scope.py` ma tylko przykład w docstringu.
        if relative != "core/scope.py" and constructor.search(path.read_text(encoding="utf-8")):
            found.add(relative)

    assert found == {"modules/recipes/service.py", "modules/transfer/service.py"}
    factory_source = (APP_DIR / "modules/recipes/service.py").read_text(encoding="utf-8")
    assert "allow_global=True" in factory_source
    transfer_source = (APP_DIR / "modules/transfer/service.py").read_text(encoding="utf-8")
    assert "allow_global=True" not in transfer_source
