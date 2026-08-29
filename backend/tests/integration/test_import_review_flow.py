"""Review importu przed zatwierdzeniem: rozstrzygnięcia, uwagi, blokady.

Ten plik pilnuje najważniejszego niezmiennika importu (02_DOMAIN §13.6):
**dopóki nie padnie `approve`, w danych aplikacji nie przybywa ANI JEDEN
wiersz.** Cała reszta — mapowania, porcje, scalenia, kalorie — żyje w czterech
tabelach stagingu i da się z niej wycofać jednym `reject`.

Staging budują fabryki, a nie prawdziwy PDF: scenariusze dotyczą LOGIKI
rozstrzygania, a odczyt plików ma własne testy (`test_pdf_corpus.py`,
`test_import_approve.py`).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.core.scope import Scope
from app.modules.catalog.models import CanonicalProduct, MeasureKind, ProductUnitWeight
from app.modules.importer.ai_assist import AiAssistant
from app.modules.importer.models import (
    ImportIssue,
    ImportIssueKind,
    ImportIssueSeverity,
    ImportJobStatus,
    StagedRecipeResolution,
)
from app.modules.importer.review_service import (
    IngredientDecision,
    IssueDecision,
    RecipeDecision,
    ReviewService,
)
from app.modules.recipes.models import Recipe, RecipeIngredient
from tests.factories import (
    create_category,
    create_import_issue,
    create_import_job,
    create_product,
    create_recipe,
    create_staged_ingredient,
    create_staged_recipe,
    create_user,
)

pytestmark = pytest.mark.integration


def _service(session: AsyncSession, *, api_key: str = "") -> ReviewService:
    """Serwis review z asystentem BEZ klucza — tryb deterministyczny (ADR-011)."""
    return ReviewService(
        session,
        uploads_dir="data/uploads",
        max_pdf_mb=25,
        assistant=AiAssistant(
            api_key=api_key, model="claude-opus-5", max_tokens=1024, timeout_s=5.0
        ),
    )


async def _domain_counts(session: AsyncSession) -> dict[str, int]:
    """Liczniki encji DOMENOWYCH — import nie ma prawa ich ruszyć przed approve."""
    return {
        label: int((await session.execute(select(func.count()).select_from(model))).scalar_one())
        for label, model in (
            ("recipes", Recipe),
            ("recipe_ingredients", RecipeIngredient),
            ("products", CanonicalProduct),
            ("unit_weights", ProductUnitWeight),
        )
    }


async def _issue_kinds(session: AsyncSession, job_id: int) -> list[str]:
    rows = (
        await session.execute(
            select(ImportIssue.kind).where(
                ImportIssue.import_job_id == job_id, ImportIssue.resolved_at.is_(None)
            )
        )
    ).scalars()
    return sorted(kind.value for kind in rows)


# --- niezmiennik §13.6 ---------------------------------------------------------------


async def test_pelny_resolve_nie_tworzy_zadnej_encji_domenowej(db_session: AsyncSession) -> None:
    """Punkt 1 z sekcji Tests karty B16: dopiero `approve` zapisuje cokolwiek.

    Scenariusz przechodzi CAŁE review — mapowanie, porcje, poprawkę nazwy —
    i sprawdza, że liczniki `recipes`/`products`/`unit_weights` nie drgnęły.
    """
    user = await create_user(db_session, email="review@example.com")
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(db_session, category=category, name="Cebula")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job, pdf_kcal=Decimal("635"))
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, raw_qty=Decimal("2"), raw_unit="Sztuka"
    )
    before = await _domain_counts(db_session)

    service = _service(db_session)
    await service.resolve(
        job.id,
        actor=user,
        recipes=[
            RecipeDecision(
                staged_recipe_id=dish.id,
                name="Gołąbki bez zawijania (pełna nazwa)",
                resolved_servings=7,
            )
        ],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=product.id)
        ],
        issues=[],
    )

    assert await _domain_counts(db_session) == before


async def test_pierwszy_resolve_przestawia_job_w_review(db_session: AsyncSession) -> None:
    """`parsed → in_review`: lista importów ma pokazać, że ktoś już przy tym siedzi."""
    user = await create_user(db_session, email="status@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)

    view = await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[RecipeDecision(staged_recipe_id=dish.id, resolved_servings=2)],
        ingredients=[],
        issues=[],
    )

    assert view.job.status is ImportJobStatus.IN_REVIEW


# --- uwagi pochodne ------------------------------------------------------------------


async def test_niezmapowany_skladnik_daje_blocker_ktory_znika_po_zmapowaniu(
    db_session: AsyncSession,
) -> None:
    """`unmapped_product` jest wyliczany ze stanu mapowań, więc rozwiązuje się sam."""
    user = await create_user(db_session, email="unmapped@example.com")
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(db_session, category=category, name="Cebula")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    ingredient = await create_staged_ingredient(db_session, staged_recipe=dish)
    service = _service(db_session)

    await service.resolve(job.id, actor=user, recipes=[], ingredients=[], issues=[])
    assert await _issue_kinds(db_session, job.id) == ["unmapped_product"]

    view = await service.resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=product.id)
        ],
        issues=[],
    )

    assert await _issue_kinds(db_session, job.id) == []
    assert view.blockers == []


async def test_rozjazd_kcal_daje_ostrzezenie_z_obiema_wartosciami(
    db_session: AsyncSession,
) -> None:
    """Rozjazd > 10% ⇒ `kcal_mismatch` z wyliczonymi i pdf-owymi kaloriami (AC 4)."""
    user = await create_user(db_session, email="kcal@example.com")
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(
        db_session, category=category, name="Cebula", kcal_100=Decimal("40")
    )
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job, pdf_kcal=Decimal("500"))
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, grams=Decimal("100")
    )

    await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=product.id)
        ],
        issues=[],
    )

    issue = (
        await db_session.execute(
            select(ImportIssue).where(ImportIssue.kind == ImportIssueKind.KCAL_MISMATCH)
        )
    ).scalar_one()
    assert issue.details["wyliczone"] == "40"
    assert issue.details["z_pdf"] == "500.0"
    assert issue.details["różnica_proc"].startswith("-92")


async def test_poprawa_mapowania_ponizej_progu_kasuje_ostrzezenie(
    db_session: AsyncSession,
) -> None:
    """Auto-rozwiązanie z karty B16: mismatch znika, gdy mapowanie się poprawi."""
    user = await create_user(db_session, email="kcalfix@example.com")
    category = await create_category(db_session, name="Warzywa")
    slaby = await create_product(
        db_session, category=category, name="Cebula", kcal_100=Decimal("40")
    )
    dobry = await create_product(
        db_session, category=category, name="Ryż biały", kcal_100=Decimal("500")
    )
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job, pdf_kcal=Decimal("500"))
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, grams=Decimal("100")
    )
    service = _service(db_session)

    await service.resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=slaby.id)
        ],
        issues=[],
    )
    assert "kcal_mismatch" in await _issue_kinds(db_session, job.id)

    await service.resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=dobry.id)
        ],
        issues=[],
    )

    assert await _issue_kinds(db_session, job.id) == []


async def test_ustalenie_porcji_zamyka_blocker_wieloporcyjnosci(
    db_session: AsyncSession,
) -> None:
    """`multi_portion_suspect` prosi o jedną informację — po jej podaniu jest zamknięty."""
    user = await create_user(db_session, email="portions@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    issue = await create_import_issue(db_session, job=job, staged_recipe=dish)

    await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[RecipeDecision(staged_recipe_id=dish.id, resolved_servings=7)],
        ingredients=[],
        issues=[],
    )

    await db_session.refresh(issue)
    assert issue.resolved_at is not None
    assert "7" in (issue.resolution or "")


async def test_uwage_da_sie_zamknac_recznie_wlasnym_uzasadnieniem(
    db_session: AsyncSession,
) -> None:
    """„To jednak osobny przepis" — duplikat zamyka człowiek, nie algorytm."""
    user = await create_user(db_session, email="issue@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    issue = await create_import_issue(
        db_session,
        job=job,
        staged_recipe=dish,
        kind=ImportIssueKind.DUPLICATE_RECIPE,
        severity=ImportIssueSeverity.WARNING,
    )

    await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[],
        issues=[IssueDecision(issue_id=issue.id, resolution="To osobny przepis.")],
    )

    await db_session.refresh(issue)
    assert issue.resolution == "To osobny przepis."
    assert issue.resolved_at is not None


