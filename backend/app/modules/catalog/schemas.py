"""Schematy request/response modułu catalog (04_API §1 i §2).

Wszystkie wartości NUMERIC wychodzą jako stringi dziesiętne (`DecimalString`,
ADR-008): `"105.00"`, nie `105.0`. Dzięki temu OpenAPI opisuje je jako `string`,
`task fe-types` generuje `string`, a frontend nie ma okazji przepuścić ich przez
`Number()` i zgubić precyzji.

Wejście też jest `Decimal`, nie `float` — pydantic przyjmie zarówno `"1.5"`, jak
i `1.5`, ale w obu przypadkach zbuduje `Decimal`. Liczba zmiennoprzecinkowa
w JSON-ie o wartości niedającej się zapisać dokładnie (np. `0.1`) zostaje
odrzucona przez `decimal_places`, bo `Decimal(0.1)` ma kilkanaście cyfr po
przecinku — to jest ta „granica API", na której float nie przechodzi
(CLAUDE.md §2).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.schemas import DecimalString
from app.modules.catalog.models import MeasureKind, Perishability, VerificationStatus
from app.modules.catalog.units import AmountUnit

#: Nazwa produktu/kategorii/jednostki: przycinana PRZED sprawdzeniem długości,
#: więc `"   "` jest odrzucane, a nie zapisywane jako pusty string.
NonEmptyName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
#: Źródło danych o wartościach (`usda:...`, `producent:etykieta`, `manual`).
NutritionSource = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]

#: Waga jednej sztuki w gramach — NUMERIC(8,2), zawsze dodatnia.
PieceWeight = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("999999"), max_digits=8, decimal_places=2)
]
#: Kalorie na 100 g/ml — NUMERIC(7,2).
Kcal100 = Annotated[
    Decimal, Field(ge=Decimal("0"), le=Decimal("99999.99"), max_digits=7, decimal_places=2)
]
#: Makroskładnik na 100 g/ml — NUMERIC(6,2). Górna granica 100 g na 100 g
#: to fizyka, nie kaprys: więcej składnika niż produktu być nie może.
Macro100 = Annotated[
    Decimal, Field(ge=Decimal("0"), le=Decimal("100"), max_digits=6, decimal_places=2)
]
#: Indeks glikemiczny 0..110 (02_DOMAIN §4.1) — NUMERIC(5,1).
GlycemicIndex = Annotated[
    Decimal, Field(ge=Decimal("0"), le=Decimal("110"), max_digits=5, decimal_places=1)
]
#: Gramy na jednostkę domową — NUMERIC(8,2), dodatnie.
GramsPerUnit = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("999999"), max_digits=8, decimal_places=2)
]


# --- kategorie -------------------------------------------------------------------


class CategoryRead(BaseModel):
    """Kategoria zakupowa ze słownika globalnego."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: int
    perishability: Perishability


class CategoryListResponse(BaseModel):
    """Lista kategorii (04_API §1 — kształt `{items, total}` także bez paginacji)."""

    items: list[CategoryRead]
    total: int


class CategoryCreateRequest(BaseModel):
    """Nowa kategoria (ADMIN)."""

    name: NonEmptyName
    position: int = Field(default=0, ge=0, le=9999)
    perishability: Perishability = Perishability.DURABLE


class CategoryUpdateRequest(BaseModel):
    """Częściowa edycja kategorii; pole pominięte zostaje bez zmian."""

    name: NonEmptyName | None = None
    position: int | None = Field(default=None, ge=0, le=9999)
    perishability: Perishability | None = None


# --- przeliczniki jednostek domowych ------------------------------------------------


