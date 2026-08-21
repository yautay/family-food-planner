# ADR-008 — Silniki nutrition i shopping jako czyste funkcje na Decimal

Status: ACCEPTED (2026-08-16)

## Kontekst
Wymóg: logika obliczeniowa deterministyczna i bardzo dobrze pokryta
testami; błędy w kcal/agregacji podważają sens aplikacji.

## Decyzja
- `modules/nutrition/engine.py` i `modules/shopping/engine.py`: czyste
  funkcje (wejście: dataclassy/typy proste, wyjście: struktury wyników),
  zero I/O, zero ORM, zero datetime.now() — czas i dane wchodzą parametrami.
- Arytmetyka: `Decimal` end-to-end; zaokrąglenia tylko na krawędzi
  prezentacji/serializacji (reguły w 02_DOMAIN §6).
- Serwisy modułów robią I/O (pobierają dane, wołają engine, zapisują wynik).
- Wyniki żywieniowe nigdy nie są cache'owane w encjach (niezmiennik
  02_DOMAIN §13.2) — jedyny snapshot to metadane importu PDF (walidacja).

## Stan faktyczny
- `nutrition/engine.py` istnieje od BATCH_05, `shopping/engine.py` od BATCH_10.
  Oba importują wyłącznie `decimal`, `collections.abc`, własne typy i enumy
  domenowe — zero sesji, zero zegara.
- Krawędź zaokrągleń: nutrition — `round_for_output`; shopping —
  `quantize_amount`/`quantize_package` (skala kolumn NUMERIC) plus `ceil` liczby
  opakowań, bo opakowań nie kupuje się po pół. Kroki pośrednie zostają w pełnej
  precyzji `Decimal`, więc `1/3` porcji nie zamienia się w błąd na gramach.
- Wejście silnika zakupowego jest SERIALIZOWALNE (`dump_input`/`load_input` →
  `shopping_generations.params`, wersjonowane `{"v": 1}`): ten sam podgląd
  odtwarza się z bazy bez ponownego pytania planu, co czyni determinizm
  testowalnym także na poziomie API.

## Konsekwencje
+ Testy jednostkowe silników bez DB (szybkie, property-based z hypothesis).
+ „Zmiana mnożnika zmienia wszystko spójnie" wynika z konstrukcji.
− Dyscyplina granicy engine/service pilnowana w Review batchach.
