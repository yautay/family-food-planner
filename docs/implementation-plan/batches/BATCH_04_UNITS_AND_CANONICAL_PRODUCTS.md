# BATCH_04 — UNITS_AND_CANONICAL_PRODUCTS

Klasa: FOUND · Zależności: BATCH_03 · Szacunek rozmiaru: L (największy fundament)

## Goal

Po tym batchu istnieje fundament danych systemu: globalny słownik produktów
kanonicznych z wartościami /100 g i IG, kategorie zakupowe (seed), jednostki
domowe per produkt i konwersje ilości do g/ml/szt. USER dodaje produkty
inline (UNVERIFIED), ADMIN edytuje wartości (audit before/after)
i weryfikuje. Powstają wzorce obowiązkowe dla reszty projektu: `ProductPicker`
z create-in-context, blokada usuwania 409 `used_in` + archiwizacja oraz
adapter `ProductNutrition` — jedyne wejście silnika (B05) do wartości.

## Context

Zastaje: auth (B02), households + `ScopedQuery` (`app/core/scope.py`) +
audit (`audit.service.record`) z B03; AppShell z placeholderem „Produkty";
panele admin (Użytkownicy/Rodziny). Produkty są GLOBALNE (02 §3.1 pkt 3) —
ScopedQuery NIE dotyczy encji katalogu; z B03 bierzemy audit i prototyp
409 used_in (DELETE rodziny).

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` + PROGRESS.md
  (statusy B01–B03; dziennik może korygować tę kartę).
- `docs/architecture/02_DOMAIN_MODEL.md` §4 (Catalog: 4.1–4.3, 4.6, 4.9 —
  WIĄŻĄCE) i §3.1 pkt 3 (globalność słowników).
- ADR-004 (rdzeń + rejestr nutrients + adapter ProductNutrition), ADR-005
  (normalizacja g/ml/szt, przeliczniki własnością produktu), ADR-012
  (blokada usuwania + archiwizacja, bez soft delete).
- `docs/architecture/03_DATABASE_DESIGN.md` §3 (schemat catalog — WIĄŻĄCY;
  tu BEZ stores/retail_products — patrz Out of Scope).
- `docs/implementation-plan/01_PDF_AUDIT.md` §5.5 (kategorie — seed),
  §5.2 (niespójne gramatury — po co product_unit_weights).
- `docs/architecture/04_API_DESIGN.md` §1 (stringi dziesiętne! paginacja,
  `?q=`, 409 `details.used_in`), §2 (products, nutrition, unit-weights).
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §4 (ProductPicker —
  wzorzec OBOWIĄZKOWY, powstaje tu), §5 (vee-validate + zod).
- `docs/architecture/06_UIUX_PRINCIPLES.md` §3 (create-in-context,
  destrukcja bezpieczna), §4 pkt 8 (widok edycji produktu).
- `docs/architecture/08_TESTING_STRATEGY.md` §2.3 (konwersje — obszar
  krytyczny), §4 (wiersz „nutrition produktu").

## Stages

1. **DB + seed**: modele modułu `catalog` (ProductCategory,
   CanonicalProduct, ProductUnitWeight, Nutrient, ProductNutrientValue) +
   migracja schematu + osobna migracja danych: seed kategorii
   z 01_PDF_AUDIT §5.5 (GRZYBY … INNE — pełna lista w §5.5) + wymagane
   z 02 §4.3 (PIECZYWO, SUCHE/STRĄCZKOWE, MAKARONY-RYŻ-KASZE,
   PUSZKI-SŁOIKI) — finalna lista bez duplikatów znaczeniowych (decyzja
   implementującego, uzasadnić); `perishability` fresh: warzywa/owoce/
   nabiał/mięso/pieczywo/grzyby, reszta durable; `position`. Rejestr
   `nutrients` PUSTY. `pg_trgm` w migracji.
2. **Konwersje jednostek**: `catalog/units.py` — czyste funkcje (Decimal,
   zero I/O): (ilość, jednostka) → (amount, unit ∈ g/ml/szt) dla
   jednostek systemowych (g, kg, ml, l, szt., opak.) i domowych (lookup
   w ProductUnitWeight przekazanym jako dane); szt.→g przez
   `piece_weight_g`; wyjątek domenowy gdy nieprzeliczalne. Pełne testy
   unit (§2.3) ZANIM powstanie API.
3. **Adapter ProductNutrition**: dataclass (ADR-004) — jedyne wejście
   silnika do wartości: rdzeń z kolumn + rozszerzenia z rejestru; nikt
   poza adapterem nie czyta tych tabel. `nutrition_for(product)` + flaga
   kompletności (brak makro/IG).
4. **Serwis + blokada usuwania**: CRUD produktów (USER tworzy →
   UNVERIFIED; normalized_name unikat), ADMIN-only: edycja nutrition/IG
   (audit `record` z payload `{before, after}`) i weryfikacja
   (UNVERIFIED→VERIFIED, `verified_at`, `nutrition_source`). Reużywalny
   helper `assert_deletable(entity, used_in)` → 409 `conflict`
   z `details.used_in` (referencje na razie puste — mechanizm i kontrakt
   testowy powstają TU); archiwizacja `is_archived` (znika z pickerów).
   CRUD kategorii (ADMIN) i unit-weights (USER).
5. **API**: routery wg tabeli Backend; szukajka trigram (`?q=` —
   similarity po `name` + prefix po `normalized_name`); filtry:
   kategoria, status, `include_archived=false` domyślnie. Ilości w JSON
   jako stringi dziesiętne (04 §1).
6. **Frontend — strona Produkty** (`/produkty`, widok 8): lista/grid
   z szukajką (debounce na `?q=`), filtry, plakietki; formularz produktu:
   nazwa, kategoria, typ miary + waga sztuki (PIECE), wartości /100 g +
   IG, przeliczniki jednostek domowych (add/edit/delete); nutrition
   edytowalne tylko dla ADMIN; BEZ uploadu zdjęcia (B05). Usuwanie:
   dialog → przy 409 lista „Używane w:" (06 §3.3) + „Archiwizuj zamiast".
7. **ProductPicker + ProductCreateDrawer** (wzorzec obowiązkowy,
   05_FRONTEND §4): command palette z wyszukiwaniem (trigram API); brak
   trafienia ⇒ `+ Dodaj produkt "cebula"` ⇒ drawer z minimalnym
   formularzem ⇒ zapis (UNVERIFIED) ⇒ auto-wybór i powrót do przerwanego
   flow. Komponent samodzielny, bez zależności od strony.
8. **Admin — weryfikacja**: `/admin/weryfikacja` — lista UNVERIFIED
   (najstarsze najpierw), wejście w edycję, akcja „Zweryfikuj" (komplet
   wartości + `nutrition_source`).
9. **Testy, fe-types, produkty demo w `db-seed-demo` (~15 — 08 §5), living docs, PROGRESS, commit `batch(04): ...`.**

## Database / migrations

Tabele DOKŁADNIE wg 03_DATABASE §3 (kolumny, typy NUMERIC i CHECK-i
z dokumentu, nie z pamięci): `product_categories`, `canonical_products`,
`product_unit_weights`, `nutrients` (seed pusty — MVP, ADR-004),
`product_nutrient_values`. BEZ `stores`, `store_category_order`,
`retail_products` (→ B09).

- Kluczowe reguły: `normalized_name` UNIQUE; `piece_weight_g` wymagane
  gdy `measure_kind=piece`; `glycemic_index` CHECK 0..110;
  `perishability_override` NULL-owalne (dopisane do 03 §3 2026-08-16 —
  konsument: silnik zakupowy B10, w UI B04 wystarczy pole w formularzu);
  UNIQUE(product_id, unit_label) i UNIQUE(product_id, nutrient_code).
- Indeksy: GIN trigram na `name` (`CREATE EXTENSION IF NOT EXISTS
  pg_trgm` w migracji).
- Migracja danych (seed) ODDZIELNA od schematu, idempotentna (03 §1);
  downgrade seedu = usunięcie po nazwach.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/products` | GET, POST | USER | lista: `?q=` trigram, `category_id`, `verification_status`, `include_archived`, paginacja; POST → UNVERIFIED |
