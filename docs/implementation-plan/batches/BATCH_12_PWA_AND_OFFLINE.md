# BATCH_12 — PWA_AND_OFFLINE

Klasa: PLAT · Zależności: BATCH_11 (listy + share), R3 · Bramki decyzji: brak
· Rozmiar: **M** · Dozwolona równoległość: **B12 ∥ B13 ∥ B14** (osobne git
worktree — patrz sekcja Cross-Batch Impact, kolizje plików!).

## Goal

Aplikacja staje się instalowalną PWA (manifest PL, ikony, standalone,
splash), a lista zakupowa — kluczowy widok mobilny — działa w pełni offline:
otwarta lista (zalogowany i publiczny `/l/:token`) jest snapshotowana do
IndexedDB, odhaczenia offline trafiają do kolejki mutacji i synchronizują
się po odzyskaniu sieci (last-write-wins per pozycja). Użytkownik w sklepie
bez zasięgu odhacza zakupy tak samo, jak z zasięgiem.

## Context

Batch zastaje (po B11 + R3):

- `frontend/` — działające SPA (Vite, Vue 3, Pinia, TanStack Query).
  **Korekta po B01 (2026-08-16)**: `vite-plugin-pwa` JEST już wpięty
  w `frontend/vite.config.ts` (registerType `autoUpdate`, manifest PL,
  `navigateFallbackDenylist` dla `/api/`, ikony placeholder
  `public/icon.svg` + `icon-maskable.svg`). Ten batch NIE inicjalizuje
  pluginu — dokłada strategie cache, kolejkę offline i KOMPLET ikon
  (PNG 192/512, splash) w miejsce placeholderów SVG.
- `frontend/src/main.ts`;
  strony `ZakupyPage`, `ListaZakupowPage` (`/zakupy/listy/:id`),
  `PublicznaListaPage` (`/l/:token`, poza shellem, bez auth).
- Backend: `backend/app/modules/shopping/` — **stan faktyczny po B11**:
  `lists_router.py` z `PATCH /shopping/lists/{id}/items/{item_id}`
  (`{checked?, already_have?}`) i `public_router.py` z
  `PATCH /api/v1/public/lists/{token}/items/{item_id}` (WYŁĄCZNIE `{checked}`,
  `extra="forbid"`, rate limit 60/min/IP, 410 po expiry/revoke). Logika obu
  ścieżek mieszka w `lists_service.py`, nie w `service.py`.

### Sześć rzeczy z B11, które wiążą ten batch

1. **`checked_at` to moment OSTATNIEJ decyzji o checkboxie — także odznaczenia.**
   Ustawia go SERWER (`_apply_item_changes` w `lists_service.py`) przy każdej
   zmianie `checked`, w obie strony; klient go dziś NIE przysyła. Ta semantyka
   jest wybrana pod LWW z ADR-009: żeby rozstrzygnąć konflikt dwóch telefonów,
   trzeba wiedzieć, która decyzja jest MŁODSZA, a nie tylko kiedy coś odhaczono.
   Dokładając `checked_at` od klienta (Stage 1), nie zmieniaj tej semantyki —
   rozszerz ją: `checked_at` z żądania wygrywa tylko wtedy, gdy jest MŁODSZE od
   zapisanego, a pole pominięte znaczy „użyj czasu serwera".
2. **Kształt odpowiedzi publicznej** (biała lista pól, `PublicListRead`):
   `{name, expires_at, items: [{id, label, amount, unit, category_name, checked,
   leftover_amount, already_have, packages_count, package_size}]}`. Snapshot
   IndexedDB buduj na TYM kształcie — nie ma tu `position` ani `category_id`,
   bo kolejność pozycji jest już ustalona przez serwer (sekcje idą po sobie
   w kolejności profilu sklepu). Dokładanie pól do tej odpowiedzi wymaga
   aktualizacji testu białej listy i jest zmianą kontraktu bezpieczeństwa.
   Strona zalogowana dostaje `sections` (`ShoppingListDetailRead`) — dwa różne
   kształty, dwa snapshoty.
3. **Publiczny klient HTTP już istnieje**: `frontend/src/api/publicList.ts`
   (`credentials: 'omit'`, bez CSRF, `PublicListUnavailableError` dla 404/410
   i `PublicListRequestError` dla reszty). Kolejka offline ma używać JEGO,
   nie `apiFetch` — i musi rozróżniać te dwa błędy: wygaśnięcie tokenu
   w trakcie offline (Stage 5) to `PublicListUnavailableError`, a nie brak sieci.
