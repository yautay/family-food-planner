"""Zatwierdzenie i odrzucenie importu na REALNYM `dieta.pdf` (08_TESTING §2.10).

Round-trip idzie przez cały pion: upload pliku z korpusu → parsowanie →
rozstrzygnięcia review → `approve` → prawdziwy przepis z prawdziwymi ilościami.
Atrapa PDF-a przetestowałaby wyłącznie ścieżkę błędu, więc korzystamy z tego
samego pliku, na którym stoją testy korpusowe.

Bohaterem jest **gołąbki z `dieta.pdf`** — przypadek z 01_PDF_AUDIT §5.1
(3305 g składników, 635 kcal, „Przepis na 7 porcji") razem z sekcją `Produkty`
(ziemniaki 225 g podane NA PORCJĘ). To jedyne miejsce w projekcie, w którym
obie te reguły spotykają się w jednym przepisie.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError
from app.core.scope import Scope
from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.catalog.models import (
    CanonicalProduct,
    ProductCategory,
    ProductUnitWeight,
    VerificationStatus,
)
from app.modules.catalog.naming import normalize_name
from app.modules.importer.ai_assist import AiAssistant
from app.modules.importer.models import (
    ImportIssue,
    ImportJob,
    ImportJobStatus,
    StagedIngredient,
    StagedRecipe,
    StagedRecipeResolution,
)
from app.modules.importer.review_service import (
    UNIT_WEIGHT_SOURCE,
    IngredientDecision,
    RecipeDecision,
    ReviewService,
)
from app.modules.importer.service import ImporterService
from app.modules.recipes.models import Recipe, RecipeIngredient, RecipeSource
from app.modules.recipes.service import RecipesService
from tests.factories import create_category, create_product, create_recipe, create_user

pytestmark = pytest.mark.integration

CORPUS_DIR = Path(__file__).resolve().parents[3] / "data" / "source_pdfs"
GOLABKI = "Gołąbki bez zawijania"

#: Wartości „na 100 g" bliskie tabelom żywieniowym — po to, żeby wyliczone
#: kalorie porcji wyszły w okolicy 635 kcal z dokumentu, a nie dlatego, że
#: ktoś dobrał liczby pod asercję. Rozjazd z PDF-em ma zostać poniżej progu 10%.
GOLABKI_KCAL_100 = {
    "Cebula": Decimal("40"),
    "Jajko": Decimal("143"),
    "Kapusta włoska": Decimal("25"),
    "Masło klarowane": Decimal("876"),
    "Passata": Decimal("30"),
    "Ryż biały": Decimal("360"),
    "Łopatka wieprzowa": Decimal("270"),
    "Ziemniak": Decimal("77"),
}


def _review(session: AsyncSession) -> ReviewService:
    """Serwis review bez klucza AI — tryb deterministyczny (ADR-011)."""
    settings = get_settings()
    return ReviewService(
        session,
        uploads_dir=settings.uploads_dir,
        max_pdf_mb=settings.pdf_max_upload_mb,
        assistant=AiAssistant(api_key="", model="claude-opus-5", max_tokens=512, timeout_s=5.0),
    )


async def _upload_diet(session: AsyncSession, user: User) -> ImportJob:
    """Wgraj i sparsuj prawdziwy `dieta.pdf` — dokładnie tak, jak robi to endpoint."""
    settings = get_settings()
    service = ImporterService(
        session, uploads_dir=settings.uploads_dir, max_pdf_mb=settings.pdf_max_upload_mb
    )
    return await service.upload(
        actor=user, filename="dieta.pdf", data=(CORPUS_DIR / "dieta.pdf").read_bytes()
    )


async def _staged(session: AsyncSession, job: ImportJob) -> list[StagedRecipe]:
    rows = (
        await session.execute(
            select(StagedRecipe)
            .where(StagedRecipe.import_job_id == job.id)
            .order_by(StagedRecipe.id)
        )
    ).scalars()
    return list(rows)


async def _ingredients(session: AsyncSession, dish: StagedRecipe) -> list[StagedIngredient]:
    rows = (
        await session.execute(
            select(StagedIngredient)
            .where(StagedIngredient.staged_recipe_id == dish.id)
            .order_by(StagedIngredient.id)
        )
    ).scalars()
    return list(rows)


async def _category(session: AsyncSession) -> ProductCategory:
    """Kategoria „Inne" — wymaga jej ścieżka `create_new_product`; idempotentnie."""
    existing = (
        await session.execute(select(ProductCategory).where(ProductCategory.name == "Inne"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return await create_category(session, name="Inne")


async def _product(
    session: AsyncSession,
    *,
    category: ProductCategory,
    name: str,
    kcal_100: Decimal | None,
) -> CanonicalProduct:
    """Produkt katalogu; idempotentnie, bo `normalized_name` jest unikatem globalnym."""
    existing = (
        await session.execute(
            select(CanonicalProduct).where(CanonicalProduct.normalized_name == normalize_name(name))
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return await create_product(session, category=category, name=name, kcal_100=kcal_100)


async def _map_golabki(
    session: AsyncSession, job: ImportJob, *, with_values: bool
) -> tuple[StagedRecipe, list[IngredientDecision], list[RecipeDecision]]:
    """Zmapuj składniki gołąbków na produkty; resztę dań posiłkowych pomiń."""
    category = await _category(session)
    staged = await _staged(session, job)
    golabki = next(row for row in staged if row.name == GOLABKI)

    decisions: list[IngredientDecision] = []
    for item in await _ingredients(session, golabki):
        product = await _product(
            session,
            category=category,
            name=item.raw_name,
            kcal_100=GOLABKI_KCAL_100[item.raw_name] if with_values else None,
        )
        decisions.append(IngredientDecision(ingredient_id=item.id, confirmed_product_id=product.id))

    skips = [
        RecipeDecision(staged_recipe_id=row.id, resolution=StagedRecipeResolution.SKIP)
        for row in staged
        if row.id != golabki.id
    ]
    return golabki, decisions, skips


# --- happy path -----------------------------------------------------------------------


async def test_zatwierdzenie_golabkow_tworzy_przepis_na_siedem_porcji(
    db_session: AsyncSession,
) -> None:
    """Punkt 2 z sekcji Tests karty B16 — najważniejszy scenariusz batcha.

    Sprawdzamy naraz cztery rzeczy, które muszą wyjść razem albo wcale:
    `base_servings=7`, `source=pdf_import`, `import_job_id` i to, że ziemniaki
    z sekcji `Produkty` weszły do przepisu PRZEMNOŻONE przez liczbę porcji —
    czyli że na talerzu jest ich znowu 225 g.
    """
    user = await create_user(db_session, email="approve@example.com")
    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)

    await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    result = await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    assert len(result.created_recipe_ids) == 1
    recipe = (
        await db_session.execute(select(Recipe).where(Recipe.id == result.created_recipe_ids[0]))
    ).scalar_one()
    assert recipe.name == GOLABKI
    assert recipe.base_servings == 7
    assert recipe.source is RecipeSource.PDF_IMPORT
    assert recipe.import_job_id == job.id

    amounts = {
        row.product_id: row.amount
        for row in (
            await db_session.execute(
                select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
            )
        ).scalars()
    }
    products = {
        row.id: row.name
        for row in (
            await db_session.execute(
                select(CanonicalProduct).where(CanonicalProduct.id.in_(amounts))
            )
        ).scalars()
    }
    by_name = {products[pid]: amount for pid, amount in amounts.items()}

    assert by_name["Kapusta włoska"] == Decimal("1500.000")
    # 225 g na porcję x 7 porcji — po podzieleniu przez `base_servings` wróci 225 g.
    assert by_name["Ziemniak"] == Decimal("1575.000")


async def test_kalorie_porcji_golabkow_zgadzaja_sie_z_jadlospisem(
    db_session: AsyncSession,
) -> None:
    """635 kcal z dokumentu wobec wyliczenia silnika — rozjazd poniżej progu 10%.

    To jest jedyny test, który sprawdza CAŁĄ ścieżkę liczbową importu: gramatura
    z PDF-a → skalowanie sekcji `Produkty` → `base_servings` → adapter → silnik.
    Pomyłka w którymkolwiek kroku wyjdzie tu jako rozjazd o dziesiątki procent.
    """
    user = await create_user(db_session, email="kcalgolabki@example.com")
    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)

    view = await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    golabki_view = next(item for item in view.recipes if item.recipe.name == GOLABKI)

    assert golabki_view.meal.pdf_kcal == Decimal("635.0")
    assert golabki_view.meal.computed_kcal is not None
    assert Decimal("570") < golabki_view.meal.computed_kcal < Decimal("700")
    assert golabki_view.meal.delta_pct is not None
    assert abs(golabki_view.meal.delta_pct) < Decimal("10")

    result = await review.approve(job.id, actor=user, scope=Scope.PRIVATE)
    portions = await RecipesService(db_session).portion_values(result.created_recipe_ids)
    portion_kcal = portions[result.created_recipe_ids[0]].portion.kcal

    # Przepis po zapisie liczy TO SAMO, co review przed zatwierdzeniem.
    assert abs(portion_kcal - golabki_view.meal.computed_kcal) < Decimal("1")


async def test_zatwierdzenie_uczy_przelicznikow_jednostek_domowych(
    db_session: AsyncSession,
) -> None:
    """Punkt 3 z sekcji Tests (§5.2): pary ilość x jednostka x gramy → mediana.

    UWAGA — odstępstwo od przykładu z karty: `Cebula, 2 x Sztuka (210 g)` NIE
    zakłada wiersza `(Cebula, sztuka, 105)`. Etykieta „szt." jest w katalogu
    ZAREZERWOWANA (`UNIT_LABEL_RESERVED`, B04): mostkiem sztuka → gram jest
    `piece_weight_g` produktu (ADR-005), którego wolno dotknąć wyłącznie
    ADMIN-owi (D15). Import uczy więc przeliczników jednostek DOMOWYCH:
    łyżeczka, szklanka, woreczek.
    """
    user = await create_user(db_session, email="units@example.com")
    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)

    await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    rows = (
        await db_session.execute(
            select(ProductUnitWeight, CanonicalProduct.name).join(
                CanonicalProduct, CanonicalProduct.id == ProductUnitWeight.product_id
            )
        )
    ).all()
    learned = {name: (row.unit_label, row.grams_per_unit, row.source) for row, name in rows}

    assert learned["Masło klarowane"] == ("łyżeczka", Decimal("6.00"), UNIT_WEIGHT_SOURCE)
    assert learned["Passata"] == ("szklanka", Decimal("240.00"), UNIT_WEIGHT_SOURCE)
    assert learned["Ryż biały"] == ("woreczek", Decimal("100.00"), UNIT_WEIGHT_SOURCE)
    assert "Cebula" not in learned


async def test_kolejny_import_laczy_probki_w_nowa_mediane(db_session: AsyncSession) -> None:
    """Wiersz nauczony wcześniej dostaje NOWĄ medianę, a nie drugi wiersz."""
    user = await create_user(db_session, email="units2@example.com")
    category = await _category(db_session)
    passata = await create_product(db_session, category=category, name="Passata")
    db_session.add(
        ProductUnitWeight(
            product_id=passata.id,
            unit_label="szklanka",
            grams_per_unit=Decimal("200.00"),
            source=UNIT_WEIGHT_SOURCE,
            samples_count=1,
        )
    )
    await db_session.commit()

    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)
    await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    rows = (
        await db_session.execute(
            select(ProductUnitWeight).where(ProductUnitWeight.unit_label == "szklanka")
        )
    ).scalars()
    weights = list(rows)

    assert len(weights) == 1
    assert weights[0].grams_per_unit == Decimal("220.00")
    assert weights[0].samples_count == 2


async def test_recznie_wpisany_przelicznik_jest_nietykalny(db_session: AsyncSession) -> None:
    """Człowiek wygrywa z pomiarem: wiersz o innym źródle zostaje bez zmian.

    Implementation Notes karty B16: „wpisów `source='manual'` NIE nadpisywać".
    Ochronę rozszerzamy na wiersze BEZ źródła, bo dziś powstają właśnie tak —
    ręcznie, przez `POST /products/{id}/unit-weights`.
    """
    user = await create_user(db_session, email="manual@example.com")
    category = await _category(db_session)
    passata = await create_product(db_session, category=category, name="Passata")
    db_session.add(
        ProductUnitWeight(
            product_id=passata.id,
            unit_label="szklanka",
            grams_per_unit=Decimal("250.00"),
            source="manual",
            samples_count=1,
        )
    )
    await db_session.commit()

    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)
    await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    row = (
        await db_session.execute(
            select(ProductUnitWeight).where(ProductUnitWeight.unit_label == "szklanka")
        )
    ).scalar_one()

    assert row.grams_per_unit == Decimal("250.00")
    assert row.samples_count == 1


