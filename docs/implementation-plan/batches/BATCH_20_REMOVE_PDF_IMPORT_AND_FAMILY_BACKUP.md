# BATCH_20 — REMOVE_PDF_IMPORT_AND_FAMILY_BACKUP

Klasa: PLAT (zmiana zakresu produktu na polecenie właściciela) · Zależności:
B17 (istnieją `core/body_limit.py`, `core/ratelimits.py`, `core/uploads_report.py`,
które ten batch odchudza), B14 + R4 (transfer z D22 wdrożonym) · Bramki
decyzji: **D25 — ZATWIERDZONE 2026-09-06** (usunięcie importera, transfer
jedynym importem/eksportem); **D26 — rekomendacja, NIE blokuje** (batch
realizuje ją bez czekania; inna odpowiedź właściciela = korekta karty) ·
Rozmiar: **M** (usuwanie jest mechaniczne, ale szerokie: ~3,9 k linii modułu,
~3,8 k linii testów, ~2,2 k linii frontendu, 12 MB danych, 5 dokumentów;
do tego D24 + U21 w transferze) · Sekwencyjnie, **PRZED B18**.

## Goal

Aplikacja nie ma importu PDF. Jedynym importem/eksportem jest **kopia danych
rodziny**: członek rodziny pobiera ZIP z produktami, przelicznikami jednostek,
przepisami, posiłkami planu, szablonami, spiżarnią, turami i listami swojej
rodziny, a potem wgrywa go z powrotem — na czystą instancję (odtworzenie) albo
na żywą (scalenie: to, co już jest, zostaje; nowe rzeczy dochodzą; raport
DRY-RUN mówi prawdę o tym, co zostanie scalone). ADMIN zachowuje kopię całej
instancji. Po batchu w repo nie ma ani jednej linii kodu, testu, zależności,
ustawienia, dokumentu ani pliku danych, który istniał wyłącznie dla importera
PDF — sprawdzalne grepem (Acceptance Criteria 4).

## Context

Batch zastaje (po B17, HEAD `c4c8719`):

- **Importer PDF kompletny i używany**: moduł `backend/app/modules/importer/`
  (`parser.py` 874, `review_service.py` 1123, `ai_assist.py` 526, `service.py`
  491, `models.py` 315, `router.py` 298, `schemas.py` 247, `matching.py` 40 —
  3924 linie), router pod `/api/v1/import/*` (9 endpointów, 04_API §2),
  staging w bazie (migracje `0014_importer_staging` i
  `0015_importer_review_columns`, HEAD = `0015`): tabele `import_jobs`,
  `staged_recipes`, `staged_ingredients`, `import_issues`; typy enum
  `import_job_status`, `staged_recipe_resolution`, `import_match_kind`,
  `import_issue_kind`, `import_issue_severity`. Kolumny `recipes.source`
  (enum `recipe_source` = `manual|pdf_import`) i `recipes.import_job_id`
  powstały w `0006`; `0014` dopięło do drugiej FK
  `fk_recipes_import_job_id_import_jobs` (SET NULL) i indeks
  `ix_recipes_import_job_id`.
- **Sploty z resztą aplikacji** (pełny inwentarz w §Expected files):
  `app/models.py` (rejestr modeli), `app/main.py` (`build_import_router`),
  `app/core/deps.py` (`get_importer_service`, `get_import_review_service`),
  `app/core/config.py` (`pdf_max_upload_mb`, `pdf_parse_timeout_s`,
  `anthropic_api_key/model/max_tokens/timeout_s`), `app/core/body_limit.py`
  (reguła `^/api/v1/import/pdf$`), `app/core/uploads.py`
  (`PRIVATE_SUBDIRS = ("transfer", "import-pdf")`),
  `app/core/uploads_report.py` (`ImportJob.file_path` w `collect_references`),
  `app/modules/audit/service.py` (`AuditEntity.IMPORT_JOB`,
  `AuditAction.IMPORT_UPLOAD/IMPORT_DELETE/IMPORT_APPROVE/IMPORT_REJECT`),
  `app/modules/recipes/{models,schemas,service}.py` (`RecipeSource`,
  `Recipe.source`, `Recipe.import_job_id`, `ImportedIngredient`,
  `create_imported_recipe`), `app/modules/catalog/service.py`
  (`record_unit_weight_samples`) + `app/modules/catalog/unit_weights.py`
  (`merge_samples` — jedyny konsument to importer), zależności `pdfplumber`
  i `anthropic` w `pyproject.toml`/`uv.lock`, zmienne `PDF_*`/`ANTHROPIC_*`
  w `.env.example` i `docker/compose.test.yml`.
- **Frontend**: `pages/ImportPage.vue`, `pages/ImportReviewPage.vue`,
  `components/domain/StagedRecipeCard.vue`, `StagedIngredientRow.vue`,
  `api/pdfImport.ts`, grupa `queryKeys.import`, trasy `import` i
  `import-review` w `router.ts`, pozycja „Import PDF" w `navigation.ts`
  (ikona `FileUp`), teksty `pdfImport` i `importReview` w `lib/texts.ts`,
  specy vitest i dwa specy E2E (`import-upload.spec.ts`,
  `import-review-flow.spec.ts`) czytające `data/source_pdfs/dieta.pdf`.
- **Dane w repo**: `data/source_pdfs/*.pdf` (8 plików, 12 MB — jadłospisy
  JEDNEJ osoby z imieniem i nazwiskiem na stronie tytułowej) i
  `data/reference/prototype.db` (588 KB). Poza repo (gitignore):
  `backend/data/uploads/import-pdf/` (13 PDF-ów na maszynie dev).
- **Dokumenty**: `docs/implementation-plan/01_PDF_AUDIT.md` (kontrakt
  parsera), `docs/RUNBOOK_IMPORT_PDF.md`, `docs/adr/ADR-011-importer-pdf.md`,
  sekcje w 01–09 architektury (lista w §Expected files), `CLAUDE.md` (blok
  „Dołożone w BATCH_15" i wzmianki w B17), README, skille `pasnik-*`,
  `03_AI_SKILLS.md` (SKILL-PDF, SKILL-API), karta B18.
- **Transfer (B14 + R4) działa i JEST już „kopią danych rodziny" w sensie
  zakresu**: eksport użytkownika bierze `ScopedQuery.owned_condition` =
  własne encje + encje rodziny o `scope=household` + spiżarnia rodziny
  (`select_own_household`) + profile członków + własne cele i oceny + tylko
  te wiersze słowników globalnych, do których to wskazuje; 30 sekcji formatu
  v1 obejmuje `canonical_products`, `product_unit_weights` (przeliczniki =
  „miary"), `product_nutrient_values`, `retail_products`, `recipes` (+
  składniki, tagi, oceny), `plan_days` → `plan_meals` → `plan_meal_items` →
  `plan_item_servings` („posiłki"), szablony, cykle, `pantry_items`, tury,
  generacje, listy. Import buduje mapę stary→nowy ID, kolizje słowników
  rozstrzyga po `normalized_name` (`use_existing` domyślnie), a reużyty
  rodzic NIE dostaje drugiego kompletu dzieci (D22). Czego brakuje do
  „scalenia, które mówi prawdę": **D24** (raport DRY-RUN ma WYMIENIĆ dni
  planu, które zostaną scalone) i **U21** (`to_create` zawyżone dla sekcji
  `ON CONFLICT DO NOTHING`) — obie rzeczy mają jeden mechanizm (indeks
  istniejących wierszy podawany do czystego `analyze`) i wchodzą tutaj.
- UI transferu nazywa się dziś „Twoje dane" (`UstawieniaPage`, teksty
  `transfer.*` w `lib/texts.ts`), a strona `/admin/dane` — „Instancja".

