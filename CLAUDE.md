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
- warstwa i18n — UI wyłącznie po polsku (D3, ADR-007),
- sekrety w plikach śledzonych; `.env` nigdy w repo (07_SECURITY §7),
- migracja z numerem „zarezerwowanym" — numer = pierwszy wolny,
  `down_revision` z `alembic heads` (ADR-002),
- ręczne interfejsy TS dla odpowiedzi API — typy pochodzą z `task fe-types`,
- biblioteki wykresów — wykresy to własne SVG (ADR-013).

## 3. Komendy (Taskfile — jedyne wejście)

Wymagane na hoście: **Docker Desktop, uv, Node 22+, go-task**.
Start od zera: `cp .env.example .env` → `task install` → `task dev`.

| Komenda | Do czego |
|---|---|
| `task dev` | cały stack w Dockerze (app + frontend + db + db-test), hot reload |
| `task dev-db` | same bazy (gdy testy uruchamiasz z hosta) |
| `task down` / `task logs` | zatrzymanie / logi |
| `task check` | **BRAMKA DoD**: migrations-check + unit + int + api + fe-test + typecheck + lint + format-check + fe-build |
| `task test-unit` / `test-int` / `test-api` / `test-be` | pytest wg markerów; zawężenie przez `--`, np. `task test-int -- -k wydajnosc -s` |
| `task fe-test` | vitest |
| `task test-e2e` (+ `task e2e-install`) | Playwright, chromium |
| `task typecheck` / `lint` / `format` / `format-check` | mypy+vue-tsc / ruff+eslint / ruff format+prettier |
| `task db-migrate` / `db-heads` / `db-revision -- --rev-id 0002 -m "opis"` | Alembic |
| `task fe-types` | OpenAPI → `backend/openapi.json` → `frontend/src/api/generated.ts` (oba commitowane) |
| `task audit` / `task secrets-scan` | Review batche i BATCH_17 |
| `task create-admin` | tworzy konto ADMIN (prompt albo `FFP_ADMIN_*` z env; nigdy hasło w repo) |
| `task db-seed-demo` | idempotentny seed demo (od B04: ~15 produktów; kolejne encje dokładają batche domenowe) |

Nigdy nie wołaj gołego `pytest`/`vitest`/`alembic` — Taskfile wstrzykuje
`.env` i właściwy interpreter.

## 4. Backend — wzorzec kodu

Moduł: `backend/app/modules/<nazwa>/{models,schemas,service,router}.py`.
`router.py` (HTTP + walidacja wejścia) → `service.py` (logika, transakcje,
autoryzacja scope, jedyne I/O) → `models.py` (SQLAlchemy 2.0 typed).
Router nigdy nie dotyka sesji DB; moduł→moduł wyłącznie przez service.
Silniki obliczeń (`nutrition/engine.py`, `shopping/engine.py`) to czyste
funkcje bez I/O (ADR-008). Katalogi modułów tworzy batch, który je zasiedla.

Fundament dostarczony w BATCH_01 i BATCH_02:

- `app/core/config.py` — `Settings` (pydantic-settings). Nowa zmienna =
  wpis w `.env.example` w tym samym commicie. Brak wymaganej zmiennej =
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
  tabele ze scope/ilością używają `postgresql.ENUM(..., create_type=False)`.

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
  rozszerzenia wzorca `_PUBLIC_TOKEN_PATH`.
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

## 6. Migracje

`task db-revision -- --rev-id <pierwszy wolny> -m "opis"`; `down_revision`
uzupełnij wynikiem `task db-heads`. Po zmianie: dokładnie jedna głowa
(pilnuje tego `task migrations-check` w `task check`), a `upgrade` i
`downgrade` muszą przechodzić na czystej bazie. Backfill = osobna,
idempotentna migracja.
