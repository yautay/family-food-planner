"""Paczka narzędzia `/pdf-extract` przechodzi prawdziwy import transferu (BATCH_22, D31/D33).

Na bazie testowej, przez `TransferService` — tę samą ścieżkę, którą pójdzie paczka
wgrywana przez właściciela. Dane SYNTETYCZNE (`tests/pdf_extract_fixtures.py`).

Kluczowe właściwości:

- DRY-RUN mówi to, co zrobi `apply` (`to_create`),
- DRUGI import tej samej paczki daje `created = 0` dla produktów, przepisów i składników (D22/D24),
- kolejna wersja REUŻYWA produkty z poprzedniej (brak duplikatu po `normalized_name`),
- każdy zapisany składnik przechodzi `normalize_amount` na zapisaną ilość (UI nie da 422),
- paczka `scope=instance` zachowuje `global` tylko dla ADMIN-a będącego właścicielem,
  a `scope=user` obcina `global` do rodziny nawet przy imporcie przez ADMIN-a (D33).
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from io import BytesIO
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.core.scope import RecipeScope
from app.modules.accounts.models import User, UserRole
from app.modules.catalog.models import CanonicalProduct, ProductCategory
from app.modules.recipes.models import Recipe, RecipeIngredient, Tag, recipe_tags
from app.modules.transfer.schemas import DATA_ENTRY_NAME
from app.modules.transfer.service import TransferService
from scripts.pdf_extract.catalog_index import build_index, resolve_catalog
from scripts.pdf_extract.package import (
    KNOWN_CATEGORIES,
    RecipeScopeChoice,
    build_archive,
    build_document,
)
from scripts.pdf_extract.roundtrip import ingredient_invariants
from scripts.pdf_extract.spec import Spec
from tests import factories
from tests.pdf_extract_fixtures import version_one, version_two

pytestmark = pytest.mark.integration

OWNER_EMAIL = "wlasciciel@example.com"


def _service(session: AsyncSession, settings: Settings) -> TransferService:
    return TransferService(session, uploads_dir=settings.uploads_dir, max_zip_mb=100)


def _pack(
    spec: Spec,
    versions: dict[str, Spec] | None = None,
    **kwargs: Any,
) -> bytes:
    index = build_index(versions or {})
    resolved = resolve_catalog(spec, index)
    return build_archive(build_document(spec, resolved.products, **kwargs))


def _rewrite(archive: bytes, mutate: Callable[[dict[str, Any]], object]) -> bytes:
    with zipfile.ZipFile(BytesIO(archive)) as source:
        document: dict[str, Any] = json.loads(source.read(DATA_ENTRY_NAME))
    mutate(document)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr(DATA_ENTRY_NAME, json.dumps(document))
    return buffer.getvalue()


async def _seed_dictionaries(session: AsyncSession) -> None:
    """Słowniki z migracji `0005`/`0007` — conftest czyści je między testami, produkcja je ma."""
    for position, (name, _) in enumerate(KNOWN_CATEGORIES, start=1):
        await factories.create_category(session, name=name, position=position)
    for name in ("śniadanie", "obiad", "kolacja"):
        session.add(Tag(name=name, is_system=True))
    await session.commit()


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_dry_run_apply_i_drugi_import_nie_dubluja_produktow_ani_przepisow(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Pierwszy import tworzy dane, drugi: `created=0` dla produktów, przepisów i składników."""
    await _seed_dictionaries(db_session)
    household = await factories.create_household(db_session, name="Rodzina testowa")
    user = await factories.create_user(
        db_session, email="user-pdfx@example.com", household=household
    )
    archive = _pack(version_one())
    service = _service(db_session, settings)

    import_id, report = await service.dry_run(user, filename="export.zip", data=archive)
    # Kategorie i tagi systemowe już są (reużyte), „podwieczorek” nie występuje w 0001.
    assert "product_categories" not in report.to_create
    assert "tags" not in report.to_create
    assert report.to_create["canonical_products"] == 4
    assert report.to_create["recipes"] == 2
    assert report.to_create["recipe_ingredients"] == 6
    assert report.to_create["product_unit_weights"] == 2  # mąka: łyżka, mleko: szklanka
    assert report.to_create["recipe_tags"] == 2

    first = await service.apply(user, import_id=import_id, decisions=[])
    assert first.created["canonical_products"] == 4
    assert first.created["recipes"] == 2

    products = (await db_session.execute(select(CanonicalProduct))).scalars().all()
    assert {p.verification_status.value for p in products} == {"unverified"}
    recipes = (await db_session.execute(select(Recipe))).scalars().all()
    assert {(r.scope, r.owner_user_id, r.household_id) for r in recipes} == {
        (RecipeScope.HOUSEHOLD, user.id, household.id)
    }
    assert await ingredient_invariants(db_session) == []

    import_id, report_two = await service.dry_run(user, filename="export.zip", data=archive)
    for section in ("canonical_products", "product_unit_weights", "recipes", "recipe_ingredients"):
        assert section not in report_two.to_create
    second = await service.apply(user, import_id=import_id, decisions=[])
    for section in ("canonical_products", "recipes", "recipe_ingredients", "recipe_tags"):
        assert second.created.get(section, 0) == 0
    assert await _count(db_session, CanonicalProduct) == 4
    assert await _count(db_session, Recipe) == 2
    assert await _count(db_session, RecipeIngredient) == 6


