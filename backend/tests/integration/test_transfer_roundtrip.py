"""Round-trip transferu: eksport → CZYSTA baza → import (08_TESTING §2, AC 6).

To jest test, dla którego istnieje cały batch: dane należą do użytkownika, więc
plik eksportu musi wystarczyć do ich odtworzenia bez SaaS (02_DOMAIN §11).
Sprawdzamy liczności i kluczowe pola per encja — nigdy identyfikatory, bo te
w nowej bazie są nowe z definicji.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scope import RecipeScope, Scope
from app.core.security import utcnow
from app.core.uploads import save_image
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, RetailProduct
from app.modules.catalog.units import AmountUnit
from app.modules.households.models import MemberProfile
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.pantry.models import PantryItem
from app.modules.planning.models import (
    DayTemplate,
    PlanDay,
    PlanItemServing,
    PlanMeal,
    PlanMealItem,
    WeekCycle,
    WeekTemplate,
)
from app.modules.recipes.models import Recipe, RecipeIngredient, RecipeRating
from app.modules.shopping.models import ShoppingList, ShoppingListItem, ShoppingRoundConfig
from app.modules.transfer.schemas import DATA_ENTRY_NAME, TransferScope
from app.modules.transfer.service import TransferService
from tests import factories
from tests.conftest import DB_TABLES

pytestmark = pytest.mark.integration

TODAY = date(2030, 3, 4)

#: Ile zdjęć i jak dużych składa się na paczkę ~50 MB (test dużego archiwum).
PHOTO_COUNT = 16
PHOTO_SIDE = 2600


@dataclass
class Seeded:
    """Uchwyty na dane źródłowe — do porównania po imporcie."""

    user: User
    recipe_photo: str
    retail_photo: str


def _jpeg_bytes(*, size: int = 64, color: tuple[int, int, int] = (200, 120, 40)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="JPEG")
    return buffer.getvalue()


async def _seed(session: AsyncSession, uploads_root: Path) -> Seeded:
    """Pełny przekrój domeny na jednym koncie: katalog, przepisy, plan, zakupy."""
    household = await factories.create_household(session, name="Kowalscy")
    user = await factories.create_user(session, email="anna@example.com", household=household)
    profile = await factories.create_member_profile(session, household=household, name="Anna")

    warzywa = await factories.create_category(session, name="Warzywa", position=1)
    nabial = await factories.create_category(session, name="Nabiał", position=2)
    cebula = await factories.create_product(
        session,
        category=warzywa,
        name="Cebula",
        kcal_100=Decimal("40.00"),
        glycemic_index=Decimal("15.0"),
    )
    jogurt = await factories.create_product(session, category=nabial, name="Jogurt naturalny")
    await factories.create_unit_weight(
        session, product=cebula, unit_label="łyżka", grams_per_unit=Decimal("15.00")
    )

    store = await factories.create_store(session, name="Biedronka")
    await factories.create_category_order(session, store=store, categories=[nabial, warzywa])
    retail_photo = save_image(_jpeg_bytes(), uploads_root=uploads_root, subdir="retail").path
    retail = await factories.create_retail_product(
        session, product=jogurt, store=store, photo_path=retail_photo
    )

    recipe_photo = save_image(
        _jpeg_bytes(color=(20, 160, 90)), uploads_root=uploads_root, subdir="recipes"
    ).path
    recipe = await factories.create_recipe(
        session,
        owner=user,
        name="Zupa cebulowa",
        instructions="Kroić, dusić.",
        base_servings=4,
        photo_path=recipe_photo,
    )
    await factories.create_ingredient(
        session, recipe=recipe, product=cebula, amount=Decimal("500.000")
    )
    tag = await factories.create_tag(session, name="obiad")
    await factories.attach_tag(session, recipe=recipe, tag=tag)
    await factories.create_rating(session, recipe=recipe, user=user, rating=5)

    # DWA cele z różnymi `valid_from` — ustalenie BATCH_13: utrata historii po
    # cichu przepisałaby statusy dni sprzed zmiany celu.
    await factories.create_goal(session, user=user, valid_from=date(2030, 1, 1))
    await factories.create_goal(
        session, user=user, valid_from=date(2030, 3, 1), kcal=Decimal("2400")
    )

    day = await factories.create_plan_day(session, owner=user, day=TODAY, title="Dzień testowy")
    meal = await factories.create_plan_meal(session, plan_day=day, name="Obiad")
    item = await factories.create_plan_item(session, meal=meal, recipe=recipe)
    await factories.create_item_split(session, item=item, profile=profile)
    await factories.create_plan_item(
        session,
        meal=meal,
        product=jogurt,
        amount=Decimal("200.000"),
        amount_unit=AmountUnit.GRAM,
        position=1,
    )

    day_template = await factories.create_day_template(
        session,
        owner=user,
        name="Dzień cebulowy",
        payload=factories.day_payload(
            meals=[
                factories.template_meal(
                    items=[
                        factories.template_recipe_item(recipe.id),
                        factories.template_product_item(jogurt.id),
                    ]
                )
            ]
        ),
    )
    week_template = await factories.create_week_template(
        session,
        owner=user,
        name="Tydzień bazowy",
        payload={
            "v": 1,
            "days": [{"offset": 0, "day": day_template.payload}],
        },
    )
    await factories.create_week_cycle(
        session, owner=user, name="Rotacja", template_ids=[week_template.id]
    )

    await factories.create_pantry_item(
        session, owner=user, product=cebula, expiry_date=TODAY + timedelta(days=5)
    )
    await factories.create_pantry_item(
        session, owner=user, retail_product_id=retail.id, amount=Decimal("400.000")
    )

    await factories.create_round_config(session, owner=user, name="Niedziela")
    shopping_list = await factories.create_shopping_list(
        session, owner=user, name="Zakupy testowe", store=store, public_token="x" * 43
    )
    await factories.create_shopping_list_item(
        session,
        shopping_list=shopping_list,
        category=warzywa,
        product=cebula,
        label="Cebula",
        needed_amount=Decimal("1000.000"),
    )
    await factories.create_shopping_list_item(
        session,
        shopping_list=shopping_list,
        category=nabial,
        retail_product=retail,
        label="Jogurt naturalny",
        needed_amount=Decimal("400.000"),
        position=1,
    )
    return Seeded(user=user, recipe_photo=recipe_photo, retail_photo=retail_photo)


async def _wipe(session: AsyncSession) -> None:
    """Czysta baza — dokładnie ten sam zestaw tabel, co izolacja testów."""
    await session.execute(text(f"TRUNCATE TABLE {', '.join(DB_TABLES)} RESTART IDENTITY CASCADE"))
    await session.commit()


async def _count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_round_trip_odtwarza_dane_na_czystej_bazie(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Eksport → TRUNCATE → import: liczności i kluczowe pola wracają bez ID."""
    uploads_root = Path(settings.uploads_dir)
    seeded = await _seed(db_session, uploads_root)
    service = TransferService(db_session, uploads_dir=settings.uploads_dir, max_zip_mb=100)

    exported = await service.export(
        seeded.user,
        scope=TransferScope.USER,
        app_version="test",
        now=utcnow(),
    )
    archive_bytes = exported.path.read_bytes()

    # Plik musi być czytelny standardowym narzędziem (Acceptance Criterion 1).
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        document = json.loads(archive.read(DATA_ENTRY_NAME))
        names = set(archive.namelist())
    assert document["schema_version"] == 1
    assert document["scope"] == "user"
    assert f"photos/{seeded.recipe_photo}" in names
    assert f"photos/{seeded.retail_photo}" in names
    # Żywy token publiczny NIE opuszcza bazy (ustalenie REVIEW R3).
    assert "public_token" not in json.dumps(document)

    await _wipe(db_session)
    fresh_household = await factories.create_household(db_session, name="Nowa rodzina")
    fresh_user = await factories.create_user(
        db_session, email="nowa@example.com", household=fresh_household
    )

    import_id, report = await service.dry_run(fresh_user, filename="export.zip", data=archive_bytes)
    assert report.collisions == []
    assert report.to_create["recipes"] == 1
    assert report.to_create["canonical_products"] == 2

    summary = await service.apply(fresh_user, import_id=import_id, decisions=[])
    assert summary.created["recipes"] == 1
    assert summary.photos_imported == 2

    # --- liczności per encja ------------------------------------------------
    assert await _count(db_session, CanonicalProduct) == 2
    assert await _count(db_session, RetailProduct) == 1
    assert await _count(db_session, Recipe) == 1
    assert await _count(db_session, RecipeIngredient) == 1
    assert await _count(db_session, RecipeRating) == 1
    assert await _count(db_session, PlanDay) == 1
    assert await _count(db_session, PlanMeal) == 1
    assert await _count(db_session, PlanMealItem) == 2
    assert await _count(db_session, PlanItemServing) == 1
    assert await _count(db_session, MemberProfile) == 1
    assert await _count(db_session, DayTemplate) == 1
    assert await _count(db_session, WeekTemplate) == 1
    assert await _count(db_session, WeekCycle) == 1
    assert await _count(db_session, PantryItem) == 2
    assert await _count(db_session, ShoppingRoundConfig) == 1
    assert await _count(db_session, ShoppingList) == 1
    assert await _count(db_session, ShoppingListItem) == 2

    # --- kluczowe pola ------------------------------------------------------
    recipe = (await db_session.execute(select(Recipe))).scalar_one()
    assert recipe.name == "Zupa cebulowa"
    assert recipe.base_servings == 4
    assert recipe.owner_user_id == fresh_user.id
    assert recipe.photo_path is not None
    assert recipe.photo_path != seeded.recipe_photo  # nowa, losowa nazwa pliku

    ingredient = (await db_session.execute(select(RecipeIngredient))).scalar_one()
    assert ingredient.amount == Decimal("500.000")
    assert ingredient.recipe_id == recipe.id
    product = await db_session.get(CanonicalProduct, ingredient.product_id)
    assert product is not None
    assert product.name == "Cebula"
    assert product.kcal_100 == Decimal("40.00")
    assert product.glycemic_index == Decimal("15.0")

    # Payload szablonu wskazuje NOWE identyfikatory, nie te z pliku.
    template = (await db_session.execute(select(DayTemplate))).scalar_one()
    # `payload` to JSONB, więc mypy widzi `object` — asercja formatu jest tu
    # częścią testu: gdyby import zapisał inny kształt, `cast` by to ukrył.
    meals = template.payload["meals"]
    assert isinstance(meals, list)
    items = meals[0]["items"]
    assert items[0]["recipe_id"] == recipe.id
    cycle = (await db_session.execute(select(WeekCycle))).scalar_one()
    week = (await db_session.execute(select(WeekTemplate))).scalar_one()
    assert cycle.template_ids == [week.id]

    # CAŁA historia celów, nie tylko cel bieżący (ustalenie BATCH_13).
    goals = (
        (await db_session.execute(select(UserNutritionGoal).order_by(UserNutritionGoal.valid_from)))
        .scalars()
        .all()
    )
    assert [goal.valid_from for goal in goals] == [date(2030, 1, 1), date(2030, 3, 1)]
    assert [goal.kcal for goal in goals] == [Decimal("2000"), Decimal("2400")]

    # Lista zakupowa wraca BEZ linku publicznego — udostępnia się ją na nowo.
    shopping_list = (await db_session.execute(select(ShoppingList))).scalar_one()
    assert shopping_list.public_token is None
    assert shopping_list.token_revoked is False
    assert shopping_list.store_id is not None


