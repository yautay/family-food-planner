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
   rate limit; PATCH checkboxa. **Zweryfikowane realnymi requestami
   w REVIEW R3** (200/410/410/404/422, zero PII w odpowiedzi, 429 po 60
   żądaniach na WSPÓLNYM liczniku GET+PATCH, `***` w obu logach). **Pokryte
   w BATCH_11**:
   `tests/api/shopping/test_public_lists_api.py` (komplet, w tym asercja
   DOKŁADNEGO zbioru kluczy odpowiedzi i 429 po 60 żądaniach/min) oraz
   `tests/api/shopping/test_shopping_lists_api.py` (macierz uprawnień listy,
   sortowanie wg profilu sklepu, 409 przy usuwaniu użytego sklepu).
10. **Import PDF**: korpus = 8 realnych PDF-ów w `data/source_pdfs/`
    (testy parsera na plikach, snapshoty wyników); anomalie z 01_PDF_AUDIT
    jako nazwane przypadki testowe; walidacja krzyżowa z
    `data/reference/prototype.db` (84 przepisy / 592 składniki — parser
    musi osiągnąć ≥ tę kompletność). **Pokryte w BATCH_15**:
    `tests/unit/test_pdf_parser.py` (regexy i maszyna stanów na wyciętych
    tekstach), `tests/integration/test_pdf_corpus.py` (24 dni / 96 posiłków /
    642 wiersze / 178 nazw / 24 sumy kontrolne + cztery nazwane anomalie §5.1),
    `tests/integration/test_prototype_crosscheck.py` (101 ≥ 84 przepisy,
    629 ≥ 592 składniki; różnice RAPORTOWANE w wyjściu testu, nie zamiatane)
    oraz `tests/api/test_import_api.py` (sniffing, limit, anty-IDOR
    i niezmiennik „zero encji domenowych"). Testy korpusowe są `integration`,
    mimo że nie dotykają bazy: czytają dysk i uruchamiają pdfplumber, więc nie
    mieszczą się w kontrakcie `unit` (§1).

## 3. E2E (Playwright) — utrzymywany mały i stabilny

Smoke (każdy batch): login → plan dnia → dodanie posiłku → wylogowanie.
Core flows (rozbudowywane w batchach, które je dostarczają):
1. Przepis z inline create produktu → wartości per porcja.
2. Tydzień: kopiuj dzień, szablon, cykl.
3. Zakupy: generacja → pytanie o spiżarnię → preview z resztkami →
   finalizacja → publiczny link → odhaczenie bez logowania.
   Dwa specy: `shopping-generate.spec.ts` (B10, do finalizacji) i
   `shopping-list-sharing.spec.ts` (B11, od strony listy do odwołania linku).
   Publiczny link otwiera się w OSOBNYM kontekście przeglądarki
   (`browser.newContext()` — bez `storageState`), inaczej test przechodziłby
   także wtedy, gdy strona publiczna po cichu korzysta z cookies sesji.
4. Import PDF: upload dieta.pdf → review (gołąbki 7 porcji!) → zatwierdzenie
   → przepis widoczny.
Konwencje: selektory `data-testid`, bez sleepów (expect z timeoutem),
seed przez API, nie przez UI.

### 3.1 Izolacja danych (stan faktyczny po review R2, 2026-08-21)

Suita jedzie na bazie DEWELOPERSKIEJ i na JEDNYM koncie (07_SECURITY §2 — w
repozytorium nie ma i nie może być działającego hasła), a katalog produktów
jest globalny. Specy nie są więc od siebie niezależne i pięć reguł jest
WIĄŻĄCE dla każdego nowego specu:

1. **Jedno logowanie na przebieg.** Projekt `setup` (`e2e/auth.setup.ts`)
   loguje się raz i zapisuje `storageState`; pozostałe projekty z niego
   startują. `/auth/login` ma limit 5/min/IP, więc logowanie per spec kończyło
   się losowymi 429. Spec testujący SAMO logowanie zeruje `storageState`
   u siebie (`EMPTY_STATE` z `e2e/auth-state.ts`).
2. **Przebieg jednowątkowy** (`fullyParallel: false`, `workers: 1`).
   Szukajki produktów i przepisów są trigramowe, a inline create wymaga ZERA
   wyników — encja utworzona równolegle przez inny spec pod podobną nazwą
   ukrywa opcję „+ Dodaj" i test pada bez winy aplikacji.
3. **Własny prefiks nazw + sprzątanie po obu stronach.** Wyjątek: listy
   zakupowe nie mają prefiksu (nazwę nadaje im finalizacja z zakresu dat), więc
   `clearShoppingLists` rozpoznaje je po ROKU z nazwy — oknem dat E2E (lata
   2030+). Sprzątanie list MUSI iść przed produktami: pozycje trzymają produkt
   i wariant sklepowy FK RESTRICT. Każdy spec podpisuje
   swoje encje wspólnym prefiksem (`E2E <obszar>`) i wywołuje
   `cleanupE2eData` z `e2e/cleanup.ts` w `beforeAll` (leczy stan po przebiegu
   przerwanym w połowie) ORAZ w `afterAll` (wykonuje się także po nieudanym
   teście). Kolejność usuwania wymuszają blokady: cykle → szablony → posiłki
   planu → przepisy → produkty.
4. **Daty planu z okna zarezerwowanego dla E2E (lata 2030+).** „Dziś" zostaje
   dla ręcznego klikania. Dzięki tej konwencji `setup` czyści całe okno
   (`purgeE2eLeftovers`, rok po roku — `GET /plan/days` przyjmuje max 366 dni).
5. **Spec, który przestawia konto do innej rodziny, biegnie OSOBNO.**
   `households.spec.ts` ma własny projekt Playwrighta zależny od `chromium`,
   bo encje ze scope zapisują `household_id` także dla `private` (ADR-006)
   i sprzątające `DELETE /admin/households/{id}` trafiałoby na FK RESTRICT.

Kryterium sprawności tej izolacji to DWA kolejne przebiegi z tym samym
wynikiem, nie jednorazowe zielone.

## 4. Macierz uprawnień (testowana w API testach każdego zasobu)

| Operacja | anonim | USER (obcy) | USER (członek rodziny) | właściciel | ADMIN |
|---|---|---|---|---|---|
| odczyt PRIVATE | 401 | 404 | 404 | 200 | 200 |
| odczyt HOUSEHOLD | 401 | 404 | 200 | 200 | 200 |
| edycja HOUSEHOLD | 401 | 404 | 200 | 200 | 200 |
| zmiana scope / delete | 401 | 404 | 403 | 200 | 200 |
| nutrition produktu (edycja) | 401 | 403 | 403 | 403 | 200 |
| `measure_kind` / `piece_weight_g` produktu (D15) | 401 | 403 | 403 | 403 | 200 |
| sklepy i produkty sklepowe (CRUD) | 401 | 200 | 200 | 200 | 200 |
| publiczna lista (token) | 200 | 200 | 200 | 200 | 200 |

**Wyjątek: encje „zawsze household" (spiżarnia — `pantry_items`).** Nie mają
kolumny `scope`, więc wiersz „zmiana scope / delete" stosuje się do nich tylko
połową: zmiany scope'u nie ma, a usunięcie jest zwykłą operacją członka rodziny
(**200/204 zamiast 403** — decyzja właściciela D17). Obcy USER nadal dostaje
404. Testy: `tests/api/pantry/test_pantry_api.py::test_czlonek_rodziny_usuwa_cudza_pozycje`
i `tests/integration/pantry/test_pantry_service.py::test_kazdy_czlonek_rodziny_usuwa_cudza_pozycje`.

**Słowniki globalne bez scope'u (kategorie, produkty, sklepy, warianty retail).**
Nie mają właściciela ani rodziny, więc kolumny „USER (obcy)" i „właściciel"
znaczą dla nich to samo — cudzych zasobów tu nie ma, jest jedna widoczność
i różne prawa ZAPISU. Dla sklepów i produktów sklepowych USER może wszystko
(02_DOMAIN §3.1 pkt 3 i 4), a wyjątki katalogu są wymienione wyżej: wartości
odżywcze i weryfikacja (ADMIN), usunięcie produktu (D13) oraz sposób liczenia
i waga sztuki (D15). Testy: `tests/api/catalog/test_stores_api.py`,
`tests/api/catalog/test_retail_api.py`, `tests/api/test_products.py::test_d15_*`.

Macierz jest udowodniona raz, na poziomie mechanizmu: BATCH_03 dostarczył
`tests/integration/test_scope_matrix.py` na encji testowej `ScopedNote`
(konsumuje ten sam `ScopedQuery`, co encje produkcyjne, ale nie istnieje
w migracjach — tabelę tworzy fixture `scoped_notes_table` w bazie testowej).
Batche domenowe NIE przepisują testów mixinu — powtarzają macierz jako testy
API swojego zasobu (kody HTTP, nie wywołania serwisu).

## 5. Dane testowe

Fabryki (proste funkcje asynchroniczne) per moduł w `tests/factories.py`;
`task db-seed-demo` — deterministyczny, idempotentny seed demo do ręcznego
klikania i E2E.

**Stan faktyczny seedu (BATCH_10, 2026-08-21)** — `backend/scripts/seed_demo.py`
zasiewa:

- 15 produktów kanonicznych z mieszaną kompletnością wartości i przelicznikami
  jednostek domowych (od B04),
- jeden sklep („Biedronka") i 10 produktów sklepowych z opakowaniami, w tym dwa
  warianty tego samego produktu, żeby było widać wybór „najmniejsza resztka,
  remis → mniejsze opakowanie" (§2.6),
- 5 przepisów i TYDZIEŃ PLANU (od `DEMO_WEEK_START = 2026-08-24`) — materiał, na
  którym liczony jest snapshot podglądu zakupów.

Cztery rzeczy, o których muszą wiedzieć kolejne batche:

- **Encje ze scope (przepisy, plan) trafiają do PIERWSZEGO konta ADMIN**
  (decyzja B10). Seed nie tworzy konta — bez ADMIN-a robi część globalną
  i mówi, czego nie dołożył. Osobne konto demo odrzucono: wymagałoby hasła
  z env i kolejnej zmiennej konfiguracji (07_SECURITY §2).
- **Plan demo leży POZA okienkiem E2E** (lata 2030+, §3.1): `purgeE2eLeftovers`
  czyści tamto okno w całości i zabrałby plan demo.
- E2E buduje sobie dane samo (przez UI i API); wyjątkiem są pozycje planu
  z produktem, które celowo sięgają po produkty seedu. Spec zakupów robi tak
  z konieczności: pozycja finalnej listy trzyma produkt FK RESTRICT, a listy
  zakupowej nie da się (do B11) usunąć, więc własny produkt zostałby w bazie
  na zawsze.
- Rodziny 2+3 seed nadal NIE zakłada (nie była potrzebna do snapshotu) — to
  jedyny nieodrobiony punkt pierwotnego zakresu §5.

## 6. Definicja zieloności

Zero known-failing testów na masterze. Test flaky = naprawiany albo usuwany
świadomą decyzją w PROGRESS — nigdy retry-until-green.

## 7. Bramka dryfu modeli (ustalenie REVIEW R3, 2026-08-22)

`task migrations-check` bada WYŁĄCZNIE liczbę głów łańcucha, więc rozjazd
między modelami SQLAlchemy a schematem migracji przez dwa batche żył cicho
(`pantry_items.retail_product_id` bez `ForeignKey` w modelu; constraint dopięła
migracja `0011`). Konsekwencja byłaby dotkliwa: pierwszy `--autogenerate`
wygenerowałby `drop_constraint` na FK, którego nikt nie chciał usuwać.

Od R3 bramką jest
`tests/integration/test_migrations.py::test_modele_nie_dryfuja_od_schematu_po_migracjach`
— po `upgrade head` porównuje `Base.metadata` ze schematem realnej bazy
(`alembic.autogenerate.compare_metadata`) i wymaga PUSTEJ listy różnic. Test
pomija encję testową `scoped_notes` (nie tworzą jej migracje produkcyjne).
Odpowiednik na hoście: `uv run alembic check` w `backend/`.
