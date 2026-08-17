# BATCH_06 — GOALS_AND_DAY_PLAN

Klasa: CORE · Zależności: BATCH_05 (przepisy + silnik nutrition) · Rozmiar: **L**

## Goal

Po tym batchu użytkownik ustawia dzienne cele żywieniowe (z historią
obowiązywania) i buduje plan dnia: dowolna liczba posiłków o własnych
nazwach, pozycje z przepisów (mnożnik porcji) lub produktów luzem,
opcjonalny rozkład rodzinny porcji, cel kcal per posiłek i jawna akcja
„dopasuj porcję do celu". Widok Planu dnia (widok 1 wizualizacji) pokazuje
kafelki wartość/cel z paskami, karty posiłków i panel makro — wszystkie
wartości liczone silnikiem z B05, nic nie jest cache'owane.

## Context

Batch zastaje po B05 (stan faktyczny sprawdź w `PROGRESS.md`):

- `modules/nutrition/engine.py` — czyste funkcje Decimal (stan FAKTYCZNY
  po B05, sygnatury są kontraktem):
  `ingredient_nutrition(basis_amount, product: ProductNutrition)` — ilość na
  osi WARTOŚCI produktu (`to_basis_amount` z `catalog/units.py`; wzór
  przepakowania i obsługi rozjechanego `measure_kind`:
  `recipes/service.py::_ingredient_values`); produkt UNVERIFIED ⇒
  `complete=False` + wpis „…: produkt niezweryfikowany" w `missing`;
  `recipe_nutrition(list)` (= `aggregate`), `portion_nutrition(total,
  base_servings: int)`, `scale(values, multiplier: Decimal)`,
  `glycemic_load(gi, carbs_g, fiber_g|None)`, `aggregate(list)` (dedupe
  `missing`, `complete` = AND), `round_for_output(values)` (kcal→1, reszta→0,1,
  WYŁĄCZNIE na wyjściu). Typy w `modules/nutrition/types.py`:
  `NutritionValues` (`{kcal, protein_g, fat_g, carbs_g, fiber_g, sugars_g,
  glycemic_load, complete, missing[]}` — pola Decimal to SUMA Z DOSTĘPNYCH),
  `NUTRITION_NUMERIC_FIELDS`, `ZERO_VALUES`, re-eksport `ProductNutrition`.
- `modules/recipes/` — CRUD przepisów, `GET /recipes/{id}?servings=`, tagi,
  oceny, zdjęcia. **B06 MUSI zarejestrować licznik referencji przepisów**:
  `recipes.service.register_recipe_reference_finder(finder)` z
  `finder(session, recipe_id) -> Sequence[UsedInRef]` — bez tego DELETE
  przepisu użytego w planie da gołe 409 z FK RESTRICT zamiast listy
  „Używane w:" (rejestr powstał w B05 i jest pusty).
  `modules/catalog/` — produkty + normalizacja jednostek (ADR-005).
- Typ enumowy **`amount_unit`** (`g,ml,piece`) tworzy migracja `0006` —
  `plan_meal_items.amount_unit` używa `postgresql.ENUM(..., create_type=False)`
  (tak samo jak `entity_scope`).
- Pułapka FastAPI z B05: parametr query typu Decimal deklaruj przez
  `Annotated[Decimal, Query(...)]` — `Field(...)` w Annotated nie działa
  jako query param (`?servings=` w `recipes/router.py` to wzór).
- `member_profiles` (B03) — profile członków rodziny z `default_multiplier`
  i opcjonalnym `kcal_goal`; `users.ui_settings JSONB` (B02).
- Frontend: ProductPicker, AmountInput, RecipeCard, klient API, AppShell.
- Brak: tabel goals/plan, stron `/plan-dnia` i sekcji celów w ustawieniach,
  komponentów charts.

Konwencje potwierdzone w review R1 (obowiązują od pierwszej linii tego batcha):

- **Typ enumowy `entity_scope` tworzy migracja B05** (`recipes`). Każda
  kolejna tabela ze scope — a więc wszystkie tabele planningu — używa
  `postgresql.ENUM("private", "household", name="entity_scope",
  create_type=False)`, inaczej migracja wywali się na „type already exists".
  Kolumny wzorca dostajesz z `ScopedMixin`, nie deklarujesz ich ponownie;
  model z własnymi `__table_args__` musi dołożyć `scope_check_constraint()`.
