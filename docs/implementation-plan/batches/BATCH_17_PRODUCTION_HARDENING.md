# BATCH_17 — PRODUCTION_HARDENING

Klasa: PROD · Zależności: R4 (werdykt GO / GO warunkowe) · Szacunek rozmiaru: M

## Goal

Aplikacja staje się gotowa do wdrożenia: skrypty backup/restore z retencją
i kontenerem cron, healthcheck rozszerzony (migracje, DB, dysk), produkcyjny
multi-stage Dockerfile z obrazami tagowanymi wersją git, logging produkcyjny
JSON oraz przegląd całej konfiguracji prod. Dodatkowo batch wykonuje
konkretne naprawy wskazane przez R4. Samo wdrożenie na Odroida (compose.prod,
proxy, runbooki) to B18.

## Context

Po R4 aplikacja ma werdykt GO (ew. warunkowy) i listę ustaleń P1 — część
z nich R4 wpisał do sekcji „Ustalenia R4 do wykonania" poniżej. Istnieje
multi-stage Dockerfile z B01 (stage `base` + `dev`) i compose.dev.yml
(app + frontend + db + db-test na tmpfs); NIE istnieją: skrypty backup,
target prod obrazu, rozszerzony healthcheck, prod logging.

Konkrety z B01 do wykorzystania/uzupełnienia:

- `docker/Dockerfile`: `base` instaluje zależności do `/opt/venv`
  (`UV_PROJECT_ENVIRONMENT`), `dev` dokłada grupę dev i `--reload`.
  Stage `frontend-build` + `prod` (SPA przez StaticFiles, ADR-014)
  dokłada TEN batch — świadomie nie było ich wcześniej.
- Aplikacja startuje jako `uvicorn app.main:create_app --factory`.
- `/api/v1/health` zwraca wyłącznie `{status, version}`. Rozszerzenie
  o zgodność head↔DB i status `degraded` (09_DEPLOYMENT §2) to zadanie
  tego batcha — B01 świadomie tego nie robił (health bez dostępu do DB).
- **Nowe z BATCH_16 — `ANTHROPIC_API_KEY`** (07_SECURITY §7). Trzy rzeczy
  do checklisty tego batcha: (1) plik env na prod ma `chmod 600` (klucz jest
  płatny, a jego wyciek to cudzy rachunek); (2) **grep logów prod pod kątem
  klucza i treści promptów** — kod loguje wyłącznie fakt niepowodzenia
  wywołania, ale to trzeba potwierdzić na realnym logu, nie na kodzie;
  (3) pusty klucz jest POPRAWNĄ konfiguracją produkcyjną — healthcheck ani
  start aplikacji nie mają z tego powodu zgłaszać `degraded`.
- Nagłówki bezpieczeństwa i CSP (07_SECURITY §3) **są już wpięte** —
  dostarczył je BATCH_02 (`app/core/middleware.py`, `SecurityHeadersMiddleware`,
  test API sprawdza wartości). Ten batch je PRZEGLĄDA, nie tworzy od zera:
  zweryfikuj wyjątek CSP dla `/api/docs` (w prod ścieżka nie istnieje) oraz
  ewentualne domknięcie `base-uri`/`object-src`.
- **Do przeglądu z B02** (follow-upy zgłoszone w Completion notes B02):
  1. **IP za reverse proxy** — `get_remote_address` (slowapi) i
     `sessions.ip` biorą adres bezpośredniego połączenia. Po wdrożeniu za
     proxy wszystkie żądania wyglądają jak z jednego IP, więc limit
     5/min/IP na `/auth/login` staje się limitem GLOBALNYM dla wszystkich
     kont naraz, a limit 60/min na `/public/*` — wspólny dla wszystkich osób
     z linkiem. Wymaga `--proxy-headers` + `forwarded-allow-ips` (uvicorn)
     albo `ProxyHeadersMiddleware`. **Proxy jest znane od D7 (2026-09-05):
     to Caddy, nie nginx.** Caddy w dyrektywie `reverse_proxy` ustawia
     `X-Forwarded-For` i `X-Forwarded-Proto` domyślnie, więc po stronie
     aplikacji zostaje wyłącznie ZAUFANIE do tych nagłówków — i to zaufanie
     musi być ograniczone do adresu proxy, inaczej dowolny klient poda
     własny `X-Forwarded-For` i limit logowania przestanie cokolwiek znaczyć.
     Dotyczy to także `accounts/router.py:40` (`request.client.host` zapisywany
     jako IP sesji) — dziś zapisze adres proxy dla każdej sesji.
  2. Parametry argon2 (domyślne biblioteki), TTL sesji 30 dni i próg
     blokady konta (10 porażek / 15 min) — stałe w `app/core/security.py`.
