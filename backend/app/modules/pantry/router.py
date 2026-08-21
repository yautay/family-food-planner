"""HTTP modułu pantry: `/pantry` (04_API §2).

Router nie zna reguł domenowych: waliduje wejście, woła serwis, mapuje widok na
schemat odpowiedzi. Widoczność egzekwuje serwis (04_API §3), więc nie ma tu
żadnego filtra po rodzinie.

`date.today()` mieszka w routerze, a nie w serwisie — czas wchodzi do logiki
parametrem, tak samo jak w module nutrition (ustalenie review R2).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, get_pantry_service
from app.modules.pantry.schemas import (
    PantryItemCreateRequest,
    PantryItemRead,
    PantryItemUpdateRequest,
    PantryListResponse,
    PantrySort,
)
from app.modules.pantry.service import PantryItemView, PantryService

ServiceDep = Annotated[PantryService, Depends(get_pantry_service)]


def _to_read(view: PantryItemView) -> PantryItemRead:
    """Widok serwisu → schemat odpowiedzi (produkt bywa `None`: pozycja retail)."""
    item = view.item
    return PantryItemRead(
        id=item.id,
        product_id=item.product_id,
        product_name=view.product.name if view.product is not None else None,
        category_id=view.category.id if view.category is not None else None,
        category_name=view.category.name if view.category is not None else None,
        measure_kind=view.product.measure_kind if view.product is not None else None,
        retail_product_id=item.retail_product_id,
        amount=item.amount,
        amount_unit=item.amount_unit,
        expiry_date=item.expiry_date,
        location=item.location,
        note=item.note,
        owner_user_id=item.owner_user_id,
        household_id=item.household_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def build_pantry_router() -> APIRouter:
    """Router `/pantry` — lista, dodanie, zmiana ilości/ważności, usunięcie."""
    router = APIRouter(prefix="/pantry", tags=["pantry"])

    @router.get("", response_model=PantryListResponse, summary="Stan spiżarni rodziny")
    async def list_items(
        user: CurrentUser,
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query(max_length=200)] = None,
        category_id: Annotated[int | None, Query(ge=1)] = None,
        sort: PantrySort = PantrySort.EXPIRY,
        expires_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    ) -> PantryListResponse:
        views, total = await service.list_items(
            user,
            limit=limit,
            offset=offset,
            today=date.today(),
            query=q,
            category_id=category_id,
            sort=sort,
            expires_within_days=expires_within_days,
        )
        return PantryListResponse(items=[_to_read(view) for view in views], total=total)

    @router.post(
        "",
        response_model=PantryItemRead,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie pozycji do spiżarni",
    )
    async def create_item(
        payload: PantryItemCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> PantryItemRead:
        return _to_read(await service.create_item(actor=user, payload=payload))

    @router.patch(
        "/{item_id}",
        response_model=PantryItemRead,
        summary="Zmiana ilości/ważności/lokalizacji/notatki (amount=0 = wyzerowanie)",
    )
    async def update_item(
        item_id: int,
        payload: PantryItemUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> PantryItemRead:
        view = await service.update_item(
            item_id, actor=user, changes=payload.model_dump(exclude_unset=True)
        )
        return _to_read(view)

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie pozycji spiżarni (każdy członek rodziny — D17)",
    )
    async def delete_item(item_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.delete_item(item_id, actor=user)

    return router
