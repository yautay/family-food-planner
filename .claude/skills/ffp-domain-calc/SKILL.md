---
name: ffp-domain-calc
description: Reguły logiki obliczeniowej Family Food Planner — Decimal end-to-end, normalizacja jednostek, wzory nutrition (kcal/makro/IG→ŁG), determinizm silnika zakupowego, zaokrąglenia, property-based testy. Ładuj przy każdym batchu liczącym ilości lub wartości.
---

<!-- verified: 2026-08-16 (przegląd w BATCH_01: kodu obliczeniowego jeszcze nie
     ma, więc treść bez zmian; realne uzgodnienie z kodem robią R2/R3)
     stack: Python 3.13 · Decimal (stdlib) · hypothesis dołoży batch z pierwszym
            silnikiem (B04/B05)
     źródła nadrzędne: ADR-004, ADR-005, ADR-008, 02_DOMAIN §6 i §9, 08_TESTING §2
     uruchamianie testów: `task test-unit` (silniki nie dotykają bazy) -->

# FFP — kontrakt obliczeń domenowych

## Arytmetyka (ADR-008) — zero tolerancji

- `Decimal` end-to-end; `float` w jakimkolwiek kroku domenowym = błąd
  blokujący. Literały: `Decimal("0.1")`, nigdy `Decimal(0.1)`.
- Zaokrąglenia WYŁĄCZNIE na krawędzi prezentacji/serializacji:
  kcal → 1; makra/błonnik/cukry → 0,1 g; ŁG → 0,1. Kroki pośrednie bez
  zaokrągleń. `ROUND_HALF_UP`.
- Silniki (`nutrition/engine.py`, `shopping/engine.py`) = czyste funkcje:
  zero I/O, zero ORM, zero `datetime.now()`/losowości — czas i dane wchodzą
  parametrami. Wejścia/wyjścia: dataclassy, nie modele ORM.

## Jednostki (ADR-005)

- Osie ilości: masa → g, objętość → ml, sztuki → szt. (waga sztuki
  z `piece_weight_g` produktu). Ilość bez jednoznacznej reprezentacji
  na osi NIE ISTNIEJE w danych — zapis odrzucany w serwisie.
- Jednostki domowe (łyżka/garść/plaster/opakowanie) są WŁASNOŚCIĄ produktu
  (`product_unit_weights`); nigdy globalna tabela przeliczników. Próbki
  z importu → mediana + samples_count.
- Prezentacja (kg dla ≥1000 g) to sprawa frontendu — silniki zawsze w g/ml.

## Wzory nutrition (02_DOMAIN §6)

```
wartości(g, produkt)   = g/100 × wartości_100 produktu
przepis (całość)       = Σ składników
porcja                 = całość / base_servings
pozycja planu          = porcja × servings (mnożnik Decimal)
posiłek / dzień        = Σ pozycji
węglow. przyswajalne   = max(carbs − fiber, 0)
ŁG                     = IG × węglow._przyswajalne_g / 100   (per porcja)
```

- Brak IG lub brak wartości produktu ⇒ wynik z flagą `complete=False`
  i listą `missing` — NIGDY nie zgaduj ani nie wstawiaj zera w miejsce
  braku (0 ≠ brak danych!).
- Wartości NIE są cache'owane w encjach (niezmiennik 02_DOMAIN §13.2);
  jedyny snapshot = `pdf_kcal`/`pdf_macros` importu (walidacja, >10%
  rozjazdu ⇒ issue).

## Silnik zakupowy (02_DOMAIN §9)

- Pipeline: plan → porcje → składniki → normalizacja → agregacja per
  produkt → [spiżarnia TYLKO gdy `use_pantry=True` — decyzja użytkownika,
  nigdy domyślnie] → „mam już w domu" → tury (perishability: override
  produktu ?? kategoria) → opakowania → preview z niejasnościami.
- Opakowania: `packages = ceil(need / package_size)`; resztka = kupione −
  potrzeba, zawsze zwracana. Wybór wariantu opakowania: najmniejsza
  resztka, remis → mniejsze opakowanie.
- Spiżarnia: odejmowanie nigdy poniżej zera; wynik raportuje co i ile odjęto.
- **Determinizm**: ten sam input ⇒ identyczny output; wszystkie sortowania
  stabilne (po id/nazwie); żadnych setów bez sortowania na wyjściu.
- Niejednoznaczność (brak retail, brak kategorii, nieprzeliczalna pozycja)
  ⇒ pozycja w `issues` preview — silnik NIE decyduje za użytkownika.

## Testy (08_TESTING §2)

- Property-based (hypothesis) obowiązkowe dla: liniowości skalowania
  (2× porcji = 2× wartości), sumowania (dzień = Σ posiłków), agregacji
  zakupowej (Σ pozycji = Σ zapotrzebowań).
- Nazwane przypadki brzegowe: mnożnik 0, base_servings=1, produkt bez IG,
  plan krótszy niż okno tury, potrzeba < najmniejsze opakowanie,
  dokładna wielokrotność opakowania (resztka 0).
- Snapshot testy silnika zakupowego na seedzie demo — zmiana snapshotu
  wymaga uzasadnienia w Completion notes.
