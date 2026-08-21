"""Warianty sklepowe na realnej bazie (BATCH_09).

Sedno tego pliku to niezmienniki, które trzyma baza albo serwis, a nie schemat
żądania: obowiązkowe powiązanie z produktem kanonicznym (FK RESTRICT w obie
strony konsekwencji), zgodność jednostki opakowania z osią produktu
(02_DOMAIN §13.1) i blokada usuwania z listą użyć (ADR-012) — w tym pozycje
spiżarni, których FK dopięła migracja `0011`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.models import MeasureKind
from app.modules.catalog.retail_service import RetailService, RetailValidationError
from app.modules.catalog.service import CatalogService
from app.modules.catalog.units import AmountUnit
from tests.factories import (
    create_admin,
    create_category,
    create_pantry_item,
    create_product,
    create_retail_product,
    create_store,
    create_user,
)

pytestmark = pytest.mark.integration


# --- obowiązkowe powiązanie z produktem kanonicznym ---------------------------------


async def test_wariant_bez_istniejacego_produktu_jest_odrzucany(db_session: AsyncSession) -> None:
    """AC 1: retail bez produktu kanonicznego nie istnieje (02_DOMAIN §4.4)."""
    service = RetailService(db_session)
    user = await create_user(db_session)

    with pytest.raises(RetailValidationError):
        await service.create_retail_product(
            actor=user,
            canonical_product_id=999_999,
            name="Widmo 400 g",
            brand=None,
            store_id=None,
            package_amount=Decimal("400.00"),
            package_unit=AmountUnit.GRAM,
            pieces_per_package=None,
        )


async def test_produktu_uzytego_w_retail_nie_da_sie_usunac(db_session: AsyncSession) -> None:
    """FK RESTRICT + licznik referencji: 409 z czytelną listą użyć (ADR-012)."""
    catalog = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Jogurt naturalny")
    await create_retail_product(db_session, product=product, name="Pilos Jogurt 400 g")

    with pytest.raises(ConflictError) as excinfo:
        await catalog.delete_product(product.id, actor=admin)

    used_in = excinfo.value.details["used_in"]
    assert [(entry["type"], entry["name"]) for entry in used_in] == [
        ("retail_product", "Pilos Jogurt 400 g")
    ]


async def test_nieistniejacy_sklep_jest_odrzucany(db_session: AsyncSession) -> None:
    """Sklep jest opcjonalny, ale WSKAZANY musi istnieć."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    with pytest.raises(RetailValidationError):
        await service.create_retail_product(
            actor=user,
            canonical_product_id=product.id,
            name="Jogurt 400 g",
            brand=None,
            store_id=999_999,
            package_amount=Decimal("400.00"),
            package_unit=AmountUnit.GRAM,
            pieces_per_package=None,
        )


# --- zgodność jednostki opakowania z osią produktu ---------------------------------


@pytest.mark.parametrize(
    ("measure_kind", "package_unit"),
    [
        (MeasureKind.MASS, AmountUnit.MILLILITER),
        (MeasureKind.VOLUME, AmountUnit.GRAM),
        (MeasureKind.PIECE, AmountUnit.GRAM),
    ],
)
async def test_jednostka_niezgodna_z_measure_kind_jest_odrzucana(
    db_session: AsyncSession, measure_kind: MeasureKind, package_unit: AmountUnit
) -> None:
    """Opakowanie „400 ml" produktu liczonego na wagę to ilość, której nikt nie przeliczy."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name=f"Produkt {measure_kind.value}",
        measure_kind=measure_kind,
        piece_weight_g=Decimal("60.00") if measure_kind is MeasureKind.PIECE else None,
    )

    with pytest.raises(RetailValidationError):
        await service.create_retail_product(
            actor=user,
            canonical_product_id=product.id,
            name="Opakowanie w złej jednostce",
            brand=None,
            store_id=None,
            package_amount=Decimal("400.00"),
            package_unit=package_unit,
            pieces_per_package=None,
        )


async def test_edycja_nie_moze_rozjechac_jednostki_z_produktem(db_session: AsyncSession) -> None:
    """PATCH sprawdza stan KOŃCOWY, nie samo żądanie."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, measure_kind=MeasureKind.MASS)
    retail = await create_retail_product(db_session, product=product)

    with pytest.raises(RetailValidationError):
        await service.update_retail_product(
            retail.id, actor=user, changes={"package_unit": AmountUnit.MILLILITER}
        )


