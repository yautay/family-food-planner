"""HTTP modułu catalog: `/products`, `/categories`, `/stores`, `/retail-products`.

Podział uprawnień (04_API §2, 08_TESTING §4) jest widoczny wprost w sygnaturach:

- `CurrentUser` — lista i szczegóły produktów, tworzenie (inline create),
  edycja pól opisowych, archiwizacja, przeliczniki jednostek domowych oraz
  CAŁE sklepy i produkty sklepowe (02_DOMAIN §3.1 pkt 3 i 4),
- `AdminUser` — wartości odżywcze (`PUT /nutrition`), weryfikacja i mutacje
  słownika kategorii.

Dwa endpointy stoją na `CurrentUser`, choć reguła jest administracyjna:
`DELETE /products/{id}` (D13) i `PATCH /products/{id}` ze zmianą `measure_kind`
(D15). Bramkę egzekwuje serwis, żeby komunikat 403 mógł podpowiedzieć wyjście
(archiwizację, prośbę do administratora), a nie tylko odmówić.

Router nie zna reguł domenowych: sprawdza wejście, woła serwis, mapuje wynik.
Kompletność wartości liczy adapter `ProductNutrition` (przez `ProductView`),
a nie ten moduł.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.core.deps import (
    AdminUser,
    CurrentUser,
    get_catalog_service,
    get_retail_service,
    get_stores_service,
)
from app.core.uploads import MAX_IMAGE_BYTES, image_urls
from app.modules.catalog.models import (
    ProductCategory,
    ProductUnitWeight,
    Store,
    VerificationStatus,
)
from app.modules.catalog.retail_service import RetailProductView, RetailService
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
    ProductSort,
    ProductUpdateRequest,
    RetailProductCreateRequest,
    RetailProductListResponse,
    RetailProductRead,
    RetailProductUpdateRequest,
    StoreCategoryOrderEntry,
    StoreCategoryOrderRequest,
    StoreCategoryOrderResponse,
    StoreCreateRequest,
    StoreListResponse,
    StoreRead,
    StoreUpdateRequest,
    UnitWeightCreateRequest,
    UnitWeightListResponse,
    UnitWeightRead,
    UnitWeightUpdateRequest,
)
from app.modules.catalog.service import NUTRITION_FIELDS, CatalogService, ProductView
from app.modules.catalog.stores_service import CategoryOrderEntry, StoresService

ServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
StoresServiceDep = Annotated[StoresService, Depends(get_stores_service)]
RetailServiceDep = Annotated[RetailService, Depends(get_retail_service)]


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


def _stores_response(stores: list[Store]) -> StoreListResponse:
    items = [StoreRead.model_validate(store) for store in stores]
    return StoreListResponse(items=items, total=len(items))


def _category_order_response(entries: list[CategoryOrderEntry]) -> StoreCategoryOrderResponse:
    items = [
        StoreCategoryOrderEntry(
            category_id=entry.category_id,
            category_name=entry.category_name,
            position=entry.position,
        )
        for entry in entries
    ]
    return StoreCategoryOrderResponse(items=items, total=len(items))


def _to_retail_read(view: RetailProductView) -> RetailProductRead:
    """`RetailProductView` → schemat odpowiedzi (URL-e zdjęcia, nie ścieżki z dysku)."""
    retail = view.retail
    photo_url, photo_thumb_url = image_urls(retail.photo_path)
    return RetailProductRead(
        id=retail.id,
        canonical_product_id=retail.canonical_product_id,
        canonical_product_name=view.product.name,
        name=retail.name,
        brand=retail.brand,
        store_id=retail.store_id,
        store_name=view.store.name if view.store is not None else None,
        package_amount=retail.package_amount,
        package_unit=retail.package_unit,
        pieces_per_package=retail.pieces_per_package,
        photo_url=photo_url,
        photo_thumb_url=photo_thumb_url,
        is_archived=retail.is_archived,
        created_at=retail.created_at,
        updated_at=retail.updated_at,
    )


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
        sort: ProductSort = ProductSort.NAME,
    ) -> ProductListResponse:
        views, total = await service.list_products(
            limit=limit,
            offset=offset,
            query=q,
            category_id=category_id,
            verification_status=verification_status,
            include_archived=include_archived,
            sort=sort,
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


def build_stores_router() -> APIRouter:
    """Router `/stores` — słownik globalny; wszystko dla zalogowanego USERA.

    Nie ma tu `AdminUser` ani jednego endpointu: sklepy i ich profile edytuje
    każdy członek instancji (02_DOMAIN §3.1 pkt 3), bo kolejność przejścia po
    sklepie to wiedza tego, kto w nim robi zakupy, a nie decyzja administratora.
    """
    router = APIRouter(prefix="/stores", tags=["catalog"])

    @router.get("", response_model=StoreListResponse, summary="Lista sklepów")
    async def list_stores(
        user: CurrentUser, service: StoresServiceDep, include_archived: bool = False
    ) -> StoreListResponse:
        return _stores_response(await service.list_stores(include_archived=include_archived))

    @router.post(
        "",
        response_model=StoreRead,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie sklepu (także inline z pickera)",
    )
    async def create_store(
        payload: StoreCreateRequest, user: CurrentUser, service: StoresServiceDep
    ) -> StoreRead:
        store = await service.create_store(actor=user, name=payload.name, color=payload.color)
        return StoreRead.model_validate(store)

    @router.patch("/{store_id}", response_model=StoreRead, summary="Edycja sklepu")
    async def update_store(
        store_id: int,
        payload: StoreUpdateRequest,
        user: CurrentUser,
        service: StoresServiceDep,
    ) -> StoreRead:
        store = await service.update_store(
            store_id, actor=user, changes=payload.model_dump(exclude_unset=True)
        )
        return StoreRead.model_validate(store)

    @router.delete(
        "/{store_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie sklepu (tylko nieużywanego — 409 z listą użyć)",
    )
    async def delete_store(store_id: int, user: CurrentUser, service: StoresServiceDep) -> None:
        await service.delete_store(store_id, actor=user)

    @router.get(
        "/{store_id}/category-order",
        response_model=StoreCategoryOrderResponse,
        summary="Kolejność kategorii w tym sklepie",
    )
    async def get_category_order(
        store_id: int, user: CurrentUser, service: StoresServiceDep
    ) -> StoreCategoryOrderResponse:
        return _category_order_response(await service.category_order(store_id))

    @router.put(
        "/{store_id}/category-order",
        response_model=StoreCategoryOrderResponse,
        summary="Pełna podmiana kolejności kategorii (lista `category_id` w kolejności)",
    )
    async def set_category_order(
        store_id: int,
        payload: StoreCategoryOrderRequest,
        user: CurrentUser,
        service: StoresServiceDep,
    ) -> StoreCategoryOrderResponse:
        entries = await service.set_category_order(
            store_id, actor=user, category_ids=payload.category_ids
        )
        return _category_order_response(entries)

    return router


def build_retail_products_router() -> APIRouter:
    """Router `/retail-products` — warianty sklepowe produktów kanonicznych."""
    router = APIRouter(prefix="/retail-products", tags=["catalog"])

    @router.get("", response_model=RetailProductListResponse, summary="Lista produktów sklepowych")
    async def list_retail_products(
        user: CurrentUser,
        service: RetailServiceDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        canonical_product_id: Annotated[int | None, Query(ge=1)] = None,
        store_id: Annotated[int | None, Query(ge=1)] = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        include_archived: bool = False,
    ) -> RetailProductListResponse:
        views, total = await service.list_retail_products(
            limit=limit,
            offset=offset,
            canonical_product_id=canonical_product_id,
            store_id=store_id,
            query=q,
            include_archived=include_archived,
        )
        return RetailProductListResponse(
            items=[_to_retail_read(view) for view in views], total=total
        )

    @router.post(
        "",
        response_model=RetailProductRead,
        status_code=status.HTTP_201_CREATED,
        summary="Dodanie produktu sklepowego (wymaga produktu kanonicznego)",
    )
    async def create_retail_product(
        payload: RetailProductCreateRequest, user: CurrentUser, service: RetailServiceDep
    ) -> RetailProductRead:
        return _to_retail_read(
            await service.create_retail_product(
                actor=user,
                canonical_product_id=payload.canonical_product_id,
                name=payload.name,
                brand=payload.brand,
                store_id=payload.store_id,
                package_amount=payload.package_amount,
                package_unit=payload.package_unit,
                pieces_per_package=payload.pieces_per_package,
            )
        )

    @router.patch(
        "/{retail_id}",
        response_model=RetailProductRead,
        summary="Edycja produktu sklepowego (także archiwizacja przez `is_archived`)",
    )
    async def update_retail_product(
        retail_id: int,
        payload: RetailProductUpdateRequest,
        user: CurrentUser,
        service: RetailServiceDep,
    ) -> RetailProductRead:
        return _to_retail_read(
            await service.update_retail_product(
                retail_id, actor=user, changes=payload.model_dump(exclude_unset=True)
            )
        )

    @router.delete(
        "/{retail_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Usunięcie produktu sklepowego (tylko nieużywanego — 409 z listą użyć)",
    )
    async def delete_retail_product(
        retail_id: int, user: CurrentUser, service: RetailServiceDep
    ) -> None:
        await service.delete_retail_product(retail_id, actor=user)

    @router.put(
        "/{retail_id}/photo",
        response_model=RetailProductRead,
        summary="Zdjęcie opakowania (multipart; sniffing, re-encode, miniatura)",
    )
    async def upload_photo(
        retail_id: int,
        user: CurrentUser,
        service: RetailServiceDep,
        file: Annotated[UploadFile, File(description="Plik obrazu, maks. 10 MB")],
    ) -> RetailProductRead:
        # Odczyt z sufitem: do RAM trafia najwyżej limit + 1 bajt — plik ponad
        # limit dostaje 413 z `save_image` bez materializowania całości (jak B05).
        data = await file.read(MAX_IMAGE_BYTES + 1)
        return _to_retail_read(await service.set_photo(retail_id, actor=user, data=data))

    @router.delete(
        "/{retail_id}/photo",
        response_model=RetailProductRead,
        summary="Usunięcie zdjęcia produktu sklepowego",
    )
    async def delete_photo(
        retail_id: int, user: CurrentUser, service: RetailServiceDep
    ) -> RetailProductRead:
        return _to_retail_read(await service.delete_photo(retail_id, actor=user))

    return router