# --- produkty zakładane importem ------------------------------------------------------


async def test_flaga_zaloz_nowy_tworzy_produkty_unverified(db_session: AsyncSession) -> None:
    """Produkty z importu powstają jako UNVERIFIED — wartości uzupełnia ADMIN (§4.9)."""
    user = await create_user(db_session, email="newproducts@example.com")
    await _category(db_session)
    job = await _upload_diet(db_session, user)
    staged = await _staged(db_session, job)
    golabki = next(row for row in staged if row.name == GOLABKI)
    review = _review(db_session)

    await review.resolve(
        job.id,
        actor=user,
        recipes=[
            RecipeDecision(staged_recipe_id=row.id, resolution=StagedRecipeResolution.SKIP)
            for row in staged
            if row.id != golabki.id
        ],
        ingredients=[
            IngredientDecision(ingredient_id=item.id, create_new_product=True)
            for item in await _ingredients(db_session, golabki)
        ],
        issues=[],
    )
    result = await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    products = (
        await db_session.execute(
            select(CanonicalProduct).where(CanonicalProduct.id.in_(result.created_product_ids))
        )
    ).scalars()
    created = list(products)

    assert len(created) == 8
    assert all(row.verification_status is VerificationStatus.UNVERIFIED for row in created)
    assert {row.name for row in created} == set(GOLABKI_KCAL_100)


