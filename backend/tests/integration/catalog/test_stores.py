"""Sklepy i profile kolejności kategorii na realnej bazie (BATCH_09).

Sprawdzamy to, czego nie widać w testach HTTP: kaskady, blokadę usuwania
(ADR-012), niezależność profili dwóch sklepów i trwałość kolejności po
podmianie. Profil jest permutacją, więc testy pytają o KOLEJNOŚĆ, nie
o zbiór id.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.models import StoreCategoryOrder
from app.modules.catalog.service import CatalogService
from app.modules.catalog.stores_service import StoresService, StoreValidationError
from tests.factories import (
    create_admin,
    create_category,
    create_product,
    create_retail_product,
    create_store,
    create_user,
)

pytestmark = pytest.mark.integration


async def _order_rows(session: AsyncSession, store_id: int) -> int:
    """Liczba wierszy profilu danego sklepu (kontrola kaskad)."""
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(StoreCategoryOrder)
                .where(StoreCategoryOrder.store_id == store_id)
            )
        ).scalar_one()
    )


# --- CRUD i unikalność nazwy --------------------------------------------------------


async def test_duplikat_nazwy_sklepu_jest_odrzucany(db_session: AsyncSession) -> None:
    """Nazwa sklepu jest unikalna, a 409 nosi podpowiedź istniejącego wpisu."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    existing = await service.create_store(actor=user, name="Lidl", color=None)

    with pytest.raises(ConflictError) as excinfo:
        await service.create_store(actor=user, name="lidl", color=None)

    assert excinfo.value.details["existing"]["id"] == existing.id


async def test_zmiana_nazwy_na_zajeta_jest_odrzucana(db_session: AsyncSession) -> None:
    """PATCH nie może zrobić z dwóch sklepów jednego."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    await create_store(db_session, name="Lidl")
    other = await create_store(db_session, name="Biedronka")

    with pytest.raises(ConflictError):
        await service.update_store(other.id, actor=user, changes={"name": "Lidl"})


async def test_archiwalne_sklepy_sa_domyslnie_ukryte(db_session: AsyncSession) -> None:
    """Archiwizacja znika z list wyboru, ale nie kasuje danych (ADR-012)."""
    service = StoresService(db_session)
    await create_store(db_session, name="Czynny")
    await create_store(db_session, name="Zamknięty", is_archived=True)

    widoczne = [store.name for store in await service.list_stores()]
    wszystkie = [store.name for store in await service.list_stores(include_archived=True)]

    assert widoczne == ["Czynny"]
    assert wszystkie == ["Czynny", "Zamknięty"]


# --- blokada usuwania i kaskady -----------------------------------------------------


async def test_sklep_uzywany_w_retail_zwraca_409_z_lista_uzyc(db_session: AsyncSession) -> None:
    """Sklep przypisany do wariantu sklepowego nie znika po cichu (ADR-012)."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    store = await create_store(db_session, name="Lidl")
    await create_retail_product(db_session, product=product, store=store, name="Pilos Jogurt 400 g")

    with pytest.raises(ConflictError) as excinfo:
        await service.delete_store(store.id, actor=user)

    used_in = excinfo.value.details["used_in"]
    assert [(entry["type"], entry["name"]) for entry in used_in] == [
        ("retail_product", "Pilos Jogurt 400 g")
    ]


async def test_usuniecie_sklepu_kasuje_jego_profil_kaskada(db_session: AsyncSession) -> None:
    """Profil to atrybut sklepu — znika razem z nim i nie blokuje usunięcia."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    nabial = await create_category(db_session, name="Nabiał")
    store = await create_store(db_session, name="Lidl")
    await service.set_category_order(store.id, actor=user, category_ids=[nabial.id, warzywa.id])
    assert await _order_rows(db_session, store.id) == 2

    await service.delete_store(store.id, actor=user)

    assert await _order_rows(db_session, store.id) == 0
    with pytest.raises(NotFoundError):
        await service.get_store(store.id)


# --- profil kolejności kategorii ----------------------------------------------------


async def test_put_podmienia_cala_kolejnosc_i_jest_trwaly(db_session: AsyncSession) -> None:
    """Pełna podmiana: pozycje spoza nowej listy wypadają z profilu."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    nabial = await create_category(db_session, name="Nabiał")
    pieczywo = await create_category(db_session, name="Pieczywo")
    store = await create_store(db_session, name="Lidl")

    await service.set_category_order(
        store.id, actor=user, category_ids=[warzywa.id, nabial.id, pieczywo.id]
    )
    # Druga podmiana odwraca kolejność i wyrzuca pieczywo z profilu.
    zapisane = await service.set_category_order(
        store.id, actor=user, category_ids=[nabial.id, warzywa.id]
    )

    assert [entry.category_id for entry in zapisane] == [nabial.id, warzywa.id]
    assert [entry.position for entry in zapisane] == [0, 1]
    # Odczyt z bazy, nie z wyniku mutacji: kolejność musi PRZETRWAĆ zapis.
    odczyt = await service.category_order(store.id)
    assert [entry.category_id for entry in odczyt] == [nabial.id, warzywa.id]
    assert [entry.category_name for entry in odczyt] == ["Nabiał", "Warzywa"]


