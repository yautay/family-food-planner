# PROGRESS — status batchy i dziennik programu

Aktualizowany przez agentów wykonujących batche. Status: `[ ]` nierozpoczęty,
`[~]` w toku, `[x]` DONE (Definition of Done z 00_MASTER_PLAN §7 spełnione,
commit wykonany). Kolumna „Blokery" = zależności + decyzje z 02_DECISIONS.

## Statusy

| Batch | Status | Blokery | Commit |
|---|---|---|---|
| 01 PROJECT_SCAFFOLD_AND_DEV_LOOP | [x] | — | `batch(01)` na master (hash wpisać po push) |
| 02 AUTH_AND_ACCOUNTS | [x] | — | `batch(02)` na master (hash wpisać po push) |
| 03 HOUSEHOLDS_AND_SCOPE | [x] | — | `batch(03)` na master (hash wpisać po push) |
| 04 UNITS_AND_CANONICAL_PRODUCTS | [x] | — | `batch(04)` na master (hash wpisać po push) |
| R1 REVIEW_FOUNDATIONS | [x] | — | `batch(R1)` na master (hash wpisać po push) |
| 05 RECIPES_AND_NUTRITION_ENGINE | [x] | — | `batch(05)` na master (hash wpisać po push) |
| 06 GOALS_AND_DAY_PLAN | [ ] | 05 | |
| 07 WEEK_TEMPLATES_AND_CYCLES | [ ] | 06 | |
| R2 REVIEW_PLANNING_CORE | [ ] | 05–07 | |
| 08 PANTRY | [ ] | 04, R2 | |
| 09 RETAIL_PRODUCTS_AND_STORES | [ ] | 04, R2 | |
| 10 SHOPPING_ENGINE | [ ] | 06, 08, 09 | |
| 11 SHOPPING_LISTS_AND_SHARING | [ ] | 10 | |
| R3 REVIEW_SHOPPING | [ ] | 08–11 | |
| 12 PWA_AND_OFFLINE | [ ] | 11, R3 | |
| 13 STATISTICS | [ ] | 06, R3 | |
| 14 IMPORT_EXPORT | [ ] | R3 | |
| 15 PDF_IMPORT_EXTRACTION | [ ] | 05 (zalecane po R3) | |
| 16 PDF_IMPORT_REVIEW_AND_AI | [ ] | 15, 04 | |
| R4 REVIEW_PRE_PRODUCTION | [ ] | 01–16 | |
| 17 PRODUCTION_HARDENING | [ ] | R4 | |
| 18 PRODUCTION_DEPLOYMENT_AND_OPERATIONS | [ ] | 17; **D6, D7** | |

## Dziennik

Wpis po każdym batchu (dopisywany NA GÓRZE sekcji): data, batch, 2–5 zdań:
co weszło + **„rzeczy, o których muszą wiedzieć następne batche"**
(odstępstwa, nowe kontrakty, pułapki). Wpis NIE zastępuje propagacji —
zmiany dotykające przyszłych batchy trzeba wpisać do ich kart
(00_MASTER_PLAN §8); dziennik to indeks, nie schowek.

---

**2026-08-17 — BATCH_05 (RECIPES_AND_NUTRITION_ENGINE)**: jest serce systemu.
Migracje `0006` (recipes/recipe_ingredients/tags/recipe_tags/recipe_ratings +
enumy `entity_scope`, `amount_unit`, `recipe_source` + GIN trigram na
`recipes.name`) i `0007` (idempotentny seed 9 tagów systemowych, w tym
„ulubione"). Czysty silnik `nutrition/{engine,types}.py` (Decimal, property-based,
pokrycie 100%), moduł `recipes/` (CRUD z filtrami, normalizacja składników
przy zapisie, oceny z upsertem, tagi z inline create), `core/uploads.py`
(sniffing+re-encode+miniatury) + auth-gated `GET /uploads/*`. Frontend:
`/przepisy` (grid + chipsy tagów), szczegół z regulacją porcji na żywo,
edytor z ProductPicker/AmountInput, RecipeCard; naprawy U9/U10 z R1.
Warunki R1 domknięte: D15 wdrożone (measure_kind → UNVERIFIED), D16
zaasercjonowane testem. `task check` zielony (3 migrations-check / 170 unit /
78 int / 184 api / 144 vitest / mypy 92 pliki / vue-tsc / ruff / eslint /
prettier / vite build).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Sygnatury silnika i `NutritionValues` są kontraktem** (karta B05,
   Cross-Batch Impact). `ingredient_nutrition` przyjmuje ilość na osi
   WARTOŚCI produktu (`to_basis_amount`); liczby w wyniku to SUMA
   Z DOSTĘPNYCH danych + `complete`/`missing` (braki i UNVERIFIED nigdy nie
   są cichym zerem). Wzór budowy wejść z ORM (przepakowanie `UnitWeight`,
   obsługa rozjechanego `measure_kind` po D15):
   `recipes/service.py::_ingredient_values` i `_build_ingredients`.