- `task audit` i `task secrets-scan` istnieją w Taskfile (nieuruchamiane
  w `task check`).
- **Do przeglądu z B12 (PWA, ADR-009)** — service worker jest od B12 częścią
  produkcyjnego builda i CSP musi go dopuszczać:
  1. **`worker-src`/`script-src` z `'self'`**: `dist/sw.js` i `workbox-*.js`
     rejestrują się z tego samego originu. Zaostrzenie CSP bez tego wyłącza
     SW po cichu — aplikacja działa, ale przestaje działać offline, czego nie
     złapie żaden istniejący test. Po zmianie nagłówków **zweryfikuj
     rejestrację SW na buildzie produkcyjnym**, nie tylko brak błędów w konsoli.
  2. `manifest.webmanifest` musi być serwowany przez backend (ADR-014) z typem
     `application/manifest+json`; bez tego przeglądarka nie zaproponuje
     instalacji, a Lighthouse „installable" spada.
  3. Runtime cache SW świadomie POMIJA `/api/v1/auth/*` (odpowiedzi
     z `Set-Cookie`). Rozszerzając strategie cache, tego wykluczenia nie
     wolno zdjąć (07_SECURITY).
- **Do przeglądu z R1** (ustalenia review fundamentów, patrz dziennik
  `PROGRESS.md`):
  1. **Świeżość kontraktu API nie jest bramkowana**: `task check` nie
     sprawdza, czy `backend/openapi.json` i `frontend/src/api/generated.ts`
     odpowiadają kodowi (w R1 były zgodne — regeneracja dała zerowy diff).
     Kandydat na bramkę: `task fe-types` + `git diff --exit-code` na obu
     plikach (03_AI_SKILLS §9 przypisuje bramki jakości do B01/B17).
  2. **`SECRET_KEY` jest wymagane w konfiguracji, ale nieużywane w kodzie**
     — sesje i tokeny CSRF pochodzą z `secrets`, nie z podpisu tym kluczem.
     Decyzja do podjęcia tutaj: zostawić jako zarezerwowane (i dopisać to
     wprost w `.env.example` + 07_SECURITY §7) albo usunąć z wymaganych.
  3. **Wyszukiwarki ADMIN-a nie escapują `%`/`_`**: `list_users`
     i `list_households` (`accounts/service.py:178`,
     `households/service.py:154`) budują `ilike(f"%{query}%")` bez
     `autoescape=True` — B04 naprawił dokładnie to w katalogu produktów.
     Skutek: szukanie „50%" zwraca wszystko od „50". Niski priorytet, ale
     ta sama pułapka wraca w każdej nowej wyszukiwarce.
