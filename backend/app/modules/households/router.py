"""HTTP modułu households: `/admin/households` i `/households/my` (04_API §2).

Router nie wie, czym jest rodzina ani kto do niej należy — sprawdza wejście,
woła serwis i mapuje wynik. Autoryzacja: `require_admin` dla ścieżek
administracyjnych, `CurrentUser` dla ścieżek użytkownika; reszta reguł
(członkostwo, 404 dla cudzych profili) mieszka w serwisie (04_API §3 pkt 2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import AdminUser, CurrentUser, get_households_service, require_admin
from app.modules.households.schemas import (
    HouseholdCreateRequest,
    HouseholdDetail,
    HouseholdListResponse,
    HouseholdMember,
    HouseholdMembersRequest,
    HouseholdRead,
    HouseholdSummary,
    HouseholdUpdateRequest,
    MemberProfileCreateRequest,
    MemberProfileListResponse,
    MemberProfileRead,
    MemberProfileUpdateRequest,
    MyHouseholdResponse,
)
from app.modules.households.service import HouseholdsService, HouseholdView

ServiceDep = Annotated[HouseholdsService, Depends(get_households_service)]


def _to_read(view: HouseholdView) -> HouseholdRead:
    """Rodzina + liczniki. Router czyta WYŁĄCZNIE `HouseholdView` — nigdy relacji
    ORM, bo te potrafią być leniwe, a warstwa HTTP jest synchroniczna."""
    return HouseholdRead(
        id=view.household.id,
        name=view.household.name,
        created_at=view.household.created_at,
        updated_at=view.household.updated_at,
        members_count=len(view.members),
        profiles_count=len(view.profiles),
    )


def _to_detail(view: HouseholdView) -> HouseholdDetail:
    return HouseholdDetail(
        **_to_read(view).model_dump(),
        members=[HouseholdMember.model_validate(member) for member in view.members],
        profiles=[MemberProfileRead.model_validate(profile) for profile in view.profiles],
    )


def build_admin_households_router() -> APIRouter:
    """Router `/admin/households` — zarządzanie rodzinami; wyłącznie rola ADMIN."""
    router = APIRouter(
        prefix="/admin/households", tags=["admin"], dependencies=[Depends(require_admin)]
    )

    @router.get("", response_model=HouseholdListResponse, summary="Lista rodzin")
    async def list_households(
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query(max_length=200)] = None,
    ) -> HouseholdListResponse:
        views, total = await service.list_households(limit=limit, offset=offset, query=q)
        return HouseholdListResponse(items=[_to_read(view) for view in views], total=total)

    @router.post(
        "",
        response_model=HouseholdDetail,
        status_code=status.HTTP_201_CREATED,
        summary="Utworzenie rodziny",
    )
    async def create_household(
        payload: HouseholdCreateRequest, service: ServiceDep, actor: AdminUser
    ) -> HouseholdDetail:
        return _to_detail(await service.create_household(name=payload.name, actor=actor))

    @router.get(
        "/{household_id}",
        response_model=HouseholdDetail,
        summary="Szczegóły rodziny z członkami i profilami",
    )
    async def get_household(household_id: int, service: ServiceDep) -> HouseholdDetail:
        return _to_detail(await service.household_view(household_id))

    @router.patch("/{household_id}", response_model=HouseholdDetail, summary="Zmiana nazwy rodziny")
    async def update_household(
        household_id: int,
        payload: HouseholdUpdateRequest,
        service: ServiceDep,
        actor: AdminUser,
    ) -> HouseholdDetail:
        return _to_detail(
            await service.update_household(household_id, name=payload.name, actor=actor)
        )

    @router.delete(
        "/{household_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie rodziny (409 z listą użyć, gdy nie jest pusta)",
    )
    async def delete_household(household_id: int, service: ServiceDep, actor: AdminUser) -> None:
        await service.delete_household(household_id, actor=actor)

    @router.put(
        "/{household_id}/members",
        response_model=HouseholdDetail,
        summary="Podmiana składu rodziny (konta spoza listy zostają odpięte)",
    )
    async def set_members(
        household_id: int,
        payload: HouseholdMembersRequest,
        service: ServiceDep,
        actor: AdminUser,
    ) -> HouseholdDetail:
        return _to_detail(
            await service.set_members(household_id, user_ids=payload.user_ids, actor=actor)
        )

    return router


def build_households_router() -> APIRouter:
    """Router `/households/my` — moja rodzina i profile jej członków."""
    router = APIRouter(prefix="/households", tags=["households"])

    @router.get("/my", response_model=MyHouseholdResponse, summary="Moja rodzina")
    async def my_household(user: CurrentUser, service: ServiceDep) -> MyHouseholdResponse:
        view = await service.my_household(user)
        if view is None:
            return MyHouseholdResponse(household=None, members=[], profiles=[])
        return MyHouseholdResponse(
            household=HouseholdSummary.model_validate(view.household),
            members=[HouseholdMember.model_validate(member) for member in view.members],
            profiles=[MemberProfileRead.model_validate(profile) for profile in view.profiles],
        )

    @router.get(
        "/my/profiles",
        response_model=MemberProfileListResponse,
        summary="Profile członków mojej rodziny",
    )
    async def list_profiles(user: CurrentUser, service: ServiceDep) -> MemberProfileListResponse:
        profiles = await service.list_profiles(user)
        return MemberProfileListResponse(
            items=[MemberProfileRead.model_validate(profile) for profile in profiles],
            total=len(profiles),
        )

    @router.post(
        "/my/profiles",
        response_model=MemberProfileRead,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie profilu członka rodziny",
    )
    async def create_profile(
        payload: MemberProfileCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> MemberProfileRead:
        profile = await service.create_profile(
            user=user,
            name=payload.name,
            default_multiplier=payload.default_multiplier,
            kcal_goal=payload.kcal_goal,
            is_active=payload.is_active,
        )
        return MemberProfileRead.model_validate(profile)

    @router.patch(
        "/my/profiles/{profile_id}",
        response_model=MemberProfileRead,
        summary="Edycja profilu członka rodziny",
    )
    async def update_profile(
        profile_id: int,
        payload: MemberProfileUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> MemberProfileRead:
        # `exclude_unset` niesie informację, której samo `None` nie ma: pole
        # pominięte zostaje bez zmian, a jawne `kcal_goal: null` czyści cel.
        profile = await service.update_profile(
            profile_id, user=user, changes=payload.model_dump(exclude_unset=True)
        )
        return MemberProfileRead.model_validate(profile)

    @router.delete(
        "/my/profiles/{profile_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie profilu członka rodziny",
    )
    async def delete_profile(profile_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.delete_profile(profile_id, user=user)

    return router
