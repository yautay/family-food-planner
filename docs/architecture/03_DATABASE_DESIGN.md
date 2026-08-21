# 03 — Projekt bazy danych

PostgreSQL 17 (kontener, dane na bind mount hosta — ADR-002). SQLAlchemy 2.0
declarative + Alembic. Konwencje: nazwy tabel `snake_case` l.mn., PK `id`
(BIGINT identity), `created_at`/`updated_at` (timestamptz, UTC) wszędzie,
FK z jawnym `ON DELETE`. Ilości i wartości odżywcze: `NUMERIC` (nigdy float).

## 1. Konwencje migracji (przejęte z netQArnera — sprawdzone w boju)

- Numer pliku migracji = **pierwszy wolny** w `backend/migrations/versions/`
  w chwili implementacji; `down_revision` = wynik `alembic heads`. NIGDY
  numer przepisany z planu.
- Po dodaniu migracji `alembic heads` musi zwracać dokładnie jedną głowę,
  a `alembic upgrade head` + `downgrade -1` + `upgrade head` przechodzić
  na kopii realnej bazy.
- Migracje danych (backfill) oddzielone od migracji schematu, idempotentne.

## 2. Schemat — accounts & households

```sql
users (id, email UNIQUE, password_hash, display_name, role ENUM(admin,user),
       is_active BOOL, household_id FK→households NULL ON DELETE SET NULL,
       ui_settings JSONB DEFAULT '{}',            -- progi wskaźników itp.
       failed_login_count INT DEFAULT 0,          -- blokada konta (07_SECURITY §2)
       locked_until timestamptz NULL)             -- stan w bazie, nie w pamięci procesu
sessions (id TEXT PK,        -- secrets.token_urlsafe(32), spójnie z 07_SECURITY §2
       user_id FK CASCADE, expires_at, created_at, ip, user_agent)
       -- indeksy: expires_at (sprzątanie), user_id (odwołanie sesji konta);
       -- bez updated_at — rolę znacznika ostatniego użycia pełni expires_at
households (id, name)
member_profiles (id, household_id FK CASCADE NULL,
       owner_user_id FK NULL ON DELETE SET NULL,   -- profil przeżywa konto
       name, default_multiplier NUMERIC(4,2) DEFAULT 1.0,
       kcal_goal NUMERIC(6,0) NULL, is_active BOOL)
user_nutrition_goals (id, user_id FK CASCADE, valid_from DATE,
       kcal NUMERIC(6,0), protein_g NUMERIC(6,1) NULL, fat_g NULL,
       carbs_g NULL, UNIQUE(user_id, valid_from))
```

Użytkownik bez rodziny: `household_id NULL`; encje HOUSEHOLD-scope wiszą
wtedy efektywnie na userze (patrz wzorzec scope §4).

## 3. Schemat — catalog

```sql
product_categories (id, name UNIQUE, position INT,
       perishability ENUM(fresh,durable) DEFAULT durable)
canonical_products (id, name, normalized_name UNIQUE, category_id FK RESTRICT,
       measure_kind ENUM(mass,volume,piece),
       piece_weight_g NUMERIC(8,2) NULL,          -- wymagane gdy piece
       kcal_100 NUMERIC(7,2) NULL, protein_100 NUMERIC(6,2) NULL,
       fat_100 NUMERIC(6,2) NULL, carbs_100 NUMERIC(6,2) NULL,
       fiber_100 NUMERIC(6,2) NULL,
       sugars_100 NUMERIC(6,2) NULL,
       glycemic_index NUMERIC(5,1) NULL CHECK (0<=glycemic_index<=110),
       verification_status ENUM(unverified,verified) DEFAULT unverified,
       nutrition_source TEXT NULL, verified_at timestamptz NULL,
       perishability_override ENUM(fresh,durable) NULL,  -- nadpisanie kategorii (02_DOMAIN §9.2)
       is_archived BOOL DEFAULT false)
product_unit_weights (id, product_id FK CASCADE, unit_label TEXT,  -- 'łyżka'…
       grams_per_unit NUMERIC(8,2), source TEXT, samples_count INT DEFAULT 1,
       UNIQUE(product_id, unit_label))
product_nutrient_values (id, product_id FK CASCADE, nutrient_code TEXT,
       amount_per_100 NUMERIC(9,3), UNIQUE(product_id, nutrient_code))
       -- rozszerzalność na mikroelementy (ADR-004); nutrient_code ze
       -- słownika nutrients (code, name, unit, display_order) seedowanego
       -- pusto w MVP — dodanie mikro nie wymaga zmiany schematu
nutrients (code PK, name, unit, display_order)
stores (id, name UNIQUE, color TEXT NULL, is_archived BOOL DEFAULT false)
store_category_order (store_id FK CASCADE, category_id FK CASCADE,
       position INT, PRIMARY KEY(store_id, category_id))
retail_products (id, canonical_product_id FK RESTRICT, name, brand NULL,
       store_id FK NULL SET NULL, package_amount NUMERIC(8,2),
       package_unit ENUM(g,ml,piece), pieces_per_package INT NULL,
       photo_path TEXT NULL, is_archived BOOL)
```

