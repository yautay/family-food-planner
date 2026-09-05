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
| 12 PWA_AND_OFFLINE | [x] | — | `batch(12)` na master (hash wpisać po push) |
| 13 STATISTICS | [x] | — | `batch(13)` na master (hash wpisać po push) |
| 14 IMPORT_EXPORT | [x] | — | `batch(14)` na master (hash wpisać po push) |
| 15 PDF_IMPORT_EXTRACTION | [x] | — | `batch(15)` na master (hash wpisać po push) |
| 16 PDF_IMPORT_REVIEW_AND_AI | [x] | — | `batch(16)` na master (hash wpisać po push) |
| R4 REVIEW_PRE_PRODUCTION | [x] | — | `batch(R4)` na master (hash wpisać po push) |
| 19 FIX_LIST_PAGINATION | [x] | — | `batch(19)` na master (hash wpisać po push) |
| 17 PRODUCTION_HARDENING | [ ] | R4 | |
| 18 PRODUCTION_DEPLOYMENT_AND_OPERATIONS | [ ] | 17, 19 (D6 i D7 zatwierdzone 2026-09-05) | |

## Dziennik

Wpis po każdym batchu (dopisywany NA GÓRZE sekcji): data, batch, 2–5 zdań:
co weszło + **„rzeczy, o których muszą wiedzieć następne batche"**
(odstępstwa, nowe kontrakty, pułapki). Wpis NIE zastępuje propagacji —
zmiany dotykające przyszłych batchy trzeba wpisać do ich kart
(00_MASTER_PLAN §8); dziennik to indeks, nie schowek.

---

**2026-09-05 — BATCH_19 (FIX_LIST_PAGINATION) — warunek 1 werdyktu R4 ZAMKNIĘTY.**

Sześć ekranów listy dochodzi teraz do ostatniej pozycji, a licznik mówi „50
z 185" zamiast samego „185". **Wzorzec: „pokaż więcej" z rosnącym `offset` na
`useInfiniteQuery`**, jeden composable (`frontend/src/api/pagination.ts`) plus
jeden komponent (`components/domain/LoadMoreButton.vue`) — nie sześć kopii.
Rosnący `limit` odrzucony z trzech powodów: rozbija się o sufit 200 (04_API §1),
karta batcha zakazuje podnoszenia `limit` ponad sufit, a trzecie kliknięcie
pobierałoby 150 pozycji, żeby pokazać 50 nowych.

**Rzecz, o której muszą wiedzieć następne batche — `offset` NIE WCHODZI do
klucza zapytań.** Niesie go `pageParam`, więc klucz listy jest ten sam co przed
batchem i `invalidateQueries` po mutacji nadal trafia w CAŁĄ listę. Klucz per
strona rozbiłby cache na osobne wpisy, z których inwalidacja odświeżałaby
jeden — to ta sama pułapka, którą B11 rozwiązał rozłącznymi prefiksami
`index`/`detail`. Dlatego `offset` w interfejsach filtrów w `queryKeys.ts` jest
teraz OPCJONALNY: podają go wyłącznie pickery, które biorą jedną krótką stronę
i paginacji nie mają. **Nowy ekran listy reużywa `usePaginatedList`; własna
kolejka stron albo kopiowanie doładowanych stron do Pinii to błąd review
(ADR-007).**

**Sortowanie kolejki weryfikacji poszło na SERWER** (`GET /products?sort=`,
zamknięty słownik `name|created_at`, literówka = 422). To był najgorszy przypadek
z R4 i wariant „skreślić deklarację" był gorszy: `/admin/weryfikacja` to ekran,
na którym właściciel uzupełnia wartości odżywcze po imporcie, więc kolejność
„od najstarszych" jest tam funkcją, nie ozdobą. **Zmierzone na 68 pozycjach
w realnej kolejce bazy dev**: stara ścieżka (serwer sortuje po `name`, strona
układa po `created_at`) nie pokazywała na pierwszej stronie ANI najstarszego
realnego produktu, ANI ostatniego z zaimportowanej sześćdziesiątki — po
naprawie pierwsza strona zaczyna się od najstarszego, a „pokaż więcej" dowozi
resztę. Konwencja `?sort=` dopisana do **04_API §1**: porządek listy należy do
serwera, a porządek nadany POBRANEJ STRONIE w przeglądarce jest błędem, bo
układa wycinek wybrany innym kryterium.

Rozmiary stron zostały jak były (`/spizarnia` 100, reszta 50) — batch dokłada
dosięgalność, nie przestawia stron; zmniejszenie strony spiżarni DOŁOŻYŁOBY
kliknięć tam, gdzie ich dziś nie ma (06_UIUX §2).

Dokumentacja: nowy **06_UIUX §3.6** (obowiązujący wzorzec paginacji, sześć
reguł), akapit „Stan faktyczny po REVIEW R4" w **05_FRONTEND §3** skreślony
i zastąpiony stanem faktycznym, **04_API §1** rozszerzone o `?sort=`.
`e2e/cleanup.ts` dostał `clearCategories` (kategorie idą PO produktach — FK
z 409, a słownik kategorii jest globalny, więc śmieć widzą wszystkie ekrany).

**`/code-review` na diffie znalazł DWA realne błędy we własnym wzorcu i oba są
naprawione z testem regresji** (warto, bo dotyczą composable'a, na którym stoi
sześć ekranów):

1. **Nieudane doładowanie kasowało z widoku wiersze, które już były na ekranie.**
   `isError` wystawiał stan błędu CAŁEGO `useInfiniteQuery`, a ten zapala się
   także po nieudanym `fetchNextPage`. Odtworzone probem: po padnięciu drugiej
   strony liczba wyrenderowanych kart spadała z 50 na 0, a licznik dalej mówił
   „50 z 60" — czyli wracał dokładnie ten rozjazd liczby z widokiem, który ten
   batch likwiduje. Naprawa: `isError` tylko gdy `pages.length === 0`, plus
   `loadMoreFailed` (lista zostaje, komunikat siada przy przycisku, bo on jest
   ponowieniem). Reguła dopisana do **06_UIUX §3.6 pkt 7**.
2. **Paginacja po `offset` mogła wyrenderować ten sam wiersz dwa razy.** Gdy
   zbiór zmieni się między pobraniem stron, granice się przesuwają i pozycja
   wchodzi na dwie strony — dwa węzły z tym samym `:key` psują patchowanie listy
   w Vue. Naprawa: odsiew po `id` (`TItem extends { id: number }`), licznik
   `loaded` liczony PO odsiewie, a `offset` dalej z surowej liczby pobranych
   wierszy. Odsiew NIE naprawia pominięcia wiersza — to robi `invalidateQueries`,
   po którym TanStack pobiera wszystkie wczytane strony na raz.

**Świadomie zostaje**: paginacja `/import` (dług U25/U29), filtry
czasu/trudności/oceny w `/przepisy` (API je ma, 06_UIUX §4 widok 2 ich nie chce
— rewizja to decyzja właściciela), wirtualizacja i nieskończone przewijanie.
**Nowy follow-up**: select przypisania konta na `/admin/rodziny` bierze jedną
stronę z sufitem 200 bez „pokaż więcej" — to kontrolka formularza, nie ekran
listy, i przy instancji powyżej 200 kont potrzebuje SZUKAJKI, nie doładowywania.

---

**2026-09-05 — DECYZJE WŁAŚCICIELA po raporcie R4: D6, D7, D24 i rozszerzenie
D16 zamknięte; kolejność B19 → B17 → B18 ustalona.**

Wszystkie pytania z raportu R4 mają odpowiedź. **Rejestr 02_DECISIONS nie ma
już ANI JEDNEJ decyzji blokującej batch** — pierwszy raz od początku programu.
Zostaje w nim pięć pozycji bez konsumenta (D8 FUTURE, D9, D10, D11, D21).

1. **D6 — kopia off-device: na razie BEZ automatu, ręcznie na dysk zewnętrzny.**
   Odrzucone rclone do chmury i rsync na NAS. Dla **B18** znaczy to trzy rzeczy:
   krok kopiowania wchodzi do `OPERATIONS.md` jako PROCEDURA, nie skrypt
   w cronie; `pasnik.env` nie dostaje zdalnych poświadczeń; a runbook MUSI
   powiedzieć wprost, przed czym ta konfiguracja nie chroni — kopia leżąca na
   tym samym Odroidzie ratuje przed pomyłką użytkownika, ale nie przed awarią
   dysku ani kradzieżą sprzętu. Krok zostaje jako miejsce do wypełnienia, żeby
   dołożenie NAS-a nie wymagało zmiany kodu.

2. **D24 — scalanie dnia planu zostaje, ale raport DRY-RUN ma je WYMIENIĆ**
   (wariant b). Pułapka wykonawcza, o której musi wiedzieć batch, który to
   weźmie: `analyze` jest CZYSTE i nie zna stanu bazy dla sekcji z `merge_key`,
   więc „7 dni planu zostanie scalonych" wymaga indeksu istniejących wierszy.
   To jest ten sam mechanizm, którego brakuje **U21** — oba domykają się razem.
   Priorytet **P2**: rozjazd dotyczy wyłącznie importu do ŻYWEJ instancji,
   a odtwarzanie na czystą bazę jest co do sztuki dokładne.

3. **D16 rozszerzone (wariant a): ADMIN nie tylko widzi, ale i EDYTUJE treść
   encji ze scope wszystkich rodzin.** Kod od dawna tak działał; decyzja
   opisywała tylko odczyt. Właściciel przyjął to jako zamierzone — administrator
   i tak ma bazę i `/transfer/export?scope=instance`. **Świadomie przyjęte
   ryzyko**: `share_list` generuje publiczny token dla CUDZEJ listy, a taki link
   opuszcza instancję i można go najwyżej odwołać. Dziś bezprzedmiotowe (jedno
   konto ADMIN, jedna rodzina); przy drugiej rodzinie albo drugim adminie punkt
   wraca do przeglądu.

   **Granica, której to rozszerzenie NIE dotyka i której nie wolno z nim
   zlepić**: widoczność nadal nie wybiera CELU ZAPISU. Rozszerzenie mówi, co
   ADMIN może zrobić z wierszem, który JAWNIE WSKAZAŁ po id; naprawa z R4 mówi,
   że gdy użytkownik wiersza NIE wskazał (dzień planu adresuje data), serwer ma
   wybrać wiersz WŁASNY. Bez tego rozdzielenia wraca błąd, w którym ADMIN
   planujący własny obiad kasował tytuł cudzego dnia.