2. **Rejestr referencji przepisów**:
   `recipes.service.register_recipe_reference_finder(finder)` — B06 (plan)
   i B07 (szablony) MUSZĄ się zarejestrować, inaczej DELETE przepisu
   w użyciu da 409 bez listy `used_in` (druga linia: FK RESTRICT).
   Rejestr produktów działa: przepisy zgłaszają się do katalogu, DELETE
   produktu użytego w przepisie zwraca nazwę przepisu.
3. **Migracja `0006` utworzyła enumy** `entity_scope`, `amount_unit`,
   `recipe_source` — kolejne tabele ze scope/ilością używają
   `postgresql.ENUM(..., create_type=False)`. Fixture `scoped_notes_table`
   już NIE tworzy/nie kasuje `entity_scope` (typ należy do migracji);
   `test_catalog_seed._rerun_seed` celuje `upgrade 0005` + `stamp head`,
   bo powtórka migracji SCHEMATU na bazie z tym schematem = DuplicateObject.
4. **`recipes.import_job_id` bez FK** — dopina go migracja B15 razem
   z tabelą `import_jobs` (03_DATABASE §5, stan faktyczny).
5. **Upload obrazów ma jeden pipeline**: `core/uploads.py` + serving
   `GET /uploads/{path}` z sesją (poza `/api/v1`). B09 reużywa z własnym
   `subdir` — konkrety wpisane do karty B09. Nowa zmienna konfiguracji:
   `UPLOADS_DIR` (default `data/uploads`); w compose/prod wymaga bind mount
   (B17/B18). Nowe zależności: pillow, python-multipart (runtime);
   hypothesis, pytest-cov (dev).
6. **D15 wdrożone / D16 utrwalone testem** — szczegóły w 02_DECISIONS
   (oba czekają na formalny głos właściciela; testy wskazują, co zmienić
   przy odwrotnym rozstrzygnięciu).
7. **PUT /recipes/{id} wymienia składniki kompletem** (nowe wiersze, id
   pozycji nie są stabilne) — konsumenci nie mogą trzymać referencji do
   `recipe_ingredients.id`. Serce na karcie = tag systemowy „ulubione"
   (przypisanie per przepis, nie per user — uproszczenie z karty B05).
8. **Pułapka FastAPI**: query param typu Decimal deklaruj przez
   `Annotated[Decimal, Query(...)]` — `Field(...)` w Annotated jest
   ignorowany jako query (wzór: `?servings=` w `recipes/router.py`).
9. Kolejna wolna migracja: `0008`. Karty zaktualizowane: B06 (kontrakt
   silnika, rejestr referencji, amount_unit, pułapka Query), B09 (API
   uploadów). E2E `recipe-inline-create.spec.ts` napisany, NIEURUCHOMIONY
   (brak Dockera w tej sesji — dług U15 rośnie o jeden spec, do odhaczenia
   przed R2 razem z `produkty.spec.ts` i `households.spec.ts`).

**2026-08-16 — REVIEW R1 (REVIEW_FOUNDATIONS) — WERDYKT: PASS Z WARUNKAMI**

B05 może startować, o ile domknie ustalenia wpisane do swojej karty (sekcja
„Implementation Notes" → „Ustalenia review R1 do domknięcia w tym batchu").
Audyt objął cały kod od `0c872b4` do `833b4d1` (B01–B04) w jednej sesji:
wzorzec modułu, `ScopedQuery`, sesje/CSRF/rate limit, migracje, katalog
i wartości odżywcze, frontend, kontrakt komend.

**Warunki werdyktu:**

1. **Nie odwracać naprawy `basis_unit`** w `catalog/units.py` — silnik B05
   stoi na rozdzieleniu osi przechowywania (`base_unit`) i osi wartości
   „na 100" (`basis_unit`).
2. B05 wykonuje ustalenia U9, U10 i rozstrzyga w kodzie D15 + D16 (karta B05).
3. **D15 i D16 w 02_DECISIONS są OPEN** — decyzja właściciela najpóźniej
   w trakcie B05; bez odpowiedzi B05 utrzymuje stan faktyczny i asercjonuje
   go testem, żeby wybór był widoczny w kodzie, nie domyślny.
4. Przed R2: uruchomić E2E (`households.spec.ts`, `produkty.spec.ts`) i
   `task secrets-scan` na maszynie z Docker Desktop i wpisać wynik tutaj
   (dług wisi od B03).

