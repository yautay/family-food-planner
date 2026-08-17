# BATCH_05 — RECIPES_AND_NUTRITION_ENGINE

Klasa: CORE · Zależności: BATCH_04 (produkty kanoniczne + ProductPicker), R1 (review fundamentów) · Rozmiar: **L**

## Goal

Po tym batchu użytkownik tworzy, przegląda, filtruje i ocenia przepisy ze
zdjęciami, a system wylicza deterministycznie wartości odżywcze (kcal, makra,
ŁG z IG) na dowolną liczbę porcji. Powstaje **serce systemu**: czysty silnik
`modules/nutrition/engine.py` (ADR-008), z którego będą korzystać wszystkie
kolejne batche (plan dnia, statystyki, zakupy), oraz infrastruktura uploadu
plików (używana ponownie w B09 dla zdjęć produktów retail).

## Context

Batch zastaje po B01–B04 + R1 (stan faktyczny sprawdź w `PROGRESS.md`):

- `backend/app/core/` — config, db, security, deps (`current_user`,
  `require_admin`), errors (kształt błędu z 04_API §1), mixin `ScopedQuery`.

  **`recipes` to PIERWSZA produkcyjna encja ze scope** — konkretne API
  mechanizmu z B03 (`backend/app/core/scope.py`), nie zgaduj go:

  ```python
  from app.core.scope import Scope, ScopedMixin, ScopedQuery, SCOPE_ENUM

  class Recipe(TimestampMixin, ScopedMixin, Base):          # PK `id` i kolumny
      __tablename__ = "recipes"                             # scope daje mixin
      name: Mapped[str] = mapped_column(Text, nullable=False)
      # własne __table_args__? MUSZĄ zawierać scope_check_constraint()

  _RECIPES = ScopedQuery(Recipe, not_found_message="Nie znaleziono przepisu.")

  recipe = await _RECIPES.get_or_404(session, recipe_id, user)   # cudze → 404
  _RECIPES.assert_can_manage(recipe, user)                       # scope/delete
  recipe = Recipe(name=..., **ScopedQuery.ownership_for_create(user, scope))
  statement = _RECIPES.select_visible(user)                      # lista
  ```

  Edycja treści encji HOUSEHOLD nie wymaga `assert_can_manage` (rodzina sobie
  ufa); wymagają go WYŁĄCZNIE zmiana scope i usunięcie. Własnych filtrów
  widoczności nie piszemy — to błąd review.

  **Migracja `recipes` tworzy typ enumowy `entity_scope`** (B03 celowo go nie
  utworzył, bo nie miał go kto używać): `sa.Enum("private", "household",
  name="entity_scope")` w `upgrade`, jawny `DROP TYPE` w `downgrade` (wzór:
  `user_role` w migracji `0002`). Kolejne tabele ze scope (B06+) muszą
  wtedy użyć `postgresql.ENUM(..., create_type=False)`.

  Macierz uprawnień z 08_TESTING §4 jest już udowodniona na encji testowej
  (`tests/integration/test_scope_matrix.py`) — w B05 powtarzasz ją jako testy
  API `/recipes` (anonim 401 / obcy 404 / członek 200 / delete: członek 403).
