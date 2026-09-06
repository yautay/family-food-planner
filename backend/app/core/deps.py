"""Zależności FastAPI: sesja użytkownika i kontrola roli.

To JEDYNE wejście autoryzacji w aplikacji (04_API §3). Kolejne moduły używają
`CurrentUser` / `AdminUser`, nigdy własnego odczytu cookie.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings, request_settings
from app.core.cookies import csrf_cookie_name, session_cookie_name, set_session_cookies
from app.core.db import get_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.accounts.models import User, UserRole
from app.modules.accounts.service import SESSION_REQUIRED, AccountsService
from app.modules.audit.service import AuditService
from app.modules.catalog.retail_service import RetailService
from app.modules.catalog.service import CatalogService
from app.modules.catalog.stores_service import StoresService
from app.modules.households.service import HouseholdsService
from app.modules.nutrition.service import GoalsService
from app.modules.pantry.service import PantryService
from app.modules.planning.service import PlanningService
from app.modules.planning.stats_service import StatsService
from app.modules.planning.templates_service import TemplatesService
from app.modules.recipes.service import RecipesService
from app.modules.shopping.lists_service import ShoppingListsService
from app.modules.shopping.service import ShoppingService
from app.modules.transfer.service import TransferService


def get_accounts_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountsService:
    """Serwis kont na potrzeby routerów i innych dependency."""
    return AccountsService(session)


def get_households_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HouseholdsService:
    """Serwis rodzin i profili członków."""
    return HouseholdsService(session)


def get_catalog_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogService:
    """Serwis katalogu: produkty kanoniczne, kategorie, przeliczniki jednostek."""
    return CatalogService(session)


def get_stores_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StoresService:
    """Serwis sklepów i profili kolejności kategorii (BATCH_09)."""
    return StoresService(session)


def get_retail_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RetailService:
    """Serwis produktów sklepowych: warianty, opakowania, zdjęcia (BATCH_09)."""
    return RetailService(session)


def get_recipes_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RecipesService:
    """Serwis przepisów: CRUD, składniki, tagi, oceny, zdjęcie."""
    return RecipesService(session)


def get_goals_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GoalsService:
    """Serwis celów żywieniowych (historia po `valid_from`)."""
    return GoalsService(session)


def get_pantry_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PantryService:
    """Serwis spiżarni: stan domowy produktów (BATCH_08)."""
    return PantryService(session)


def get_planning_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlanningService:
    """Serwis planu dnia: dni, posiłki, pozycje, rozkład rodzinny, kopiowanie."""
    return PlanningService(session)


def get_stats_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatsService:
    """Serwis statystyk: agregaty dzienne z planu i celów (BATCH_13, tylko odczyt)."""
    return StatsService(session)


def get_templates_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TemplatesService:
    """Serwis szablonów dnia/tygodnia i cykli tygodni (BATCH_07)."""
    return TemplatesService(session)


def get_shopping_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ShoppingService:
    """Serwis zakupów: tury, generacje, finalizacja list (BATCH_10)."""
    return ShoppingService(session)


def get_shopping_lists_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ShoppingListsService:
    """Serwis gotowych list zakupowych: odhaczanie, sklep, udostępnianie (BATCH_11)."""
    return ShoppingListsService(session)


def get_transfer_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TransferService:
    """Serwis eksportu/importu logicznego (BATCH_14) — zna katalog uploadów i limit paczki."""
    return TransferService(
        session,
        uploads_dir=settings.uploads_dir,
        max_zip_mb=settings.transfer_max_zip_mb,
        image_max_mb=settings.image_max_upload_mb,
    )


def get_audit_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditService:
    """Serwis dziennika operacji (odczyt dla ADMIN-a; zapisy robią serwisy domenowe)."""
    return AuditService(session)


async def get_current_user(
    request: Request,
    response: Response,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> User:
    """Cookie → sesja → użytkownik. Brak/niepoprawna/wygasła sesja = 401."""
    settings = request_settings(request)
    session_id = request.cookies.get(session_cookie_name(settings))
    if not session_id:
        raise UnauthorizedError(SESSION_REQUIRED)

    user, refreshed = await service.resolve_session(session_id)
    if refreshed:
        # TTL przesunięty w bazie ⇒ przesuwamy też cookies, inaczej przeglądarka
        # skasowałaby je 30 dni po logowaniu mimo aktywnej sesji.
        _refresh_session_cookies(request, response)

    # Do logów trafia id użytkownika, nigdy email ani id sesji (07_SECURITY §8).
    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user


def _refresh_session_cookies(request: Request, response: Response) -> None:
    """Wyślij te same wartości cookies z nowym `Max-Age` (TTL przesuwne, ADR-003)."""
    settings = request_settings(request)
    session_id = request.cookies.get(session_cookie_name(settings))
    csrf_token = request.cookies.get(csrf_cookie_name(settings))
    if not session_id or not csrf_token:
        # Bez tokenu CSRF nie ma czego odświeżać — sesja i tak działa, a nowy
        # token powstanie przy kolejnym logowaniu.
        return
    set_session_cookies(response, session_id=session_id, csrf_token=csrf_token, settings=settings)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """Endpointy `/admin/*` — rola ADMIN, inaczej 403 (02_DOMAIN §2)."""
    if user.role is not UserRole.ADMIN:
        raise ForbiddenError("Ta operacja wymaga uprawnień administratora.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