**Ustalenia NAPRAWIONE w commicie review:**

- **U1 (blokujące dla B05)** `backend/app/modules/catalog/units.py:191` —
  konwersja jednostki domowej mnożyła ilość przez `grams_per_unit`, ale
  oznaczała wynik osią `base_unit`, czyli dla produktu `measure_kind=piece`
  „sztukami". `to_grams`/`to_basis_amount` mnożyły to po raz drugi przez
  `piece_weight_g`: dla jajka (105 g) „1 opakowanie = 600 g" dawało 63 000 g.
  Sprzeczne z docstringiem tej samej funkcji, z ADR-004 (wartości na 100 g)
  i z dziennikiem B04 pkt 3; niepokryte testem, choć `tests/unit/
  test_product_nutrition.py:153` buduje dokładnie taki produkt. Naprawa: nowa
  czysta funkcja `basis_unit(measure_kind)` (objętość → ml, masa i sztuki → g),
  użyta też przez `nutrition_adapter.nutrition_for` (jedna definicja osi) +
  dwa testy regresyjne. **Silnik B05 dostaje poprawną podstawę obliczeń.**
- **U2** `backend/migrations/versions/0005_seed_product_categories.py:82` —
  `downgrade()` kasował kategorie bez sprawdzenia referencji, więc na bazie
  z JAKIMKOLWIEK produktem kończył się `ForeignKeyViolation` (FK
  `canonical_products.category_id` ma RESTRICT). Odtworzone realnie na db-test.
  03_DATABASE §1 wymaga cyklu up/down/up na kopii REALNEJ bazy, a 09_DEPLOYMENT
  §4 dopuszcza migracje w dół „tylko gdy downgrade przetestowany" — test
  sprawdzał wyłącznie pustą bazę. Naprawa: `DELETE ... AND NOT EXISTS
  (SELECT 1 FROM canonical_products ...)` + test
  `test_downgrade_seedu_przechodzi_na_bazie_z_produktami`.
- **U3** `docker/compose.dev.yml:110` — warunek `[ -d node_modules/vite ]`
  nie odświeżał wolumenu po zmianie zależności (follow-up otwarty od B02).
  Teraz `npm ci` wykonuje się, gdy `package-lock.json` różni się od stempla
  w wolumenie. Logika `sh` przetestowana lokalnie (5 scenariuszy), YAML
  zwalidowany; **w kontenerze NIEURUCHOMIONE — brak Dockera w tej sesji.**
- **U4** `CLAUDE.md` — `task check` w tabeli komend pomijał `fe-build`;
  sekcja §4 („Fundament") kończyła się na B02, więc nie wymieniała
  `core/scope.py`, `core/deletion.py`, `core/schemas.py`, `catalog/units.py`,
  `catalog/nutrition_adapter.py` ani kontraktu `AuditService.record()`;
  akapit o testach mówił o JEDNYM miejscu na nową tabelę, a są DWA
  (`DB_TABLES` + `EXPECTED_TABLES`, plus `EXPECTED_ENUM_TYPES` dla enumów).
- **U5** `07_SECURITY §2` — dokument obiecywał „wykładniczy backoff po 10
  nieudanych", kod ma stałą blokadę 15 min z zerowaniem licznika
  (`core/security.py:153`). Kod ma rację (wystarcza na model zagrożeń §1),
  więc doprecyzowany dokument + wskazanie B17 jako miejsca rewizji parametrów.
- **U6** `07_SECURITY §3` — nieopisany drugi wyjątek CSRF: `POST /auth/login`
  (przed logowaniem nie ma cookie `csrf_token`, z którym można porównać
  nagłówek). Kod ma rację, dokument uzupełniony wraz z granicami ryzyka.
- **U7** `.claude/skills/ffp-{backend,frontend,security,domain-calc}` —
  wszystkie cztery opisywały stan „po B01" (ffp-security twierdził, że
  argon2/slowapi „dokłada B02" i że nagłówki CSP należą do B17, a już są;
  ffp-frontend, że LoginPage jest placeholderem; ffp-domain-calc, że kodu
  obliczeniowego nie ma). Nagłówki `verified` i inwentarze uzgodnione ze
  stanem repo; dopisany rozdział o dwóch osiach jednostek i o adapterze
  wartości. To domyka follow-up B02 pkt 4 (03_AI_SKILLS §8).
- **U8** karta `BATCH_R1` odwoływała się w trzech miejscach do nieistniejącego
  skilla `ffp-framework` — poprawione na cztery realne skille `ffp-*`.

**Ustalenia PRZEKAZANE dalej (follow-up z miejscem docelowym):**

