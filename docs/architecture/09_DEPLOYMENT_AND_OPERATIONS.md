# 09 — Deployment, backup i operacje

Docelowo: Odroid H2 (x86-64, Debian-family), Docker + Docker Compose
(ustalone; NIE LXC), za istniejącym reverse proxy z TLS i domeną (D7: Caddy
jako usługa systemowa hosta, `pasnik.cpt-sztos.com`). Ten dokument opisuje
**stan faktyczny po BATCH_17** (obraz prod, healthcheck, backup/restore,
konfiguracja) oraz założenia dla **BATCH_18** (compose.prod, proxy, runbooki).

## 1. Topologia produkcyjna (założenia wiążące)

- 2 kontenery: `app` (Uvicorn+FastAPI, serwuje też SPA i uploady)
  i `db` (postgres:17). Opcjonalny profil `backup` (kontener z pętlą
  cron — §3).
- Sieć: tylko `app` wystawia port na localhost hosta; `db` bez portów.
  **Port NIE MOŻE być 8080** (tak podawał ten dokument jako przykład): na
  docelowym hoście `127.0.0.1:8080` zajmuje Pi-hole (`pihole.cpt-sztos.com`
  w `Caddyfile` właściciela, ustalenie D7 z 2026-09-05). Zajęte są tam także
  3000, 1880, 4173, 8013, 8888, 9000 i 9101. Proponowany port aplikacji:
  **8081** — B18 potwierdza go `ss -ltnp` PRZED wpisaniem do compose,
  bo lista usług na tym hoście może się zmienić.
  Reverse proxy hosta (Caddy) kieruje na ten port.
- **Lifecycle danych ≠ lifecycle kontenera** — bind mounts hosta:

```
/srv/pasnik/pgdata    → /var/lib/postgresql/data
/srv/pasnik/uploads   → /data/uploads      (zdjęcia + scratch kopii danych)
/srv/pasnik/backups   → /backups           (dumpy + kopie uploads)
/srv/pasnik/env/pasnik.env (chmod 600)        → env_file kontenera app
```

  Kontenery `app` i `backup` pracują jako **UID/GID 10001** (użytkownik
  `pasnik` w obu obrazach) — katalogi `uploads` i `backups` na hoście dostają
  `chown 10001:10001`, inaczej upload zdjęcia i zapis dumpu kończą się
  `Permission denied`. `pgdata` należy do użytkownika obrazu `postgres`
  (bez zmian).

- **Obrazy (stan faktyczny B17)** — `docker/Dockerfile`, multi-stage:
  `base` (zależności w `/opt/venv`, uv) → `dev` (hot reload) oraz
  `frontend-build` (node:22, `vite build`) → **`prod`** (`base` bez grupy dev,
  kod + migracje + `scripts/` + `dist` w `/app/static`, ADR-014; `USER
  pasnik`; `HEALTHCHECK` pytonowym one-linerem po `/api/v1/health`;
  start przez `docker/entrypoint.sh`: `uvicorn --workers $UVICORN_WORKERS
  --proxy-headers --log-level $LOG_LEVEL`, bez `--reload`). Budowanie:
  **`task build-prod`** → `pasnik-app:<git describe --tags --always --dirty>`
  + `pasnik-app:latest` oraz `pasnik-backup:<ta sama wersja>` + `:latest`.
  `APP_VERSION` wchodzi do obrazu jako build-arg (ta sama wartość co tag),
  więc pole `version` w health = tag obrazu. `.dockerignore` w korzeniu repo
  trzyma poza kontekstem `.env`, `backend/data`, testy, `node_modules`.
