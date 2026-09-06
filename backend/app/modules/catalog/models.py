"""Modele modułu catalog: kategorie, produkty kanoniczne, jednostki, nutrienty.

Schemat wiążący: 03_DATABASE §3. Produkty są GLOBALNE (02_DOMAIN §3.1 pkt 3) —
żadna z tych tabel NIE ma kolumn wzorca scope i nie przechodzi przez
`ScopedQuery`. Widoczność jest jedna dla całej instancji, różnicują się tylko
uprawnienia do zapisu (wartości odżywcze i weryfikacja: wyłącznie ADMIN).

Model wartości odżywczych (ADR-004) jest dwuczęściowy: rdzeń jako kolumny
`canonical_products` (typowany, walidowany CHECK-ami) i rozszerzenia jako pary
w `product_nutrient_values` ze słownikiem `nutrients`. Obie części czyta
WYŁĄCZNIE adapter `ProductNutrition` (`nutrition_adapter.py`) — silnik nutrition
nigdy nie sięga do tych kolumn bezpośrednio.

Kolumny rdzenia są NULLOWALNE, choć 03_DATABASE §3 wymieniał je bez adnotacji
NULL. Powód jest wymuszony przez sam model domenowy: USER tworzy produkt inline
z minimalnego formularza (02_DOMAIN §4.9, 06_UIUX §3.1) i nie zna kcal ani
makro — wartości uzupełnia później ADMIN. Gdyby kolumny były NOT NULL, jedyną
alternatywą byłoby wpisywanie zer, a „0 kcal" to nieprawda, nie brak danych
(ADR-004: brak wartości ⇒ wynik oznaczony jako niekompletny, nigdy zgadywany).
Dokument zaktualizowany do stanu faktycznego w BATCH_04.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.modules.catalog.units import AmountUnit, MeasureKind

__all__ = [
    "MEASURE_KIND_ENUM",
    "PACKAGE_UNIT_ENUM",
    "PERISHABILITY_ENUM",
    "VERIFICATION_STATUS_ENUM",
    "CanonicalProduct",
    "MeasureKind",
    "Nutrient",
    "Perishability",
    "ProductCategory",
    "ProductNutrientValue",
    "ProductUnitWeight",
    "RetailProduct",
    "Store",
    "StoreCategoryOrder",
    "VerificationStatus",
]


class Perishability(StrEnum):
    """Trwałość — steruje podziałem na tury zakupowe (02_DOMAIN §9.2, B10)."""

    FRESH = "fresh"
    DURABLE = "durable"


class VerificationStatus(StrEnum):
    """Cykl weryfikacji produktu (02_DOMAIN §4.9)."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"


def _pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """Typ enumowy PG z wartościami (nie nazwami) składowych — jak `USER_ROLE_ENUM`."""
    return Enum(enum, name=name, values_callable=lambda members: [m.value for m in members])


#: Typy enumowe współdzielone przez modele i migrację — jedna definicja nazw.
PERISHABILITY_ENUM = _pg_enum(Perishability, "perishability")
MEASURE_KIND_ENUM = _pg_enum(MeasureKind, "measure_kind")
VERIFICATION_STATUS_ENUM = _pg_enum(VerificationStatus, "verification_status")

#: Jednostka opakowania produktu sklepowego (03_DATABASE §3: `ENUM(g,ml,piece)`).
#: To DOKŁADNIE ten sam typ PG co `recipes.amount_unit` — powstał w migracji
#: `0006`, więc tutaj jest wyłącznie REFERENCJĄ (`create_type=False`, CLAUDE.md §4).
#: Osobny typ „package_unit" byłby duplikatem tej samej dziedziny wartości.
PACKAGE_UNIT_ENUM = postgresql.ENUM(
    AmountUnit,
    name="amount_unit",
    create_type=False,
    values_callable=lambda members: [m.value for m in members],
)


class ProductCategory(TimestampMixin, Base):
    """Kategoria zakupowa — słownik globalny, seed w migracji danych (02_DOMAIN §4.3).

    Kategoria niesie `perishability`, czyli informację, w której turze zakupowej
    produkt ma się pojawić. Dlatego nie wolno łączyć w jedną kategorię rzeczy
    o różnej trwałości (D14: pieczywo jest fresh, makarony durable — nie ma
    wspólnej kategorii „zbożowe").
    """

    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    #: Kolejność domyślna listy zakupów; profil sklepu (B09) może ją nadpisać.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    perishability: Mapped[Perishability] = mapped_column(
        PERISHABILITY_ENUM,
        nullable=False,
        default=Perishability.DURABLE,
        server_default=Perishability.DURABLE.value,
    )

    products: Mapped[list[CanonicalProduct]] = relationship(
        back_populates="category", passive_deletes=True
    )