- **U9 → karta B05** `frontend/src/pages/produkty/ProduktFormPage.vue:707`
  + `frontend/src/lib/texts.ts:117` — przeliczniki jednostek renderują się
  zawsze w gramach („1 szklanka = 250 g" dla mleka, mimo że wartość leży na
  osi ml — patrz `scripts/seed_demo.py:181`), a etykieta „Gramów na jednostkę"
  zachęca do wpisania gramów przy produkcie liczonym na 100 ml. R1 tego nie
  ruszał: zmienia zachowanie widoczne dla użytkownika (granica z karty).
- **U10 → karta B05** `frontend/src/components/domain/ProductCreateDrawer.vue:52`
  — ponowne otwarcie drawera nie czyści `measureKind`/`pieceWeight`, więc po
  dodaniu produktu „w sztukach" następny inline create startuje z tą miarą
  i starą wagą sztuki.
- **U11 → karta B05** `backend/scripts/seed_demo.py:288` — seed normalizuje
  etykiety jednostek przez `normalize_unit_label`, a serwis przez
  `canonical_unit_label` (`catalog/service.py:813`), który dodatkowo scala
  „opak." → „opakowanie" i odrzuca zarezerwowane „szt.". Dla dzisiejszych 15
  produktów wynik jest identyczny; to pułapka na rosnący seed.
- **U12 → karta B17** `task check` nie bramkuje świeżości `backend/openapi.json`
  i `frontend/src/api/generated.ts` (follow-up B01 pkt 1). W R1 sprawdzone
  realnie: `task fe-types` dał zerowy diff, więc kontrakt jest zgodny z kodem.
- **U13 → karta B17** `SECRET_KEY` jest wymaganą zmienną konfiguracji, ale
  żaden kod jej nie używa (sesje i CSRF biorą entropię z `secrets`).
  Do decyzji: zostawić jako zarezerwowaną i opisać, albo przestać wymagać.
- **U14 → karta B17** `backend/app/modules/accounts/service.py:178`
  i `backend/app/modules/households/service.py:154` — `ilike(f"%{query}%")`
  bez `autoescape=True`, czyli dokładnie ten błąd, który B04 naprawił
  w katalogu. Wyszukiwarki ADMIN-a, więc niski priorytet.
- **U15 → sesja z Docker Desktop, przed R2** E2E `households.spec.ts`
  i `produkty.spec.ts` nadal NIEURUCHOMIONE, `task secrets-scan` (gitleaks
  w kontenerze) NIEWYKONANY — w tym środowisku nie ma `docker` w PATH.
  Substytut wykonany w R1: `git ls-files` bez `.env`, grep sekretów po
  plikach śledzonych (0 trafień) i statyczna weryfikacja, że wszystkie
  `data-testid` używane w testach E2E istnieją w `frontend/src`.

**Decyzje OPEN dla właściciela (02_DECISIONS):**

- **D15** `backend/app/modules/catalog/service.py:451` — zmiana `measure_kind`
  przez USERA nie unieważnia weryfikacji, a przestawia podstawę wartości
  („na 100 g" ⇄ „na 100 ml"). Rekomendacja: zbijać do UNVERIFIED + audyt.
- **D16** `backend/app/core/scope.py:160` — `visible_condition` daje ADMIN-owi
  `true()` (macierz 08_TESTING §4: ADMIN ma 200 w każdym wierszu), a 04_API §3
  pkt 2 i 07_SECURITY §4 mówią, że ADMIN nie jest wyjątkiem na ścieżkach
  użytkownika — i tak działa `member_profiles` (jest na to test!). Dwa
  dokumenty nadrzędne mówią co innego, więc R1 nie rozstrzyga tego sam.
  Zmiana jest tania dopóki nie ma encji produkcyjnych ze scope, czyli do B05.

**Co sprawdzone i CZYSTE (bez ustaleń):** wzorzec modułu (żaden router nie
dotyka sesji DB — grep po `AsyncSession`/`get_session`/`session.`; brak logiki
w importach krzyżowych), kontrakt błędu 04_API §1 wraz z kodami 401/403/404/
409/422/429, macierz uprawnień 08 §4 per zasób z asertami (anty-IDOR: cudzy
profil i cudza notatka scope'owana → 404; `nutrition` produktu: anonim 401 /
USER 403 / ADMIN 200; D13: USER dostaje 403 z podpowiedzią archiwizacji),
CSRF (mutacja bez nagłówka → 403, także dla anonima przed routingiem), rate
limit (szósta próba w minucie → 429) i blokada konta (10 porażek → neutralne
401), cookies (HttpOnly/SameSite=Lax/Secure w prod, logout usuwa wiersz, TTL
przesuwne odświeża też cookie), argon2id + rehash, brak `Float` w modelach
i schematach, każdy `ForeignKey` z jawnym `ON DELETE` (8/8 w migracjach),
CHECK `scope_requires_household` egzekwowany przez bazę, adapter
`ProductNutrition` jako jedyne wejście obliczeń, zero kopii stanu serwera
w Pinia (jedyny store to sesja), zero wartości hex w komponentach, typy FE
wyłącznie z `generated.ts`.

