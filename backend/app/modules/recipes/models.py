"""Modele modułu recipes: przepisy, składniki, tagi i oceny.

Schemat wiążący: 03_DATABASE §5. `recipes` to PIERWSZA produkcyjna encja ze
scope (ADR-006) — kolumny wzorca i PK dostarcza `ScopedMixin`, a widoczność
egzekwuje wyłącznie `ScopedQuery` w serwisie. Migracja tego modułu tworzy typ
enumowy `entity_scope`; kolejne tabele ze scope (B06+) używają
`postgresql.ENUM(..., create_type=False)`.

Składnik przechowuje DWIE ilości (ADR-005, 02_DOMAIN §5):

- `display_qty` + `display_unit` — to, co wpisał użytkownik („2 x łyżka"),
- `amount` + `amount_unit` — ilość znormalizowana na oś produktu (g/ml/szt.),
  policzona przy zapisie przez `catalog/units.py`. Zapis składnika bez
  jednoznacznego przeliczenia jest niemożliwy (niezmiennik 02_DOMAIN §13.1),
  dlatego `amount` jest NOT NULL.

Wartości odżywcze przepisu NIE są przechowywane — zawsze wylicza je silnik
(`nutrition/engine.py`, niezmiennik 02_DOMAIN §13.2).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.scope import ScopedMixin, scope_check_constraint
from app.modules.catalog.units import AmountUnit

__all__ = [
    "AMOUNT_UNIT_ENUM",
    "Recipe",
    "RecipeIngredient",
    "RecipeRating",
    "Tag",
    "recipe_tags",
]


def _pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """Typ enumowy PG z wartościami (nie nazwami) składowych — jak w catalog."""
    return Enum(enum, name=name, values_callable=lambda members: [m.value for m in members])


#: Typy enumowe współdzielone przez modele i migrację — jedna definicja nazw.
#: `amount_unit` będzie reużyty przez planning (B06), pantry (B08) i shopping
#: (B10/11) — te migracje MUSZĄ użyć `postgresql.ENUM(..., create_type=False)`.
AMOUNT_UNIT_ENUM = _pg_enum(AmountUnit, "amount_unit")


class Recipe(TimestampMixin, ScopedMixin, Base):
    """Przepis/danie (02_DOMAIN §5). PK i kolumny scope daje `ScopedMixin`."""

    __tablename__ = "recipes"
    __table_args__ = (
        # Własne __table_args__ MUSZĄ zawierać CHECK-a wzorca scope (karta B05).
        scope_check_constraint(),
        CheckConstraint("base_servings >= 1", name="base_servings_positive"),
        CheckConstraint(
            "difficulty IS NULL OR (difficulty >= 1 AND difficulty <= 10)",
            name="difficulty_range",
        ),
        # Wyszukiwarka `?q=` toleruje literówki jak w katalogu (04_API §1);
        # RecipePicker w planie dnia (B06) wymaga szybkich odpowiedzi.
        Index(
            "ix_recipes_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Na ile porcji jest przepis — mianownik wszystkich wartości „per porcja".
    base_servings: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    prep_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Ścieżka względna na bind mount uploadów (03_DATABASE §11), nie URL.
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # Kolekcje istnieją dla konfiguracji kaskad, NIE do odczytu w warstwie HTTP
    # (lekcja z BATCH_03: leniwa relacja tknięta poza greenletem = 500).
    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe", passive_deletes=True
    )
    ratings: Mapped[list[RecipeRating]] = relationship(
        back_populates="recipe", passive_deletes=True
    )


class RecipeIngredient(TimestampMixin, Base):
    """Składnik przepisu — produkt kanoniczny + ilość wpisana i znormalizowana."""

    __tablename__ = "recipe_ingredients"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: CASCADE: składnik jest częścią przepisu, nie osobnym bytem (ADR-012).
    recipe_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: RESTRICT: produkt użyty w przepisie nie może zniknąć (02_DOMAIN §13.4).
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    display_qty: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    display_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    amount_unit: Mapped[AmountUnit] = mapped_column(AMOUNT_UNIT_ENUM, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class Tag(TimestampMixin, Base):
    """Tag przepisu — słownik globalny, płaski (02_DOMAIN §5).

    `is_system=True` mają tagi z seedu migracji (śniadanie, obiad, „ulubione"…);
    tagi użytkowe z inline create powstają z `is_system=False`.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


#: Przypisanie N:M przepis↔tag — czysta tabela asocjacyjna (03_DATABASE §5),
#: bez własnego modelu i bez timestampów (wiersz nie ma cyklu życia poza parą).
recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column(
        "recipe_id",
        BigInteger,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        BigInteger,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class RecipeRating(TimestampMixin, Base):
    """Ocena 1-5 na parę (przepis, użytkownik) — upsert, bez komentarzy."""

    __tablename__ = "recipe_ratings"
    __table_args__ = (
        UniqueConstraint("recipe_id", "user_id", name="uq_recipe_ratings_recipe_id_user_id"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: CASCADE: ocena bez autora nie znaczy nic (średnia i tak jest wyliczana).
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="ratings")
