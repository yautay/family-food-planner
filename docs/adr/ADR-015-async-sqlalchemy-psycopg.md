# ADR-015 — Dostęp do bazy asynchronicznie: SQLAlchemy async + psycopg 3

Status: ACCEPTED (2026-08-16, BATCH_01)

## Kontekst
Architektura zakłada route'y `async` w FastAPI (ADR-001, skill pasnik-backend:
„żadnych blokujących wywołań w event loopie"), ale nie rozstrzygała, czy
warstwa DB jest synchroniczna czy asynchroniczna. Wybór trzeba było podjąć
przy pisaniu `app/core/db.py` w BATCH_01, bo determinuje sygnatury serwisów
we WSZYSTKICH kolejnych batchach (`Session` vs `AsyncSession`) i sposób
uruchamiania Alembica.

Synchroniczne SQLAlchemy w route'cie `async` blokuje event loop przy każdym
zapytaniu — to dokładnie ten błąd, przed którym ostrzega kontrakt backendu.
Alternatywa (route'y `def`, FastAPI w threadpoolu) działa, ale rozjeżdża się
z resztą architektury i utrudnia późniejsze operacje współbieżne.

## Decyzja
- Silnik: `create_async_engine` + `async_sessionmaker`, driver **psycopg 3**
  (`postgresql+psycopg://`). Jeden driver do trybu async i sync — psycopg 3
  obsługuje oba, więc narzędzia (np. inspekcja bazy w testach) nie wymagają
  drugiej zależności (bez asyncpg).
- Serwisy przyjmują `AsyncSession`; dependency `app.core.db.get_session`.
- URL z env jest normalizowany (`normalize_database_url`), więc
  `postgresql://…` w `DATABASE_URL` też zadziała.
- Alembic pracuje na tym samym silniku async (`migrations/env.py`,
  `connection.run_sync`).
- **Windows**: psycopg async nie działa na `ProactorEventLoop`. Narzędzia
  uruchamiane na hoście dewelopera (alembic, pytest) wymuszają
  `SelectorEventLoop` — `app.core.db.selector_loop_factory()` oraz hook
  `pytest_asyncio_loop_factories` w `tests/conftest.py`. Sama aplikacja
  działa w kontenerze Linux, więc jej to nie dotyczy; uruchamianie
  `uvicorn` natywnie na Windows z dostępem do bazy NIE jest wspierane.

## Konsekwencje
+ Brak blokowania event loopu; spójność z `async` route'ami od pierwszego
  modułu z bazą (B02).
+ Jedna zależność DBAPI (psycopg 3) dla aplikacji, migracji i testów.
− Serwisy muszą być `async` (każde `session.execute` z `await`); testy
  integracyjne dotykające sesji są `async`.
− Windows-dev ma dodatkowy warunek (SelectorEventLoop) — udokumentowany
  w CLAUDE.md i skillu `pasnik-backend`; pętla dev i tak stoi w Dockerze.
