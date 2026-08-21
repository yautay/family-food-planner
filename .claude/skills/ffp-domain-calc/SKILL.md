---
name: ffp-domain-calc
description: Reguły logiki obliczeniowej Family Food Planner — Decimal end-to-end, normalizacja jednostek, wzory nutrition (kcal/makro/IG→ŁG), determinizm silnika zakupowego, zaokrąglenia, property-based testy. Ładuj przy każdym batchu liczącym ilości lub wartości.
---

<!-- verified: 2026-08-21 (REVIEW R2 — uzgodnione z kodem po B05–B07:
     units.py + nutrition_adapter.py + nutrition/{engine,types}.py;
     silnik ZAKUPOWY dalej nie istnieje — dokłada go B10)
     stack: Python 3.13 · Decimal (stdlib) · hypothesis 6.165 (jest w
            `[dependency-groups] dev` od B05) · pytest-cov
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
- **`nutrition/engine.py` ISTNIEJE od B05 i jest wzorcem** (audyt R2:
  importuje wyłącznie `decimal`, `collections.abc`, `AppError` i własne typy —
  zero ORM, zero zegara). Kontrakt wyjścia `NutritionValues`
  (`nutrition/types.py`) jest wspólny dla B06/B07/B10/B13 — zmiany WYŁĄCZNIE
  addytywne. Gotowe do reużycia: `ingredient_nutrition`, `aggregate`,
  `recipe_nutrition`, `portion_nutrition`, `scale`, `glycemic_load`,
  `goal_status`, `fit_servings_to_target`, `round_for_output`. Zaokrągla
  JEDNA funkcja — `round_for_output` na krawędzi serializacji.

## Jednostki (ADR-005) — kod jest w `app/modules/catalog/units.py`

- Konwersje mają JEDNO miejsce (`normalize_amount`, `to_grams`,
  `to_basis_amount`) i nie wolno ich powtarzać w silniku. Ilość bez
  jednoznacznej reprezentacji NIE ISTNIEJE w danych: `UnitConversionError`
  (AppError → 422) i zapis pada.
- **Dwie różne osie, nie mieszać** (ustalenie R1): `base_unit` = oś
  PRZECHOWYWANIA ilości podanej w jednostce produktu (masa → g, objętość → ml,
  sztuki → szt.), `basis_unit` = oś WARTOŚCI „na 100" (objętość → ml,
  **masa i sztuki → g**). Przelicznik jednostki domowej daje ilość na osi
  `basis_unit`, więc dla produktu w sztukach — gramy.
- Wartości odżywcze czyta WYŁĄCZNIE adapter `ProductNutrition`
  (`catalog/nutrition_adapter.py`: `nutrition_for`, `measure_for`,
  `digestible_carbs_100`); silnik nie zna kolumn `canonical_products`.
  `measure_for` przyjmuje dataclassy `UnitWeight`, nie wiersze ORM.
- Jednostki domowe (łyżka/garść/plaster/opakowanie) są WŁASNOŚCIĄ produktu
  (`product_unit_weights`); nigdy globalna tabela przeliczników. Próbki
  z importu → mediana + samples_count.
- Prezentacja (kg dla ≥1000 g) to sprawa frontendu (`src/lib/format.ts`) —
  silniki zawsze w g/ml.

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