# --- scalanie i pomijanie --------------------------------------------------------------


async def test_scalenie_wymaga_wskazania_przepisu(db_session: AsyncSession) -> None:
    """`merge_into_existing` bez celu to decyzja niepełna — 409, nie cichy zapis."""
    user = await create_user(db_session, email="merge@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)

    with pytest.raises(ConflictError):
        await _service(db_session).resolve(
            job.id,
            actor=user,
            recipes=[
                RecipeDecision(
                    staged_recipe_id=dish.id,
                    resolution=StagedRecipeResolution.MERGE_INTO_EXISTING,
                )
            ],
            ingredients=[],
            issues=[],
        )


async def test_scalenie_z_cudzym_przepisem_konczy_sie_404(db_session: AsyncSession) -> None:
    """Widoczność przepisu docelowego liczy moduł recipes — cudzy przepis to 404."""
    user = await create_user(db_session, email="mine@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    foreign = await create_recipe(db_session, owner=stranger, name="Cudze danie")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)

    with pytest.raises(NotFoundError):
        await _service(db_session).resolve(
            job.id,
            actor=user,
            recipes=[
                RecipeDecision(
                    staged_recipe_id=dish.id,
                    resolution=StagedRecipeResolution.MERGE_INTO_EXISTING,
                    target_recipe_id=foreign.id,
                )
            ],
            ingredients=[],
            issues=[],
        )


async def test_pominiete_danie_nie_generuje_blokad(db_session: AsyncSession) -> None:
    """`skip` znaczy „tego nie importujemy" — jego niezmapowane składniki nie blokują."""
    user = await create_user(db_session, email="skip@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    await create_staged_ingredient(db_session, staged_recipe=dish)

    view = await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[RecipeDecision(staged_recipe_id=dish.id, resolution=StagedRecipeResolution.SKIP)],
        ingredients=[],
        issues=[],
    )

    assert view.blockers == []


# --- widoczność i tryb bez AI ----------------------------------------------------------


async def test_cudzy_job_to_404_takze_w_review(db_session: AsyncSession) -> None:
    """Ta sama granica, co w BATCH_15: cudzy import nie istnieje (07_SECURITY §4)."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="ktos@example.com")
    job = await create_import_job(db_session, owner=owner)

    with pytest.raises(NotFoundError):
        await _service(db_session).staged(job.id, actor=stranger)


async def test_bez_klucza_api_asysta_odmawia_ale_reszta_dziala(
    db_session: AsyncSession,
) -> None:
    """Tryb deterministyczny (ADR-011): 503 z komunikatem PL, flow ręczny bez zmian."""
    user = await create_user(db_session, email="noai@example.com")
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(db_session, category=category, name="Cebula")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    ingredient = await create_staged_ingredient(db_session, staged_recipe=dish)
    service = _service(db_session)

    with pytest.raises(ServiceUnavailableError):
        await service.ai_suggest(job.id, actor=user)

    view = await service.resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=product.id)
        ],
        issues=[],
    )

    assert view.ai_available is False
    assert view.blockers == []


async def test_zatwierdzenie_z_nierozstrzygnietym_blockerem_to_409_bez_zapisow(
    db_session: AsyncSession,
) -> None:
    """Punkt 6 z sekcji Tests: 409 z listą blokad i ZERO encji domenowych (AC 5)."""
    user = await create_user(db_session, email="blocked@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    await create_staged_ingredient(db_session, staged_recipe=dish)
    await create_import_issue(db_session, job=job, staged_recipe=dish)
    before = await _domain_counts(db_session)

    with pytest.raises(ConflictError) as exc:
        await _service(db_session).approve(job.id, actor=user, scope=Scope.PRIVATE)

    kinds = {item["kind"] for item in exc.value.details["blockers"]}
    assert kinds == {"multi_portion_suspect", "unmapped_product"}
    assert await _domain_counts(db_session) == before
    await db_session.refresh(job)
    assert job.status is not ImportJobStatus.APPROVED


async def test_produkt_liczony_na_100_ml_daje_komunikat_zamiast_falszywych_kalorii(
    db_session: AsyncSession,
) -> None:
    """Gramatura z PDF-a nie przelicza się na 100 ml — i to widać w review, nie w cichym wyniku.

    Przeliczenie g → ml wymagałoby gęstości, której model nie ma (ADR-005).
    Zachowanie jest DOKŁADNIE takie samo, jak przy ręcznie wpisanym składniku
    w gramach dla produktu liczonego na 100 ml (`recipes/service.py`):
    ilość zapisuje się tak, jak ją podano, a wartości odżywcze są oznaczone
    jako niepoliczalne — zamiast liczby „mniej więcej".
    """
    user = await create_user(db_session, email="volume@example.com")
    category = await create_category(db_session, name="Nabiał")
    mleko = await create_product(
        db_session,
        category=category,
        name="Mleko 2%",
        measure_kind=MeasureKind.VOLUME,
        kcal_100=Decimal("50"),
    )
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job, pdf_kcal=Decimal("165"))
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, raw_name="Kefir", grams=Decimal("330")
    )

    view = await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=mleko.id)
        ],
        issues=[],
    )

    assert view.recipes[0].meal.computed_kcal is None
    assert "nie da się przeliczyć" in view.recipes[0].meal.reason
    # Brak wyliczenia NIE jest rozjazdem: `kcal_mismatch` nie ma prawa powstać.
    assert await _issue_kinds(db_session, job.id) == []


async def test_danie_scalane_z_istniejacym_nie_wymaga_mapowan(
    db_session: AsyncSession,
) -> None:
    """Ustalenie `/code-review`: `merge_into_existing` nie wnosi swoich składników.

    Danie uznane za duplikat nie tworzy przepisu, więc żądanie zmapowania jego
    ośmiu pozycji byłoby pracą bez odbiorcy — blokada `unmapped_product`
    obowiązuje wyłącznie dania, które MAJĄ powstać.
    """
    user = await create_user(db_session, email="mergemap@example.com")
    existing = await create_recipe(db_session, owner=user, name="Gołąbki z zeszłego tygodnia")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    await create_staged_ingredient(db_session, staged_recipe=dish)

    view = await _service(db_session).resolve(
        job.id,
        actor=user,
        recipes=[
            RecipeDecision(
                staged_recipe_id=dish.id,
                resolution=StagedRecipeResolution.MERGE_INTO_EXISTING,
                target_recipe_id=existing.id,
            )
        ],
        ingredients=[],
        issues=[],
    )

    assert view.blockers == []
    assert await _issue_kinds(db_session, job.id) == []
