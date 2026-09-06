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

- [x] **1. Healthcheck nie sprawdza migracji.** WYKONANE: `app/core/health.py` — `{status: ok|degraded, version, checks: {db, migrations, disk}}`; head liczony ze skryptów Alembica (bez `env.py`), `migrations: skipped` gdy baza nie odpowiada; `degraded` = nadal HTTP 200 (kontener odpowiadający jest `healthy`, treść czyta operator — 09 §2). Testy: `tests/unit/test_health.py`, `tests/api/test_health.py` (niezmigrowana / bez bazy / mało dysku / pusty klucz Anthropic). `GET /api/v1/health` zwraca
      dziś dosłownie `{"status":"ok","version":"0.1.0"}` (sprawdzone realnym
      requestem), a **09_DEPLOYMENT §2 wymaga statusu `degraded`, gdy głowa
      Alembica nie zgadza się z bazą**. To nie jest kosmetyka: procedura
      update z §4 nie migruje automatycznie, więc jedyną rzeczą, która ma
      wykryć „kontener wstał na starym schemacie", jest właśnie healthcheck.
      Uwaga wykonawcza: dzisiejszy endpoint świadomie nie dotyka bazy
      (B01), więc dochodzi zależność od sesji — healthcheck compose musi
      tolerować `degraded` inaczej niż `down`.
- [x] **2. CSP nie ma dyrektyw, które NIE dziedziczą po `default-src`.** WYKONANE: `+ object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`; wyjątek Swagger obowiązuje tylko poza prod. **SW zweryfikowany na buildzie prod** (`frontend/e2e/tools/sw-check.mjs`, Playwright Chromium na `pasnik-app:latest`): scope `/`, `activated`, precache 65 wpisów, zero błędów CSP. 07_SECURITY §3.
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
- [x] **3. Endpointy uploadu nie mają rate limitu.** WYKONANE: `app/core/ratelimits.py` — zdjęcia (przepis, wariant) 30/min/IP, `POST /import/pdf` i `POST /transfer/import` 10/min/IP; do tego druga połowa ochrony — `app/core/body_limit.py` (413 przed aplikacją, także chunked; uploady = limit + 1 MB marginesu, reszta `REQUEST_MAX_BODY_MB`=2). Testy: `tests/api/test_upload_rate_limits.py`, `tests/api/test_body_limit_api.py`, `tests/unit/test_body_limit.py`. Limity ma `/auth/login`
      (5/min/IP), `/import/jobs/{id}/ai-suggest` (10/min) i cała ścieżka
      `/public/*` (60/min wspólnie). NIE mają go: `POST /import/pdf` (25 MB
      na żądanie!), `POST /recipes/{id}/photo`, `PUT /retail-products/{id}/photo`
      i `POST /transfer/import` (100 MB). Model zagrożeń §1 nie broni się przed
      członkiem rodziny, ale broni przed PRZEJĘTĄ sesją — a tam jedyny koszt
      zapełnienia dysku Odroida to pętla `curl`. To naturalnie łączy się
      ze Stage 3 (body limit): limit rozmiaru i limit częstości to dwie
      połowy tej samej ochrony.
- [x] **4. Pliki uploadów bez referencji nie mają żadnego sprzątacza.** WYKONANE: `task uploads-report` (`python -m app.cli uploads-report`, `app/core/uploads_report.py`) — klasyfikuje referencjonowane / tymczasowe (`transfer/`) / OSIEROCONE i wiersze bez pliku; NIC nie kasuje (D10). Zmierzone na bazie dev: 10 plików, 11,6 MB; 5 z referencją, 2 scratch, **3 osierocone, 4,4 MB** (`5a7156f3…`, `b025f343…`, `e4d92d5a…`) — zgodnie z R4. Test: `tests/unit/test_uploads_report.py`.
      R4 znalazł w `backend/data/uploads/import-pdf/` **trzy PDF-y (4,4 MB)**,
      do których nie prowadzi żaden wiersz `import_jobs` — pozostałość po
      testach dziedziczących `UPLOADS_DIR` z `.env` (dług **U26**) i po
      resecie bazy dev z D23. Na produkcji ten sam mechanizm zostawi śmieci
      po każdym nieudanym imporcie. **Nie budować crona kasującego** (D10:
      nic nie usuwamy automatycznie) — wystarczy komenda raportująca „pliki
      bez referencji", którą runbook backupu woła obok `du`.
