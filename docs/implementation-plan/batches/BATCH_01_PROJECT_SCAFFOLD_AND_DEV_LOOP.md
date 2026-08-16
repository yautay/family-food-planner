# BATCH_01 — PROJECT_SCAFFOLD_AND_DEV_LOOP

Klasa: FOUND · Zależności: brak · Szacunek rozmiaru: M

## Goal

Po tym batchu repozytorium ma kompletny szkielet monorepo (backend FastAPI +
frontend Vue 3) z działającą pętlą deweloperską: `docker compose` podnosi
aplikację z hot-reloadem i PostgreSQL, `task check` przechodzi na zielono,
`/api/v1/health` odpowiada. Powstaje też kontrakt jakości dla wszystkich
kolejnych sesji: `CLAUDE.md`, uzgodnione project skille ffp-* i generowanie
typów TS z OpenAPI. Zero logiki domenowej — wyłącznie fundament.

## Context

Repozytorium zawiera dziś TYLKO `docs/` i `data/` — żadnego kodu. Ten batch
tworzy całą strukturę z 01_ARCHITECTURE §2 od zera. Brak zależnych batchy,
brak decyzji-bramek.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` — procedura sesji.
- `docs/architecture/01_ARCHITECTURE_OVERVIEW.md` §2 (struktura repo —
  WIĄŻĄCA), §3 (stack twardy), §5 (production-readiness od B01).
- `docs/architecture/04_API_DESIGN.md` §1 (konwencje, kształt błędu), mapa:
  `GET /health` bez auth.
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §1–2, §7 (podział
  Query/Pinia, warstwa API, konwencje jakości).
- `docs/architecture/06_UIUX_PRINCIPLES.md` §1 (tokens Tailwind — wdrażane tu).
- `docs/architecture/07_SECURITY_DESIGN.md` §7 (sekrety wyłącznie env).
- `docs/architecture/08_TESTING_STRATEGY.md` §1 (piramida, definicja
  `task check`).
- `docs/implementation-plan/03_AI_SKILLS.md` — manifest systemu skilli
  (hierarchia, matryca, polityka aktualizacji); ten batch uzgadnia
  istniejące skille ffp-* z rzeczywistym kodem.
- ADR-001 (modularny monolit), ADR-002 (bind mounts), ADR-007 (frontend
  stack), ADR-014 (backend serwuje SPA — w dev odroczony, patrz Notes).

## Stages

1. **Szkielet backendu**: `backend/pyproject.toml` (uv; Python 3.13, FastAPI,
   SQLAlchemy 2.0, Alembic, Pydantic v2, pydantic-settings, structlog,
   Uvicorn; dev: pytest, httpx, ruff, mypy). `app/core/config.py`
   (pydantic-settings: `DATABASE_URL`, `SECRET_KEY`, `APP_ENV`, `APP_VERSION`),
   `app/core/db.py` (engine + session factory), `app/core/errors.py`
   (kształt błędu 04_API §1 + handlery), `app/main.py` (app factory
   `create_app()`, konfiguracja structlog, router `/api/v1/health`).
   Weryfikacja: `uv run uvicorn app.main:app` + curl health lokalnie.
2. **Alembic**: `backend/migrations/` zainicjalizowany (env.py czyta
   `DATABASE_URL` z configu), migracja bazowa `0001` PUSTA (bez tabel) —
   ustala łańcuch rewizji. Weryfikacja: `alembic heads` = jedna głowa,
   `upgrade head` + `downgrade base` przechodzą.
3. **Szkielet frontendu**: Vite + Vue 3 + TypeScript strict (`vue-tsc`),
   Tailwind CSS 4 z tokens z 06_UIUX §1 (`--background #FAF6EF`,
   `--card #FFFFFF`, `--primary #E07A2F`, hover `#C96A26`, wtórny `#3F7A5E`,
   ostrzeżenie `#D9A441`, błąd `#C24C3B`, tekst `#2B2620`/`#6F675C`,
   obramowania `#EDE5D8`, rounded-xl/lg, Inter, tabular-nums), init
   shadcn-vue (button, card, input jako próba działania), Pinia, TanStack
   Query, vue-router z `AppShell.vue` (pusty layout) i stroną `/login`
   (placeholder bez logiki), `src/api/client.ts` (fetch wrapper wg 05 §2 —
   credentials include, mapowanie `ApiError`; CSRF header dopisze B02).
   vite-plugin-pwa: manifest minimalny (nazwa PL, ikony placeholder,
   standalone) — BEZ logiki offline. Dev proxy `/api` → backend.
