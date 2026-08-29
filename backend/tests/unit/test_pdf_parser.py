"""Parser jadłospisów PDF — regexy i maszyna stanów na wyciętych tekstach.

Fragmenty pochodzą DOSŁOWNIE z 01_PDF_AUDIT (§3.1, §3.2, §3.3, §7) i z realnej
ekstrakcji korpusu; testy korpusowe na plikach żyją osobno
(`tests/integration/test_pdf_corpus.py`), bo wymagają dysku.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.importer.parser import (
    INGREDIENT_RE,
    MEAL_HEADER_RE,
    PageKind,
    classify_pages,
    parse_document,
)

pytestmark = pytest.mark.unit


# --- regexy ---------------------------------------------------------------------


def test_naglowek_posilku_daje_kcal_i_wszystkie_makra() -> None:
    """Nagłówek z §3.1 rozkłada się na energię i pięć wartości."""
    match = MEAL_HEADER_RE.match("ŚNIADANIE Kcal: 468 W: 31.3 B: 17.9 T: 30.4 Bł: 9.0 ŁG: 4.3")

    assert match is not None
    assert match.group("meal") == "ŚNIADANIE"
    assert match.group("kcal") == "468"
    assert match.group("carbs") == "31.3"
    assert match.group("protein") == "17.9"
    assert match.group("fat") == "30.4"
    assert match.group("fiber") == "9.0"
    assert match.group("glycemic") == "4.3"


@pytest.mark.parametrize(
    ("line", "name", "qty", "unit", "grams"),
    [
        ("Cebula, 0,3 x Sztuka (31,5 g)", "Cebula", "0.3", "Sztuka", "31.5"),
        ("Przecier pomidorowy, 6 x Łyżka (90 g)", "Przecier pomidorowy", "6", "Łyżka", "90"),
        # Trailing space w nazwie jest w materiale (§5.3) — normalizacja zbija go
        # dopiero przy mapowaniu, surowa nazwa zostaje taka, jak w dokumencie.
        (
            "Ser mozzarella light , 0,5 x Sztuka (62,5 g)",
            "Ser mozzarella light",
            "0.5",
            "Sztuka",
            "62.5",
        ),
    ],
)
def test_wiersz_skladnika_rozklada_sie_na_pola(
    line: str, name: str, qty: str, unit: str, grams: str
) -> None:
    """Przecinek dziesiętny staje się `Decimal`, gramatura pochodzi z nawiasu (§3.2)."""
    document = parse_document([f"Poniedziałek\n{_MEAL_HEADER}\nDanie Przepis\n{line}"])
    ingredient = document.dishes[0].ingredients[0]

    assert ingredient.raw_name == name
    assert ingredient.raw_qty == Decimal(qty)
    assert ingredient.raw_unit == unit
    assert ingredient.grams == Decimal(grams)


def test_skladnik_sklejony_z_instrukcja_dzieli_sie_na_dwie_rzeczy() -> None:
    """Pułapka §3.2: pdfplumber dokleja prawą kolumnę do wiersza składnika."""
    line = "Cebula, 2 x Sztuka (210 g) Kapustę poszatkować, doprawić solą i odstawić."
    document = parse_document([f"Środa\n{_MEAL_HEADER}\nGołąbki Przepis\n{line}"])
    dish = document.dishes[0]

    assert dish.ingredients[0].raw_name == "Cebula"
    assert dish.ingredients[0].grams == Decimal("210")
    assert dish.instructions == "Kapustę poszatkować, doprawić solą i odstawić."


def test_instrukcja_bez_spacji_po_nawiasie_tez_sie_odkleja() -> None:
    """W korpusie prawa kolumna potrafi przykleić się wprost do `)` (dieta.pdf s. 7)."""
    line = "Szynka parmeńska (Prosciutto), 3 x Plaster (45 g)mozzarellą. Włóż do piekarnika"
    document = parse_document([f"Środa\n{_MEAL_HEADER}\nPizza Przepis\n{line}"])
    dish = document.dishes[0]

    assert dish.ingredients[0].raw_name == "Szynka parmeńska (Prosciutto)"
    assert dish.ingredients[0].grams == Decimal("45")
    assert dish.instructions.startswith("mozzarellą.")


def test_skladnik_bez_pary_ilosc_jednostka_jest_parsowany() -> None:
    """`Cukinia, 200 g` wchodzi do kontraktu §3.2 decyzją właściciela D20.

    Gramatura jest jedynym źródłem ilości (§8.3), więc wiersz bez pary
    ilość x jednostka niesie komplet potrzebnych danych — para zostaje pusta.
    """
    document = parse_document(
        [f"Środa\n{_MEAL_HEADER}\nOmlet Przepis\nCukinia, 200 g\n{_DAY_TOTAL}"]
    )
    ingredient = document.dishes[0].ingredients[0]

    assert ingredient.raw_name == "Cukinia"
    assert ingredient.grams == Decimal("200")
    assert ingredient.raw_qty is None
    assert ingredient.raw_unit is None
    assert document.findings == ()


def test_skladnik_bez_pary_toleruje_doklejona_prawa_kolumne() -> None:
    """Ten sam wariant z urwkiem instrukcji — sześć takich wierszy w korpusie."""
    line = "Cukinia, 200 g wymieszać z serem i pokrojonym pomidorem."
    document = parse_document([f"Środa\n{_MEAL_HEADER}\nOmlet Przepis\n{line}\n{_DAY_TOTAL}"])
    dish = document.dishes[0]

    assert dish.ingredients[0].raw_name == "Cukinia"
    assert dish.ingredients[0].grams == Decimal("200")
    assert dish.instructions == "wymieszać z serem i pokrojonym pomidorem."


@pytest.mark.parametrize(
    ("head", "tail", "unit", "grams"),
    [
        # Jednostka w DRUGIEJ linii (`Kostka`) — najczęstszy wariant w korpusie.
        ("Czekolada ciemna (60-69% masy kakaowej), 2 x", "Kostka (16 g)", "Kostka", "16"),
        # …i w PIERWSZEJ, gdy zawinął się sam nawias z gramaturą.
        ("Kakao (proszek bez dodatku cukru), 1 x Łyżeczka", "(5 g)", "Łyżeczka", "5"),
    ],
)
def test_skladnik_zawiniety_miedzy_dwie_linie_sklada_sie_z_powrotem(
    head: str, tail: str, unit: str, grams: str
) -> None:
    """Drugi wariant dołożony przez D20: `…, N x` + `Jednostka (GRAMY g)`."""
    document = parse_document(
        [f"Środa\n{_MEAL_HEADER}\nDeser Przepis\n{head}\n{tail}\n{_DAY_TOTAL}"]
    )
    ingredient = document.dishes[0].ingredients[0]

    assert ingredient.raw_qty is not None
    assert ingredient.raw_unit == unit
    assert ingredient.grams == Decimal(grams)
    assert document.findings == ()


def test_linia_wygladajaca_na_skladnik_ale_niezgodna_z_kontraktem_daje_ostrzezenie() -> None:
    """Wiersz zawinięty, którego druga połowa nie przyszła — parser NIE zgaduje.

    D20 rozszerzyła kontrakt §3.2 o dwa warianty, ale nie zniosła reguły:
    linia spoza kontraktu zostaje ZGŁOSZONA z surową treścią, a nie dopasowana
    innym wzorcem.
    """
    document = parse_document(
        [f"Środa\n{_MEAL_HEADER}\nDeser Przepis\nCzekolada ciemna, 2 x\n{_DAY_TOTAL}"]
    )

    assert document.dishes[0].ingredients == []
    warning = next(f for f in document.findings if f.kind == "parse_warning")
    assert warning.severity == "warning"
    assert warning.details["linia"] == "Czekolada ciemna, 2 x"


def test_zwykla_linia_instrukcji_nie_jest_ostrzezeniem() -> None:
    """Bez tego zawężenia raport tonąłby w ostrzeżeniach o prawej kolumnie."""
    document = parse_document(
        [f"Środa\n{_MEAL_HEADER}\nOmlet Przepis\nSmaż aż masa jajeczna się zetnie.\n{_DAY_TOTAL}"]
    )

    assert document.findings == ()
    assert document.dishes[0].instructions == "Smaż aż masa jajeczna się zetnie."


# --- sekcje tekstowe (§3.3, §7) --------------------------------------------------

#: Nagłówek posiłku używany tam, gdzie treścią testu nie są makra.
_MEAL_HEADER = "OBIAD Kcal: 635 W: 71.7 B: 28.8 T: 27.8 Bł: 13.2 ŁG: 36.1"
#: Domknięcie dnia pasujące do `_MEAL_HEADER`. Dzień BEZ „SUMA DNIA" jest dla
#: parsera niedomknięty i słusznie kończy się ostrzeżeniem, więc fragmenty,
#: których tematem nie jest suma kontrolna, muszą ją mieć.
_DAY_TOTAL = "SUMA DNIA Kcal: 635 W: 71.7g B: 28.8g T: 27.8g Bł: 13.2g ŁG: 36.1"

#: Reprezentatywny przykład surowej ekstrakcji z 01_PDF_AUDIT §7 — w całości.
_GOLABKI = """Środa
OBIAD Kcal: 635 W: 71.7 B: 28.8 T: 27.8 Bł: 13.2 ŁG: 36.1
Gołąbki bez zawijania Przepis na 7 porcji
Cebula, 2 x Sztuka (210 g) Kapustę poszatkować, doprawić solą i odstawić.
Jajko, 1 x Sztuka (60 g) Po chwili odsączyć z wody. Cebulę zeszklić, dodać
Kapusta włoska, 1 x Sztuka (1500 g) do mięsa i ugotowanego ostudzonego ryżu.
Zjedz 1 z 7 porcji
Produkty
Ziemniak, 3 x Sztuka (225 g)
SUMA DNIA Kcal: 635 W: 71.7g B: 28.8g T: 27.8g Bł: 13.2g ŁG: 36.1"""


def test_przyklad_z_audytu_paragraf_7_parsuje_sie_w_calosci() -> None:
    """Nazwa, liczba porcji, składniki, sekcja `Produkty` i instrukcja (§7)."""
    document = parse_document([_GOLABKI])
    dish = document.dishes[0]

    assert dish.name == "Gołąbki bez zawijania"
    assert dish.declared_servings == 7
    assert [item.raw_name for item in dish.ingredients] == [
        "Cebula",
        "Jajko",
        "Kapusta włoska",
        # `Produkty` to dodatek do TEGO SAMEGO dania (§3.3) — wliczony w makro.
        "Ziemniak",
    ]
    assert dish.grams_total == Decimal("1995")
    assert "Kapustę poszatkować" in dish.instructions


def test_komentarz_trafia_do_wlasnego_pola_a_nie_do_instrukcji() -> None:
    """Sekcja `Komentarz` (§3.3) jest uwagą dietetyczki, nie przepisem."""
    page = (
        "Poniedziałek\n"
        "OBIAD Kcal: 659 W: 66.7 B: 34.3 T: 30.1 Bł: 15.2 ŁG: 18.1\n"
        "Fasolka po bretońsku Przepis\n"
        "Cebula, 0,3 x Sztuka (31,5 g) Cebulę zeszklić, dodać czosnek.\n"
        "Komentarz\n"
        "Jeżeli danie okaże się zbyt duże objętościowo,\n"
        "proszę dać szklankę fasoli\n"
    )
    dish = parse_document([page]).dishes[0]

    assert dish.instructions == "Cebulę zeszklić, dodać czosnek."
    assert (
        dish.comment == "Jeżeli danie okaże się zbyt duże objętościowo, proszę dać szklankę fasoli"
    )


def test_posilek_moze_miec_wiecej_niz_jedno_danie() -> None:
    """§2.3: dwa dania w jednej kolacji to dwa osobne `staged_recipes`."""
    page = (
        "Wtorek\n"
        "KOLACJA Kcal: 474 W: 46.1 B: 16.6 T: 25.5 Bł: 6.7 ŁG: 18.2\n"
        "Zupa pomidorowa z ryżem Przepis\n"
        "Pomidory z puszki, 0,5 x Opakowanie (120 g)\n"
        "Kanapka z wędliną Przepis\n"
        "Chleb żytni, 1 x Kromka (40 g)\n"
    )
    document = parse_document([page])

    assert [dish.name for dish in document.dishes] == [
        "Zupa pomidorowa z ryżem",
        "Kanapka z wędliną",
    ]
    assert len(document.meals) == 1


# --- sumy kontrolne (§4) ---------------------------------------------------------


def test_zgodna_suma_dnia_nie_produkuje_ostrzezenia() -> None:
    """Suma kcal posiłków = `SUMA DNIA` w 24/24 dniach korpusu (§4)."""
    page = (
        "Poniedziałek\n"
        "ŚNIADANIE Kcal: 468 W: 31.3 B: 17.9 T: 30.4 Bł: 9.0 ŁG: 4.3\n"
        "OBIAD Kcal: 659 W: 66.7 B: 34.3 T: 30.1 Bł: 15.2 ŁG: 18.1\n"
        "SUMA DNIA Kcal: 1127 W: 98.0g B: 52.2g T: 60.5g Bł: 24.2g ŁG: 22.4\n"
    )
    document = parse_document([page])

    assert [checksum.ok for checksum in document.checksums] == [True]
    assert document.findings == ()


def test_rozjazd_sumy_dnia_ponad_tolerancje_daje_ostrzezenie_z_liczbami() -> None:
    """Rozjazd > 2 kcal to sygnał BŁĘDU PARSERA, nie błędu dokumentu (§4)."""
    page = (
        "Poniedziałek\n"
        "ŚNIADANIE Kcal: 468 W: 31.3 B: 17.9 T: 30.4 Bł: 9.0 ŁG: 4.3\n"
        "SUMA DNIA Kcal: 999 W: 98.0g B: 52.2g T: 60.5g Bł: 24.2g ŁG: 22.4\n"
    )
    document = parse_document([page])

    assert [checksum.ok for checksum in document.checksums] == [False]
    (finding,) = document.findings
    assert finding.details["oczekiwane"] == "999"
    assert finding.details["otrzymane"] == "468"


def test_tolerancja_dwoch_kcal_miesci_zaokraglenia_dokumentu() -> None:
    """Kontrakt §4 mówi ±2 kcal — 2 kcal różnicy to nadal zgodność."""
    page = (
        "Poniedziałek\n"
        "ŚNIADANIE Kcal: 468 W: 31.3 B: 17.9 T: 30.4 Bł: 9.0 ŁG: 4.3\n"
        "SUMA DNIA Kcal: 470 W: 31.3g B: 17.9g T: 30.4g Bł: 9.0g ŁG: 4.3\n"
    )
    assert parse_document([page]).checksums[0].ok is True


# --- klasyfikacja stron (§2) -----------------------------------------------------


def test_lista_zakupow_i_wymienniki_sa_pomijane() -> None:
    """§5.4 i §2.5: obu sekcji importer nie czyta — także kontynuacji bez nagłówka."""
    pages = [
        "Dietetyk Natalia Augustyniak\nPlan żywieniowy\n2000 kcal",
        "Podsumowanie jadłospisu Tydzień 1\nPONIEDZIAŁEK WTOREK ŚRODA",
        _GOLABKI,
        "Lista zakupów\nPRODUKT ILOŚĆ WAGA\nCebula 1,39 x sztuka 157,5 g",
        # Druga strona listy zakupów NIE MA nagłówka (dieta.pdf s. 9).
        "Suszone pomidory 3 x sztuka 21 g\n9/10",
        "Wymienniki\nPRODUKT ILOŚĆ WAGA",
    ]

    assert classify_pages(pages) == (
        PageKind.TITLE,
        PageKind.SUMMARY,
        PageKind.DAY,
        PageKind.SHOPPING_LIST,
        PageKind.SHOPPING_LIST,
        PageKind.EXCHANGES,
    )


def test_list_przewodni_jest_rozpoznany_i_nie_daje_posilkow() -> None:
    """`dieta (2).pdf` ma na s. 2 list zamiast podsumowania (§6) — i to jest OK."""
    pages = [
        "Dietetyk Natalia Augustyniak\nPlan żywieniowy\n2000 kcal",
        "Dzień dobry\nPrzez portal przesyłam diety.\n"
        "1. Każdy tydzień diety najlepiej zacząć od dnia owocowo-warzywnego.\n2/9",
        "Podsumowanie jadłospisu Tydzień 1",
    ]
    document = parse_document(pages)

    assert document.pages == (PageKind.TITLE, PageKind.LETTER, PageKind.SUMMARY)
    assert document.days == ()
    assert document.findings == ()


def test_stopka_strony_nie_jest_trescia() -> None:
    """`3/10` to numer strony, nie linia dokumentu."""
    document = parse_document([f"Środa\n{_MEAL_HEADER}\nOmlet Przepis\n6/10"])

    assert document.dishes[0].instructions == ""


# --- podejrzenie wieloporcyjności (§5.1) -----------------------------------------


def _meal_page(grams: int, *, declared: str = "") -> str:
    return (
        "Środa\n"
        "OBIAD Kcal: 638 W: 71.7 B: 28.8 T: 27.8 Bł: 13.2 ŁG: 36.1\n"
        f"Zupa węgierska Przepis{declared}\n"
        f"Ziemniak, 1 x Sztuka ({grams} g)\n"
        "SUMA DNIA Kcal: 638 W: 71.7g B: 28.8g T: 27.8g Bł: 13.2g ŁG: 36.1\n"
    )


def test_ciezki_posilek_bez_liczby_porcji_dostaje_blocker() -> None:
    """§5.1: powyżej progu i bez oznaczenia parser NIE ZGADUJE — pyta w review."""
    document = parse_document([_meal_page(900)])

    (finding,) = document.findings
    assert finding.kind == "multi_portion_suspect"
    assert finding.severity == "blocker"
    assert finding.details["masa_g"] == "900"
    assert finding.details["próg_g"] == "800"


def test_ciezki_posilek_z_jawna_liczba_porcji_nie_ma_issue() -> None:
    """Gołąbki ważą 3305 g, ale dokument mówi „Przepis na 7 porcji" — to nie problem."""
    assert parse_document([_meal_page(900, declared=" na 7 porcji")]).findings == ()


