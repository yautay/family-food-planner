"""Adapter `ProductNutrition` — JEDYNE wejście silników do wartości odżywczych.

ADR-004 rozdziela wartości na dwa miejsca: rdzeń w kolumnach
`canonical_products` i rozszerzenia w `product_nutrient_values`. Konsekwencją
tego podziału jest reguła, której pilnuje review: **nikt poza tym modułem nie
czyta tych kolumn i tej tabeli**. Silnik nutrition (B05), silnik zakupowy (B10)
i statystyki (B13) dostają jedną, płaską dataclassę i nie wiedzą, że wartości
mieszkają w dwóch strukturach.

Drugie zadanie adaptera to KOMPLETNOŚĆ. Brak wartości nigdy nie jest zerem
(0 kcal to nieprawda, nie brak danych): produkt bez makro albo bez IG daje
`complete=False` i listę `missing` w języku polskim, którą 04_API §1 przekazuje
wprost do odpowiedzi silnika, a UI pokazuje jako plakietkę „niepełne dane"
(06_UIUX §3.5).

Moduł jest czysty — czyta atrybuty encji, ale sam nie wykonuje I/O. Rozszerzenia
przekazuje się wprost (`extras`), bo doładowanie relacji w warstwie
synchronicznej kończyłoby się `MissingGreenlet` (lekcja z BATCH_03).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from app.modules.catalog.models import (
    CanonicalProduct,
    ProductNutrientValue,
    VerificationStatus,
)
from app.modules.catalog.units import (
    AmountUnit,
    MeasureKind,
    ProductMeasure,
    UnitWeight,
    basis_unit,
)

#: Opisy braków po polsku — trafiają wprost do `nutrition.missing` (04_API §1).
CORE_LABELS: tuple[tuple[str, str], ...] = (
    ("kcal_100", "brak kalorii"),
    ("protein_100", "brak białka"),
    ("fat_100", "brak tłuszczu"),
    ("carbs_100", "brak węglowodanów"),
)
GLYCEMIC_INDEX_LABEL = "brak indeksu glikemicznego"


@dataclass(frozen=True)
class ProductNutrition:
    """Komplet wartości produktu na 100 g (VOLUME: na 100 ml) — wejście silników."""

    product_id: int
    name: str
    measure_kind: MeasureKind
    #: Jednostka, w której podane jest „na 100": `g` albo `ml`.
    basis_unit: AmountUnit
    piece_weight_g: Decimal | None
    kcal_100: Decimal | None
    protein_100: Decimal | None
    fat_100: Decimal | None
    carbs_100: Decimal | None
    fiber_100: Decimal | None
    sugars_100: Decimal | None
    glycemic_index: Decimal | None
    verification_status: VerificationStatus
    #: Mikroelementy z rejestru `nutrients` (w MVP pusty słownik — ADR-004).
    extras: Mapping[str, Decimal]

    @property
    def has_core_macros(self) -> bool:
        """Czy komplet rdzenia (kcal + białko + tłuszcz + węglowodany) jest znany."""
        return all(getattr(self, field) is not None for field, _ in CORE_LABELS)

    @property
    def has_glycemic_index(self) -> bool:
        """IG jest opcjonalny w danych, ale bez niego nie da się policzyć ŁG."""
        return self.glycemic_index is not None

    @property
    def is_verified(self) -> bool:
        """Czy wartości zostały sprawdzone przez ADMIN-a (02_DOMAIN §4.9)."""
        return self.verification_status is VerificationStatus.VERIFIED

    @property
    def is_complete(self) -> bool:
        """Komplet potrzebny do policzenia kcal, makro ORAZ ładunku glikemicznego."""
        return self.has_core_macros and self.has_glycemic_index

    @property
    def missing(self) -> tuple[str, ...]:
        """Czego brakuje — gotowe komunikaty `"<produkt>: brak ..."` (04_API §1)."""
        gaps = [label for field, label in CORE_LABELS if getattr(self, field) is None]
        if not self.has_glycemic_index:
            gaps.append(GLYCEMIC_INDEX_LABEL)
        return tuple(f"{self.name}: {gap}" for gap in gaps)

    @property
    def digestible_carbs_100(self) -> Decimal | None:
        """Węglowodany przyswajalne = węglowodany minus błonnik, min 0 (02_DOMAIN §6).

        Brak błonnika NIE jest traktowany jak zero: produkt bez tej wartości ma
        po prostu tyle węglowodanów przyswajalnych, ile węglowodanów — to
        najostrożniejsze założenie, a niekompletność sygnalizuje `missing`.
        """
        if self.carbs_100 is None:
            return None
        if self.fiber_100 is None:
            return self.carbs_100
        return max(self.carbs_100 - self.fiber_100, Decimal("0"))

    def extra(self, nutrient_code: str) -> Decimal | None:
        """Wartość rozszerzonego składnika albo `None`, gdy nieznana."""
        return self.extras.get(nutrient_code)


def nutrition_for(
    product: CanonicalProduct,
    extras: Iterable[ProductNutrientValue] = (),
) -> ProductNutrition:
    """Zbuduj adapter z encji produktu i (już wczytanych) wartości rozszerzonych."""
    measure_kind = product.measure_kind
    return ProductNutrition(
        product_id=product.id,
        name=product.name,
        measure_kind=measure_kind,
        # Jedna definicja osi wartości dla adaptera i dla konwersji (units.basis_unit).
        basis_unit=basis_unit(measure_kind),
        piece_weight_g=product.piece_weight_g,
        kcal_100=product.kcal_100,
        protein_100=product.protein_100,
        fat_100=product.fat_100,
        carbs_100=product.carbs_100,
        fiber_100=product.fiber_100,
        sugars_100=product.sugars_100,
        glycemic_index=product.glycemic_index,
        verification_status=product.verification_status,
        extras=MappingProxyType({value.nutrient_code: value.amount_per_100 for value in extras}),
    )


def measure_for(
    product: CanonicalProduct,
    unit_weights: Iterable[UnitWeight] = (),
) -> ProductMeasure:
    """Dane potrzebne konwersjom jednostek — ta sama zasada co wyżej: encja → dataclass."""
    return ProductMeasure(
        measure_kind=product.measure_kind,
        piece_weight_g=product.piece_weight_g,
        unit_weights=tuple(unit_weights),
    )
