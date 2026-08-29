"""Uczenie przeliczników jednostek domowych z próbek — CZYSTE funkcje.

01_PDF_AUDIT §5.2 zmierzył rzecz, z której bierze się cały ten moduł: ta sama
para (produkt, jednostka) ma w materiale RÓŻNE gramatury — jajko waży 50 albo
60 g, łyżka mąki 5, 12 albo 15 g. Przelicznik jest więc statystyką, a nie
stałą, i `product_unit_weights` trzyma jej **medianę** razem z liczbą próbek.
Mediana, nie średnia: jeden wiersz z pomyłką w gramaturze przesunąłby średnią,
a mediany nie ruszy.

**Aproksymacja, którą trzeba znać** (Implementation Notes karty BATCH_16):
tabela nie przechowuje pojedynczych próbek, tylko medianę i licznik. Łącząc
stary wiersz z nowymi próbkami traktujemy więc starą medianę jak
`samples_count` powtórzeń tej samej liczby. Wynik nie zawsze równa się medianie
prawdziwego zbioru wszystkich pomiarów, ale jest jej odporną przybliżeniem
i nie wymaga tabeli próbek (ta byłaby zmianą schematu, czyli decyzją
właściciela — patrz 02_DECISIONS).

Zero I/O, zero ORM — zapis robi `catalog/service.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "GRAMS_PER_UNIT_QUANTUM",
    "merge_samples",
    "quantize_grams_per_unit",
    "weighted_median",
]

#: Skala kolumny `product_unit_weights.grams_per_unit` (NUMERIC(8,2)).
GRAMS_PER_UNIT_QUANTUM = Decimal("0.01")


def quantize_grams_per_unit(value: Decimal) -> Decimal:
    """Sprowadź przelicznik do skali kolumny (ADR-008: zaokrąglamy na krawędzi)."""
    return value.quantize(GRAMS_PER_UNIT_QUANTUM, rounding=ROUND_HALF_UP)


def weighted_median(samples: Sequence[tuple[Decimal, int]]) -> Decimal:
    """Mediana zbioru podanego jako pary (wartość, ile razy występuje).

    Postać ważona jest tu konieczna, nie wygodna: stary wiersz reprezentuje
    `samples_count` pomiarów, a materializowanie ich listą znaczyłoby alokację
    proporcjonalną do licznika, którym da się sterować przez API.

    Parzysta liczba próbek daje średnią dwóch środkowych (klasyczna definicja),
    nieparzysta — element środkowy.
    """
    entries = sorted((value, count) for value, count in samples if count > 0)
    total = sum(count for _, count in entries)
    if total <= 0:
        raise ValueError("Mediana pustego zbioru próbek nie istnieje.")

    lower_index = (total - 1) // 2
    upper_index = total // 2
    lower: Decimal | None = None
    seen = 0
    for value, count in entries:
        seen += count
        if lower is None and seen > lower_index:
            lower = value
        if seen > upper_index:
            # `lower_index <= upper_index`, więc dolny środek jest już znany;
            # gdy oba wypadły w tej samej próbce, `lower` jest po prostu `value`.
            return ((value if lower is None else lower) + value) / 2
    raise ValueError("Nie udało się wyznaczyć mediany — niespójne liczniki próbek.")


def merge_samples(
    new_values: Sequence[Decimal],
    *,
    existing_median: Decimal | None = None,
    existing_count: int = 0,
) -> tuple[Decimal, int]:
    """Nowe próbki (+ ewentualny stary wiersz) → (mediana, liczba próbek).

    Zwracana mediana jest już w skali kolumny; licznik rośnie o liczbę NOWYCH
    pomiarów, bo tyle ich faktycznie doszło.
    """
    if not new_values:
        raise ValueError("Brak nowych próbek — nie ma czego łączyć.")

    pairs: list[tuple[Decimal, int]] = [(value, 1) for value in new_values]
    if existing_median is not None and existing_count > 0:
        pairs.append((existing_median, existing_count))

    return quantize_grams_per_unit(weighted_median(pairs)), existing_count + len(new_values)
