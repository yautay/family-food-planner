"""Logika spiżarni: jedyne miejsce I/O modułu pantry (01_ARCHITECTURE §2).

Spiżarnia jest wyłącznie STANEM domowym. Ten moduł niczego od niczego nie
odejmuje — pytanie „Uwzględnić stan domowy?" i odejmowanie należą do silnika
zakupowego (BATCH_10), a przyjęcie zakupów do BATCH_11 (02_DOMAIN §8). Jedyne
wyjście dla tamtych batchy to `PantryService.get_household_state()`.

Widoczność egzekwuje `HouseholdScopedQuery` (`core/scope.py`), nie własny filtr:
pozycja z cudzej rodziny to 404, identycznie jak nieistniejąca (07_SECURITY §4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deletion import USED_IN_LIMIT, UsedInRef
from app.core.errors import AppError
from app.core.scope import HouseholdScopedQuery
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, ProductCategory, RetailProduct
from app.modules.catalog.retail_service import register_retail_reference_finder
from app.modules.catalog.service import register_product_reference_finder
from app.modules.catalog.units import AmountUnit, base_unit
from app.modules.pantry.models import PantryItem
from app.modules.pantry.schemas import PantryItemCreateRequest, PantrySort

__all__ = [
    "PantryItemView",
    "PantryReceipt",
    "PantryService",
    "PantryStateItem",
    "PantryValidationError",
]

PANTRY_ITEM_NOT_FOUND = "Nie znaleziono tej pozycji spiżarni."
PRODUCT_NOT_AVAILABLE = "Nie znaleziono produktu, który chcesz dodać do spiżarni."

#: Pola, które PATCH wolno podmienić. Jednostki nie ma na liście świadomie:
#: oś ilości należy do produktu, więc jej zmiana byłaby cichym przeliczeniem.
EDITABLE_FIELDS = ("amount", "expiry_date", "location", "note")

_PANTRY = HouseholdScopedQuery(PantryItem, not_found_message=PANTRY_ITEM_NOT_FOUND)


class PantryValidationError(AppError):
    """Dane pozycji nie trzymają się reguł domeny (produkt, jednostka).

    Nie `RequestValidationError`: te reguły zależą od produktu wskazanego
    w żądaniu, a nie od kształtu pojedynczego pola.
    """

    status_code = 422
    code = "validation_error"


@dataclass(frozen=True)
class PantryItemView:
    """Pozycja razem z tym, co warstwa HTTP musi o niej wiedzieć.

    Produkt i kategoria bywają `None`: pozycja może w przyszłości wskazywać
    wyłącznie produkt sklepowy (BATCH_09), a CHECK w bazie dopuszcza taki wiersz.
    """

    item: PantryItem
    product: CanonicalProduct | None
    category: ProductCategory | None


@dataclass(frozen=True)
class PantryReceipt:
    """Wynik przyjęcia zakupów: pozycja + czy DOLANO do istniejącej partii.

    Rozróżnienie jest dla użytkownika, nie dla kodu: „dodano 3 pozycje,
    zwiększono 2" mówi mu, że spiżarnia nie rozsypała się na duplikaty.
    """

    item: PantryItem
    merged: bool


@dataclass(frozen=True)
class PantryStateItem:
    """Stan domowy jednej pozycji — KONTRAKT dla silnika zakupowego (B10) i B11.

    Ilość jest już znormalizowana na oś produktu (g/ml/szt.), więc konsument
    niczego nie przelicza; agregacja per produkt należy do niego, bo to on wie,
    czy sumuje po produkcie kanonicznym, czy po sklepowym.
    """

    item_id: int
    product_id: int | None
    retail_product_id: int | None
    amount: Decimal
    amount_unit: AmountUnit
    expiry_date: date | None


class PantryService:
    """Operacje na spiżarni. Jedyne miejsce I/O tego modułu."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- odczyt -----------------------------------------------------------------

    async def list_items(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        today: date,
        query: str | None = None,
        category_id: int | None = None,
        sort: PantrySort = PantrySort.EXPIRY,
        expires_within_days: int | None = None,
    ) -> tuple[list[PantryItemView], int]:
        """Lista pozycji widocznych dla użytkownika z filtrami widoku 6.

        `expires_within_days` obejmuje TAKŻE pozycje już przeterminowane —
        filtr „kończy się w ciągu N dni", który ukrywałby to, co się zepsuło
        wczoraj, pokazywałby mniej pilne zamiast bardziej pilnych.
        """
        statement = self._visible(user)
        if category_id is not None:
            statement = statement.where(CanonicalProduct.category_id == category_id)
        if expires_within_days is not None:
            statement = statement.where(
                PantryItem.expiry_date.is_not(None),
                PantryItem.expiry_date <= today + timedelta(days=expires_within_days),
            )

        phrase = (query or "").strip()
        if phrase:
            statement = statement.where(_search_condition(phrase))

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()

        rows = (
            await self._session.execute(
                statement.add_columns(CanonicalProduct, ProductCategory)
                .order_by(*_ordering(sort, phrase))
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [PantryItemView(item=row[0], product=row[1], category=row[2]) for row in rows], total

    async def get_household_state(self, user: User) -> list[PantryStateItem]:
        """Stan domowy dla silnika zakupowego (B10) i przyjęcia zakupów (B11).

        Pozycje wyzerowane (`amount = 0`) NIE wchodzą do wyniku: wiersz z zerem
        znaczy „nie mamy tego w domu", więc odjęcie go od potrzeb byłoby błędem.
        Kolejność jest deterministyczna (produkt, data, id), bo konsumentem jest
        silnik, którego wynik nie może zależeć od planu zapytania (ADR-008).

        Zakres to WŁASNY dom (`select_own_household`), a nie widoczność
        (`select_visible`): ADMIN widzi cudze spiżarnie na liście (D16), ale jego
        własne zakupy mają się odjąć od jego własnego domu, a nie od wszystkich
        rodzin w instancji.
        """
        rows = (
            (
                await self._session.execute(
                    _PANTRY.select_own_household(user)
                    .where(PantryItem.amount > 0)
                    .order_by(
                        PantryItem.product_id.asc().nulls_last(),
                        PantryItem.retail_product_id.asc().nulls_last(),
                        PantryItem.expiry_date.asc().nulls_last(),
                        PantryItem.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            PantryStateItem(
                item_id=row.id,
                product_id=row.product_id,
                retail_product_id=row.retail_product_id,
                amount=row.amount,
                amount_unit=row.amount_unit,
                expiry_date=row.expiry_date,
            )
            for row in rows
        ]

    # --- zapis ------------------------------------------------------------------

    async def create_item(self, *, actor: User, payload: PantryItemCreateRequest) -> PantryItemView:
        """Nowa pozycja spiżarni — zawsze na rodzinę autora (02_DOMAIN §3.1 pkt 1).

        Ta sama metoda obsłuży „przyjmij zakupy do spiżarni" z BATCH_11: akcja
        dokłada pozycje z odhaczonych elementów listy, nie tworzy własnego zapisu.
        """
        product = await self._product_or_422(payload.product_id)
        item = PantryItem(
            product_id=product.id,
            amount=payload.amount,
            amount_unit=self._unit_for(product, payload.amount_unit),
            expiry_date=payload.expiry_date,
            location=payload.location,
            note=payload.note,
            **HouseholdScopedQuery.ownership_for_create(actor),
        )
        self._session.add(item)
        await self._session.commit()
        return await self._view(item)

    async def receive_purchase(
        self, *, actor: User, product_id: int, amount: Decimal
    ) -> PantryReceipt:
        """Przyjęcie ZAKUPÓW do spiżarni (konsument: „przyjmij zakupy", B11).

        Reguła scalania — jawna, bo to decyzja domenowa, a nie szczegół zapisu:
        zakupy dolewamy do istniejącej pozycji tego produktu **bez daty
        ważności**, a gdy takiej nie ma, zakładamy nową. Uzasadnienie: wiersz
        z datą ważności jest KONKRETNĄ partią („ten jogurt do 12.09"), więc
        dolanie do niego świeżego zakupu skłamałoby o dacie; wiersz bez daty to
        stan luzem („mąka w szafce”) i tam nowa torba po prostu się dodaje.
        Gdy takich wierszy jest kilka (użytkownik mógł je założyć ręcznie),
        bierzemy najstarszy — wybór musi być deterministyczny.

        Zakupy nie znają daty ważności (lista zakupowa jej nie nosi), więc nowa
        pozycja powstaje bez niej i użytkownik może ją uzupełnić w spiżarni.
        Ilość jest już na osi produktu — przelicznikami zajmuje się wołający.

        Kandydata do dolania szukamy przez `select_own_household`, a NIE
        `select_visible`: dla ADMIN-a widoczność to `true()` (D16), więc
        przyjęcie zakupów dolałoby mu ilość do NAJSTARSZEJ pasującej pozycji
        w całej instancji — czyli do cudzej spiżarni. „Co mamy w domu" jest
        przynależnością, nie widocznością (ten sam powód, dla którego
        `get_household_state` używa tego samego warunku).
        """
        product = await self._product_or_422(product_id)
        existing = (
            (
                await self._session.execute(
                    _PANTRY.select_own_household(actor)
                    .where(
                        PantryItem.product_id == product.id,
                        PantryItem.expiry_date.is_(None),
                    )
                    .order_by(PantryItem.id)
                    .limit(1)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )

        if existing is not None:
            existing.amount = existing.amount + amount
            await self._session.commit()
            return PantryReceipt(item=(await self._view(existing)).item, merged=True)

        item = PantryItem(
            product_id=product.id,
            amount=amount,
            amount_unit=self._unit_for(product, None),
            **HouseholdScopedQuery.ownership_for_create(actor),
        )
        self._session.add(item)
        await self._session.commit()
        return PantryReceipt(item=(await self._view(item)).item, merged=False)

    async def update_item(
        self, item_id: int, *, actor: User, changes: Mapping[str, Any]
    ) -> PantryItemView:
        """Edycja pozycji przez DOWOLNEGO członka rodziny (02_DOMAIN §3.1 pkt 2).

        `changes` to wyłącznie pola faktycznie przysłane (`exclude_unset`) —
        inaczej nie dałoby się wyczyścić daty ważności ani lokalizacji.
        Wyzerowanie (`amount = 0`) jest zwykłą edycją: wiersz zostaje.
        """
        item = await _PANTRY.get_or_404(self._session, item_id, actor)
        for field in EDITABLE_FIELDS:
            if field in changes:
                setattr(item, field, changes[field])
        await self._session.commit()
        return await self._view(item)

    async def delete_item(self, item_id: int, *, actor: User) -> None:
        """Usunięcie pozycji: KAŻDY członek rodziny (decyzja właściciela D17).

        Świadomie BEZ `assert_can_manage`. Spiżarnia jest jednym stanem domowym,
        więc „kto dodał" jest tu informacją, a nie przywilejem: skoro członek
        rodziny może pozycję wyzerować, blokowanie mu usunięcia wiersza byłoby
        pozorną ochroną. Wyjątek od 02_DOMAIN §3.1 pkt 2 jest opisany w tamtym
        dokumencie i w macierzy 08_TESTING §4.

        Granica została bez zmian: pozycja z CUDZEJ rodziny to 404 z `get_or_404`,
        a nie 403 — obcy nie dowiaduje się nawet, że taki wiersz istnieje.
        """
        await _PANTRY.get_or_404(self._session, item_id, actor)
        await self._session.execute(delete(PantryItem).where(PantryItem.id == item_id))
        await self._session.commit()

    # --- pomocnicze -------------------------------------------------------------

    def _visible(self, user: User) -> Select[tuple[PantryItem]]:
        """Widoczne pozycje z doklejonym produktem i kategorią."""
        return _with_product(_PANTRY.select_visible(user))

    async def _view(self, item: PantryItem) -> PantryItemView:
        """Pozycja + produkt + kategoria jednym zapytaniem (bez leniwych relacji).

        `populate_existing=True` NIE jest ozdobą: sesja ma `expire_on_commit=False`,
        więc po commicie w mapie tożsamości siedzi encja z wartościami sprzed
        zapisu — `Decimal("0")` z żądania zamiast `Decimal("0.000")` z kolumny
        NUMERIC(10,3). Bez tej opcji SELECT wykonałby się, ale wynik i tak
        przyszedłby z pamięci i odpowiedź API miałaby złą skalę (złapał to
        `task check` po pierwszej próbie usunięcia `refresh`).
        """
        row = (
            await self._session.execute(
                _with_product(select(PantryItem))
                .add_columns(CanonicalProduct, ProductCategory)
                .where(PantryItem.id == item.id)
                .execution_options(populate_existing=True)
            )
        ).one()
        return PantryItemView(item=row[0], product=row[1], category=row[2])

    async def _product_or_422(self, product_id: int) -> CanonicalProduct:
        """Produkt kanoniczny albo 422 — 404 należy do zasobu, nie do jego pola."""
        product = await self._session.get(CanonicalProduct, product_id)
        if product is None:
            raise PantryValidationError(PRODUCT_NOT_AVAILABLE, details={"product_id": product_id})
        return product

    @staticmethod
    def _unit_for(product: CanonicalProduct, requested: AmountUnit | None) -> AmountUnit:
        """Oś ilości pozycji: zawsze oś produktu (ADR-005, niezmiennik 02_DOMAIN §13.1).

        Pominięta jednostka jest wygodą UI, nie furtką: podana jawnie musi się
        zgadzać z `measure_kind`, bo „3 szt." mąki nie znaczy nic policzalnego.
        """
        expected = base_unit(product.measure_kind)
        if requested is not None and requested is not expected:
            raise PantryValidationError(
                f"„{product.name}” jest mierzony w jednostce „{expected.value}”, "
                f"więc ilość w „{requested.value}” nie da się zapisać.",
                details={
                    "product_id": product.id,
                    "expected_unit": expected.value,
                    "amount_unit": requested.value,
                },
            )
        return expected


def _with_product[T: tuple[Any, ...]](statement: Select[T]) -> Select[T]:
    """Doklej produkt kanoniczny i jego kategorię — JEDNO miejsce z tymi joinami.

    LEFT, a nie INNER: pozycja wskazująca wyłącznie produkt sklepowy (BATCH_09)
    musi zostać na liście, a nie zniknąć po cichu. Kolejny join (retail po B09)
    dokłada się tutaj, więc lista i szczegół nie mogą się rozjechać.
    """
    return statement.outerjoin(
        CanonicalProduct, PantryItem.product_id == CanonicalProduct.id
    ).outerjoin(ProductCategory, CanonicalProduct.category_id == ProductCategory.id)


def _search_condition(phrase: str) -> ColumnElement[bool]:
    """Trafienie po nazwie produktu: fragment albo podobieństwo trigramowe.

    `autoescape=True` — `%` i `_` z frazy użytkownika nie działają jak
    wieloznaczniki (U14 z review R1).
    """
    threshold = get_settings().catalog_search_similarity_threshold
    return or_(
        CanonicalProduct.name.icontains(phrase, autoescape=True),
        func.similarity(CanonicalProduct.name, phrase) >= threshold,
    )


def _ordering(sort: PantrySort, phrase: str) -> tuple[Any, ...]:
    """Porządek listy; pozycje bez daty ważności ZAWSZE na końcu (widok 6).

    Przy szukaniu najpierw idą najlepsze trafienia — inaczej fraza wpisana
    w szukajkę nie miałaby wpływu na to, co widać u góry.
    """
    prefix: tuple[Any, ...] = (
        (func.similarity(CanonicalProduct.name, phrase).desc(),) if phrase else ()
    )
    if sort is PantrySort.NAME:
        return (*prefix, CanonicalProduct.name.asc().nulls_last(), PantryItem.id)
    return (
        *prefix,
        PantryItem.expiry_date.asc().nulls_last(),
        CanonicalProduct.name.asc().nulls_last(),
        PantryItem.id,
    )


async def _pantry_using_product(session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
    """Licznik referencji dla katalogu: pozycje spiżarni z tym produktem (ADR-012).

    Bez tego `DELETE /products/{id}` kończyłby się 409 bez listy „Używane w:" —
    poprawnym dzięki FK RESTRICT, ale nieczytelnym (06_UIUX §3.3).
    """
    rows = (
        await session.execute(
            select(PantryItem.id, CanonicalProduct.name)
            .join(CanonicalProduct, PantryItem.product_id == CanonicalProduct.id)
            .where(PantryItem.product_id == product_id)
            .order_by(PantryItem.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="pantry_item", id=int(row[0]), name=str(row[1])) for row in rows]


async def _pantry_using_retail_product(
    session: AsyncSession, retail_product_id: int
) -> Sequence[UsedInRef]:
    """Licznik referencji dla wariantów sklepowych (dołożony w BATCH_09).

    `pantry_items.retail_product_id` dostał constraint FK RESTRICT dopiero
    w migracji B09 (kolumna istnieje od `0010`), więc od tej chwili pozycja
    spiżarni blokuje usunięcie wariantu sklepowego — a użytkownik ma zobaczyć
    KTÓRE pozycje, nie samo „nie można" (06_UIUX §3.3).

    Nazwą jest nazwa wariantu: pozycja spiżarni własnej nazwy nie ma, a nazwa
    produktu kanonicznego bywa `NULL` dla pozycji czysto retailowej.
    """
    rows = (
        await session.execute(
            select(PantryItem.id, RetailProduct.name)
            .join(RetailProduct, PantryItem.retail_product_id == RetailProduct.id)
            .where(PantryItem.retail_product_id == retail_product_id)
            .order_by(PantryItem.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="pantry_item", id=int(row[0]), name=str(row[1])) for row in rows]


# Rejestracja przy imporcie modułu — jak w recipes (B05): każdy proces budujący
# aplikację ma licznik wpięty automatycznie.
register_product_reference_finder(_pantry_using_product)
register_retail_reference_finder(_pantry_using_retail_product)
