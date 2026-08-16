"""Schematy odczytu dziennika (04_API §2 — `A /audit`).

Dziennik jest wyłącznie do czytania, więc nie ma tu schematów żądań zapisu:
wpisy powstają w serwisach domenowych przez `AuditService.record`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEntryRead(BaseModel):
    """Wpis dziennika widziany przez administratora."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    #: NULL po usunięciu konta, które wykonało operację (FK ON DELETE SET NULL).
    user_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    payload: dict[str, Any]
    created_at: datetime


class AuditListResponse(BaseModel):
    """Lista wpisów z paginacją (04_API §1)."""

    items: list[AuditEntryRead]
    total: int
