# 08 — Strategia testów

Zasada nadrzędna: logika obliczeniowa (żywienie, jednostki, agregacja,
opakowania, tury) jest deterministyczna, czysta i pokryta testami blisko
100%. Testy są warunkiem DoD każdego batcha — agent raportuje REALNE wyniki
uruchomień, nigdy „powinno przejść".

## 1. Piramida i narzędzia

| Poziom | Narzędzie | Zakres | Uruchomienie |
|---|---|---|---|
| Backend unit | pytest | silnik nutrition, konwersje jednostek, shopping engine, parser PDF — czyste funkcje, bez DB | `task test-unit` (sekundy) |
| Backend integration | pytest + PG (compose test) | serwisy + DB: scope, blokady usuwania, kaskady, migracje | `task test-int` |
| Backend API | pytest + httpx AsyncClient | kontrakty HTTP, auth, CSRF, RBAC, kody błędów | `task test-api` |
| Frontend unit/component | vitest + @vue/test-utils | composables, formatters, komponenty krytyczne (ProductPicker, AmountInput, NutritionBar) | `task fe-test` |
| Typy | vue-tsc, mypy | całość | `task typecheck` |
| E2E | Playwright (TS) | kluczowe flow przez realny stack (compose) | `task test-e2e` |
| Lint | ruff, eslint | całość | `task lint` |

`task check` = unit+int+api+fe-test+typecheck+lint — bramka DoD batcha.
Testy integracyjne: baza z compose (`db-test` na tmpfs), każda klasa testowa
w transakcji z rollbackiem; migracje aplikowane raz na sesję testową.

## 2. Obszary krytyczne (wymóg zlecenia — testować szczególnie dokładnie)

1. **Nutrition**: wartości/100 g → porcja → mnożnik → posiłek → dzień;
   ŁG z IG i węglowodanów przyswajalnych; flagi niekompletności; property-
   based (hypothesis): suma pozycji = wartość dnia, skalowanie liniowe.
2. **Servings**: mnożniki proste i rozkłady rodzinne (suma rozkładu =
   servings), „dopasuj porcję do celu".
3. **Konwersje jednostek**: g/kg/ml/l/szt/opak + jednostki domowe per
   produkt; odmowa zapisu ilości nieprzeliczalnej; prezentacja kg.
4. **Agregacja zakupowa**: wiele przepisów/dni → jeden produkt; jednostki
   mieszane; produkty luzem z planu.
5. **Spiżarnia**: odejmowanie tylko na żądanie; nigdy poniżej zera;
   pozycje retail vs kanoniczne.
6. **Opakowania i resztki**: ceil, resztka, brak retail, wiele wariantów
   opakowań (wybór domyślny = najmniejsza resztka, remis → mniejsze opak.).
7. **Tury**: preset niedziela/środa; świeże/trwałe; zakresy dni; edge:
   plan krótszy niż okno tury.
8. **Uprawnienia**: macierz §4.
9. **Tokeny publiczne**: ważny/wygasły/odwołany/nieistniejący; brak PII;
   rate limit; PATCH checkboxa.
10. **Import PDF**: korpus = 8 realnych PDF-ów w `data/source_pdfs/`
    (testy parsera na plikach, snapshoty wyników); anomalie z 01_PDF_AUDIT
    jako nazwane przypadki testowe; walidacja krzyżowa z
    `data/reference/prototype.db` (84 przepisy / 592 składniki — parser
    musi osiągnąć ≥ tę kompletność).

## 3. E2E (Playwright) — utrzymywany mały i stabilny

Smoke (każdy batch): login → plan dnia → dodanie posiłku → wylogowanie.
Core flows (rozbudowywane w batchach, które je dostarczają):
1. Przepis z inline create produktu → wartości per porcja.
2. Tydzień: kopiuj dzień, szablon, cykl.
3. Zakupy: generacja → pytanie o spiżarnię → preview z resztkami →
   finalizacja → publiczny link → odhaczenie bez logowania.
4. Import PDF: upload dieta.pdf → review (gołąbki 7 porcji!) → zatwierdzenie
   → przepis widoczny.
Konwencje: selektory `data-testid`, bez sleepów (expect z timeoutem),
seed przez API, nie przez UI.

## 4. Macierz uprawnień (testowana w API testach każdego zasobu)

| Operacja | anonim | USER (obcy) | USER (członek rodziny) | właściciel | ADMIN |
|---|---|---|---|---|---|
| odczyt PRIVATE | 401 | 404 | 404 | 200 | 200 |
| odczyt HOUSEHOLD | 401 | 404 | 200 | 200 | 200 |
| edycja HOUSEHOLD | 401 | 404 | 200 | 200 | 200 |
| zmiana scope / delete | 401 | 404 | 403 | 200 | 200 |
| nutrition produktu (edycja) | 401 | 403 | 403 | 403 | 200 |
| publiczna lista (token) | 200 | 200 | 200 | 200 | 200 |

## 5. Dane testowe

Fabryki (factory-boy lub proste funkcje) per moduł w `tests/factories.py`;
`task db-seed-demo` — deterministyczny seed demo (rodzina 2+3, ~15 produktów,
5 przepisów, tydzień planu, lista) do ręcznego klikania i E2E; odwracalny.

## 6. Definicja zieloności

Zero known-failing testów na masterze. Test flaky = naprawiany albo usuwany
świadomą decyzją w PROGRESS — nigdy retry-until-green.
