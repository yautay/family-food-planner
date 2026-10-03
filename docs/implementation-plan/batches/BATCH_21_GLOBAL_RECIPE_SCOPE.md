# BATCH_21 — GLOBAL_RECIPE_SCOPE

Klasa: PLAT (zmiana modelu uprawnień na polecenie właściciela) · Zależności:
B20 (transfer jako jedyny import/eksport), R3/R4 (reference finders, test
dryfu modeli) · Bramki decyzji: **D32 — ZATWIERDZONE 2026-10-03** (kierunek:
zakres `global` dla przepisów); szczegóły projektowe D32 to REKOMENDACJA, którą
batch realizuje bez czekania (inna odpowiedź właściciela = korekta karty, nie
bloker) · Rozmiar: **L** (enum współdzielony przez 8 tabel, migracja
nieodwracalna, siedem miejsc w serwisach, transfer, frontend, macierz uprawnień)
· Sekwencyjnie, **PRZED B22**; z B18 nie koliduje (inne pliki), ale migracja
jest osobną rewizją i jedzie na produkcję z dumpem wg ADR-017.

## Goal

Przepis może mieć zakres `global`: widzi go KAŻDY zalogowany użytkownik każdej
rodziny, używa go we własnych planach, szablonach, cyklach i listach zakupów,
a tworzy, edytuje, archiwizuje i usuwa wyłącznie ADMIN. Zwykły użytkownik może
„skopiować do mojej rodziny” — dostaje własną, edytowalną kopię. Produkty
kanoniczne zostają bez zmian (są globalne od początku, 02_DOMAIN §3.1 pkt 3).
Dzięki temu paczka wygenerowana przez B22 (`/pdf-extract`) może wnieść przepisy
dietetyka do całej instancji, a nie tylko do jednej rodziny.

## Context

Stan zastany (numery linii z przeglądu wpływu 2026-10-03 — **zweryfikuj przed
edycją**, kod mógł się przesunąć):

- `backend/app/core/scope.py`: `Scope` (`PRIVATE`/`HOUSEHOLD`), `SCOPE_ENUM` =
  `postgresql.ENUM(Scope, name="entity_scope", create_type=False)`,
  `ScopedMixin.scope: Mapped[Scope]`, `ScopedQuery.visible_condition` /
  `owned_condition` / `assert_can_manage` / `assert_scope_allowed` /
  `ownership_for_create`. CHECK `scope_requires_household`
  (`scope <> 'household' OR household_id IS NOT NULL`) NIE ogranicza `global`.
- **8 tabel używa typu `entity_scope`**: `recipes` (0006), `plan_days` (0008),
  `day_templates`, `week_templates`, `week_cycles` (0009),
  `shopping_round_configs`, `shopping_generations`, `shopping_lists` (0012).
  `pantry_items` ma `HouseholdScopedMixin` i nie jest dotknięta.
- Pydantic: `Scope` występuje w schematach zapisu planowania, zakupów i przepisów
  (`planning/schemas.py`, `shopping/schemas.py`, `recipes/schemas.py`); w
  `generated.ts` komponent `Scope` jest użyty ~18 razy.
- Odczyty przepisów BEZ filtra scope (świadomie): `RecipesService.portion_values`
  i `ingredient_amounts` — plany z przepisem globalnym liczą się poprawnie dla
  każdej rodziny już dziś. Zapisy z walidacją widoczności: planowanie
  `_assert_recipe_available`, szablony `_assert_references_alive`, cykle
  (`apply_cycle`) — biorą widoczność z `ScopedQuery`, więc przejmą `global`
  automatycznie, jeśli `visible_condition` przepisów go uwzględni.
- Luki zapisu, które po dodaniu `global` stałyby się dziurami: `create_recipe`
  (`ownership_for_create`), `update_recipe` (edycja treści tylko `get_or_404` —
  dziś każdy członek rodziny, dla `global` każdy użytkownik instancji), zmiana
  zakresu (`assert_can_manage` przepuszcza właściciela, więc USER mógłby
  awansować swój przepis do `global`), `delete_recipe`, `set_photo`,
  `delete_photo`.