- **Nowa tabela = wpis w DWÓCH miejscach testowych**: `DB_TABLES`
  (`tests/conftest.py`) i `EXPECTED_TABLES`
  (`tests/integration/test_migrations.py`); nowy typ enumowy dopisz do
  `EXPECTED_ENUM_TYPES` tam samo. Bez tego `task check` pada na asercji
  zestawu tabel.
- **Każde pole NUMERIC w odpowiedzi to `DecimalString`** (`app/core/schemas.py`)
  — cele kcal, mnożniki porcji i wartości wychodzą jako stringi dziesiętne;
  po stronie FE parser jest jeden (`src/lib/decimal.ts`), formatowanie jedno
  (`src/lib/format.ts`).
- Mnożniki i ilości przechodzą przez `catalog/units.py`; uwaga na dwie osie
  (`base_unit` vs `basis_unit` — patrz karta B05, naprawa z R1).
- Widoczność planów: `ScopedQuery` bez wyjątków. Jeśli właściciel rozstrzygnie
  **D16** (czy ADMIN widzi cudze encje na ścieżkach użytkownika), B06 idzie za
  rozstrzygnięciem — mechanizm jest w jednym miejscu (`app/core/scope.py`).
  B05 zaasercjonował stan faktyczny testem
  `tests/api/recipes/test_recipes_api.py::test_d16_admin_widzi_cudze_przepisy_na_sciezkach_uzytkownika`
  — rozstrzygnięcie odwrotne ma zacząć od wywrócenia tego testu.

Wymagane lektury przed startem:

