# `deploy/` — wdrożenie Paśnika (LXC + ansistrano)

Paśnik jedzie na produkcję **jedną ścieżką**: `ansible-playbook` z WSL maszyny
operatora, `rsync` release'u, usługa systemd w kontenerze LXC `pasnik`
(Incus) na hoście 192.168.2.121, baza `ffp_db` w klastrze `postgres-apps` na tym
samym hoście, TLS na Caddym .121 (decyzje D29 i D30, ADR-017; wzorzec:
`nc-tech-test-runner/deploy/`).
Maszyna powstaje osobno i wcześniej — z `deploy/lxc/` (`lxc/README.md`).
Ten katalog zakłada, że ona już stoi.

Wejście dla człowieka to **Taskfile** (`task provision | deploy | rollback`) —
cienkie wrappery nad `deploy/ansible-run.sh`. Opis operacji „od zera do
produkcji" i runbooki awaryjne: `docs/OPERATIONS.md` (powstaje w 18b); tu jest
to, co potrzebne do samego deployu.

## Dwa kanały, dwie role

| Kanał | Kto | Co robi | Uprawnienia |
|---|---|---|---|
| `root` | `playbook-provision.yml`, kroki „przed wydaniem" w `playbook-deploy.yml` | **raz na maszynę**: unity systemd, `pasnik.env`, `pgpass`, `pasnik-cli`, skrypty backupu; przy deployu: samotest, prawa plików, `select 1` rolą aplikacji | SSH wyłącznie kluczem, pełny root |
| `deploy` | `playbook-deploy.yml` (release), `playbook-rollback.yml` | **przy każdym wydaniu**: rsync, venv, dump, migracja, `current`, restart | SSH kluczem, `sudo` **tylko** `systemctl {daemon-reload, start\|stop\|restart\|is-active pasnik, start pasnik-backup}` i `sudo -u pasnik pasnik-cli` |

Dlaczego dwa: zapis unitu **jest** rootem — „wąska reguła sudo dla provisionu"
byłaby pełnym rootem pod inną nazwą. Rozdzielenie kanałów zostawia ścieżkę
rutynową (codzienną) naprawdę nieuprzywilejowaną. `releases/` należy do
`deploy`, ansistrano **nie** używa `become`.

> Klucz `deploy` jest właścicielem kodu, który usługa uruchamia jako `pasnik`
> z dostępem do `pasnik.env`. Traktuj go jak klucz do **sekretów aplikacji**
> (nie roota maszyny). Domyślnie `PROVISION_PUBKEY` jest tym samym kluczem.

## Maszyna operatora (raz)

WSL (Ubuntu), `rsync`, `ssh` i **ansible-core z pipa**, nie z `apt` (`apt` wiezie
2.10, na którym role ansistrano nie chodzą):

```bash
python3 -m venv ~/.venvs/ansible && ~/.venvs/ansible/bin/pip install "ansible-core>=2.16,<2.18"
```

Role i kolekcje (do `deploy/.ansible/`, poza gitem):

```powershell
task deploy-galaxy
```

Na Windowsie: Docker Desktop, `uv`, Node 22+, `go-task` (jak w CLAUDE.md §3) —
`task deploy` buduje frontend i skanuje repo gitleaksem przed wysłaniem.

`ansible.cfg` działa **wyłącznie z katalogu `deploy/`**, a checkout na `/mnt/c`
bywa przez Ansible ignorowany jako „world-writable directory". Dlatego
`ansible-run.sh` ustawia jawnie `ANSIBLE_CONFIG=ansible.cfg` i podaje
`-i inventories/prod` — ręczne komendy muszą robić to samo.

## Sekrety

W repo są wyłącznie **nazwy** zmiennych i szablony z `CHANGE_ME`. Wartości
trzymasz w pliku Ansible Vault **poza repo**:

```bash
~/.venvs/ansible/bin/ansible-vault create ~/pasnik-prod.yml
```

| Zmienna | Co to | Skąd |
|---|---|---|
| `vault_db_password` | hasło roli `ffp_user` do bazy `ffp_db` | operator klastra `postgres-apps` (właściciel zna) |
| `vault_secret_key` | `SECRET_KEY` aplikacji: 32+ znaków `[A-Za-z0-9_-]` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

Potrzebne **tylko w provisionie** (`task provision` prosi o hasło do vaulta;
plik: `~/pasnik-prod.yml`, `PASNIK_VAULT_FILE` nadpisuje). Deploy sekretów nie
dotyka. Wartości lądują wyłącznie w `/etc/pasnik/pasnik.env` (`root:pasnik`
0640) i `/etc/pasnik/pgpass` (`pasnik` 0600). Agent AI tego pliku nie tworzy
i nie czyta.