- Transfer (`transfer/serializer.py`, `service.py`, `importer.py`): eksport
  `scope=user` bierze `select_owned` (własne + rodziny); import klonuje
  `scope` z pliku (`coerce_value`) i przypisuje właściciela/rodzinę kontu
  importującemu, a `_apply_section_quirks` wymusza `private` tylko gdy brak
  rodziny; pozycje planu z `recipe_id` poza zbiorem eksportowalnym są
  **po cichu odrzucane** razem z podziałami porcji (`service.py` ok. L320–327);
  `ExportFile` akceptuje wyłącznie `schema_version: Literal[1]`.
- `is_archived` przepisu NIE jest ustawialne przez API (brak w `RecipePayload`,
  brak endpointu); `list_recipes` domyślnie je ukrywa.
- Usunięcie przepisu: `register_recipe_reference_finder` (plany, szablony —
  JSONB bez FK) + FK `plan_meal_items.recipe_id ON DELETE RESTRICT`.
- `/uploads/*` autoryzuje wyłącznie sesją (`CurrentUser`) + allowlista
  `SERVED_SUBDIRS`; nie ma sprawdzenia „czyj przepis”.
- Migracje: głowa `0016`; `backend/migrations/env.py` wykonuje CAŁY
  `upgrade head` w JEDNEJ transakcji; rola produkcyjna `ffp_user`
  (NOSUPERUSER) jest właścicielem typu `entity_scope` (utworzyła go w `0006`).

Wymagane lektury: 02_DECISIONS **D32**, **D26**, **D16**, **D22**; ADR-006,
ADR-012; 02_DOMAIN §3.1, §5, §11; 03_DATABASE §4; 04_API §3 (reguły
autoryzacji) i „Format eksportu transfer v1”; 07_SECURITY §4 i §6;
08_TESTING §4; CLAUDE.md §4 (blok „B03/B04”, „B05”, „R3”).

## Stages

0. **Baseline**: `task check` zielony na HEAD; zapisz w Completion notes liczby
   wierszy `recipes` per `scope` z bazy dev.
1. **Migracja `0017`** (numer = pierwszy wolny, `down_revision` z `task db-heads`):
   `ALTER TYPE entity_scope ADD VALUE IF NOT EXISTS 'global'` w
   `autocommit_block()`, JAKO OSOBNA REWIZJA, bez użycia wartości w tej samej
   rewizji. Kolejna rewizja (`0018`, to samo zadanie, osobny plik) dokłada CHECK-i
   z użyciem wartości — patrz „Database”. `downgrade` rewizji z `ADD VALUE` = no-op
   z docstringiem (PG nie ma `DROP VALUE`).
2. **Backend — model**: `RecipeScope` (3 wartości) tylko dla `Recipe`;
   `Recipe.scope` nadpisuje kolumnę z mixina własnym
   `postgresql.ENUM(RecipeScope, name="entity_scope", create_type=False, …)`;
   `Scope` zostaje na dwóch wartościach dla pozostałych 7 tabel.
3. **Backend — widoczność i uprawnienia**: `visible_condition` przepisów +
   `OR scope='global'` (wariant `ScopedQuery` dla przepisów albo flaga
   `allow_global`; NIGDY w `owned_condition`); jawne kontrole roli w
   `recipes/service.py` (create / edit / photo / scope do-z global / delete /
   archive) → 403.
4. **Backend — nowe akcje**: `POST /recipes/{id}/copy`, archiwizacja ADMIN-a
   (`POST /recipes/{id}/archive` i `/unarchive` albo `PATCH` z `is_archived` —
   rozstrzygnij zgodnie z konwencją 04_API i zapisz w Completion notes),
   blokada obniżenia zakresu przy użyciu przez inne rodziny (409 + `used_in`).
