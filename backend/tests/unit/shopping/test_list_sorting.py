"""Sortowanie pozycji listy zakupowej — czyste funkcje, bez bazy (08_TESTING §1).

Reguła z karty B11 §Backend („Sortowanie") ma cztery części i każda ma tu
własny scenariusz: profil pełny, profil częściowy, brak sklepu oraz porządek
wewnątrz sekcji („mam już w domu" na dół).
"""

from __future__ import annotations

import pytest

from app.modules.catalog.stores_service import CategoryOrderEntry
from app.modules.shopping.sorting import SortableItem, sort_into_sections

pytestmark = pytest.mark.unit

#: Kategorie: (id, globalna pozycja). Globalna kolejność to 1 → 2 → 3.
WARZYWA = 1
PIECZYWO = 2
NAPOJE = 3
GLOBAL = {WARZYWA: 0, PIECZYWO: 5, NAPOJE: 9}


def _entry(category_id: int, position: int) -> CategoryOrderEntry:
    return CategoryOrderEntry(
        category_id=category_id, category_name=f"kategoria-{category_id}", position=position
    )


def _item(
    item_id: int, category_id: int, *, position: int = 0, already_have: bool = False
) -> SortableItem:
    return SortableItem(
        item_id=item_id,
        category_id=category_id,
        already_have=already_have,
        position=position,
    )


def test_pelny_profil_sklepu_decyduje_o_kolejnosci_sekcji() -> None:
    """Profil obejmujący wszystkie kategorie listy ustawia sekcje wbrew kolejności globalnej."""
    items = [_item(10, WARZYWA), _item(11, PIECZYWO), _item(12, NAPOJE)]
    profile = [_entry(NAPOJE, 0), _entry(PIECZYWO, 1), _entry(WARZYWA, 2)]

    sections = sort_into_sections(items, profile=profile, global_positions=GLOBAL)

    assert [section.category_id for section in sections] == [NAPOJE, PIECZYWO, WARZYWA]


def test_kategorie_spoza_profilu_ida_na_koniec_wg_kolejnosci_globalnej() -> None:
    """Profil zawiera WYŁĄCZNIE dopisane kategorie — reszta na koniec (karta B11 §Context)."""
    items = [_item(10, WARZYWA), _item(11, PIECZYWO), _item(12, NAPOJE)]
    # W profilu tylko napoje: warzywa i pieczywo są „poza sklepem".
    profile = [_entry(NAPOJE, 0)]

    sections = sort_into_sections(items, profile=profile, global_positions=GLOBAL)

    # Napoje z profilu przed wszystkim; potem globalna kolejność 0 → 5.
    assert [section.category_id for section in sections] == [NAPOJE, WARZYWA, PIECZYWO]


def test_lista_bez_sklepu_uzywa_wylacznie_kolejnosci_globalnej() -> None:
    """Sklep bez profilu i lista bez sklepu to ten sam, poprawny przypadek."""
    items = [_item(10, NAPOJE), _item(11, WARZYWA), _item(12, PIECZYWO)]

    sections = sort_into_sections(items, profile=(), global_positions=GLOBAL)

    assert [section.category_id for section in sections] == [WARZYWA, PIECZYWO, NAPOJE]


def test_w_sekcji_mam_w_domu_ida_na_dol_a_reszta_po_position() -> None:
    """„Mam już w domu" zostaje widoczne, ale nie zaśmieca góry sekcji (AC 2)."""
    items = [
        _item(10, WARZYWA, position=0, already_have=True),
        _item(11, WARZYWA, position=1),
        _item(12, WARZYWA, position=2),
    ]

    sections = sort_into_sections(items, profile=(), global_positions=GLOBAL)

    assert sections[0].item_ids == (11, 12, 10)


def test_kategoria_bez_pozycji_globalnej_nie_wysadza_sortowania() -> None:
    """Niekompletny słownik kategorii daje kolejność stabilną, a nie wyjątek."""
    items = [_item(10, NAPOJE), _item(11, 999)]

    sections = sort_into_sections(items, profile=(), global_positions=GLOBAL)

    assert [section.category_id for section in sections] == [NAPOJE, 999]


def test_kolejnosc_jest_deterministyczna_przy_rownych_pozycjach() -> None:
    """Remis pozycji rozstrzyga id — inaczej ta sama lista wyglądałaby różnie."""
    items = [_item(10, PIECZYWO), _item(11, WARZYWA)]
    equal_positions = {WARZYWA: 3, PIECZYWO: 3}

    first = sort_into_sections(items, profile=(), global_positions=equal_positions)
    second = sort_into_sections(list(reversed(items)), profile=(), global_positions=equal_positions)

    assert [section.category_id for section in first] == [WARZYWA, PIECZYWO]
    assert [section.category_id for section in second] == [WARZYWA, PIECZYWO]