Indeksy: `canonical_products(normalized_name)` (unique, trigram GIN na
`name` dla wyszukiwarki), `retail_products(canonical_product_id)`.

Stan faktyczny (BATCH_04, migracje `0004` + `0005`):

- Powstały `product_categories`, `canonical_products`, `product_unit_weights`,
  `nutrients`, `product_nutrient_values`.
- **BATCH_09 (migracja `0011`) dołożył `stores`, `store_category_order`
  i `retail_products`** dokładnie w kształcie powyżej, plus `created_at`/
  `updated_at`. Trzy szczegóły wykonawcze: `retail_products.package_unit`
  REUŻYWA typu enumowego `amount_unit` z migracji `0006` (ta sama dziedzina
  `g|ml|piece`, więc osobnego typu nie ma), `store_category_order` kasuje się
  kaskadą z obu stron (profil to atrybut sklepu, a kategoria nie ma prawa
  blokować sklepu), a indeksy to `retail_products(canonical_product_id)`
  (wymieniony wyżej) i `retail_products(store_id)` pod filtr `?store_id=`.
  CHECK-ów `package_amount > 0` ani `pieces_per_package >= 1` NIE MA — ten
  dokument ich nie definiuje, a pilnują ich schematy Pydantic i serwis (ta sama
  zasada co dla `pantry_items.amount`).
- **Rekoncyliacja odroczonego FK z BATCH_08**: `pantry_items.retail_product_id`
  istniało od migracji `0010` jako `BIGINT NULL` bez constraintu (tabeli
  `retail_products` jeszcze nie było). Migracja `0011` dopina
  `fk_pantry_items_retail_product_id_retail_products` z `ON DELETE RESTRICT`,
  więc od tej chwili pozycja spiżarni blokuje usunięcie wariantu sklepowego
  (409 z listą użyć — licznik referencji w `pantry/service.py`).
- **Rdzeń wartości odżywczych jest NULLOWALNY** (`kcal_100` … `carbs_100`) —
  poprawka wobec pierwotnego szkicu. USER tworzy produkt inline, nie znając
  wartości (02_DOMAIN §4.9), a ADMIN uzupełnia je później; NOT NULL wymuszałby
  wpisanie zer, czyli zapisanie nieprawdy. Brak wartości sygnalizuje adapter
  `ProductNutrition` (`complete=False` + lista `missing`), nigdy zero (ADR-004).
- CHECK-i: `piece_weight_matches_measure_kind` (waga sztuki istnieje dokładnie
  dla `measure_kind='piece'` i jest dodatnia), `glycemic_index_range` (0..110),
  `nutrition_non_negative`, `grams_per_unit_positive`, `samples_count_positive`,
  `amount_per_100_non_negative`.