- `00_MASTER_PLAN.md` §6–8 · `02_DOMAIN_MODEL.md` §6 (cele, progi, „dopasuj
  porcję do celu"), §7 (PlanDay/PlanMeal/PlanMealItem, rozkład rodzinny), §13.3
- `03_DATABASE_DESIGN.md` §1, §2 (`user_nutrition_goals`), §4 (wzorzec scope),
  §6 (plan_days/plan_meals/plan_meal_items/plan_item_servings — WIĄŻĄCE)
- `04_API_DESIGN.md` §1–3 (`/goals`, `/plan/*`) · `05_FRONTEND_ARCHITECTURE.md`
  §1–4 · `06_UIUX_PRINCIPLES.md` §2–3, §4 widok 1 · ADR-008, ADR-013
- `08_TESTING_STRATEGY.md` §2.1–2.2, §3 (smoke), §4
- `02_DECISIONS.md` **D9** (progi 90–110%, konfigurowalne per user — przyjęte
  bez osobnego zatwierdzenia) i D10 (nic nie usuwamy automatycznie)

## Stages

1. **DB**: migracja `user_nutrition_goals` + tabel planning (§Database);
   up/down/up zielone.
2. **Silnik — rozszerzenia**: czyste funkcje `fit_servings_to_target`
   i `goal_status` w `nutrition/engine.py` + testy unit.
3. **Backend goals**: serwis (cel obowiązujący w dacie), router, walidacje.
4. **Backend plan**: serwisy dnia/posiłku/pozycji (rozkład rodzinny,
   agregaty przez silnik), `/plan/copy`, router.
5. **Frontend**: charts `NutritionBar` + `DonutChart` (ADR-013),
   `PlanDniaPage` (widok 1), sekcja celów i progów w `UstawieniaPage`.
6. **Testy int/api/fe + E2E smoke rozszerzony** + docs/PROGRESS.

## Database / migrations

Wg `03_DATABASE_DESIGN.md` — bez odstępstw:

- `user_nutrition_goals` (§2): `user_id FK CASCADE`, `valid_from DATE`,
  `kcal NUMERIC(6,0)`, `protein_g/fat_g/carbs_g NUMERIC(6,1) NULL`,
  `UNIQUE(user_id, valid_from)`. Cel obowiązujący w dniu D = wiersz
  z największym `valid_from <= D`.
- `plan_days` (§6): wzorzec scope + `day DATE`, `title TEXT NULL`,
  `UNIQUE(owner_user_id, day)`.
- `plan_meals`: `plan_day_id FK CASCADE`, `name`, `position`,
  `kcal_target NUMERIC(6,0) NULL`.
- `plan_meal_items`: `plan_meal_id FK CASCADE`, `recipe_id FK RESTRICT NULL`,
  `product_id FK RESTRICT NULL`, `amount NUMERIC(10,3) NULL`,
  `amount_unit ENUM(g,ml,piece) NULL`, `servings NUMERIC(6,2) DEFAULT 1.0`,
  `position`, `CHECK ((recipe_id IS NOT NULL) <> (product_id IS NOT NULL))`.
- `plan_item_servings`: `plan_meal_item_id FK CASCADE`,
  `member_profile_id FK CASCADE`, `multiplier NUMERIC(4,2)` — suma
  multiplierów = `servings` pozycji (pilnowane SERWISEM przy zapisie, nie
  constraintem).
- Progi statusów (D9): klucz `nutrition_thresholds` w `users.ui_settings`
  (JSONB, default `{"low": 90, "high": 110}`) — bez migracji schematu.
- Numer migracji = pierwszy wolny; jedna głowa po merge'u.

## Backend

| Ścieżka (`/api/v1`) | Metoda | Rola | Uwagi |
|---|---|---|---|
| `/goals` | GET | U | historia własnych celów (sort `valid_from` desc) + cel bieżący |
| `/goals` | POST | U | nowy cel od `valid_from` (409 przy duplikacie daty) |
| `/goals/{id}` | PUT/DELETE | U | tylko własne; historia zachowana (D10 — bez auto-czyszczenia) |
| `/auth/me/ui-settings` | PATCH | U | m.in. `nutrition_thresholds` (walidacja: 0 < low < high) |
| `/plan/days?from=&to=` | GET | U | dni z posiłkami+pozycjami+`nutrition` (dzień, posiłek, pozycja) + cel z dnia + statusy |
| `/plan/days/{date}` | GET/PUT | U | PUT tworzy/aktualizuje dzień (title, scope) |
| `/plan/days/{date}/meals` | POST | U | nazwa własna, `kcal_target?`, position |
| `/plan/meals/{id}` | PATCH/DELETE | U | nazwa, `kcal_target`, position |
| `/plan/meals/{id}/items` | POST | U | przepis (`recipe_id`+`servings`) LUB produkt luzem (`product_id`+ilość → normalizacja ADR-005) |
| `/plan/items/{id}` | PATCH/DELETE | U | `servings`, rozkład rodzinny (`servings_split[]`), ilość, position |
| `/plan/items/{id}/fit-to-target` | POST | U | zwraca PROPOZYCJĘ mnożnika (nie zapisuje!) |
| `/plan/copy` | POST | U | `{what: "day"\|"meal", source, targets[]}` — dzień na datę/daty, posiłek do dnia |

Serwisy i reguły:

- `planning/service.py`: agregaty WYŁĄCZNIE przez silnik B05 — pozycja
  z przepisem = `scale(portion_nutrition(...), servings)`; produkt luzem =
  `ingredient_nutrition(amount_g, product)`; posiłek/dzień = `aggregate(...)`
  (niezmiennik 02 §13.3: zmiana mnożnika zmienia wszystko spójnie).
- Rozkład rodzinny: przy zapisie `servings_split` serwis waliduje
  sumę multiplierów = `servings` (Decimal, dokładnie); niezgodność ⇒ 422
  z komunikatem PL. Profile tylko z rodziny właściciela dnia.
- `fit_servings_to_target` (engine, czysta): `target_kcal / kcal_porcji` →
  Decimal kwantyzowany do 0,01 (w dół, by nie przekraczać celu); endpoint
  zwraca `{proposed_servings, resulting_nutrition}`; zastosowanie = osobny
  PATCH pozycji (akcja JAWNA — nic nie zmienia się samo, 02 §6).
- `goal_status(value, target, thresholds)` (engine, czysta): `below`
  (<low%), `ok` (low–high%), `above` (>high%); progi z `ui_settings` usera.
- `/plan/copy`: głęboka kopia (nowe id posiłków/pozycji/rozkładów);
  kopiowanie na datę z istniejącym dniem DOPISUJE posiłki na koniec
  (bez nadpisywania — bezpieczne, deterministyczne); wiele dat naraz.
- Scope przez `ScopedQuery`; `UNIQUE(owner_user_id, day)` mapowane na 409.

## Frontend

- `src/components/charts/NutritionBar.vue` i `DonutChart.vue` — TU powstają
  (ADR-013): własne SVG, kolory tylko z tokens 06_UIUX §1, `role="img"` +
  `aria-label` z wartościami; statusy kolorem ZAWSZE z tekstem (bursztyn/
  zieleń/czerwień). Pełny `BarChart` (stacked) → B07.
- `pages/plan-dnia/PlanDniaPage.vue` (widok 1, routing `/plan-dnia/:date?`):
  - nagłówek: data + nawigacja dzień ±1 / dziś;
  - 4 kafelki Kalorie/Białko/Tłuszcze/Węglowodany: wartość/cel + NutritionBar
    + status słowny (trio wartość/cel/delta — 06_UIUX §3.5);
  - lista `MealCard` (nazwa, kcal/target posiłku, miniatury pozycji, menu ⋮:
    edytuj / duplikuj / przenieś / usuń / dopasuj porcję do celu);
  - pozycje: mnożnik inline (stepper), rozkład rodzinny w drawerze
    (profile z mnożnikami, suma walidowana na żywo, default z
    `default_multiplier` profili);
  - panel boczny (desktop): DonutChart makro dnia + mini-słupki tygodnia
    (7×NutritionBar pionowy, kcal vs cel);
  - FAB „+": dodaj posiłek / dodaj pozycję — `RecipePicker` (command palette
    wzorem ProductPickera, inline create: minimalny drawer nazwa+base_servings)
    lub ProductPicker + AmountInput dla produktu luzem;
  - „dopasuj porcję do celu": dialog z propozycją mnożnika i wynikowym kcal,
    Zastosuj/Anuluj; puste stany uczą (06 §3.2).
