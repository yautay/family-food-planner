"""Logika list zakupowych: odczyt, odhaczanie, sklep, udostępnianie, spiżarnia.

Dlaczego OSOBNY serwis obok `shopping/service.py`: tamten odpowiada za drogę
plan → podgląd → finalizacja (silnik, `params`, tury), a ten za życie GOTOWEJ
listy w sklepie. Granica jest ta sama, co między generacją a listą w 02_DOMAIN
§9: po finalizacji lista nie pyta już silnika o nic — ma własne pozycje, własny
profil sortowania i własny publiczny token. Wzorzec „kilka serwisów w jednym
module" jest w repo od B09 (`catalog/{service,stores_service,retail_service}`).

Cztery reguły, z których wynika kształt tego pliku:

1. **Widoczność wyłącznie przez `ScopedQuery`** — cudza lista to 404, także na
   pozycjach (pozycja nie ma własnego scope, dziedziczy go po liście,
   04_API §2c). Usunięcie listy wymaga `assert_can_manage` (08_TESTING §4).
2. **Ścieżka publiczna nie zna użytkownika.** Autoryzuje ją WYŁĄCZNIE pełny
   token z URL-a (unique index, ADR-010), więc jej metody nie przyjmują `User`
   i nigdy nie sięgają do `ScopedQuery`. Wygasła/odwołana lista to 410,
   nieznany token to 404, a komunikat jest w obu przypadkach IDENTYCZNY.
3. **Czas wchodzi parametrem** (`now` z routera) — jak w B08 i B10.
4. **Zero PII w odpowiedzi publicznej** (niezmiennik 02_DOMAIN §13.5): ten
   serwis zwraca dla ścieżki publicznej WŁASNY widok (`PublicListView`), a nie
   encje — schemat nie ma więc z czego wziąć właściciela ani rodziny.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, GoneError, NotFoundError
from app.core.scope import ScopedQuery
from app.core.security import generate_token
from app.modules.accounts.models import User
from app.modules.catalog.models import ProductCategory, Store
from app.modules.catalog.stores_service import CategoryOrderEntry, StoresService
from app.modules.catalog.units import AmountUnit
from app.modules.pantry.service import PantryService
from app.modules.shopping.models import ShoppingList, ShoppingListItem
from app.modules.shopping.sorting import SortableItem, sort_into_sections

__all__ = [
    "LIST_GONE",
    "PUBLIC_URL_PREFIX",
    "ListSection",
    "PublicListItemView",
    "PublicListView",
    "ReceivedToPantry",
    "ShareView",
    "ShoppingListDetail",
    "ShoppingListSummary",
    "ShoppingListsService",
]

LIST_NOT_FOUND = "Nie znaleziono tej listy zakupowej."
ITEM_NOT_FOUND = "Nie znaleziono tej pozycji listy zakupowej."
STORE_NOT_AVAILABLE = "Nie znaleziono sklepu, który chcesz przypisać do listy."
#: Komunikat 410 przepisany DOSŁOWNIE z ADR-010 — pilnuje go test API.
LIST_GONE = "Ta lista zakupowa już wygasła lub została usunięta."
#: Ten sam komunikat dla nieznanego tokenu: nie potwierdzamy, czy kiedykolwiek
#: istniał (karta B11, Implementation Notes pkt 5).
LIST_TOKEN_UNKNOWN = LIST_GONE
NOTHING_TO_RECEIVE = "Nie ma czego przyjąć do spiżarni — najpierw odhacz kupione pozycje na liście."

#: Ścieżka publiczna linku (ADR-010). Origin dokłada frontend z `window.location`,
#: bo backend nie zna adresu, pod którym stoi reverse proxy (karta B11, pkt 7).
PUBLIC_URL_PREFIX = "/l/"

#: Dozwolone okna ważności linku (ADR-010: default 7 dni).
MIN_SHARE_DAYS = 1
MAX_SHARE_DAYS = 365
DEFAULT_SHARE_DAYS = 7

_LISTS = ScopedQuery(ShoppingList, not_found_message=LIST_NOT_FOUND)


class ShoppingListValidationError(AppError):
    """422 — żądanie wskazuje encję, której nie ma (np. nieistniejący sklep)."""

    status_code = 422
    code = "validation_error"


@dataclass(frozen=True)
class ListSection:
    """Sekcja listy: kategoria + pozycje w kolejności przejścia po sklepie."""

    category_id: int
    category_name: str
    items: list[ShoppingListItem]


@dataclass(frozen=True)
class ShareView:
    """Stan publicznego linku listy (ADR-010)."""

    url: str
    expires_at: datetime
    revoked: bool


@dataclass(frozen=True)
class ShoppingListSummary:
    """Lista na liście list: bez pozycji, ale z licznikiem odhaczonych."""

    shopping_list: ShoppingList
    store_name: str | None
    items_total: int
    items_checked: int
    share: ShareView | None


@dataclass(frozen=True)
class ShoppingListDetail:
    """Pełny widok listy: sekcje w kolejności sklepu + stan udostępnienia."""

    shopping_list: ShoppingList
    store_name: str | None
    sections: list[ListSection]
    share: ShareView | None


@dataclass(frozen=True)
class PublicListItemView:
    """Pozycja w widoku publicznym — BIAŁA LISTA pól (02_DOMAIN §13.5).

    Czego tu świadomie NIE MA: `product_id`, `retail_product_id`, `position`,
    `from_pantry_amount` ani czegokolwiek o właścicielu. Osoba z linkiem ma
    kupić zakupy, a nie poznać strukturę danych rodziny.
    """

    id: int
    label: str
    amount: Decimal
    unit: AmountUnit
    category_name: str
    checked: bool
    leftover_amount: Decimal | None
    already_have: bool
    packages_count: int | None
    package_size: Decimal | None


@dataclass(frozen=True)
class PublicListView:
    """Publiczny widok listy: nazwa, ważność, pozycje. Nic więcej."""

    name: str
    expires_at: datetime
    items: list[PublicListItemView]


@dataclass(frozen=True)
class ReceivedToPantry:
    """Wynik „przyjmij zakupy do spiżarni": ile pozycji weszło i ile pominięto."""

    created: int
    increased: int
    skipped: int


