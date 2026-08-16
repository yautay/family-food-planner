"""HTTP modułu catalog: `/products`, `/categories` i przeliczniki jednostek.

Podział uprawnień (04_API §2, 08_TESTING §4) jest widoczny wprost w sygnaturach:

- `CurrentUser` — lista i szczegóły produktów, tworzenie (inline create),
  edycja pól opisowych, archiwizacja, przeliczniki jednostek domowych,
- `AdminUser` — wartości odżywcze (`PUT /nutrition`), weryfikacja, usuwanie
  produktu (D13) i mutacje słownika kategorii.

Router nie zna reguł domenowych: sprawdza wejście, woła serwis, mapuje wynik.
Kompletność wartości liczy adapter `ProductNutrition` (przez `ProductView`),
a nie ten moduł.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import AdminUser, CurrentUser, get_catalog_service
from app.modules.catalog.models import ProductCategory, ProductUnitWeight, VerificationStatus
from app.modules.catalog.schemas import (
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryRead,
    CategoryUpdateRequest,
    NutritionCompleteness,
    ProductCreateRequest,
    ProductDetail,
    ProductListResponse,
    ProductNutritionRead,
    ProductNutritionRequest,
    ProductRead,
    ProductUpdateRequest,
    UnitWeightCreateRequest,
    UnitWeightListResponse,
    UnitWeightRead,
    UnitWeightUpdateRequest,
)
from app.modules.catalog.service import NUTRITION_FIELDS, CatalogService, ProductView

ServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]


def _to_read(view: ProductView) -> ProductRead:
    """`ProductView` → schemat listy. Router czyta wyłącznie dane zmaterializowane."""
    product = view.product
    nutrition = view.nutrition
    return ProductRead(
        id=product.id,
        name=product.name,
        normalized_name=product.normalized_name,
        category_id=view.category.id,
        category_name=view.category.name,
        measure_kind=product.measure_kind,
        piece_weight_g=product.piece_weight_g,
        verification_status=product.verification_status,
        verified_at=product.verified_at,
        # Trwałość efektywna: nadpisanie produktu wygrywa z kategorią
        # (02_DOMAIN §9.2) — konsumentem jest silnik zakupowy w B10.
        perishability=product.perishability_override or view.category.perishability,
        perishability_override=product.perishability_override,
        is_archived=product.is_archived,
        nutrition=ProductNutritionRead.model_validate(product),
        completeness=NutritionCompleteness(
            complete=nutrition.is_complete,
            has_core_macros=nutrition.has_core_macros,
            has_glycemic_index=nutrition.has_glycemic_index,
            missing=list(nutrition.missing),
        ),
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _to_detail(view: ProductView) -> ProductDetail:
    return ProductDetail(
        **_to_read(view).model_dump(),
        unit_weights=[UnitWeightRead.model_validate(weight) for weight in view.unit_weights],
    )


def _categories_response(categories: list[ProductCategory]) -> CategoryListResponse:
    items = [CategoryRead.model_validate(category) for category in categories]
    return CategoryListResponse(items=items, total=len(items))


def _unit_weights_response(weights: list[ProductUnitWeight]) -> UnitWeightListResponse:
    items = [UnitWeightRead.model_validate(weight) for weight in weights]
    return UnitWeightListResponse(items=items, total=len(items))


def build_products_router() -> APIRouter:
    """Router `/products` — katalog produktów kanonicznych."""
    router = APIRouter(prefix="/products", tags=["catalog"])

    @router.get("", response_model=ProductListResponse, summary="Lista i wyszukiwanie produktów")
    async def list_products(
        user: CurrentUser,
        service: ServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query(max_length=200)] = None,
        category_id: Annotated[int | None, Query(ge=1)] = None,
        verification_status: VerificationStatus | None = None,
        include_archived: bool = False,
    ) -> ProductListResponse:
        views, total = await service.list_products(
            limit=limit,
            offset=offset,
            query=q,
            category_id=category_id,
            verification_status=verification_status,
            include_archived=include_archived,
        )
        return ProductListResponse(items=[_to_read(view) for view in views], total=total)

    @router.post(
        "",
        response_model=ProductDetail,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie produktu (powstaje jako niezweryfikowany)",
    )
    async def create_product(
        payload: ProductCreateRequest, user: CurrentUser, service: ServiceDep
    ) -> ProductDetail:
        return _to_detail(
            await service.create_product(
                actor=user,
                name=payload.name,
                category_id=payload.category_id,
                measure_kind=payload.measure_kind,
                piece_weight_g=payload.piece_weight_g,
                perishability_override=payload.perishability_override,
            )
        )

    @router.get("/{product_id}", response_model=ProductDetail, summary="Szczegóły produktu")
    async def get_product(product_id: int, user: CurrentUser, service: ServiceDep) -> ProductDetail:
        return _to_detail(await service.product_view(product_id))

    @router.patch(
        "/{product_id}", response_model=ProductDetail, summary="Edycja pól opisowych produktu"
    )
    async def update_product(
        product_id: int,
        payload: ProductUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> ProductDetail:
        # `exclude_unset`: pole pominięte zostaje bez zmian, a jawne
        # `perishability_override: null` czyści nadpisanie trwałości.
        return _to_detail(
            await service.update_product(
                product_id, actor=user, changes=payload.model_dump(exclude_unset=True)
            )
        )

    @router.delete(
        "/{product_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie produktu (ADMIN, tylko nieużywanego — 409 z listą użyć)",
    )
    async def delete_product(product_id: int, user: CurrentUser, service: ServiceDep) -> None:
        # Świadomie `CurrentUser`, nie `AdminUser`: regułę „usuwa wyłącznie
        # administrator" (D13) egzekwuje serwis, żeby komunikat 403 mógł
        # podpowiedzieć archiwizację zamiast suchego „brak uprawnień".
        await service.delete_product(product_id, actor=user)

    @router.put(
        "/{product_id}/nutrition",
        response_model=ProductDetail,
        summary="Wartości odżywcze i IG (ADMIN, wpis w dzienniku before/after)",
    )
    async def set_nutrition(
        product_id: int,
        payload: ProductNutritionRequest,
        actor: AdminUser,
        service: ServiceDep,
    ) -> ProductDetail:
        values = payload.model_dump(include=set(NUTRITION_FIELDS))
        return _to_detail(
            await service.set_nutrition(
                product_id,
                actor=actor,
                values=values,
                nutrition_source=payload.nutrition_source,
            )
        )

    @router.post(
        "/{product_id}/verify",
        response_model=ProductDetail,
        summary="Weryfikacja produktu (ADMIN, wymaga kompletu wartości)",
    )
    async def verify_product(
        product_id: int, actor: AdminUser, service: ServiceDep
    ) -> ProductDetail:
        return _to_detail(await service.verify_product(product_id, actor=actor))

    @router.post(
        "/{product_id}/archive",
        response_model=ProductDetail,
        summary="Archiwizacja produktu (znika z list wyboru)",
    )
    async def archive_product(
        product_id: int, user: CurrentUser, service: ServiceDep
    ) -> ProductDetail:
        return _to_detail(await service.set_archived(product_id, actor=user, archived=True))

    @router.delete(
        "/{product_id}/archive",
        response_model=ProductDetail,
        summary="Przywrócenie produktu z archiwum",
    )
    async def restore_product(
        product_id: int, user: CurrentUser, service: ServiceDep
    ) -> ProductDetail:
        return _to_detail(await service.set_archived(product_id, actor=user, archived=False))

    @router.get(
        "/{product_id}/unit-weights",
        response_model=UnitWeightListResponse,
        summary="Przeliczniki jednostek domowych produktu",
    )
    async def list_unit_weights(
        product_id: int, user: CurrentUser, service: ServiceDep
    ) -> UnitWeightListResponse:
        return _unit_weights_response(await service.list_unit_weights(product_id))

    @router.post(
        "/{product_id}/unit-weights",
        response_model=UnitWeightRead,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie przelicznika jednostki domowej",
    )
    async def create_unit_weight(
        product_id: int,
        payload: UnitWeightCreateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> UnitWeightRead:
        weight = await service.create_unit_weight(
            product_id,
            actor=user,
            unit_label=payload.unit_label,
            grams_per_unit=payload.grams_per_unit,
            source=payload.source,
            samples_count=payload.samples_count,
        )
        return UnitWeightRead.model_validate(weight)

    @router.patch(
        "/{product_id}/unit-weights/{unit_weight_id}",
        response_model=UnitWeightRead,
        summary="Edycja przelicznika jednostki domowej",
    )
    async def update_unit_weight(
        product_id: int,
        unit_weight_id: int,
        payload: UnitWeightUpdateRequest,
        user: CurrentUser,
        service: ServiceDep,
    ) -> UnitWeightRead:
        weight = await service.update_unit_weight(
            product_id,
            unit_weight_id,
            actor=user,
            changes=payload.model_dump(exclude_unset=True),
        )
        return UnitWeightRead.model_validate(weight)

    @router.delete(
        "/{product_id}/unit-weights/{unit_weight_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie przelicznika jednostki domowej",
    )
    async def delete_unit_weight(
        product_id: int, unit_weight_id: int, user: CurrentUser, service: ServiceDep
    ) -> None:
        await service.delete_unit_weight(product_id, unit_weight_id, actor=user)

    return router


def build_categories_router() -> APIRouter:
    """Router `/categories` — odczyt dla każdego, mutacje wyłącznie dla ADMIN-a."""
    router = APIRouter(prefix="/categories", tags=["catalog"])

    @router.get("", response_model=CategoryListResponse, summary="Słownik kategorii zakupowych")
    async def list_categories(user: CurrentUser, service: ServiceDep) -> CategoryListResponse:
        return _categories_response(await service.list_categories())

    @router.post(
        "",
        response_model=CategoryRead,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie kategorii (ADMIN)",
    )
    async def create_category(
        payload: CategoryCreateRequest, actor: AdminUser, service: ServiceDep
    ) -> CategoryRead:
        category = await service.create_category(
            actor=actor,
            name=payload.name,
            position=payload.position,
            perishability=payload.perishability,
        )
        return CategoryRead.model_validate(category)

    @router.patch(
        "/{category_id}",
        response_model=CategoryRead,
        summary="Edycja kategorii (ADMIN)",
    )
    async def update_category(
        category_id: int,
        payload: CategoryUpdateRequest,
        actor: AdminUser,
        service: ServiceDep,
    ) -> CategoryRead:
        category = await service.update_category(
            category_id, actor=actor, changes=payload.model_dump(exclude_unset=True)
        )
        return CategoryRead.model_validate(category)

    @router.delete(
        "/{category_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie kategorii (ADMIN, tylko pustej — 409 z listą produktów)",
    )
    async def delete_category(category_id: int, actor: AdminUser, service: ServiceDep) -> None:
        await service.delete_category(category_id, actor=actor)

    return router
