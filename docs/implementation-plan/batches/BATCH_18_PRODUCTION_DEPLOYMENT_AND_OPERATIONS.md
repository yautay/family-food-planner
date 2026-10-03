# BATCH_18 — PRODUCTION_DEPLOYMENT_AND_OPERATIONS

Klasa: PROD · Zależności: B17 + B19 + B20 · Bramki decyzji: **D6, D7
(2026-09-05) i D29 (2026-10-03) — ZATWIERDZONE** · Szacunek rozmiaru: L
(podział dozwolony: **18a** maszyna + deploy + smoke, **18b** backup + drill +
`OPERATIONS.md`)

> **Karta PRZEPISANA 2026-10-03 po decyzji D29** (ADR-017). Poprzednia wersja
> zakładała `compose.prod.yml` z własnym `postgres:17` na hoście z Caddym (D12)
> — nic z niej nie powstało na hoście. Teraz: kontener **LXC (Incus)** na
> Odroidzie **192.168.2.111**, wdrożenie **Ansible + ansistrano** wg wzorca
> `C:\dev\nc-tech-test-runner\deploy\`, baza w **istniejącym klastrze
> `postgres-apps` (PG 16) na 192.168.2.121**. Ustalenia R4 dotyczące Caddy'ego,
> PWA, D10 i drillu zostały przeniesione niżej bez zmian treści.

## Goal

Paśnik działa produkcyjnie pod `https://pasnik.cpt-sztos.com`: aplikacja jako
usługa systemd w kontenerze LXC `pasnik` na .111, dane w bazie `ffp_db`
klastra `postgres-apps` na .121, TLS na Caddym .121. Deploy i rollback jednym
playbookiem z WSL, dump przed każdą migracją, backup nocny timerem systemd,
kopia off-device wg D6, **restore drill wykonany realnie**, a `docs/OPERATIONS.md`
pozwala właścicielowi operować systemem bez tej sesji.

## Context

Po B17 istnieją: healthcheck z treścią (`status`/`version`/`checks`), skrypty
`backup.sh`/`restore.sh` + `backup_prune.py` (env-driven), konfiguracja
w całości przez env, flagi uvicorna w `docker/entrypoint.sh`, obraz prod
i stack testowy (zostają jako lokalny test obrazu — ADR-017). NIE istnieją:
katalog `deploy/`, kontener LXC, unity systemd, `OPERATIONS.md`, blok Caddy
dla aplikacji. Batch pracuje na REALNYCH hostach właściciela (.111 i .121) —
kroki na hostach wykonuje albo potwierdza właściciel.

Wymagane lektury przed startem:

- `implementation_prompt.md` + ta karta w całości.
- **`docs/architecture/09_DEPLOYMENT_AND_OPERATIONS.md` — WIĄŻĄCY w całości**
  (topologia, rozkład `/opt/pasnik`, migracje w hooku, backup, deploy/rollback,
  env, journald).
- **ADR-017** i **D29** (02_DECISIONS) — co zastąpiło D12/ADR-002 i dlaczego.
- `docs/architecture/07_SECURITY_DESIGN.md` §3 (HSTS na proxy), §7 (env,
  `FORWARDED_ALLOW_IPS`), §9 (rola bazy, współdzielony klaster).
- 02_DECISIONS: D6, D7 (+ korekta celu proxy w D29), D10.
- **Wzorzec** (czytać przed pisaniem czegokolwiek w `deploy/`):
  `C:\dev\nc-tech-test-runner\deploy\**` (README, `group_vars/all.yml`,
  `playbook-*.yml`, `tasks/*.yml`, `templates/*.j2`, `lxc/provision.sh`,
  `lxc/create-incus.sh`), `docs\technical\{poc-lxc,deploy}.md` oraz
  `docs\implementation-plan\13_DEBT_AND_OPERATOR_TASKS.md` (długi, których
  NIE powielamy) i gałąź `feature/batch-10-observability` (poprawki
  `--check --diff` i cytowania env). Dla kroków aplikacja + PostgreSQL:
  `C:\dev\qa-test-toc\deploy-pre-prod\tasks\{after-update,before-symlink,restart-and-health,assert-external-infra}.yml`.