| `/api/v1/products/{id}` | GET, PATCH, DELETE | USER (PATCH pól opisowych), DELETE wg reguł | 409 `used_in` gdy użyty; DELETE tylko właścicielskie sensy globalne — patrz Notes |
| `/api/v1/products/{id}/nutrition` | PUT | ADMIN | wartości /100 + IG + nutrition_source → audit before/after |
| `/api/v1/products/{id}/verify` | POST | ADMIN | UNVERIFIED→VERIFIED (komplet wartości wymagany) |
| `/api/v1/products/{id}/archive` | POST, DELETE | USER/ADMIN | archiwizacja / przywrócenie |
| `/api/v1/products/{id}/unit-weights` (+`/{uwId}`) | GET, POST, PATCH, DELETE | USER | przeliczniki jednostek domowych |
| `/api/v1/categories` | GET, POST, PATCH, DELETE | GET: USER; mutacje: ADMIN | słownik kategorii; DELETE z produktami → 409 used_in |

- Serwis egzekwuje: unikat `normalized_name` (409 z podpowiedzią
  istniejącego produktu — ważne dla inline create), PIECE ⇒
  `piece_weight_g` wymagane, IG 0..110, wartości nieujemne.
- `units.py` i adapter — czyste (bez I/O), importowalne przez `nutrition`
  (B05) i `importer` (B15).
