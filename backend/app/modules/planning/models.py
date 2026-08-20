"""Modele modułu planning: dzień planu, posiłki, pozycje i rozkład rodzinny.

Schemat wiążący: 03_DATABASE §6. `plan_days` to encja ze scope (ADR-006) —
kolumny wzorca i PK dostarcza `ScopedMixin`, widoczność egzekwuje wyłącznie
`ScopedQuery` w serwisie. Typ enumowy `entity_scope` istnieje od migracji `0006`
(recipes), więc modele i migracja tego batcha go REUŻYWAJĄ (`create_type=False`);
to samo dotyczy `amount_unit`.

Struktura jest kompozycją: dzień → posiłki → pozycje → rozkład rodzinny.
Każdy poziom w dół ma FK `ON DELETE CASCADE` (dziecko bez rodzica nie znaczy nic),
a odwołania na zewnątrz (`recipe_id`, `product_id`) mają RESTRICT — przepisu ani
produktu użytego w planie nie da się usunąć (02_DOMAIN §13.4, ADR-012).

Wartości odżywcze NIE mają tu żadnej kolumny i mieć nie będą: liczy je silnik
przy każdym odczycie (niezmiennik 02_DOMAIN §13.2), dzięki czemu zmiana mnożnika
porcji zmienia wszystko spójnie (§13.3).

Szablony i cykle (BATCH_07, 03_DATABASE §6) siedzą w tym samym module, bo ich
jedyną treścią jest struktura planu: `day_templates`/`week_templates` trzymają
ZAMROŻONĄ kopię struktury w `payload JSONB` (bez dat), a `week_cycles` — samą
kolejność szablonów. Szablon nie jest edytowalny relacyjnie: PUT nadpisuje cały
payload (03_DATABASE §6). Referencje `recipe_id`/`product_id` żyją WEWNĄTRZ
payloadu, więc baza nie ma na nie FK — blokadę usuwania liczy serwis zapytaniem
po indeksie GIN (ADR-012), a nie RESTRICT.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.scope import ScopedMixin, scope_check_constraint
from app.modules.catalog.units import AmountUnit
from app.modules.recipes.models import AMOUNT_UNIT_ENUM

__all__ = [
    "PAYLOAD_GIN_OPS",
    "DayTemplate",
    "PlanDay",
    "PlanItemServing",
    "PlanMeal",
    "PlanMealItem",
    "WeekCycle",
    "WeekTemplate",
]

#: Pozycja pozycji/posiłku na liście — porządek ustala użytkownik, nie baza.
_POSITION_DEFAULT = 0


class PlanDay(TimestampMixin, ScopedMixin, Base):
    """Dzień planu: data + właściciel/scope, dowolna liczba posiłków (02_DOMAIN §7)."""

    __tablename__ = "plan_days"
    __table_args__ = (
        # Własne __table_args__ MUSZĄ zawierać CHECK-a wzorca scope (karta B06).
        scope_check_constraint(),
        # Jeden dzień planu na użytkownika i datę (03_DATABASE §6) — próba
        # utworzenia drugiego kończy się 409, nie drugim równoległym planem.
        UniqueConstraint("owner_user_id", "day", name="uq_plan_days_owner_user_id_day"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Kolekcja istnieje dla konfiguracji kaskad, NIE do odczytu w warstwie HTTP
    # (lekcja z BATCH_03: leniwa relacja tknięta poza greenletem = 500).
    meals: Mapped[list[PlanMeal]] = relationship(back_populates="day", passive_deletes=True)


class PlanMeal(TimestampMixin, Base):
    """Posiłek dnia — nazwa własna („II śniadanie"), pozycja i opcjonalny cel kcal."""

    __tablename__ = "plan_meals"
    __table_args__ = (
        CheckConstraint("kcal_target IS NULL OR kcal_target > 0", name="kcal_target_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("plan_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_POSITION_DEFAULT, server_default="0"
    )
    kcal_target: Mapped[Decimal | None] = mapped_column(Numeric(6, 0), nullable=True)

    day: Mapped[PlanDay] = relationship(back_populates="meals")
    items: Mapped[list[PlanMealItem]] = relationship(back_populates="meal", passive_deletes=True)


class PlanMealItem(TimestampMixin, Base):
    """Pozycja posiłku: przepis z mnożnikiem porcji ALBO produkt luzem z ilością.

    CHECK pilnuje, że dokładnie jedno z `recipe_id`/`product_id` jest wypełnione —
    „pozycja bez treści" i „pozycja o dwóch treściach" to stany, których silnik
    nie umiałby policzyć, więc nie wolno ich zapisać (03_DATABASE §6).
    """

    __tablename__ = "plan_meal_items"
    __table_args__ = (
        CheckConstraint(
            "(recipe_id IS NOT NULL) <> (product_id IS NOT NULL)",
            name="recipe_xor_product",
        ),
        # Produkt luzem MUSI mieć ilość ze znormalizowaną jednostką (02_DOMAIN §13.1);
        # pozycja z przepisem ilości nie ma — jej „ilością" jest mnożnik porcji.
        CheckConstraint(
            "(product_id IS NULL AND amount IS NULL AND amount_unit IS NULL) "
            "OR (product_id IS NOT NULL AND amount IS NOT NULL AND amount_unit IS NOT NULL)",
            name="product_requires_amount",
        ),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount_positive"),
        CheckConstraint("servings > 0", name="servings_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    plan_meal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("plan_meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: RESTRICT: przepis użyty w planie nie może zniknąć (409 z listą „Używane w:").
    recipe_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("recipes.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: RESTRICT: to samo dla produktu luzem (02_DOMAIN §13.4).
    product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    amount_unit: Mapped[AmountUnit | None] = mapped_column(AMOUNT_UNIT_ENUM, nullable=True)
    #: Mnożnik porcji (02_DOMAIN §7). Przy rozkładzie rodzinnym = suma multiplierów.
    servings: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=Decimal("1.00"), server_default=text("1.0")
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=_POSITION_DEFAULT, server_default="0"
    )

    meal: Mapped[PlanMeal] = relationship(back_populates="items")
    servings_split: Mapped[list[PlanItemServing]] = relationship(
        back_populates="item", passive_deletes=True
    )


class PlanItemServing(TimestampMixin, Base):
    """Rozkład rodzinny pozycji: ile porcji zjada dany profil członka rodziny.

    Suma multiplierów musi równać się `servings` pozycji. Pilnuje tego SERWIS
    przy zapisie, nie constraint (03_DATABASE §6): baza nie widzi całej kolekcji
    w momencie pojedynczego INSERT-u, więc CHECK byłby złudzeniem gwarancji.
    """

    __tablename__ = "plan_item_servings"
    __table_args__ = (
        UniqueConstraint(
            "plan_meal_item_id",
            "member_profile_id",
            name="uq_plan_item_servings_plan_meal_item_id_member_profile_id",
        ),
        CheckConstraint("multiplier > 0", name="multiplier_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    plan_meal_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("plan_meal_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: CASCADE: rozkład bez profilu nie ma sensu — znika razem z osobą przy stole.
    member_profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("member_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)

    item: Mapped[PlanMealItem] = relationship(back_populates="servings_split")


# --- szablony i cykle (BATCH_07, 03_DATABASE §6) -------------------------------------

#: Klasa operatorów GIN dla payloadów szablonów (ADR-012). `jsonb_path_ops` jest
#: mniejszy i szybszy od domyślnego `jsonb_ops`, ale obsługuje WYŁĄCZNIE operatory
#: `@>`, `@?` i `@@` — dlatego zliczanie referencji MUSI używać containmentu `@>`,
#: a nie `?`/`->`. Wybór jest wiążący dla serwisu: zmiana operatora bez zmiany tej
#: klasy cicho zdegraduje zapytanie do seq scanu.
PAYLOAD_GIN_OPS = "jsonb_path_ops"


class DayTemplate(TimestampMixin, ScopedMixin, Base):
    """Szablon dnia: nazwa + zamrożona struktura posiłków w `payload` (02_DOMAIN §7).

    Payload NIE ma dat — szablon jest przepisem na dzień, nie dniem. Kształt
    pilnuje Pydantic (`DayTemplatePayload`, wersja `v:1`); baza widzi tylko JSONB,
    bo szablon nadpisywany jest całością i nie ma po nim zapytań strukturalnych
    poza zliczaniem referencji.
    """

    __tablename__ = "day_templates"
    __table_args__ = (
        # Własne __table_args__ MUSZĄ zawierać CHECK-a wzorca scope (03_DATABASE §4).
        scope_check_constraint(),
        Index(
            "ix_day_templates_payload_gin",
            "payload",
            postgresql_using="gin",
            postgresql_ops={"payload": PAYLOAD_GIN_OPS},
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class WeekTemplate(TimestampMixin, ScopedMixin, Base):
    """Szablon tygodnia: `payload` z listą dni po offsetach 0-6 (02_DOMAIN §7).

    Każdy dzień w payloadzie ma dokładnie ten sam kształt, co payload szablonu
    dnia — jeden kontrakt zamiast dwóch, więc instancjacja tygodnia to siedem
    razy ta sama operacja co instancjacja dnia.
    """

    __tablename__ = "week_templates"
    __table_args__ = (
        scope_check_constraint(),
        Index(
            "ix_week_templates_payload_gin",
            "payload",
            postgresql_using="gin",
            postgresql_ops={"payload": PAYLOAD_GIN_OPS},
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class WeekCycle(TimestampMixin, ScopedMixin, Base):
    """Cykl tygodni A→B→C: uporządkowana lista szablonów tygodnia + start rotacji.

    `template_ids` jest TABLICĄ bez FK (03_DATABASE §6) — Postgres nie potrafi
    postawić klucza obcego na elemencie tablicy. Spójności pilnuje serwis:
    usunięcie szablonu użytego w cyklu kończy się 409 z nazwą cyklu w `used_in`,
    a `apply` odrzuca cykl wskazujący na nieistniejący szablon.

    `start_date` wyznacza, od którego szablonu startuje rotacja dla danego
    tygodnia; `NULL` znaczy „od pierwszego z listy".
    """

    __tablename__ = "week_cycles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Kolejność ma znaczenie — to ona jest rotacją A→B→C→A.
    template_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
