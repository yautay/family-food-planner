# 01 — Przegląd architektury

Paśnik — prywatna, rodzinna aplikacja do planowania
żywienia, przepisów, kalorii/makro, spiżarni i inteligentnych list
zakupowych. Mała liczba użytkowników, dostęp publiczny przez Internet
(istniejący reverse proxy), hosting: kontener LXC (Incus) na Odroidzie,
wdrażany ansistrano; dev na Docker Compose (D29, ADR-017).

## 1. Decyzja główna: modularny monolit (ADR-001)

Jeden proces FastAPI + jedna baza PostgreSQL + SPA Vue serwowane przez
backend. Zero mikroserwisów, zero brokerów, zero Redis — skala tego nie
uzasadnia, a każdy dodatkowy proces to koszt operacyjny na Odroidzie.

```
┌── 192.168.2.121 ──────────────────┐     ┌── Odroid 192.168.2.111 (Incus) ─────────────┐
│ Caddy (TLS, pasnik.cpt-sztos.com) │────►│ proxy device :<port> ─► LXC `pasnik`         │
│                                   │     │  systemd: Uvicorn + FastAPI (User=pasnik)    │
│ postgres-apps (PG 16, Docker)     │◄────│   /api/v1/*  → routery modułów               │
│   baza ffp_db (współdzielony      │     │   /*         → SPA dist (release)            │
│   klaster z netQArnerem)          │     │   /uploads/* → pliki (auth-gated)            │
└───────────────────────────────────┘     │  /opt/pasnik/shared/{uploads,backups}        │
                                          │  pasnik-backup.timer ─ pg_dump + tar uploads │
                                          └──────────────────────────────────────────────┘
```

Produkcja od decyzji D29 (ADR-017): kontener LXC wdrażany ansistrano, baza
w istniejącym klastrze `postgres-apps` — szczegóły w 09_DEPLOYMENT.

## 2. Struktura repozytorium

Stan faktyczny po BATCH_01 (moduły domenowe i katalogi oznaczone „(Bxx)"
powstają w batchu, który je zasiedla — pustych katalogów na zapas nie ma).

```
family-food-planner/
  backend/
    alembic.ini      # bez poświadczeń — URL bierze migrations/env.py
    pyproject.toml   # uv; ruff + mypy + pytest konfigurowane tu
    uv.lock
    openapi.json     # generowany (task fe-types), commitowany — diff API w Review
    scripts/         # export_openapi.py
    app/
      core/          # config, db, errors, logging (+ security, deps: B02/B03)
      modules/       # (B02+)
        accounts/    # models.py, schemas.py, service.py, router.py (wzorzec
        households/  #   powtarzany w każdym module)
        catalog/
        recipes/
        nutrition/   # silnik obliczeń: czyste funkcje, bez I/O
        planning/
        pantry/
        shopping/    # engine.py (czysty) + service.py (I/O) + router.py
        transfer/     # kopia danych rodziny i instancji (ADR-016)
        audit/
      main.py        # composition root: create_app() — brak app na poziomie modułu
    migrations/      # Alembic: env.py + versions/0001_initial.py (pusta)
    tests/           # lustro modułów: unit/ integration/ api/ + conftest.py
  frontend/
    index.html · vite.config.ts · tsconfig*.json · components.json
    eslint.config.ts · playwright.config.ts · .prettierrc.json
    public/          # icon.svg, icon-maskable.svg (placeholdery PWA, B12)
    src/
      api/           # client.ts (apiFetch/ApiError), queryKeys.ts, generated.ts
      assets/        # tailwind.css — JEDYNE miejsce definicji kolorów
      components/    # ui/ (shadcn-vue: button, card, input) + domain/ (B02+)
      layouts/       # AppShell.vue
      pages/         # LoginPage.vue; plan-dnia, tydzien, przepisy… (B02+)
      stores/        # (B02+ — authStore)
      lib/           # utils.ts (cn), texts.ts (B02+)
      main.ts · router.ts · App.vue
    e2e/             # Playwright (login.spec.ts)
  docker/            # Dockerfile (dev + prod do testu obrazu), compose.dev.yml,
                     #   compose.test.yml, backup/ (skrypty backupu)
  deploy/            # (B18) Ansible + ansistrano, provision LXC
  docs/              # architektura, ADR, implementation-plan
  .claude/skills/    # project skille pasnik-* (03_AI_SKILLS)
  Taskfile.yml       # jedyne źródło komend dev (task help)
  CLAUDE.md · .env.example · .editorconfig · .gitignore
```

Reguła modułu backendu: `router.py` (HTTP, walidacja wejścia przez schemas)
→ `service.py` (logika, transakcje, autoryzacja scope) → `models.py`
(SQLAlchemy). Router nigdy nie dotyka sesji DB bezpośrednio. Moduł →
moduł wyłącznie przez service.

## 3. Stack (twardo ustalony)

| Warstwa | Wybór | Uwagi |
|---|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, Uvicorn | uv jako package manager; driver psycopg 3 async (ADR-015) |
| Hasła/sesje | argon2-cffi, sesje server-side w PG, cookie HttpOnly | ADR-003, bez JWT |
| Rate limit | slowapi | login + endpointy publiczne |
| Obrazy | Pillow (walidacja + miniatury) | |
| Logi | structlog → stdout (JSON w prod) | zbiera Docker |
| Frontend | Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS 4 | bez Nuxta |
| Komponenty | shadcn-vue (reka-ui) + `@lucide/vue` | ADR-007 (paczka `lucide-vue-next` jest zdeprecjonowana) |
| Server state | TanStack Query (Vue Query) | Pinia tylko UI state |
| Formularze | vee-validate + zod | |
| PWA | vite-plugin-pwa (Workbox) + idb | ADR-009 |
| QR | qrcode (npm, render kliencki) | |
| Wykresy | własne prymitywy SVG | ADR-013, bez biblioteki |
| Testy | pytest / vitest + vue-tsc / Playwright | 08_TESTING_STRATEGY |
| i18n | BRAK — UI wyłącznie PL (decyzja właściciela 2026-08-16) | |

## 4. Przepływy przekrojowe

- **Żywienie**: encje przechowują ilości; wartości (kcal/makro/ŁG) zawsze
  wylicza `nutrition` z produktów kanonicznych (jedno źródło prawdy,
  niezmiennik 02 §13.3).
- **Zakupy**: `shopping/engine.py` = czysta funkcja (wejście: plan+konfig,
  wyjście: preview struct) — testowalna bez DB; `service.py` materializuje
  listy.
- **Scope**: mixin `ScopedQuery` w core — jedno miejsce egzekwowania
  PRIVATE/HOUSEHOLD (02 §3.1).
- **Autoryzacja**: dependency FastAPI `current_user` / `require_admin`;
  endpointy publiczne (token listy) w osobnym routerze bez sesji.

## 5. Production-readiness od pierwszego batcha

Każdy batch utrzymuje: konfigurację wyłącznie przez env (pydantic-settings,
`.env.example` aktualizowany), migracje odtwarzalne, `/api/v1/health`
(healthcheck), logowanie strukturalne, sekrety poza repo. Finalny
deployment (LXC + ansistrano, proxy, backup/restore, update/rollback) —
BATCH_17/18 po Review 4, na bazie rzeczywistej aplikacji.

## 6. Czego świadomie NIE budujemy

Mikroserwisy, Redis/kolejki, realtime/WebSockety (odhaczanie listy działa
na poll/sync), wersjonowanie przepisów, system zamienników składników,
integracje płatne, i18n, self-service rejestracja, 2FA (możliwe FUTURE).
