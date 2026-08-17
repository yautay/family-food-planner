"""Wspólne fabryki danych dla testów silnika nutrition — bez ORM (ADR-008)."""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType

from app.modules.catalog.models import VerificationStatus
from app.modules.catalog.units import AmountUnit, MeasureKind, basis_unit
from app.modules.nutrition.types import (
    NUTRITION_NUMERIC_FIELDS,
    NutritionValues,
    ProductNutrition,
)


def product(
    *,
    product_id: int = 1,
    name: str = "Cebula",
    measure_kind: MeasureKind = MeasureKind.MASS,
    piece_weight_g: Decimal | None = None,
    kcal_100: Decimal | None = None,
    protein_100: Decimal | None = None,
    fat_100: Decimal | None = None,
    carbs_100: Decimal | None = None,
    fiber_100: Decimal | None = None,
    sugars_100: Decimal | None = None,
    glycemic_index: Decimal | None = None,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
) -> ProductNutrition:
    """`ProductNutrition` budowany wprost — dokładnie to, co odda adapter."""
    unit: AmountUnit = basis_unit(measure_kind)
    return ProductNutrition(
        product_id=product_id,
        name=name,
        measure_kind=measure_kind,
        basis_unit=unit,
        piece_weight_g=piece_weight_g,
        kcal_100=kcal_100,
        protein_100=protein_100,
        fat_100=fat_100,
        carbs_100=carbs_100,
        fiber_100=fiber_100,
        sugars_100=sugars_100,
        glycemic_index=glycemic_index,
        verification_status=verification_status,
        extras=MappingProxyType({}),
    )


def full_product(**overrides: object) -> ProductNutrition:
    """Produkt z kompletem wartości — ręcznie policzalny w testach przykładowych.

    Domyślnie: kcal 50, białko 1,5, tłuszcz 0,2, węglowodany 10, błonnik 2,
    cukry 6, IG 40 — na 100 g.
    """
    values: dict[str, object] = {
        "name": "Produkt pełny",
        "kcal_100": Decimal("50.00"),
        "protein_100": Decimal("1.50"),
        "fat_100": Decimal("0.20"),
        "carbs_100": Decimal("10.00"),
        "fiber_100": Decimal("2.00"),
        "sugars_100": Decimal("6.00"),
        "glycemic_index": Decimal("40.0"),
    }
    values.update(overrides)
    return product(**values)  # type: ignore[arg-type]


def values_of(items: NutritionValues) -> dict[str, Decimal]:
    """Pola liczbowe wyniku jako słownik — do porównań per pole."""
    return {field: getattr(items, field) for field in NUTRITION_NUMERIC_FIELDS}