4. **D7 — ZATWIERDZONE. Domena `pasnik.cpt-sztos.com`, proxy to CADDY jako
   usługa systemowa na tym samym hoście.** Pierwotna rekomendacja zakładała
   nginksa i była błędna — karta B18 przestawiona: zamiast szablonu vhosta
   powstaje `docker/proxy/pasnik.Caddyfile.example`, a z listy zadań znika
   ręczna konfiguracja TLS i przekierowania HTTP→HTTPS (Caddy robi oba sam,
   a ACME na tym hoście działa — `charts`, `toc` i `seaweed-filler` mają
   publiczne certyfikaty). Docelowy blok to trzy linijki:
   `reverse_proxy 127.0.0.1:8081` plus `encode zstd gzip`.

   **Lektura realnego `/etc/caddy/Caddyfile` dała cztery ustalenia, których
   żadna z odpowiedzi wprost nie zawierała — i jedno z nich jest kolizją:**

   - **`127.0.0.1:8080` ZAJMUJE Pi-hole.** A dokładnie ten port 09_DEPLOYMENT
     §1 podawał jako przykład dla aplikacji. Gdyby B18 wziął dokument
     dosłownie, kontener albo by nie wstał, albo przesłonił Pi-hole.
     Dokument poprawiony, proponowany port to **8081**; zajęte na tym hoście
     są też 3000, 1880, 4173, 8013, 8888, 9000 i 9101. B18 potwierdza
     `ss -ltnp` przed wpisaniem do compose.
   - **Blok `pasnik.cpt-sztos.com` JUŻ ISTNIEJE** i serwuje statyczny landing
     (`root * /srv/sftp/ftpuser/files/landing`, commit `2a34e5e`). B18 go
     PODMIENIA — dwa bloki na tę samą domenę to błąd konfiguracji, nie
     nadpisanie.
   - **Access log Caddy'ego to TRZECIA warstwa, w której może wyciec publiczny
     token listy.** Do dziś maskowaliśmy dwie (nasz `structlog` i access log
     Uvicorna) — obie w kontenerze. Caddy zapisuje PEŁNY URI, więc blok
     z dyrektywą `log` wpisałby `/api/v1/public/lists/<token>` do pliku na
     hoście, poza wszystkim, co kontrolujemy. Token w takim logu działa: kto go
     przeczyta, otwiera listę bez logowania. Dopisane do **07_SECURITY §5
     pkt 9** jako wymaganie do zweryfikowania GREPEM po realnym logu.
   - **Limitu rozmiaru ciała nie trzeba ustawiać** (Caddy domyślnie nie
     ogranicza, więc PDF 25 MB i paczka transferu 100 MB przechodzą), ale
     **HSTS nie jest ustawiony nigdzie** w konfiguracji właściciela, a
     07_SECURITY §3 przypisuje go proxy — B18 dokłada go z KRÓTKIM `max-age`
     na start, bo przeglądarka ten nagłówek zapamiętuje.

   Domena **POTWIERDZONA** przez właściciela tego samego dnia. W trakcie
   ustaleń padło raz `pasnik.cpt-sztos.com.pl`, ale rozstrzygnął realny
   `Caddyfile`, w którym jest `pasnik.cpt-sztos.com` — tak jak wszystkie
   pozostałe serwisy na tym hoście. Odnotowane, bo to jest dokładnie ten
   rodzaj szczegółu, który ktoś kiedyś „poprawi" z powrotem.

   **Konsekwencja techniczna niezależna od tych odpowiedzi, wpisana do B17**:
   za proxy wszystkie żądania przychodzą z adresu proxy, więc `get_remote_address`
   zamienia limit 5/min/IP na `/auth/login` w limit GLOBALNY dla wszystkich kont
   naraz, a 60/min na `/public/*` — we wspólny dla wszystkich osób z linkiem.
   Caddy ustawia `X-Forwarded-For` w `reverse_proxy` domyślnie, więc po stronie
   aplikacji zostaje zaufanie do tego nagłówka — ograniczone do adresu proxy,
   inaczej dowolny klient poda własny i limit logowania przestanie cokolwiek
   znaczyć. Dotyczy też `accounts/router.py:40`, który zapisuje IP sesji.

5. **Kolejność: B19 → ręczny import ośmiu jadłospisów → B17 → B18.** Batche 19
   i 17 są wzajemnie niezależne (frontend kontra obraz prod i backup), więc
   kolejność była wolna. Wybór jest właściwy: import daje 103 dania i 185
   produktów, a bez paginacji `/admin/weryfikacja` — ekran, na którym uzupełnia
   się wartości odżywcze — dosięga tylko pięćdziesiątki wybranej alfabetycznie.


**2026-09-05 — REVIEW R4 (REVIEW_PRE_PRODUCTION) — WERDYKT: GO WARUNKOWE**

**B17 może startować od razu. B18 nie startuje, dopóki nie zamkną się trzy
warunki niżej.** Aplikacja jest przedprodukcyjnie zdrowa tam, gdzie decyduje
się bezpieczeństwo danych rodziny: publiczna ścieżka nie wypuszcza PII, uploady
mają sniffing i autoryzację, w repo nie ma sekretów, oba audyty zależności są
czyste, a **backup logiczny naprawdę odtwarza dane** — sprawdzone round-tripem
na CZYSTEJ instancji, nie zadeklarowane. Wydajność ma zapas rzędu
dziesięciokrotności budżetu. Warunki dotyczą rzeczy, które uderzają dopiero
przy realnym użyciu.

**Warunki werdyktu:**

1. **`BATCH_19_FIX_LIST_PAGINATION` przed B18** (P1, nowa karta). Żaden ekran
   listy nie ma paginacji — każdy wysyła `offset: 0` ze stałym limitem. Dziś
   niewidoczne (15 produktów demo), po imporcie ośmiu jadłospisów **103 dania
   i 185 nazw produktów** trafi w sufit 50.
2. **D6 i D7 zatwierdzone przed B18** — bramka istniała przed R4 i R4 jej NIE
   rusza. **B17 ich nie potrzebuje.**
3. **Punkty 1–3 z „Ustaleń R4" w karcie B17**: healthcheck sprawdzający
   zgodność migracji (09_DEPLOYMENT §2 tego WYMAGA), CSP bez `base-uri`
   i `form-action` (te dwie dyrektywy NIE dziedziczą po `default-src`), brak
   rate limitu na endpointach uploadu.

GO warunkowe, a nie NO-GO, bo po naprawach z tego commita nie została ani jedna
znana dziura w danych albo autoryzacji — zostało niewykończenie, którego cena
rośnie dopiero po wdrożeniu.

---

**NAJWAŻNIEJSZE ZNALEZISKO — ADMIN dopisywał do CUDZEGO dnia planu.
NAPRAWIONE w tym commicie.**

Dzień planu nie ma id w URL-u — adresuje go DATA — więc `PlanningService`
miał JEDEN resolver „który dzień dla tej daty", z którego korzystał zarówno
odczyt, jak i `PUT /plan/days/{date}`, `POST /plan/days/{date}/meals`
i instancjacja szablonu. Resolver pytał `visible_condition`, a ta zwraca
ADMIN-owi `true()` (D16). Skutek: administrator, który NIE miał własnego dnia
na daną datę, trafiał w najstarszy wiersz **dowolnego użytkownika z dowolnej
rodziny**.

Odtworzone realnie na działającym stacku (nie z lektury kodu): ADMIN wykonał
`POST /plan/days/2029-11-17/meals` → posiłek wylądował w dniu cudzej rodziny;
`PUT /plan/days/2029-11-17` → cudzemu dniowi zniknął tytuł („Urodziny Zosi"
→ `null`) i `scope` przeskoczył `household` → `private`, czyli dzień wypadł
z widoku pozostałych członków TAMTEJ rodziny. Żadnego z tych pól ADMIN nie
nazwał — wystarczyło, że planował własny obiad.

To nie jest eskalacja uprawnień (trzeba sesji ADMIN-a), tylko **cicha korupcja
cudzych danych przy zwykłym użyciu** — i wprost łamie D16, która mówi, że
wyjątek dla ADMIN-a dotyczy ODCZYTU i „nie rozciąga się na mutacje reguł
właścicielskich".

Naprawa: `_resolve_day(..., for_write=True)` i `_resolved_days(..., owned=True)`
używają `owned_condition` zamiast `visible_condition` na ścieżkach ZAPISU
(`upsert_day`, `create_meal`, `append_day_payload`) oraz w `demand_rows`.
Dla nie-ADMIN-a `owned_condition` jest DOKŁADNIE tym samym warunkiem, więc
członek rodziny nadal dopisuje posiłki do wspólnego dnia rodzinnego — reguła
z B07 bez zmian, żaden istniejący test nie musiał być osłabiony. `demand_rows`
weszło do tej samej granicy z osobnego powodu: lista zakupowa ADMIN-a
powstawała z planów WSZYSTKICH rodzin, podczas gdy spiżarnia po drugiej
stronie silnika idzie po `select_own_household` od R3 — obie strony mówiły
o innym domu. Test: `test_admin_nie_dopisuje_do_cudzego_dnia_planu`; test D16
na ODCZYT (`test_d16_admin_widzi_cudzy_plan_na_sciezkach_uzytkownika`) stoi
nietknięty obok niego. Granica dopisana do **04_API §3 pkt 2-bis**
i **07_SECURITY §4**.

---

**Bezpieczeństwo: ZERO otwartych HIGH.**

`/security-review` przeszedł po CAŁYM kodzie w czterech równoległych przebiegach
(core+auth+konta, moduły domenowe, zakupy+transfer+importer, frontend). Jedyne
ustalenie powyżej progu to opisany wyżej resolver dnia planu — naprawione.
Frontend: **zero trafień** na `v-html`/`innerHTML`/`document.write`, zero
`<a href>` w szablonach (każda nawigacja to `RouterLink` z nazwaną trasą, więc
`javascript:` nie ma się gdzie pojawić), zero `console.*` w kodzie produkcyjnym,
zero odczytów `import.meta.env`; skan zbudowanego bundla pod `sk-ant-` i wzorce
kluczy — czysty. `safeNext` w `LoginPage` odrzuca `next`, który nie zaczyna się
od jednego `/`.

Zweryfikowane REALNYMI żądaniami na działającym stacku, nie testami:

