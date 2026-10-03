"""Transfer a przepisy `global` (BATCH_21, D32 pkt 8).

Trzy granice, każda z testem:

1. **Eksport użytkownika** dołącza przepisy `global`, do których odwołują się jego
   plany i szablony (zakres w pliku obcięty do `household`/`private`) — inaczej
   pozycje planu z cudzym przepisem znikałyby po cichu. Przepisy globalne, których
   nikt tu nie używa, NIE wchodzą (`owned_condition` bez zmian, D26).
2. **Import** nigdy nie daje nie-ADMIN-owi przepisu `global` — także gdy ktoś
   ręcznie edytuje `export.json` (eskalacja uprawnień przez plik).
3. **Eksport/import instancji** zachowuje `global`, ale tylko dla właściciela-ADMIN-a.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any, cast

import pytest
from sqlalchemy import Column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scope import RecipeScope, Scope
from app.core.security import utcnow
from app.modules.accounts.models import User, UserRole
from app.modules.planning.models import DayTemplate, PlanDay, PlanItemServing, PlanMealItem
from app.modules.recipes.models import Recipe
from app.modules.transfer.importer import TransferValidationError
from app.modules.transfer.schemas import DATA_ENTRY_NAME, TransferScope
from app.modules.transfer.service import TransferService, coerce_value
from tests import factories
from tests.conftest import DB_TABLES

pytestmark = pytest.mark.integration

DAY = date(2030, 6, 3)


def _service(session: AsyncSession, settings: Settings) -> TransferService:
    return TransferService(session, uploads_dir=settings.uploads_dir, max_zip_mb=100)


async def _wipe(session: AsyncSession) -> None:
    await session.execute(text(f"TRUNCATE TABLE {', '.join(DB_TABLES)} RESTART IDENTITY CASCADE"))
    await session.commit()
    # Po surowym TRUNCATE mapa tożsamości trzyma OBIEKTY ze starymi id (RESTART IDENTITY
    # wydaje te same numery nowym wierszom) — bez tego `session.get(User, 1)` zwraca duchy.
    session.expunge_all()


def _document(archive_bytes: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        document: dict[str, Any] = json.loads(archive.read(DATA_ENTRY_NAME))
    return document


def _rewrite(archive_bytes: bytes, mutate: Callable[[dict[str, Any]], object]) -> bytes:
    """Ręcznie „zepsuty" plik: dokładnie to, co zrobiłby złośliwy użytkownik."""
    document = _document(archive_bytes)
    mutate(document)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DATA_ENTRY_NAME, json.dumps(document))
    return buffer.getvalue()


async def _export(
    service: TransferService, actor: User, scope: TransferScope = TransferScope.USER
) -> bytes:
    exported = await service.export(actor, scope=scope, app_version="test", now=utcnow())
    return exported.path.read_bytes()


async def _admin_global_world(session: AsyncSession) -> dict[str, Any]:
    """Admin z globalnym przepisem + użytkownik OBCEJ rodziny planujący z tym przepisem."""
    admin = await factories.create_admin(session, email="admin-t@example.com")
    household = await factories.create_household(session, name="Obca rodzina")
    user = await factories.create_user(session, email="obcy-t@example.com", household=household)
    profile = await factories.create_member_profile(session, household=household, name="Ola")
    category = await factories.create_category(session, name="Warzywa")
    carrot = await factories.create_product(session, category=category, name="Marchew")
    used = await factories.create_recipe(
        session, owner=admin, name="Globalna użyta", scope=RecipeScope.GLOBAL, base_servings=2
    )
    await factories.create_ingredient(session, recipe=used, product=carrot, amount=Decimal("300"))
    unused = await factories.create_recipe(
        session, owner=admin, name="Globalna nieużyta", scope=RecipeScope.GLOBAL
    )
    day = await factories.create_plan_day(session, owner=user, day=DAY)
    meal = await factories.create_plan_meal(session, plan_day=day, name="Obiad")
    item = await factories.create_plan_item(session, meal=meal, recipe=used)
    await factories.create_item_split(session, item=item, profile=profile)
    await factories.create_day_template(
        session,
        owner=user,
        name="Szablon z globalnym",
        payload=factories.day_payload(
            meals=[factories.template_meal(items=[factories.template_recipe_item(used.id)])]
        ),
    )
    return {"admin": admin, "user": user, "used": used, "unused": unused, "household": household}


