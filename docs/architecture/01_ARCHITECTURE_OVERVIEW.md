# 01 — Przegląd architektury

Family Food Planner (FFP) — prywatna, rodzinna aplikacja do planowania
żywienia, przepisów, kalorii/makro, spiżarni i inteligentnych list
zakupowych. Mała liczba użytkowników, dostęp publiczny przez Internet
(istniejący reverse proxy), hosting: Odroid H2, Docker + Docker Compose.

## 1. Decyzja główna: modularny monolit (ADR-001)

Jeden proces FastAPI + jedna baza PostgreSQL + SPA Vue serwowane przez
backend. Zero mikroserwisów, zero brokerów, zero Redis — skala tego nie
uzasadnia, a każdy dodatkowy proces to koszt operacyjny na Odroidzie.

```
┌──────────────────────────── Odroid H2 ───────────────────────────┐
│  reverse proxy (istniejący, TLS)                                  │
│      │ https://ffp.<domena>                                       │
│      ▼                                                            │
│  ┌─ kontener app ────────────────────────────┐  ┌─ kontener db ─┐ │
│  │ Uvicorn + FastAPI                          │  │ PostgreSQL 17 │ │
│  │  /api/v1/*  → routery modułów              │──│               │ │
│  │  /*         → SPA dist (StaticFiles)       │  └───────┬───────┘ │
│  │  /uploads/* → pliki (auth-gated)           │          │         │
│  └───────┬────────────────────────────────────┘          │         │
│     bind mount /srv/ffp/uploads          bind mount /srv/ffp/pgdata│
│     bind mount /srv/ffp/backups  ◄─ pg_dump + kopia uploads        │
└────────────────────────────────────────────────────────────────────┘
```

## 2. Struktura repozytorium

```
family-food-planner/
  backend/
    app/
      core/          # config (pydantic-settings), db, security, deps, errors
      modules/
        accounts/    # models.py, schemas.py, service.py, router.py (wzorzec
        households/  #   powtarzany w każdym module)
        catalog/
        recipes/
        nutrition/   # silnik obliczeń: czyste funkcje, bez I/O
        planning/
        pantry/
        shopping/    # engine.py (czysty) + service.py (I/O) + router.py
        importer/
        transfer/
        audit/
      main.py        # composition root: app factory, routery, middleware
    migrations/      # Alembic
    tests/           # lustro modułów: unit/ integration/ api/
    pyproject.toml   # uv; ruff + mypy konfigurowane tu
  frontend/
    src/
      api/           # klient HTTP + typy z OpenAPI
      components/    # ui/ (shadcn-vue) + domenowe
      composables/
      pages/         # vue-router file-like: plan-dnia, tydzien, przepisy,
      stores/        #   produkty, spizarnia, zakupy, statystyki, ustawienia
      lib/
    e2e/             # Playwright
  docker/            # Dockerfile, compose.dev.yml, compose.prod.yml (B18)
  data/
    source_pdfs/     # 8 PDF-ów dietetyczki (wejście importera + testy)
    reference/       # prototype.db — TYLKO referencja walidacyjna importera
  docs/              # architektura, ADR, implementation-plan
  Taskfile.yml       # jedyne źródło komend dev (task help)
```

Reguła modułu backendu: `router.py` (HTTP, walidacja wejścia przez schemas)
→ `service.py` (logika, transakcje, autoryzacja scope) → `models.py`
(SQLAlchemy). Router nigdy nie dotyka sesji DB bezpośrednio. Moduł →
moduł wyłącznie przez service.

## 3. Stack (twardo ustalony)

| Warstwa | Wybór | Uwagi |
|---|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, Uvicorn | uv jako package manager |
| Hasła/sesje | argon2-cffi, sesje server-side w PG, cookie HttpOnly | ADR-003, bez JWT |
| Rate limit | slowapi | login + endpointy publiczne |
| PDF | pdfplumber (ekstrakcja), anthropic SDK (asysta mapowania) | ADR-011 |
| Obrazy | Pillow (walidacja + miniatury) | |
| Logi | structlog → stdout (JSON w prod) | zbiera Docker |
| Frontend | Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS 4 | bez Nuxta |
| Komponenty | shadcn-vue (reka-ui) + lucide-vue-next | ADR-007 |
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
(healthcheck compose), logowanie strukturalne, sekrety poza repo. Finalny
deployment (compose.prod, proxy, backup/restore, update/rollback) —
BATCH_17/18 po Review 4, na bazie rzeczywistej aplikacji.

## 6. Czego świadomie NIE budujemy

Mikroserwisy, Redis/kolejki, realtime/WebSockety (odhaczanie listy działa
na poll/sync), wersjonowanie przepisów, system zamienników składników,
integracje płatne, i18n, self-service rejestracja, 2FA (możliwe FUTURE).
