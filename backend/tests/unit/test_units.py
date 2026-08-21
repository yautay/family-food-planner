"""Konwersje jednostek — obszar krytyczny (08_TESTING §2.3), pokrycie blisko 100%.

Reguła nadrzędna, której pilnują te testy: ilość, której nie da się jednoznacznie
przeliczyć na oś produktu, NIE MOŻE zostać zapisana (ADR-005, 02_DOMAIN §13.1).
Drugi motyw przewodni: żadnego `float` — wszystkie wartości i asercje są
`Decimal`, bo `0.1 + 0.2` na floatach nie jest `0.3`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.naming import normalize_name
from app.modules.catalog.units import (
    AmountUnit,
    MeasureKind,
    NormalizedAmount,
    ProductMeasure,
    UnitConversionError,
    UnitWeight,
    base_unit,
    basis_unit,
    canonical_unit_label,
    find_unit_weight,
    normalize_amount,
    normalize_unit_label,
    to_base_amount,
    to_basis_amount,
    to_grams,
)

pytestmark = pytest.mark.unit

MASS_PRODUCT = ProductMeasure(measure_kind=MeasureKind.MASS)
VOLUME_PRODUCT = ProductMeasure(measure_kind=MeasureKind.VOLUME)
#: Cebula z audytu PDF (01_PDF_AUDIT §5.2): sztuka waży 105 g.
PIECE_PRODUCT = ProductMeasure(measure_kind=MeasureKind.PIECE, piece_weight_g=Decimal("105.00"))
#: Mąka pszenna: łyżka bywa 5, 12 albo 15 g — tu wpis produktu mówi 12.
FLOUR = ProductMeasure(
    measure_kind=MeasureKind.MASS,
    unit_weights=(
        UnitWeight(unit_label="łyżka", grams_per_unit=Decimal("12.00")),
        UnitWeight(unit_label="garść", grams_per_unit=Decimal("30.00")),
        UnitWeight(unit_label="opakowanie", grams_per_unit=Decimal("1000.00")),
    ),
)


# --- jednostki systemowe -------------------------------------------------------


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (Decimal("250"), "g", Decimal("250")),
        (Decimal("1.5"), "kg", Decimal("1500.0")),
        (Decimal("0.001"), "kg", Decimal("1.000")),
    ],
)
def test_masa_sprowadzana_jest_do_gramow(quantity: Decimal, unit: str, expected: Decimal) -> None:
    """g i kg lądują na osi gramów, bez zaokrągleń po drodze."""
    result = normalize_amount(quantity, unit, MASS_PRODUCT)

    assert result == NormalizedAmount(expected, AmountUnit.GRAM)


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (Decimal("330"), "ml", Decimal("330")),
        (Decimal("1.75"), "l", Decimal("1750.00")),
    ],
)
def test_objetosc_sprowadzana_jest_do_mililitrow(
    quantity: Decimal, unit: str, expected: Decimal
) -> None:
    """ml i l lądują na osi mililitrów."""
    result = normalize_amount(quantity, unit, VOLUME_PRODUCT)

    assert result == NormalizedAmount(expected, AmountUnit.MILLILITER)


def test_sztuki_zostaja_sztukami_a_do_gramow_przelicza_je_waga_sztuki() -> None:
    """`szt.` przechowujemy jako sztuki; mostkiem do gramów jest `piece_weight_g`."""
    amount = normalize_amount(Decimal("2"), "szt.", PIECE_PRODUCT)

    assert amount == NormalizedAmount(Decimal("2"), AmountUnit.PIECE)
    assert to_grams(amount, PIECE_PRODUCT) == Decimal("210.00")


@pytest.mark.parametrize("label", ["szt.", "szt", "Sztuka", " SZTUKI "])
def test_warianty_zapisu_sztuki_znacza_to_samo(label: str) -> None:
    """Użytkownik pisze „szt", importer „sztuka" — to jedna i ta sama jednostka."""
    assert normalize_amount(Decimal("1"), label, PIECE_PRODUCT).unit is AmountUnit.PIECE


def test_sztuki_dla_produktu_nieliczonego_w_sztukach_sa_odrzucane() -> None:
    """Bez wagi sztuki nie ma jak przeliczyć — zapis odrzucony, nie zgadnięty."""
    with pytest.raises(UnitConversionError) as excinfo:
        normalize_amount(Decimal("1"), "szt.", MASS_PRODUCT)

    assert "nie jest mierzony w sztukach" in excinfo.value.message


# --- jednostki domowe -----------------------------------------------------------


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (Decimal("2"), "łyżka", Decimal("24.00")),
        (Decimal("1"), "garść", Decimal("30.00")),
        (Decimal("0.5"), "opakowanie", Decimal("500.000")),
        # „opak." i „opakowanie" to ta sama jednostka (02_DOMAIN §4.2).
        (Decimal("1"), "opak.", Decimal("1000.00")),
    ],
)
def test_jednostki_domowe_przeliczaja_sie_przez_przelicznik_produktu(
    quantity: Decimal, unit: str, expected: Decimal
) -> None:
    """Gramatura jednostki domowej jest własnością produktu (01_PDF_AUDIT §5.2)."""
    assert normalize_amount(quantity, unit, FLOUR) == NormalizedAmount(expected, AmountUnit.GRAM)


def test_jednostka_domowa_bez_przelicznika_jest_odrzucana() -> None:
    """Brak przelicznika = odmowa zapisu z podpowiedzią, co zrobić (ADR-005)."""
    with pytest.raises(UnitConversionError) as excinfo:
        normalize_amount(Decimal("1"), "szczypta", FLOUR)

    assert "szczypta" in excinfo.value.message
    assert excinfo.value.status_code == 422


def test_ten_sam_przelicznik_moze_znaczyc_co_innego_dla_innego_produktu() -> None:
    """Uniwersalnej tabeli przeliczników nie ma: łyżka mąki ≠ łyżka śmietany."""
    cream = ProductMeasure(
        measure_kind=MeasureKind.MASS,
        unit_weights=(UnitWeight(unit_label="łyżka", grams_per_unit=Decimal("25.00")),),
    )

    assert normalize_amount(Decimal("1"), "łyżka", FLOUR).amount == Decimal("12.00")
    assert normalize_amount(Decimal("1"), "łyżka", cream).amount == Decimal("25.00")


def test_jednostka_domowa_produktu_w_sztukach_daje_gramy() -> None:
    """Regresja z review R1: przelicznik jednostki domowej daje GRAMY, nie sztuki.

    Wynik oznaczony jako `piece` kazałby `to_grams` pomnożyć go po raz drugi przez
    `piece_weight_g` — dla jajka po 105 g „1 opakowanie = 600 g" wyszłoby 63 000 g.
    """
    eggs = ProductMeasure(
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("105.00"),
        unit_weights=(UnitWeight(unit_label="opakowanie", grams_per_unit=Decimal("600.00")),),
    )

    amount = normalize_amount(Decimal("1"), "opakowanie", eggs)

    assert amount == NormalizedAmount(Decimal("600.00"), AmountUnit.GRAM)
    assert to_grams(amount, eggs) == Decimal("600.00")
    assert to_basis_amount(amount, eggs) == Decimal("600.00")


def test_jednostka_domowa_produktu_objetosciowego_daje_mililitry() -> None:
    """Produkt liczony na 100 ml musi dostać ilość w ml, inaczej silnik policzy bzdurę."""
    oil = ProductMeasure(
        measure_kind=MeasureKind.VOLUME,
        unit_weights=(UnitWeight(unit_label="łyżka", grams_per_unit=Decimal("10.00")),),
    )

    assert normalize_amount(Decimal("3"), "łyżka", oil) == NormalizedAmount(
        Decimal("30.00"), AmountUnit.MILLILITER
    )


# --- precyzja i przypadki brzegowe -----------------------------------------------


def test_konwersja_nie_gubi_precyzji_dziesietnej() -> None:
    """`0,3 raza 105 g` to dokładnie 31,5 g — na floatach wyszłoby 31.499999999999996."""
    amount = normalize_amount(Decimal("0.3"), "szt.", PIECE_PRODUCT)

    assert to_grams(amount, PIECE_PRODUCT) == Decimal("31.500")


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1"), Decimal("-0.001")])
def test_ilosc_niedodatnia_jest_bledem(quantity: Decimal) -> None:
    """Zero i wartości ujemne nie są ilością — to błąd wejścia, nie „pusta pozycja"."""
    with pytest.raises(UnitConversionError):
        normalize_amount(quantity, "g", MASS_PRODUCT)


