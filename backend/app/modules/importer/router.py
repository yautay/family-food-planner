"""HTTP importera PDF: `/import/pdf`, `/import/jobs` i review (04_API §2).

Router waliduje wejście, woła serwis i mapuje wynik — zero logiki. Za tym jednym
prefiksem stoją DWA serwisy: `ImporterService` (upload, lista, usunięcie)
i `ReviewService` (staged, resolve, ai-suggest, approve, reject).

`POST /import/jobs/{id}/ai-suggest` jest JEDYNYM endpointem tego modułu
z własnym limitem tempa: każde wywołanie kosztuje realne pieniądze u dostawcy
modelu, a review z natury klika się szybko (karta B16 §Security). Limiter
wstrzykuje `create_app` — tym samym wzorcem co `/auth` i router publiczny.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from slowapi import Limiter

from app.core.deps import CurrentUser, get_import_review_service, get_importer_service
from app.modules.importer.models import ImportJob
from app.modules.importer.review_service import (
    IngredientDecision,
    IssueDecision,
    RecipeDecision,
    ReviewService,
    StagedIngredientView,
    StagedJobView,
    StagedRecipeView,
)
from app.modules.importer.schemas import (
    ApproveBlockerRead,
    ImportApproveRequest,
    ImportApproveResponse,
    ImportIssueRead,
    ImportJobDetail,
    ImportJobListResponse,
    ImportJobSummary,
    ImportResolveRequest,
    MealNutritionRead,
    StagedIngredientRead,
    StagedJobResponse,
    StagedRecipeRead,
)
from app.modules.importer.service import ImporterService

ServiceDep = Annotated[ImporterService, Depends(get_importer_service)]
ReviewDep = Annotated[ReviewService, Depends(get_import_review_service)]

#: Limit tempa asysty AI: przycisk „Zaproponuj z AI" wolno kliknąć kilka razy
#: pod rząd (poprawiam mapowania i pytam ponownie), ale nie w pętli.
AI_SUGGEST_RATE_LIMIT = "10/minute"

#: Domyślna nazwa, gdy klient nie poda żadnej — pusty string w tabeli jobów
#: byłby wierszem bez tożsamości dla człowieka.
FALLBACK_FILENAME = "jadlospis.pdf"


def _report_counts(job: ImportJob) -> dict[str, int | None]:
    """Skróty z `parse_report` na listę jobów; brak raportu = same `None`."""
    report: dict[str, Any] = job.parse_report or {}
    issues: dict[str, Any] = report.get("issues") or {}
    return {
        "days": report.get("days"),
        "meals": report.get("meals"),
        "staged_recipes": report.get("staged_recipes"),
        "ingredients": report.get("ingredients"),
        "blockers": issues.get("blocker"),
        "warnings": issues.get("warning"),
    }


def _to_summary(job: ImportJob) -> ImportJobSummary:
    return ImportJobSummary(
        id=job.id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        **_report_counts(job),
    )


def _to_detail(job: ImportJob) -> ImportJobDetail:
    return ImportJobDetail(
        id=job.id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        parse_report=job.parse_report,
        **_report_counts(job),
    )


def _to_ingredient(view: StagedIngredientView) -> StagedIngredientRead:
    """Wiersz składnika + nazwy produktów, żeby UI nie dociągał ich osobno."""
    item = view.ingredient
    return StagedIngredientRead(
        id=item.id,
        raw_name=item.raw_name,
        raw_qty=item.raw_qty,
        raw_unit=item.raw_unit,
        grams=item.grams,
        from_extras_section=item.from_extras_section,
        match_kind=item.match_kind,
        confidence=item.confidence,
        suggested_product_id=item.suggested_product_id,
        suggested_product_name=view.suggested_product.name if view.suggested_product else None,
        confirmed_product_id=item.confirmed_product_id,
        confirmed_product_name=view.confirmed_product.name if view.confirmed_product else None,
        create_new_product=item.create_new_product,
    )


def _to_staged_recipe(view: StagedRecipeView) -> StagedRecipeRead:
    row = view.recipe
    return StagedRecipeRead(
        id=row.id,
        name=row.name,
        day_label=row.day_label,
        meal_label=row.meal_label,
        instructions=row.instructions,
        comment=row.comment,
        declared_servings=row.declared_servings,
        resolved_servings=row.resolved_servings,
        resolution=row.resolution,
        target_recipe_id=row.target_recipe_id,
        pdf_macros=row.pdf_macros,
        meal=MealNutritionRead(
            computed_kcal=view.meal.computed_kcal,
            pdf_kcal=view.meal.pdf_kcal,
            delta_pct=view.meal.delta_pct,
            reason=view.meal.reason,
        ),
        ingredients=[_to_ingredient(item) for item in view.ingredients],
        issues=[ImportIssueRead.model_validate(issue) for issue in view.issues],
    )


def _to_staged_response(view: StagedJobView) -> StagedJobResponse:
    return StagedJobResponse(
        job=_to_detail(view.job),
        recipes=[_to_staged_recipe(recipe) for recipe in view.recipes],
        job_issues=[ImportIssueRead.model_validate(issue) for issue in view.job_issues],
        blockers=[
            ApproveBlockerRead(
                staged_recipe_id=blocker.staged_recipe_id,
                recipe_name=blocker.recipe_name,
                kind=blocker.kind,
                message=blocker.message,
            )
            for blocker in view.blockers
        ],
        ai_available=view.ai_available,
    )


def build_import_router(limiter: Limiter) -> APIRouter:
    """Router `/import` — upload PDF-a, przegląd jobów i ekran review (B15/B16)."""
    router = APIRouter(prefix="/import", tags=["import"])

    @router.post(
        "/pdf",
        response_model=ImportJobDetail,
        status_code=status.HTTP_201_CREATED,
        summary="Wgranie jadłospisu PDF (multipart; 25 MB, sniffing, parsowanie)",
    )
    async def upload_pdf(
        user: CurrentUser,
        service: ServiceDep,
        file: Annotated[UploadFile, File(description="Jadłospis PDF, maks. 25 MB")],
    ) -> ImportJobDetail:
        # Odczyt z sufitem: do RAM trafia najwyżej limit + 1 bajt, a plik ponad
        # limit dostaje 413 bez materializowania całości (wzorzec `upload_photo`).
        data = await file.read(service.max_pdf_bytes + 1)
        job = await service.upload(
            actor=user, filename=file.filename or FALLBACK_FILENAME, data=data
        )
        return _to_detail(job)

    @router.get("/jobs", response_model=ImportJobListResponse, summary="Lista importów")
    async def list_jobs(
        user: CurrentUser,
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ImportJobListResponse:
        jobs, total = await service.list_jobs(actor=user, limit=limit, offset=offset)
        return ImportJobListResponse(items=[_to_summary(job) for job in jobs], total=total)

    @router.get(
        "/jobs/{job_id}",
        response_model=ImportJobDetail,
        summary="Szczegóły importu razem z raportem parsowania",
    )
    async def get_job(job_id: int, user: CurrentUser, service: ServiceDep) -> ImportJobDetail:
        return _to_detail(await service.get_job(job_id, actor=user))

    @router.delete(
        "/jobs/{job_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie importu (kasuje staging i plik)",
    )
    async def delete_job(job_id: int, user: CurrentUser, service: ServiceDep) -> Response:
        await service.delete_job(job_id, actor=user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/jobs/{job_id}/staged",
        response_model=StagedJobResponse,
        summary="Stan review importu: dania, składniki, uwagi i blokady",
    )
    async def staged(job_id: int, user: CurrentUser, review: ReviewDep) -> StagedJobResponse:
        return _to_staged_response(await review.staged(job_id, actor=user))

    @router.post(
        "/jobs/{job_id}/resolve",
        response_model=StagedJobResponse,
        summary="Zapis decyzji review (mapowania, porcje, scalenia, uwagi)",
    )
    async def resolve(
        job_id: int, payload: ImportResolveRequest, user: CurrentUser, review: ReviewDep
    ) -> StagedJobResponse:
        view = await review.resolve(
            job_id,
            actor=user,
            recipes=[
                RecipeDecision(
                    staged_recipe_id=item.staged_recipe_id,
                    name=item.name,
                    resolution=item.resolution,
                    target_recipe_id=item.target_recipe_id,
                    resolved_servings=item.resolved_servings,
                )
                for item in payload.recipes
            ],
            ingredients=[
                IngredientDecision(
                    ingredient_id=item.ingredient_id,
                    confirmed_product_id=item.confirmed_product_id,
                    create_new_product=item.create_new_product,
                )
                for item in payload.ingredients
            ],
            issues=[
                IssueDecision(issue_id=item.issue_id, resolution=item.resolution)
                for item in payload.issues
            ],
        )
        return _to_staged_response(view)

    @router.post(
        "/jobs/{job_id}/ai-suggest",
        response_model=StagedJobResponse,
        summary="Propozycje AI: mapowania, duplikaty, podpowiedź porcji (503 bez klucza)",
    )
    @limiter.limit(AI_SUGGEST_RATE_LIMIT)
    async def ai_suggest(
        request: Request, job_id: int, user: CurrentUser, review: ReviewDep
    ) -> StagedJobResponse:
        # `request` jest tu WYMAGANY przez slowapi (czyta z niego adres klienta),
        # mimo że sam kod go nie używa — usunięcie parametru wysadza limiter.
        return _to_staged_response(await review.ai_suggest(job_id, actor=user))

    @router.post(
        "/jobs/{job_id}/approve",
        response_model=ImportApproveResponse,
        summary="Zatwierdzenie importu — tworzy przepisy, produkty i przeliczniki",
    )
    async def approve(
        job_id: int, payload: ImportApproveRequest, user: CurrentUser, review: ReviewDep
    ) -> ImportApproveResponse:
        result = await review.approve(job_id, actor=user, scope=payload.scope)
        return ImportApproveResponse(
            job=_to_detail(result.job),
            created_recipe_ids=result.created_recipe_ids,
            created_product_ids=result.created_product_ids,
            merged_count=result.merged_count,
            skipped_count=result.skipped_count,
            unit_weight_rows=result.unit_weight_rows,
        )

    @router.post(
        "/jobs/{job_id}/reject",
        response_model=ImportJobDetail,
        summary="Odrzucenie importu — kasuje staging i plik PDF",
    )
    async def reject(job_id: int, user: CurrentUser, review: ReviewDep) -> ImportJobDetail:
        return _to_detail(await review.reject(job_id, actor=user))

    return router