class CanonicalProduct(TimestampMixin, Base):
    """Produkt kanoniczny — fundament systemu (02_DOMAIN §4.1).

    Każdy przepis, plan i pozycja spiżarni wskazuje TEN SAM wiersz dla cebuli.
    `normalized_name` (unikat) jest kluczem tożsamości produktu i liczy go
    wyłącznie `naming.normalize_name`.
    """

    __tablename__ = "canonical_products"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_canonical_products_normalized_name"),
        # Waga sztuki istnieje dokładnie dla produktów mierzonych w sztukach:
        # dla nich jest jedynym mostkiem szt. → g (ADR-005), dla pozostałych
        # byłaby danymi, których nikt nie używa i których nikt nie aktualizuje.
        CheckConstraint(
            "(measure_kind = 'piece' AND piece_weight_g IS NOT NULL AND piece_weight_g > 0)"
            " OR (measure_kind <> 'piece' AND piece_weight_g IS NULL)",
            name="piece_weight_matches_measure_kind",
        ),
        CheckConstraint(
            "glycemic_index IS NULL OR (glycemic_index >= 0 AND glycemic_index <= 110)",
            name="glycemic_index_range",
        ),
        CheckConstraint(
            "(kcal_100 IS NULL OR kcal_100 >= 0)"
            " AND (protein_100 IS NULL OR protein_100 >= 0)"
            " AND (fat_100 IS NULL OR fat_100 >= 0)"
            " AND (carbs_100 IS NULL OR carbs_100 >= 0)"
            " AND (fiber_100 IS NULL OR fiber_100 >= 0)"
            " AND (sugars_100 IS NULL OR sugars_100 >= 0)",
            name="nutrition_non_negative",
        ),
        # Wyszukiwarka tolerująca literówki (04_API §1, `?q=`). Indeks trigramowy
        # zakłada rozszerzenie pg_trgm — tworzy je migracja katalogu.
        Index(
            "ix_canonical_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    #: RESTRICT: kategoria z produktami nie znika po cichu — użytkownik dostaje
    #: 409 z listą użyć (ADR-012).
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    measure_kind: Mapped[MeasureKind] = mapped_column(MEASURE_KIND_ENUM, nullable=False)
    piece_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Rdzeń wartości odżywczych na 100 g (VOLUME: na 100 ml) — ADR-004.
    # NULL = „nie wiemy", nigdy 0 (patrz docstring modułu).
    kcal_100: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    protein_100: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    fat_100: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    carbs_100: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    fiber_100: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    sugars_100: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    glycemic_index: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)

    verification_status: Mapped[VerificationStatus] = mapped_column(
        VERIFICATION_STATUS_ENUM,
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default=VerificationStatus.UNVERIFIED.value,
    )
    nutrition_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Nadpisanie trwałości kategorii dla pojedynczego produktu (02_DOMAIN §9.2).
    #: Konsumentem jest silnik zakupowy (B10); tutaj to wyłącznie pole formularza.
    perishability_override: Mapped[Perishability | None] = mapped_column(
        PERISHABILITY_ENUM, nullable=True
    )
    #: Archiwizacja zamiast usuwania (ADR-012) — znika z pickerów i list domyślnych.
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    category: Mapped[ProductCategory] = relationship(back_populates="products")
    # Kolekcje istnieją dla konfiguracji kaskad, NIE do odczytu w warstwie HTTP
    # (lekcja z BATCH_03: leniwa relacja tknięta poza greenletem = 500).
    unit_weights: Mapped[list[ProductUnitWeight]] = relationship(
        back_populates="product", passive_deletes=True
    )
    nutrient_values: Mapped[list[ProductNutrientValue]] = relationship(
        back_populates="product", passive_deletes=True
    )


class ProductUnitWeight(TimestampMixin, Base):
    """Przelicznik jednostki domowej produktu (ADR-005).

    `unit_label` zapisywany jest już znormalizowany (`units.normalize_unit_label`),
    inaczej UNIQUE nie zablokowałby pary „Łyżka" / „łyżka ".
    """

    __tablename__ = "product_unit_weights"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "unit_label", name="uq_product_unit_weights_product_id_unit_label"
        ),
        CheckConstraint("grams_per_unit > 0", name="grams_per_unit_positive"),
        CheckConstraint("samples_count >= 1", name="samples_count_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unit_label: Mapped[str] = mapped_column(Text, nullable=False)
    grams_per_unit: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Liczba próbek, z których policzono medianę. Dziś ustawia ją WYŁĄCZNIE
    #: formularz produktu (`POST /products/{id}/unit-weights` wysyła 1) —
    #: mechanizm zbierania próbek odszedł razem z importerem PDF (D25).
    samples_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    product: Mapped[CanonicalProduct] = relationship(back_populates="unit_weights")


class Nutrient(TimestampMixin, Base):
    """Słownik rozszerzeń wartości odżywczych (ADR-004).

    W MVP seedowany PUSTO: mikroelementy dokłada się INSERT-em do tego słownika,
    bez migracji łamiącej schemat.
    """

    __tablename__ = "nutrients"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class ProductNutrientValue(TimestampMixin, Base):
    """Wartość rozszerzonego składnika odżywczego produktu, na 100 g/ml."""

    __tablename__ = "product_nutrient_values"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "nutrient_code",
            name="uq_product_nutrient_values_product_id_nutrient_code",
        ),
        CheckConstraint("amount_per_100 >= 0", name="amount_per_100_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: RESTRICT — kodu nie da się usunąć ze słownika, dopóki ktoś go używa.
    nutrient_code: Mapped[str] = mapped_column(
        Text, ForeignKey("nutrients.code", ondelete="RESTRICT"), nullable=False
    )
    amount_per_100: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)

    product: Mapped[CanonicalProduct] = relationship(back_populates="nutrient_values")


