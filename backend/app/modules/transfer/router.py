"""HTTP modułu transfer: `/transfer/export` i `/transfer/import` (04_API §2).

Router nie zna formatu ani reguł kolizji — waliduje wejście, woła serwis
i mapuje wynik. Dwie rzeczy są tu świadome:

- **eksport jest POST-em**, mimo że nic nie zmienia w danych domenowych: buduje
  plik na dysku, zostawia wpis w dzienniku i nie ma prawa dać się wywołać
  z `<img src>` ani zostać zapamiętany przez cache przeglądarki,
- **plik odpowiedzi kasuje `BackgroundTask`** — paczka żyje dokładnie tyle, ile
  trwa jej wysyłka, a scratch nie rośnie po każdym kliknięciu.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.config import Settings, get_settings
from app.core.deps import CurrentUser, get_transfer_service
from app.modules.transfer.schemas import (
    DryRunReport,
    ImportApplyRequest,
    ImportSummary,
    TransferScope,
)
from app.modules.transfer.service import TransferService, cleanup_file

ServiceDep = Annotated[TransferService, Depends(get_transfer_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def build_transfer_router() -> APIRouter:
    """Router `/transfer` — eksport ZIP, dry-run importu i jego zastosowanie."""
    router = APIRouter(prefix="/transfer", tags=["transfer"])

    @router.post(
        "/export",
        summary="Eksport danych do archiwum ZIP",
        response_class=FileResponse,
        responses={200: {"content": {"application/zip": {}}, "description": "Archiwum eksportu"}},
    )
    async def export(
        user: CurrentUser,
        service: ServiceDep,
        settings: SettingsDep,
        scope: Annotated[TransferScope, Query(description="Zakres eksportu")] = (
            TransferScope.USER
        ),
    ) -> FileResponse:
        result = await service.export(
            user,
            scope=scope,
            app_version=settings.app_version,
            now=datetime.now(UTC),
        )
        return FileResponse(
            result.path,
            media_type="application/zip",
            filename=result.filename,
            background=BackgroundTask(cleanup_file, result.path),
            headers={"Cache-Control": "no-store"},
        )

    @router.post(
        "/import",
        response_model=DryRunReport,
        summary="Wgranie archiwum i raport DRY-RUN (nic nie zapisuje)",
    )
    async def dry_run(
        user: CurrentUser,
        service: ServiceDep,
        settings: SettingsDep,
        file: Annotated[UploadFile, File(description="Archiwum ZIP z eksportu")],
    ) -> DryRunReport:
        # Odczyt z sufitem: do RAM trafia najwyżej limit + 1 bajt, a plik ponad
        # limit dostaje 413 bez materializowania całości (wzorzec `upload_photo`).
        limit = settings.transfer_max_zip_mb * 1024 * 1024
        data = await file.read(limit + 1)
        import_id, report = await service.dry_run(
            user, filename=file.filename or "export.zip", data=data
        )
        return DryRunReport(
            import_id=import_id,
            schema_version=1,
            scope=report.scope,
            exported_at=report.exported_at,
            app_version=report.app_version,
            to_create=report.to_create,
            collisions=report.collisions,
            warnings=report.warnings,
            photos=report.photos,
        )

    @router.post(
        "/import/{import_id}/apply",
        response_model=ImportSummary,
        summary="Zastosowanie importu z decyzjami dla kolizji",
    )
    async def apply(
        import_id: str,
        payload: ImportApplyRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> ImportSummary:
        return await service.apply(user, import_id=import_id, decisions=payload.decisions)

    return router
