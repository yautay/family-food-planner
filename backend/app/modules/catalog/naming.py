"""Normalizacja nazw produktów — JEDNA funkcja dla całego systemu.

`canonical_products.normalized_name` jest kluczem unikalności katalogu, a ten
sam klucz liczy import kopii danych rodziny (`transfer`) przy rozstrzyganiu
kolizji produktów. Gdyby liczyły go dwie różne funkcje, import widziałby
duplikaty tam, gdzie baza widzi jeden wiersz — dlatego moduł jest osobny,
czysty i bez zależności.

Zakres normalizacji jest MINIMALNY i celowo taki zostaje: trim, zbicie białych
znaków, lowercase. Żadnego usuwania znaków diakrytycznych ani liczby mnogiej —
„Maliny" i „Malina" to dla systemu różne produkty, a o ich scaleniu decyduje
człowiek, edytując katalog.
"""

from __future__ import annotations


def normalize_name(name: str) -> str:
    """`"  Serek   Kanapkowy "` → `"serek kanapkowy"`.

    `casefold()`, nie `lower()`: dla polskich znaków wynik jest ten sam, ale
    casefold jest zdefiniowany jako operacja porównawcza i radzi sobie
    z przypadkami w rodzaju „ß" — nazwy produktów bywają importowane z etykiet.
    """
    return " ".join(name.split()).casefold()
