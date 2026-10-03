# 09 — Deployment, backup i operacje

Docelowo (decyzja **D29**, ADR-017, 2026-10-03): **kontener LXC (Incus) `pasnik`
na Odroidzie 192.168.2.111**, wdrażany **Ansible + ansistrano** wg wzorca
`nc-tech-test-runner/deploy/`; baza w **istniejącym klastrze `postgres-apps`
(PostgreSQL 16) na 192.168.2.121**; TLS i domena na Caddym hosta .121 (D7,
`pasnik.cpt-sztos.com`). Docker na produkcji NIE występuje (D12 i ADR-002
zastąpione). Ten dokument opisuje **stan faktyczny po BATCH_17** (healthcheck,
skrypty backup/restore, konfiguracja przez env, obraz prod jako lokalny stos
testowy) oraz założenia WIĄŻĄCE dla **BATCH_18** (maszyna, deploy, runbooki).

## 1. Topologia produkcyjna (założenia wiążące)

```
Internet ─► Caddy na 192.168.2.121 (TLS, pasnik.cpt-sztos.com, D7)
             └─► 192.168.2.111:<APP_PORT>      proxy device Incusa; ufw: tylko z .121
                   └─► LXC `pasnik` (Debian 13, Python 3.13)
                         systemd `pasnik.service` → uvicorn 0.0.0.0:8000, User=pasnik
                         └─► 192.168.2.121:5432  postgres-apps (PG 16), baza ffp_db
Operator (WSL, ansible-core) ─► 192.168.2.111:2223 ─► LXC:22   (proxy device SSH)
```

- **Host LXC**: Odroid 192.168.2.111 z Incusem; obok stoi `nq-runner-poc`
  (SSH :2222), więc Paśnik dostaje INNY port SSH (propozycja **2223**) i port
  aplikacji, który B18 potwierdza `ss -ltnp` na .111 (propozycja **8081**).
  Kontener na `incusbr0` (NAT), z zewnątrz osiągalny wyłącznie przez proxy
  device'y. **Pułapka znana z runnera (dług O4)**: Docker na .111 ustawia
  `iptables -P FORWARD DROP` i odcina NAT Incusa — reguły `DOCKER-USER`
  dla `incusbr0` MUSZĄ być utrwalone, inaczej po restarcie hosta aplikacja
  nie dosięgnie bazy.
