"""HTTP modułu planning: `/plan/*` (04_API §2).

Router waliduje wejście, woła serwis i mapuje widoki na schematy. Nie ma tu
żadnego filtra widoczności ani reguły domenowej — scope egzekwuje `ScopedQuery`
w serwisie (04_API §3), a wartości liczy silnik.

Mutacje odpowiadają CAŁYM dniem po zmianie: interfejs planu i tak pokazuje
dzień w całości (kafelki, posiłki, panel makro), więc jedna odpowiedź zamiast
„204 + refetch" oszczędza rundę i eliminuje moment, w którym widok kłamie.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, get_planning_service
from app.core.scope import Scope
from app.core.uploads import thumbnail_path_for
from app.modules.nutrition.schemas import GoalMetricRead, nutrition_read
from app.modules.planning.schemas import (
    DayGoalProgressRead,
    DayRead,
    DaysResponse,
    FitToTargetResponse,
    ItemCreateRequest,
    ItemUpdateRequest,
    MealCreateRequest,
    MealRead,
    MealUpdateRequest,
    PlanCopyRequest,
    PlanDayUpsertRequest,
    PlanItemRead,
    PlanServingSplitRead,
)
from app.modules.planning.service import DayView, FitProposal, ItemView, MealView, PlanningService
from app.modules.recipes.router import UPLOADS_URL_PREFIX

ServiceDep = Annotated[PlanningService, Depends(get_planning_service)]


def _thumb_url(photo_path: str | None) -> str | None:
    """Miniatura zdjęcia przepisu jako URL endpointu `/uploads/*` (albo `None`)."""
    if not photo_path:
        return None
    return f"{UPLOADS_URL_PREFIX}/{thumbnail_path_for(photo_path)}"


def _to_item(view: ItemView) -> PlanItemRead:
    item = view.item
    return PlanItemRead(
        id=item.id,
        position=item.position,
        recipe_id=item.recipe_id,
        recipe_name=None if view.recipe is None else view.recipe.name,
        recipe_photo_thumb_url=None if view.recipe is None else _thumb_url(view.recipe.photo_path),
        product_id=item.product_id,
        product_name=None if view.product is None else view.product.name,
        amount=item.amount,
        amount_unit=item.amount_unit,
        servings=item.servings,
        servings_split=[
            PlanServingSplitRead(
                member_profile_id=row.member_profile_id,
                member_name=row.member_name,
                multiplier=row.multiplier,
            )
            for row in view.split
        ],
        nutrition=nutrition_read(view.nutrition),
    )


def _to_meal(view: MealView) -> MealRead:
    return MealRead(
        id=view.meal.id,
        name=view.meal.name,
        position=view.meal.position,
        kcal_target=view.meal.kcal_target,
        kcal_status=view.kcal_status,
        items=[_to_item(item) for item in view.items],
        nutrition=nutrition_read(view.nutrition),
    )


def _to_day(view: DayView) -> DayRead:
    entity = view.entity
    progress = {
        field: GoalMetricRead(
            value=metric.value,
            target=metric.target,
            delta=metric.delta,
            status=metric.status,
        )
        for field, metric in view.progress.items()
    }
    return DayRead(
        id=None if entity is None else entity.id,
        day=view.day,
        title=None if entity is None else entity.title,
        # Dzień, którego jeszcze nie ma, pokazujemy jako prywatny — taki powstanie
        # przy pierwszym posiłku, jeśli użytkownik nie wybierze inaczej.
        scope=Scope.PRIVATE if entity is None else entity.scope,
        owner_user_id=None if entity is None else entity.owner_user_id,
        meals=[_to_meal(meal) for meal in view.meals],
        nutrition=nutrition_read(view.nutrition),
        goal_progress=DayGoalProgressRead(**progress),
        goal_valid_from=None if view.goal is None else view.goal.valid_from,
        created_at=None if entity is None else entity.created_at,
        updated_at=None if entity is None else entity.updated_at,
    )


def _to_fit(proposal: FitProposal) -> FitToTargetResponse:
    return FitToTargetResponse(
        item_id=proposal.item.id,
        target_kcal=proposal.target_kcal,
        current_servings=proposal.item.servings,
        proposed_servings=proposal.proposed_servings,
        resulting_nutrition=nutrition_read(proposal.resulting_nutrition),
    )


def build_plan_router() -> APIRouter:
    """Router `/plan` — dni, posiłki, pozycje, kopiowanie i dopasowanie porcji."""
    router = APIRouter(prefix="/plan", tags=["planning"])

    @router.get(
        "/days",
        response_model=DaysResponse,
        summary="Dni planu z zakresu dat (posiłki, pozycje, wartości, cel i statusy)",
    )
    async def list_days(
        user: CurrentUser,
        service: ServiceDep,
        date_from: Annotated[date, Query(alias="from")],
        date_to: Annotated[date, Query(alias="to")],
    ) -> DaysResponse:
        views = await service.list_days(user, date_from=date_from, date_to=date_to)
        return DaysResponse(items=[_to_day(view) for view in views], total=len(views))

    @router.get(
        "/days/{day}",
        response_model=DayRead,
        summary="Plan wybranego dnia; data bez planu zwraca pusty dzień, nie 404",
    )
    async def get_day(day: date, user: CurrentUser, service: ServiceDep) -> DayRead:
        return _to_day(await service.get_day(user, day))

    @router.put(
        "/days/{day}",
        response_model=DayRead,
        summary="Utworzenie albo aktualizacja dnia (tytuł, widoczność)",
    )
    async def upsert_day(
        day: date, payload: PlanDayUpsertRequest, user: CurrentUser, service: ServiceDep
    ) -> DayRead:
        view = await service.upsert_day(user, day, title=payload.title, scope=payload.scope)
        return _to_day(view)

    @router.post(
        "/days/{day}/meals",
        response_model=DayRead,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy posiłek dnia (dzień powstaje implicite, gdy jeszcze go nie ma)",
    )
    async def create_meal(
        day: date, payload: MealCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> DayRead:
        return _to_day(await service.create_meal(user, day, payload))

    @router.patch(
        "/meals/{meal_id}",
        response_model=DayRead,
        summary="Edycja posiłku (nazwa, cel kcal, kolejność)",
    )
    async def update_meal(
        meal_id: int, payload: MealUpdateRequest, user: CurrentUser, service: ServiceDep
    ) -> DayRead:
        return _to_day(await service.update_meal(meal_id, user=user, payload=payload))

    @router.delete(
        "/meals/{meal_id}",
        response_model=DayRead,
        summary="Usunięcie posiłku razem z pozycjami",
    )
    async def delete_meal(meal_id: int, user: CurrentUser, service: ServiceDep) -> DayRead:
        return _to_day(await service.delete_meal(meal_id, user=user))

    @router.post(
        "/meals/{meal_id}/items",
        response_model=DayRead,
        status_code=status.HTTP_201_CREATED,
        summary="Nowa pozycja: przepis z mnożnikiem albo produkt luzem z ilością",
    )
    async def add_item(
        meal_id: int, payload: ItemCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> DayRead:
        return _to_day(await service.add_item(meal_id, user=user, payload=payload))

    @router.patch(
        "/items/{item_id}",
        response_model=DayRead,
        summary="Edycja pozycji (mnożnik, ilość, rozkład rodzinny, kolejność)",
    )
    async def update_item(
        item_id: int, payload: ItemUpdateRequest, user: CurrentUser, service: ServiceDep
    ) -> DayRead:
        return _to_day(await service.update_item(item_id, user=user, payload=payload))

    @router.delete(
        "/items/{item_id}",
        response_model=DayRead,
        summary="Usunięcie pozycji planu",
    )
    async def delete_item(item_id: int, user: CurrentUser, service: ServiceDep) -> DayRead:
        return _to_day(await service.delete_item(item_id, user=user))

    @router.post(
        "/items/{item_id}/fit-to-target",
        response_model=FitToTargetResponse,
        summary="PROPOZYCJA mnożnika porcji pod cel kcal posiłku (nic nie zapisuje)",
    )
    async def fit_to_target(
        item_id: int, user: CurrentUser, service: ServiceDep
    ) -> FitToTargetResponse:
        return _to_fit(await service.fit_to_target(item_id, user=user))

    @router.post(
        "/copy",
        response_model=DaysResponse,
        summary="Głęboka kopia dnia na daty albo posiłku do dnia (dopisuje, nie nadpisuje)",
    )
    async def copy(
        payload: PlanCopyRequest, user: CurrentUser, service: ServiceDep
    ) -> DaysResponse:
        views = await service.copy(user=user, payload=payload)
        return DaysResponse(items=[_to_day(view) for view in views], total=len(views))

    return router
