# BATCH_18 — PRODUCTION_DEPLOYMENT_AND_OPERATIONS

Klasa: PROD · Zależności: B17 + **bramki decyzji D6 (backup off-device)
i D7 (domena/proxy) — batch NIE startuje, dopóki obie nie są ZATWIERDZONE
w 02_DECISIONS** · Szacunek rozmiaru: L

## Goal

Aplikacja działa produkcyjnie na Odroidzie H2: `compose.prod.yml` za
istniejącym reverse proxy pod domeną z D7, backup automatyczny z kopią
off-device wg D6, **restore drill wykonany realnie**, procedury update/
rollback sprawdzone, a `docs/OPERATIONS.md` zawiera runbooki pozwalające
właścicielowi operować systemem bez tej sesji.

## Context

Po B17 istnieją: obraz prod tagowany wersją git, skrypty backup/restore
(przećwiczone na compose testowym), healthcheck rozszerzony, konfiguracja
w pełni przez env. NIE istnieją: compose.prod.yml, vhost proxy, katalogi
`/srv/ffp/*` na Odroidzie, OPERATIONS.md. Ten batch częściowo pracuje na
REALNYM hoście właściciela — kroki wykonywane na Odroidzie wymagają jego
udziału/dostępu; agent przygotowuje komplet i prowadzi procedurę.

**STOP-bramka**: jeśli D6 lub D7 mają status OPEN w
`docs/implementation-plan/02_DECISIONS.md` — zatrzymaj się i zapytaj
właściciela (implementation_prompt pkt 1e). Z D7 muszą wynikać: domena/
subdomena, typ proxy (nginx?), sposób dokładania vhosta; z D6: cel kopii
off-device (NAS/chmura/rclone remote) i dane dostępowe (poza repo!).

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` + karta w całości.
- **`docs/architecture/09_DEPLOYMENT_AND_OPERATIONS.md` §1–6 — WIĄŻĄCY
  w całości** (topologia, migracje jawne, backup, update/rollback,
  środowiska, obserwowalność).
- `docs/architecture/07_SECURITY_DESIGN.md` §3 (HSTS na proxy), §7
  (ffp.env chmod 600), §9 (db bez portów hosta).
- `docs/implementation-plan/02_DECISIONS.md` — treść zatwierdzonych D6/D7
  (+ D10 retencja, rekomendacja z R4).
- Karta `BATCH_17` (Completion notes — faktyczne nazwy skryptów/targetów).

**Warunek z B12 (PWA, ADR-009) — HTTPS jest tu funkcjonalnością, nie ozdobą.**
Przeglądarka rejestruje service workera WYŁĄCZNIE na `https://` (albo
`localhost`), więc bez działającego TLS na reverse proxy lista zakupowa
przestaje działać offline — cicho, bez błędu widocznego dla użytkownika.
Do procedury i do healthchecku (09_DEPLOYMENT §2) dopisz trzy sprawdzenia po
wdrożeniu, wykonywane na PRAWDZIWEJ domenie, nie na localhoście:

1. `GET /manifest.webmanifest` → 200 z typem `application/manifest+json`,
2. `GET /sw.js` → 200 z typem JavaScript i **bez agresywnego cache** (SW musi
   dać się podmienić przy kolejnym wdrożeniu — inaczej użytkownicy zostaną
   z poprzednią wersją aplikacji),
3. w DevTools na urządzeniu mobilnym: „Application → Service Workers"
   pokazuje aktywnego workera, a prompt instalacji jest dostępny.
- ADR-002 (bind mounts, migracje w update), ADR-014 (jeden kontener app).
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §6 (PWA — acceptance).

## Stages

1. **compose.prod.yml** (09 §1): serwisy `app` (obraz tagowany, port
   `127.0.0.1:8080:8000`, `env_file: /srv/ffp/env/ffp.env`,
   `stop_grace_period: 30s`, `restart: unless-stopped`, healthcheck
   z `/api/v1/health`) i `db` (postgres:17, **bez portów hosta**,
   healthcheck pg_isready) + profil `backup` z B17. Bind mounts:
   `/srv/ffp/pgdata`, `/srv/ffp/uploads`, `/srv/ffp/backups`.
   Weryfikacja lokalna: compose config + uruchomienie na maszynie dev
   z katalogami zastępczymi.
