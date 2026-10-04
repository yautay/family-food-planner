"""`pdfx-roundtrip`: import paczki na bazie TESTOWEJ, dwa razy, porównanie liczników (D31 pkt 4).

To jedyne miejsce narzędzia, które dotyka bazy, i tylko TESTOWEJ: URL pochodzi
wyłącznie z `TEST_DATABASE_URL`, nazwa bazy musi kończyć się `_test`, a URL nie może
być równy `DATABASE_URL` (dev). Przed przebiegiem tabele są czyszczone (`TRUNCATE`
— baza testowa jest scratchem; testy integracyjne robią to samo), więc NIE uruchamiaj
go równolegle z `task test-int` (wspólna baza).

Przebieg przechodzi przez `TransferService` — dokładnie tę ścieżkę, którą pójdzie
paczka wgrywana przez właściciela: DRY-RUN → `apply` → DRY-RUN → `apply`. Drugi
import musi dać `created = 0` dla produktów, przepisów i składników (D22/D24).
Dodatkowo sprawdzamy to, co zepsułoby UI: dla KAŻDEGO składnika w bazie
`normalize_amount(display_qty, display_unit)` musi dać zapisaną ilość.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import normalize_database_url, selector_loop_factory
from app.core.scope import RecipeScope
from app.core.security import generate_token, hash_password

# Rejestr modeli MUSI być zaimportowany (jak w `app/cli.py` i `scripts/seed_demo.py`):
# narzędzie omija `create_app()`, więc bez tej linii relacje ORM nie są skonfigurowane.
from app.models import Base
from app.modules.accounts.models import User, UserRole
from app.modules.catalog.models import CanonicalProduct, ProductUnitWeight
from app.modules.catalog.nutrition_adapter import measure_for
from app.modules.catalog.units import UnitConversionError, UnitWeight, normalize_amount
from app.modules.households.models import Household
from app.modules.recipes.models import Recipe, RecipeIngredient
from app.modules.transfer.schemas import DATA_ENTRY_NAME
from app.modules.transfer.service import TransferService
from scripts.pdf_extract.spec import SpecError

#: Sekcje, których drugi import NIE MA prawa utworzyć (D22: reużyty rodzic = pominięte dzieci).
MUST_NOT_REPEAT = (
    "canonical_products",
    "product_unit_weights",
    "recipes",
    "recipe_ingredients",
    "recipe_tags",
)
_AMOUNT_TOLERANCE = Decimal("0.001")
#: Roundtrip czyści tabele (TRUNCATE), więc łączy się tylko z bazą na tej maszynie.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class RoundtripError(SpecError):
    """Roundtrip nie może się odbyć (zła baza, brak URL-a) albo wykrył niezgodność."""


@dataclass
class RoundtripResult:
    """Liczniki obu przebiegów i lista naruszeń (pusta = zielono)."""

    first_created: dict[str, int] = field(default_factory=dict)
    first_reused: dict[str, int] = field(default_factory=dict)
    first_warnings: list[str] = field(default_factory=list)
    second_created: dict[str, int] = field(default_factory=dict)
    second_reused: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def assert_test_database(test_url: str | None, dev_url: str | None) -> str:
    """URL bazy TESTOWEJ albo `RoundtripError` — narzędzie nie dotknie niczego innego."""
    if not test_url:
        raise RoundtripError(
            "Brak TEST_DATABASE_URL — roundtrip działa wyłącznie na bazie testowej (`task dev-db`)."
        )
    url = make_url(test_url)
    if not (url.database or "").endswith("_test"):
        raise RoundtripError(
            f"Baza „{url.database}” nie wygląda na testową (nazwa musi kończyć się `_test`)."
        )
    if url.host not in LOCAL_HOSTS:
        raise RoundtripError(
            f"Host „{url.host}” nie jest lokalny — roundtrip robi TRUNCATE i działa wyłącznie "
            "na lokalnej bazie testowej (`task dev-db`)."
        )
    if dev_url and make_url(dev_url) == url:
        raise RoundtripError("TEST_DATABASE_URL wskazuje tę samą bazę co DATABASE_URL — przerwano.")
    return test_url


def read_header(zip_path: Path) -> dict[str, object]:
    """Nagłówek i sekcja `users` paczki — wystarcza, żeby dobrać konto wczytujące."""
    with zipfile.ZipFile(zip_path) as archive:
        document: dict[str, object] = json.loads(archive.read(DATA_ENTRY_NAME))
    return document


async def ingredient_invariants(session: AsyncSession) -> list[str]:
    """Każdy składnik w bazie musi przechodzić `normalize_amount` na zapisaną ilość.

    To jest błąd, który wyszedł dopiero przy ręcznej analizie: „5 x Sztuka”
    pieczarek zapisane w bazie wygląda dobrze, a pierwsza edycja w UI kończy się 422.
    """
    problems: list[str] = []
    weights: dict[int, list[UnitWeight]] = {}
    for row in (await session.execute(select(ProductUnitWeight))).scalars():
        weights.setdefault(row.product_id, []).append(
            UnitWeight(unit_label=row.unit_label, grams_per_unit=row.grams_per_unit)
        )
    products = {
        product.id: product
        for product in (await session.execute(select(CanonicalProduct))).scalars()
    }
    recipes = {
        recipe.id: recipe.name for recipe in (await session.execute(select(Recipe))).scalars()
    }
    for ingredient in (await session.execute(select(RecipeIngredient))).scalars():
        product = products[ingredient.product_id]
        label = f"{recipes.get(ingredient.recipe_id, '?')} / {product.name}"
        if ingredient.display_qty is None or ingredient.display_unit is None:
            problems.append(f"{label}: brak display_qty/display_unit")
            continue
        measure = measure_for(product, weights.get(product.id, []))
        try:
            normalized = normalize_amount(ingredient.display_qty, ingredient.display_unit, measure)
        except UnitConversionError as exc:
            problems.append(
                f"{label}: „{ingredient.display_qty} {ingredient.display_unit}” → {exc.message}"
            )
            continue
        if (
            normalized.unit != ingredient.amount_unit
            or abs(normalized.amount - ingredient.amount) > _AMOUNT_TOLERANCE
        ):
            problems.append(
                f"{label}: zapisano {ingredient.amount} {ingredient.amount_unit.value}, "
                f"a normalize_amount daje {normalized.amount} {normalized.unit.value}"
            )
    return problems


async def _clean(session: AsyncSession) -> None:
    names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    await session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
    await session.commit()
    session.expunge_all()


async def run_roundtrip(
    zip_path: Path, *, session_factory: async_sessionmaker[AsyncSession]
) -> RoundtripResult:
    """Dwukrotny import paczki przez `TransferService` na wskazanej (testowej) bazie."""
    data = zip_path.read_bytes()
    document = read_header(zip_path)
    is_instance = document.get("scope") == "instance"
    result = RoundtripResult()

    async with session_factory() as session:
        await _clean(session)
        household = Household(name="Roundtrip")
        session.add(household)
        await session.commit()
        await session.refresh(household)

        email = "roundtrip@example.test"
        if is_instance:
            users = (document.get("data") or {}).get("users") or []  # type: ignore[attr-defined]
            if not users:
                raise RoundtripError("Paczka scope=instance bez sekcji users.")
            email = str(users[0]["email"])
        actor = User(
            email=email,
            password_hash=hash_password(generate_token()),
            display_name="Roundtrip",
            role=UserRole.ADMIN if is_instance else UserRole.USER,
            is_active=True,
            household_id=household.id,
        )
        session.add(actor)
        await session.commit()
        await session.refresh(actor)

        with tempfile.TemporaryDirectory(prefix="pdfx-roundtrip-") as uploads:
            service = TransferService(session, uploads_dir=uploads, max_zip_mb=100)

            import_id, first_report = await service.dry_run(
                actor, filename=zip_path.name, data=data
            )
            first = await service.apply(actor, import_id=import_id, decisions=[])
            result.first_created, result.first_reused = first.created, first.reused
            result.first_warnings = list(first_report.warnings)
            if "users" in first_report.to_create:
                result.problems.append(
                    "DRY-RUN zapowiada utworzenie konta (`users`) — e-mail paczki nie pasuje do "
                    "żadnego istniejącego konta."
                )

            import_id, second_report = await service.dry_run(
                actor, filename=zip_path.name, data=data
            )
            for section in MUST_NOT_REPEAT:
                if second_report.to_create.get(section):
                    result.problems.append(
                        f"DRY-RUN drugiego importu zapowiada {second_report.to_create[section]} "
                        f"x {section} (powinno być 0)."
                    )
            second = await service.apply(actor, import_id=import_id, decisions=[])
            result.second_created, result.second_reused = second.created, second.reused
            for section in MUST_NOT_REPEAT:
                if second.created.get(section):
                    result.problems.append(
                        f"drugi import utworzył {second.created[section]} x {section} (D22/D24)."
                    )

        result.problems.extend(await ingredient_invariants(session))

        if is_instance:
            scopes = {recipe.scope for recipe in (await session.execute(select(Recipe))).scalars()}
            if scopes != {RecipeScope.GLOBAL}:
                result.problems.append(
                    "po imporcie instancji nie wszystkie przepisy mają zakres `global`: "
                    + ", ".join(sorted(scope.value for scope in scopes))
                )
    return result


def run(zip_path: Path) -> RoundtripResult:
    """Punkt wejścia CLI: silnik z `TEST_DATABASE_URL` + pętla selektorowa (Windows)."""
    url = assert_test_database(os.environ.get("TEST_DATABASE_URL"), os.environ.get("DATABASE_URL"))

    async def main() -> RoundtripResult:
        engine = create_async_engine(normalize_database_url(url), hide_parameters=True)
        try:
            factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
            return await run_roundtrip(zip_path, session_factory=factory)
        finally:
            await engine.dispose()

    return asyncio.run(main(), loop_factory=selector_loop_factory())