def test_posilek_ponizej_progu_nie_jest_podejrzany() -> None:
    """Dokładnie 800 g to jeszcze nie „powyżej progu"."""
    assert parse_document([_meal_page(800)]).findings == ()


def test_prog_liczy_sie_dla_calego_posilku_nie_dla_pojedynczego_dania() -> None:
    """Tabela §5.1 mierzy masę POSIŁKU — `dieta (7)` KOLACJA to 806 g w dwóch daniach.

    Żadne z dań nie przekracza progu samo, ale `pdf_kcal` opisuje cały posiłek,
    więc zdanie „składniki ważą 806 g przy 554 kcal" jest zdaniem o posiłku.
    Uzasadnienie i pomiar: errata 01_PDF_AUDIT §9.
    """
    page = (
        "Poniedziałek\n"
        "KOLACJA Kcal: 554 W: 54.2 B: 16.4 T: 33.3 Bł: 8.6 ŁG: 21.7\n"
        "Zupa krem z dyni Przepis\n"
        "Dynia, 0,3 x Sztuka (615 g)\n"
        "Kanapka z wędliną Przepis\n"
        "Chleb żytni, 1 x Kromka (191 g)\n"
        "SUMA DNIA Kcal: 554 W: 54.2g B: 16.4g T: 33.3g Bł: 8.6g ŁG: 21.7\n"
    )
    document = parse_document([page])

    (finding,) = document.findings
    assert finding.kind == "multi_portion_suspect"
    assert finding.details["masa_g"] == "806"
    # Issue wisi na CIĘŻSZYM daniu posiłku — to je człowiek będzie rozstrzygał.
    assert finding.dish_index == 0


