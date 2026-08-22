# PROGRESS — status batchy i dziennik programu

Aktualizowany przez agentów wykonujących batche. Status: `[ ]` nierozpoczęty,
`[~]` w toku, `[x]` DONE (Definition of Done z 00_MASTER_PLAN §7 spełnione,
commit wykonany). Kolumna „Blokery" = zależności + decyzje z 02_DECISIONS.

## Statusy

| Batch | Status | Blokery | Commit |
|---|---|---|---|
| 01 PROJECT_SCAFFOLD_AND_DEV_LOOP | [x] | — | `batch(01)` na master (hash wpisać po push) |
| 02 AUTH_AND_ACCOUNTS | [x] | — | `batch(02)` na master (hash wpisać po push) |
| 03 HOUSEHOLDS_AND_SCOPE | [x] | — | `batch(03)` na master (hash wpisać po push) |
| 04 UNITS_AND_CANONICAL_PRODUCTS | [x] | — | `batch(04)` na master (hash wpisać po push) |
| R1 REVIEW_FOUNDATIONS | [x] | — | `batch(R1)` na master (hash wpisać po push) |
| 05 RECIPES_AND_NUTRITION_ENGINE | [x] | — | `batch(05)` na master (hash wpisać po push) |
| 06 GOALS_AND_DAY_PLAN | [x] | — | `d6bacd7` batch(06) |
| 07 WEEK_TEMPLATES_AND_CYCLES | [x] | — | `batch(07)` na master (hash wpisać po push) |
| R2 REVIEW_PLANNING_CORE | [x] | — | `batch(R2)` na master (hash wpisać po push) |
| 08 PANTRY | [x] | — | `batch(08)` na master (hash wpisać po push) |
| 09 RETAIL_PRODUCTS_AND_STORES | [x] | — | `batch(09)` na master (hash wpisać po push) |
| 10 SHOPPING_ENGINE | [x] | — | `batch(10)` na master (hash wpisać po push) |
| 11 SHOPPING_LISTS_AND_SHARING | [x] | — | `batch(11)` na master (hash wpisać po push) |
| R3 REVIEW_SHOPPING | [x] | — | `batch(R3)` na master (hash wpisać po push) |
| 12 PWA_AND_OFFLINE | [ ] | — (R3 PASS) | |
| 13 STATISTICS | [ ] | — (R3 PASS) | |
| 14 IMPORT_EXPORT | [ ] | — (R3 PASS) | |
| 15 PDF_IMPORT_EXTRACTION | [ ] | 05 (zalecane po R3) | |
| 16 PDF_IMPORT_REVIEW_AND_AI | [ ] | 15, 04 | |
| R4 REVIEW_PRE_PRODUCTION | [ ] | 01–16 | |
| 17 PRODUCTION_HARDENING | [ ] | R4 | |
| 18 PRODUCTION_DEPLOYMENT_AND_OPERATIONS | [ ] | 17; **D6, D7** | |

## Dziennik

Wpis po każdym batchu (dopisywany NA GÓRZE sekcji): data, batch, 2–5 zdań:
co weszło + **„rzeczy, o których muszą wiedzieć następne batche"**
(odstępstwa, nowe kontrakty, pułapki). Wpis NIE zastępuje propagacji —
zmiany dotykające przyszłych batchy trzeba wpisać do ich kart
(00_MASTER_PLAN §8); dziennik to indeks, nie schowek.

---

**2026-08-22 — REVIEW R3 (REVIEW_SHOPPING) — WERDYKT: PASS**

**B12, B13 i B14 mogą startować (także równolegle).** Pion zakupowy jest zdrowy:
silnik jest czysty i deterministyczny, opakowania/resztki/tury liczą się zgodnie
z 02_DOMAIN §9, spiżarnia nie odejmuje niczego bez pytania, a **publiczna ścieżka
przeszła pełny audyt 07_SECURITY §5 realnymi requestami na działającym stacku** —
nie tylko testami. Audyt objął zakres od `0c7452c` (R2) do stanu roboczego:
moduły `pantry`, `catalog` (retail/stores), `shopping` (engine + oba serwisy +
router publiczny), frontend zakupów, listy i strony publicznej oraz suitę E2E.
**Warunków blokujących NIE MA**; sześć ustaleń naprawionych w tym commicie, dwie
decyzje właściciela (D18/D19) eskalowane, jedno odstępstwo świadomie przyjęte
i dopisane do dokumentacji.

**Silnik zakupowy — DETERMINIZM POTWIERDZONY.** `shopping/engine.py` importuje
wyłącznie `decimal`, `datetime`, `dataclasses`, `enum`, `collections.abc`,
`AppError`, `catalog/units.py` i enum `Perishability`: zero sesji, zero zegara,
zero losowości. `float` nie występuje w torze obliczeń. Żaden zbiór (`set`) nie
wychodzi na zewnątrz — służą wyłącznie testom przynależności, a każde sortowanie
jest jawne i domknięte `id` (`_section_rank`, `_item_rank`, `sorted(demand)`).
Odtworzenie z `params` sprawdzone DWOMA drogami: test
`test_params_odtwarzaja_identyczne_wejscie_i_identyczny_preview` oraz realnie —
`POST /shopping/generate` i dwa kolejne `GET /shopping/generations/{id}` dały
odpowiedzi IDENTYCZNE BAJT W BAJT.

**Arytmetyka opakowań sprawdzona na realnych danych** (seed demo, plan 24–30.08):
240 g przy opakowaniu 1 kg → 1 szt., zostaje 760 g; 1250 ml przy 1 l → 2 szt.,
zostaje 750 ml; 630 g przy 400 g → 2 szt., zostaje 170 g; 150 g przy 150 g →
1 szt., **resztka dokładnie 0** (przypadek brzegowy „dokładna wielokrotność");
7 szt. przy opakowaniu 10 szt. → 1 szt., zostaje 3 szt. Produkty bez wariantu
sklepowego wyszły w gramach z ostrzeżeniem `missing_retail` i BEZ liczby
opakowań — dokładnie jak chce 02_DOMAIN §9.3. Spiżarnia: 1000 g marchwi w domu
pokryło 240 g w pierwszej turze i 120 g w drugiej (FIFO po dniach), wynik
`needed = 0` i **nigdy poniżej zera**; pozycje z zerowym zapotrzebowaniem NIE
weszły na finalną listę (13 → 12 i 9 → 8 pozycji). Preset tur „Niedziela/Środa"
jest DANYMI (`PRESET_ROUNDS` zasiewa się przy pierwszym wejściu i od tej chwili
jest edytowalny), a `perishability` rozstrzyga serwis (`override ?? kategoria`),
nie silnik.

**Audyt tokenów publicznych — KAŻDY punkt 07_SECURITY §5 zweryfikowany realnym
requestem** (curl na `http://127.0.0.1:8000`, lista utworzona pełną drogą
plan → generacja → finalizacja → udostępnienie):

- token 43 znaki base64url, lookup po unique index, ZERO prefiksów i `LIKE`;
- **odpowiedź publiczna bez PII**: dokładnie `{name, expires_at, items[]}`,
  a pozycja `{id, label, amount, unit, category_name, checked, leftover_amount,
  already_have, packages_count, package_size}` — skan odpowiedzi po `email`,
  `owner`, `household`, `user_id`, `product_id`, `position`, `from_pantry`
  nie trafił NICZEGO;
- ważny token 200, **wygasły 410, odwołany 410, nieznany 404** z IDENTYCZNYM
  komunikatem, token o złym kształcie 422 PRZED zapytaniem do bazy (próba
  `' or 1=1--` kończy się na walidacji wzorca);
- **rate limit potwierdzony**: 70 żądań GET dało 59×200 + 11×429, a PATCH po
  wyczerpaniu limitu też 429 — licznik jest WSPÓLNY dla całej ścieżki, ścieżka
  zalogowana pozostała nietknięta (200);
- **maskowanie w logach potwierdzone GREPEM po realnym logu**: token nie
  występuje w `docker logs` ani razu, a ścieżka wychodzi jako
  `/api/v1/public/lists/***` w OBU warstwach (nasz `structlog` i access log
  Uvicorna);
- publiczny PATCH przyjmuje WYŁĄCZNIE `checked` (`already_have` i
  `needed_amount` dostają 422 `extra_forbidden`), pozycja z innej listy tym
  tokenem to 404, a powtórzone `{"checked": true}` zwraca 200 i **nie przesuwa
  `checked_at`** — czyli PATCH jest idempotentny (kluczowe dla kolejki B12);
- nagłówki bezpieczeństwa (CSP, nosniff, DENY, Referrer-Policy) wychodzą też na
  ścieżce publicznej, a odpowiedź nie ustawia żadnego cookie.

**Mobile UX i wydruk sprawdzone W PRZEGLĄDARCE (Chromium, 375–390 px), nie
zadeklarowane.** Publiczna lista renderuje się bez sesji i poza `AppShell`:
12 checkboxów **48×48 px** w wierszach 64 px, każdy z `aria-label`, nagłówki
sekcji `position: sticky`, ZERO elementów interaktywnych mniejszych niż 44 px,
brak poziomego przewijania przy 375 px. Wydruk (emulacja mediów `print` + PDF)
na obu stronach: nawigacja ukryta, checkboxy zamienione na `☐`, kategorie jako
nagłówki, zero cieni. Udostępnianie sprawdzone realnie w UI: link (67 znaków,
absolutny), kopiowanie, odwołanie i **QR jako PNG data-URL 240 px generowany
klientem**.

**Sześć ustaleń NAPRAWIONYCH w tym commicie:**

1. **U16 ZAMKNIĘTY — rejestr liczników referencji do rodziny.**
   `households/service.py` dostał `register_household_reference_finder`
   (wzorzec `register_product_reference_finder`), a liczniki zarejestrowały
   `recipes`, `planning` (dni), `planning/templates` (szablony dnia/tygodnia
   i cykle), `pantry` oraz `shopping` (tury, generacje, listy) — pięć finderów
   pokrywających DZIEWIĘĆ tabel z `household_id ON DELETE RESTRICT`. ADMIN
   dostaje teraz 409 z listą „Używane w:" z NAZWAMI (przepis, „Plan dnia
   06.05.2030", szablon, pozycja spiżarni z nazwą produktu, tura, generacja
   z zakresem dat, lista), przyciętą do `USED_IN_LIMIT`. Druga linia obrony
   (`IntegrityError` → 409 z pustą listą) zostaje i od teraz znaczy dokładnie
   jedno: „konsument bez licznika". Testy: `test_u16_*` w
   `tests/api/test_admin_households.py`.
2. **U17 ZAMKNIĘTY — pusty dzień planu sprząta się sam.**
   `PlanningService.delete_meal` usuwa wiersz `plan_days`, jeśli został bez
   posiłków, bez tytułu i z domyślną widocznością. To była NAJCZĘSTSZA przyczyna
   409 z pustym `used_in`: dzień powstaje implicite przy pierwszym posiłku, a po
   usunięciu wszystkich UI pokazuje „brak planu" — wiersz był niewidzialny, ale
   dalej blokował rodzinę. Tytuł i `scope='household'` to jawne decyzje
   użytkownika, więc taki dzień ZOSTAJE (i widać go w `used_in` z datą).
   `DELETE /plan/days/{date}` świadomie NIE powstał — 04_API §2 dostał sekcję
   „Cykl życia dnia planu" opisującą stan faktyczny zamiast skrótu „CRUD".
3. **Dług z B10 zamknięty + NOWA BRAMKA.** `pantry_items.retail_product_id`
   dostało `ForeignKey` w modelu (constraint dopięła migracja `0011` dwa batche
   temu), więc `alembic check` jest czysty. Żeby to się nie powtórzyło,
   `tests/integration/test_migrations.py` ma teraz
   `test_modele_nie_dryfuja_od_schematu_po_migracjach` — porównuje
   `Base.metadata` ze schematem po `upgrade head` (`compare_metadata`).
   Sprawdzone jako CZERWONE przed naprawą: bez `ForeignKey` w modelu test
   wykrywa „removed foreign key", czyli dokładnie to, co pierwszy
   `--autogenerate` skasowałby po cichu.
4. **`accept_to_pantry` jest teraz JEDNĄ transakcją.**
   `PantryService.receive_purchase` NIE COMMITUJE (wzorzec
   `AuditService.record`) — robi `flush`, a commit należy do wołającego.
   Wcześniej commit szedł per pozycja, więc błąd w połowie listy zostawiał
   spiżarnię w stanie pośrednim, a ponowienie akcji dolewało już przyjęte
   pozycje DRUGI raz. Test regresyjny (`monkeypatch` wysadzający drugą
   pozycję) sprawdzony jako czerwony przed naprawą.
5. **Odhaczona pozycja „mam już w domu" NIE wchodzi do spiżarni.** Wiersz
   oznaczony `already_have` jest na liście jako przypomnienie, a nie jako coś
   do kupienia (02_DOMAIN §9.3 — „nic nie kupujemy") — odhaczenie go („tak, potwierdzam, że mam")
   dokładało do spiżarni ilość, której nikt nie kupił. Teraz liczy się jako
   `skipped`, a komunikat w UI POKAZUJE tę liczbę (wcześniej `skipped` nie
   docierało do użytkownika w ogóle).
6. **Wydruk był brązowo-szary, nie czarno-biały** (06_UIUX §6). `print.css`
   wymuszał `color` tylko na `html, body`, a każdy tekst ma własną klasę
   z tokens (`#2B2620`, `#6F675C`), więc dziedziczenie nie miało jak zadziałać.
   Reguła obejmuje teraz `*` — sprawdzone emulacją mediów `print`: zero
   elementów z kolorem innym niż czysta czerń.