async def test_opakowanie_wielosztukowe_zapisuje_liczbe_sztuk(db_session: AsyncSession) -> None:
    """AC 2: jajka 10 szt. — `pieces_per_package` jest zwykłym atrybutem opakowania."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )

    view = await service.create_retail_product(
        actor=user,
        canonical_product_id=product.id,
        name="Jaja z wolnego wybiegu 10 szt.",
        brand="Zielona Zagroda",
        store_id=None,
        package_amount=Decimal("10.00"),
        package_unit=AmountUnit.PIECE,
        pieces_per_package=10,
    )

    assert view.retail.pieces_per_package == 10
    assert view.retail.package_unit is AmountUnit.PIECE
    # NUMERIC(8,2) — skala z bazy, nie z żądania (pułapka z dziennika B08 pkt 5).
    assert view.retail.package_amount == Decimal("10.00")


# --- lista, filtry i archiwizacja -------------------------------------------------


async def test_archiwalny_wariant_znika_z_listy_domyslnej(db_session: AsyncSession) -> None:
    """Archiwizacja to alternatywa usuwania (ADR-012), nie ukrycie danych."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product, name="Jogurt 400 g")

    await service.update_retail_product(retail.id, actor=user, changes={"is_archived": True})

    widoczne, total = await service.list_retail_products(limit=50, offset=0)
    assert (widoczne, total) == ([], 0)

    wszystkie, total_all = await service.list_retail_products(
        limit=50, offset=0, include_archived=True
    )
    assert total_all == 1
    assert wszystkie[0].retail.id == retail.id


async def test_filtry_produktu_i_sklepu_dzialaja_razem(db_session: AsyncSession) -> None:
    """Karta produktu pyta o warianty JEDNEGO produktu, preview B10 — o jeden sklep."""
    service = RetailService(db_session)
    category = await create_category(db_session)
    jogurt = await create_product(db_session, category=category, name="Jogurt")
    maka = await create_product(db_session, category=category, name="Mąka")
    lidl = await create_store(db_session, name="Lidl")
    biedronka = await create_store(db_session, name="Biedronka")

    await create_retail_product(db_session, product=jogurt, store=lidl, name="Jogurt Pilos")
    await create_retail_product(db_session, product=jogurt, store=biedronka, name="Jogurt Mleczny")
    await create_retail_product(db_session, product=maka, store=lidl, name="Mąka Castello")

    per_produkt, total = await service.list_retail_products(
        limit=50, offset=0, canonical_product_id=jogurt.id
    )
    assert total == 2
    assert {view.retail.name for view in per_produkt} == {"Jogurt Pilos", "Jogurt Mleczny"}

    per_sklep, total_store = await service.list_retail_products(
        limit=50, offset=0, canonical_product_id=jogurt.id, store_id=lidl.id
    )
    assert total_store == 1
    assert per_sklep[0].retail.name == "Jogurt Pilos"
    assert per_sklep[0].store is not None
    assert per_sklep[0].store.name == "Lidl"


async def test_szukajka_znajduje_po_marce(db_session: AsyncSession) -> None:
    """`?q=` obejmuje markę: użytkownik szuka „Pilos", nie pełnej nazwy wariantu."""
    service = RetailService(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_retail_product(
        db_session, product=product, name="Jogurt naturalny 400 g", brand="Pilos"
    )
    await create_retail_product(
        db_session, product=product, name="Jogurt grecki 300 g", brand="Mlekovita"
    )

    trafienia, total = await service.list_retail_products(limit=50, offset=0, query="pilos")

    assert total == 1
    assert trafienia[0].retail.brand == "Pilos"


async def test_wariant_bez_sklepu_jest_dozwolony(db_session: AsyncSession) -> None:
    """Sklep jest opcjonalny (03_DATABASE §3) — widok oddaje wtedy `None`."""
    service = RetailService(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_retail_product(db_session, product=product, store=None)

    views, _ = await service.list_retail_products(limit=50, offset=0)

    assert views[0].store is None


# --- blokada usuwania wariantu ------------------------------------------------------


async def test_wariant_uzyty_w_spizarni_zwraca_409_z_lista_uzyc(
    db_session: AsyncSession,
) -> None:
    """Rekoncyliacja FK z B08: pozycja spiżarni trzyma wariant sklepowy (RESTRICT)."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product, name="Jogurt Pilos 400 g")
    await create_pantry_item(db_session, owner=user, product=product, retail_product_id=retail.id)

    with pytest.raises(ConflictError) as excinfo:
        await service.delete_retail_product(retail.id, actor=user)

    used_in = excinfo.value.details["used_in"]
    assert [(entry["type"], entry["name"]) for entry in used_in] == [
        ("pantry_item", "Jogurt Pilos 400 g")
    ]


async def test_nieuzywany_wariant_znika(db_session: AsyncSession) -> None:
    """Usunięcie nieużywanego wariantu to zwykła operacja, nie wyjątek."""
    service = RetailService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    retail = await create_retail_product(db_session, product=product)

    await service.delete_retail_product(retail.id, actor=user)

    with pytest.raises(NotFoundError):
        await service.get_retail_product(retail.id)