## Pierwsze uruchomienie (kolejność)

1. **Maszyna stoi**: `create-incus.sh` skończył się `SAMOTEST: OK`, reguły
   `DOCKER-USER` nałożone (`lxc/README.md` §1–3), wpis klucza hosta wklejony do
   `~/.ssh/pasnik-prod.hostkeys` (§4).
2. **Wartości niesekretne** w `group_vars/prod.yml` — w szczególności `ct_ip`
   i `bridge_gateway` z wyjścia `create-incus.sh`; provision odmówi, jeśli
   któraś jest `CHANGE_ME`.
3. **Vault** z sekretami (wyżej).
4. **Provision** (raz):

   ```powershell
   task provision
   ```

   Zakłada unity (`pasnik` włączony, **nie** wystartowany; timer backupu
   uruchomiony), `pasnik.env`, `pgpass`, `pasnik-cli`, skrypty backupu w
   `/usr/local/lib/pasnik`.
5. **Deploy**:

   ```powershell
   task deploy
   ```

   `fe-build` → `secrets-scan` → ansistrano: guard stechłego dista, rsync, guard
   sekretów, `uv sync --frozen --no-dev`, import-smoke, **dump bazy**,
   `alembic upgrade head`, symlink `current`, restart, **health z asercją na
   treść** (`status: ok`, `version` = release, `migrations: ok`), `/api/docs` → 404.
6. **Konto administratora** (hasło z promptu, nie z historii powłoki):

   ```powershell
   wsl -d Ubuntu-22.04 -- ssh -t -p 2223 root@192.168.2.121 /usr/local/bin/pasnik-cli -- python -m app.cli create-admin
   ```

7. **Caddy na .121** — właściciel wg D7: `task deploy-caddy-vhost` renderuje
   przykład do `deploy/.ansible/pasnik-caddy-vhost.conf`. Blok `pasnik.cpt-sztos.com`
   w `/etc/caddy/Caddyfile` **podmieniasz** (dziś serwuje landing; dwa bloki na tę
   samą domenę to błąd), potem:

   ```bash
   caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
   ```

   Bez dyrektywy `log` (publiczny token listy), HSTS z krótkim `max-age`.
   Cel: `reverse_proxy <ct_ip>:8000` — wprost po moście (Caddy i kontener są
   na tym samym hoście).

## Komendy

| Po co | Komenda |
|---|---|
| provision (raz) | `task provision` (`-- -e force_env=true` nadpisuje `pasnik.env`/`pgpass` z vaulta) |
| deploy | `task deploy` |
| próba na sucho | `task deploy -- --check --diff` (rola ansistrano pominięta — nie umie próby; sprawdza kanał root, prawa, bazę, rsync; wymaga ukończonego provisionu) |
| rollback | `task rollback` |
| rollback na konkretne wydanie | `task rollback -- -e ansistrano_rollback_to_release=20261003120000Z` |
| po odtworzeniu maszyny (nowy klucz hosta) | dowolny playbook z `-- -e refresh_host_key=true`, najpierw wklej nowy wpis (`lxc/README.md` §4) |
| sama składnia | `task deploy-syntax` |
| przykład bloku Caddy | `task deploy-caddy-vhost` |

Wszystko z katalogu repo; wrapper wchodzi do WSL sam.

## Układ na maszynie

```
/opt/pasnik/
  releases/<ts>/                 release: backend/{app,migrations,scripts,.venv} + frontend/dist + VERSION   (deploy)
  current -> releases/<ts>       przełączane przez ansistrano
  shared/uploads                 UPLOADS_DIR (zdjęcia + scratch kopii danych)           (pasnik 0750)
  shared/backups                 BACKUP_DIR (dumpy + kopie uploadów)                    (pasnik 0750)
  shared/uv-cache                cache uv między release'ami                            (deploy)
/etc/pasnik/                     root:pasnik 0750
  pasnik.env                     0640 root:pasnik — konfiguracja + sekrety (EnvironmentFile)
  pgpass                         0600 pasnik     — hasło roli dla pg_dump/psql (PGPASSFILE)
/usr/local/lib/pasnik/           backup.sh, restore.sh, backup_prune.py (z repo; root)
/usr/local/bin/pasnik-cli        wejście operatora (poniżej)
/etc/systemd/system/pasnik.service, pasnik-backup.service, pasnik-backup.timer
```

Pięć ostatnich wydań zostaje (`ansistrano_keep_releases: 5`). `shared/`
i `/etc/pasnik` przeżywają każdy deploy i rollback — zmiana konfiguracji **nie
jest** wydaniem, tylko provisionem. W release'ie jedzie wyłącznie biała lista:
`backend/` (bez testów i danych), `frontend/dist/` i `VERSION`
(`group_vars/all.yml`, `ansistrano_rsync_extra_params`).