class Store(TimestampMixin, Base):
    """Sklep — słownik globalny, edytowalny przez USERA (02_DOMAIN §3.1 pkt 3, §4.5).

    Sklep sam z siebie niesie mało: nazwę i opcjonalny kolor do odróżnienia na
    liście. Wartość dokłada mu PROFIL (`store_category_order`) — kolejność
    fizycznego przejścia po sklepie, wg której B11 sortuje listę zakupową.

    `is_archived` zamiast usuwania (ADR-012, rozstrzygnięcie planu B09 pkt 2):
    sklep, którego już nie odwiedzamy, znika z pickerów, ale zostaje przy
    historycznych produktach sklepowych.
    """

    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("name", name="uq_stores_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Token/etykieta koloru z palety UI (06_UIUX §1) — nigdy hex z komponentu.
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # Kolekcja istnieje dla konfiguracji kaskady, NIE do odczytu w warstwie HTTP
    # (lekcja z BATCH_03: leniwa relacja tknięta poza greenletem = 500).
    category_order: Mapped[list[StoreCategoryOrder]] = relationship(
        back_populates="store", passive_deletes=True
    )


class StoreCategoryOrder(TimestampMixin, Base):
    """Jedna pozycja profilu sklepu: kategoria + jej miejsce w kolejności (02_DOMAIN §4.5).

    Klucz główny jest złożony (`store_id`, `category_id`) — kategoria występuje
    w profilu sklepu najwyżej raz, więc osobne `id` byłoby tylko dodatkowym
    sposobem zapisania duplikatu.

    Obie strony kasują się KASKADĄ, nie RESTRICT-em: profil to atrybut sklepu
    (kompozycja rodzic→dziecko, ADR-012), a kategoria usunięta ze słownika nie
    ma prawa blokować sklepu — sama kategoria jest chroniona 409-ką od strony
    produktów (`delete_category`).
    """

    __tablename__ = "store_category_order"

    store_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product_categories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    #: Pozycja w przejściu po sklepie; spójność permutacji pilnuje serwis (PUT
    #: podmienia całość), bo pojedynczy wiersz nie wie nic o pozostałych.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    store: Mapped[Store] = relationship(back_populates="category_order")


class RetailProduct(TimestampMixin, Base):
    """Produkt sklepowy — konkretny produkt z półki (02_DOMAIN §4.4).

    Powiązanie z produktem kanonicznym jest OBOWIĄZKOWE i to jest cała istota
    tej tabeli: „Pilos Jogurt naturalny 400 g" ma sens tylko jako wariant
    kanonicznego „jogurtu naturalnego", bo wartości odżywcze, przeliczniki
    i agregacja zakupów żyją przy kanonicznym (ADR-004). Retail dokłada do tego
    to, czego kanoniczny nie wie: markę, sklep i WIELKOŚĆ OPAKOWANIA, z której
    silnik zakupowy (B10) liczy liczbę opakowań i resztkę.

    `package_unit` musi zgadzać się z `measure_kind` produktu kanonicznego
    (g↔mass, ml↔volume, piece↔piece) — pilnuje tego serwis, bo baza nie widzi
    obu tabel w jednym CHECK-u.
    """

    __tablename__ = "retail_products"
    __table_args__ = (
        # 03_DATABASE §3 wymienia ten indeks wprost: najczęstszym zapytaniem jest
        # „warianty retail TEGO produktu kanonicznego" (karta produktu, B10).
        Index("ix_retail_products_canonical_product_id", "canonical_product_id"),
        Index("ix_retail_products_store_id", "store_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: RESTRICT: produkt kanoniczny użyty w retail nie znika (ADR-012). Licznik
    #: referencji dla czytelnej 409-ki rejestruje `retail_service`.
    canonical_product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("canonical_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: SET NULL, nie RESTRICT: sklep bywa likwidowany, a wielkość opakowania
    #: zostaje prawdziwa — wariant bez sklepu jest dozwolonym stanem (03 §3).
    #: Fizyczne usunięcie sklepu i tak blokuje 409 z listy użyć (`delete_store`),
    #: więc SET NULL zadziała tylko przy usunięciu z pominięciem serwisu.
    store_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True,
    )
    package_amount: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    package_unit: Mapped[AmountUnit] = mapped_column(PACKAGE_UNIT_ENUM, nullable=False)
    #: Sztuki w opakowaniu (jajka 10 szt.) — opcjonalne, bo większość opakowań
    #: opisuje wyłącznie masa albo objętość.
    pieces_per_package: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Ścieżka WZGLĘDNA w katalogu uploadów (`app/core/uploads.py`); miniatura
    #: wynika z konwencji nazwy, więc nie ma dla niej osobnej kolumny.
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