5. **Transfer**: obcięcie `global` przy imporcie dla nie-ADMIN-a, dołączanie
   przepisów globalnych referencjonowanych przez plany/szablony do eksportu
   użytkownika (zakres obcięty do `household`), tolerancja nieznanej wartości
   enuma jako 422 (nie `ValueError`).
6. **Frontend**: opcja „Wszyscy” w edytorze (tylko dla ADMIN-a), odznaka zakresu
   na karcie i w szczególe, `Edytuj`/`Usuń`/zdjęcie tylko dla ADMIN-a przy
   `global`, przycisk „Kopiuj do mojej rodziny”, przycisk archiwizacji dla
   ADMIN-a, `task fe-types`.
7. **Dokumenty**: ADR-006 (aneks albo nowy ADR — pierwszy wolny numer),
   02_DOMAIN §3.1/§5/§11, 03_DATABASE §4–§6, 04_API (kopiowanie, archiwizacja,
   reguły 2/2a/2c-bis, format transferu), 07_SECURITY §4 i §6, 08_TESTING §4,
   CLAUDE.md (blok `core/scope.py`, zasada `entity_scope`), docstringi
   `core/scope.py` i `recipes/models.py`.
8. **Weryfikacja**: `task check`, `task test-e2e` (nowy spec), test migracji
   dwustopniowy (patrz „Tests”), `task fe-types-check`, PROGRESS.

## Database / migrations

- **`0017` (tylko enum)**: `with op.get_context().autocommit_block():
  op.execute("ALTER TYPE entity_scope ADD VALUE IF NOT EXISTS 'global'")`.
  Powód osobnej rewizji i `autocommit_block`: `env.py` stosuje całe
  `upgrade head` w jednej transakcji, a w PG16 `ADD VALUE` jest dozwolone w
  transakcji, ale NOWEJ wartości nie wolno użyć przed commitem — CHECK, indeks
  częściowy ani wiersz z `'global'` nie mogą powstać w tej samej transakcji.
  **Pułapka testowa**: baza testowa migruje od zera w JEDNEJ transakcji
  (`tests/conftest.py::migrated_database`), a typ utworzony w tej samej
  transakcji bywa z tego wyjątkiem zwolniony — test z samego `upgrade head` od
  zera może przejść tam, gdzie produkcja (0016→0017 na istniejącej bazie)
  się wywróci. Dlatego obowiązkowy test dwustopniowy.
- **`0018` (CHECK-i, osobna rewizja)**: `recipes`:
  `scope <> 'global' OR household_id IS NULL` (przepis globalny nie należy do
  rodziny); pozostałe 7 tabel: `scope <> 'global'` (dziś wartość jest dla nich
  niemożliwa przez typ Pythona, CHECK czyni ją niemożliwą także dla SQL-a).
  Nazwy wg konwencji `ck_<tabela>_<nazwa>`. Rewizja musi się wykonać na bazie
  z istniejącymi wierszami — CHECK `NOT VALID` + `VALIDATE` jest zbędny, bo
  żaden istniejący wiersz nie ma `global`.
- **Downgrade**: `0018` zdejmuje CHECK-i; `0017` = no-op z docstringiem
  („PostgreSQL nie potrafi usunąć wartości enuma; wiersze z `global` po
  downgrade’ie zostają nieczytelne dla starego kodu — przed cofnięciem
  zmień ich zakres albo przywróć dump”).
- `tests/integration/test_migrations.py`: `EXPECTED_ENUM_TYPES` bez zmian (typ ten
  sam); asercja wartości `entity_scope` = `private, household, global`;
  test dryfu modeli zielony BEZ korekty asercji (to dowód, że `RecipeScope` i
  schemat zgadzają się).

## Backend

Endpointy nowe i zmieniane (04_API §2 — dopisać):

