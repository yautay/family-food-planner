"""Import w bazie, która JUŻ coś ma: kolizje, zła wersja, rollback (karta B14 §Tests).

Trzy własności pilnowane tutaj są warunkiem zaufania do importu:

1. kolizję po kluczu naturalnym widać w raporcie ZANIM cokolwiek powstanie,
2. plik z niezgodną wersją kończy się czytelnym 422 i zerem zapisów,
3. błąd w środku `apply` cofa CAŁOŚĆ — baza wygląda jak przed importem.
"""

from __future__ import annotations

import json
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import utcnow
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct
from app.modules.catalog.units import AmountUnit
from app.modules.planning.models import PlanDay, PlanMeal
from app.modules.recipes.models import Recipe, RecipeIngredient
from app.modules.transfer.importer import TransferValidationError
from app.modules.transfer.schemas import (
    DATA_ENTRY_NAME,
    CollisionAction,
    CollisionDecision,
    TransferScope,
)
from app.modules.transfer.service import TransferService
from tests import factories

pytestmark = pytest.mark.integration


def _service(session: AsyncSession, settings: Settings) -> TransferService:
    return TransferService(session, uploads_dir=settings.uploads_dir, max_zip_mb=100)


def _rewrite(archive_bytes: bytes, document: dict[str, object]) -> bytes:
    """Ten sam ZIP z podmienionym `export.json` — materiał na uszkodzony plik."""
    buffer = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(archive_bytes)) as source,
        zipfile.ZipFile(buffer, "w") as target,
    ):
        for info in source.infolist():
            payload = (
                json.dumps(document).encode()
                if info.filename == DATA_ENTRY_NAME
                else source.read(info.filename)
            )
            target.writestr(info.filename, payload)
    return buffer.getvalue()


