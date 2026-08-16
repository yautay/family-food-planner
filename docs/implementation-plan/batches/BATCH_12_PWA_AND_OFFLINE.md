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
- Backend: `backend/app/modules/shopping/` — `router.py` z
  `PATCH /shopping/lists/{id}/items/{item_id}` (check/already-have) oraz
  publiczny `PATCH /public/lists/{token}` (rate limit, 410 po expiry);
  kolumny `checked`, `checked_at` w `shopping_list_items` już istnieją.
- `shopping_list_items.label` — tekst pozycji renderowalny offline
  (03_DATABASE §8, celowo zdenormalizowany).

Wymagane lektury: **ADR-009** (całość — kontrakt tego batcha),
05_FRONTEND §6 (PWA i offline), §1 (Pinia = kolejka offline), 06_UIUX §5
(mobile, lista krytyczna), 04_API §2 (`/public/lists/{token}`),
07_SECURITY §5 (tokeny publiczne), 08_TESTING §2.9–§3.

## Stages

1. **Backend LWW** — `PATCH` checkboxa przyjmuje opcjonalne `checked_at`
   klienta; serwis stosuje last-write-wins per pozycja; testy API zielone.
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

**Brak nowych migracji.** Schemat wystarcza: `shopping_list_items.checked`,
`checked_at timestamptz` (03_DATABASE §8). Jeśli w trakcie okaże się
potrzebna kolumna — STOP i wpis do 02_DECISIONS (nie zgadywać), bo B13/B14
mogą równolegle dodawać migracje (po merge'u `alembic heads` = jedna głowa).

## Backend

Zmiany minimalne, wyłącznie w module `shopping`:

| Ścieżka | Metoda | Rola | Zmiana |
|---|---|---|---|
| `/api/v1/shopping/lists/{id}/items/{item_id}` | PATCH | U | body przyjmuje opcjonalne `checked_at` (ISO8601 UTC); LWW |
| `/api/v1/public/lists/{token}` | PATCH | P | jw. dla pozycji publicznych; 410 po expiry/revoke bez zmian |

Logika LWW w `shopping/service.py`: jeżeli przysłane `checked_at` jest
**starsze** niż zapisane w DB — mutacja ignorowana (odpowiedź 200 ze stanem
aktualnym; klient przyjmuje stan serwera). Brak `checked_at` w body =
zachowanie dotychczasowe (natychmiastowe, `now()` serwera) — kompatybilność
z odhaczaniem online. Walidacja: `checked_at` z przyszłości > 5 min ⇒
przycinane do `now()` serwera (ochrona przed rozjechanym zegarem klienta).

## Frontend

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
7. `task check` + E2E offline zielone.

## Out of Scope

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
- `backend/app/modules/shopping/service.py` (M — LWW), `schemas.py` (M),
  `router.py` (M — pole `checked_at`)
- `frontend/src/lib/offline/*.test.ts`, `backend/tests/api/test_shopping_lww.py`,
  `frontend/e2e/offline-lista.spec.ts` (N)
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §6 (M — stan faktyczny)

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