- `backend/app/modules/catalog/` (BATCH_04, migracje `0004`+`0005`) — konkrety,
  których NIE wymyślasz od nowa:

  - **`catalog/units.py`** to jedyne miejsce konwersji ilości:
    `normalize_amount(quantity: Decimal, unit_label: str, product: ProductMeasure)
    -> NormalizedAmount(amount, unit)` (`AmountUnit` = `g` | `ml` | `piece`),
    `to_grams(...)`, `to_basis_amount(...)` (ilość na osi, w której podane są
    wartości „na 100"), `UnitConversionError` (AppError → 422). Nieprzeliczalna
    ilość MUSI wysadzić zapis składnika — to niezmiennik 02_DOMAIN §13.1.

    **DWIE osie, nie jedna (naprawa w R1 — nie odwracaj jej!)**:
    `base_unit(measure_kind)` = oś przechowywania ilości podanej w jednostce
    produktu (masa → `g`, objętość → `ml`, sztuki → `piece`);
    `basis_unit(measure_kind)` = oś wartości „na 100" (objętość → `ml`,
    **masa i sztuki → `g`**). Przelicznik jednostki domowej
    (`product_unit_weights.grams_per_unit`) zwraca ilość na osi `basis_unit`,
    więc dla produktu w sztukach daje GRAMY. Konsekwencja dla schematu
    `recipe_ingredients`: `amount_unit` dla produktu `measure_kind=piece` bywa
    `g` (gdy użyto jednostki domowej) albo `piece` (gdy użyto `szt.`) — oba
    zapisy są legalne i `to_basis_amount` obsługuje oba.
  - **Adapter `ProductNutrition` JUŻ ISTNIEJE**
    (`catalog/nutrition_adapter.py`: `nutrition_for(product, extras)`,
    `measure_for(product, unit_weights)`) — silnik B05 konsumuje go, a NIE tworzy
    drugiego. Ma `is_complete`, `has_core_macros`, `has_glycemic_index`,
    `missing` (komunikaty PL), `digestible_carbs_100` i `basis_unit`.
    Uwagi z R1: (a) `measure_for` przyjmuje dataclassy `UnitWeight`
    z `units.py`, NIE wiersze ORM `ProductUnitWeight` — serwis musi je
    przepakować; (b) jedynym miejscem poza adapterem, które czyta kolumny
    wartości, jest schemat ODPOWIEDZI `ProductNutritionRead`
    (`catalog/router.py`) — to prezentacja formularza admina, nie wejście
    obliczeń; silnik nie ma prawa dołożyć drugiego takiego czytnika;
    (c) `hypothesis` NIE jest jeszcze zależnością — B05 dopisuje ją do
    `[dependency-groups] dev` w `backend/pyproject.toml` (`uv sync`).
  - **Wartości rdzenia są NULLOWALNE** — produkt po inline create nie ma kcal
    ani makro. Silnik musi to unieść flagą `complete=False`, nigdy zerem.
  - **Blokada usuwania**: `app/core/deletion.py` (`UsedInRef`, `assert_deletable`,
    `conflict_from_integrity_error`). Przepisy dopinają się do rejestru
    w `catalog/service.py`: `register_product_reference_finder(finder)`, gdzie
    `finder(session, product_id) -> Sequence[UsedInRef]` zwraca CZYTELNE nazwy
    („Gołąbki"). Bez tego użytkownik dostanie 409 bez listy „Używane w:".
  - `normalize_name` (`catalog/naming.py`) liczy `normalized_name` — używaj tej
    funkcji, nie własnej.
- `frontend/src/components/domain/ProductPicker.vue` + `ProductCreateDrawer`
  + `AmountInput` (wszystkie z B04 — NIE piszesz ich drugi raz), klient API
  `src/api/client.ts`, typy generowane (`task fe-types`).

  `ProductPicker`: props `modelValue: Product | ProductDetail | null`, `label?`,
  `limit?` (8), `disabled?`, `debounceMs?` (250); emits `update:modelValue`
  i `selected(product)`; `data-testid`: `picker-input`, `picker-option-{id}`,
  `picker-create`, `picker-selected`.
  `AmountInput`: props `modelValue: string | null` (STRING dziesiętny, nie
  `Number`), `unit?`, `units?`, `label?`, `decimalPlaces?`, `positive?`,
  `required?`, `testid?`, `hint?`; emits `update:modelValue`, `update:unit`.
  Formatowanie ilości wyłącznie przez `src/lib/format.ts` (`formatAmount`).
- Brak: przepisów, tagów, ocen, silnika nutrition, uploadu zdjęć.

Wymagane lektury przed startem:

- `00_MASTER_PLAN.md` §6–8 (szablon, DoD, living documentation)
- `02_DOMAIN_MODEL.md` §5 (Recipes), §6 (silnik — wzory i zaokrąglenia), §13
- `03_DATABASE_DESIGN.md` §1 (migracje), §5 (schemat recipes — WIĄŻĄCY), §11
- `04_API_DESIGN.md` §1–3 · `05_FRONTEND_ARCHITECTURE.md` §1–5
- `06_UIUX_PRINCIPLES.md` §3, §4 widoki 2–3 · `07_SECURITY_DESIGN.md` §6
- `08_TESTING_STRATEGY.md` §2.1–2.3, §4 · ADR-004, ADR-005, ADR-008, ADR-012
- `02_DECISIONS.md` D4 (zakres wartości), D11 (IG — braki tolerowane)

## Stages

1. **DB**: migracja tabel recipes/tags/ratings + seed tagów systemowych;
   `alembic upgrade head` + `downgrade -1` + `upgrade head` zielone.
2. **Silnik nutrition**: `modules/nutrition/engine.py` + adapter
   `ProductNutrition`; komplet testów unit (property-based + brzegowe) —
   silnik DONE zanim powstanie jakikolwiek endpoint.
3. **Backend recipes**: models/schemas/service/router; normalizacja ilości
   przy zapisie (odrzucenie nieprzeliczalnych), tagi, oceny, autoryzacja scope.
4. **Upload**: `core/uploads.py` (sniffing, re-encode, miniatury) + endpoint
   zdjęcia przepisu + auth-gated serving `/uploads/*`.
5. **Frontend**: `task fe-types`, strony widoków 2–3 + edytor z ProductPicker
   i AmountInput; query keys i mutacje.
6. **Testy int/api/fe + E2E** (core flow 1) + aktualizacja docs/PROGRESS.

## Database / migrations

Tabele dokładnie wg `03_DATABASE_DESIGN.md` §5 (nie wymyślać własnych kolumn):

- `recipes` — wzorzec scope (`owner_user_id`, `household_id`, `scope`) +
  `name`, `instructions TEXT DEFAULT ''`, `base_servings INT CHECK >=1
  DEFAULT 1`, `prep_time_min INT NULL`, `difficulty INT NULL CHECK 1..10`,
  `photo_path TEXT NULL`, `source ENUM(manual,pdf_import) DEFAULT manual`,
  `import_job_id FK NULL` (FK dopnie B15 — tu kolumna nullable bez FK albo
  FK odroczony; uzasadnić wybór w Completion notes), `is_archived BOOL`.
- `recipe_ingredients` — `recipe_id FK CASCADE`, `product_id
  FK→canonical_products RESTRICT`, `display_qty NUMERIC(8,3) NULL`,
  `display_unit TEXT NULL`, `amount NUMERIC(10,3)`, `amount_unit
  ENUM(g,ml,piece)`, `note TEXT DEFAULT ''`, `position INT`.
- `tags` (`name UNIQUE`, `is_system BOOL DEFAULT false`), `recipe_tags`
  (PK złożony), `recipe_ratings` (`rating INT CHECK 1..5`,
  `UNIQUE(recipe_id, user_id)`).
- Seed (migracja danych, osobna od schematu, idempotentna) tagów systemowych:
  śniadanie, obiad, kolacja, szybkie, warzywne, do lunchboxa, do zamrożenia,
  dzieci lubią, **ulubione** (serce na karcie — 06_UIUX §4.2).
- Numer migracji = pierwszy wolny w `backend/migrations/versions/`;
  `down_revision` z `alembic heads`; downgrade usuwa tabele i enumy.

## Backend

| Ścieżka (`/api/v1`) | Metoda | Rola | Uwagi |
|---|---|---|---|
| `/recipes` | GET | U | filtry: `q`, `tag` (multi), `prep_time_max`, `difficulty_max`, `rating_min`, `scope`; paginacja `limit/offset`, `{items,total}` |
| `/recipes` | POST | U | tworzy ze składnikami; normalizacja ilości (niżej) |
| `/recipes/{id}` | GET | U | `?servings=2.5` → pole `nutrition` per porcja × mnożnik (04_API §1) |
| `/recipes/{id}` | PUT | U | pełna podmiana (składniki wymieniane kompletem) |
| `/recipes/{id}` | DELETE | wł./A | 409 + `details.used_in` gdy użyty (od B06: plan; od B07: szablony) |
| `/recipes/{id}/rating` | PUT | U | upsert własnej oceny 1–5; odpowiedź zawiera średnią |
| `/recipes/{id}/photo` | POST/DELETE | U (scope edycji) | multipart; pipeline z §Security |
| `/tags` | GET/POST | U | POST = inline create (tag użytkowy `is_system=false`) |
| `/uploads/{path}` | GET | U | serving plików z autoryzacją (poza `/api/v1`, wg 01_ARCH §1) |

Serwisy i reguły:

- `recipes/service.py`: każda pozycja składnika przechodzi normalizację przez
  serwis catalogu (ADR-005): (`display_qty`, `display_unit`, produkt) →
  `amount` w g/ml/szt. **Brak jednoznacznego przelicznika ⇒ 422**
  `validation_error` z komunikatem PL wskazującym produkt i jednostkę
  („Podaj gramaturę jednostki »łyżka« dla produktu Mąka"). `amount_unit=piece`
  tylko dla produktów `measure_kind=piece` (03_DB §5).
- `nutrition/engine.py` — czyste funkcje, `Decimal`, zero I/O (ADR-008):
  `ingredient_nutrition(amount_g, product)`, `recipe_nutrition(ingredients)`,
  `portion_nutrition(total, base_servings)`, `scale(values, multiplier)`,
  `glycemic_load(gi, carbs_g, fiber_g)` = `gi × max(carbs−fiber, 0) / 100`,
  `aggregate(list) → suma + completeness`, `round_for_output(values)`
  (kcal→1, makra→0,1 g, ŁG→0,1 — WYŁĄCZNIE na wyjściu, 02_DOMAIN §6).
- Adapter `ProductNutrition` (dataclass, ADR-004) — jedyne wejście silnika;
  czyta kolumny rdzenia + (w przyszłości) `product_nutrient_values`.
- Kształt `nutrition` w odpowiedziach: `{kcal, protein_g, fat_g, carbs_g,
  fiber_g, sugars_g, glycemic_load, complete, missing[]}`; braki IG/wartości
  i produkty UNVERIFIED ⇒ `complete=false` + pozycje w `missing` (02 §4.9).
- Wartości NIGDY nie zapisywane w encjach (niezmiennik 02 §13.2).

## Frontend

- `pages/przepisy/PrzepisyPage.vue` (widok 2): grid `RecipeCard` (zdjęcie,
  czas, kcal/porcję, średnia ocen, serce=tag „ulubione"), chipsy tagów,
  szukajka (`?q=` debounced), pusty stan „Dodaj pierwszy przepis".
- `pages/przepisy/PrzepisSzczegolPage.vue` (widok 3): hero zdjęcie, meta,
  taby Składniki / Przygotowanie / Wartości odżywcze; **regulacja liczby
  porcji na żywo** — refetch `GET /recipes/{id}?servings=` (TanStack Query,
  `placeholderData: keepPreviousData`); plakietka „niepełne dane" z tooltipem
  `missing` (06_UIUX §3.5).
- `pages/przepisy/PrzepisEdytorPage.vue`: formularz vee-validate+zod
  (`src/lib/schemas/recipe.ts`), lista składników: `ProductPicker`
  (inline create z B04 — obowiązkowo działa stąd!) + `AmountInput`
  (ilość + jednostka produktu, przecinek dziesiętny); tagi jako multi-picker
  z inline create; upload zdjęcia z podglądem.
- `src/api/queryKeys.ts` += `recipes`, `tags`; composables
  `useRecipesQuery`, `useRecipeMutation` z `invalidateQueries`.
- Routing: `/przepisy`, `/przepisy/:id`, `/przepisy/:id/edytuj` + pozycja
  „Przepisy" w AppShell (sidebar/bottom-nav).

## Security

- Upload (07_SECURITY §6 — tu powstaje `core/uploads.py`, reużyty w B09/B15):
  limit 10 MB, sniffing treści (Pillow `verify`), **re-encode** Pillow
  (strip EXIF/payloadów), miniatura obok oryginału, nazwa `uuid4().hex+ext`,
  zapis na bind mount poza web-rootem, serving wyłącznie przez endpoint
  z sesją (nie StaticFiles). Zły typ ⇒ 422, za duży ⇒ 413.
- Scope przepisów przez `ScopedQuery`: cudzy PRIVATE ⇒ 404 (anty-IDOR,
  07 §4); zmiana scope/usunięcie tylko właściciel/ADMIN (macierz 08 §4).
- Ocena: użytkownik zapisuje wyłącznie własną (`user_id` z sesji, nie z body).
- Mutacje z nagłówkiem CSRF (istniejący middleware).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE, SKILL-CALC
- **Recommended**: SKILL-SEC
- **Review**: SKILL-REVIEW

## Tests

- **Unit — silnik (08_TESTING §2.1, pokrycie ~100%)**: przykłady liczbowe
  z ręcznie policzonymi wynikami; property-based (hypothesis):
  addytywność (`aggregate(a,b) = a+b` per pole), liniowość skalowania
  (`scale(v,k)` proporcjonalne), nieujemność, `complete` fałszywe gdy
  jakikolwiek brak. Brzegowe: błonnik > węglowodany ⇒ przyswajalne 0 ⇒ ŁG 0;
  brak IG ⇒ ŁG częściowe + `missing`; brak makra produktu; `base_servings=1`;
  mnożnik `0.25`; zaokrąglenie tylko w `round_for_output` (wynik pośredni
  nie traci precyzji — test na Decimal).
- **Unit — konwersje (§2.3)**: g/kg/ml/l/szt/jednostki domowe per produkt;
  odmowa nieprzeliczalnej; piece bez `piece_weight_g` ⇒ błąd.
- **Integration**: zapis przepisu normalizuje składniki; zapis z jednostką
  bez gramatury ⇒ rollback (nic w DB); seed tagów idempotentny; rating
  upsert (drugi PUT nadpisuje); DELETE produktu użytego w przepisie ⇒ 409
  z nazwą przepisu w `used_in`; kaskada recipe→ingredients/tags/ratings.
- **API**: pełna macierz uprawnień 08 §4 dla `/recipes`; `?servings=`
  poprawnie skaluje `nutrition`; upload: nie-obraz 422, >10 MB 413,
  `/uploads/*` bez sesji ⇒ 401; filtry i paginacja.
- **FE (vitest)**: `AmountInput` (przecinek, walidacja), formatowanie kg,
  edytor: dodanie składnika przez ProductPicker aktualizuje model.
- **E2E (core flow 1, 08 §3)**: login → nowy przepis → w ProductPickerze
  wpis bez trafienia → `+ Dodaj produkt` → drawer → zapis → auto-wybór →
  ilość → zapis przepisu → szczegół pokazuje wartości per porcja → zmiana
  porcji przelicza na żywo. Selektory `data-testid`, seed przez API.

## Acceptance Criteria

1. `task check` zielony; migracje up/down/up przechodzą na kopii bazy.
2. Silnik nutrition: czyste funkcje Decimal, bez I/O/ORM; testy property-based
   + brzegowe zielone; pokrycie engine.py ≥ 95%.
3. Zapis przepisu z ilością nieprzeliczalną jest niemożliwy (422, komunikat PL
   wskazuje produkt/jednostkę); w DB nie istnieje składnik bez `amount`.
4. `GET /recipes/{id}?servings=2.5` zwraca `nutrition` = porcja × 2,5
   z flagą `complete` i listą `missing` przy brakach IG/wartości.
5. Lista przepisów filtruje po tagach (chipsy), tekście, czasie, trudności,
   ocenie; paginacja `{items,total}`.
6. Ocena 1–5 per (przepis, user) z upsertem; średnia widoczna na karcie.
7. Upload zdjęcia: sniffing + re-encode + miniatura; plik dostępny wyłącznie
   po zalogowaniu; zły typ/rozmiar odrzucony.
8. Edytor: inline create produktu z ProductPickera działa bez opuszczenia
   formularza przepisu (E2E flow 1 zielony).
9. Macierz uprawnień 08 §4 dla przepisów przechodzi w testach API.
10. Widok szczegółu: regulacja porcji przelicza składniki i wartości na żywo;
    plakietka „niepełne dane" przy `complete=false`.

## Out of Scope

- Plan dnia, cele, mnożniki w planie → BATCH_06.
- Szablony/tygodnie i blokada usuwania przepisu użytego w szablonie → BATCH_07
  (tu tylko hook zliczania referencji rozszerzalny o kolejne źródła).
- Zdjęcia produktów retail → BATCH_09 (reużywa `core/uploads.py`).
- `source=pdf_import` i `import_job_id` — wypełnia BATCH_15/16.
- Mikroelementy (`nutrients`/`product_nutrient_values`) — słownik pusty,
  adapter gotowy (ADR-004); UI mikro nie powstaje.

## Expected files/modules

- `backend/app/modules/nutrition/engine.py`, `types.py` (ProductNutrition,
  NutritionValues) — NOWE; bez router/service w tym batchu.
- `backend/app/modules/recipes/{models,schemas,service,router}.py` — NOWE.
- `backend/app/core/uploads.py` — NOWE; `main.py` — rejestracja routerów.
- `backend/migrations/versions/<pierwszy_wolny>_recipes_tags_ratings.py`
  (+ osobny seed tagów).
- `backend/tests/unit/nutrition/`, `tests/unit/catalog/test_conversions*`,
  `tests/integration/recipes/`, `tests/api/recipes/`, `tests/factories.py` +=.
- `frontend/src/pages/przepisy/*` (3 strony), `components/domain/RecipeCard.vue`,
  (ew. `AmountInput.vue`), `src/lib/schemas/recipe.ts`, `src/api/queryKeys.ts`,
  `frontend/e2e/recipe-inline-create.spec.ts`.
- Aktualizacje: `PROGRESS.md`, ew. `04_API_DESIGN.md` (stan faktyczny).

## Implementation Notes

- Kolejność twarda: silnik + testy PRZED endpointami — endpointy tylko
  konsumują gotowy, przetestowany silnik.
- **Ustalenia review R1 do domknięcia w tym batchu** (pełna lista w dzienniku
  `PROGRESS.md`, wpis R1):
  1. `ProduktFormPage.vue` pokazuje przeliczniki jednostek zawsze w gramach
     („1 szklanka = 250 g" dla mleka) i etykietę „Gramów na jednostkę" — dla
     produktu VOLUME wartość leży na osi ml. Poprawić przy okazji dotykania
     `AmountInput`/jednostek: użyć `basisUnit` (już policzone w tym pliku)
     i neutralnej etykiety. R1 tego nie ruszał, bo zmienia to, co widzi
     użytkownik.
  2. `ProductCreateDrawer.vue` nie czyści `measureKind`/`pieceWeight` przy
     ponownym otwarciu — po dodaniu produktu „w sztukach" następny inline
     create startuje z `sztuki` i starą wagą sztuki. Reset w tym samym
     `watch`, który czyści `name`.
  3. **D15** (02_DECISIONS): zmiana `measure_kind` nie unieważnia weryfikacji
     wartości. Zanim silnik zacznie liczyć na tych danych, wdrożyć
     rekomendację (zbicie do UNVERIFIED + audyt) albo odnotować decyzję
     właściciela.
  4. **D16** (02_DECISIONS): `/recipes` to PIERWSZA encja ze scope, więc ten
     batch rozstrzyga w kodzie, czy ADMIN widzi na liście cudze przepisy.
     Bez odpowiedzi właściciela: zostaje stan faktyczny `ScopedQuery`
     (ADMIN widzi wszystko, macierz 08_TESTING §4) — i wtedy test API musi
     to jawnie asercjonować, żeby decyzja była widoczna w kodzie.
- Granica ADR-008: service pobiera produkty i buduje `ProductNutrition`,
  silnik nie zna ORM. Nie przenosić Decimal→float nigdzie po drodze; w JSON
  ilości/wartości jako stringi dziesiętne (04_API §1).
- Rozstrzygnięcia dla implementującego (uzasadnić w Completion notes):
  FK `import_job_id` teraz czy w B15; strategia miniatur (rozmiary);
  czy `PUT /recipes/{id}` przy wymianie składników zachowuje `id` pozycji
  (sugestia: nie — pełna wymiana, prostsze).
- Pułapka z 08 §2.1: nie testować zaokrągleń przez porównania float —
  wszystkie asercje na Decimal/stringach.
- Tag „ulubione" jest per-user w sensie UX, ale model N:M przepis↔tag jest
  globalny — serce na karcie działa na przypisaniu tagu do przepisu
  (świadome uproszczenie domowe; jeśli implementujący uzna to za zbyt
  mylące dla rodziny, zaparkować pytanie w 02_DECISIONS, nie zmieniać schematu).

## Cross-Batch Impact

- **B06/B07/B10/B13**: konsumują `nutrition/engine.py` — sygnatury funkcji
  i kształt `NutritionValues` są kontraktem; zmiany tylko addytywne.
- **B09**: reużywa `core/uploads.py` dla zdjęć retail — wpisać do karty B09
  ścieżkę i API helpera po implementacji.
- **B06**: RecipePicker w planie dnia będzie wzorowany na ProductPickerze;
  endpoint `/recipes?q=` musi być szybki (trigram z B04).
- **B15/16**: `source`, `import_job_id`, snapshoty PDF jako metadane.
- Po zakończeniu: zaktualizować karty B06 (Context: co dokładnie istnieje
  w silniku), B09 (upload) — obowiązek z 00_MASTER §7.

## Implementation checklist

- [x] Migracja schematu + seed tagów; up/down/up zielone, jedna głowa
- [x] `nutrition/engine.py` + `types.py` + testy unit (property + brzegowe)
- [x] Serwis recipes: normalizacja, scope, blokady, oceny, tagi
- [x] Router recipes + tags; kształty błędów wg 04_API §1
- [x] `core/uploads.py` + endpoint photo + auth-gated `/uploads/*`
- [x] `task fe-types`; strony widoków 2–3 + edytor z ProductPicker/AmountInput
- [x] Testy integration/api/fe; E2E core flow 1 (spec napisany; NIEURUCHOMIONY — brak Dockera)
- [x] PROGRESS.md + propagacja Cross-Batch Impact do kart B06/B09

## Verification checklist

- [x] `task check` (unit+int+api+fe-test+typecheck+lint) zielony — wynik REALNY
      (3 migrations-check / 170 unit / 78 int / 184 api / 144 vitest / mypy /
      vue-tsc / ruff / eslint / format-check / vite build, exit 0)
- [x] `alembic upgrade head && downgrade -1 && upgrade head` — realnie przez
      `tests/integration/test_migrations.py` na db-test (pełny cykl base↔head,
      asercja zestawu tabel i typów enumowych)
- [x] Pokrycie `nutrition/engine.py` ≥ 95% — **100%** (engine 44/44 stmts,
      types 18/18; `pytest --cov=app/modules/nutrition`)
- [ ] E2E `recipe-inline-create` zielony na realnym stacku — **NIEURUCHOMIONY**
      (w środowisku sesji brak Dockera; dług U15, do odhaczenia przed R2)
- [ ] Ręcznie: przepis z 3 składnikami itd. — **NIEWYKONANE ręcznie** (stack
      nie wstaje bez Dockera); acceptance criteria 1–7 i 9 dowiedzione
      testami int/api (patrz Completion notes), 8 i 10 pokryte E2E spec +
      vitest edytora — do potwierdzenia na compose przed R2
- [x] Dokumentacja zaktualizowana (PROGRESS, karty B06/B09, 04_API §2,
      03_DATABASE §5, 02_DECISIONS D15/D16, CLAUDE.md §4)
- [x] Commit `batch(05): <opis>`; `git status` czysty w zakresie batcha

## Completion notes

**Wykonane.** Stages 1–6 w komplecie: migracje `0006` (schemat §5 + enumy
`entity_scope`/`amount_unit`/`recipe_source` + GIN trigram na `recipes.name`)
i `0007` (seed 9 tagów, idempotentny, downgrade oszczędza tagi w użyciu);
silnik `nutrition/{engine,types}.py` (pokrycie 100%, property-based:
addytywność, liniowość, nieujemność, completeness); moduł `recipes/`
(CRUD + filtry + oceny + tagi + zdjęcie); `core/uploads.py` + `GET /uploads/*`
z sesją; frontend widoków 2–3 + edytor + RecipeCard + naprawy U9/U10.

**Rozstrzygnięcia pozostawione implementującemu (uzasadnienia):**

1. **FK `import_job_id`: teraz NIE** — kolumna nullable bez FK; constraint
   dopina migracja B15 razem z tabelą `import_jobs`. FK do nieistniejącej
   tabeli nie istnieje w PG, a pusta tabela „na zapas" łamie ADR-001.
2. **Miniatury: jeden rozmiar** — `_thumb.jpg`, dłuższy bok ≤512 px, JPEG q85.
   Wystarcza kartom gridu (~240 px) także na ekranach 2x; drugi rozmiar
   to koszt bez konsumenta (YAGNI); hero szczegółu używa oryginału.
3. **PUT wymienia składniki kompletem, id pozycji NIEZACHOWANE** (sugestia
   karty przyjęta) — prostszy serwis i brak fikcji stabilności; nikt jeszcze
   nie trzyma FK do `recipe_ingredients`.
4. **D15 wdrożone wg rekomendacji** (zbicie do UNVERIFIED + `verified_at=NULL`
   przy zmianie `measure_kind` na produkcie z wartościami; widoczne w audycie
   `product.update` — snapshot rozszerzony o `verification_status`).
   Wariantu „zmiana measure_kind tylko dla ADMIN-a" NIE wdrożono — czeka na
   właściciela (02_DECISIONS zaktualizowane).
5. **D16: utrzymany stan faktyczny** ScopedQuery (ADMIN widzi wszystko)
   + jawny test API asercjonujący tę decyzję (nazwa testu w 02_DECISIONS).
6. **Serce „ulubione" na karcie jest wyłącznie wskaźnikiem** (tag przypięty
   do przepisu); przełączanie ulubionych = tag w edytorze. Toggle z karty
   wymagałby PUT całego przepisu albo osobnego endpointu spoza karty batcha —
   zostawione świadomie; jeśli okaże się mylące, pytanie do 02_DECISIONS.
7. **Filtr tagów = koniunkcja (AND)**: doklikiwanie chipsów zawęża
   („obiad" + „ulubione" = ulubione obiady); semantyka nie była w karcie.
8. **Defensywa silnika po D15**: składnik zapisany przed zmianą
   `measure_kind` (np. amount w g, produkt teraz VOLUME) nie wysadza odczytu
   500 — pozycja nie wnosi wartości, wynik dostaje `complete=False`
   i komunikat „ilość w jednostce niezgodnej ze sposobem liczenia produktu"
   (`recipes/service.py::_ingredient_values`).

**Odstępstwa:**

- Testy konwersji per produkt NIE trafiły do `tests/unit/catalog/` (Expected
  files) — komplet scenariuszy §2.3 istnieje od B04/R1 w
  `tests/unit/test_units.py` (jednostki systemowe, domowe per produkt,
  odmowa nieprzeliczalnej, piece bez wagi, obie osie). Duplikowanie plików
  dla samej ścieżki uznane za szum.
- `recipe_tags` bez `created_at`/`updated_at` (03_DATABASE §1 mówi „wszędzie")
  — czysta tabela asocjacyjna zgodna literalnie z §5; odnotowane w 03 §5.
- `AmountInput` nie wymagał zmian (Expected files: „ew.") — reużyty jak jest.
- Naprawa spoza listy plików: fixture `scoped_notes_table`
  (`tests/conftest.py`) przestał tworzyć/kasować typ `entity_scope` (należy
  do migracji 0006; ORM-owy `table.drop` kasowałby typ w użyciu), a
  `tests/integration/test_catalog_seed.py` ponawia seed przez
  `upgrade 0005` + `stamp head` zamiast `upgrade head` (powtórka migracji
  SCHEMATU 0006 na bazie z tym schematem = DuplicateObject). To adaptacje
  wymuszone przez 0006, nie osłabienie testów.

**Follow-upy:**

- E2E `recipe-inline-create.spec.ts` + ręczna weryfikacja acceptance 8/10
  na realnym stacku — przed R2 (dług U15; w tej sesji brak Dockera).
- `docker-compose`/prod: `UPLOADS_DIR` wymaga bind mount poza web-rootem —
  dopisać do zakresu B17/B18 przy przeglądzie deploymentu.
- Seed demo (`task db-seed-demo`) nadal bez przepisów (08_TESTING §5 mówi
  o „5 przepisach") — naturalne miejsce: po B06/B07, gdy będzie też tydzień
  planu; do rozważenia w R2.
- `fetchRecipes` składa query string ręcznie (parametr `tag` wielokrotny) —
  jeśli kolejny moduł też będzie potrzebował parametrów multi, rozszerzyć
  `apiFetch.query` zamiast kopiować wzorzec.

**Review (SKILL-REVIEW, /code-review na diffie przed commitem):** 8 kątów;
część finderów uruchomiona subagentami, kąty A/B/C i konwencje wykonane
bezpośrednio po tym, jak subagenci padli na limicie sesji API (bez utraty
pokrycia — diff przejrzany w całości). 10 ustaleń, z tego NAPRAWIONE przed
commitem: (1) watch edytora nadpisywał niezapisane edycje po refetchu
(populate-once), (2) upload czytał całe body do RAM przed limitem (odczyt
z sufitem 10 MB+1), (3) `_rerun_seed` tagów wybuchłby przy migracji 0008
(upgrade celuje w 0007), (4) `SCOPE_ENUM` dostał `create_type=False` — typ
należy do migracji, fixture wrócił do symetrycznego ORM create/drop,
(5) `apiFetch.query` obsługuje parametry wielokrotne (koniec ręcznego query
stringa), (6) `USED_IN_LIMIT` przeniesiony do `core/deletion.py`,
(7) usunięte puste podklasy `RecipeCreateRequest`/`RecipeUpdateRequest`
(jeden `RecipePayload` w OpenAPI), (8) `_to_detail` bez podmiany klucza przez
dict + drobne (ternary o identycznych gałęziach, `formatDecimal` dla
mnożnika porcji, `MeasureKind` z generated.ts zamiast ręcznej unii,
dedup żądań `loadHomeUnits`, `Cache-Control: immutable` dla `/uploads/*`,
`_replace_tags` bez parametru `clear`, `replace(ZERO_VALUES, …)`,
`setQueryData` po zapisie, inline `scaled_fiber`, restrukturyzacja
`_ComputedRecipe`). ODROCZONE świadomie: duplikacja wyszukiwarki trigramowej
catalog↔recipes (ekstrakcja helpera dotyka katalogu — kandydat R2) i
read-back po zapisie (~6 nadmiarowych zapytań na POST — skala domowa,
optymalizacja przy okazji R2). Po naprawach `task check` ponownie zielony.

**Pytania do właściciela:** brak nowych — D15/D16 czekają na formalne
zatwierdzenie (rekomendacje wdrożone/zaasercjonowane, szczegóły
w 02_DECISIONS).
