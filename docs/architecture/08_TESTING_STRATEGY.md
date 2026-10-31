# 08 — Strategia testów

Zasada nadrzędna: logika obliczeniowa (żywienie, jednostki, agregacja,
opakowania, tury) jest deterministyczna, czysta i pokryta testami blisko
100%. Testy są warunkiem DoD każdego batcha — agent raportuje REALNE wyniki
uruchomień, nigdy „powinno przejść".

UX01 / 2026-10-30: `task test-e2e-linux` uruchamia tę samą suitę, kod i lokalną
bazę w oficjalnym obrazie Playwright 1.62.1, ze współdzielonym localhost
kontenera frontend. Nie jest oddzielnym środowiskiem danych: nadal obowiązuje
jedna rezerwacja DB/E2E. Obraz i zainstalowany pakiet muszą mieć tę samą wersję.
Windows Chromium dwukrotnie przerwał pobranie modułu bootstrapu błędem
`ERR_NO_BUFFER_SPACE`, przy niewielkiej liczbie połączeń i dużej wolnej pamięci.
To odpowiada zgłoszeniu [Playwright #43545](https://github.com/microsoft/playwright/issues/43545);
związek z `TcpPortRandomizationWin` jest wnioskiem, nie pomiarem NetLog naszego
hosta. Linux omija tę ścieżkę systemową bez instalacji alpha, zmiany lockfile,
nadpisania wbudowanych flagów Chromium lub ustawień sieciowych Windows.

UX03 / 2026-10-31: `task check DB_TEST_RUNTIME=linux` zachowuje wszystkie
bramki, a `test-int` i `test-api` wykonuje w jednorazowym kontenerze z obrazu
lokalnego dev API. Backend konkretnego worktree jest montowany tylko do
odczytu; baza pozostaje tą samą `db-test`, po wewnętrznym adresie sieci compose.
Runner dopuszcza wyłącznie dev/test, localhost i nazwy `pasnik_test` lub
`pasnik_ux_test`; oba URL-e są kierowane do testowej bazy, a poświadczenia
przechodzą przez env. Cache i uploady są tymczasowe. Domyślny runtime nadal
jest hostowy; `CLI_ARGS` działają w obu wariantach. Tryb Linux omija ścieżkę
połączeń hosta, która przerwała jeden test Windows błędem 10048. Nie ustalono
dokładnej przyczyny tego błędu ani wyczerpania portów. Nadal obowiązuje jedna
rezerwacja DB/E2E i rzeczywiste kody wyjścia wszystkich testów.

## 1. Piramida i narzędzia

| Poziom | Narzędzie | Zakres | Uruchomienie |
|---|---|---|---|
| Backend unit | pytest | silnik nutrition, konwersje jednostek, shopping engine, raport DRY-RUN transferu — czyste funkcje, bez DB | `task test-unit` (sekundy) |
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
10. **Kopia danych rodziny (transfer)**: round-trip eksport → CZYSTA baza →
    import (`tests/integration/test_transfer_roundtrip.py`), kolizje i rollback
    (`test_transfer_collisions.py`), granice zakresu i macierz uprawnień
    (`tests/api/test_transfer_api.py`), a sam raport DRY-RUN — jako funkcja
    CZYSTA — w `tests/unit/test_transfer_serializer.py`. Dwa niezmienniki,
    które trzeba trzymać testem, bo psują się cicho: **raport obiecuje
    dokładnie to, co utworzy zapis** (`to_create == created`, dług U21) oraz
    **kopia rodziny nie niesie prywatnych encji innych członków** (D26).
    Import jadłospisów PDF razem z całym swoim pakietem testów (korpus,
    parser, review, AI) został usunięty w BATCH_20 — decyzja **D25**.

## 3. E2E (Playwright) — utrzymywany mały i stabilny

Smoke (każdy batch): login → plan dnia → dodanie posiłku → wylogowanie.
Core flows (rozbudowywane w batchach, które je dostarczają):
1. Przepis z inline create produktu → wartości per porcja.
   UX08: `ux-editor.spec.ts` na390/1024 sprawdza rzeczywisty klik etykiety
   drugiej z dwóch wyszukiwarek, pozostanie po klawiaturowej próbie wyjścia,
   walidację wiersza, kontrolowane odpowiedzi422/403/409 zachowujące dane
   i potem rzeczywisty zapis z GET ilości12.500. Asercje geometrii po422
   dowodzą widoczności fokusu poza paskiem zapisu i mobilną nawigacją.
   `recipe-global` sprawdza rzeczywisty USER read-only i kopię w edytorze.
   Visual rozróżnia podstawowy i rozwinięty edytor; zdjęcie potwierdza dopiero
   po natywnym otwarciu sekcji klawiaturą. Unit testy nie deklarują geometrii
   jsdom jako dowodu widoczności; obejmują guardy/refetch/generację sesji.
   Fixture visual obejmuje rzeczywiste jednostki g/ml/szt. na pięciu
   szerokościach: pomiar miejsca na etykietę i natywną strzałkę po załadowaniu
   fontu oraz PNG. Regresja musi być czerwona przy zwężaniu wyboru jednostki.
2. Tydzień: kopiuj dzień, szablon, cykl. UX07 rozszerza rzeczywiste E2E
   o kalendarz klawiaturą przez koniec roku, dwa cele z zachowaniem zajętego
   dnia, pełne nazwy, powrót ze szczegółu (dedykowany i browser
   Back) oraz zakres zakupów. `ux-week.spec.ts` dołącza rzeczywiste PNG
   agendy i załadowanego kalendarza na360/768/1024 oraz dołu podglądu
   na360/1024. Testy komponentów sprawdzają cele wejść tygodnia do panelu
   UX03, odrzucony refetch z cache, pusty dzień,
   archiwalne/brakujące odniesienia oraz ograniczony podgląd skrajnego cyklu.
3. Zakupy: generacja → pytanie o spiżarnię → preview z resztkami →
   finalizacja → publiczny link → odhaczenie bez logowania.
   Dwa specy: `shopping-generate.spec.ts` (B10, do finalizacji) i
   `shopping-list-sharing.spec.ts` (B11, od strony listy do odwołania linku).
   Publiczny link otwiera się w OSOBNYM kontekście przeglądarki
   (`browser.newContext()` — bez `storageState`), inaczej test przechodziłby
   także wtedy, gdy strona publiczna po cichu korzysta z cookies sesji.
4. Kopia danych rodziny: pobranie kopii → wczytanie TEGO SAMEGO pliku →
   raport kolizji → wczytanie → podsumowanie (`transfer.spec.ts`). Spec jedzie
   po `data-testid`, więc przemianowanie sekcji na „Kopia danych rodziny"
   (B20) go nie dotyka.
5. Spiżarnia i produkty UX09: `ux-pantry-products.spec.ts` tworzy własną
   kategorię55produktów/105partii i sprząta wyłącznie swoje dane. Sprawdza
   filtr serwera, edycję drugiej strony, zapis0,25g potwierdzony GET,
   transporterror zachowujący szkic, Escape/Enter/powrót fokusu, powrót
   biblioteki i cold reload. Używa rzeczywistych polskich `missing` z API
   oraz klawiaturowego otwarcia/odczytu/zamknięcia szczegółów; mierzy nazwę
   pilnego zapasu na390. Dziewięć PNG obejmuje pantry/form390/768/1024,
   bibliotekę390/1024 i panel390. Unit testy dodatkowo dowodzą budżetu żądań
   przy ogromnym `pages`, zachowania głębszego cache/fokusu oraz ręcznego
   pobierania po częściowym odtworzeniu.
6. Ustawienia i podsumowanie UX10: `ux-settings-summary.spec.ts` używa
   własnego USER-a i rodziny, sprawdza cztery zakładki klawiaturą, błąd422
   z zachowanym szkicem, profile, historię celów i progi na390/1024.
   `statystyki.spec.ts` sprawdza rzeczywiste luki i neutralne średnie całego
   planu, odrębną historię celu konta oraz zakres92dni. `retail-stores`
   otwiera Zakupy także po reload i potwierdza trwałość kolejności przez API.
   Opt-in `UX_ADMIN_VISUAL=1` / `ux-admin-visual.spec.ts` wykonuje odczyty
   czterech ekranów administracji z rzeczywistą sesją ADMIN, bez mutacji.
   Włączenie `households.spec.ts` uruchamia cały projekt chromium jako
   zależność; taki przebieg należy raportować według faktycznych testów,
   a nie przedstawiać jako małą suitę zawężoną argumentami CLI.
Konwencje: selektory `data-testid`, gotowość UI przez expect z timeoutem,
seed przez API, nie przez UI. Wyjątek czasu w UX06 dotyczy jawnego wygaśnięcia
rzeczywistego staleTime (31 s przy 30 s konfiguracji): test dwóch kart wymaga
potem rzeczywistego GET po nawigacji UI. Nie zastępuje to asercji gotowości,
nie zmienia ustawień aplikacji i nie jest ponawianiem nieudanego żądania.

### 3.1 Izolacja danych (stan faktyczny po review R2, 2026-08-21)

Suita jedzie na bazie DEWELOPERSKIEJ. Bazowe specy dzielą konto ADMIN,
scenariusze izolowane mają oznaczonych własnych aktorów i EMPTY_STATE.
Hasła pochodzą z env albo są losowane wyłącznie w pamięci; katalog produktów
jest globalny. Specy nie są niezależne, poniższe reguły są wiążące:

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
6. **Roundtrip transferu ma świeżego USER-a i pusty browser context.**
   `transfer.spec.ts` eksportuje i importuje dane wyłącznie tego konta,
   zachowuje pobrany ZIP oraz sprawdza rzeczywistą kolizję i kopię przepisu.
   Finally usuwa własne przepisy i konto. Nie używać wspólnego ADMIN-a:
   import historii generacji/tur jest addytywny, więc powtarzany roundtrip
   kopiuje całą jego historię. Nie odwiedzać Zakupów w tym scenariuszu —
   odczyt konfiguracji zasiewa domyślne tury. Limity importu pozostają aktywne.
7. **Generator zakupów ma własnego oznaczonego USER-a i dwie tury.**
   `shopping-generate.spec.ts` nie używa historii ADMIN-a. Exact marker,
   rzeczywiste /me i odmowa administracji poprzedzają sprzątanie własnych dat,
   list i tur. Finally dezaktywuje aktora; historia z FK pozostaje. Nie kasować
   konfiguracji współdzielonego konta ani nie zwiększać timeoutu zamiast izolacji.

### 3.2 Odbiór zbudowanego PWA (UX06)

`task test-pwa` buduje frontend, przełącza wyłącznie lokalny frontend na preview,
wykonuje `ux-pwa.spec.ts` w oficjalnym Playwright 1.62.1 i przez defer przywraca
Vite dev również po FAIL. Readiness działa we wskazanym kontenerze, niezależnie
od hostowego FRONTEND_PORT. Nie restartuje API/baz i nie tworzy nowego środowiska.

`task test-pwa-advanced` uruchamia oddzielne opt-in UX_PWA_ADVANCED: dwie karty
listy/planu z rzeczywistą opóźnioną odpowiedzią, potwierdzoną zmianę rodziny A2
z przywróceniem dokładnych składów w finally oraz aktualizację starego buildu
SW na tym samym originie. Upgrade wymaga zachowanego legacy artefaktu
`backend/data/ux06-results/legacy-dist-before-isolation`; test sprawdza ścieżki,
kopiuje wyłącznie wygenerowane dist i zawsze przywraca nowy build. Nie używa
syntetycznego service workera. Brak artefaktu przy opt-in jest błędem, nie skipem.

Oba runnery używają --no-deps (bez szerokiego purge setup), workers=1,
prawdziwego context.setOffline i rzeczywistych odmów backendu. PWA odczyty
kontrolne i opóźniony GET używają bezpiecznego Node fetch, bez instrumentowanych
context.request/route.fetch, które przy awarii zapisują Cookie w krokach raportu.
Opóźniony GET nadal dostarcza rzeczywiste status/nagłówki/body z backendu.
Publiczne tokeny, cookie i hasła nie trafiają do raportów tych prób;
trace/video/screenshot są wyłączone.
Świadectwa observera sprawdzają też krótkotrwałe ujawnienie po zamknięciu sesji.
Samo działanie otwartej karty nie dowodzi cold restartu ani izolacji kont.

Próba pending po prywatnym cold restarcie obejmuje rzeczywiste ponowne otwarcie
aplikacji online po przywróceniu transportu. Chromium może po cold reload
optymistycznie podawać navigator.onLine=true i nie wyemitować nowego online;
Playwright domyślnie emuluje fokus, więc bringToFront nie dowodzi jego zmiany.
Reload sprawdza udokumentowaną pobudkę kolejki przy starcie z ADR-009,
bez syntetycznych zdarzeń i bez zmiany navigatora. Obowiązkowe pozostają browser /me przed PATCH,
niezależny serwerowy GET, zniknięcie bannera oraz przywrócenie jednej pozycji.
To dowód recovery po ponownym otwarciu aplikacji, nie zdarzenia online/focus.

Wypełnianie pola hasła przez `fill` zapisuje jego wartość w tytule kroku HTML.
`e2e/secret-password.ts` używa osobnego argumentu evaluate, natywnego settera
input i zdarzenia input; nadal działa zwykły formularz i żądanie logowania.
Wywołujący muszą również wyłączyć trace: ślad zawiera argumenty evaluate
i body logowania, także przy retry CI. Dotyczy setup/smoke/global/navigation
oraz PWA/visual. Kontrola raportu odczytuje embedded ZIP bez wypisywania
sekretów; stary artefakt po redakcji zachowuje wynik i dowody testu.

`task test-shopping-print` uruchamia oddzielny opt-in `UX_PRINT=1` na dev,
z normalnym projektem setup i jednym workerem. Własny oznaczony USER tworzy
50 rzeczywistych długich produktów i listę, a finally sprząta wyłącznie jego
dane oraz dezaktywuje konto. HTTP setup/cleanup używa natywnego Node fetch,
aby wyjątek transportu nie zapisał Cookie/CSRF jako kroku APIRequestContext
w raporcie Playwright. Błędy transportu/body są ogólne, bez raw cause.
Trace, video i screenshot są wyłączone. Anonimowy GET potwierdza brak Cookie,
CSRF i prywatnych pól; oba rzeczywiste PDF A4 mają wszystkie wiersze,
również kupione zwinięte na ekranie. O renderuje każdą stronę do PNG,
sprawdza tekst/ilości, granice stron i brak podziału wiersza oraz wykonuje
niezależny odbiór wizualny. Sama emulacja print CSS nie zastępuje tego odbioru.

Każda rzeczywista próba logowania API/UI, także niepoprawne hasło i opt-in
visual, wywołuje `reserveLoginAttempt` z `e2e/login-budget.ts`. Helper
rezerwuje slot przed wysłaniem i zapisuje tylko timestampy w ignorowanym
`e2e/.auth/login-attempts.json`. Wspólny budżet pięciu prób na 60 sekund
z buforem obejmuje restarty workerów i kolejne przebiegi Windows/Linux.
Oczekiwanie wynika z końca okna; helper nie ponawia odrzuconych żądań i nie
zmienia limitu backendu. Nieprawidłowy plik lub rozbieżny zegar przerywa test
bez resetowania budżetu. Timeout testu/hooka rośnie tylko o wyliczony czas
oczekiwania, a timeouty asercji pozostają bez zmian.

`server.watch.ignored` Vite pomija `e2e/.auth/**` obok raportów i wyników
Playwrighta. Zapis cookies lub budżetu nie jest zmianą kodu. Trace UX03
wykazał, że Tailwind wysyłał dla niego `full-reload` bez standardowego logu
Vite; po wykluczeniu katalogu oba ślady setup/smoke mają zero takich zdarzeń.

Kryterium sprawności tej izolacji to DWA kolejne przebiegi z tym samym
wynikiem, nie jednorazowe zielone.

## 4. Macierz uprawnień (testowana w API testach każdego zasobu)

| Operacja | anonim | USER (obcy) | USER (członek rodziny) | właściciel | ADMIN |
|---|---|---|---|---|---|
| odczyt PRIVATE | 401 | 404 | 404 | 200 | 200 |
| odczyt HOUSEHOLD | 401 | 404 | 200 | 200 | 200 |
| edycja HOUSEHOLD | 401 | 404 | 200 | 200 | 200 |
| zmiana scope / delete | 401 | 404 | 403 | 200 | 200 |
| odczyt przepisu `global` (D32) | 401 | 200 | 200 | 200 | 200 |
| tworzenie / edycja treści / zdjęcie / zmiana scope / delete / archiwizacja przepisu `global` | 401 | 403 | 403 | 403 (także zdegradowany były admin) | 200 |
| `POST /recipes/{id}/copy` (przepis widoczny) | 401 | 201 | 201 | 201 | 201 |
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

**Przepisy `global` (BATCH_21, D32).** Trzy ostatnie wiersze macierzy dowodzą kodami HTTP
`tests/api/recipes/test_recipes_global_api.py` (wiersz „zdegradowany były admin" asercjonuje
rolę, nie `owner_user_id`), a użycie przez obcą rodzinę — `test_recipes_global_usage_api.py`
(plan, szablon dnia, cykl, lista zakupów). `scope=global` poza przepisami: 422 dla dnia planu,
szablonów i cykli (API), a dla wszystkich ośmiu tabel — CHECK-i w bazie
(`tests/integration/recipes/test_global_scope_db.py`). **Migracja ma test DWUSTOPNIOWY**
(`tests/integration/test_migrations.py::test_migracja_0017_na_istniejacej_bazie_z_wierszami`):
baza staje na `0016` z wierszami, COMMIT, dopiero potem `upgrade head` — odtwarza produkcję,
bo test jednoprzebiegowy od zera nie wykryje błędu „nowa wartość enuma użyta w tej samej
transakcji" (typ utworzony w tej samej transakcji bywa z ograniczenia zwolniony).
Strażnik `tests/unit/test_recipe_scope.py` pilnuje, żeby każde `ScopedQuery(Recipe, …)` poza
transferem miało `allow_global=True`, a E2E `recipe-global.spec.ts` przechodzi cały flow
(ADMIN publikuje → USER innej rodziny widzi, planuje, kopiuje, edytuje kopię).

Macierz jest udowodniona raz, na poziomie mechanizmu: BATCH_03 dostarczył
`tests/integration/test_scope_matrix.py` na encji testowej `ScopedNote`
(konsumuje ten sam `ScopedQuery`, co encje produkcyjne, ale nie istnieje
w migracjach — tabelę tworzy fixture `scoped_notes_table` w bazie testowej).
Batche domenowe NIE przepisują testów mixinu — powtarzają macierz jako testy
API swojego zasobu (kody HTTP, nie wywołania serwisu).

## 5. Dane testowe

Program UX00–UX11 (2026-10-30) ma dodatkowy, izolowany fixture przez
`task ux-baseline -- --photo <plik>`. Guard dopuszcza wyłącznie lokalne
bazy `pasnik_ux` / `pasnik_ux_test`, bez purge. Instrukcja i jawne ograniczenia:
`docs/implementation-plan/ux-redesign/FIXTURE.md`. Opt-in `UX_VISUAL=1`
uruchamia rzeczywiste zrzuty istniejących ekranów w `e2e/ux-visual.spec.ts`;
bez flagi pomijany jest tylko ten dodatkowy scenariusz, nie wymagane core E2E.
Fixture ma własne konta, daty 2029 poza cleanup zwykłego E2E, lokalny manifest
bez sekretów oraz sprawdzone ponowienie bez duplikowania danych.

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

Audyt zależności backendu uruchamia `task audit-be`. Target najpierw pobiera
`purelib` i `platlib` z projektowego interpretera przez `uv run --locked`,
następnie przekazuje oba katalogi jako `--path` do `python -m pip_audit`
w osobnym środowisku narzędzia. Dzięki temu audyt nie wybiera pakietów
overlayu `--with` i nie wymaga pip w venv aplikacji. Kod wyjścia z alertami
pozostaje niezerowy; wykonanie audytu nie oznacza zielonego wyniku.

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