**Inwentaryzacja klastra `postgres-apps` (2026-10-03, wykonał właściciel):**
PostgreSQL **16.15** (obraz `postgres:16`, PGDG na Debianie 13), `listen_addresses
= *`, port wystawiony na `192.168.2.121:5432`. Baza **`ffp_db`**, właściciel
**`ffp_user`** (LOGIN, bez SUPERUSER/CREATEDB/CREATEROLE), pusta: schemat
`public` (właściciel `pg_database_owner`) bez tabel, z rozszerzeń tylko
`plpgsql`. `pg_hba`: `trust` wyłącznie lokalnie, `host all all all
scram-sha-256` dla reszty. Inni lokatorzy: `netqarner` (210 MB, aplikacja
netQArner) i `netqarner_db` (pozostałość). **Wnioski**: migracja `0004`
założy `pg_trgm` rolą właściciela (rozszerzenie trusted); `backup.sh`/
`restore.sh` działają na całej BAZIE bez zmian; drill potrzebuje bazy
założonej przez superusera; hasło `ffp_user` zna właściciel — wchodzi do vaulta,
nigdy do repo.

**Ustalenia przeniesione z REVIEW R4 (treść bez zmian, korekta celu proxy):**

1. **D6** — kopia off-device RĘCZNA na dysk zewnętrzny: do `OPERATIONS.md`
   PROCEDURA (co, skąd, jak sprawdzić kompletność), nie skrypt. Runbook mówi
   wprost, przed czym to NIE chroni (kopia tylko na .111 ≠ ochrona przed
   awarią dysku czy kradzieżą). Krok kopiowania zostaje miejscem do
   wypełnienia (NAS/chmura bez zmiany kodu).
2. **D7** — domena `pasnik.cpt-sztos.com`, Caddy jako usługa systemowa na
   **.121**, JEDEN `Caddyfile` bez `import`. Cel proxy od D29:
   **`reverse_proxy 192.168.2.111:<APP_PORT>`** (nie loopback). Pułapki:
   (a) blok `pasnik.cpt-sztos.com` JUŻ ISTNIEJE i serwuje landing
   (`root * /srv/sftp/ftpuser/files/landing`) — PODMIENIAMY go, nie dopisujemy
   drugiego; (b) port 8080 to Pi-hole (dotyczy .121; port na .111 potwierdzić
   `ss -ltnp` na .111); (c) brak `import` — edycja w miejscu;
   (d) **`log` zapisałby publiczny token listy** — nie włączamy, weryfikacja
   grepem po realnym logu. Limit ciała: Caddy domyślnie nie ogranicza —
   potwierdzić realnym wgraniem paczki 100 MB. HSTS: dołożyć z KRÓTKIM
   `max-age`. Wzór: istniejący blok `toc.cpt-sztos.com`. Przeładowanie:
   `caddy validate --config /etc/caddy/Caddyfile` → `systemctl reload caddy`.
3. **D10** — bez automatu kasującego; runbook: zajętość
   `/opt/pasnik/shared/uploads` (loguje `backup.sh`) + `uploads-report`.
   **Na dev raport pokazuje 13 osieroconych PDF-ów w `uploads/import-pdf/` —
   decyzja właściciela (2026-09-12): zostają. Nie proponuj kasowania.** Na
   produkcji ich nie będzie (uploady startują puste), chyba że właściciel
   przeniesie katalog z dev — wtedy jadą do backupów.
4. **Drill obejmuje DRUGĄ ścieżkę**: kopia danych (transfer) → czysta baza →
   import. Plik nie ma haseł ani tokenów publicznych, ale jest danymi
   osobowymi. Po imporcie instancji hasła nadaje ADMIN (`create-admin` +
   `PATCH /admin/users/{id}`).
5. **Zimny start ~1,5 s** pierwszego żądania każdego workera — przyjęty
   (09 §2), smoke nie mierzy czasu pierwszego żądania.

**Stan FAKTYCZNY, na którym batch stoi (nie pisać od nowa):**