**Nazwa-pułapka**: `backend/app/modules/transfer/importer.py` to importer
PACZKI TRANSFERU (dry-run, `parent_blocked`, `TransferValidationError`) —
zostaje. To samo `tests/unit/test_transfer_serializer.py`,
`tests/integration/test_transfer_collisions.py`, `frontend/src/api/transfer.ts`,
`TransferImportDialog.vue`, `e2e/transfer.spec.ts` i endpointy
`/api/v1/transfer/import*`. Kasujemy wyłącznie moduł `importer` (PDF).

Wymagane lektury: 02_DECISIONS **D25** (zakres) i **D26** (semantyka
„rodzina"), **D22**, **D24**; 02_DOMAIN §11; 04_API §2 (mapa zasobów +
„Format eksportu transfer v1"); 03_DATABASE §4 (wzorzec scope), §9 (do
skreślenia), §10; 07_SECURITY §6 (uploady — serwowanie `/uploads/*`), §7
(sekrety); ADR-006, ADR-011 (do zastąpienia), ADR-012; 08_TESTING §2 i §4;
CLAUDE.md §4 („Dołożone w BATCH_15", „Dołożone w BATCH_17") i §6.

## Stages

0. **Baseline**: `task check` zielony na HEAD przed zmianą; zapisz w
   Completion notes liczby wierszy `recipes`, `canonical_products`,
   `product_unit_weights` z bazy dev (`task dev-db` + psql) — po batchu mają
   być IDENTYCZNE (treść wniesiona importerem zostaje, D25).
1. **Migracja `0016`** (numer = pierwszy wolny, `down_revision` z
   `task db-heads` = `0015`): zdejmuje ślady importera ze schematu; up/down na
   czystej bazie; test dryfu modeli przechodzi; `EXPECTED_TABLES`,
   `EXPECTED_ENUM_TYPES`, `DB_TABLES` skorygowane.
2. **Backend — wycięcie**: moduł, rejestr, router, dependencies, ustawienia,
   reguła body-limit, `PRIVATE_SUBDIRS`, `uploads_report`, enumy audytu,
   `RecipeSource`/`import_job_id`/`create_imported_recipe`/`ImportedIngredient`,
   `record_unit_weight_samples` + `catalog/unit_weights.py`, fabryki i testy;
   zależności `pdfplumber`/`anthropic` z `pyproject.toml` + `uv lock`;
   `.env.example`, `docker/compose.test.yml`, komentarz w `entrypoint.sh`;
   `task fe-types` → nowy `openapi.json` bez `/import/*` i bez schematów
   `ImportJob*`/`Staged*`.
3. **Frontend — wycięcie**: strony, komponenty, klient API, klucze zapytań,
   trasy, pozycja nawigacji, teksty, specy vitest, oba specy E2E;
   `generated.ts` z kroku 2; `router.spec.ts` i test nawigacji przestawione
   na nowy komplet tras (zmiana STANU OCZEKIWANEGO, nie osłabienie).
4. **Transfer = kopia danych rodziny**: (a) teksty i układ sekcji w
   `UstawieniaPage` („Kopia danych rodziny": co zawiera, że wczytanie SCALA,
   i że wszystko, co powstaje z kopii, należy do konta, które ją wczytuje —
   D26); (b) **D24 + U21**: `TransferService` buduje indeks istniejących
   wierszy dla sekcji z `merge_key` (`plan_days`: zbiór dat importującego) i
   dla sekcji `ON CONFLICT DO NOTHING` (`product_unit_weights` po
   `(product_id, unit_label)`, `product_nutrient_values`, `recipe_ratings`,
   `user_nutrition_goals`) i podaje go do CZYSTEGO `analyze`; raport dostaje
   ostrzeżenie „N dni planu zostanie scalonych — ich posiłki nie zostaną
   ruszone" oraz `to_create` równe temu, co `apply` naprawdę utworzy;
   (c) `TransferImportDialog` pokazuje to ostrzeżenie w sekcji „Uwagi" (już
   istnieje — bez nowego kroku).