- **Proxy device aplikacji** w trybie `nat=true` (wymaga statycznego IPv4
  kontenera): uvicorn widzi wtedy prawdziwy adres Caddy'ego (.121) i
  `FORWARDED_ALLOW_IPS=192.168.2.121`. W trybie domyślnym (bez `nat`) Incus
  łączy się z kontenerem z loopbacku, więc zaufany musiałby być `127.0.0.1`,
  a jedyną barierą przed podrobionym `X-Forwarded-For` byłby ufw na .111 —
  dopuszczalne wyłącznie jako odnotowane odstępstwo (§2 „Za proxy").
- **Rozkład w LXC** (ansistrano):

```
/opt/pasnik/releases/<ts>/       kod release + backend/.venv + frontend/dist   (deploy:deploy)
/opt/pasnik/current -> releases/<ts>
/opt/pasnik/shared/uploads       UPLOADS_DIR (zdjęcia + scratch kopii danych)   (pasnik, 0750)
/opt/pasnik/shared/backups       BACKUP_DIR (dumpy + kopie uploads)             (pasnik, 0750)
/opt/pasnik/shared/uv-cache      cache uv między release'ami                    (deploy)
/etc/pasnik/pasnik.env           konfiguracja + sekrety (root:pasnik 0640)
/etc/systemd/system/pasnik{,-backup}.{service,timer}
```

  **Lifecycle danych ≠ lifecycle aplikacji**: dane relacyjne żyją w klastrze
  na .121, pliki w `shared/` — żaden release ich nie dotyka, a `keep_releases`
  kasuje wyłącznie stare katalogi kodu.
- **Użytkownicy LXC**: `root` (SSH tylko kluczem: provision, health), `deploy`
  (właściciel `releases/`, hasło zablokowane, sudoers WYŁĄCZNIE na
  `systemctl daemon-reload|start|stop|restart|is-active` dla `pasnik` i
  `pasnik-backup` oraz `pasnik-cli` jako `pasnik`), `pasnik` (system,
  nologin — z jego uprawnieniami działa aplikacja i backup).
- **Release (stan docelowy B18)**: frontend budowany LOKALNIE (`task fe-build`)
  i wysyłany jako `frontend/dist`; backend: `uv sync --frozen --no-dev` do
  `backend/.venv` w katalogu release (serwer potrzebuje PyPI; cache uv
  w `shared/`). Wersja = `git describe --tags --always --dirty` stemplowana
  lokalnie do pliku w release (rsync NIE wysyła `.git`) i podawana usłudze
  jako `APP_VERSION`, więc pole `version` w health = wdrożony release.
- **Kontrakt cache SPA** (ADR-009, „trzy sprawdzenia" z karty B18):
  `assets/*` (hash w nazwie) → `Cache-Control: public, max-age=31536000,
  immutable`; `index.html`, `sw.js`, `workbox-*.js`, `manifest.webmanifest`
  → `no-cache`. `manifest.webmanifest` wychodzi z typem
  `application/manifest+json`. Nieznane `/api/*` i `/uploads/*` zwracają
  kontraktowe 404 JSON, NIE `index.html` (`app/core/spa.py`). Bez zmian
  względem obrazu — serwuje to sam backend (ADR-014).
- **Obraz prod (stan faktyczny B17, NIE droga na produkcję)** — `docker/Dockerfile`
  target `prod` + `task build-prod` → `pasnik-app:<git describe>` i
  `pasnik-backup:<ta sama wersja>`, stack `docker/compose.test.yml`. Zostają
  jako lokalne narzędzie testu „aplikacja jak na produkcji" (`task
  test-stack-up`, `task backup-drill`), dopóki osobna decyzja ich nie usunie.

## 2. Start aplikacji, migracje, healthcheck

- **Usługa** `pasnik.service`: `User=pasnik`, `WorkingDirectory=/opt/pasnik/current/backend`,
  `EnvironmentFile=/etc/pasnik/pasnik.env`, `ExecStart` = uvicorn z venv
  release'u z tymi samymi flagami co `docker/entrypoint.sh` (`app.main:create_app
  --factory --host 0.0.0.0 --port 8000 --workers $UVICORN_WORKERS
  --timeout-worker-healthcheck 30 --proxy-headers --no-server-header
  --log-level …`), `Restart=on-failure`, `TimeoutStopSec=30` (graceful
  shutdown uvicorna), hardening `NoNewPrivileges`, `ProtectSystem=strict`,
  `ReadWritePaths=/opt/pasnik/shared/uploads`, `PrivateTmp`, `ProtectHome`.
- Aplikacja przy starcie NIE migruje. Migrację wykonuje hook ansistrano
  **przed** przełączeniem `current`: dump bazy → `alembic upgrade head`
  z NOWEGO release (ADR-017 pkt 6). Świadoma decyzja: brak wyścigu między
  workerami i brak niespodzianek przy restarcie.
- **Healthcheck `GET /api/v1/health` (stan faktyczny B17, `app/core/health.py`)**:

  ```json
  {"status": "ok|degraded", "version": "<release>", "checks": {"db": "ok|fail", "migrations": "ok|fail|skipped", "disk": "ok|fail"}}
  ```

  - `db` i `migrations` z JEDNEGO zapytania (`SELECT version_num FROM
    alembic_version`, limit 3 s): odpowiedź = baza żyje i wersja do porównania
    z head skryptów release'u (liczony ze `migrations/versions`, bez `env.py`);
    brak tabeli = baza żyje, `migrations: fail`; inny błąd/timeout = `db: fail`,
    `migrations: skipped`.
  - `disk` — wolne miejsce na dysku katalogu uploadów ≥ `DISK_MIN_FREE_MB`
    (domyślnie 1024).
  - **`degraded` to nadal HTTP 200.** Dlatego smoke po deployu MUSI czytać
    TREŚĆ: `status == "ok"` i `version == <release>` — sam kod 200
    przepuściłby nieudaną migrację albo odciętą bazę. Restart usługi przy
    `degraded` niczego nie naprawia (baza jest na innym hoście, migracje są
    krokiem jawnym), więc systemd go nie robi.
  - Bez uwierzytelnienia i bez szczegółów infrastruktury (żadnych ścieżek,
    hostów, numerów rewizji). Checkiem jest wyłącznie to, co może paść
    w RUNTIME (baza, migracje, dysk) — ustawienie opcjonalnej funkcji nim
    nie jest (07_SECURITY §7).
- **Zimny start (obserwacja R2, potwierdzona R4) — świadomie przyjęty**:
  pierwsze żądanie po starcie procesu trwa ~1,5 s, kolejne 30–50 ms; przy
  `UVICORN_WORKERS=2` dotyczy pierwszego żądania KAŻDEGO workera. Rozgrzewki
  w healthchecku nie ma.
- **Rate limity a workery**: licznik slowapi jest w pamięci PROCESU, więc przy
  2 workerach realny sufit per IP to dwukrotność deklarowanej wartości
  (login 5/min → do 10/min; uploady 30/10 na minutę → 60/20). Twardą granicą
  logowania pozostaje blokada konta w bazie (07_SECURITY §2).
- **Za proxy**: uvicorn startuje z `--proxy-headers`; zaufane adresy proxy to
  `FORWARDED_ALLOW_IPS` (uvicorn czyta zmienną sam, domyślnie `127.0.0.1`).
  Docelowo `192.168.2.121` (proxy device `nat=true`, §1). Bez poprawnej
  wartości wszystkie żądania mają IP proxy, a limit 5/min/IP na
  `/auth/login` staje się limitem GLOBALNYM; ze zbyt szeroką (`*`) każdy, kto
  dosięgnie portu na .111, podstawi sobie dowolny adres.

## 3. Backup i restore

- **Co** (stan faktyczny B17, bez zmian): `pg_dump --format=custom --no-owner
  --no-privileges` BAZY aplikacji (nigdy całego klastra) + `tar.gz` katalogu
  uploadów **bez scratcha `transfer/`** + opcjonalnie kopia pliku env
  (`BACKUP_ENV_FILE`, domyślnie WYŁĄCZONA) + `sha256` zestawu. Zestaw =
  wspólny stempel UTC: `pasnik-<YYYYmmddTHHMMSSZ>.dump`,
  `pasnik-<stempel>-uploads.tar.gz`, `[pasnik-<stempel>.env]`,
  `pasnik-<stempel>.sha256`. Pliki powstają jako `.tmp` i są przenoszone po
  sukcesie; `umask 077` ⇒ uprawnienia 600.
- **Skrypty**: `docker/backup/backup.sh`, `docker/backup/restore.sh`, retencja
  `backend/scripts/backup_prune.py` (czysta stdlib, testowana pytestem).
  Konfigurowane wyłącznie env (`PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`,
  `BACKUP_DIR`, `UPLOADS_DIR`, `PRUNE_SCRIPT`, `BACKUP_KEEP_*`) — B18 uruchamia
  je w LXC bez zmian semantyki (ewentualne przeniesienie katalogu = decyzja
  karty). Hasło przez `PGPASSFILE` (0600, właściciel `pasnik`), nie w env
  procesu.
- **Klient = wersja serwera**: Debian 13 ma klienta 17, a dump z `pg_dump` 17
  nie zawsze wraca na serwer 16 (`pg_restore --exit-on-error`). W LXC
  instalujemy **`postgresql-client-16` z PGDG** (rola dawnej zasady „obraz
  backupu = ta sama wersja co `db`").
- **Kiedy**: `pasnik-backup.timer` codziennie o 03:00 (`Persistent=true` —
  przebieg pominięty przez wyłączony kontener nadrabia się po starcie),
  `pasnik-backup.service` (`Type=oneshot`, `User=pasnik`); wynik w journald
  (`journalctl -u pasnik-backup`). Dodatkowo **dump przed każdą migracją**
  w hooku deployu (§4). `docker/backup/cron-loop.sh` przestaje być potrzebny
  na produkcji (zostaje w stacku testowym).
- **Retencja** — `7 dziennych + 4 tygodniowe`, semantyka borg-podobna
  (UTC): zostają WSZYSTKIE zestawy z 7 najnowszych dni kalendarzowych
  mających backup (dump przed migracją nie ginie przez nocny z tej samej doby)
  + najnowszy zestaw z każdego z 4 najnowszych tygodni ISO; reszta jest
  usuwana. Idempotentne; pliki spoza konwencji nazw nietykane.
- **Dokąd**: `/opt/pasnik/shared/backups` w LXC + kopia off-device wg D6
  (RĘCZNA, na dysk zewnętrzny — procedura w `OPERATIONS.md`). Kopia leżąca
  tylko na .111 nie chroni przed awarią dysku Odroida ani kradzieżą sprzętu.
- **Restore** (`restore.sh <dump> [<uploads.tar.gz>] [--wipe-uploads]`):
  sprawdza `sha256` → `pg_restore --clean --if-exists --no-owner
  --no-privileges --exit-on-error` do BAZY aplikacji (rolą-właścicielem;
  **usługa `pasnik` musi być zatrzymana** — otwarte sesje blokują DROP) →
  rozpakowanie uploadów → wypisuje `alembic_version`. Następny krok runbooku
  ZAWSZE: `alembic upgrade head`, start usługi, smoke.
- **Restore drill na produkcji**: do OSOBNEJ bazy w tym samym klastrze
  (`ffp_db_drill` — zakłada ją superuser `postgres-apps`, bo rola aplikacji nie
  ma `CREATEDB`), nigdy `--clean` na `ffp_db`; release uruchomiony ręcznie na
  innym porcie z `DATABASE_URL` drillu → health → smoke. Druga ścieżka: kopia
  danych rodziny (transfer) na czystą bazę.
- **Stack testowy (lokalnie, stan faktyczny B17)**: `task build-prod`,
  `task test-stack-up`, `task backup`, `task restore -- …`,
  `task test-stack-down`, `task backup-drill` (`docker/backup/drill.sh`).
  Ostatni drill B17 (2026-09-05, Docker Desktop/Windows) — Completion notes
  karty `BATCH_17`; B18 wpisuje wynik drillu z produkcji do `OPERATIONS.md`.
- **Zajętość uploadów** (D10, rewizja R4): `backup.sh` loguje `du -sh`
  katalogu uploadów i backupów; `pasnik-cli python -m app.cli uploads-report`
  wypisuje pliki BEZ referencji w bazie — WYŁĄCZNIE raport, nic nie kasuje.
- Dodatkowo eksport logiczny aplikacji (moduł transfer) = backup „ludzki",
  niezależny od wersji PG.

## 4. Update / rollback

Wszystko z WSL w katalogu `deploy/` (cienkie wrappery w Taskfile — karta B18):

- **Provision** (`playbook-provision.yml`, kanał `root`, rzadko): asercje
  maszyny (selftest z `lxc/provision.sh`), szablony unitów systemd,
  `pasnik.env` renderowany RAZ (`force: false`, sekrety z vaulta spoza repo),
  `pasnik-cli`. Niczego nie instaluje — maszynę buduje `provision.sh`.
- **Deploy** (`playbook-deploy.yml`, kanał `deploy`):
  1. pre-tasks: brak `CHANGE_ME`; lokalny `frontend/dist` istnieje i ma tę
     samą wersję co release (stale-dist guard); baza osiągalna z LXC;
  2. rsync do `releases/<ts>` (`--chmod=D755,F644`, `--delete-excluded`,
     bez `.git`, testów, `node_modules`, `.env*`, lokalnych uploadów);
  3. `after-update`: guard sekretów w release, `uv sync --frozen --no-dev`,
     import-smoke;
  4. `before-symlink`: **dump bazy** (asercja niepustego pliku) →
     `alembic upgrade head` z nowego release;
  5. symlink `current` → `systemctl restart pasnik` → health z parsowaniem
     JSON (`status: ok`, `version` = release) → `/api/docs` = 404.
- **Rollback** (`playbook-rollback.yml`): `ansistrano.rollback` do poprzedniego
  release + ten sam restart i health. Migracji NIE cofa — gdy nowy release
  migrował schemat: stop usługi → `restore.sh` dumpu sprzed migracji → rollback
  (downgrade wyłącznie przetestowany, 03_DATABASE §1).
- Health po deployu ma pokazać `migrations: ok` — `fail` znaczy, że krok
  migracji został pominięty.

## 5. Konfiguracja środowisk

| | dev (Windows/dowolne) | test (obraz prod lokalnie) | prod (LXC) |
|---|---|---|---|
| uruchomienie | `compose.dev.yml` (hot reload) | `compose.test.yml` (B17) | systemd `pasnik.service` |
| PostgreSQL | kontener `db`/`db-test` (**16** od B18 — parytet z prod) | kontener `db` (16 od B18) | `postgres-apps` PG 16 na .121, baza `ffp_db` |
| frontend | vite dev server + proxy /api | dist w obrazie | `frontend/dist` w release |
| dane | wolumeny nazwane | wolumeny nazwane | baza zewnętrzna + `/opt/pasnik/shared` |
| sekrety | .env lokalny | .env lokalny | `/etc/pasnik/pasnik.env` 0640 root:pasnik |
| `APP_ENV` | dev | prod (wymuszone w compose) | prod |

Cała konfiguracja różnicująca środowiska idzie przez env
(`app/core/config.py`, komplet z opisem w `.env.example`): m.in. `APP_ENV`,
`APP_VERSION`, `LOG_LEVEL`, `UVICORN_WORKERS`, `FORWARDED_ALLOW_IPS`,
`DISK_MIN_FREE_MB`, `SPA_DIST_DIR`, `UPLOADS_DIR`, `IMAGE_MAX_UPLOAD_MB`,
`TRANSFER_MAX_ZIP_MB`, `REQUEST_MAX_BODY_MB`, `BACKUP_*`, `TZ`. Poza obrazem
NIC nie ustawia się samo: `APP_ENV=prod`, `SPA_DIST_DIR=/opt/pasnik/current/frontend/dist`
i ABSOLUTNY `UPLOADS_DIR=/opt/pasnik/shared/uploads` muszą być w `pasnik.env`
(względna ścieżka rozwiązałaby się w katalogu release i znikała z każdym
deployem). Wartości bez spacji i cudzysłowów — plik czyta systemd, a `pasnik-cli`
nie może go interpretować inaczej (pułapka znana z runnera). Od BATCH_20 nie
ma tu ANI JEDNEGO klucza do usługi zewnętrznej (D25).

**Użytkownik bazy (07_SECURITY §9) — na produkcji SPEŁNIONE od D29**: rola
`ffp_user` jest właścicielem `ffp_db` i nie ma `SUPERUSER`, `CREATEDB` ani
`CREATEROLE` (inwentaryzacja 2026-10-03). Aplikacja tego nie potrzebuje:
migracje tworzą obiekty wyłącznie we własnej bazie, a `pg_trgm` jest w PG 13+
„trusted". `backup.sh` łączy się tą samą rolą (`--no-owner` w dumpie jest po
to, żeby restore nie zależał od nazwy roli). W dev/test rola nadal jest
bootstrapowa (SUPERUSER) — to nie jest produkcja.

## 6. Obserwowalność (na miarę domową)

Logi na stdout procesu → **journald** (`journalctl -u pasnik`,
`journalctl -u pasnik-backup`). W `APP_ENV=prod` **cały stdout jest JSON-em**:
structlog i rekordy stdlib (`uvicorn`, `uvicorn.access`, biblioteki) przez
`structlog.stdlib.ProcessorFormatter`; poziom `LOG_LEVEL`. Jedyny wyjątek: dwie
linie startowe SUPERVISORA uvicorna są zwykłym tekstem. Publiczny token listy
maskowany PRZED renderowaniem (`/api/v1/public/lists/***`, `/l/***`); silnik
bazy z `hide_parameters=True` — 07_SECURITY §8. Access log Caddy'ego na .121
pozostaje WYŁĄCZONY dla bloku Paśnika (D7 pkt 3). `/health` (status, wersja,
migracje, baza, dysk — §2). Miejsce na przyszłość: prosty uptime-check
z zewnątrz — decyzja przy B18.

## 7. Wymagania sprzętowe (sanity)

Odroid .111 dzieli zasoby między kontenery Incusa (runner ma limit 3 CPU /
6 GiB); Paśnik z 2 workerami potrzebuje ułamka tego — limity kontenera ustala
`create-incus.sh` w B18. PostgreSQL liczy się na .121 razem z netQArnerem.
Jedyny chwilowy peak CPU/IO to pakowanie i rozpakowanie kopii danych rodziny
ze zdjęciami — robione synchronicznie w żądaniu, ale NA DYSKU i w wątku puli
(bez Celery; ADR-001).