| Ścieżka | Metoda | Kto | Uwagi |
|---|---|---|---|
| `/api/v1/recipes/{id}/copy` | POST | każdy zalogowany (widzący przepis) | nowy przepis: właściciel = wywołujący, `scope` z body (`private`/`household`, domyślnie `household` gdy ma rodzinę), składniki + tagi + KOPIA pliku zdjęcia, bez ocen; nazwa z sufiksem `(kopia)`, gdy kopiuje się przepis, którego nazwę wywołujący już ma — nazwy nie są unikalne, ale kopia ma być odróżnialna |
| `/api/v1/recipes/{id}/archive`, `/unarchive` | POST | ADMIN | patrz Stage 4 |
| `/api/v1/recipes` | POST | USER/ADMIN | `scope=global` tylko ADMIN (403 dla USER), `household_id=NULL` |
| `/api/v1/recipes/{id}` | PUT | wg zakresu | przepis `global`: wyłącznie ADMIN (403, bo widoczny); zmiana zakresu do/z `global`: wyłącznie ADMIN |
| `/api/v1/recipes/{id}` | DELETE | wg zakresu | `global`: ADMIN; 409 `used_in` bez zmian; blokada gdy używają go inne rodziny |
| `/api/v1/recipes/{id}/photo` | PUT/DELETE | wg zakresu | `global`: ADMIN |
| `GET /api/v1/recipes?scope=` | GET | każdy | filtr przyjmuje `global`; typ z `RecipeScope` |

- **Nie** polegaj na `owner_user_id == user.id` dla `global` — sprawdź rolę
  (`user.role is UserRole.ADMIN`). Zdegradowany były admin jest nadal
  właścicielem wiersza i nie może go ruszać.
- Obniżenie zakresu z `global` (np. do `household`) wymaga `household_id`:
  weź rodzinę ADMIN-a wykonującego akcję (ścieżka „household fill” w
  `update_recipe` już to robi dla właściciela); jeśli inne rodziny mają
  pozycje planu lub szablony z tym przepisem → 409 z `used_in`, bo ich
  szablony dostałyby `DEAD_RECIPES`, a przepis zniknąłby z ich pickerów.
- Kopia zdjęcia: nowy pomocnik w `core/uploads.py` (np. `copy_image`) przez
  pipeline `save_image` (re-encode, miniatura), wołany przez
  `run_in_threadpool`; **nigdy nie współdziel `photo_path`** między przepisami.
- `register_household_reference_finder` dla `recipes` — przepisy `global` mają
  `household_id=NULL`, więc nie blokują usunięcia rodziny admina (test).
- `ownership_for_create(actor, scope)` dla `global`: bez `household_id`.
- Audyt: akcje `recipe.global_create/update/delete/archive` (konwencja
  `<encja>.<czasownik>`, wpis do `AuditAction`/`AuditEntity`); `AuditService.record`
  nie commituje.
- Oceny: `recipe_ratings` UNIQUE(recipe_id, user_id) — działa; `avg_rating`
  to teraz średnia ze wszystkich rodzin (opisz w 04_API).

Transfer:

- **Import**: dla każdego, kto nie jest ADMIN-em (i dla `scope=user` w ogóle),
  `global` w pliku → `household` (gdy importujący ma rodzinę) albo `private`.
  Przy imporcie instancji `global` zostaje wyłącznie wtedy, gdy zmapowany
  właściciel jest ADMIN-em. Nieznana wartość enuma w pliku → 422
  `TransferValidationError`, nie `ValueError`.
- **Eksport `scope=user`**: do `recipes` dołączane są przepisy `global`, do
  których odwołują się plany/szablony użytkownika (zakres w pliku obcięty do
  `household`, więc po imporcie to kopia importującego); `owned_condition` NIE
  jest rozszerzane. Test: eksport planu z przepisem globalnym → import na
  czystą instancję zachowuje pozycję planu i jej podziały porcji.
- Eksport instancji (`_collect_instance`) zachowuje `global` w całości —
  test round-trip.

## Frontend

- `src/lib/schemas/recipe.ts`: `RECIPE_SCOPES` + `global`; `src/api/recipes.ts`:
  `RecipeScope` z nowego komponentu `RecipeScope` (NIE z `Scope`);
  `queryKeys.ts` — typ filtra z jednego źródła, nie literały.
