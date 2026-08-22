"""„Przyjmij zakupy do spiżarni" + trwałość stanu listy (karta B11 §Tests).

Motyw przewodni: akcja jest JAWNA i policzalna. Nic nie wchodzi do spiżarni
w tle (02_DOMAIN §8), a ilość, która wchodzi, to ilość KUPIONA — całe
opakowania, nie sama potrzeba. Reguła scalania (`PantryService.receive_purchase`)
ma tu własne scenariusze, bo to decyzja domenowa, nie szczegół zapisu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.scope import Scope
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, MeasureKind, Perishability
from app.modules.catalog.units import AmountUnit
from app.modules.pantry.models import PantryItem
from app.modules.pantry.service import PantryService
from app.modules.shopping.lists_service import ShoppingListsService
from app.modules.shopping.models import ShoppingList, ShoppingListItem
from tests.factories import (
    assign_to_household,
    create_admin,
    create_category,
    create_household,
    create_pantry_item,
    create_product,
    create_shopping_list,
    create_shopping_list_item,
    create_user,
)

pytestmark = pytest.mark.integration

NOW = datetime(2030, 1, 6, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Fixture:
    """Materiał scenariuszy: użytkownik, lista i jej dwie pozycje z produktami."""

    user: User
    shopping_list: ShoppingList
    flour: CanonicalProduct
    tomato: CanonicalProduct
    flour_item: ShoppingListItem
    tomato_item: ShoppingListItem


async def _list_with_two_items(db_session: AsyncSession) -> Fixture:
    """Lista z dwiema pozycjami: mąka w opakowaniach i pomidor bez opakowania."""
    user = await create_user(db_session, email="zakupy@example.com")
    sypkie = await create_category(
        db_session, name="Sypkie", perishability=Perishability.DURABLE, position=5
    )
    warzywa = await create_category(
        db_session, name="Warzywa", perishability=Perishability.FRESH, position=0
    )
    flour = await create_product(db_session, category=sypkie, name="Mąka pszenna")
    tomato = await create_product(db_session, category=warzywa, name="Pomidor")
    shopping_list = await create_shopping_list(db_session, owner=user, scope=Scope.PRIVATE)
    flour_item = await create_shopping_list_item(
        db_session,
        shopping_list=shopping_list,
        category=sypkie,
        product=flour,
        label="Mąka pszenna 1 kg",
        needed_amount=Decimal("1400.000"),
        packages_count=2,
        package_size=Decimal("1000.00"),
        leftover_amount=Decimal("600.000"),
        position=0,
    )
    tomato_item = await create_shopping_list_item(
        db_session,
        shopping_list=shopping_list,
        category=warzywa,
        product=tomato,
        label="Pomidor",
        needed_amount=Decimal("700.000"),
        position=1,
    )
    return Fixture(
        user=user,
        shopping_list=shopping_list,
        flour=flour,
        tomato=tomato,
        flour_item=flour_item,
        tomato_item=tomato_item,
    )


async def _pantry_rows(db_session: AsyncSession, product_id: int) -> list[PantryItem]:
    rows = (
        (
            await db_session.execute(
                select(PantryItem)
                .where(PantryItem.product_id == product_id)
                .order_by(PantryItem.id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def test_przyjmuje_wylacznie_odhaczone_pozycje(db_session: AsyncSession) -> None:
    """Nieodhaczone pozycje NIE wchodzą do spiżarni — zakupy ≠ dostawa (02_DOMAIN §8)."""
    data = await _list_with_two_items(db_session)
    service = ShoppingListsService(db_session)
    await service.update_item(
        data.shopping_list.id,
        data.flour_item.id,
        user=data.user,
        now=NOW,
        checked=True,
    )

    result = await service.accept_to_pantry(
        data.shopping_list.id,
        user=data.user,
    )

    assert (result.created, result.increased, result.skipped) == (1, 0, 0)
    assert len(await _pantry_rows(db_session, data.flour.id)) == 1
    assert await _pantry_rows(db_session, data.tomato.id) == []


async def test_ilosc_to_kupione_opakowania_a_nie_potrzeba(db_session: AsyncSession) -> None:
    """2 x 1000 g = 2000 g w spiżarni, choć potrzeba było 1400 g.

    Resztka wraca do domu razem z opakowaniem — przyjęcie `needed_amount`
    zaniżałoby stan domowy dokładnie o wyliczoną resztkę.
    """
    data = await _list_with_two_items(db_session)
    service = ShoppingListsService(db_session)
    for item in (data.flour_item, data.tomato_item):
        await service.update_item(
            data.shopping_list.id,
            item.id,
            user=data.user,
            now=NOW,
            checked=True,
        )

    result = await service.accept_to_pantry(
        data.shopping_list.id,
        user=data.user,
    )

    assert (result.created, result.increased) == (2, 0)
    flour_rows = await _pantry_rows(db_session, data.flour.id)
    tomato_rows = await _pantry_rows(db_session, data.tomato.id)
    assert flour_rows[0].amount == Decimal("2000.000")
    assert flour_rows[0].amount_unit is AmountUnit.GRAM
    # Bez wariantu sklepowego zostaje potrzeba — tyle wiadomo o zakupie.
    assert tomato_rows[0].amount == Decimal("700.000")


async def test_dolewa_do_istniejacej_pozycji_bez_daty_waznosci(
    db_session: AsyncSession,
) -> None:
    """Duplikaty: zakup dolewa się do pozycji BEZ daty ważności (karta B11, pkt 4)."""
    data = await _list_with_two_items(db_session)
    istniejaca = await create_pantry_item(
        db_session,
        owner=data.user,
        product=data.flour,
        amount=Decimal("500.000"),
    )
    service = ShoppingListsService(db_session)
    await service.update_item(
        data.shopping_list.id,
        data.flour_item.id,
        user=data.user,
        now=NOW,
        checked=True,
    )

    result = await service.accept_to_pantry(
        data.shopping_list.id,
        user=data.user,
    )

    assert (result.created, result.increased) == (0, 1)
    rows = await _pantry_rows(db_session, data.flour.id)
    assert len(rows) == 1
    assert rows[0].id == istniejaca.id
    assert rows[0].amount == Decimal("2500.000")


async def test_pozycja_z_data_waznosci_nie_jest_dolewana(db_session: AsyncSession) -> None:
    """Wiersz z datą ważności to KONKRETNA partia — dolanie skłamałoby o dacie."""
    data = await _list_with_two_items(db_session)
    partia = await create_pantry_item(
        db_session,
        owner=data.user,
        product=data.flour,
        amount=Decimal("500.000"),
        expiry_date=date(2030, 6, 1),
    )
    service = ShoppingListsService(db_session)
    await service.update_item(
        data.shopping_list.id,
        data.flour_item.id,
        user=data.user,
        now=NOW,
        checked=True,
    )

    result = await service.accept_to_pantry(
        data.shopping_list.id,
        user=data.user,
    )

    assert (result.created, result.increased) == (1, 0)
    rows = await _pantry_rows(db_session, data.flour.id)
    assert len(rows) == 2
    assert rows[0].id == partia.id
    assert rows[0].amount == Decimal("500.000")
    assert rows[1].amount == Decimal("2000.000")
    assert rows[1].expiry_date is None


async def test_brak_odhaczonych_pozycji_daje_409(db_session: AsyncSession) -> None:
    """Akcja bez odhaczeń nie jest „operacją bez efektu", tylko konfliktem stanu."""
    data = await _list_with_two_items(db_session)
    service = ShoppingListsService(db_session)

    with pytest.raises(ConflictError):
        await service.accept_to_pantry(
            data.shopping_list.id,
            user=data.user,
        )


