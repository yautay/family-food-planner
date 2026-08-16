# ADR-012 — Usuwanie: blokada przy referencjach + archiwizacja, bez soft delete

Status: ACCEPTED (2026-08-16)

## Kontekst
Wymóg właściciela: bez wersjonowania przepisów; produkt nieużyty można
usunąć, użyty — nie; nie komplikować ponad potrzebę.

## Decyzja
- DELETE encji słownikowych/domenowych: serwis liczy referencje (FK +
  wystąpienia w payloadach JSONB szablonów); >0 ⇒ 409 `conflict`
  z `details.used_in` (czytelna lista miejsc użycia dla UI).
- Alternatywa: `is_archived` — znika z pickerów i list domyślnych,
  zostaje w danych historycznych; odwracalne.
- FK w bazie: `RESTRICT` na referencjach domenowych (druga linia obrony),
  `CASCADE` tylko rodzic→dziecko kompozycji (przepis→składniki,
  lista→pozycje, dzień→posiłki).
- Soft delete (deleted_at) NIE istnieje w systemie.

## Konsekwencje
+ Brak osieroconych referencji i brak „ukrytych" danych.
− Zliczanie referencji w JSONB szablonów wymaga indeksu GIN i testu —
  przypięte w BATCH_07 (szablony) i sprawdzane w Review 2.
