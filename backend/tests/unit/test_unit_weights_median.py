"""Uczenie przeliczników jednostek domowych z próbek importu (01_PDF_AUDIT §5.2).

Reguła, której pilnują te testy: przelicznik jest MEDIANĄ pomiarów, a nie
średnią. Materiał źródłowy ma dla tej samej pary (produkt, jednostka) różne
gramatury — jajko 50 albo 60 g, łyżka mąki 5, 12 albo 15 g — więc jedna
pomyłka w dokumencie nie może przesunąć przelicznika dla wszystkich przepisów.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.catalog.unit_weights import merge_samples, quantize_grams_per_unit, weighted_median

pytestmark = pytest.mark.unit


def _d(values: str) -> list[Decimal]:
    """`"50 60 70"` → lista `Decimal` (skrót czytelności asercji)."""
    return [Decimal(part) for part in values.split()]


# --- sama mediana ------------------------------------------------------------------


def test_nieparzysta_liczba_probek_daje_element_srodkowy() -> None:
    """Trzy pomiary łyżki mąki z §5.2 (5, 12, 15 g) → 12 g."""
    samples = [(value, 1) for value in _d("5 12 15")]

    assert weighted_median(samples) == Decimal("12")


def test_parzysta_liczba_probek_daje_srednia_dwoch_srodkowych() -> None:
    """Jajko waży w materiale 50 albo 60 g — mediana dwóch pomiarów to 55 g."""
    samples = [(value, 1) for value in _d("50 60")]

    assert weighted_median(samples) == Decimal("55")


def test_jedna_odstajaca_probka_nie_rusza_mediany() -> None:
    """Po to jest mediana: literówka „1050 g" zamiast „105 g" nie psuje przelicznika."""
    samples = [(value, 1) for value in _d("105 105 120 1050")]

    assert weighted_median(samples) == Decimal("112.5")


def test_probka_z_licznikiem_wazy_tyle_ile_powtorzen() -> None:
    """Postać ważona MUSI dać ten sam wynik, co lista powtórzeń.

    Na tym stoi cała aproksymacja łączenia: stary wiersz reprezentuje
    `samples_count` pomiarów, których tabela już nie pamięta.
    """
    weighted = weighted_median([(Decimal("100"), 3), (Decimal("200"), 1)])
    expanded = weighted_median([(value, 1) for value in _d("100 100 100 200")])

    assert weighted == expanded == Decimal("100")


def test_pusty_zbior_probek_to_blad_a_nie_zero() -> None:
    """Mediana pustego zbioru nie istnieje — zero byłoby wymyśloną gramaturą."""
    with pytest.raises(ValueError, match="pustego"):
        weighted_median([])


# --- łączenie z istniejącym wierszem ------------------------------------------------


def test_pierwsze_probki_zakladaja_wiersz_od_zera() -> None:
    """Bez starego wiersza mediana liczy się z samych nowych pomiarów."""
    median, count = merge_samples(_d("105 120"))

    assert median == Decimal("112.50")
    assert count == 2


def test_laczenie_ze_starym_wierszem_uwzglednia_jego_licznik() -> None:
    """Stara mediana 100 g z 5 próbek + jedna nowa 200 g → nadal 100 g.

    To jest właśnie zachowanie, którego oczekujemy: pojedynczy nowy import nie
    przewraca przelicznika nauczonego z kilku poprzednich.
    """
    median, count = merge_samples(_d("200"), existing_median=Decimal("100"), existing_count=5)

    assert median == Decimal("100.00")
    assert count == 6


def test_wiele_nowych_probek_potrafi_przesunac_stara_mediane() -> None:
    """Odwrotna strona tej samej reguły: przewaga nowych pomiarów wygrywa."""
    median, count = merge_samples(
        _d("200 200 200 200"), existing_median=Decimal("100"), existing_count=1
    )

    assert median == Decimal("200.00")
    assert count == 5


def test_wynik_jest_w_skali_kolumny() -> None:
    """`grams_per_unit` to NUMERIC(8,2) — zaokrąglamy na krawędzi zapisu (ADR-008)."""
    median, _ = merge_samples(_d("10 10.005"))

    assert median == quantize_grams_per_unit(median)
    assert median == Decimal("10.00")


def test_brak_nowych_probek_to_blad_wolajacego() -> None:
    """Wołanie „połącz nic z niczym" jest pomyłką w kodzie, nie stanem danych."""
    with pytest.raises(ValueError, match="Brak nowych próbek"):
        merge_samples([], existing_median=Decimal("100"), existing_count=1)