- `PrzepisEdytorPage.vue`: opcja „Wszyscy” w `<select id="recipe-scope">` tylko
  gdy `auth.isAdmin`; zapis przepisu `global` przez USER-a jest niemożliwy w UI
  (pole nieaktywne, podpowiedź), a backend i tak zwraca 403.
- `PrzepisSzczegolPage.vue`: `canManage` osobno dla `global` (tylko ADMIN) —
  dziś link „Edytuj” widać dla każdego; przycisk „Kopiuj do mojej rodziny”
  (testid `recipe-copy`), przycisk „Archiwizuj”/„Przywróć” dla ADMIN-a.
- `RecipeCard.vue`/`PrzepisyPage.vue`: odznaka zakresu (dziś żadnego wskaźnika;
  nazwy mogą się powtarzać, więc kopia i oryginał wyglądałyby tak samo) i
  filtr „Wszyscy / Rodzina / Prywatne”.
- `lib/texts.ts`: `scopeGlobal`, teksty kopiowania, archiwizacji i odznak —
  po polsku, bez i18n (D3); tokens kolorów, bez hexów.
- Miejsca z literałem `'private'|'household'` dla INNYCH encji (plan tygodnia,
  szablony, cykle) NIE są ruszane — `Scope` zostaje dwuwartościowy.
- `task fe-types` po zmianie OpenAPI; różnica w `generated.ts` ma być
  ograniczona do `RecipeScope`, endpointów copy/archive i parametru filtra.

## Security

- Eskalacja przez transfer (ręcznie edytowany `export.json` z `"scope":"global"`)
  jest zamknięta obcięciem po stronie importu — test negatywny obowiązkowy.
- Wszystkie nowe odmowy to 403 (przepis widoczny), nie 404; obcy PRYWATNY
  przepis nadal 404 (ADR-006 bez zmian).
- `/uploads/*` bez zmian, ale 07_SECURITY §6 dostaje zdanie: autoryzacja zdjęć
  to sesja + allowlista podkatalogów, bez sprawdzenia właściciela przepisu;
  nieodgadywalność ścieżki (UUID) jest jedyną barierą.
- `SKILL-SECREV` na diffie: macierz ról, import, kopiowanie zdjęć.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3.

- **Required**: SKILL-BE, SKILL-FE, SKILL-SEC
- **Recommended**: — (obliczeń nie ruszamy)
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **Macierz uprawnień (08_TESTING §4, krytyczne)** — nowe wiersze: odczyt
  `global` (USER innej rodziny 200; brak sesji 401); tworzenie / edycja treści /
  zdjęcie / zmiana zakresu / usunięcie / archiwizacja `global` (USER 403, ADMIN
  200, zdegradowany były właściciel 403); `scope=global` odrzucone (422) dla dnia
  planu, szablonu dnia/tygodnia, cyklu, konfiguracji tury, generacji i listy;
  `POST /recipes/{id}/copy` (200, kopia niezależna: edycja kopii nie zmienia
  oryginału, usunięcie zdjęcia kopii nie kasuje pliku oryginału).
- **Integracja**: przepis `global` w planie, szablonie i liście zakupów OBCEJ
  rodziny — pozycja się dodaje, wartości odżywcze i lista zakupowa liczą się;
  usunięcie przepisu używanego przez dwie rodziny → 409 z `used_in`; archiwizacja
  używanego przepisu przechodzi, a plan dalej się liczy; obniżenie zakresu przy
  użyciu przez inną rodzinę → 409; usunięcie rodziny admina nie jest blokowane
  przez przepisy `global` (`household_id` NULL).
- **Migracje (integration)**: test DWUSTOPNIOWY — baza na `0016` z kilkoma
  wierszami `recipes`, `COMMIT`, potem `upgrade head` (to odtwarza produkcję);
  `downgrade` do `0016` przechodzi; asercja wartości enuma; test dryfu.
