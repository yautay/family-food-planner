"""Model spiżarni: `pantry_items` (schemat wiążący: 03_DATABASE §7).

Spiżarnia jest STANEM domowym, nie dokumentem: jeden wiersz = „mamy w domu tyle
a tyle tego produktu". Stąd trzy decyzje widoczne w schemacie:

1. **Zawsze household** (02_DOMAIN §3.1 pkt 1) — kolumny `scope` nie ma,
   widoczność wynika z `household_id`. Użytkownik bez rodziny ma spiżarnię
   osobistą (`household_id IS NULL`, wiersz wisi na `owner_user_id`), dlatego
   model używa `HouseholdScopedMixin`, a nie `ScopedMixin`.
2. **Ilość zawsze na osi produktu** (`amount` + `amount_unit` ∈ g|ml|szt.,
   niezmiennik 02_DOMAIN §13.1). Wyzerowanie to `amount = 0`, a NIE usunięcie
   wiersza — „skończyła się mąka" to wciąż wiedza o spiżarni.
3. **Produkt kanoniczny albo sklepowy** — CHECK pilnuje, że pozycja wskazuje
   przynajmniej jeden z nich.

`retail_product_id` powstało w migracji `0010` BEZ constraintu FK (tabela
`retail_products` doszła dopiero w BATCH_09) i constraint dopięła migracja
`0011` — ale model o tym nie wiedział jeszcze przez dwa batche, więc `alembic
check` widział „removed foreign key" i następny autogenerate SKASOWAŁBY ten
constraint. Ustalenie REVIEW R3: kolumna, której FK dopina późniejsza migracja,
musi dostać `ForeignKey` w modelu w TYM SAMYM commicie co migracja — inaczej
dryf modelu żyje cicho, bo `task check` bada tylko liczbę głów, nie zgodność
metadanych ze schematem.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.core.scope import HouseholdScopedMixin
from app.modules.catalog.units import AmountUnit
from app.modules.recipes.models import AMOUNT_UNIT_ENUM

__all__ = ["PantryItem"]


class PantryItem(TimestampMixin, HouseholdScopedMixin, Base):
    """Pozycja spiżarni (02_DOMAIN §8). PK i kolumny właścicielskie daje mixin."""

    __tablename__ = "pantry_items"
    __table_args__ = (
        CheckConstraint(
            "product_id IS NOT NULL OR retail_product_id IS NOT NULL",
            name="product_required",
        ),
        # Nieujemność świadomie NIE jest CHECK-iem: 03_DATABASE §7 go nie
        # definiuje, a schemat bazy jest wiążący (karta B08, nota 3). Pilnują
        # jej schemat Pydantic i serwis.
    )

    #: RESTRICT: produkt użyty w spiżarni nie znika (ADR-012, 02_DOMAIN §13.4).
    #: Licznik referencji rejestruje `pantry/service.py`, żeby 409 miało listę.
    product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: RESTRICT jak przy produkcie kanonicznym: wariant sklepowy leżący
    #: w spiżarni nie znika (constraint dopięła migracja `0011`, B09).
    retail_product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("retail_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=3), nullable=False)
    amount_unit: Mapped[AmountUnit] = mapped_column(AMOUNT_UNIT_ENUM, nullable=False)
    #: Opcjonalna — wiele produktów sypkich nie ma sensownej daty w domu.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    #: Wolny tekst z podpowiedziami w UI (szafka/lodówka/zamrażarka) — słownika
    #: lokalizacji świadomie NIE ma (karta B08, Out of Scope).
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
