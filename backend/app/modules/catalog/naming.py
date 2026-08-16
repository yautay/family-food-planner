"""Normalizacja nazw produktów — JEDNA funkcja dla całego systemu.

`canonical_products.normalized_name` jest kluczem unikalności katalogu, a ten
sam klucz liczy importer PDF (B15/B16) przy dopasowywaniu surowych nazw
z dokumentu do istniejących produktów (01_PDF_AUDIT §5.3). Gdyby liczyły go
dwie różne funkcje, importer widziałby duplikaty tam, gdzie baza widzi jeden
wiersz — dlatego moduł jest osobny, czysty i bez zależności.

Zakres normalizacji jest MINIMALNY i celowo taki zostaje (01_PDF_AUDIT §5.3):
trim, zbicie białych znaków, lowercase. Żadnego usuwania znaków diakrytycznych
ani liczby mnogiej — „Maliny" i „Malina" to dla systemu różne produkty,
o ich scaleniu decyduje człowiek w review importu.
"""

from __future__ import annotations


def normalize_name(name: str) -> str:
    """`"  Serek   Kanapkowy "` → `"serek kanapkowy"`.

    `casefold()`, nie `lower()`: dla polskich znaków wynik jest ten sam, ale
    casefold jest zdefiniowany jako operacja porównawcza i radzi sobie
    z przypadkami w rodzaju „ß" — nazwy produktów bywają importowane z etykiet.
    """
    return " ".join(name.split()).casefold()