class UnitWeightRead(BaseModel):
    """Przelicznik jednostki domowej produktu (ADR-005)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    unit_label: str
    grams_per_unit: DecimalString
    source: str | None
    samples_count: int


class UnitWeightListResponse(BaseModel):
    """Przeliczniki produktu."""

    items: list[UnitWeightRead]
    total: int


class UnitWeightCreateRequest(BaseModel):
    """Nowy przelicznik. Etykieta jest normalizowana w serwisie przed zapisem."""

    unit_label: NonEmptyName
    grams_per_unit: GramsPerUnit
    source: str | None = Field(default=None, max_length=300)
    samples_count: int = Field(default=1, ge=1, le=100000)


class UnitWeightUpdateRequest(BaseModel):
    """Częściowa edycja przelicznika."""

    unit_label: NonEmptyName | None = None
    grams_per_unit: GramsPerUnit | None = None
    source: str | None = Field(default=None, max_length=300)
    samples_count: int | None = Field(default=None, ge=1, le=100000)


# --- produkty -----------------------------------------------------------------------


class NutritionCompleteness(BaseModel):
    """Czy wartości wystarczą do policzenia czegokolwiek (04_API §1, 06_UIUX §3.5).

    Liczone przez adapter `ProductNutrition` — UI pokazuje na tej podstawie
    plakietkę „niepełne dane" z tooltipem `missing`.
    """

    complete: bool
    has_core_macros: bool
    has_glycemic_index: bool
    missing: list[str]


class ProductNutritionRead(BaseModel):
    """Wartości odżywcze produktu na 100 g (VOLUME: na 100 ml) — ADR-004."""

    model_config = ConfigDict(from_attributes=True)

    kcal_100: DecimalString | None
    protein_100: DecimalString | None
    fat_100: DecimalString | None
    carbs_100: DecimalString | None
    fiber_100: DecimalString | None
    sugars_100: DecimalString | None
    glycemic_index: DecimalString | None
    nutrition_source: str | None


class ProductRead(BaseModel):
    """Produkt na liście — komplet potrzebny kafelkowi i pickerowi."""

    id: int
    name: str
    normalized_name: str
    category_id: int
    category_name: str
    measure_kind: MeasureKind
    piece_weight_g: DecimalString | None
    verification_status: VerificationStatus
    verified_at: datetime | None
    perishability: Perishability
    perishability_override: Perishability | None
    is_archived: bool
    nutrition: ProductNutritionRead
    completeness: NutritionCompleteness
    created_at: datetime
    updated_at: datetime


class ProductDetail(ProductRead):
    """Szczegóły produktu — dodatkowo przeliczniki jednostek domowych."""

    unit_weights: list[UnitWeightRead]


class ProductListResponse(BaseModel):
    """Lista produktów z paginacją (04_API §1)."""

    items: list[ProductRead]
    total: int


class ProductCreateRequest(BaseModel):
    """Nowy produkt. Wartości odżywcze NIE wchodzą tędy — mają własny endpoint.

    Formularz inline (`ProductCreateDrawer`) wysyła dokładnie te pola: nazwa,
    kategoria, typ miary i — dla sztuk — waga sztuki. Użytkownik dodający cebulę
    w środku edycji przepisu nie zna jej kaloryczności i nie ma jej zgadywać
    (02_DOMAIN §4.9).
    """

    name: NonEmptyName
    category_id: int = Field(ge=1)
    measure_kind: MeasureKind = MeasureKind.MASS
    piece_weight_g: PieceWeight | None = None
    perishability_override: Perishability | None = None


class ProductUpdateRequest(BaseModel):
    """Częściowa edycja pól opisowych produktu (USER)."""

    name: NonEmptyName | None = None
    category_id: int | None = Field(default=None, ge=1)
    measure_kind: MeasureKind | None = None
    piece_weight_g: PieceWeight | None = None
    perishability_override: Perishability | None = None


class ProductNutritionRequest(BaseModel):
    """PEŁNA podmiana wartości odżywczych (PUT, wyłącznie ADMIN).

    Pole pominięte znaczy „nie znamy tej wartości" i zostaje wyczyszczone — to
    świadoma konsekwencja PUT-a: po operacji stan odpowiada dokładnie temu, co
    przysłał administrator, bez resztek po poprzedniej wersji.
    """

    kcal_100: Kcal100 | None = None
    protein_100: Macro100 | None = None
    fat_100: Macro100 | None = None
    carbs_100: Macro100 | None = None
    fiber_100: Macro100 | None = None
    sugars_100: Macro100 | None = None
    glycemic_index: GlycemicIndex | None = None
    nutrition_source: NutritionSource | None = None


# --- sklepy i profile kolejności kategorii -----------------------------------------

#: Etykieta koloru sklepu z palety UI (06_UIUX §1) — nie hex, żeby motyw dał się
#: zmienić bez migracji danych.
StoreColor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
#: Marka produktu sklepowego (Pilos, Mlekovita…).
BrandName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
#: Wielkość opakowania — NUMERIC(8,2), zawsze dodatnia (opakowanie „0 g" nie istnieje).
PackageAmount = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("999999"), max_digits=8, decimal_places=2)
]


class StoreRead(BaseModel):
    """Sklep ze słownika globalnego."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class StoreListResponse(BaseModel):
    """Lista sklepów (kształt `{items, total}` także bez paginacji — 04_API §1)."""

    items: list[StoreRead]
    total: int