**Wyniki uruchomień (realne):** `task check` zielony na wejściu (exit 0) i po
naprawach — 3 migrations-check / **146** unit / **65** int / 157 api / 141
vitest / mypy 73 pliki / vue-tsc / ruff / eslint / ruff format 79 plików /
prettier / vite build (przed R1 było 143 unit / 64 int; +3 testy do
`test_units.py` i +1 do `test_catalog_seed.py`). `task test-be` przed
naprawami: 363 testy zielone. `alembic heads` = `0005` (jedna głowa);
pełny cykl `upgrade head → downgrade base → upgrade head` wykonany na db-test
DWA razy: na bazie z produktem ujawnił U2 (`ForeignKeyViolation`), a po
naprawie przechodzi w tym samym scenariuszu i kończy na `0005 (head)`;
`task audit` —
pip-audit „No known vulnerabilities found", `npm audit --audit-level=high`
„found 0 vulnerabilities"; `/security-review` na całości zmian — **zero
ustaleń HIGH/MEDIUM** (39 route'ów przejrzanych po dependency, brak surowego
SQL, brak wycieku PII w schematach odpowiedzi), cztery obserwacje poniżej
progu, z których dwie weszły jako U5 i U13; `/code-review` — 6 ustaleń
(U1, U2, U9, U10, U11 + D15).

**2026-08-16 — BATCH_04 (UNITS_AND_CANONICAL_PRODUCTS)**: jest fundament danych.
Migracje `0004` (5 tabel katalogu + `pg_trgm` + indeks GIN trigram + CHECK-i)
i `0005` (idempotentny seed 14 kategorii z `perishability`), moduł
`app/modules/catalog/` z czystymi `units.py` (konwersje g/ml/szt + jednostki
domowe) i adapterem `ProductNutrition`, `app/core/deletion.py` (kontrakt 409
`used_in`), pełne API produktów/kategorii/przeliczników z wyszukiwarką
trigramową i audytem before/after przy wartościach odżywczych. Frontend:
`/produkty` (lista + szukajka + filtry), formularz produktu (wartości
edytowalne tylko dla ADMIN), `/admin/weryfikacja`, obowiązkowy `ProductPicker`
+ `ProductCreateDrawer`, `AmountInput`, `src/lib/format.ts`. `task db-seed-demo`
przestał być placeholderem (15 produktów, idempotentnie). `task check` zielony
(3 migrations-check / 142 unit / 64 int / 157 api / 141 vitest / mypy 73 pliki /
ruff / eslint / prettier / vite build).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Wartości odżywcze czyta się WYŁĄCZNIE adapterem `ProductNutrition`**
   (`catalog/nutrition_adapter.py`: `nutrition_for`, `measure_for`). Sięgnięcie
   silnika po kolumny `canonical_products` albo po `product_nutrient_values`
   = błąd review (ADR-004). Adapter daje `is_complete`, `has_core_macros`,
   `has_glycemic_index`, `missing` (komunikaty PL) i `digestible_carbs_100`.
2. **Kolumny rdzenia (`kcal_100` … `carbs_100`) są NULLOWALNE** — odstępstwo od
   literalnego 03_DATABASE §3, wymuszone przez inline create USERA
   (dokument zaktualizowany). Brak wartości NIGDY nie jest zerem: konsument
   pokazuje `complete=False` i listę braków.
3. **Każda ilość przechodzi przez `catalog/units.py`**: `normalize_amount(qty,
   unit_label, ProductMeasure) -> NormalizedAmount(amount, unit ∈ g|ml|piece)`,
   `to_grams`, `to_basis_amount`; nieprzeliczalna ilość rzuca
   `UnitConversionError` (AppError → 422) i zapis MUSI paść. Jednostka domowa
   daje ilość na osi bazowej produktu (ml dla VOLUME!), a `to_grams` odmawia
   przeliczenia ml → g.
4. **Blokada usuwania ma punkt wpięcia**: `app/core/deletion.py` (`UsedInRef`,
   `assert_deletable`, `conflict_from_integrity_error`) + rejestr
   `catalog.service.register_product_reference_finder(finder)`, gdzie
   `finder(session, product_id) -> Sequence[UsedInRef]`. Moduł z FK do
   `canonical_products` (B05 przepisy, B08 spiżarnia, B09 retail, B11 listy)
   MUSI się zarejestrować, inaczej 409 wyjdzie bez listy „Używane w:".