- **Transfer**: round-trip planu z przepisem globalnym na czystą instancję;
  import `"scope":"global"` przez USER-a → obcięte do `household`; import
  instancji z adminem → `global` zachowany; nieznana wartość enuma → 422.
- **Unit**: `RecipeScope` vs `Scope` (OpenAPI: komponent `Scope` nadal dwuwartościowy,
  `task fe-types-check`).
- **vitest**: edytor (opcja „Wszyscy” tylko dla ADMIN-a), szczegół (Edytuj/Usuń
  tylko ADMIN dla `global`, przycisk kopiowania), karta (odznaka).
- **E2E**: spec `recipe-global.spec.ts` (prefiks `E2E przepis-global`,
  `cleanupE2eData` w `beforeAll`/`afterAll`): ADMIN publikuje przepis, USER z
  innej rodziny go widzi, dodaje do planu, kopiuje do rodziny i edytuje kopię.
  Cała suita w dwóch kolejnych przebiegach.

## Acceptance Criteria

1. `task db-heads` = `0018`; `upgrade head` z bazy na `0016` (po commicie) i od
   zera przechodzi; `downgrade` do `0016` przechodzi; typ `entity_scope` ma
   wartości `private, household, global`.
2. ADMIN publikuje przepis `global`; użytkownik z innej rodziny widzi go na liście,
   w wyszukiwarce, w pickerze planu i w szczególe; nie może go edytować, usunąć
   ani zmienić zdjęcia (403).
3. Komponent `Scope` w OpenAPI i `generated.ts` pozostaje dwuwartościowy;
   `RecipeScope` jest trójwartościowy i tylko przepisy go używają.
4. Plan, szablon, cykl i lista zakupów OBCEJ rodziny działają z przepisem
   `global` (wartości odżywcze, skład listy).
5. Kopia przepisu globalnego ma własny plik zdjęcia i własne składniki; zmiana
   kopii nie wpływa na oryginał.
6. Import nie pozwala nie-ADMIN-owi uzyskać przepisu `global`; eksport planu z
   przepisem globalnym nie gubi pozycji.
7. `task check` i `task test-e2e` zielone; macierz 08_TESTING §4 zaktualizowana;
   ADR-006 i dokumenty z Stage 7 zgodne z kodem.

## Out of Scope

- Zakres `global` dla czegokolwiek poza przepisami (plany, szablony, listy,
  spiżarnia — zostają na `private`/`household`).
- Per-przepisowa autoryzacja `/uploads/*` (tylko udokumentowanie stanu).
- Wersjonowanie przepisów globalnych i powiadamianie rodzin o zmianie.
- Komentarze i oceny widoczne międzyrodzinnie poza średnią.
- Wgrywanie przepisów PDF-ów — to B22.

## Expected files/modules

Nowe: `backend/migrations/versions/0017_*.py`, `0018_*.py`,
`frontend/e2e/recipe-global.spec.ts`, testy w `backend/tests/{api,integration,unit}/`.
Zmieniane: `backend/app/core/scope.py`, `backend/app/core/uploads.py`,
`backend/app/modules/recipes/{models,schemas,service,router}.py`,
`backend/app/modules/audit/service.py`, `backend/app/modules/transfer/{serializer,service,importer,schemas}.py`,
`backend/openapi.json`, `frontend/src/api/{recipes,queryKeys,generated}.ts`,
`frontend/src/lib/{texts,schemas/recipe}.ts`,
`frontend/src/pages/przepisy/{PrzepisEdytorPage,PrzepisSzczegolPage,PrzepisyPage}.vue`,
`frontend/src/components/domain/RecipeCard.vue`,
`backend/tests/conftest.py`/`factories.py`, `scripts/seed_demo.py` (jeśli
przepis demo ma pokazywać `global`), dokumenty z Stage 7.

## Implementation Notes

