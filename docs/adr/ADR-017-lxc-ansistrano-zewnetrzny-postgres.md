# ADR-017 — Produkcja w kontenerze LXC przez ansistrano; PostgreSQL we współdzielonym klastrze

Status: ACCEPTED (2026-10-03)

## Kontekst
ADR-002 i D12 zakładały produkcję jako `compose.prod.yml` na hoście z Caddy:
kontener `app` z obrazu prod, własny kontener `postgres:17` z danymi na bind
mountach `/srv/pasnik/*`, rollback tagiem obrazu. Do 2026-10-03 nic z tego nie
powstało na hoście (B18 `[ ]`). Właściciel prowadzi już dwie usługi według
innego wzorca i woli go od Dockera na serwerze (decyzja **D29**):

- `nc-tech-test-runner/deploy/` — kontener **Incus** z Debianem 13 na Odroidzie
  192.168.2.111, maszyna z `lxc/provision.sh`, kod przez **ansistrano**
  (rsync, `releases/<ts>` + symlink `current`), usługa **systemd**, dwa kanały
  SSH (`root` do provision/health, `deploy` z wąskim sudoers), journald;
- klaster **`postgres-apps`** (PostgreSQL 16, Docker na 192.168.2.121, port
  wystawiony w LAN), w którym właściciel przygotował bazę `ffp_db` z rolą
  `ffp_user` (NOSUPERUSER, właściciel bazy, baza pusta).

## Decyzja
1. **Runtime = kontener LXC (Incus) `pasnik` na 192.168.2.111**, Debian 13 —
   systemowy Python 3.13 spełnia `requires-python >=3.13`. Bez Dockera
   w kontenerze. Ruch: Caddy (.121, TLS, D7) → `192.168.2.111:<port>` (proxy
   device Incusa) → uvicorn w LXC. Port na .111 otwarty WYŁĄCZNIE dla .121.
2. **Wdrożenie = Ansible + ansistrano** (`ansistrano.deploy` 4.4.0,
   `ansistrano.rollback` 4.0.1, `deploy_via: rsync`) z katalogu `deploy/` w repo,
   uruchamiane z WSL. Rozkład: `/opt/pasnik/releases/<ts>`, `current`,
   `shared/` (uploady, backupy, cache uv). Konfiguracja i sekrety poza release:
   `/etc/pasnik/pasnik.env`.
3. **Release = katalog, nie obraz.** Frontend budowany LOKALNIE (`task fe-build`)
   i wysyłany rsynciem jako `frontend/dist`; zależności Pythona instalowane na
   serwerze do **venv per release** (`uv sync --frozen --no-dev`), więc rollback
   to przełączenie symlinka i restart usługi. Wersja (`APP_VERSION`) stemplowana
   lokalnie z `git describe` — rsync nie wysyła `.git`.
4. **Usługa systemd jako nieuprzywilejowany `pasnik`**, z hardeningiem
   (`ProtectSystem=strict`, zapis tylko do `shared/uploads`); flagi uvicorna te
   same co w `docker/entrypoint.sh` (`--factory`, `--proxy-headers`,
   `--timeout-worker-healthcheck 30`, `--no-server-header`, `UVICORN_WORKERS`).
5. **PostgreSQL = zewnętrzny, współdzielony klaster** `postgres-apps` (PG 16),
   osobna BAZA aplikacji (`ffp_db`) i rola-właściciel bez SUPERUSER. Paśnik nie
   zarządza klastrem (wersja, `pg_hba`, superuser należą do operatora .121).
6. **Migracje nadal JAWNE** — reguła z ADR-002 zostaje: w hooku ansistrano
   PRZED przełączeniem `current` idą kolejno: dump bazy, `alembic upgrade head`
   z nowego release. Aplikacja nigdy nie migruje przy starcie (inaczej niż
   netQArner, który migruje leniwie).
7. **Polityka numeracji migracji z ADR-002 bez zmian**: pierwszy wolny numer,
   `down_revision` z `alembic heads`.