- `UstawieniaPage` — sekcja „Cele żywieniowe": formularz celu od daty,
  historia celów; sekcja „Progi statusów" (low/high %, default 90/110).
- `queryKeys` += `planDays`, `goals`; mutacje z invalidation zakresu dat;
  Pinia bez kopii danych serwera (ADR-007).

## Security

- Wszystkie zasoby batcha za sesją + CSRF; scope `ScopedQuery` — cudzy
  PRIVATE dzień ⇒ 404; edycja HOUSEHOLD przez członka rodziny OK (macierz).
- Anty-IDOR na zagnieżdżeniach: PATCH `/plan/items/{id}` weryfikuje łańcuch
  item→meal→day→scope (nie tylko istnienie id).
- Rozkład rodzinny: `member_profile_id` musi należeć do rodziny właściciela
  dnia — inaczej 422 (nie ujawniamy cudzych profili).
- Cele i `ui_settings`: wyłącznie własne (`user_id` z sesji, nie z body).
- Brak nowych uploadów/tokenów publicznych.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE, SKILL-CALC
- **Review**: SKILL-REVIEW

## Tests

- **Unit — engine (08 §2.1–2.2)**: `fit_servings_to_target` (dokładny cel,
  zaokrąglenie w dół do 0,01, kcal_porcji=0 ⇒ błąd domenowy, brak targetu);
  `goal_status` (progi brzegowe: dokładnie 90% = ok, dokładnie 110% = ok,
  progi niestandardowe z ui_settings); property-based: dzień = suma posiłków
  = suma pozycji (addytywność `aggregate`), skalowanie liniowe mnożnika,
  completeness propaguje się z pozycji na dzień.
- **Unit — serwis (bez DB, na strukturach)**: walidacja sumy rozkładu
  (3×1.0 + 2×0.8 + 2×1.3 ⇒ servings 6.2 — przykład z 02 §7; niezgodność ⇒ błąd).