- Dwa podejścia do kolumny `scope` w `Recipe` — wybrane: nadpisanie kolumny
  mixina własnym `ENUM(RecipeScope, name="entity_scope", create_type=False)`.
  Odrzucone: dodanie `GLOBAL` do wspólnego `Scope` (każdy USER mógłby wysłać
  `global` dla listy zakupów; rozszerza ~18 typów TS) oraz osobny typ PG
  (migracja `ALTER COLUMN … USING`, większa i ryzykowniejsza).
- Zmiana `visible_condition` jest per-encja (flaga lub podklasa), bo
  `ScopedQuery` jest współdzielony przez wszystkie moduły ze scope.
- Oceny i `avg_rating` — po zmianie zakresu na `global` średnia mieszka ponad
  rodzinami; to zamierzone, ale UI nie pokazuje, czyje oceny.
- Pamiętaj o `register_household_reference_finder`: dopóki `household_id` jest
  NULL, przepis globalny nie zalicza się do rodziny.

## Cross-Batch Impact

- **B22** (`/pdf-extract`): paczka może zawierać przepisy `scope=global`, ale
  wgrywa je ADMIN; bez B21 B22 generuje wyłącznie `household`/`private`.
- **B18**: niezależny, ale migracje `0017`/`0018` jadą na produkcję tym samym
  deployem (dump → migracja); runbook `deploy/README.md` dostaje zdanie o
  nieodwracalności `ADD VALUE`.
- Każdy przyszły batch dodający encję ze scope używa `Scope` (2 wartości) i NIE
  dziedziczy `global`.

## Implementation checklist

- [x] Baseline: `task check` zielony; liczby `recipes` per `scope`
- [x] Migracje `0017` (enum, `autocommit_block`) i `0018` (CHECK-i)
- [x] `RecipeScope`, kolumna `Recipe.scope`, widoczność per encja
- [x] Kontrole ról (create/edit/photo/scope/delete/archive)
- [x] `POST /recipes/{id}/copy` + `copy_image`
- [x] Archiwizacja ADMIN-a, blokada obniżenia zakresu (409 `used_in`)
- [x] Transfer: obcięcie `global`, dołączanie referencjonowanych, 422 dla nieznanej wartości
- [x] Frontend: edytor, szczegół, karta, filtr, teksty, `task fe-types`
- [x] Macierz uprawnień + testy migracji dwustopniowe + E2E
- [x] Dokumenty z Stage 7, PROGRESS

## Verification checklist