def test_mililitrow_nie_przeliczamy_na_gramy() -> None:
    """Bez gęstości ml → g to zgadywanie, a silnik nie zgaduje (ADR-005)."""
    amount = NormalizedAmount(Decimal("100"), AmountUnit.MILLILITER)

    with pytest.raises(UnitConversionError):
        to_grams(amount, VOLUME_PRODUCT)


def test_sztuki_bez_wagi_sztuki_nie_przeliczaja_sie_na_gramy() -> None:
    """Druga linia obrony `to_grams` — dane niespójne wychodzą wyjątkiem, nie zerem."""
    broken = ProductMeasure(measure_kind=MeasureKind.PIECE, piece_weight_g=None)

    with pytest.raises(UnitConversionError):
        to_grams(NormalizedAmount(Decimal("1"), AmountUnit.PIECE), broken)


# --- oś wartości odżywczych --------------------------------------------------------


def test_baza_wartosci_odzywczych_dla_sztuk_liczona_jest_w_gramach() -> None:
    """Produkt PIECE ma wartości na 100 g, więc 2 sztuki po 105 g = 210 g."""
    amount = normalize_amount(Decimal("2"), "szt.", PIECE_PRODUCT)

    assert to_basis_amount(amount, PIECE_PRODUCT) == Decimal("210.00")