- Audit: `product.created` (kto — istotne dla UNVERIFIED),
  `product.nutrition_updated` (before/after), `product.verified`,
  `product.archived`, `category.*`.

## Frontend

- `ProduktyPage.vue` — lista + szukajka + filtry + puste stany („Dodaj
  pierwszy produkt"); plakietka weryfikacji; archiwalne ukryte
  (przełącznik).
- `ProduktFormPage.vue` (`/produkty/nowy`, `/produkty/:id/edytuj`) — zod
  schema w `src/lib/schemas/product.ts` (stringi dziesiętne, przecinek
  PL), sekcje unit-weights i nutrition (ADMIN edytowalna, USER readonly);
  akcje: zapisz, archiwizuj, usuń (dialog 409 → lista używane-w).
- `ProductPicker.vue` + `ProductCreateDrawer.vue` — wzorzec 05 §4; emit
  `selected(product)`; obsługa klawiatury, `data-testid` dla E2E.
- `AmountInput.vue` — ilość + jednostka, walidacja dziesiętna
  z przecinkiem (tu: unit-weights; konsumowany szeroko od B05).
- `src/lib/format.ts` — `formatAmount` (g→kg ≥1000, przecinek PL; 05 §7)
  — jedyne miejsce formatowania ilości.
- `AdminWeryfikacjaPage.vue` (`/admin/weryfikacja`).
- Query keys: `products.*`, `categories`, `admin.unverified`; mutacje
  z invalidateQueries.

## Security

- Uprawnienia nutrition: `/nutrition` i `/verify` — wyłącznie ADMIN
  (macierz 08 §4: USER/właściciel → 403); pozostały CRUD produktów dla
  USER (słownik globalny, 02 §3.1).
- Każda edycja wartości i weryfikacja → wpis audit before/after
  (rozliczalność danych, na których liczy silnik).
- Ilości jako stringi dziesiętne parsowane do Decimal — float odrzucany
  na granicy API (zakaz z CLAUDE.md).
- Trigram parametryzowany przez SQLAlchemy (bez interpolacji SQL).
- Wszystkie mutacje pod CSRF; brak nowych endpointów publicznych.

## Tests

- **Unit — konwersje (08 §2.3, obszar krytyczny, blisko 100%)**: kg→g,
  l→ml, szt→g przez piece_weight_g, opak./łyżka/garść przez unit_weights;
  brak przelicznika → wyjątek (odmowa zapisu); Decimal bez utraty
  precyzji (`"0.3"×105 g`); brzegowe (0, ujemne → błąd); formatAmount
  (vitest): 999 g → „999 g", 1500 g → „1,5 kg".
- **Unit — ProductNutrition**: rdzeń z kolumn, rozszerzenia z rejestru,
  flagi kompletności (brak IG / brak makra).
- **Integration**: unikat normalized_name (warianty spacji/case),
  CASCADE unit_weights/nutrient_values, RESTRICT kategorii z produktami,
  seed idempotentny, trigram „cebul" → „Cebula".
- **API**: USER tworzy → 201 UNVERIFIED + audit `product.created`;
  PUT nutrition: anonim 401 / USER 403 / ADMIN 200 + audit before/after
  (asercja payloadu); verify bez kompletu wartości → 422; DELETE
  nieużytego → 204, kontrakt 409 `details.used_in` (symulowany konsument
  testowy — mechanizm gotowy na B05); archiwizacja ukrywa z list
  i pickera; walidacje: IG 111 → 422, PIECE bez piece_weight_g → 422,
  float w JSON → 422; unit-weights duplikat (product, label) → 409.
- **Frontend (vitest)**: ProductPicker — wyszukiwanie (mock API), wybór
  klawiaturą, brak wyniku → „+ Dodaj" → drawer → emit `selected`;
  walidacja zod formularza (przecinek dziesiętny, zakres IG).
- **E2E**: login → Produkty → utworzenie produktu → plakietka UNVERIFIED
  → admin weryfikuje na `/admin/weryfikacja` → plakietka znika.

## Acceptance Criteria

1. Po migracji istnieje słownik kategorii (seed §5.5 + rozszerzenia)
   z perishability; rejestr nutrients pusty.
2. USER dodaje produkt (formularz i ProductPicker-drawer) → UNVERIFIED;
   duplikat znormalizowanej nazwy → czytelny 409.
3. ADMIN edytuje wartości /100 g + IG i weryfikuje; w audit wpis
   before/after (sprawdzalny na `/api/v1/audit`).
4. USER nie może edytować wartości odżywczych (403 + UI readonly).
5. Szukajka toleruje literówki (trigram); archiwalne domyślnie ukryte.
6. DELETE nieużytego działa; kontrakt 409 `used_in` pokryty testem;
   archiwizacja odwracalna.
7. CRUD przeliczników działa; zapis ilości nieprzeliczalnej odrzucany.
8. ProductPicker: pełny cykl create-in-context bez opuszczenia flow.
9. `/admin/weryfikacja` pokazuje kolejkę UNVERIFIED.
10. `task check` zielony; migracje odwracalne (schemat i seed).

## Out of Scope

- `stores`, `store_category_order`, `retail_products` (03 §3) → BATCH_09.
- Upload zdjęcia produktu → BATCH_05 (tam infrastruktura uploadów).
- Silnik nutrition (obliczenia porcji/posiłków) → BATCH_05.
- Realne referencje `used_in` z przepisów/planów → B05+ (mechanizm
  i kontrakt powstają tu).
- Uczenie przeliczników z próbek importu (mediana) → B15/16; tu ręczny CRUD.
- Ostrzeżenie „liczone z produktów UNVERIFIED" w widokach → B05/06.
- Mikroelementy (wpisy w nutrients) — świadomie puste w MVP (ADR-004).

## Expected files/modules

- `backend/app/modules/catalog/{models,schemas,service,router,units.py,
  nutrition_adapter.py}` (nazwa pliku adaptera — decyzja implementującego)
- `backend/app/core/deletion.py` (helper 409 used_in) LUB w
  catalog/service z re-eksportem — uzasadnić wybór
- `backend/migrations/versions/<pierwszy-wolny>_catalog.py` +
  `<kolejny>_seed_categories.py`
- `backend/tests/unit/test_units.py`, `test_product_nutrition.py`;
  `tests/integration/test_catalog*`; `tests/api/test_products*`,
  `test_categories*`; `tests/factories.py` (Product/CategoryFactory)
- `frontend/src/pages/produkty/{ProduktyPage,ProduktFormPage}.vue`,
  `src/pages/admin/AdminWeryfikacjaPage.vue`, `src/components/domain/
  {ProductPicker,ProductCreateDrawer,AmountInput}.vue`,
  `src/lib/{format.ts,schemas/product.ts}`, `src/api/{queryKeys.ts,
  generated.ts}`, router, nawigacja (Produkty aktywne, Admin: Weryfikacja)
- `Taskfile.yml` (`db-seed-demo` — produkty demo)
- `docs/implementation-plan/PROGRESS.md`

## Implementation Notes

- Kolejność twarda: migracje → units.py z testami → adapter → serwis →
  API → FE strona → ProductPicker → admin. Konwersje przed API (API ich
  używa przy walidacji unit-weights).
- DELETE produktu globalnego: kto może (twórca-USER gdy nieużyty? ADMIN
  zawsze gdy nieużyty?) — 02 §4.6 mówi tylko o referencjach; decyzja
  implementującego, uzasadnić w Completion notes.
- Seed: rozstrzygnąć nakładanie „ZBOŻOWE" vs „PIECZYWO"/„MAKARONY-RYŻ-
  KASZE" — udokumentować finalny słownik.
- Trigram: próg similarity dobrać empirycznie (start 0.25), w configu.
- `normalized_name` liczone jedną funkcją normalize (trim, zbicie spacji,
  lowercase) — reużyje jej importer B15/16.
- ProductPicker: emit/props pod konsumentów B05/B08/B09; drawer przyjmuje
  prefill nazwy.
- 409 used_in: struktura `details.used_in = [{type, id, name}]` — ustalić
  TERAZ (kontrakt dla UI i wszystkich przyszłych encji).
- Ilości w JSON jako stringi dziesiętne — pydantic: Decimal + serializacja
  str; FE nie parsuje do Number tam, gdzie się liczy.

## Cross-Batch Impact

- **B05**: RecipeIngredient używa `catalog/units.py` i ProductPickera;
  silnik nutrition czyta WYŁĄCZNIE przez adapter ProductNutrition; realne
  `used_in` (przepisy) dopina się do helpera 409; upload zdjęć (B05)
  obejmie też produkty.
- **B05–B11**: ProductPicker (create-in-context) i kontrakt 409/used_in
  obowiązują każdy picker i każde usuwanie (06 §3). **B08/B09**:
  pantry_items i retail_products → FK RESTRICT do canonical.
- **B10**: perishability kategorii zasila tury; nadpisanie per produkt
  (02 §9.2) nie ma kolumny w 03 §3 — doda ją B10, jeśli potrzebna.
- **B15/16**: importer używa normalize(), trigramu do sugestii mapowań,
  zasila product_unit_weights próbkami (mediana).
- Po zakończeniu: dopisać do kart B05/B08/B09 faktyczne API ProductPicker
  (props/emits) i sygnaturę helpera used_in.

## Implementation checklist

- [ ] Migracja schematu catalog (5 tabel + pg_trgm + indeksy)
- [ ] Migracja seed kategorii (idempotentna, perishability, odwracalna)
- [ ] units.py: konwersje czyste + komplet testów unit (§2.3)
- [ ] Adapter ProductNutrition + testy kompletności
- [ ] Serwis: CRUD, normalized_name, walidacje PIECE/IG, archiwizacja
- [ ] Helper 409 used_in (kontrakt details ustalony)
- [ ] Nutrition PUT (ADMIN, audit before/after) + verify
- [ ] API products/categories/unit-weights + trigram
- [ ] FE: ProduktyPage, ProduktFormPage, ProductPicker +
      ProductCreateDrawer, AmountInput + formatAmount, /admin/weryfikacja
- [ ] db-seed-demo (~15 produktów), fe-types, query keys, nawigacja
- [ ] Testy int/api/fe + E2E (create → verify)
- [ ] PROGRESS.md + propagacja do B05/B08/B09

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `alembic heads` = 1; upgrade → downgrade → upgrade OK (obie migracje)
- [ ] Testy konwersji: 100% ścieżek units.py (raport realny)
- [ ] Macierz uprawnień nutrition (401/403/200) pokryta testami API
- [ ] Wpisy audit before/after asercjonowane
- [ ] ProductPicker vitest zielony; E2E create→verify zielony
- [ ] Acceptance Criteria 1–10 potwierdzone
- [ ] Living docs + karty B05/B08/B09 zaktualizowane;
      commit `batch(04): ...`, status czysty

## Completion notes

(wypełnia agent wykonujący)
