"""HTTP modułu audit: `GET /audit` (04_API §2 — wyłącznie ADMIN).

Dziennik jest append-only, więc router celowo NIE ma metod POST/PATCH/DELETE.
Wpisy dokładają serwisy domenowe w swoich transakcjach.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_audit_service, require_admin
from app.modules.audit.schemas import AuditEntryRead, AuditListResponse
from app.modules.audit.service import AuditService

ServiceDep = Annotated[AuditService, Depends(get_audit_service)]


def build_audit_router() -> APIRouter:
    """Router `/audit` — przegląd dziennika operacji."""
    router = APIRouter(prefix="/audit", tags=["admin"], dependencies=[Depends(require_admin)])

    @router.get("", response_model=AuditListResponse, summary="Dziennik operacji")
    async def list_entries(
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        action: Annotated[str | None, Query(max_length=100)] = None,
        entity_type: Annotated[str | None, Query(max_length=100)] = None,
        user_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> AuditListResponse:
        entries, total = await service.list_entries(
            limit=limit,
            offset=offset,
            action=action,
            entity_type=entity_type,
            user_id=user_id,
        )
        return AuditListResponse(
            items=[AuditEntryRead.model_validate(entry) for entry in entries], total=total
        )

    return router