def _noise_jpeg(side: int) -> bytes:
    """Szum losowy — JPEG kompresuje go marnie, więc plik jest realnie duży."""
    image = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


async def test_duza_paczka_ze_zdjeciami_przechodzi_w_obie_strony(
    db_session: AsyncSession, settings: Settings
) -> None:
    """~50 MB zdjęć: eksport pakuje je na dysk, import re-enkoduje każde z osobna.

    Test pilnuje, że pipeline nie trzyma paczki w pamięci i nie przewraca się na
    limitach (Odroid H2 — karta B14, Implementation Notes). Zdjęcia to szum,
    bo obraz jednolity skompresowałby się do kilku kilobajtów i nic by nie mierzył.
    """
    uploads_root = Path(settings.uploads_dir)
    user = await factories.create_user(db_session, email="duzy@example.com")
    category = await factories.create_category(db_session, name="Nabiał")
    product = await factories.create_product(db_session, category=category, name="Jogurt")

    photos = 0
    for index in range(PHOTO_COUNT):
        saved = save_image(_noise_jpeg(PHOTO_SIDE), uploads_root=uploads_root, subdir="retail")
        await factories.create_retail_product(
            db_session,
            product=product,
            name=f"Wariant {index}",
            photo_path=saved.path,
        )
        photos += 1
    # Wariant sklepowy sam z siebie nie wchodzi do eksportu użytkownika (nikt go
    # nie używa), więc każde zdjęcie musi mieć powód: pozycję w spiżarni.
    retail_rows = (await db_session.execute(select(RetailProduct))).scalars().all()
    for retail in retail_rows:
        await factories.create_pantry_item(
            db_session, owner=user, retail_product_id=retail.id, amount=Decimal("400.000")
        )

    service = TransferService(db_session, uploads_dir=settings.uploads_dir, max_zip_mb=100)
    exported = await service.export(
        user, scope=TransferScope.USER, app_version="test", now=utcnow()
    )
    archive_bytes = exported.path.read_bytes()
    assert len(archive_bytes) > 40 * 1024 * 1024, "paczka miała być realnie duża"

    await _wipe(db_session)
    fresh = await factories.create_user(db_session, email="odbiorca@example.com")
    import_id, report = await service.dry_run(fresh, filename="e.zip", data=archive_bytes)
    assert report.photos == photos

    summary = await service.apply(fresh, import_id=import_id, decisions=[])
    assert summary.photos_imported == photos
    assert await _count(db_session, RetailProduct) == photos
    assert await _count(db_session, PantryItem) == photos