def _document(archive_bytes: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        loaded: dict[str, Any] = json.loads(archive.read(DATA_ENTRY_NAME))
    return loaded


async def _seed_and_export(session: AsyncSession, settings: Settings) -> tuple[bytes, User]:
    """Konto źródłowe z przepisem na cebuli + drugie konto, na które importujemy."""
    author = await factories.create_user(session, email="autor@example.com")
    category = await factories.create_category(session, name="Warzywa")
    cebula = await factories.create_product(session, category=category, name="Cebula")
    recipe = await factories.create_recipe(session, owner=author, name="Zupa cebulowa")
    await factories.create_ingredient(
        session, recipe=recipe, product=cebula, amount=Decimal("300.000")
    )

    exported = await _service(session, settings).export(
        author, scope=TransferScope.USER, app_version="test", now=utcnow()
    )
    archive_bytes = exported.path.read_bytes()
    importer = await factories.create_user(session, email="importujacy@example.com")
    return archive_bytes, importer


async def _count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_kolizja_produktu_jest_raportowana_przed_zapisem(
    db_session: AsyncSession, settings: Settings
) -> None:
    """„Cebula" już jest w katalogu globalnym — dry-run mówi o tym i niczego nie tworzy."""
    archive_bytes, importer = await _seed_and_export(db_session, settings)
    before = await _count(db_session, CanonicalProduct)

    _, report = await _service(db_session, settings).dry_run(
        importer, filename="export.zip", data=archive_bytes
    )

    collision = next(item for item in report.collisions if item.entity == "canonical_products")
    assert collision.name == "Cebula"
    assert collision.default is CollisionAction.USE_EXISTING
    assert await _count(db_session, CanonicalProduct) == before
    assert await _count(db_session, Recipe) == 1


async def test_use_existing_nie_duplikuje_produktu(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Domyślna decyzja podpina przepis pod istniejący produkt zamiast tworzyć drugi."""
    archive_bytes, importer = await _seed_and_export(db_session, settings)
    service = _service(db_session, settings)
    import_id, _ = await service.dry_run(importer, filename="e.zip", data=archive_bytes)

    await service.apply(importer, import_id=import_id, decisions=[])

    assert await _count(db_session, CanonicalProduct) == 1
    assert await _count(db_session, Recipe) == 2
    ingredients = (await db_session.execute(select(RecipeIngredient))).scalars().all()
    assert len({row.product_id for row in ingredients}) == 1


async def test_create_copy_tworzy_kopie_z_sufiksem(
    db_session: AsyncSession, settings: Settings
) -> None:
    """„Utwórz kopię" daje drugi produkt o nazwie z sufiksem i spójnym `normalized_name`."""
    archive_bytes, importer = await _seed_and_export(db_session, settings)
    service = _service(db_session, settings)
    import_id, report = await service.dry_run(importer, filename="e.zip", data=archive_bytes)
    collision = next(item for item in report.collisions if item.entity == "canonical_products")

    await service.apply(
        importer,
        import_id=import_id,
        decisions=[
            CollisionDecision(
                entity="canonical_products",
                source_id=collision.source_id,
                action=CollisionAction.CREATE_COPY,
            )
        ],
    )

    products = (
        (await db_session.execute(select(CanonicalProduct).order_by(CanonicalProduct.id)))
        .scalars()
        .all()
    )
    assert [row.name for row in products] == ["Cebula", "Cebula (import)"]
    assert products[1].normalized_name == "cebula (import)"


async def test_plik_z_inna_wersja_konczy_sie_422_i_zerem_zapisow(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Acceptance Criterion 7: czytelny komunikat po polsku, nie 500 i nie zapis."""
    archive_bytes, importer = await _seed_and_export(db_session, settings)
    document = _document(archive_bytes)
    document["schema_version"] = 999
    broken = _rewrite(archive_bytes, document)
    before = await _count(db_session, CanonicalProduct)

    with pytest.raises(TransferValidationError) as error:
        await _service(db_session, settings).dry_run(importer, filename="e.zip", data=broken)

    assert "wersji aplikacji" in error.value.message
    assert await _count(db_session, CanonicalProduct) == before


async def test_uszkodzona_referencja_cofa_caly_import(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Błąd w środku `apply` = zero zmian w bazie (Acceptance Criterion 5)."""
    archive_bytes, importer = await _seed_and_export(db_session, settings)
    document = _document(archive_bytes)
    # Składnik wskazuje produkt, którego w pliku nie ma — import musi paść,
    # a nie wstawić przepis bez składnika ani przypiąć losowy produkt.
    document["data"]["recipe_ingredients"][0]["product_id"] = 999_999
    broken = _rewrite(archive_bytes, document)

    service = _service(db_session, settings)
    import_id, _ = await service.dry_run(importer, filename="e.zip", data=broken)
    products_before = await _count(db_session, CanonicalProduct)
    recipes_before = await _count(db_session, Recipe)

    with pytest.raises(TransferValidationError):
        await service.apply(importer, import_id=import_id, decisions=[])

    assert await _count(db_session, CanonicalProduct) == products_before
    assert await _count(db_session, Recipe) == recipes_before
    assert await _count(db_session, RecipeIngredient) == 1


async def test_archiwum_z_path_traversal_jest_odrzucane(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Wpis `../` nie ma prawa dojść do rozpakowania (07_SECURITY §6)."""
    archive_bytes, importer = await _seed_and_export(db_session, settings)
    buffer = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(archive_bytes)) as source,
        zipfile.ZipFile(buffer, "w") as target,
    ):
        for info in source.infolist():
            target.writestr(info.filename, source.read(info.filename))
        target.writestr("../../wyciek.txt", b"zlosliwa zawartosc")

    with pytest.raises(TransferValidationError):
        await _service(db_session, settings).dry_run(
            importer, filename="zlo.zip", data=buffer.getvalue()
        )


async def test_plik_ktory_nie_jest_zipem_konczy_sie_422(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Sniffing po TREŚCI: PDF nazwany `.zip` nie przechodzi."""
    importer = await factories.create_user(db_session, email="ktos@example.com")
    with pytest.raises(TransferValidationError):
        await _service(db_session, settings).dry_run(
            importer, filename="export.zip", data=b"%PDF-1.7 to nie jest archiwum"
        )


async def test_import_wlasnego_eksportu_reuzywa_dnia_planu_i_nie_tyka_jego_posilkow(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Ten sam plik wgrany na TO SAMO konto scala dni planu, zamiast wywalać import.

    `plan_days` ma UNIQUE(owner_user_id, day), więc import własnego eksportu
    trafiłby w konflikt przy pierwszym dniu. Wiersz dnia jest więc REUŻYWANY.

    **Decyzja D22 (2026-08-30, wdrożona w REVIEW R4) zmieniła to, co dzieje się
    z jego posiłkami.** Do R4 dopisywały się od nowa — z uzasadnieniem „tak samo
    DOPISUJE instancjacja szablonu (B07)". Różnica, której to uzasadnienie nie
    widziało: szablon instancjuje CZŁOWIEK jednym kliknięciem i wie, co robi,
    a import przy każdym przebiegu doklejał komplet po cichu. Efekt zmierzono
    w BATCH_16 na `transfer.spec.ts`: po kilku pętlach eksport→import dzień miał
    1536 posiłków zamiast dwóch. Od R4 „użyj istniejącego" znaczy „zostaw ten
    wiersz i jego zawartość w spokoju" — posiłki reużytego dnia są POMIJANE.
    Sam przypadek „dopisz posiłki do istniejącego dnia" pozostaje uzasadniony,
    ale wymaga JAWNEJ decyzji użytkownika przy kolizji (poza zakresem D22).
    """
    author = await factories.create_user(db_session, email="autor@example.com")
    category = await factories.create_category(db_session, name="Warzywa")
    product = await factories.create_product(db_session, category=category, name="Cebula")
    day = await factories.create_plan_day(db_session, owner=author, day=date(2030, 6, 1))
    meal = await factories.create_plan_meal(db_session, plan_day=day, name="Obiad")
    await factories.create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("100.000"),
        amount_unit=AmountUnit.GRAM,
    )

    service = _service(db_session, settings)
    exported = await service.export(
        author, scope=TransferScope.USER, app_version="test", now=utcnow()
    )
    import_id, _ = await service.dry_run(author, filename="e.zip", data=exported.path.read_bytes())
    summary = await service.apply(author, import_id=import_id, decisions=[])

    assert summary.reused["plan_days"] == 1
    assert await _count(db_session, PlanDay) == 1
    # Dzień został reużyty, więc jego posiłek ZOSTAŁ TAKI, JAKI BYŁ (D22):
    # ani nie zniknął, ani nie doszedł jego duplikat.
    assert await _count(db_session, PlanMeal) == 1
    assert "plan_meals" not in summary.created