**Odstępstwo ŚWIADOMIE PRZYJĘTE (nie naprawiane):** status 404 (token nieznany)
i 410 (wygasły/odwołany) różnią się, choć komunikat jest identyczny — kod
odpowiedzi zdradza więc, czy token kiedykolwiek istniał. Przy entropii 256 bitów
i limicie 60/min/IP ta wyrocznia jest bezużyteczna (trzeba najpierw wylosować
istniejący token), a rozróżnienie ratuje diagnostykę właściciela listy. Frontend
nie korzysta z różnicy — `publicList.ts` mapuje oba kody na jeden ekran.
Dopisane do 07_SECURITY §5 jako punkt 8, żeby nikt tego nie „naprawiał" po cichu.

**Decyzje ESKALOWANE (OPEN w 02_DECISIONS, review ich NIE zgaduje):**

- **D18 — ręczne pozycje listy zakupowej.** Rekomendacja: TAK, ale dopiero
  w batchu dotykającym tej strony (B12) i WYŁĄCZNIE jako pozycja z produktem
  kanonicznym; pozycja „luźny tekst" wypada z sortowania sekcji (profil sklepu)
  i z przyjęcia do spiżarni. Obejście na dziś: dopisać rzecz do planu
  i wygenerować turę ponownie.
- **D19 — znacznik „już przyjęte" na liście.** Po R3 akcja jest atomowa, ale
  nadal POWTARZALNA; ochroną jest wyłącznie dialog. Rekomendacja: kolumna
  `shopping_lists.received_at` w B12, bo dopiero offline czyni powtórkę
  prawdopodobną (ponowienie żądania z kolejki po utracie odpowiedzi).

**Plan B12–B16 — bramka OTWARTA, kolejność importera POTWIERDZONA.**
Sekwencja zostaje **B12 ∥ B13 ∥ B14 → B15 → B16 → R4**. Wariant „B15 zaraz po
R3" rozważony i odrzucony: B15 dokłada migrację stagingu, a dwie migracje
w równoległych worktree łamią wymóg jednej głowy po merge'u; trzy batche PLAT
są krótsze i nie wchodzą w moduł `recipes`. Warunek D2 („nie później niż po R3")
czytamy jako **przed B17/B18** i to zostaje twarde. Kolizje plików w dozwolonej
trójce sprawdzone PRZED dopuszczeniem: `frontend/package.json` + lockfile
(wszystkie trzy), `src/api/queryKeys.ts` (B13 i B14), `backend/app/main.py`
(tylko B14) oraz `docs/architecture/04_API_DESIGN.md` (B13 i B14) — wszystkie
rozwiązywalne unią przy sekwencyjnym merge'u; żadnych kolizji w kodzie modułów
(B12: shopping/offline, B13: planning/stats, B14: transfer). Karty B12–B16
zaktualizowane ustaleniami (m.in. B12: idempotencja PATCH-a, WSPÓLNY limit
60/min/IP dla kolejki, sekcje składane przez SERWER, D18/D19 do rozstrzygnięcia
przed Stage 5; B14: `public_token` NIGDY w eksporcie, `params` czytane przez
`load_input`, kolejność importu wymuszona przez FK).

**Wyniki uruchomień (realne):** `task check` zielony na WEJŚCIU (exit 0:
3 migrations-check / 303 unit / 229 int / 343 api / 296 vitest w 32 plikach /
mypy 164 plików + vue-tsc / ruff / eslint / prettier / vite build) i po
naprawach (**+6 testów integracyjnych** → 235 int, **+2 API** → 345 api).
`alembic check`: „No new upgrade operations detected" (przed naprawą:
`remove_fk` na `pantry_items`). E2E: **15/15 w dwóch kolejnych przebiegach**
(1,5 min i 1,8 min). `task audit`: pip-audit „No known vulnerabilities found",
`npm audit --audit-level=high` „found 0 vulnerabilities". `task secrets-scan`:
„no leaks found" (21 commitów, 4,77 MB).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Nowa tabela ze `household_id` = nowy licznik referencji** w tym samym
   batchu (`register_household_reference_finder`). Bez niego 409 przy usuwaniu
   rodziny wraca z pustą listą i ADMIN nie wie, co blokuje.
2. **Kolumna, której FK dopina PÓŹNIEJSZA migracja, musi dostać `ForeignKey`
   w modelu w tym samym commicie co ta migracja.** Pilnuje tego bramka dryfu
   w `task check`. Dotyczy wprost B15: `recipes.import_job_id` czeka na
   `import_jobs`.
3. **Metoda serwisu wołana w PĘTLI po jednej decyzji użytkownika nie commituje**
   — `flush()` i commit u wołającego (wzorzec `AuditService.record`,
   `PantryService.receive_purchase`).
4. **Publiczny PATCH checkboxa jest idempotentny**, a limit 60/min/IP jest
   WSPÓLNY dla GET i PATCH całej ścieżki publicznej — kolejka offline (B12) musi
   traktować 429 jako stan przejściowy z backoffem, nie jako porażkę mutacji.
5. **Kolejność sekcji listy liczy SERWER** — offline nie ma z czego jej
   przeliczyć, więc zmiana sklepu nie może iść do kolejki bez informacji, że
   porządek odświeży się po synchronizacji.

**2026-08-22 — BATCH_11 (SHOPPING_LISTS_AND_SHARING): lista działa w sklepie i da się
ją wysłać linkiem.** Weszły: `shopping/lists_service.py` (drugi serwis modułu —
życie gotowej listy), czysty `shopping/sorting.py`, routery `/shopping/lists/*`
i `/api/v1/public/lists/*`, `GoneError` (410) w core, maskowanie tokenu w access
logu Uvicorna, `PantryService.receive_purchase`, strona listy z sekcjami i
checkboxami 48 px, `ShareListDialog` (link/QR/Web Share/odwołanie), publiczna
strona `/l/:token` poza shellem, wariant do druku i E2E domykające core flow 3.
**Bez migracji — head zostaje `0012`** (unique index na `public_token` założyła
`0012`). Siedem rzeczy, o których muszą wiedzieć następne batche:

1. **Sekcje listy składa SERWER, nie przeglądarka.** `GET /shopping/lists/{id}`
   zwraca `sections` już w kolejności przejścia po sklepie (profil `store_category_order`
   → reszta wg globalnej pozycji kategorii; `already_have` na dół sekcji).
   Gdyby kolejność liczył frontend, ta sama lista miałaby trzy różne porządki:
   na ekranie, na wydruku i pod publicznym linkiem. Sklep przypisuje się PATCH-em
   LISTY (`store_id`/`clear_store`), nie przy finalizacji generacji.
2. **`checked_at` to moment OSTATNIEJ decyzji o checkboxie — także odznaczenia.**
   Ustawia go serwer przy każdej zmianie `checked`, w obie strony; klient go nie
   przysyła. Tak go potrzebuje LWW z ADR-009: B12 musi wiedzieć, która decyzja
   jest MŁODSZA, a nie tylko kiedy coś odhaczono. Karta B12 zaktualizowana.
3. **Odpowiedź publiczna to jawna BIAŁA LISTA pól** (`PublicListRead`, bez
   `from_attributes`), a test asercjonuje DOKŁADNY zbiór kluczy. Dołożenie
   czegokolwiek do tej odpowiedzi jest zmianą kontraktu bezpieczeństwa
   (02_DOMAIN §13.5), nie ulepszeniem UI. Strona zalogowana dostaje INNY kształt
   (`sections`) — offline w B12 to dwa osobne snapshoty.
4. **Publiczny router MUSI siedzieć pod `/api/v1/public/`.** Dokładnie ten prefiks
   jest zwolniony z CSRF i tylko on jest maskowany w logach. Limit 60/min/IP jest
   WSPÓLNY dla całej ścieżki (`limiter.shared_limit`, scope `public-lists`) —
   `limiter.limit` liczyłby per trasę, czyli dawałby faktycznie 120/min.
   Kolejny endpoint publiczny dołącza do tego scope, nie zakłada własnego.
5. **Maskowanie tokenu wymaga DWÓCH warstw** i to jest ustalenie z review, nie
   ozdoba: `mask_path` w naszym middleware ORAZ `MaskPublicTokenFilter` na
   loggerze `uvicorn.access`. Uvicorn formatuje ścieżkę sam z `record.args`, więc
   bez filtra token wychodził w `docker compose logs app` w całości.
6. **„Co mamy w domu" to przynależność, nie widoczność.** `receive_purchase`
   szuka pozycji do scalenia przez `select_own_household`, bo `select_visible`
   zwraca ADMIN-owi `true()` (D16) — pierwsza wersja dolewała mu zakupy do
   spiżarni obcej rodziny. Każdy nowy ZAPIS w encji „zawsze household" musi
   wybrać ten sam warunek co `get_household_state`.
7. **Playwright zapisuje artefakty pod watcherem Vite.** `test-results/` i
   `playwright-report/` leżą w katalogu frontendu, więc każdy zapis w trakcie
   przebiegu wywoływał PEŁNE przeładowanie strony i gubił stan UI (spec tracił
   w połowie otwarty panel). `server.watch.ignored` w `vite.config.ts` to zamyka —
   następny spec z dłuższym flow nie musi tego odkrywać od nowa.

`task check` ZIELONY W CAŁOŚCI (exit 0): migrations-check (3),
**test-unit (303)**, **test-int (229)**, **test-api (343)**,
fe-test (296 w 32 plikach), typecheck (mypy 164 pliki + vue-tsc), lint,
format-check, fe-build. E2E: **dwa kolejne przebiegi
z identycznym wynikiem 15/15** (nowy spec `shopping-list-sharing` otwiera
`/l/{token}` w OSOBNYM kontekście przeglądarki — bez `storageState`, więc bez
ciasteczka sesji; inaczej test przechodziłby też wtedy, gdy strona publiczna po
cichu korzysta z cookies). Maskowanie tokenu sprawdzone RĘCZNIE na realnym
stacku w obu logach.

**`/code-review` + `/security-review` na diffie: sześć ustaleń, wszystkie
NAPRAWIONE w tym commicie**, dwa poważne (token w access logu Uvicorna; ADMIN
dolewający zakupy do cudzej spiżarni — oba z testem regresyjnym, drugi
sprawdzony jako czerwony przed naprawą) i cztery mniejsze (`MissingGreenlet` na
PATCH-u listy po `updated_at` z `onupdate`; klucz szczegółu listy był dzieckiem
klucza indeksu w TanStack Query, więc invalidacja kasowała świeżą odpowiedź
PATCH-a; limit `/public/*` liczony per endpoint; śmieciowe id w URL-u dawało
wieczny spinner). Szczegóły i uzasadnienia: Completion notes karty B11.