2. **Reverse proxy (D7)**: konkretny plik vhosta dla istniejącego proxy
   właściciela (wg D7) — `proxy_pass http://127.0.0.1:8080`, nagłówki
   X-Forwarded-*, HSTS, limity rozmiaru body ≥ limitów aplikacji,
   ewent. cache statyk (ADR-014). Plik w repo jako szablon
   (`docker/proxy/ffp.conf.example`) + krok instalacji w runbooku.
3. **Runbook instalacji (Odroid)**: krok po kroku w OPERATIONS.md:
   utworzenie katalogów `/srv/ffp/*` z uprawnieniami, `ffp.env`
   (chmod 600, komplet zmiennych z `.env.example`), build/pull obrazu,
   `docker compose run --rm app alembic upgrade head` (pierwsza migracja —
   jawna, 09 §2), `task create-admin`, vhost + reload proxy, smoke.
4. **Wykonanie instalacji**: przeprowadzić procedurę na Odroidzie
   (z właścicielem); aplikacja dostępna przez HTTPS na domenie z D7;
   health `ok`; PWA instaluje się z produkcji.
5. **Procedura update i rollback** (09 §4): skrypt/target `task deploy`:
   backup → build/tag → `alembic upgrade head` → `compose up -d`;
   rollback: `compose up` poprzedniego tagu + (gdy trzeba) restore z
   backupu sprzed update; downgrade migracji tylko przetestowany.
   Przećwiczyć update no-op i rollback na produkcji lub kopii.
6. **Backup off-device (D6)**: krok kopiowania (rclone/rsync wg D6)
   dołączony do backupu cron; konfiguracja remote wyłącznie w env/hoście
   (nigdy w repo); weryfikacja, że kopia ląduje w celu i jest kompletna.
