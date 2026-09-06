"""HTTP modułu recipes: `/recipes`, `/tags` i zdjęcie przepisu.

Router nie zna reguł domenowych: waliduje wejście (schemas), woła serwis,
mapuje widoki na schematy odpowiedzi. Scope egzekwuje serwis przez
`ScopedQuery` (04_API §3) — tu nie ma żadnego filtra widoczności.

Upload zdjęcia jest jedynym endpointem multipart: router czyta bajty
(to warstwa HTTP), a cały pipeline bezpieczeństwa (limit, sniffing,
re-encode, miniatura — 07_SECURITY §6) wykonuje serwis przez `core/uploads`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from slowapi import Limiter

from app.core.deps import CurrentUser, get_recipes_service
from app.core.ratelimits import PHOTO_UPLOAD_RATE_LIMIT
from app.core.scope import Scope
from app.core.uploads import image_urls
from app.modules.nutrition.schemas import nutrition_read
from app.modules.nutrition.types import NutritionValues
from app.modules.recipes.schemas import (
    RatingRequest,
    RatingResponse,
    RecipeDetail,
    RecipeIngredientRead,
    RecipeListResponse,
    RecipePayload,
    RecipeSummary,
    TagCreateRequest,
    TagListResponse,
    TagRead,
)
from app.modules.recipes.service import (
    IngredientView,
    RecipeDetailView,
    RecipesService,
    RecipeView,
)

ServiceDep = Annotated[RecipesService, Depends(get_recipes_service)]


def _photo_urls(photo_path: str | None) -> tuple[str | None, str | None]:
    """Ścieżka względna z DB → URL-e endpointu `/uploads/*` (oryginał + miniatura).

    Konwencja URL mieszka w `core/uploads` (jedno miejsce dla przepisów B05
    i wariantów sklepowych B09) — tutaj zostaje tylko nazwa lokalna.
    """
    return image_urls(photo_path)


def _to_summary(view: RecipeView, *, nutrition: NutritionValues | None = None) -> RecipeSummary:
    """Widok → schemat karty; `nutrition` nadpisuje wartości per porcja (szczegóły)."""
    recipe = view.recipe
    photo_url, photo_thumb_url = _photo_urls(recipe.photo_path)
    return RecipeSummary(
        id=recipe.id,
        name=recipe.name,
        scope=recipe.scope,
        owner_user_id=recipe.owner_user_id,
        base_servings=recipe.base_servings,
        prep_time_min=recipe.prep_time_min,
        difficulty=recipe.difficulty,
        source=recipe.source,
        is_archived=recipe.is_archived,
        photo_url=photo_url,
        photo_thumb_url=photo_thumb_url,
        tags=[TagRead.model_validate(tag) for tag in view.tags],
        avg_rating=view.avg_rating,
        ratings_count=view.ratings_count,
        my_rating=view.my_rating,
        nutrition=nutrition_read(nutrition if nutrition is not None else view.nutrition),
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


def _to_ingredient(view: IngredientView) -> RecipeIngredientRead:
    ingredient = view.ingredient
    return RecipeIngredientRead(
        id=ingredient.id,
        product_id=ingredient.product_id,
        product_name=view.product.name,
        measure_kind=view.product.measure_kind,
        display_qty=ingredient.display_qty,
        display_unit=ingredient.display_unit,
        amount=ingredient.amount,
        amount_unit=ingredient.amount_unit,
        scaled_amount=view.scaled_amount,
        note=ingredient.note,
        position=ingredient.position,
    )


def _to_detail(view: RecipeDetailView) -> RecipeDetail:
    # Szczegóły pokazują nutrition porcja x mnożnik, nie „na 1 porcję" z listy.
    summary = _to_summary(view.base, nutrition=view.nutrition)
    return RecipeDetail(
        **summary.model_dump(),
        instructions=view.base.recipe.instructions,
        servings=view.servings,
        ingredients=[_to_ingredient(item) for item in view.ingredients],
    )


def build_recipes_router(limiter: Limiter) -> APIRouter:
    """Router `/recipes` — CRUD, oceny i zdjęcie."""
    router = APIRouter(prefix="/recipes", tags=["recipes"])

    @router.get("", response_model=RecipeListResponse, summary="Lista i filtrowanie przepisów")
    async def list_recipes(
        user: CurrentUser,
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query(max_length=200)] = None,
        tag: Annotated[list[int] | None, Query()] = None,
        prep_time_max: Annotated[int | None, Query(ge=1, le=6000)] = None,
        difficulty_max: Annotated[int | None, Query(ge=1, le=10)] = None,
        rating_min: Annotated[int | None, Query(ge=1, le=5)] = None,
        scope: Scope | None = None,
        include_archived: bool = False,
    ) -> RecipeListResponse:
        views, total = await service.list_recipes(
            user,
            limit=limit,
            offset=offset,
            query=q,
            tag_ids=tag or (),
            prep_time_max=prep_time_max,
            difficulty_max=difficulty_max,
            rating_min=rating_min,
            scope=scope,
            include_archived=include_archived,
        )
        return RecipeListResponse(items=[_to_summary(view) for view in views], total=total)

    @router.post(
        "",
        response_model=RecipeDetail,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy przepis ze składnikami (normalizacja ilości przy zapisie)",
    )
    async def create_recipe(
        payload: RecipePayload, user: CurrentUser, service: ServiceDep
    ) -> RecipeDetail:
        return _to_detail(await service.create_recipe(actor=user, payload=payload))

    @router.get(
        "/{recipe_id}",
        response_model=RecipeDetail,
        summary="Szczegóły przepisu; ?servings= przelicza nutrition i składniki",
    )
    async def get_recipe(
        recipe_id: int,
        user: CurrentUser,
        service: ServiceDep,
        servings: Annotated[Decimal, Query(gt=Decimal("0"), le=Decimal("100"))] = Decimal("1"),
    ) -> RecipeDetail:
        return _to_detail(await service.recipe_detail(user, recipe_id, servings=servings))

    @router.put(
        "/{recipe_id}",
        response_model=RecipeDetail,
        summary="Pełna podmiana przepisu (składniki wymieniane kompletem)",
    )
    async def update_recipe(
        recipe_id: int,
        payload: RecipePayload,
        user: CurrentUser,
        service: ServiceDep,
    ) -> RecipeDetail:
        return _to_detail(await service.update_recipe(recipe_id, actor=user, payload=payload))

    @router.delete(
        "/{recipe_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie przepisu (właściciel/ADMIN; 409 gdy używany)",
    )
    async def delete_recipe(recipe_id: int, user: CurrentUser, service: ServiceDep) -> None:
        await service.delete_recipe(recipe_id, actor=user)

    @router.put(
        "/{recipe_id}/rating",
        response_model=RatingResponse,
        summary="Własna ocena 1-5 (upsert); odpowiedź zawiera średnią",
    )
    async def rate_recipe(
        recipe_id: int,
        payload: RatingRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> RatingResponse:
        view = await service.rate_recipe(recipe_id, actor=user, rating=payload.rating)
        return RatingResponse(
            my_rating=view.my_rating,
            avg_rating=view.avg_rating,
            ratings_count=view.ratings_count,
        )

    @router.post(
        "/{recipe_id}/photo",
        response_model=RecipeDetail,
        summary="Zdjęcie przepisu (multipart; sniffing, re-encode, miniatura)",
    )
    @limiter.limit(PHOTO_UPLOAD_RATE_LIMIT)
    async def upload_photo(
        request: Request,
        recipe_id: int,
        user: CurrentUser,
        service: ServiceDep,
        file: Annotated[UploadFile, File(description="Plik obrazu (limit: IMAGE_MAX_UPLOAD_MB)")],
    ) -> RecipeDetail:
        # `request` wymaga slowapi (adres klienta). Odczyt z sufitem: do RAM trafia
        # najwyżej limit + 1 bajt — plik ponad limit dostaje 413 z `save_image`
        # bez materializowania całości; sufit całego ciała pilnuje
        # `BodyLimitMiddleware` (B17).
        data = await file.read(service.image_max_bytes + 1)
        return _to_detail(await service.set_photo(recipe_id, actor=user, data=data))

    @router.delete(
        "/{recipe_id}/photo",
        response_model=RecipeDetail,
        summary="Usunięcie zdjęcia przepisu",
    )
    async def delete_photo(recipe_id: int, user: CurrentUser, service: ServiceDep) -> RecipeDetail:
        return _to_detail(await service.delete_photo(recipe_id, actor=user))

    return router


def build_tags_router() -> APIRouter:
    """Router `/tags` — słownik globalny; POST to inline create tagu użytkowego."""
    router = APIRouter(prefix="/tags", tags=["recipes"])

    @router.get("", response_model=TagListResponse, summary="Słownik tagów")
    async def list_tags(user: CurrentUser, service: ServiceDep) -> TagListResponse:
        items = [TagRead.model_validate(tag) for tag in await service.list_tags()]
        return TagListResponse(items=items, total=len(items))

    @router.post(
        "",
        response_model=TagRead,
        status_code=status.HTTP_201_CREATED,
        summary="Nowy tag użytkowy (inline create z multi-pickera)",
    )
    async def create_tag(
        payload: TagCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> TagRead:
        return TagRead.model_validate(await service.create_tag(actor=user, name=payload.name))

    return router
