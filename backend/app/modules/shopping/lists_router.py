"""HTTP list zakupowych: `/shopping/lists/*` (04_API §2).

Router nie zna reguł domenowych — waliduje wejście, woła serwis, mapuje widok.
`datetime.now(UTC)` mieszka TUTAJ (wzorzec z B10): czas wchodzi do logiki
parametrem, więc serwis da się przetestować bez podmieniania zegara.

Osobny plik od `router.py`, bo osobny serwis: generacje to droga plan → podgląd,
listy to życie gotowej listy w sklepie (patrz `lists_service.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, get_shopping_lists_service
from app.modules.shopping.lists_service import (
    ListSection,
    ShoppingListDetail,
    ShoppingListsService,
    ShoppingListSummary,
)
from app.modules.shopping.schemas import (
    AcceptToPantryResponse,
    ListItemUpdateRequest,
    ListSectionRead,
    ListUpdateRequest,
    ShareCreateRequest,
    ShareRead,
    ShoppingListDetailRead,
    ShoppingListItemRead,
    ShoppingListsResponse,
    ShoppingListStatus,
    ShoppingListSummaryRead,
)

ServiceDep = Annotated[ShoppingListsService, Depends(get_shopping_lists_service)]

SHARE_DESCRIPTION = (
    "Generuje NOWY publiczny token (`secrets.token_urlsafe(32)`, 43 znaki "
    "base64url) i ustawia ważność listy. Ponowne udostępnienie zawsze tworzy "
    "nowy link — odwołany nie wraca do życia (ADR-010)."
)


def _section_read(section: ListSection) -> ListSectionRead:
    return ListSectionRead(
        category_id=section.category_id,
        category_name=section.category_name,
        items=[ShoppingListItemRead.model_validate(item) for item in section.items],
    )


def _detail_read(detail: ShoppingListDetail) -> ShoppingListDetailRead:
    shopping_list = detail.shopping_list
    return ShoppingListDetailRead(
        id=shopping_list.id,
        generation_id=shopping_list.generation_id,
        name=shopping_list.name,
        round_name=shopping_list.round_name,
        store_id=shopping_list.store_id,
        store_name=detail.store_name,
        expires_at=shopping_list.expires_at,
        share=None if detail.share is None else ShareRead(**vars(detail.share)),
        sections=[_section_read(section) for section in detail.sections],
        created_at=shopping_list.created_at,
        updated_at=shopping_list.updated_at,
    )


def _summary_read(summary: ShoppingListSummary) -> ShoppingListSummaryRead:
    shopping_list = summary.shopping_list
    return ShoppingListSummaryRead(
        id=shopping_list.id,
        generation_id=shopping_list.generation_id,
        name=shopping_list.name,
        round_name=shopping_list.round_name,
        store_id=shopping_list.store_id,
        store_name=summary.store_name,
        expires_at=shopping_list.expires_at,
        items_total=summary.items_total,
        items_checked=summary.items_checked,
        share=None if summary.share is None else ShareRead(**vars(summary.share)),
        created_at=shopping_list.created_at,
    )


def build_shopping_lists_router() -> APIRouter:
    """Router `/shopping/lists` — odczyt, odhaczanie, sklep, udostępnianie, spiżarnia."""
    router = APIRouter(prefix="/shopping/lists", tags=["shopping"])

    @router.get(
        "",
        response_model=ShoppingListsResponse,
        summary="Listy zakupowe widoczne dla użytkownika",
        description=(
            "Najnowsze pierwsze. `status=expired` pokazuje listy po terminie — "
            "te NIE są usuwane automatycznie (D10), przestaje działać wyłącznie "
            "ich publiczny link."
        ),
    )
    async def list_lists(
        user: CurrentUser,
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        list_status: Annotated[ShoppingListStatus | None, Query(alias="status")] = None,
    ) -> ShoppingListsResponse:
        expired = None if list_status is None else list_status is ShoppingListStatus.EXPIRED
        rows, total = await service.list_lists(
            user, limit=limit, offset=offset, now=datetime.now(UTC), expired=expired
        )
        return ShoppingListsResponse(
            items=[_summary_read(row) for row in rows],
            total=total,
        )

    @router.get(
        "/{list_id}",
        response_model=ShoppingListDetailRead,
        summary="Lista zakupowa z pozycjami w sekcjach (kolejność profilu sklepu)",
    )
    async def get_list(
        list_id: int, user: CurrentUser, service: ServiceDep
    ) -> ShoppingListDetailRead:
        return _detail_read(await service.get_list(list_id, user=user))

    @router.patch(
        "/{list_id}",
        response_model=ShoppingListDetailRead,
        summary="Edycja listy: nazwa i sklep (zmiana sklepu przesortowuje sekcje)",
    )
    async def update_list(
        list_id: int,
        payload: ListUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> ShoppingListDetailRead:
        return _detail_read(
            await service.update_list(
                list_id,
                user=user,
                name=payload.name,
                store_id=payload.store_id,
                clear_store=payload.clear_store,
            )
        )

    @router.delete(
        "/{list_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie listy (właściciel albo ADMIN)",
        description=(
            "Ręczna, jawna decyzja — automat nie kasuje niczego (D10). Pozycje "
            "giną kaskadą, więc produkt użyty tylko na tej liście da się potem usunąć."
        ),
    )
    async def delete_list(list_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.delete_list(list_id, user=user)

    @router.patch(
        "/{list_id}/items/{item_id}",
        response_model=ShoppingListItemRead,
        summary="Odhaczenie pozycji albo „mam już w domu”",
        description="`checked_at` ustawia serwer (UTC) — klient go nie przysyła (ADR-009).",
    )
    async def update_item(
        list_id: int,
        item_id: int,
        payload: ListItemUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> ShoppingListItemRead:
        item = await service.update_item(
            list_id,
            item_id,
            user=user,
            now=datetime.now(UTC),
            checked=payload.checked,
            already_have=payload.already_have,
        )
        return ShoppingListItemRead.model_validate(item)

    @router.post(
        "/{list_id}/share",
        response_model=ShareRead,
        status_code=status.HTTP_201_CREATED,
        summary="Udostępnienie listy publicznym linkiem",
        description=SHARE_DESCRIPTION,
    )
    async def share_list(
        list_id: int,
        payload: ShareCreateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> ShareRead:
        share = await service.share_list(
            list_id,
            user=user,
            expires_in_days=payload.expires_in_days,
            now=datetime.now(UTC),
        )
        return ShareRead(**vars(share))

    @router.delete(
        "/{list_id}/share",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Odwołanie publicznego linku (natychmiast 410 dla odwiedzających)",
    )
    async def revoke_share(list_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.revoke_share(list_id, user=user)

    @router.post(
        "/{list_id}/accept-to-pantry",
        response_model=AcceptToPantryResponse,
        summary="Przyjęcie odhaczonych zakupów do spiżarni",
        description=(
            "Akcja JAWNA (02_DOMAIN §8) — zakupy nie trafiają do spiżarni w tle. "
            "Ilość liczymy jako kupioną (`packages_count * package_size`), a bez "
            "opakowania jako `needed_amount`. Zakup dolewa się do pozycji tego "
            "produktu BEZ daty ważności, a gdy takiej nie ma — zakłada nową."
        ),
    )
    async def accept_to_pantry(
        list_id: int, user: CurrentUser, service: ServiceDep
    ) -> AcceptToPantryResponse:
        result = await service.accept_to_pantry(list_id, user=user)
        return AcceptToPantryResponse(
            created=result.created, increased=result.increased, skipped=result.skipped
        )

    return router
