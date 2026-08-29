"""Dziennik operacji — zapis (append-only) i przegląd dla administratora.

Kontrakt zapisu: `record()` NIE commituje. Wpis powstaje w tej samej transakcji,
co operacja, którą opisuje — brak wpisu ⇒ brak operacji i odwrotnie. Serwis
wołający robi jeden `commit()` na końcu.

Czego w `payload` być NIE MOŻE (07_SECURITY §8, karta B03 §Security): haseł,
hashy, tokenów sesji i pełnych payloadów żądań. Zapisujemy identyfikatory
i NAZWY zmienionych pól, nie ich wrażliwe wartości.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEntry


class AuditEntity(StrEnum):
    """Typy encji objętych dziennikiem (02_DOMAIN §12). Rozszerzają je kolejne batche."""

    USER = "user"
    HOUSEHOLD = "household"
    MEMBER_PROFILE = "member_profile"
    PRODUCT = "product"
    PRODUCT_CATEGORY = "product_category"
    #: Transfer nie ma własnej encji — wpis opisuje OPERACJĘ na zbiorze danych
    #: (02_DOMAIN §12: „eksport/import"), więc `entity_id` zostaje puste.
    TRANSFER = "transfer"
    #: Import PDF (BATCH_15) — `entity_id` to id joba, bo job JEST encją.
    IMPORT_JOB = "import_job"


class AuditAction(StrEnum):
    """Operacje zapisywane w dzienniku. Konwencja: `<encja>.<czasownik>`."""

    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"

    HOUSEHOLD_CREATE = "household.create"
    HOUSEHOLD_UPDATE = "household.update"
    HOUSEHOLD_DELETE = "household.delete"
    HOUSEHOLD_MEMBERS_UPDATE = "household.members_update"

    MEMBER_PROFILE_CREATE = "member_profile.create"
    MEMBER_PROFILE_UPDATE = "member_profile.update"
    MEMBER_PROFILE_DELETE = "member_profile.delete"

    # Katalog produktów (BATCH_04). `product.nutrition_update` i `product.verify`
    # niosą payload {before, after} — to na tych danych liczy silnik nutrition.
    PRODUCT_CREATE = "product.create"
    PRODUCT_UPDATE = "product.update"
    PRODUCT_NUTRITION_UPDATE = "product.nutrition_update"
    PRODUCT_VERIFY = "product.verify"
    PRODUCT_ARCHIVE = "product.archive"
    PRODUCT_RESTORE = "product.restore"
    PRODUCT_DELETE = "product.delete"

    PRODUCT_UNIT_WEIGHT_CREATE = "product_unit_weight.create"
    PRODUCT_UNIT_WEIGHT_UPDATE = "product_unit_weight.update"
    PRODUCT_UNIT_WEIGHT_DELETE = "product_unit_weight.delete"

    # Transfer danych (BATCH_14). Payload niesie WYŁĄCZNIE liczby i decyzje —
    # nigdy treści przenoszonych encji (07_SECURITY §8).
    TRANSFER_EXPORT = "transfer.export"
    TRANSFER_IMPORT = "transfer.import"

    # Import PDF (BATCH_15). Payload niesie WYŁĄCZNIE status i liczby —
    # nigdy treści jadłospisu ani nazw dań (07_SECURITY §8).
    IMPORT_UPLOAD = "import_job.upload"
    IMPORT_DELETE = "import_job.delete"

    CATEGORY_CREATE = "product_category.create"
    CATEGORY_UPDATE = "product_category.update"
    CATEGORY_DELETE = "product_category.delete"


class AuditService:
    """Zapis i odczyt dziennika. Nie ma metod edycji ani usuwania wpisów."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def record(
        self,
        *,
        action: AuditAction,
        entity_type: AuditEntity,
        entity_id: int | None,
        actor_id: int | None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Dołóż wpis do bieżącej transakcji (commit należy do serwisu wołającego)."""
        entry = AuditEntry(
            user_id=actor_id,
            action=action.value,
            entity_type=entity_type.value,
            entity_id=entity_id,
            payload=payload or {},
        )
        self._session.add(entry)
        return entry

    async def list_entries(
        self,
        *,
        limit: int,
        offset: int,
        action: str | None = None,
        entity_type: str | None = None,
        user_id: int | None = None,
    ) -> tuple[list[AuditEntry], int]:
        """Przegląd dziennika dla ADMIN-a: najnowsze pierwsze, z filtrami i paginacją."""
        statement = select(AuditEntry)
        if action:
            statement = statement.where(AuditEntry.action == action)
        if entity_type:
            statement = statement.where(AuditEntry.entity_type == entity_type)
        if user_id is not None:
            statement = statement.where(AuditEntry.user_id == user_id)

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    # `id` jako druga kolumna sortowania: wpisy z jednej transakcji
                    # mają identyczny `created_at` (server_default now()).
                    statement.order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total
