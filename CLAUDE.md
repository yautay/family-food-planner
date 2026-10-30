# CLAUDE.md

**Faza projektu: implementacja batchami. Fundament (BATCH_01) gotowy.**
Ten plik to kontrakt repo: komendy, wzorce kodu i twarde zakazy. Procedura
sesji: `docs/implementation-plan/implementation_prompt.md`.

## 1. Proces

1. Implementację prowadzi się WYŁĄCZNIE batchami:
   `docs/implementation-plan/implementation_prompt.md` → procedura,
   `docs/implementation-plan/batches/` → karty, `PROGRESS.md` → statusy.
2. Architektura jest zaprojektowana (`docs/architecture/`, `docs/adr/`).
   Nie projektuj jej ponownie; konflikt rzeczywistości z dokumentem =
   pytanie do właściciela albo wpis w `02_DECISIONS.md`, nie cicha zmiana.
3. Decyzje właściciela: `docs/implementation-plan/02_DECISIONS.md`.
   Decyzja-bramka w statusie OPEN blokuje wskazany batch.
4. Skille: karta batcha ma sekcję „Skills" — Required ładujesz na starcie
   sesji, Review uruchamiasz na diffie przed commitem. Manifest i mapa
   ID→skill: `docs/implementation-plan/03_AI_SKILLS.md`. Hierarchia przy
   konfliktach: właściciel > ADR/architektura > karta batcha > master
   prompt > CLAUDE.md > skille > ogólna wiedza. Skill NIGDY nie nadpisuje
   ADR (np. żadnego JWT, bo skill tak radzi — obowiązuje ADR-003).
5. Jeden batch = jeden finalny commit `batch(XX): opis`; bez push.
6. Testy uruchamiaj realnie i raportuj faktyczne wyniki.

## 2. Twarde zakazy (od pierwszej linii kodu)

- **float** dla ilości/wartości odżywczych — zawsze Decimal/NUMERIC, a w JSON
  stringi dziesiętne (ADR-008, 04_API §1),
- kopiowanie stanu serwera do Pinia — stan serwera żyje w TanStack Query
  (ADR-007),
- endpoint zasobu bez testu macierzy uprawnień/scope (08_TESTING §4),
- zakres `global` dla czegokolwiek poza przepisami — wspólny `Scope` ma DWIE
  wartości, a trzecią (`global`) ma wyłącznie `RecipeScope` (D32, ADR-006 aneks),
- warstwa i18n — UI wyłącznie po polsku (D3, ADR-007),
- sekrety w plikach śledzonych; `.env` nigdy w repo (07_SECURITY §7),
- migracja z numerem „zarezerwowanym" — numer = pierwszy wolny,
  `down_revision` z `alembic heads` (ADR-017 pkt 7, dawniej ADR-002),
- ręczne interfejsy TS dla odpowiedzi API — typy pochodzą z `task fe-types`,
- biblioteki wykresów — wykresy to własne SVG (ADR-013).

## 3. Komendy (Taskfile — jedyne wejście)

Wymagane na hoście: **Docker Desktop, uv, Node 22+, go-task**. Do deployu
produkcyjnego (B18a) dodatkowo **WSL (Ubuntu) z `ansible-core>=2.16,<2.18`
z pipa** w `~/.venvs/ansible` (NIE z apt) i `task deploy-galaxy` (role
ansistrano) — szczegóły w `deploy/README.md`.
Start od zera: `cp .env.example .env` → `task install` → `task dev`.

| Komenda | Do czego |
|---|---|
| `task dev` | cały stack w Dockerze (app + frontend + db + db-test), hot reload |
| `task dev-db` | same bazy (gdy testy uruchamiasz z hosta) |
| `task down` / `task logs` | zatrzymanie / logi |
| `task check` | **BRAMKA DoD**: migrations-check + unit + int + api + fe-test + typecheck + lint + format-check + fe-build + fe-types-check |
| `task test-unit` / `test-int` / `test-api` / `test-be` | pytest wg markerów; zawężenie przez `--`, np. `task test-int -- -k wydajnosc -s` |
| `task fe-test` | vitest |
| `task test-e2e` (+ `task e2e-install`) | Playwright, chromium; zawężenie przez `--`, np. `task test-e2e -- offline-lista.spec.ts` |
| `task test-e2e-linux` | ta sama suita i lokalny stack w oficjalnym obrazie Playwright 1.62.1; stabilne Chromium Linux jako obejście `ERR_NO_BUFFER_SPACE` Windows, bez zmiany zależności/flagów; argumenty po `--` |
| `task typecheck` / `lint` / `format` / `format-check` | mypy+vue-tsc / ruff+eslint / ruff format+prettier |
| `task db-migrate` / `db-heads` / `db-revision -- --rev-id 0002 -m "opis"` | Alembic |
| `task fe-types` / `fe-types-check` | OpenAPI → `backend/openapi.json` → `frontend/src/api/generated.ts` (oba commitowane); `-check` = porównanie „wygenerowane teraz" z „w repo" (bramka świeżości kontraktu, w `task check`; NIE `git diff` — bramka DoD chodzi po brudnym drzewie) |
| `task audit` / `task secrets-scan` | Review batche i BATCH_17 |
| `task create-admin` | tworzy konto ADMIN (prompt albo `PASNIK_ADMIN_*` z env; nigdy hasło w repo) |
| `task db-seed-demo` | idempotentny seed demo (od B04: ~15 produktów; kolejne encje dokładają batche domenowe) |
| `task ux-baseline -- --photo <lokalny-plik>` | izolowany zestaw danych UX00 do kontroli rzeczywistego UI; wyłącznie bazy `pasnik_ux` / `pasnik_ux_test`, bez resetu danych (instrukcja `ux-redesign/FIXTURE.md`) |
| `task pdfx-index` / `pdfx-verify` / `pdfx-package` / `pdfx-roundtrip` | **`/pdf-extract` (B22, D31)**: katalog i zestawienie produktów / weryfikacja silnikiem aplikacji (+ `--report`) / paczka transferu `export.zip` / import paczki na bazie TESTOWEJ dwa razy; parametry po `--`, ścieżki od korzenia repo |
| `task uploads-report` | pliki uploadów BEZ referencji w bazie — TYLKO raport, nic nie kasuje (D10) |
| `task build-prod` | obrazy `pasnik-app:<git describe>` (+`:latest`, SPA w środku, ADR-014) i `pasnik-backup` |
| `task test-stack-up` / `test-stack-down` | stack testowy obrazu prod (`docker/compose.test.yml`, app na 127.0.0.1:8081) / kasacja z wolumenami |
| `task backup` / `task restore -- <dump> [tar] [--wipe-uploads]` | backup i restore stacku testowego (`docker/backup/*.sh`) |
| `task backup-drill` | round-trip backup → `down -v` → restore → smoke (`docker/backup/drill.sh`, wymaga `PASNIK_TEST_BACKUPS_DIR`) |
| `task provision` | **PRODUKCJA** (B18a): provision maszyny LXC kanałem root (unity, `pasnik.env`, `pgpass`, `pasnik-cli`); vault z sekretami POZA repo (`~/pasnik-prod.yml`) |
| `task deploy` | **PRODUKCJA**: `fe-build` → `secrets-scan` → ansistrano (dump → migracja → symlink → restart → health z asercją na treść); próba: `-- --check --diff` |
| `task rollback` | **PRODUKCJA**: poprzedni release (migracji NIE cofa — `deploy/README.md`) |
| `task deploy-galaxy` / `deploy-syntax` / `deploy-caddy-vhost` | role Ansible / `--syntax-check` playbooków / przykład bloku Caddy (D7) |