def test_baza_wartosci_odzywczych_dla_objetosci_liczona_jest_w_mililitrach() -> None:
    """Produkt VOLUME ma wartości na 100 ml."""
    amount = normalize_amount(Decimal("0.25"), "l", VOLUME_PRODUCT)

    assert to_basis_amount(amount, VOLUME_PRODUCT) == Decimal("250.00")


def test_gramy_dla_produktu_objetosciowego_sa_odrzucane_jako_baza() -> None:
    """Ilość w gramach nie pasuje do wartości „na 100 ml" — lepiej błąd niż cichy wynik."""
    amount = NormalizedAmount(Decimal("100"), AmountUnit.GRAM)

    with pytest.raises(UnitConversionError):
        to_basis_amount(amount, VOLUME_PRODUCT)


@pytest.mark.parametrize(
    ("measure_kind", "expected"),
    [
        (MeasureKind.MASS, AmountUnit.GRAM),
        (MeasureKind.VOLUME, AmountUnit.MILLILITER),
        (MeasureKind.PIECE, AmountUnit.PIECE),
    ],
)
def test_os_produktu_wynika_z_typu_miary(measure_kind: MeasureKind, expected: AmountUnit) -> None:
    assert base_unit(measure_kind) is expected


@pytest.mark.parametrize(
    ("measure_kind", "expected"),
    [
        (MeasureKind.MASS, AmountUnit.GRAM),
        (MeasureKind.VOLUME, AmountUnit.MILLILITER),
        # Sztuki mają wartości na 100 g, więc oś WARTOŚCI to gramy, nie sztuki.
        (MeasureKind.PIECE, AmountUnit.GRAM),
    ],
)
def test_os_wartosci_odzywczych_rozni_sie_od_osi_przechowywania(
    measure_kind: MeasureKind, expected: AmountUnit
) -> None:
    assert basis_unit(measure_kind) is expected


# --- normalizacja etykiet i nazw ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Łyżka ", "łyżka"),
        ("PLASTER", "plaster"),
        ("garść  duża", "garść duża"),
    ],
)
def test_etykieta_jednostki_normalizuje_sie_do_porownan(raw: str, expected: str) -> None:
    assert normalize_unit_label(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [("opak", "opakowanie"), ("Szt", "szt.")])
