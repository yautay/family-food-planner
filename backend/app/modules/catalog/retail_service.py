"""Logika produktów sklepowych (retail) — 02_DOMAIN §4.4.

Osobny plik obok `service.py` i `stores_service.py` z tego samego powodu, co
`templates_service.py` w module planning (B07): inny obszar tego samego modułu.
Modułu top-level `retail` NIE ma — wariant sklepowy jest częścią słownika
instancji (02_DOMAIN §1) i bez produktu kanonicznego nie istnieje.

Trzy rzeczy, które ten serwis pilnuje i których nie pilnuje baza:

1. **Produkt kanoniczny musi istnieć** — kolumna jest NOT NULL, ale „nie ma
   takiego id" to dla użytkownika błąd danych wejściowych (422), nie 500 z FK.
2. **Zgodność jednostki opakowania z `measure_kind`** produktu kanonicznego
   (g↔mass, ml↔volume, piece↔piece). Oś bierzemy z `units.base_unit`, czyli
   z JEDYNEGO miejsca konwersji ilości w systemie (CLAUDE.md §4) — nie z
   własnej tabelki mapowań.
3. **Blokada usuwania** (ADR-012): wariant użyty w spiżarni czy na liście
   zakupowej znika tylko przez `is_archived`.

Zdjęcia jadą przez `app/core/uploads.py` — ten sam pipeline co zdjęcia
przepisów (B05): limit 10 MB, sniffing treści, re-encode do JPEG, miniatura.
Pillow jest CPU-bound, więc wołamy go przez `run_in_threadpool` (ADR-015).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deletion import (
    USED_IN_LIMIT,
    UsedInRef,
    assert_deletable,
    conflict_from_integrity_error,
)
from app.core.errors import AppError, NotFoundError
from app.core.uploads import delete_image, save_image
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, RetailProduct, Store
from app.modules.catalog.service import register_product_reference_finder
from app.modules.catalog.units import AmountUnit, base_unit

__all__ = [
    "PHOTO_SUBDIR",
    "RetailProductView",
    "RetailService",
    "RetailValidationError",
    "register_retail_reference_finder",
    "unregister_retail_reference_finder",
]

#: Podkatalog uploadów dla zdjęć wariantów sklepowych (obok `recipes`).
PHOTO_SUBDIR = "retail"

RETAIL_NOT_FOUND = "Nie znaleziono produktu sklepowego o podanym identyfikatorze."
CANONICAL_REQUIRED = (
    "Produkt sklepowy musi wskazywać produkt kanoniczny — to z niego biorą się "
    "wartości odżywcze i miejsce na liście zakupów. Wybierz produkt i spróbuj ponownie."
)
STORE_NOT_AVAILABLE = "Nie znaleziono sklepu, który chcesz przypisać. Odśwież listę sklepów."
RETAIL_IN_USE = (
    "Produkt sklepowy jest używany i nie może zostać usunięty. Zamiast usuwać, "
    "zarchiwizuj go — zniknie z list wyboru, a dane historyczne zostaną nietknięte."
)
NO_PHOTO_MESSAGE = "Ten produkt sklepowy nie ma zdjęcia."

#: Jednostka opakowania w komunikacie o niezgodności — po polsku, jak w UI.
_UNIT_LABELS: dict[AmountUnit, str] = {
    AmountUnit.GRAM: "gramach (g)",
    AmountUnit.MILLILITER: "mililitrach (ml)",
    AmountUnit.PIECE: "sztukach",
}

#: Pola, które PATCH wolno podmienić. `canonical_product_id` NIE jest tu
#: świadomie: przepięcie wariantu na inny produkt zmieniłoby znaczenie danych
#: historycznych (spiżarnia, listy) bez śladu — patrz `RetailProductUpdateRequest`.
EDITABLE_FIELDS = (
    "name",
    "brand",
    "store_id",
    "package_amount",
    "package_unit",
    "pieces_per_package",
    "is_archived",
)


class RetailValidationError(AppError):
    """422 — dane wariantu nie trzymają się reguł domeny.

    Nie `RequestValidationError`: te reguły zależą od WSKAZANEGO produktu
    kanonicznego (jego `measure_kind`), a nie od kształtu pojedynczego pola.
    """

    status_code = 422
    code = "validation_error"


#: Funkcja licząca referencje do wariantu sklepowego w innym module.
RetailReferenceFinder = Callable[[AsyncSession, int], Awaitable[Sequence[UsedInRef]]]

#: Rejestr konsumentów wariantów retail. Moduły z FK do `retail_products`
#: (spiżarnia — B08/B09, pozycje list zakupowych — B11) rejestrują tu funkcję
#: zwracającą CZYTELNE nazwy miejsc użycia. Bez wpisu 409 wyszłoby bez listy
#: „Używane w:" — poprawne dzięki FK RESTRICT, ale bezużyteczne (06_UIUX §3.3).
_RETAIL_REFERENCE_FINDERS: list[RetailReferenceFinder] = []


def register_retail_reference_finder(finder: RetailReferenceFinder) -> None:
    """Zarejestruj licznik referencji do wariantu sklepowego."""
    if finder not in _RETAIL_REFERENCE_FINDERS:
        _RETAIL_REFERENCE_FINDERS.append(finder)


def unregister_retail_reference_finder(finder: RetailReferenceFinder) -> None:
    """Wyrejestruj licznik — testy sprzątają po sobie, żeby nie przeciekał dalej."""
    if finder in _RETAIL_REFERENCE_FINDERS:
        _RETAIL_REFERENCE_FINDERS.remove(finder)


@dataclass(frozen=True)
class RetailProductView:
    """Wariant razem z tym, co warstwa HTTP musi o nim wiedzieć.

    Encje towarzyszące są doczytane JAWNIE — warstwa HTTP jest synchroniczna,
    więc sięgnięcie po leniwą relację kończy się `MissingGreenlet` i 500
    (lekcja z BATCH_03).
    """

    retail: RetailProduct
    product: CanonicalProduct
    store: Store | None


class RetailService:
    """Operacje na wariantach sklepowych. Jedyne miejsce I/O tego obszaru."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._uploads_root = Path(get_settings().uploads_dir)

    # --- odczyt -------------------------------------------------------------------

    async def get_retail_product(self, retail_id: int) -> RetailProduct:
        """Wariant albo 404. Słownik jest globalny, więc nie ma tu filtra scope."""
        retail = (
            await self._session.execute(
                select(RetailProduct)
                .where(RetailProduct.id == retail_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if retail is None:
            raise NotFoundError(RETAIL_NOT_FOUND)
        return retail

    async def retail_view(self, retail_id: int) -> RetailProductView:
        """Wariant + produkt kanoniczny + sklep, jednym zapytaniem."""
        row = (
            await self._session.execute(
                self._view_statement()
                .where(RetailProduct.id == retail_id)
                .execution_options(populate_existing=True)
            )
        ).first()
        if row is None:
            raise NotFoundError(RETAIL_NOT_FOUND)
        return RetailProductView(retail=row[0], product=row[1], store=row[2])

    async def list_retail_products(
        self,
        *,
        limit: int,
        offset: int,
        canonical_product_id: int | None = None,
        store_id: int | None = None,
        query: str | None = None,
        include_archived: bool = False,
    ) -> tuple[list[RetailProductView], int]:
        """Lista wariantów z filtrami z karty B09 (04_API §1).

        Szukajka jest zwykłym dopasowaniem fragmentu nazwy albo marki — nie
        trigramem jak w katalogu kanonicznym. Wariantów jednego produktu jest
        kilka, a nie tysiące, więc próg podobieństwa wprowadzałby tylko
        niespodzianki; `autoescape` chroni `%` i `_` z frazy użytkownika.
        """
        statement = self._view_statement()
        if not include_archived:
            statement = statement.where(RetailProduct.is_archived.is_(False))
        if canonical_product_id is not None:
            statement = statement.where(RetailProduct.canonical_product_id == canonical_product_id)
        if store_id is not None:
            statement = statement.where(RetailProduct.store_id == store_id)
        phrase = (query or "").strip()
        if phrase:
            statement = statement.where(
                RetailProduct.name.icontains(phrase, autoescape=True)
                | RetailProduct.brand.icontains(phrase, autoescape=True)
            )

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            await self._session.execute(
                statement.order_by(RetailProduct.name, RetailProduct.id)
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            )
        ).all()
        return (
            [RetailProductView(retail=row[0], product=row[1], store=row[2]) for row in rows],
            int(total),
        )

    async def options_for_products(
        self, product_ids: Sequence[int], *, include_archived: bool = False
    ) -> dict[int, list[RetailProduct]]:
        """Warianty sklepowe wskazanych produktów — wejście silnika zakupowego (B10).

        Publiczne wejście obok `list_retail_products`, bo tamto pyta o JEDEN
        produkt kanoniczny (karta produktu), a silnik potrzebuje kilkudziesięciu
        naraz i nie może generować N+1 (CLAUDE.md §4: moduł→moduł przez serwis).

        `include_archived=True` służy WYŁĄCZNIE sprowadzeniu pozycji spiżarni do
        produktu kanonicznego: wariant zarchiwizowany nadal opisuje to, co leży
        w domu, ale silnik go nie proponuje jako opakowania do kupienia
        (ADR-012, karta B10 §Context pkt 1).

        Kolejność jest ustalona (wielkość opakowania, potem id) — wynik silnika
        nie może zależeć od planu zapytania (ADR-008).
        """
        unique_ids = sorted(set(product_ids))
        if not unique_ids:
            return {}

        statement = select(RetailProduct).where(RetailProduct.canonical_product_id.in_(unique_ids))
        if not include_archived:
            statement = statement.where(RetailProduct.is_archived.is_(False))
        rows = (
            (
                await self._session.execute(
                    statement.order_by(
                        RetailProduct.canonical_product_id,
                        RetailProduct.package_amount,
                        RetailProduct.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[int, list[RetailProduct]] = {product_id: [] for product_id in unique_ids}
        for row in rows:
            grouped[row.canonical_product_id].append(row)
        return grouped

    async def variants_by_ids(self, retail_ids: Sequence[int]) -> dict[int, RetailProduct]:
        """Warianty po identyfikatorach — także archiwalne (zbiorczy odczyt dla B10).

        Silnik zakupowy potrzebuje tego, żeby sprowadzić pozycję SPIŻARNI opisaną
        wariantem sklepowym do produktu kanonicznego: taka pozycja opisuje realną
        zawartość szafki, nawet gdy wariant zdjęto już z półki.
        """
        unique_ids = sorted(set(retail_ids))
        if not unique_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    select(RetailProduct).where(RetailProduct.id.in_(unique_ids))
                )
            )
            .scalars()
            .all()
        )
        return {row.id: row for row in rows}

    # --- zapis ---------------------------------------------------------------------

    async def create_retail_product(
        self,
        *,
        actor: User,
        canonical_product_id: int,
        name: str,
        brand: str | None,
        store_id: int | None,
        package_amount: Decimal,
        package_unit: AmountUnit,
        pieces_per_package: int | None,
    ) -> RetailProductView:
        """Nowy wariant sklepowy. Tworzy go USER (02_DOMAIN §3.1 pkt 4)."""
        product = await self._require_product(canonical_product_id)
        await self._require_store(store_id)
        _assert_package_unit(product, package_unit)

        retail = RetailProduct(
            canonical_product_id=canonical_product_id,
            name=name,
            brand=brand,
            store_id=store_id,
            package_amount=package_amount,
            package_unit=package_unit,
            pieces_per_package=pieces_per_package,
        )
        self._session.add(retail)
        await self._session.commit()
        return await self.retail_view(retail.id)

    async def update_retail_product(
        self, retail_id: int, *, actor: User, changes: Mapping[str, Any]
    ) -> RetailProductView:
        """Częściowa edycja wariantu (USER). Jednostkę sprawdzamy po zmianie."""
        retail = await self.get_retail_product(retail_id)
        product = await self._require_product(retail.canonical_product_id)
        if "store_id" in changes:
            await self._require_store(changes["store_id"])

        for field in EDITABLE_FIELDS:
            if field in changes:
                setattr(retail, field, changes[field])
        # Stan KOŃCOWY, nie samo żądanie: PATCH może w ogóle nie ruszyć jednostki,
        # a ona i tak musi zostać zgodna z osią produktu kanonicznego.
        _assert_package_unit(product, retail.package_unit)

        await self._session.commit()
        return await self.retail_view(retail_id)

    async def delete_retail_product(self, retail_id: int, *, actor: User) -> None:
        """Fizyczne usunięcie — wyłącznie nieużywanego wariantu (ADR-012).

        Zdjęcie kasujemy PO udanym commicie: plik usunięty przed rollbackiem
        zostawiłby wiersz wskazujący nieistniejący obraz.
        """
        retail = await self.get_retail_product(retail_id)
        assert_deletable(RETAIL_IN_USE, await self.retail_references(retail_id))
        photo_path = retail.photo_path

        await self._session.execute(delete(RetailProduct).where(RetailProduct.id == retail_id))
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Druga linia obrony: konsument, który nie zarejestrował licznika
            # (B11). Bez tego użytkownik dostałby 500 zamiast 409.
            await self._session.rollback()
            raise conflict_from_integrity_error(RETAIL_IN_USE) from exc

        if photo_path:
            await run_in_threadpool(delete_image, photo_path, uploads_root=self._uploads_root)

    async def retail_references(self, retail_id: int) -> list[UsedInRef]:
        """Gdzie wariant jest używany — suma odpowiedzi zarejestrowanych konsumentów."""
        references: list[UsedInRef] = []
        for finder in _RETAIL_REFERENCE_FINDERS:
            references.extend(await finder(self._session, retail_id))
        return references[:USED_IN_LIMIT]

    # --- zdjęcie --------------------------------------------------------------------

    async def set_photo(self, retail_id: int, *, actor: User, data: bytes) -> RetailProductView:
        """Upload zdjęcia opakowania (pipeline 07_SECURITY §6, infrastruktura B05)."""
        retail = await self.get_retail_product(retail_id)

        # Pillow jest CPU-bound — poza pętlą zdarzeń (ADR-015).
        saved = await run_in_threadpool(
            save_image, data, uploads_root=self._uploads_root, subdir=PHOTO_SUBDIR
        )
        previous = retail.photo_path
        retail.photo_path = saved.path
        await self._session.commit()

        if previous:
            await run_in_threadpool(delete_image, previous, uploads_root=self._uploads_root)
        return await self.retail_view(retail_id)

    async def delete_photo(self, retail_id: int, *, actor: User) -> RetailProductView:
        """Usunięcie zdjęcia; wariant bez zdjęcia → 404 (nie ma czego usuwać)."""
        retail = await self.get_retail_product(retail_id)
        if not retail.photo_path:
            raise NotFoundError(NO_PHOTO_MESSAGE)

        path = retail.photo_path
        retail.photo_path = None
        await self._session.commit()
        await run_in_threadpool(delete_image, path, uploads_root=self._uploads_root)
        return await self.retail_view(retail_id)

    # --- pomocnicze ------------------------------------------------------------------

    @staticmethod
    def _view_statement() -> Select[tuple[RetailProduct, CanonicalProduct, Store]]:
        """Wariant + produkt (INNER, bo wymagany) + sklep (OUTER, bo opcjonalny).

        Typ mówi `Store`, ale kolumna sklepu jest z LEFT JOIN, więc w wierszu
        bywa `None` — SQLAlchemy nie ma jak tego wyrazić w adnotacji `Select`.
        Dlatego konsumenci pakują wynik w `RetailProductView`, gdzie pole jest
        jawnie `Store | None`.
        """
        return (
            select(RetailProduct, CanonicalProduct, Store)
            .join(CanonicalProduct, RetailProduct.canonical_product_id == CanonicalProduct.id)
            .outerjoin(Store, RetailProduct.store_id == Store.id)
        )

    async def _require_product(self, product_id: int) -> CanonicalProduct:
        """Produkt kanoniczny wariantu; brak → 422, nie 404.

        Z punktu widzenia API to błąd DANYCH WEJŚCIOWYCH (wskazano produkt,
        którego nie ma), a nie brak adresowanego zasobu — tak samo traktuje to
        spiżarnia (B08) i składniki przepisu (B05).
        """
        product = (
            await self._session.execute(
                select(CanonicalProduct).where(CanonicalProduct.id == product_id)
            )
        ).scalar_one_or_none()
        if product is None:
            raise RetailValidationError(CANONICAL_REQUIRED)
        return product

    async def _require_store(self, store_id: int | None) -> None:
        """Sklep jest opcjonalny, ale wskazany MUSI istnieć (422)."""
        if store_id is None:
            return
        exists = (
            await self._session.execute(select(Store.id).where(Store.id == store_id))
        ).scalar_one_or_none()
        if exists is None:
            raise RetailValidationError(STORE_NOT_AVAILABLE)


def _assert_package_unit(product: CanonicalProduct, package_unit: AmountUnit) -> None:
    """Jednostka opakowania musi leżeć na osi produktu kanonicznego (ADR-005).

    Opakowanie „400 ml" produktu liczonego na wagę nie jest literówką, tylko
    ilością, której nikt później nie przeliczy: ml → g wymagałoby gęstości,
    której w modelu nie ma i nie będzie (02_DOMAIN §13.1).
    """
    expected = base_unit(product.measure_kind)
    if package_unit is not expected:
        raise RetailValidationError(
            f"Opakowanie produktu „{product.name}” podaje się w {_UNIT_LABELS[expected]} — "
            "tak liczy się ten produkt kanoniczny. Zmień jednostkę opakowania."
        )


async def _retail_using_product(session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
    """Licznik referencji dla katalogu: warianty sklepowe tego produktu (ADR-012).

    Bez tego `DELETE /products/{id}` kończyłby się 409 bez listy „Używane w:" —
    poprawnym dzięki FK RESTRICT, ale nieczytelnym (06_UIUX §3.3).
    """
    rows = (
        await session.execute(
            select(RetailProduct.id, RetailProduct.name)
            .where(RetailProduct.canonical_product_id == product_id)
            .order_by(RetailProduct.name, RetailProduct.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="retail_product", id=int(row[0]), name=str(row[1])) for row in rows]


# Rejestracja przy imporcie modułu — jak w recipes (B05) i pantry (B08): każdy
# proces budujący aplikację ma licznik wpięty automatycznie.
register_product_reference_finder(_retail_using_product)
