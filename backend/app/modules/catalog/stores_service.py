"""Logika sklepów i profili kolejności kategorii (02_DOMAIN §4.5).

Osobny plik obok `service.py` z tego samego powodu, co `templates_service.py`
w module planning (B07): to inny obszar tego samego modułu, a `service.py`
katalogu ma już 860 linii. Nowego modułu top-level NIE ma — sklepy są częścią
słownika instancji (02_DOMAIN §1), więc mieszkają w `catalog`.

Sklepy są GLOBALNE (02_DOMAIN §3.1 pkt 3): nie ma tu `ScopedQuery`, bo nie ma
czego zawężać — każdy zalogowany widzi ten sam słownik i każdy może go
edytować. Sesji wymaga router (`CurrentUser`).

Profil sklepu (`store_category_order`) jest PODMIENIANY W CAŁOŚCI, nigdy
łatany po jednym wierszu: kolejność to permutacja, a nie zbiór niezależnych
liczb — częściowa aktualizacja pozwoliłaby zapisać dwie kategorie na tej samej
pozycji albo dziurę w numeracji.

Dziennika audytu tu nie ma świadomie: 02_DOMAIN §12 obejmuje wartości odżywcze,
weryfikację produktów, import, operacje admina na kontach i transfer danych —
sklep to zwykły słownik użytkowy, jak pozycje spiżarni w B08.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deletion import (
    USED_IN_LIMIT,
    UsedInRef,
    assert_deletable,
    conflict_from_integrity_error,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.accounts.models import User
from app.modules.catalog.models import (
    ProductCategory,
    RetailProduct,
    Store,
    StoreCategoryOrder,
)

__all__ = [
    "CategoryOrderEntry",
    "StoreValidationError",
    "StoresService",
    "register_store_reference_finder",
    "unregister_store_reference_finder",
]

STORE_NOT_FOUND = "Nie znaleziono sklepu o podanym identyfikatorze."
STORE_IN_USE = (
    "Sklep jest używany i nie może zostać usunięty. Zamiast usuwać, zarchiwizuj go — "
    "zniknie z list wyboru, a dane historyczne zostaną nietknięte."
)
ORDER_DUPLICATE = (
    "Ta sama kategoria występuje w kolejności więcej niż raz. Kolejność przejścia "
    "po sklepie to jedna lista — każda kategoria ma w niej dokładnie jedno miejsce."
)
ORDER_UNKNOWN_CATEGORY = (
    "Kolejność wskazuje kategorię, której nie ma w słowniku. Odśwież stronę i zapisz ponownie."
)
STORE_NAME_TAKEN = "Sklep o tej nazwie już istnieje."


class StoreValidationError(AppError):
    """422 — dane sklepu albo profilu są wewnętrznie sprzeczne.

    Nie `RequestValidationError`: te reguły dotyczą LISTY jako całości
    (duplikaty, istnienie kategorii), a nie kształtu pojedynczego pola.
    """

    status_code = 422
    code = "validation_error"


#: Funkcja licząca referencje do sklepu w innym module.
StoreReferenceFinder = Callable[[AsyncSession, int], Awaitable[Sequence[UsedInRef]]]

#: Rejestr konsumentów sklepów. B09 liczy `retail_products` wprost (ta sama
#: tabela, ten sam modul), a listy zakupowe z profilem sklepu (`shopping_lists`,
#: B11) dopisują swój licznik tutaj — inaczej 409 wyszłoby bez listy „Używane w:".
_STORE_REFERENCE_FINDERS: list[StoreReferenceFinder] = []


def register_store_reference_finder(finder: StoreReferenceFinder) -> None:
    """Zarejestruj licznik referencji do sklepu (wołane przy imporcie modułu)."""
    if finder not in _STORE_REFERENCE_FINDERS:
        _STORE_REFERENCE_FINDERS.append(finder)


def unregister_store_reference_finder(finder: StoreReferenceFinder) -> None:
    """Wyrejestruj licznik — testy sprzątają po sobie, żeby nie przeciekał dalej."""
    if finder in _STORE_REFERENCE_FINDERS:
        _STORE_REFERENCE_FINDERS.remove(finder)


@dataclass(frozen=True)
class CategoryOrderEntry:
    """Pozycja profilu razem z nazwą kategorii — gotowa dla warstwy HTTP."""

    category_id: int
    category_name: str
    position: int


class StoresService:
    """Operacje na sklepach i ich profilach. Jedyne miejsce I/O tego obszaru."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- sklepy -------------------------------------------------------------------

    async def list_stores(self, *, include_archived: bool = False) -> list[Store]:
        """Sklepy alfabetycznie, w całości. Bez paginacji i bez filtra `q`.

        Słownik jest krótki (kilka albo kilkanaście pozycji), jak kategorie, więc
        `StorePicker` dostaje całą listę jednym zapytaniem i filtruje ją po
        stronie klienta. Szukajka serwerowa byłaby tu API bez konsumenta —
        a takiego nie utrzymujemy „na wszelki wypadek".
        """
        statement: Select[tuple[Store]] = select(Store)
        if not include_archived:
            statement = statement.where(Store.is_archived.is_(False))

        rows = (
            (
                await self._session.execute(
                    statement.order_by(Store.name, Store.id).execution_options(
                        populate_existing=True
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def get_store(self, store_id: int) -> Store:
        """Sklep albo 404. Słownik jest globalny, więc nie ma tu filtra scope."""
        store = (
            await self._session.execute(
                select(Store).where(Store.id == store_id).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if store is None:
            raise NotFoundError(STORE_NOT_FOUND)
        return store

    async def create_store(self, *, actor: User, name: str, color: str | None) -> Store:
        """Nowy sklep — także inline z `StorePicker` (06_UIUX §3.1).

        Duplikat sprawdzamy BEZ rozróżniania wielkości liter (wzorzec `create_tag`
        z B05): baza pilnuje dokładnego zapisu, ale „Lidl" i „lidl" to dla
        człowieka jeden sklep, a picker ma zaproponować istniejący, nie tworzyć
        bliźniaka. `actor` nie zmienia tu niczego — słownik jest globalny
        i edytowalny przez USERA (02_DOMAIN §3.1 pkt 3).
        """
        cleaned = " ".join(name.split())
        existing = await self._find_by_name(cleaned)
        if existing is not None:
            raise _duplicate_error(existing)

        store = Store(name=cleaned, color=color)
        self._session.add(store)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Wyścig dwóch żądań: baza rozstrzyga UNIQUE, my tłumaczymy na 409.
            await self._session.rollback()
            raise ConflictError(STORE_NAME_TAKEN) from exc
        await self._session.refresh(store)
        return store

    async def update_store(
        self, store_id: int, *, actor: User, changes: Mapping[str, Any]
    ) -> Store:
        """Edycja sklepu: nazwa, kolor, archiwizacja."""
        store = await self.get_store(store_id)
        if "name" in changes:
            cleaned = " ".join(str(changes["name"]).split())
            duplicate = await self._find_by_name(cleaned, exclude_id=store_id)
            if duplicate is not None:
                raise _duplicate_error(duplicate)
            store.name = cleaned
        for field in ("color", "is_archived"):
            if field in changes:
                setattr(store, field, changes[field])
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(STORE_NAME_TAKEN) from exc
        await self._session.refresh(store)
        return store

    async def delete_store(self, store_id: int, *, actor: User) -> None:
        """Usuń sklep — wyłącznie nieużywany; inaczej 409 z listą użyć (ADR-012).

        Profil (`store_category_order`) NIE blokuje: to atrybut sklepu, więc
        znika kaskadą razem z nim.
        """
        await self.get_store(store_id)
        assert_deletable(STORE_IN_USE, await self.store_references(store_id))

        await self._session.execute(delete(Store).where(Store.id == store_id))
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Druga linia obrony: konsument, który nie zarejestrował licznika
            # (B11). Bez tego użytkownik dostałby 500 zamiast 409.
            await self._session.rollback()
            raise conflict_from_integrity_error(STORE_IN_USE) from exc

    async def store_references(self, store_id: int) -> list[UsedInRef]:
        """Gdzie sklep jest używany: warianty retail + liczniki konsumentów (B11)."""
        rows = (
            await self._session.execute(
                select(RetailProduct.id, RetailProduct.name)
                .where(RetailProduct.store_id == store_id)
                .order_by(RetailProduct.name, RetailProduct.id)
                .limit(USED_IN_LIMIT)
            )
        ).all()
        references = [
            UsedInRef(type="retail_product", id=int(row[0]), name=str(row[1])) for row in rows
        ]
        for finder in _STORE_REFERENCE_FINDERS:
            references.extend(await finder(self._session, store_id))
        return references[:USED_IN_LIMIT]

    # --- profil kolejności kategorii ------------------------------------------------

    async def category_order(self, store_id: int) -> list[CategoryOrderEntry]:
        """Kategorie profilu w kolejności przejścia po sklepie (404, gdy sklepu nie ma)."""
        await self.get_store(store_id)
        rows = (
            await self._session.execute(
                select(
                    StoreCategoryOrder.category_id,
                    ProductCategory.name,
                    StoreCategoryOrder.position,
                )
                .join(ProductCategory, StoreCategoryOrder.category_id == ProductCategory.id)
                .where(StoreCategoryOrder.store_id == store_id)
                .order_by(StoreCategoryOrder.position, ProductCategory.name)
            )
        ).all()
        return [
            CategoryOrderEntry(
                category_id=int(row[0]), category_name=str(row[1]), position=int(row[2])
            )
            for row in rows
        ]

    async def set_category_order(
        self, store_id: int, *, actor: User, category_ids: Sequence[int]
    ) -> list[CategoryOrderEntry]:
        """PEŁNA podmiana profilu: lista `category_id` w docelowej kolejności.

        `position` liczymy z indeksów listy — kolejność jest tym, co przysłał
        klient, a numery są wewnętrznym szczegółem. Duplikat i nieznana
        kategoria kończą się 422 PRZED jakimkolwiek zapisem: pół-zapisany profil
        byłby gorszy od odrzuconego żądania.
        """
        await self.get_store(store_id)

        wanted = list(category_ids)
        if len(set(wanted)) != len(wanted):
            raise StoreValidationError(ORDER_DUPLICATE)

        if wanted:
            known = set(
                (
                    await self._session.execute(
                        select(ProductCategory.id).where(ProductCategory.id.in_(wanted))
                    )
                )
                .scalars()
                .all()
            )
            missing = [category_id for category_id in wanted if category_id not in known]
            if missing:
                raise StoreValidationError(
                    ORDER_UNKNOWN_CATEGORY, details={"unknown_category_ids": missing}
                )

        await self._session.execute(
            delete(StoreCategoryOrder).where(StoreCategoryOrder.store_id == store_id)
        )
        if wanted:
            await self._session.execute(
                insert(StoreCategoryOrder),
                [
                    {"store_id": store_id, "category_id": category_id, "position": position}
                    for position, category_id in enumerate(wanted)
                ],
            )
        await self._session.commit()
        return await self.category_order(store_id)

    # --- pomocnicze ------------------------------------------------------------------

    async def _find_by_name(self, name: str, *, exclude_id: int | None = None) -> Store | None:
        """Sklep o tej nazwie (bez rozróżniania wielkości liter) albo `None`."""
        statement = select(Store).where(func.lower(Store.name) == name.casefold())
        if exclude_id is not None:
            statement = statement.where(Store.id != exclude_id)
        return (await self._session.execute(statement)).scalars().first()


def _duplicate_error(existing: Store) -> ConflictError:
    """409 z podpowiedzią istniejącego sklepu — paliwo dla inline create.

    Picker może od razu zaproponować „ten sklep już jest, wziąć go?" zamiast
    zostawiać użytkownika z samym komunikatem o błędzie (06_UIUX §3.1).
    """
    return ConflictError(
        f"Sklep „{existing.name}” już istnieje.",
        details={
            "existing": {
                "id": existing.id,
                "name": existing.name,
                "is_archived": existing.is_archived,
            }
        },
    )
