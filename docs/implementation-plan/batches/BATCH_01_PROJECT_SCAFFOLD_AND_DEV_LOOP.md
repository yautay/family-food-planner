# BATCH_01 — PROJECT_SCAFFOLD_AND_DEV_LOOP

Klasa: FOUND · Zależności: brak · Szacunek rozmiaru: M

## Goal

Po tym batchu repozytorium ma kompletny szkielet monorepo (backend FastAPI +
frontend Vue 3) z działającą pętlą deweloperską: `docker compose` podnosi
aplikację z hot-reloadem i PostgreSQL, `task check` przechodzi na zielono,
`/api/v1/health` odpowiada. Powstaje też kontrakt jakości dla wszystkich
kolejnych sesji: `CLAUDE.md`, project skill `ffp-framework` i generowanie
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
- `docs/implementation-plan/03_AI_SKILLS.md` — zakres CLAUDE.md i project
  skilla (obowiązkowe artefakty tego batcha).
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
   test-int + test-api + fe-test + typecheck + lint), `test-unit`,
   `test-int`, `test-api`, `fe-test`, `typecheck` (mypy + vue-tsc), `lint`
   (ruff + eslint), `fe-types` (eksport OpenAPI z app factory → generator
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
   `docs/implementation-plan/implementation_prompt.md`. Project skill
   `.claude/skills/ffp-framework/SKILL.md` wg 03_AI_SKILLS: kontrakt
   kodowania (moduł backendu, ScopedQuery — zapowiedź z odesłaniem do B03,
   konwencje Decimal, Query vs Pinia, create-in-context, jak uruchamiać
   testy) — ładowany przy pracy w `backend/**` / `frontend/**`; przy
   tworzeniu użyć skilla `skill-creator`.
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
8. `CLAUDE.md` i `.claude/skills/ffp-framework/SKILL.md` istnieją i zawierają
   komplet z 03_AI_SKILLS (komendy, zakazy, wskaźnik na master prompt).

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
- `CLAUDE.md`, `.claude/skills/ffp-framework/SKILL.md`
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

- **Wszystkie batche**: Taskfile, CLAUDE.md i skill ffp-framework to
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

- [ ] Backend: pyproject (uv), app factory, config, errors, health
- [ ] structlog skonfigurowany (request id, bez sekretów)
- [ ] Alembic init + pusta migracja bazowa, up/down zweryfikowane
- [ ] Frontend: Vite+Vue3+TS strict+Tailwind4+shadcn-vue z tokens 06_UIUX
- [ ] Pinia, TanStack Query, vue-router, AppShell, /login placeholder
- [ ] vite-plugin-pwa minimalny manifest (bez offline)
- [ ] docker/compose.dev.yml: app + db (pg17) + db-test (tmpfs), healthchecki
- [ ] Taskfile.yml: komplet targetów (w tym placeholdery create-admin,
      db-seed-demo)
- [ ] task fe-types działa, generated.ts commitowany
- [ ] .env.example, .gitignore, .editorconfig
- [ ] CLAUDE.md + .claude/skills/ffp-framework/SKILL.md
- [ ] Testy: api health, unit config/factory, int migracje, fe-test, e2e konfig
- [ ] PROGRESS.md zaktualizowany

## Verification checklist

- [ ] `task check` zielony (unit + int + api + fe-test + typecheck + lint)
- [ ] `alembic heads` = 1 głowa; upgrade → downgrade → upgrade przechodzi
- [ ] compose up działa; health zwraca status+version; hot reload BE i FE
      sprawdzony ręcznie
- [ ] `git ls-files` bez .env / sekretów / node_modules / dist
- [ ] Acceptance Criteria 1–8 odhaczone jedno po drugim
- [ ] Dokumentacja: PROGRESS.md + ewentualne korekty 01_ARCHITECTURE do
      stanu faktycznego
- [ ] Commit `batch(01): ...` wykonany, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
