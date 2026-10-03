"""Modele modułu shopping (schemat wiążący: 03_DATABASE §8).

Cztery tabele, trzy różne role:

1. `shopping_round_configs` — KONFIGURACJA tur zakupowych rodziny (02_DOMAIN §9.2).
   Encja ze scope, bo tury są ustaleniem domowym, a nie słownikiem globalnym.
   Preset „Niedziela/Środa" powstaje jako DANE przy pierwszym użyciu (serwis),
   nie jako hardcode w silniku — użytkownik ma go móc zmienić.
2. `shopping_generations` — jedna próba wygenerowania zakupów. `params JSONB`
   trzyma PEŁNE wejście silnika (03_DATABASE §8), więc preview odtwarza się
   deterministycznie z bazy, a nie z ponownego odpytywania planu. To jest
   jedyne źródło prawdy o preview — osobnych tabel „pozycji preview" NIE MA
   (karta B10, Implementation Notes pkt 3).
3. `shopping_lists` + `shopping_list_items` — WYNIK finalizacji: po jednej
   liście na turę. Kolumny tokenów publicznych (`public_token`,
   `token_revoked`) powstają już tutaj, ale konsumuje je BATCH_11 — żaden
   endpoint tego batcha ich nie wystawia ani nie generuje (karta §Security).

Kierunki FK wynikają z ADR-012: kompozycja rodzic→dziecko kasuje się kaskadą
(`generation → lists → items`), a odwołania na zewnątrz (produkt, wariant
sklepowy, kategoria) mają RESTRICT — encji użytej na liście nie da się usunąć.
Wyjątek: `shopping_lists.store_id` ma SET NULL, bo lista bez profilu sklepu
jest poprawna (03_DATABASE §8); czytelną 409-kę daje licznik referencji
zarejestrowany w `shopping/service.py`.

Typy enumowe `entity_scope` (migracja `0006`) i `amount_unit` (`0006`) są tu
WYŁĄCZNIE referencją (`create_type=False`); własne typy tego batcha to
`shopping_round_mode` i `shopping_generation_status`. `RoundMode` mieszka
w `engine.py`, bo należy do logiki podziału na tury — model tylko odwzorowuje
go w typie PG (tak samo jak `AmountUnit` z `catalog/units.py`).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.scope import ScopedMixin, no_global_scope_check_constraint, scope_check_constraint
from app.modules.catalog.units import AmountUnit
from app.modules.recipes.models import AMOUNT_UNIT_ENUM
from app.modules.shopping.engine import RoundMode

__all__ = [
    "GENERATION_STATUS_ENUM",
    "ROUND_MODE_ENUM",
    "GenerationStatus",
    "RoundMode",
    "ShoppingGeneration",
    "ShoppingList",
    "ShoppingListItem",
    "ShoppingRoundConfig",
]


class GenerationStatus(StrEnum):
    """Cykl życia generacji: preview → final albo discarded (04_API §2).

    `DISCARDED` jest stanem, a nie usunięciem wiersza: historia generacji to
    wartość (D10), a `params` bywa wejściem statystyk (B13).
    """

    PREVIEW = "preview"
    FINAL = "final"
    DISCARDED = "discarded"


def _pg_enum(enum: type[StrEnum], name: str) -> postgresql.ENUM:
    """Typ enumowy PG z wartościami (nie nazwami) składowych — jak w catalogu."""
    return postgresql.ENUM(
        enum, name=name, values_callable=lambda members: [member.value for member in members]
    )


#: Typy enumowe tego batcha — jedna definicja nazw dla modeli i migracji `0012`.
ROUND_MODE_ENUM = _pg_enum(RoundMode, "shopping_round_mode")
GENERATION_STATUS_ENUM = _pg_enum(GenerationStatus, "shopping_generation_status")


class ShoppingRoundConfig(TimestampMixin, ScopedMixin, Base):
    """Jedna tura zakupowa w konfiguracji rodziny (02_DOMAIN §9.2).

    `shopping_weekday` używa konwencji `date.weekday()` (0 = poniedziałek,
    6 = niedziela) i jest informacją O HARMONOGRAMIE — podział zapotrzebowania
    liczy silnik z okien `covers_days`/`fresh_days`, a nie z dnia tygodnia.
    """

    __tablename__ = "shopping_round_configs"
    __table_args__ = (
        # Własne `__table_args__` MUSZĄ nieść CHECK-a wzorca scope (03_DATABASE §4).
        scope_check_constraint(),
        no_global_scope_check_constraint(),
        CheckConstraint(
            "shopping_weekday IS NULL OR (shopping_weekday >= 0 AND shopping_weekday <= 6)",
            name="shopping_weekday_in_week",
        ),
        CheckConstraint("covers_days > 0", name="covers_days_positive"),
        CheckConstraint("fresh_days IS NULL OR fresh_days > 0", name="fresh_days_positive"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: `NULL` = tura bez ustalonego dnia (kupuję, kiedy wypadnie).
    shopping_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    covers_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Tylko dla `DURABLE_PLUS_FRESH_WINDOW`: na ile dni kupujemy świeże.
    fresh_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[RoundMode] = mapped_column(ROUND_MODE_ENUM, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class ShoppingGeneration(TimestampMixin, ScopedMixin, Base):
    """Jedna generacja zakupów: zakres, decyzja o spiżarni i pełne wejście silnika.

    `params` NIE jest kopią wyniku — to WEJŚCIE (plan, produkty, spiżarnia,
    warianty, tury, decyzje użytkownika). Preview liczy się z niego przy każdym
    odczycie, więc `GET` i `resolve` idą tą samą ścieżką co `generate`
    (karta B10, Implementation Notes pkt 3).
    """

    __tablename__ = "shopping_generations"
    __table_args__ = (
        scope_check_constraint(),
        no_global_scope_check_constraint(),
        CheckConstraint("date_from <= date_to", name="date_range_ordered"),
    )

    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    #: Odpowiedź na JAWNE pytanie „Uwzględnić stan domowy?" (02_DOMAIN §8).
    used_pantry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[GenerationStatus] = mapped_column(
        GENERATION_STATUS_ENUM,
        nullable=False,
        default=GenerationStatus.PREVIEW,
        server_default=GenerationStatus.PREVIEW.value,
    )

    lists: Mapped[list[ShoppingList]] = relationship(
        back_populates="generation", passive_deletes=True
    )


class ShoppingList(TimestampMixin, ScopedMixin, Base):
    """Lista zakupowa jednej tury (02_DOMAIN §9.4).

    `generation_id` jest NULLABLE, bo lista ma prawo istnieć bez generacji
    (ręczna lista w B11), ale utworzona z generacji ginie razem z nią (CASCADE).
    """

    __tablename__ = "shopping_lists"
    __table_args__ = (
        scope_check_constraint(),
        no_global_scope_check_constraint(),
        UniqueConstraint("public_token", name="uq_shopping_lists_public_token"),
    )

    generation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("shopping_generations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Nazwa tury, z której lista powstała („Niedziela") — tekst, nie FK: lista
    #: historyczna nie może zmienić treści po edycji konfiguracji tur.
    round_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: SET NULL: lista bez sklepu jest poprawna, sortowanie wraca do domyślnego.
    store_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: 43 znaki base64url (256 bitów) — tworzy i konsumuje BATCH_11 (ADR-010).
    public_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    generation: Mapped[ShoppingGeneration | None] = relationship(back_populates="lists")
    items: Mapped[list[ShoppingListItem]] = relationship(
        back_populates="shopping_list", passive_deletes=True
    )


class ShoppingListItem(TimestampMixin, Base):
    """Pozycja listy zakupowej — gotowa do renderu także offline (ADR-009).

    `label` jest ŚWIADOMĄ denormalizacją: offline (B12) nie ma dostępu do
    katalogu, więc pozycja musi umieć się pokazać sama. Semantyki tej kolumny
    nie wolno zmieniać (karta B10, Cross-Batch Impact).

    Ilości: `needed_amount` to POTRZEBA po odjęciu spiżarni, `package_size` i
    `packages_count` opisują wybrany wariant sklepowy, a `leftover_amount`
    resztkę (kupione - potrzeba), którą UI eksponuje zawsze (02_DOMAIN §9.3).
    """

    __tablename__ = "shopping_list_items"
    __table_args__ = (
        CheckConstraint("needed_amount >= 0", name="needed_amount_not_negative"),
        CheckConstraint("packages_count IS NULL OR packages_count > 0", name="packages_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    list_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: RESTRICT: kategoria decyduje o miejscu pozycji na liście, także po latach.
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: RESTRICT: produkt użyty na liście nie znika (02_DOMAIN §13.4).
    product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: RESTRICT: licznik referencji rejestruje `shopping/service.py` (karta B09).
    retail_product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("retail_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    needed_amount: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    amount_unit: Mapped[AmountUnit] = mapped_column(AMOUNT_UNIT_ENUM, nullable=False)
    packages_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    package_size: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    leftover_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    #: Decyzja użytkownika „mam już w domu" — pozycja zostaje widoczna (02_DOMAIN §9.1).
    already_have: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: Ile odjęto ze spiżarni (`NULL` = nie pytaliśmy o stan domowy).
    from_pantry_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    checked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Moment przyjęcia TEJ pozycji do spiżarni; `NULL` = jeszcze nieprzyjęta (D19).
    #: Bez tego znacznika `accept_to_pantry` nie jest idempotentne, a ponowienie
    #: żądania z kolejki offline (ADR-009) dolewa zakupy DRUGI raz — po cichu.
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")
