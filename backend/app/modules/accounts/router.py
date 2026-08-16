"""HTTP modułu accounts: `/auth/*` i `/admin/users` (04_API §2).

Router zajmuje się wyłącznie warstwą HTTP: walidacją wejścia, cookies i
mapowaniem wyniku serwisu na schemat odpowiedzi. Logika i dostęp do bazy
mieszkają w `service.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from slowapi import Limiter

from app.core.config import Settings
from app.core.cookies import clear_session_cookies, set_session_cookies
from app.core.deps import AdminUser, CurrentUser, get_accounts_service, require_admin
from app.core.security import SESSION_COOKIE_NAME, generate_token
from app.modules.accounts.schemas import (
    CurrentUser as CurrentUserSchema,
)
from app.modules.accounts.schemas import (
    LoginRequest,
    UserCreateRequest,
    UserListResponse,
    UserRead,
    UserUpdateRequest,
)
from app.modules.accounts.service import AccountsService

#: Rate limit logowania per IP (07_SECURITY §2).
LOGIN_RATE_LIMIT = "5/minute"

ServiceDep = Annotated[AccountsService, Depends(get_accounts_service)]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def build_auth_router(settings: Settings, limiter: Limiter) -> APIRouter:
    """Router `/auth` — logowanie, wylogowanie, dane zalogowanego użytkownika."""
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/login", response_model=CurrentUserSchema, summary="Logowanie")
    @limiter.limit(LOGIN_RATE_LIMIT)
    async def login(
        request: Request,
        response: Response,
        payload: LoginRequest,
        service: ServiceDep,
    ) -> CurrentUserSchema:
        user, session_id = await service.login(
            email=payload.email,
            password=payload.password,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        set_session_cookies(
            response,
            session_id=session_id,
            csrf_token=generate_token(),
            settings=settings,
        )
        return CurrentUserSchema.model_validate(user)

    @router.post(
        "/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Wylogowanie (unieważnia sesję po stronie serwera)",
    )
    async def logout(
        request: Request,
        response: Response,
        user: CurrentUser,
        service: ServiceDep,
    ) -> None:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if session_id:
            await service.logout(session_id)
        clear_session_cookies(response, settings=settings)

    @router.get("/me", response_model=CurrentUserSchema, summary="Zalogowany użytkownik")
    async def me(user: CurrentUser) -> CurrentUserSchema:
        return CurrentUserSchema.model_validate(user)

    return router


def build_admin_users_router() -> APIRouter:
    """Router `/admin/users` — zarządzanie kontami; wyłącznie rola ADMIN."""
    router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])

    @router.get("", response_model=UserListResponse, summary="Lista kont")
    async def list_users(
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query(max_length=200)] = None,
    ) -> UserListResponse:
        users, total = await service.list_users(limit=limit, offset=offset, query=q)
        return UserListResponse(
            items=[UserRead.model_validate(user) for user in users], total=total
        )

    @router.post(
        "",
        response_model=UserRead,
        status_code=status.HTTP_201_CREATED,
        summary="Utworzenie konta",
    )
    async def create_user(payload: UserCreateRequest, service: ServiceDep) -> UserRead:
        user = await service.create_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
            is_active=payload.is_active,
        )
        return UserRead.model_validate(user)

    @router.get("/{user_id}", response_model=UserRead, summary="Szczegóły konta")
    async def get_user(user_id: int, service: ServiceDep) -> UserRead:
        return UserRead.model_validate(await service.get_user(user_id))

    @router.patch("/{user_id}", response_model=UserRead, summary="Edycja konta")
    async def update_user(
        user_id: int,
        payload: UserUpdateRequest,
        service: ServiceDep,
        actor: AdminUser,
    ) -> UserRead:
        user = await service.update_user(
            user_id,
            actor=actor,
            display_name=payload.display_name,
            role=payload.role,
            is_active=payload.is_active,
            password=payload.password,
        )
        return UserRead.model_validate(user)

    @router.delete(
        "/{user_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie konta (409, gdy ma powiązane dane)",
    )
    async def delete_user(user_id: int, service: ServiceDep, actor: AdminUser) -> None:
        await service.delete_user(user_id, actor=actor)

    return router
