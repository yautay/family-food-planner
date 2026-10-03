# ADR-002 — PostgreSQL w Dockerze, dane na bind mounts, Alembic

Status: SUPERSEDED przez ADR-017 (2026-10-03)

> Produkcja nie stoi na compose: decyzja właściciela **D29** przeniosła ją do
> kontenera LXC wdrażanego ansistrano, a bazę do istniejącego klastra
> `postgres-apps` (PG 16). Zasady „migracje jawne, nie przy starcie" i
> „numer migracji = pierwszy wolny" obowiązują dalej — ADR-017 pkt 6–7.
> Treść poniżej zostaje jako zapis, na czym stała ta decyzja.

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