- **Integration**: cel obowiązujący wg `valid_from` (dzień przed/po zmianie);
  `UNIQUE(user_id, valid_from)` ⇒ 409; głęboka kopia dnia (nowe id, wartości
  równe, edycja kopii nie zmienia oryginału); kopiowanie na zajętą datę
  dopisuje posiłki; kaskady day→meals→items→servings; produkt luzem
  z jednostką nieprzeliczalną ⇒ 422 i rollback; RESTRICT: DELETE przepisu
  użytego w planie ⇒ 409 z datą/nazwą dnia w `used_in`.
- **API**: macierz uprawnień 08 §4 dla `/plan/days` i `/goals`; PATCH
  mnożnika zmienia `nutrition` pozycji/posiłku/dnia w jednej odpowiedzi
  GET; `fit-to-target` niczego nie zapisuje (GET po nim = stan sprzed);
  `ui-settings` walidacja progów.
- **FE (vitest)**: `NutritionBar` (wartość/cel/status, aria-label),
  `DonutChart` (udziały makro), logika statusu z progami.
- **E2E — smoke rozszerzony (08 §3)**: login → plan dnia → dodaj posiłek
  („II śniadanie") → dodaj pozycję z istniejącym przepisem → kafelki
  i donut aktualizują wartości → zmiana mnożnika → wartości spójnie
  przeliczone → wylogowanie.

## Acceptance Criteria

1. `task check` zielony; migracje up/down/up na kopii bazy.
2. Cel dzienny z historią: zmiana celu od daty nie zmienia statusów dni
   sprzed tej daty (test integracyjny).
3. Plan dnia przyjmuje dowolną liczbę posiłków o własnych nazwach
   i `kcal_target`; pozycje: przepis z mnożnikiem LUB produkt luzem
   (znormalizowany, nieprzeliczalny odrzucony).
4. Rozkład rodzinny: suma multiplierów = servings wymuszona serwisem (422
   przy niezgodności); przypadek prosty (servings bez rozkładu) działa bez
   dodatkowych kroków.
5. Kafelki dnia pokazują wartość/cel/pasek/status wg progów z `ui_settings`
   (default 90–110%, edytowalne w ustawieniach — D9).
6. „Dopasuj porcję do celu" wyłącznie proponuje mnożnik; zapis następuje
   dopiero po jawnym zatwierdzeniu.
7. `/plan/copy` kopiuje dzień na datę/daty i posiłek do dnia — głęboka kopia,
   bez nadpisywania istniejących posiłków.
8. Wartości dnia/posiłku/pozycji zawsze z silnika B05, nigdzie nie zapisane
   w DB (inspekcja schematu + test niezmiennika 02 §13.2–13.3).
9. Macierz uprawnień 08 §4 zielona dla planu i celów; anty-IDOR na
   zagnieżdżonych id.
10. E2E smoke rozszerzony zielony; `NutritionBar`/`DonutChart` dostępne
    (aria-label) i w kolorach tokens.

## Out of Scope

- Widok tygodnia, szablony dnia/tygodnia, cykle, „powiel blok", drag&drop
  między dniami → BATCH_07 (model danych planu już to umożliwia).
- Agregacja zakupowa z planu → BATCH_10; statystyki zakresów → BATCH_13.
- `TrendLine` i pełny `BarChart` → B13/B07.
- Cele per członek rodziny w UI planu (kcal_goal profili) — tylko dane
  z B03; wizualizacja per osoba to kandydat FUTURE (zaparkować, nie budować).

## Expected files/modules

- `backend/app/modules/nutrition/engine.py` += `fit_servings_to_target`,
  `goal_status` (addytywnie — kontrakt B05 nienaruszony).
- `backend/app/modules/planning/{models,schemas,service,router}.py` — NOWE.
- `backend/app/modules/accounts/` — endpoint `ui-settings`, serwis goals
  (lub `modules/nutrition/goals_*` — decyzja implementującego, uzasadnić).
- `backend/migrations/versions/<pierwszy_wolny>_goals_and_planning.py`.
- `backend/tests/{unit,integration,api}/planning/`, `tests/factories.py` +=.
- `frontend/src/components/charts/{NutritionBar,DonutChart}.vue`,
  `components/domain/{MealCard,RecipePicker,ServingsSplitDrawer}.vue`,
  `pages/plan-dnia/PlanDniaPage.vue`, `pages/ustawienia/UstawieniaPage.vue`
  (sekcje cele+progi), `src/lib/schemas/{goal,plan}.ts`, `queryKeys.ts` +=,
  `frontend/e2e/smoke.spec.ts` (rozszerzenie).
- Aktualizacje: `PROGRESS.md`, karta B07 (Context), ew. `04_API_DESIGN.md`.

## Implementation Notes

- `GET /plan/days?from=&to=` to najcięższy endpoint batcha: ładować dzień
  z posiłkami/pozycjami/rozkładami jednym zapytaniem (selectinload), potem
  jedno pobranie produktów/przepisów i JEDNO przejście silnikiem — bez N+1.
- `PATCH /auth/me/ui-settings` nie występuje w mapie 04_API §2 — dopisać do
  dokumentu przy aktualizacji (stan faktyczny, zgodny z konwencjami §1).
- Decyzja „kopiowanie na zajętą datę dopisuje posiłki" jest przyjęta w tej
  karcie — jeśli implementujący znajdzie mocny kontrargument, parkuje
  w 02_DECISIONS zamiast zmieniać zachowanie po cichu.
- Duplikacja posiłku (menu ⋮) = `/plan/copy what=meal` na ten sam dzień.
- Mini-słupki tygodnia w panelu: dane z tego samego `GET /plan/days`
  (zakres tygodnia) — bez dodatkowego endpointu.
- Pułapka Decimal: `servings NUMERIC(6,2)`, multiplier `NUMERIC(4,2)` —
  walidację sumy robić na Decimal, nigdy float; JSON jako stringi.
- Pozostawione implementującemu (uzasadnić): moduł dla goals (accounts vs
  nutrition); kształt `servings_split` w API; czy PUT dnia tworzy dzień
  implicite przy pierwszym posiłku (sugestia: tak — mniej kliknięć, 06 §2).

## Cross-Batch Impact

- **B07**: siatka tygodnia, kopiowanie bloków i szablony budują na
  `/plan/copy` i strukturach planning z tego batcha; payload JSONB szablonów
  odzwierciedla kształt meals/items — po implementacji zaktualizować kartę
  B07 (Context: faktyczne kształty).
- **B10**: silnik zakupowy czyta plan (zakres dat, servings, rozkłady) —
  agregacja porcji zależy od poprawności sumy rozkładów z tego batcha.
- **B13**: statystyki liczą wg celu obowiązującego w dniu (`valid_from`)
  i progów z `ui_settings`; reużywają `goal_status`.
- **B12**: smoke E2E rozszerzony tutaj jest bazą testu offline.
- Po zakończeniu: przenieść ustalenia do kart B07/B10/B13 (00_MASTER §7).

## Implementation checklist

- [ ] Migracja goals + planning; up/down/up zielone, jedna głowa
- [ ] Engine: `fit_servings_to_target`, `goal_status` + testy unit
- [ ] Serwis+router goals, `ui-settings` (progi D9)
- [ ] Serwis+router plan (dni/posiłki/pozycje/rozkłady/copy/fit-to-target)
- [ ] Charts: NutritionBar, DonutChart (tokens, aria)
- [ ] PlanDniaPage (widok 1) + RecipePicker + sekcje w UstawieniaPage
- [ ] Testy integration/api/fe; E2E smoke rozszerzony
- [ ] PROGRESS.md + propagacja do kart B07/B10/B13

## Verification checklist

- [ ] `task check` zielony — wynik REALNY, nie „powinno przejść"
- [ ] `alembic upgrade head && downgrade -1 && upgrade head` na kopii bazy
- [ ] Property-based: dzień = suma posiłków — zielone (raport hypothesis)
- [ ] E2E smoke (dodanie posiłku + pozycji + mnożnik) zielony na compose
- [ ] Ręcznie: dzień z 3 posiłkami, rozkład 3×1.0+2×0.8+2×1.3, dopasuj do
      celu, kopiuj dzień na 2 daty; acceptance criteria 1–10 odhaczone
- [ ] Dokumentacja zaktualizowana (PROGRESS, 04_API, karty przyszłe)
- [ ] Commit `batch(06): <opis>`; `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