- [x] `task check` zielony; `task test-e2e` zielony dwa razy z rzędu
- [x] `task db-heads` jedna głowa = `0018`; up/down na czystej bazie
- [x] Test dwustopniowy (0016 → commit → head) zielony
- [x] `task fe-types-check` zielony, komponent `Scope` dwuwartościowy
- [x] `/code-review` i `/security-review` na diffie, ustalenia naprawione lub odnotowane
- [x] Jeden commit `batch(21): zakres global dla przepisów` (bez push — repo nie ma remote'a ani upstreamu; właściciel wybrał „tylko commit”)

## Completion notes

**Wykonane.** Wszystkie etapy 0–8. Baseline: `task check` zielony na HEAD (unit 476, int 269,
api 411, vitest 393); liczby `recipes` w bazie dev przed i po: **5 × `private`**. Migracje `0017`
(`ADD VALUE` w `autocommit_block`) i `0018` (CHECK-i na 8 tabelach); `upgrade` 0016→0018 wykonany
realnie na bazie dev z wierszami (kontener `app`, nie z hosta — port 5432 to cudza baza).
`RecipeScope` + `RECIPE_SCOPE_ENUM`, `ScopedQuery(allow_global)` z `assert_can_edit_content`,
`outside_audience_condition`, fabryka `recipe_visibility_query`; `copy`, `archive`, blokada
obniżenia (rejestr `register_recipe_foreign_use_finder`), transfer (obcięcie przy imporcie,
dołączanie przepisów globalnych do eksportu użytkownika, 422 dla nieznanego enuma także w
DRY-RUN), frontend, `task fe-types`, dokumenty Stage 7 (ADR-006 aneks, 02/03/04/07/08, CLAUDE.md).

**Testy (realne).** Końcowy `task check` zielony: patrz PROGRESS (liczby w dzienniku).
Nowe: `tests/api/recipes/test_recipes_global_api.py` (macierz ról, kopia, archiwizacja, audyt),
`…_usage_api.py` (plan/szablon/cykl/lista zakupów obcej rodziny), `tests/integration/recipes/
test_global_scope_db.py` (CHECK-i), `tests/integration/test_transfer_global.py`,
`tests/integration/test_migrations.py` (test DWUSTOPNIOWY — dowiedzione, że pada bez
`autocommit_block`: „unsafe use of new value"), `tests/unit/test_recipe_scope{,_openapi}.py`,
vitest (karta, szczegół, edytor, filtr), E2E `recipe-global.spec.ts`; **`task test-e2e` 20/20 dwa
razy z rzędu**, baza dev po przebiegu czysta.

**Odstępstwa od karty / rozstrzygnięcia.**
1. Archiwizacja = `POST|DELETE /recipes/{id}/archive` (konwencja `/products/{id}/archive`), nie
   `/unarchive`. Dodany też audyt `recipe.unarchive`.
2. `POST /recipes/{id}/copy` zwraca **201** (karta: „200") — tworzy zasób, jak `POST /recipes`.
   Ma limit tempa jak upload zdjęcia (kopia powiela plik na dysku).
3. Zdjęcie przepisu to `POST` (nie `PUT`) — stan istniejący.
4. **Obniżenie z `global` przekazuje przepis ADMIN-owi wykonującemu akcję** (`owner_user_id` i
   `household_id` = jego); „użycie przez inne rodziny" = dni planu/szablony spoza jego grona
   (rodzina dla `household`, tylko on dla `private`). Audyt niesie `owner_before/after`.
5. Import: dla pliku `scope=user` `global` obcinane ZAWSZE (także ADMIN) — wprost z karty;
   kopia instancji zachowuje `global` tylko dla właściciela-ADMIN-a, inaczej przepis wraca do
   rodziny właściciela. Własny przepis `global` ADMIN-a wychodzi w pliku użytkownika jako kopia.
6. Poprawki z `/code-review` (6 ustaleń, wszystkie naprawione): blokada wiersza przy obniżaniu,
   wspólna fabryka `recipe_visibility_query`, `copy_image` zwraca `None` także dla uszkodzonego
   pliku, szybszy `_copy_name`, jedna mapa etykiet zakresu w `texts.ts`, `owner_before/after`.
   `/security-review`: brak ustaleń ≥ 8/10.
7. `data/` i hunki B18 nie weszły do commitu; karty B21/B22 i wpisy D31/D32 (PROGRESS,
   02_DECISIONS, 03_AI_SKILLS) weszły za zgodą właściciela. CLAUDE.md wszedł tylko z blokiem B21.

**Decyzje / pytania.** **D33 (OPEN)** w 02_DECISIONS: czy import `scope=user` przez ADMIN-a ma
zachować `global` (rekomendacja: NIE; B22 emituje paczkę `scope=instance`).

**Follow-upy poza zakresem.** (a) `deploy/README.md` (nieśledzona praca B18) — zdanie o
nieodwracalności `ADD VALUE` dopisane do karty B18, nie do runbooka. (b) `/uploads/*` nadal bez
autoryzacji per przepis (udokumentowane w 07_SECURITY §6). (c) Ponowny import kopii INSTANCJI
dubluje przepisy `global` cudzych adminów (indeks kolizji bierze `select_owned`) — do rozważenia
w B22. (d) Opis `RecipeScope` (docstring) trafia do OpenAPI/`generated.ts` — kosmetyka.
(e) Git: gałąź `master` nie ma upstreamu ani remote'a, więc polecenie `git push` nie zostało
wykonane.