- Flagi uvicorna i mapowanie `LOG_LEVEL` → `docker/entrypoint.sh`. Unit
  systemd ma uruchamiać TĘ SAMĄ logikę — wydziel ją do skryptu w repo
  (np. `deploy/files/pasnik-serve.sh`) albo wołaj `entrypoint.sh` z venv
  release'u; NIE kopiuj flag w drugie miejsce.
- `Settings.env_file=(".env","../.env")` względem katalogu roboczego —
  w LXC konfiguracja przychodzi WYŁĄCZNIE z `EnvironmentFile`; w katalogu
  release nie może leżeć żaden `.env` (guard w `after-update`).
- `SPA_DIST_DIR`, `UPLOADS_DIR`, `APP_ENV`, `APP_VERSION` ustawiał obraz —
  w LXC muszą przyjść z `pasnik.env` (+ `APP_VERSION` z pliku release).
  `UPLOADS_DIR` ABSOLUTNY. `MIGRATIONS_DIR` w `core/health.py` liczony
  względem pakietu — release musi zachować układ `backend/{app,migrations}`.
- Cookies prod `__Host-*` wymagają HTTPS — smoke logowania przez domenę,
  nie przez `curl http://…:8000`.
- `python -m app.cli create-admin` czyta hasło z TTY (`getpass`) albo
  `PASNIK_ADMIN_*`; idempotentne. `uploads-report` czyta `UPLOADS_DIR`.
- Weryfikacja SW na realnej domenie: `node frontend/e2e/tools/sw-check.mjs
  https://pasnik.cpt-sztos.com`.

**Warunek z B12 (PWA, ADR-009) — HTTPS jest funkcjonalnością.** Po wdrożeniu,
na PRAWDZIWEJ domenie: (1) `GET /manifest.webmanifest` → 200,
`application/manifest+json`; (2) `GET /sw.js` → 200, typ JavaScript, `no-cache`;
(3) na telefonie: aktywny service worker i dostępny prompt instalacji.

## Stages

**Część 18a — maszyna, deploy, smoke**

1. **Parytet PostgreSQL 16**: `docker/compose.dev.yml` (`db`, `db-test`),
   `docker/compose.test.yml` i `docker/backup/Dockerfile` → `postgres:16`.
   `task check` zielony na 16 (w tym `pg_trgm`/`similarity()` w testach
   wyszukiwania); odnotuj, czy coś zależało od 17. Baza dev wstaje pusta
   (nowy wolumen danych) — odtworzenie: `task db-migrate` + `create-admin`
   + `db-seed-demo`, zgoda właściciela na reset przed wykonaniem.
2. **Maszyna — `deploy/lxc/`** (wzór: runner):
   - `provision.sh` (root, idempotentny, kończy się selftestem
     `/usr/local/sbin/pasnik-selftest`): Debian 13; pakiety `python3 rsync
     openssh-server ca-certificates sudo curl` + **uv** w wersji z
     `docker/Dockerfile` + **`postgresql-client-16` z repozytorium PGDG**;
     użytkownicy `deploy` (hasło zablokowane, klucz operatora) i `pasnik`
     (system, nologin); katalogi i uprawnienia wg 09 §1; sudoers
     `/etc/sudoers.d/60-pasnik-deploy` (sprawdzony `visudo -cf`):
     `systemctl daemon-reload` oraz `start|stop|restart|is-active` dla
     `pasnik` i `start` dla `pasnik-backup`, plus `-u pasnik
     /usr/local/bin/pasnik-cli`; sshd tylko klucze, root `prohibit-password`.
     `deploy` NIE jest w grupie `sudo`.
   - `create-incus.sh`: `incus launch images:debian/13 pasnik` z limitami,
     statyczny IPv4 na `incusbr0`, proxy device SSH `0.0.0.0:2223→22` i
     aplikacji `0.0.0.0:<APP_PORT>→8000` z **`nat=true`**, push + uruchomienie
     `provision.sh`, snapshot `czysty`, `--recreate`. **Wypisuje odcisk klucza
     hosta** (dług nr 4 runnera — pierwszy provision nie może akceptować
     dowolnego klucza).
   - `lxc/README.md`: kroki na hoście .111 — ufw (port aplikacji tylko
     z 192.168.2.121, SSH 2223 z LAN), **utrwalone reguły `DOCKER-USER` dla
     `incusbr0`** (`iptables-persistent` albo unit), sprawdzenie
     `ss -ltnp` przed wyborem portów.
