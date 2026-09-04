# ADR-002 — PostgreSQL w Dockerze, dane na bind mounts, Alembic

Status: ACCEPTED (2026-08-16)

## Kontekst
Wymóg: lifecycle kontenera ≠ lifecycle danych; trwałe dane (DB, zdjęcia,
uploady) muszą przeżyć rekreację kontenerów i być łatwe do backupu.

## Decyzja
PostgreSQL 17 jako kontener compose; katalog danych na bind mount
`/srv/pasnik/pgdata`. Analogicznie `/srv/pasnik/uploads` (zdjęcia, PDF-y importu)
i `/srv/pasnik/backups`. Migracje: Alembic; polityka numeracji = pierwszy
wolny numer + `down_revision` z `alembic heads` (bez rezerwacji numerów
w planie — sprawdzona lekcja netQArnera). Migracje uruchamiane jawnie
w procedurze update, nie przy starcie kontenera.

## Konsekwencje
+ Backup = pg_dump + kopia katalogów; restore niezależny od stanu obrazów.
+ Brak wyścigów migracji przy restarcie.
− Jawny krok migracji w procedurze update (udokumentowany w runbooku B18).
NUMERIC dla ilości/wartości odżywczych (nigdy float) — 03_DATABASE §0.
