"""Serwis spiżarni + baza: CRUD, wyzerowanie, scope „zawsze household", CHECK.

Scenariusze z karty B08 §Tests (integration). Motyw przewodni: spiżarnia jest
JEDNYM stanem rodziny (02_DOMAIN §3.1 pkt 1), a wyzerowanie to `amount = 0`,
nie usunięcie wiersza (02_DOMAIN §8).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.models import MeasureKind
from app.modules.catalog.service import CatalogService
from app.modules.catalog.units import AmountUnit
from app.modules.pantry.models import PantryItem
from app.modules.pantry.schemas import PantryItemCreateRequest, PantrySort
from app.modules.pantry.service import PantryService, PantryValidationError
from tests.factories import (
    assign_to_household,
    create_admin,
    create_category,
    create_household,
    create_pantry_item,
    create_product,
    create_retail_product,
    create_user,
)

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 21)


async def _count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(PantryItem))).scalar_one())


async def test_pelny_cykl_zycia_pozycji(db_session: AsyncSession) -> None:
    """Dodanie → zmiana ilości → wyzerowanie (wiersz zostaje) → usunięcie."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Mąka pszenna")
    service = PantryService(db_session)

    created = await service.create_item(
        actor=user,
        payload=PantryItemCreateRequest(
            product_id=product.id,
            amount=Decimal("1000.000"),
            expiry_date=TODAY + timedelta(days=30),
            location="szafka",
            note="górna półka",
        ),
    )
    assert created.item.amount == Decimal("1000.000")
    assert created.item.amount_unit is AmountUnit.GRAM
    assert created.item.household_id == household.id
    assert created.product is not None and created.product.name == "Mąka pszenna"

    changed = await service.update_item(
        created.item.id, actor=user, changes={"amount": Decimal("250.000")}
    )
    assert changed.item.amount == Decimal("250.000")

    zeroed = await service.update_item(
        created.item.id, actor=user, changes={"amount": Decimal("0")}
    )
    assert zeroed.item.amount == Decimal("0.000")
    assert await _count(db_session) == 1, "wyzerowanie NIE usuwa wiersza (02_DOMAIN §8)"

    await service.delete_item(created.item.id, actor=user)
    assert await _count(db_session) == 0


async def test_patch_czysci_date_waznosci_i_lokalizacje(db_session: AsyncSession) -> None:
    """`null` dla kolumn NULLABLE znaczy „wyczyść"; pominięte pola zostają bez zmian."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(
        db_session,
        owner=user,
        product=product,
        expiry_date=TODAY,
        location="lodówka",
        note="do zupy",
    )

    view = await PantryService(db_session).update_item(
        item.id, actor=user, changes={"expiry_date": None, "location": None}
    )

    assert view.item.expiry_date is None
    assert view.item.location is None
    assert view.item.note == "do zupy", "pominięte pole zostaje bez zmian"


async def test_jednostka_musi_pasowac_do_miary_produktu(db_session: AsyncSession) -> None:
    """`piece` dla produktu mierzonego masą = 422 i BRAK zapisu (02_DOMAIN §13.1)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Mąka")
    service = PantryService(db_session)

    with pytest.raises(PantryValidationError):
        await service.create_item(
            actor=user,
            payload=PantryItemCreateRequest(
                product_id=product.id, amount=Decimal("3"), amount_unit=AmountUnit.PIECE
            ),
        )

    assert await _count(db_session) == 0


