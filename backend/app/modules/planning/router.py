"""HTTP modułu planning: `/plan/*`, `/templates/*` i `/cycles` (04_API §2).

Router waliduje wejście, woła serwis i mapuje widoki na schematy. Nie ma tu
żadnego filtra widoczności ani reguły domenowej — scope egzekwuje `ScopedQuery`
w serwisie (04_API §3), a wartości liczy silnik.

Mutacje odpowiadają CAŁYM dniem po zmianie: interfejs planu i tak pokazuje
dzień w całości (kafelki, posiłki, panel makro), więc jedna odpowiedź zamiast
„204 + refetch" oszczędza rundę i eliminuje moment, w którym widok kłamie.

Szablony i cykle (BATCH_07) trzymają się tej samej zasady: instancjacja i apply
odpowiadają listą utworzonych dni, więc widok tygodnia od razu ma czym się
odświeżyć. Lista szablonów NIE zwraca payloadów — payload jedzie tylko przy
odczycie pojedynczego szablonu (i przy eksporcie w B14).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import (
    CurrentUser,
    get_planning_service,
    get_stats_service,
    get_templates_service,
)
from app.core.scope import Scope
from app.core.uploads import image_urls
from app.modules.nutrition.schemas import GoalMetricRead, nutrition_read
from app.modules.planning.models import DayTemplate, WeekTemplate
from app.modules.planning.schemas import (
    CycleApplyRequest,
    CycleListResponse,
    CycleRead,
    CycleWriteRequest,
    DayGoalProgressRead,
    DayRead,
    DaysResponse,
    DayTemplatePayload,
    DayTemplateReadFull,
    DayTemplateWriteRequest,
    FitToTargetResponse,
    InstantiateDayRequest,
    InstantiateResponse,
    InstantiateWeekRequest,
    ItemCreateRequest,
    ItemUpdateRequest,
    MealCreateRequest,
    MealRead,
    MealUpdateRequest,
    PlanCopyRequest,
    PlanDayUpsertRequest,
    PlanItemRead,
    PlanServingSplitRead,
    RecipeItemCreatedResponse,
    RecipeItemCreateRequest,
    StatsAveragesRead,
    StatsDailyResponse,
    StatsDayRead,
    StatsGoalRead,
    StatsStatusRead,
    StatsSummaryRead,
    TemplateListResponse,
    TemplateSummaryRead,
    WeekTemplatePayload,
    WeekTemplateReadFull,
    WeekTemplateWriteRequest,
)
from app.modules.planning.service import (
    DayView,
    FitProposal,
    GoalMetric,
    ItemView,
    MealView,
    PlanningService,
)
from app.modules.planning.stats_service import DailyStats, DayStat, StatsService
from app.modules.planning.templates_service import (
    CycleView,
    InstantiateResult,
    TemplatesService,
    day_summary,
    week_summary,
)

ServiceDep = Annotated[PlanningService, Depends(get_planning_service)]
TemplatesDep = Annotated[TemplatesService, Depends(get_templates_service)]
StatsDep = Annotated[StatsService, Depends(get_stats_service)]


def _thumb_url(photo_path: str | None) -> str | None:
    """Miniatura zdjęcia przepisu jako URL endpointu `/uploads/*` (albo `None`)."""
    return image_urls(photo_path)[1]


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
        goal_progress=_to_goal_progress(view.progress),
        goal_valid_from=None if view.goal is None else view.goal.valid_from,
        created_at=None if entity is None else entity.created_at,
        updated_at=None if entity is None else entity.updated_at,
    )


def _to_day_template(template: DayTemplate) -> DayTemplateReadFull:
    """Szablon dnia → odpowiedź z payloadem zwalidowanym kontraktem `v:1`.

    Payload z bazy przechodzi walidację także przy ODCZYCIE: szablon zapisany
    przez starszą wersję kontraktu ma paść jawnie, a nie wyciec do UI w kształcie,
    którego frontend nie zna.
    """
    content = DayTemplatePayload.model_validate(template.payload)
    return DayTemplateReadFull(
        id=template.id,
        name=template.name,
        scope=template.scope,
        owner_user_id=template.owner_user_id,
        summary=day_summary(content),
        payload=content,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _to_week_template(template: WeekTemplate) -> WeekTemplateReadFull:
    content = WeekTemplatePayload.model_validate(template.payload)
    return WeekTemplateReadFull(
        id=template.id,
        name=template.name,
        scope=template.scope,
        owner_user_id=template.owner_user_id,
        summary=week_summary(content),
        payload=content,
        created_at=template.created_at,
        updated_at=template.updated_at,
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
        "/days/{day}/recipe-items",
        response_model=RecipeItemCreatedResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Zaplanuj przepis w istniejącym lub nowym posiłku atomowo",
    )
    async def create_recipe_item(
        day: date, payload: RecipeItemCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> RecipeItemCreatedResponse:
        view, meal_id, item_id = await service.create_recipe_item(user, day, payload)
        return RecipeItemCreatedResponse(day=_to_day(view), meal_id=meal_id, item_id=item_id)

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
        summary="Głęboka kopia dnia/posiłku albo powielenie bloku N dni (dopisuje, nie nadpisuje)",
    )
    async def copy(
        payload: PlanCopyRequest, user: CurrentUser, service: ServiceDep
    ) -> DaysResponse:
        # Blok ma inną arytmetykę wejścia (od kiedy, ile dni, ile powtórzeń), ale
        # ten sam mechanizm zapisu — dlatego jedna ścieżka HTTP, dwie metody serwisu.
        views = (
            await service.copy_block(user=user, payload=payload)
            if payload.what == "block"
            else await service.copy(user=user, payload=payload)
        )
        return DaysResponse(items=[_to_day(view) for view in views], total=len(views))

    return router


# --- statystyki (BATCH_13) ----------------------------------------------------------


def _to_goal_progress(progress: Mapping[str, GoalMetric]) -> DayGoalProgressRead:
    """Słownik kafelków z serwisu → schemat czterech kafelków (jedno mapowanie)."""
    return DayGoalProgressRead(
        **{
            field: GoalMetricRead(
                value=metric.value,
                target=metric.target,
                delta=metric.delta,
                status=metric.status,
            )
            for field, metric in progress.items()
        }
    )


def _to_stats_day(stat: DayStat) -> StatsDayRead:
    goal = stat.goal
    return StatsDayRead(
        day=stat.day,
        has_plan=stat.has_plan,
        # `None` zostaje `None`: dzień bez planu to luka, nie zerowe wartości.
        nutrition=None if stat.nutrition is None else nutrition_read(stat.nutrition),
        goal=(
            None
            if goal is None
            else StatsGoalRead(
                kcal=goal.kcal,
                protein_g=goal.protein_g,
                fat_g=goal.fat_g,
                carbs_g=goal.carbs_g,
                valid_from=goal.valid_from,
            )
        ),
        status=StatsStatusRead(**stat.status),
    )


def _to_stats(stats: DailyStats) -> StatsDailyResponse:
    summary = stats.summary
    avg = summary.avg
    return StatsDailyResponse(
        days=[_to_stats_day(stat) for stat in stats.days],
        summary=StatsSummaryRead(
            days_in_range=summary.days_in_range,
            days_with_plan=summary.days_with_plan,
            avg=(
                None
                if avg is None
                else StatsAveragesRead(
                    kcal=avg.kcal,
                    protein_g=avg.protein_g,
                    fat_g=avg.fat_g,
                    carbs_g=avg.carbs_g,
                    fiber_g=avg.fiber_g,
                    sugars_g=avg.sugars_g,
                    glycemic_load=avg.glycemic_load,
                    complete=avg.complete,
                    missing=list(avg.missing),
                )
            ),
            goal_progress=_to_goal_progress(summary.progress),
        ),
    )


def build_stats_router() -> APIRouter:
    """Router `/stats` — agregaty dzienne widoku Statystyki (04_API §2).

    Wyłącznie odczyt: nic tu nie powstaje ani nie jest cache'owane w bazie
    (niezmiennik 02_DOMAIN §13.2), więc router nie ma metod mutujących.
    """
    router = APIRouter(prefix="/stats", tags=["planning"])

    @router.get(
        "/daily",
        response_model=StatsDailyResponse,
        summary="Agregaty dzienne zakresu: wartości, cel z dnia, statusy i średnie",
    )
    async def daily_stats(
        user: CurrentUser,
        service: StatsDep,
        date_from: Annotated[date, Query(alias="from")],
        date_to: Annotated[date, Query(alias="to")],
    ) -> StatsDailyResponse:
        return _to_stats(await service.daily(user, date_from=date_from, date_to=date_to))

    return router


def _to_instantiate(result: InstantiateResult) -> InstantiateResponse:
    return InstantiateResponse(
        items=[_to_day(view) for view in result.days],
        total=len(result.days),
        warnings=result.warnings,
    )


def _to_cycle(view: CycleView) -> CycleRead:
    cycle = view.cycle
    return CycleRead(
        id=cycle.id,
        name=cycle.name,
        scope=cycle.scope,
        owner_user_id=cycle.owner_user_id,
        template_ids=list(cycle.template_ids),
        template_names=view.template_names,
        start_date=cycle.start_date,
        created_at=cycle.created_at,
        updated_at=cycle.updated_at,
    )


def build_templates_router() -> APIRouter:
    """Router `/templates` — szablony dnia i tygodnia (CRUD + instancjacja)."""
    router = APIRouter(prefix="/templates", tags=["planning"])

    # --- szablony dnia ---------------------------------------------------------------

    @router.get(
        "/days",
        response_model=TemplateListResponse,
        summary="Widoczne szablony dnia (bez payloadów)",
    )
    async def list_day_templates(user: CurrentUser, service: TemplatesDep) -> TemplateListResponse:
        templates = await service.list_day_templates(user)
        items = [
            TemplateSummaryRead(
                id=template.id,
                name=template.name,
                scope=template.scope,
                owner_user_id=template.owner_user_id,
                summary=day_summary(DayTemplatePayload.model_validate(template.payload)),
                created_at=template.created_at,
                updated_at=template.updated_at,
            )
            for template in templates
        ]
        return TemplateListResponse(items=items, total=len(items))

    @router.post(
        "/days",
        response_model=DayTemplateReadFull,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy szablon dnia — payload wprost albo zbudowany z dnia planu",
    )
    async def create_day_template(
        payload: DayTemplateWriteRequest, user: CurrentUser, service: TemplatesDep
    ) -> DayTemplateReadFull:
        return _to_day_template(await service.create_day_template(user=user, payload=payload))

    @router.get(
        "/days/{template_id}",
        response_model=DayTemplateReadFull,
        summary="Szablon dnia z payloadem",
    )
    async def get_day_template(
        template_id: int, user: CurrentUser, service: TemplatesDep
    ) -> DayTemplateReadFull:
        return _to_day_template(await service.get_day_template(template_id, user=user))

    @router.put(
        "/days/{template_id}",
        response_model=DayTemplateReadFull,
        summary="Nadpisanie CAŁEGO szablonu dnia (edycji per posiłek nie ma — 03_DB §6)",
    )
    async def update_day_template(
        template_id: int,
        payload: DayTemplateWriteRequest,
        user: CurrentUser,
        service: TemplatesDep,
    ) -> DayTemplateReadFull:
        template = await service.update_day_template(template_id, user=user, payload=payload)
        return _to_day_template(template)

    @router.delete(
        "/days/{template_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie szablonu dnia (właściciel albo ADMIN)",
    )
    async def delete_day_template(
        template_id: int, user: CurrentUser, service: TemplatesDep
    ) -> None:
        await service.delete_day_template(template_id, user=user)

    @router.post(
        "/days/{template_id}/instantiate",
        response_model=InstantiateResponse,
        summary="Szablon dnia → plan na wskazane daty (dopisuje, jak /plan/copy)",
    )
    async def instantiate_day_template(
        template_id: int,
        payload: InstantiateDayRequest,
        user: CurrentUser,
        service: TemplatesDep,
    ) -> InstantiateResponse:
        result = await service.instantiate_day_template(template_id, user=user, dates=payload.dates)
        return _to_instantiate(result)

    # --- szablony tygodnia -----------------------------------------------------------

    @router.get(
        "/weeks",
        response_model=TemplateListResponse,
        summary="Widoczne szablony tygodnia (bez payloadów)",
    )
    async def list_week_templates(user: CurrentUser, service: TemplatesDep) -> TemplateListResponse:
        templates = await service.list_week_templates(user)
        items = [
            TemplateSummaryRead(
                id=template.id,
                name=template.name,
                scope=template.scope,
                owner_user_id=template.owner_user_id,
                summary=week_summary(WeekTemplatePayload.model_validate(template.payload)),
                created_at=template.created_at,
                updated_at=template.updated_at,
            )
            for template in templates
        ]
        return TemplateListResponse(items=items, total=len(items))

    @router.post(
        "/weeks",
        response_model=WeekTemplateReadFull,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy szablon tygodnia — payload wprost albo z 7 dni planu",
    )
    async def create_week_template(
        payload: WeekTemplateWriteRequest, user: CurrentUser, service: TemplatesDep
    ) -> WeekTemplateReadFull:
        return _to_week_template(await service.create_week_template(user=user, payload=payload))

    @router.get(
        "/weeks/{template_id}",
        response_model=WeekTemplateReadFull,
        summary="Szablon tygodnia z payloadem",
    )
    async def get_week_template(
        template_id: int, user: CurrentUser, service: TemplatesDep
    ) -> WeekTemplateReadFull:
        return _to_week_template(await service.get_week_template(template_id, user=user))

    @router.put(
        "/weeks/{template_id}",
        response_model=WeekTemplateReadFull,
        summary="Nadpisanie CAŁEGO szablonu tygodnia",
    )
    async def update_week_template(
        template_id: int,
        payload: WeekTemplateWriteRequest,
        user: CurrentUser,
        service: TemplatesDep,
    ) -> WeekTemplateReadFull:
        template = await service.update_week_template(template_id, user=user, payload=payload)
        return _to_week_template(template)

    @router.delete(
        "/weeks/{template_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie szablonu tygodnia (409, gdy używa go cykl)",
    )
    async def delete_week_template(
        template_id: int, user: CurrentUser, service: TemplatesDep
    ) -> None:
        await service.delete_week_template(template_id, user=user)

    @router.post(
        "/weeks/{template_id}/instantiate",
        response_model=InstantiateResponse,
        summary="Szablon tygodnia → 7 dni planu od poniedziałku (jedna transakcja)",
    )
    async def instantiate_week_template(
        template_id: int,
        payload: InstantiateWeekRequest,
        user: CurrentUser,
        service: TemplatesDep,
    ) -> InstantiateResponse:
        result = await service.instantiate_week_template(
            template_id, user=user, week_start=payload.week_start
        )
        return _to_instantiate(result)

    return router


def build_cycles_router() -> APIRouter:
    """Router `/cycles` — cykle tygodni A→B→C i ich stosowanie na zakres dat."""
    router = APIRouter(prefix="/cycles", tags=["planning"])

    @router.get("", response_model=CycleListResponse, summary="Widoczne cykle tygodni")
    async def list_cycles(user: CurrentUser, service: TemplatesDep) -> CycleListResponse:
        views = await service.list_cycles(user)
        return CycleListResponse(items=[_to_cycle(view) for view in views], total=len(views))

    @router.post(
        "",
        response_model=CycleRead,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy cykl — kolejność szablonów JEST rotacją",
    )
    async def create_cycle(
        payload: CycleWriteRequest, user: CurrentUser, service: TemplatesDep
    ) -> CycleRead:
        return _to_cycle(await service.create_cycle(user=user, payload=payload))

    @router.put(
        "/{cycle_id}",
        response_model=CycleRead,
        summary="Edycja cyklu (nazwa, kolejność szablonów, start rotacji)",
    )
    async def update_cycle(
        cycle_id: int, payload: CycleWriteRequest, user: CurrentUser, service: TemplatesDep
    ) -> CycleRead:
        return _to_cycle(await service.update_cycle(cycle_id, user=user, payload=payload))

    @router.delete(
        "/{cycle_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie cyklu (szablonów nie rusza)",
    )
    async def delete_cycle(cycle_id: int, user: CurrentUser, service: TemplatesDep) -> None:
        await service.delete_cycle(cycle_id, user=user)

    @router.post(
        "/{cycle_id}/apply",
        response_model=InstantiateResponse,
        summary="Rotacyjna instancjacja szablonów cyklu na zakres dat (od poniedziałku)",
    )
    async def apply_cycle(
        cycle_id: int, payload: CycleApplyRequest, user: CurrentUser, service: TemplatesDep
    ) -> InstantiateResponse:
        return _to_instantiate(await service.apply_cycle(cycle_id, user=user, payload=payload))

    return router
