# BATCH_10 — SHOPPING_ENGINE

Klasa: SHOP · Zależności: BATCH_06 + BATCH_08 + BATCH_09 (bez bramek) ·
Rozmiar: **L** — najcięższa logika programu; sekwencyjnie, NIE równolegle.

## Goal

Po tym batchu użytkownik generuje zakupy z planu: wybiera zakres dat,
jawnie decyduje, czy uwzględnić spiżarnię, dostaje deterministyczny PREVIEW
(agregaty per produkt, tury, opakowania retail z resztkami, odjęcia ze
spiżarni, przełączniki „mam już w domu", niejasności) i po rozstrzygnięciu
niejasności finalizuje generację do list zakupowych per tura. Sercem batcha
jest `modules/shopping/engine.py` — czysta funkcja na `Decimal` (ADR-008).

## Context

Co już istnieje:
- Plan dnia/tygodnia (`plan_meal_items`: przepis LUB produkt luzem,
  `servings`, znormalizowane ilości składników w g/ml) — B05–B07.
- `modules/nutrition/engine.py` jako wzorzec czystego silnika (ADR-008).
- Spiżarnia: `PantryService.get_household_state()` (B08 — sprawdzić
  faktyczną sygnaturę w kodzie i Completion notes B08).
- Retail + sklepy (B09): warianty opakowań per produkt kanoniczny,
  `product_categories.perishability`, `RetailProductCreateDrawer`
  (kontrakt props/emit w Completion notes B09).
- Wzorce frontendu: TanStack Query, Pinia (stan szkicu generacji — 05 §1).

Wymagane lektury przed startem:
- `02_DOMAIN_MODEL.md` §9.1–9.3 (pipeline, tury, opakowania/resztki —
  WIĄŻĄCE) + §8 (spiżarnia: jawne pytanie)
- `03_DATABASE_DESIGN.md` §1, §4, §8 (schemat shopping — WIĄŻĄCY)
- `04_API_DESIGN.md` §2 (`/shopping/*`)
- `docs/adr/ADR-008-czyste-silniki-decimal.md` (zero I/O/ORM/`datetime.now()`)
- `08_TESTING_STRATEGY.md` §2.4–2.7 (KAŻDY punkt = nazwane przypadki
  testowe), §5 (seed demo)
- `06_UIUX_PRINCIPLES.md` §2 (minimum kliknięć), §3 pkt 5

## Stages

1. **DB**: migracja czterech tabel z 03 §8 (kolumny tokenów powstają teraz,
   używa ich B11); up/down/up.
2. **Engine (TDD)**: typy wejścia/wyjścia (dataclassy) + czysty pipeline
   w `modules/shopping/engine.py`; testy jednostkowe WSZYSTKICH kroków
   (08 §2.4–2.7) + property-based + determinizm — zielone bez DB.
3. **Serwis + API**: `ShoppingService` (I/O); round-configs CRUD + seed
   presetu; `/generate`, `/resolve`, `/finalize`.
4. **Frontend — konfiguracja i formularz**: strona Zakupy, tury,
   zakres dat + checkbox spiżarni.
5. **Frontend — preview**: agregaty, tury, resztki, odjęcia spiżarni,
   toggle „mam już w domu", inline create retail, niejasności, finalizacja.
6. **Snapshot + E2E + docs**: snapshoty na seedzie demo, E2E
   generacja→preview→finalizacja, PROGRESS.md, propagacja do B11.

## Database / migrations

Dokładnie schemat z 03_DATABASE §8 (plus `created_at`/`updated_at`):
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

- `+scope-wzorzec` = kolumny z 03 §4 (`owner_user_id`, `household_id`, `scope`).
- `public_token`/`token_revoked` tworzone TERAZ, konsumowane w B11.
- `shopping_generations.params` = PEŁNE wejście generacji (JSONB) —
  odtwarzalność preview i testy regresyjne silnika (03 §8).
- Numer migracji = pierwszy wolny; `down_revision` = `alembic heads`.

## Backend

### Silnik — `backend/app/modules/shopping/engine.py` (CZYSTY, ADR-008)

Wejście: dataclassy (zero ORM/I/O, czas parametrem); `Decimal` end-to-end,
zaokrąglenia tylko na krawędzi serializacji. Pipeline zgodny z 02 §9.1,
każdy krok = czysta funkcja komponowana w `generate_preview(EngineInput) -> PreviewResult`:

1. **plan → porcje → składniki**: pozycje planu z zakresu dat (przepisy
   rozwinięte do składników × `servings`; produkty luzem wprost);
2. **normalizacja**: wszystko do g/ml/szt. (ilości wchodzą znormalizowane
   z B05 — silnik waliduje kompletność);
3. **agregacja per produkt kanoniczny**: suma potrzeb; jednostki mieszane
   sprowadzone do bazowej `measure_kind`;
4. **spiżarnia (opcjonalnie)**: TYLKO gdy `use_pantry=True` (jawne pytanie
   w UI, NIGDY domyślnie); wynik nigdy ujemny; `from_pantry_amount` do preview;
5. **overrides „mam już w domu"**: lista `already_have` z wejścia —
   pozycja zostaje w preview jako oznaczona, nie znika;
6. **podział na tury**: wg konfiguracji (perishability z kategorii; tryby
   `all`/`durable_plus_fresh_window`/`fresh_only`; okna wg `covers_days`/
   `fresh_days`); edge: plan krótszy niż okno tury;
7. **dobór opakowań retail**: `packages_count = ceil(potrzeba/wielkość)`,
   resztka = kupione − potrzeba; wiele wariantów → **najmniejsza resztka,
   remis → mniejsze opakowanie** (08 §2.6); brak retail = pozycja w g/ml
   (dozwolone, 02 §9.3);
8. **preview**: struktura wynikowa + niejasności (`ambiguities`):
   `missing_retail` (podpowiedź, nie bloker), `product_without_category`,
   `plan_item_without_amount` — każda z referencją i wagą (bloker/ostrzeżenie).

**Determinizm**: ten sam `EngineInput` ⇒ identyczny `PreviewResult`
(stabilne sortowania po id/nazwie, żadnych setów bez sortowania).

### Serwis i endpointy

`ShoppingService` (I/O): buduje `EngineInput` z planu, spiżarni (tylko gdy
`use_pantry`) i retail; serializuje wejście do `shopping_generations.params`.

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/shopping/round-configs` | GET, POST | U | konfiguracja tur; GET przy braku konfiguracji **seeduje preset** (patrz niżej) |
| `/api/v1/shopping/round-configs/{id}` | PATCH, DELETE | U | edycja/usunięcie tury; `position` steruje kolejnością |
| `/api/v1/shopping/generate` | POST | U | `{date_from, date_to, use_pantry, round_config_ids?}` → zapis `shopping_generations` (status=`preview`, `params` JSONB) + preview w odpowiedzi; nic więcej nie zapisuje (04 §2) |
| `/api/v1/shopping/generations/{id}` | GET | U | odtworzenie preview z `params` (deterministyczne) |
| `/api/v1/shopping/generations/{id}/resolve` | POST | U | decyzje: toggle `already_have`, wybór wariantu retail, przypisanie utworzonego retail, rozstrzygnięcia niejasności → aktualizacja `params` + przeliczony preview |
| `/api/v1/shopping/generations/{id}/finalize` | POST | U | walidacja: brak nierozwiązanych blokerów → tworzy `shopping_lists` + `shopping_list_items` per tura (label, ilości, opakowania, resztki, `from_pantry_amount`, `already_have`), `expires_at` = +7 dni (D10/ADR-010), status=`final` |
| `/api/v1/shopping/generations/{id}` | DELETE | U | status=`discarded` (soft — historia zostaje, D10) |

**Seed presetu tur** (02 §9.2 — seed danych, NIE hardcode; edytowalny):
przy pierwszym użyciu (brak konfiguracji w scope) utworzyć: „Niedziela" —
`shopping_weekday`=6, `mode=durable_plus_fresh_window`, `covers_days`=7,
`fresh_days`=4; „Środa" — `shopping_weekday`=2, `mode=fresh_only`,
`covers_days`=3. Konwencję `shopping_weekday` (0=poniedziałek, jak
`date.weekday()`) udokumentować w OpenAPI.

## Frontend

- `frontend/src/pages/zakupy/ZakupyPage.vue` (route `/zakupy`):
  - **sekcja „Tury zakupów"**: lista konfiguracji (nazwa, dzień, okno,
    tryb), edycja/dodanie/usunięcie, kolejność;
  - **formularz generacji**: zakres dat (domyślnie najbliższy tydzień planu,
    06 §2) + checkbox **„Uwzględnić stan domowy?" — domyślnie ODZNACZONY,
    użytkownik zawsze decyduje jawnie** (02 §8; nigdy nie zaznaczać
    domyślnie ani nie zapamiętywać odpowiedzi).
- **Preview** (`ZakupyPreview.vue` + podkomponenty):
  - sekcje per tura, w turze pozycje per kategoria; pozycja: label, potrzeba
    (`formatAmount`), opakowania („2 × 400 g"), **`LeftoverBadge`
    „Zostanie: 150 g"** (resztki zawsze wyeksponowane — 02 §9.3);
  - panel „Odjęte ze spiżarni" (tylko gdy `use_pantry`): `from_pantry_amount`
    per pozycja; toggle „mam już w domu" (optimistic, POST `/resolve`);
  - pozycje bez retail: podpowiedź + „Dodaj produkt sklepowy" otwierający
    `RetailProductCreateDrawer` z B09 (prefill nazwą); po `created` →
    `/resolve` z przypisaniem wariantu;
  - panel „Do rozstrzygnięcia": niejasności; blokery blokują przycisk
    „Utwórz listy" z czytelnym powodem; finalizacja → toast + nawigacja
    do list (do B11 placeholder — Implementation Notes pkt 5).
- Pinia: `shoppingDraftStore` — stan szkicu generacji (05 §1);
  dane serwera trzyma TanStack Query.

## Security

- Wszystkie endpointy za sesją + CSRF; scope przez `ScopedQuery` (03 §4);
  cudza generacja → 404; testy anty-IDOR dla generations i lists;
  `params` JSONB bez PII poza id encji; nie logować pełnych payloadów (07 §8).
- Tokeny publiczne: kolumny istnieją, ale ŻADEN endpoint ich nie wystawia
  ani nie generuje (to B11) — test, że odpowiedzi nie zawierają `public_token`.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-CALC
- **Recommended**: SKILL-FE
- **Review**: SKILL-REVIEW

## Tests

Obszary krytyczne 08 §2.4–2.7 — KAŻDY punkt jako nazwane przypadki w `backend/tests/unit/shopping/`:

- **Agregacja (2.4)**: `test_aggregates_same_product_across_recipes_and_days`,
  `test_mixed_units_normalized_before_aggregation`,
  `test_loose_plan_items_included`, `test_multiplied_servings_scale_amounts`.
- **Spiżarnia (2.5)**: `test_pantry_subtracted_only_when_use_pantry_true`,
  `test_pantry_never_negative_result` (spiżarnia > potrzeba ⇒ 0),
  `test_pantry_retail_vs_canonical_items`, `test_pantry_deductions_reported_in_preview`.
- **Opakowania i resztki (2.6)**: `test_ceil_packages_count`,
  `test_leftover_computed_and_exposed`, `test_no_retail_falls_back_to_grams`,
  `test_variant_choice_smallest_leftover`, `test_variant_tie_prefers_smaller_package`.
- **Tury (2.7)**: `test_preset_sunday_wednesday_split`, `test_fresh_vs_durable_assignment`,
  `test_round_day_windows`, `test_plan_shorter_than_round_window`.
- **Property-based (hypothesis)**: suma ilości po agregacji = suma przed;
  odejmowanie spiżarni nigdy poniżej zera; `packages_count × package_size >= potrzeba`.
- **Determinizm**: dwa wywołania silnika na tym samym wejściu ⇒ identyczne wyniki.
- **Snapshot**: preview na seedzie demo (`task db-seed-demo`, 08 §5) jako
  snapshot JSON; zmiana snapshotu = świadoma decyzja w review diffa.
- **Integration**: seed presetu raz (nie duplikuje się); `params` odtwarza
  identyczny preview; finalize tworzy listy per tura z kompletem kolumn;
  finalize z blokerem → 409; migracja up/down/up.
- **API**: kontrakt generate/resolve/finalize; macierz uprawnień 08 §4;
  anty-IDOR; brak `public_token` w odpowiedziach.
- **Frontend**: checkbox spiżarni domyślnie odznaczony; `LeftoverBadge`; bloker dezaktywuje finalizację.
- **E2E**: seed demo → generacja → jawne zaznaczenie spiżarni → preview
  z resztkami i odjęciami → toggle „mam już w domu" → finalizacja →
  listy utworzone per tura.

## Acceptance Criteria

1. Konfiguracja tur: CRUD działa; pierwsze użycie seeduje edytowalny
   preset niedziela/środa zgodny z 02 §9.2.
2. POST `/shopping/generate` zapisuje WYŁĄCZNIE `shopping_generations`
   (status=`preview`, pełne `params`); GET generacji odtwarza identyczny preview.
3. Spiżarnia odejmowana tylko przy jawnym `use_pantry=true`; checkbox
   domyślnie odznaczony; preview pokazuje, co odjęto.
4. Dobór opakowań: ceil, resztka wyeksponowana; wiele wariantów →
   najmniejsza resztka, remis → mniejsze opakowanie; brak retail →
   pozycja w g/ml z podpowiedzią inline create.
5. Podział na tury zgodny z konfiguracją i perishability; plan krótszy
   niż okno tury nie powoduje błędów.
6. Niejasności listowane w preview; blokery uniemożliwiają finalizację
   (409 + czytelny komunikat); finalize tworzy listy per tura.
7. Silnik: czysta funkcja na `Decimal`, deterministyczny; pokrycie
   08 §2.4–2.7 w komplecie + property-based + snapshot na seedzie demo.
8. `task check` zielony; migracja odwracalna, jedna głowa.

## Out of Scope

- Strona listy zakupowej (checkboxy, sortowanie per sklep, druk),
  udostępnianie/tokeny/QR, „przyjmij zakupy do spiżarni" → BATCH_11.
- Offline/PWA dla list → BATCH_12.
- Automatyczne zamienniki składników (02 §9.3 — poza programem);
  nadpisanie perishability per produkt — patrz Implementation Notes pkt 2.

## Expected files/modules

Nowe:
- `backend/app/modules/shopping/{__init__.py,engine.py,models.py,schemas.py,service.py,router.py}`
- `backend/migrations/versions/<pierwszy_wolny>_shopping_tables.py`
- `backend/tests/unit/shopping/test_engine_{aggregation,pantry,packages,rounds,determinism}.py`
- `backend/tests/unit/shopping/test_engine_properties.py` (hypothesis)
  + `snapshots/` (snapshot JSON preview)
- `backend/tests/integration/test_shopping_service.py`, `backend/tests/api/test_shopping_api.py`
- `frontend/src/pages/zakupy/{ZakupyPage.vue,ZakupyPreview.vue,RoundConfigSection.vue}`
- `frontend/src/components/domain/LeftoverBadge.vue` (jeśli nie istnieje)
- `frontend/src/stores/shoppingDraftStore.ts`, `frontend/src/composables/useShopping.ts`
- `frontend/e2e/shopping-generate.spec.ts`

Zmieniane: `backend/app/main.py`, `backend/tests/factories.py`,
`frontend/src/api/{queryKeys.ts,generated.ts}`, router + AppShell
(pozycja „Zakupy"), skrypt seedu demo (dane pod snapshoty engine).

## Implementation Notes

1. **Zacząć od silnika (TDD, bez DB)** — API i UI dopiero na zielonych
   testach jednostkowych; granica engine/service bezwzględna (ADR-008).
2. **Perishability per produkt — ROZSTRZYGNIĘTE na etapie planu
   (2026-08-16)**: 03 §3 ma kolumnę `canonical_products.perishability_override
   ENUM(fresh,durable) NULL` (migracja tej kolumny: jeśli B04 jej nie dodał,
   dodaje ją TEN batch). Silnik dalej przyjmuje perishability jako atrybut
   pozycji wejściowej; serwis rozwiązuje: `override ?? kategoria`.
3. `resolve` modyfikuje `params` i przelicza preview silnikiem — jedna
   ścieżka prawdy; bez osobnego stanu preview w DB.
4. Ilości w JSON jako stringi dziesiętne (04 §1); frontend nie liczy na floatach.
5. Nawigacja po finalizacji: B11 dostarcza `ListaZakupowPage` — tu wystarczy
   placeholder route `/zakupy/listy/:id` (surowa lista pozycji), który
   B11 zastąpi; odnotować w Completion notes.
6. Stabilne sortowanie WSZĘDZIE w silniku (id/nazwa) — warunek determinizmu.
7. Rozmiar L: jeśli batch pęka, granica cięcia = po etapie 3 (silnik+API zielone)
   — zgłosić do review zamiast dowozić UI po łebkach.

## Cross-Batch Impact

- **BATCH_11**: konsumuje `shopping_lists`/`shopping_list_items` w całości
  (`label`, `leftover_amount`, `already_have`, `from_pantry_amount`, kolumny
  tokenów); zastępuje placeholder strony listy; rozszerza blokadę usuwania
  sklepu o `shopping_lists.store_id`. Po batchu zaktualizować kartę B11
  o faktyczny kształt odpowiedzi finalize.
- **BATCH_12**: offline korzysta z `label` — nie zmieniać semantyki kolumny.
- **BATCH_13**: statystyki mogą czytać `params` — utrzymać stabilny kształt.

## Implementation checklist

- [ ] Migracja 4 tabel (03 §8) — up/down/up, jedna głowa
- [ ] Typy wejścia/wyjścia silnika (dataclassy, Decimal) + pipeline:
      agregacja → spiżarnia → overrides → tury → opakowania → preview
- [ ] Testy jednostkowe 08 §2.4–2.7 (nazwane) + hypothesis + determinizm
      + snapshot na seedzie demo
- [ ] `ShoppingService` + round-configs CRUD + seed presetu
- [ ] `/generate`, `/resolve`, `/finalize` + testy int/api + anty-IDOR
- [ ] UI: konfiguracja tur + formularz (checkbox spiżarni odznaczony!)
- [ ] UI: preview (tury, resztki, odjęcia, toggle, inline create retail, niejasności)
- [ ] Placeholder `/zakupy/listy/:id` + E2E generacja→preview→finalizacja
- [ ] PROGRESS.md + aktualizacja karty B11

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `alembic upgrade head` + `downgrade -1` + `upgrade head`; jedna głowa
- [ ] Czystość silnika: `session|datetime.now|os.` nieobecne w engine.py
- [ ] Determinizm i snapshot zielone dwa razy z rzędu
- [ ] Acceptance Criteria 1–8 sprawdzone; odpowiedzi API bez `public_token`
- [ ] Dokumentacja + karty przyszłych batchy zaktualizowane
- [ ] Commit `batch(10): …`, `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