def test_potwierdzenie_porcji_uzupelnia_brakujacy_naglowek() -> None:
    """`Zjedz 1 z N porcji` to pełnoprawne oznaczenie wieloporcyjności (§3.3)."""
    page = (
        "Środa\n"
        "OBIAD Kcal: 599 W: 63.7 B: 46.9 T: 18.4 Bł: 10.4 ŁG: 29.0\n"
        "Pulpety z dorsza Przepis\n"
        "Dorsz, 4 x Porcja (900 g)\n"
        "Zjedz 1 z 2 porcji\n"
        "SUMA DNIA Kcal: 599 W: 63.7g B: 46.9g T: 18.4g Bł: 10.4g ŁG: 29.0\n"
    )
    document = parse_document([page])

    assert document.dishes[0].declared_servings == 2
    assert document.findings == ()


def test_odmiana_liczebnika_w_naglowku_nie_psuje_parsowania() -> None:
    """Dokument pisze „na 2 porcje", „na 7 porcji" i „na 1 porcję" — wszystkie liczą się."""
    for suffix, expected in ((" na 2 porcje", 2), (" na 7 porcji", 7), (" na 1 porcję", 1)):
        document = parse_document([_meal_page(100, declared=suffix)])
        assert document.dishes[0].declared_servings == expected