- nagłówki (nosniff, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`,
  CSP bez zewnętrznych źródeł) wychodzą też na ścieżce publicznej i na 404;
- publiczna lista: token 43 znaki, odpowiedź to DOKŁADNIE
  `{name, expires_at, items}`, pozycja to dokładnie dziesięć pól z białej listy,
  **`received_at` nieobecne** (D19), skan po `email`/`owner`/`household`/
  `user_id`/`product_id`/`from_pantry` — zero trafień;
- token o złym kształcie → 422 PRZED zapytaniem do bazy, nieznany → 404
  z tym samym komunikatem co 410, odpowiedź bez `Set-Cookie`;
- rate limit: 70 żądań GET dało 54×200 + 16×429, PATCH po wyczerpaniu też 429
  (licznik WSPÓLNY), ścieżka zalogowana nietknięta;
- maskowanie tokenu potwierdzone GREPEM po realnym logu w OBU warstwach
  (`structlog` i access log Uvicorna) — `/api/v1/public/lists/***`;
- mutacja bez `X-CSRF-Token` → 403.

`task audit`: pip-audit „No known vulnerabilities found"; `npm audit` **miał
jedno HIGH** — `fast-uri` 3.1.5 (łańcuch `vite-plugin-pwa → workbox-build →
ajv`, `"dev": true`, więc narzędzie budowania, nie kod wysyłany do
przeglądarki). Podbite do 3.1.7, oba audyty czyste. `task secrets-scan`:
„no leaks found" (33 commity, 6,07 MB).

**Trzy obserwacje poniżej progu poszły do B17** (pkt 6–8 „Ustaleń R4"):
prefiks `__Host-` dla cookies, `hide_parameters=True` na silniku (nieobsłużony
`DBAPIError` na INSERCIE do `sessions` wypisałby token do logu wraz z sekcją
`[parameters: ...]`) i `PRIVATE_SUBDIRS` porównywane z uwzględnieniem wielkości
liter.

---

**Wydajność (baza dev, seed demo + przekrój domeny; ASGI, mediana z 5)**

| Widok | Zapytań SQL | Mediana | Min–Max |
|---|---|---|---|
| Plan dnia (1 dzień) | 11 | 31 ms | 25–44 ms |
| **Plan tygodnia (7 dni)** | **11** | **37 ms** | 35–57 ms |
| Lista przepisów (szukajka) | 9 | 29 ms | 25–51 ms |
| Katalog produktów (50) | 7 | 38 ms | 24–42 ms |
| Statystyki (7 dni) | 12 | 45 ms | 32–49 ms |
| **Statystyki (92 dni — sufit)** | **12** | **43 ms** | 36–50 ms |
| Konfiguracja tur | 3 | 17 ms | 14–21 ms |
| Generacja zakupów (7 dni + spiżarnia) | 14 | 55 ms | 44–69 ms |
| Podgląd generacji (z `params`) | 3 | 14 ms | 12–22 ms |
| Lista zakupowa (szczegół) | 5 | 24 ms | 22–26 ms |
| Spiżarnia | 4 | 17 ms | 14–19 ms |
| Publiczna lista (przez HTTP) | — | 22 ms | 18–37 ms |

**Budżet <500 ms z R2 spełniony z zapasem ×10.** Kluczowe są nie czasy, tylko
DWIE liczby zapytań: plan tygodnia kosztuje **tyle samo zapytań co jeden dzień**
(11 = 11), a statystyki na 92 dniach **tyle samo co na 7** (12 = 12) — czyli
liczba round-tripów nie zależy od zakresu i N+1 nie ma w żadnym z mierzonych
widoków. Indeksy sprawdzone `EXPLAIN`-em: `ix_day_templates_payload_gin` jest
faktycznie używany przy containmencie `@>` (nie założony — wymuszony
`enable_seqscan=off` i odczytany z planu), `ix_canonical_products_name_trgm`
i `ix_recipes_name_trgm` przy `%`. Regresji wobec R2 nie ma: R2 mierzył
`GET /plan/days` na 100–177 ms przy 112 pozycjach, tu jest 37 ms przy mniejszym
planie — rząd wielkości ten sam.

---

**Backup logiczny — round-trip wykonany REALNIE, nie zadeklarowany.**

Eksport instancji z bazy dev → **świeża baza `pasnik_rt`** (`CREATE DATABASE`
+ `alembic upgrade head`, zero wierszy) → dry-run → apply. Odtworzyło się
WSZYSTKO, co było w źródle, co do wiersza — **25 sekcji z zawartością**
(23 utworzone + 2 słowniki reużyte, bo migracje zasiewają kategorie i tagi):
14 kategorii, 9 tagów, 1 sklep, 15 produktów kanonicznych, 10 przeliczników,
10 wariantów sklepowych, 1 rodzina, 1 konto, 2 profile, 2 cele (CAŁA historia
z `valid_from`), 5 przepisów, 15 składników, 1 ocena, 7 dni planu, 15 posiłków,
16 pozycji, 1 szablon dnia, 1 szablon tygodnia, 1 cykl, 2 pozycje spiżarni,
2 tury, 2 generacje, 4 listy, 40 pozycji list, 6 wpisów audytu. **`to_create` z raportu DRY-RUN zgadzał się
co do sztuki z tym, co faktycznie powstało** — raport jest rzetelny. Braków
w zakresie eksportu NIE MA, więc ustalenie blokujące nie powstało.

Uczciwe zastrzeżenie: ten przebieg NIE objął zdjęć, bo dane demo ich nie mają
(`photos_imported` = 0). Ścieżkę plików pokrywają testy integracyjne —
`test_round_trip_odtwarza_dane_na_czystej_bazie` (dwa zdjęcia wracają pod
NOWYMI, losowymi nazwami po re-enkodowaniu) i
`test_duza_paczka_ze_zdjeciami_przechodzi_w_obie_strony` (~50 MB archiwum).

**D22 WDROŻONA i zmierzona.** Drugi import tego samego pliku dokładał
**+15 posiłków i +16 pozycji** do REUŻYTYCH dni planu (reużyty rodzic dostawał
drugi komplet dzieci). Po naprawie: **0**. Mechanizm: `Section.parent` nazywa
kolumnę rodzica KOMPOZYCJI, a kryterium jest sprawdzalne w bazie — FK
`ON DELETE CASCADE` (ADR-012). Sprawdzenie idzie PRZED `resolve_references`,
bo pominięte dziecko nie trafia do `IdMap` i jego własne dzieci dostałyby
„martwą referencję", wywracając cały import. Tych samych funkcji używa raport
DRY-RUN. Przepisany został jeden istniejący test
(`test_import_wlasnego_eksportu_reuzywa_dnia_planu_i_nie_tyka_jego_posilkow`) —
asercjonował DOKŁADANIE posiłków, czyli zachowanie, które ta decyzja odwraca;
nie osłabiono go, tylko przestawiono na nową regułę z uzasadnieniem
w docstringu.

**Czego D22 świadomie NIE obejmuje**: sekcje bez klucza naturalnego (wariant
sklepowy, profil członka, pozycja spiżarni, tura, generacja, lista, szablon,
cykl) **nadal duplikują się przy drugim imporcie** — nie mają tożsamości,
po której dałoby się je rozpoznać, więc „utwórz kopię" jest dla nich jedyną
sensowną semantyką. Zmierzone i opisane w 04_API §2. Pytanie, czy milczące
scalanie dnia planu ma zostać milczące, poszło do rejestru jako **D24 (OPEN)**.

---

**Spójność statystyk z planem dnia (ustalenie B13) — potwierdzona pomiarem.**

Ten sam zakres w `/plan/days` i `/stats/daily`: **zero rozjazdów** na 7 dniach
× 7 polach wartości; statusy identyczne w obu widokach. Dzień bez planu jest
LUKĄ (`has_plan: false`, `nutrition: null`, statusy `null`), a dzielnikiem
średniej jest `days_with_plan` (7 z 8 dni zakresu). Zmiana celu w środku
zakresu działa jak zapowiedziano: przy celach 2000 (od 01.08) i 2200 (od 28.08)
`summary.goal_progress.kcal.target` wyszło (2000×4 + 2200×3)/7, czyli ŚREDNIA
celów dni z planem, nie „ostatni cel".

**Przy okazji znaleziony i naprawiony błąd**: ta średnia wychodziła jako
`"2085.714285714285714285714286"`, a `formatDecimal` we froncie obcina
wyłącznie KOŃCOWE ZERA — więc ekran Statystyk pokazywał 24 cyfry po przecinku.
`avg` przechodziło przez `round_for_output`, średnia CELÓW nie. Doszło
`engine.round_field_for_output(field, value)` (ta sama reguła: kcal → 1,
makra → 0,1) i `summarize` używa go dla `target` i `delta`. Sprawdzone na żywo:
`target: "2086"`, `delta: "-779"`. Test:
`test_srednia_celow_zaokragla_sie_na_wyjsciu_jak_reszta_wartosci`.

Świadoma konsekwencja tej naprawy: `goal_status` podsumowania liczy się teraz
z celu ZAOKRĄGLONEGO, więc dokładnie na granicy progu (90%/110% z D9) status
może wyjść inaczej niż przed zmianą. Tak jest POPRAWNIE — `value` było
zaokrąglane od zawsze, a status ma odpowiadać liczbom, które użytkownik widzi
na ekranie, nie tym, które zostały w pamięci.

---

**Weryfikacja wyrywkowa AC — po dwa kryteria z każdego batcha**

| Batch | Kryteria | Wynik |
|---|---|---|
| 01 | AC1 compose podnosi stack; AC7 zero sekretów w repo | ✔ 4 kontenery healthy; `git ls-files` tylko `.env.example`, gitleaks czysty |
| 02 | AC5 mutacja bez CSRF → 403; AC3 wylogowanie unieważnia sesję | ✔ realny 403; `test_auth.py` (22 testy) |
| 03 | AC3 macierz scope; AC5 usunięcie rodziny z członkami → 409 `used_in` | ✔ `test_scope_matrix.py`; `test_u16_*` |
| 04 | AC5 szukajka toleruje literówki; AC9 kolejka UNVERIFIED | ✔ „marhew" → „Marchew" (similarity 0,50 ≥ próg 0,25); ekran JEST, ale z ustaleniem P1 (paginacja) |
| 05 | AC4 `?servings=2.5`; AC2 silnik czysty + property-based | ✔ 255 kcal → 639 przy ×2,5 (zaokrąglenie na krawędzi, nie 638 — dokładnie tak ma być); testy hypothesis |
| 06 | AC6 fit-to-target tylko PROPONUJE; AC2 historia celów | ✔ propozycja 2,13 → 499 kcal, `servings` w bazie nadal 2,00; dwa cele z `valid_from` przeżyły round-trip |
| 07 | AC1 indeksy GIN; AC7 409 przy przepisie użytym w szablonie | ✔ `EXPLAIN` pokazuje `ix_day_templates_payload_gin`; testy szablonów |
| 08 | AC5 nic nie odejmuje spiżarni automatycznie; AC3 spiżarnia wspólna | ✔ `generate(use_pantry=true)` → delta `pantry_items` = 0; testy pantry |
| 09 | AC4 profil sklepu = trwała kolejność; AC7 jedna głowa | ✔ PUT `[5,4,3,2,1]` → GET zwraca `[5,4,3,2,1]`; `alembic heads` = `0015` |
| 10 | AC2 `generate` zapisuje TYLKO generację; AC7 determinizm | ✔ delta: +1 generacja, 0 list, 0 pozycji; dwa `GET` identyczne bajt w bajt (13 799 B) |
| 11 | AC4 link 43 znaki; AC6 limit 60/min + maskowanie | ✔ token 43 znaki; 54×200 + 16×429, `***` w obu logach |
| 12 | AC7 przyjęcie idempotentne (D19); AC4 LWW | ✔ 1. `accept` 200 `created=1`, 2. → 409; `test_shopping_lww.py` |
| 13 | AC2 słupki zgodne z planem dnia; AC4 dni bez planu to luki | ✔ 0 rozjazdów na 7×7 pól; `days_with_plan` 7 z 8 |
| 14 | AC6 round-trip na czystej bazie; AC3 raport DRY-RUN rzetelny | ✔ 25 sekcji odtworzonych; `to_create` == `created` |
| 15 | AC2 liczby korpusu; AC9 walidacja krzyżowa | ✔ `test_pdf_corpus.py` 24/96/**662**/**185**; `test_prototype_crosscheck.py` ≥84/≥592 |
| 16 | AC5 approve zablokowany przy blokerach; AC8 AI jako propozycja | ✔ `test_approve_gate.py`; `test_ai_parsing.py` + `test_import_ai_assist.py` (zero realnych wywołań) |

**Uwaga do B15 AC2**: karta wymaga „642 składniki, 178 nazw", a testy
asercjonują 662/185. To NIE jest rozjazd, tylko skutek decyzji **D20** wdrożonej
w B16 — liczby w karcie B15 opisują stan sprzed rozszerzenia kontraktu §3.2
i są zapisem historycznym.

**Uzgodnienie liczb korpusu (rozbieżność zgłoszona przy zleceniu R4)**:
„≥84 przepisy / 592 składniki" to PRÓG walidacji krzyżowej z `prototype.db`
(D2), „24 dni / 96 posiłków / 662 wiersze / 185 nazw" to POMIAR korpusu
(01_PDF_AUDIT §1 po D20), a „101 przepisów / 629 składników" z B15 to wynik
krzyżowy PO dedupie, czyli liczba porównywana z progiem. Trzy różne miary,
zero sprzeczności — wyjaśnienie dopisane do karty R4 §Tests. Do zapamiętania:
**103 dania ≠ 96 posiłków**, bo posiłek bywa dwudaniowy (§2).

**Follow-upy obiecane w Completion notes — kontrola przekrojowa**: U7 (skill
`ffp-framework`) faktycznie zamknięty w commicie renameu — w żywych dokumentach
zostały wyłącznie wzmianki HISTORYCZNE (treść D23 i dziennik), zgodnie z regułą
podziału z D23; katalogi skilli to wyłącznie `pasnik-*`. U16/U17 zamknięte
w R3, U22 zamknięty w B16 (kolumna `from_extras_section`, migracja `0015`),
U30 rozstrzygnięty jako D22 i wdrożony tutaj. Bramka dryfu modeli z R3 świeci
zielono. **Nie znalazłem ani jednego follow-upu zadeklarowanego jako wykonany,
który nie byłby wykonany.**

---

**Dług techniczny — JEDNA lista z priorytetami**

Grep `TODO|FIXME|HACK|XXX` po `backend/**` i `frontend/**`: **zero trafień**.
Cały dług programu żyje w dziennikach, więc poniżej jest jego konsolidacja.

**P1 — przed wdrożeniem (mają przypisane miejsce wykonania):**

- **Paginacja list w UI** → `BATCH_19_FIX_LIST_PAGINATION` (nowa karta).
  Sześć ekranów, `offset: 0` na sztywno. Najgorszy przypadek to
  `/admin/weryfikacja`: sortuje „najstarsze na górze" po stronie KLIENTA,
  czyli sortuje pięćdziesiątkę wybraną alfabetycznie przez serwer — produkt
  spoza pierwszych 50 nazw jest z tego ekranu nieosiągalny.
- **Healthcheck bez kontroli migracji** → B17 pkt 1 (09_DEPLOYMENT §2 WYMAGA
  statusu `degraded`).
- **CSP bez `base-uri` i `form-action`** → B17 pkt 2 (te dyrektywy nie
  dziedziczą po `default-src`).
- **Brak rate limitu na uploadach** (`/import/pdf` 25 MB, zdjęcia,
  `/transfer/import` 100 MB) → B17 pkt 3.

**P2 — po wdrożeniu:**

- **U21 POWIĘKSZONY przez D22, domyka się RAZEM z D24**: raport DRY-RUN nadal
  liczy optymistycznie sekcje bez klucza naturalnego, a od R4 dotyczy to także
  DZIECI rodzica scalanego po `merge_key` — przy powtórnym imporcie na to samo
  konto raport obiecuje posiłki, których `apply` nie utworzy. Rozjazd występuje
  WYŁĄCZNIE przy scalaniu (import na czystą instancję jest dokładny —
  zmierzone). **D24 (zatwierdzona 2026-09-05, wariant b) wymaga DOKŁADNIE tego
  samego mechanizmu**: żeby raport mógł napisać „7 dni planu zostanie
  scalonych", `analyze` musi znać istniejące wiersze sekcji z `merge_key` —
  a mając ten indeks, przestaje też zawyżać `to_create`. Jedna praca, dwa
  długi; wycenić i wykonać razem, priorytet P2 (po wdrożeniu).
- **`GET /api/v1/audit` nie ma konsumenta** — ekran `/admin/audit` był w B03
  opcjonalny („jeśli tanio") i nie powstał. Dziennik operacji zapisuje się przy
  każdej wrażliwej akcji, ale przeczytać go można tylko przez API albo bazę.
  Martwy klucz `queryKeys.adminAudit` (`frontend/src/api/queryKeys.ts:174`).
  Stan dopisany do 05_FRONTEND §3.
- **ADMIN przechodzi przez `visible_condition` także na ścieżkach ZAPISU
  zakupów** — `share_list`, `revoke_share`, `update_item`, `resolve`,
  `finalize`, `accept_to_pantry` wołają `get_or_404` (dla ADMIN-a `true()`)
  bez `assert_can_manage`. Różnica wobec naprawionego dziś dnia planu jest
  istotna i dlatego R4 tego NIE ruszył: tam ADMIN trafiał w cudzy wiersz
  PRZYPADKIEM, tu musi świadomie podać cudze id. Do rozstrzygnięcia razem
  z rewizją granic D16 — albo domknąć `assert_can_manage`, albo dopisać do
  D16, że ADMIN edytuje treść wszystkiego.
- **U27** — N+1 w `ai-suggest`: `_unmapped_names` woła `list_products` raz na
  nieodwzorowaną nazwę (2 zapytania każde). Po pełnym imporcie to ~180 nazw,
  czyli rząd 360 zapytań na jedno kliknięcie.
- **U26 → osierocone pliki**: testy uruchamiane taskiem dziedziczą `UPLOADS_DIR`
  z `.env`, więc w `backend/data/uploads/import-pdf/` leżą **3 PDF-y (4,4 MB)**
  bez wiersza w bazie. Na produkcji ten sam mechanizm zostawi śmieci po każdym
  nieudanym imporcie → B17 pkt 4 (komenda raportująca, NIE cron kasujący).
- **U12** (świeżość kontraktu API niebramkowana), **U13** (`SECRET_KEY`
  wymagany, nieużywany), **U24** (`PDF_PARSE_TIMEOUT_S` przerywa żądanie, nie
  wątek; przy okazji: to stała modułu, nie zmienna env — na Odroidzie może
  wymagać innej wartości) → wszystkie już w karcie B17. **U19** (brak komendy
  CLI restore) → B18. W R4 sprawdzone realnie: `task fe-types` daje ZEROWY diff,
  więc kontrakt jest zgodny z kodem.

**P3 — nice to have:**

- **U14** `ilike` bez `autoescape=True` w wyszukiwarkach ADMIN-a
  (`accounts/service.py:180`, `households/service.py:183`) — już w karcie B17.
- **U23** 3 ze 103 nazw dań ucięte przez zawijanie kolumn.
- **U25/U29** lista importów bez paginacji — świadomie POZA B19.
- **U28** E2E zostawia zatwierdzony job (statusy rozstrzygnięte są nieusuwalne
  z założenia).
- Prefiks `__Host-` dla cookies, `hide_parameters=True`, `PRIVATE_SUBDIRS`
  bez `lower()` → B17 pkt 6–8.
- **ADMIN zatwierdzający CUDZY job importu tworzy przepisy NA SIEBIE**
  (`review_service.approve` przekazuje `actor`, nie właściciela joba). Dziś
  bez znaczenia (jeden ADMIN = właściciel), do rozstrzygnięcia, gdy powstanie
  drugie konto ADMIN.
- `bind_contextvars(user_id=…)` nigdy nie odpinane — kwestia atrybucji logów.
- `coerce_value` rzuca gołe `ValueError` na złej wartości enuma w pliku
  transferu → 500 zamiast 422.

**ZAMKNIĘTE, potwierdzone w R4**: U1–U11 (R1/B05), U15 (E2E od R2), U16/U17
(R3), U18 (seed rozszerzony w B10), U22 (B16), U7 (rename D23), U30 → D22 →
wdrożone tutaj. Dług z B13 (`planning/service.py::_GOAL_FIELDS` jako druga
kopia listy pól celu) **domknięty w tym commicie** — została jedna lista,
`nutrition/types.GOAL_NUMERIC_FIELDS`.

---

**Decyzje**

- **D22 → ZATWIERDZONA i WDROŻONA** (przeniesiona do tabeli zatwierdzonych
  razem z **D23**, która wisiała w „Otwarte" mimo statusu ZATWIERDZONE).
- **D10 (retencja) — rewizja wykonana, REKOMENDACJA BEZ ZMIAN**: nic nie
  usuwamy automatycznie. Sprawdzone w kodzie, co JUŻ się sprząta (sesje przy
  logowaniu, PDF odrzuconego importu, scratch transferu z TTL 24 h, stare
  zdjęcie przy podmianie) i co nie rośnie samo. Jedyną nieograniczoną osią jest
  `/srv/pasnik/uploads`, więc do B17/B18 idą dwa konkrety zamiast automatu:
  raport zajętości w runbooku backupu i komenda „pliki bez referencji".
- **D21 — grunt przygotowany POMIAREM, nie szacunkiem**. Parser puszczony na
  całym korpusie zebrał próbki wszystkich wierszy z jednostką „Sztuka":
  **42 produkty, 223 próbki**. Rozkład jakości lepszy, niż zakładała §5.2 —
  **34 produkty (81%) mają rozrzut ZEROWY**, niespójnych jest osiem
  i ich rozrzut to 12–20% (`Papryka czerwona` 200–230 przy 27 próbkach,
  `Jajko` 50–60 przy 25, `Cebula` 105–120 przy 24) z jednym odstającym
  (`Burak` 100–150 g przy trzech próbkach). Mediana ma więc realnie co robić.
  Dwa zastrzeżenia dla ekranu zatwierdzania: **14 produktów ma DOKŁADNIE JEDNĄ
  próbkę** (tam „mediana" to przepisanie jednego odczytu — trzeba pokazywać
  `samples_count`), a „Sztuka" u dietetyczki bywa CAŁYM warzywem (`Cukinia`
  600 g, `Brokuł` 500 g, `Dynia` 900 g, `Kapusta włoska` 1500 g — wszystkie
  z rozrzutem zerowym, więc to nie błędy odczytu). Blokerem nadal nie jest
  jakość danych, tylko D15. Skala: osiem jadłospisów = ~42 propozycje,
  34 jednogłośne.
- **D24 (NOWA, OPEN)** — czy scalenie dnia planu przy imporcie ma pozostać
  milczące. Wskazana wprost przez D22; rekomendacja: zostawić scalanie, ale
  wymienić je w ostrzeżeniach raportu DRY-RUN.
- **D6 i D7 — NADAL OPEN. Przypomnienie: bez ich zatwierdzenia B18 NIE
  STARTUJE. B17 startuje bez nich.**

---

**Dokumentacja: każdy z dziewięciu dokumentów architektury przejrzany.**
Zaktualizowane do stanu faktycznego: **01_ARCHITECTURE** (§2 wymieniał
nieistniejący katalog `src/composables/`; §3 podawał `lucide-vue-next` zamiast
`@lucide/vue`), **02_DOMAIN §11** i **04_API §2** (semantyka D22),
**04_API §3 pkt 2-bis** i **07_SECURITY §4** (granica „widoczność nie wybiera
celu zapisu"), **05_FRONTEND §3** (brakowało `/przepisy/nowy`
i `/import/jobs/:id/review`; `/admin/*` obiecywał ekran audytu, którego nie ma;
dopisany stan faktyczny paginacji). Potwierdzone jako zgodne bez zmian:
03_DATABASE (36 tabel w bazie = 36 w `EXPECTED_TABLES`), 06_UIUX,
08_TESTING, 09_DEPLOYMENT. **ADR-001…015 przejrzane — żaden nie jest martwy
ani łamany** (karta R4 mówiła „001…014"; ADR-015 istnieje od B01 i został
dopisany do zakresu audytu). Sprawdzone wyrywkowo w kodzie: zero `float`
w torze domenowym (jedyne wystąpienia to próg pg_trgm, timeouty i `confidence`
z JSON-a natychmiast konwertowane na `Decimal`), zero bibliotek wykresów, zero
i18n, zero JWT/passlib/python-jose, `postgresql+psycopg://` z
`selector_loop_factory`, cztery store'y Pinia i wszystkie to stan UI, zero
wartości hex w komponentach, zero `any` w TS. CLAUDE.md dostał sekcję
„Dołożone w REVIEW R4".

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Widoczność NIE wybiera celu zapisu.** Zasób adresowany czymś innym niż
   własne id (data, nazwa, klucz naturalny) musi rozstrzygać „który wiersz to
   mój" przez `owned_condition`, nie `visible_condition` — inaczej `true()`
   ADMIN-a z D16 zamienia zapis w zapis do cudzej rodziny.
2. **Nowa sekcja formatu transferu z FK `ON DELETE CASCADE` do rodzica
   deklaruje `Section.parent` w TYM SAMYM batchu** (D22), inaczej ten sam plik
   zaimportowany dwa razy podwoi zawartość rodzica.
3. **Liczba policzona z wartości odżywczych wychodzi na zewnątrz ZAOKRĄGLONA** —
   `round_field_for_output` dla pojedynczego pola, `round_for_output` dla
   całych `NutritionValues`. Formatter frontendu obcina wyłącznie końcowe zera
   i pokaże 24 cyfry po przecinku, jeśli je dostanie.
4. **Nowy ekran listy MA mieć paginację** — wzorzec ustala B19 i dopisze go do
   06_UIUX. Do tego czasu każdy nowy `offset: 0` powiększa dług P1.

**Wyniki uruchomień (realne).** `task check` zielony na WEJŚCIU (exit 0,
przed jakąkolwiek zmianą) i zielony PO naprawach: 3 migrations-check /
**432 unit** / **330 integration** / **411 api** (13 min 15 s) /
**398 vitest w 42 plikach** / mypy 201 plików + vue-tsc / ruff / eslint /
prettier (217 plików) / `vite build` (69 wpisów precache). Przyrost wobec stanu
na wejściu to dokładnie trzy testy, po jednym na naprawę: +1 unit
(zaokrąglanie średniej celów), +1 integration (D22), +1 api (izolacja zapisu
ADMIN-a).

**E2E: 20/20 w DWÓCH kolejnych przebiegach** (1,5 min i 1,3 min) — kryterium
z 08_TESTING §3.1 spełnione, zero flaków. Warto odnotować `transfer.spec.ts`:
**2,6 s w obu przebiegach**. Przed D22 ten sam spec potrafił rosnąć do 73 s
i wywracać na timeoucie dwa cudze specy (B16), a po ręcznym resecie bazy dev
schodził do 8,6 s. Teraz nie ma czego resetować — reużyty rodzic nie dostaje
drugiego kompletu dzieci, więc dane nie puchną między przebiegami.

`task audit`: pip-audit „No known vulnerabilities found",
`npm audit --audit-level=high` „found 0 vulnerabilities" (po podbiciu
`fast-uri`). `task secrets-scan`: „no leaks found" (33 commity, 6,07 MB).
`task fe-types`: ZEROWY diff, więc `backend/openapi.json`
i `frontend/src/api/generated.ts` są zgodne z kodem (U12 sprawdzone realnie,
choć nadal niebramkowane). `alembic heads`: jedna głowa `0015` — **R4 nie
dodał migracji**, bo żadna naprawa nie dotknęła schematu.

**Review własnych zmian**: `/code-review` na diffie — **zero ustaleń**.
Przejrzane hunk po hunku: brak zmiany zachowania dla nie-ADMIN-a
(`owned_condition` == `visible_condition` poza rolą ADMIN), `mark_blocked`
wołane transitywnie także dla wiersza POMINIĘTEGO (bez tego dziecko dziecka
dostałoby „martwą referencję"), `parent` NIE nadany żadnej sekcji
referencującej słownik.

**Środowisko**: pomiary i round-trip robione na bazie dev odtworzonej przy
renameie D23 (migracje → `create-admin` → `seed_demo`), więc były to dane
czyste, nie narosłe. Przekrój domeny doseedowany PRZEZ API pod prefiksem
„R4 "; dane dowodowe PoC (`poc-obcy@example.com`, „POC Obca Rodzina", dzień
2029-11-17) usunięte po weryfikacji naprawy.

**2026-09-04 — DECYZJA D23 (właściciel): aplikacja nazywa się „Paśnik".**
Rewizja D1, wykonana od razu i w pełnym zakresie — razem z identyfikatorami
technicznymi. Nazwa wyświetlana to `Paśnik`, slug techniczny `pasnik` (bez
diakrytyku, bo trafia do nazw paczek, bazy, kontenerów i cache'ów).

**Cztery rzeczy, o których muszą wiedzieć następne batche:**

1. **Katalogi skilli nazywają się teraz `.claude/skills/pasnik-*`** (`git mv`),
   a mapa ID→skill w **03_AI_SKILLS §3** wskazuje nowe ścieżki. Karty batchy
   odwołują się do ID (SKILL-BE, SKILL-FE…), więc same nie wymagały zmian —
   poza czterema odwołaniami do skilla `ffp-framework`, który NIGDY nie istniał
   (dług **U7** z R1). Wskazywały nieistniejącą ścieżkę w kartach B17, R2, R3
   i R4; poprawione na realne `pasnik-*`.
2. **Projekt compose to `pasnik-dev`, użytkownik i baza PG to `pasnik`.**
   Nowy projekt = NOWE WOLUMENY, więc baza dev wstała pusta i została
   odtworzona (`alembic upgrade head` → `create-admin` → `seed_demo`). Stare
   wolumeny `ffp-dev_pgdata` i `ffp-dev_node_modules` zostały na dysku jako
   osierocone — do usunięcia ręcznie, gdy nie będą już potrzebne jako kopia.
   Kontenery to `pasnik-dev-app-1`, `pasnik-dev-db-1` itd.: **komendy
   `docker exec` z runbooka i starszych wpisów dziennika mają stare nazwy.**
3. **Zmienne środowiskowe: `PASNIK_ADMIN_*`** (było `FFP_ADMIN_*`) i
   `PASNIK_UPDATE_SNAPSHOTS` (aktualizacja snapshotu silnika zakupowego).
   `.env.example` zaktualizowany; lokalny `.env` też — razem z portem 5434
   z kroku 1 runbooka, więc `task dev` wstaje bez override'u.
4. **Identyfikatory po stronie klienta zmieniły wartości**: cookie sesji
   `pasnik_session`, IndexedDB `pasnik-offline`, localStorage
   `pasnik.pantry.view`, cache'y SW `pasnik-api`/`pasnik-uploads`, nazwa
   eksportu `pasnik-export-`. Skutek: istniejące sesje są wylogowane, a
   ewentualna kolejka offline w przeglądarce porzucona. Na etapie
   przedprodukcyjnym bez znaczenia — po wdrożeniu taka zmiana wymagałaby
   migracji, nie samego renamingu. Import transferu NIE waliduje nazwy pliku,
   więc stare eksporty `ffp-export-*.zip` pozostają importowalne.

**Czego świadomie NIE ruszono**, żeby nie falsyfikować zapisu: treści **D1**,
całego tego dziennika oraz katalogu repozytorium `C:\dev\family-food-planner`
(zmiana ścieżki to operacja na dysku, nie w repo) i URL-a starego archiwum
w 01_PDF_AUDIT. Reguła na przyszłość jest w D23: aktualizujemy wszystko, co
czytelnik może dziś WYKONAĆ albo na czym stoi kontrakt; dziennik i treść
zatwierdzonych decyzji zostają. **Dlatego wpisy poniżej mówią `ffp_session`
i `ffp-dev` — i tak ma być: wtedy tak się nazywały.**


**2026-08-29 — BATCH_16 (PDF_IMPORT_REVIEW_AND_AI).** Importer PDF jest domknięty:
ekran review (`/import/jobs/:id/review`), pięć endpointów (`staged`, `resolve`,
`ai-suggest`, `approve`, `reject`), AI-asysta jako czysta propozycja i
zatwierdzenie tworzące realne Recipe + produkty UNVERIFIED + mediany
`product_unit_weights` + audyt — wszystko w JEDNEJ transakcji. Round-trip
przechodzi na realnym `dieta.pdf`: gołąbki → przepis `base_servings=7`,
`source=pdf_import`, kalorie porcji zgodne z jadłospisem w granicach progu 10%.

**Sześć rzeczy, o których muszą wiedzieć następne batche:**

1. **D20 wdrożona, ale liczby korpusu wyszły INNE niż zapowiadała decyzja:
   662 wiersze / 185 nazw, nie 649/180.** Wierszy spoza pierwotnego wzorca §3.2
   jest **20, nie 7**. Powód jest sprawdzalny: liczbę 7 wzięto z licznika
   `parse_warning` BATCH_15, którego regexy kotwiczyły na KOŃCU linii, więc nie
   widziały ani jednego wiersza z doklejoną prawą kolumną (§3.2 pułapka 1) —
   a takich jest 6 z 10 w wariancie „bez pary" i 7 z 10 w „zawiniętym". Ślad
   luki był w samej erracie: przykładem wariantu była `Cukinia, 200 g`, której
   na liście czterech „zmierzonych" wierszy nie było. Zakres decyzji BEZ zmian,
   skorygował się wyłącznie POMIAR; skutki uboczne sprawdzone i zerowe (zbiór
   blockerów `multi_portion_suspect`, sześć mas z §5.1 i 24/24 sumy kontrolne
   bez ruchu). Zaktualizowane: **01_PDF_AUDIT §1/§3.2/§9/§9.2**, D20, testy
   korpusowe i crosscheck (185 vs 181 prototypu, **+4**).
2. **Migracja `0015` — karta mówiła „docelowo bez migracji", a jednak jest**,
   i obie kolumny wymuszają dokumenty nadrzędne, nie wygoda:
   `staged_ingredients.confidence` (02_DOMAIN §10 i ADR-011 wymagają pewności
   przy propozycji AI; szkic 03_DATABASE §9 ją pominął) oraz
   `from_extras_section` (dług **U22**). Bez tej drugiej ziemniaki do gołąbków
   — 225 g podane NA PORCJĘ — zostałyby podzielone przez 7. Głowa: `0015`.
3. **Walidacja kcal liczy się PER POSIŁEK, nie per danie** — to samo odstępstwo
   i to samo uzasadnienie, co errata §9.1 dla progu wieloporcyjności: `pdf_kcal`
   opisuje posiłek, a posiłek bywa dwudaniowy. Kto będzie czytał `meal` z
   odpowiedzi `staged`, dostaje liczby POSIŁKU, nie dania.
4. **Import NIE uczy wag sztuki** (`piece_weight_g`), choć karta podawała
   `Cebula → 105 g` jako przykład. Etykieta „szt." jest w `product_unit_weights`
   zarezerwowana (B04), a `piece_weight_g` zmienia wyłącznie ADMIN i zmiana
   unieważnia weryfikację (**D15**). Uczą się jednostki DOMOWE (łyżeczka,
   szklanka, woreczek). Sprawa poszła do 02_DECISIONS jako **D21 (OPEN)**.
5. **Nazwa schematu Pydantic jest częścią kontraktu frontendu.** Dwa moduły
   z klasą `ResolveRequest` zmuszają FastAPI do kwalifikowania OBU pełną ścieżką
   modułu w OpenAPI — i psują `generated.ts` temu modułowi, który był pierwszy.
   Stąd prefiksy `ImportResolveRequest`/`ImportApproveRequest`. **Nowy schemat
   o generycznej nazwie: sprawdź `grep app__modules__ frontend/src/api/generated.ts`
   po `task fe-types`** — ma być zero trafień.
6. **Nowa zależność backendu: `anthropic`** (SDK). Obraz `app` wymaga przebudowy
   przed E2E. Klucz `ANTHROPIC_API_KEY` może być PUSTY i to jest wspierany tryb
   pracy (ADR-011): `ai-suggest` odpowiada wtedy 503, UI chowa przyciski AI,
   a cała reszta importu działa bez zmian — E2E leci właśnie w tym trybie.

**Wyniki uruchomień (realne):** `task check` zielony (exit 0) — 3 migrations-check
/ **431 unit** / **329 int** / **410 api** / **398 vitest w 42 plikach** / mypy
201 plików + vue-tsc / ruff / eslint / prettier / vite build. Suita API trwa teraz
**39 minut**, bo wgrywa i parsuje realne PDF-y w kilku scenariuszach — planować to,
nie przerywać. E2E: **flow importu przechodzi** (`import-review-flow.spec.ts`
i `import-upload.spec.ts`, 3/3 z setupem) na przebudowanym obrazie `app`
(doszedł `anthropic`) i migracji `0015` na bazie dev.

**Po resecie bazy dev (30.08.2026)** pełna suita idzie 18/20 — oba specy
importu przechodzą w KAŻDYM przebiegu, a `transfer` zszedł z timeoutu do
**8,6 s**. Pozostałe pojedyncze faile są NIEPOWTARZALNE (za każdym razem inny
spec, każdy przechodzi w izolacji i w kolejnym przebiegu) i dotyczą obszarów
spoza tego batcha — to znana kruchość suity dzielącej jedną bazę dev
(08_TESTING §3.1). Trzeci przebieg pod obciążeniem maszyny (równolegle wstał
kontener innego projektu) rozlał się na 8 timeoutów i **nie jest miarodajny** —
czas suity urósł z 3,6 do 10 minut przy zdrowym stacku (`/health` 34 ms,
zero 5xx).

**Review na diffie:** `/code-review` — dwa realne błędy naprawione
(`unmapped_product` blokował dania SCALANE, które nie wnoszą swoich składników
nigdzie; `kcal_mismatch` przypinał się do dania POMINIĘTEGO, czyli do karty
wyszarzonej w UI). `/security-review` — jedno ustalenie MEDIUM, naprawione:
lista kandydatów wysyłana do Claude API szła przez `visible_condition`, a ta
daje ADMIN-owi `true()` (**D16**) — administrator wysłałby poza instancję nazwy
przepisów WSZYSTKICH rodzin, wbrew D5. Kandydatów wyznacza teraz
`owned_condition` (`RecipesService.owned_names`), z testem czytającym dosłownie
wysłane żądania. Wszystkie trzy mają testy regresyjne.

Nowe długi: **U27** (N+1 zapytań o kandydatów w `ai-suggest`), **U28** (E2E
zostawia zatwierdzony job — statusy rozstrzygnięte są nieusuwalne z założenia),
**U29** (lista importów bez paginacji) i **U30 — NIE Z TEGO BATCHA, ROZSTRZYGNIĘTE
decyzją D22 (30.08.2026)**: import transferu reużywający rodzica wstawiał jego
dzieci OD NOWA (sekcje `plan_meals`/`recipe_ingredients` nie mają klucza
naturalnego), więc `transfer.spec.ts` podwajał dane demo przy każdym przebiegu —
1536 składników w daniu zamiast 3, `transfer/import/apply` w 73 s i timeout
na dwóch cudzych specach. Właściciel rozstrzygnął: **reużyty rodzic zostaje
nietknięty, dzieci pomijamy**; naprawa w R4. Baza dev zresetowana 30.08.2026
(downgrade base → upgrade head → seed demo → create-admin) — po resecie
`transfer.spec.ts` przechodzi w 8,6 s.


**2026-08-29 — DECYZJA D20 (właściciel): kontrakt PDF §3.2 zostaje rozszerzony.**
Właściciel zatwierdził rekomendację z BATCH_15: parser ma czytać dwa warianty
wiersza składnika, których dziś nie czyta — bez pary ilość + jednostka
(`Cukinia, 200 g`) i zawinięty między dwie linie (`…, 2 x` + `Kostka (16 g)`).
**Wykonanie należy do BATCH_16 i wchodzi tam jako Stage 0** (przed resztą, bo
zmienia dane wejściowe każdego kolejnego etapu). Cena zmiany, którą trzeba
zapłacić w tym samym commicie: **01_PDF_AUDIT §1 i §9.2 rosną z 642/178 na
649/180**, asercje `tests/integration/test_pdf_corpus.py` przestawiają się na
nowe liczby (nie osłabiają), unit test o ostrzeżeniu opisuje odtąd parsowanie,
a crosscheck §8.6 zbliża się do 181 nazw prototypu i nadal RAPORTUJE różnicę
zamiast asercji równości. Zachowanie wydanego B15 bez zmian — te 7 wierszy jest
tam widoczne jako `parse_warning`. Zaktualizowane: 02_DECISIONS (D20 przeniesiona
do zatwierdzonych), 01_PDF_AUDIT §9.2, karty B15 i B16.

**2026-08-29 — BATCH_15 (PDF_IMPORT_EXTRACTION).** Importer PDF ma pierwszą
połowę: upload jadłospisu (25 MB, sniffing `%PDF`, losowa nazwa, sha256),
**deterministyczny parser** wg wiążącego kontraktu 01_PDF_AUDIT, staging
w czterech nowych tabelach (migracja `0014`, głowa `0014`), sugestie mapowania
EXACT i raport odczytu w UI (`/import`). Parser **odtworzył wszystkie liczby
z audytu §1 co do jednej**: 24 dni, 96 posiłków, 642 wiersze składników,
178 nazw produktów, 24/24 sumy kontrolne. Walidacja krzyżowa z `prototype.db`:
**101 przepisów ≥ 84** i **629 składników ≥ 592**. Joby kończą na `parsed` —
review i zatwierdzanie to B16.

**Sześć rzeczy, o których muszą wiedzieć następne batche:**

1. **Próg wieloporcyjności (800 g) liczy się PER POSIŁEK, nie per danie** —
   i to jest odstępstwo od Implementation Notes karty B15, popartе pomiarem
   (errata 01_PDF_AUDIT **§9.1**). Wszystkie sześć mas z tabeli §5.1 odtwarza
   się wyłącznie jako suma całego posiłku razem z sekcją `Produkty`; rozstrzyga
   `dieta (7).pdf` KOLACJA = 806 g w DWÓCH daniach, z których żadne nie
   przekracza progu samo. Reguła per danie dałaby 3 blockery zamiast 4.
   Issue wisi na najcięższym daniu posiłku, więc ekran review w B16 pyta
   o porcje w kontekście POSIŁKU.
2. **Kontrakt 01_PDF_AUDIT dostał sekcję §9 „Errata z implementacji"** — pięć
   punktów, każdy z pomiarem na tym samym korpusie. Najważniejszy poza §9.1:
   **7 wierszy składników nie pasuje do wzorca §3.2** (`Cukinia, 200 g` i wiersze
   zawinięte między dwie linie). Parser ich NIE zgaduje — zgłasza jako
   `parse_warning` z surową linią. Rozszerzenie kontraktu to **decyzja D20 —
   ZATWIERDZONA 2026-08-29 (TAK, wykonanie w B16)**; zmienia liczby w §1 audytu
   na 649/180 i asercje testów korpusowych. B16 ma to jako **Stage 0**.
3. **Staging stoi POZA wzorcem scope i ma tak zostać.** `import_jobs` nie ma
   `scope` ani `household_id` (03_DATABASE §9): jadłospis to dokument zdrowotny
   jednej osoby, nie stan domowy. Widoczność egzekwuje jawny warunek
   właścicielski w serwisie (wzorzec `nutrition/service.py`), ADMIN widzi
   wszystko wg D16, cudzy job to 404. `ScopedQuery` tu nie pasuje i jego brak
   NIE jest „ręcznym filtrem scope" z listy błędów review.
4. **`recipes.import_job_id` ma wreszcie FK** (`SET NULL`, migracja `0014`) —
   dług z `0006` domknięty razem z `ForeignKey` w modelu, więc bramka dryfu
   z R3 świeci zielono. Wzorzec dla następnej kolumny czekającej na tabelę.
5. **Nowy podkatalog uploadów `import-pdf` jest w `PRIVATE_SUBDIRS`.**
   `/uploads/*` sprawdza WYŁĄCZNIE sesję, a jadłospis nosi imię i nazwisko
   pacjenta na stronie tytułowej — każdy nowy katalog z cudzą prywatnością
   dopisuje się tam w tym samym batchu (ustalenie review B14, teraz zastosowane).
6. **Lista jobów NIE niesie `parse_report`** (`ImportJobSummary` ma tylko liczby
   zbiorcze) — pełny raport dociąga `GET /import/jobs/{id}`. Złapało to dopiero
   **E2E**: vitest z raportem wklejonym w mock listy przechodził przy zepsutej
   stronie. Mocki frontendu muszą odwzorowywać PODZIAŁ odpowiedzi, nie wygodę
   testu.

**Wyniki uruchomień (realne):** `task check` zielony (exit 0) — 3 migrations-check
/ **379 unit** / **289 int** / **398 api** / **367 vitest w 39 plikach** / mypy
190 plików + vue-tsc / ruff / eslint / prettier / vite build. E2E: **19/19**
(18 testów + setup, 1,3 min) na pełnym stacku z przebudowanym obrazem app
(doszedł pdfplumber) i migracją `0014` na bazie dev. Testy korpusowe biegną na
8 REALNYCH plikach z `data/source_pdfs/`, nie na mockach.

**Review na diffie (`/code-review`):** ustalenia i sposób ich domknięcia
w Completion notes karty. Nowe długi zapisane tamże: **U22** (sekcja `Produkty`
bez znacznika w bazie — problem skalowania porcji w B16), **U23** (3 ze 103 nazw
dań ucięte przez zawijanie kolumn), **U24** (`PDF_PARSE_TIMEOUT_S` przerywa
żądanie, nie wątek — twardy limit to temat B17), **U25** (brak paginacji listy
importów w UI) i **U26** — testy uruchamiane taskiem dziedziczą
`UPLOADS_DIR` z `.env`, a conftest ustawia katalog tymczasowy przez
`setdefault`, więc wgrane pliki lądują w `backend/data/uploads/`; po B14
zostawał tam pusty katalog, po B15 prawdziwy PDF z jadłospisem. Doraźnie
`backend/data/` w `.gitignore`. Karta **B16** dostała sekcję „Stan faktyczny po BATCH_15"
z faktycznymi ścieżkami plików i sześcioma pułapkami.

**2026-08-29 — BATCH_14 (IMPORT_EXPORT).** Dane należą do użytkownika: jest
**format transfer v1** (ZIP z `export.json` + `photos/`), eksport własnych danych
i całej instancji (ADMIN), a import ma dwa kroki — raport **DRY-RUN**, który nie
zapisuje ani jednego wiersza, i `apply` w JEDNEJ transakcji z decyzją per kolizja
(„użyj istniejącego" / „utwórz kopię"). UI: sekcja „Twoje dane" w Ustawieniach,
nowa strona `/admin/dane` i wspólny `TransferImportDialog`. **Bez migracji** —
head nadal `0013`.

**Siedem rzeczy, o których muszą wiedzieć następne batche:**

1. **`transfer/serializer.py::SECTIONS` + `schemas.py::SECTION_ORDER` to JEDNA
   definicja formatu dla obu stron transferu.** Nowa tabela domenowa = nowy wpis
   w `SECTIONS` **i** w `SECTION_ORDER`, inaczej po prostu nie da się jej
   wyeksportować (i nikt tego nie zauważy, bo eksport nie krzyczy o brakach).
   Test `test_referencje_wskazuja_sekcje_wczesniejsza_w_kolejnosci` pilnuje, że
   każda referencja wskazuje sekcję wchodzącą WCZEŚNIEJ — FK z RESTRICT nie
   wybaczają innej kolejności (ustalenie R3).
2. **`ScopedQuery.owned_condition` / `select_owned` (`app/core/scope.py`)** —
   bliźniak `HouseholdScopedQuery.household_condition`: „to są MOJE dane", BEZ
   wyjątku dla ADMIN-a. `visible_condition` deleguje teraz do tej metody, więc
   zachowanie dla nie-ADMIN-a jest niezmienione. Każdy przyszły widok, który
   znaczy „moje", a nie „wolno mi zobaczyć" (eksport, rozliczenia, cokolwiek per
   konto), używa `select_owned`, a nie `select_visible`.
3. **Czego eksport NIE niesie i nie ma nieść**: `users.password_hash`,
   `sessions`, `shopping_lists.public_token`/`token_revoked` (żywy token bez
   logowania w pliku, który ląduje w mailu — ADR-010), `created_at`/`updated_at`
   poza `audit_entries`, `recipes.import_job_id`. Pilnuje tego unit test
   `test_zadna_sekcja_nie_niesie_hasla_ani_tokenu` na tabeli `SECTIONS`.
4. **`shopping_generations` wychodzą tylko w stanie `final`/`discarded`**, a ich
   `params` przenoszą się DOSŁOWNIE (wersjonowane wejście silnika, R3). Generacja
   `preview` jest jedynym stanem edytowalnym, więc po imporcie jej finalizacja
   tworzyłaby pozycje list z identyfikatorami cudzej bazy.
5. **Powtórny import własnego pliku na to samo konto działa**: `plan_days`
   scalają się po `UNIQUE(owner_user_id, day)` (posiłki dopisują się do
   istniejącego dnia, jak przy instancjacji szablonu z B07), a wiersze niosące
   FAKT o rodzicu (przeliczniki, wartości odżywcze, oceny, cele na datę) wchodzą
   `ON CONFLICT DO NOTHING`. Nowa tabela z UNIQUE, do której import może trafić
   dwa razy, MUSI zadeklarować `merge_key` albo `idempotent` — inaczej użytkownik
   dostanie 409 na całym imporcie.
6. **Limit paczki transferu to nowa zmienna `TRANSFER_MAX_ZIP_MB`** (domyślnie
   100, `.env.example` + 07_SECURITY §6/§7). Archiwum przechodzi kontrolę
   w kolejności: limit rozmiaru → sygnatura ZIP → biała lista wpisów
   (`export.json` i `photos/…`, żadnych `..`, ścieżek absolutnych ani
   backslashy) → rozmiar po dekompresji z NAGŁÓWKÓW (zip-bomba pada przed
   rozpakowaniem). Zdjęcia z archiwum idą przez `core/uploads.save_image`, więc
   dostają nowe nazwy i są re-enkodowane.
7. **E2E: prefiks nazwy musi być NA POCZĄTKU** (`E2E <obszar> …`).
   `cleanupE2eData` dopasowuje encje przez `byPrefix`, więc nazwa w rodzaju
   „Zupa E2E transfer" przeżywa sprzątanie — i natychmiast wywraca kolejny spec,
   bo trigramowa szukajka przepisów znajduje cudzą pozostałość i ukrywa inline
   create (dług U15 z review R2, złapane realnym failem w tym batchu).

**Review na diffie (`/code-review` + `/security-review`) zgłosił pięć ustaleń,
wszystkie naprawione w tym samym commicie** — szczegóły w Completion notes karty.
Dwa warto znać poza tym batchem: (a) **`GET /uploads/*` sprawdza wyłącznie sesję,
nie właściciela pliku**, więc katalog uploadów NIE jest miejscem na dane jednego
konta — stąd `core/uploads.py::PRIVATE_SUBDIRS`, do którego dopisuje się każdy
nowy podkatalog trzymający cudzą prywatność; (b) **`hash_password` musi iść przez
`run_in_threadpool`** także w pętli po wierszach, nie tylko w `accounts/service.py`.

Ustalenia propagowane do kart: **B15** (staging PDF nie wchodzi do eksportu v1;
`recipes.import_job_id` w pliku jest `null`; nowa encja domenowa = rozszerzenie
serializera; FK do `import_jobs` musi wejść do modelu w tym samym commicie co
migracja) i **B18** (transfer logiczny jako DRUGA ścieżka restore obok
`pg_dump` — do przećwiczenia w procedurze; plik eksportu nie ma haseł i jest
danymi osobowymi jak backup). 02_DECISIONS bez zmian — batch nie miał bramki
i nie potrzebował nowej decyzji. Cztery długi zapisane w Completion notes karty:
**U18** (import selektywny), **U19** (brak komendy CLI restore), **U20**
(leniwe sprzątanie scratcha importu), **U21** (`to_create` liczone
optymistycznie dla sekcji `ON CONFLICT DO NOTHING`).

**2026-08-22 — BATCH_13 (STATISTICS).** Jest strona `/statystyki` (widok 7):
zakres **Tydzień / Miesiąc / Własny** (sufit 92 dni walidowany po obu stronach),
zakładki **Kalorie** i **Makroskładniki**, słupki dni z **schodkową** linią celu,
średnia krocząca 7 dni jako nakładka na słupkach makro oraz podsumowanie
średnia/cel/delta/status. Dane liczy nowy, wyłącznie odczytowy endpoint
`GET /api/v1/stats/daily?from=&to=` (moduł `planning`, serwis
`stats_service.py`) — bez ani jednej kolumny cache w bazie (02_DOMAIN §13.2)
i bez migracji (head nadal `0013` z B12).

**Sześć rzeczy, o których muszą wiedzieć następne batche:**

1. **`planning/stats_service.py` nie liczy nic sam.** Dni bierze przez
   `PlanningService.list_days` (ten sam `ScopedQuery` i ta sama reguła
   rozstrzygania dnia, co widok planu), cele przez `GoalsService.goals_of` +
   `goal_for_day`, statusy przez `engine.goal_status`, a średnią przez
   `aggregate` + `portion_nutrition` + `round_for_output`. Nowy widok liczący
   cokolwiek żywieniowego reużywa tych wejść — drugiego zaokrąglania ani
   drugiego filtra widoczności w tym pionie nie ma i nie ma powstać.
2. **Kontrakt `/stats/daily`**: `days[]` ma element dla KAŻDEJ daty zakresu;
   dzień bez planu to `has_plan: false`, `nutrition: null`, statusy `null`
   (luka, nie zero). **Dzień istniejący, ale bez posiłków** (po R3 zostaje
   tylko taki z tytułem) też liczy się jako brak planu. `summary.avg` jest
   `null` przy zerze dni z planem, a `summary.goal_progress` używa
   `DayGoalProgressRead`/`GoalMetricRead` — tego samego kształtu, co kafelki
   planu dnia; `target` jest ŚREDNIĄ celów dni z planem, liczoną per pole.
3. **`nutrition/types.py += GOAL_NUMERIC_FIELDS`** — jedno źródło listy pól,
   które mają odpowiednik w celu użytkownika (`kcal`, `protein_g`, `fat_g`,
   `carbs_g`). Nowe pole celu = wpis TUTAJ, nie czwarta lista w schematach.
   (Dług: `planning/service.py::_GOAL_FIELDS` nadal ma własną kopię — scalić
   przy R4.)
4. **`BarChart` ma teraz DWA tryby celu**: `target` na całym wykresie = jedna
   pozioma linia (tak używa go widok tygodnia z B07, bez zmian), `target` na
   POJEDYNCZYM słupku = linia SCHODKOWA (dzień bez celu ją przerywa). Doszło
   też `empty: true` (luka — przerywany obrys, dzień nie wchodzi do skali),
   podmienialny `emptyText` i slot **`overlay`** udostępniający geometrię
   (`width`, `height`, `scaleMax`).
5. **`TrendLine` ma dwa tryby renderowania**: samodzielny (`<svg>` z własną
   skalą) i nakładka (`frame` z geometrią rodzica ⇒ `<g>` bez własnego `<svg>`,
   do slotu `overlay`). Wspólna skala jest warunkiem sensu wykresu; punkt
   `null` PRZERYWA linię, a nie udaje zera.
6. **`e2e/cleanup.ts` eksportuje teraz `csrfHeaders`** — spec statystyk seeduje
   dane PRZEZ API (plan 3 dni + cel), bo klikanie planu sprawdzałoby plan, nie
   statystyki. Cel żywieniowy należy do JEDNEGO konta E2E, więc spec ustawia
   `valid_from` w oknie testowym (2031) i usuwa cel w `afterAll`; presety
   „Tydzień"/„Miesiąc" liczą się od „dziś", więc dane z lat 2030+ oglądamy
   zakresem WŁASNYM.

Ustalenia propagowane do kart: **B14** (round-trip celów — eksport musi
zachować CAŁĄ historię `user_nutrition_goals` z `valid_from`, inaczej statusy
dni sprzed zmiany celu po cichu się przepiszą; plus `app/main.py` ma już wpis
routera statystyk) i **R4** (nowa sekcja audytu „Spójność statystyk z planem
dnia": te same liczby w obu widokach, progi z `ui_settings`, cel schodkowy,
luki jako dzielnik). 02_DECISIONS bez zmian — batch nie miał bramki i nie
potrzebował nowej decyzji.

**2026-08-22 — BATCH_12 (PWA_AND_OFFLINE).** Aplikacja jest instalowalną PWA
(manifest PL, komplet ikon PNG 192/512 `any`+`maskable`, `apple-touch-icon`,
Workbox: precache shella, `NetworkFirst` dla `/api/*` z `networkTimeoutSeconds: 3`,
`CacheFirst` dla `/uploads/*`), a lista zakupowa — zalogowana i publiczna
`/l/:token` — działa bez sieci: treść leży w IndexedDB, odhaczenia idą do kolejki
z własnym `checked_at` i synchronizują się po powrocie zasięgu (LWW per pozycja).
Weszła też decyzja **D19**: `shopping_list_items.received_at` (migracja `0013`)
czyni `accept-to-pantry` idempotentnym.

**Osiem rzeczy, o których muszą wiedzieć następne batche:**

1. **Migracja `0013_shopping_item_received_at`** — head to teraz `0013`.
   B13/B14 idące równolegle numerują od `0014`; po merge'u sprawdź
   `task db-heads` (obie karty mają o tym wpis).
2. **PATCH pozycji (prywatny i publiczny) przyjmuje opcjonalne `checked_at`**
   z WYMAGANĄ strefą czasową; starszy znacznik nie nadpisuje młodszego (200 ze
   stanem serwera), znacznik z przyszłości ponad 5 minut jest przycinany do
   `now()` serwera, a powtórka tego samego żądania NIE przesuwa znacznika.
   Ta ostatnia własność (idempotencja z R3) jest warunkiem ponawiania z kolejki
   i nie wolno jej zepsuć „optymalizacją" warunku w `_apply_item_changes`.
3. **`accept_to_pantry` przyjmuje teraz `now` z routera** i stempluje
   `received_at` w tej samej transakcji co wpis w spiżarni. **409 ma dwa
   warianty** (`NOTHING_TO_RECEIVE` i `ALREADY_RECEIVED`), a
   `ReceivedToPantry`/`AcceptToPantryResponse` mają addytywne
   `already_received`.
4. **`received_at` NIE wchodzi do odpowiedzi publicznej** — pilnuje tego
   asercja dokładnego zbioru kluczy w `test_public_lists_api.py`. Każde nowe
   pole pozycji listy wymaga świadomej decyzji, po której stronie tej granicy
   stoi.
5. **Nowa warstwa `frontend/src/lib/offline/`**: `db.ts` (IndexedDB przez `idb`;
   klucz kolejki `{target}#{itemId}` = deduplikacja per pozycja), `clock.ts`
   (przesunięcie zegara z nagłówka `Date` KAŻDEJ odpowiedzi — hook siedzi
   w `api/client.ts` i `api/publicList.ts`), `sync.ts` (klasyfikacja
   sent/retry/gone/dropped), `hydrate.ts` (snapshot → cache TanStack Query
   z `updatedAt: 1`), `registerSW.ts`. Store `stores/offlineQueue.ts` (Pinia).
   Ekran, który ma działać offline, reużywa TEGO — nie pisze drugiej kolejki.
6. **`checkPublicListItem` ma czwarty, opcjonalny argument `checkedAt`**;
   `updateShoppingListItem` przyjmuje `checked_at` w payloadzie.
7. **Czego kolejka świadomie NIE obsługuje**: zmiany sklepu (kolejność sekcji
   składa serwer, ustalenie R3) i przyjęcia zakupów do spiżarni (jego wartością
   jest policzalna odpowiedź serwera). Obie akcje są offline wyłączone
   z podpowiedzią. Wpuszczenie ich do kolejki wymaga decyzji, nie „ulepszenia".
8. **Nowe zależności frontendu**: `idb` (runtime) i `fake-indexeddb` (dev —
   testy jadą na prawdziwym IndexedDB, nie na atrapie). B13/B14 rozwiązują
   konflikt `package.json` unią zależności.
9. **`networkMode: 'always'` w `main.ts`** (queries I mutations) — zmiana
   GLOBALNA, nie lokalna dla listy. Domyślny tryb `'online'` pauzuje mutacje
   przy `navigator.onLine === false`, więc kolejka offline nigdy nie
   zobaczyłaby odhaczenia. Skutek uboczny dla innych ekranów: mutacja bez sieci
   nie wisi w pamięci, tylko od razu pada z komunikatem — czyli zachowuje się
   jak przed wprowadzeniem TanStack pauzy i tak też jest opisana w 05_FRONTEND §6.
10. **Wszystko, co idzie do IndexedDB, przechodzi przez `plain()`** — structured
   clone rzuca `DataCloneError` na proxy Vue. Nowy magazyn albo nowe pole
   w `db.ts` musi trzymać się tej granicy; błąd jest CICHY (`withDb` go łyka).
11. **`task test-e2e` przepuszcza argumenty za `--`** (`task test-e2e --
   offline-lista.spec.ts`) — wzorzec targetów pytest. Bramka woła target bez
   argumentów, więc pełny przebieg jest zawsze ten sam.

Ustalenia dla B17 (CSP musi dopuszczać SW z `'self'`, `manifest.webmanifest`
z właściwym typem, wykluczenie `/api/v1/auth/*` z runtime cache) i B18 (HTTPS
jest warunkiem działania SW; trzy sprawdzenia po wdrożeniu) są wpisane do ICH
kart, nie tylko tutaj.

**2026-08-22 — D18 i D19 ZAMKNIĘTE przez właściciela (ustalenia R3).**
Rejestr 02_DECISIONS nie ma już żadnej decyzji dotyczącej batchy 12–17;
otwarte zostają D6/D7 (bramki B18) i cztery pozycje bez konsumenta.

**D18 — ręczne pozycje listy zakupowej: NIE.** Rekomendacja agenta („tak, ale
jako pozycja z produktem kanonicznym, w B12") została ODRZUCONA. Lista pozostaje
w CAŁOŚCI wynikiem generacji z planu, bo z metadanych pozycji (produkt kanoniczny
+ kategoria + opakowanie) żyją trzy rzeczy naraz: sekcje sortowane profilem
sklepu, plakietka resztki i przyjęcie zakupów do spiżarni — pozycja dopisana
ręcznie byłaby wyjątkiem w każdym z tych miejsc. Ścieżka dla brakującej rzeczy:
dopisać do PLANU i wygenerować turę ponownie. Wpisane do **02_DOMAIN §9.4**
(reguła jawna) i do **Out of Scope karty B12** — z adnotacją, że nie wolno tego
wprowadzić „jako ułatwienia offline".

**D19 — znacznik przyjęcia zakupów: PER POZYCJA (opcja 3), wdrożenie w B12.**
Odrzucone: (a) „zostaje sam dialog" — po wejściu kolejki offline ponowienie
żądania po utracie odpowiedzi jest normalną pracą, nie awarią, więc podwójne
dolanie zrobiłoby się samo, a skutek jest CICHY (spiżarnia pokazuje 4 l mleka
zamiast 2 l i użytkownik dowiaduje się o tym, gdy silnik przestaje je kupować);
(b) „znacznik na LIŚCIE" — jedna lista = jedno przyjęcie blokuje uzasadniony
przypadek „doniosłem jeszcze dwie rzeczy z torby i odhaczyłem je później".
Koszt (a) był zerowy, ale kupował bezpieczeństwo za cenę wyłączenia akcji
offline; koszt (b) i (c) jest IDENTYCZNY (jedna kolumna, jedna migracja), więc
wybór wariantu poprawnego semantycznie nic nie kosztował.

**Co to znaczy dla B12** (karta zaktualizowana w §Database/migrations, §Backend,
§Frontend, §Stages 1a, §Tests, Acceptance Criteria 7–8, Out of Scope, Expected
files i Implementation checklist):

1. **B12 przestał być batchem bez migracji** — dochodzi
   `shopping_list_items.received_at timestamptz NULL`. Numer = pierwszy wolny,
   `down_revision` z `task db-heads`, a po merge'u z równoległymi B13/B14
   trzeba sprawdzić, czy `alembic heads` daje jedną głowę (obie te karty też
   mogą dołożyć migrację). Migracja NIE backfilluje istniejących list —
   historyczne przyjęcia nie są nigdzie zapisane, więc każda wartość byłaby
   wymyślona.
2. **Atomowość z R3 jest warunkiem poprawności D19**, nie ozdobą: stempel
   `received_at` i wpis w spiżarni muszą lecieć w JEDNEJ transakcji
   (`receive_purchase` nie commituje od R3), inaczej przerwanie między nimi
   daje dokładnie ten podwójny zapis, przed którym decyzja broni.
3. **`received_at` NIE wchodzi do odpowiedzi publicznej.** `PublicListItemRead`
   to biała lista pól (02_DOMAIN §13.5) — osoba z linkiem nie ma nic wiedzieć
   o spiżarni rodziny. Test dokładnego zbioru kluczy w
   `test_public_lists_api.py` musi to złapać.
4. **Dwa różne 409, nie jedno**: „nic nie odhaczone" (dotychczasowe
   `NOTHING_TO_RECEIVE`) i „te zakupy są już w spiżarni" — dla użytkownika to
   dwie różne sytuacje. Odpowiedź `ReceivedToPantry` dostaje ADDYTYWNIE pole
   `already_received`.
5. **Dzięki znacznikowi przyjęcie zakupów MOŻE wejść do kolejki offline**
   (Stage 5). Bez niego trzeba by je offline zablokować — to była realna
   alternatywa, nie hipoteza.

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
