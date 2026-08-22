"""Kolejność pozycji na liście zakupowej — CZYSTE funkcje, bez I/O.

Reguła jest jedna i pochodzi z karty B11 §Backend („Sortowanie"):

1. Sekcje idą w kolejności PROFILU sklepu (`store_category_order`, B09).
2. Kategorie, których w profilu NIE MA, idą na koniec w kolejności globalnej
   (`product_categories.position`). To nie jest brak danych, a kontrakt: profil
   zawiera wyłącznie kategorie do niego dopisane (karta B11 §Context).
3. Lista bez sklepu = cała kolejność globalna (profil pusty to poprawny stan).
4. W sekcji: pozycje „mam już w domu" na DÓŁ, reszta po `position` z generacji.

Dlaczego osobny moduł, a nie metoda serwisu: to jedyna nietrywialna arytmetyka
tego batcha, a testuje się ją bez bazy (08_TESTING §1 — piramida). Serwis mapuje
wiersze na `SortableItem`, dostaje kolejność i układa według niej encje.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.modules.catalog.stores_service import CategoryOrderEntry

__all__ = [
    "SortableItem",
    "SortedSection",
    "sort_into_sections",
]

#: Kategoria bez pozycji w słowniku globalnym trafia za wszystkie znane. Nie
#: powinno się zdarzyć (kategoria zawsze ma `position`), ale sortowanie nie ma
#: prawa wysypać się na niekompletnym słowniku.
_UNKNOWN_GLOBAL_POSITION = 10**9


@dataclass(frozen=True)
class SortableItem:
    """Minimum, którego potrzebuje sortowanie — bez ORM-a i bez ilości.

    `position` to kolejność nadana przez finalizację generacji (B10), czyli
    porządek, w jakim silnik wypisał pozycje w turze.
    """

    item_id: int
    category_id: int
    already_have: bool
    position: int


@dataclass(frozen=True)
class SortedSection:
    """Jedna sekcja listy: kategoria + identyfikatory pozycji w kolejności."""

    category_id: int
    item_ids: tuple[int, ...]


def _section_rank(
    category_id: int,
    *,
    profile_positions: Mapping[int, int],
    global_positions: Mapping[int, int],
) -> tuple[int, int, int]:
    """Klucz sortowania sekcji: najpierw profil, potem reszta wg słownika.

    Pierwszy element to KUBEŁEK (0 = w profilu, 1 = poza profilem) — bez niego
    kategoria z globalną pozycją 0 wyprzedziłaby kategorię z profilu.
    `category_id` na końcu daje determinizm przy równych pozycjach.
    """
    in_profile = profile_positions.get(category_id)
    if in_profile is not None:
        return (0, in_profile, category_id)
    return (1, global_positions.get(category_id, _UNKNOWN_GLOBAL_POSITION), category_id)


def _item_rank(item: SortableItem) -> tuple[int, int, int]:
    """Klucz pozycji w sekcji: „mam w domu" na dół, reszta po `position`."""
    return (1 if item.already_have else 0, item.position, item.item_id)


def sort_into_sections(
    items: Sequence[SortableItem],
    *,
    profile: Sequence[CategoryOrderEntry],
    global_positions: Mapping[int, int],
) -> list[SortedSection]:
    """Pozycje listy → sekcje per kategoria w kolejności przejścia po sklepie.

    `profile` to wynik `StoresService.category_order` (pusta sekwencja = lista
    bez sklepu albo sklep bez profilu — oba są poprawnym stanem);
    `global_positions` to `product_categories.position` dla kategorii z listy.
    """
    profile_positions = {entry.category_id: entry.position for entry in profile}

    grouped: dict[int, list[SortableItem]] = {}
    for item in items:
        grouped.setdefault(item.category_id, []).append(item)

    ordered_categories = sorted(
        grouped,
        key=lambda category_id: _section_rank(
            category_id,
            profile_positions=profile_positions,
            global_positions=global_positions,
        ),
    )
    return [
        SortedSection(
            category_id=category_id,
            item_ids=tuple(item.item_id for item in sorted(grouped[category_id], key=_item_rank)),
        )
        for category_id in ordered_categories
    ]
