---
name: ffp-backend
description: Kontrakt backendu Family Food Planner — wzorzec modułu FastAPI (router→service→models), SQLAlchemy 2.0 typed, Alembic, Pydantic v2, ScopedQuery, pytest. Ładuj przed pracą nad plikami w backend/**.
---

<!-- verified: 2026-08-16 (blueprint; B01 uzgadnia z rzeczywistym kodem)
     stack: Python 3.13 · FastAPI 0.12x · SQLAlchemy 2.0 · Pydantic 2.x · PG 17
     hierarchia: ADR i docs/architecture NADRZĘDNE wobec tego skilla -->

# FFP — kontrakt backendu

## Wzorzec modułu (ADR-001, 01_ARCHITECTURE §2)

`backend/app/modules/<nazwa>/{models.py, schemas.py, service.py, router.py}`.

- **router.py**: tylko HTTP — walidacja wejścia (schemas), wywołanie serwisu,
  mapowanie wyniku. NIGDY nie dotyka sesji DB ani nie zawiera logiki.
- **service.py**: logika, transakcje, autoryzacja scope. Jedyne miejsce I/O.
- Moduł→moduł WYŁĄCZNIE przez service (import modeli dozwolony do JOIN-ów,
  logika biznesowa — nie).
- Silniki obliczeń (`nutrition/engine.py`, `shopping/engine.py`): czyste
  funkcje bez I/O — reguły w skillu `ffp-domain-calc`.

## SQLAlchemy 2.0 — styl obowiązkowy

- Deklaratywnie z typami: `Mapped[str]`, `mapped_column(...)`; bez
  legacy `Column = Column(...)` i bez Query API 1.x (`session.query`).
- Zapytania: `select(...)` + `session.execute(...).scalars()`.
- Ilości i wartości odżywcze: **NUMERIC ↔ Decimal**. `float` w modelu,
  schemacie lub obliczeniu = błąd blokujący review (ADR-008).
- FK zawsze z jawnym `ON DELETE` (RESTRICT domenowe, CASCADE tylko
  kompozycja rodzic→dziecko — ADR-012). `created_at`/`updated_at` wszędzie.

## Alembic (ADR-002, 03_DATABASE §1)

- Numer migracji = pierwszy wolny w `migrations/versions/`; `down_revision`
  = wynik `alembic heads`. NIGDY numer z planu/karty.
- Po zmianie: `alembic heads` → dokładnie 1 głowa; `upgrade head` i
  `downgrade -1` przechodzą na kopii bazy. Backfill = osobna migracja,
  idempotentna.

## Pydantic v2 / API (04_API)

- Schematy request/response w `schemas.py`; nigdy nie zwracaj modeli ORM
  bezpośrednio. `model_config = ConfigDict(from_attributes=True)` dla odczytu.
- Ilości w JSON jako **stringi dziesiętne** (`"12.5"`); serializatory pól
  Decimal → str.
- Błędy: jeden kształt `{"error": {code, message, details}}`; message po
  polsku; 409 dla blokady usunięcia z `details.used_in=[{type,id,name}]`;
  404 (nie 403) dla cudzych zasobów.
- Paginacja: `?limit=` (≤200) `&offset=` → `{items, total}`.

## Autoryzacja i scope

- Dependency `current_user` / `require_admin`; endpointy publiczne tylko
  w routerze `public` (tokeny list).
- Widoczność zasobów WYŁĄCZNIE przez mixin `ScopedQuery` (core) — warunek
  `owner_user_id = :uid OR (scope='household' AND household_id = :hh)`.
  Ręczne filtry scope w serwisach = błąd review.
- Każdy nowy zasób MA test macierzy uprawnień (08_TESTING §4) — endpoint
  bez testu scope nie przechodzi DoD.

## Async

- Route'y async; żadnych blokujących wywołań w event loopie (Pillow,
  pdfplumber → `run_in_threadpool`). Bez własnych wątków/kolejek (ADR-001).

## pytest

- Unit (czyste funkcje, bez DB) / integration (PG z compose, rollback po
  teście) / api (httpx AsyncClient + ASGITransport). Fabryki w
  `tests/factories.py`. Testy nazywają scenariusz po polsku w docstringu.
- Uruchamiaj przez `task test-unit|test-int|test-api|check` — nigdy goły
  `pytest` (zły interpreter/env).

## Konfiguracja i logi

- Wyłącznie env przez pydantic-settings (`core/config.py`); nowa zmienna =
  wpis w `.env.example` w tym samym commicie.
- structlog: request id + user id (nie email); NIGDY tokenów/haseł w logach
  (`/public/lists/***` maskowane). Szczegóły wrażliwe: skill `ffp-security`.
