"""Zależności FastAPI: sesja użytkownika i kontrola roli.

To JEDYNE wejście autoryzacji w aplikacji (04_API §3). Kolejne moduły używają
`CurrentUser` / `AdminUser`, nigdy własnego odczytu cookie.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.cookies import set_session_cookies
from app.core.db import get_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from app.modules.accounts.models import User, UserRole
from app.modules.accounts.service import SESSION_REQUIRED, AccountsService
from app.modules.audit.service import AuditService
from app.modules.catalog.service import CatalogService
from app.modules.households.service import HouseholdsService
from app.modules.nutrition.service import GoalsService
from app.modules.planning.service import PlanningService
from app.modules.recipes.service import RecipesService


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


def get_planning_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlanningService:
    """Serwis planu dnia: dni, posiłki, pozycje, rozkład rodzinny, kopiowanie."""
    return PlanningService(session)


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
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
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
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not session_id or not csrf_token:
        # Bez tokenu CSRF nie ma czego odświeżać — sesja i tak działa, a nowy
        # token powstanie przy kolejnym logowaniu.
        return
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    set_session_cookies(response, session_id=session_id, csrf_token=csrf_token, settings=settings)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """Endpointy `/admin/*` — rola ADMIN, inaczej 403 (02_DOMAIN §2)."""
    if user.role is not UserRole.ADMIN:
        raise ForbiddenError("Ta operacja wymaga uprawnień administratora.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