async def test_eksport_planu_z_przepisem_global_zachowuje_pozycje_i_podzialy(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Round-trip: przepis globalny wchodzi do pliku jako kopia rodziny i wraca na instancję."""
    world = await _admin_global_world(db_session)
    service = _service(db_session, settings)

    archive_bytes = await _export(service, world["user"])
    document = _document(archive_bytes)

    recipes = document["data"]["recipes"]
    assert [row["name"] for row in recipes] == ["Globalna użyta"]  # „nieużyta" NIE wchodzi
    assert recipes[0]["scope"] == "household"  # obcięte; plik użytkownika nie niesie `global`
    assert recipes[0]["household_id"] == world["household"].id
    assert recipes[0]["owner_user_id"] == world["user"].id  # nie ujawnia id admina
    assert len(document["data"]["plan_meal_items"]) == 1
    assert len(document["data"]["plan_item_servings"]) == 1
    assert [row["recipe_id"] for row in document["data"]["plan_meal_items"]] == [recipes[0]["id"]]

    await _wipe(db_session)
    fresh_household = await factories.create_household(db_session, name="Nowa")
    fresh = await factories.create_user(
        db_session, email="nowy@example.com", household=fresh_household
    )
    import_id, report = await service.dry_run(fresh, filename="e.zip", data=archive_bytes)
    assert report.to_create["recipes"] == 1
    summary = await service.apply(fresh, import_id=import_id, decisions=[])

    assert summary.created["plan_meal_items"] == 1
    assert summary.created["plan_item_servings"] == 1
    recipe = (await db_session.execute(select(Recipe))).scalar_one()
    assert recipe.scope == RecipeScope.HOUSEHOLD
    assert recipe.owner_user_id == fresh.id and recipe.household_id == fresh_household.id
    item = (await db_session.execute(select(PlanMealItem))).scalar_one()
    assert item.recipe_id == recipe.id
    assert len((await db_session.execute(select(PlanItemServing))).scalars().all()) == 1
    template = (await db_session.execute(select(DayTemplate))).scalar_one()
    assert template.payload["meals"][0]["items"][0]["recipe_id"] == recipe.id  # type: ignore[index]


async def test_wlasny_przepis_global_admina_wychodzi_w_pliku_uzytkownika_jako_kopia(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Plik `scope=user` NIGDY nie niesie `global` — także dla ADMIN-a-właściciela."""
    admin = await factories.create_admin(db_session, email="solo-admin@example.com")
    household = await factories.create_household(db_session, name="Rodzina admina")
    admin.household_id = household.id
    await db_session.commit()
    await factories.create_recipe(
        db_session, owner=admin, name="Moja globalna", scope=RecipeScope.GLOBAL
    )

    document = _document(await _export(_service(db_session, settings), admin))

    row = document["data"]["recipes"][0]
    assert row["scope"] == "household" and row["household_id"] == household.id
    # Przepis w bazie nadal jest globalny — eksport nie mutuje wiersza ORM.
    stored = (await db_session.execute(select(Recipe))).scalar_one()
    await db_session.refresh(stored)
    assert stored.scope == RecipeScope.GLOBAL and stored.household_id is None


async def test_import_global_przez_usera_jest_obciety_do_household(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Ręcznie edytowany `export.json` z `"scope":"global"` nie daje przepisu globalnego."""
    owner = await factories.create_user(
        db_session,
        email="zrodlo@example.com",
        household=await factories.create_household(db_session, name="Źródło"),
    )
    await factories.create_recipe(db_session, owner=owner, name="Podrobiony", scope=Scope.HOUSEHOLD)
    service = _service(db_session, settings)
    archive_bytes = await _export(service, owner)

    def escalate(document: dict[str, Any]) -> None:
        for row in document["data"]["recipes"]:
            row["scope"] = "global"
            row["household_id"] = None

    forged = _rewrite(archive_bytes, escalate)
    assert _document(forged)["data"]["recipes"][0]["scope"] == "global"

    await _wipe(db_session)
    household = await factories.create_household(db_session, name="Importujący")
    importer = await factories.create_user(
        db_session, email="importer@example.com", household=household
    )
    import_id, report = await service.dry_run(importer, filename="e.zip", data=forged)
    assert any(
        "dostępn" in warning and "wszystkich rodzin" in warning for warning in report.warnings
    )
    summary = await service.apply(importer, import_id=import_id, decisions=[])

    recipe = (await db_session.execute(select(Recipe))).scalar_one()
    assert recipe.scope == RecipeScope.HOUSEHOLD
    assert recipe.household_id == household.id and recipe.owner_user_id == importer.id
    assert any("wszystkich rodzin" in warning for warning in summary.warnings)


async def test_import_global_przez_usera_bez_rodziny_daje_private(
    db_session: AsyncSession, settings: Settings
) -> None:
    owner = await factories.create_user(db_session, email="z2@example.com")
    await factories.create_recipe(db_session, owner=owner, name="Podrobiony 2")
    service = _service(db_session, settings)
    forged = _rewrite(
        await _export(service, owner),
        lambda doc: [row.update(scope="global") for row in doc["data"]["recipes"]],
    )
    await _wipe(db_session)
    loner = await factories.create_user(db_session, email="solo-importer@example.com")

    import_id, _ = await service.dry_run(loner, filename="e.zip", data=forged)
    await service.apply(loner, import_id=import_id, decisions=[])

    recipe = (await db_session.execute(select(Recipe))).scalar_one()
    assert recipe.scope == RecipeScope.PRIVATE and recipe.household_id is None


async def test_import_pliku_uzytkownika_przez_admina_tez_obcina_global(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Kopia danych RODZINY nie publikuje przepisów globalnych nawet przy ADMIN-ie."""
    owner = await factories.create_user(db_session, email="z3@example.com")
    await factories.create_recipe(db_session, owner=owner, name="Podrobiony 3")
    service = _service(db_session, settings)
    forged = _rewrite(
        await _export(service, owner),
        lambda doc: [row.update(scope="global") for row in doc["data"]["recipes"]],
    )
    await _wipe(db_session)
    admin = await factories.create_admin(db_session, email="admin-importer@example.com")

    import_id, _ = await service.dry_run(admin, filename="e.zip", data=forged)
    await service.apply(admin, import_id=import_id, decisions=[])

    recipe = (await db_session.execute(select(Recipe))).scalar_one()
    assert recipe.scope != RecipeScope.GLOBAL


async def test_eksport_i_import_instancji_zachowuja_global_dla_wlasciciela_admina(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Round-trip instancji: `global` zostaje, `household_id` pozostaje NULL (CHECK z 0018)."""
    world = await _admin_global_world(db_session)
    service = _service(db_session, settings)

    archive_bytes = await _export(service, world["admin"], TransferScope.INSTANCE)
    scopes = {row["name"]: row["scope"] for row in _document(archive_bytes)["data"]["recipes"]}
    assert scopes == {"Globalna użyta": "global", "Globalna nieużyta": "global"}

    await _wipe(db_session)
    fresh_admin = await factories.create_admin(db_session, email="nowy-admin@example.com")
    import_id, _ = await service.dry_run(fresh_admin, filename="i.zip", data=archive_bytes)
    await service.apply(fresh_admin, import_id=import_id, decisions=[])

    recipes = (await db_session.execute(select(Recipe).order_by(Recipe.name))).scalars().all()
    assert [(row.name, row.scope, row.household_id) for row in recipes] == [
        ("Globalna nieużyta", RecipeScope.GLOBAL, None),
        ("Globalna użyta", RecipeScope.GLOBAL, None),
    ]
    admin_row = (
        await db_session.execute(select(User).where(User.email == "admin-t@example.com"))
    ).scalar_one()
    assert admin_row.role is UserRole.ADMIN
    assert {row.owner_user_id for row in recipes} == {admin_row.id}


async def test_import_instancji_z_globalnym_przepisem_nie_admina_wraca_do_jego_rodziny(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Zmapowany właściciel NIE jest ADMIN-em (np. były admin) → `global` się nie zachowuje."""
    household = await factories.create_household(db_session, name="Rodzina byłego admina")
    former_admin = await factories.create_user(
        db_session, email="byly@example.com", household=household
    )
    await factories.create_recipe(
        db_session, owner=former_admin, name="Osierocona globalna", scope=RecipeScope.GLOBAL
    )
    admin = await factories.create_admin(db_session, email="wykonawca@example.com")
    service = _service(db_session, settings)
    archive_bytes = await _export(service, admin, TransferScope.INSTANCE)

    await _wipe(db_session)
    fresh_admin = await factories.create_admin(db_session, email="nowy-admin2@example.com")
    import_id, _ = await service.dry_run(fresh_admin, filename="i.zip", data=archive_bytes)
    await service.apply(fresh_admin, import_id=import_id, decisions=[])

    recipe = (await db_session.execute(select(Recipe))).scalar_one()
    owner = await db_session.get(User, recipe.owner_user_id)
    assert owner is not None and owner.email == "byly@example.com"
    assert recipe.scope == RecipeScope.HOUSEHOLD
    assert recipe.household_id == owner.household_id is not None


async def test_nieznany_zakres_w_pliku_to_422_a_nie_valueerror(
    db_session: AsyncSession, settings: Settings
) -> None:
    owner = await factories.create_user(db_session, email="z4@example.com")
    await factories.create_recipe(db_session, owner=owner, name="Zepsuty zakres")
    await factories.create_plan_day(db_session, owner=owner, day=DAY)
    service = _service(db_session, settings)
    archive_bytes = await _export(service, owner)
    importer = await factories.create_user(db_session, email="z5@example.com")

    unknown = _rewrite(
        archive_bytes,
        lambda doc: [row.update(scope="wszyscy") for row in doc["data"]["recipes"]],
    )
    with pytest.raises(TransferValidationError) as error:
        await service.dry_run(importer, filename="e.zip", data=unknown)
    assert error.value.status_code == 422 and "wszyscy" in error.value.message

    # `global` jest znany WYŁĄCZNIE przepisom: dla dnia planu to plik niezgodny z formatem.
    global_day = _rewrite(
        archive_bytes,
        lambda doc: [row.update(scope="global") for row in doc["data"]["plan_days"]],
    )
    with pytest.raises(TransferValidationError):
        await service.dry_run(importer, filename="e.zip", data=global_day)


def test_coerce_value_nieznany_enum_to_422_nie_valueerror() -> None:
    """Druga linia obrony w `apply` (dry-run nie jest jedyną drogą do `coerce_value`)."""
    day_scope = cast("Column[Any]", PlanDay.__table__.c.scope)
    recipe_scope = cast("Column[Any]", Recipe.__table__.c.scope)

    with pytest.raises(TransferValidationError) as error:
        coerce_value(day_scope, "global")

    assert error.value.status_code == 422
    assert coerce_value(day_scope, "household") == Scope.HOUSEHOLD
    assert coerce_value(recipe_scope, "global") == RecipeScope.GLOBAL