class ShoppingListsService:
    """Operacje na gotowych listach zakupowych. Jedyne miejsce I/O tego obszaru."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._stores = StoresService(session)
        self._pantry = PantryService(session)

    # --- odczyt --------------------------------------------------------------------

    async def list_lists(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        now: datetime,
        expired: bool | None = None,
    ) -> tuple[list[ShoppingListSummary], int]:
        """Listy widoczne dla użytkownika, najnowsze pierwsze.

        `expired=None` zwraca wszystko: wygasła lista NIE znika (D10 — historia
        jest wartością), tylko jej token przestaje działać. Filtr `?status=`
        jest wygodą widoku, nie retencją.
        """
        statement = _LISTS.select_visible(user)
        if expired is True:
            statement = statement.where(ShoppingList.expires_at <= now)
        elif expired is False:
            statement = statement.where(ShoppingList.expires_at > now)

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    statement.order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        lists = list(rows)
        counts = await self._item_counts([row.id for row in lists])
        store_names = await self._store_names([row.store_id for row in lists])
        return [
            ShoppingListSummary(
                shopping_list=row,
                store_name=store_names.get(row.store_id) if row.store_id else None,
                items_total=counts.get(row.id, (0, 0))[0],
                items_checked=counts.get(row.id, (0, 0))[1],
                share=_share_view(row),
            )
            for row in lists
        ], int(total)

    async def get_list(self, list_id: int, *, user: User) -> ShoppingListDetail:
        """Lista z pozycjami POSORTOWANYMI wg profilu sklepu (karta B11 §Backend)."""
        shopping_list = await _LISTS.get_or_404(self._session, list_id, user)
        return await self._detail(shopping_list)

    # --- edycja --------------------------------------------------------------------

    async def update_list(
        self,
        list_id: int,
        *,
        user: User,
        name: str | None = None,
        store_id: int | None = None,
        clear_store: bool = False,
    ) -> ShoppingListDetail:
        """Nazwa i sklep listy. Sklep = profil sortowania, więc zmienia kolejność sekcji.

        Sklep wybiera się TUTAJ, a nie przy finalizacji: „gdzie dziś jadę" jest
        decyzją momentu zakupów, a nie właściwością generacji (karta B11 §Context
        pkt 3). Nieznany sklep to 422 — 404 należy do zasobu z URL-a, nie do
        wartości jego pola (wzorzec z B08).
        """
        shopping_list = await _LISTS.get_or_404(self._session, list_id, user)
        if name is not None:
            shopping_list.name = name
        if clear_store:
            shopping_list.store_id = None
        elif store_id is not None:
            store = await self._session.get(Store, store_id)
            if store is None:
                raise ShoppingListValidationError(
                    STORE_NOT_AVAILABLE, details={"store_id": store_id}
                )
            shopping_list.store_id = store.id
        await self._session.commit()
        # `updated_at` ma `onupdate=func.now()`, więc po UPDATE liczy je BAZA
        # i kolumna zostaje wygaszona. Bez tego odświeżenia jej odczyt w routerze
        # byłby leniwym IO w kontekście bez greenletu (MissingGreenlet) — złapał
        # to `task check` przy pierwszym przebiegu testów PATCH-a.
        await self._session.refresh(shopping_list)
        return await self._detail(shopping_list)

    async def delete_list(self, list_id: int, *, user: User) -> None:
        """Usunięcie listy: właściciel albo ADMIN (macierz 08_TESTING §4).

        D10 zostaje w mocy: automat nie kasuje NICZEGO, a to jest jawna decyzja
        człowieka. Pozycje giną kaskadą (`ON DELETE CASCADE`, ADR-012) — i to
        jedyna droga, żeby produkt użyty wyłącznie na tej liście dał się w końcu
        usunąć (FK pozycji ma RESTRICT).
        """
        shopping_list = await _LISTS.get_or_404(self._session, list_id, user)
        _LISTS.assert_can_manage(shopping_list, user)
        await self._session.execute(delete(ShoppingList).where(ShoppingList.id == list_id))
        await self._session.commit()

    async def update_item(
        self,
        list_id: int,
        item_id: int,
        *,
        user: User,
        now: datetime,
        checked: bool | None = None,
        already_have: bool | None = None,
    ) -> ShoppingListItem:
        """Odhaczenie i „mam już w domu" — jedyne, co da się na pozycji zmienić.

        Reszta pozycji jest WYNIKIEM generacji (karta B11 §Out of Scope pkt 4),
        więc ilości i produktu tu się nie edytuje.
        """
        await _LISTS.get_or_404(self._session, list_id, user)
        item = await self._item_or_404(list_id, item_id)
        _apply_item_changes(item, checked=checked, already_have=already_have, now=now)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    # --- udostępnianie (ADR-010) ---------------------------------------------------

    async def share_list(
        self, list_id: int, *, user: User, expires_in_days: int, now: datetime
    ) -> ShareView:
        """Nowy publiczny link: token 256-bit + wybrana ważność.

        Każde udostępnienie generuje NOWY token, także po odwołaniu — stary link
        nie wraca do życia, bo mógł już trafić do obcych rąk (ADR-010).
        Udostępnić może każdy członek rodziny listy: rodzina sobie ufa
        (02_DOMAIN §3.1), a link i tak da się natychmiast odwołać.
        """
        shopping_list = await _LISTS.get_or_404(self._session, list_id, user)
        shopping_list.public_token = generate_token()
        shopping_list.token_revoked = False
        shopping_list.expires_at = now + timedelta(days=expires_in_days)
        await self._session.commit()
        await self._session.refresh(shopping_list)
        share = _share_view(shopping_list)
        assert share is not None  # token właśnie powstał
        return share

    async def revoke_share(self, list_id: int, *, user: User) -> None:
        """Odwołanie linku: token zostaje w bazie, ale przestaje działać (410).

        Nie zerujemy kolumny, żeby ponowne udostępnienie nie mogło wylosować
        (teoretycznie) tej samej wartości i wskrzesić starego linku.
        """
        shopping_list = await _LISTS.get_or_404(self._session, list_id, user)
        shopping_list.token_revoked = True
        await self._session.commit()

    # --- ścieżka publiczna (bez sesji, autoryzuje token) ---------------------------

    async def public_list(self, token: str, *, now: datetime) -> PublicListView:
        """Treść listy dla osoby z linkiem — bez PII (02_DOMAIN §13.5)."""
        shopping_list = await self._list_by_token(token, now=now)
        detail = await self._detail(shopping_list)
        return PublicListView(
            name=shopping_list.name,
            expires_at=shopping_list.expires_at,
            items=[
                PublicListItemView(
                    id=item.id,
                    label=item.label,
                    amount=item.needed_amount,
                    unit=item.amount_unit,
                    category_name=section.category_name,
                    checked=item.checked,
                    leftover_amount=item.leftover_amount,
                    already_have=item.already_have,
                    packages_count=item.packages_count,
                    package_size=item.package_size,
                )
                for section in detail.sections
                for item in section.items
            ],
        )

    async def public_check_item(
        self, token: str, item_id: int, *, checked: bool, now: datetime
    ) -> PublicListItemView:
        """Odhaczenie pozycji z publicznego linku — WYŁĄCZNIE pole `checked`.

        Uprawnienia tokenu kończą się tutaj (ADR-010): schemat żądania nie ma
        innych pól, więc próba przemycenia `already_have` czy ilości nie ma jak
        wejść, a nie tylko „jest ignorowana".
        """
        shopping_list = await self._list_by_token(token, now=now)
        item = await self._item_or_404(shopping_list.id, item_id)
        _apply_item_changes(item, checked=checked, already_have=None, now=now)
        await self._session.commit()
        await self._session.refresh(item)
        category_name = await self._category_name(item.category_id)
        return PublicListItemView(
            id=item.id,
            label=item.label,
            amount=item.needed_amount,
            unit=item.amount_unit,
            category_name=category_name,
            checked=item.checked,
            leftover_amount=item.leftover_amount,
            already_have=item.already_have,
            packages_count=item.packages_count,
            package_size=item.package_size,
        )

    # --- przyjęcie zakupów do spiżarni (02_DOMAIN §8) ------------------------------

    async def accept_to_pantry(self, list_id: int, *, user: User) -> ReceivedToPantry:
        """Odhaczone pozycje → spiżarnia. Akcja JAWNA, nigdy w tle.

        Ilość: KUPIONA, czyli `packages_count * package_size`, a nie potrzeba.
        Do domu wraca całe opakowanie, więc resztka też jest stanem domowym —
        gdybyśmy przyjmowali `needed_amount`, spiżarnia od pierwszych zakupów
        zaniżałaby stan dokładnie o wyliczoną resztkę. Bez wariantu sklepowego
        (brak opakowania) zostaje `needed_amount` — tyle wiadomo.

        Jednostki się nie przelicza: `package_size` jest z definicji na osi
        produktu kanonicznego (niezmiennik B09), tej samej, którą przyjmuje
        `PantryService`. Nieodhaczone pozycje nie wchodzą w ogóle, a odhaczone
        bez produktu kanonicznego albo z zerową ilością liczymy jako `skipped` —
        nie ma czego dołożyć, ale użytkownik ma o tym wiedzieć.

        **Całość jest JEDNĄ transakcją** (ustalenie REVIEW R3): `receive_purchase`
        nie commituje, a commit jest tutaj, po przejściu wszystkich pozycji.
        Wcześniej każda pozycja commitowała osobno, więc błąd w połowie listy
        (np. produkt usunięty w międzyczasie → 422) zostawiał spiżarnię w stanie
        pośrednim i zwracał użytkownikowi błąd, po którym ponowienie akcji
        dolewało już przyjęte pozycje DRUGI raz.
        """
        await _LISTS.get_or_404(self._session, list_id, user)
        items = await self._items(list_id)
        created = 0
        increased = 0
        skipped = 0
        for item in items:
            if not item.checked:
                continue
            if item.already_have:
                # „Mam już w domu" znaczy „nic nie kupujemy" (02_DOMAIN §9.3),
                # więc pozycja nie jest zakupem — nawet odhaczona. Bez tego warunku
                # odhaczenie wyszarzonego wiersza („tak, potwierdzam, że mam")
                # dokładało do spiżarni ilość, której nikt nie kupił (ustalenie
                # REVIEW R3). Liczymy ją jako pominiętą, żeby użytkownik zobaczył,
                # że nie zniknęła po cichu.
                skipped += 1
                continue
            amount = _purchased_amount(item)
            if item.product_id is None or amount <= Decimal("0"):
                skipped += 1
                continue
            result = await self._pantry.receive_purchase(
                actor=user, product_id=item.product_id, amount=amount
            )
            if result.merged:
                increased += 1
            else:
                created += 1
        if created == 0 and increased == 0:
            # Rollback jawny: pętla mogła zrobić `flush` dla pozycji, które
            # ostatecznie policzyliśmy jako pominięte.
            await self._session.rollback()
            raise ConflictError(NOTHING_TO_RECEIVE)
        await self._session.commit()
        return ReceivedToPantry(created=created, increased=increased, skipped=skipped)

    # --- pomocnicze ----------------------------------------------------------------

    async def _detail(self, shopping_list: ShoppingList) -> ShoppingListDetail:
        """Lista + posortowane sekcje. JEDNA droga dla widoku prywatnego i publicznego."""
        items = await self._items(shopping_list.id)
        categories = await self._categories([item.category_id for item in items])
        profile: Sequence[CategoryOrderEntry] = (
            await self._stores.category_order(shopping_list.store_id)
            if shopping_list.store_id is not None
            else ()
        )
        sections = sort_into_sections(
            [
                SortableItem(
                    item_id=item.id,
                    category_id=item.category_id,
                    already_have=item.already_have,
                    position=item.position,
                )
                for item in items
            ],
            profile=profile,
            global_positions={
                category_id: position for category_id, (_, position) in categories.items()
            },
        )
        by_id = {item.id: item for item in items}
        store_names = await self._store_names([shopping_list.store_id])
        return ShoppingListDetail(
            shopping_list=shopping_list,
            store_name=(
                store_names.get(shopping_list.store_id)
                if shopping_list.store_id is not None
                else None
            ),
            sections=[
                ListSection(
                    category_id=section.category_id,
                    category_name=categories.get(section.category_id, ("", 0))[0],
                    items=[by_id[item_id] for item_id in section.item_ids],
                )
                for section in sections
            ],
            share=_share_view(shopping_list),
        )

    async def _list_by_token(self, token: str, *, now: datetime) -> ShoppingList:
        """Lista po PEŁNYM tokenie: 404 nieznany, 410 wygasły albo odwołany.

        Lookup idzie po unique index (07_SECURITY §5) — bez prefiksów, bez
        `LIKE`, bez porównań częściowych.
        """
        shopping_list = (
            await self._session.execute(
                select(ShoppingList).where(ShoppingList.public_token == token)
            )
        ).scalar_one_or_none()
        if shopping_list is None:
            raise NotFoundError(LIST_TOKEN_UNKNOWN)
        if shopping_list.token_revoked or shopping_list.expires_at <= now:
            raise GoneError(LIST_GONE)
        return shopping_list

    async def _items(self, list_id: int) -> list[ShoppingListItem]:
        rows = (
            (
                await self._session.execute(
                    select(ShoppingListItem)
                    .where(ShoppingListItem.list_id == list_id)
                    .order_by(ShoppingListItem.position, ShoppingListItem.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _item_or_404(self, list_id: int, item_id: int) -> ShoppingListItem:
        """Pozycja NALEŻĄCA do tej listy — cudza daje 404 (04_API §2c)."""
        item = (
            await self._session.execute(
                select(ShoppingListItem).where(
                    ShoppingListItem.id == item_id, ShoppingListItem.list_id == list_id
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError(ITEM_NOT_FOUND)
        return item

    async def _item_counts(self, list_ids: Sequence[int]) -> dict[int, tuple[int, int]]:
        """Liczba pozycji i odhaczonych per lista — jednym zapytaniem, nie N+1."""
        if not list_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    ShoppingListItem.list_id,
                    func.count(),
                    func.count().filter(ShoppingListItem.checked.is_(True)),
                )
                .where(ShoppingListItem.list_id.in_(list(list_ids)))
                .group_by(ShoppingListItem.list_id)
            )
        ).all()
        return {int(row[0]): (int(row[1]), int(row[2])) for row in rows}

    async def _categories(self, category_ids: Sequence[int]) -> dict[int, tuple[str, int]]:
        """Nazwa i globalna pozycja kategorii — materiał do sortowania sekcji."""
        unique = sorted(set(category_ids))
        if not unique:
            return {}
        rows = (
            await self._session.execute(
                select(ProductCategory.id, ProductCategory.name, ProductCategory.position).where(
                    ProductCategory.id.in_(unique)
                )
            )
        ).all()
        return {int(row[0]): (str(row[1]), int(row[2])) for row in rows}

    async def _category_name(self, category_id: int) -> str:
        return (await self._categories([category_id])).get(category_id, ("", 0))[0]

    async def _store_names(self, store_ids: Sequence[int | None]) -> dict[int, str]:
        unique = sorted({store_id for store_id in store_ids if store_id is not None})
        if not unique:
            return {}
        rows = (
            await self._session.execute(select(Store.id, Store.name).where(Store.id.in_(unique)))
        ).all()
        return {int(row[0]): str(row[1]) for row in rows}


# --- czyste funkcje pomocnicze ----------------------------------------------------------


def _share_view(shopping_list: ShoppingList) -> ShareView | None:
    """Stan linku dla WŁAŚCICIELA listy; `None` = nigdy nie udostępniona.

    Odwołany link zostaje widoczny jako `revoked=True`, bo UI ma pokazać, że
    ktoś go kiedyś wystawił (i dać przycisk „udostępnij ponownie").
    """
    if shopping_list.public_token is None:
        return None
    return ShareView(
        url=f"{PUBLIC_URL_PREFIX}{shopping_list.public_token}",
        expires_at=shopping_list.expires_at,
        revoked=shopping_list.token_revoked,
    )


def _apply_item_changes(
    item: ShoppingListItem,
    *,
    checked: bool | None,
    already_have: bool | None,
    now: datetime,
) -> None:
    """Zastosuj zmiany pozycji; `checked_at` ustawia SERWER, nigdy klient.

    `checked_at` to moment OSTATNIEJ decyzji o checkboxie — także odznaczenia.
    Tak go potrzebuje LWW z ADR-009 (B12): żeby rozstrzygnąć konflikt dwóch
    telefonów, trzeba wiedzieć, która decyzja jest młodsza, a nie tylko kiedy
    coś zostało odhaczone. Klient `checked_at` nie przysyła (karta B11,
    Implementation Notes pkt 3).
    """
    if checked is not None and checked != item.checked:
        item.checked = checked
        item.checked_at = now
    if already_have is not None:
        item.already_have = already_have


def _purchased_amount(item: ShoppingListItem) -> Decimal:
    """Ile FAKTYCZNIE wraca do domu: całe opakowania albo sama potrzeba."""
    if item.packages_count is not None and item.package_size is not None:
        return Decimal(item.packages_count) * item.package_size
    return item.needed_amount