7. **RESTORE DRILL (realnie!)**: na świeżym środowisku (inny katalog/
   maszyna): przywróć env → `pg_restore` → uploads → migracje idempotentnie
   → smoke (login, plan, lista, zdjęcie przepisu). Czas i wynik opisać
   w OPERATIONS.md (sekcja „ostatni drill: data, czas, wynik").
8. **OPERATIONS.md + domknięcie**: runbooki (patrz sekcja Backend/Ops);
   aktualizacja 09_DEPLOYMENT do stanu faktycznego; PROGRESS.md;
   commit `batch(18): ...`.

## Database / migrations

- Brak zmian schematu. Pierwsza migracja produkcyjna = jawny krok
  runbooka (`compose run --rm app alembic upgrade head`), NIGDY auto-start
  (ADR-002, 09 §2).
- Update: backup automatycznie PRZED `alembic upgrade head` (krok skryptu).
- Rollback z migracją w dół wyłącznie gdy downgrade przetestowany;
  w wątpliwości — restore z backupu sprzed update (09 §4).

## Backend / Operacje

Brak nowych endpointów. Deliverables operacyjne:

| Artefakt | Treść |
|---|---|
| `docker/compose.prod.yml` | topologia 09 §1 (app+db+profil backup) |
| `docker/proxy/ffp.conf.example` | vhost wg D7 (szablon bez sekretów/domeny właściciela, jeśli wrażliwa) |
| `scripts/deploy.sh` / `task deploy` | update: backup→build→migrate→up |
| `scripts/rollback.sh` / `task rollback` | poprzedni tag + instrukcja restore |
| `docs/OPERATIONS.md` | runbooki: instalacja, update, rollback, restore, backup off-device, dodanie użytkownika (create-admin/admin UI), diagnoza: nie wstaje / 500 / pełny dysk / degraded health; sekcja „ostatni restore drill" |

- OPERATIONS.md pisany dla właściciela-człowieka: komendy do wklejenia,
  oczekiwany wynik każdego kroku, co zrobić gdy krok zawiedzie.

## Frontend

- Brak zmian kodu. Weryfikacja z produkcji: PWA instalowalna (manifest,
  ikony, standalone), lista zakupowa offline działa po pierwszym otwarciu,
  publiczny link `/l/:token` działa przez HTTPS z telefonu.

## Security

- `ffp.env` na hoście chmod 600; sekrety (SECRET_KEY, hasło DB,
  ANTHROPIC_API_KEY, remote backupu) NIGDY w repo — w repo tylko
  `.env.example` i szablon vhosta.
- `db` bez portów hosta; `app` wyłącznie na 127.0.0.1 (proxy terminuje
  TLS; HSTS na proxy — 07 §3).
- Backupy (lokalne i off-device) zawierają dane rodziny + env: uprawnienia
  restrykcyjne, cel off-device prywatny (weryfikacja ACL w D6-remote).
- Po instalacji: skan z zewnątrz (curl nagłówków przez domenę) — nagłówki
  security obecne, `/api/v1/health` nie ujawnia infrastruktury, porty
  poza 443/80 (proxy) niedostępne.
- Hasło pierwszego admina ustawione interaktywnie przy create-admin,
  nieobecne w historii shella (instrukcja w runbooku).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-SEC
- **Recommended**: SKILL-BE
- **Review**: SKILL-SECREV

## Tests

- `task check` zielony (bez zmian logiki — regresja).
- **Smoke produkcyjny po instalacji** (ręcznie, wynik w raporcie):
  login przez HTTPS, plan dnia, generacja listy, publiczny link
  z telefonu, upload zdjęcia, health `ok`.
- **Restore drill** (Stage 7) — najważniejszy „test" batcha; wynik
  i czas udokumentowane.
- **Update no-op + rollback**: przećwiczone realnie (ta sama wersja →
  deploy → rollback do tej samej wersji) — procedury działają.
- **Backup automatyczny**: odczekać/wymusić przebieg crona na produkcji;
  artefakty w `/srv/ffp/backups` + kopia off-device obecna; prune nie
  usuwa świeżych.
- Healthcheck compose: zatrzymanie db → kontener app raportuje degraded,
  compose restartuje wg polityki (obserwacja, opis).

## Acceptance Criteria

1. Aplikacja działa na Odroidzie przez **HTTPS na domenie z D7**;
   health `ok`; SPA, API i uploady serwowane przez kontener app.
2. `db` niedostępna z zewnątrz hosta; `app` słucha tylko na 127.0.0.1.
3. Backup automatyczny wykonuje się (cron, 03:00) i odkłada komplet
   w `/srv/ffp/backups` + **kopia off-device wg D6 istnieje w celu**.
4. **Restore drill przeszedł realnie** — udokumentowany w OPERATIONS.md
   (data, czas trwania, wynik smoke).
5. Procedura update (backup→build→migrate→up) i rollback przećwiczone;
   obrazy tagowane, poprzedni tag dostępny.
6. **PWA instaluje się z produkcji** (telefon właściciela); publiczny
   link listy działa bez logowania.
7. `docs/OPERATIONS.md` kompletny: instalacja, update, rollback, restore,
   backup off-device, dodanie użytkownika, diagnoza (nie wstaje / 500 /
   pełny dysk) — każdy runbook z komendami i oczekiwanym wynikiem.
8. W repo zero sekretów produkcyjnych (`git ls-files` + grep); ffp.env
   chmod 600 na hoście.
9. PROGRESS.md: status + wpis; 09_DEPLOYMENT zgodny ze stanem faktycznym.

## Out of Scope

- Zewnętrzny uptime-check (healthchecks.io) — decyzja właściciela przy
  tym batchu, wpis do 02_DECISIONS jeśli odroczona (09 §6).
- Loki/centralne logi, monitoring ponad `docker logs` (09 §6 — later).
- 2FA (D8 FUTURE), retencja automatyczna list (D10 — wg decyzji).
- Jakiekolwiek zmiany funkcjonalne aplikacji.

## Expected files/modules

- `docker/compose.prod.yml`, `docker/proxy/ffp.conf.example`
- `scripts/deploy.sh`, `scripts/rollback.sh` (lub targety Taskfile —
  spójnie z B17; uzasadnić wybór)
- `Taskfile.yml` (targety deploy/rollback/backup-offsite jeśli task)
- `docs/OPERATIONS.md` (NOWY — jedyny dozwolony nowy dokument)
- `docs/architecture/09_DEPLOYMENT_AND_OPERATIONS.md` (aktualizacja
  do stanu faktycznego), `docs/implementation-plan/PROGRESS.md`
- Na hoście (poza repo): `/srv/ffp/{pgdata,uploads,backups,env/ffp.env}`,
  vhost proxy

## Implementation Notes

- Batch dotyka REALNEGO hosta — każdy krok na Odroidzie wykonywać z
  właścicielem i potwierdzać wynik; nic „na ślepo". Kroki wymagające
  fizycznego dostępu/sekretów wykonuje właściciel wg przygotowanych komend.
- Restore drill NA INNYM środowisku niż produkcja (katalog `/srv/ffp-drill`
  albo maszyna dev) — nigdy nie nadpisywać produkcyjnych bind mounts.
- Kolejność: compose.prod lokalnie → proxy szablon → instalacja → smoke →
  update/rollback → backup off-device → drill → OPERATIONS.md. Dokument
  operacyjny pisać RÓWNOLEGLE z wykonywaniem kroków (świeża pamięć).
- Jeśli proxy właściciela różni się od założeń D7 (inny serwer, inne
  konwencje vhostów) — dostosować szablon, odnotować w 02_DECISIONS/ADR
  gdy trwałe.
- Rozmiar L: jeśli sesja pęka, naturalny podział = instalacja+update
  (część 1) / backup off-device+drill+OPERATIONS (część 2) — podział
  zgłosić w PROGRESS, nie ciągnąć maratonu.

## Cross-Batch Impact

- Ostatni batch planu: dalsze prace = nowe karty wg szablonu (00 §12).
- OPERATIONS.md staje się dokumentem żywym — każda przyszła zmiana
  procedur operacyjnych aktualizuje go w tym samym commicie.
- Odroczone decyzje operacyjne (uptime-check, retencja D10) → 02_DECISIONS.
- CLAUDE.md/skill: dopisać zakaz dotykania produkcji poza procedurami
  OPERATIONS.md (jeśli nie wynika już z treści).

## Implementation checklist

- [ ] Bramki D6/D7 ZATWIERDZONE zweryfikowane w 02_DECISIONS (STOP jeśli nie)
- [ ] compose.prod.yml wg 09 §1 (bind mounts, 127.0.0.1:8080, bez portów db,
      stop_grace_period, unless-stopped, healthchecki)
- [ ] Szablon vhosta proxy wg D7 (X-Forwarded-*, HSTS, limity body)
- [ ] Runbook instalacji napisany, wykonany na Odroidzie, smoke przez HTTPS
- [ ] Pierwsza migracja jawnie; create-admin wykonany bezpiecznie
- [ ] deploy.sh (backup→build→migrate→up) + rollback.sh; przećwiczone
- [ ] Backup cron na produkcji + kopia off-device wg D6 zweryfikowana
- [ ] RESTORE DRILL wykonany i udokumentowany
- [ ] PWA z produkcji zainstalowana; publiczny link z telefonu działa
- [ ] OPERATIONS.md kompletny (wszystkie runbooki + diagnoza)
- [ ] 09_DEPLOYMENT + PROGRESS zaktualizowane

## Verification checklist

- [ ] `task check` zielony
- [ ] Acceptance Criteria 1–9 odhaczone jedno po drugim
- [ ] Zero sekretów w repo (grep); ffp.env 600 na hoście
- [ ] Skan nagłówków/portów z zewnątrz wykonany i opisany
- [ ] `/code-review` zmian wykonany przed commitem
- [ ] Commit `batch(18): ...`, `git status` czysty (pliki hosta poza repo)

## Completion notes

(wypełnia agent wykonujący)
