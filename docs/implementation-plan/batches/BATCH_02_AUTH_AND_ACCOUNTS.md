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

Konkrety z wykonanego B01 (2026-08-16) — czytaj przed pisaniem kodu:

- **DB jest async** (ADR-015): `AsyncSession`, dependency
  `app.core.db.get_session`, driver `postgresql+psycopg://`. Serwisy
  `async def`, `await session.execute(...)`. Na Windows narzędzia hosta
  wymuszają SelectorEventLoop (jest w `db.py` i `tests/conftest.py`).
- **Nie ma `app` na poziomie modułu** — uruchomienie przez
  `uvicorn app.main:create_app --factory`; router modułu rejestruje się
  w `create_app()`. Prefiks: `API_V1_PREFIX = "/api/v1"`.
- **Błędy**: rzucaj `AppError`/`NotFoundError`/`ForbiddenError`/
  `UnauthorizedError`/`ConflictError` z `app/core/errors.py`, nigdy
  `HTTPException`. Handler 429 dla slowapi dopisz do
  `register_error_handlers` (kod `rate_limited` już jest w mapie).
- **Testy**: każdy plik testowy deklaruje `pytestmark` (`unit`/`integration`
  /`api`) — bez markera nie trafi do żadnego targetu. Fixture'y `app`,
  `client`, `settings`, `test_database_url` są w `tests/conftest.py`.
- **Migracja**: `task db-revision -- --rev-id 0002 -m "accounts"`,
  `down_revision = "0001"` (potwierdź `task db-heads`).
- **Frontend**: klient to `apiFetch`/`ApiError` w `src/api/client.ts`
  (miejsce na nagłówek CSRF oznaczone komentarzem); alias `@/`;
  AppShell w `src/layouts/AppShell.vue`; ikony z `@lucide/vue`;
  `vee-validate`/`zod` NIE są jeszcze zainstalowane — dołóż je w B02.
- **Sekrety w dev**: `.env` powstaje z `.env.example`; nowa zmienna =
  wpis w `.env.example` w tym samym commicie.

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
- `sessions`: id TEXT PK (`secrets.token_urlsafe(32)` — 03 §2), user_id
  FK→users ON DELETE CASCADE, expires_at,
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
- Sesja: `secrets.token_urlsafe(32)` jako id (kolumna TEXT),
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

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-SEC
- **Recommended**: SKILL-FE
- **Review**: SKILL-REVIEW, SKILL-SECREV

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

- [x] Modele User+Session + migracja (up/down zweryfikowane)
- [x] core/security: argon2id, tokeny, compare_digest
- [x] core/deps: current_user (TTL przesuwny), require_admin
- [x] /auth/login, /auth/logout, /auth/me
- [x] Rate limit 5/min/IP + blokada konta po 10 porażkach / 15 min
- [x] Middleware CSRF double-submit + nagłówki bezpieczeństwa (07 §3)
- [x] CLI create-admin (Taskfile podmieniony, zero haseł w repo)
- [x] /admin/users CRUD + ochrona własnego konta admina
- [x] FE: client CSRF, authStore, guard, LoginPage, AppShell z nawigacją,
      PlaceholderPage, /admin/uzytkownicy
- [x] task fe-types zregenerowany
- [x] Testy unit/int/api/fe + E2E smoke
- [x] PROGRESS.md + korekta 03_DATABASE (kolumny blokady, indeksy sesji)

## Verification checklist

- [x] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [x] Migracja: `alembic heads` = 1; upgrade → downgrade → upgrade OK
- [x] E2E smoke login→plan-dnia→logout zielony na compose
- [x] Macierz ról (anonim/USER/ADMIN) pokryta testami API — realne wyniki
- [x] Nagłówki bezpieczeństwa i CSRF sprawdzone testem, nie ręcznie
- [x] `git ls-files`: żadnych haseł/sekretów
- [x] Acceptance Criteria 1–8 potwierdzone
- [x] Living docs zaktualizowane; commit `batch(02): ...`, status czysty

## Completion notes

**Wykonane** (2026-08-16)

Backend: `app/core/{security,deps,cookies,middleware}.py`, moduł
`app/modules/accounts/{models,schemas,service,router}.py`, `app/cli.py`,
migracja `0002_users_sessions`, rejestr modeli `app/models.py`,
`TimestampMixin` w `core/db.py`, handler 429 w `core/errors.py`, limiter
slowapi + middleware w `create_app()`. Frontend: CSRF i handler 401
w `api/client.ts`, `api/{auth,adminUsers}.ts`, `stores/auth.ts`,
`router.ts` z guardem, `LoginPage`, `PlaceholderPage`, `AdminUsersPage`,
AppShell (sidebar + bottom-nav), `lib/{navigation,texts}.ts`.
Testy: 54 unit / 18 int / 55 api / 39 vitest / 4 E2E — wszystkie zielone,
`task check` zielony.

**Decyzje implementacyjne (uzasadnione)**

1. **Blokada konta w kolumnach `users.failed_login_count` i
   `users.locked_until`** (nie osobna tabela): jeden wiersz na konto, brak
   przyrostu danych, stan przeżywa restart procesu — wymóg z karty. Logika
   liczników to czyste funkcje w `core/security.py` (testy unit).
2. **`DELETE /admin/users/{id}` = twarde usunięcie, ale tylko konta bez
   danych.** Sesje giną kaskadą; przy FK RESTRICT z modułów domenowych
   (od B03) `IntegrityError` mapowany na 409 z komunikatem „dezaktywuj
   zamiast usuwać". Zgodne z ADR-012 (fizyczne usunięcie tylko dla encji
   nieużywanych) i nie zostawia w bazie kont-widm. Dezaktywacja pozostaje
   przez PATCH `is_active`.