- [x] **6. Prefiks `__Host-` dla cookies sesji i CSRF** WYKONANE: `core/cookies.py::session_cookie_name/csrf_cookie_name(settings)` — `__Host-` razem z `Secure` (`APP_ENV=prod`); deps, middleware CSRF i router auth czytają nazwę przez te funkcje; frontend `CSRF_COOKIE_CANDIDATES` (`client.ts`, `transfer.ts`), E2E `cleanup.ts` to samo. Testy: `tests/unit/test_cookies.py`, `test_auth.py::test_w_prod_cookies_maja_prefiks_host_i_dzialaja_pod_nim`, `client.spec.ts`. Zweryfikowane na obrazie prod: login → `__Host-pasnik_session`/`__Host-csrf_token`, `/auth/me` 200 pod prefiksowaną nazwą. (obserwacja z audytu
      frontendu w R4). Double-submit czyta PIERWSZE ciasteczko `csrf_token`
      z `document.cookie` — to standardowe zastrzeżenie tego wzorca: subdomena
      albo sąsiad na tym samym rejestrowalnym domenie mogłaby przypiąć własną
      parę cookie+nagłówek. Lekarstwo nie leży we froncie, tylko w `Set-Cookie`:
      prefiks `__Host-` wiąże ciasteczko z dokładnie jednym hostem i `Path=/`.
      **Pułapka wykonawcza**: `__Host-` WYMAGA flagi `Secure`, więc na
      `http://localhost` przeglądarka takie ciasteczko odrzuci — nazwa musi być
      zależna od `APP_ENV` tak samo, jak dziś jest `Secure`
      (`app/core/cookies.py`). Zmiana wylogowuje istniejące sesje.
- [x] **7. `create_async_engine` bez `hide_parameters=True`** WYKONANE: `core/db.py`, jedna linia; żaden test nie asertował `[parameters: ...]`. Test: `test_cookies.py::test_silnik_bazy_ukrywa_parametry_w_komunikatach_bledow`. (obserwacja
      z audytu core w R4). `core/errors.py` loguje pełny traceback, a
      SQLAlchemy dokleja do komunikatu `DBAPIError` sekcję `[parameters: ...]`.
      Nieobsłużony błąd na INSERCIE do `sessions` wypisałby więc **token sesji**
      do logu — dokładnie to, czego zabrania 07_SECURITY §8. Nie da się tego
      wywołać z zewnątrz (to awaria bazy, nie żądanie użytkownika), więc nie
      jest to dziura, tylko jedna linia w `core/db.py`, która zamyka klasę
      problemu.
- [x] **8. `PRIVATE_SUBDIRS` porównuje się z uwzględnieniem wielkości liter** WYKONANE: `parts[0].lower()` w `resolve_upload_path`; test `test_prywatny_podkatalog_jest_zamkniety_niezaleznie_od_wielkosci_liter`.
      (`core/uploads.py:157`). Na Linuksie produkcyjnym nieszkodliwe, bo
      `/uploads/Transfer/...` po prostu nie istnieje. Na hoście deweloperskim
      z systemem plików bez rozróżniania wielkości liter (Windows, macOS)
      ścieżka `Transfer/` przechodzi kontrolę i trafia w ten sam plik.
      `parts[0].lower()` zamyka temat niezależnie od systemu.