async def test_pozycja_bez_produktu_kanonicznego_jest_pomijana(
    db_session: AsyncSession,
) -> None:
    """Odhaczona pozycja bez produktu wchodzi do `skipped`, a nie wysadza akcji."""
    data = await _list_with_two_items(db_session)
    kategoria = await create_category(
        db_session, name="Inne", perishability=Perishability.DURABLE, position=9
    )
    bez_produktu = await create_shopping_list_item(
        db_session,
        shopping_list=data.shopping_list,
        category=kategoria,
        product=None,
        label="Coś ręcznie dopisanego",
        checked=True,
        position=5,
    )
    service = ShoppingListsService(db_session)
    await service.update_item(
        data.shopping_list.id,
        data.flour_item.id,
        user=data.user,
        now=NOW,
        checked=True,
    )

    result = await service.accept_to_pantry(
        data.shopping_list.id,
        user=data.user,
    )

    assert bez_produktu.product_id is None
    assert (result.created, result.skipped) == (1, 1)


async def test_receive_purchase_liczy_w_sztukach_bez_konwersji(
    db_session: AsyncSession,
) -> None:
    """Produkt liczony w sztukach dostaje `piece` — oś bierze się z `measure_kind`."""
    user = await create_user(db_session, email="jajka@example.com")
    kategoria = await create_category(
        db_session, name="Nabiał", perishability=Perishability.FRESH, position=2
    )
    jajka = await create_product(
        db_session,
        category=kategoria,
        name="Jajka",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )

    receipt = await PantryService(db_session).receive_purchase(
        actor=user, product_id=jajka.id, amount=Decimal("10.000")
    )

    assert receipt.merged is False
    assert receipt.item.amount == Decimal("10.000")
    assert receipt.item.amount_unit is AmountUnit.PIECE


