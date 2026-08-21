"""HTTP modułu shopping: `/shopping/*` (04_API §2).

Router nie zna reguł domenowych: waliduje wejście, woła serwis, mapuje widok na
schemat odpowiedzi. Widoczność egzekwuje serwis przez `ScopedQuery`, więc nie ma
tu żadnego filtra po rodzinie.

`datetime.now(UTC)` mieszka TUTAJ, a nie w serwisie — czas wchodzi do logiki
parametrem (ten sam wzorzec co `date.today()` w spiżarni, ustalenie review R2).
Zaokrąglenie ilości też jest tutaj: silnik liczy w pełnej precyzji, a krawędź
serializacji kwantyzuje do skali kolumn (ADR-008).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, get_shopping_service
from app.modules.shopping.engine import (
    PreviewIssue,
    PreviewLine,
    PreviewResult,
    PreviewRound,
    blocking_issues,
    quantize_amount,
    quantize_package,
)
from app.modules.shopping.models import ShoppingGeneration
from app.modules.shopping.schemas import (
    FinalizeResponse,
    GenerateRequest,
    GenerationRead,
    PreviewIssueRead,
    PreviewLineRead,
    PreviewRoundRead,
    ResolveRequest,
    RetailChoiceInput,
    RetailOptionRead,
    RoundConfigCreateRequest,
    RoundConfigListResponse,
    RoundConfigRead,
    RoundConfigUpdateRequest,
    ShoppingListItemRead,
    ShoppingListRead,
)
from app.modules.shopping.service import (
    GenerationView,
    ShoppingListView,
    ShoppingService,
)

ServiceDep = Annotated[ShoppingService, Depends(get_shopping_service)]

WEEKDAY_DOC = (
    "Dzień tygodnia zakupów w konwencji `date.weekday()`: **0 = poniedziałek**, "
    "6 = niedziela. `null` = tura bez ustalonego dnia."
)


def _line_read(line: PreviewLine) -> PreviewLineRead:
    """Pozycja preview → schemat odpowiedzi (tu zaokrąglamy ilości)."""
    return PreviewLineRead(
        round_key=line.round_key,
        product_id=line.product_id,
        label=line.label,
        amount_unit=line.unit,
        needed_amount=quantize_amount(line.needed_amount),
        raw_amount=quantize_amount(line.raw_amount),
        category_id=line.category_id,
        category_name=line.category_name,
        perishability=line.perishability,
        days=list(line.days),
        from_pantry_amount=(
            quantize_amount(line.from_pantry_amount)
            if line.from_pantry_amount is not None
            else None
        ),
        already_have=line.already_have,
        retail_product_id=line.retail_product_id,
        retail_label=line.retail_label,
        package_amount=(
            quantize_package(line.package_amount) if line.package_amount is not None else None
        ),
        packages_count=line.packages_count,
        leftover_amount=(
            quantize_amount(line.leftover_amount) if line.leftover_amount is not None else None
        ),
        retail_options=[
            RetailOptionRead(
                retail_product_id=option.retail_product_id,
                label=option.label,
                package_amount=quantize_package(option.package_amount),
                package_unit=option.package_unit,
                store_id=option.store_id,
                store_name=option.store_name,
            )
            for option in line.retail_options
        ],
    )


def _round_read(round_view: PreviewRound) -> PreviewRoundRead:
    return PreviewRoundRead(
        key=round_view.key,
        name=round_view.name,
        mode=round_view.mode,
        shopping_weekday=round_view.shopping_weekday,
        shopping_date=round_view.shopping_date,
        date_from=round_view.date_from,
        date_to=round_view.date_to,
        items=[_line_read(line) for line in round_view.items],
    )


def _issue_read(issue: PreviewIssue) -> PreviewIssueRead:
    return PreviewIssueRead(
        key=issue.key,
        kind=issue.kind,
        severity=issue.severity,
        message=issue.message,
        dismissed=issue.dismissed,
        product_id=issue.product_id,
        plan_item_id=issue.plan_item_id,
        pantry_item_id=issue.pantry_item_id,
    )


def _generation_read(generation: ShoppingGeneration, preview: PreviewResult) -> GenerationRead:
    """Generacja + preview → jedna odpowiedź (bez `params`: to wejście, nie treść)."""
    return GenerationRead(
        id=generation.id,
        date_from=generation.date_from,
        date_to=generation.date_to,
        use_pantry=generation.used_pantry,
        status=generation.status,
        scope=generation.scope,
        owner_user_id=generation.owner_user_id,
        household_id=generation.household_id,
        rounds=[_round_read(round_view) for round_view in preview.rounds],
        issues=[_issue_read(issue) for issue in preview.issues],
        retail_choices=[
            RetailChoiceInput(product_id=product_id, retail_product_id=retail_id)
            for product_id, retail_id in preview.retail_choices
        ],
        has_blockers=bool(blocking_issues(preview)),
        created_at=generation.created_at,
        updated_at=generation.updated_at,
    )


def _view_read(view: GenerationView) -> GenerationRead:
    return _generation_read(view.generation, view.preview)


def _list_read(view: ShoppingListView) -> ShoppingListRead:
    """Utworzona lista razem z pozycjami; `public_token` nie wychodzi (B11)."""
    return ShoppingListRead(
        id=view.shopping_list.id,
        generation_id=view.shopping_list.generation_id,
        name=view.shopping_list.name,
        round_name=view.shopping_list.round_name,
        store_id=view.shopping_list.store_id,
        expires_at=view.shopping_list.expires_at,
        items=[ShoppingListItemRead.model_validate(item) for item in view.items],
    )


def build_shopping_router() -> APIRouter:
    """Router `/shopping` — tury, generacja, rozstrzyganie niejasności, finalizacja."""
    router = APIRouter(prefix="/shopping", tags=["shopping"])

    @router.get(
        "/round-configs",
        response_model=RoundConfigListResponse,
        summary="Konfiguracja tur zakupowych (pierwsze użycie zasiewa preset)",
        description=(
            "Zwraca tury zakupowe użytkownika. Gdy nie ma ani jednej, zasiewa "
            "edytowalny preset z 02_DOMAIN §9.2 (Niedziela i Środa). " + WEEKDAY_DOC
        ),
    )
    async def list_round_configs(user: CurrentUser, service: ServiceDep) -> RoundConfigListResponse:
        rows = await service.list_round_configs(user)
        return RoundConfigListResponse(
            items=[RoundConfigRead.model_validate(row) for row in rows], total=len(rows)
        )

    @router.post(
        "/round-configs",
        response_model=RoundConfigRead,
        status_code=status.HTTP_201_CREATED,
        summary="Nowa tura zakupowa",
        description=WEEKDAY_DOC,
    )
    async def create_round_config(
        payload: RoundConfigCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> RoundConfigRead:
        entity = await service.create_round_config(
            user,
            name=payload.name,
            mode=payload.mode,
            covers_days=payload.covers_days,
            fresh_days=payload.fresh_days,
            shopping_weekday=payload.shopping_weekday,
            position=payload.position,
        )
        return RoundConfigRead.model_validate(entity)

    @router.patch(
        "/round-configs/{config_id}",
        response_model=RoundConfigRead,
        summary="Edycja tury zakupowej",
        description=WEEKDAY_DOC,
    )
    async def update_round_config(
        config_id: int,
        payload: RoundConfigUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> RoundConfigRead:
        changes: dict[str, object] = payload.model_dump(
            exclude_unset=True,
            exclude_none=True,
            exclude={"clear_shopping_weekday", "clear_fresh_days"},
        )
        if payload.clear_shopping_weekday:
            changes["shopping_weekday"] = None
        if payload.clear_fresh_days:
            changes["fresh_days"] = None
        entity = await service.update_round_config(config_id, user=user, changes=changes)
        return RoundConfigRead.model_validate(entity)

    @router.delete(
        "/round-configs/{config_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie tury zakupowej",
    )
    async def delete_round_config(config_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.delete_round_config(config_id, user=user)

    @router.post(
        "/generate",
        response_model=GenerationRead,
        status_code=status.HTTP_201_CREATED,
        summary="Generacja zakupów → podgląd (zapisuje wyłącznie szkic generacji)",
        description=(
            "Liczy podgląd zakupów dla zakresu dat i zapisuje szkic generacji "
            "(`status=preview`) razem z pełnym wejściem silnika. Listy zakupowe "
            "powstają dopiero w `finalize`. **`use_pantry` domyślnie `false`** — "
            "stan domowy odejmujemy wyłącznie na jawne życzenie (02_DOMAIN §8)."
        ),
    )
    async def generate(
        payload: GenerateRequest, user: CurrentUser, service: ServiceDep
    ) -> GenerationRead:
        return _view_read(
            await service.generate(
                user,
                date_from=payload.date_from,
                date_to=payload.date_to,
                use_pantry=payload.use_pantry,
                round_config_ids=payload.round_config_ids,
            )
        )

    @router.get(
        "/generations/{generation_id}",
        response_model=GenerationRead,
        summary="Odtworzenie podglądu generacji (deterministyczne)",
    )
    async def get_generation(
        generation_id: int, user: CurrentUser, service: ServiceDep
    ) -> GenerationRead:
        return _view_read(await service.get_generation(generation_id, user=user))

    @router.post(
        "/generations/{generation_id}/resolve",
        response_model=GenerationRead,
        summary="Decyzje w podglądzie: mam w domu, wybór wariantu, odłożenie niejasności",
        description=(
            "Pole pominięte zostaje bez zmian; pole podane ZASTĘPUJE cały zbiór. "
            "Każde wywołanie odświeża też katalog produktów sklepowych, więc wariant "
            "utworzony inline jest od razu dostępny do wyboru."
        ),
    )
    async def resolve(
        generation_id: int,
        payload: ResolveRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> GenerationRead:
        return _view_read(
            await service.resolve(
                generation_id,
                user=user,
                already_have=payload.already_have,
                retail_choices=(
                    None
                    if payload.retail_choices is None
                    else [
                        (choice.product_id, choice.retail_product_id)
                        for choice in payload.retail_choices
                    ]
                ),
                dismissed_issues=payload.dismissed_issues,
            )
        )

    @router.post(
        "/generations/{generation_id}/finalize",
        response_model=FinalizeResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Utworzenie list zakupowych z podglądu (po jednej na turę)",
        description=(
            "Nierozstrzygnięty bloker kończy się 409 z listą powodów w "
            "`details.issues`. Listy wygasają po 7 dniach (D10/ADR-010)."
        ),
    )
    async def finalize(
        generation_id: int, user: CurrentUser, service: ServiceDep
    ) -> FinalizeResponse:
        views = await service.finalize(generation_id, user=user, now=datetime.now(UTC))
        return FinalizeResponse(items=[_list_read(view) for view in views], total=len(views))

    @router.delete(
        "/generations/{generation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Odrzucenie szkicu generacji (miękko — historia zostaje)",
    )
    async def discard(generation_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.discard(generation_id, user=user)

    return router