Nigdy nie wołaj gołego `pytest`/`vitest`/`alembic` — Taskfile wstrzykuje
`.env` i właściwy interpreter.

**Produkcja jest poza zasięgiem sesji AI.** `task provision|deploy|rollback`
i każde polecenie na hostach .111/.121 (Incus, ufw, DOCKER-USER, Caddy,
klaster `postgres-apps`) wykonuje albo zatwierdza właściciel wg runbooków
(`deploy/README.md`, `deploy/lxc/README.md`, od 18b `docs/OPERATIONS.md`) —
agent ich nie wymyśla, nie obchodzi blokad i nie dotyka bazy `ffp_db` poza
tym, co opisuje runbook. Sekrety (hasło `ffp_user`, `SECRET_KEY`) żyją
w vaulcie poza repo i nigdy nie trafiają do czatu ani do plików śledzonych.

## 4. Backend — wzorzec kodu

Moduł: `backend/app/modules/<nazwa>/{models,schemas,service,router}.py`.
`router.py` (HTTP + walidacja wejścia) → `service.py` (logika, transakcje,
autoryzacja scope, jedyne I/O) → `models.py` (SQLAlchemy 2.0 typed).
Router nigdy nie dotyka sesji DB; moduł→moduł wyłącznie przez service.
Silniki obliczeń (`nutrition/engine.py`, `shopping/engine.py`) to czyste
funkcje bez I/O (ADR-008). Katalogi modułów tworzy batch, który je zasiedla.

Fundament dostarczony w BATCH_01 i BATCH_02:

- `app/core/config.py` — `Settings` (pydantic-settings). Nowa zmienna =
  wpis w `.env.example` **i w `deploy/templates/pasnik.env.j2`** (+ wartość
  w `deploy/group_vars/prod.yml`, jeśli jest konfigurowalna) w tym samym
  commicie — pilnuje tego `tests/unit/test_deploy_config.py` (wyjątek:
  `APP_VERSION`, wersję podaje `serve.sh` z pliku release'u). Wartości
  w `pasnik.env` bez spacji i cudzysłowów (plik czyta systemd i `pasnik-cli`). Brak wymaganej zmiennej =
  `ConfigurationError` z komunikatem po polsku.
- `app/core/db.py` — `Base` (naming convention!), `TimestampMixin`
  (`created_at`/`updated_at`), silnik async (`postgresql+psycopg://`,
  ADR-015), `get_session` jako dependency, `selector_loop_factory()` dla
  narzędzi uruchamianych na Windows.
- `app/models.py` — rejestr modeli. Nowy moduł z tabelami = jedna linia
  tutaj, inaczej Alembic nie widzi schematu.
- `app/core/errors.py` — `AppError` + podklasy (`NotFoundError`,
  `ForbiddenError`, `ConflictError`, …) i handlery. Serwisy rzucają te
  wyjątki, NIE `HTTPException`. Kształt odpowiedzi:
  `{"error": {code, message, details}}`, message po polsku.
- `app/core/logging.py` — structlog + middleware requestów (request id,
  ścieżka maskowana dla `/public/lists/*`). Nigdy nie loguj haseł, tokenów
  ani payloadów (07_SECURITY §8).
- `app/core/security.py` — argon2id (hash/verify/rehash), `generate_token`
  (`secrets.token_urlsafe(32)`), `tokens_match` (`hmac.compare_digest`),
  TTL sesji i czyste funkcje blokady konta. Żadnej własnej kryptografii.
- `app/core/deps.py` — JEDYNE wejście autoryzacji: `CurrentUser`,
  `AdminUser`, `require_admin`. Nowy moduł ich używa, nie czyta cookie sam.
- `app/core/cookies.py` — nazwy i atrybuty cookies sesji/CSRF (jedno miejsce).
- `app/core/middleware.py` — CSRF double-submit (`CSRF_EXEMPT_PREFIXES`)
  + nagłówki bezpieczeństwa i CSP (07_SECURITY §3).
- `app/main.py` — `create_app()` jako composition root (limiter slowapi,
  middleware, routery). Aplikacja NIE powstaje na poziomie modułu;
  uruchomienie: `uvicorn app.main:create_app --factory`.

Dołożone w BATCH_03 i BATCH_04 (też fundament — nie pisz tego od nowa):

- `app/core/scope.py` — `Scope`, `SCOPE_ENUM`, `ScopedMixin` (kolumny wzorca
  scope + PK), `ScopedQuery` (`select_visible`, `get_or_404`,
  `assert_can_manage`, `assert_scope_allowed`, `ownership_for_create`).
  Własny filtr widoczności w serwisie = błąd review; cudza encja to **404**.
  Typ enumowy `entity_scope` tworzy migracja PIERWSZEJ tabeli ze scope (B05).
  Od B21 także `RecipeScope`, `ScopedQuery(allow_global=True)` i
  `assert_can_edit_content` — patrz blok „Dołożone w BATCH_21".
- `app/core/deletion.py` — kontrakt 409: `UsedInRef`, `assert_deletable`,
  `conflict_from_integrity_error` (`details.used_in`). Moduł z FK do
  `canonical_products` rejestruje licznik referencji przez
  `catalog.service.register_product_reference_finder`.
- `app/core/schemas.py` — `DecimalString`: każde pole NUMERIC w odpowiedzi
  używa tego aliasu (OpenAPI `string` ⇒ `task fe-types` generuje `string`).
- `app/modules/catalog/units.py` — JEDYNE miejsce konwersji ilości
  (`normalize_amount`, `to_grams`, `to_basis_amount`, `base_unit` vs
  `basis_unit`); nieprzeliczalna ilość rzuca `UnitConversionError` (422)
  i zapis MUSI paść (02_DOMAIN §13.1).
- `app/modules/catalog/nutrition_adapter.py` — `ProductNutrition` /
  `nutrition_for` / `measure_for`: jedyne wejście SILNIKÓW do wartości
  odżywczych (ADR-004). Sięganie po kolumny `canonical_products`
  z pominięciem adaptera = błąd review.
- `app/modules/audit/service.py` — `AuditService.record()` NIE commituje
  (wpis w tej samej transakcji co operacja); nowa akcja = wpis w
  `AuditAction`/`AuditEntity`, konwencja `<encja>.<czasownik>`.

Dołożone w BATCH_05 (też fundament):

- `app/core/uploads.py` — JEDYNY pipeline obrazów (07_SECURITY §6):
  `save_image` (limit 10 MB → 413, sniffing Pillow → 422, re-encode JPEG,
  miniatura `_thumb`), `delete_image`, `thumbnail_path_for`,
  `resolve_upload_path`. Funkcje synchroniczne — serwis woła przez
  `run_in_threadpool`. Serving: `GET /uploads/{path}` z sesją
  (`app/main.py`), NIGDY StaticFiles. Katalog: `Settings.uploads_dir`.
- `app/modules/nutrition/{engine,types}.py` — czysty silnik obliczeń
  (ADR-008): wejście WYŁĄCZNIE `ProductNutrition` z adaptera, ilości na osi
  `basis_unit`; `NutritionValues` to kontrakt między batchami (zmiany tylko
  addytywne); zaokrągla wyłącznie `round_for_output` na wyjściu.
- `app/modules/recipes/service.py` — rejestr
  `register_recipe_reference_finder(finder)`: moduł z FK do `recipes`
  (plan B06, szablony B07) rejestruje licznik, inaczej 409 bez `used_in`.
- Enumy `entity_scope` i `amount_unit` istnieją od migracji `0006` — kolejne
  tabele ze scope/ilością używają `postgresql.ENUM(..., create_type=False)`
  (z `Scope`, dwuwartościowym; `entity_scope` ma od `0017` trzecią wartość
  `global`, ale używa jej WYŁĄCZNIE `recipes` przez `RecipeScope`).

Dołożone w BATCH_10 (też fundament):

- `app/modules/shopping/engine.py` — DRUGI czysty silnik (ADR-008): pipeline
  zakupowy na `Decimal`, wejście `EngineInput` (dataclassy), wyjście
  `PreviewResult`. Zawiera też `dump_input`/`load_input` (serializacja wejścia do
  `shopping_generations.params`, wersja `{"v": 1}`) oraz `quantize_amount`/
  `quantize_package` — JEDYNE zaokrąglenia ilości w module. `RoundMode` mieszka
  w silniku, model bazy tylko go odwzorowuje.
- `app/modules/catalog/units.py += to_base_amount` — ilość na osi
  PRZECHOWYWANIA produktu (`base_unit`); jedyne miejsce, które dzieli przez
  `piece_weight_g`. Zakupy liczą się na tej osi, wartości odżywcze na
  `basis_unit` — nie mieszać.
- Nowe publiczne wejścia serwisów (moduł→moduł tylko tak, §4):
  `PlanningService.demand_rows`, `RecipesService.ingredient_amounts`,
  `RetailService.options_for_products` i `variants_by_ids`.
- `app/modules/shopping/service.py` rejestruje TRZY liczniki referencji
  (produkt, wariant sklepowy, sklep) — `shopping_lists.store_id` ma SET NULL,
  więc bez licznika lista po cichu straciłaby profil sortowania.
- `scripts/` jest PAKIETEM: snapshot silnika importuje stałe seedu demo
  (`scripts.seed_demo`), żeby dane testu i dane komendy nie istniały dwa razy.

Dołożone w BATCH_11 (też fundament):

- `app/core/logging.py += MaskPublicTokenFilter` / `install_access_log_filter()`
  — maskowanie publicznego tokenu w **access logu Uvicorna** (nasz log maskuje
  `mask_path`, ale Uvicorn formatuje ścieżkę sam). Nowy endpoint pod
  `/public/lists/` dziedziczy to bez zmian; inny prefiks publiczny wymaga
  rozszerzenia wzorca `_PUBLIC_TOKEN_PATH` — od B17 wzorzec obejmuje też trasę
  SPA `/l/<token>`, bo backend serwuje SPA i widzi tę ścieżkę w logach.
- `app/core/errors.py += GoneError` (410, kod `gone`) — zasób, który ISTNIAŁ,
  ale przestał być dostępny. Treść komunikatu 410 i 404 na ścieżce publicznej
  jest IDENTYCZNA (nie potwierdzamy istnienia tokenu, ADR-010).
- `app/modules/shopping/lists_service.py` — DRUGI serwis modułu shopping (życie
  gotowej listy: odhaczanie, sklep, udostępnianie, przyjęcie do spiżarni).
  Ścieżka publiczna ma tu własne metody, które NIE przyjmują `User` i nie tykają
  `ScopedQuery` — autoryzuje je wyłącznie pełny token z URL-a.
- `app/modules/shopping/sorting.py` — czyste funkcje kolejności pozycji listy
  (profil sklepu → reszta wg globalnej pozycji kategorii; `already_have` na dół).
  **Sekcje składa SERWER**, nie przeglądarka: inaczej ta sama lista wyglądałaby
  inaczej na ekranie, na wydruku i pod publicznym linkiem.
- `app/modules/shopping/public_router.py` — JEDYNY router bez sesji poza
  `/health`. MUSI siedzieć pod `/api/v1/public/`: dokładnie ten prefiks jest
  zwolniony z CSRF (`CSRF_EXEMPT_PREFIXES`) i maskowany w logach (`mask_path`).
  Limit 60/min/IP jest WSPÓLNY dla całej ścieżki (`limiter.shared_limit`, scope
  `public-lists`), nie per endpoint; limiter wstrzykuje `create_app` (wzór
  `build_auth_router`).
- `PantryService.receive_purchase(actor, product_id, amount)` — przyjęcie
  ZAKUPÓW z jawną regułą scalania: dolewamy do pozycji tego produktu BEZ daty
  ważności, a gdy takiej nie ma, zakładamy nową (wiersz z datą to konkretna
  partia i dolanie skłamałoby o dacie).
- `checked_at` to moment OSTATNIEJ decyzji o checkboxie (także odznaczenia) —
  ustawia go serwer, klient nigdy go nie przysyła. Na tym oprze LWW z ADR-009
  w B12.
- Frontend: `meta.anonymous` w `src/router.ts` (trasa dla KAŻDEGO, bez
  przekierowania zalogowanego — inaczej niż `meta.public`, czyli ekran
  logowania), osobny klient `src/api/publicList.ts` (`credentials: 'omit'`, bez
  CSRF — `client.ts` NIE dostaje trybów warunkowych) oraz `src/assets/print.css`
  (reguły wyłącznie w `@media print`; ukrywają nawigację `AppShell`).

Dołożone w REVIEW R3 (audyt pionu zakupowego — też fundament):

- `app/modules/households/service.py += register_household_reference_finder`
  — rejestr liczników referencji do RODZINY (dług U16). Każda tabela ze scope
  trzyma `household_id` z `ON DELETE RESTRICT`, więc bez wpisu ADMIN dostaje
  409 z PUSTĄ listą „Używane w:" i nie wie, co blokuje usunięcie. Liczniki
  rejestrują dziś `recipes`, `planning` (dni), `planning/templates`
  (szablony + cykle), `pantry` i `shopping` (tury, generacje, listy).
  **Nowa tabela z `household_id` = nowy licznik w TYM SAMYM batchu.**
- **Pusty dzień planu sprząta się sam**: `PlanningService.delete_meal` usuwa
  wiersz `plan_days` bez posiłków i BEZ TYTUŁU (dług U17). `DELETE
  /plan/days/{date}` nie istnieje i nie ma powstać — 04_API §2 „Cykl życia
  dnia planu" opisuje stan faktyczny.
- `PantryService.receive_purchase` **NIE COMMITUJE** (wzorzec
  `AuditService.record`): commit należy do `accept_to_pantry`, więc przyjęcie
  całej listy jest JEDNĄ transakcją. Metoda serwisu wołana w pętli po pozycjach
  jednej akcji użytkownika nigdy nie commituje sama.
- **Dryf modelu jest teraz bramką**:
  `tests/integration/test_migrations.py::test_modele_nie_dryfuja_od_schematu_po_migracjach`
  porównuje `Base.metadata` ze schematem po `upgrade head`. Kolumna, której FK
  dopina PÓŹNIEJSZA migracja, musi dostać `ForeignKey` w modelu w tym samym
  commicie — inaczej pierwszy `--autogenerate` skasuje constraint.
- `src/assets/print.css` wymusza `color: #000` na `*` (nie tylko `body`):
  każdy tekst ma klasę z tokens, więc bez tego wydruk wychodził brązowo-szary,
  a 06_UIUX §6 mówi „czarno-biały".

Dołożone w BATCH_12 (też fundament):

- `shopping_list_items.received_at` (migracja `0013`, decyzja D19) —
  `accept_to_pantry` jest IDEMPOTENTNE: bierze pozycje odhaczone, nie
  „mam już w domu" i BEZ stempla, po czym stempluje je w TEJ SAMEJ transakcji
  co wpis w spiżarni. Dwa różne 409 (`NOTHING_TO_RECEIVE` i `ALREADY_RECEIVED`),
  addytywne `already_received` w odpowiedzi. Pole jest w odpowiedzi PRYWATNEJ,
  **nigdy w publicznej** (biała lista `PublicListItemRead`).
- `_apply_item_changes` w `lists_service.py` stosuje LAST-WRITE-WINS: PATCH
  checkboxa (prywatny i publiczny) przyjmuje opcjonalne `checked_at`
  (`AwareDatetime`, naiwna data = 422); starszy znacznik nie zmienia stanu,
  znacznik z przyszłości ponad `CLOCK_SKEW_TOLERANCE` (5 min) jest przycinany.
  **Warunku `checked != item.checked` nie wolno ruszać** — na nim stoi
  idempotencja PATCH-a, bez której kolejka offline dublowałaby zapisy.

Dołożone w REVIEW R4 (też fundament):

- `app/modules/transfer/serializer.py::Section.parent` + `importer.py::
  parent_blocked`/`mark_blocked` — kontrakt decyzji **D22**: import, który
  REUŻYWA wiersza, POMIJA jego sekcje-dzieci. Kryterium „dziecka" jest jedno
  i sprawdzalne w bazie: FK `ON DELETE CASCADE` do rodzica (ADR-012), więc
  składniki przepisu i posiłki dnia — tak, a produkt kanoniczny w składniku —
  nie. Nowa sekcja formatu z takim FK deklaruje `parent` w TYM SAMYM batchu,
  inaczej ten sam plik zaimportowany dwa razy podwoi zawartość rodzica.
  Sprawdzenie idzie PRZED `resolve_references` (pominięte dziecko nie trafia
  do `IdMap`, więc jego własne dzieci dostałyby „martwą referencję"), a tych
  samych funkcji używa raport DRY-RUN — `to_create` ma mówić to, co zrobi
  `apply`.
- `app/modules/nutrition/engine.py += round_field_for_output(field, value)` —
  zaokrąglenie POJEDYNCZEJ liczby tą samą regułą, co `round_for_output`
  (kcal → 1, reszta → 0,1). Używa go `stats_service.summarize` dla ŚREDNIEJ
  CELÓW i delty. Reguła bez zmian: liczba policzona z wartości odżywczych
  wychodzi na zewnątrz zaokrąglona, bo formatter frontendu obcina wyłącznie
  końcowe zera i pokaże `2085,714285714285714285714286` w całości.
- `nutrition/types.GOAL_NUMERIC_FIELDS` jest JEDYNĄ listą pól celu —
  `planning/service.py::_GOAL_FIELDS` (druga kopia z B13) już nie istnieje.
  Nowe pole celu = wpis w `types.py`, nigdzie indziej.

Dołożone w BATCH_17 (też fundament — nie pisz tego od nowa):

- `app/core/health.py` — `/api/v1/health` = `{status: ok|degraded, version,
  checks: {db, migrations, disk}}`, **zawsze HTTP 200** (09_DEPLOYMENT §2:
  `degraded` to informacja dla operatora, nie powód do restartu; healthcheck
  Dockera testuje sam kod). Head migracji liczony ze skryptów (bez `env.py`);
  próg dysku `DISK_MIN_FREE_MB`. Bez ścieżek, hostów i rewizji w odpowiedzi.
  Jawny wyjątek od reguły „router nie dotyka sesji DB" (§4): to router
  infrastrukturalny w `core/`, bez logiki domenowej — sesję przekazuje do
  `run_health_checks`, które jest jedynym I/O tego modułu.
- `app/core/body_limit.py` — czysty ASGI `BodyLimitMiddleware`: sufit ciała
  żądania PRZED aplikacją (413 w kształcie 04_API §1 także dla chunked).
  Uploady: limit z `Settings` + 1 MB marginesu; reszta `REQUEST_MAX_BODY_MB`.
  **Nowy endpoint uploadu = reguła w `build_body_limit_rules` + limit
  w `core/ratelimits.py` w tym samym batchu** — inaczej dostaje sufit 2 MB
  i zero rate limitu.
- `app/core/ratelimits.py` — limity uploadów (zdjęcia 30/min, paczka kopii
  danych 10/min); routery z uploadem dostają `limiter` z `create_app`
  (wzór `/auth`).
  Licznik slowapi jest per PROCES: przy `UVICORN_WORKERS=2` sufit ×2.
- `app/core/config.py::request_settings(request)` — JEDYNE miejsce, z którego
  middleware i dependency biorą `Settings` żądania (`app.state.settings`).
- `app/core/cookies.py` — nazwy cookies zależą od `APP_ENV`: w prod
  `__Host-pasnik_session` / `__Host-csrf_token` (`session_cookie_name` /
  `csrf_cookie_name(settings)`). **Literał nazwy cookie w kodzie = błąd
  review**; frontend sprawdza obie kandydatki (`CSRF_COOKIE_CANDIDATES`
  w `src/api/client.ts`), E2E to samo w `e2e/cleanup.ts`.
- `app/core/spa.py` — serwowanie `dist/` przez backend (ADR-014) tylko gdy
  `SPA_DIST_DIR` ustawione (obraz prod: `/app/static`); catch-all rejestrowany
  OSTATNI; `/api/*` i `/uploads/*` nigdy nie dostają `index.html`; `assets/`
  immutable, `index.html`/`sw.js`/`manifest` `no-cache` (kontrakt PWA).
- `app/core/logging.py` — w prod/test także rekordy stdlib (uvicorn) są
  JSON-em (`ProcessorFormatter`); `configure_logging(stream=)` do testów.
  Silnik bazy ma `hide_parameters=True` — nie wyłączaj (07_SECURITY §8).
- `app/core/uploads_report.py` + `python -m app.cli uploads-report` — raport
  plików bez referencji (D10: NIC nie kasuje). Nowa kolumna ze ścieżką pliku =
  wpis w `collect_references`, inaczej jej pliki wyjdą jako „osierocone".
- Limity plików są konfiguracją: `save_image(..., max_bytes=)`
  (`IMAGE_MAX_UPLOAD_MB`) i `TRANSFER_MAX_ZIP_MB`. Stałe w modułach to
  wartości domyślne.
- `docker/Dockerfile` target `prod` (+ `frontend-build`), `docker/entrypoint.sh`
  (`UVICORN_WORKERS`, `LOG_LEVEL`, `--proxy-headers`, `FORWARDED_ALLOW_IPS`
  czyta sam uvicorn), `docker/compose.test.yml`, `docker/backup/{backup,
  restore,cron-loop,drill}.sh`, retencja `backend/scripts/backup_prune.py`
  (stdlib only — jest kopiowany do obrazu backupu). Oba obrazy pracują jako
  UID 10001. Obraz prod i `compose.test.yml` to od D29 (ADR-017) LOKALNY test
  obrazu, nie droga na produkcję: produkcja = LXC + ansistrano (`deploy/`),
  Caddy i runbooki → B18.

Dołożone (i ZDJĘTE) w BATCH_20 — decyzja D25, ADR-016:

- **Importu jadłospisów PDF NIE MA i nie ma go pisać od nowa.** Zniknął moduł
  `app/modules/importer/` z całym obszarem przejściowym (migracja `0016`), obie
  zależności do czytania PDF-ów i do modelu, ich ustawienia, dwie kolumny
  `recipes` opisujące pochodzenie przepisu, metody serwisów istniejące
  wyłącznie dla niego (`RecipesService.create_imported_recipe` i
  `owned_names`, `CatalogService.find_by_name` i przyjmowanie próbek wag)
  oraz ekrany `/import*`. **Nowy import danych = ROZSZERZENIE formatu
  `transfer`** (sekcja w `serializer.py` + klucz naturalny + `parent`, gdy
  sekcja jest kompozycją), nie nowy moduł z obszarem przejściowym (ADR-016).
- `app/core/uploads.py` — `PRIVATE_SUBDIRS` (lista ZAKAZANYCH) zastąpione
  przez **`SERVED_SUBDIRS` (ALLOWLISTA**: `recipes`, `retail`,
  `transfer-import`). Katalog nieznany kodowi jest zamknięty z definicji, więc
  wycofanie funkcji nie udostępnia jej resztek każdemu zalogowanemu.
  **Nowy podkatalog uploadów = wpis TUTAJ w tym samym batchu**, inaczej
  zdjęcia z niego nie wyświetlą się w ogóle.
- `Section.merge_key` w `transfer/serializer.py` to teraz **UNIQUE sekcji dla
  DWÓCH konsumentów**: `apply` scala albo pomija po nim wiersz, a raport
  DRY-RUN sprawdza po nim, czy wiersz JUŻ jest w bazie. Sekcja `idempotent`
  MUSI mieć `merge_key` równy swojemu UNIQUE-owi — inaczej `to_create` zawyży
  (dług U21). Indeks buduje `TransferService._existing_index` (I/O),
  `importer.analyze` zostaje CZYSTE (ADR-008) i dostaje go argumentem razem
  z `actor_user_id`/`actor_household_id` (tłumaczy przez nie klucze obce,
  tak samo jak `apply`).
- `importer.merged_days_warning` — zbiorcze ostrzeżenie D24 („3 dni planu
  zostaną scalone…"), z odmianą liczebnika w kodzie: UI nie ma warstwy i18n
  (D3), więc polską gramatykę robimy sami.
- Teksty transferu mówią **„kopia danych rodziny"**, nie „eksport/import"
  (`lib/texts.ts::transfer`); w kodzie i API nazwy techniczne zostają.

Dołożone w BATCH_21 (zakres `global` dla przepisów — D32, ADR-006 aneks):

- **Dwa enumy, jeden typ PG.** `core/scope.py::Scope` (`private`, `household`) obsługuje
  KAŻDĄ encję ze scope poza przepisem; `RecipeScope` (+ `global`) — tylko `Recipe`
  (`Recipe.scope` nadpisuje kolumnę mixina własnym `RECIPE_SCOPE_ENUM`). Nowa encja
  ze scope używa `Scope` i NIE dziedziczy `global`; jej model niesie
  `no_global_scope_check_constraint()` (mixin dokłada go sam, własny `__table_args__`
  musi to zrobić jawnie).
- `ScopedQuery(Recipe, …, allow_global=True)` dopisuje `global` do `visible_condition`
  (NIGDY do `owned_condition` — na nim stoi eksport D26) i wymaga ROLI ADMIN w
  `assert_can_edit_content`/`assert_can_manage`. **Każde `ScopedQuery(Recipe, …)` poza
  transferem MUSI mieć flagę** — pilnuje tego `tests/unit/test_recipe_scope.py`. Odmowa
  to 403 (przepis widoczny); rolę sprawdza się jawnie, nie przez `owner_user_id`.
- **`is` na granicy `Scope`/`RecipeScope` nie działa** (różne obiekty, `StrEnum` równa się
  po wartości) — porównuj `==`. `RecipesService` ma jedno miejsce przestawiające zakres:
  `_change_scope` (awans zeruje `household_id`; obniżenie przekazuje przepis ADMIN-owi
  i jest blokowane 409 `used_in` przez `register_recipe_foreign_use_finder` — planowanie
  rejestruje licznik dni i szablonów SPOZA grona, `core/scope.py::outside_audience_condition`).
- Nowe akcje: `POST /recipes/{id}/copy` (`copy_recipe` + `core/uploads.copy_image`: kopia
  pliku przez pełny pipeline, NIGDY wspólna ścieżka), `POST|DELETE /recipes/{id}/archive`
  (ADMIN); audyt `recipe.global_*` i `recipe.archive|unarchive`.
- **Transfer:** `service._settle_global_recipe` (import obcina `global`, kopia INSTANCJI
  zachowuje je tylko dla właściciela-ADMIN-a), `_as_actors_copy` (eksport użytkownika
  dołącza przepisy globalne wskazane przez plany/szablony jako migawkę, nie wiersz ORM),
  `importer.validate_row_scope` (nieznany zakres = 422 także w DRY-RUN),
  `coerce_value` (nieznany enum = 422, nie `ValueError`).
- **Migracje `0017` (`ADD VALUE`, `autocommit_block`) i `0018` (CHECK-i) to DWIE rewizje**
  i tak ma zostać: nowej wartości enuma nie wolno użyć w transakcji, która ją dodała,
  a `env.py` robi całe `upgrade head` w jednej. `ADD VALUE` jest NIEODWRACALNE
  (`downgrade` = no-op). Test dwustopniowy w `test_migrations.py` jest obowiązkowy dla
  każdej przyszłej migracji dodającej wartość enuma.
- Frontend: `RecipeScope` (z `generated.ts`, NIE `Scope`) w `api/recipes.ts` i
  `queryKeys.ts`; opcja „Wszyscy" w edytorze tylko dla ADMIN-a, przepis globalny dla
  USER-a jest w edytorze tylko do odczytu, a w szczególe `recipe-copy` zamiast
  `recipe-edit`/`recipe-delete`; odznaka zakresu na karcie (`recipe-scope-badge-{id}`).

Dołożone w BATCH_18a (produkcja = LXC + ansistrano, ADR-017 — nie pisz od nowa):

- **Deploy**: katalog `deploy/` (Ansible), `deploy/lxc/` (maszyna: `provision.sh`,
  `create-incus.sh`, `host-firewall.sh`). Release = biała lista rsynca
  (`backend/`, `frontend/dist/`, `VERSION`), venv per release
  (`uv sync --frozen --no-dev`), migracja w hooku `before-symlink` PO dumpie,
  nigdy przy starcie aplikacji. Konfiguracja produkcji WYŁĄCZNIE
  z `/etc/pasnik/pasnik.env` — w release'ie nie może leżeć żaden `.env`.
- `backend/scripts/serve.sh` — JEDYNE źródło flag uvicorna (obraz prod woła je
  przez `docker/entrypoint.sh`, LXC przez `pasnik.service`). Flagi w drugim
  miejscu = błąd review (pilnuje test_deploy_config). `APP_VERSION` w LXC
  pochodzi z pliku `VERSION` release'u (`PASNIK_VERSION_FILE`), nie z env.
- `frontend/vite.config.ts` stempluje `dist/build-info.json` (wersja =
  `git describe --tags --always --dirty`) — strażnik stechłego dista w deployu.
- `pasnik-cli -- <polecenie>` na maszynie: jako `pasnik`, ze środowiskiem
  usługi (pętla po `pasnik.env`, NIE `source`). Wzorzec dla każdego
  przyszłego polecenia operatora (`create-admin`, `uploads-report`).
- Skrypty backupu zostają w `docker/backup/` i `backend/scripts/`; provision
  kopiuje je do `/usr/local/lib/pasnik` (zmiana skryptu = ponowny provision).
- Port aplikacji na .111 ogranicza `DOCKER-USER` (proxy `nat=true` omija INPUT,
  więc ufw go nie widzi) — `deploy/lxc/host-firewall.sh`. `FORWARDED_ALLOW_IPS`
  = adres Caddy'ego, `*` zabronione (07_SECURITY §7).

Dołożone w BATCH_22 (narzędzie `/pdf-extract` — D31, POZA runtime aplikacji):

- **Co to jest**: skill `.claude/skills/pdf-extract/SKILL.md` (`/pdf-extract <plik.pdf>`)
  + kod `backend/scripts/pdf_extract/` (`spec`, `catalog_index`, `verify`, `package`,
  `report`, `roundtrip`, `cli`). PDF czyta sesja agenta; kod liczy, weryfikuje i pakuje.
  **Aplikacja nadal nie ma importu PDF** (D25/ADR-016): `app/` nie importuje
  `scripts.pdf_extract` (pilnuje test), brak nowych zależności runtime, brak `float`
  (test statyczny na AST). Nowy import danych dalej = rozszerzenie formatu `transfer`.
- **Wynik = paczka transferu v1**, nie SQL: `data/diet-imports/NNNN-slug/{spec.json,
  report.md,export.zip}` (numer = pierwszy wolny). `spec.json` to JEDYNE źródło prawdy
  (liczby jako stringi, `extra="forbid"`, brak pól na dane osobowe); raport i paczka są
  pochodne, a ta sama spec daje te same bajty. Katalog produktów = suma wszystkich
  `spec.json`; kolejna wersja deklaruje produkt w `reused` zamiast go redefiniować.
- **Dwie bramki właściciela** (skill się na nich zatrzymuje): propozycja scaleń produktów
  (skutek kcal!) i `report.md`. **Wgrywa właściciel** (Ustawienia → „Kopia danych rodziny”
  albo `/admin/dane`), agent nigdy — produkcja poza zasięgiem sesji AI (§3).
- **Reguła jednostek jest w JEDNYM miejscu**: `verify.resolve_ingredient` (wołają ją
  weryfikacja i generator paczki). Jednostka domowa nierozwiązywalna przez `normalize_amount`
  („Sztuka” przy produkcie spoza `PIECE`, brak przelicznika) albo odbiegająca od gramów
  z PDF-a ponad próg (10%) → gramy, oryginał w `note`. Produkt VOLUME: gramy z PDF-a jako ml.
- **Zakres przepisów w paczce** (D33, wariant A): `--recipe-scope household|private`
  → `scope=user` z placeholderami id (`owner_user_id`/`household_id` = 1, import mapuje je
  na konto wczytujące; `null` w `household_id` zrobiłby z przepisu prywatny); `global` →
  `scope=instance` + sekcja `users` (`--owner-email`, rola `user`, `is_active=false`, żeby
  literówka nie założyła ADMIN-a). Wgrywa ADMIN z konta o TYM SAMYM e-mailu (inaczej drugi
  import zdubluje przepisy), a w DRY-RUN `users` nie może być w „Nowe”. W `/admin/dane`
  jest rozwijana podpowiedź o tym (`admin-dane-help`).
- **`pdfx-roundtrip`** dotyka WYŁĄCZNIE bazy z `TEST_DATABASE_URL` (nazwa `*_test`, różna
  od `DATABASE_URL`), robi `TRUNCATE` i nie wolno go puszczać równolegle z `task test-int`.
- Kategorie produktów w paczce MUSZĄ być z migracji `0005` (kopia listy w `package.py`
  pilnowana testem zgodności); nowy produkt w kategorii spoza listy = błąd, nie nowa kategoria.
- **Prywatność (D27)**: PDF-y i `data/source_pdfs/` poza gitem (`.gitignore`), w `spec.json`
  i raporcie nie ma danych osobowych. Paczki `global` z e-mailem właściciela się nie commituje.

Testy: `tests/{unit,integration,api}/` (pakiet — z `__init__.py`), markery
`unit`/`integration`/`api` (wymagane — bez markera test nie wejdzie do
żadnego targetu), docstring po polsku opisujący scenariusz. Fixture'y
wspólne w `tests/conftest.py` (`app`, `client`, `settings`,
`test_database_url`, `db_session`, `db_client`). **Nowa tabela = wpis w DWÓCH
miejscach**: `DB_TABLES` (`tests/conftest.py` — TRUNCATE między testami) i
`EXPECTED_TABLES` (`tests/integration/test_migrations.py` — asercja na dokładny
zestaw tabel po `upgrade head`); migracja z nowym typem enumowym dopisuje go
do `EXPECTED_ENUM_TYPES` w tym samym pliku. Fabryki: `tests/factories.py`,
logowanie i nagłówek CSRF w testach API: `tests/helpers.py`. Mutacja bez
`X-CSRF-Token` = 403.

## 5. Frontend — wzorzec kodu

`<script setup lang="ts">`, TS strict, bez `any`. Stan serwera = TanStack
Query (klucze w `src/api/queryKeys.ts`), Pinia = wyłącznie stan UI.
Wywołania HTTP tylko przez `src/api/client.ts` (`apiFetch`, `ApiError`).
Kolory wyłącznie przez tokens z `src/assets/tailwind.css` (06_UIUX §1) —
żadnych wartości hex w komponentach. Komponenty shadcn-vue w
`src/components/ui/` modyfikuje się przez tokens, nie przez fork logiki;
domenowe w `src/components/domain/`. Teksty po polsku, wielokrotnego użytku
w `src/lib/texts.ts`. Mobile-first, cele dotykowe ≥44 px, `aria-label` dla
elementów bez tekstu, selektory E2E przez `data-testid`.

**Przycisk, który nawiguje, to LINK**: `<Button as-child>` z zagnieżdżonym
`<RouterLink :to="…">` (`to` i `data-testid` na linku). `as="router-link"`
NIE działa — reka-ui `Primitive` woła `h(props.as, …)`, a string jest dla
`h()` nazwą tagu, więc powstaje nieznany element bez `href`, bez nawigacji
i bez roli dla czytnika ekranu. Pilnuje tego test
`src/components/ui/button/Button.spec.ts` (ustalenie review R2).

Sesja: `src/stores/auth.ts` (jedyny stan sesji w Pinia), guard w
`src/router.ts`, pozycje menu w `src/lib/navigation.ts` (jeden wpis =
sidebar + bottom-nav). Batch domenowy podmienia `component` istniejącej
trasy z `PlaceholderPage`, nie dokłada nowego wpisu nawigacji.
E2E: nowy spec podpisuje encje własnym prefiksem `E2E <obszar>`, sprząta
`cleanupE2eData` w `beforeAll` i `afterAll`, daty planu bierze z lat 2030+,
a suita jest jednowątkowa (08_TESTING §3.1) — nie zakładaj równoległości.
Nowa zależność npm wymaga odświeżenia `node_modules` w kontenerze:
`docker compose --env-file .env -f docker/compose.dev.yml exec frontend
npm ci` + restart serwisu.

## 5a. Frontend — warstwa offline (BATCH_12, ADR-009)

Ekran, który ma działać bez sieci, REUŻYWA tego, nie pisze drugiej kolejki:

- `src/lib/offline/db.ts` — IndexedDB (`idb`): snapshoty list i kolejka mutacji.
  Klucz kolejki `{target}#{itemId}` = deduplikacja per pozycja. **Wszystko, co
  tam wchodzi, przechodzi przez `plain()`** — structured clone rzuca
  `DataCloneError` na proxy Vue, a błąd jest CICHY (`withDb` go łyka).
- `src/lib/offline/clock.ts` — przesunięcie zegara z nagłówka `Date` każdej
  odpowiedzi (hook w `api/client.ts` i `api/publicList.ts`). `checked_at`
  kolejki jest w czasie SERWERA.
- `src/lib/offline/sync.ts` — klasyfikacja wyniku wysyłki:
  `sent`/`offline`/`retry`/`gone`/`dropped`. Licznik prób rośnie WYŁĄCZNIE przy
  `retry` (odmowa serwera) — brak sieci nie może kasować zakupów.
- `src/lib/offline/hydrate.ts` — snapshot → cache TanStack Query
  z `updatedAt: 1` (inaczej `staleTime` blokuje refetch po powrocie sieci).
- `src/stores/offlineQueue.ts` (Pinia) — enqueue/flush/backoff, `start()`
  wołane raz z `main.ts`. Flush jest SEKWENCYJNY (wspólny limit 60/min/IP).
- `main.ts` ustawia **`networkMode: 'always'`** dla queries i mutations. Bez
  tego TanStack pauzuje mutacje offline i kolejka nigdy ich nie zobaczy.
- Offline NIE obejmuje zmiany sklepu (kolejność sekcji składa serwer) ani
  przyjęcia zakupów do spiżarni (wartością jest policzalna odpowiedź serwera) —
  obie akcje są wtedy wyłączone z podpowiedzią. Wpuszczenie ich wymaga decyzji.

## 6. Migracje

`task db-revision -- --rev-id <pierwszy wolny> -m "opis"`; `down_revision`
uzupełnij wynikiem `task db-heads`. Po zmianie: dokładnie jedna głowa
(pilnuje tego `task migrations-check` w `task check`), a `upgrade` i
`downgrade` muszą przechodzić na czystej bazie. Backfill = osobna,
idempotentna migracja.

**Na produkcji migracje biegną rolą `ffp_user` (NOSUPERUSER, właściciel bazy
w klastrze `postgres-apps`, PG 16)** — migracja wymagająca uprawnień ponad
właściciela bazy (np. rozszerzenie spoza listy „trusted", `CREATE ROLE`,
`CREATE DATABASE`) jest NIEWYKONALNA bez operatora klastra i wymaga decyzji
właściciela przed napisaniem. `pg_trgm` (0004) jest „trusted"; próbę
`upgrade head`/`downgrade base` wykonuje się rolą bez SUPERUSER-a (B18a).
Dev/test stoją na `postgres:16` (parytet z produkcją).