- **Kontrakt cache SPA** (ADR-009, „trzy sprawdzenia" z karty B18):
  `assets/*` (hash w nazwie) → `Cache-Control: public, max-age=31536000,
  immutable`; `index.html`, `sw.js`, `workbox-*.js`, `manifest.webmanifest`
  → `no-cache`. `manifest.webmanifest` wychodzi z typem
  `application/manifest+json`. Nieznane `/api/*` i `/uploads/*` zwracają
  kontraktowe 404 JSON, NIE `index.html` (`app/core/spa.py`).

## 2. Start aplikacji, migracje, healthcheck

- Kontener app przy starcie NIE migruje automatycznie; migracje uruchamia
  jawny krok `docker compose run --rm app alembic upgrade head` w procedurze
  update (świadoma decyzja: brak wyścigu i brak niespodzianek przy
  restarcie).
- `restart: unless-stopped`; graceful shutdown (Uvicorn) — compose
  `stop_grace_period: 30s`; `entrypoint.sh` robi `exec`, więc SIGTERM trafia
  w uvicorna (PID 1).
- **Healthcheck `GET /api/v1/health` (stan faktyczny B17, `app/core/health.py`)**:

  ```json
  {"status": "ok|degraded", "version": "<tag>", "checks": {"db": "ok|fail", "migrations": "ok|fail|skipped", "disk": "ok|fail"}}
  ```

  - `db` i `migrations` z JEDNEGO zapytania (`SELECT version_num FROM
    alembic_version`, limit 3 s): odpowiedź = baza żyje i wersja do porównania
    z head skryptów w obrazie (liczony ze `migrations/versions`, bez `env.py`);
    brak tabeli = baza żyje, `migrations: fail`; inny błąd/timeout = `db: fail`,
    `migrations: skipped`. Jeden timeout mieści się w `--timeout 5s` HEALTHCHECK-u;
  - `disk` — wolne miejsce na dysku katalogu uploadów ≥ `DISK_MIN_FREE_MB`
    (domyślnie 1024).
  - **`degraded` to nadal HTTP 200.** Healthcheck Dockera/compose testuje
    sam kod odpowiedzi: kontener, który odpowiada, jest `healthy` także
    niezmigrowany — restart w pętli niczego by nie naprawił (migracje są
    krokiem jawnym), a ukryłby przyczynę. `down` = brak odpowiedzi.
    Operator czyta TREŚĆ: `curl -s 127.0.0.1:8081/api/v1/health`.
  - Bez uwierzytelnienia i bez szczegółów infrastruktury (żadnych ścieżek,
    hostów, numerów rewizji). Checkiem jest wyłącznie to, co może paść
    w RUNTIME (baza, migracje, dysk) — ustawienie opcjonalnej funkcji nim
    nie jest (07_SECURITY §7).
- **Zimny start (obserwacja R2, potwierdzona R4) — świadomie przyjęty**:
  pierwsze żądanie po starcie procesu (`GET /plan/days`) trwa ~1,5 s
  (budowanie modeli Pydantica, plany zapytań PG), kolejne 30–50 ms. Przy
  `UVICORN_WORKERS=2` dotyczy to pierwszego żądania KAŻDEGO workera. Rozgrzewki
  w healthchecku nie ma: healthcheck ma być tani i pytać o stan, nie
  o wydajność, a jednorazowe 1,5 s po `compose up` nie uzasadnia kodu.
- **Rate limity a workery**: licznik slowapi jest w pamięci PROCESU, więc przy
  2 workerach realny sufit per IP to dwukrotność deklarowanej wartości
  (login 5/min → do 10/min; uploady 30/10 na minutę → 60/20). Twardą granicą
  logowania pozostaje blokada konta w bazie (07_SECURITY §2).
- **Za proxy**: uvicorn startuje z `--proxy-headers`; zaufane adresy proxy to
  `FORWARDED_ALLOW_IPS` (uvicorn czyta zmienną sam, domyślnie `127.0.0.1`).
  W compose połączenie od Caddy'ego przychodzi z bramy sieci dockera, nie
  z loopbacku — B18 wpisuje adres bramy albo `*` (port aplikacji jest
  opublikowany wyłącznie na 127.0.0.1 hosta, więc jedynym nadawcą jest
  proxy). Bez tego wszystkie żądania mają IP proxy, a limit 5/min/IP na
  `/auth/login` staje się limitem GLOBALNYM.

## 3. Backup i restore (stan faktyczny B17)

- **Co**: `pg_dump --format=custom --no-owner --no-privileges` + `tar.gz`
  katalogu uploadów **bez scratcha `transfer/`** (TTL 24 h, nie są to dane)
  + opcjonalnie kopia pliku env (`BACKUP_ENV_FILE`, domyślnie WYŁĄCZONA — env
  żyje na hoście; B18 decyduje, czy go montować do kontenera backupu)
  + `sha256` zestawu. Zestaw = wspólny stempel UTC:
  `pasnik-<YYYYmmddTHHMMSSZ>.dump`, `pasnik-<stempel>-uploads.tar.gz`,
  `[pasnik-<stempel>.env]`, `pasnik-<stempel>.sha256`. Pliki powstają jako
  `.tmp` i są przenoszone po sukcesie; `umask 077` ⇒ uprawnienia 600
  (backup = komplet danych rodziny, traktowany jak sekret).
- **Skrypty**: `docker/backup/backup.sh`, `docker/backup/restore.sh`,
  `docker/backup/cron-loop.sh`; retencja: `backend/scripts/backup_prune.py`
  (czysta stdlib, testowana pytestem) kopiowany do obrazu jako
  `/opt/backup/prune.py`. Obraz: `docker/backup/Dockerfile` = `postgres:17`
  (TA SAMA wersja co serwis `db` — `pg_dump`/`pg_restore` zawsze pasują do
  serwera) + `python3`, `USER 10001`.
- **Kiedy**: kontener `backup` (profil `backup`) uruchamia `cron-loop.sh`:
  codziennie o `BACKUP_AT` (domyślnie `03:00`, strefa `TZ`), wynik każdego
  przebiegu na stdout (`docker logs`), kod wyjścia ≠ 0 = linia `BŁĄD`.
  Decyzja B17: pętla `sleep`, nie crond — crond w `postgres:17` to dodatkowy
  demon, który nie przekazuje wyjścia zadań na stdout kontenera i gubi
  zmienne środowiskowe (jedyne źródło konfiguracji).
- **Retencja** — `7 dziennych + 4 tygodniowe`, semantyka borg-podobna
  (UTC): zostają WSZYSTKIE zestawy z 7 najnowszych dni kalendarzowych
  mających backup (ręczny backup przed migracją z §4 nie ginie przez nocny
  z tej samej doby) + najnowszy zestaw z każdego z 4 najnowszych tygodni ISO;
  reszta jest usuwana. Idempotentne; pliki spoza konwencji nazw nietykane.
  `python3 /opt/backup/prune.py --dir /backups --dry-run` pokazuje plan.
- **Dokąd**: `/srv/pasnik/backups` (bind mount) + kopia off-device wg D6
  (RĘCZNA, na dysk zewnętrzny — procedura w runbooku B18).
- **Restore** (`restore.sh <dump> [<uploads.tar.gz>] [--wipe-uploads]`,
  nieinteraktywny; gołe nazwy plików są szukane w `BACKUP_DIR`): sprawdza
  `sha256` zestawu (jeśli jest; `--ignore-missing` dla pominiętego `.env`) → `pg_restore
  --clean --if-exists --no-owner --no-privileges --exit-on-error` (działa na
  świeżej i na zapełnionej bazie; **app musi być zatrzymana** — otwarte sesje
  blokują DROP) → rozpakowanie uploadów (domyślnie dokłada, `--wipe-uploads`
  czyści katalog) → wypisuje `alembic_version` z dumpu. Następny krok
  runbooku ZAWSZE: `alembic upgrade head` (idempotentnie domiga do wersji
  obrazu), start app, smoke.
- **Targety Taskfile (stack testowy `docker/compose.test.yml`)**:
  `task build-prod`, `task test-stack-up` (db → migracje → app na
  `127.0.0.1:${PASNIK_TEST_PORT:-8081}`), `task backup`, `task restore --
  pasnik-<stempel>.dump [pasnik-<stempel>-uploads.tar.gz] [--wipe-uploads]`
  (gołe nazwy — `restore.sh` szuka ich w `BACKUP_DIR`),
  `task test-stack-down` (kasuje wolumeny), **`task backup-drill`**
  (`docker/backup/drill.sh`: seed → zdjęcie → backup → `down -v` → restore →
  porównanie liczności 18 tabel i liczby plików → smoke API). compose.prod
  (B18) używa TYCH SAMYCH obrazów i skryptów — podmienia porty/wolumeny na
  bind mounty `/srv/pasnik/*` i `env_file`.
- **Ostatni drill (B17, 2026-09-05, Docker Desktop/Windows, stack testowy)**:
  patrz Completion notes karty `BATCH_17` — wynik, czasy i rozmiary są tam
  zapisane po REALNYM wykonaniu; B18 powtarza drill na Odroidzie i wpisuje
  swój wynik do `OPERATIONS.md`.
- **Zajętość uploadów** (D10, rewizja R4): `backup.sh` loguje `du -sh`
  katalogu uploadów i katalogu backupów przy każdym przebiegu; `task
  uploads-report` (`python -m app.cli uploads-report`) wypisuje pliki BEZ
  referencji w bazie (i wiersze wskazujące brakujący plik) — WYŁĄCZNIE
  raport, nic nie kasuje. Oba trafiają do runbooku backupu (B18).
- Dodatkowo eksport logiczny aplikacji (moduł transfer) = backup „ludzki",
  niezależny od wersji PG.

## 4. Update / rollback

Update: `git pull` → `task build-prod` (tag = `git describe`) → backup przed
migracją (`task backup` / `backup.sh` — automatyczny krok skryptu B18) →
`docker compose run --rm app alembic upgrade head` → `compose up -d`.
Rollback: obrazy tagowane, `compose up` poprzedniego tagu (`PASNIK_IMAGE_TAG`);
migracje w dół tylko gdy downgrade przetestowany (każda migracja ma test down
— 03_DATABASE §1); w razie wątpliwości restore z backupu sprzed update
(`restore.sh`). Health po update ma pokazać `migrations: ok` — `fail` znaczy,
że krok migracji został pominięty.

## 5. Konfiguracja środowisk

| | dev (Windows/dowolne) | test (obraz prod lokalnie) | prod (Odroid) |
|---|---|---|---|
| compose | `compose.dev.yml` (hot reload, porty otwarte) | **`compose.test.yml`** (B17: czysta baza + `pasnik-app:<tag>` + profil `backup`) | `compose.prod.yml` (B18) |
| frontend | vite dev server + proxy /api | dist w obrazie app | dist w obrazie app |
| dane | wolumeny nazwane | wolumeny nazwane (`down -v` kasuje); backupy opcjonalnie na katalogu hosta `PASNIK_TEST_BACKUPS_DIR` | bind mounts /srv/pasnik |
| sekrety | .env lokalny | .env lokalny | pasnik.env chmod 600 |
| `APP_ENV` | dev | prod (wymuszone w compose) | prod |

Cała konfiguracja różnicująca środowiska idzie przez env
(`app/core/config.py`, komplet z opisem w `.env.example`): m.in. `APP_ENV`,
`LOG_LEVEL`, `UVICORN_WORKERS`, `FORWARDED_ALLOW_IPS`, `DISK_MIN_FREE_MB`,
`SPA_DIST_DIR`, `UPLOADS_DIR`, `IMAGE_MAX_UPLOAD_MB`, `TRANSFER_MAX_ZIP_MB`,
`REQUEST_MAX_BODY_MB`, `BACKUP_AT`, `BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY`,
`BACKUP_ENV_FILE`, `TZ`. Żadnych wartości prod zaszytych w kodzie.
Od BATCH_20 nie ma tu ANI JEDNEGO klucza do usługi zewnętrznej (D25).

**Użytkownik bazy (07_SECURITY §9) — stan faktyczny, NIEEGZEKWOWANE**: w compose
dev/test rola `POSTGRES_USER` jest rolą bootstrapową obrazu `postgres`, czyli
SUPERUSER. Aplikacja tego nie potrzebuje: migracje tworzą wyłącznie obiekty we
własnej bazie, a rozszerzenie `pg_trgm` jest w PG 13+ „trusted" (może je
założyć właściciel bazy). B18 ma w `compose.prod.yml` dodać skrypt
inicjalizacyjny (`/docker-entrypoint-initdb.d/`) zakładający rolę aplikacyjną
`NOSUPERUSER NOCREATEROLE` będącą właścicielem bazy i podać ją w
`DATABASE_URL`; `backup.sh` łączy się tą samą rolą (`--no-owner` w dumpie jest
po to, żeby restore nie zależał od nazwy roli).