- **Do przeglądu z R2** (review rdzenia planowania, 2026-08-21):
  4. **Zimny start pierwszego żądania.** `GET /plan/days` na tygodniu
     ze 112 pozycjami trwa 100–180 ms na rozgrzanym procesie, ale PIERWSZE
     żądanie po starcie procesu ~1,5 s (budowanie modeli Pydantica i planów
     zapytań PG). To koszt startu, nie zapytania, ale użytkownik zobaczy go
     po każdym restarcie kontenera — kandydat na rozgrzewkę w healthchecku
     albo świadome przyjęcie i opisanie w 09_DEPLOYMENT.
  5. **`task secrets-scan` jest już używalny jako bramka** — od R2 istnieje
     `.gitleaks.toml` (pełne reguły domyślne + allowlist dwóch literałów
     haseł testowych po wzorcu, nie po ścieżce) i komenda kończy się exit 0
     na czystym repo. Do decyzji tutaj: czy wciągnąć ją do `task check`
     (koszt: ~18 s i wymaga Dockera) albo do osobnego targetu CI.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` + karta w całości.
- **`docs/architecture/09_DEPLOYMENT_AND_OPERATIONS.md` — WIĄŻĄCY**:
  §1 (topologia, bind mounts), §2 (start bez auto-migracji, healthcheck
  degraded), **§3 (backup — rdzeń tego batcha)**, §4 (update/rollback —
  obrazy tagowane), §5 (środowiska), §6–7.
- `docs/architecture/07_SECURITY_DESIGN.md` §7 (sekrety env, chmod 600),
  §8 (logi bez tokenów), §9 (PG bez SUPERUSER, port tylko w sieci compose).
- `docs/architecture/01_ARCHITECTURE_OVERVIEW.md` §5; 08_TESTING §1.
- `docs/implementation-plan/PROGRESS.md` — werdykt R4 i warunki.
- ADR-002 (bind mounts, migracje jawne), ADR-014 (backend serwuje SPA —
  target prod domyka tę decyzję).

## Ustalenia R4 do wykonania

Wypełnione przez **REVIEW R4 (2026-09-05)**. Wykonać jako Stage 1, każdy
punkt odhaczyć z krótkim opisem w Completion notes. Punkty 1–3 to jedyne
ustalenia P1 R4 przypisane do tego batcha — reszta długu programu jest
w PROGRESS jako rejestr P2/P3 i tu jej NIE MA.

- [ ] **1. Healthcheck nie sprawdza migracji.** `GET /api/v1/health` zwraca
      dziś dosłownie `{"status":"ok","version":"0.1.0"}` (sprawdzone realnym
      requestem), a **09_DEPLOYMENT §2 wymaga statusu `degraded`, gdy głowa
      Alembica nie zgadza się z bazą**. To nie jest kosmetyka: procedura
      update z §4 nie migruje automatycznie, więc jedyną rzeczą, która ma
      wykryć „kontener wstał na starym schemacie", jest właśnie healthcheck.
      Uwaga wykonawcza: dzisiejszy endpoint świadomie nie dotyka bazy
      (B01), więc dochodzi zależność od sesji — healthcheck compose musi
      tolerować `degraded` inaczej niż `down`.
- [ ] **2. CSP nie ma dyrektyw, które NIE dziedziczą po `default-src`.**
      Realny nagłówek to `default-src 'self'; img-src 'self' data: blob:;
      style-src 'self' 'unsafe-inline'`. `object-src` i `worker-src`
      dziedziczą i są bezpieczne, ale **`base-uri` i `form-action` NIE
      dziedziczą** — bez nich wstrzyknięty `<base>` przestawia wszystkie
      ścieżki względne, a przejęty formularz może wysłać dane na obcy host.
      Dołożyć `base-uri 'none'; form-action 'self'; frame-ancestors 'none'`
      (to ostatnie jako nowocześniejszy odpowiednik `X-Frame-Options`, który
      zostaje). Miejsce: `app/core/middleware.py::SECURITY_HEADERS`
      + 07_SECURITY §3. **Po zmianie zweryfikować rejestrację service workera
      na buildzie produkcyjnym** — to ta sama pułapka, co w punkcie „Do
      przeglądu z B12" wyżej.
- [ ] **3. Endpointy uploadu nie mają rate limitu.** Limity ma `/auth/login`
      (5/min/IP), `/import/jobs/{id}/ai-suggest` (10/min) i cała ścieżka
      `/public/*` (60/min wspólnie). NIE mają go: `POST /import/pdf` (25 MB
      na żądanie!), `POST /recipes/{id}/photo`, `PUT /retail-products/{id}/photo`
      i `POST /transfer/import` (100 MB). Model zagrożeń §1 nie broni się przed
      członkiem rodziny, ale broni przed PRZEJĘTĄ sesją — a tam jedyny koszt
      zapełnienia dysku Odroida to pętla `curl`. To naturalnie łączy się
      ze Stage 3 (body limit): limit rozmiaru i limit częstości to dwie
      połowy tej samej ochrony.
- [ ] **4. Pliki uploadów bez referencji nie mają żadnego sprzątacza.**
      R4 znalazł w `backend/data/uploads/import-pdf/` **trzy PDF-y (4,4 MB)**,
      do których nie prowadzi żaden wiersz `import_jobs` — pozostałość po
      testach dziedziczących `UPLOADS_DIR` z `.env` (dług **U26**) i po
      resecie bazy dev z D23. Na produkcji ten sam mechanizm zostawi śmieci
      po każdym nieudanym imporcie. **Nie budować crona kasującego** (D10:
      nic nie usuwamy automatycznie) — wystarczy komenda raportująca „pliki
      bez referencji", którą runbook backupu woła obok `du`.
- [ ] **6. Prefiks `__Host-` dla cookies sesji i CSRF** (obserwacja z audytu
      frontendu w R4). Double-submit czyta PIERWSZE ciasteczko `csrf_token`
      z `document.cookie` — to standardowe zastrzeżenie tego wzorca: subdomena
      albo sąsiad na tym samym rejestrowalnym domenie mogłaby przypiąć własną
      parę cookie+nagłówek. Lekarstwo nie leży we froncie, tylko w `Set-Cookie`:
      prefiks `__Host-` wiąże ciasteczko z dokładnie jednym hostem i `Path=/`.
      **Pułapka wykonawcza**: `__Host-` WYMAGA flagi `Secure`, więc na
      `http://localhost` przeglądarka takie ciasteczko odrzuci — nazwa musi być
      zależna od `APP_ENV` tak samo, jak dziś jest `Secure`
      (`app/core/cookies.py`). Zmiana wylogowuje istniejące sesje.
- [ ] **7. `create_async_engine` bez `hide_parameters=True`** (obserwacja
      z audytu core w R4). `core/errors.py` loguje pełny traceback, a
      SQLAlchemy dokleja do komunikatu `DBAPIError` sekcję `[parameters: ...]`.
      Nieobsłużony błąd na INSERCIE do `sessions` wypisałby więc **token sesji**
      do logu — dokładnie to, czego zabrania 07_SECURITY §8. Nie da się tego
      wywołać z zewnątrz (to awaria bazy, nie żądanie użytkownika), więc nie
      jest to dziura, tylko jedna linia w `core/db.py`, która zamyka klasę
      problemu.
- [ ] **8. `PRIVATE_SUBDIRS` porównuje się z uwzględnieniem wielkości liter**
      (`core/uploads.py:157`). Na Linuksie produkcyjnym nieszkodliwe, bo
      `/uploads/Transfer/...` po prostu nie istnieje. Na hoście deweloperskim
      z systemem plików bez rozróżniania wielkości liter (Windows, macOS)
      ścieżka `Transfer/` przechodzi kontrolę i trafia w ten sam plik.
      `parts[0].lower()` zamyka temat niezależnie od systemu.
- [ ] **5. Zajętość `/srv/pasnik/uploads` do runbooka backupu** (rewizja
      **D10** w R4): to JEDYNA oś, która rośnie bez ograniczenia — zdjęcia
      przepisów i wariantów oraz jadłospisy PDF zatwierdzonych importów
      zostają na zawsze i tak ma być (audyt pochodzenia przepisu).

## Stages

1. **Naprawy z R4**: wykonać listę z sekcji „Ustalenia R4 do wykonania";
   każdą odhaczyć z krótkim opisem w Completion notes.
2. **Dockerfile prod**: target `prod` w multi-stage (stage frontend build →
   stage python bez dev-deps; dist w obrazie — ADR-014; Uvicorn workers=2,
   bez --reload; USER nie-root). Tagowanie obrazu wersją git
   (`task build-prod` → tag `pasnik-app:<git describe/sha>`).
3. **Konfiguracja prod**: przegląd `app/core/config.py` — WSZYSTKIE
   wartości różniące środowiska przez env (żadnych defaultów prod w kodzie);
   limity rozmiaru request (body limit dla uploadów: obraz 10 MB, PDF 25 MB
   + margines); `APP_ENV=prod` przełącza logging. `.env.example` uzupełniony.
4. **Logging prod**: structlog → JSON na stdout gdy `APP_ENV=prod`;
   poziomy przez env (`LOG_LEVEL`); potwierdzone filtry: zero tokenów
   (sesyjnych/publicznych/API), maskowanie `/public/lists/***`.
5. **Healthcheck rozszerzony**: `/api/v1/health` zwraca `status:
   ok|degraded`, `version`, oraz checki: DB odpowiada, `alembic heads`
   == wersja w DB (degraded gdy niezmigrowana — 09 §2), wolne miejsce
   na dysku danych (degraded poniżej progu z env, default 1 GB).
   Bez auth; bez ujawniania ścieżek/hostów w odpowiedzi.
6. **Skrypty backup/restore** (09 §3): `docker/backup/` — skrypt backup
   (`pg_dump -Fc` + `tar` uploads + kopia pliku env WYŁĄCZONA z repo —
   tylko instrukcja; prune retencji: 7 dziennych + 4 tygodniowe),
   skrypt restore (przywraca dump + uploads do wskazanego środowiska),
   kontener cron w profilu `backup` (codziennie 03:00, logi na stdout).
7. **Testy**: round-trip backup→restore REALNIE wykonany na compose
   testowym; test healthcheck degraded przy braku migracji; testy
   jednostkowe checków. `task check` zielony.
8. **Docs i domknięcie**: 09_DEPLOYMENT zaktualizowany do stanu
   faktycznego (nazwy skryptów, targety task); PROGRESS.md; commit
   `batch(17): ...`.

## Database / migrations

- Brak zmian schematu. Jeśli naprawa z R4 wymaga migracji: numer =
  pierwszy wolny, `down_revision` z `alembic heads`, down testowany
  (ADR-002); po zmianie `alembic heads` = 1.
- Healthcheck porównuje rewizję head (z kodu) z `alembic_version` w DB —
  odczyt read-only, bez side effectów.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/health` | GET | publiczny | rozszerzony: `{status: ok\|degraded, version, checks: {db, migrations, disk}}` — bez ścieżek i szczegółów infrastruktury |

- `core/config.py`: nowe env — `LOG_LEVEL`, `UVICORN_WORKERS` (compose),
  `DISK_MIN_FREE_MB`, `MAX_UPLOAD_IMAGE_MB`, `MAX_UPLOAD_PDF_MB`
  (jeśli dotąd zaszyte w kodzie).
- Limit rozmiaru request: middleware/konfiguracja odrzucająca body ponad
  limit z czytelnym 413 w kształcie błędu 04_API §1.
- Skrypty backup/restore: bash w `docker/backup/` (uruchamialne też
  ręcznie przez `task backup` / `task restore -- <plik>`), idempotentny
  prune, kod wyjścia ≠0 przy niepowodzeniu (cron alarmuje logiem).

## Frontend

- Brak zmian funkcjonalnych. Weryfikacja: build produkcyjny (`vite build`)
  przechodzi i dist serwowany przez backend w obrazie prod działa
  (SPA fallback na index.html — ADR-014), PWA manifest dostępny.

## Security

- Obraz prod: nie-root user, bez dev-dependencies, bez source map
  z sekretami; `docker history` bez sekretów (build args nie niosą kluczy).
- Backup zawiera dump DB i uploads — pliki backupu traktowane jak sekrety
  (zawierają dane rodziny): uprawnienia 600, katalog poza web-rootem;
  skrypt NIE loguje zawartości ani connection stringów.
- Logging prod: potwierdzić na realnym logu, że nie ma tokenów/haseł
  (grep po przechwyconym stdout).
- PG: user aplikacyjny bez SUPERUSER (07 §9) — zweryfikować i opisać
  w 09_DEPLOYMENT, jeśli dotąd nieegzekwowane.
- Naprawy z R4 o charakterze security wykonywane w pierwszej kolejności.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-SEC
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **Round-trip backup→restore (KLUCZOWY, wykonany REALNIE)**: na compose
  testowym — seed demo → backup → zniszczenie środowiska (down -v /
  czysta baza) → restore → smoke API (login, plan, lista) + porównanie
  liczności kluczowych tabel przed/po. Wynik (czasy, rozmiary) w raporcie.
- **Healthcheck degraded**: baza bez wykonanej ostatniej migracji →
  `status: degraded` z `checks.migrations: fail`; DB niedostępna →
  degraded; dysk poniżej progu (prog ustawiony sztucznie wysoko) → degraded.
- **Prune retencji**: unit test na zestawie dat plików (7 dziennych +
  4 tygodniowe zostają, reszta znika; idempotencja).
- **Limit uploadu**: request ponad limit → 413 w kształcie błędu.
- **Obraz prod**: kontener z obrazu prod startuje, serwuje SPA i API
  (test smoke w compose testowym).
- `task check` zielony.

## Acceptance Criteria

1. Wszystkie pozycje „Ustalenia R4 do wykonania" odhaczone (albo jawnie
   przeniesione z uzasadnieniem do PROGRESS).
2. `task backup` tworzy komplet: dump `-Fc` + tar uploads; prune retencji
   działa wg 7d/4w; kontener cron w profilu `backup` wykonuje backup.
3. Round-trip backup→restore wykonany realnie na compose testowym —
   aplikacja po restore działa (smoke), dane zgodne.
4. `/api/v1/health` zwraca degraded przy: niezmigrowanej bazie, braku DB,
   niskim dysku — potwierdzone testami.
5. Obraz prod: multi-stage, tagowany wersją git, nie-root, dist w środku;
   `docker run` obrazu serwuje aplikację.
6. Cała konfiguracja różnicująca środowiska przechodzi przez env;
   `.env.example` kompletny; Uvicorn workers=2 w konfiguracji prod.
7. Logi w trybie prod: JSON, poziom z env, zero tokenów (zweryfikowane
   grepem po realnym logu).
8. `task check` zielony; 09_DEPLOYMENT zaktualizowany do stanu faktycznego.

## Out of Scope

- `compose.prod.yml`, konfiguracja reverse proxy, instalacja na Odroidzie,
  runbooki operacyjne, backup off-device, restore drill na produkcji → B18.
- Rozstrzyganie D6/D7 (bramki B18) — nie blokują B17.
- Naprawy P2/P3 z rejestru długu (pozostają w PROGRESS).
- Uptime-check zewnętrzny (decyzja przy B18 — 09 §6).

## Expected files/modules

- `docker/Dockerfile` (target prod), `docker/backup/{backup.sh,restore.sh,
  crontab,Dockerfile}` (lub równoważnie — uzasadnić), profil `backup`
  w compose (dev/test do ćwiczeń; prod spina B18).
- `backend/app/core/config.py`, `backend/app/main.py` / moduł health
  (rozszerzenie), middleware limitu rozmiaru.
- `Taskfile.yml`: `backup`, `restore`, `build-prod` (+ help).
- `backend/tests/`: healthcheck degraded, prune, limit uploadu, smoke prod.
- `.env.example`, `docs/architecture/09_DEPLOYMENT_AND_OPERATIONS.md`,
  `docs/implementation-plan/PROGRESS.md`.

## Implementation Notes

- Kolejność: naprawy R4 → Dockerfile prod → config/logging → healthcheck →
  backup → testy. Backup testować na compose TESTOWYM, nigdy na dev-bazie
  z realnymi danymi właściciela.
- Restore skrypt ma być używalny w B18 jako część runbooka — parametry
  (plik dumpu, katalog uploads) jawne, bez interakcji.
- Kopia pliku env w backupie: 09 §3 wymienia env jako część kompletu —
  ale env żyje na hoście (B18); w B17 skrypt przyjmuje opcjonalną ścieżkę
  env do włączenia w archiwum, default wyłączone w dev/test.
- Decyzje pozostawione implementującemu (uzasadnić w Completion notes):
  cron w dedykowanym kontenerze z crond vs `sleep`-loop; sposób pomiaru
  wolnego dysku w kontenerze (statvfs na katalogu uploads).
- Wersja obrazu: `git describe --tags --always` — jeśli brak tagów git,
  sha; spójnie z polem `version` w health.

## Cross-Batch Impact

- **B18**: konsumuje WSZYSTKO z tego batcha (obraz prod, skrypty backup/
  restore, healthcheck, env). Po zakończeniu B17 zaktualizować kartę B18
  o faktyczne nazwy targetów/skryptów i wymagane zmienne env.
- **PROGRESS**: pozycje R4 przeniesione/wykonane — zaktualizować rejestr długu.
- Zmiany komend → Taskfile + CLAUDE.md + project skille `pasnik-*` naraz.

## Implementation checklist

- [ ] Ustalenia R4 wykonane i odhaczone
- [ ] Dockerfile target prod (nie-root, dist, workers=2) + tagowanie git
- [ ] Config: wszystkie wartości prod przez env; `.env.example` kompletny
- [ ] Limity rozmiaru request (413 w kształcie błędu)
- [ ] Logging prod JSON + LOG_LEVEL + weryfikacja braku tokenów
- [ ] Healthcheck: db + migracje + dysk, statusy ok/degraded
- [ ] backup.sh (pg_dump -Fc + tar uploads + prune 7d/4w) + restore.sh
- [ ] Kontener cron w profilu backup
- [ ] Taskfile: backup/restore/build-prod
- [ ] Round-trip backup→restore wykonany realnie
- [ ] Testy: degraded, prune, limit, smoke obrazu prod
- [ ] 09_DEPLOYMENT + PROGRESS zaktualizowane

## Verification checklist

- [ ] `task check` zielony (testy+lint+typecheck)
- [ ] `alembic heads` = 1 (jeśli doszła migracja: up/down/up przechodzi)
- [ ] Round-trip backup→restore: raport z czasami i weryfikacją danych
- [ ] Obraz prod zbudowany i uruchomiony (smoke)
- [ ] Acceptance Criteria 1–8 odhaczone
- [ ] `/code-review` zmian wykonany przed commitem
- [ ] Commit `batch(17): ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
