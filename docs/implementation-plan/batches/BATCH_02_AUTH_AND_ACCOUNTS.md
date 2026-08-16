# BATCH_02 — AUTH_AND_ACCOUNTS

Klasa: FOUND · Zależności: BATCH_01 · Szacunek rozmiaru: M

## Goal

Po tym batchu aplikacja ma pełne uwierzytelnianie: logowanie/wylogowanie na
sesjach server-side (cookie HttpOnly), ochronę CSRF, rate limit logowania,
role ADMIN/USER i administrację kontami. Pierwszego admina tworzy CLI
`task create-admin`. Frontend dostaje LoginPage z prawdziwą sesją, guard
routera i AppShell z docelową nawigacją (linki do placeholderów).

## Context

Zastaje: szkielet z B01 — app factory (`backend/app/main.py`), core
(`config/db/errors`), pusta migracja bazowa, `frontend/src/api/client.ts`
(bez CSRF), pusty AppShell, `/login` placeholder, targety Taskfile
(`create-admin` jako placeholder do podmiany). Żadnych tabel w DB.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` + PROGRESS.md
  (status B01 i ewentualne korekty w dzienniku).
- `docs/architecture/02_DOMAIN_MODEL.md` §2 (Accounts: User, Session, role).
- `docs/architecture/03_DATABASE_DESIGN.md` §1 (konwencje migracji!),
  §2 (users, sessions — schemat WIĄŻĄCY).
- `docs/architecture/04_API_DESIGN.md` §1 (kształt błędów, konwencje),
  §2 (auth + /admin/users), §3 (zasady autoryzacji).
- `docs/architecture/07_SECURITY_DESIGN.md` §2 (argon2id, sesje, rate
  limit), §3 (CSRF, nagłówki — WIĄŻĄCE wartości), §7–8 (sekrety, logi).
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §1 (authStore = jedyny
  stan sesji w Pinia), §2 (client + CSRF), §3 (routing, guard).
- `docs/architecture/06_UIUX_PRINCIPLES.md` §1 (tokens), §5 (mobile:
  sidebar → bottom-nav).
- `docs/architecture/08_TESTING_STRATEGY.md` §1, §3 (smoke E2E), §4
  (macierz uprawnień — tu wchodzi w części ról).
- ADR-003 (sesje cookie + argon2, bez JWT).

## Stages

1. **DB**: moduł `app/modules/accounts/models.py` (User, Session) +
   migracja (users, sessions wg 03_DATABASE §2 — z `household_id` NULL FK
   dopiero w B03: tu kolumna NIE powstaje; patrz Database). Up/down
   zweryfikowane.
2. **Rdzeń security**: `app/core/security.py` — hash/verify argon2id
   (argon2-cffi, rehash przy weryfikacji gdy parametry wzrosły), generacja
   id sesji i tokenu CSRF (`secrets.token_urlsafe(32)`), porównania
   `hmac.compare_digest`. `app/core/deps.py` — dependency `current_user`
   (cookie → sesja → user, przesuwne `expires_at`), `require_admin`.
3. **Auth API**: router `accounts` — login (weryfikacja hasła, utworzenie
   sesji, set-cookie sesyjne + csrf), logout (delete sesji + czyszczenie
   cookies), `GET /auth/me`. Rate limit slowapi 5/min/IP na login +
   licznik porażek per konto (10 nieudanych → blokada 15 min, komunikat
   neutralny — bez zdradzania czy konto istnieje).
4. **Middleware**: CSRF double-submit (wymagany `X-CSRF-Token` dla
   POST/PUT/PATCH/DELETE poza `/auth/login` i przyszłym `/public/*`)
   + nagłówki bezpieczeństwa z 07_SECURITY §3 (nosniff, Referrer-Policy,
   X-Frame-Options DENY, CSP). Sprzątanie wygasłych sesji przy logowaniu.
5. **CLI**: `task create-admin` → skrypt (np. `python -m app.cli
   create-admin`) pytający interaktywnie o email/hasło (min. 10 znaków)
   lub biorący je z env — nigdy z kodu; idempotentny komunikat gdy email
   zajęty.
6. **Admin CRUD**: `GET/POST /api/v1/admin/users`,
   `GET/PATCH/DELETE /admin/users/{id}` (tworzenie kont, zmiana roli,
   `is_active`, reset hasła; DELETE tylko dezaktywacja lub twarde usunięcie
   konta bez danych — decyzja implementującego, uzasadnić). Ochrona przed
   odebraniem sobie admina/dezaktywacją własnego konta.
7. **Frontend**: `stores/auth.ts` (user z `/auth/me`, akcje login/logout —
   TYLKO stan sesji, zero kopii innych danych serwera), CSRF w
   `api/client.ts` (odczyt cookie `csrf_token` → nagłówek), `LoginPage`
   (vee-validate + zod, komunikaty PL, błąd 401/429 pod formularzem),
   guard routera (brak sesji → `/login`, po zalogowaniu → `/plan-dnia`),
   AppShell: sidebar desktop + bottom-nav mobile (Plan / Przepisy / Zakupy /
   Więcej) wg 06_UIUX §5; pozycje nawigacji: Plan dnia, Tydzień, Przepisy,
   Produkty, Spiżarnia, Zakupy, Statystyki, Ustawienia, Admin (tylko rola
   ADMIN) — linki mogą prowadzić do placeholderów `PlaceholderPage`.
   Strona `/admin/uzytkownicy`: tabela kont + formularz tworzenia +
   akcje (rola, aktywność, reset hasła).
8. **Testy + E2E smoke** (sekcja Tests), aktualizacja docs/PROGRESS,
   commit `batch(02): ...`.

## Database / migrations

Wg 03_DATABASE §2 (WIĄŻĄCE):

- `users`: id BIGINT identity PK, email UNIQUE, password_hash,
  display_name, role ENUM(admin,user), is_active BOOL,
  ui_settings JSONB DEFAULT '{}', created_at/updated_at timestamptz.
  **Bez `household_id`** — tę kolumnę dodaje migracja B03 razem z tabelą
  `households` (nie tworzymy FK do nieistniejącej tabeli).
- `sessions`: id UUID PK, user_id FK→users ON DELETE CASCADE, expires_at,
  created_at, ip, user_agent. Indeks na `expires_at` (sprzątanie) i
  `user_id`.
- Migracja: numer = pierwszy wolny w `migrations/versions/`,
  `down_revision` = `alembic heads`; `upgrade head` + `downgrade -1` +
  `upgrade head` przechodzi na kopii bazy dev.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/auth/login` | POST | publiczny | email+hasło → sesja; rate limit 5/min/IP; 401 neutralne |
| `/api/v1/auth/logout` | POST | zalogowany | usuwa sesję, czyści cookies |
| `/api/v1/auth/me` | GET | zalogowany | user (id, email, display_name, role, ui_settings) |
| `/api/v1/admin/users` | GET, POST | ADMIN | lista (paginacja `limit/offset`, `?q=`), tworzenie konta |
| `/api/v1/admin/users/{id}` | GET, PATCH, DELETE | ADMIN | szczegóły, edycja (rola/aktywność/hasło), usunięcie/dezaktywacja |

- Warstwy: `router.py` → `service.py` → `models.py`; router nie dotyka
  sesji DB (01_ARCHITECTURE §2).
- Walidacje: email poprawny i unikalny (409 conflict), hasło ≥10 znaków
  (422), rola z enuma. Błędy w kształcie 04_API §1.
- `/auth/me` zwraca też pole `household` = null (kontrakt na B03 — pole
  istnieje od razu, żeby FE nie łamał typów przy B03).

## Frontend

- `src/stores/auth.ts` — jedyny stan sesji; inicjalizacja przy starcie
  aplikacji (`/auth/me` → user | null). Bez persystencji do localStorage
  (cookie wystarcza).
- `src/pages/LoginPage.vue` — formularz wg tokens, obsługa 401
  („Nieprawidłowy email lub hasło") i 429 („Zbyt wiele prób…").
- `src/pages/admin/AdminUsersPage.vue` pod trasą `/admin/uzytkownicy`
  (route guard: rola ADMIN, inaczej 404/redirect).
- `AppShell.vue`: sidebar (desktop) / bottom-nav (mobile ≥44 px celów
  dotykowych); wpis „Admin" widoczny tylko dla ADMIN; menu użytkownika
  z akcją „Wyloguj".
- `PlaceholderPage.vue` — jeden komponent wielokrotnego użytku
  („Ta sekcja powstanie w kolejnych etapach") dla tras: /plan-dnia,
  /tydzien, /przepisy, /produkty, /spizarnia, /zakupy, /statystyki,
  /ustawienia.
- Mutacje logowania/wylogowania przez TanStack Query mutation +
  invalidacja; typy z `generated.ts` (odśwież `task fe-types`).

## Security

Ten batch JEST warstwą bezpieczeństwa aplikacji:

- Hasła: argon2id, parametry domyślne biblioteki, rehash przy logowaniu;
  min. długość 10 (07 §2).
- Sesja: `secrets.token_urlsafe(32)` jako id (kolumna UUID → patrz Notes),
  cookie `HttpOnly; Secure; SameSite=Lax; Path=/`, TTL 30 dni przesuwne,
  logout = DELETE wiersza (natychmiastowe odwołanie).
- CSRF: cookie `csrf_token` (nie-HttpOnly) + nagłówek `X-CSRF-Token`,
  porównanie `hmac.compare_digest`; login wyłączony z CSRF (nie ma jeszcze
  sesji), chroniony rate limitem.
- Rate limit: slowapi 5/min/IP na `/auth/login`; blokada konta po 10
  porażkach na 15 min — komunikat identyczny jak przy złym haśle
  (bez enumeracji kont).
- Nagłówki (middleware, 07 §3): `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`,
  `CSP: default-src 'self'; img-src 'self' data: blob:; style-src 'self'
  'unsafe-inline'`.
- Logi: nigdy hasło/id sesji/token; user id zamiast emaila (07 §8).
- Brak samorejestracji; konta tworzy wyłącznie ADMIN.

## Tests

- **Unit**: hash/verify argon2 (+ rehash), generacja/porównanie CSRF,
  logika blokady konta (czyste funkcje licznika porażek).
- **Integration**: tworzenie/wygaszanie sesji (TTL przesuwny), kaskada
  users→sessions, sprzątanie wygasłych sesji, unikalność email.
- **API** (pełny zakres 08_TESTING):
  - login OK → set-cookie sesyjne + csrf; złe hasło → 401 neutralne;
    konto nieaktywne → 401;
  - `me` bez cookie → 401; z cookie → 200; po logout → 401 (sesja
    unieważniona natychmiast);
  - CSRF: mutacja bez nagłówka → 403, ze złym → 403, z poprawnym → 2xx;
  - rate limit: 6. próba w minucie → 429; 10 porażek → blokada 15 min
    (429/401 wg implementacji, komunikat neutralny);
  - macierz ról: `/admin/users` dla anonima → 401, USER → 403, ADMIN → 200;
  - admin nie może dezaktywować/zdegradować samego siebie → 409/422;
  - nagłówki bezpieczeństwa obecne w odpowiedzi.
- **Frontend (vitest)**: authStore (login/logout/me), guard routera
  (redirect na /login), client dokleja X-CSRF-Token.
- **E2E smoke (Playwright)**: create-admin (seed przez CLI/API) → login →
  widok /plan-dnia (placeholder) → logout → redirect /login. Selektory
  `data-testid`, bez sleepów.

## Acceptance Criteria

1. `task create-admin` tworzy pierwszego admina bez żadnego hasła w repo;
   ponowne wywołanie z tym samym emailem kończy się czytelnym komunikatem.
2. Login przez UI działa; cookie sesyjne jest HttpOnly (weryfikacja w
   devtools), csrf_token czytelny dla JS.
3. Wylogowanie unieważnia sesję server-side (stare cookie → 401).
4. 6. próba logowania w ciągu minuty z jednego IP → 429; po 10 nieudanych
   próbach na konto — blokada 15 min z komunikatem neutralnym.
5. Mutacja bez nagłówka CSRF → 403 (sprawdzone testem API).
6. ADMIN zarządza kontami na `/admin/uzytkownicy`; USER nie widzi wpisu
   Admin w nawigacji i dostaje 403 na `/api/v1/admin/*`.
7. AppShell pokazuje pełną nawigację (9 pozycji), placeholdery klikalne,
   bottom-nav na mobile.
8. E2E smoke login→plan-dnia→logout zielony; `task check` zielony.

## Out of Scope

- Households, `users.household_id`, scope → BATCH_03.
- Profile członków rodziny i ustawienia rodziny → BATCH_03.
- `user_nutrition_goals` → BATCH_06 (mimo że w 03_DATABASE §2).
- Progi wskaźników w `ui_settings` (edycja) → BATCH_06; kolumna już jest.
- Rate limit endpointów publicznych `/public/*` → BATCH_11.
- 2FA, samorejestracja, odzyskiwanie hasła emailem — nie istnieją (01 §6).

## Expected files/modules

- `backend/app/modules/accounts/{models,schemas,service,router}.py`
- `backend/app/core/{security,deps}.py`; rozszerzenia `app/main.py`
  (middleware CSRF + nagłówki, slowapi limiter)
- `backend/app/cli.py` (create-admin) + podmiana targetu w `Taskfile.yml`
- `backend/migrations/versions/<pierwszy-wolny>_users_sessions.py`
- `backend/tests/{unit,integration,api}/test_auth*`, `tests/factories.py`
  (UserFactory)
- `frontend/src/stores/auth.ts`, `src/pages/LoginPage.vue`,
  `src/pages/admin/AdminUsersPage.vue`, `src/pages/PlaceholderPage.vue`,
  `src/AppShell.vue` (nawigacja), `src/router.ts` (guardy, trasy),
  `src/api/client.ts` (CSRF), `src/api/generated.ts` (regeneracja)
- `frontend/e2e/smoke.spec.ts`
- `docs/implementation-plan/PROGRESS.md`

## Implementation Notes

- ROZSTRZYGNIĘTE na etapie planu (2026-08-16): `sessions.id` = TEXT
  z `secrets.token_urlsafe(32)` (256 bitów), spójnie z 07_SECURITY §2;
  03_DATABASE §2 zaktualizowane. Nie używać UUID.
- Blokada konta: licznik porażek przechowywany w DB (kolumny na users lub
  osobna tabelka) — nie w pamięci procesu (restart nie może zerować
  blokady). Decyzja implementującego, uzasadnić.
- `Secure` cookie w dev na http://localhost — sterować flagą z configu
  (`APP_ENV`), w prod zawsze Secure; test API sprawdza wariant prod.
- slowapi wymaga wpięcia limitera do app state + handlera 429 w kształcie
  błędu 04_API §1.
- CSP z 07 §3 przepisać dosłownie — bez „ulepszania".
- Kolejność frontendu: client CSRF → authStore → guard → LoginPage →
  AppShell → admin page. E2E na końcu, na compose.

## Cross-Batch Impact

- **B03**: dodaje `users.household_id` + rozszerza `/auth/me` o realny
  `household`; przejmuje AdminPage (sekcja rodzin obok użytkowników).
- **B03+ każdy**: `current_user`/`require_admin` z `core/deps.py` to
  jedyne wejście autoryzacji; nowe moduły ich używają, nie duplikują.
- **B04**: nawigacja „Produkty" przestaje być placeholderem.
- **B06**: edycja progów wskaźników w `ui_settings` (kolumna gotowa).
- **B11**: wyjątek CSRF dla `/public/*` już przewidziany w middleware —
  zaimplementować jako lista prefiksów, nie hardcode jednej ścieżki.
- **B17**: parametry argon2/TTL sesji do przeglądu hardeningowego.
- Po zakończeniu: uzupełnić karty B03/B04 o faktyczne ścieżki plików
  (deps, middleware), jeśli różnią się od założeń.

## Implementation checklist

- [ ] Modele User+Session + migracja (up/down zweryfikowane)
- [ ] core/security: argon2id, tokeny, compare_digest
- [ ] core/deps: current_user (TTL przesuwny), require_admin
- [ ] /auth/login, /auth/logout, /auth/me
- [ ] Rate limit 5/min/IP + blokada konta po 10 porażkach / 15 min
- [ ] Middleware CSRF double-submit + nagłówki bezpieczeństwa (07 §3)
- [ ] CLI create-admin (Taskfile podmieniony, zero haseł w repo)
- [ ] /admin/users CRUD + ochrona własnego konta admina
- [ ] FE: client CSRF, authStore, guard, LoginPage, AppShell z nawigacją,
      PlaceholderPage, /admin/uzytkownicy
- [ ] task fe-types zregenerowany
- [ ] Testy unit/int/api/fe + E2E smoke
- [ ] PROGRESS.md + korekta 03_DATABASE (id sesji) jeśli dotyczy

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] Migracja: `alembic heads` = 1; upgrade → downgrade → upgrade OK
- [ ] E2E smoke login→plan-dnia→logout zielony na compose
- [ ] Macierz ról (anonim/USER/ADMIN) pokryta testami API — realne wyniki
- [ ] Nagłówki bezpieczeństwa i CSRF sprawdzone testem, nie ręcznie
- [ ] `git ls-files`: żadnych haseł/sekretów
- [ ] Acceptance Criteria 1–8 potwierdzone
- [ ] Living docs zaktualizowane; commit `batch(02): ...`, status czysty

## Completion notes

(wypełnia agent wykonujący)