async def test_jednostka_wynika_z_produktu_gdy_pominieta(db_session: AsyncSession) -> None:
    """Bez `amount_unit` serwis bierze oś produktu: sztuki dla `measure_kind=piece`."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    eggs = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )
    milk = await create_product(
        db_session, category=category, name="Mleko", measure_kind=MeasureKind.VOLUME
    )
    service = PantryService(db_session)

    eggs_item = await service.create_item(
        actor=user, payload=PantryItemCreateRequest(product_id=eggs.id, amount=Decimal("10"))
    )
    milk_item = await service.create_item(
        actor=user, payload=PantryItemCreateRequest(product_id=milk.id, amount=Decimal("1500"))
    )

    assert eggs_item.item.amount_unit is AmountUnit.PIECE
    assert milk_item.item.amount_unit is AmountUnit.MILLILITER


async def test_nieistniejacy_produkt_konczy_sie_422(db_session: AsyncSession) -> None:
    """Produkt spoza katalogu to błąd danych wejściowych, nie 404 zasobu."""
    user = await create_user(db_session)

    with pytest.raises(PantryValidationError):
        await PantryService(db_session).create_item(
            actor=user, payload=PantryItemCreateRequest(product_id=987654, amount=Decimal("1"))
        )


async def test_check_wymaga_produktu_kanonicznego_albo_sklepowego(
    db_session: AsyncSession,
) -> None:
    """Wiersz bez żadnego produktu jest niemożliwy — pilnuje tego CHECK w bazie."""
    user = await create_user(db_session)
    db_session.add(
        PantryItem(
            owner_user_id=user.id,
            household_id=None,
            product_id=None,
            retail_product_id=None,
            amount=Decimal("100.000"),
            amount_unit=AmountUnit.GRAM,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_pozycja_tylko_z_produktem_sklepowym_przechodzi(db_session: AsyncSession) -> None:
    """CHECK dopuszcza wiersz z samym `retail_product_id` (wariant sklepowy z B09).

    Odczyt takiej pozycji NIE MOŻE jej gubić: join produktu kanonicznego jest
    LEFT, więc pozycja zostaje na liście z pustą nazwą produktu.

    Wariant musi ISTNIEĆ: od migracji `0011` kolumna ma FK RESTRICT (B09 dopiął
    constraint odroczony w B08), więc wcześniejsze „id z powietrza" nie ma prawa
    się zapisać — i to jest ta zmiana, którą test dokumentuje.
    """
    user = await create_user(db_session)
    category = await create_category(db_session)
    canonical = await create_product(db_session, category=category, name="Jogurt naturalny")
    retail = await create_retail_product(db_session, product=canonical)
    item = await create_pantry_item(
        db_session, owner=user, product=None, retail_product_id=retail.id
    )

    views, total = await PantryService(db_session).list_items(user, limit=50, offset=0, today=TODAY)

    assert total == 1
    assert views[0].item.id == item.id
    assert views[0].item.retail_product_id == retail.id
    assert views[0].product is None


async def test_spizarnia_jest_wspolna_dla_rodziny(db_session: AsyncSession) -> None:
    """Drugi członek widzi i EDYTUJE pozycję dodaną przez pierwszego (AC 3)."""
    household = await create_household(db_session)
    author = await create_user(db_session, email="a@example.com", household=household)
    member = await create_user(db_session, email="b@example.com", household=household)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=author, product=product)
    service = PantryService(db_session)

    views, total = await service.list_items(member, limit=50, offset=0, today=TODAY)
    assert total == 1 and views[0].item.id == item.id

    changed = await service.update_item(
        item.id, actor=member, changes={"amount": Decimal("120.000")}
    )
    assert changed.item.amount == Decimal("120.000")


async def test_uzytkownik_bez_rodziny_ma_spizarnie_osobista(db_session: AsyncSession) -> None:
    """Bez rodziny pozycja wisi na użytkowniku i nie widzi jej nikt inny."""
    loner = await create_user(db_session, email="sam@example.com")
    other = await create_user(db_session, email="inny@example.com")
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    service = PantryService(db_session)

    created = await service.create_item(
        actor=loner, payload=PantryItemCreateRequest(product_id=product.id, amount=Decimal("300"))
    )
    assert created.item.household_id is None

    mine, _ = await service.list_items(loner, limit=50, offset=0, today=TODAY)
    theirs, total = await service.list_items(other, limit=50, offset=0, today=TODAY)

    assert [view.item.id for view in mine] == [created.item.id]
    assert theirs == [] and total == 0


async def test_odejscie_z_rodziny_zabiera_dostep_do_jej_spizarni(
    db_session: AsyncSession,
) -> None:
    """Spiżarnia zostaje przy rodzinie, nie przy autorze wpisu.

    To różnica wobec `ScopedQuery`, gdzie `owner_user_id = :uid` wystarcza do
    widoczności. Tu wystarczyć NIE MOŻE: jeden stan domowy należy do domu.
    """
    household = await create_household(db_session)
    author = await create_user(db_session, household=household)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_pantry_item(db_session, owner=author, product=product)

    await assign_to_household(db_session, user=author, household=None)
    views, total = await PantryService(db_session).list_items(
        author, limit=50, offset=0, today=TODAY
    )

    assert views == [] and total == 0


async def test_admin_widzi_cudze_pozycje_spizarni(db_session: AsyncSession) -> None:
    """D16: ADMIN widzi encje ze scope także na ścieżkach użytkownika."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=user, product=product)

    views, total = await PantryService(db_session).list_items(
        admin, limit=50, offset=0, today=TODAY
    )

    assert total == 1 and views[0].item.id == item.id


