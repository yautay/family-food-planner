# ADR-004 — Model wartości odżywczych: kolumny rdzenia + rejestr nutrients

Status: ACCEPTED (2026-08-16)

## Kontekst
Od startu śledzimy: kcal, białko, tłuszcz, węglowodany, błonnik, cukry
(decyzja właściciela 2026-08-16) + indeks glikemiczny (IG) produktu,
z którego liczony jest ładunek glikemiczny (ŁG). Docelowo wybrane
mikroelementy — bez łamiącej przebudowy schematu.

## Decyzja
- Rdzeń jako kolumny `canonical_products` (`kcal_100 … sugars_100`,
  `glycemic_index`): typowane, szybkie, walidowane CHECK-ami.
- Rozszerzenia jako pary w `product_nutrient_values` + słownik `nutrients`
  (code, name, unit) — dodanie mikroelementu = INSERT do słownika, zero
  migracji łamiącej.
- Wszystkie wartości per 100 g (VOLUME: per 100 ml; PIECE: per 100 g +
  obowiązkowa waga sztuki).
- ŁG = IG × max(węglowodany − błonnik, 0) / 100, liczony per porcja;
  brak IG ⇒ wynik oznaczony jako niekompletny, nigdy zgadywany.

## Konsekwencje
+ Silnik nutrition ma stały, typowany rdzeń; mikro dochodzą bez migracji.
− Dwa miejsca przechowywania wartości — silnik czyta oba przez jeden
  adapter (`ProductNutrition` dataclass), nikt inny nie sięga do tabel.