# --- raport ----------------------------------------------------------------------


def test_raport_liczy_strony_dni_i_sumy_kontrolne() -> None:
    """`parse_report` niesie liczby, na których stoi UI podglądu (karta §Backend)."""
    from app.modules.importer.parser import build_parse_report

    pages = [
        "Dietetyk\nPlan żywieniowy",
        _GOLABKI,
        "Lista zakupów\nPRODUKT",
        "Wymienniki",
    ]
    report = build_parse_report(
        parse_document(pages),
        match_counts={"exact": 3, "none": 1},
        issue_counts={"blocker": 0, "warning": 0},
    )

    assert report["pages"] == {
        "total": 4,
        "days": 1,
        "skipped_shopping": 1,
        "skipped_exchanges": 1,
    }
    assert report["days"] == 1
    assert report["meals"] == 1
    assert report["staged_recipes"] == 1
    assert report["ingredients"] == 4
    assert report["match"] == {"exact": 3, "none": 1}
    assert report["day_checksums"] == [
        {"day": "Środa", "expected": "635", "computed": "635", "ok": True}
    ]


def test_regex_skladnika_nie_lapie_wiersza_listy_zakupow() -> None:
    """Lista zakupów ma inny format (`Cebula 1,39 x sztuka 157,5 g`) — i tak ją pomijamy."""
    assert INGREDIENT_RE.match("Cebula 1,39 x sztuka 157,5 g") is None
