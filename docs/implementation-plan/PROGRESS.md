# PROGRESS — status batchy i dziennik programu

Aktualizowany przez agentów wykonujących batche. Status: `[ ]` nierozpoczęty,
`[~]` w toku, `[x]` DONE (Definition of Done z 00_MASTER_PLAN §7 spełnione,
commit wykonany). Kolumna „Blokery" = zależności + decyzje z 02_DECISIONS.

## Statusy

| Batch | Status | Blokery | Commit |
|---|---|---|---|
| 01 PROJECT_SCAFFOLD_AND_DEV_LOOP | [x] | — | `batch(01)` na master (hash wpisać po push) |
| 02 AUTH_AND_ACCOUNTS | [ ] | 01 | |
| 03 HOUSEHOLDS_AND_SCOPE | [ ] | 02 | |
| 04 UNITS_AND_CANONICAL_PRODUCTS | [ ] | 03 | |
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