3. **Nazwy cookies**: `pasnik_session` (HttpOnly) + `csrf_token` (dla JS).
   Prefiks `pasnik_` chroni przed kolizją z innymi aplikacjami na localhost
   w dev.
4. **`sessions` bez `updated_at`** — 03_DATABASE §2 wylicza kolumny tej
   tabeli wprost; rolę znacznika ostatniego użycia pełni przesuwane
   `expires_at`. Kolumny blokady i indeksy dopisane do §2 (living docs).
5. **`email` w schematach ODPOWIEDZI jako `str`, nie `EmailStr`**
   (walidacja `EmailStr` zostaje na wejściu). Wykryte na realnym stacku:
   konto zapisane wcześniej, którego domenę `email-validator` odrzuca
   (np. `.test`), wysadzało ODCZYT listy kont błędem 500. Test regresyjny:
   `test_lista_nie_wywraca_sie_na_nietypowym_emailu`.
6. **CLI waliduje email tym samym `EmailStr` co API** — inaczej dało się
   założyć konto, którym nie da się zalogować (dokładnie to się wydarzyło
   przy pierwszym uruchomieniu E2E).
7. **CSP nie jest wysyłane dla `/api/docs` i `/api/openapi.json`**
   (Swagger UI ładuje skrypty z CDN). W prod te ścieżki nie istnieją, więc
   wyjątek jest tam martwy. Odnotowane w 07_SECURITY §3.
8. **Limiter slowapi tworzony per aplikacja** w `create_app()` i przekazany
   do buildera routera — każda instancja ma własny licznik, więc testy się
   nie zatruwają, a produkcja działa tak samo (jeden proces = jeden limiter).

**Odstępstwa od karty**

- Karta zakładała `_set_session_cookies` w routerze; helpery wylądowały
  w `app/core/cookies.py`, bo używa ich też `core/deps.py` (patrz niżej).
- Test „405 dla niedozwolonej metody" w `tests/api/test_health.py` musiał
  zmienić cel z `POST /health` na `GET /auth/login`: middleware CSRF działa
  PRZED routingiem, więc POST bez tokenu daje 403, nie 405. Zachowanie jest
  pożądane (nie zdradza istnienia tras) i ma własny test.
- `frontend/e2e/login.spec.ts` (B01) zastąpiony przez `e2e/smoke.spec.ts` —
  stary test asercjonował, że przycisk logowania jest WYŁĄCZONY.
- `e2e/**/*.ts` przeniesione z projektu TS „app" do „node"
  (`tsconfig.node.json`) — testy E2E używają `process.env`.
- Katalog `tests/` stał się pakietem (`__init__.py`), bo `tests.factories`
  i `tests.helpers` importowane z dwóch poziomów mylą mypy.

**Ustalenia review**

- `/security-review`: brak ustaleń o pewności ≥ 8/10. Sprawdzone: cykl
  życia sesji, dopasowanie prefiksów CSRF, macierz ról, enumeracja kont,
  wyciek tokenu CSRF na froncie, parametr `next` w LoginPage.
- `/code-review` (high): **1 błąd naprawiony w tym batchu** — przesuwne TTL
  działało tylko po stronie serwera; cookie zachowywało `Max-Age`
  z logowania, więc przeglądarka kasowała sesję 30 dni po zalogowaniu mimo
  aktywności. Naprawa: `resolve_session` zwraca flagę `refreshed`,
  `get_current_user` ponownie wysyła oba cookies z nowym `Max-Age`
  (testy `test_przesuniecie_ttl_odswieza_takze_cookies` i
  `test_swieza_sesja_nie_odswieza_cookies`). Drugie ustalenie (IP za proxy)
  przeniesione do follow-upów — nie da się go domknąć bez konfiguracji
  reverse proxy z B18.

**Follow-upy (poza zakresem tego batcha)**

1. **IP za reverse proxy (B17/B18)**: `get_remote_address` slowapi
   i `sessions.ip` widzą adres bezpośredniego połączenia. Po wdrożeniu za
   nginx limit 5/min/IP na `/auth/login` stanie się limitem globalnym.
   Wymaga `--proxy-headers` + `forwarded-allow-ips`. Wpisane do karty B17.
2. **Wolumen `node_modules` w compose dev nie odświeża się** — serwis
   `frontend` uruchamia `[ -d node_modules/vite ] || npm ci`, więc nowa
   zależność frontendu wymaga ręcznego
   `docker compose ... exec frontend npm ci` + restartu. Trafiło na to
   pierwsze uruchomienie E2E. Do rozważenia w review R1 (poprawka jednej
   linii w `docker/compose.dev.yml`) — świadomie NIE dotykane tutaj.
3. Formularz tworzenia konta na `/admin/uzytkownicy` zakłada zawsze rolę
   USER; nadanie roli ADMIN to osobna akcja na liście. Wystarczające dla
   zakresu karty; ewentualny selektor roli w formularzu — przy B03.
4. **Skille `pasnik-security` i `pasnik-backend` mają nieaktualne nagłówki**
   („do dostarczenia: sesje/CSRF/rate limit (B02) … nagłówki i CSP (B17)"
   — już są; `argon2-cffi`/`slowapi` są w `pyproject`). Świadomie NIE
   aktualizowane tutaj: właścicielem aktualizacji skilli są batche review
   (03_AI_SKILLS §8) — do zrobienia w R1.

**Pytania do właściciela**: brak. Żaden wpis w `02_DECISIONS.md` nie był
potrzebny.