8. **Backup = skrypty B17 + timer systemd w LXC** (03:00), klient `pg_dump`
   w wersji SERWERA (16, PGDG). Dump PER BAZA (`ffp_db`), więc `restore.sh
   --clean` nigdy nie dotyka innych lokatorów klastra.

## Konsekwencje
+ Wzorzec, który właściciel już zna i obsługuje (runner), zamiast drugiego
  sposobu wdrażania.
+ Rollback w sekundach (symlink); poprzednie release z gotowym venvem leżą
  na dysku.
+ Baza żyje niezależnie od kontenera aplikacji — ADR-002 „lifecycle danych ≠
  lifecycle aplikacji" jest spełnione mocniej niż wcześniej.
− Aplikacja i baza na DWÓCH hostach: awaria .121 albo LAN = `degraded`;
  restore i backup idą po sieci.
− Parytet wersji: dev/test muszą przejść z `postgres:17` na `postgres:16`.
− Serwer potrzebuje dostępu do PyPI (instalacja venv); `uv.lock` gwarantuje
  powtarzalność, cache uv w `shared/` skraca kolejne deploye.
− Docker na hoście .111 odcina NAT Incusa (`FORWARD DROP`) — reguły
  `DOCKER-USER` muszą być utrwalone, inaczej restart hosta odetnie bazę.
− Obraz prod (`docker/Dockerfile` target `prod`) i stack testowy
  `compose.test.yml` przestają być drogą na produkcję; zostają jako lokalne
  narzędzie testu obrazu, dopóki osobna decyzja ich nie usunie.

Zastępuje: **ADR-002** (w całości — punkty 6 i 7 przenoszą jego zasady,
które nadal obowiązują). Doprecyzowuje: **ADR-014** (decyzja rdzeniowa —
backend serwuje SPA i uploady z jednego originu — bez zmian; „jeden obraz do
wdrożenia i rollbacku" zastępuje „jeden katalog release").

## Aneks B18a — doprecyzowania z implementacji (2026-10-03)

Nie zmieniają decyzji, domykają to, co karta zostawiła do wyboru:

9. **Jedno źródło flag uvicorna**: `backend/scripts/serve.sh` (jedzie i do obrazu,
   i do release'u). `docker/entrypoint.sh` jest cienkim wywołaniem; unit LXC woła
   ten sam skrypt z `PATH` zaczynającym się od `backend/.venv/bin`. Wersja
   release'u (`APP_VERSION`) pochodzi z pliku `VERSION` (`PASNIK_VERSION_FILE`),
   więc `pasnik.env` — renderowany raz — jej nie niesie.
10. **Skrypty backupu** zostają w `docker/backup/` i `backend/scripts/`; provision
    kopiuje je do `/usr/local/lib/pasnik/`. Dump przed migracją to
    `systemctl start pasnik-backup` (ten sam unit co timer), a asercję nowego
    zestawu robi `pasnik-cli` jako `pasnik` — `deploy` nie czyta `shared/backups`.
11. **`pasnik-cli`** ładuje środowisko pętlą po `pasnik.env`, a nie `source`
    i nie `systemd-run` (ten wymaga roota, a sudoers daje deployowi wyłącznie
    `-u pasnik pasnik-cli`). Równoważność z `EnvironmentFile=` zapewnia
    ograniczony format pliku (bez spacji i cudzysłowów — test).
12. **Port aplikacji na .111 zamyka `DOCKER-USER`, nie ufw**: proxy device
    `nat=true` robi DNAT, który omija INPUT. Reguła DROP na pozycji 1 łańcucha
    (`deploy/lxc/host-firewall.sh`) jest warunkiem bezpieczeństwa
    `FORWARDED_ALLOW_IPS=192.168.2.121`.
13. **Release = biała lista rsynca** (`backend/`, `frontend/dist/`, `VERSION`),
    bez `docker/`, `docs/`, `deploy/`, testów i danych; strażnik stechłego dista
    porównuje `git describe` z `dist/build-info.json` (vite).