async def test_duplikat_kategorii_w_kolejnosci_jest_odrzucany(db_session: AsyncSession) -> None:
    """Kolejność to permutacja — ta sama kategoria nie może wystąpić dwa razy."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    store = await create_store(db_session, name="Lidl")

    with pytest.raises(StoreValidationError):
        await service.set_category_order(
            store.id, actor=user, category_ids=[warzywa.id, warzywa.id]
        )

    assert await _order_rows(db_session, store.id) == 0


async def test_nieznana_kategoria_w_kolejnosci_nie_zapisuje_niczego(
    db_session: AsyncSession,
) -> None:
    """Odrzucone żądanie nie może zostawić pół-zapisanego profilu."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    store = await create_store(db_session, name="Lidl")
    await service.set_category_order(store.id, actor=user, category_ids=[warzywa.id])

    with pytest.raises(StoreValidationError):
        await service.set_category_order(store.id, actor=user, category_ids=[warzywa.id, 999_999])

    # Stary profil zostaje nietknięty — walidacja biegnie PRZED czyszczeniem.
    assert [entry.category_id for entry in await service.category_order(store.id)] == [warzywa.id]


async def test_dwa_sklepy_maja_niezalezne_profile(db_session: AsyncSession) -> None:
    """AC 4: kolejność jest własnością sklepu, nie słownika kategorii."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    nabial = await create_category(db_session, name="Nabiał")
    lidl = await create_store(db_session, name="Lidl")
    biedronka = await create_store(db_session, name="Biedronka")

    await service.set_category_order(lidl.id, actor=user, category_ids=[warzywa.id, nabial.id])
    await service.set_category_order(biedronka.id, actor=user, category_ids=[nabial.id, warzywa.id])

    assert [entry.category_id for entry in await service.category_order(lidl.id)] == [
        warzywa.id,
        nabial.id,
    ]
    assert [entry.category_id for entry in await service.category_order(biedronka.id)] == [
        nabial.id,
        warzywa.id,
    ]


async def test_pusta_lista_czysci_profil(db_session: AsyncSession) -> None:
    """„Sklep bez profilu" jest dozwolonym stanem — PUT z pustą listą go daje."""
    service = StoresService(db_session)
    user = await create_user(db_session)
    warzywa = await create_category(db_session, name="Warzywa")
    store = await create_store(db_session, name="Lidl")
    await service.set_category_order(store.id, actor=user, category_ids=[warzywa.id])

    assert await service.set_category_order(store.id, actor=user, category_ids=[]) == []
    assert await _order_rows(db_session, store.id) == 0


async def test_profil_nieistniejacego_sklepu_to_404(db_session: AsyncSession) -> None:
    """Cudzy/nieistniejący identyfikator zawsze zachowuje się tak samo (07_SECURITY §4)."""
    service = StoresService(db_session)
    with pytest.raises(NotFoundError):
        await service.category_order(999_999)


async def test_usuniecie_kategorii_nie_blokuje_sie_o_profil(db_session: AsyncSession) -> None:
    """Kategoria w profilu sklepu kasuje się kaskadą, nie 409-ką.

    Kategorii i tak nie da się usunąć, dopóki ma produkty (`delete_category`),
    więc jedyną rzeczą, którą profil mógłby tu zrobić, byłoby zablokowanie
    pustej kategorii bez powodu.
    """
    stores = StoresService(db_session)
    catalog = CatalogService(db_session)
    admin = await create_admin(db_session)
    category = await create_category(db_session, name="Do usunięcia")
    store = await create_store(db_session, name="Lidl")
    await stores.set_category_order(store.id, actor=admin, category_ids=[category.id])

    await catalog.delete_category(category.id, actor=admin)

    assert await _order_rows(db_session, store.id) == 0
