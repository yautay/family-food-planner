"""Serwis katalogu na realnej bazie: unikaty, kaskady, blokady usuwania, trigram.

Poziom integracyjny sprawdza to, czego nie widać w testach jednostkowych:
zachowanie constraintów PostgreSQL (UNIQUE, RESTRICT, CASCADE) i działanie
wyszukiwarki trigramowej, która jest funkcją bazy, a nie Pythona.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deletion import UsedInRef
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    Nutrient,
    Perishability,
    ProductNutrientValue,
    ProductUnitWeight,
    VerificationStatus,
)
from app.modules.catalog.service import (
    CatalogService,
    ProductValidationError,
    register_product_reference_finder,
    unregister_product_reference_finder,
)
from tests.factories import (
    create_admin,
    create_category,
    create_product,
    create_unit_weight,
    create_user,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def similarity_threshold(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], None]]:
    """Podmiana progu wyszukiwarki na czas jednego testu (z posprzątaniem cache)."""

    def override(value: str) -> None:
        monkeypatch.setenv("CATALOG_SEARCH_SIMILARITY_THRESHOLD", value)
        get_settings.cache_clear()

    yield override
    # Bez tego kolejne testy dostałyby ustawienia z podmienioną wartością.
    get_settings.cache_clear()


# --- unikalność znormalizowanej nazwy -------------------------------------------


@pytest.mark.parametrize("duplicate", ["cebula", "  Cebula  ", "CEBULA", "Cebula "])
async def test_duplikat_znormalizowanej_nazwy_jest_odrzucany(
    db_session: AsyncSession, duplicate: str
) -> None:
    """Warianty spacji i wielkości liter to TEN SAM produkt (01_PDF_AUDIT §5.3)."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")

    with pytest.raises(ConflictError) as excinfo:
        await service.create_product(
            actor=user,
            name=duplicate,
            category_id=category.id,
            measure_kind=MeasureKind.MASS,
        )

    assert excinfo.value.details["existing"]["name"] == "Cebula"


async def test_rozne_nazwy_to_rozne_produkty(db_session: AsyncSession) -> None:
    """Normalizacja jest minimalna: „Cebula" i „Cebula czerwona" pozostają osobne."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")

    view = await service.create_product(
        actor=user,
        name="Cebula czerwona",
        category_id=category.id,
        measure_kind=MeasureKind.MASS,
    )

    assert view.product.normalized_name == "cebula czerwona"


async def test_zmiana_nazwy_na_zajeta_jest_odrzucana(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")
    other = await create_product(db_session, category=category, name="Marchew")

    with pytest.raises(ConflictError):
        await service.update_product(other.id, actor=user, changes={"name": "cebula"})


# --- kaskady i blokady usuwania ---------------------------------------------------


async def test_usuniecie_produktu_kasuje_jego_przeliczniki_i_wartosci(
    db_session: AsyncSession,
) -> None:
    """CASCADE dotyczy kompozycji: przelicznik i wartość rozszerzona są częścią produktu."""
    service = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_unit_weight(db_session, product=product)
    # Rejestr `nutrients` jest w MVP pusty (ADR-004), więc mikroelement na
    # potrzeby testu zakładamy tak, jak zrobi to przyszły INSERT do słownika.
    db_session.add(Nutrient(code="vit_c", name="Witamina C", unit="mg", display_order=1))
    await db_session.flush()
    db_session.add(
        ProductNutrientValue(
            product_id=product.id, nutrient_code="vit_c", amount_per_100=Decimal("7.400")
        )
    )
    await db_session.commit()

    await service.delete_product(product.id, actor=admin)

    assert await db_session.scalar(select(func.count()).select_from(CanonicalProduct)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProductUnitWeight)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProductNutrientValue)) == 0
    # Słownik nutrientów przeżywa usunięcie produktu (FK RESTRICT w drugą stronę).
    assert await db_session.scalar(select(func.count()).select_from(Nutrient)) == 1


async def test_kategorii_z_produktami_nie_da_sie_usunac(db_session: AsyncSession) -> None:
    """RESTRICT + 409 z listą użyć (ADR-012, 06_UIUX §3.3)."""
    service = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")

    with pytest.raises(ConflictError) as excinfo:
        await service.delete_category(category.id, actor=admin)

    assert excinfo.value.details["used_in"] == [
        {"type": "product", "id": (await _first_product_id(db_session)), "name": "Cebula"}
    ]


async def test_pusta_kategoria_znika(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session, name="Do usunięcia")

    await service.delete_category(category.id, actor=admin)

    with pytest.raises(NotFoundError):
        await service.get_category(category.id)


async def test_uzywany_produkt_zwraca_409_z_lista_uzyc(db_session: AsyncSession) -> None:
    """Kontrakt `details.used_in` dla przyszłych konsumentów (przepisy B05, spiżarnia B08).

    Rejestr liczników referencji jest w BATCH_04 pusty, więc symulujemy tu
    konsumenta — dokładnie tak, jak zrobi to moduł przepisów.
    """
    service = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    async def finder(_session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
        return [UsedInRef(type="recipe", id=7, name="Gołąbki")]

    register_product_reference_finder(finder)
    try:
        with pytest.raises(ConflictError) as excinfo:
            await service.delete_product(product.id, actor=admin)
    finally:
        unregister_product_reference_finder(finder)

    assert excinfo.value.details == {"used_in": [{"type": "recipe", "id": 7, "name": "Gołąbki"}]}
    assert await db_session.scalar(select(func.count()).select_from(CanonicalProduct)) == 1


async def test_zwykly_uzytkownik_nie_usuwa_produktu(db_session: AsyncSession) -> None:
    """D13: katalog jest wspólny, więc USER może wyłącznie archiwizować."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    with pytest.raises(ForbiddenError) as excinfo:
        await service.delete_product(product.id, actor=user)

    assert "zarchiwizować" in excinfo.value.message


