# 09 — Deployment, backup i operacje

Docelowo: Odroid H2 (x86-64, Debian-family), Docker + Docker Compose
(ustalone; NIE LXC), za istniejącym reverse proxy z TLS i domeną.
Ten dokument ustala założenia i szkielet; **finalny deployment powstaje
w BATCH_17 (hardening) i BATCH_18 (deployment & operations) po Review 4**,
na podstawie rzeczywiście istniejącej aplikacji.

## 1. Topologia produkcyjna (założenia wiążące)

- 2 kontenery: `app` (Uvicorn+FastAPI, serwuje też SPA i uploady)
  i `db` (postgres:17). Opcjonalny profil `backup` (kontener cron).
- Sieć: tylko `app` wystawia port na localhost hosta (np. 127.0.0.1:8080);
  reverse proxy hosta → ten port. `db` bez portów hosta.
- **Lifecycle danych ≠ lifecycle kontenera** — bind mounts hosta:

```
/srv/ffp/pgdata    → /var/lib/postgresql/data
/srv/ffp/uploads   → /data/uploads      (zdjęcia, PDF-y importu)
/srv/ffp/backups   → /backups           (dumpy + kopie uploads)
/srv/ffp/env/ffp.env (chmod 600)        → env_file kontenera app
```

- Obrazy: multi-stage Dockerfile (stage frontend build → stage python;
  dist kopiowany do obrazu app). Wersjonowane tagiem git.

## 2. Start aplikacji i migracje

- Kontener app przy starcie NIE migruje automatycznie; migracje uruchamia
  jawny krok `docker compose run --rm app alembic upgrade head` w procedurze
  update (świadoma decyzja: brak wyścigu i brak niespodzianek przy
  restarcie). Healthcheck `/health` weryfikuje też zgodność head vs DB
  (status `degraded` gdy niezmigrowana).
- `restart: unless-stopped`; graceful shutdown (Uvicorn) — compose
  `stop_grace_period: 30s`.

## 3. Backup (projekt od początku, wdrożenie B17/B18)

- **Co**: `pg_dump -Fc` (custom format) + rsync/tar katalogu uploads +
  kopia pliku env (sekrety!) — komplet wystarczający do pełnego odtworzenia.
- **Kiedy**: cron kontener (profil backup) codziennie 03:00; retencja
  7 dziennych + 4 tygodniowe (prune skryptem).
- **Dokąd**: `/srv/ffp/backups` + zalecana kopia off-device (rsync na NAS /
  rclone do chmury — decyzja właściciela przy B18).
- **Restore (runbook w B18, ćwiczony realnie)**: świeży compose → przywróć
  env → `pg_restore` → przywróć uploads → migracje idempotentnie → smoke.
- Dodatkowo eksport logiczny aplikacji (moduł transfer) = backup „ludzki",
  niezależny od wersji PG.

## 4. Update / rollback

Update: `git pull` → build obrazów → backup przed migracją (automatyczny
krok skryptu) → `alembic upgrade head` → `compose up -d`. Rollback: obrazy
tagowane, `compose up` poprzedniego tagu; migracje w dół tylko gdy
downgrade przetestowany (każda migracja ma test down — 03_DATABASE §1);
w razie wątpliwości restore z backupu sprzed update.

## 5. Konfiguracja środowisk

| | dev (Windows/dowolne) | test (CI/lokalnie) | prod (Odroid) |
|---|---|---|---|
| compose | compose.dev.yml (hot reload, porty otwarte) | compose.test.yml (db tmpfs) | compose.prod.yml (B18) |
| frontend | vite dev server + proxy /api | build | dist w obrazie app |
| dane | wolumeny nazwane | efemeryczne | bind mounts /srv/ffp |
| sekrety | .env lokalny | wartości testowe | ffp.env chmod 600 |

## 6. Obserwowalność (na miarę domową)

Logi JSON na stdout → `docker logs` / opcjonalnie loki później. `/health`
(status, wersja, migracje, dostępność DB). Miejsce na przyszłość: prosty
uptime-check z zewnątrz (np. healthchecks.io ping z crona) — decyzja przy B18.

## 7. Wymagania sprzętowe (sanity)

Odroid H2 (4 rdzenie, ~8-32 GB RAM): PG + Uvicorn (2 workery) + nginx hosta
to ułamek możliwości; pdfplumber przy imporcie to chwilowy peak CPU —
import wykonywany synchronicznie w request z limitem czasu albo w wątku
(bez Celery; ADR-001).
