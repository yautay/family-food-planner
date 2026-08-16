"""Deterministyczny seed danych demo (`task db-seed-demo`, 08_TESTING §5).

Po co: żeby dało się kliknąć aplikację i uruchomić E2E bez ręcznego wklepywania
katalogu. Seed jest **idempotentny** — kluczem tożsamości produktu jest
`normalized_name`, więc powtórne uruchomienie niczego nie duplikuje i nie
nadpisuje wartości poprawionych ręcznie.

Zakres w BATCH_04: produkty kanoniczne i przeliczniki jednostek domowych.
Rodzinę 2+3, przepisy, tydzień planu i listę zakupową dokładają batche, które
te encje wprowadzają (B03 dał rodziny, B05 przepisy, B07 plan) — komenda rośnie
razem z modelem, zamiast czekać na komplet.

Dane są ŚWIADOMIE mieszane pod względem kompletności: część produktów jest
zweryfikowana z pełnymi wartościami, część czeka w kolejce `UNVERIFIED` bez
kalorii. Bez tego nie da się obejrzeć ani plakietki „niepełne dane"
(06_UIUX §3.5), ani ekranu `/admin/weryfikacja`.

Użycie:
    task db-seed-demo
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ConfigurationError, get_settings
from app.core.db import get_session_factory, selector_loop_factory
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    ProductCategory,
    ProductUnitWeight,
    VerificationStatus,
)
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import normalize_unit_label

#: Źródło wartości w danych demo — od razu widać, że nie są to dane referencyjne.
DEMO_SOURCE = "demo"


@dataclass(frozen=True)
class DemoProduct:
    """Produkt demo. `None` w wartościach = świadomy brak (nie zero — ADR-004)."""

    name: str
    category: str
    measure_kind: MeasureKind = MeasureKind.MASS
    piece_weight_g: Decimal | None = None
    kcal_100: Decimal | None = None
    protein_100: Decimal | None = None
    fat_100: Decimal | None = None
    carbs_100: Decimal | None = None
    fiber_100: Decimal | None = None
    sugars_100: Decimal | None = None
    glycemic_index: Decimal | None = None
    #: Etykieta jednostki domowej → gramy na jednostkę (01_PDF_AUDIT §5.2).
    unit_weights: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def is_verified(self) -> bool:
        """Zweryfikowany = ma komplet rdzenia; resztę zostawiamy w kolejce admina."""
        return None not in (self.kcal_100, self.protein_100, self.fat_100, self.carbs_100)


def _d(value: str) -> Decimal:
    """Literał dziesiętny — nigdy `Decimal(float)` (ADR-008)."""
    return Decimal(value)


#: 15 produktów pokrywających wszystkie typy miary i oba stany weryfikacji.
DEMO_PRODUCTS: tuple[DemoProduct, ...] = (
    DemoProduct(
        name="Cebula",
        category="Warzywa",
        kcal_100=_d("40.00"),
        protein_100=_d("1.10"),
        fat_100=_d("0.10"),
        carbs_100=_d("9.30"),
        fiber_100=_d("1.70"),
        sugars_100=_d("4.20"),
        glycemic_index=_d("15.0"),
        unit_weights=(("sztuka średnia", "105.00"),),
    ),
    DemoProduct(
        name="Marchew",
        category="Warzywa",
        kcal_100=_d("41.00"),
        protein_100=_d("0.90"),
        fat_100=_d("0.20"),
        carbs_100=_d("9.60"),
        fiber_100=_d("2.80"),
        sugars_100=_d("4.70"),
        glycemic_index=_d("35.0"),
        unit_weights=(("sztuka średnia", "80.00"),),
    ),
    DemoProduct(
        name="Pomidor",
        category="Warzywa",
        kcal_100=_d("18.00"),
        protein_100=_d("0.90"),
        fat_100=_d("0.20"),
        carbs_100=_d("3.90"),
        fiber_100=_d("1.20"),
        sugars_100=_d("2.60"),
        glycemic_index=_d("30.0"),
    ),
    DemoProduct(
        name="Banan",
        category="Owoce",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=_d("120.00"),
        kcal_100=_d("89.00"),
        protein_100=_d("1.10"),
        fat_100=_d("0.30"),
        carbs_100=_d("22.80"),
        fiber_100=_d("2.60"),
        sugars_100=_d("12.20"),
        glycemic_index=_d("51.0"),
    ),
    DemoProduct(
        name="Jabłko",
        category="Owoce",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=_d("180.00"),
        kcal_100=_d("52.00"),
        protein_100=_d("0.30"),
        fat_100=_d("0.20"),
        carbs_100=_d("13.80"),
        fiber_100=_d("2.40"),
        sugars_100=_d("10.40"),
        glycemic_index=_d("36.0"),
    ),
    DemoProduct(
        name="Pieczarki",
        category="Grzyby",
        kcal_100=_d("22.00"),
        protein_100=_d("3.10"),
        fat_100=_d("0.30"),
        carbs_100=_d("3.30"),
        fiber_100=_d("1.00"),
        glycemic_index=_d("15.0"),
    ),
    DemoProduct(
        name="Jajko",
        category="Nabiał i jaja",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=_d("60.00"),
        kcal_100=_d("143.00"),
        protein_100=_d("12.60"),
        fat_100=_d("9.50"),
        carbs_100=_d("0.70"),
        glycemic_index=_d("0.0"),
    ),
    DemoProduct(
        name="Skyr naturalny",
        category="Nabiał i jaja",
        kcal_100=_d("63.00"),
        protein_100=_d("11.00"),
        fat_100=_d("0.20"),
        carbs_100=_d("4.00"),
        sugars_100=_d("4.00"),
        glycemic_index=_d("11.0"),
        unit_weights=(("opakowanie", "150.00"),),
    ),
    DemoProduct(
        name="Mleko 2%",
        category="Nabiał i jaja",
        measure_kind=MeasureKind.VOLUME,
        kcal_100=_d("51.00"),
        protein_100=_d("3.30"),
        fat_100=_d("2.00"),
        carbs_100=_d("4.80"),
        sugars_100=_d("4.80"),
        glycemic_index=_d("30.0"),
        unit_weights=(("szklanka", "250.00"),),
    ),
    DemoProduct(
        name="Pierś z kurczaka",
        category="Mięso i produkty mięsne",
        kcal_100=_d("110.00"),
        protein_100=_d("23.10"),
        fat_100=_d("1.30"),
        carbs_100=_d("0.00"),
        glycemic_index=_d("0.0"),
        unit_weights=(("porcja", "150.00"),),
    ),
    DemoProduct(
        name="Chleb żytni razowy",
        category="Pieczywo",
        kcal_100=_d("223.00"),
        protein_100=_d("7.50"),
        fat_100=_d("1.20"),
        carbs_100=_d("42.50"),
        fiber_100=_d("8.00"),
        glycemic_index=_d("58.0"),
        unit_weights=(("kromka", "35.00"),),
    ),
    DemoProduct(
        name="Ryż brązowy",
        category="Makarony, ryż i kasze",
        kcal_100=_d("353.00"),
        protein_100=_d("7.10"),
        fat_100=_d("2.50"),
        carbs_100=_d("72.10"),
        fiber_100=_d("3.40"),
        glycemic_index=_d("50.0"),
        unit_weights=(("szklanka", "180.00"), ("opakowanie", "1000.00")),
    ),
    DemoProduct(
        name="Mąka pszenna typ 500",
        category="Makarony, ryż i kasze",
        kcal_100=_d("341.00"),
        protein_100=_d("9.90"),
        fat_100=_d("1.00"),
        carbs_100=_d("70.60"),
        fiber_100=_d("2.50"),
        glycemic_index=_d("70.0"),
        # Ta sama łyżka waży w audycie PDF 5, 12 albo 15 g — demo pokazuje jedną
        # ustaloną wartość, edytowalną przy produkcie (01_PDF_AUDIT §5.2).
        unit_weights=(("łyżka", "12.00"), ("szklanka", "130.00")),
    ),
    # Dwa produkty świadomie NIEZWERYFIKOWANE i bez wartości — tak wygląda
    # katalog po inline create USERA i tym żyje ekran `/admin/weryfikacja`.
    DemoProduct(name="Oliwa z oliwek", category="Tłuszcze", measure_kind=MeasureKind.VOLUME),
    DemoProduct(name="Orzechy włoskie", category="Orzechy i nasiona"),
)


async def seed_products(session: AsyncSession) -> tuple[int, int]:
    """Wstaw brakujące produkty demo. Zwraca (dodane, pominięte)."""
    categories = {
        category.name: category
        for category in (await session.execute(select(ProductCategory))).scalars().all()
    }
    if not categories:
        raise SeedError(
            "Brak kategorii w bazie. Uruchom najpierw migracje (`task db-migrate`) — "
            "słownik kategorii pochodzi z migracji danych 0005."
        )

    existing = set(
        (await session.execute(select(CanonicalProduct.normalized_name))).scalars().all()
    )

    added = 0
    for demo in DEMO_PRODUCTS:
        normalized = normalize_name(demo.name)
        if normalized in existing:
            continue
        category = categories.get(demo.category)
        if category is None:
            raise SeedError(
                f"Kategoria „{demo.category}” nie istnieje w słowniku. "
                "Seed demo zakłada kategorie z migracji 0005."
            )

        product = CanonicalProduct(
            name=demo.name,
            normalized_name=normalized,
            category_id=category.id,
            measure_kind=demo.measure_kind,
            piece_weight_g=demo.piece_weight_g,
            kcal_100=demo.kcal_100,
            protein_100=demo.protein_100,
            fat_100=demo.fat_100,
            carbs_100=demo.carbs_100,
            fiber_100=demo.fiber_100,
            sugars_100=demo.sugars_100,
            glycemic_index=demo.glycemic_index,
            nutrition_source=DEMO_SOURCE if demo.is_verified else None,
            verification_status=(
                VerificationStatus.VERIFIED if demo.is_verified else VerificationStatus.UNVERIFIED
            ),
        )
        session.add(product)
        await session.flush()

        for label, grams in demo.unit_weights:
            session.add(
                ProductUnitWeight(
                    product_id=product.id,
                    unit_label=normalize_unit_label(label),
                    grams_per_unit=Decimal(grams),
                    source=DEMO_SOURCE,
                )
            )
        added += 1

    await session.commit()
    return added, len(DEMO_PRODUCTS) - added


class SeedError(RuntimeError):
    """Seed nie ma na czym pracować — komunikat po polsku, bez stacktrace'u."""


async def _run() -> str:
    factory = get_session_factory()
    async with factory() as session:
        added, skipped = await seed_products(session)
    return f"Seed demo: dodano {added} produktów, pominięto {skipped} (już istniały)."


def main() -> int:
    """Punkt wejścia `python -m scripts.seed_demo`."""
    try:
        get_settings()
        # loop_factory: na Windows psycopg async wymaga SelectorEventLoop.
        message = asyncio.run(_run(), loop_factory=selector_loop_factory())
    except (ConfigurationError, SeedError) as exc:
        print(f"Błąd: {exc}")
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