async def test_kazdy_czlonek_rodziny_usuwa_cudza_pozycje(db_session: AsyncSession) -> None:
    """D17: pozycję spiżarni usuwa KAŻDY członek rodziny, nie tylko autor wpisu.

    Spiżarnia jest jednym stanem domowym: skoro członek rodziny może pozycję
    wyzerować, blokowanie mu usunięcia wiersza byłoby pozorną ochroną. To
    świadomy wyjątek od 02_DOMAIN §3.1 pkt 2 („usunięcie: właściciel lub ADMIN").
    """
    household = await create_household(db_session)
    author = await create_user(db_session, email="a@example.com", household=household)
    member = await create_user(db_session, email="b@example.com", household=household)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=author, product=product)

    await PantryService(db_session).delete_item(item.id, actor=member)

    assert await _count(db_session) == 0


async def test_pozycja_z_obcej_rodziny_to_404(db_session: AsyncSession) -> None:
    """Cudza pozycja i nieistniejąca dają identyczny 404 (07_SECURITY §4).

    Sprawdzamy to na ścieżkach, które faktycznie istnieją w API (PATCH i DELETE):
    obie rozstrzygają pozycję po id przez `ScopedQuery.get_or_404`, więc to one
    są realną powierzchnią anty-IDOR.
    """
    ours = await create_household(db_session, name="Kowalscy")
    theirs = await create_household(db_session, name="Nowakowie")
    user = await create_user(db_session, email="my@example.com", household=ours)
    stranger = await create_user(db_session, email="oni@example.com", household=theirs)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    item = await create_pantry_item(db_session, owner=stranger, product=product)
    service = PantryService(db_session)

    with pytest.raises(NotFoundError):
        await service.update_item(item.id, actor=user, changes={"amount": Decimal("1")})
    with pytest.raises(NotFoundError):
        await service.delete_item(item.id, actor=user)
    with pytest.raises(NotFoundError):
        await service.delete_item(999_999, actor=user)

    assert await _count(db_session) == 1, "cudza pozycja nie może zniknąć"


async def test_sortowanie_filtry_i_szukajka(db_session: AsyncSession) -> None:
    """Domyślnie po dacie ważności (bez daty na końcu); `?q=` i kategoria zawężają."""
    user = await create_user(db_session)
    fresh = await create_category(db_session, name="Nabiał", position=1)
    dry = await create_category(db_session, name="Suche", position=2)
    yoghurt = await create_product(db_session, category=fresh, name="Jogurt naturalny")
    milk = await create_product(db_session, category=fresh, name="Mleko")
    rice = await create_product(db_session, category=dry, name="Ryż biały")

    await create_pantry_item(db_session, owner=user, product=rice, expiry_date=None)
    await create_pantry_item(
        db_session, owner=user, product=milk, expiry_date=TODAY + timedelta(days=10)
    )
    await create_pantry_item(
        db_session, owner=user, product=yoghurt, expiry_date=TODAY + timedelta(days=2)
    )
    service = PantryService(db_session)

    by_expiry, total = await service.list_items(user, limit=50, offset=0, today=TODAY)
    assert total == 3
    assert [view.product.name for view in by_expiry if view.product is not None] == [
        "Jogurt naturalny",
        "Mleko",
        "Ryż biały",
    ]

    by_name, _ = await service.list_items(
        user, limit=50, offset=0, today=TODAY, sort=PantrySort.NAME
    )
    assert [view.product.name for view in by_name if view.product is not None] == [
        "Jogurt naturalny",
        "Mleko",
        "Ryż biały",
    ]

    filtered, total = await service.list_items(
        user, limit=50, offset=0, today=TODAY, category_id=dry.id
    )
    assert total == 1 and filtered[0].product is not None
    assert filtered[0].product.name == "Ryż biały"

    found, total = await service.list_items(user, limit=50, offset=0, today=TODAY, query="jogurt")
    assert total == 1 and found[0].product is not None
    assert found[0].product.name == "Jogurt naturalny"

    soon, total = await service.list_items(
        user, limit=50, offset=0, today=TODAY, expires_within_days=7
    )
    assert total == 1 and soon[0].product is not None
    assert soon[0].product.name == "Jogurt naturalny"