async def test_kolejna_wersja_reuzywa_produkty_z_poprzedniej(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Wersja 0002 niesie mąkę i jajko z 0001 (pełna definicja), a import scala je po nazwie."""
    await _seed_dictionaries(db_session)
    household = await factories.create_household(db_session)
    user = await factories.create_user(
        db_session, email="user-pdfx2@example.com", household=household
    )
    service = _service(db_session, settings)
    first, second = version_one(), version_two()

    import_id, _ = await service.dry_run(user, filename="a.zip", data=_pack(first))
    await service.apply(user, import_id=import_id, decisions=[])
    products_before = await _count(db_session, CanonicalProduct)

    archive_two = _pack(second, {"0001-syntetyczny": first})
    import_id, report = await service.dry_run(user, filename="b.zip", data=archive_two)
    assert report.to_create["canonical_products"] == 1  # tylko masło; mąka i jajko są reużyte
    assert report.to_create["recipes"] == 1
    assert {c.name for c in report.collisions if c.entity == "canonical_products"} == {
        "Mąka testowa",
        "Jajko testowe",
    }
    summary = await service.apply(user, import_id=import_id, decisions=[])
    assert summary.created["canonical_products"] == 1
    assert summary.reused["canonical_products"] == 2

    assert await _count(db_session, CanonicalProduct) == products_before + 1
    names = (await db_session.execute(select(CanonicalProduct.normalized_name))).scalars().all()
    assert len(names) == len(set(names))  # brak duplikatu po normalized_name
    assert await ingredient_invariants(db_session) == []

    # Drugi import wersji 0002 też niczego nie dubluje.
    import_id, _ = await service.dry_run(user, filename="b.zip", data=archive_two)
    again = await service.apply(user, import_id=import_id, decisions=[])
    assert again.created.get("canonical_products", 0) == 0
    assert again.created.get("recipes", 0) == 0


async def test_import_przez_usera_obcina_global_do_rodziny(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Plik `scope=user` z ręcznie dopisanym `global` (jak edycja `export.json`) → rodzinny."""
    await _seed_dictionaries(db_session)
    household = await factories.create_household(db_session)
    user = await factories.create_user(
        db_session, email="user-pdfx3@example.com", household=household
    )
    tampered = _rewrite(
        _pack(version_one()),
        lambda doc: [row.update({"scope": "global"}) for row in doc["data"]["recipes"]],
    )
    service = _service(db_session, settings)
    import_id, _ = await service.dry_run(user, filename="t.zip", data=tampered)
    await service.apply(user, import_id=import_id, decisions=[])
    scopes = {r.scope for r in (await db_session.execute(select(Recipe))).scalars()}
    assert scopes == {RecipeScope.HOUSEHOLD}


async def test_import_scope_user_przez_admina_tez_obcina_global(
    db_session: AsyncSession, settings: Settings
) -> None:
    """D33 (wariant A): plik `scope=user` wczytany przez ADMIN-a NIE daje przepisów globalnych."""
    await _seed_dictionaries(db_session)
    admin = await factories.create_admin(db_session, email=OWNER_EMAIL)
    tampered = _rewrite(
        _pack(version_one()),
        lambda doc: [row.update({"scope": "global"}) for row in doc["data"]["recipes"]],
    )
    service = _service(db_session, settings)
    import_id, _ = await service.dry_run(admin, filename="t.zip", data=tampered)
    await service.apply(admin, import_id=import_id, decisions=[])
    scopes = {r.scope for r in (await db_session.execute(select(Recipe))).scalars()}
    assert scopes == {RecipeScope.PRIVATE}  # admin z tej fixtury nie ma rodziny


async def test_paczka_global_zachowuje_zakres_i_drugi_import_nie_dubluje(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Paczka `scope=instance` wczytana przez ADMIN-a-właściciela: `global`, bez duplikatów."""
    await _seed_dictionaries(db_session)
    admin = await factories.create_admin(db_session, email=OWNER_EMAIL)
    archive = _pack(version_one(), recipe_scope=RecipeScopeChoice.GLOBAL, owner_email=OWNER_EMAIL)
    service = _service(db_session, settings)

    import_id, report = await service.dry_run(admin, filename="g.zip", data=archive)
    assert report.scope.value == "instance"
    assert "users" not in report.to_create  # konto istnieje — import je reużyje
    assert report.to_create["recipes"] == 2
    summary = await service.apply(admin, import_id=import_id, decisions=[])
    assert summary.created["recipes"] == 2

    recipes = (await db_session.execute(select(Recipe))).scalars().all()
    assert {(r.scope, r.household_id, r.owner_user_id) for r in recipes} == {
        (RecipeScope.GLOBAL, None, admin.id)
    }
    assert await _count(db_session, User) == 1  # konta nikt nie założył

    # Ten sam ADMIN wgrywa ten sam plik drugi raz: przepisy są „własne”, więc `created = 0`.
    import_id, report_two = await service.dry_run(admin, filename="g.zip", data=archive)
    assert "recipes" not in report_two.to_create
    again = await service.apply(admin, import_id=import_id, decisions=[])
    assert again.created.get("recipes", 0) == 0
    assert again.created.get("canonical_products", 0) == 0
    assert await _count(db_session, Recipe) == 2


async def test_paczka_global_wgrana_przez_innego_admina_nie_daje_global_i_dry_run_to_pokazuje(
    db_session: AsyncSession, settings: Settings
) -> None:
    """E-mail w paczce ≠ konto wczytujące: `users` w „Nowe” (STOP), przepisy NIE są globalne."""
    await _seed_dictionaries(db_session)
    other_admin = await factories.create_admin(db_session, email="inny-admin@example.com")
    archive = _pack(version_one(), recipe_scope=RecipeScopeChoice.GLOBAL, owner_email=OWNER_EMAIL)
    service = _service(db_session, settings)

    import_id, report = await service.dry_run(other_admin, filename="g.zip", data=archive)
    assert report.to_create.get("users") == 1  # to widzi właściciel w podglądzie i przerywa
    await service.apply(other_admin, import_id=import_id, decisions=[])

    created_user = (
        await db_session.execute(select(User).where(User.email == OWNER_EMAIL))
    ).scalar_one()
    assert (created_user.role, created_user.is_active) == (UserRole.USER, False)
    scopes = {r.scope for r in (await db_session.execute(select(Recipe))).scalars()}
    assert RecipeScope.GLOBAL not in scopes


async def test_paczke_instancji_nie_wczyta_zwykly_user(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Powierzchnia ataku paczki `global`: plik instancji przyjmuje wyłącznie ADMIN."""
    await _seed_dictionaries(db_session)
    household = await factories.create_household(db_session)
    user = await factories.create_user(
        db_session, email="user-pdfx4@example.com", household=household
    )
    archive = _pack(version_one(), recipe_scope=RecipeScopeChoice.GLOBAL, owner_email=OWNER_EMAIL)
    with pytest.raises(ForbiddenError):
        await _service(db_session, settings).dry_run(user, filename="g.zip", data=archive)


async def test_bez_slownikow_paczka_zaklada_kategorie_i_tagi(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Na bazie bez słowników (jak po TRUNCATE w testach) paczka niesie kategorie i tagi sama."""
    household = await factories.create_household(db_session)
    user = await factories.create_user(
        db_session, email="user-pdfx5@example.com", household=household
    )
    service = _service(db_session, settings)
    import_id, report = await service.dry_run(user, filename="e.zip", data=_pack(version_one()))
    assert report.to_create["product_categories"] == 3  # makarony, nabiał, grzyby
    assert report.to_create["tags"] == 2
    await service.apply(user, import_id=import_id, decisions=[])
    assert await _count(db_session, ProductCategory) == 3
    tag_ids = (await db_session.execute(select(recipe_tags.c.tag_id))).scalars().all()
    assert len(tag_ids) == 2
