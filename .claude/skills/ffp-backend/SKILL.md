---
name: ffp-backend
description: Kontrakt backendu Family Food Planner — wzorzec modułu FastAPI (router→service→models), SQLAlchemy 2.0 typed, Alembic, Pydantic v2, ScopedQuery, pytest. Ładuj przed pracą nad plikami w backend/**.
---

<!-- verified: 2026-08-16 (REVIEW R1 — uzgodnione z kodem po B01–B04)
     stack: Python 3.13 · FastAPI 0.141 · SQLAlchemy 2.0.52 · Pydantic 2.13
            · Alembic 1.19 · psycopg 3.3 (async) · pytest 9.1 · mypy 2.3
            · argon2-cffi 25 · slowapi 0.1.10 · PG 17 · uv
     hierarchia: ADR i docs/architecture NADRZĘDNE wobec tego skilla -->

# FFP — kontrakt backendu

## Fundament z BATCH_01–04 (istnieje, nie pisz tego od nowa)

- `app/core/config.py` — `Settings` (pydantic-settings), `get_settings()`
  z cache, `ConfigurationError` po polsku przy brakach. Nowa zmienna =
  wpis w `.env.example` w tym samym commicie.
- `app/core/db.py` — `Base` z `naming_convention`, silnik async
  (`postgresql+psycopg://`, ADR-015), `get_session()` jako dependency,
  `selector_loop_factory()` (Windows: psycopg nie działa na Proactor).
- `app/core/errors.py` — `AppError` + `NotFoundError` / `ForbiddenError` /
  `UnauthorizedError` / `ConflictError` i handlery. Serwisy rzucają te
  wyjątki, NIGDY `HTTPException`.
- `app/core/logging.py` — structlog + `RequestLoggingMiddleware`.
- `app/main.py` — `create_app(settings)`; aplikacji NIE ma na poziomie
  modułu (uruchomienie: `uvicorn app.main:create_app --factory`).
  Nowy moduł rejestruje router właśnie tutaj.
- `app/core/deps.py` — JEDYNE wejście autoryzacji: `CurrentUser`, `AdminUser`,
  `require_admin` (+ fabryki serwisów). Router nie czyta cookie sam.
- `app/core/{security,cookies,middleware}.py` — argon2id, tokeny, TTL sesji,
  atrybuty cookies, CSRF double-submit i nagłówki bezpieczeństwa. Szczegóły:
  skill `ffp-security`.
- `app/core/scope.py` — `ScopedMixin` + `ScopedQuery` (patrz §Autoryzacja).
- `app/core/deletion.py` — `UsedInRef`, `assert_deletable`,
  `conflict_from_integrity_error`: kontrakt 409 z `details.used_in`. FK
  domenowe mają RESTRICT, więc `IntegrityError` z commita łapiesz jako drugą
  linię obrony — inaczej użytkownik dostanie 500 zamiast 409.
  **Trzy rejestry liczników referencji** (wzorzec: moduł POSIADAJĄCY encję
  rejestruje funkcję u modułu, którego encję trzyma):
  `catalog.service.register_product_reference_finder`,
  `recipes.service.register_recipe_reference_finder`,
  `catalog.retail_service` / `stores_service` (warianty i sklepy) oraz
  `households.service.register_household_reference_finder` (od REVIEW R3).
  **Nowa tabela ze `household_id` albo z FK do encji słownikowej = nowy
  licznik w TYM SAMYM batchu**, inaczej 409 wraca z pustą listą.
- `app/core/schemas.py` — `DecimalString` dla KAŻDEGO pola NUMERIC w odpowiedzi.
- `app/modules/catalog/` — `units.py` (jedyne konwersje ilości),
  `nutrition_adapter.py` (jedyne wejście silników do wartości, ADR-004),
  `naming.normalize_name` (klucz tożsamości produktu).
- `app/modules/audit/service.py` — `record()` bez commita; wpis powstaje
  w transakcji operacji. Nowa akcja = wpis w `AuditAction`/`AuditEntity`
  (`<encja>.<czasownik>`); Decimal w payloadzie przez `format(value, "f")`.

## Wzorzec modułu (ADR-001, 01_ARCHITECTURE §2)

`backend/app/modules/<nazwa>/{models.py, schemas.py, service.py, router.py}`.
Katalog modułu tworzy batch, który go zasiedla — pustych katalogów „na zapas"
nie ma.

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
  = wynik `task db-heads`. NIGDY numer z planu/karty. Rewizja bazowa to
  pusta `0001_initial`.
- Tworzenie: `task db-revision -- --rev-id 0002 -m "opis"` (plik dostaje
  nazwę `0002_opis.py`; hook formatuje go ruffem).
- Po zmianie: dokładnie 1 głowa (pilnuje `task migrations-check` wewnątrz
  `task check`); `upgrade head` i `downgrade` przechodzą na czystej bazie.
  Backfill = osobna migracja, idempotentna.
- `migrations/env.py` bierze URL z `DATABASE_URL` albo z `-x db_url=…`;
  w `alembic.ini` NIE MA poświadczeń.

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

## Transakcje

- Serwis kończy operację JEDNYM commitem. Metoda wołana w PĘTLI po pozycjach
  jednej decyzji użytkownika nie commituje sama — robi `flush()` i commit
  zostawia wołającemu (wzorzec `AuditService.record`,
  `PantryService.receive_purchase` po REVIEW R3). Commit per element zostawia
  po błędzie stan pośredni, którego ponowienie akcji policzy DRUGI raz.

## Async

- Route'y async; sesja DB też jest async (`AsyncSession`, ADR-015).
- Żadnych blokujących wywołań w event loopie (Pillow, pdfplumber →
  `run_in_threadpool`). Bez własnych wątków/kolejek (ADR-001).

## pytest

- Katalogi `tests/{unit,integration,api}/`; KAŻDY plik testowy deklaruje
  marker (`pytestmark = pytest.mark.unit|integration|api`) — bez markera
  test nie wejdzie do żadnego targetu Taskfile'a.
- Fixture'y w `tests/conftest.py`: `settings`, `app`, `client`
  (httpx AsyncClient + ASGITransport), `db_session`/`db_client` (baza),
  `test_database_url` (db-test). Fabryki danych → `tests/factories.py`,
  logowanie i nagłówek CSRF → `tests/helpers.py`.
- **Nowa tabela = wpis w DWÓCH miejscach**: `DB_TABLES` (conftest, TRUNCATE)
  i `EXPECTED_TABLES` (`tests/integration/test_migrations.py`); nowy typ
  enumowy dopisz do `EXPECTED_ENUM_TYPES` tam samo.
- **Bramka dryfu modeli** (REVIEW R3):
  `test_modele_nie_dryfuja_od_schematu_po_migracjach` porównuje `Base.metadata`
  ze schematem po `upgrade head`. Kolumna, której FK dopina PÓŹNIEJSZA migracja
  (wzorzec „batch mergowany jako drugi"), musi dostać `ForeignKey` w modelu
  w tym samym commicie co ta migracja. Sprawdzenie na hoście: `uv run alembic
  check` w `backend/`.
- Testy integracyjne dostają `DATABASE_URL` = `TEST_DATABASE_URL`; baza dev
  jest nietykalna.
- Testy nazywają scenariusz po polsku w docstringu.
- Uruchamiaj przez `task test-unit|test-int|test-api|check` — nigdy goły
  `pytest` (zły interpreter/env, brak `.env`).

## Konfiguracja i logi

- Wyłącznie env przez pydantic-settings (`core/config.py`); nowa zmienna =
  wpis w `.env.example` w tym samym commicie.
- structlog: request id + user id (nie email); NIGDY tokenów/haseł w logach
  (`/public/lists/***` maskowane). Szczegóły wrażliwe: skill `ffp-security`.
