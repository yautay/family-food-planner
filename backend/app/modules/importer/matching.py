"""Mapowanie surowych nazw z PDF-a na produkty kanoniczne — wyłącznie EXACT.

BATCH_15 robi tu JEDNĄ rzecz: sprowadza surową nazwę do klucza tożsamości
katalogu i sprawdza, czy taki produkt już istnieje. Dopasowanie rozmyte
i propozycje AI należą do BATCH_16 (ADR-011) — w tym batchu nie ma ANI JEDNEGO
wywołania zewnętrznego, importer jest w pełni offline.

Klucz liczy `catalog.naming.normalize_name` — TA SAMA funkcja, która wyznacza
`canonical_products.normalized_name` (01_PDF_AUDIT §5.3). Gdyby importer liczył
go po swojemu, widziałby duplikaty tam, gdzie baza widzi jeden wiersz, i
proponowałby założenie produktu, który natychmiast padłby na UNIQUE.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.modules.catalog.naming import normalize_name

__all__ = ["exact_matches", "normalized_keys"]


def normalized_keys(raw_names: Iterable[str]) -> set[str]:
    """Klucze tożsamości surowych nazw — wejście do zapytania o katalog."""
    return {normalize_name(name) for name in raw_names if name.strip()}


def exact_matches(raw_names: Iterable[str], *, catalog_index: Mapping[str, int]) -> dict[str, int]:
    """Surowa nazwa → id produktu, gdy klucz tożsamości trafia DOKŁADNIE.

    `catalog_index` to `{normalized_name: product_id}` zbudowany przez serwis
    jednym zapytaniem. Brak trafienia = brak wpisu w wyniku (`match_kind=none`)
    — parser nigdy nie zgaduje produktu.
    """
    matches: dict[str, int] = {}
    for name in raw_names:
        product_id = catalog_index.get(normalize_name(name))
        if product_id is not None:
            matches[name] = product_id
    return matches
