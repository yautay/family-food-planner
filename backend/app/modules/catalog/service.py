"""Logika modułu catalog: produkty kanoniczne, kategorie i przeliczniki jednostek.

Katalog jest GLOBALNY (02_DOMAIN §3.1 pkt 3) — nie ma tu `ScopedQuery`, bo nie
ma czego zawężać: każdy zalogowany użytkownik widzi ten sam słownik. Różnicują
się uprawnienia do ZAPISU i egzekwuje je router (`CurrentUser` vs `AdminUser`):

- USER: tworzy produkty (inline create → `UNVERIFIED`), edytuje pola opisowe
  POZA sposobem liczenia, archiwizuje i przywraca, zarządza przelicznikami
  jednostek domowych,
- ADMIN: dodatkowo wartości odżywcze (`PUT /nutrition`), weryfikacja
  (`POST /verify`), usuwanie produktów (D13), zmiana `measure_kind`
  i `piece_weight_g` (D15) oraz CRUD kategorii.

Dwie reguły roli siedzą w SERWISIE, nie w routerze (D13 i D15): endpoint
zostaje na `CurrentUser`, żeby odpowiedź 403 mogła podpowiedzieć wyjście —
archiwizację albo prośbę do administratora — zamiast suchego „brak uprawnień".

Każda zmiana wartości i każda weryfikacja zostawia wpis w dzienniku z payloadem
`{"before": ..., "after": ...}` — silnik liczy na tych danych, więc muszą być
rozliczalne (02_DOMAIN §12). `AuditService.record()` nie commituje: wpis
powstaje w tej samej transakcji co operacja.

Serwis oddaje `ProductView` (dane zmaterializowane), nigdy encji z leniwymi
relacjami — warstwa HTTP jest synchroniczna i sięgnięcie po niezaładowaną
relację kończy się `MissingGreenlet` i odpowiedzią 500 (lekcja z BATCH_03).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deletion import (
    USED_IN_LIMIT,
    UsedInRef,
    assert_deletable,
    conflict_from_integrity_error,
)
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.modules.accounts.models import User, UserRole
from app.modules.audit.service import AuditAction, AuditEntity, AuditService
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    Perishability,
    ProductCategory,
    ProductNutrientValue,
    ProductUnitWeight,
    VerificationStatus,
)
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.nutrition_adapter import ProductNutrition, nutrition_for
from app.modules.catalog.unit_weights import merge_samples
from app.modules.catalog.units import PIECE_LABEL, canonical_unit_label, normalize_unit_label

PRODUCT_NOT_FOUND = "Nie znaleziono produktu o podanym identyfikatorze."
CATEGORY_NOT_FOUND = "Nie znaleziono kategorii o podanym identyfikatorze."
UNIT_WEIGHT_NOT_FOUND = "Nie znaleziono przelicznika jednostki o podanym identyfikatorze."

PRODUCT_IN_USE = (
    "Produkt jest używany i nie może zostać usunięty. Zamiast usuwać, zarchiwizuj go — "
    "zniknie z wyszukiwarki i list wyboru, a dane historyczne zostaną nietknięte."
)
CATEGORY_IN_USE = (
    "Kategoria ma przypisane produkty i nie może zostać usunięta. "
    "Przenieś produkty do innej kategorii i spróbuj ponownie."
)
PRODUCT_DELETE_FORBIDDEN = (
    "Produkty kanoniczne usuwa wyłącznie administrator — katalog jest wspólny dla "
    "wszystkich rodzin. Możesz zarchiwizować produkt: zniknie z list wyboru."
)
MEASURE_KIND_FORBIDDEN = (
    "Sposób liczenia produktu może zmienić tylko administrator — te same liczby znaczą "
    "co innego na 100 g i na 100 ml. Poproś administratora albo utwórz nowy produkt."
)
UNIT_LABEL_TAKEN = "Ten produkt ma już przelicznik dla tej jednostki."
UNIT_LABEL_RESERVED = (
    "Jednostki „szt.” nie definiuje się przelicznikiem — wynika ona z wagi sztuki produktu."
)
UNIT_LABEL_REQUIRED = "Podaj nazwę jednostki domowej (np. łyżka, garść, opakowanie)."
VERIFY_INCOMPLETE = (
    "Weryfikacja wymaga kompletu wartości: kalorie, białko, tłuszcz, węglowodany "
    "oraz źródło danych."
)
PIECE_WEIGHT_REQUIRED = "Produkt mierzony w sztukach musi mieć podaną wagę jednej sztuki."
PIECE_WEIGHT_NOT_ALLOWED = "Wagę sztuki podaje się wyłącznie dla produktów mierzonych w sztukach."

#: Pola opisowe produktu, które wolno zmienić PATCH-em (USER). Wartości odżywcze
#: NIE są tu wymienione świadomie — te idą wyłącznie przez `PUT /nutrition`.
PRODUCT_EDITABLE_FIELDS = ("name", "category_id", "measure_kind", "perishability_override")

#: Kolumny rdzenia wartości odżywczych (ADR-004) — jedno źródło dla zapisu i audytu.
NUTRITION_FIELDS = (
    "kcal_100",
    "protein_100",
    "fat_100",
    "carbs_100",
    "fiber_100",
    "sugars_100",
    "glycemic_index",
)
#: Bez tych wartości nie da się policzyć nic sensownego, więc nie ma weryfikacji.
REQUIRED_FOR_VERIFICATION = ("kcal_100", "protein_100", "fat_100", "carbs_100")


class ProductValidationError(AppError):
    """422 — dane produktu są wewnętrznie sprzeczne (np. PIECE bez wagi sztuki).

    Nie `RequestValidationError`, bo tych reguł nie da się wyrazić w schemacie
    pojedynczego pola: zależą od stanu encji po zmianie.
    """

    status_code = 422
    code = "validation_error"


#: Funkcja licząca referencje do produktu w innym module.
ProductReferenceFinder = Callable[[AsyncSession, int], Awaitable[Sequence[UsedInRef]]]

#: Rejestr konsumentów katalogu. Moduły, które trzymają FK do `canonical_products`
#: (przepisy — B05, spiżarnia — B08, produkty sklepowe — B09, pozycje list — B11),
#: rejestrują tu funkcję zwracającą CZYTELNE nazwy miejsc użycia. Bez wpisu
#: użytkownik zobaczyłby 409 bez listy „Używane w:" — technicznie poprawne dzięki
#: FK RESTRICT, ale bezużyteczne (06_UIUX §3.3).
_PRODUCT_REFERENCE_FINDERS: list[ProductReferenceFinder] = []


def register_product_reference_finder(finder: ProductReferenceFinder) -> None:
    """Zarejestruj licznik referencji do produktu (wołane przy imporcie modułu)."""
    if finder not in _PRODUCT_REFERENCE_FINDERS:
        _PRODUCT_REFERENCE_FINDERS.append(finder)


def unregister_product_reference_finder(finder: ProductReferenceFinder) -> None:
    """Wyrejestruj licznik — testy sprzątają po sobie, żeby nie przeciekał dalej."""
    if finder in _PRODUCT_REFERENCE_FINDERS:
        _PRODUCT_REFERENCE_FINDERS.remove(finder)


@dataclass(frozen=True)
class ProductView:
    """Produkt razem z tym, co warstwa HTTP musi o nim wiedzieć."""

    product: CanonicalProduct
    category: ProductCategory
    unit_weights: list[ProductUnitWeight]
    nutrient_values: list[ProductNutrientValue]

    @property
    def nutrition(self) -> ProductNutrition:
        """Wartości widziane przez adapter — jedyne wejście do kompletności."""
        return nutrition_for(self.product, self.nutrient_values)


class CatalogService:
    """Operacje na katalogu produktów. Jedyne miejsce I/O tego modułu."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    # --- kategorie ---------------------------------------------------------------

    async def list_categories(self) -> list[ProductCategory]:
        """Cały słownik kategorii — kilkanaście pozycji, więc bez paginacji."""
        rows = (
            (
                await self._session.execute(
                    select(ProductCategory).order_by(ProductCategory.position, ProductCategory.name)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def get_category(self, category_id: int) -> ProductCategory:
        """Kategoria albo 404."""
        category = (
            await self._session.execute(
                select(ProductCategory)
                .where(ProductCategory.id == category_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if category is None:
            raise NotFoundError(CATEGORY_NOT_FOUND)
        return category

    async def create_category(
        self,
        *,
        actor: User,
        name: str,
        position: int,
        perishability: Perishability,
    ) -> ProductCategory:
        """Nowa kategoria (ADMIN). Nazwa jest unikalna w całej instancji."""
        category = ProductCategory(name=name, position=position, perishability=perishability)
        self._session.add(category)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"Kategoria „{name}” już istnieje.") from exc

        self._audit.record(
            action=AuditAction.CATEGORY_CREATE,
            entity_type=AuditEntity.PRODUCT_CATEGORY,
            entity_id=category.id,
            actor_id=actor.id,
            payload={"name": category.name, "perishability": category.perishability.value},
        )
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def update_category(
        self, category_id: int, *, actor: User, changes: Mapping[str, Any]
    ) -> ProductCategory:
        """Edycja kategorii (ADMIN): nazwa, kolejność, trwałość."""
        category = await self.get_category(category_id)
        before = self._category_snapshot(category)

        for field in ("name", "position", "perishability"):
            if field in changes:
                setattr(category, field, changes[field])

        after = self._category_snapshot(category)
        if before != after:
            self._audit.record(
                action=AuditAction.CATEGORY_UPDATE,
                entity_type=AuditEntity.PRODUCT_CATEGORY,
                entity_id=category.id,
                actor_id=actor.id,
                payload={"before": before, "after": after},
            )
            try:
                await self._session.commit()
            except IntegrityError as exc:
                await self._session.rollback()
                raise ConflictError("Kategoria o tej nazwie już istnieje.") from exc
            await self._session.refresh(category)
        return category

    async def delete_category(self, category_id: int, *, actor: User) -> None:
        """Usuń kategorię — wyłącznie pustą; inaczej 409 z listą produktów (ADR-012)."""
        category = await self.get_category(category_id)
        products = (
            (
                await self._session.execute(
                    select(CanonicalProduct)
                    .where(CanonicalProduct.category_id == category_id)
                    .order_by(CanonicalProduct.name)
                    .limit(USED_IN_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        assert_deletable(
            CATEGORY_IN_USE,
            [UsedInRef(type="product", id=item.id, name=item.name) for item in products],
        )

        name = category.name
        await self._session.execute(
            delete(ProductCategory).where(ProductCategory.id == category_id)
        )
        self._audit.record(
            action=AuditAction.CATEGORY_DELETE,
            entity_type=AuditEntity.PRODUCT_CATEGORY,
            entity_id=category_id,
            actor_id=actor.id,
            payload={"name": name},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Druga linia obrony: FK RESTRICT z modułów, które nie policzyły swoich
            # referencji. Bez tego użytkownik dostałby 500 zamiast 409.
            await self._session.rollback()
            raise conflict_from_integrity_error(CATEGORY_IN_USE) from exc

    # --- produkty: odczyt ---------------------------------------------------------

    async def get_product(self, product_id: int) -> CanonicalProduct:
        """Produkt albo 404. Katalog jest globalny, więc nie ma tu filtra scope."""
        product = (
            await self._session.execute(
                select(CanonicalProduct)
                .where(CanonicalProduct.id == product_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if product is None:
            raise NotFoundError(PRODUCT_NOT_FOUND)
        return product

    async def product_view(self, product_id: int) -> ProductView:
        """Produkt + kategoria + przeliczniki + wartości rozszerzone, doczytane jawnie."""
        product = await self.get_product(product_id)
        return (await self._views([product]))[0]

    async def _views(self, products: Sequence[CanonicalProduct]) -> list[ProductView]:
        """Widoki dla wielu produktów trzema zapytaniami — bez N+1 i bez lazy loadów."""
        if not products:
            return []
        product_ids = [product.id for product in products]

        categories = {
            category.id: category
            for category in (
                await self._session.execute(
                    select(ProductCategory).where(
                        ProductCategory.id.in_({product.category_id for product in products})
                    )
                )
            )
            .scalars()
            .all()
        }

        weights_by: dict[int, list[ProductUnitWeight]] = {
            product_id: [] for product_id in product_ids
        }
        for weight in (
            (
                await self._session.execute(
                    select(ProductUnitWeight)
                    .where(ProductUnitWeight.product_id.in_(product_ids))
                    .order_by(ProductUnitWeight.unit_label)
                )
            )
            .scalars()
            .all()
        ):
            weights_by[weight.product_id].append(weight)

        values_by: dict[int, list[ProductNutrientValue]] = {
            product_id: [] for product_id in product_ids
        }
        for value in (
            (
                await self._session.execute(
                    select(ProductNutrientValue)
                    .where(ProductNutrientValue.product_id.in_(product_ids))
                    .order_by(ProductNutrientValue.nutrient_code)
                )
            )
            .scalars()
            .all()
        ):
            values_by[value.product_id].append(value)

        return [
            ProductView(
                product=product,
                category=categories[product.category_id],
                unit_weights=weights_by[product.id],
                nutrient_values=values_by[product.id],
            )
            for product in products
        ]

    async def list_products(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
        category_id: int | None = None,
        verification_status: VerificationStatus | None = None,
        include_archived: bool = False,
    ) -> tuple[list[ProductView], int]:
        """Lista produktów z wyszukiwarką trigramową i filtrami (04_API §1)."""
        statement: Select[tuple[CanonicalProduct]] = select(CanonicalProduct)
        if not include_archived:
            statement = statement.where(CanonicalProduct.is_archived.is_(False))
        if category_id is not None:
            statement = statement.where(CanonicalProduct.category_id == category_id)
        if verification_status is not None:
            statement = statement.where(CanonicalProduct.verification_status == verification_status)

        phrase = (query or "").strip()
        ordering: tuple[Any, ...]
        if phrase:
            statement = statement.where(_search_condition(phrase))
            ordering = (_similarity(phrase).desc(), CanonicalProduct.name, CanonicalProduct.id)
        else:
            ordering = (CanonicalProduct.name, CanonicalProduct.id)

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    statement.order_by(*ordering)
                    .limit(limit)
                    .offset(offset)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return await self._views(list(rows)), total

    # --- produkty: zapis ----------------------------------------------------------

    async def create_product(
        self,
        *,
        actor: User,
        name: str,
        category_id: int,
        measure_kind: MeasureKind,
        piece_weight_g: Decimal | None = None,
        perishability_override: Perishability | None = None,
    ) -> ProductView:
        """Nowy produkt. Tworzy go także USER — powstaje jako `UNVERIFIED` (02_DOMAIN §4.9)."""
        product = await self.create_product_pending(
            actor=actor,
            name=name,
            category_id=category_id,
            measure_kind=measure_kind,
            piece_weight_g=piece_weight_g,
            perishability_override=perishability_override,
        )
        await self._session.commit()
        return await self.product_view(product.id)

    async def create_product_pending(
        self,
        *,
        actor: User,
        name: str,
        category_id: int,
        measure_kind: MeasureKind,
        piece_weight_g: Decimal | None = None,
        perishability_override: Perishability | None = None,
    ) -> CanonicalProduct:
        """Wiersz produktu BEZ commita — dla operacji, które muszą być jedną transakcją.

        Wzorzec z REVIEW R3 (`PantryService.receive_purchase`): metoda wołana
        w pętli po pozycjach JEDNEJ decyzji użytkownika nie commituje sama.
        Zatwierdzenie importu (BATCH_16) zakłada kilkanaście produktów naraz
        i albo powstają wszystkie razem z przepisami, albo żaden.
        """
        await self.get_category(category_id)
        _assert_piece_weight(measure_kind, piece_weight_g)

        normalized = normalize_name(name)
        existing = await self._find_by_normalized_name(normalized)
        if existing is not None:
            raise _duplicate_error(existing)

        product = CanonicalProduct(
            name=name,
            normalized_name=normalized,
            category_id=category_id,
            measure_kind=measure_kind,
            piece_weight_g=piece_weight_g,
            perishability_override=perishability_override,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        self._session.add(product)
        await self._session.flush()

        # Kto utworzył produkt, ma znaczenie: UNVERIFIED trafia do kolejki
        # weryfikacji, a admin chce wiedzieć, kogo zapytać o źródło danych.
        self._audit.record(
            action=AuditAction.PRODUCT_CREATE,
            entity_type=AuditEntity.PRODUCT,
            entity_id=product.id,
            actor_id=actor.id,
            payload={"name": product.name, "category_id": category_id},
        )
        return product

    async def find_by_name(self, name: str) -> CanonicalProduct | None:
        """Produkt o tym kluczu tożsamości (`naming.normalize_name`) albo `None`.

        Wejście dla importera: przed założeniem produktu z surowej nazwy trzeba
        sprawdzić, czy pod tym kluczem coś już nie stoi — także wiersz
        ZARCHIWIZOWANY, bo UNIQUE go nie odróżnia.
        """
        return await self._find_by_normalized_name(normalize_name(name))

    async def record_unit_weight_samples(
        self,
        product_id: int,
        *,
        actor: User,
        samples: Mapping[str, Sequence[Decimal]],
        source: str,
    ) -> list[ProductUnitWeight]:
        """Dołóż próbki przeliczników jednostek domowych; BEZ commita.

        Reguła łączenia i jej aproksymacja: `catalog/unit_weights.py`.

        **Czego ta metoda nie rusza**: wierszy o innym `source` niż podany.
        Przelicznik wpisany ręcznie (przez człowieka w UI albo przez ADMIN-a)
        jest decyzją, a nie pomiarem — import nie ma prawa jej nadpisać
        (Implementation Notes karty BATCH_16: „wpisów `source='manual'` NIE
        nadpisywać"). Rozszerzamy tę ochronę na wiersze BEZ źródła, bo dziś
        powstają właśnie tak: z ręki, przez `POST /products/{id}/unit-weights`.
        """
        touched: list[ProductUnitWeight] = []
        existing_rows = {
            row.unit_label: row
            for row in (
                await self._session.execute(
                    select(ProductUnitWeight).where(ProductUnitWeight.product_id == product_id)
                )
            )
            .scalars()
            .all()
        }

        for raw_label, values in samples.items():
            if not values:
                continue
            label = canonical_unit_label(raw_label)
            if label == PIECE_LABEL:
                # „szt." nie jest jednostką domową — mostkiem szt. → g jest
                # `piece_weight_g` produktu (ADR-005), nie ten wiersz.
                continue
            row = existing_rows.get(label)
            if row is not None and row.source != source:
                continue

            median, count = merge_samples(
                list(values),
                existing_median=row.grams_per_unit if row is not None else None,
                existing_count=row.samples_count if row is not None else 0,
            )
            if row is None:
                row = ProductUnitWeight(
                    product_id=product_id,
                    unit_label=label,
                    grams_per_unit=median,
                    source=source,
                    samples_count=count,
                )
                self._session.add(row)
                action = AuditAction.PRODUCT_UNIT_WEIGHT_CREATE
            else:
                row.grams_per_unit = median
                row.samples_count = count
                action = AuditAction.PRODUCT_UNIT_WEIGHT_UPDATE

            self._audit.record(
                action=action,
                entity_type=AuditEntity.PRODUCT,
                entity_id=product_id,
                actor_id=actor.id,
                payload={
                    "unit_label": label,
                    "grams_per_unit": format(median, "f"),
                    "samples_count": count,
                    "source": source,
                },
            )
            touched.append(row)

        await self._session.flush()
        return touched

    async def update_product(
        self, product_id: int, *, actor: User, changes: Mapping[str, Any]
    ) -> ProductView:
        """Edycja pól opisowych (USER). Wartości odżywcze mają osobny endpoint.

        Wyjątkiem są `measure_kind` i sprzężona z nim `piece_weight_g`: te
        zmienia wyłącznie ADMIN (D15, bramka w `_assert_measure_change_allowed`).
        """
        product = await self.get_product(product_id)
        _assert_measure_change_allowed(actor, product, changes)
        before = self._product_snapshot(product)

        if "category_id" in changes:
            await self.get_category(changes["category_id"])

        for field in PRODUCT_EDITABLE_FIELDS:
            if field in changes:
                setattr(product, field, changes[field])
        if "name" in changes:
            product.normalized_name = normalize_name(product.name)
        if "piece_weight_g" in changes:
            product.piece_weight_g = changes["piece_weight_g"]
        # Waga sztuki jest sprzężona z typem miary, więc sprawdzamy stan KOŃCOWY:
        # PATCH może zmienić którekolwiek z dwóch pól, także tylko jedno.
        if product.measure_kind is not MeasureKind.PIECE:
            product.piece_weight_g = None
        _assert_piece_weight(product.measure_kind, product.piece_weight_g)

        # D15 (02_DECISIONS): zmiana `measure_kind` przestawia podstawę wartości
        # („na 100 g" ⇄ „na 100 ml", ADR-004), więc na produkcie z jakimikolwiek
        # wartościami odżywczymi unieważnia weryfikację. Silnik nutrition (B05)
        # ma pokazać „niepełne dane", dopóki ADMIN nie sprawdzi liczb na nowej osi.
        if (
            product.measure_kind.value != before["measure_kind"]
            and product.verification_status is VerificationStatus.VERIFIED
            and any(getattr(product, field) is not None for field in NUTRITION_FIELDS)
        ):
            product.verification_status = VerificationStatus.UNVERIFIED
            product.verified_at = None

        duplicate = await self._find_by_normalized_name(
            product.normalized_name, exclude_id=product.id
        )
        if duplicate is not None:
            raise _duplicate_error(duplicate)

        after = self._product_snapshot(product)
        if before != after:
            self._audit.record(
                action=AuditAction.PRODUCT_UPDATE,
                entity_type=AuditEntity.PRODUCT,
                entity_id=product.id,
                actor_id=actor.id,
                payload={"before": before, "after": after},
            )
            await self._session.commit()
        return await self.product_view(product_id)

    async def set_nutrition(
        self,
        product_id: int,
        *,
        actor: User,
        values: Mapping[str, Decimal | None],
        nutrition_source: str | None,
    ) -> ProductView:
        """Pełna podmiana wartości odżywczych — wyłącznie ADMIN (08_TESTING §4).

        PUT, więc pole pominięte znaczy „skasuj wartość": po tej operacji stan
        odpowiada dokładnie temu, co przysłał administrator. Audit dostaje
        `{"before": ..., "after": ...}`, bo na tych liczbach opiera się cały
        silnik (02_DOMAIN §12).
        """
        product = await self.get_product(product_id)
        before = self._nutrition_snapshot(product)

        for field in NUTRITION_FIELDS:
            setattr(product, field, values.get(field))
        product.nutrition_source = nutrition_source

        after = self._nutrition_snapshot(product)
        if before != after:
            self._audit.record(
                action=AuditAction.PRODUCT_NUTRITION_UPDATE,
                entity_type=AuditEntity.PRODUCT,
                entity_id=product.id,
                actor_id=actor.id,
                payload={"before": before, "after": after},
            )
            await self._session.commit()
        return await self.product_view(product_id)

    async def verify_product(self, product_id: int, *, actor: User) -> ProductView:
        """`UNVERIFIED` → `VERIFIED` (ADMIN). Bez kompletu wartości — 422."""
        product = await self.get_product(product_id)

        missing = [field for field in REQUIRED_FOR_VERIFICATION if getattr(product, field) is None]
        if not (product.nutrition_source or "").strip():
            missing.append("nutrition_source")
        if missing:
            raise ProductValidationError(VERIFY_INCOMPLETE, details={"missing": missing})

        product.verification_status = VerificationStatus.VERIFIED
        product.verified_at = datetime.now(UTC)
        self._audit.record(
            action=AuditAction.PRODUCT_VERIFY,
            entity_type=AuditEntity.PRODUCT,
            entity_id=product.id,
            actor_id=actor.id,
            payload={"nutrition_source": product.nutrition_source},
        )
        await self._session.commit()
        return await self.product_view(product_id)

    async def set_archived(self, product_id: int, *, actor: User, archived: bool) -> ProductView:
        """Archiwizacja i jej cofnięcie (ADR-012) — bezpieczna alternatywa usuwania."""
        product = await self.get_product(product_id)
        if product.is_archived != archived:
            product.is_archived = archived
            self._audit.record(
                action=AuditAction.PRODUCT_ARCHIVE if archived else AuditAction.PRODUCT_RESTORE,
                entity_type=AuditEntity.PRODUCT,
                entity_id=product.id,
                actor_id=actor.id,
                payload={"name": product.name},
            )
            await self._session.commit()
        return await self.product_view(product_id)

    async def delete_product(self, product_id: int, *, actor: User) -> None:
        """Fizyczne usunięcie produktu — wyłącznie ADMIN i wyłącznie nieużywanego.

        D13 (02_DECISIONS): katalog jest wspólny dla wszystkich rodzin, więc
        usunięcie przez jednego użytkownika uderzałoby we wszystkie. USER — także
        twórca produktu — może wyłącznie archiwizować.
        """
        if actor.role is not UserRole.ADMIN:
            raise ForbiddenError(PRODUCT_DELETE_FORBIDDEN)

        product = await self.get_product(product_id)
        assert_deletable(PRODUCT_IN_USE, await self.product_references(product_id))

        name = product.name
        await self._session.execute(
            delete(CanonicalProduct).where(CanonicalProduct.id == product_id)
        )
        self._audit.record(
            action=AuditAction.PRODUCT_DELETE,
            entity_type=AuditEntity.PRODUCT,
            entity_id=product_id,
            actor_id=actor.id,
            payload={"name": name},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise conflict_from_integrity_error(PRODUCT_IN_USE) from exc

    async def product_references(self, product_id: int) -> list[UsedInRef]:
        """Gdzie produkt jest używany — suma odpowiedzi zarejestrowanych konsumentów.

        W BATCH_04 rejestr jest pusty (nie ma jeszcze przepisów ani spiżarni),
        więc lista zawsze wychodzi pusta. Mechanizm i kontrakt odpowiedzi 409
        powstają jednak TERAZ, bo obowiązują każde kolejne usuwanie (ADR-012).
        """
        references: list[UsedInRef] = []
        for finder in _PRODUCT_REFERENCE_FINDERS:
            references.extend(await finder(self._session, product_id))
        return references[:USED_IN_LIMIT]

    # --- przeliczniki jednostek domowych --------------------------------------------

    async def list_unit_weights(self, product_id: int) -> list[ProductUnitWeight]:
        """Przeliczniki produktu (404, gdy produktu nie ma)."""
        await self.get_product(product_id)
        rows = (
            (
                await self._session.execute(
                    select(ProductUnitWeight)
                    .where(ProductUnitWeight.product_id == product_id)
                    .order_by(ProductUnitWeight.unit_label)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_unit_weight(
        self,
        product_id: int,
        *,
        actor: User,
        unit_label: str,
        grams_per_unit: Decimal,
        source: str | None,
        samples_count: int,
    ) -> ProductUnitWeight:
        """Nowy przelicznik jednostki domowej (USER)."""
        await self.get_product(product_id)
        label = _clean_unit_label(unit_label)

        weight = ProductUnitWeight(
            product_id=product_id,
            unit_label=label,
            grams_per_unit=grams_per_unit,
            source=source,
            samples_count=samples_count,
        )
        self._session.add(weight)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(UNIT_LABEL_TAKEN, details={"unit_label": label}) from exc

        self._audit.record(
            action=AuditAction.PRODUCT_UNIT_WEIGHT_CREATE,
            entity_type=AuditEntity.PRODUCT,
            entity_id=product_id,
            actor_id=actor.id,
            payload={"unit_label": label, "grams_per_unit": _decimal_or_none(grams_per_unit)},
        )
        await self._session.commit()
        await self._session.refresh(weight)
        return weight

    async def update_unit_weight(
        self,
        product_id: int,
        unit_weight_id: int,
        *,
        actor: User,
        changes: Mapping[str, Any],
    ) -> ProductUnitWeight:
        """Edycja przelicznika (USER)."""
        weight = await self.get_unit_weight(product_id, unit_weight_id)
        before = self._unit_weight_snapshot(weight)

        if "unit_label" in changes:
            weight.unit_label = _clean_unit_label(changes["unit_label"])
        for field in ("grams_per_unit", "source", "samples_count"):
            if field in changes:
                setattr(weight, field, changes[field])

        after = self._unit_weight_snapshot(weight)
        if before != after:
            self._audit.record(
                action=AuditAction.PRODUCT_UNIT_WEIGHT_UPDATE,
                entity_type=AuditEntity.PRODUCT,
                entity_id=product_id,
                actor_id=actor.id,
                payload={"before": before, "after": after},
            )
            try:
                await self._session.commit()
            except IntegrityError as exc:
                await self._session.rollback()
                raise ConflictError(UNIT_LABEL_TAKEN) from exc
            await self._session.refresh(weight)
        return weight

    async def delete_unit_weight(
        self, product_id: int, unit_weight_id: int, *, actor: User
    ) -> None:
        """Usuń przelicznik. Nie ma tu blokady 409 — zapisane ilości są już
        znormalizowane do g/ml/szt., więc nic nie zależy od tego wiersza
        (niezmiennik 02_DOMAIN §13.1)."""
        weight = await self.get_unit_weight(product_id, unit_weight_id)
        label = weight.unit_label
        await self._session.execute(
            delete(ProductUnitWeight).where(ProductUnitWeight.id == unit_weight_id)
        )
        self._audit.record(
            action=AuditAction.PRODUCT_UNIT_WEIGHT_DELETE,
            entity_type=AuditEntity.PRODUCT,
            entity_id=product_id,
            actor_id=actor.id,
            payload={"unit_label": label},
        )
        await self._session.commit()

    async def get_unit_weight(self, product_id: int, unit_weight_id: int) -> ProductUnitWeight:
        """Przelicznik należący do TEGO produktu; cudzy albo nieistniejący → 404."""
        weight = await self._session.get(ProductUnitWeight, unit_weight_id)
        if weight is None or weight.product_id != product_id:
            raise NotFoundError(UNIT_WEIGHT_NOT_FOUND)
        return weight

    # --- pomocnicze ------------------------------------------------------------------

    async def _find_by_normalized_name(
        self, normalized: str, *, exclude_id: int | None = None
    ) -> CanonicalProduct | None:
        statement = select(CanonicalProduct).where(CanonicalProduct.normalized_name == normalized)
        if exclude_id is not None:
            statement = statement.where(CanonicalProduct.id != exclude_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    @staticmethod
    def _category_snapshot(category: ProductCategory) -> dict[str, Any]:
        return {
            "name": category.name,
            "position": category.position,
            "perishability": category.perishability.value,
        }

    @staticmethod
    def _product_snapshot(product: CanonicalProduct) -> dict[str, Any]:
        """Pola opisowe produktu w payloadzie audytu.

        `verification_status` jest tu od D15: zbicie weryfikacji przy zmianie
        `measure_kind` ma być widoczne w before/after wpisu `product.update`.
        """
        return {
            "name": product.name,
            "category_id": product.category_id,
            "measure_kind": product.measure_kind.value,
            "piece_weight_g": _decimal_or_none(product.piece_weight_g),
            "perishability_override": (
                None
                if product.perishability_override is None
                else product.perishability_override.value
            ),
            "verification_status": product.verification_status.value,
        }

    @staticmethod
    def _nutrition_snapshot(product: CanonicalProduct) -> dict[str, Any]:
        """Wartości odżywcze w payloadzie audytu — Decimal jako tekst, nigdy float."""
        snapshot: dict[str, Any] = {
            field: _decimal_or_none(getattr(product, field)) for field in NUTRITION_FIELDS
        }
        snapshot["nutrition_source"] = product.nutrition_source
        return snapshot

    @staticmethod
    def _unit_weight_snapshot(weight: ProductUnitWeight) -> dict[str, Any]:
        return {
            "unit_label": weight.unit_label,
            "grams_per_unit": _decimal_or_none(weight.grams_per_unit),
            "source": weight.source,
            "samples_count": weight.samples_count,
        }


def _similarity(phrase: str) -> ColumnElement[float]:
    """Podobieństwo trigramowe nazwy do frazy (pg_trgm) — klucz sortowania trafień."""
    return func.similarity(CanonicalProduct.name, phrase)


def _search_condition(phrase: str) -> ColumnElement[bool]:
    """Trafienie: prefiks znormalizowanej nazwy ALBO podobieństwo trigramowe.

    Prefiks łapie pisanie od początku nazwy („cebu" → „Cebula") jeszcze zanim
    podobieństwo CAŁYCH nazw przekroczy próg; trigram łapie literówki („cebual").
    Fraza wchodzi parametrem SQLAlchemy — żadnego sklejania SQL-a z tekstem
    użytkownika (07_SECURITY).

    `autoescape=True` jest konieczne: bez niego `%` i `_` z wpisanej frazy
    działałyby jak wieloznaczniki LIKE, więc szukanie „jogurt 0%" pasowałoby
    do wszystkiego zaczynającego się od „jogurt 0".
    """
    threshold = get_settings().catalog_search_similarity_threshold
    return or_(
        CanonicalProduct.normalized_name.startswith(normalize_name(phrase), autoescape=True),
        _similarity(phrase) >= threshold,
    )


def _assert_measure_change_allowed(
    actor: User, product: CanonicalProduct, changes: Mapping[str, Any]
) -> None:
    """D15 (02_DECISIONS): `measure_kind` zmienia WYŁĄCZNIE ADMIN.

    `measure_kind` decyduje, czy wartości produktu znaczą „na 100 g", czy
    „na 100 ml" (ADR-004), a katalog jest GLOBALNY — przestawienie podstawy
    przez jednego użytkownika uderza we wszystkie rodziny. `piece_weight_g`
    jedzie z tą samą bramką, bo jest z miarą sprzężone (`_assert_piece_weight`):
    bez tego USER przestawiłby wagę sztuki i zmienił wynik przeliczeń, nie
    ruszając samego pola miary.

    Porównujemy WARTOŚCI, nie obecność klucza: formularz produktu wysyła oba
    pola przy każdym zapisie, więc bramka na samej obecności zablokowałaby
    USEROWI także zmianę nazwy czy kategorii — a te wolno mu zmieniać
    (08_TESTING §4, wymóg testu macierzy z karty B09).

    Bramka siedzi w serwisie, nie w routerze (wzorzec D13): dzięki temu 403 może
    podpowiedzieć wyjście — prośbę do administratora albo nowy produkt.
    """
    if actor.role is UserRole.ADMIN:
        return
    if "measure_kind" in changes and changes["measure_kind"] != product.measure_kind:
        raise ForbiddenError(MEASURE_KIND_FORBIDDEN)
    if "piece_weight_g" in changes and changes["piece_weight_g"] != product.piece_weight_g:
        raise ForbiddenError(MEASURE_KIND_FORBIDDEN)


def _assert_piece_weight(measure_kind: MeasureKind, piece_weight_g: Decimal | None) -> None:
    """Waga sztuki istnieje dokładnie dla produktów mierzonych w sztukach."""
    if measure_kind is MeasureKind.PIECE and piece_weight_g is None:
        raise ProductValidationError(PIECE_WEIGHT_REQUIRED)
    if measure_kind is not MeasureKind.PIECE and piece_weight_g is not None:
        raise ProductValidationError(PIECE_WEIGHT_NOT_ALLOWED)


def _clean_unit_label(unit_label: str) -> str:
    """Etykieta do zapisu: kanoniczna, żeby UNIQUE faktycznie łapał duplikaty.

    „Łyżka", „łyżka " i „ŁYŻKA" to jeden przelicznik; „opak." i „opakowanie" też.
    """
    label = canonical_unit_label(unit_label)
    if not normalize_unit_label(unit_label):
        raise ProductValidationError(UNIT_LABEL_REQUIRED)
    if label == PIECE_LABEL:
        raise ProductValidationError(UNIT_LABEL_RESERVED)
    return label


def _duplicate_error(existing: CanonicalProduct) -> ConflictError:
    """409 z podpowiedzią istniejącego produktu.

    `existing` w `details` jest kluczowy dla inline create: picker może od razu
    zaproponować „Ten produkt już jest — wybrać go?" zamiast zostawiać
    użytkownika z samym komunikatem o błędzie (06_UIUX §3.1).
    """
    return ConflictError(
        f"Produkt „{existing.name}” już istnieje w katalogu.",
        details={
            "existing": {
                "id": existing.id,
                "name": existing.name,
                "is_archived": existing.is_archived,
            }
        },
    )


def _decimal_or_none(value: Decimal | None) -> str | None:
    """`Decimal` → tekst bez notacji wykładniczej; `None` zostaje `None`."""
    return None if value is None else format(value, "f")
