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
- `backend/app/modules/catalog/` — `canonical_products`,
  `product_unit_weights`, `product_categories`, serwis normalizacji jednostek
  (ADR-005) i blokada usuwania (ADR-012). Przepis dopisuje się do listy
  referencji blokujących usunięcie produktu.
- `frontend/src/components/domain/ProductPicker.vue` + `ProductCreateDrawer`
  (create-in-context z B04), `AmountInput` (jeśli B04 go nie dostarczył —
  powstaje w tym batchu wg 05_FRONTEND §4), klient API `src/api/client.ts`,
  typy generowane (`task fe-types`).
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

- [ ] Migracja schematu + seed tagów; up/down/up zielone, jedna głowa
- [ ] `nutrition/engine.py` + `types.py` + testy unit (property + brzegowe)
- [ ] Serwis recipes: normalizacja, scope, blokady, oceny, tagi
- [ ] Router recipes + tags; kształty błędów wg 04_API §1
- [ ] `core/uploads.py` + endpoint photo + auth-gated `/uploads/*`
- [ ] `task fe-types`; strony widoków 2–3 + edytor z ProductPicker/AmountInput
- [ ] Testy integration/api/fe; E2E core flow 1
- [ ] PROGRESS.md + propagacja Cross-Batch Impact do kart B06/B09

## Verification checklist

- [ ] `task check` (unit+int+api+fe-test+typecheck+lint) zielony — wynik REALNY
- [ ] `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
- [ ] Pokrycie `nutrition/engine.py` ≥ 95% (raport w Completion notes)
- [ ] E2E `recipe-inline-create` zielony na realnym stacku
- [ ] Ręcznie: przepis z 3 składnikami (w tym 1 inline create), zdjęcie,
      regulacja porcji, filtr tagów; acceptance criteria 1–10 odhaczone
- [ ] Dokumentacja zaktualizowana (PROGRESS, karty B06/B09, ew. 04_API)
- [ ] Commit `batch(05): <opis>`; `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