4. **Trasa `/l/:token` ma `meta.anonymous: true`** (nowa flaga w `router.ts`,
   sprawdzana PRZED `auth.ensureLoaded()`), jest importowana leniwie i renderuje
   własny minimalny layout. Service worker musi więc precache'ować TEN chunk
   osobno — shell aplikacji nie jest na tej stronie ładowany.
5. **Optimistic update jest już zaimplementowany** na obu stronach przez
   `setQueryData` w `onMutate` + rollback z kontekstu (`ListaZakupowPage.vue`,
   `PublicznaListaPage.vue`). Kolejka offline ma go ROZSZERZYĆ (persystencja
   w idb), nie zastąpić — i nie przepisywać na Pinia stanu serwera (ADR-007).
6. **Klucze TanStack Query**: `queryKeys.shopping.list(id)` =
   `['shopping','lists','detail', id]`, `queryKeys.publicList.detail(token)` =
   `['public-list', token]`. Prefiks indeksu (`['shopping','lists','index']`)
   jest ROZŁĄCZNY ze szczegółem świadomie — wspólny prefiks kasował świeżo
   podmienioną odpowiedź PATCH-a przy invalidacji listy list.
- `shopping_list_items.label` — tekst pozycji renderowalny offline
  (03_DATABASE §8, celowo zdenormalizowany). **Stan faktyczny po B10**:
  `label` to nazwa WYBRANEGO WARIANTU SKLEPOWEGO („Mąka pszenna 1 kg"), a gdy
  wariantu nie ma — nazwa produktu kanonicznego („Cebula"). Semantyki tej
  kolumny nie wolno zmieniać: offline nie ma dostępu do katalogu, więc pozycja
  musi umieć pokazać się sama.

### Pięć ustaleń z REVIEW R3 (2026-08-22, sprawdzone realnymi requestami)

1. **Publiczny PATCH JEST idempotentny** i to jest własność, na której kolejka
   offline może się oprzeć: `_apply_item_changes` ustawia `checked_at` TYLKO
   przy faktycznej zmianie wartości, więc powtórzone `{"checked": true}` zwraca
   200 i NIE przesuwa znacznika czasu. Rozszerzając PATCH o `checked_at`
   klienta (Stage 1), zachowaj to: powtórka tego samego żądania nie może
   zmieniać stanu, bo kolejka po utracie odpowiedzi wyśle je ponownie.
2. **Limit 60/min/IP jest WSPÓLNY dla GET i PATCH całej ścieżki publicznej**
   (`limiter.shared_limit`, scope `public-lists` — zweryfikowane: 60. żądanie
   przechodzi, 61. to 429, a PATCH po wyczerpaniu limitu GET-ami też dostaje
   429). Kolejka, która po odzyskaniu sieci wypluje 40 odhaczeń plus odświeżenia
   listy, wejdzie w limit. **429 to stan przejściowy, nie porażka mutacji**:
   wymagany backoff i zachowanie pozycji w kolejce. Ta sama lista otwarta na
   dwóch telefonach za jednym NAT-em dzieli ten licznik.
3. **Sekcje składa SERWER** (`sorting.py`), więc offline nie potrafi ich
   przeliczyć: zmiana sklepu listy (`PATCH /shopping/lists/{id}`) zmienia
   KOLEJNOŚĆ sekcji, a offline nie zna profilu `store_category_order`. Wniosek
   dla tego batcha: zmiana sklepu **nie wchodzi do kolejki offline** (dostępna
   tylko online) albo wchodzi z jawną informacją, że kolejność odświeży się po
   synchronizacji. Nie licz kolejności na kliencie — to złamałoby ustalenie
   B11 pkt 1 (jedna lista = jedna kolejność na ekranie, w druku i pod linkiem).
4. **Przyjęcie zakupów do spiżarni jest atomowe (R3), ale NIE było
   idempotentne** — powtórka dolewała zakupy drugi raz. **Decyzja właściciela
   D19 ZATWIERDZONA 2026-08-22: znacznik PER POZYCJA, wdrożenie w TYM batchu.**
   Pełna instrukcja: §Database/migrations i §Backend niżej. To warunek wejścia
   przyjęcia zakupów do kolejki offline (Stage 5) — bez znacznika ta akcja
   musiałaby być offline zablokowana.
5. **Ręczne pozycje listy — decyzja D18 ZATWIERDZONA 2026-08-22: NIE, nic nie
   dopisujemy ręcznie.** Lista pozostaje w całości wynikiem generacji; brakującą
   rzecz dopisuje się do PLANU i generuje turę ponownie (02_DOMAIN §9.4).
   Ten batch NIE dokłada pola „dodaj pozycję" — jest w Out of Scope.

Wymagane lektury: **ADR-009** (całość — kontrakt tego batcha),
05_FRONTEND §6 (PWA i offline), §1 (Pinia = kolejka offline), 06_UIUX §5
(mobile, lista krytyczna), 04_API §2 (`/public/lists/{token}`),
07_SECURITY §5 (tokeny publiczne), 08_TESTING §2.9–§3.

## Stages

1. **Backend LWW** — `PATCH` checkboxa przyjmuje opcjonalne `checked_at`
   klienta; serwis stosuje last-write-wins per pozycja; testy API zielone.
1a. **Backend: znacznik przyjęcia (D19)** — migracja `received_at` na pozycjach,
   `accept_to_pantry` idempotentne, 409 gdy nie ma nic nowego; testy API
   i integracyjne zielone. Robić RAZEM z etapem 1 (jedna migracja, jeden
   przebieg testów backendu), a nie na końcu batcha.
2. **PWA shell** — vite-plugin-pwa skonfigurowany (manifest, ikony,
   Workbox precache + NetworkFirst `/api/*`); aplikacja instalowalna,
   Lighthouse PWA installable = pass.
3. **Snapshot IndexedDB** — otwarta lista (obie strony) zapisywana do idb;
   po odcięciu sieci lista renderuje się ze snapshotu.
4. **Kolejka mutacji + sync** — odhaczenia offline kolejkowane w Pinia +
   idb (przeżywa reload), flush po `online`/focus; korekta zegara.
5. **UX offline** — wskaźnik trybu offline, licznik oczekujących zmian,
   obsługa wygaśnięcia tokenu w trakcie offline (410 przy synchronizacji).
6. **Testy** — vitest kolejki + E2E Playwright z `context.setOffline`.
7. **Docs** — aktualizacja 05_FRONTEND §6 do stanu faktycznego, PROGRESS.md.

## Database / migrations

**Jedna migracja — kolumna `received_at` (decyzja D19).**

| Tabela | Kolumna | Typ | Uwagi |
|---|---|---|---|
| `shopping_list_items` | `received_at` | `timestamptz NULL` | moment przyjęcia TEJ pozycji do spiżarni; `NULL` = jeszcze nieprzyjęta |

Zasady bez zmian: numer = pierwszy wolny w `migrations/versions/`,
`down_revision` = wynik `task db-heads` (NIGDY numer z tej karty), `upgrade`
i `downgrade` przechodzą na czystej bazie, `alembic heads` = jedna głowa.
**B13 i B14 mogą iść równolegle i też dodawać migracje** — po merge'u gałęzi
sprawdź `task db-heads` i przy dwóch głowach zrób migrację scalającą, zanim
puścisz `task check`.

Czego migracja NIE robi: nie backfilluje istniejących list (wszystkie pozycje
zostają `NULL`, czyli „nieprzyjęte"). To świadome — historyczne przyjęcia nie są
nigdzie zapisane, więc każda inna wartość byłaby wymyślona. Praktyczny skutek
jest znikomy: listy sprzed wdrożenia wygasły albo mają zakupy dawno w spiżarni.

Reszta schematu wystarcza: `shopping_list_items.checked` i
`checked_at timestamptz` istnieją od `0012` (03_DATABASE §8). **Po wdrożeniu
zaktualizuj 03_DATABASE §8 o nową kolumnę** (living documentation) oraz
`DB_TABLES` nie ruszaj (tabela istnieje), ale dopisz kolumnę do asercji tam,
gdzie testy sprawdzają kształt pozycji.

## Backend

Zmiany minimalne, wyłącznie w module `shopping`:

| Ścieżka | Metoda | Rola | Zmiana |
|---|---|---|---|
| `/api/v1/shopping/lists/{id}/items/{item_id}` | PATCH | U | body przyjmuje opcjonalne `checked_at` (ISO8601 UTC); LWW |
| `/api/v1/public/lists/{token}` | PATCH | P | jw. dla pozycji publicznych; 410 po expiry/revoke bez zmian |

| `/api/v1/shopping/lists/{id}/accept-to-pantry` | POST | U | przyjmuje WYŁĄCZNIE pozycje odhaczone i nieprzyjęte; stempluje `received_at`; 409 gdy nie ma nic nowego |

**Znacznik przyjęcia (D19) — instrukcja wykonawcza.** Zmiana siedzi w
`shopping/lists_service.py::accept_to_pantry` (nie w `service.py` — to drugi
serwis modułu, od B11):

1. Pętla pomija pozycje `received_at IS NOT NULL` obok istniejących warunków
   (`not checked` i `already_have` — ten drugi doszedł w R3: „mam już w domu"
   nie jest zakupem).
2. `received_at = now` ustawia SERWER (czas wchodzi parametrem z routera, jak
   `checked_at`), w TEJ SAMEJ transakcji co zapis w spiżarni. **Atomowość jest
   warunkiem poprawności, nie ozdobą**: `PantryService.receive_purchase` nie
   commituje od R3, więc commit jest jeden — gdyby stempel i wpis w spiżarni
   szły osobno, przerwanie między nimi dawałoby dokładnie ten podwójny zapis,
   przed którym D19 broni.
3. Gdy nie ma ANI JEDNEJ pozycji do przyjęcia, ale jakaś była już przyjęta —
   409 z komunikatem „Te zakupy są już w spiżarni." Gdy nic nie jest odhaczone —
   zostaje dotychczasowe 409 `NOTHING_TO_RECEIVE`. Dwa różne komunikaty, bo to
   dwie różne sytuacje dla użytkownika.
4. Odpowiedź `ReceivedToPantry` dostaje pole `already_received: int` (liczba
   pominiętych bo już przyjętych) obok `created`/`increased`/`skipped`. Zmiana
   ADDYTYWNA — `skipped` zachowuje znaczenie z R3.
5. `ShoppingListItemRead` zwraca `received_at`, żeby lista mogła oznaczyć
   pozycje już przyjęte. **Odpowiedź PUBLICZNA (`PublicListItemRead`) tego pola
   NIE DOSTAJE** — to biała lista pól (02_DOMAIN §13.5), a osoba z linkiem nie
   ma nic wiedzieć o spiżarni rodziny.

Logika LWW w `shopping/lists_service.py`: jeżeli przysłane `checked_at` jest
**starsze** niż zapisane w DB — mutacja ignorowana (odpowiedź 200 ze stanem
aktualnym; klient przyjmuje stan serwera). Brak `checked_at` w body =
zachowanie dotychczasowe (natychmiastowe, `now()` serwera) — kompatybilność
z odhaczaniem online. Walidacja: `checked_at` z przyszłości > 5 min ⇒
przycinane do `now()` serwera (ochrona przed rozjechanym zegarem klienta).

## Frontend

- **Stan „przyjęte" na liście (D19)**: pozycja z `received_at` dostaje dyskretny
  znacznik (tekst, nie tylko kolor — 06_UIUX §1), a przycisk „Przyjmij zakupy
  do spiżarni" pokazuje, ile pozycji WEJDZIE przy kliknięciu (0 = przycisk
  nieaktywny z podpowiedzią „wszystko już przyjęte"). Komunikat po akcji
  rozszerza istniejący `texts.shoppingList.acceptDone` — dziś ma
  `(created, increased, skipped)`, dochodzi `alreadyReceived`.
  Dzięki znacznikowi ta akcja MOŻE wejść do kolejki offline; bez niego musiałaby
  być offline zablokowana.
- `vite.config.ts` + vite-plugin-pwa: manifest — `name`/`short_name` PL
  („Family Food Planner" / „FFP"), `lang: "pl"`, `display: "standalone"`,
  `theme_color: "#E07A2F"`, `background_color: "#FAF6EF"` (tokens 06_UIUX
  §1), ikony 192/512 + maskable + apple-touch-icon (splash iOS z ikony);
  pliki w `frontend/public/icons/`.
- Workbox (generateSW): precache shella (dist), runtime caching:
  `NetworkFirst` dla `/api/*` (timeout sieci ~3 s → cache), `CacheFirst`
  dla statyków/fontów. `navigateFallback: index.html` z wykluczeniem
  `/api` i `/uploads`.
- `src/lib/offline/db.ts` — wrapper idb: store `list-snapshots`
  (klucz: `list:{id}` lub `public:{token}`, wartość: payload listy +
  `fetched_at`), store `mutation-queue` (klucz auto, wartość:
  `{target, itemId, checked, checked_at, attempts}`).
- `src/stores/offlineQueue.ts` (Pinia — stan UI, zgodnie z ADR-007):
  enqueue przy braku sieci lub błędzie fetch; **deduplikacja per pozycja**
  (nowy wpis nadpisuje starszy dla tej samej pozycji — podwójne odhaczenie
  = jeden PATCH z ostatnim stanem); flush po `window online`, focusie
  i mount; po sukcesie `invalidateQueries` klucza listy.
- Korekta zegara: przy każdej odpowiedzi API klient liczy
  `skew = serverDate − clientNow` (nagłówek `Date`); `checked_at`
  zapisywane do kolejki jako czas klienta + skew.
- `ListaZakupowPage` i `PublicznaListaPage`: hydratacja ze snapshotu, gdy
  fetch pada; checkbox działa zawsze (optimistic → kolejka); komponent
  `OfflineBanner` („Tryb offline — zmiany zapiszą się po odzyskaniu
  zasięgu", licznik oczekujących zmian) w UI listy.
- Wygaśnięcie tokenu w trakcie offline: flush dostaje **410** ⇒ kolejka dla
  tego tokenu czyszczona, snapshot oznaczony jako wygasły, przyjazny ekran
  „Ta lista zakupowa już wygasła lub została usunięta." (04_API §3).

## Security

- Publiczny PATCH pozostaje poza CSRF (autoryzuje token w URL) i pod rate
  limitem 60/min/IP (07_SECURITY §5) — kolejka flushuje sekwencyjnie,
  nie równolegle, żeby nie wpadać w limit.
- Snapshot w IndexedDB zawiera wyłącznie treść listy (label, ilość,
  kategoria, checked) — zero PII, zgodnie z niezmiennikiem 02_DOMAIN §13.5.
- Service worker NIE cache'uje odpowiedzi z `Set-Cookie`; `/api/auth/*`
  wykluczone z runtime cache.
- Token w kluczu idb: akceptowalne (to samo urządzenie co URL); tokenów
  nie logujemy w konsoli ani w raportach błędów.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-FE
- **Recommended**: SKILL-SEC
- **Review**: SKILL-REVIEW

## Tests

- **vitest (kolejka — obowiązkowe scenariusze z ADR-009):**
  1. offline → 3 odhaczenia → online → flush wysyła PATCH-e z `checked_at`,
     kolejka pusta, invalidate wywołany;
  2. podwójne odhaczenie tej samej pozycji offline → jeden PATCH z ostatnim
     stanem (deduplikacja);
  3. konflikt LWW: serwer ma nowszy `checked_at` → odpowiedź serwera
     wygrywa, UI przyjmuje stan serwera;
  4. flush dostaje 410 (token wygasł offline) → kolejka wyczyszczona,
     stan „wygasła" ustawiony;
  5. korekta zegara: klient z zegarem +10 min → `checked_at` po korekcie.
- **vitest (komponenty):** `OfflineBanner` (licznik), hydratacja listy ze
  snapshotu.
- **API (pytest):** PATCH z `checked_at` starszym niż DB → stan bez zmian;
  nowszym → zapis; `checked_at` z przyszłości → przycięte; publiczny PATCH
  z `checked_at` na wygasłym tokenie → 410.
- **Znacznik przyjęcia (D19) — integration + API:**
  1. przyjęcie dwóch odhaczonych pozycji stempluje `received_at` obu;
  2. DRUGIE wywołanie tej samej akcji → 409 „już w spiżarni", spiżarnia BEZ
     zmian (to jest test regresyjny decyzji — sprawdź, że jest czerwony bez
     znacznika);
  3. odhaczenie TRZECIEJ pozycji po przyjęciu → kolejne przyjęcie wchodzi
     i dotyczy WYŁĄCZNIE tej trzeciej („doniosłem dwie rzeczy z torby" —
     przypadek, dla którego odrzucono znacznik na liście);
  4. pozycja `already_have` odhaczona nie dostaje `received_at` (nie jest
     zakupem — ustalenie R3);
  5. odpowiedź publiczna NIE zawiera `received_at` (asercja dokładnego zbioru
     kluczy w `test_public_lists_api.py` musi zostać czerwona, jeśli ktoś to
     pole tam dołoży).
- **E2E (Playwright, `context.setOffline(true)`):** otwórz listę → offline
  → odhacz 2 pozycje (UI reaguje natychmiast, banner widoczny) → online →
  reload → pozycje odhaczone na serwerze. Wariant dla `/l/:token` bez
  logowania. Selektory `data-testid`, bez sleepów (08_TESTING §3).

## Acceptance Criteria

1. Aplikacja instaluje się jako PWA (Chrome/Android: prompt instalacji;
   manifest PL, ikona, standalone, splash) — weryfikacja Lighthouse.
2. Otwarta wcześniej lista zakupowa renderuje się po odcięciu sieci
   (zalogowany i `/l/:token`).
3. Odhaczenia offline są widoczne natychmiast, a po odzyskaniu sieci
   trafiają na serwer bez utraty; podwójne odhaczenie nie dubluje żądań.
4. Konflikt dwóch urządzeń rozstrzyga późniejszy `checked_at` (LWW).
5. UI listy pokazuje wskaźnik offline + liczbę oczekujących zmian.
6. Token wygasły w trakcie offline ⇒ przyjazny ekran 410, kolejka
   wyczyszczona, bez pętli retry.
7. **Przyjęcie zakupów jest idempotentne (D19)**: powtórzone wywołanie —
   także z kolejki offline — nie dubluje ilości w spiżarni, a pozycje odhaczone
   PÓŹNIEJ dają się przyjąć normalnie. Lista pokazuje, co już przyjęte.
8. `task check` + E2E offline zielone; `alembic heads` = jedna głowa po merge'u
   z równoległymi B13/B14.

## Out of Scope

- **Ręczne pozycje listy zakupowej — decyzja D18 (2026-08-22): NIE.** Lista
  jest w całości wynikiem generacji; brakującą rzecz dopisuje się do planu
  i generuje turę ponownie (02_DOMAIN §9.4). Nie dokładać pola „dodaj pozycję"
  ani jako ułatwienia offline — rewizja wymaga nowej decyzji właściciela.
- Offline dla innych widoków niż lista zakupowa (plan/przepisy — FUTURE,
  osobna decyzja po R4).
- WebSockety/realtime (ADR-009: polling przy focusie wystarcza).
- Background Sync API (flush przy powrocie do aplikacji wystarcza — decyzja
  ADR-009; rewizja tylko nowym ADR-em).
- Push notifications — poza zakresem programu.

## Expected files/modules

- `frontend/vite.config.ts` (M), `frontend/package.json` (M — deps:
  `vite-plugin-pwa`, `idb`), `frontend/public/icons/*` (N)
- `frontend/src/lib/offline/db.ts` (N), `frontend/src/lib/offline/sync.ts` (N)
- `frontend/src/stores/offlineQueue.ts` (N)
- `frontend/src/components/domain/OfflineBanner.vue` (N)
- `frontend/src/pages/ListaZakupowPage.vue` (M), `PublicznaListaPage.vue` (M)
- `backend/app/modules/shopping/lists_service.py` (M — LWW + znacznik D19),
  `models.py` (M — `received_at`), `schemas.py` (M), `lists_router.py` (M)
- `backend/migrations/versions/00XX_received_at.py` (N — numer = pierwszy wolny,
  `down_revision` z `task db-heads`)
- `frontend/src/lib/texts.ts` (M — `acceptDone` + stan „przyjęte")
- `frontend/src/lib/offline/*.test.ts`, `backend/tests/api/test_shopping_lww.py`,
  `frontend/e2e/offline-lista.spec.ts` (N)
- `backend/tests/integration/shopping/test_accept_to_pantry.py` (M — scenariusze
  idempotencji z §Tests)
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §6 (M — stan faktyczny),
  `docs/architecture/03_DATABASE_DESIGN.md` §8 (M — kolumna `received_at`)

## Implementation Notes

- **Dev vs build**: service worker testować na buildzie produkcyjnym
  (`task fe-build` + preview) — dev server nie odda realnego precache;
  w dev `devOptions.enabled: false` (unikać zatrutego cache w trakcie pracy).
- Aktualizacja SW: `registerType: "autoUpdate"` + prompt „Dostępna nowa
  wersja — odśwież" zamiast cichej podmiany w trakcie odhaczania.
- `NetworkFirst` dla `/api/*` MUSI mieć krótki `networkTimeoutSeconds`
  (ok. 3 s) — inaczej offline UX to 30 s spinnera.
- Kolejność implementacji: backend LWW najpierw (etap 1) — frontend testuje
  się o realny kontrakt, nie o mock.
- Decyzja pozostawiona implementującemu (z uzasadnieniem w Completion
  notes): czy snapshot odświeżać przy każdym fetchu listy, czy tylko przy
  pełnym sukcesie zapytania.
- iOS Safari: brak wsparcia `beforeinstallprompt` — instrukcja „Dodaj do
  ekranu początkowego" wyświetlana tylko na iOS, nie blokuje AC.

## Cross-Batch Impact

- **Kolizje równoległości (B12 ∥ B13 ∥ B14)**: wspólne pliki to
  `frontend/package.json` + lockfile (wszystkie trzy dodają zależności)
  oraz potencjalnie `src/api/queryKeys.ts`. Zasada z 00_MASTER §5: osobne
  worktree, merge sekwencyjny (kolejność merge'ów ustala właściciel),
  konflikt w package.json rozwiązywany unią zależności; B12 NIE dotyka
  `src/pages/StatystykiPage*` (B13) ani `UstawieniaPage`/`AdminPage` (B14),
  B13/B14 NIE dotykają `vite.config.ts` ani `src/lib/offline/*`.
- **B14 (eksport/import)**: bez wpływu — kolejka offline nie jest
  encją domenową i nie podlega eksportowi.
- **B17 (hardening)**: CSP musi pozostać zgodne z service workerem
  (worker z `'self'`); dopisać do karty B17 punkt weryfikacji SW po
  zaostrzeniu nagłówków.
- **B18 (deployment)**: HTTPS przez reverse proxy jest warunkiem działania
  SW w produkcji — odnotować w karcie B18 (healthcheck: manifest + SW
  serwowane poprawnie przez backend, ADR-014).

## Implementation checklist

- [ ] Backend: `checked_at` w PATCH + LWW + przycinanie przyszłości
- [ ] Testy API LWW zielone
- [ ] Migracja `received_at` (numer = pierwszy wolny, up i down na czystej bazie)
- [ ] `accept_to_pantry` idempotentne + 409 „już w spiżarni"; `received_at`
      w odpowiedzi PRYWATNEJ, NIE w publicznej
- [ ] Pięć scenariuszy znacznika przyjęcia z §Tests (w tym „doniosłem dwie
      rzeczy z torby" i regresja czerwona bez znacznika)
- [ ] Lista pokazuje pozycje już przyjęte; przycisk nieaktywny, gdy nie ma nic
      nowego do przyjęcia
- [ ] 03_DATABASE §8 uzupełnione o `received_at`
- [ ] vite-plugin-pwa: manifest PL, ikony, standalone, splash
- [ ] Workbox: precache shell, NetworkFirst `/api/*` (timeout 3 s),
      CacheFirst statyki, wykluczenia auth/uploads
- [ ] idb: store snapshotów + store kolejki
- [ ] Pinia `offlineQueue`: enqueue, deduplikacja, flush, korekta zegara
- [ ] Snapshot + hydratacja: `ListaZakupowPage` i `PublicznaListaPage`
- [ ] `OfflineBanner` + licznik oczekujących zmian
- [ ] Obsługa 410 (token wygasły offline)
- [ ] vitest: 5 scenariuszy kolejki + komponenty
- [ ] E2E offline (zalogowany + publiczny token)
- [ ] 05_FRONTEND §6 zaktualizowane, PROGRESS.md wpis

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `task test-e2e` zielony, w tym nowe scenariusze offline
- [ ] Lighthouse: PWA installable pass (build produkcyjny)
- [ ] Ręcznie: DevTools offline → odhaczenie → online → stan na serwerze
- [ ] Brak nowych migracji (potwierdzić `alembic heads` = 1 głowa po merge)
- [ ] Acceptance Criteria 1–7 odhaczone z dowodem (test lub zrzut)
- [ ] Dokumentacja i PROGRESS.md zaktualizowane; commit `batch(12): …`

## Completion notes

(wypełnia agent wykonujący)