5. **Usuwanie produktu kanonicznego to wyłącznie ADMIN (D13)** i regułę
   egzekwuje SERWIS, nie `AdminUser` w routerze — dzięki temu 403 podpowiada
   archiwizację. Ten sam wzorzec warto powtórzyć tam, gdzie 403 ma uczyć.
6. **Nowe akcje audytu**: `product.create`, `product.update`,
   `product.nutrition_update`, `product.verify`, `product.archive`,
   `product.restore`, `product.delete`, `product_unit_weight.*`,
   `product_category.*` (encje `product`, `product_category`).
7. **Frontend — komponenty obowiązkowe już istnieją**: `ProductPicker`
   (props `modelValue`/`label`/`limit`/`disabled`/`debounceMs`, emits
   `update:modelValue` i `selected`), `ProductCreateDrawer`, `AmountInput`
   (`modelValue` to STRING dziesiętny). Ilości formatuje TYLKO
   `src/lib/format.ts` → `formatAmount` (g→kg ≥1000, przecinek PL).
   Nowy picker/własny select w kolejnym batchu = błąd review.
8. **Nowa zmienna konfiguracji**: `CATALOG_SEARCH_SIMILARITY_THRESHOLD` (0.25).
   Kolejna wolna migracja: `0006`. Nowa tabela nadal = wpis w `DB_TABLES`
   (conftest) **i** `EXPECTED_TABLES` (`test_migrations.py`); doszła też stała
   `EXPECTED_ENUM_TYPES` — migracja z enumem dopisuje tam swój typ.
9. **Karty zaktualizowane**: B05 (units/adapter/rejestr referencji + API
   pickera i AmountInput), B08 i B09 (rejestr referencji, kontrakt komponentów,
   `catalog` jako moduł do rozbudowy, nie do zduplikowania).
10. **Follow-upy dla R1**: E2E `produkty.spec.ts` i `households.spec.ts`
    napisane, ale NIEURUCHOMIONE (brak Dockera); `db-seed-demo` bez trybu
    `--reset`; indeks GIN trigram nieużywany przez warunek `similarity >= próg`;
    wciąż otwarty `compose.dev.yml` / `node_modules` z B02.

**2026-08-16 — BATCH_03 (HOUSEHOLDS_AND_SCOPE)**: są rodziny i jest jedno
miejsce egzekwowania widoczności. Migracja `0003` (`households`,
`member_profiles`, `audit_entries`, `users.household_id`), `app/core/scope.py`
(`Scope`, `ScopedMixin`, generyczny `ScopedQuery`) udowodniony pełną macierzą
08 §4 na encji testowej `ScopedNote`, moduł `audit` (`record()` append-only
+ `GET /api/v1/audit` dla ADMIN, audit dopięty wstecznie do operacji B02 na
kontach), `/admin/households` z `set_members`, `/households/my` i CRUD profili.
Frontend: `/ustawienia` z sekcją rodziny i profilami, `/admin/rodziny`,
`authStore.household`, `src/lib/decimal.ts`. `task check` zielony
(3 migrations-check / 92 unit / 36 int / 118 api / 73 vitest / mypy 57 plików /
ruff / eslint / prettier / vite build).

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Żadnych własnych filtrów widoczności** — każda encja współdzielna
   konsumuje `ScopedMixin` + `ScopedQuery` z `app/core/scope.py`
   (`get_or_404`, `select_visible`, `assert_can_manage`,
   `ownership_for_create`). Ręczny filtr scope w serwisie = błąd review.
   Cudza encja to **404, nie 403**. Konkretny przykład użycia wklejony do
   karty B05.
2. **Typ enumowy `entity_scope` jeszcze NIE istnieje w bazie** — B03 stworzył
   sam mechanizm, bez produkcyjnej tabeli. Tworzy go migracja `recipes`
   (B05); każda kolejna tabela ze scope musi wtedy użyć
   `postgresql.ENUM(..., create_type=False)`.
3. **Kontrakt 409 `used_in` ustalony**:
   `details = {"used_in": [{"type", "id", "name"}]}`. Referencje liczy się
   PRZED usunięciem, a `IntegrityError` z commita łapie jako drugą linię
   obrony — inaczej użytkownik dostaje 500 zamiast 409. Obowiązuje każde
   usuwanie od B04 (ADR-012).
4. **`AuditService.record()` NIE commituje** — wpis powstaje w tej samej
   transakcji co operacja. Serwis domenowy trzyma `self._audit =
   AuditService(session)` i robi jeden `commit()`. Nowa akcja = wpis
   w `AuditAction`/`AuditEntity` (konwencja `<encja>.<czasownik>`).
   Decimal w payloadzie serializowany przez `format(value, "f")`, nigdy float.