# --- scalanie, pomijanie, odrzucenie ---------------------------------------------------


async def test_scalenie_nie_tworzy_duplikatu_przepisu(db_session: AsyncSession) -> None:
    """Punkt 4 z sekcji Tests: `merge_into_existing` nie dokłada nowego przepisu."""
    user = await create_user(db_session, email="mergeapprove@example.com")
    existing = await create_recipe(db_session, owner=user, name="Gołąbki z zeszłego tygodnia")
    job = await _upload_diet(db_session, user)
    golabki, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)

    await review.resolve(
        job.id,
        actor=user,
        recipes=[
            *skips,
            RecipeDecision(
                staged_recipe_id=golabki.id,
                resolution=StagedRecipeResolution.MERGE_INTO_EXISTING,
                target_recipe_id=existing.id,
            ),
        ],
        ingredients=mappings,
        issues=[],
    )
    result = await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    recipes = int((await db_session.execute(select(func.count()).select_from(Recipe))).scalar_one())
    assert result.created_recipe_ids == []
    assert result.merged_count == 1
    assert recipes == 1
    # Przelicznikom scalenie nie przeszkadza: próbki opisują PRODUKT, nie przepis.
    assert result.unit_weight_rows > 0


async def test_odrzucenie_kasuje_staging_i_plik_z_dysku(db_session: AsyncSession) -> None:
    """Punkt 5 z sekcji Tests: po `reject` zostaje sam job jako ślad decyzji."""
    user = await create_user(db_session, email="reject@example.com")
    job = await _upload_diet(db_session, user)
    path = Path(get_settings().uploads_dir) / job.file_path
    assert path.is_file()

    result = await _review(db_session).reject(job.id, actor=user)

    assert result.status is ImportJobStatus.REJECTED
    assert not path.exists()
    for model in (StagedRecipe, StagedIngredient, ImportIssue):
        remaining = int(
            (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
        )
        assert remaining == 0, f"{model.__name__} przetrwał odrzucenie importu"
    # Job zostaje: `DELETE /import/jobs/{id}` nie przyjmuje statusów rozstrzygniętych.
    assert (
        int((await db_session.execute(select(func.count()).select_from(ImportJob))).scalar_one())
        == 1
    )


async def test_dziennik_notuje_zatwierdzenie_i_odrzucenie(db_session: AsyncSession) -> None:
    """Audyt importu niesie LICZBY, nigdy nazw dań (07_SECURITY §8)."""
    user = await create_user(db_session, email="audit@example.com")
    approved = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, approved, with_values=True)
    review = _review(db_session)
    await review.resolve(approved.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    await review.approve(approved.id, actor=user, scope=Scope.PRIVATE)

    rejected = await _upload_diet(db_session, user)
    await review.reject(rejected.id, actor=user)

    entries = {
        entry.action: entry.payload
        for entry in (
            await db_session.execute(
                select(AuditEntry).where(
                    AuditEntry.action.in_(["import_job.approve", "import_job.reject"])
                )
            )
        ).scalars()
    }

    assert entries["import_job.approve"]["recipes_created"] == 1
    assert entries["import_job.approve"]["recipes_skipped"] == 12
    assert entries["import_job.reject"]["staged_recipes_removed"] == 13
    payload_text = str(entries)
    assert GOLABKI not in payload_text


async def test_zatwierdzony_job_nie_da_sie_zatwierdzic_drugi_raz(
    db_session: AsyncSession,
) -> None:
    """Import jest jednorazowy: powtórka zrobiłaby drugi komplet przepisów."""
    user = await create_user(db_session, email="twice@example.com")
    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)
    await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    with pytest.raises(ConflictError):
        await review.approve(job.id, actor=user, scope=Scope.PRIVATE)


async def test_staging_zatwierdzonego_jobu_zostaje_jako_metadane(
    db_session: AsyncSession,
) -> None:
    """03_DATABASE §12: `pdf_kcal`/`pdf_macros` są metadanymi walidacyjnymi.

    Prawdą aplikacji są wartości wyliczone z produktów kanonicznych (ADR-011),
    ale liczby z jadłospisu zostają — bez nich nie da się już nigdy sprawdzić,
    czy import był wierny dokumentowi.
    """
    user = await create_user(db_session, email="metadata@example.com")
    job = await _upload_diet(db_session, user)
    _, mappings, skips = await _map_golabki(db_session, job, with_values=True)
    review = _review(db_session)
    await review.resolve(job.id, actor=user, recipes=skips, ingredients=mappings, issues=[])
    await review.approve(job.id, actor=user, scope=Scope.PRIVATE)

    golabki = next(row for row in await _staged(db_session, job) if row.name == GOLABKI)

    assert golabki.pdf_kcal == Decimal("635.0")
    assert golabki.pdf_macros is not None
    assert golabki.pdf_macros["W"] == "71.7"
