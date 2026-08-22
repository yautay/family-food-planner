"""HTTP ścieżki publicznej listy: `/public/lists/*` (04_API §3 pkt 3, ADR-010).

Jedyny router aplikacji BEZ sesji poza `/health`. Trzy rzeczy, które muszą tu
zostać dokładnie tak, jak są:

1. **Prefiks `/public/`** — `CSRF_EXEMPT_PREFIXES` w `app/core/middleware.py`
   zwalnia z CSRF dokładnie prefiks `/api/v1/public/`. Przeniesienie routera pod inną
   ścieżkę wyłączyłoby publiczny PATCH (403), a dopisanie nowego wyjątku do
   middleware byłoby poszerzaniem powierzchni ataku bez powodu.
2. **Rate limit 60/min/IP** (07_SECURITY §5) — jedyna obrona przed skanowaniem
   tokenów obok ich entropii; limiter wstrzykuje `create_app` (wzór z `/auth`).
3. **Odpowiedź z BIAŁEJ LISTY pól** — router nie zwraca encji ORM, tylko widok
   serwisu przepisany polami. Zero PII to niezmiennik 02_DOMAIN §13.5, nie
   ustawienie.

Maskowanie tokenu w logach robi `mask_path()` w `app/core/logging.py` (B02):
ścieżka trafia do logu jako `/api/v1/public/lists/***`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from slowapi import Limiter

from app.core.deps import get_shopping_lists_service
from app.modules.shopping.lists_service import (
    PublicListItemView,
    ShoppingListsService,
)
from app.modules.shopping.schemas import (
    PublicListItemRead,
    PublicListItemUpdateRequest,
    PublicListRead,
)

ServiceDep = Annotated[ShoppingListsService, Depends(get_shopping_lists_service)]

#: 60/min/IP na całą ścieżkę publiczną (07_SECURITY §5, ADR-010).
PUBLIC_RATE_LIMIT = "60/minute"
#: Zakres WSPÓLNEGO licznika. `limiter.limit` liczyłby każdy endpoint osobno,
#: więc `/public/*` miałoby faktycznie 120/min — a limit z 07_SECURITY §5 dotyczy
#: całej ścieżki publicznej, nie pojedynczej trasy.
PUBLIC_RATE_LIMIT_SCOPE = "public-lists"

#: Token ma 43 znaki base64url (`token_urlsafe(32)`). Walidacja długości i
#: alfabetu jest tania i odsiewa skanery PRZED zapytaniem do bazy; niepasujący
#: token dostaje 422 z generycznym komunikatem, więc nic o sobie nie dowiaduje.
TokenPath = Annotated[str, Path(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")]

GONE_RESPONSE: dict[int | str, dict[str, Any]] = {
    410: {"description": "Link wygasł albo został odwołany"}
}


def _item_read(item: PublicListItemView) -> PublicListItemRead:
    """Widok serwisu → schemat odpowiedzi. Pola przepisane JAWNIE, po jednym."""
    return PublicListItemRead(
        id=item.id,
        label=item.label,
        amount=item.amount,
        unit=item.unit,
        category_name=item.category_name,
        checked=item.checked,
        leftover_amount=item.leftover_amount,
        already_have=item.already_have,
        packages_count=item.packages_count,
        package_size=item.package_size,
    )


def build_public_lists_router(limiter: Limiter) -> APIRouter:
    """Router `/public/lists` — odczyt listy i odhaczanie po tokenie, bez sesji."""
    router = APIRouter(prefix="/public/lists", tags=["public"])

    @router.get(
        "/{token}",
        response_model=PublicListRead,
        summary="Treść listy zakupowej po publicznym tokenie (bez logowania)",
        description=(
            "Odpowiedź zawiera WYŁĄCZNIE treść listy: nazwę, ważność i pozycje. "
            "Nieznany token → 404, wygasły albo odwołany → 410. Komunikat jest "
            "w obu przypadkach identyczny — nie ujawniamy, czy token istniał."
        ),
        responses=GONE_RESPONSE,
    )
    @limiter.shared_limit(PUBLIC_RATE_LIMIT, scope=PUBLIC_RATE_LIMIT_SCOPE)
    async def public_list(
        request: Request,
        token: TokenPath,
        service: ServiceDep,
    ) -> PublicListRead:
        view = await service.public_list(token, now=datetime.now(UTC))
        return PublicListRead(
            name=view.name,
            expires_at=view.expires_at,
            items=[_item_read(item) for item in view.items],
        )

    @router.patch(
        "/{token}/items/{item_id}",
        response_model=PublicListItemRead,
        summary="Odhaczenie pozycji z publicznego linku",
        description=(
            "Token pozwala zmienić WYŁĄCZNIE `checked` (ADR-010) — każde inne "
            "pole w ciele żądania kończy się 422. Opcjonalne `checked_at` nie "
            "poszerza tych uprawnień: mówi tylko, KIEDY zapadła decyzja, żeby "
            "odhaczenie z kolejki offline nie nadpisało świeższego stanu "
            "(last-write-wins, ADR-009). Bez CSRF (autoryzuje token w URL), "
            "za to z limitem 60/min/IP."
        ),
        responses=GONE_RESPONSE,
    )
    @limiter.shared_limit(PUBLIC_RATE_LIMIT, scope=PUBLIC_RATE_LIMIT_SCOPE)
    async def public_check_item(
        request: Request,
        token: TokenPath,
        item_id: int,
        payload: PublicListItemUpdateRequest,
        service: ServiceDep,
    ) -> PublicListItemRead:
        return _item_read(
            await service.public_check_item(
                token,
                item_id,
                checked=payload.checked,
                now=datetime.now(UTC),
                checked_at=payload.checked_at,
            )
        )

    return router
