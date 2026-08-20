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
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.scope import ScopedMixin, scope_check_constraint
from app.modules.catalog.units import AmountUnit
from app.modules.recipes.models import AMOUNT_UNIT_ENUM

__all__ = ["PlanDay", "PlanItemServing", "PlanMeal", "PlanMealItem"]

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