def test_warianty_etykiet_sprowadzaja_sie_do_jednej_postaci(raw: str, expected: str) -> None:
    assert canonical_unit_label(raw) == expected


def test_wyszukiwanie_przelicznika_ignoruje_zapis_etykiety() -> None:
    weights = (UnitWeight(unit_label="Łyżka", grams_per_unit=Decimal("12.00")),)

    assert find_unit_weight(weights, " łyżka ") is not None
    assert find_unit_weight(weights, "garść") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Serek   Kanapkowy ", "serek kanapkowy"),
        ("Cebula", "cebula"),
        ("Ser mozzarella light ", "ser mozzarella light"),
    ],
)
def test_normalizacja_nazwy_produktu_zbija_spacje_i_wielkosc_liter(raw: str, expected: str) -> None:
    """Duplikaty z audytu PDF (01_PDF_AUDIT §5.3) muszą dawać ten sam klucz."""
    assert normalize_name(raw) == expected


# --- oś PRZECHOWYWANIA ilości (`to_base_amount`, wejście zakupów B10) -----------------


def test_os_przechowywania_zwraca_ilosc_bez_zmian_gdy_jednostka_sie_zgadza() -> None:
    """Gramy dla produktu w masie i mililitry dla objętości nie wymagają konwersji."""
    assert to_base_amount(
        NormalizedAmount(Decimal("250"), AmountUnit.GRAM), MASS_PRODUCT
    ) == Decimal("250")
    assert to_base_amount(
        NormalizedAmount(Decimal("500"), AmountUnit.MILLILITER), VOLUME_PRODUCT
    ) == Decimal("500")


def test_gramy_wracaja_na_sztuki_dla_produktu_mierzonego_w_sztukach() -> None:
    """Jednostka domowa produktu PIECE daje gramy — zakupy potrzebują sztuk.

    To odwrotność `to_basis_amount`: opakowanie jajek liczy się w sztukach,
    więc 210 g cebuli po 105 g/szt. to dokładnie 2 sztuki.
    """
    amount = NormalizedAmount(Decimal("210.00"), AmountUnit.GRAM)

    assert to_base_amount(amount, PIECE_PRODUCT) == Decimal("2")


def test_sztuki_wracaja_na_gramy_dla_produktu_mierzonego_w_masie() -> None:
    """Ilość w sztukach przy produkcie masowym idzie przez `to_grams`, nie przez domysł."""
    eggs = ProductMeasure(measure_kind=MeasureKind.MASS, piece_weight_g=Decimal("60.00"))

    with pytest.raises(UnitConversionError):
        # Produkt masowy nie ma wagi sztuki w praktyce (CHECK w bazie), więc
        # przeliczenie jest niemożliwe — tu waga jest podana sztucznie.
        to_base_amount(NormalizedAmount(Decimal("2"), AmountUnit.PIECE), MASS_PRODUCT)
    assert to_base_amount(NormalizedAmount(Decimal("2"), AmountUnit.PIECE), eggs) == Decimal(
        "120.00"
    )


def test_os_przechowywania_odrzuca_nieprzeliczalne_pary() -> None:
    """Mililitry dla produktu masowego i gramy dla objętości = wyjątek, nie przybliżenie."""
    with pytest.raises(UnitConversionError):
        to_base_amount(NormalizedAmount(Decimal("100"), AmountUnit.MILLILITER), MASS_PRODUCT)
    with pytest.raises(UnitConversionError):
        to_base_amount(NormalizedAmount(Decimal("100"), AmountUnit.GRAM), VOLUME_PRODUCT)


def test_sztuki_bez_wagi_sztuki_nie_daja_sie_policzyc_z_gramow() -> None:
    """Produkt w sztukach bez `piece_weight_g` nie zgaduje, ile to sztuk."""
    unknown = ProductMeasure(measure_kind=MeasureKind.PIECE)

    with pytest.raises(UnitConversionError):
        to_base_amount(NormalizedAmount(Decimal("300"), AmountUnit.GRAM), unknown)