5. **`app/core/schemas.py` → `DecimalString`** — każde pole NUMERIC
   w odpowiedzi używa tego aliasu (OpenAPI `string` ⇒ `task fe-types`
   generuje `string`). Ograniczenia wejścia jako Annotated, bo mypy odrzuca
   `Field(**dict)`. Po stronie FE parser jest jeden: `src/lib/decimal.ts`.
6. **Nowa tabela = wpis w DWÓCH miejscach testowych**: `DB_TABLES`
   (`tests/conftest.py`, TRUNCATE) **i** `EXPECTED_TABLES`
   (`tests/integration/test_migrations.py` — asercja na dokładny zestaw
   tabel po `upgrade head`). Kolejna wolna migracja: `0004`.
7. **Karty zaktualizowane**: B04 (konkrety audytu, `DecimalString`, prototyp
   409, `src/lib/decimal.ts`) i B05 (gotowy przykład użycia `ScopedQuery`
   + instrukcja tworzenia `entity_scope`).
8. **Follow-up dla R1**: E2E `frontend/e2e/households.spec.ts` jest napisany,
   ale NIE został uruchomiony — sesja domykająca batch nie miała Dockera.
   Do odhaczenia na maszynie z Docker Desktop. Wciąż otwarty także follow-up
   z B02 (`compose.dev.yml` nie odświeża `node_modules`).
9. **Domknięcie B03 zrobiła inna sesja niż implementacja** (checklisty,
   Completion notes, PROGRESS, commit) — notatki w karcie opisują stan kodu,
   nie intencje autora.

**2026-08-16 — BATCH_02 (AUTH_AND_ACCOUNTS)**: aplikacja ma prawdziwe
logowanie. Sesje server-side w PG (cookie `ffp_session` HttpOnly, TTL 30 dni
przesuwne), argon2id z rehashem, CSRF double-submit i nagłówki bezpieczeństwa
jako middleware, rate limit slowapi 5/min/IP na `/auth/login` + blokada konta
(10 porażek / 15 min, stan w `users`), `/admin/users` CRUD, CLI
`task create-admin`. Frontend: authStore (Pinia), guard routera, LoginPage
(vee-validate + zod), AppShell z pełną nawigacją (sidebar + bottom-nav),
`/admin/uzytkownicy`. `task check` zielony (54 unit / 18 int / 55 api /
39 vitest / mypy / vue-tsc / ruff / eslint / prettier / vite build), E2E smoke
login→plan-dnia→logout zielony na compose.

**Co MUSZĄ wiedzieć kolejne batche:**

1. **Autoryzacja ma jedno wejście**: `app/core/deps.py` → `CurrentUser`,
   `AdminUser`, `require_admin`. Nowy moduł ich UŻYWA, nie czyta cookie sam.
   Cookies (nazwy, atrybuty, odświeżanie) — `app/core/cookies.py`.
2. **Każda mutacja wymaga nagłówka `X-CSRF-Token`** — także w testach API
   (`tests/helpers.py`: `login`, `csrf_headers`). Middleware CSRF działa
   PRZED routingiem, więc POST bez tokenu daje 403, a nie 404/405.
   Wyjątki to lista prefiksów `CSRF_EXEMPT_PREFIXES` w
   `app/core/middleware.py` — `/api/v1/public/` jest już wpisany dla B11.
3. **Nowy moduł z tabelami = jedna linia w `backend/app/models.py`**
   (rejestr modeli). Bez tego `Base.metadata` jest niepełna i Alembic nie
   widzi schematu. Kolejna wolna migracja: `0003`.
4. **Testy z bazą**: fixture'y `db_session` (serwisy) i `db_client` (HTTP)
   w `tests/conftest.py`; nową tabelę dopisz do stałej `DB_TABLES`
   (TRUNCATE między testami). Fabryki w `tests/factories.py`. `tests/`
   jest teraz pakietem (`__init__.py`) — inaczej mypy widzi moduł dwa razy.
   Część testów `api` dotyka bazy, więc `task test-api` wymaga db-test.
5. **Schematy ODPOWIEDZI nie walidują emaila** (`str`, nie `EmailStr`) —
   walidacja należy do wejścia, inaczej starszy wiersz wysadza odczyt 500.
   Ta sama reguła obowiązuje przyszłe schematy read-only.
6. **Nowa zależność frontendu wymaga ręcznego odświeżenia node_modules
   w kontenerze**: `docker compose --env-file .env -f docker/compose.dev.yml
   exec frontend npm ci` + restart serwisu. Wolumen nazwany nie aktualizuje
   się sam (`npm ci` w compose odpala się tylko przy pustym katalogu).