3. **Ansible — `deploy/`** (układ 1:1 z runnerem): `ansible.cfg`,
   `requirements.yml` (ansistrano.deploy 4.4.0, ansistrano.rollback 4.0.1,
   ansible.posix ≥1.5.4), `inventories/prod/hosts.yml` (.111:2223,
   `ansible_ssh_common_args` z osobnym plikiem kluczy hosta),
   `group_vars/all.yml` (architektura + `ansistrano_*` + NAZWY sekretów
   z sentinelem `CHANGE_ME`), `group_vars/prod.yml` (wartości nieskryte:
   host bazy, nazwa bazy/roli, port, domena), `.gitignore` `deploy/.ansible/`.
   Sekrety (`vault_db_password`, `vault_secret_key`) w vaulcie POZA repo:
   `-e @~/pasnik-prod.yml --ask-vault-pass`, potrzebne tylko w provision.
4. **Provision** (`playbook-provision.yml`, kanał root): `assert-machine`
   (selftest, Python 3.13, `pg_dump --version` = 16, uprawnienia katalogów,
   brak Dockera w LXC), szablony `pasnik.service`, `pasnik-backup.{service,timer}`,
   `pasnik.env` (`force: "{{ force_env }}"`, domyślnie false; `no_log`;
   asercja, że ŻADNA zmienna nie została `CHANGE_ME`), `PGPASSFILE` dla
   `pasnik`, `/usr/local/bin/pasnik-cli`; `daemon-reload`, `enable` bez
   startu (`current` jeszcze nie istnieje); wypis TODO dla operatora.
   **Wzór unitu**: 09 §2 (User=pasnik, EnvironmentFile, hardening,
   `ReadWritePaths` tylko na uploads). **`pasnik-cli`** uruchamia polecenie
   jako `pasnik` w `current/backend` z TYM SAMYM środowiskiem co usługa
   (`systemd-run --uid=pasnik --wait --pty -p EnvironmentFile=…` albo
   równoważnie) — NIE przez `source` pliku env w bashu (dług nr 1 runnera).
5. **Deploy** (`playbook-deploy.yml`, wzór 09 §4):
   - pre-tasks (localhost): sentinel `CHANGE_ME`, `frontend/dist/index.html`
     istnieje, plik wersji release = `git describe --tags --always --dirty`
     i zgadza się ze znacznikiem w `frontend/dist` (stale-dist guard, wzór
     TOC — vite stempluje wersję w build), `task secrets-scan` czysty;
   - pre-tasks (root): selftest, `assert-external-infra` (`pg_isready
     -h 192.168.2.121` + `select 1` rolą aplikacji z LXC);
   - rsync: `--chmod=D755,F644`, `--delete-excluded`, wykluczenia runnera
     + `frontend/node_modules`, `frontend/src`, `frontend/e2e`, `tests`,
     `docker`, `docs`, `.env*`, `backend/data`, `deploy/.ansible`;
   - `after-update.yml`: guard sekretów w release (najpierw kasuje release,
     potem assert — wzór runnera), `uv sync --frozen --no-dev` w
     `release/backend` z `UV_CACHE_DIR=shared/uv-cache`, import-smoke
     `python -c "import app.main"`;
   - `before-symlink.yml`: dump bazy przez `sudo systemctl start
     pasnik-backup` (albo `pasnik-cli` z `backup.sh` — wybór uzasadnić)
     i asercja nowego, niepustego zestawu; potem `pasnik-cli alembic upgrade
     head` z NOWEGO release (przekazanie ścieżki release, bo `current` jeszcze
     wskazuje stary);
   - `restart-and-health.yml` (wspólny z rollbackiem): `sudo -n systemctl
     restart pasnik` → `is-active` → `GET http://127.0.0.1:8000/api/v1/health`
     z retry i **asercją na treść** `status == "ok"` oraz `version` = release;
     `GET /api/docs` → 404; przy porażce `journalctl -u pasnik -n 50`
     (kanał root). Wszystkie read-only taski z `check_mode: false`, a rola
     ansistrano pomijana w `--check` (poprawka z gałęzi B10 runnera).
   - Pierwszy deploy na pustą bazę: migracje `0001…head` + `pg_trgm`;
     następnie `pasnik-cli python -m app.cli create-admin` interaktywnie.