# --- trwałość stanu listy i retencja (D10) ---------------------------------------


async def test_stan_checkboxow_jest_trwaly_po_ponownym_pobraniu(
    db_session: AsyncSession,
) -> None:
    """Odhaczenie zapisuje się w bazie, a `checked_at` zna moment decyzji (ADR-009)."""
    data = await _list_with_two_items(db_session)
    service = ShoppingListsService(db_session)
    await service.update_item(
        data.shopping_list.id,
        data.flour_item.id,
        user=data.user,
        now=NOW,
        checked=True,
    )

    detail = await service.get_list(
        data.shopping_list.id,
        user=data.user,
    )

    pozycje = {item.id: item for section in detail.sections for item in section.items}
    flour_item = pozycje[data.flour_item.id]
    assert flour_item.checked is True
    assert flour_item.checked_at == NOW
    # Odznaczenie też odnotowuje moment — LWW porównuje OSTATNIĄ decyzję.
    pozniej = NOW + timedelta(hours=1)
    odznaczona = await service.update_item(
        data.shopping_list.id,
        data.flour_item.id,
        user=data.user,
        now=pozniej,
        checked=False,
    )
    assert odznaczona.checked is False
    assert odznaczona.checked_at == pozniej


async def test_wygasla_lista_zostaje_w_bazie_a_token_przestaje_dzialac(
    db_session: AsyncSession,
) -> None:
    """D10: nic nie znika automatycznie — wygasa wyłącznie publiczny link."""
    data = await _list_with_two_items(db_session)
    service = ShoppingListsService(db_session)
    share = await service.share_list(
        data.shopping_list.id,
        user=data.user,
        expires_in_days=1,
        now=NOW,
    )
    token = share.url.removeprefix("/l/")

    # Zegar przesunięty o dwa dni: token wygasł, wiersz nie drgnął.
    pozniej = NOW + timedelta(days=2)
    with pytest.raises(Exception) as gone:
        await service.public_list(token, now=pozniej)
    assert getattr(gone.value, "status_code", None) == 410

    zostala = (
        await db_session.execute(
            select(ShoppingList).where(ShoppingList.id == data.shopping_list.id)
        )
    ).scalar_one()
    assert zostala.public_token == token
    detail = await service.get_list(
        data.shopping_list.id,
        user=data.user,
    )
    assert len(detail.sections) == 2


async def test_admin_nie_dolewa_do_cudzej_spizarni(db_session: AsyncSession) -> None:
    """ADMIN widzi wszystkie spiżarnie (D16), ale przyjmuje zakupy do WŁASNEJ.

    Regresja z `/code-review` B11: kandydata do dolania szukaliśmy przez
    `select_visible`, które dla ADMIN-a zwraca `true()`. Skutek byłby taki, że
    „przyjmij zakupy do spiżarni" powiększało ilość w NAJSTARSZEJ pasującej
    pozycji w całej instancji — czyli w spiżarni obcej rodziny.
    """
    obca_rodzina = await create_household(db_session, name="Nowakowie")
    obcy = await create_user(db_session, email="obcy-dom@example.com")
    await assign_to_household(db_session, user=obcy, household=obca_rodzina)

    kategoria = await create_category(
        db_session, name="Sypkie", perishability=Perishability.DURABLE, position=5
    )
    maka = await create_product(db_session, category=kategoria, name="Mąka pszenna")
    cudza_pozycja = await create_pantry_item(
        db_session, owner=obcy, product=maka, amount=Decimal("500.000")
    )

    admin = await create_admin(db_session, email="admin-zakupy@example.com")
    lista = await create_shopping_list(db_session, owner=admin, scope=Scope.PRIVATE)
    pozycja = await create_shopping_list_item(
        db_session,
        shopping_list=lista,
        category=kategoria,
        product=maka,
        label="Mąka pszenna 1 kg",
        needed_amount=Decimal("1000.000"),
        checked=True,
    )

    service = ShoppingListsService(db_session)
    result = await service.accept_to_pantry(lista.id, user=admin)

    assert pozycja.checked is True
    assert (result.created, result.increased) == (1, 0)
    await db_session.refresh(cudza_pozycja)
    assert cudza_pozycja.amount == Decimal("500.000")
    wiersze = await _pantry_rows(db_session, maka.id)
    assert [row.owner_user_id for row in wiersze] == [obcy.id, admin.id]