- `product_unit_weights.unit_label` zapisywany jest ZNORMALIZOWANY
  (`units.canonical_unit_label`: trim, zbicie spacji, lowercase, „opak." →
  „opakowanie"), inaczej UNIQUE(product_id, unit_label) przepuszczałby
  „Łyżka" obok „łyżka".
- `product_nutrient_values.nutrient_code` ma FK → `nutrients.code`
  ON DELETE RESTRICT; rejestr `nutrients` jest w MVP pusty (ADR-004).
- Rozszerzenie `pg_trgm` tworzy migracja `0004`; jej `downgrade` świadomie go
  NIE usuwa (rozszerzenie jest własnością bazy, nie jednego batcha).
- Migracja danych `0005` seeduje 14 kategorii (01_PDF_AUDIT §5.5 + wymagania
  02_DOMAIN §4.3), idempotentnie (`ON CONFLICT DO NOTHING`). „Zbożowe" nie
  wchodzą (D14); „Przetwory" i „puszki-słoiki" scalono w jedną kategorię, bo
  różniła je wyłącznie nazwa, a nie `perishability`.

## 4. Wzorzec scope (wspólny dla recipes/planning/shopping)

Kolumny: `owner_user_id FK→users RESTRICT`, `household_id FK→households
NULL`, `scope ENUM(private,household)`. Zapytania „widoczne dla mnie":

```sql
WHERE owner_user_id = :uid
   OR (scope='household' AND household_id = :user_household_id)
```

CHECK: `scope='household'` ⇒ `household_id IS NOT NULL` — z wyjątkiem
użytkowników bez rodziny (wtedy scope household niedozwolony na poziomie
serwisu). Egzekwowanie w jednym miejscu: mixin serwisowy `ScopedQuery`.

Stan faktyczny (BATCH_03, `backend/app/core/scope.py`):

- `ScopedMixin` dostarcza kolumny wzorca **oraz** PK `id` (konwencja §1) —
  model konsumujący nie deklaruje ich ponownie. CHECK `scope_requires_household`
  dokłada `__table_args__` mixinu; model z własnymi `__table_args__` musi
  dołożyć `scope_check_constraint()` samodzielnie.
- `owner_user_id` → `users.id` **ON DELETE RESTRICT**, `household_id` →
  `households.id` **ON DELETE RESTRICT**. RESTRICT, a nie SET NULL: wyzerowanie
  `household_id` przy `scope='household'` złamałoby CHECK-a, a rodziny i tak
  usuwa się wyłącznie puste (409 `used_in`).
- `household_id` zapisywany jest także dla `scope='private'` — dzięki temu
  późniejsza zmiana scope nie musi zgadywać rodziny (konsekwencje przenosin:
  ADR-006).
- Typ enumowy nazywa się `entity_scope` i tworzy go migracja PIERWSZEJ
  produkcyjnej tabeli ze scope (`recipes`, BATCH_05); BATCH_03 dostarczył sam
  mechanizm i macierz testów na encji testowej `scoped_notes` (tworzonej
  wyłącznie w bazie testowej, nigdy migracją).
- **Spiżarnia stoi obok tego wzorca, nie w nim** (BATCH_08): jest zawsze domowa,
  więc kolumny `scope` nie ma, a widoczność liczy `HouseholdScopedQuery` —
  szczegóły i uzasadnienie w §7.

## 5. Schemat — recipes

```sql
recipes (id, +scope-wzorzec, name, instructions TEXT DEFAULT '',
       base_servings INT CHECK >=1 DEFAULT 1, prep_time_min INT NULL,
       difficulty INT NULL CHECK 1..10, photo_path TEXT NULL,
       source ENUM(manual,pdf_import) DEFAULT manual,
       import_job_id FK NULL, is_archived BOOL)
recipe_ingredients (id, recipe_id FK CASCADE,
       product_id FK→canonical_products RESTRICT,
       display_qty NUMERIC(8,3) NULL, display_unit TEXT NULL, -- '2 × łyżka'
       amount NUMERIC(10,3), amount_unit ENUM(g,ml,piece),    -- znormalizowane
       note TEXT DEFAULT '', position INT)
tags (id, name UNIQUE, is_system BOOL DEFAULT false)
recipe_tags (recipe_id FK CASCADE, tag_id FK CASCADE, PK(recipe_id,tag_id))
recipe_ratings (id, recipe_id FK CASCADE, user_id FK CASCADE,
       rating INT CHECK 1..5, UNIQUE(recipe_id,user_id))
```

`amount_unit=piece` dozwolone tylko dla produktów `measure_kind=piece`
(walidacja serwisowa); do obliczeń piece → g przez `piece_weight_g`.

Stan faktyczny (BATCH_05, migracje `0006` + `0007`):

- Migracja `0006` tworzy trzy typy enumowe: **`entity_scope`** (pierwsza
  produkcyjna tabela ze scope — 03 §4), **`amount_unit`** (reużyją go
  planning/pantry/shopping przez `postgresql.ENUM(..., create_type=False)`)
  i `recipe_source`.
- **`recipes.import_job_id` jest kolumną BEZ klucza obcego** — tabela
  `import_jobs` powstaje dopiero w B15 i dopiero tamta migracja dopina
  constraint (FK do nieistniejącej tabeli nie istnieje w PG).
- `recipe_tags` to czysta tabela asocjacyjna bez `created_at`/`updated_at`
  (świadomy wyjątek od §1 — wiersz nie ma cyklu życia poza parą kluczy;
  precedens: append-only `audit_entries` bez `updated_at`).
- `recipes.name` ma indeks trigramowy GIN (wyszukiwarka `?q=`, wymóg
  szybkości dla RecipePickera w B06); `pg_trgm` istnieje od migracji `0004`.
- Migracja danych `0007` seeduje 9 tagów systemowych (02_DOMAIN §5 +
  „ulubione" — serce na karcie, 06_UIUX §4.2), idempotentnie; downgrade
  usuwa tylko tagi seedu NIEprzypisane do żadnego przepisu (lekcja U2 z R1).

## 6. Schemat — planning

```sql
plan_days (id, +scope-wzorzec, day DATE, title TEXT NULL,
       UNIQUE(owner_user_id, day))       -- jeden dzień planu na usera i datę
plan_meals (id, plan_day_id FK CASCADE, name TEXT, position INT,
       kcal_target NUMERIC(6,0) NULL)
plan_meal_items (id, plan_meal_id FK CASCADE,
       recipe_id FK RESTRICT NULL, product_id FK RESTRICT NULL,
       amount NUMERIC(10,3) NULL, amount_unit ENUM(g,ml,piece) NULL,
       servings NUMERIC(6,2) DEFAULT 1.0, position INT,
       CHECK (recipe_id IS NOT NULL) <> (product_id IS NOT NULL))
plan_item_servings (id, plan_meal_item_id FK CASCADE,
       member_profile_id FK CASCADE, multiplier NUMERIC(4,2))
       -- opcjonalny rozkład rodzinny; suma multiplierów = servings pozycji
       -- (pilnowane serwisem przy zapisie)
day_templates (id, +scope-wzorzec, name, payload JSONB)
week_templates (id, +scope-wzorzec, name, payload JSONB)
week_cycles (id, +scope-wzorzec, name, template_ids BIGINT[], start_date DATE NULL)
```

Szablony jako **JSONB payload** (zamrożona kopia struktury z referencjami
do recipe_id/product_id): szablon nie jest edytowalny relacyjnie, tylko
nadpisywany całością — upraszcza model, a referencje wewnątrz payloadu
liczą się do blokady usuwania przepisów przez zliczenie w serwisie
(zapytanie po JSONB path, indeks GIN).

Stan faktyczny (BATCH_06, migracja `0008`):

- Powstały `user_nutrition_goals` (§2) oraz `plan_days`, `plan_meals`,
  `plan_meal_items`, `plan_item_servings`.
- Typy `entity_scope` i `amount_unit` są REUŻYWANE z migracji `0006`
  (`postgresql.ENUM(..., create_type=False)`); `downgrade` migracji `0008`
  świadomie ich NIE kasuje — należą do `0006` i używa ich moduł przepisów.
- Dodatkowe CHECK-i wobec szkicu: `plan_meal_items.product_requires_amount`
  (produkt luzem MUSI mieć ilość i jednostkę, pozycja z przepisem nie ma
  żadnej — niezmiennik 02_DOMAIN §13.1), `amount_positive`, `servings_positive`,
  `plan_meals.kcal_target_positive`, `user_nutrition_goals.kcal_positive`
  i `macros_non_negative`. `plan_item_servings` ma
  `UNIQUE(plan_meal_item_id, member_profile_id)` — ta sama osoba nie może
  wystąpić w rozkładzie dwa razy.
- `plan_days.day` ma indeks (najczęstsze zapytanie modułu to zakres dat).
- Suma multiplierów rozkładu = `servings` pozycji pozostaje regułą SERWISU
  (baza nie widzi całej kolekcji przy pojedynczym INSERT); pilnuje jej
  `planning/service.py::assert_split_matches_servings` (czysta funkcja).

Stan faktyczny (BATCH_07, migracja `0009`):

- Powstały `day_templates`, `week_templates` (wzorzec scope + `name` +
  `payload JSONB`) i `week_cycles` (wzorzec scope + `name` +
  `template_ids BIGINT[]` + `start_date DATE NULL`). Typ `entity_scope` jest
  REUŻYWANY z `0006`; `downgrade` go nie kasuje.
- **Indeksy GIN `jsonb_path_ops`** na obu payloadach
  (`ix_day_templates_payload_gin`, `ix_week_templates_payload_gin`) — warunek
  sprawności blokady usuwania z ADR-012. Wybór klasy operatorów jest WIĄŻĄCY
  dla zapytań: `jsonb_path_ops` obsługuje wyłącznie `@>`, `@?` i `@@`, więc
  zliczanie referencji używa containmentu `@>`
  (`payload @> '{"meals":[{"items":[{"recipe_id": X}]}]}'`), a dla szablonu
  tygodnia tego samego wzorca zagnieżdżonego w `days[].day`. Forma
  potwierdzona `EXPLAIN`-em w
  `tests/integration/planning/test_templates_service.py`.
- Referencje `recipe_id`/`product_id` siedzą WEWNĄTRZ payloadu, więc te tabele
  nie mają na nie FK — jedyną obroną jest licznik referencji w serwisie
  (`templates_service.py`), inaczej DELETE przepisu użytego tylko w szablonie
  przeszedłby bez 409.
- `week_cycles.template_ids` nie ma FK (tablica): usunięcie szablonu użytego
  w cyklu daje 409 z nazwą cyklu w `details.used_in`, a `apply` odrzuca cykl
  wskazujący na nieistniejący/niewidoczny szablon (422).
- Payload jest wersjonowany polem `v: 1` i walidowany Pydantic ZARÓWNO przy
  zapisie, JAK I przy odczycie; Decimale jedzą do JSONB jako stringi
  dziesiętne (`model_dump(mode="json")`, ADR-008) — float po drodze zmieniłby
  ilości w szablonie.

## 7. Schemat — pantry

```sql
pantry_items (id, household_id FK NULL, owner_user_id FK,  -- scope: zawsze household
       product_id FK→canonical_products RESTRICT NULL,
       retail_product_id FK RESTRICT NULL,
       amount NUMERIC(10,3), amount_unit ENUM(g,ml,piece),
       expiry_date DATE NULL, location TEXT NULL, note TEXT DEFAULT '',
       CHECK (product_id IS NOT NULL) OR (retail_product_id IS NOT NULL))
```

Stan faktyczny (BATCH_08, migracja `0010`, `backend/app/modules/pantry/models.py`):

- Tabela **nie ma kolumny `scope`** ani CHECK-a `scope_requires_household`:
  spiżarnia jest zawsze domowa (02_DOMAIN §3.1 pkt 1), a użytkownik bez rodziny
  trzyma ją na sobie (`household_id IS NULL`). Wzorzec §4 się tu nie stosuje —
  kolumny właścicielskie daje `HouseholdScopedMixin`, a widoczność
  `HouseholdScopedQuery` (oba w `app/core/scope.py`, obok `ScopedQuery`):

  ```sql
  WHERE household_id = :user_household_id
     OR (household_id IS NULL AND owner_user_id = :uid)
  ```

  Samo `owner_user_id = :uid` NIE wystarcza świadomie: po odejściu z rodziny
  wpis zostaje przy rodzinie, bo to jeden stan domu, a nie prywatna notatka.
- `owner_user_id` i `household_id` → RESTRICT (jak we wzorcu §4);
  `product_id` → `canonical_products` **RESTRICT** (ADR-012, licznik referencji
  rejestruje `pantry/service.py`).
- **`retail_product_id` istnieje jako `BIGINT NULL` BEZ constraintu FK** —
  tabela `retail_products` powstaje dopiero w BATCH_09. Constraint dopina batch
  mergowany jako drugi (B09 albo R3); do tego czasu CHECK „produkt kanoniczny
  ALBO sklepowy" działa, ale integralności odwołania retail pilnuje wyłącznie
  serwis (API nie przyjmuje jeszcze tego pola).
- Nieujemność `amount` egzekwują schemat Pydantic i serwis — CHECK-a w bazie
  świadomie nie ma, bo nie definiuje go ten dokument.
- Indeksy: `owner_user_id`, `household_id`, `product_id`, `retail_product_id`,
  `expiry_date` (domyślny porządek widoku 6).

## 8. Schemat — shopping

```sql
shopping_round_configs (id, +scope-wzorzec, name,          -- „Niedziela"
       shopping_weekday INT NULL, covers_days INT,          -- ile dni planu
       fresh_days INT NULL,                                 -- świeże na ile dni
       mode ENUM(all,durable_plus_fresh_window,fresh_only), position INT)
shopping_generations (id, +scope-wzorzec, date_from, date_to,
       used_pantry BOOL, params JSONB, status ENUM(preview,final,discarded))
shopping_lists (id, generation_id FK CASCADE NULL, +scope-wzorzec,
       name, round_name TEXT NULL, store_id FK NULL SET NULL,
       expires_at timestamptz, public_token TEXT UNIQUE NULL,
       token_revoked BOOL DEFAULT false)
shopping_list_items (id, list_id FK CASCADE, category_id FK RESTRICT,
       product_id FK RESTRICT NULL, retail_product_id FK RESTRICT NULL,
       label TEXT,                                          -- render offline
       needed_amount NUMERIC(10,3), amount_unit ENUM(g,ml,piece),
       packages_count INT NULL, package_size NUMERIC(8,2) NULL,
       leftover_amount NUMERIC(10,3) NULL,
       already_have BOOL DEFAULT false, from_pantry_amount NUMERIC(10,3) NULL,
       checked BOOL DEFAULT false, checked_at timestamptz NULL, position INT)
```

`public_token`: 43 znaki base64url (256 bitów); index unique; lookup tylko
po pełnym tokenie. `shopping_generations.params` przechowuje pełne wejście
generacji (odtwarzalność preview i test regresyjny silnika).

Stan faktyczny (BATCH_10, migracja `0012`):

- Trzy pierwsze tabele mają kolumny wzorca scope (§4) razem z CHECK-iem
  `scope_requires_household`; `shopping_list_items` scope'u NIE ma — dziedziczy
  go po liście (04_API §3 pkt 2c).
- Nowe typy enumowe: `shopping_round_mode` (`all`, `durable_plus_fresh_window`,
  `fresh_only`) i `shopping_generation_status` (`preview`, `final`,
  `discarded`). `entity_scope` i `amount_unit` są REUŻYTE z migracji `0006`
  (`create_type=False`), więc downgrade `0012` ich nie kasuje.
- CHECK-i domenowe dołożone ponad schemat wyżej: `date_from <= date_to`
  (generacje), `covers_days > 0`, `fresh_days > 0`, `shopping_weekday`
  w zakresie 0–6 (tury), `needed_amount >= 0` i `packages_count > 0` (pozycje).
- `public_token` i `token_revoked` istnieją, ale **żaden endpoint tego batcha
  ich nie czyta ani nie wystawia** — konsumuje je BATCH_11 (pilnuje tego test
  `tests/api/shopping/test_shopping_api.py`).
- `params` ma wersję kształtu (`{"v": 1, …}`): niezgodna wersja daje 409
  z instrukcją „wygeneruj zakupy ponownie", nigdy 500 (`ShoppingParamsError`).
- Liczniki referencji dla 409 `used_in` rejestruje `shopping/service.py`:
  produkt kanoniczny, wariant sklepowy ORAZ sklep (`shopping_lists.store_id`
  ma SET NULL, więc bez licznika lista po cichu straciłaby profil sortowania).

## 9. Schemat — importer

```sql
import_jobs (id, owner_user_id FK, filename, file_path, file_sha256,
       status ENUM(uploaded,parsed,in_review,approved,rejected,failed),
       parse_report JSONB NULL, error TEXT NULL)
staged_recipes (id, import_job_id FK CASCADE, name, day_label, meal_label,
       instructions TEXT, comment TEXT, declared_servings INT NULL,
       pdf_kcal NUMERIC(7,1) NULL, pdf_macros JSONB NULL,   -- W/B/T/Bł/ŁG
       resolution ENUM(create,merge_into_existing,skip) NULL,
       target_recipe_id FK NULL, resolved_servings INT NULL)
staged_ingredients (id, staged_recipe_id FK CASCADE, raw_name, raw_qty,
       raw_unit, grams NUMERIC(10,3),
       suggested_product_id FK NULL, match_kind ENUM(exact,fuzzy,ai,none),
       confirmed_product_id FK NULL, create_new_product BOOL DEFAULT false)
import_issues (id, import_job_id FK CASCADE, staged_recipe_id FK NULL,
       kind ENUM(multi_portion_suspect,kcal_mismatch,unmapped_product,
                 unit_conflict,duplicate_recipe,parse_warning),
       severity ENUM(blocker,warning), details JSONB,
       resolution TEXT NULL, resolved_at timestamptz NULL)
```

Zatwierdzenie joba dozwolone tylko bez nierozwiązanych issues `blocker`.

## 10. Schemat — audit i transfer

```sql
audit_entries (id, user_id FK NULL SET NULL, action TEXT, entity_type TEXT,
       entity_id BIGINT NULL, payload JSONB, created_at)
       -- payload: before/after dla nutrition, parametry importu/eksportu
       -- indeksy: (entity_type, entity_id), created_at DESC, user_id
       -- BEZ updated_at: tabela jest append-only (BATCH_03)
```

Eksport nie ma tabel (generowany plik); import loguje się w audit_entries.

## 11. Storage plików

Uploady (zdjęcia przepisów/produktów, PDF-y importu) na bind mount
`/data/uploads` (ADR-002), ścieżki względne w DB, nazwy losowe
(`uuid4().hex + rozszerzenie po sniffingu typu`), oryginalna nazwa tylko
w metadanych. Miniatury generowane przy uploadzie (Pillow), obok oryginału.

## 12. Retencja i sprzątanie

- Sesje: usuwanie wygasłych przy logowaniu + job okresowy (proste DELETE).
- Listy zakupowe: wygasłe pozostają w DB (historia), tylko token przestaje
  działać; ADMIN/właściciel może usuwać stare listy ręcznie (bulk).
- Import jobs: pliki PDF usuwane przy odrzuceniu; zatwierdzone zostają
  (audyt pochodzenia przepisu).

## 13. Backup

`pg_dump -Fc` (custom format) przez kontener narzędziowy + kopia katalogu
uploads; szczegóły operacyjne: `09_DEPLOYMENT_AND_OPERATIONS.md`. Restore
ćwiczony w BATCH_18 (nie „wierzymy", tylko sprawdzamy).