6. **Rollback** (`playbook-rollback.yml`): asercja ≥2 release,
   `ansistrano.rollback`, `restart-and-health.yml`; runbook restore przy
   rollbacku przez migrację (09 §4).
7. **Caddy (.121)**: `deploy/templates/caddy-vhost.example.j2` renderowany
   lokalnie/do pliku przykładowego; podmiana bloku w `/etc/caddy/Caddyfile`
   wykonuje WŁAŚCICIEL wg D7 (wyżej).
8. **Taskfile**: cienkie wrappery `task deploy`, `task rollback`,
   `task provision` (wołają `wsl … ansible-playbook -i inventories/prod …`
   w `deploy/`; `task deploy` zależy od `fe-build`). Opis wymagań operatora
   (WSL, venv `ansible-core>=2.16,<2.18`, `ansible-galaxy install -r
   requirements.yml`) w `deploy/README.md` i CLAUDE.md §3.
9. **Wykonanie z właścicielem**: `create-incus.sh` → host .111 (ufw,
   DOCKER-USER) → provision → deploy → create-admin → Caddy → smoke przez
   HTTPS (login, plan dnia, generacja listy, publiczny link z telefonu,
   upload zdjęcia, trzy sprawdzenia PWA) → deploy no-op → rollback → deploy.

**Część 18b — backup, drill, dokumentacja**

10. **Backup**: `backup.sh`/`restore.sh`/`backup_prune.py` uruchamiane
    w LXC (lokalizację w repo wybrać i uzasadnić: zostają w `docker/backup/`
    i są rsyncowane, albo przenosiny do `deploy/files/` z aktualizacją
    stacku testowego); `pasnik-backup.timer` 03:00 `Persistent=true`;
    przebieg realny (wymuszony `systemctl start` + nocny), prune nie usuwa
    świeżych, wynik w journald.
11. **Off-device (D6)**: procedura ręczna w `OPERATIONS.md` (`incus file
    pull` na .111 → dysk zewnętrzny, weryfikacja `sha256sum -c`).
12. **RESTORE DRILL (realnie)**: superuser `postgres-apps` zakłada
    `ffp_db_drill` (właściciel `ffp_user`) → `restore.sh` z `PGDATABASE=ffp_db_drill`
    → `alembic upgrade head` → release uruchomiony ręcznie na innym porcie
    z `DATABASE_URL` drillu → health `ok` + smoke API → `DROP DATABASE
    ffp_db_drill`. Druga ścieżka: kopia danych rodziny na czystą bazę
    (ustalenie R4 pkt 4). Data, czasy, rozmiary → `OPERATIONS.md`.
13. **Reboot .111**: restart hosta → LXC wstaje, usługa wstaje, health `ok`
    (dowód utrwalenia `DOCKER-USER`).
14. **Dokumentacja i domknięcie**: `docs/OPERATIONS.md`, `deploy/README.md`,
    09_DEPLOYMENT do stanu faktycznego, CLAUDE.md (sekcja „Deploy" + zakaz
    dotykania produkcji poza runbookami), PROGRESS, commit `batch(18): ...`.

## Database / migrations

