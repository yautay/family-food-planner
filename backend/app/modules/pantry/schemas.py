"""Schematy request/response modułu pantry (04_API §1-2).

Ilość jest w bazie NUMERIC(10,3) i w JSON wychodzi jako string dziesiętny
(`DecimalString`, ADR-008). Na wejściu przyjmujemy ją **na osi produktu**
(g/ml/szt.), a nie w dowolnej jednostce domowej — spiżarnia to stan, który
użytkownik koryguje („zostało 250 g"), a nie przepis, w którym wpisuje
„2 łyżki". Dzięki temu wyzerowanie jest zwykłym `{"amount": "0"}`, podczas gdy
`normalize_amount` z definicji odrzuca ilości ≤ 0 (02_DOMAIN §13.1).

`amount >= 0`, nigdy mniej: ujemny stan domowy nie znaczy nic, a odejmowanie
w silniku zakupowym (B10) liczyłoby wtedy nadmiar zakupów (08_TESTING §2.5).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.core.schemas import DecimalString
from app.modules.catalog.models import MeasureKind
from app.modules.catalog.units import AmountUnit

__all__ = [
    "PantryItemCreateRequest",
    "PantryItemRead",
    "PantryItemUpdateRequest",
    "PantryListResponse",
    "PantrySort",
]

#: Ilość na osi produktu — NUMERIC(10,3), nieujemna (0 = „skończyło się").
PantryAmount = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("9999999.999"), max_digits=10, decimal_places=3),
]
Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PantrySort(StrEnum):
    """Porządek listy: domyślnie po dacie ważności (widok 6, 06_UIUX §4)."""

    EXPIRY = "expiry"
    NAME = "name"


class PantryItemCreateRequest(BaseModel):
    """Nowa pozycja spiżarni.

    `amount_unit` wolno pominąć — wtedy serwis bierze oś produktu (`g`/`ml`/
    `piece` wg `measure_kind`). Podana jawnie MUSI się z nią zgadzać, inaczej
    422: produkt mierzony w masie nie ma stanu „3 sztuki".

    Produktu sklepowego jeszcze się nie wybiera (kolumna czeka na BATCH_09,
    karta B08 §Out of Scope), więc `product_id` jest tu wymagany.
    """

    product_id: int = Field(ge=1)
    amount: PantryAmount
    amount_unit: AmountUnit | None = None
    expiry_date: date | None = None
    location: Location | None = None
    note: str = Field(default="", max_length=500)


#: Pola, dla których `null` w PATCH-u znaczy „wyczyść" (kolumny NULLABLE).
#: Reszta jest NOT NULL, więc `null` to błąd wejścia, nie życzenie użytkownika.
NULLABLE_ON_UPDATE = frozenset({"expiry_date", "location"})


class PantryItemUpdateRequest(BaseModel):
    """Częściowa edycja pozycji: ilość, data ważności, lokalizacja, notatka.

    Pole POMINIĘTE zostaje bez zmian; `{"amount": "0"}` to wyzerowanie — wiersz
    zostaje w spiżarni (02_DOMAIN §8). Jednostki się nie zmienia: oś ilości
    należy do produktu, nie do pozycji.
    """

    amount: PantryAmount | None = None
    expiry_date: date | None = None
    location: Location | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> PantryItemUpdateRequest:
        """`null` wolno przysłać wyłącznie dla kolumn NULLABLE (wzorzec z B03)."""
        empty = sorted(
            field
            for field in self.model_fields_set
            if field not in NULLABLE_ON_UPDATE and getattr(self, field) is None
        )
        if empty:
            raise ValueError(f"Te pola nie mogą być puste: {', '.join(empty)}.")
        return self


class PantryItemRead(BaseModel):
    """Pozycja w odczycie — z danymi produktu, których potrzebuje widok 6.

    Świadomie BEZ `from_attributes`: `product_name`, `category_name`
    i `measure_kind` nie są kolumnami `PantryItem`, więc `model_validate(item)`
    nie miałoby z czego ich wziąć. Schemat składa router z widoku serwisu.
    """

    id: int
    product_id: int | None
    product_name: str | None
    category_id: int | None
    category_name: str | None
    measure_kind: MeasureKind | None
    retail_product_id: int | None
    amount: DecimalString
    amount_unit: AmountUnit
    expiry_date: date | None
    location: str | None
    note: str
    #: Kto dodał pozycję — UI pokazuje, że spiżarnia jest wspólna.
    owner_user_id: int
    household_id: int | None
    created_at: datetime
    updated_at: datetime


class PantryListResponse(BaseModel):
    items: list[PantryItemRead]
    total: int