**Follow-upy dla R3** (wpisane też do karty R3): `accept_to_pantry` nie jest
atomowe i jest powtarzalne (brak znacznika „już przyjęte"); specy zakupowe mogą
wrócić do własnych produktów, bo `clearShoppingLists` już istnieje; dług z B10
(dryf modelu `pantry_items.retail_product_id`) bez zmian.

**2026-08-21 — BATCH_10 (SHOPPING_ENGINE): zakupy liczą się z planu.** Weszły:
migracja `0012` (`shopping_round_configs`, `shopping_generations`,
`shopping_lists`, `shopping_list_items` + typy `shopping_round_mode`
i `shopping_generation_status`, head = `0012`), CZYSTY silnik
`app/modules/shopping/engine.py` (pipeline 02_DOMAIN §9.1 na `Decimal`),
`ShoppingService` z `/shopping/round-configs`, `/generate`, `/generations/{id}`
(GET + miękki DELETE), `/resolve`, `/finalize`, strona `/zakupy` (tury +
formularz + podgląd z resztkami i panelem spiżarni), rozszerzony seed demo
(sklep, 10 opakowań, 5 przepisów, tydzień planu) i E2E `shopping-generate`.
Siedem rzeczy, o których muszą wiedzieć następne batche:

1. **`shopping_generations.params` to PEŁNE, WERSJONOWANE wejście silnika**
   (`{"v": 1, …}`), nie zapis wyniku. `generate` je zapisuje, a `GET` i
   `resolve` liczą podgląd PONOWNIE z tego zapisu — dlatego podgląd jest
   deterministyczny i nie zależy od tego, czy plan zmienił się w międzyczasie
   (test integracyjny usuwa pozycje planu i dostaje identyczny podgląd).
   Czytać przez `engine.load_input`, nigdy ręcznie po kluczach JSONB; niezgodna
   wersja daje 409 z instrukcją, nie 500. Karta B13 zaktualizowana.
2. **Oś zakupów to `base_unit`, nie `basis_unit`.** Nowa funkcja
   `catalog/units.py::to_base_amount` jest JEDYNYM miejscem, które dzieli przez
   `piece_weight_g` (gramy → sztuki). Opakowanie jajek ma 10 szt., nie 600 g —
   bez tej konwersji pozycje w sztukach i w gramach sumowałyby się bzdurnie.
3. **Trzy nowe publiczne wejścia serwisów** (moduł→moduł wyłącznie tak):
   `PlanningService.demand_rows` (pozycje planu z zakresu, TA SAMA reguła
   rozstrzygania dnia co `list_days` — inaczej zakupy policzyłyby się podwójnie),
   `RecipesService.ingredient_amounts` (ilości składników, bez scope — jak
   `portion_values`), `RetailService.options_for_products` + `variants_by_ids`.
4. **Moduł `shopping` rejestruje TRZY liczniki referencji**: produkt kanoniczny,
   wariant sklepowy i SKLEP. Ten trzeci jest nieoczywisty i konieczny:
   `shopping_lists.store_id` ma `SET NULL`, więc baza sama nie obroni tej
   referencji i lista po cichu straciłaby profil sortowania (ostrzeżenie z B09
   pkt 2 — domknięte).
5. **Niejasności mają cztery rodzaje, dwa są blokerami.** Blokery:
   `plan_item_without_amount`, `product_without_category`. Ostrzeżenia:
   `missing_retail` (02_DOMAIN §9.3), `pantry_amount_not_convertible` (rodzaj
   dołożony ponad kartę — nieprzeliczalny stan domowy NIE jest odejmowany, więc
   użytkownik musi o tym wiedzieć). Bloker da się ŚWIADOMIE ODŁOŻYĆ
   (`dismissed_issues` w `params`) i wtedy finalizacja przechodzi bez tej
   pozycji — inaczej jedna zła pozycja planu blokowałaby zakupy na zawsze.
6. **Seed demo dopisuje encje ze scope do PIERWSZEGO konta ADMIN** i stawia
   tydzień planu na STAŁEJ dacie `2026-08-24` — POZA okienkiem E2E (lata 2030+),
   bo `purgeE2eLeftovers` czyści tamto okno w całości. `scripts/` jest od teraz
   PAKIETEM: snapshot silnika importuje stałe seedu, żeby dane testu i dane
   komendy nie istniały w repo dwa razy.
7. **E2E zakupów pracuje na produktach SEEDU, nie własnych** — pozycja finalnej
   listy trzyma produkt i wariant FK RESTRICT, a listy nie da się (do B11)
   usunąć, więc własny produkt zostałby w bazie na zawsze i zatruwał szukajkę
   trigramową. Przy okazji naprawiony (WZMOCNIONY, nie osłabiony) spec
   `recipe-inline-create`: wybierał kartę produktu przez `first()` na
   nieprzefiltrowanej jeszcze liście i po rozszerzeniu seedu trafiał w „Banan",
   którego skasować nie wolno.

`task check` ZIELONY W CAŁOŚCI (exit 0): migrations-check (3),
**test-unit (290)**, **test-int (219)**, **test-api (309)**, fe-test (263 w 28
plikach), typecheck (mypy 155 plików + vue-tsc), lint, format-check, fe-build.
Cykl migracji `upgrade head → downgrade -1 → upgrade head` przeszedł na realnej
bazie; E2E **trzy przebiegi** z identycznym wynikiem (14/14). Snapshot podglądu
(`tests/unit/shopping/snapshots/demo_week_preview.json`) regeneruje się przez
`FFP_UPDATE_SNAPSHOTS=1` — zmiana tego pliku w diffie zawsze wymaga decyzji.

**`/code-review` (SKILL-REVIEW) na diffie: dwa ustalenia, oba NAPRAWIONE
w tym samym commicie.** (a) `retailChoices` w podglądzie powstawało z pozycji,
więc warianty dobrane AUTOMATEM wyjeżdżały do `/resolve` jako jawne decyzje —
pierwsza dowolna zmiana zamrażała je wszystkie i późniejsze dodanie mniejszego
opakowania nic już nie zmieniało. Naprawa: `PreviewResult`/`GenerationRead`
echują JAWNE `retail_choices`, a frontend buduje na nich, nie na pozycjach
(nowe asercje w testach int i api). (b) `seed_plan` indeksowało słownik przepisów
bez sprawdzenia — brakujący przepis demo dawał `KeyError` zamiast `SeedError`
z komunikatem po polsku.

**Follow-up dla R3 (poza zakresem B10)**: `alembic check` raportuje dryf modelu
`pantry_items.retail_product_id` (brak `ForeignKey` w modelu, constraint jest
w migracji `0011`). `task check` tego nie łapie, bo `migrations-check` bada tylko
liczbę głów. Naprawa to jedna linia w `pantry/models.py`.

**2026-08-21 — BATCH_09 (RETAIL_PRODUCTS_AND_STORES): produkty sklepowe, sklepy
i profile kolejności kategorii; D15 domknięta.** Weszły: migracja `0011`
(`stores`, `store_category_order`, `retail_products`, head = `0011`), dwa nowe
serwisy w module `catalog` (`stores_service.py`, `retail_service.py`) z routerami
`/stores`, `/stores/{id}/category-order` (GET/PUT) i `/retail-products`
(+ `PUT|DELETE /photo`), sekcja „Sklepy" w Ustawieniach z edytorem kolejności
(DnD **i** strzałki), sekcja „Produkty sklepowe" na karcie produktu oraz E2E
`retail-stores.spec.ts`. Sześć rzeczy, o których muszą wiedzieć następne batche:

1. **Odroczony FK z B08 jest DOPIĘTY.** `pantry_items.retail_product_id` ma
   `fk_pantry_items_retail_product_id_retail_products` z `ON DELETE RESTRICT`,
   a `pantry/service.py` rejestruje licznik referencji przez
   `retail_service.register_retail_reference_finder`, więc 409 przy usuwaniu
   wariantu pokazuje pozycje spiżarni. **Konsekwencja dla testów**: nie da się
   już wstawić pozycji spiżarni z wymyślonym `retail_product_id` — trzeba
   PRAWDZIWEGO wariantu (fabryka `create_retail_product`). Jeden test B08 tak
   robił i `task check` go złapał; został poprawiony, nie osłabiony.
2. **Dwa nowe rejestry liczników referencji.**
   `retail_service.register_retail_reference_finder` (dla FK do
   `retail_products` — pozycje list zakupowych w B11) i
   `stores_service.register_store_reference_finder` (dla `shopping_lists.store_id`
   w B11). Bez wpisu 409 wyjdzie z PUSTĄ listą „Używane w:", a przy sklepie nie
   ma nawet drugiej linii obrony — FK listy ma `SET NULL`, więc lista po cichu
   straciłaby profil sortowania. Karty B10 i B11 mają to wpisane.
3. **`package_unit` to TEN SAM typ PG co `amount_unit`** z migracji `0006`
   (`postgresql.ENUM(..., create_type=False)` również w modelu, nie tylko
   w migracji). Kolejna tabela z jednostką ilości robi tak samo — osobnego typu
   nie tworzymy, `EXPECTED_ENUM_TYPES` bez zmian.
4. **Jednostka opakowania jest zawsze na osi produktu kanonicznego** —
   serwis liczy ją przez `units.base_unit(product.measure_kind)` i odrzuca
   niezgodność 422-ką. Silnik zakupowy (B10) może więc robić
   `ceil(potrzeba / package_amount)` BEZ konwersji; to niezmiennik, nie
   założenie. Warianty archiwalne domyślnie nie wchodzą do listy.
5. **Kontrakt `RetailProductCreateDrawer`** (dla preview zakupów w B10/B11):
   props `{ open, canonicalProductId, prefillName? }`, emits
   `created(retailProduct)` / `close()`. Poza id produktu nie wymaga niczego —
   sposób liczenia dociąga sam z `/products/{id}`. Sprawdzone testami
   `RetailProductCreateDrawer.spec.ts`; karta B10 zaktualizowana.
6. **Sprzątanie E2E ma dwa nowe ogniwa w USTALONEJ kolejności**: spiżarnia →
   **warianty retail → sklepy** → produkty kanoniczne (`clearRetailProducts`
   i `clearStores` w `e2e/cleanup.ts`, wpięte też w `purgeE2eLeftovers`).
   Odwrotna kolejność zostawia śmieci: wariant trzyma produkt FK RESTRICT,
   a sklep jest trzymany przez wariant 409-ką.

**D15 ZAMKNIĘTA I WDROŻONA W CAŁOŚCI.** Bramka `_assert_measure_change_allowed`
siedzi w `catalog/service.py::update_product` (403 z podpowiedzią wyjścia, wzorzec
D13), obejmuje `measure_kind` ORAZ `piece_weight_g`, a pola są wyłączone dla
nie-ADMIN-a w `ProduktFormPage.vue`. **Doprecyzowanie wykonawcze, o którym musi
wiedzieć każdy, kto tknie ten formularz: bramka porównuje WARTOŚCI, nie obecność
klucza w żądaniu** — formularz wysyła oba pola przy każdym zapisie, więc blokada
na obecności odebrałaby USEROWI edycję nazwy i kategorii, czego decyzja jawnie
zakazywała. Macierz uprawnień w `tests/api/test_products.py::test_d15_*` sprawdza
oba kierunki (USER 403 na zmianę, USER 200 na pozostałe pola, ADMIN 200).
Rejestr 02_DECISIONS nie ma już ŻADNEJ decyzji dotyczącej batchy 09–17 — otwarte
zostają D6/D7 (bramki B18) i cztery pozycje bez konsumenta.

**Konwencja pliku modułu potwierdzona**: obszar dokładany do istniejącego modułu
dostaje własny plik SERWISU (`stores_service.py`, `retail_service.py` — wzorem
`planning/templates_service.py`), ale modele i schematy zostają w jednym
`models.py`/`schemas.py` modułu, bo `app/models.py` importuje właśnie moduł
modeli i to on decyduje, co widzi Alembic.

**2026-08-21 — BATCH_08 (PANTRY): spiżarnia jako stan domowy, bez żadnego
automatycznego odejmowania.** Weszły: migracja `0010_pantry_items` (head = `0010`),
moduł `app/modules/pantry/` z endpointami `/api/v1/pantry` (GET/POST/PATCH/DELETE),
widok `/spizarnia` (kafelki/lista, filtr kategorii, szukajka, sortowanie po dacie
ważności, plakietka przeterminowania) i E2E `pantry.spec.ts` z inline create
produktu. Pięć rzeczy, o których muszą wiedzieć następne batche:

1. **Nowy wariant scope w `app/core/scope.py`: `HouseholdScopedMixin` +
   `HouseholdScopedQuery`.** Encja „zawsze household" NIE ma kolumny `scope`
   (03_DATABASE §7), więc `ScopedMixin` się do niej nie stosuje — jego CHECK
   zabraniałby wiersza „household bez rodziny", a to jest wymagany przypadek
   użytkownika bez rodziny. Warunek widoczności to
   `household_id = :hh OR (household_id IS NULL AND owner_user_id = :uid)` —
   **bez samodzielnego `owner_user_id = :uid`**, żeby po odejściu z rodziny wpis
   został przy rodzinie. Kolejna encja tego typu używa tego mixinu, a nie pisze
   własnego filtru. ADMIN dostaje `true()` jak w `ScopedQuery` (D16) i macierz
   uprawnień to asercjonuje.
2. **`pantry_items.retail_product_id` istnieje BEZ constraintu FK** — B08
   zmergował się pierwszy, `retail_products` jeszcze nie ma. **Rekoncyliację
   wykonuje B09** (albo R3, jeśli B09 zmieni kolejność): gotowy
   `op.create_foreign_key(... ondelete="RESTRICT")` czeka w karcie B09 §Context.
   Do tego czasu API spiżarni wymaga `product_id` i nie przyjmuje produktu
   sklepowego — świadomie, bo nie da się zwalidować odwołania do nieistniejącej
   tabeli.
3. **Kontrakt dla B10/B11**: `PantryService.get_household_state(user) ->
   list[PantryStateItem]` (`item_id`, `product_id`, `retail_product_id`,
   `amount`, `amount_unit`, `expiry_date`). Ilości leżą na osi PRZECHOWYWANIA
   (`base_unit`: sztuki zostają sztukami), pozycje z `amount = 0` NIE wchodzą do
   wyniku, a wynik to lista POZYCJI, nie agregat per produkt (jeden produkt =
   wiele partii z różnymi datami). **Wyjątek D16 tu NIE obowiązuje**: stan domowy
   jedzie po `select_own_household`, więc ADMIN generujący zakupy odejmie swoją
   spiżarnię, a nie wszystkich rodzin — granica jak dla `/households/my`
   (04_API §3 pkt 2a). Karty B10 i B11 są już zaktualizowane; B11 dostał
   wyjaśnienie, dlaczego nie ma metody „dodaj albo zwiększ".
4. **`e2e/cleanup.ts` sprząta spiżarnię PRZED produktami.** `pantry_items.product_id`
   ma FK RESTRICT, więc zostawiona pozycja blokuje `DELETE /products/{id}`
   409-ką i zatruwa kolejne przebiegi — ten sam dług, który R2 zamykał dla
   przepisów. Nowy spec dotykający spiżarni nie musi nic dokładać: `clearPantry`
   jest już wpięte w `cleanupE2eData` i `purgeE2eLeftovers`.

5. **Pułapka: `expire_on_commit=False` + mapa tożsamości gubi skalę NUMERIC.**
   Serwis, który po commicie zwraca ilości z kolumny NUMERIC, NIE MOŻE polegać
   na kolejnym `select()` — SQLAlchemy odda tę samą instancję z pamięci
   (z `Decimal("0")` z żądania) zamiast wiersza z bazy (`Decimal("0.000")`),
   i odpowiedź API wyjdzie ze złą skalą. Trzeba `await session.refresh(item)`
   albo `.execution_options(populate_existing=True)` na odczycie po zapisie
   (pantry używa tego drugiego — jedno zapytanie zamiast dwóch). Złapał to
   `task check` w B08 trzema czerwonymi testami API; B10/B11 zwracają ilości
   tak samo, więc dotyczy ich wprost.

**D17 ZAMKNIĘTE przez właściciela w trakcie batcha: pozycję spiżarni usuwa
KAŻDY CZŁONEK RODZINY.** Rekomendacja agenta („zostawić autora wpisu, bo tak
mówi 02_DOMAIN §3.1 pkt 2") została odrzucona na rzecz spójności domenowej:
spiżarnia to jeden stan domowy, więc „kto dodał" jest informacją, a nie
przywilejem — skoro członek rodziny może pozycję wyzerować, blokowanie mu
usunięcia wiersza było pozorną ochroną. Stan wdrożony: `delete_item` bez bramki
właścicielskiej, a `HouseholdScopedQuery` **nie ma `assert_can_manage` w ogóle**
(encja „zawsze household" nie ma reguły właścicielskiej, bo nie ma też scope'u
do zmiany). Cudza rodzina nadal 404. Wyjątek dopisany do **02_DOMAIN §3.1 pkt 2**
i **08_TESTING §4** — kolejna encja „zawsze household" dziedziczy tę regułę.
`task check` zielony, E2E dwa przebiegi z identycznym wynikiem (11/11).

**2026-08-21 — D15 ZAMKNIĘTE przez właściciela: `measure_kind` zmienia
WYŁĄCZNIE ADMIN.** Część pierwsza (zmiana unieważnia weryfikację) działa od B05;
część druga — bramka uprawnień — **czeka na wdrożenie w B09**, bo to następny
batch dotykający modułu `catalog` i formularza produktu. Instrukcja wykonawcza
jest w karcie B09 (§Backend „Wdrożenie decyzji D15") i w Implementation
checklist: bramka w serwisie (nie w routerze — 403 ma podpowiadać wyjście, jak
przy D13), obejmuje `measure_kind` ORAZ sprzężone `piece_weight_g`, pole
wyłączone w `ProduktFormPage` dla nie-ADMIN-a, test macierzy uprawnień
sprawdzający też, że PATCH pozostałych pól opisowych nadal działa dla USERA.
`create_product` bez zmian — USER wybiera miarę, zakładając produkt.
**Właściciel świadomie przyjął koszt**: USER nie poprawi sam miary we własnym,
świeżo utworzonym inline produkcie. Wariant złagodzony („USER może, dopóki
produkt nie ma wartości") został ODRZUCONY — nie wprowadzać go z powrotem jako
ulepszenia; ewentualna zmiana wymaga nowej decyzji właściciela.
**Rejestr 02_DECISIONS nie ma już żadnej decyzji blokującej batche** —
otwarte zostają D6/D7 (bramki B18) i cztery pozycje bez konsumenta.

**2026-08-21 — D16 ZAMKNIĘTE przez właściciela: TAK, ADMIN widzi wszystkie
encje ze scope na ścieżkach użytkownika.** Zero zmian w kodzie — decyzja
utrzymuje stan faktyczny (`ScopedQuery.visible_condition` → `true()` dla
ADMIN-a) i to, co już asercjonuje test `test_d16_admin_widzi_cudze_przepisy_*`.
Domknięcie polegało na doprecyzowaniu dokumentów, które mówiły co innego:
**04_API §3 pkt 2/2a** i **07_SECURITY §4** opisują teraz wyjątek razem z jego
granicami — dotyczy ODCZYTU encji ze `ScopedMixin`, NIE rozciąga się na mutacje
reguł właścicielskich (`assert_can_manage`), na zasoby adresowane własną rodziną
(`/households/my`, profile członków — tam ADMIN widzi swoją rodzinę i jest na to
osobny test, więc to granica, nie niespójność) ani na odpowiedzi publiczne.
**Dla kolejnych batchy**: nowa encja ze `ScopedMixin` dziedziczy to zachowanie
automatycznie i MA je zaasercjonować w swojej macierzy uprawnień. Blokada
wejścia do B08 zdjęta — zostaje otwarte tylko D15 (nic nie blokuje).

**2026-08-21 — REVIEW R2 (REVIEW_PLANNING_CORE) — WERDYKT: PASS**

**B08 i B09 mogą startować (także równolegle).** Rdzeń planowania jest zdrowy:
silnik nutrition jest czysty i policzalny, niezmienniki 02_DOMAIN §13.1–13.4 są
przypięte testami, widok tygodnia nie ma N+1, a dług E2E (U15) jest domknięty.
Audyt objął zakres od `c87569f` (R1) do stanu roboczego: moduły `recipes`,
`nutrition`, `planning`, frontend planu/tygodnia/przepisów oraz suitę E2E.
Warunków blokujących NIE MA — trzy ustalenia idą jako follow-up do R3, dwie
decyzje właściciela (D15/D16) są eskalowane, nie rozstrzygnięte przez review.

**Silnik nutrition — CZYSTY, bez ustaleń.** `nutrition/engine.py` importuje
wyłącznie `decimal`, `collections.abc`, `AppError` i własne typy: zero ORM, zero
sesji, zero zegara i losowości (jedyny `date.today()` w module siedzi w routerze,
czyli czas wchodzi parametrem). `float` nie występuje w torze obliczeń — jedyne
wystąpienie w całym backendzie to `catalog_search_similarity_threshold` (próg
pg_trgm, nie wartość domenowa). Zaokrągla DOKŁADNIE jedna funkcja
(`round_for_output`, kcal→1, reszta→0,1, `ROUND_HALF_UP`) i tylko na krawędzi
serializacji; kroki pośrednie niosą pełną precyzję. Wzory §6 zgodne, ŁG liczone
z węglowodanów przyswajalnych z `max(carbs - fiber, 0)`. Braki nigdy nie są
cichym zerem: `complete=False` + `missing` z nazwą produktu, także dla produktu
UNVERIFIED. Testy property-based (hypothesis) przeczytane MERYTORYCZNIE — badają
addytywność agregacji, liniowość skalowania, nieujemność, propagację
niekompletności oraz „dzień = Σ posiłków = Σ pozycji"; strategie generują
realny zakres kolumn NUMERIC. Progi D9 (90–110%, oba progi w przedziale „OK",
konfigurowalne przez `ui_settings`) zgodne z decyzją.

**Niezmienniki §13 — każdy ma test.** §13.1 `test_ilosc_nieprzeliczalna_odrzuca_zapis_bez_sladu`
(422 + ZERO wierszy) i `tests/unit/test_units.py`; §13.2 inspekcja schematu
(`test_wartosci_nie_sa_zapisywane_w_bazie`) + grep kolumn: poza
`canonical_products` nie ma ani jednej kolumny z WYNIKIEM — `kcal_goal`,
`kcal_target` i `user_nutrition_goals.kcal` to CELE, nie cache; §13.3 test przez
API (`test_plan_api.py:346`) i przez serwis; §13.4 409 z `used_in` dla planu
i dla obu rodzajów szablonów. Blokada JSONB potwierdzona `EXPLAIN`-em, który
faktycznie pokazuje `ix_day_templates_payload_gin` (containment `@>`, klasa
`jsonb_path_ops`) — nie założona, sprawdzona.

**Pomiar wydajności tygodnia (nowy test `tests/integration/planning/test_plan_performance.py`).**
Plan 7 dni × 4 posiłki × 4 pozycje = **112 pozycji**, przepisy po 5 składników,
rozkłady rodzinne na każdej pozycji z przepisem. Wynik: **10 zapytań SQL dla
JEDNEGO dnia i te same 10 dla całego tygodnia** — liczba zapytań nie zależy od
zakresu dat ani liczby pozycji, czyli N+1 nie ma (licznik na zdarzeniu
`before_cursor_execute`, nie „na oko"). Czas: `PlanningService.list_days`
42–130 ms, `GET /plan/days` przez HTTP **100–177 ms** na rozgrzanym procesie.
**Budżet <500 ms SPEŁNIONY.** Uwaga uczciwa: PIERWSZE żądanie w procesie trwa
~1,5 s (budowanie modeli Pydantica i planów zapytań) — to koszt startu, nie
zapytania, ale użytkownik po restarcie kontenera go zobaczy; obserwacja dla B17.
Odstępstwo od karty: pomiar NIE mógł być zrobiony „na seedzie demo", bo seed nie
zawiera planu (patrz niżej) — dane do pomiaru seeduje test.

**Model porcji i UX planu — bez ustaleń.** Prosty przypadek został prosty: jedno
pole `item-servings-input`, rozkład rodzinny jest opcjonalnym drawerem, a suma
rozkładu = `servings` pilnowana czystą funkcją na `Decimal`
(`assert_split_matches_servings`, test z przykładem 2×1,0+2×0,8+2×1,3).
„Dopasuj porcję do celu" jest jawną akcją: `fit-to-target` zwraca PROPOZYCJĘ,
zapis to osobny PATCH. Kliknięcia od intencji do efektu: dodanie posiłku 2,
kopiuj dzień 2, zastosuj szablon 4. Frontend nie kopiuje planu do Pinii (jedyny
store to sesja), a każda mutacja unieważnia `queryKeys.planDays.all`.

**Gotowość pod B10 — PASS z jednym brakiem, wpisanym do karty.** Z planu da się
wyciągnąć zakres dat → pozycje → ilości znormalizowane, ale brakuje publicznego
wejścia po stronie właścicieli danych (`RecipesService` nie oddaje ilości
składników, tylko wartości odżywcze porcji). Pięć ustaleń wiążących (w tym
pułapka „ta sama data może mieć DWA widoczne dni — licząc prosto z `plan_days`
policzysz zakupy podwójnie") wpisane do karty B10 §Context.

**Ustalenia NAPRAWIONE w commicie review:**

- **U15 DOMKNIĘTY — E2E 10/10 w DWÓCH kolejnych przebiegach** (kryterium z karty,
  nie jednorazowe zielone; przed review 5/10). Trzy przyczyny, trzy naprawy:
  1. **Martwe `Button as="router-link"`** — 9 wystąpień w 6 plikach z B04/B05
     zamienione na `as-child` + zagnieżdżony `<RouterLink>`. `h()` z ciągiem
     znaków tworzy ELEMENT o tej nazwie, nie komponent, więc powstawał nieznany
     tag `<router-link>`: bez `href`, bez nawigacji, bez roli `link` dla czytnika
     ekranu. Strażnik: `src/components/ui/button/Button.spec.ts` — test na `<a>`
     z `href` i klasami wariantu ORAZ skan wszystkich `src/**/*.vue` przez
     `import.meta.glob`, żeby dziewiąte wystąpienie nie wróciło niezauważone.
  2. **Izolacja danych** — nowy `frontend/e2e/cleanup.ts`: sprzątanie per spec
     (własny prefiks nazw, `beforeAll` + `afterAll`, kolejność wymuszona
     blokadami: cykle → szablony → posiłki → przepisy → produkty) plus
     `purgeE2eLeftovers` w projekcie `setup`, który raz na przebieg kasuje śmieci
     ze starych konwencji nazw. Bez tego drugi przebieg padał, bo szukajka
     TRIGRAMOWA znajdowała „Zupa E2E <stary stamp>" i `canCreate` w pickerze
     (wymaga ZERA wyników) gasił opcję „+ Dodaj".
  3. **Wspólne konto i równoległość** — suita jest teraz JEDNOWĄTKOWA
     (`workers: 1`, `fullyParallel: false`), a `households.spec.ts` ma OSOBNY
     projekt zależny od `chromium`, więc żaden spec nie tworzy encji ze scope
     w czasie, gdy konto należy do tymczasowej rodziny.
- **Asercja `BarChart` w `week-template-cycle.spec.ts` była NIESPEŁNIALNA.**
  Poprawka z B07 zmieniła sposób pomiaru słupka (`data-height` zamiast
  `toBeVisible`), ale dzień zbudowany z przepisu utworzonego inline (nazwa +
  porcja bazowa, ZERO składników) ma 0 kcal, więc `BarChart` renderuje „brak
  danych" i żaden słupek nie może mieć wysokości > 0. Spec dokłada teraz pozycję
  z produktem z seedu („Ryż brązowy", 353 kcal/100 g) — asercja „przynajmniej
  jeden słupek > 0" stała się prawdziwym testem „cykl skopiował plan RAZEM
  z jego wartościami", a nie życzeniem.
- **`task secrets-scan` był NIEUŻYWALNY jako bramka** (warunek 4 werdyktu R1).
  Na czystym repo dawał 14 trafień i kod wyjścia 1 — wszystkie na dwóch
  literałach haseł TESTOWYCH (`haslo-testowe-2026`, `nowe-haslo-2026`), których
  nie da się użyć w żadnym środowisku. Nowy `.gitleaks.toml`: `useDefault = true`
  (pełny zestaw reguł zachowany) + allowlist po WZORCU sekretu, nie po ścieżce,
  więc dowolny inny sekret w tych samych plikach nadal wywala skan. Teraz
  „no leaks found", exit 0.
- **Komentarz w `apply_cycle` obiecywał co innego niż robi kod** (ustalenie
  `/code-review`): sprawdzenie istnienia szablonów obejmuje CAŁĄ listę cyklu,
  nie tylko tygodnie z zakresu — węższa jest walidacja referencji w payloadach.
  Komentarz doprecyzowany, konsekwencja dla importu wpisana do karty B14.
- **Targety pytest przepuszczają argumenty za `--`** (`task test-int -- -k
  fraza -s`). Bez tego nie da się zawęzić przebiegu ani zobaczyć pomiaru bez
  wołania gołego pytesta, którego CLAUDE.md §3 słusznie zabrania (nie widziałby
  `.env`). Bramka `task check` woła te targety BEZ argumentów, więc pełny zakres
  jest zawsze ten sam.

**Ustalenia PRZEKAZANE dalej (follow-up z miejscem docelowym):**

- **U16 → karta R3** `backend/app/modules/households/service.py:210` —
  `delete_household` liczy referencje tylko dla `users` i `member_profiles`,
  więc encje ze scope (dziś 5 tabel, po B08–B11 dziewięć) blokują usunięcie
  przez FK RESTRICT i wpadają w drugą linię obrony: 409 z `used_in: []`.
  Zachowanie jest POPRAWNE (409, nie 500), ale ADMIN nie wie, co blokuje.
  R2 świadomie nie zakładał rejestru finderów teraz — R3 zastaje pełny zbiór
  konsumentów i zrobi to raz, zamiast dwa razy.
- **U17 → karta R3** `backend/app/modules/planning/router.py:215` — `04_API §2`
  opisuje `/plan/days/{date}` jako CRUD, a jest tylko GET i PUT. Wiersz
  `plan_days` powstaje implicite przy pierwszym posiłku i NIE ZNIKA po usunięciu
  wszystkich posiłków (UI pokazuje „brak planu", wiersz trzyma `household_id`) —
  to najczęstsza przyczyna pustego `used_in` z U16. Trzy warianty rozwiązania
  w karcie R3.
- **U18 → karta B10 (+ 08_TESTING §5)** `backend/scripts/seed_demo.py` — seed
  demo ma WYŁĄCZNIE katalog (15 produktów). Rodziny 2+3, 5 przepisów, tygodnia
  planu i listy z 08_TESTING §5 nie dołożył ani B05, ani B07, choć docstring
  seedu tak zakładał. Konsekwencja twarda: snapshoty silnika zakupowego „na
  seedzie demo" z karty B10 są dziś niewykonalne — rozszerzenie seedu należy do
  zakresu B10 (jest w jego Expected files) i wymaga decyzji, czyją własnością
  są encje ze scope (seed nie zna żadnego konta).
- **Obserwacja dla B17**: pierwsze żądanie `GET /plan/days` w świeżym procesie
  trwa ~1,5 s (budowanie schematów), kolejne ~100–180 ms.

**Decyzje OPEN — ESKALOWANE, nie rozstrzygnięte:**

- **D15** (zmiana `measure_kind`) — rekomendacja WDROŻONA w B05 i potwierdzona
  przez R2; do formalnego głosu właściciela zostaje tylko, czy samą zmianę
  zastrzec dla ADMIN-a. Nowa informacja: zmiana nie przelicza ilości JUŻ
  ZAPISANYCH, więc stara ilość może stać się nieprzeliczalna — kod obsługuje to
  jako `complete=False` z komunikatem (nie 500), a B10 musi zrobić to samo.
- **D16** (czy ADMIN widzi cudze encje na ścieżkach użytkownika) — **decydować
  PRZED B08.** Review nie może tego rozstrzygnąć, bo konflikt jest między
  dokumentami NADRZĘDNYMI wobec review (08_TESTING §4 vs 04_API §3 + 07_SECURITY
  §4). Dziś zachowanie dziedziczy 5 encji ze scope, B08–B11 dołożą kolejne
  cztery — koszt odwrócenia rośnie z każdym batchem.

**Security i zależności:** `/security-review` na całym zakresie od R1 —
**ZERO ustaleń** (przejrzane wektory: SQL injection przez szukajkę trigramową
i containment JSONB, path traversal w `core/uploads.py`, obejście scope przez
payload szablonu, IDOR po zagnieżdżonych id, sesje/CSRF w nowych routerach,
XSS w `frontend/src`). Jedna uwaga operacyjna do MOJEGO kodu, naprawiona
w tym commicie: `purgeE2eLeftovers` kasuje szeroko (plan z lat 2030+, przepisy
i produkty ze śladem testu, na koncie ADMIN-a), więc dostał bramkę
`baseURL` — działa WYŁĄCZNIE przeciw localhostowi, w przeciwnym razie rzuca
z komunikatem. `task audit`: pip-audit „No known vulnerabilities found",
`npm audit --audit-level=high` „found 0 vulnerabilities" — bez podbić.
`task secrets-scan`: po dołożeniu `.gitleaks.toml` „no leaks found".
Macierz uprawnień 08 §4 sprawdzona per nowy zasób: recipes, ratings, goals,
plan (dzień/posiłek/pozycja — łańcuch, nie samo id), templates, cycles —
anonim 401, obcy 404, członek rodziny 200, zmiana scope przez członka 403,
mutacja bez CSRF 403. Wszystkie testy istnieją i przechodzą.

**Wyniki uruchomień (realne):** `task check` zielony na WEJŚCIU (exit 0:
3 migrations-check / 242 unit / 147 int / 243 api / 198 vitest w 19 plikach /
mypy 117 plików / vue-tsc / ruff / eslint / ruff format 127 plików / prettier /
vite build) i po naprawach (**+3 testy integracyjne wydajności, +4 vitest** →
150 int / 202 vitest / mypy 118 plików / format-check 128). E2E:
**10/10 w dwóch kolejnych przebiegach** (55 s i 56 s; po dołożeniu bramki
`baseURL` powtórzone: 40 s i 40 s — także 10/10). `task audit` i
`task secrets-scan` czyste. Bez migracji — R2 nie dotknął schematu, `alembic
heads` = `0009`, kolejna wolna migracja `0010`.

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Przycisk, który nawiguje, to LINK**: `<Button as-child>` +
   `<RouterLink>`. `as="router-link"` nie działa i jest teraz łapane testem.
2. **Nowy spec E2E**: własny prefiks nazw `E2E <obszar>`, `cleanupE2eData`
   w `beforeAll` I `afterAll`, daty planu z lat 2030+, ZERO założeń
   o równoległości (suita ma `workers: 1`). Reguły spisane w 08_TESTING §3.1.
3. **Nowa zależność `Base` ze scope = nowy blocker usuwania rodziny.** Dopóki
   U16 jest otwarte, każda nowa tabela ze `ScopedMixin` powiększa zbiór blokad
   z pustym `used_in` — odnotuj to w Completion notes swojego batcha.
4. **`task test-* -- <argumenty pytesta>`** działa (np. `-k fraza -s`).
5. Karty zaktualizowane: B08, B09 (nieistniejące ścieżki: `router/index.ts`,
   `components/AppShell.vue`, `pages/ustawienia/`, `ProduktEdytujPage.vue`,
   `src/composables/` — poprawione na stan faktyczny), B10 (gotowość agregatów
   + seed demo), B11 (ścieżki), B13 (potwierdzone: `goal_for_day` + historia
   celów wystarczają statystykom „wg celu z dnia" — bez zmian w karcie),
   B14 (cykl z martwym `template_ids`), R3 (U16, U17, konwencje E2E).
   Dokumenty: 07_SECURITY §7, 08_TESTING §3.1 i §5, CLAUDE.md §3 i §5,
   skille `ffp-frontend` i `ffp-domain-calc` uzgodnione ze stanem po B07.

**2026-08-20 — BATCH_07 (WEEK_TEMPLATES_AND_CYCLES)**: tydzień da się złożyć
w kilku kliknięciach. Migracja `0009` (`day_templates`, `week_templates` z
`payload JSONB` + **indeksy GIN `jsonb_path_ops`**, `week_cycles` z
`template_ids BIGINT[]`). Kontrakt payloadu `v:1` (Pydantic, `extra="forbid"`,
Decimale jako stringi) walidowany przy zapisie I odczycie. Nowy
`planning/templates_service.py` (CRUD szablonów, instancjacja, cykle + apply)
i czysty `planning/sequences.py` (rotacja cyklu, sekwencja bloku).
`PlanningService` dostał JEDEN mechanizm zapisu — `day_payload_from_rows` +
`append_day_payload` — z którego korzystają `copy`, `copy_block` i instancjacja.
Frontend: `BarChart` (stacked SVG + linia celu), `PlanTygodniaPage` (widok 4)
z DnD i obowiązkowym wariantem przyciskowym, pięć dialogów + wspólny
`PlanningDialog`.

`task check` ZIELONY W CAŁOŚCI (exit 0): migrations-check (3),
test-unit (240), **test-int (147)**, **test-api (243)**, fe-test (198 w 19
plikach), typecheck (mypy 116 + vue-tsc), lint, format-check (126), fe-build.
Cykl migracji `upgrade head → downgrade base → upgrade head` przeszedł na
realnej bazie razem z asercją dokładnego zestawu tabel.

**Uwaga o środowisku (nie o kodzie)**: pierwsza sesja tego batcha nie mogła
uruchomić `test-int`/`test-api`, bo silnik WSL2 Docker Desktopa nie startował
(pipe `dockerDesktopLinuxEngine` nie istniał, `task dev-db` padało na
`unable to get image 'postgres:17'`). Restart Docker Desktopa to naprawił.
Pierwszy przebieg z bazą wyłapał wtedy błąd w TEŚCIE (nie w kodzie):
`text()` traktuje `:1` z literału JSON `"recipe_id":1` jako parametr wiązany,
więc wzorzec do `EXPLAIN` musi iść parametrem (`CAST(:pattern AS jsonb)`).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Zliczanie referencji w JSONB używa containmentu `@>`, nie
   `jsonb_path_exists`** — i to jest wiążące, nie stylistyczne. Indeks GIN
   założono klasą `jsonb_path_ops`, która obsługuje wyłącznie `@>`, `@?`, `@@`;
   funkcja `jsonb_path_exists` nie jest operatorem indeksowanym, więc planner
   zrobiłby seq scan po wszystkich szablonach przy każdym DELETE przepisu.
   Wzorzec: `payload @> '{"meals":[{"items":[{"recipe_id": X}]}]}'`, a dla
   tygodnia ten sam wzorzec zagnieżdżony w `days[].day`. ADR-012 domknięty
   po stronie kodu; test `EXPLAIN` wyłącza `enable_seqscan`, bo na pustej
   tabeli planner i tak wybrałby skan.
2. **Instancjacja to KOPIA bez live-sync.** Dni z szablonu/cyklu/bloku to
   zwykłe wiersze `plan_days/plan_meals/plan_meal_items` — B10 (zakupy) i B13
   (statystyki) nie muszą o szablonach wiedzieć nic. Konsekwencja dla B10:
   ten sam `recipe_id` może wystąpić w dniu wielokrotnie (szablon DOPISUJE,
   nie nadpisuje), więc agregacja musi sumować, nie deduplikować.
3. **`BarChart` istnieje — B13 go REUŻYWA, nie pisze drugiego.** Słupek jest
   stackowany, gdy `segments` ma >1 element, więc makro stacked to kwestia
   danych, nie komponentu. Skala jest wspólna dla wszystkich słupków i wciąga
   `target`, żeby linia celu nie wypadła z kadru. Kontrakt propsów w karcie B13.
4. **Payload `v:1` to kontrakt eksportu (B14).** Pełny kształt wpisany do karty
   B14 razem z ostrzeżeniem: import MUSI przemapować `recipe_id`/`product_id`/
   `member_profile_id` wewnątrz JSONB oraz `template_ids` w cyklach — baza nie
   pilnuje tych referencji żadnym FK.
5. **`start_date = NULL` w cyklu = „pierwszy tydzień ZAKRESU dostaje pierwszy
   szablon"**, nie „każdy tydzień dostaje pierwszy". Pierwsza implementacja
   robiła to drugie (cykl w ogóle nie rotował) — wyłapał to test jednostkowy.
   Rotacja jest cykliczna też przed `start_date` (tydzień wcześniej ⇒ ostatni
   szablon listy).
6. **KAŻDY payload przychodzący od użytkownika, który trafia do wiersza planu,
   MUSI przejść walidację scope na referencjach.** `/security-review` znalazł tu
   HIGH: payload szablonu przyjmował dowolne `recipe_id`, a `instantiate`
   przepisywał je do `plan_meal_items` — bez bramki, którą `add_item` ma od B06
   (`_assert_recipe_available`). Ponieważ `RecipesService.portion_values`
   ŚWIADOMIE nie filtruje scope (dzień rodzinny może zawierać prywatny przepis
   właściciela), `GET /plan/days` oddawał wtedy nazwę i wartości odżywcze
   cudzego prywatnego przepisu. Naprawione filtrem
   `ScopedQuery.visible_condition` w `_assert_references_alive` (przy zapisie
   ORAZ przy instancjacji; cudzy i nieistniejący dają ten sam komunikat).
   **Reguła dla B14 (import) i każdego batcha z payloadem JSONB: sprawdzenie
   ISTNIENIA id to nie autoryzacja.** Produkty kanoniczne są wyjątkiem —
   katalog jest globalny.
7. **Rejestry referencji rozszerza się DOKŁADAJĄC finder**, nie edytując
   `recipes/service.py` ani `catalog/service.py` — te pliki nie były w tym
   batchu ruszane. Nowe typy w `used_in`: `day_template`, `week_template`,
   `week_cycle`.
8. **Nowe komponenty OpenAPI payloadu mają sufiksy `-Input`/`-Output`**
   (Pydantic dzieli schemat, gdy walidacja i serializacja pola różnią się
   typem — `DecimalString` przyjmuje liczbę albo string, zwraca string).
   Żaden istniejący komponent nie zniknął ani nie zmienił nazwy; frontend
   trzyma oba aliasy w `api/templates.ts`.
9. **B06 nie miał commita.** Na starcie tej sesji PROGRESS pokazywał `[x]`,
   a `git log` stał na `batch(05)` — cała praca B06 leżała niezacommitowana.
   Właściciel zdecydował „najpierw commit `batch(06)`", więc B06 dostał własny
   commit `d6bacd7`. **Reguła na przyszłość: bramka wyjścia batcha to `git log`,
   nie kolumna w tabeli.**
10. Przy okazji naprawiony `ServingsSplitDrawer.spec.ts` z B06: `get(...)`
   zwraca wrapper BEZ `exists`, więc `vue-tsc` sypał 2x TS2339 i bramka nie
   mogła być zielona. Poprawka (`find(...).exists()`) weszła do commita B06.
11. **Trzy ustalenia z punktu 13 są PRZENIESIONE do karty R2** (sekcja Context
    „Ustalenia WEJŚCIOWE" + pozycje w Audit checklist i Implementation
    checklist) — z dowodami, plikami i rekomendacjami, żeby R2 nie odkrywał ich
    od nowa. Ten dziennik jest indeksem, karta R2 jest miejscem pracy.
12. Kolejna wolna migracja: `0010`. Karty zaktualizowane: B10 (dni z szablonów
    to zwykłe dni), B13 (kontrakt `BarChart`), B14 (payload `v:1` + remapowanie
    id). `03_DATABASE §6` i `04_API §2/§3` opisują stan faktyczny.
13. **Obraz kontenera `app` był przestarzały od B05** — brakowało w nim
    `Pillow` (`ModuleNotFoundError: No module named 'PIL'` z `core/uploads.py`),
    więc `app` wysypywał się na importach, a `task dev` dawał kontener
    `unhealthy`. To NIE jest wina B07 — obraz nie był przebudowany od dołożenia
    zależności. Lekarstwo: `task dev-detached` (`up --build -d`), nie samo
    `up -d`. **Reguła: nowa zależność w `pyproject.toml` = przebudowa obrazu,
    inaczej stack dev kłamie o stanie kodu.**
14. **E2E URUCHOMIONE pierwszy raz w projekcie — U15 ZOSTAJE OTWARTY.**
    Suita nigdy wcześniej nie przeszła przez logowanie, więc jedno uruchomienie
    odsłoniło warstwę problemów. NAPRAWIONE w tej sesji:
    - **kolizja z rate limitem**: `/auth/login` ma 5/min/IP (07_SECURITY §2),
      a suita logowała się OSIEM razy na sześciu workerach — po piątym leciało
      429 i specy padały LOSOWO na `toHaveURL(/plan-dnia/)`. Wygląda jak flake,
      jest zderzeniem testów z realnym zabezpieczeniem. Rozwiązanie: projekt
      `setup` (`e2e/auth.setup.ts`) loguje się RAZ i zapisuje `storageState`;
      specy testujące samo logowanie zerują stan u siebie. 8 logowań → 3.
    - **zły przepływ inline create przepisu** w `smoke.spec.ts` (B06)
      i `week-template-cycle.spec.ts` (B07): `recipe-picker-create` tylko
      OTWIERA drawer, a specy oczekiwały od razu zaznaczenia. Brakowało
      `recipe-create-submit`. Spec B06 nigdy nie był uruchomiony, więc błąd
      przeszedł do B07 przez skopiowanie wzorca.
    - **asercja słupka `BarChart`**: `<rect height=0>` ma zerowy bounding box,
      więc `toBeVisible()` na dniu bez posiłków zawodzi. Liczy się `data-height`.

    **ZOSTAJE do R2 — trzy sprawy, żadna w kodzie aplikacji:**
    a) **martwe przyciski `Button as="router-link"`** (9 wystąpień, 6 plików,
       B04/B05) — renderują sam TEKST, nie link: brak nawigacji i regres
       dostępności. Dowód: snapshot ARIA Playwrighta pokazuje
       `text: "Dodaj produkt"` tam, gdzie menu ma `link "Produkty"`. Blokuje
       `produkty.spec.ts` i `recipe-inline-create.spec.ts`. Poprawka to
       `:as="RouterLink"` (referencja komponentu, nie string) + test asercjujący
       `<a>`. **Zaparkowane decyzją właściciela.** B07 jest wolny od tego błędu
       — `PlanTygodniaPage` używa `<RouterLink>` wprost.
    b) **brak izolacji danych testowych**: specy używają STAŁYCH dat
       (`2031-03-05`, `2032-03-01`) i nie sprzątają po sobie, więc kolejny
       przebieg pada na cudzych danych — `plan-empty` nie jest już pusty,
       a szukajka trigramowa znajduje przepisy „Zupa E2E <stamp>" z poprzednich
       przebiegów i ukrywa opcję „+ Dodaj". Potrzebny teardown albo reset bazy
       E2E, nie kolejne łatki w asercjach.
    c) **wspólne konto + równoległość**: `households.spec.ts` przepisuje admina
       do nowej rodziny, gdy inne specy tworzą jako on encje ze scope; te
       dostają `household_id` tej rodziny (`ScopedQuery` zapisuje go także dla
       PRIVATE), więc sprzątające DELETE rodziny kończy się 409. Kod zachowuje
       się POPRAWNIE (jest druga linia obrony na `IntegrityError`) — to problem
       projektu testów. Uwaga na przyszłość: w tej ścieżce `used_in` jest puste,
       więc użytkownik nie wie, co blokuje usunięcie; moje trzy nowe tabele
       z `household_id RESTRICT` powiększają zbiór takich blokad.

**2026-08-17 — BATCH_06 (GOALS_AND_DAY_PLAN)**: plan dnia liczy się naprawdę.
Migracja `0008` (`user_nutrition_goals` + `plan_days`/`plan_meals`/
`plan_meal_items`/`plan_item_servings`, reużycie enumów `entity_scope`
i `amount_unit` z `0006`). Silnik dostał addytywnie `goal_status`
i `fit_servings_to_target` + typy progów (D9). Cele mieszkają w module
`nutrition` (02_DOMAIN §1), progi w `users.ui_settings` przez nowy
`PATCH /auth/me/ui-settings`. Nowy moduł `planning/` z pełnym `/plan/*`:
dni (pusty dzień zamiast 404), posiłki, pozycje (przepis albo produkt luzem),
rozkład rodzinny walidowany na Decimal, `/plan/copy` (głęboka kopia,
dopisywanie) i `fit-to-target`, który NICZEGO nie zapisuje. Frontend:
`PlanDniaPage` (widok 1), `NutritionBar`/`DonutChart` (własne SVG, ADR-013),
`MealCard`, `RecipePicker` z inline create, `ServingsSplitDrawer`, sekcje celów
i progów w ustawieniach.

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Test seedu, który schodzi migracjami poniżej head, MUSI wracać
   `upgrade head`, a nie `stamp head`.** `test_tags_seed.py` robił
   `downgrade 0006` + `_rerun_seed` (czyli `stamp head`), więc w chwili, gdy nad
   seedem stanęła migracja `0008`, reszta sesji testowej pracowała na bazie BEZ
   tabel planu — 57 błędów setupu w plikach, które z B06 nie mają nic wspólnego.
   Naprawione w tym batchu; ta sama pułapka czeka każdy przyszły seed.
   **Pochodna:** przerwany przebieg testów zostawia bazę `db-test` w stanie
   „znacznik na head, schematu brak" i KAŻDY kolejny przebieg pada na
   `TRUNCATE`. Ratunek: `DROP SCHEMA public CASCADE; CREATE SCHEMA public`
   + `alembic upgrade head` (follow-up dla R2 w Completion notes B06).
2. **Kontrakt pola `nutrition` przeniesiony**: `NutritionRead` i
   `nutrition_read()` mieszkają teraz w `app/modules/nutrition/schemas.py`
   (recipes je stamtąd importuje). Nazwa komponentu OpenAPI bez zmian.
3. **Mnożnik działa TAK SAMO dla przepisu i produktu luzem**: wartości pozycji
   = wartości jednej porcji × `servings` (02_DOMAIN §13.3). Dla produktu
   „jedna porcja" to zapisana ilość, więc B10 liczy zapotrzebowanie jako
   `amount x servings`. Rozkład rodzinny NIE skaluje ilości — jego suma jest
   z definicji równa `servings`.
4. **Reguła rozstrzygania dnia dla daty** (`PlanningService._resolve_day`):
   najpierw WŁASNY dzień, potem widoczny rodzinny. Widok tygodnia (B07)
   i instancjacja szablonów muszą używać tej samej reguły.
5. **Planning zarejestrował DWA liczniki referencji**: przepisów (rejestr B05)
   i produktów (rejestr B04). DELETE przepisu/produktu użytego w planie zwraca
   409 z `used_in` typu `plan_day` (nazwa = tytuł dnia albo `Plan dnia D.M.RRRR`).
6. **Zagnieżdżone id sprawdza się łańcuchem**: `/plan/meals/{id}` i
   `/plan/items/{id}` walidują `item → meal → day → scope`, nie samo istnienie
   id (04_API §2c). Ten wzorzec obowiązuje każdy zasób zagnieżdżony w encji
   ze scope (B07 szablony, B11 pozycje list).
7. **02_DOMAIN §7 miał literówkę w przykładzie rozkładu** („3×1.0 + 2×0.8 +
   2×1.3 ⇒ 6.2" daje 7,2). Poprawione na `2×1.0 + 2×0.8 + 2×1.3`; sama reguła
   „suma rozkładu = servings" bez zmian.
8. **Frontend ma nowe wspólne moduły**: `src/lib/dates.ts` (arytmetyka dat
   kalendarzowych — widok tygodnia B07 liczy nią daty), `src/lib/nutrition.ts`
   (etykiety i klasy statusów + `statusFor` do podglądu progów),
   `src/lib/decimal.ts += sumDecimals/decimalsEqual` (sumowanie bez floatów).
   `RecipePicker` powtarza kontrakt `ProductPickera` z prefiksem testid
   `recipe-picker-` — nowy picker przepisu w kolejnym batchu = błąd review.
9. Kolejna wolna migracja: `0009`. Karty zaktualizowane: B07 (faktyczne
   kształty planu i `copy`), B10 (zasady agregacji zapotrzebowania), B13
   (gotowe `goal_status`/`goal_for_day`/`thresholds_from_ui_settings`).
   `04_API` dostało `PATCH /auth/me/ui-settings`, `fit-to-target` oraz zasady
   §2c (łańcuch scope) i §2d (pusty dzień zamiast 404); `03_DATABASE §6` —
   stan faktyczny migracji `0008`.
11. **E2E `smoke.spec.ts` rozszerzony o plan dnia, ale NIEURUCHOMIONY** (brak
    Dockera w tej sesji) — dług U15 z R1 rośnie o ten scenariusz. `/plan-dnia`
    nie jest już placeholderem, więc stary asert `placeholder-page` zniknął.

**2026-08-17 — BATCH_05 (RECIPES_AND_NUTRITION_ENGINE)**: jest serce systemu.
Migracje `0006` (recipes/recipe_ingredients/tags/recipe_tags/recipe_ratings +
enumy `entity_scope`, `amount_unit`, `recipe_source` + GIN trigram na
`recipes.name`) i `0007` (idempotentny seed 9 tagów systemowych, w tym
„ulubione"). Czysty silnik `nutrition/{engine,types}.py` (Decimal, property-based,
pokrycie 100%), moduł `recipes/` (CRUD z filtrami, normalizacja składników
przy zapisie, oceny z upsertem, tagi z inline create), `core/uploads.py`
(sniffing+re-encode+miniatury) + auth-gated `GET /uploads/*`. Frontend:
`/przepisy` (grid + chipsy tagów), szczegół z regulacją porcji na żywo,
edytor z ProductPicker/AmountInput, RecipeCard; naprawy U9/U10 z R1.
Warunki R1 domknięte: D15 wdrożone (measure_kind → UNVERIFIED), D16
zaasercjonowane testem. `task check` zielony (3 migrations-check / 170 unit /
78 int / 184 api / 144 vitest / mypy 92 pliki / vue-tsc / ruff / eslint /
prettier / vite build).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Sygnatury silnika i `NutritionValues` są kontraktem** (karta B05,
   Cross-Batch Impact). `ingredient_nutrition` przyjmuje ilość na osi
   WARTOŚCI produktu (`to_basis_amount`); liczby w wyniku to SUMA
   Z DOSTĘPNYCH danych + `complete`/`missing` (braki i UNVERIFIED nigdy nie
   są cichym zerem). Wzór budowy wejść z ORM (przepakowanie `UnitWeight`,
   obsługa rozjechanego `measure_kind` po D15):
   `recipes/service.py::_ingredient_values` i `_build_ingredients`.
2. **Rejestr referencji przepisów**:
   `recipes.service.register_recipe_reference_finder(finder)` — B06 (plan)
   i B07 (szablony) MUSZĄ się zarejestrować, inaczej DELETE przepisu
   w użyciu da 409 bez listy `used_in` (druga linia: FK RESTRICT).
   Rejestr produktów działa: przepisy zgłaszają się do katalogu, DELETE
   produktu użytego w przepisie zwraca nazwę przepisu.
3. **Migracja `0006` utworzyła enumy** `entity_scope`, `amount_unit`,
   `recipe_source` — kolejne tabele ze scope/ilością używają
   `postgresql.ENUM(..., create_type=False)`. Fixture `scoped_notes_table`
   już NIE tworzy/nie kasuje `entity_scope` (typ należy do migracji);
   `test_catalog_seed._rerun_seed` celuje `upgrade 0005` + `stamp head`,
   bo powtórka migracji SCHEMATU na bazie z tym schematem = DuplicateObject.
4. **`recipes.import_job_id` bez FK** — dopina go migracja B15 razem
   z tabelą `import_jobs` (03_DATABASE §5, stan faktyczny).
5. **Upload obrazów ma jeden pipeline**: `core/uploads.py` + serving
   `GET /uploads/{path}` z sesją (poza `/api/v1`). B09 reużywa z własnym
   `subdir` — konkrety wpisane do karty B09. Nowa zmienna konfiguracji:
   `UPLOADS_DIR` (default `data/uploads`); w compose/prod wymaga bind mount
   (B17/B18). Nowe zależności: pillow, python-multipart (runtime);
   hypothesis, pytest-cov (dev).
6. **D15 wdrożone / D16 utrwalone testem** — szczegóły w 02_DECISIONS
   (oba czekają na formalny głos właściciela; testy wskazują, co zmienić
   przy odwrotnym rozstrzygnięciu).
7. **PUT /recipes/{id} wymienia składniki kompletem** (nowe wiersze, id
   pozycji nie są stabilne) — konsumenci nie mogą trzymać referencji do
   `recipe_ingredients.id`. Serce na karcie = tag systemowy „ulubione"
   (przypisanie per przepis, nie per user — uproszczenie z karty B05).
8. **Pułapka FastAPI**: query param typu Decimal deklaruj przez
   `Annotated[Decimal, Query(...)]` — `Field(...)` w Annotated jest
   ignorowany jako query (wzór: `?servings=` w `recipes/router.py`).
9. Kolejna wolna migracja: `0008`. Karty zaktualizowane: B06 (kontrakt
   silnika, rejestr referencji, amount_unit, pułapka Query), B09 (API
   uploadów). E2E `recipe-inline-create.spec.ts` napisany, NIEURUCHOMIONY
   (brak Dockera w tej sesji — dług U15 rośnie o jeden spec, do odhaczenia
   przed R2 razem z `produkty.spec.ts` i `households.spec.ts`).

**2026-08-16 — REVIEW R1 (REVIEW_FOUNDATIONS) — WERDYKT: PASS Z WARUNKAMI**

B05 może startować, o ile domknie ustalenia wpisane do swojej karty (sekcja
„Implementation Notes" → „Ustalenia review R1 do domknięcia w tym batchu").
Audyt objął cały kod od `0c872b4` do `833b4d1` (B01–B04) w jednej sesji:
wzorzec modułu, `ScopedQuery`, sesje/CSRF/rate limit, migracje, katalog
i wartości odżywcze, frontend, kontrakt komend.

**Warunki werdyktu:**

1. **Nie odwracać naprawy `basis_unit`** w `catalog/units.py` — silnik B05
   stoi na rozdzieleniu osi przechowywania (`base_unit`) i osi wartości
   „na 100" (`basis_unit`).
2. B05 wykonuje ustalenia U9, U10 i rozstrzyga w kodzie D15 + D16 (karta B05).
3. **D15 i D16 w 02_DECISIONS są OPEN** — decyzja właściciela najpóźniej
   w trakcie B05; bez odpowiedzi B05 utrzymuje stan faktyczny i asercjonuje
   go testem, żeby wybór był widoczny w kodzie, nie domyślny.
4. Przed R2: uruchomić E2E (`households.spec.ts`, `produkty.spec.ts`) i
   `task secrets-scan` na maszynie z Docker Desktop i wpisać wynik tutaj
   (dług wisi od B03).

**Ustalenia NAPRAWIONE w commicie review:**

- **U1 (blokujące dla B05)** `backend/app/modules/catalog/units.py:191` —
  konwersja jednostki domowej mnożyła ilość przez `grams_per_unit`, ale
  oznaczała wynik osią `base_unit`, czyli dla produktu `measure_kind=piece`
  „sztukami". `to_grams`/`to_basis_amount` mnożyły to po raz drugi przez
  `piece_weight_g`: dla jajka (105 g) „1 opakowanie = 600 g" dawało 63 000 g.
  Sprzeczne z docstringiem tej samej funkcji, z ADR-004 (wartości na 100 g)
  i z dziennikiem B04 pkt 3; niepokryte testem, choć `tests/unit/
  test_product_nutrition.py:153` buduje dokładnie taki produkt. Naprawa: nowa
  czysta funkcja `basis_unit(measure_kind)` (objętość → ml, masa i sztuki → g),
  użyta też przez `nutrition_adapter.nutrition_for` (jedna definicja osi) +
  dwa testy regresyjne. **Silnik B05 dostaje poprawną podstawę obliczeń.**
- **U2** `backend/migrations/versions/0005_seed_product_categories.py:82` —
  `downgrade()` kasował kategorie bez sprawdzenia referencji, więc na bazie
  z JAKIMKOLWIEK produktem kończył się `ForeignKeyViolation` (FK
  `canonical_products.category_id` ma RESTRICT). Odtworzone realnie na db-test.
  03_DATABASE §1 wymaga cyklu up/down/up na kopii REALNEJ bazy, a 09_DEPLOYMENT
  §4 dopuszcza migracje w dół „tylko gdy downgrade przetestowany" — test
  sprawdzał wyłącznie pustą bazę. Naprawa: `DELETE ... AND NOT EXISTS
  (SELECT 1 FROM canonical_products ...)` + test
  `test_downgrade_seedu_przechodzi_na_bazie_z_produktami`.
- **U3** `docker/compose.dev.yml:110` — warunek `[ -d node_modules/vite ]`
  nie odświeżał wolumenu po zmianie zależności (follow-up otwarty od B02).
  Teraz `npm ci` wykonuje się, gdy `package-lock.json` różni się od stempla
  w wolumenie. Logika `sh` przetestowana lokalnie (5 scenariuszy), YAML
  zwalidowany; **w kontenerze NIEURUCHOMIONE — brak Dockera w tej sesji.**
- **U4** `CLAUDE.md` — `task check` w tabeli komend pomijał `fe-build`;
  sekcja §4 („Fundament") kończyła się na B02, więc nie wymieniała
  `core/scope.py`, `core/deletion.py`, `core/schemas.py`, `catalog/units.py`,
  `catalog/nutrition_adapter.py` ani kontraktu `AuditService.record()`;
  akapit o testach mówił o JEDNYM miejscu na nową tabelę, a są DWA
  (`DB_TABLES` + `EXPECTED_TABLES`, plus `EXPECTED_ENUM_TYPES` dla enumów).
- **U5** `07_SECURITY §2` — dokument obiecywał „wykładniczy backoff po 10
  nieudanych", kod ma stałą blokadę 15 min z zerowaniem licznika
  (`core/security.py:153`). Kod ma rację (wystarcza na model zagrożeń §1),
  więc doprecyzowany dokument + wskazanie B17 jako miejsca rewizji parametrów.
- **U6** `07_SECURITY §3` — nieopisany drugi wyjątek CSRF: `POST /auth/login`
  (przed logowaniem nie ma cookie `csrf_token`, z którym można porównać
  nagłówek). Kod ma rację, dokument uzupełniony wraz z granicami ryzyka.
- **U7** `.claude/skills/ffp-{backend,frontend,security,domain-calc}` —
  wszystkie cztery opisywały stan „po B01" (ffp-security twierdził, że
  argon2/slowapi „dokłada B02" i że nagłówki CSP należą do B17, a już są;
  ffp-frontend, że LoginPage jest placeholderem; ffp-domain-calc, że kodu
  obliczeniowego nie ma). Nagłówki `verified` i inwentarze uzgodnione ze
  stanem repo; dopisany rozdział o dwóch osiach jednostek i o adapterze
  wartości. To domyka follow-up B02 pkt 4 (03_AI_SKILLS §8).
- **U8** karta `BATCH_R1` odwoływała się w trzech miejscach do nieistniejącego
  skilla `ffp-framework` — poprawione na cztery realne skille `ffp-*`.

**Ustalenia PRZEKAZANE dalej (follow-up z miejscem docelowym):**

- **U9 → karta B05** `frontend/src/pages/produkty/ProduktFormPage.vue:707`
  + `frontend/src/lib/texts.ts:117` — przeliczniki jednostek renderują się
  zawsze w gramach („1 szklanka = 250 g" dla mleka, mimo że wartość leży na
  osi ml — patrz `scripts/seed_demo.py:181`), a etykieta „Gramów na jednostkę"
  zachęca do wpisania gramów przy produkcie liczonym na 100 ml. R1 tego nie
  ruszał: zmienia zachowanie widoczne dla użytkownika (granica z karty).
- **U10 → karta B05** `frontend/src/components/domain/ProductCreateDrawer.vue:52`
  — ponowne otwarcie drawera nie czyści `measureKind`/`pieceWeight`, więc po
  dodaniu produktu „w sztukach" następny inline create startuje z tą miarą
  i starą wagą sztuki.
- **U11 → karta B05** `backend/scripts/seed_demo.py:288` — seed normalizuje
  etykiety jednostek przez `normalize_unit_label`, a serwis przez
  `canonical_unit_label` (`catalog/service.py:813`), który dodatkowo scala
  „opak." → „opakowanie" i odrzuca zarezerwowane „szt.". Dla dzisiejszych 15
  produktów wynik jest identyczny; to pułapka na rosnący seed.
- **U12 → karta B17** `task check` nie bramkuje świeżości `backend/openapi.json`
  i `frontend/src/api/generated.ts` (follow-up B01 pkt 1). W R1 sprawdzone
  realnie: `task fe-types` dał zerowy diff, więc kontrakt jest zgodny z kodem.
- **U13 → karta B17** `SECRET_KEY` jest wymaganą zmienną konfiguracji, ale
  żaden kod jej nie używa (sesje i CSRF biorą entropię z `secrets`).
  Do decyzji: zostawić jako zarezerwowaną i opisać, albo przestać wymagać.
- **U14 → karta B17** `backend/app/modules/accounts/service.py:178`
  i `backend/app/modules/households/service.py:154` — `ilike(f"%{query}%")`
  bez `autoescape=True`, czyli dokładnie ten błąd, który B04 naprawił
  w katalogu. Wyszukiwarki ADMIN-a, więc niski priorytet.
- **U15 → sesja z Docker Desktop, przed R2** E2E `households.spec.ts`
  i `produkty.spec.ts` nadal NIEURUCHOMIONE, `task secrets-scan` (gitleaks
  w kontenerze) NIEWYKONANY — w tym środowisku nie ma `docker` w PATH.
  Substytut wykonany w R1: `git ls-files` bez `.env`, grep sekretów po
  plikach śledzonych (0 trafień) i statyczna weryfikacja, że wszystkie
  `data-testid` używane w testach E2E istnieją w `frontend/src`.

**Decyzje OPEN dla właściciela (02_DECISIONS):**

- **D15** `backend/app/modules/catalog/service.py:451` — zmiana `measure_kind`
  przez USERA nie unieważnia weryfikacji, a przestawia podstawę wartości
  („na 100 g" ⇄ „na 100 ml"). Rekomendacja: zbijać do UNVERIFIED + audyt.
- **D16** `backend/app/core/scope.py:160` — `visible_condition` daje ADMIN-owi
  `true()` (macierz 08_TESTING §4: ADMIN ma 200 w każdym wierszu), a 04_API §3
  pkt 2 i 07_SECURITY §4 mówią, że ADMIN nie jest wyjątkiem na ścieżkach
  użytkownika — i tak działa `member_profiles` (jest na to test!). Dwa
  dokumenty nadrzędne mówią co innego, więc R1 nie rozstrzyga tego sam.
  Zmiana jest tania dopóki nie ma encji produkcyjnych ze scope, czyli do B05.

**Co sprawdzone i CZYSTE (bez ustaleń):** wzorzec modułu (żaden router nie
dotyka sesji DB — grep po `AsyncSession`/`get_session`/`session.`; brak logiki
w importach krzyżowych), kontrakt błędu 04_API §1 wraz z kodami 401/403/404/
409/422/429, macierz uprawnień 08 §4 per zasób z asertami (anty-IDOR: cudzy
profil i cudza notatka scope'owana → 404; `nutrition` produktu: anonim 401 /
USER 403 / ADMIN 200; D13: USER dostaje 403 z podpowiedzią archiwizacji),
CSRF (mutacja bez nagłówka → 403, także dla anonima przed routingiem), rate
limit (szósta próba w minucie → 429) i blokada konta (10 porażek → neutralne
401), cookies (HttpOnly/SameSite=Lax/Secure w prod, logout usuwa wiersz, TTL
przesuwne odświeża też cookie), argon2id + rehash, brak `Float` w modelach
i schematach, każdy `ForeignKey` z jawnym `ON DELETE` (8/8 w migracjach),
CHECK `scope_requires_household` egzekwowany przez bazę, adapter
`ProductNutrition` jako jedyne wejście obliczeń, zero kopii stanu serwera
w Pinia (jedyny store to sesja), zero wartości hex w komponentach, typy FE
wyłącznie z `generated.ts`.

**Wyniki uruchomień (realne):** `task check` zielony na wejściu (exit 0) i po
naprawach — 3 migrations-check / **146** unit / **65** int / 157 api / 141
vitest / mypy 73 pliki / vue-tsc / ruff / eslint / ruff format 79 plików /
prettier / vite build (przed R1 było 143 unit / 64 int; +3 testy do
`test_units.py` i +1 do `test_catalog_seed.py`). `task test-be` przed
naprawami: 363 testy zielone. `alembic heads` = `0005` (jedna głowa);
pełny cykl `upgrade head → downgrade base → upgrade head` wykonany na db-test
DWA razy: na bazie z produktem ujawnił U2 (`ForeignKeyViolation`), a po
naprawie przechodzi w tym samym scenariuszu i kończy na `0005 (head)`;
`task audit` —
pip-audit „No known vulnerabilities found", `npm audit --audit-level=high`
„found 0 vulnerabilities"; `/security-review` na całości zmian — **zero
ustaleń HIGH/MEDIUM** (39 route'ów przejrzanych po dependency, brak surowego
SQL, brak wycieku PII w schematach odpowiedzi), cztery obserwacje poniżej
progu, z których dwie weszły jako U5 i U13; `/code-review` — 6 ustaleń
(U1, U2, U9, U10, U11 + D15).

**2026-08-16 — BATCH_04 (UNITS_AND_CANONICAL_PRODUCTS)**: jest fundament danych.
Migracje `0004` (5 tabel katalogu + `pg_trgm` + indeks GIN trigram + CHECK-i)
i `0005` (idempotentny seed 14 kategorii z `perishability`), moduł
`app/modules/catalog/` z czystymi `units.py` (konwersje g/ml/szt + jednostki
domowe) i adapterem `ProductNutrition`, `app/core/deletion.py` (kontrakt 409
`used_in`), pełne API produktów/kategorii/przeliczników z wyszukiwarką
trigramową i audytem before/after przy wartościach odżywczych. Frontend:
`/produkty` (lista + szukajka + filtry), formularz produktu (wartości
edytowalne tylko dla ADMIN), `/admin/weryfikacja`, obowiązkowy `ProductPicker`
+ `ProductCreateDrawer`, `AmountInput`, `src/lib/format.ts`. `task db-seed-demo`
przestał być placeholderem (15 produktów, idempotentnie). `task check` zielony
(3 migrations-check / 142 unit / 64 int / 157 api / 141 vitest / mypy 73 pliki /
ruff / eslint / prettier / vite build).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Wartości odżywcze czyta się WYŁĄCZNIE adapterem `ProductNutrition`**
   (`catalog/nutrition_adapter.py`: `nutrition_for`, `measure_for`). Sięgnięcie
   silnika po kolumny `canonical_products` albo po `product_nutrient_values`
   = błąd review (ADR-004). Adapter daje `is_complete`, `has_core_macros`,
   `has_glycemic_index`, `missing` (komunikaty PL) i `digestible_carbs_100`.
2. **Kolumny rdzenia (`kcal_100` … `carbs_100`) są NULLOWALNE** — odstępstwo od
   literalnego 03_DATABASE §3, wymuszone przez inline create USERA
   (dokument zaktualizowany). Brak wartości NIGDY nie jest zerem: konsument
   pokazuje `complete=False` i listę braków.
3. **Każda ilość przechodzi przez `catalog/units.py`**: `normalize_amount(qty,
   unit_label, ProductMeasure) -> NormalizedAmount(amount, unit ∈ g|ml|piece)`,
   `to_grams`, `to_basis_amount`; nieprzeliczalna ilość rzuca
   `UnitConversionError` (AppError → 422) i zapis MUSI paść. Jednostka domowa
   daje ilość na osi bazowej produktu (ml dla VOLUME!), a `to_grams` odmawia
   przeliczenia ml → g.
4. **Blokada usuwania ma punkt wpięcia**: `app/core/deletion.py` (`UsedInRef`,
   `assert_deletable`, `conflict_from_integrity_error`) + rejestr
   `catalog.service.register_product_reference_finder(finder)`, gdzie
   `finder(session, product_id) -> Sequence[UsedInRef]`. Moduł z FK do
   `canonical_products` (B05 przepisy, B08 spiżarnia, B09 retail, B11 listy)
   MUSI się zarejestrować, inaczej 409 wyjdzie bez listy „Używane w:".
5. **Usuwanie produktu kanonicznego to wyłącznie ADMIN (D13)** i regułę
   egzekwuje SERWIS, nie `AdminUser` w routerze — dzięki temu 403 podpowiada
   archiwizację. Ten sam wzorzec warto powtórzyć tam, gdzie 403 ma uczyć.
6. **Nowe akcje audytu**: `product.create`, `product.update`,
   `product.nutrition_update`, `product.verify`, `product.archive`,
   `product.restore`, `product.delete`, `product_unit_weight.*`,
   `product_category.*` (encje `product`, `product_category`).
7. **Frontend — komponenty obowiązkowe już istnieją**: `ProductPicker`
   (props `modelValue`/`label`/`limit`/`disabled`/`debounceMs`, emits
   `update:modelValue` i `selected`), `ProductCreateDrawer`, `AmountInput`
   (`modelValue` to STRING dziesiętny). Ilości formatuje TYLKO
   `src/lib/format.ts` → `formatAmount` (g→kg ≥1000, przecinek PL).
   Nowy picker/własny select w kolejnym batchu = błąd review.
8. **Nowa zmienna konfiguracji**: `CATALOG_SEARCH_SIMILARITY_THRESHOLD` (0.25).
   Kolejna wolna migracja: `0006`. Nowa tabela nadal = wpis w `DB_TABLES`
   (conftest) **i** `EXPECTED_TABLES` (`test_migrations.py`); doszła też stała
   `EXPECTED_ENUM_TYPES` — migracja z enumem dopisuje tam swój typ.
10. **Karty zaktualizowane**: B05 (units/adapter/rejestr referencji + API
   pickera i AmountInput), B08 i B09 (rejestr referencji, kontrakt komponentów,
   `catalog` jako moduł do rozbudowy, nie do zduplikowania).
10. **Follow-upy dla R1**: E2E `produkty.spec.ts` i `households.spec.ts`
    napisane, ale NIEURUCHOMIONE (brak Dockera); `db-seed-demo` bez trybu
    `--reset`; indeks GIN trigram nieużywany przez warunek `similarity >= próg`;
    wciąż otwarty `compose.dev.yml` / `node_modules` z B02.

**2026-08-16 — BATCH_03 (HOUSEHOLDS_AND_SCOPE)**: są rodziny i jest jedno
miejsce egzekwowania widoczności. Migracja `0003` (`households`,
`member_profiles`, `audit_entries`, `users.household_id`), `app/core/scope.py`
(`Scope`, `ScopedMixin`, generyczny `ScopedQuery`) udowodniony pełną macierzą
08 §4 na encji testowej `ScopedNote`, moduł `audit` (`record()` append-only
+ `GET /api/v1/audit` dla ADMIN, audit dopięty wstecznie do operacji B02 na
kontach), `/admin/households` z `set_members`, `/households/my` i CRUD profili.
Frontend: `/ustawienia` z sekcją rodziny i profilami, `/admin/rodziny`,
`authStore.household`, `src/lib/decimal.ts`. `task check` zielony
(3 migrations-check / 92 unit / 36 int / 118 api / 73 vitest / mypy 57 plików /
ruff / eslint / prettier / vite build).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Żadnych własnych filtrów widoczności** — każda encja współdzielna
   konsumuje `ScopedMixin` + `ScopedQuery` z `app/core/scope.py`
   (`get_or_404`, `select_visible`, `assert_can_manage`,
   `ownership_for_create`). Ręczny filtr scope w serwisie = błąd review.
   Cudza encja to **404, nie 403**. Konkretny przykład użycia wklejony do
   karty B05.
2. **Typ enumowy `entity_scope` jeszcze NIE istnieje w bazie** — B03 stworzył
   sam mechanizm, bez produkcyjnej tabeli. Tworzy go migracja `recipes`
   (B05); każda kolejna tabela ze scope musi wtedy użyć
   `postgresql.ENUM(..., create_type=False)`.
3. **Kontrakt 409 `used_in` ustalony**:
   `details = {"used_in": [{"type", "id", "name"}]}`. Referencje liczy się
   PRZED usunięciem, a `IntegrityError` z commita łapie jako drugą linię
   obrony — inaczej użytkownik dostaje 500 zamiast 409. Obowiązuje każde
   usuwanie od B04 (ADR-012).
4. **`AuditService.record()` NIE commituje** — wpis powstaje w tej samej
   transakcji co operacja. Serwis domenowy trzyma `self._audit =
   AuditService(session)` i robi jeden `commit()`. Nowa akcja = wpis
   w `AuditAction`/`AuditEntity` (konwencja `<encja>.<czasownik>`).
   Decimal w payloadzie serializowany przez `format(value, "f")`, nigdy float.
5. **`app/core/schemas.py` → `DecimalString`** — każde pole NUMERIC
   w odpowiedzi używa tego aliasu (OpenAPI `string` ⇒ `task fe-types`
   generuje `string`). Ograniczenia wejścia jako Annotated, bo mypy odrzuca
   `Field(**dict)`. Po stronie FE parser jest jeden: `src/lib/decimal.ts`.
6. **Nowa tabela = wpis w DWÓCH miejscach testowych**: `DB_TABLES`
   (`tests/conftest.py`, TRUNCATE) **i** `EXPECTED_TABLES`
   (`tests/integration/test_migrations.py` — asercja na dokładny zestaw
   tabel po `upgrade head`). Kolejna wolna migracja: `0004`.
7. **Karty zaktualizowane**: B04 (konkrety audytu, `DecimalString`, prototyp
   409, `src/lib/decimal.ts`) i B05 (gotowy przykład użycia `ScopedQuery`
   + instrukcja tworzenia `entity_scope`).
8. **Follow-up dla R1**: E2E `frontend/e2e/households.spec.ts` jest napisany,
   ale NIE został uruchomiony — sesja domykająca batch nie miała Dockera.
   Do odhaczenia na maszynie z Docker Desktop. Wciąż otwarty także follow-up
   z B02 (`compose.dev.yml` nie odświeża `node_modules`).
9. **Domknięcie B03 zrobiła inna sesja niż implementacja** (checklisty,
   Completion notes, PROGRESS, commit) — notatki w karcie opisują stan kodu,
   nie intencje autora.

**2026-08-16 — BATCH_02 (AUTH_AND_ACCOUNTS)**: aplikacja ma prawdziwe
logowanie. Sesje server-side w PG (cookie `ffp_session` HttpOnly, TTL 30 dni
przesuwne), argon2id z rehashem, CSRF double-submit i nagłówki bezpieczeństwa
jako middleware, rate limit slowapi 5/min/IP na `/auth/login` + blokada konta
(10 porażek / 15 min, stan w `users`), `/admin/users` CRUD, CLI
`task create-admin`. Frontend: authStore (Pinia), guard routera, LoginPage
(vee-validate + zod), AppShell z pełną nawigacją (sidebar + bottom-nav),
`/admin/uzytkownicy`. `task check` zielony (54 unit / 18 int / 55 api /
39 vitest / mypy / vue-tsc / ruff / eslint / prettier / vite build), E2E smoke
login→plan-dnia→logout zielony na compose.

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Autoryzacja ma jedno wejście**: `app/core/deps.py` → `CurrentUser`,
   `AdminUser`, `require_admin`. Nowy moduł ich UŻYWA, nie czyta cookie sam.
   Cookies (nazwy, atrybuty, odświeżanie) — `app/core/cookies.py`.
2. **Każda mutacja wymaga nagłówka `X-CSRF-Token`** — także w testach API
   (`tests/helpers.py`: `login`, `csrf_headers`). Middleware CSRF działa
   PRZED routingiem, więc POST bez tokenu daje 403, a nie 404/405.
   Wyjątki to lista prefiksów `CSRF_EXEMPT_PREFIXES` w
   `app/core/middleware.py` — `/api/v1/public/` jest już wpisany dla B11.
3. **Nowy moduł z tabelami = jedna linia w `backend/app/models.py`**
   (rejestr modeli). Bez tego `Base.metadata` jest niepełna i Alembic nie
   widzi schematu. Kolejna wolna migracja: `0003`.
4. **Testy z bazą**: fixture'y `db_session` (serwisy) i `db_client` (HTTP)
   w `tests/conftest.py`; nową tabelę dopisz do stałej `DB_TABLES`
   (TRUNCATE między testami). Fabryki w `tests/factories.py`. `tests/`
   jest teraz pakietem (`__init__.py`) — inaczej mypy widzi moduł dwa razy.
   Część testów `api` dotyka bazy, więc `task test-api` wymaga db-test.
5. **Schematy ODPOWIEDZI nie walidują emaila** (`str`, nie `EmailStr`) —
   walidacja należy do wejścia, inaczej starszy wiersz wysadza odczyt 500.
   Ta sama reguła obowiązuje przyszłe schematy read-only.
6. **Nowa zależność frontendu wymaga ręcznego odświeżenia node_modules
   w kontenerze**: `docker compose --env-file .env -f docker/compose.dev.yml
   exec frontend npm ci` + restart serwisu. Wolumen nazwany nie aktualizuje
   się sam (`npm ci` w compose odpala się tylko przy pustym katalogu).
7. **Nawigacja i teksty**: pozycje menu w `src/lib/navigation.ts` (jeden
   wpis = sidebar + bottom-nav), teksty wielokrotnego użytku w
   `src/lib/texts.ts`, trasy z placeholderami w `src/router.ts` — batch
   domenowy podmienia `component`, nie dokłada nowego wpisu nawigacji.
8. **Karty zaktualizowane**: B03 (konkrety fundamentu auth), B04 (trasa
   „Produkty" gotowa), B11 (wyjątek CSRF i limiter już istnieją),
   B17 (nagłówki/CSP JUŻ są — batch je przegląda, nie tworzy; dochodzi
   przegląd IP za reverse proxy i parametrów argon2/TTL).
9. **Follow-up dla review R1**: `docker/compose.dev.yml` nie odświeża
   `node_modules` (pkt 6) — poprawka jednej linii, świadomie nie robiona
   w B02 (poza zakresem).

**2026-08-16 — BATCH_01 (PROJECT_SCAFFOLD_AND_DEV_LOOP)**: monorepo stoi.
Backend FastAPI (`create_app()`, `/api/v1/health`, config/db/errors/logging),
Alembic z pustą rewizją `0001`, frontend Vite+Vue3+TS strict+Tailwind 4
z tokens 06_UIUX i shadcn-vue, `docker/compose.dev.yml` (app + frontend + db
+ db-test na tmpfs), `Taskfile.yml`, CLAUDE.md, uzgodnione 4 skille ffp-*.
`task check` zielony (16 unit / 2 int / 5 api / 8 vitest / mypy / vue-tsc /
ruff / eslint / prettier / vite build), E2E smoke `/login` przechodzi.

**Co MUSZĄ wiedzieć kolejne batche:**

1. **DB jest asynchroniczna — nowy ADR-015** (SQLAlchemy async + psycopg 3).
   Serwisy dostają `AsyncSession` z `app.core.db.get_session`, są `async`.
   Na Windows narzędzia hosta (alembic, pytest) wymuszają SelectorEventLoop —
   gotowe w `db.py` i `tests/conftest.py`; natywny `uvicorn` na Windows
   z dostępem do bazy NIE jest wspierany (pętla dev stoi w Dockerze).
2. **Nie ma `app` na poziomie modułu** — `uvicorn app.main:create_app
   --factory`; router nowego modułu rejestruje się w `create_app()`.
3. **Błędy**: rzucaj `AppError`/`NotFoundError`/`ForbiddenError`/
   `ConflictError` z `app/core/errors.py`, nigdy `HTTPException`.
4. **Markery pytest są obowiązkowe** (`pytestmark = pytest.mark.unit|
   integration|api`) — test bez markera nie trafi do żadnego targetu.
   Testy integracyjne jadą na `TEST_DATABASE_URL` (db-test); `conftest`
   podmienia `DATABASE_URL`, żeby downgrade nie tknął bazy dev.
5. **Kontrakt komend**: `Taskfile.yml` + `CLAUDE.md` + skille ffp-* to jeden
   organizm — zmiana nazwy targetu wymaga aktualizacji wszystkich trzech.
   `task check` zawiera dodatkowo `format-check`, `fe-build` i
   `migrations-check` (jedna głowa migracji).
6. **`task fe-types`** generuje `backend/openapi.json` **i**
   `frontend/src/api/generated.ts` — oba commitowane (diff API w Review).
   TypeScript przypięty do ~5.9 przez peer dependency openapi-typescript.
7. **Karty zaktualizowane**: B02 (konkrety fundamentu), B12 (vite-plugin-pwa
   JEST już wpięty — B12 dokłada strategie i ikony PNG), B17 (stage prod
   Dockerfile, health `degraded`, nagłówki/CSP).
8. **D12 rozstrzygnięte tego samego dnia — bez Ansistrano**: wdrożenie
   zostaje na procedurze z 09_DEPLOYMENT §4 (`git pull` → build → backup →
   `alembic upgrade head` → `compose up -d`), B18 opakowuje ją w skrypt.
   Blokery B18 to nadal tylko D6 i D7.

**2026-08-16 — PLAN**: Blueprint utworzony (architektura 01–09, ADR-001–014,
audyt PDF, decyzje D1–D11, karty batchy 01–18 + R1–R4, master prompt).
Zatwierdzone D1–D5; otwarte D6/D7 blokują wyłącznie B18. Pierwszy batch
do zlecenia: **BATCH_01_PROJECT_SCAFFOLD_AND_DEV_LOOP**.