- [x] **5. Zajętość `/srv/pasnik/uploads` do runbooka backupu** WYKONANE: `backup.sh` loguje `du -sh` katalogu uploadów i katalogu backupów przy każdym przebiegu (widoczne w `docker logs backup`), a `task uploads-report` daje rozbicie na pliki; 09 §3 wskazuje oba jako pozycje runbooku B18. (rewizja
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

- [x] Ustalenia R4 wykonane i odhaczone
- [x] Dockerfile target prod (nie-root, dist, workers=2) + tagowanie git
- [x] Config: wszystkie wartości prod przez env; `.env.example` kompletny
- [x] Limity rozmiaru request (413 w kształcie błędu)
- [x] Logging prod JSON + LOG_LEVEL + weryfikacja braku tokenów
- [x] Healthcheck: db + migracje + dysk, statusy ok/degraded
- [x] backup.sh (pg_dump -Fc + tar uploads + prune 7d/4w) + restore.sh
- [x] Kontener cron w profilu backup
- [x] Taskfile: backup/restore/build-prod
- [x] Round-trip backup→restore wykonany realnie
- [x] Testy: degraded, prune, limit, smoke obrazu prod
- [x] 09_DEPLOYMENT + PROGRESS zaktualizowane

## Verification checklist

- [x] `task check` zielony (testy+lint+typecheck)
- [x] `alembic heads` = 1 (jeśli doszła migracja: up/down/up przechodzi)
- [x] Round-trip backup→restore: raport z czasami i weryfikacją danych
- [x] Obraz prod zbudowany i uruchomiony (smoke)
- [x] Acceptance Criteria 1–8 odhaczone
- [x] `/code-review` zmian wykonany przed commitem
- [x] Commit `batch(17): ...`, `git status` czysty

## Completion notes

**Wykonane (2026-09-05).** Wszystkie osiem punktów „Ustaleń R4" (odhaczone
wyżej z opisem), Stage 2–8 z karty. Szczegóły stanu faktycznego: 09_DEPLOYMENT
§1–6, 07_SECURITY §2/§3/§6/§7/§8, ADR-003, CLAUDE.md „Dołożone w BATCH_17",
skille `pasnik-backend`/`pasnik-security`, karta B18 („Stan FAKTYCZNY po
BATCH_17").

**Wyniki uruchomień (realne):** `task check` **exit 0** na finalnym drzewie: 3 migrations-check / **482 unit** (20 s) / **333 integration** (2 min 42 s) / **436 api** (13 min 23 s) / **429 vitest w 47 plikach** / mypy 217 plików + vue-tsc / ruff / eslint / prettier / `vite build` (71 wpisów precache) / **fe-types-check** (kontrakt zgodny z kodem). Przyrost wobec wejścia (432/330/414/428): **+50 unit, +3 integration, +22 api, +1 vitest**. E2E: **21/21 w DWÓCH kolejnych przebiegach** (1,9 min i 2,0 min), zero flaków. `task audit`: pip-audit „No known vulnerabilities found", `npm audit --audit-level=high` „found 0 vulnerabilities". `task secrets-scan`: „no leaks found" (38 commitów, 6,28 MB). `alembic heads`: jedna głowa `0015` — batch nie dodał migracji.

**Round-trip backup → restore (REALNIE, `task backup-drill` =
`docker/backup/drill.sh`, stack `docker/compose.test.yml`, obraz
`pasnik-app:c7d0fee-dirty`, Docker Desktop/Windows):** czysta baza → migracje →
`create-admin` → seed demo → zdjęcie przepisu przez API → liczności 18 tabel
i 2 pliki uploadów → **backup 1 s** (dump 132 KB `-Fc`, uploady 12 KB tar.gz,
`sha256`) → `down -v` (wolumeny skasowane, potwierdzone `docker volume ls`) →
`restore.sh --wipe-uploads` (sumy kontrolne zgodne, `pg_restore` 1 s,
`alembic_version = 0015`) → `alembic upgrade head` (no-op) → app → health `ok`
po **19 s** od startu restore → liczności PO == PRZED co do wiersza
(users 1, canonical_products 15, product_unit_weights 10, retail_products 10,
stores 1, recipes 5, recipe_ingredients 15, plan_days 7, plan_meals 15,
plan_meal_items 16, audit_entries 1, reszta 0), 2/2 plików uploadów, smoke:
login, przepisy 5, dni planu 7, listy 0, zdjęcie przepisu HTTP 200. **Całość
85 s.** Uczciwe zastrzeżenie: seed demo nie ma list zakupowych ani spiżarni
(liczności 0 == 0) — pokrycie tych tabel daje test R4 (round-trip transferu)
i sam `pg_dump`, który nie rozróżnia tabel.

**Smoke obrazu prod (`docker/compose.test.yml`, curl + Playwright):** health
200 `ok`, CSP z nowymi dyrektywami na każdej odpowiedzi (także 404 `/api/docs`
w prod), `/` i `/plan-dnia` → `index.html` `no-cache`, `manifest.webmanifest`
→ `application/manifest+json` `no-cache`, `sw.js` → `text/javascript`
`no-cache`, `assets/*.js` → `immutable`, `/api/v1/nope` → 404 JSON (nie HTML),
`/uploads/...` bez sesji → 401, traversal → 404, brak nagłówka `Server`.
Obraz: `USER pasnik` (uid 10001), `APP_VERSION` = tag, zero dev-deps
(`pip list | grep pytest|ruff|mypy` = 0), `docker history` bez sekretów,
681 MB (`pasnik-backup` 488 MB).

**Logi prod (grep po realnym stdout kontenera, 32 linie po logowaniu, `/auth/me`,
żądaniu z fałszywym tokenem publicznym):** hasło 0 trafień, id sesji 0,
token publiczny 0, `sk-ant` 0, maskowanie `/public/lists/***` w OBU warstwach
(structlog + `uvicorn.access`), 30/32 linii to JSON — wyjątkiem są dwie linie
startowe supervisora uvicorna (proces nadrzędny nie wykonuje `create_app`),
opisane w 09 §6.

**Decyzje implementującego (karta pozwalała):**
- **cron = pętla `sleep` (`cron-loop.sh`), nie crond**: crond w `postgres:17`
  to dodatkowy demon, który nie oddaje wyjścia zadań na stdout kontenera bez
  obejść i gubi env (jedyne źródło konfiguracji); pętla ma 30 linii i trap na
  SIGTERM.
- **pomiar dysku**: `shutil.disk_usage` na najbliższym istniejącym przodku
  katalogu uploadów (bind mount = dysk danych), próg `DISK_MIN_FREE_MB`.
- **`degraded` = HTTP 200** (uzasadnienie w 09 §2 i docstringu `health.py`).
- **`SECRET_KEY` zostaje wymagane i ZAREZERWOWANE** (R1 pkt 2, U13) —
  wariant „dopisać wprost" z karty; 07_SECURITY §7 i `.env.example`.
- **`fe-types-check` WESZŁO do `task check`** (R1 pkt 1, U12), ale NIE jako
  `git diff --exit-code`: `task check` jest bramką PRZED commitem, więc drzewo
  jest brudne z definicji i porównanie z HEAD padałoby w każdym batchu
  zmieniającym API (złapane realnym przebiegiem bramki). `scripts/
  check_api_contract.py` generuje oba pliki do katalogu tymczasowego
  i porównuje bajtowo z repo — bez gita. Zweryfikowane w obie strony:
  świeży kontrakt przechodzi, podmieniony tytuł w `openapi.json` daje exit 1
  z komunikatem po polsku. Koszt ~5 s. **`secrets-scan` NIE weszło**
  (R2 pkt 5): wymaga obrazu z Docker Hub i sieci — zostaje bramką Review/B17
  i ma być wywołane w procedurze deploy B18.
- **Parametry argon2 / TTL 30 dni / blokada 10×15 min — bez zmian** (B02 pkt 2),
  uzasadnienie w 07 §2 razem z konsekwencją `UVICORN_WORKERS=2` (limity slowapi
  per proces ⇒ ×2; twardą granicą jest blokada konta w bazie).
- **Zimny start (R2 pkt 4) — świadomie przyjęty**, opisany w 09 §2; bez
  rozgrzewki w healthchecku.
- **Retencja**: 7 dni zachowuje WSZYSTKIE zestawy z dnia (nie tylko najnowszy),
  żeby ręczny backup przed migracją nie zginął przez nocny — `backup_prune.py`.
- **Kopia env w backupie** wyłączona domyślnie (`BACKUP_ENV_FILE` puste) — env
  żyje na hoście; B18 decyduje o montowaniu.
- **UID 10001 wspólny dla obrazu app i backup** — oba piszą do wolumenu
  uploadów; bind mounty na hoście dostają `chown 10001:10001` (09 §1).

**Odstępstwa od karty:**
- Nazwa zmiennej limitu zdjęcia to `IMAGE_MAX_UPLOAD_MB`, nie
  `MAX_UPLOAD_IMAGE_MB` — spójnie z istniejącymi `PDF_MAX_UPLOAD_MB` /
  `TRANSFER_MAX_ZIP_MB`.
- `task backup` / `task restore` operują na STACKU TESTOWYM
  (`compose.test.yml`), nie na dev — dev nie ma profilu backup, bo baza dev
  to dane właściciela, a ćwiczenia mają iść na czystej instancji (Implementation
  Notes); compose.prod spina te same skrypty (B18).
- `docker/backup/crontab` nie istnieje (zamiennik: `cron-loop.sh`, uzasadnienie
  wyżej).
- Użytkownik PG bez SUPERUSER (07 §9) — ZWERYFIKOWANE jako nieegzekwowane
  i opisane w 09 §5 z receptą dla B18; skrypt init roli to compose.prod (B18).

**Pułapki znalezione po drodze (dla B18 i kolejnych):**
- **Supervisor uvicorna zabija workery nieodpowiadające na ping w 5 s** —
  na obciążonym hoście worker importujący aplikację umierał w pętli („Child
  process [n] died", bez tracebacku). `entrypoint.sh` ustawia
  `--timeout-worker-healthcheck 30` (`UVICORN_WORKER_HEALTHCHECK_S`).
- `postgres:17` na wolnym dysku robił `initdb` ~60 s — healthcheck db w
  compose.test ma `retries: 24`, `start_period: 30s`; compose.prod ma to
  odziedziczyć.
- Git Bash konwertuje `/backups/x` na ścieżkę Windows przed dockerem —
  `drill.sh` ustawia `MSYS_NO_PATHCONV=1`; `python3` bywa stubem Store —
  skrypt wybiera działający interpreter.
- FastAPI zamienia KAŻDY wyjątek podczas czytania ciała w 400 — middleware
  limitu ciała musi sam wysłać 413 i wyciszyć późniejszą odpowiedź aplikacji
  (komentarz w `body_limit.py`).
- Cookie `__Host-` nie da się ustawić w jsdom po http (egzekwuje reguły
  prefiksu) — test frontendu podstawia getter `document.cookie`.
- **Każdy przebieg `task test-e2e` dodaje job importu i PDF na dysku**
  (`cleanup.ts` nie sprząta `import_jobs`, statusy rozstrzygnięte są
  nieusuwalne) — katalog uploadów rośnie także bez użytkownika; `task
  uploads-report` to pokazuje. Follow-up bez zmiany kodu: okresowy raport
  w runbooku (B18), nie automat (D10).

**Follow-upy (poza zakresem, do rejestru w PROGRESS):**
- Rola PG `NOSUPERUSER` + init-skrypt — B18 (opisane w 09 §5).
- `FORWARDED_ALLOW_IPS` = brama sieci compose albo `*` — B18 wpisuje po
  `docker network inspect`.
- Weryfikacja SW i HSTS na REALNEJ domenie — B18 (`sw-check.mjs` przyjmuje URL).
- `secrets-scan` w procedurze deploy — B18.

**Pytania do właściciela:** brak. Skille: SKILL-BE i SKILL-SEC załadowane na
starcie; `/code-review` i `/security-review` uruchomione na diffie przed
commitem (ustalenia niżej).

**Ustalenia review (diff przed commitem):** `/code-review` (high, osiem kątów) dał **10 ustaleń — wszystkie naprawione
w tym commicie**, z testami tam, gdzie da się je zaasercjonować:

1. **Tracebacki rekordów stdlib ginęły w JSON-logu prod** — `foreign_pre_chain`
   `ProcessorFormatter` bez `format_exc_info`; `exc_info` z „Exception in ASGI
   application" wychodziło jako krotka z adresem obiektu. Test
   `test_w_prod_traceback_rekordu_stdlib_trafia_do_json`.
2. **Import zdjęć z paczki transferu ignorował `IMAGE_MAX_UPLOAD_MB`** (trzeci
   wywołujący `save_image` bez `max_bytes`) — zdjęcie przyjęte przez instancję
   z limitem 20 MB nie wracało z jej własnego eksportu. `TransferService`
   dostaje `image_max_mb` z `Settings`.
3. **Catch-all SPA jako `@router.get` dawał 405 dla `HEAD /` i dla nieznanych
   `/api/*` z metodą inną niż GET** (Starlette: dopasowana ścieżka + zła
   metoda = 405) — rozjazd prod-only wobec kontraktu 404. Router przyjmuje
   wszystkie metody, `/api|/uploads` → 404, mutacja na trasie SPA → 405; nowy
   `tests/api/test_spa.py` (7 testów: index/HEAD/cache/manifest/404/405/
   traversal/ConfigurationError). Zbiór plików `dist/` liczony RAZ przy starcie
   (`frozenset`) — bez `resolve()`/`stat()` w pętli zdarzeń i bez własnej
   logiki anty-traversal.
4. **Dev-deps w warstwie `base` obrazu** — `uv sync` instaluje grupę `dev`
   domyślnie, a `--no-dev` w `prod` kasował pliki w NOWEJ warstwie (obraz
   681 MB). `base` ma `--no-dev`, `dev` dokłada grupę jawnie: **476 MB**,
   `pip list | grep pytest|ruff|mypy` = 0.
5. **Dwa timeouty bazy w health (6 s) przekraczały `--timeout 5s` HEALTHCHECK-u**
   — jedno zapytanie (`SELECT version_num FROM alembic_version`) z rozróżnieniem
   `ProgrammingError` (baza żyje, niezmigrowana) od reszty (`fail`); head
   migracji rozgrzewany przy składaniu aplikacji.
6. **`LOG_LEVEL=WARN|FATAL` wywalał uvicorna na starcie** (zna tylko
   critical|error|warning|info|debug|trace) — mapowanie synonimów w
   `entrypoint.sh`.
7. **`drill.sh` sourcował `.env` jako skrypt bash** — hasło z `&` lub `$`
   zostałoby wykonane/ucięte; zmienne przychodzą z `dotenv:` Taskfile'a.
8. **Testy 413 zdjęcia asertowały stałą `MAX_IMAGE_BYTES`, nie limit
   z konfiguracji** — po zmianie `IMAGE_MAX_UPLOAD_MB` w `.env` bramka
   czerwieniłaby się na poprawnej konfiguracji.
9. **Ścieżki `/backups/x` przechodziły przez shell hosta** (Git Bash → ścieżka
   Windows) — `restore.sh` szuka gołych nazw w `BACKUP_DIR`, `task restore`
   i drill podają nazwy plików.
10. **Wyjątek CSP dla Swaggera z literałami ścieżek i `APP_ENV`** — teraz
    wynika z `app.docs_url`/`openapi_url` (w prod `None` ⇒ zero wyjątków).

Do tego z kątów reuse/simplification: `request_settings(request)` w jednym
miejscu (`core/config.py`), `UploadTooLargeError` jako podklasa
`PayloadTooLargeError`, wspólny `_TIMESTAMPER` dla obu strumieni logów,
szybka ścieżka body-limit przy `Content-Length` (bez opakowywania
`receive`/`send`), poprawiony komentarz o metodach, martwa gałąź
`format_size`, nowy test „każdy endpoint multipart ma regułę limitu"
(z OpenAPI) — pilnuje drugiej tabeli tras. **Świadomie NIE zrobione** (poza
zakresem, wpisane do długu): dedykowane `COOKIE_SECURE` zamiast `APP_ENV==prod`
i serwer zwracający nazwę cookie CSRF w odpowiedzi logowania (kandydaci na
decyzję, nie na cichą zmianę); wspólna stała `MIB`; helpery testowe w
`tests/helpers.py`.

`/security-review` (pełny diff, z filtrem fałszywych alarmów): **1 ustalenie,
naprawione** — **po dołożeniu serwowania SPA trasa `/l/<token>` (publiczny link
listy) trafia do backendu, a oba maskowania (`mask_path`, `MaskPublicTokenFilter`)
znały tylko `/public/lists/`** — każde otwarcie linku z telefonu wpisywałoby
token równoważny hasłu do listy do obu logów prod. Wzorzec
`_PUBLIC_TOKEN_PATH` obejmuje `/l/`, testy w `tests/unit/test_logging.py`,
07_SECURITY §5 pkt 9a. Pozostałe obszary sprawdzone jako czyste: catch-all SPA
(zbiór plików, traversal → `index.html`), body-limit (brak desync — uvicorn
dosysa resztę ciała po `response_complete`), cookies `__Host-` (nazwa z jednego
źródła, kandydaci frontendu nie obniżają porównania), health (tylko statusy),
`--proxy-headers` z domyślnym `FORWARDED_ALLOW_IPS=127.0.0.1`, `.dockerignore`,
skrypty backupu (bez connection stringów w logach).