async def test_expires_within_days_obejmuje_przeterminowane(db_session: AsyncSession) -> None:
    """Filtr „kończy się w ciągu N dni" pokazuje też to, co się już zepsuło."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_pantry_item(
        db_session, owner=user, product=product, expiry_date=TODAY - timedelta(days=3)
    )

    views, total = await PantryService(db_session).list_items(
        user, limit=50, offset=0, today=TODAY, expires_within_days=7
    )

    assert total == 1 and views[0].item.expiry_date == TODAY - timedelta(days=3)


async def test_stan_domowy_pomija_pozycje_wyzerowane(db_session: AsyncSession) -> None:
    """`get_household_state` to wejście silnika zakupowego (B10): zero to nie zapas."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    member = await create_user(db_session, email="drugi@example.com", household=household)
    category = await create_category(db_session)
    flour = await create_product(db_session, category=category, name="Mąka")
    sugar = await create_product(db_session, category=category, name="Cukier")
    await create_pantry_item(db_session, owner=user, product=flour, amount=Decimal("750.000"))
    await create_pantry_item(db_session, owner=user, product=sugar, amount=Decimal("0.000"))

    state = await PantryService(db_session).get_household_state(member)

    assert [(row.product_id, row.amount) for row in state] == [(flour.id, Decimal("750.000"))]
    assert state[0].amount_unit is AmountUnit.GRAM


async def test_stan_domowy_admina_to_JEGO_dom_a_nie_wszystkie_rodziny(
    db_session: AsyncSession,
) -> None:
    """D16 dotyczy WIDOCZNOŚCI, nie przynależności stanu domowego.

    ADMIN widzi cudze pozycje na liście, ale `get_household_state` musi zwrócić
    jego własny dom — inaczej lista zakupów administratora (B10) odjęłaby
    spiżarnie wszystkich rodzin w instancji.
    """
    household = await create_household(db_session)
    stranger = await create_user(db_session, email="obcy@example.com", household=household)
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    theirs = await create_product(db_session, category=category, name="Cudza mąka")
    mine = await create_product(db_session, category=category, name="Moja mąka")
    await create_pantry_item(db_session, owner=stranger, product=theirs)
    await create_pantry_item(db_session, owner=admin, product=mine)
    service = PantryService(db_session)

    visible, total = await service.list_items(admin, limit=50, offset=0, today=TODAY)
    state = await service.get_household_state(admin)

    assert total == 2, "na liście ADMIN widzi wszystko (D16)"
    assert len(visible) == 2
    assert [row.product_id for row in state] == [mine.id], "stan domowy to JEGO dom"


async def test_produkt_uzyty_w_spizarni_jest_chroniony_przed_usunieciem(
    db_session: AsyncSession,
) -> None:
    """Usunięcie produktu ze spiżarni = 409 z listą „Używane w:" (ADR-012).

    To test rejestracji licznika referencji: bez `register_product_reference_finder`
    ADMIN dostałby konflikt bez `details.used_in` i nie wiedziałby, gdzie szukać.
    """
    admin = await create_admin(db_session)
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Cebula")
    await create_pantry_item(db_session, owner=user, product=product)

    with pytest.raises(ConflictError) as error:
        await CatalogService(db_session).delete_product(product.id, actor=admin)

    used_in = error.value.details["used_in"]
    assert [reference["type"] for reference in used_in] == ["pantry_item"]
    assert used_in[0]["name"] == "Cebula"