7. **Nawigacja i teksty**: pozycje menu w `src/lib/navigation.ts` (jeden
   wpis = sidebar + bottom-nav), teksty wielokrotnego użytku w
   `src/lib/texts.ts`, trasy z placeholderami w `src/router.ts` — batch
   domenowy podmienia `component`, nie dokłada nowego wpisu nawigacji.
8. **Karty zaktualizowane**: B03 (konkrety fundamentu auth), B04 (trasa
   „Produkty" gotowa), B11 (wyjątek CSRF i limiter już istnieją),
   B17 (nagłówki/CSP JUŻ są — batch je przegląda, nie tworzy; dochodzi
   przegląd IP za reverse proxy i parametrów argon2/TTL).
9. **Follow-up dla review R1**: `docker/compose.dev.yml` nie odświeża
   `node_modules` (pkt 6) — poprawka jednej linii, świadomie nie robiona
   w B02 (poza zakresem).

**2026-08-16 — BATCH_01 (PROJECT_SCAFFOLD_AND_DEV_LOOP)**: monorepo stoi.
Backend FastAPI (`create_app()`, `/api/v1/health`, config/db/errors/logging),
Alembic z pustą rewizją `0001`, frontend Vite+Vue3+TS strict+Tailwind 4
z tokens 06_UIUX i shadcn-vue, `docker/compose.dev.yml` (app + frontend + db
+ db-test na tmpfs), `Taskfile.yml`, CLAUDE.md, uzgodnione 4 skille ffp-*.
`task check` zielony (16 unit / 2 int / 5 api / 8 vitest / mypy / vue-tsc /
ruff / eslint / prettier / vite build), E2E smoke `/login` przechodzi.

**Co MUSZĄ wiedzieć kolejne batche:**

1. **DB jest asynchroniczna — nowy ADR-015** (SQLAlchemy async + psycopg 3).
   Serwisy dostają `AsyncSession` z `app.core.db.get_session`, są `async`.
   Na Windows narzędzia hosta (alembic, pytest) wymuszają SelectorEventLoop —
   gotowe w `db.py` i `tests/conftest.py`; natywny `uvicorn` na Windows
   z dostępem do bazy NIE jest wspierany (pętla dev stoi w Dockerze).
2. **Nie ma `app` na poziomie modułu** — `uvicorn app.main:create_app
   --factory`; router nowego modułu rejestruje się w `create_app()`.
3. **Błędy**: rzucaj `AppError`/`NotFoundError`/`ForbiddenError`/
   `ConflictError` z `app/core/errors.py`, nigdy `HTTPException`.
4. **Markery pytest są obowiązkowe** (`pytestmark = pytest.mark.unit|
   integration|api`) — test bez markera nie trafi do żadnego targetu.
   Testy integracyjne jadą na `TEST_DATABASE_URL` (db-test); `conftest`
   podmienia `DATABASE_URL`, żeby downgrade nie tknął bazy dev.
5. **Kontrakt komend**: `Taskfile.yml` + `CLAUDE.md` + skille ffp-* to jeden
   organizm — zmiana nazwy targetu wymaga aktualizacji wszystkich trzech.
   `task check` zawiera dodatkowo `format-check`, `fe-build` i
   `migrations-check` (jedna głowa migracji).
6. **`task fe-types`** generuje `backend/openapi.json` **i**
   `frontend/src/api/generated.ts` — oba commitowane (diff API w Review).
   TypeScript przypięty do ~5.9 przez peer dependency openapi-typescript.
7. **Karty zaktualizowane**: B02 (konkrety fundamentu), B12 (vite-plugin-pwa
   JEST już wpięty — B12 dokłada strategie i ikony PNG), B17 (stage prod
   Dockerfile, health `degraded`, nagłówki/CSP).
8. **D12 rozstrzygnięte tego samego dnia — bez Ansistrano**: wdrożenie
   zostaje na procedurze z 09_DEPLOYMENT §4 (`git pull` → build → backup →
   `alembic upgrade head` → `compose up -d`), B18 opakowuje ją w skrypt.
   Blokery B18 to nadal tylko D6 i D7.

**2026-08-16 — PLAN**: Blueprint utworzony (architektura 01–09, ADR-001–014,
audyt PDF, decyzje D1–D11, karty batchy 01–18 + R1–R4, master prompt).
Zatwierdzone D1–D5; otwarte D6/D7 blokują wyłącznie B18. Pierwszy batch
do zlecenia: **BATCH_01_PROJECT_SCAFFOLD_AND_DEV_LOOP**.