5. **Dane i dokumenty**: kasacja `data/source_pdfs/`, `data/reference/`,
   `docs/RUNBOOK_IMPORT_PDF.md`, `docs/implementation-plan/01_PDF_AUDIT.md`;
   **nowy ADR-016** (transfer jedynym importem/eksportem; importer PDF
   wycofany; kryterium „co wchodzi do kopii rodziny" = `owned_condition`),
   ADR-011 → `SUPERSEDED przez ADR-016`; architektura 01–09, `CLAUDE.md`,
   README, skille `pasnik-*`, `03_AI_SKILLS.md`, karta B18; procedura
   ręczna dla dev: usunięcie `backend/data/uploads/import-pdf/` i kluczy
   `PDF_*`/`ANTHROPIC_*` z lokalnego `.env` (plik nieśledzony — agent NIE
   edytuje go sam, instruuje właściciela; `Settings` ma `extra="ignore"`,
   więc pozostawione klucze nie psują startu).
6. **Weryfikacja**: `task check`, `task test-e2e`, `task db-migrate` up/down
   na czystej bazie, `task uploads-report`, `task build-prod` (obraz bez
   pdfplumber/anthropic buduje się i przechodzi healthcheck w
   `task test-stack-up`), grep-sweep z Acceptance Criteria 4, PROGRESS.

## Database / migrations

Migracja `0016_remove_pdf_importer` (nazwa opisowa; numer = pierwszy wolny):

**upgrade** — w tej kolejności (FK i typy wymuszają ją):

1. `recipes`: `drop_constraint("fk_recipes_import_job_id_import_jobs")`,
   `drop_index("ix_recipes_import_job_id")`, `drop_column("import_job_id")`,
   `drop_column("source")`, po czym `DROP TYPE recipe_source`.
2. Tabele od dzieci do rodzica: `import_issues` → `staged_ingredients` →
   `staged_recipes` → `import_jobs` (kaskady FK; indeksy spadają z tabelami).
3. Typy enum (powstały implicite przez `sa.Enum` w `0014`, więc kasujemy je
   JAWNIE, `checkfirst=True`): `import_issue_severity`, `import_issue_kind`,
   `import_match_kind`, `staged_recipe_resolution`, `import_job_status`.

**downgrade** — odtwarza PUSTE struktury: kolumny `recipes.source`
(`recipe_source`, `NOT NULL DEFAULT 'manual'`) i `recipes.import_job_id`
(NULL) oraz cztery tabele w kształcie po `0015` (DDL skopiowane z `0014` +
`0015`, w tym `confidence`, `from_extras_section`, CHECK
`ck_staged_ingredients_confidence_range`, indeksy, FK z `recipes`). **Treści
stagingu nie da się odzyskać — to zamierzone (D25 pkt „koszty")**; docstring
migracji ma to napisać wprost.

Bez zmian: `product_unit_weights.source` (wolny tekst, wpisywany też ręcznie
w `ProduktFormPage`) i `samples_count` (formularz wysyła `1`) — obie kolumny
mają konsumenta poza importerem, więc NIE są martwe. Wiersze z
`source='pdf_import'` zostają jako historia (D25).

Testy: `tests/conftest.py::DB_TABLES` bez czterech tabel;
`tests/integration/test_migrations.py`: `EXPECTED_TABLES` bez nich,
`EXPECTED_ENUM_TYPES` bez sześciu typów; `test_modele_nie_dryfuja…` zielony
bez żadnej korekty asercji (to jest dowód, że model i schemat rozeszły się
zerowo); dodatkowo test, że `downgrade` → `upgrade` przechodzi.

## Backend

Endpointy **usuwane** (wszystkie odpowiadają 404 po batchu — trasy nie ma,
nie ma też „410 wycofane": nikt poza naszym frontendem ich nie wołał):

| Ścieżka | Metoda |
|---|---|
| `/api/v1/import/pdf` | POST |
| `/api/v1/import/jobs`, `/api/v1/import/jobs/{id}` | GET, GET/DELETE |
| `/api/v1/import/jobs/{id}/{staged,resolve,ai-suggest,approve,reject}` | GET/POST |

Endpointy transferu **bez zmian kontraktu** (`/transfer/export`,
`/transfer/import`, `/transfer/import/{id}/apply`); zmienia się TREŚĆ
raportu DRY-RUN (D24: nowy wpis w `warnings`; U21: `to_create` dokładne).
Odpowiedź `RecipeRead` traci pole `source` (nikt go nie czyta — frontend nie
ma ani jednego użycia poza `generated.ts`).

Do wycięcia poza modułem (każde miejsce z inwentarza, nic „na później"):

- `app/models.py`: linia `importer_models`.
- `app/main.py`: import i `include_router(build_import_router(limiter))`.
- `app/core/deps.py`: `get_importer_service`, `get_import_review_service`
  i importy.
- `app/core/config.py`: `pdf_max_upload_mb`, `pdf_parse_timeout_s`,
  `anthropic_*`; `.env.example` w tym samym commicie (CLAUDE.md §4).
- `app/core/body_limit.py`: reguła `^/api/v1/import/pdf$` (+ komentarz).
- `app/core/ratelimits.py`: komentarz o PDF; `FILE_UPLOAD_RATE_LIMIT`
  ZOSTAJE (transfer go używa).
- `app/core/uploads.py`: `PRIVATE_SUBDIRS` → `("transfer",)` i komentarz —
  patrz §Security (pliki-sieroty w `import-pdf/`).
- `app/core/uploads_report.py`: import `ImportJob` i `pdf_paths`; docstring.
- `app/core/errors.py`, `app/core/health.py`: komentarze wskazujące importer
  (kod zostaje — `ServiceUnavailableError` jest częścią `core`).
- `app/modules/audit/service.py`: `AuditEntity.IMPORT_JOB`,
  `AuditAction.IMPORT_*`. Kolumny `audit_entries.action`/`entity_type` to
  `Text`, a kod nigdzie nie robi `AuditAction(row.action)` — stare wpisy
  `import.*` w dzienniku zostają czytelne jako tekst. Sprawdź jedynie, czy
  frontend dziennika ADMIN-a ma mapę etykiet akcji; jeśli tak — nieznana
  akcja ma spadać na surowy tekst, nie na błąd.
- `app/modules/recipes/models.py`: `RecipeSource`, `RECIPE_SOURCE_ENUM`,
  `Recipe.source`, `Recipe.import_job_id`; `schemas.py`: pole `source`;
  `service.py`: `ImportedIngredient`, `create_imported_recipe` (jedyny
  konsument: importer). `register_recipe_reference_finder` ZOSTAJE (plan,
  szablony).
- `app/modules/catalog/service.py`: `record_unit_weight_samples` + import
  `merge_samples`; plik `catalog/unit_weights.py` w całości;
  `register_product_reference_finder` ZOSTAJE (spiżarnia, shopping,
  przepisy). Komentarz przy `samples_count` w `models.py` przepisać na stan
  faktyczny (licznik ustawia dziś wyłącznie formularz produktu).
- `app/modules/transfer/serializer.py`: komentarz o `import_job_id`.
- `scripts/seed_demo.py`: komentarze cytujące `01_PDF_AUDIT §5.2` (dokument
  znika — zastąpić opisem liczby, np. „waga sztuki zmierzona w B04").
- `backend/pyproject.toml`: `pdfplumber`, `anthropic` (+ komentarze);
  `uv lock`; sprawdź, że z locka wypadły `pdfminer-six`, `pypdfium2`,
  `docstring-parser`, `jiter`, `httpx2`, `charset-normalizer`,
  `cryptography` (jeśli nic innego ich nie ciągnie) — Pillow ZOSTAJE.
- `docker/compose.test.yml`: `ANTHROPIC_API_KEY`; `docker/entrypoint.sh`:
  komentarz o wolnym imporcie pdfplumber/anthropic.
- `tests/factories.py`: `create_import_job`, `create_staged_recipe`,
  `create_staged_ingredient` i importy; `tests/api/test_upload_rate_limits.py`
  i `tests/api/test_body_limit_api.py`: przypadki `/import/pdf`;
  `tests/unit/test_body_limit.py`: reguła PDF i `PDF_MAX_UPLOAD_MB`;
  `tests/unit/test_uploads_report.py`: ścieżki `import-pdf/*` PRZESTAWIONE
  (patrz §Security), nie skasowane; `tests/api/test_health.py::
  test_pusty_klucz_anthropic_nie_psuje_health`; `tests/unit/
  test_transfer_serializer.py` L194 (asercja o `Import-PDF/x.pdf` → zostaje
  test wielkości liter dla `transfer`, nie dla `import-pdf`);
  `tests/unit/test_unit_weights_median.py` (testuje kasowany moduł).
- Kasowane w całości: `app/modules/importer/`, `tests/unit/test_pdf_parser.py`,
  `test_ai_parsing.py`, `test_approve_gate.py`, `test_kcal_validation.py`,
  `tests/integration/test_pdf_corpus.py`, `test_prototype_crosscheck.py`,
  `test_import_ai_assist.py`, `test_import_approve.py`,
  `test_import_review_flow.py`, `tests/api/test_import_api.py`,
  `test_import_review_api.py`.

Transfer (`app/modules/transfer/`):

- `service.py::_existing_index` rozszerzyć o sekcje z `merge_key` i sekcje
  `ON CONFLICT DO NOTHING` (klucze naturalne z `serializer.py`), wynik podać
  do `importer.analyze(...)` jako argument — `analyze` ZOSTAJE czyste
  (ADR-008 dla modułów obliczeniowych: zero I/O w funkcji raportu).
- `importer.analyze`: `to_create` liczy wyłącznie wiersze, których w indeksie
  nie ma; dla `plan_days` z trafieniem → jedno zbiorcze ostrzeżenie z liczbą
  (D24, treść po polsku, bez dat — daty widać po imporcie).
- `apply` bez zmian semantyki (D22/D24: scalanie dnia zostaje).

## Frontend

- Kasowane: `src/pages/ImportPage.vue` (+ `.spec.ts`),
  `src/pages/ImportReviewPage.vue` (+ `.spec.ts`),
  `src/components/domain/StagedRecipeCard.vue` (+ `.spec.ts`),
  `src/components/domain/StagedIngredientRow.vue` (+ `.spec.ts`),
  `src/api/pdfImport.ts`, `e2e/import-upload.spec.ts`,
  `e2e/import-review-flow.spec.ts`.
- Modyfikowane: `src/router.ts` (trasy `import`, `import-review` i ich
  komentarze), `src/lib/navigation.ts` (pozycja „Import PDF", import ikony
  `FileUp`), `src/api/queryKeys.ts` (grupa `import`), `src/lib/texts.ts`
  (`pdfImport`, `importReview` — usunąć; `transfer` — przepisać),
  `src/router.spec.ts` / test nawigacji (komplet tras bez `import*`),
  `src/api/generated.ts` (z `task fe-types`).
- `UstawieniaPage.vue`, sekcja dziś „Twoje dane" → **„Kopia danych rodziny"**:
  tytuł, podtytuł („Pobierz kopię produktów, przepisów, planów, spiżarni
  i list Twojej rodziny albo wczytaj wcześniejszą kopię. Wczytanie SCALA:
  to, co już masz, zostaje, a nowe rzeczy dochodzą."), przycisk „Pobierz
  kopię danych rodziny", przycisk „Wczytaj kopię", oraz jedno zdanie o
  własności po wczytaniu (D26: „Wszystko, co powstanie z kopii, będzie
  należeć do Twojego konta i będzie widoczne dla rodziny tak jak w kopii").
  Teksty wyłącznie w `lib/texts.ts::transfer`, po polsku, bez i18n (D3).
  Nazwa pliku `pasnik-export-YYYY-MM-DD.zip` ZOSTAJE (D23 ją nazwała; zmiana
  nic nie daje użytkownikowi).
- `AdminDanePage.vue` — bez zmian funkcjonalnych; podtytuł może dostać
  odesłanie „to kopia CAŁEJ instalacji; kopię danych swojej rodziny robi
  każdy w Ustawieniach".
- `TransferImportDialog.vue`: ostrzeżenie D24 wchodzi do istniejącej sekcji
  „Uwagi" (`warningsTitle`) — żadnego nowego kroku, żadnej nowej decyzji.
  Vitest: raport z ostrzeżeniem o scaleniu renderuje się w „Uwagach".
- Bez wpisu nawigacji dla transferu (Ustawienia już są w menu); bez nowych
  komponentów.

## Security

- **Powierzchnia ataku maleje**: znika parser plików binarnych w procesie
  (pdfplumber), znika jedyne wywołanie sieciowe wychodzące (Anthropic),
  znika sekret `ANTHROPIC_API_KEY` z konfiguracji (07_SECURITY §7 — sekcja
  o tym kluczu do skreślenia), znika endpoint uploadu 25 MB.
- **Pliki-sieroty `uploads/import-pdf/`** to jedyne miejsce, w którym
  usuwanie może POGORSZYĆ bezpieczeństwo: `resolve_upload_path` działa na
  LIŚCIE ZAKAZANYCH podkatalogów, więc po zdjęciu `import-pdf` z
  `PRIVATE_SUBDIRS` każdy PDF pozostawiony na dysku stałby się pobieralny
  dla dowolnego zalogowanego konta (`GET /uploads/import-pdf/<plik>`), a to
  dokument zdrowotny z nazwiskiem. **Rekomendacja (implementujący uzasadnia
  w Completion notes)**: odwrócić logikę na **allowlistę serwowanych
  podkatalogów** (dokładnie te, w których serwisy zapisują zdjęcia — sprawdź
  w `recipes`, `retail`, `transfer/_import_photo`), tak żeby plik z katalogu,
  którego kod już nie zna, NIGDY nie był serwowany; wtedy `import-pdf/`
  znika z kodu bez śladu, a katalog na dysku dev kasuje właściciel ręcznie
  (krok w Stage 5) i `task uploads-report` pokazuje go do tego czasu jako
  sieroty. Minimum akceptowalne, jeśli allowlista okaże się za droga:
  `import-pdf` zostaje w `PRIVATE_SUBDIRS` z komentarzem „katalog wycofanej
  funkcji; do usunięcia razem z plikami" — ale to jest martwy wpis, więc
  wymaga jawnego uzasadnienia. Test API w obu wariantach: plik
  `import-pdf/x.pdf` na dysku → `GET /uploads/import-pdf/x.pdf` = 404.
- Transfer bez zmian granic: USER eksportuje/importuje w `owned_condition`
  (D26), `scope=instance` za `require_admin`; `public_token` i `password_hash`
  nadal nie opuszczają bazy; paczka nadal w `PRIVATE_SUBDIRS`.
- Migracja jest DESTRUKCYJNA dla stagingu — przed `task db-migrate` na bazie
  dev właściciel robi kopię (`pg_dump` albo eksport instancji), procedura
  w Completion notes. Produkcji jeszcze nie ma (B18 po tym batchu), więc
  nie ma żadnej żywej instancji do migrowania.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3.

- **Required**: SKILL-BE, SKILL-FE, SKILL-SEC
- **Recommended**: — (SKILL-PDF i SKILL-API tracą w tym batchu ostatniego
  konsumenta — karta B20 je wykreśla z §3)
- **Review**: SKILL-REVIEW, SKILL-SECREV (dotykamy `core/uploads.py`,
  konfiguracji sekretów i limitów uploadu)

## Tests

- **Migracje (integration)**: `upgrade head` na czystej bazie daje dokładnie
  `EXPECTED_TABLES`/`EXPECTED_ENUM_TYPES` bez importera; `downgrade 0015` →
  `upgrade head` przechodzi; test dryfu modeli zielony.
- **API**: `GET /api/v1/import/jobs` i `POST /api/v1/import/pdf` → 404
  (jeden test „trasy nie istnieją" — wzór
  `test_endpointy_review_jeszcze_nie_istnieja` z B15, tylko odwrotnie i na
  stałe); `GET /uploads/import-pdf/x.pdf` → 404 przy pliku na dysku;
  `task fe-types-check` (OpenAPI bez `/import/*`).
- **Unit**: `test_body_limit.py` — komplet reguł bez PDF; `test_uploads_report.py`
  — `import-pdf/*` klasyfikowane jako sieroty (nie ma już referencji);
  brak `PDF_*`/`ANTHROPIC_*` w `Settings` (test, że `Settings()` nie ma
  atrybutów — chroni przed „cichym powrotem" ustawień).
- **Transfer (integration, krytyczne)**: (1) D24 — import własnego eksportu
  na to samo konto: raport DRY-RUN zawiera ostrzeżenie o N dniach planu do
  scalenia, `apply` nie zmienia liczby `plan_meals` (rozszerzenie
  `test_d22_drugi_import_nie_dokłada_dzieci_reużytym_rodzicom`); (2) U21 —
  `to_create` z DRY-RUN równe `created` z `apply` dla `product_unit_weights`,
  `recipe_ratings`, `user_nutrition_goals` przy imporcie na żywą bazę;
  (3) round-trip na czystej bazie (`test_round_trip_odtwarza_dane_na_czystej_bazie`)
  BEZ zmian — nadal zielony; (4) D26 — kopia pobrana przez członka rodziny
  NIE zawiera prywatnego przepisu innego członka, ZAWIERA jego przepis
  `household` (jeśli taki test nie istnieje po B14, dołożyć).
- **vitest**: `UstawieniaPage` — sekcja „Kopia danych rodziny" (tytuł,
  oba przyciski, zdanie o własności); `TransferImportDialog` — ostrzeżenie
  o scaleniu w „Uwagach"; `router.spec.ts` — brak tras `import*`;
  nawigacja — brak pozycji „Import PDF".
- **E2E**: `transfer.spec.ts` zielony bez zmian ścieżki klikania (zmieniają
  się teksty — spec używa `data-testid`, więc selektory zostają;
  jeśli asertuje teksty, przestawić); `smoke.spec.ts` zielony; specy
  `import-*` usunięte; cała suita w DWÓCH kolejnych przebiegach.
- **Macierz uprawnień (08_TESTING §4)**: bez zmian — batch nie dodaje
  zasobu; istniejące testy transferu (`test_transfer_api.py`) zielone.

## Acceptance Criteria

1. W aplikacji nie ma ekranu `/import` ani pozycji „Import PDF"; wejście na
   `/import` daje 404 SPA (`NotFoundPage`), a `GET /api/v1/import/jobs` → 404.
2. `task db-heads` = `0016`; po `upgrade head` na czystej bazie nie ma tabel
   `import_*`/`staged_*`, kolumn `recipes.source`/`recipes.import_job_id`
   ani sześciu typów enum; `downgrade` → `upgrade` przechodzi; liczby
   wierszy `recipes`, `canonical_products`, `product_unit_weights` w bazie
   dev identyczne jak w Stage 0.
3. `pdfplumber` i `anthropic` nie występują w `pyproject.toml` ani `uv.lock`;
   `task build-prod` buduje obraz, `task test-stack-up` daje `/health` ok.
4. **Grep-sweep czysty**: `git grep -n -i -E
   "pdfplumber|anthropic|ANTHROPIC_|PDF_MAX_UPLOAD|PDF_PARSE_TIMEOUT|import_job|import-pdf|pdf_import|RecipeSource|source_pdfs|prototype\.db|01_PDF_AUDIT|RUNBOOK_IMPORT_PDF|ImportPage|ImportReviewPage|pdfImport|StagedRecipe|StagedIngredient|build_import_router|record_unit_weight_samples|merge_samples"`
   trafia WYŁĄCZNIE w: `docs/implementation-plan/PROGRESS.md`,
   `docs/implementation-plan/02_DECISIONS.md`, karty batchy w
   `docs/implementation-plan/batches/` (historia — w tym ta karta),
   `docs/adr/ADR-011-importer-pdf.md` (status SUPERSEDED) i `ADR-016`,
   migracje `0006`, `0014`, `0015`, `0016`. Każde inne trafienie = batch
   niedokończony.
5. `/ustawienia` pokazuje sekcję „Kopia danych rodziny" z pobraniem,
   wczytaniem i zdaniem o własności (D26); eksport → import tego pliku w E2E
   przechodzi.
6. DRY-RUN powtórnego wczytania własnej kopii wymienia scalane dni planu
   (D24), a `to_create` zgadza się z wynikiem `apply` (U21) — test
   integracyjny.
7. Plik pozostawiony w `uploads/import-pdf/` NIE jest serwowany przez
   `/uploads/*` (test), a `task uploads-report` działa bez importera.
8. Dokumentacja opisuje stan faktyczny: ADR-016 istnieje, ADR-011 ma status
   SUPERSEDED, 01–09 architektury bez importera PDF, `CLAUDE.md` bez bloku
   B15 i bez wzmianek PDF w B17, README bez `data/`, skille i `03_AI_SKILLS`
   bez SKILL-PDF/SKILL-API, karta B18 bez limitów PDF i `ANTHROPIC_*`;
   `task check` zielony; PROGRESS zaktualizowany; commit `batch(20): …`.

## Out of Scope

- **Idempotencja sekcji BEZ klucza naturalnego** (wariant sklepowy, profil
  członka, pozycja spiżarni, tura, generacja, lista, szablon, cykl) — drugi
  import tej samej kopii nadal je dubluje (granica opisana w D22). To wymaga
  nadania tym encjom tożsamości (klucz naturalny albo odcisk treści) i jest
  decyzją właściciela — zgłosić w Completion notes jako pytanie z
  rekomendacją, NIE implementować „przy okazji".
- Import selektywny (U18), komenda CLI do eksportu/importu bez sesji (U19),
  sprzątanie scratcha transferu w cronie (U20) — bez zmian, tematy B18/FUTURE.
- Usunięcie eksportu/importu INSTANCJI (`/admin/dane`) — ZOSTAJE (kopia całej
  instalacji ADMIN-a; D25 mówi o zakresie użytkownika).
- Zmiana semantyki „rodzina" poza rekomendacją D26 (np. prywatne encje
  innych członków w pliku) — tylko po decyzji właściciela.
- Wyczyszczenie PDF-ów i `prototype.db` z HISTORII gita (rewrite + force
  push) — operacja właściciela poza repo; batch kasuje pliki z drzewa i pyta.
- Ręczny ekran „waga sztuki" dla ADMIN-a (materiał z D21) — decyzja zamknięta
  jako bezprzedmiotowa; nowy pomysł = nowa decyzja.
- Zmiana nazwy pliku eksportu, zmiana formatu `transfer v1`.

## Expected files/modules

Legenda: **D** = kasowany, **M** = modyfikowany, **N** = nowy.

Backend:

- D `backend/app/modules/importer/` (cały katalog)
- D `backend/app/modules/catalog/unit_weights.py`
- N `backend/migrations/versions/0016_remove_pdf_importer.py`
- M `backend/app/models.py`, `app/main.py`, `app/core/deps.py`,
  `app/core/config.py`, `app/core/body_limit.py`, `app/core/ratelimits.py`,
  `app/core/uploads.py`, `app/core/uploads_report.py`, `app/core/errors.py`
  (komentarz), `app/core/health.py` (komentarz),
  `app/modules/audit/service.py`, `app/modules/recipes/{models,schemas,service}.py`,
  `app/modules/catalog/{models,service}.py`,
  `app/modules/transfer/{importer,service,serializer}.py`,
  `backend/scripts/seed_demo.py` (komentarze), `backend/pyproject.toml`,
  `backend/uv.lock`, `backend/openapi.json`
- D `backend/tests/unit/{test_pdf_parser,test_ai_parsing,test_approve_gate,test_kcal_validation,test_unit_weights_median}.py`,
  `backend/tests/integration/{test_pdf_corpus,test_prototype_crosscheck,test_import_ai_assist,test_import_approve,test_import_review_flow}.py`,
  `backend/tests/api/{test_import_api,test_import_review_api}.py`
- M `backend/tests/conftest.py`, `tests/factories.py`,
  `tests/integration/test_migrations.py`, `tests/api/test_upload_rate_limits.py`,
  `tests/api/test_body_limit_api.py`, `tests/unit/test_body_limit.py`,
  `tests/unit/test_uploads_report.py`, `tests/api/test_health.py`,
  `tests/unit/test_transfer_serializer.py`,
  `tests/integration/test_transfer_collisions.py` (D24/U21),
  `tests/integration/test_transfer_roundtrip.py` (D26),
  `tests/api/test_transfer_api.py` (D24 w raporcie), `tests/api/test_uploads*.py`
  (404 dla `import-pdf/*`)

Frontend:

- D `frontend/src/pages/{ImportPage,ImportReviewPage}.vue` (+ `.spec.ts`),
  `frontend/src/components/domain/{StagedRecipeCard,StagedIngredientRow}.vue`
  (+ `.spec.ts`), `frontend/src/api/pdfImport.ts`,
  `frontend/e2e/{import-upload,import-review-flow}.spec.ts`
- M `frontend/src/router.ts`, `src/router.spec.ts`, `src/lib/navigation.ts`
  (+ jego spec, jeśli asertuje komplet pozycji), `src/api/queryKeys.ts`,
  `src/lib/texts.ts`, `src/api/generated.ts`, `src/pages/UstawieniaPage.vue`
  (+ spec), `src/pages/admin/AdminDanePage.vue` (podtytuł),
  `src/components/domain/TransferImportDialog.vue` (+ spec),
  `frontend/e2e/transfer.spec.ts` (jeśli asertuje teksty)

Konfiguracja i dane:

- M `.env.example`, `docker/compose.test.yml`, `docker/entrypoint.sh`
  (komentarz), `README.md`
- D `data/source_pdfs/` (8 PDF), `data/reference/prototype.db` (katalog
  `data/` znika w całości, jeśli nic innego w nim nie ma)

Dokumentacja:

- D `docs/RUNBOOK_IMPORT_PDF.md`, `docs/implementation-plan/01_PDF_AUDIT.md`
- N `docs/adr/ADR-016-transfer-jedynym-importem-eksportem.md`
- M `docs/adr/ADR-011-importer-pdf.md` (status → `SUPERSEDED przez ADR-016`;
  treść nietknięta), `docs/adr/README.md` (wiersz 011 + nowy 016)
- M `docs/architecture/01_ARCHITECTURE_OVERVIEW.md` (drzewo modułów,
  katalogi danych, tabela technologii), `02_DOMAIN_MODEL.md` (§10 skreślić,
  §11 przepisać na „kopia danych rodziny" + D24/D26, lista modułów),
  `03_DATABASE_DESIGN.md` (§9 skreślić, kolumny `recipes`, §12 wzmianka
  o stagingu), `04_API_DESIGN.md` (mapa `/import/*`, sekcja „Review importu
  PDF", sekcja formatu transfer — `import_job_id`, D24/U21),
  `05_FRONTEND_ARCHITECTURE.md` (trasy `/import*`, akapit o paginacji
  `/import`), `06_UIUX_PRINCIPLES.md` (L106 — przykład z importem),
  `07_SECURITY_DESIGN.md` (§6 limity PDF, pdfplumber; §7 `ANTHROPIC_*`;
  lista zmiennych), `08_TESTING_STRATEGY.md` (tabela poziomów, §2 pkt 10,
  §3 flow 4, mock Anthropic), `09_DEPLOYMENT_AND_OPERATIONS.md` (opis
  uploadów, lista env, uwaga o CPU pdfplumber, health a `ANTHROPIC_API_KEY`)
- M `CLAUDE.md` (§1 nagłówek fazy, §4 blok „Dołożone w BATCH_15" — skreślić;
  w bloku B17 wzmianki o PDF/`PDF_PARSE_TIMEOUT_S`/`PDF_MAX_UPLOAD_MB`;
  §3 tabela — bez zmian w komendach),
  `.claude/skills/pasnik-backend/SKILL.md` (L132), `pasnik-security/SKILL.md`
  (L8, L53, L99–105), `pasnik-domain-calc/SKILL.md` (L72),
  `docs/implementation-plan/03_AI_SKILLS.md` (SKILL-PDF, SKILL-API w §3 i §4),
  `docs/implementation-plan/00_MASTER_PLAN.md` (już zaktualizowany przez
  plan — sprawdzić spójność po fakcie),
  `docs/implementation-plan/batches/BATCH_18_PRODUCTION_DEPLOYMENT_AND_OPERATIONS.md`
  (Cross-Batch Impact niżej), `docs/implementation-plan/PROGRESS.md`

## Implementation Notes

- **Kolejność w migracji ma znaczenie**: najpierw FK z `recipes` (inaczej
  `DROP TABLE import_jobs` pada na zależności), potem tabele od dzieci,
  na końcu typy; `recipe_source` dopiero po `drop_column("source")`. Typy
  z `0014` powstały przez `sa.Enum(...).create(checkfirst=True)` wewnątrz
  `create_table`, więc `drop_table` ich NIE usuwa — kasuj jawnie.
- **`downgrade` = puste struktury** i taki ma być; nie próbuj odtwarzać
  danych z audytu. Napisz to w docstringu migracji jednym zdaniem.
- **`task fe-types` po zmianach backendu, przed frontendem** — inaczej
  `vue-tsc` będzie krzyczeć o typach, których już nie ma, i odwrotnie.
  `openapi.json` i `generated.ts` commitujesz razem (`fe-types-check` w
  `task check` porównuje wygenerowane z repo).
- **`uv lock`** po edycji `pyproject.toml`, a potem `task install` (kontener
  app instaluje z locka). Sprawdź `docker/Dockerfile` — jeśli target `prod`
  instaluje pakiety systemowe tylko dla pdfplumber (np. biblioteki dla
  pypdfium2), wypadają razem z nim; jeśli są współdzielone z Pillow —
  zostają. Zmierz rozmiar obrazu przed/po (`docker image ls`) i wpisz do
  Completion notes.
- **`analyze` w transferze zostaje czyste**: indeks istniejących wierszy
  buduje `TransferService` (I/O), a `analyze(document, existing=...)` tylko
  liczy. Klucze naturalne bierz z `Section.merge_key`/`Section.key`
  w `serializer.py` — nie dubluj listy kolumn w serwisie.
- **Ostrzeżenie D24 jest ZBIORCZE** („3 dni planu zostaną scalone z tymi,
  które już masz — ich posiłki nie zostaną ruszone"), nie per dzień: raport
  ma być czytelny na telefonie.
- **Teksty transferu**: „kopia" zamiast „eksport/import" wszędzie, gdzie
  czyta to użytkownik (przyciski, tytuły, toasty); w kodzie i API nazwy
  zostają (`transfer`, `export`, `import`) — to nie jest rename techniczny.
- **`git rm` dla plików danych**, nie ręczne kasowanie — `git status` musi
  pokazać usunięcia, a nie „untracked/missing". Po skasowaniu `data/`
  sprawdź `.gitignore`/README/`01_ARCHITECTURE_OVERVIEW` pod kątem odwołań
  do tego katalogu.
- **`.env` lokalny jest poza repo** — nie edytuj go; wypisz właścicielowi
  klucze do skasowania (`PDF_MAX_UPLOAD_MB`, `PDF_PARSE_TIMEOUT_S`,
  `ANTHROPIC_*`). `Settings` ma `extra="ignore"`, więc start nie pada.
- **Katalog `backend/data/uploads/import-pdf/` na maszynie dev** kasuje
  właściciel (albo agent po jawnej zgodzie w tej samej sesji) — to dane
  osobowe, a nie artefakt builda; potwierdź `task uploads-report` przed i po.
- **Karty B15/B16 zostają w repo** z banerem „WYCOFANE przez BATCH_20 (D25)"
  — baner jest już wpisany przez plan; nie edytuj ich treści (zapis
  historyczny, reguła D23). Dziennik PROGRESS również nietknięty poza
  własnym wpisem.
- Grep-sweep z Acceptance Criteria 4 uruchamiaj kilka razy w trakcie, nie
  raz na końcu — najłatwiej przeoczyć komentarze i docstringi
  (`catalog/units.py`, `catalog/naming.py`, `core/errors.py`, `tests/unit/
  test_units.py`, `tests/integration/test_catalog*.py`,
  `tests/unit/planning/test_sequences.py`, `frontend/src/lib/schemas/template.ts`,
  `BlockCopyDialog.vue`, `ProduktFormPage.vue` — cytują `01_PDF_AUDIT`,
  którego nie będzie; przepisz uzasadnienie liczby na stan faktyczny albo
  usuń odesłanie).

## Cross-Batch Impact

- **B18 (PRODUCTION_DEPLOYMENT_AND_OPERATIONS)** — zależność rozszerzona na
  B20 (wpisane w kartę B18 przez plan). Do korekty W KARCIE B18 przez ten
  batch: (1) szablon `pasnik.env` i lista zmiennych bez `PDF_MAX_UPLOAD_MB`,
  `PDF_PARSE_TIMEOUT_S`, `ANTHROPIC_*`; (2) ustalenie D7 pkt 4 o limicie
  ciała żądania w Caddy — zostaje TYLKO „paczka transferu 100 MB" (D7 to
  decyzja zatwierdzona, więc jej treści w 02_DECISIONS nie ruszamy — korekta
  idzie w kartę B18 i 09_DEPLOYMENT); (3) zdanie „właściciel importuje
  jadłospisy (103 dania, 185 produktów)" w Context pkt 2 — historia, dopisać
  „(import wykonany przed B20; importer usunięty D25)"; (4) runbook restore:
  ścieżka „transfer logiczny" pozostaje drugą drogą odzyskania — bez zmian;
  (5) `docs/OPERATIONS.md` NIE opisuje `/import`.
- **B15/B16** — zapis historyczny z banerem; bez innych zmian.
- **Przyszłe batche**: każdy nowy import danych do aplikacji = rozszerzenie
  formatu `transfer` (sekcja + klucz naturalny + `parent`), nie nowy moduł —
  zapisać w ADR-016 jako regułę.
- **Skille**: `pasnik-security` traci punkt o kluczu Anthropic i limicie PDF;
  `pasnik-backend` traci przykład pdfplumber (zostaje Pillow jako przykład
  blokującego I/O).

## Implementation checklist

- [x] Stage 0: baseline `task check` + liczności tabel z bazy dev
- [x] Migracja `0016` (up/down na czystej bazie, listy w testach, dryf modeli)
- [x] Backend: moduł + wszystkie sploty z inwentarza usunięte
- [x] Zależności: `pyproject.toml` + `uv lock`; `.env.example`; compose.test;
      entrypoint
- [x] `task fe-types` → `openapi.json` + `generated.ts` bez `/import/*`
- [x] Frontend: strony/komponenty/API/klucze/trasy/nawigacja/teksty/specy/E2E
- [x] Transfer: teksty „Kopia danych rodziny" (D26), D24 + U21 w raporcie
- [x] `PRIVATE_SUBDIRS`/allowlista + test 404 dla `import-pdf/*`
- [x] Dane: `git rm` `data/source_pdfs`, `data/reference`
- [x] Docs: ADR-016, ADR-011 SUPERSEDED, README ADR, architektura 01–09,
      CLAUDE.md, README, skille, 03_AI_SKILLS, karta B18
- [x] Grep-sweep (AC 4) czysty
- [x] PROGRESS.md: status + wpis dziennika NA GÓRZE

## Verification checklist

- [x] `task check` zielony (migrations-check + unit + int + api + fe-test +
      typecheck + lint + format-check + fe-build + fe-types-check)
- [x] `task test-e2e` zielony w dwóch kolejnych przebiegach
- [x] `task db-heads` = `0016`; `downgrade` → `upgrade` na czystej bazie
- [x] `task build-prod` + `task test-stack-up` → `/health` `ok`
- [x] `task uploads-report` działa; `GET /uploads/import-pdf/x.pdf` = 404
- [x] Liczności `recipes`/`canonical_products`/`product_unit_weights` w bazie
      dev identyczne jak w Stage 0
- [x] `/security-review` i `/code-review` na diffie — ustalenia naprawione
      albo odnotowane
- [x] Acceptance Criteria 1–8 odhaczone z dowodem; commit `batch(20): …`

## Completion notes

**Wykonane (2026-09-06)**

- **Stage 0 — baseline**: `task check` na `8f89dc9` zielony (unit 482,
  integration 333, api 436, vitest 429/47 plików, „All checks passed!").
  Liczności w bazie dev PRZED: `recipes` **5**, `canonical_products` **22**,
  `product_unit_weights` **13** (staging: 10 jobów, 131 dań). PO migracji
  `0016`: **5 / 22 / 13** — identycznie; tabel `import_*`/`staged_*` i sześciu
  typów enumowych nie ma (sprawdzone `psql` na `pg_tables` i `pg_type`).
  Przed migracją dev zrobiony `pg_dump -Fc` do katalogu tymczasowego POZA repo
  (`%TEMP%\b20-dev-backup\pasnik-przed-0016.dump`, 706 KB) — procedura z §Security.
- **Migracja `0016_remove_pdf_importer`**: `down_revision = 0015` (z `task
  db-heads`), head = `0016`, jedna głowa. `upgrade`/`downgrade`/`upgrade` na
  czystej bazie przechodzą, test dryfu modeli zielony BEZ korekty asercji,
  `EXPECTED_TABLES`/`EXPECTED_ENUM_TYPES`/`DB_TABLES` skrócone.
- **Backend**: usunięty moduł `app/modules/importer/` i `catalog/unit_weights.py`,
  komplet splotów z inwentarza karty (rejestr modeli, router, dependencies,
  ustawienia, reguła body-limit, `uploads_report`, enumy audytu, pochodzenie
  przepisu, przyjmowanie próbek wag), obie zależności + `uv lock`,
  `.env.example`, `docker/compose.test.yml`, komentarz w `entrypoint.sh`.
- **Transfer (D24 + U21)**: `Section.merge_key` obsługuje teraz DWA
  zastosowania i został dopisany czterem sekcjom `idempotent`;
  `TransferService._existing_index` buduje po nim indeks istniejących wierszy
  i podaje go do CZYSTEGO `analyze` razem z `actor_user_id`/`actor_household_id`.
  Raport dostał zbiorcze ostrzeżenie o scalanych dniach planu
  (`merged_days_warning`, z odmianą liczebnika) i dokładne `to_create`.
- **Frontend**: usunięte dwa ekrany z komponentami, klient API, klucze zapytań,
  trasy, pozycja nawigacji i teksty; sekcja Ustawień przemianowana na
  **„Kopia danych rodziny"** ze zdaniem o własności (D26).
- **Bezpieczeństwo — wariant ALLOWLISTY (rekomendacja karty)**: `PRIVATE_SUBDIRS`
  zastąpione przez `SERVED_SUBDIRS = ("recipes", "retail", "transfer-import")`.
  Uzasadnienie: lista ZAKAZANYCH wiązała bezpieczeństwo pliku z tym, czy ktoś
  pamiętał o wpisie — skreślenie wpisu razem z funkcją udostępniało jej resztki
  każdemu zalogowanemu. Allowlista odwraca domyślną odpowiedź na „nie serwuj",
  więc katalog nieznany kodowi jest zamknięty sam z siebie. Koszt: nowy
  podkatalog uploadów wymaga wpisu (udokumentowane w `uploads.py`, CLAUDE.md,
  07_SECURITY, skillu `pasnik-security`). Sprawdzone też, że
  `resolve_upload_path` nie jest używane do ścieżek scratcha transferu —
  `TransferService` składa je sam, więc odwrócenie logiki nic tam nie psuje.
- **Dane i dokumenty**: `git rm` `data/` (8 PDF + `prototype.db`),
  `docs/RUNBOOK_IMPORT_PDF.md`, `docs/implementation-plan/01_PDF_AUDIT.md`;
  nowy **ADR-016**, ADR-011 → `SUPERSEDED przez ADR-016`, architektura 01–09,
  `CLAUDE.md` (blok B15 skreślony, dopisany blok B20), README, trzy skille
  `pasnik-*`, `03_AI_SKILLS`, `00_MASTER_PLAN`, karta B18, `.gitignore`.

**Odstępstwa od karty (i dlaczego)**

1. **Grep-sweep AC 4 nie jest w 100% pusty i nie może być** — cztery grupy
   trafień zostają świadomie, wszystkie POZA kodem aplikacji:
   - `backend/tests/unit/test_config.py` — test regresyjny, którego TREŚCIĄ są
     nazwy wycofanych ustawień (`pdf_max_upload_mb`, `anthropic_*`). Karta go
     WYMAGA w §Tests („chroni przed cichym powrotem ustawień"), a bez literałów
     nie da się go napisać. Sprzeczność wewnątrz karty; wybrałem test.
   - `docs/implementation-plan/03_AI_SKILLS.md` — nazwy własne skilli
     wbudowanych (`anthropic-skills:pdf`, `anthropic-skills:xlsx`,
     `claude-api`); pierwszy wiersz jest właśnie wykreśleniem SKILL-PDF/API.
   - `docs/implementation-plan/00_MASTER_PLAN.md` — tabela batchy i akapit
     historyczny („do 2026-09-06 drugą drogą był import jadłospisów PDF").
     To ten sam rodzaj zapisu, co PROGRESS i karty batchy z allowlisty.
   - `.claude/skills/*` i `CLAUDE.md` — **wyczyszczone**; zostało wyłącznie
     słowo „PDF" w kontekstach niezwiązanych z importerem (zapis listy do PDF
     jako pomysł „later" w 06_UIUX).
   Wzorzec AC 4 sprawdzony po każdej rundzie sprzątania; komentarze i docstringi
   cytujące `01_PDF_AUDIT` przepisane na stan faktyczny (14 miejsc w kodzie,
   testach i frontendzie).
2. **Poza inwentarzem karty usunąłem trzy martwe metody serwisów**, które
   istniały wyłącznie dla importera i których karta nie wymieniła:
   `CatalogService.find_by_name`, `RecipesService.owned_names` (jedyny konsument
   — wykrywanie duplikatów w review) oraz pole `source` w `RecipeSummary`
   i w mapowaniu routera. Bez nich Goal karty („ani jednej linii, która
   istniała wyłącznie dla importera") nie byłby spełniony, a grep-sweep by ich
   nie złapał.
3. **Format `transfer v1` stracił jedno pole** — sekcja `recipes` nie niesie już
   `source`, bo kolumna zniknęła z modelu. Karta ma „zmianę formatu transfer v1"
   w Out of Scope, ale ta akurat jest WYMUSZONA usunięciem kolumny, a nie
   projektowa. Wersji schematu nie podbijałem: import czyta wyłącznie kolumny
   zadeklarowane w `serializer.py`, więc stara paczka z tym polem wczytuje się
   bez zmian. Odnotowane w dzienniku PROGRESS pkt 4.
4. **Test 404 dla pozostawionego pliku używa nazwy `wycofany-modul/`,
   nie `import-pdf/`** (`tests/api/test_removed_pdf_import.py`,
   `tests/unit/test_uploads_report.py`). Zachowanie jest asertowane w wersji
   OGÓLNIEJSZEJ niż w karcie („dowolny katalog spoza allowlisty"), co pokrywa
   przypadek `import-pdf` i jednocześnie nie zostawia zakazanego literału
   w sweepie z AC 4.
5. **`tests/api/test_body_limit_api.py`**: test „ponad limit + margines → 413"
   przestawiony z jadłospisu PDF na ZDJĘCIE (limit 10 MB), a nie na paczkę
   transferu. Powód mierzalny: sprawdzenie na paczce wymagałoby ciała 101 MB
   w pamięci procesu testowego przy każdym przebiegu, a reguła middleware jest
   dokładnie ta sama.
6. **ADR-005** dostał poprawioną JEDNĄ frazę — odesłanie do skasowanego
   `01_PDF_AUDIT` zastąpione opisem („pomiar na jadłospisach dietetyczki").
   Decyzja i jej uzasadnienie nietknięte; ADR-ów nie edytuje się merytorycznie,
   ale wskaźnik do nieistniejącego pliku nie jest treścią decyzji.

**Decyzje wpisane do 02_DECISIONS jako OPEN (z rekomendacją)**

- **D27** — czy wyczyścić PDF-y i `prototype.db` z HISTORII gita.
  Rekomendacja: TAK, jednorazowo przed pierwszym publicznym pushem; to
  `git filter-repo` + force push, czyli operacja właściciela na repozytorium
  (unieważnia hashe commitów w PROGRESS), nie zadanie dla batcha.
- **D28** — czy nadać tożsamość sekcjom kopii danych, które jej nie mają
  (Out of Scope karty). Rekomendacja: na razie NIE — zmiana wymaga nowych
  UNIQUE-ów w modelu danych i odrzucałaby zapisy, które dziś przechodzą,
  a główny scenariusz (odtworzenie na czystą instancję) jest dokładny.

**Weryfikacja — realne wyniki**

- `task check` **zielony**: migrations-check 3, unit 408, integration 269,
  api 411, vitest 393/43 pliki, typecheck, lint, format-check, fe-build,
  fe-types-check — „All checks passed!". (Baseline na `8f89dc9`: 482/333/436
  i 429 vitest; różnica to WYŁĄCZNIE testy usunięte razem z importerem plus
  11 nowych: 10 przypadków „trasy importu nie istnieją" + serwowanie uploadów,
  3 w transferze, 1 na `Settings`.)
- `task test-e2e`: **19/19 w DWÓCH kolejnych przebiegach** (1,7 min i 1,5 min).
  Pierwsze trzy próby padły i **to nie była regresja**: baza dev miała 992 tury
  zakupowe, 4084 generacje i 2048 list z dawnych przebiegów E2E, więc `/zakupy`
  renderowało wszystko naraz i specy leciały na timeoucie (7,3 min i 5 porażek).
  Te wiersze nie mają prefiksu `E2E `, więc `cleanupE2eData` nigdy ich nie
  kasowało — **follow-up niżej**. Właściciel zatwierdził czyszczenie; po nim
  suita jest 4× szybsza. Przepisy, produkty, plan i spiżarnia nietknięte.
- `task db-heads` = `0016`; `downgrade` → `upgrade` na czystej bazie przechodzi
  (`test_upgrade_downgrade_upgrade_na_czystej_bazie`), dryf modeli zerowy.
- `task build-prod` + `task test-stack-up` → `GET /health` =
  `{"status":"ok","version":"8f89dc9-dirty","checks":{"db":"ok","migrations":"ok","disk":"ok"}}`.
  **Rozmiar obrazu prod: 476 MB → 392 MB (−84 MB, −17,6%)** — wypadły
  `pdfminer-six`, `pypdfium2`, `cryptography`, `charset-normalizer`,
  `docstring-parser`, `jiter`, `httpx2` i pięć innych (13 pakietów z locka).
  Pillow ZOSTAJE.
- `task uploads-report` działa bez importera i pokazuje 13 pozostawionych
  PDF-ów (18,9 MB) jako osierocone — dokładnie to, po co powstał (D10).

**Review skille**

- `/code-review` (high): trzy ustalenia, **wszystkie naprawione w tym commicie**.
  (1) `KEY_SEPARATOR` był surowym bajtem `0x1F` wklejonym w literał zamiast
  escape'u `` — niewidoczny w diffie, a przy zjedzeniu przez narzędzie
  klucze złożone zaczęłyby się sklejać dwuznacznie; (2) `rmdir()` w `finally`
  nowego testu API mógł zamienić zielony test w błąd, bo katalog leży
  w REALNYM katalogu uploadów; (3) **CRLF** — edycje przez `pathlib.write_text`
  na Windows zamieniły LF na CRLF w 69 plikach, w tym w `docker/entrypoint.sh`,
  przez co kontener prod wpadał w pętlę `exec … no such file or directory`.
  `task check` tego NIE łapie (git normalizuje przy commicie), złapało dopiero
  uruchomienie obrazu. Wszystkie 69 plików znormalizowane z powrotem do LF,
  obraz przebudowany i przetestowany.
- `/security-review`: **brak findings o confidence ≥ 8**. Zweryfikowane
  osobno: allowlista `resolve_upload_path` (nowy warunek jest ŚCIŚLE WĘŻSZY
  od listy zakazanych, sprawdzenia `is_absolute`/`..`/`is_relative_to`
  nietknięte, wszystkie trzy `subdir=` w kodzie pokrywają się z allowlistą,
  scratch transferu nie chodzi tą ścieżką); brak nowej drogi do danych spoza
  zakresu; brak wycieku między kontami przez nowy indeks (dla `scope=user`
  `IdMap.get("users", …)` zawsze zwraca konto importujące, więc klucz scalania
  zawiera wyłącznie jego id, a gałąź `merge_key` nigdy nie tworzy
  `CollisionRead`); `apply` nadal nie wstawi encji z cudzym `owner_user_id`;
  migracja `0016` odtwarza w `downgrade` komplet FK i CHECK-ów.
  Uwaga poniżej progu, świadomie nienaprawiona: separator `` da się
  teoretycznie przemycić w `unit_label` i sfałszować trafienie w mapie —
  efekt ogranicza się do LICZBY w raporcie DRY-RUN w obrębie tabeli globalnej,
  bez przekroczenia granicy konta.

**Follow-upy (poza zakresem tego batcha)**

1. **Sprzątanie E2E nie obejmuje tur, generacji i list zakupowych** —
   `cleanupE2eData` kasuje po prefiksie `E2E `, a `shopping-generate.spec.ts`
   tworzy tury „Niedziela"/„Środa" i listy „Zakupy <zakres dat>" bez prefiksu.
   Efekt narastał od B10: zmierzone 992/4084/2048 wierszy i suita wolniejsza
   4×, aż do fałszywych porażek. Naprawa = prefiks w tych trzech specach albo
   sprzątanie po id z odpowiedzi.
2. `docs/architecture/07_SECURITY_DESIGN.md` niósł surowe bajty `0x03 0x04`
   wewnątrz `` `PK` `` (artefakt sprzed tego batcha) — zniknęły przy
   przepisaniu tej sekcji, ale warto sprawdzić resztę dokumentów.

**Do zrobienia przez WŁAŚCICIELA poza repo**

1. Usunąć z lokalnego `.env` klucze `PDF_MAX_UPLOAD_MB`, `PDF_PARSE_TIMEOUT_S`
   i `ANTHROPIC_*` — `Settings` ma `extra="ignore"`, więc start nie pada, ale
   zostawione kłamią o konfiguracji instalacji.
2. Skasować katalog `backend/data/uploads/import-pdf/` (13 plików, 18,9 MB,
   dane osobowe). Agent go NIE ruszył — to dane, nie artefakt builda, a karta
   dopuszcza kasowanie tylko po jawnej zgodzie w tej samej sesji.
   Stan przed: `task uploads-report` wymienia dokładnie te 13 plików jako
   osierocone i nikt ich nie pobierze (allowlista `/uploads/*`).
3. Rozstrzygnąć D27 i D28.