## 6. Obserwowalność (na miarę domową)

Logi na stdout → `docker logs` / opcjonalnie loki później. W `APP_ENV=prod`
**cały stdout jest JSON-em**: structlog i rekordy stdlib (`uvicorn`,
`uvicorn.access`, biblioteki) przez `structlog.stdlib.ProcessorFormatter`
z tym samym rendererem; poziom `LOG_LEVEL` (aplikacja i uvicorn). Jedyny
wyjątek: dwie linie startowe SUPERVISORA uvicorna (`Uvicorn running on…`,
`Started parent process`) są zwykłym tekstem — pisze je proces nadrzędny,
który nigdy nie wykonuje `create_app()`; każda linia po nich jest JSON-em
(zmierzone na realnym logu obrazu prod: 2 z 32 linii). Publiczny
token listy maskowany w obu warstwach PRZED renderowaniem
(`/api/v1/public/lists/***`); silnik bazy z `hide_parameters=True` — patrz
07_SECURITY §8 (zweryfikowane grepem po realnym logu obrazu prod w B17).
`/health` (status, wersja, migracje, dostępność DB, dysk — §2). Kontener
`backup` loguje każdy przebieg i prune. Miejsce na przyszłość: prosty
uptime-check z zewnątrz (np. healthchecks.io ping z crona) — decyzja przy B18.

## 7. Wymagania sprzętowe (sanity)

Odroid H2 (4 rdzenie, ~8-32 GB RAM): PG + Uvicorn (2 workery) + Caddy hosta
to ułamek możliwości. Jedyny chwilowy peak CPU/IO to pakowanie i rozpakowanie
kopii danych rodziny ze zdjęciami — robione synchronicznie w żądaniu, ale
NA DYSKU (paczka nigdy nie wchodzi w całości do RAM) i w wątku puli, żeby nie
blokować pętli zdarzeń (bez Celery; ADR-001).
