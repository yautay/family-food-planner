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
| 04 UNITS_AND_CANONICAL_PRODUCTS | [ ] | — (03 gotowe) | |
| R1 REVIEW_FOUNDATIONS | [ ] | 01–04 | |
| 05 RECIPES_AND_NUTRITION_ENGINE | [ ] | 04, R1 | |
| 06 GOALS_AND_DAY_PLAN | [ ] | 05 | |
| 07 WEEK_TEMPLATES_AND_CYCLES | [ ] | 06 | |
| R2 REVIEW_PLANNING_CORE | [ ] | 05–07 | |
| 08 PANTRY | [ ] | 04, R2 | |
| 09 RETAIL_PRODUCTS_AND_STORES | [ ] | 04, R2 | |
| 10 SHOPPING_ENGINE | [ ] | 06, 08, 09 | |
| 11 SHOPPING_LISTS_AND_SHARING | [ ] | 10 | |
| R3 REVIEW_SHOPPING | [ ] | 08–11 | |
| 12 PWA_AND_OFFLINE | [ ] | 11, R3 | |
| 13 STATISTICS | [ ] | 06, R3 | |
| 14 IMPORT_EXPORT | [ ] | R3 | |
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