class StoreCreateRequest(BaseModel):
    """Nowy sklep — tworzy go także USER, także inline z `StorePicker` (02 §3.1 pkt 3)."""

    name: NonEmptyName
    color: StoreColor | None = None


class StoreUpdateRequest(BaseModel):
    """Częściowa edycja sklepu; pole pominięte zostaje bez zmian."""

    name: NonEmptyName | None = None
    color: StoreColor | None = None
    is_archived: bool | None = None


class StoreCategoryOrderEntry(BaseModel):
    """Jedna kategoria w profilu sklepu — z nazwą, żeby UI nie dociągał słownika."""

    category_id: int
    category_name: str
    position: int


class StoreCategoryOrderResponse(BaseModel):
    """Profil sklepu: kategorie w kolejności przejścia po sklepie.

    Zawiera WYŁĄCZNIE kategorie należące do profilu. Kategorie spoza listy są
    poza profilem (karta B09, nota 4) — silnik listy zakupowej (B11) umieści je
    na końcu, a edytor pobiera pełny słownik z `/categories`.
    """

    items: list[StoreCategoryOrderEntry]
    total: int


class StoreCategoryOrderRequest(BaseModel):
    """PEŁNA podmiana kolejności: lista `category_id` w docelowej kolejności.

    Pozycje (`position`) liczy serwis z indeksów listy — klient nie ma prawa
    przysłać dziur ani duplikatów numerów, bo to jedna spójna permutacja.
    Pusta lista jest dozwolona i znaczy „ten sklep nie ma profilu".
    """

    category_ids: list[int] = Field(default_factory=list, max_length=200)


# --- produkty sklepowe (retail) -----------------------------------------------------


class RetailProductRead(BaseModel):
    """Wariant sklepowy produktu kanonicznego (02_DOMAIN §4.4).

    `package_amount` jest stringiem dziesiętnym (ADR-008), a URL-e zdjęcia
    prowadzą do endpointu `/uploads/*` z sesją (07_SECURITY §6) — nigdy do
    ścieżki na dysku.
    """

    id: int
    canonical_product_id: int
    canonical_product_name: str
    name: str
    brand: str | None
    store_id: int | None
    store_name: str | None
    package_amount: DecimalString
    package_unit: AmountUnit
    pieces_per_package: int | None
    photo_url: str | None
    photo_thumb_url: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class RetailProductListResponse(BaseModel):
    """Lista wariantów sklepowych z paginacją (04_API §1)."""

    items: list[RetailProductRead]
    total: int


class RetailProductCreateRequest(BaseModel):
    """Nowy produkt sklepowy.

    `canonical_product_id` jest WYMAGANY (02_DOMAIN §4.4): retail bez produktu
    kanonicznego nie istnieje, bo nie miałby wartości odżywczych ani miejsca
    w agregacji zakupów. Zgodność `package_unit` z `measure_kind` produktu
    sprawdza serwis — tutaj nie znamy jeszcze produktu.
    """

    canonical_product_id: int = Field(ge=1)
    name: NonEmptyName
    brand: BrandName | None = None
    store_id: int | None = Field(default=None, ge=1)
    package_amount: PackageAmount
    package_unit: AmountUnit
    pieces_per_package: int | None = Field(default=None, ge=1, le=10000)


class RetailProductUpdateRequest(BaseModel):
    """Częściowa edycja wariantu sklepowego.

    `canonical_product_id` NIE jest edytowalny: przepięcie wariantu na inny
    produkt kanoniczny zmieniałoby znaczenie danych historycznych (spiżarnia,
    listy zakupowe) bez śladu. Pomyłkę naprawia się nowym wariantem
    i archiwizacją starego (ADR-012).
    """

    name: NonEmptyName | None = None
    brand: BrandName | None = None
    store_id: int | None = Field(default=None, ge=1)
    package_amount: PackageAmount | None = None
    package_unit: AmountUnit | None = None
    pieces_per_package: int | None = Field(default=None, ge=1, le=10000)
    is_archived: bool | None = None