async def test_pozycja_planu_z_niewidocznym_przepisem_nie_psuje_pliku(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Przepis odebrany rodzinie po wstawieniu do planu nie może zablokować importu.

    FK RESTRICT trzyma pozycję planu przy życiu, ale `select_owned` już tego
    przepisu nie zwraca — gdyby pozycja została w pliku, jej referencja nie
    miałaby pokrycia i WŁASNY importer odrzuciłby eksport (422). Wyeksportowanie
    cudzego prywatnego przepisu byłoby z kolei wyciekiem, więc pozycja wypada.
    """
    household = await factories.create_household(db_session, name="Kowalscy")
    owner = await factories.create_user(db_session, email="a@example.com", household=household)
    other = await factories.create_user(db_session, email="b@example.com", household=household)
    shared = await factories.create_recipe(
        db_session, owner=other, name="Cudzy przepis", scope=Scope.HOUSEHOLD
    )
    day = await factories.create_plan_day(db_session, owner=owner, day=date(2030, 9, 1))
    meal = await factories.create_plan_meal(db_session, plan_day=day, name="Obiad")
    await factories.create_plan_item(db_session, meal=meal, recipe=shared)

    # Właściciel przepisu zabiera go rodzinie — pozycja planu zostaje (RESTRICT).
    shared.scope = RecipeScope.PRIVATE
    await db_session.commit()

    service = TransferService(db_session, uploads_dir=settings.uploads_dir, max_zip_mb=100)
    exported = await service.export(
        owner, scope=TransferScope.USER, app_version="test", now=utcnow()
    )
    archive_bytes = exported.path.read_bytes()
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        document = json.loads(archive.read(DATA_ENTRY_NAME))
    assert document["data"]["recipes"] == []
    assert document["data"]["plan_meal_items"] == []

    # Plik jest samowystarczalny: import na czystym koncie przechodzi.
    await _wipe(db_session)
    fresh = await factories.create_user(db_session, email="nowy@example.com")
    import_id, _ = await service.dry_run(fresh, filename="e.zip", data=archive_bytes)
    summary = await service.apply(fresh, import_id=import_id, decisions=[])
    assert summary.created["plan_days"] == 1
    assert "plan_meal_items" not in summary.created


async def test_kopia_rodziny_ma_wspolne_przepisy_ale_nie_cudze_prywatne(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Granica pliku „kopia danych rodziny" (decyzja **D26**).

    Kopię pobiera JEDEN członek rodziny, ale plik ma odtworzyć to, z czego
    rodzina korzysta — więc wchodzą do niego także CUDZE przepisy o zasięgu
    `household`. Prywatny przepis współdomownika NIE wchodzi: plik ląduje
    w mailu i w kopii zapasowej, a ADR-006 mówi, że prywatność obowiązuje także
    wewnątrz rodziny. Kryterium jest jedno: `ScopedQuery.owned_condition`.
    """
    household = await factories.create_household(db_session, name="Kowalscy")
    anna = await factories.create_user(db_session, email="anna@example.com", household=household)
    bartek = await factories.create_user(
        db_session, email="bartek@example.com", household=household
    )
    await factories.create_recipe(
        db_session, owner=bartek, name="Bigos rodzinny", scope=Scope.HOUSEHOLD
    )
    await factories.create_recipe(
        db_session, owner=bartek, name="Sekretna zapiekanka", scope=Scope.PRIVATE
    )
    await factories.create_recipe(db_session, owner=anna, name="Zupa Anny", scope=Scope.PRIVATE)
    # Cel żywieniowy jest parametrem KONKRETNEJ osoby — cudzy nie wychodzi.
    await factories.create_goal(db_session, user=bartek, valid_from=date(2030, 1, 1))
    await factories.create_goal(db_session, user=anna, valid_from=date(2030, 1, 1))

    service = TransferService(db_session, uploads_dir=settings.uploads_dir, max_zip_mb=100)
    exported = await service.export(
        anna, scope=TransferScope.USER, app_version="test", now=utcnow()
    )
    with zipfile.ZipFile(BytesIO(exported.path.read_bytes())) as archive:
        document = json.loads(archive.read(DATA_ENTRY_NAME))

    assert sorted(row["name"] for row in document["data"]["recipes"]) == [
        "Bigos rodzinny",
        "Zupa Anny",
    ]
    assert [row["user_id"] for row in document["data"]["user_nutrition_goals"]] == [anna.id]
    # Plik rodziny nie niesie kont — po wczytaniu wszystko należy do konta,
    # które je wczytało (`IdMap.actor_user_id`); UI mówi to wprost (D26).
    assert "users" not in document["data"]


async def test_d22_drugi_import_nie_dokłada_dzieci_reużytym_rodzicom(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Ten sam plik zaimportowany DWA razy nie podwaja zawartości rodzica (D22).

    Pathologia zmierzona w BATCH_16: „użyj istniejącego" zostawiało przepis
    w spokoju, ale jego składniki wjeżdżały od nowa (sekcje-dzieci nie mają
    klucza naturalnego). Przy pętli eksport→import rosło to wykładniczo —
    1536 składników w daniu o trzech.

    Asercja jest per sekcja, bo NIE każda sekcja ma tu zostać nietknięta:
    wiersz bez klucza naturalnego (wariant sklepowy, profil, pozycja spiżarni)
    to z definicji „utwórz kopię" i drugi import robi drugą kopię. Decyzja D22
    dotyczy wyłącznie DZIECI wiersza, który import rozpoznał jako ten sam.
    """
    uploads_root = Path(settings.uploads_dir)
    seeded = await _seed(db_session, uploads_root)
    service = TransferService(db_session, uploads_dir=settings.uploads_dir, max_zip_mb=100)

    exported = await service.export(
        seeded.user, scope=TransferScope.USER, app_version="test", now=utcnow()
    )
    archive_bytes = exported.path.read_bytes()

    # Import na TO SAMO konto — przepisy i szablony kolidują po nazwie, a dzień
    # planu scala się po `UNIQUE(owner_user_id, day)`.
    import_id, first_report = await service.dry_run(
        seeded.user, filename="export.zip", data=archive_bytes
    )
    assert first_report.collisions, "Import własnego pliku MUSI zgłosić kolizje nazw."
    await service.apply(seeded.user, import_id=import_id, decisions=[])

    after_first = {
        model: await _count(db_session, model)
        for model in (RecipeIngredient, RecipeRating, PlanMeal, PlanMealItem, PlanItemServing)
    }

    import_id, second_report = await service.dry_run(
        seeded.user, filename="export.zip", data=archive_bytes
    )
    summary = await service.apply(seeded.user, import_id=import_id, decisions=[])

    for model, before in after_first.items():
        assert await _count(db_session, model) == before, (
            f"{model.__name__}: reużyty rodzic dostał drugi komplet dzieci (D22)."
        )

    # Raport DRY-RUN mówi to samo, co zrobi zapis: dzieci reużytego przepisu
    # nie są obiecywane. Bez tego użytkownik czytałby liczby, które nie zajdą.
    assert "recipe_ingredients" not in second_report.to_create
    assert "recipe_ingredients" not in summary.created
    assert summary.reused.get("recipes"), "Przepis o tej samej nazwie ma być REUŻYTY."
