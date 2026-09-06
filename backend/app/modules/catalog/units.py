"""Konwersje jednostek — czyste funkcje na `Decimal`, zero I/O (ADR-005, ADR-008).

Niezmiennik systemowy (02_DOMAIN §13.1): **ilość bez jednoznacznej reprezentacji
na osi produktu nie istnieje w danych**. Każdy zapis ilości (składnik przepisu,
pozycja planu, spiżarnia) przechodzi przez `normalize_amount`, a gdy przeliczenie
jest niemożliwe — zapis jest odrzucany wyjątkiem, nie „ratowany" domysłem.

Osie ilości:

- produkt `MASS`   → gramy (`g`),
- produkt `VOLUME` → mililitry (`ml`),
- produkt `PIECE`  → sztuki (`piece`), z wagą sztuki (`piece_weight_g`)
  jako mostkiem do gramów dla silników.

Jednostki systemowe (02_DOMAIN §4.2): `g`, `kg`, `ml`, `l`, `szt.`, `opak.`
Pierwsze cztery mają stały przelicznik. `szt.` wymaga produktu mierzonego
w sztukach, a `opak.` — jak każda inna jednostka domowa („łyżka", „garść",
„plaster") — przelicznika zapisanego PRZY PRODUKCIE (`product_unit_weights`).
Uniwersalnej tabeli przeliczników nie ma i nie będzie: pomiar na realnych
jadłospisach pokazał, że łyżka mąki waży 5, 12 albo 15 g zależnie od
miejsca, a jajko 50 albo 60 g.

Moduł jest importowany przez silnik nutrition (B05) i silnik zakupowy (B10) —
nie wolno mu zależeć od SQLAlchemy ani od warstwy HTTP.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.core.errors import AppError


class MeasureKind(StrEnum):
    """Bazowy typ miary produktu (02_DOMAIN §4.1). Wartości = typ enumowy w PG."""

    MASS = "mass"
    VOLUME = "volume"
    PIECE = "piece"


class AmountUnit(StrEnum):
    """Oś, na której ilość jest przechowywana (03_DATABASE §5: `ENUM(g,ml,piece)`)."""

    GRAM = "g"
    MILLILITER = "ml"
    PIECE = "piece"


class UnitConversionError(AppError):
    """Ilości nie da się jednoznacznie przeliczyć — zapis odrzucony (ADR-005).

    Status 422, bo z punktu widzenia API to błąd danych wejściowych: użytkownik
    podał jednostkę, której dla tego produktu nie znamy.
    """

    status_code = 422
    code = "validation_error"


#: Jednostki masy → gramy.
MASS_FACTORS: dict[str, Decimal] = {"g": Decimal("1"), "kg": Decimal("1000")}
#: Jednostki objętości → mililitry.
VOLUME_FACTORS: dict[str, Decimal] = {"ml": Decimal("1"), "l": Decimal("1000")}

#: Kanoniczna etykieta sztuki i opakowania. `opak.` NIE ma stałego przelicznika —
#: sprowadzamy je do jednej etykiety tylko po to, żeby lookup w przelicznikach
#: produktu znalazł wpis niezależnie od tego, czy zapisano „opak." czy
#: „opakowanie".
PIECE_LABEL = "szt."
PACKAGE_LABEL = "opakowanie"

#: Warianty zapisu tej samej jednostki. Klucze są już znormalizowane
#: (`normalize_unit_label`), więc wystarczy prosty lookup.
UNIT_ALIASES: dict[str, str] = {
    "szt": PIECE_LABEL,
    "szt.": PIECE_LABEL,
    "sztuka": PIECE_LABEL,
    "sztuki": PIECE_LABEL,
    "sztuk": PIECE_LABEL,
    "opak": PACKAGE_LABEL,
    "opak.": PACKAGE_LABEL,
    "opakowanie": PACKAGE_LABEL,
}

#: Jednostki systemowe pokazywane w UI (06_UIUX §7 — nazwy po polsku).
SYSTEM_UNIT_LABELS: tuple[str, ...] = ("g", "kg", "ml", "l", PIECE_LABEL, PACKAGE_LABEL)


@dataclass(frozen=True)
class UnitWeight:
    """Przelicznik jednostki domowej produktu (`product_unit_weights`)."""

    unit_label: str
    grams_per_unit: Decimal


@dataclass(frozen=True)
class ProductMeasure:
    """Wszystko, czego konwersja wie o produkcie — bez ORM (ADR-008).

    Serwis buduje to z encji (`ProductMeasure.from_product`), silniki dostają
    już gotową strukturę.
    """

    measure_kind: MeasureKind
    piece_weight_g: Decimal | None = None
    unit_weights: tuple[UnitWeight, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NormalizedAmount:
    """Ilość sprowadzona na oś produktu — to trafia do bazy."""

    amount: Decimal
    unit: AmountUnit


def normalize_unit_label(label: str) -> str:
    """Etykieta jednostki do porównań: trim, zbicie spacji, lowercase.

    Tą samą funkcją serwis normalizuje etykiety PRZED zapisem, dzięki czemu
    UNIQUE(product_id, unit_label) faktycznie blokuje duplikaty („Łyżka"
    i „łyżka " to jeden przelicznik, nie dwa).
    """
    return " ".join(label.split()).casefold()


def canonical_unit_label(label: str) -> str:
    """Znormalizowana etykieta ze sprowadzeniem wariantów zapisu do jednego."""
    normalized = normalize_unit_label(label)
    return UNIT_ALIASES.get(normalized, normalized)


def base_unit(measure_kind: MeasureKind) -> AmountUnit:
    """Oś, na której trzymamy ilości danego produktu podane w JEGO jednostce.

    Dotyczy jednostek systemowych: `g`/`kg` → g, `ml`/`l` → ml, `szt.` → sztuki.
    Dla wartości odżywczych („na 100") oś jest inna — patrz `basis_unit`.
    """
    if measure_kind is MeasureKind.VOLUME:
        return AmountUnit.MILLILITER
    if measure_kind is MeasureKind.PIECE:
        return AmountUnit.PIECE
    return AmountUnit.GRAM


def basis_unit(measure_kind: MeasureKind) -> AmountUnit:
    """Oś, w której podane są wartości „na 100": ml dla objętości, g dla reszty.

    To NIE to samo co `base_unit`: produkt mierzony w sztukach trzyma własne
    ilości w sztukach, ale wartości odżywcze ma na 100 **gramów** (ADR-004),
    więc przelicznik jednostki domowej (`grams_per_unit`) daje dla niego gramy.
    """
    return AmountUnit.MILLILITER if measure_kind is MeasureKind.VOLUME else AmountUnit.GRAM


def find_unit_weight(unit_weights: Iterable[UnitWeight], label: str) -> UnitWeight | None:
    """Przelicznik jednostki domowej po znormalizowanej etykiecie (albo `None`)."""
    wanted = canonical_unit_label(label)
    for weight in unit_weights:
        if canonical_unit_label(weight.unit_label) == wanted:
            return weight
    return None


def normalize_amount(
    quantity: Decimal, unit_label: str, product: ProductMeasure
) -> NormalizedAmount:
    """(ilość, jednostka) → ilość na osi produktu. Nieprzeliczalne = wyjątek.

    Kolejność rozstrzygania: jednostki masy → objętości → sztuki → przeliczniki
    domowe produktu. Jednostka domowa daje ilość na osi WARTOŚCI produktu
    (`basis_unit`: gramy dla masy i sztuk, mililitry dla objętości) — inaczej
    „łyżka mleka" wylądowałaby w gramach, a wartości odżywcze produktu VOLUME
    są liczone na 100 ml i wynik byłby cichym błędem silnika.
    """
    if quantity <= 0:
        raise UnitConversionError("Ilość musi być liczbą większą od zera.")

    label = canonical_unit_label(unit_label)

    if label in MASS_FACTORS:
        return NormalizedAmount(quantity * MASS_FACTORS[label], AmountUnit.GRAM)
    if label in VOLUME_FACTORS:
        return NormalizedAmount(quantity * VOLUME_FACTORS[label], AmountUnit.MILLILITER)

    if label == PIECE_LABEL:
        if product.measure_kind is not MeasureKind.PIECE or product.piece_weight_g is None:
            raise UnitConversionError(
                "Ten produkt nie jest mierzony w sztukach. Podaj ilość w gramach, "
                "mililitrach albo w jednostce domowej z przelicznikiem."
            )
        return NormalizedAmount(quantity, AmountUnit.PIECE)

    weight = find_unit_weight(product.unit_weights, label)
    if weight is None:
        raise UnitConversionError(
            f"Nie znam przelicznika jednostki „{unit_label.strip()}” dla tego produktu. "
            "Dodaj go w sekcji przeliczników jednostek domowych przy produkcie."
        )
    # `basis_unit`, NIE `base_unit`: dla produktu mierzonego w sztukach przelicznik
    # daje GRAMY, więc oznaczenie wyniku jako „sztuki" kazałoby `to_grams` pomnożyć
    # go jeszcze raz przez `piece_weight_g` (ustalenie review R1).
    return NormalizedAmount(quantity * weight.grams_per_unit, basis_unit(product.measure_kind))


def to_grams(amount: NormalizedAmount, product: ProductMeasure) -> Decimal:
    """Ilość w gramach. Sztuki mnoży przez `piece_weight_g`; mililitrów NIE zgaduje.

    Przeliczenie ml → g wymagałoby gęstości, której w modelu nie ma i nie będzie
    (ADR-005) — próba takiego przeliczenia to wyjątek, nie przybliżenie.
    """
    if amount.unit is AmountUnit.GRAM:
        return amount.amount
    if amount.unit is AmountUnit.PIECE:
        if product.piece_weight_g is None:
            raise UnitConversionError(
                "Produkt nie ma podanej wagi sztuki, więc nie da się przeliczyć sztuk na gramy."
            )
        return amount.amount * product.piece_weight_g
    raise UnitConversionError(
        "Nie da się przeliczyć mililitrów na gramy — to wymagałoby gęstości produktu."
    )


def to_base_amount(amount: NormalizedAmount, product: ProductMeasure) -> Decimal:
    """Ilość na osi PRZECHOWYWANIA produktu (`base_unit`) — wejście zakupów (B10).

    Kontrast z `to_basis_amount` jest celowy i wynika z dwóch osi opisanych
    w nagłówku modułu: tam celem jest oś WARTOŚCI („na 100"), więc produkt
    mierzony w sztukach dostaje gramy; tutaj celem jest oś, na której leżą
    ilości i opakowania, więc ten sam produkt dostaje SZTUKI (opakowanie jajek
    ma 10 szt., nie 600 g — 03_DATABASE §3).

    Dlatego to jedyne miejsce w module, które DZIELI przez `piece_weight_g`:
    ilość zapisana w gramach (bo `normalize_amount` tak sprowadza jednostki
    domowe produktu w sztukach) wraca tu na sztuki. Wyniku nie kwantyzujemy —
    zaokrąglenie należy do liczenia opakowań (ADR-008).
    """
    target = base_unit(product.measure_kind)
    if amount.unit is target:
        return amount.amount
    if target is AmountUnit.PIECE and amount.unit is AmountUnit.GRAM:
        if product.piece_weight_g is None or product.piece_weight_g <= 0:
            raise UnitConversionError(
                "Produkt nie ma podanej wagi sztuki, więc nie da się przeliczyć gramów na sztuki."
            )
        return amount.amount / product.piece_weight_g
    if target is AmountUnit.GRAM and amount.unit is AmountUnit.PIECE:
        return to_grams(amount, product)
    raise UnitConversionError(
        "Nie da się przeliczyć tej ilości na jednostkę produktu — sprawdź sposób "
        "liczenia produktu i jednostkę zapisanej ilości."
    )


def to_basis_amount(amount: NormalizedAmount, product: ProductMeasure) -> Decimal:
    """Ilość w jednostce, w której podane są wartości odżywcze produktu.

    Wartości są zawsze „na 100" (ADR-004): na 100 g dla masy i sztuk, na 100 ml
    dla objętości. To jest wejście silnika nutrition (B05).
    """
    if product.measure_kind is MeasureKind.VOLUME:
        if amount.unit is not AmountUnit.MILLILITER:
            raise UnitConversionError(
                "Ten produkt liczony jest na 100 ml — podaj ilość w mililitrach lub litrach."
            )
        return amount.amount
    return to_grams(amount, product)