- Brak zmian schematu w TYM batchu. Pierwsza migracja produkcyjna i każda kolejna =
  hook `before-symlink` po dumpie (ADR-017 pkt 6), NIGDY start aplikacji.
  **B21 (przepisy `global`) dokłada migracje `0017` i `0018`**, które jadą tym samym
  deployem: `0017` to `ALTER TYPE entity_scope ADD VALUE` (w `autocommit_block`,
  wykonalne rolą `ffp_user` jako właścicielem typu) i jest **NIEODWRACALNE** —
  `downgrade` to no-op, a wiersze z `scope='global'` po cofnięciu do `0016` są
  nieczytelne dla starego kodu. Rollback release'u PO migracji `0017` = restore dumpu
  z deployu albo zmiana zakresu tych wierszy przed cofnięciem; runbook
  (`deploy/README.md`, rozdział rollback) ma to jedno zdanie nazwać wprost.
- Baza `ffp_db`/rola `ffp_user` — istniejące, nie tworzymy ani nie zmieniamy
  ich atrybutów; jedyne DDL poza migracjami to `CREATE/DROP DATABASE
  ffp_db_drill` superuserem (drill, wykonuje właściciel).
- Dev/test: `postgres:16` (Stage 1); `EXPECTED_ENUM_TYPES`/`EXPECTED_TABLES`
  bez zmian.

## Backend / Operacje

Brak nowych endpointów ani zmian w `app/`. Deliverables:

| Artefakt | Treść |
|---|---|
| `deploy/lxc/{provision.sh,create-incus.sh,README.md}` | maszyna + host .111 |
| `deploy/{ansible.cfg,requirements.yml,README.md}` | kontroler i runbook Ansible |
| `deploy/inventories/prod/hosts.yml`, `deploy/group_vars/{all,prod}.yml` | środowisko |
| `deploy/playbook-{provision,deploy,rollback}.yml` + `deploy/tasks/*.yml` | wzór 09 §4 |
| `deploy/templates/{pasnik.service,pasnik-backup.service,pasnik-backup.timer,pasnik.env,pasnik-cli.sh,caddy-vhost.example}.j2` | runtime |
| skrypt startu usługi (wydzielony z `docker/entrypoint.sh`) | jedno źródło flag uvicorna |
| `Taskfile.yml` | `deploy`, `rollback`, `provision` |
| `docs/OPERATIONS.md` | runbooki (niżej) |

