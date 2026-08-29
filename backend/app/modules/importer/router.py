"""HTTP importera PDF: `/import/pdf` i `/import/jobs` (04_API §2).

Router waliduje wejście, woła serwis i mapuje wynik — zero logiki. Endpointy
review (`/import/jobs/{id}/staged`, `resolve`, `approve`, `reject`) mapa API
rezerwuje dla BATCH_16 i świadomie NIE powstają tutaj: kontrakt w `generated.ts`
bez implementacji jest gorszy niż jego brak.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.core.deps import CurrentUser, get_importer_service
from app.modules.importer.models import ImportJob
from app.modules.importer.schemas import (
    ImportJobDetail,
    ImportJobListResponse,
    ImportJobSummary,
)
from app.modules.importer.service import ImporterService

ServiceDep = Annotated[ImporterService, Depends(get_importer_service)]

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


def build_import_router() -> APIRouter:
    """Router `/import` — upload PDF-a i przegląd własnych jobów."""
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

    return router