# --- wyszukiwarka trigramowa --------------------------------------------------------


async def test_szukajka_znajduje_produkt_po_prefiksie(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")
    await create_product(db_session, category=category, name="Marchew")

    views, total = await service.list_products(limit=50, offset=0, query="cebul")

    assert total == 1
    assert views[0].product.name == "Cebula"


async def test_szukajka_toleruje_literowke(db_session: AsyncSession) -> None:
    """Wyszukiwanie trigramowe (pg_trgm) — wymóg 04_API §1 i AC 5 karty batcha."""
    service = CatalogService(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula czerwona")

    views, total = await service.list_products(limit=50, offset=0, query="cebual czerwona")

    assert total == 1
    assert views[0].product.name == "Cebula czerwona"


async def test_szukajka_traktuje_procent_jak_zwykly_znak(
    db_session: AsyncSession, similarity_threshold: Callable[[str], None]
) -> None:
    """Bez escape'owania `%` z frazy działałby jak wieloznacznik LIKE.

    Próg podobieństwa podniesiony do 1.0 wyłącza gałąź trigramową, więc test
    mierzy dokładnie dopasowanie po prefiksie — inaczej „Jogurt naturalny"
    wpadłby do wyniku przez podobieństwo i ukrył badany błąd.
    """
    similarity_threshold("1.0")
    service = CatalogService(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Jogurt naturalny")
    await create_product(db_session, category=category, name="Jogurt 0% naturalny")

    views, total = await service.list_products(limit=50, offset=0, query="jogurt 0%")

    assert total == 1
    assert views[0].product.name == "Jogurt 0% naturalny"


async def test_szukajka_nie_zwraca_produktow_bez_zwiazku(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")

    _, total = await service.list_products(limit=50, offset=0, query="zzzzzz")

    assert total == 0


async def test_archiwalne_produkty_sa_domyslnie_ukryte(db_session: AsyncSession) -> None:
    """Archiwizacja ma znikać z pickerów i list domyślnych (ADR-012)."""
    service = CatalogService(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula", is_archived=True)

    _, hidden = await service.list_products(limit=50, offset=0)
    _, shown = await service.list_products(limit=50, offset=0, include_archived=True)

    assert (hidden, shown) == (0, 1)


async def test_filtry_kategorii_i_statusu_dzialaja_razem(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    vegetables = await create_category(db_session, name="Warzywa")
    dairy = await create_category(db_session, name="Nabiał i jaja", position=2)
    await create_product(db_session, category=vegetables, name="Cebula")
    await create_product(
        db_session,
        category=dairy,
        name="Skyr naturalny",
        verification_status=VerificationStatus.VERIFIED,
    )

    _, only_dairy = await service.list_products(limit=50, offset=0, category_id=dairy.id)
    _, only_unverified = await service.list_products(
        limit=50, offset=0, verification_status=VerificationStatus.UNVERIFIED
    )

    assert (only_dairy, only_unverified) == (1, 1)


# --- przeliczniki jednostek ----------------------------------------------------------


async def test_duplikat_jednostki_domowej_jest_odrzucany(db_session: AsyncSession) -> None:
    """UNIQUE(product_id, unit_label) po ZNORMALIZOWANEJ etykiecie."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_unit_weight(db_session, product=product, unit_label="łyżka")

    with pytest.raises(ConflictError):
        await service.create_unit_weight(
            product.id,
            actor=user,
            unit_label="  ŁYŻKA ",
            grams_per_unit=Decimal("12.00"),
            source=None,
            samples_count=1,
        )


async def test_przelicznika_dla_sztuki_nie_zapisujemy(db_session: AsyncSession) -> None:
    """`szt.` wynika z wagi sztuki produktu, a nie z tabeli przeliczników (ADR-005)."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    with pytest.raises(ProductValidationError):
        await service.create_unit_weight(
            product.id,
            actor=user,
            unit_label="sztuka",
            grams_per_unit=Decimal("50.00"),
            source=None,
            samples_count=1,
        )


async def test_przelicznik_cudzego_produktu_daje_404(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Cebula")
    other = await create_product(db_session, category=category, name="Marchew")
    weight = await create_unit_weight(db_session, product=product)

    with pytest.raises(NotFoundError):
        await service.get_unit_weight(other.id, weight.id)


# --- walidacje produktu ---------------------------------------------------------------


async def test_produkt_w_sztukach_wymaga_wagi_sztuki(db_session: AsyncSession) -> None:
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)

    with pytest.raises(ProductValidationError):
        await service.create_product(
            actor=user,
            name="Jajko",
            category_id=category.id,
            measure_kind=MeasureKind.PIECE,
        )


async def test_zmiana_typu_miary_czysci_wage_sztuki(db_session: AsyncSession) -> None:
    """Waga sztuki bez sztuk to dane, których nikt nie aktualizuje — kasujemy je."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )

    view = await service.update_product(
        product.id, actor=user, changes={"measure_kind": MeasureKind.MASS}
    )

    assert view.product.piece_weight_g is None


async def test_weryfikacja_bez_kompletu_wartosci_jest_odrzucana(
    db_session: AsyncSession,
) -> None:
    service = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    with pytest.raises(ProductValidationError) as excinfo:
        await service.verify_product(product.id, actor=admin)

    assert "kcal_100" in excinfo.value.details["missing"]
    assert "nutrition_source" in excinfo.value.details["missing"]


async def test_trwalosc_nadpisana_na_produkcie_wygrywa_z_kategoria(
    db_session: AsyncSession,
) -> None:
    """02_DOMAIN §9.2 — konsumentem jest silnik zakupowy (B10)."""
    service = CatalogService(db_session)
    user = await create_user(db_session)
    category = await create_category(
        db_session, name="Przetwory, puszki i słoiki", perishability=Perishability.DURABLE
    )

    view = await service.create_product(
        actor=user,
        name="Pesto domowe",
        category_id=category.id,
        measure_kind=MeasureKind.MASS,
        perishability_override=Perishability.FRESH,
    )

    assert view.category.perishability is Perishability.DURABLE
    assert view.product.perishability_override is Perishability.FRESH


async def _first_product_id(session: AsyncSession) -> int:
    return (await session.execute(select(CanonicalProduct.id))).scalar_one()