`OPERATIONS.md` — dla właściciela-człowieka, komendy do wklejenia
i oczekiwany wynik: instalacja od zera (Incus → provision → pierwszy deploy
→ admin → Caddy), deploy, rollback (z migracją i bez), backup i restore,
off-device, drill (sekcja „ostatni drill: data, czas, wynik"), dodanie
użytkownika, rotacja hasła bazy (vault → `force_env` → restart), diagnoza:
nie wstaje (`journalctl`), 500, `degraded` (baza na .121 / migracje / dysk),
pełny dysk, LXC bez sieci po restarcie hosta (DOCKER-USER), zmiana klucza
hosta po `--recreate`.

## Frontend

- Brak zmian kodu poza ewentualnym stemplem wersji w buildzie potrzebnym
  do stale-dist guardu (jeśli build go nie ma — mała zmiana w
  `vite.config.ts`, testowana `fe-build`).
- Weryfikacja z produkcji: PWA instalowalna, lista offline po pierwszym
  otwarciu, publiczny link `/l/:token` przez HTTPS z telefonu.

## Security

- Sekrety (hasło `ffp_user`, `SECRET_KEY`) WYŁĄCZNIE w vaulcie poza repo
  i w `/etc/pasnik/pasnik.env` (`root:pasnik` 0640) oraz `PGPASSFILE` 0600;
  rsync i guard release'u wykluczają/odrzucają pliki sekretów.
- Usługa jako `pasnik` z hardeningiem systemd; `deploy` ma sudo WYŁĄCZNIE na
  wymienione `systemctl` i `pasnik-cli`; root tylko kluczem.
- Port aplikacji na .111 osiągalny wyłącznie z .121 (ufw), weryfikacja
  skanem z innej maszyny w LAN; `FORWARDED_ALLOW_IPS=192.168.2.121`
  (`*` zabronione — 07 §7).
- Baza: rola bez uprawnień poza `ffp_db`; zawężenie `pg_hba` do adresu
  .111 — REKOMENDACJA w `OPERATIONS.md`, decyzja operatora klastra.
- Publiczny token: zero w access logu Caddy'ego (log wyłączony), w journald
  maskowany — grep po realnych logach po smoke z publicznym linkiem.
- Hasło pierwszego admina interaktywnie (TTY przez `pasnik-cli`), nie
  w historii shella ani w argumentach procesu.
- `--check --diff` i każdy task z sekretem z `no_log: true` (dług nr 3
  runnera).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3.

- **Required**: SKILL-SEC
- **Recommended**: SKILL-BE
- **Review**: SKILL-SECREV, SKILL-REVIEW

## Tests

- `task check` zielony **na `postgres:16`**.
- Nowy `tests/unit/test_deploy_config.py` (marker `unit`, wzór
  `tests/test_deploy.py` runnera): wykluczenia rsync obejmują pliki sekretów
  i `.env*`; każda zmienna wymagana przez `Settings` ma wpis w
  `pasnik.env.j2`; szablon env nie zawiera wartości ze spacją ani
  cudzysłowem; flagi uvicorna mają jedno źródło.
- `ansible-playbook --syntax-check` dla trzech playbooków; `--check --diff`
  deployu kończy się bez `failed`.
- Realnie (wynik w Completion notes): provision, pierwszy deploy, smoke
  HTTPS, deploy no-op, rollback, deploy z powrotem, backup wymuszony i nocny,
  drill (obie ścieżki), reboot .111, skan portu z LAN, grep logów na token.
- Zatrzymanie dostępu do bazy (np. ufw na .121 albo zła wartość w env na
  chwilę w kopii) → health `degraded`, usługa żyje (obserwacja, opis).

## Acceptance Criteria

1. `https://pasnik.cpt-sztos.com` działa; health `ok` z `version` = wdrożony
   release; SPA, API i uploady serwowane przez usługę w LXC.
2. Port aplikacji na .111 odpowiada wyłącznie dla .121; SSH do LXC tylko
   kluczem; usługa NIE działa jako root.
3. Deploy (dump → migracja → symlink → restart → health z treścią) i rollback
   przećwiczone realnie; dump przed migracją istnieje w `shared/backups`.
4. Backup nocny wykonał się z timera; komplet zestawu + prune; procedura
   off-device wg D6 opisana i raz wykonana.
5. **Restore drill przeszedł realnie** (pg_restore do `ffp_db_drill` + kopia
   danych rodziny) — udokumentowany w `OPERATIONS.md`.
6. Restart hosta .111 → aplikacja wraca sama i widzi bazę.
7. PWA instaluje się z produkcji; publiczny link działa bez logowania; tokenu
   nie ma w logach Caddy'ego ani journald.
8. Zero sekretów w repo (`task secrets-scan` + grep); `pasnik.env` 0640
   root:pasnik, `PGPASSFILE` 0600.
9. `task check` zielony na PG 16; `OPERATIONS.md` kompletny; PROGRESS,
   09_DEPLOYMENT i CLAUDE.md zgodne ze stanem faktycznym.

## Out of Scope

- Zmiany w klastrze `postgres-apps` (wersja, `pg_hba`, superuser) i w
  netQArnerze — tylko rekomendacje.
- Usunięcie obrazu prod / `compose.test.yml` / `task build-prod` — zostają
  jako lokalny test obrazu do osobnej decyzji.
- CI uruchamiające deploy; środowisko pre-prod/staging (inventory tylko `prod`).
- Zewnętrzny uptime-check, Loki, 2FA (D8), retencja automatyczna (D10).
- Jakiekolwiek zmiany funkcjonalne aplikacji.

## Expected files/modules

- `deploy/**` (tabela wyżej), `Taskfile.yml`, `.gitignore`
- `docker/compose.dev.yml`, `docker/compose.test.yml`,
  `docker/backup/Dockerfile` (PG 16), ewentualnie `docker/entrypoint.sh`
  (wydzielenie skryptu startu)
- `tests/unit/test_deploy_config.py`
- `docs/OPERATIONS.md` (NOWY — jedyny dozwolony nowy dokument poza
  `deploy/README.md` i `deploy/lxc/README.md`)
- `docs/architecture/09_DEPLOYMENT_AND_OPERATIONS.md`, `CLAUDE.md`,
  `docs/implementation-plan/PROGRESS.md`
- Poza repo: kontener `pasnik` na .111 (`/opt/pasnik`, `/etc/pasnik`),
  reguły ufw/DOCKER-USER na .111, blok Caddy na .121, vault operatora.

## Implementation Notes

- Każdy krok na hostach .111/.121 — z właścicielem; nic na ślepo. Dostęp
  agenta: wyłącznie przez Ansible/SSH do LXC; host .111 i .121 obsługuje
  właściciel wg komend z `lxc/README.md` i D7.
- **Nie dotykaj `netqarner`, `netqarner_db` ani konfiguracji klastra.**
  Dump i restore zawsze z jawnym `PGDATABASE`.
- Kolejność 18a: PG16 lokalnie → `deploy/lxc` → `deploy/` (syntax/check)
  → host + provision → deploy → smoke → rollback. 18b: backup → off-device →
  drill → reboot → dokumenty. Podział zgłosić w PROGRESS.
- Ansible ignoruje `ansible.cfg` z `/mnt/c` (WSL, katalog world-writable) —
  komendy zawsze z `-i inventories/prod` (wzór runnera i TOC).
- Port aplikacji i SSH na .111 potwierdzić `ss -ltnp` przed wpisaniem do
  `group_vars/prod.yml` i `create-incus.sh`.
- Jeśli `nat=true` proxy device nie zadziała (np. wymóg statycznego IP
  koliduje z konfiguracją `incusbr0`), fallback z 09 §1 wymaga wpisu
  w 02_DECISIONS — nie cichej zmiany.

## Cross-Batch Impact

- Ostatni batch planu: dalsze prace = nowe karty (00 §12).
- `OPERATIONS.md` i `deploy/` są żywe — każda zmiana konfiguracji
  (nowa zmienna w `Settings`) = wpis w `pasnik.env.j2` w tym samym commicie
  (pilnuje `test_deploy_config.py`); dopisać tę regułę do CLAUDE.md §4 obok
  „nowa zmienna = wpis w `.env.example`".
- Nowa migracja wymagająca uprawnień ponad właściciela bazy (np. nie-trusted
  rozszerzenie) = niewykonalna na produkcji bez operatora klastra — reguła
  do CLAUDE.md §6.
- Odroczone decyzje operacyjne (uptime-check, zawężenie `pg_hba`, los obrazu
  prod) → 02_DECISIONS.

## Implementation checklist

- [ ] D6, D7, D29 ZATWIERDZONE zweryfikowane w 02_DECISIONS
- [ ] dev/test na `postgres:16`, `task check` zielony
- [ ] `deploy/lxc/provision.sh` + `create-incus.sh` (odcisk klucza hosta) + README hosta
- [ ] `deploy/` Ansible: inventory, group_vars, trzy playbooki, hooki, szablony
- [ ] `pasnik-cli` bez `source` pliku env; jedno źródło flag uvicorna
- [ ] `test_deploy_config.py`; `--syntax-check` i `--check --diff` czyste
- [ ] Host .111: ufw, utrwalone DOCKER-USER, porty potwierdzone
- [ ] Provision → pierwszy deploy → create-admin → Caddy → smoke HTTPS + PWA
- [ ] Deploy no-op + rollback + deploy przećwiczone
- [ ] Backup timer + przebieg realny; off-device wg D6
- [ ] RESTORE DRILL (obie ścieżki) udokumentowany
- [ ] Reboot .111 przeżyty
- [ ] `OPERATIONS.md`, `deploy/README.md`, 09, CLAUDE.md, PROGRESS

## Verification checklist

- [ ] `task check` zielony
- [ ] Acceptance Criteria 1–9 odhaczone jedno po drugim
- [ ] Zero sekretów w repo; uprawnienia plików na serwerze sprawdzone `stat`
- [ ] Skan portu z innej maszyny LAN + nagłówki przez domenę opisane
- [ ] `/security-review` i `/code-review` na diffie przed commitem
- [ ] Commit `batch(18): ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