## `pasnik-cli` — polecenia z środowiskiem usługi

```bash
pasnik-cli [--release KATALOG] -- POLECENIE [ARGUMENTY...]
```

Uruchamia polecenie jako `pasnik`, w `backend/` wybranego release'u (domyślnie
`current`), z TYM SAMYM środowiskiem co usługa. Środowisko czyta **pętla po
`pasnik.env`**, a nie `source` powłoką (dług nr 1 runnera: wartość ze spacją
czytałaby powłoka inaczej niż systemd) — format pliku jest ograniczony do
`KLUCZ=wartość` bez spacji i cudzysłowów, co pilnuje
`backend/tests/unit/test_deploy_config.py`. Różnica względem usługi: brak
sandboxu unitu (`ProtectSystem` itd.). Wołają go: `root` (SSH z TTY, np.
`create-admin`) i `deploy` przez `sudo -u pasnik` (hook migracji z nowego release'u).

## Rollback i migracje

`task rollback` przełącza `current` na poprzedni release i restartuje usługę;
health jest asertowany na wersję PRZYWRÓCONEGO release'u. **Migracji nie
cofa.** Gdy wycofywany release zmigrował schemat:

1. `systemctl stop pasnik` (na maszynie, kanał root),
2. `restore.sh` z dumpu sprzed migracji (`shared/backups`, zestaw z hooka
   `before-symlink` tuż przed deployem — `/usr/local/lib/pasnik/restore.sh`,
   uruchamiany jako `pasnik` z `PGHOST…`/`PGPASSFILE` jak w `pasnik-backup.service`),
3. dopiero potem `task rollback`.

Downgrade schematu wyłącznie przetestowany (03_DATABASE §1). Pełny runbook
z poleceniami: `docs/OPERATIONS.md` (18b).

## Czym to się różni od runnera (i dlaczego)

| Runner (`nc-tech-test-runner/deploy`) | Paśnik | Powód |
|---|---|---|
| nic nie budowane na hoście | `uv sync --frozen --no-dev` w hooku `after-update` | aplikacja ma zależności z PyPI (`uv.lock`); rollback = zmiana symlinka (venv per release) |
| usługa jako root | usługa jako `pasnik` z hardeningiem | internetowa aplikacja z sesjami; nie ma powodu na roota |
| jeden `runner.env` bez bazy | `pasnik.env` + `pgpass`, baza na innym hoście | D29 |
| `source` pliku env w `deep-health` (dług nr 1) | `pasnik-cli` z pętlą KLUCZ=wartość | wartości ze spacją |
| hook zdrowia rollbacku pod nazwą roli deploy | `ansistrano_rollback_after_symlink_tasks_file` | rola rollback czyta własne nazwy hooków — wzorzec runnera podpinał nieistniejącą |
| `stdout_callback = yaml` | `default` + `callback_result_format = yaml` | callback `yaml` zniknął z ansible-core 2.17 |
| `--exclude=dist` | biała lista rsynca | wycinałoby `frontend/dist` |
| odcisk klucza hosta nieznany przy 1. provisionie | `create-incus.sh` wypisuje odcisk i wpis `known_hosts` | dług nr 4 runnera |

## Kiedy coś nie działa

| Objaw | Co to znaczy |
|---|---|
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | maszyna była odtwarzana; skasuj pin (`-e refresh_host_key=true`) i wklej NOWY wpis z `create-incus.sh` |
| `Permission denied (publickey)` | maszyna nie dostała klucza (`OPERATOR_PUBKEY`/`PROVISION_PUBKEY`) — `lxc/README.md` |
| `sudo: a password is required` przy restarcie/dumpie | konto `deploy` nie ma reguły z `/etc/sudoers.d/60-pasnik-deploy` — maszyna zbudowana starszym `provision.sh` (odtwórz) |
| `Brak /etc/systemd/system/pasnik.service` | nie było provisionu na tej maszynie |
| stale-dist: „frontend/dist jest z innego commita" | `task fe-build` i powtórz (`task deploy` robi to sam) |
| `pg_isready` / `select 1` czerwone przed rsyncem | LXC nie dosięga bazy na .121: reguły `DOCKER-USER` (`lxc/README.md` §3), `pg_hba` klastra, hasło w vaulcie |
| health `degraded` po restarcie | `checks.db: fail` = baza; `migrations: fail` = krok migracji pominięty; `disk: fail` = pełny dysk |
| przy porażce | rescue wypisuje `journalctl -u pasnik -n 50` (kanał root) |

Diagnostyka na maszynie (kanał root): `journalctl -u pasnik -n 50`,
`systemctl status pasnik`.