4. **Docker**: `docker/Dockerfile` (multi-stage, na razie target dev),
   `docker/compose.dev.yml`: `app` (uvicorn --reload, bind mount kodu),
   `frontend` (vite dev server) lub app+vite wg uznania (uzasadnić w Notes),
   `db` (postgres:17, wolumen dev), `db-test` (postgres:17, `tmpfs` na
   danych — baza testów integracyjnych). Healthcheck `db` przez `pg_isready`.
5. **Taskfile.yml**: targety `dev` (compose up), `check` (test-unit +
   test-int + test-api + fe-test + typecheck + lint + format-check +
   kontrola „`alembic heads` = dokładnie 1"), `test-unit`,
   `test-int`, `test-api`, `fe-test`, `typecheck` (mypy + vue-tsc), `lint`
   (ruff + eslint), `format` / `format-check` (ruff format + prettier —
   wiele sesji AI wymaga formattera, inaczej diffy toną w szumie),
   `audit` (pip-audit + npm audit — używane w Review batchach i B17),
   `secrets-scan` (gitleaks przez docker run — j.w.),
   `fe-types` (eksport OpenAPI z app factory → generator
   typów TS → `frontend/src/api/generated.ts`), `db-migrate`,
   `create-admin` (placeholder z komunikatem „dostarcza BATCH_02"),
   `db-seed-demo` (placeholder — dostarczają batche domenowe), `help`.
6. **Higiena repo**: `.env.example` (wszystkie zmienne z placeholderami),
   `.gitignore` (`.env`, `node_modules/`, `dist/`, `__pycache__/`, `.venv/`,
   `uploads/` lokalne, artefakty testów), `.editorconfig`.
7. **Kontrakt AI**: `CLAUDE.md` (root) — komendy task, wzorzec modułu
   router→service→models, ZAKAZY: float w ilościach (tylko Decimal/NUMERIC/
   stringi dziesiętne), kopiowanie stanu serwera do Pinia, endpoint bez
   testu scope/uprawnień, i18n; wskaźnik na
   `docs/implementation-plan/implementation_prompt.md`. Project skille
   JUŻ ISTNIEJĄ jako artefakty blueprintu (2026-08-16):
   `.claude/skills/ffp-{backend,frontend,domain-calc,security}/SKILL.md`.
   Zadanie tego batcha: UZGODNIĆ je z rzeczywistym kodem (nazwy tasków,
   ścieżki, wersje w nagłówku `stack:`), zaktualizować datę `verified:`
   i usunąć rozjazdy — nie tworzyć od zera. Przy zmianach strukturalnych
   użyć skilla `skill-creator`.
8. **Testy i domknięcie**: test API health, smoke test app factory, test
   frontendowy (vitest — render AppShell), config pytest (markery unit/int/
   api, fixture DB na `db-test`). `task check` zielony. Aktualizacja
   PROGRESS.md, commit `batch(01): ...`.

## Database / migrations

- Żadnych tabel w tym batchu. Migracja bazowa `0001_initial` jest pusta
  (upgrade/downgrade = pass) — istnieje po to, by każdy kolejny batch miał
  jednoznaczny `down_revision` i by pipeline migracji był przetestowany
  zanim pojawi się schemat.
- Konwencje na przyszłość skonfigurowane od razu (03_DATABASE §1):
  `alembic.ini` + `env.py` z naming convention SQLAlchemy (spójne nazwy
  constraintów — warunek czystych downgrade'ów), timestamptz UTC.
- Reguła numeracji (03_DATABASE §1): numer pliku = pierwszy wolny,
  `down_revision` = wynik `alembic heads`, nigdy numer z planu.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/health` | GET | publiczny (bez auth) | `{"status": "ok", "version": "<APP_VERSION>"}` |

- `create_app()` w `app/main.py` — composition root: middleware (na razie
  tylko logowanie requestów structlog: request id, ścieżka, status, czas —
  wg 07_SECURITY §8, bez danych wrażliwych), rejestracja routerów,
  handlery błędów mapujące wyjątki na kształt `{"error": {code, message,
  details}}` (04_API §1).
- `app/core/config.py` — jedyne źródło konfiguracji; brak jakiejkolwiek
  wartości zaszytej w kodzie, która różni dev od prod.
- Katalogi przyszłych modułów (`app/modules/...`) NIE powstają na zapas —
  tworzy je batch, który je zasiedla (pusty katalog to szum).

## Frontend

- `frontend/` wg 01_ARCHITECTURE §2: `src/api/` (client.ts, queryKeys.ts —
  pusty obiekt startowy, generated.ts z fe-types), `src/components/ui/`
  (shadcn-vue), `src/pages/` (`LoginPage.vue` placeholder), `src/stores/`
  (pusty — authStore dostarczy B02), `src/lib/`.
- Router: `/login` → LoginPage; `/` → AppShell (pusty layout z napisem
  placeholder). Guardy auth dostarczy B02.
- Tailwind theme = tokens z 06_UIUX §1 zdefiniowane jako CSS variables +
  mapowanie do theme; to JEDYNE miejsce definicji kolorów.
- vite-plugin-pwa: `registerType: 'autoUpdate'`, manifest PL, bez strategii
  cache dla `/api` (offline w B12).
- `task fe-types`: skrypt eksportujący `app.openapi()` do JSON + generator
  (np. `openapi-typescript`) → `src/api/generated.ts`; plik generowany
  commitowany (świeża sesja nie musi mieć backendu wstanego, żeby
  typować frontend).

## Security

- Sekrety wyłącznie przez env (pydantic-settings); `.env` w `.gitignore`
  od PIERWSZEGO commita, `.env.example` bez realnych wartości (07 §7).
- `create-admin` jako CLI-placeholder — już teraz ZERO seedów haseł w repo.
- Health endpoint nie ujawnia niczego poza `status` i `version`.
- Logi bez haseł/tokenów/payloadów (07 §8) — konfiguracja structlog od dziś.
- Port PG nie wystawiony poza sieć compose (07 §9); hasło DB z env.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE
- **Recommended**: SKILL-CREATOR
- **Review**: SKILL-REVIEW

## Tests

- **API** (`task test-api`): `GET /api/v1/health` → 200, body zawiera
  `status == "ok"` i niepusty `version`; nieistniejąca ścieżka
  `/api/v1/nope` → 404 w kształcie błędu z 04_API §1.
- **Unit** (`task test-unit`): `create_app()` zwraca aplikację z
  zarejestrowanym routerem health (smoke); config czyta zmienne env
  i wybucha czytelnie przy braku wymaganych.
- **Integration** (`task test-int`): połączenie z `db-test`, `alembic
  upgrade head` + `downgrade base` + `upgrade head` na czystej bazie
  przechodzi (test infrastruktury migracji).
- **Frontend** (`task fe-test`): vitest renderuje AppShell i LoginPage bez
  błędów; `vue-tsc --noEmit` zielony w `task typecheck`.
- **Lint**: ruff + eslint (flat config vue+ts) zielone na całości.
- E2E Playwright: instalacja i konfiguracja `frontend/e2e/` (chromium,
  baseURL z env) + jeden smoke „strona /login się renderuje"; pełny smoke
  login→logout dostarczy B02 (tu nie ma jeszcze auth).

## Acceptance Criteria

1. `docker compose -f docker/compose.dev.yml up` podnosi app + db + db-test;
   `curl http://localhost:<port>/api/v1/health` zwraca
   `{"status":"ok","version":"..."}`.
2. Hot reload działa: zmiana pliku backendu przeładowuje uvicorn; zmiana
   komponentu Vue odświeża widok (HMR) — sprawdzone ręcznie.
3. `task check` przechodzi na zielono na świeżym klonie repo (po
   `cp .env.example .env` i compose up).
4. `alembic heads` = dokładnie jedna głowa; upgrade/downgrade/upgrade
   przechodzą na czystej bazie.
5. `task fe-types` generuje `src/api/generated.ts` bez błędów, a plik
   przechodzi `vue-tsc`.
6. `/login` renderuje się z tokens 06_UIUX (krem `#FAF6EF`, akcent
   `#E07A2F`) — weryfikacja wizualna.
7. W repo nie ma pliku `.env` ani żadnego sekretu (`git ls-files` czysty).
8. `CLAUDE.md` i 4 project skille (`.claude/skills/ffp-*/SKILL.md`) są
   uzgodnione ze stanem faktycznym repo (komendy task istnieją i działają,
   ścieżki prawdziwe, `verified:` zaktualizowane) — zgodnie z 03_AI_SKILLS.

## Out of Scope

- Auth, sesje, CSRF, konta → BATCH_02.
- Jakiekolwiek tabele domenowe i ScopedQuery → BATCH_03+.
- Logika offline/Workbox strategie → BATCH_12 (tu tylko init pluginu).
- `compose.prod.yml`, reverse proxy, backup → BATCH_17/18.
- Serwowanie SPA przez backend (ADR-014) — w dev vite dev server;
  build+StaticFiles spina B17 (odnotować w Notes jeśli inaczej).
- Realne komendy `create-admin` (B02) i `db-seed-demo` (batche domenowe).

## Expected files/modules

- `backend/pyproject.toml`, `backend/app/main.py`,
  `backend/app/core/{config,db,errors}.py`
- `backend/migrations/` (alembic.ini, env.py, `versions/0001_*.py`)
- `backend/tests/{unit,integration,api}/` + `conftest.py`
- `frontend/package.json`, `vite.config.ts`, `tsconfig.json`,
  `tailwind.css`/theme, `src/main.ts`, `src/router.ts`,
  `src/AppShell.vue` (lub `src/layouts/AppShell.vue`),
  `src/pages/LoginPage.vue`, `src/api/{client.ts,queryKeys.ts,generated.ts}`,
  `src/components/ui/*` (shadcn-vue), `frontend/e2e/` (konfig Playwright)
- `docker/Dockerfile`, `docker/compose.dev.yml`
- `Taskfile.yml`, `.env.example`, `.gitignore`, `.editorconfig`
- `CLAUDE.md`, `.claude/skills/ffp-{backend,frontend,domain-calc,security}/SKILL.md` (aktualizacja)
- `docs/implementation-plan/PROGRESS.md` (aktualizacja)

## Implementation Notes

- Kolejność: backend → alembic → frontend → docker → Taskfile → kontrakt AI
  → testy. Compose spina się dopiero, gdy oba końce działają lokalnie.
- Decyzja implementującego (z uzasadnieniem w Completion notes): frontend
  w dev jako osobny serwis compose vs `task dev` uruchamiający vite na
  hoście. Kryterium: hot reload FE i BE musi działać jednym poleceniem.
- Wersje zależności przypinać przez lockfiles (`uv lock`, `package-lock`);
  nie przepisywać wersji z docs — brać aktualne stabilne.
- shadcn-vue init potrafi nadpisać tailwind config — najpierw init, potem
  tokens, na końcu weryfikacja że theme przetrwał.
- Windows-dev uwaga: bind mounts + hot reload uvicorn wymagają
  `--reload-dir app`; sprawdzić na docelowym środowisku właściciela.
- Pusta migracja bazowa MUSI przejść downgrade — to test procedury, nie
  formalność.
- Generator typów TS: wybrać narzędzie (openapi-typescript zalecane —
  zero runtime), uzasadnić w Completion notes.

## Cross-Batch Impact

- **Wszystkie batche**: Taskfile, CLAUDE.md i project skille ffp-* to
  kontrakt każdej kolejnej sesji — zmiany komend wymagają aktualizacji
  wszystkich trzech miejsc naraz.
- **B02**: zastępuje placeholder `create-admin`, dopina CSRF w
  `src/api/client.ts`, zasiedla `stores/` (authStore) i AppShell (nawigacja).
- **B03**: pierwszy realny schemat — korzysta z gotowego łańcucha migracji.
- **B12**: rozbudowuje konfigurację vite-plugin-pwa (nie zmienia init).
- **B17/18**: Dockerfile dostaje target prod; ADR-014 (backend serwuje SPA)
  realizowany na bazie tutejszego multi-stage.
- Po zakończeniu: zaktualizować karty B02–B04, jeśli struktura katalogów
  odbiegła od 01_ARCHITECTURE §2 (i wtedy też sam dokument architektury).

## Implementation checklist

- [x] Backend: pyproject (uv), app factory, config, errors, health
- [x] structlog skonfigurowany (request id, bez sekretów)
- [x] Alembic init + pusta migracja bazowa, up/down zweryfikowane
- [x] Frontend: Vite+Vue3+TS strict+Tailwind4+shadcn-vue z tokens 06_UIUX
- [x] Pinia, TanStack Query, vue-router, AppShell, /login placeholder
- [x] vite-plugin-pwa minimalny manifest (bez offline)
- [x] docker/compose.dev.yml: app + db (pg17) + db-test (tmpfs), healthchecki
- [x] Taskfile.yml: komplet targetów (w tym placeholdery create-admin,
      db-seed-demo)
- [x] task fe-types działa, generated.ts commitowany
- [x] .env.example, .gitignore, .editorconfig
- [x] CLAUDE.md + uzgodnienie 4 skilli .claude/skills/ffp-*/SKILL.md
- [x] Testy: api health, unit config/factory, int migracje, fe-test, e2e konfig
- [x] PROGRESS.md zaktualizowany

## Verification checklist

- [x] `task check` zielony (unit + int + api + fe-test + typecheck + lint
      + format-check + fe-build + migrations-check)
- [x] `alembic heads` = 1 głowa; upgrade → downgrade → upgrade przechodzi
- [x] compose up działa; health zwraca status+version; hot reload BE i FE
      sprawdzony (logi: „WatchFiles detected changes… Reloading",
      „[vite] (client) hmr update /src/layouts/AppShell.vue")
- [x] `git ls-files` bez .env / sekretów / node_modules / dist
- [x] Acceptance Criteria 1–8 odhaczone jedno po drugim
- [x] Dokumentacja: PROGRESS.md + korekty 01_ARCHITECTURE §2/§3, ADR-015,
      uwaga implementacyjna w ADR-007
- [x] Commit `batch(01): ...` wykonany, `git status` czysty

## Completion notes

Wykonano: 2026-08-16.

### Zrobione

Backend (`backend/`): pyproject na uv (FastAPI 0.141, SQLAlchemy 2.0.52,
Pydantic 2.13, Alembic 1.19, psycopg 3.3, structlog 26; dev: pytest 9.1,
httpx, ruff, mypy), `app/core/{config,db,errors,logging}.py`, `app/main.py`
z `create_app()` i `GET /api/v1/health`. Alembic zainicjalizowany
(template async), pusta rewizja bazowa `0001_initial`. Frontend
(`frontend/`): Vite 8 + Vue 3.5 + TS 5.9 strict + Tailwind 4.3 z tokens
06_UIUX, shadcn-vue (button/card/input), Pinia, TanStack Query, vue-router,
`AppShell.vue`, `/login` placeholder, `api/{client,queryKeys,generated}.ts`,
vite-plugin-pwa (manifest PL, bez offline), vitest + Playwright.
`docker/{Dockerfile,compose.dev.yml}` (app + frontend + db + db-test),
`Taskfile.yml`, `.env.example`, `.editorconfig`, `.gitignore`, `CLAUDE.md`,
uzgodnione 4 skille ffp-*.

### Decyzje implementującego (wymagane przez kartę)

1. **Frontend jako osobny serwis compose** (nie vite na hoście). Powód:
   właściciel poprosił wprost o „cały stack do dev/testów bez zbędnej
   komplikacji"; `task dev` jednym poleceniem podnosi app + frontend + obie
   bazy. HMR przez bind mount z Windows wymaga pollingu — compose ustawia
   `VITE_USE_POLLING` i `WATCHFILES_FORCE_POLLING`, oba zweryfikowane
   w logach. `node_modules` w wolumenie nazwanym (binaria Linux ≠ Windows).
2. **Narzędzia jakości biegną na hoście** (uv + npm), usługi w Dockerze.
   `task check` bez przebudowy obrazu = sekundy zamiast minut; bazę widzi
   przez porty publikowane na 127.0.0.1.
3. **Generator typów TS: `openapi-typescript`** (zalecany w karcie; zero
   runtime, czysty plik `.d`-podobny). Wymusił przypięcie **TypeScript
   ~5.9** — 7.13.0 ma peer `typescript@^5.x`, a szablon Vite dawał TS 6.0.
   Cała reszta toolchainu (vue-tsc, typescript-eslint) obsługuje 5.9;
   alternatywa (`--legacy-peer-deps`) psułaby `npm ci` w Dockerze i CI.
4. **`task fe-types` commituje też `backend/openapi.json`** — poza typami
   TS daje materiał do diffu API w batchach Review (04_API §4).
5. **`vite build` dołożony do `task check`** — 03_AI_SKILLS §9 wymienia
   build wśród istniejących bramek, a karta go nie miała; łapie błędy
   widoczne dopiero w buildzie (np. konfiguracja PWA).
6. **`create_app()` bez instancji `app` na poziomie modułu** — uruchomienie
   `uvicorn app.main:create_app --factory`. Bez tego sam import modułu
   wymagał pełnej konfiguracji i wywracał eksport OpenAPI bez `.env`.

### Odstępstwa od karty

- **`app/core/logging.py` jako osobny plik** (karta wymieniała tylko
  `config/db/errors` i „structlog w main.py"). Konfiguracja structlog +
  middleware requestów to ~90 linii — w `main.py` zaciemniałyby composition
  root. `main.py` woła `configure_logging()` i rejestruje middleware.
- **`backend/scripts/export_openapi.py`** — plik spoza listy „Expected
  files", niezbędny do `task fe-types` (eksport `app.openapi()` do JSON).
- **`TEST_DATABASE_URL` nie jest polem `Settings`** — to konfiguracja testów,
  nie aplikacji; czyta ją `tests/conftest.py` z env (wpis jest
  w `.env.example`). `conftest` ustawia `DATABASE_URL := TEST_DATABASE_URL`,
  żeby testy migracji (downgrade base!) nigdy nie dotknęły bazy dev.
- **Health nie sprawdza zgodności migracji** (09_DEPLOYMENT §2 przewiduje
  status `degraded`). Karta definiuje `{status, version}` i zakazuje
  ujawniania czegokolwiek więcej; rozszerzenie przypisane do B17 (wpisane
  do jego karty).
- **Nagłówki bezpieczeństwa/CSP (07 §3) niewdrożone** — poza zakresem B01
  (brak auth i SPA serwowanej przez backend); zadanie B17, odnotowane
  w jego karcie.
- **ADR-007 nie został zmieniony merytorycznie**: `lucide-vue-next` jest
  zdeprecjonowany przez autorów na rzecz `@lucide/vue` (tej używa dzisiejsze
  shadcn-vue). Dopisana „Uwaga implementacyjna" bez zmiany decyzji —
  biblioteka ikon (lucide) pozostaje ta sama.

### Nowy ADR

- **ADR-015 — async SQLAlchemy + psycopg 3.** Architektura wymagała
  `async` route'ów, ale nie rozstrzygała warstwy DB; wybór determinuje
  sygnatury serwisów we wszystkich kolejnych batchach. Konsekwencja
  Windows: psycopg async nie działa na `ProactorEventLoop`, więc alembic
  i pytest na hoście wymuszają `SelectorEventLoop`
  (`selector_loop_factory()`, hook `pytest_asyncio_loop_factories`).

### Review (SKILL-REVIEW = /code-review, poziom high)

5 ustaleń, wszystkie **naprawione w tym batchu**:

1. `app/core/errors.py` — własny `detail` z `HTTPException` był gubiony
   (domyślny komunikat zawsze wygrywał); teraz wygrywa własny, a angielska
   fraza domyślna Starlette jest zamieniana na polski komunikat.
2. `app/core/logging.py` — `clear_contextvars()` kasował cały kontekst
   structloga (skasowałby `user_id` z B02) → `bound_contextvars`.
3. `docker/compose.dev.yml` — `--nosync` (alias nieudokumentowany) →
   `--no-sync`.
4. `tests/unit/test_config.py` — test wartości domyślnych czytał lokalny
   `.env` i przechodził z niewłaściwego powodu → izolacja `tmp_path`.
5. `tests/conftest.py` — martwa stała `BACKEND_DIR` usunięta.

Dołożony `tests/unit/test_errors.py` (5 testów) pokrywający kontrakt błędu
i maskowanie tokenów w logach.

### Środowisko / rzeczy dla właściciela

- Sesja agenta ma regułę uprawnień blokującą pliki `*.ini` i `.env` —
  `backend/alembic.ini` wkleił właściciel (treść podana przez agenta,
  zweryfikowana funkcjonalnie: `alembic heads`, upgrade/downgrade), `.env`
  właściciel utworzył z `.env.example`. Jeśli reguła zostanie zdjęta,
  kolejne sesje zrobią to same.
- Docker Desktop nie był w `PATH` sesji (instalacja per-user
  `%LOCALAPPDATA%\Programs\DockerDesktop`) — weryfikacja szła pełną
  ścieżką. W normalnym terminalu `docker` działa.

### Follow-upy (poza zakresem B01)

1. `task check` nie weryfikuje, czy `openapi.json`/`generated.ts` są świeże
   względem kodu — rozważyć bramkę „regeneruj i porównaj" (R1).
2. `task audit` i `task secrets-scan` napisane, ale **nieuruchomione**
   w tym batchu (wg 03_AI_SKILLS §9 należą do Review i B17).
3. Ikony PWA to placeholdery SVG — komplet PNG 192/512 dowozi B12
   (wpisane do karty B12).
4. `frontend/.vscode/extensions.json` ze szablonu Vite zostaje na dysku,
   ale jest ignorowany przez `.gitignore` (`.vscode/`).
### Pytania do właściciela

Brak otwartych. **D12 (Ansistrano) rozstrzygnięte 2026-08-16 w trakcie tej
sesji: bez Ansistrano** — wdrożenie zostaje na procedurze z 09_DEPLOYMENT §4
(`git pull` → build → backup → `alembic upgrade head` → `compose up -d`),
B18 opakowuje ją w skrypt. 09_DEPLOYMENT i karta B18 nie wymagają zmian.
