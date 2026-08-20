"""HTTP celów żywieniowych: `/goals` (04_API §2).

Router waliduje wejście, woła serwis i mapuje wynik. Właścicielem celu jest
ZAWSZE użytkownik z sesji — `user_id` nie występuje w żadnym schemacie wejścia
(karta B06 §Security).

„Dzisiaj" wchodzi do serwisu parametrem: zegar jest sprawą warstwy HTTP, dzięki
czemu logika wyboru celu obowiązującego pozostaje deterministyczna i testowalna.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, get_goals_service
from app.modules.nutrition.schemas import GoalListResponse, GoalPayload, GoalRead
from app.modules.nutrition.service import GoalsService

ServiceDep = Annotated[GoalsService, Depends(get_goals_service)]


def build_goals_router() -> APIRouter:
    """Router `/goals` — historia celów użytkownika i ich edycja."""
    router = APIRouter(prefix="/goals", tags=["nutrition"])

    @router.get(
        "",
        response_model=GoalListResponse,
        summary="Historia własnych celów (najnowszy pierwszy) + cel obowiązujący dziś",
    )
    async def list_goals(user: CurrentUser, service: ServiceDep) -> GoalListResponse:
        view = await service.list_goals(user, today=date.today())
        return GoalListResponse(
            items=[GoalRead.model_validate(goal) for goal in view.items],
            total=len(view.items),
            current=None if view.current is None else GoalRead.model_validate(view.current),
        )

    @router.post(
        "",
        response_model=GoalRead,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy cel od wskazanej daty (409, gdy cel na tę datę już istnieje)",
    )
    async def create_goal(payload: GoalPayload, user: CurrentUser, service: ServiceDep) -> GoalRead:
        return GoalRead.model_validate(await service.create_goal(user=user, payload=payload))

    @router.put("/{goal_id}", response_model=GoalRead, summary="Pełna podmiana własnego celu")
    async def update_goal(
        goal_id: int, payload: GoalPayload, user: CurrentUser, service: ServiceDep
    ) -> GoalRead:
        goal = await service.update_goal(goal_id, user=user, payload=payload)
        return GoalRead.model_validate(goal)

    @router.delete(
        "/{goal_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie wpisu historii celów (wyłącznie własnego)",
    )
    async def delete_goal(goal_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.delete_goal(goal_id, user=user)

    return router
