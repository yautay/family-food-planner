# BATCH_07 — WEEK_TEMPLATES_AND_CYCLES

Klasa: CORE · Zależności: BATCH_06 (plan dnia) · Rozmiar: **M/L**

## Goal

Po tym batchu użytkownik buduje cały tydzień szybko: widok tygodnia
(siatka dni × posiłki), kopiowanie dnia i bloków N dni (preset 2+2+2),
przenoszenie dań między dniami (drag&drop + alternatywa przyciskowa),
szablony dnia/tygodnia tworzone z istniejącego planu, cykle tygodni A→B→C
stosowane na zakres dat oraz „użyj ponownie" z historii planów. Domyka to
rdzeń planowania (przed R2) i realizuje model użycia z listu dietetyczki
(01_PDF_AUDIT §6).

## Context

Batch zastaje po B06 (stan faktyczny sprawdź w `PROGRESS.md`):

- `modules/planning/` — plan_days/plan_meals/plan_meal_items/
  plan_item_servings, serwisy agregatów (silnik B05), `/plan/days?from=&to=`,
  `/plan/copy` (`what: day|meal`, głęboka kopia, dopisywanie na zajętą datę).
- `modules/recipes/` — CRUD + blokada usuwania z listą `used_in`
  (FK plan_meal_items już liczone od B06).
- Frontend: `PlanDniaPage`, `MealCard`, `RecipePicker`, charts
  `NutritionBar`/`DonutChart`; routing `/tydzien/:weekStart?` zarezerwowany
  (05_FRONTEND §3), strona jeszcze nie istnieje.
- Brak: tabel szablonów/cykli, widoku tygodnia, `BarChart`, kopiowania bloku.

**Faktyczne kształty z B06, na których buduje ten batch** (nie zgaduj ich,
sprawdź w kodzie — to jest kontrakt payloadu szablonów):

- `PlanMeal`: `name`, `position`, `kcal_target NUMERIC(6,0) NULL`.
  `PlanMealItem`: `recipe_id` XOR `product_id`, `amount NUMERIC(10,3) NULL`
  + `amount_unit ENUM(g,ml,piece) NULL` (WYMAGANE razem dla produktu luzem,
  ZABRONIONE dla przepisu — CHECK `product_requires_amount`),
  `servings NUMERIC(6,2)`, `position`. `PlanItemServing`:
  `(member_profile_id, multiplier NUMERIC(4,2))`, suma = `servings` pozycji.
  Payload JSONB szablonu odwzorowuje dokładnie te pola.
- **`PlanningService.copy(user, payload)`** przyjmuje
  `PlanCopyRequest{what: "day"|"meal", source_date|source_meal_id,
  target_dates[]}` i zwraca `list[DayView]`. Kopiowanie bloku N dni (B07) da
  się złożyć z tej metody — nie pisz drugiego mechanizmu kopiowania.
- **Reguła rozstrzygania dnia dla daty**: najpierw WŁASNY dzień użytkownika,
  potem widoczny dzień rodzinny (`PlanningService._resolve_day`). Widok
  tygodnia i instancjacja szablonu MUSZĄ używać tej samej reguły, inaczej
  ta sama data znaczyłaby co innego w dwóch miejscach.
- **Rejestr referencji przepisów jest już wpięty** przez planning
  (`_plans_using_recipe`) — B07 dokłada WŁASNY finder dla payloadów JSONB
  szablonów, nie modyfikuje istniejącego.
- Wartości pozycji = `wartości jednej porcji x servings` również dla produktu
  luzem (rozstrzygnięcie B06, 02_DOMAIN §13.3) — szablon musi kopiować
  `servings` razem z ilością.
- Wspólny kontrakt odpowiedzi: `NutritionRead` i `nutrition_read()` mieszkają
  w `app/modules/nutrition/schemas.py` (przeniesione z recipes w B06).
- Frontend ma gotowe `src/lib/dates.ts` (`addDays`, `startOfWeek`,
  `weekDayLabel`, `isoDate`) — siatka tygodnia liczy daty tym modułem,
  nie własnym kodem.

Konwencje potwierdzone w review R1 (te same, co dla B06 — powtórzone, bo karta
musi być samowystarczalna):

- Tabele ze scope używają `ScopedMixin` + `postgresql.ENUM(..., name=
  "entity_scope", create_type=False)` — typ tworzy migracja `recipes` (B05).
- **Nowa tabela = wpis w `DB_TABLES` (conftest) I w `EXPECTED_TABLES`
  (`tests/integration/test_migrations.py`)**; nowy enum → `EXPECTED_ENUM_TYPES`.
- Pola NUMERIC w odpowiedziach: `DecimalString` (`app/core/schemas.py`).
- Referencje z payloadów JSONB liczy się przez rejestr z `catalog`/`recipes`
  (kontrakt `UsedInRef` w `app/core/deletion.py`), a `IntegrityError` z commita
  zostaje drugą linią obrony — inaczej użytkownik dostanie 500 zamiast 409.

Wymagane lektury przed startem:

- `00_MASTER_PLAN.md` §6–8 · `02_DOMAIN_MODEL.md` §7 (szablony = zamrożona
  kopia, instancjacja bez live-sync; WeekCycle; historia)
- `03_DATABASE_DESIGN.md` §1, §4, §6 — WIĄŻĄCE: `day_templates`/
  `week_templates` z **JSONB payload**, `week_cycles` z `template_ids BIGINT[]`
- **ADR-012** — zliczanie referencji w payloadach JSONB (indeks GIN + test!)
- `04_API_DESIGN.md` §1–3 (`/templates/*`, `/cycles`, `/plan/copy`)
- `06_UIUX_PRINCIPLES.md` §2 (drag&drop tylko gdzie szybszy, ZAWSZE
  z alternatywą przyciskową), §4 widok 4 · ADR-013 (`BarChart`)
- `01_PDF_AUDIT.md` §6 (model 2+2+2, dzień warzywny) · `08_TESTING` §2, §3.2, §4

## Stages

1. **DB**: migracja `day_templates`/`week_templates`/`week_cycles` + indeksy
   GIN na payload; up/down/up zielone.
2. **Backend szablony**: schemat payloadu (Pydantic), tworzenie z planu /
   od zera, instancjacja (kopia do planu), CRUD.
3. **Backend cykle + blok**: `week_cycles` CRUD + apply na zakres dat;
   `/plan/copy what=block` (powiel blok, preset 2+2+2).
4. **Blokada usuwania**: rozszerzenie zliczania referencji recipes/products
   o payloady JSONB szablonów (ADR-012) + testy.
5. **Frontend**: `BarChart` (stacked), `PlanTygodniaPage` (widok 4) z DnD
   i wszystkimi akcjami, dialogi szablonów/cykli/historii.
6. **Testy int/api/fe + E2E** (tydzień przez szablon+cykl) + docs/PROGRESS.

## Database / migrations

Wg `03_DATABASE_DESIGN.md` §6 — bez odstępstw:

- `day_templates` (wzorzec scope + `name`, `payload JSONB`),
  `week_templates` (j.w.), `week_cycles` (wzorzec scope + `name`,
  `template_ids BIGINT[]`, `start_date DATE NULL`).
- Szablon = **zamrożona kopia struktury bez dat**; edycja tylko przez
  nadpisanie całego payloadu (03_DB §6). Kontrakt payloadu (Pydantic,
  wersjonowany polem `v: 1`):
  - day: `{v, title?, meals: [{name, kcal_target?, position, items: [
    {recipe_id?|product_id?, amount?, amount_unit?, servings,
    servings_split?: [{member_profile_id, multiplier}]}]}]}`
  - week: `{v, days: [{offset: 0..6, day: <payload dnia>}]}`
- **Indeksy GIN** (ADR-012): `day_templates USING GIN (payload jsonb_path_ops)`
  i analogicznie `week_templates` — pod zapytania zliczające referencje
  `recipe_id`/`product_id` w payloadach.
- `template_ids` bez FK (array) — spójność pilnowana serwisem: usunięcie
  `week_template` użytego w cyklu ⇒ 409 z nazwą cyklu w `used_in`.
- Numer migracji = pierwszy wolny; downgrade usuwa tabele i indeksy.

## Backend

| Ścieżka (`/api/v1`) | Metoda | Rola | Uwagi |
|---|---|---|---|
| `/templates/days` | GET/POST | U | POST: payload wprost LUB `{from_date}` (zbuduj z dnia planu) |
| `/templates/days/{id}` | GET/PUT/DELETE | U | PUT = nadpisanie całego payloadu; DELETE wg macierzy scope |
| `/templates/days/{id}/instantiate` | POST | U | `{dates: [...]}` → kopia do planu (dopisywanie jak w `/plan/copy`) |
| `/templates/weeks` | GET/POST | U | POST: payload LUB `{from_week_start}` (zbuduj z 7 dni planu) |
| `/templates/weeks/{id}` | GET/PUT/DELETE | U | j.w. |
| `/templates/weeks/{id}/instantiate` | POST | U | `{week_start}` (poniedziałek) → 7 dni do planu |
| `/cycles` | GET/POST | U | `name`, `template_ids[]` (kolejność = rotacja A→B→C), `start_date?` |
| `/cycles/{id}` | PUT/DELETE | U | |
| `/cycles/{id}/apply` | POST | U | `{date_from, date_to}` → instancjacje kolejnych szablonów rotacyjnie |
| `/plan/copy` | POST | U | rozszerzenie: `what: "block"` — `{source_from, source_days: N, repeat_each: K, target_start}`; preset 2+2+2 = 3 dni × repeat_each 2 |

Serwisy i reguły:

- **Instancjacja = kopia bez live-sync** (02 §7): tworzy zwykłe wiersze
  plan_days/meals/items/servings z payloadu; późniejsza edycja szablonu nie
  zmienia planu i odwrotnie. Payload trzyma `recipe_id`/`product_id` jako
  referencje do słowników (wartości odżywcze ZAWSZE liczone na żywo —
  niezmiennik 02 §13.2; „zamrożona" jest struktura, nie liczby).
- Walidacja przy instancjacji: martwe `recipe_id`/`product_id` (zarchiwizowane
  dopuszczone z ostrzeżeniem w odpowiedzi; nieistniejące ⇒ 422 z listą) —
  możliwe tylko przy imporcie transferu, ale zabezpieczyć.
- Apply cyklu: tygodnie od `date_from` (wyrównanie do poniedziałku —
  niedopasowany `date_from` ⇒ 422), rotacja `template_ids` od pozycji
  wynikającej z `start_date` cyklu (NULL ⇒ od pierwszego); zakres niepełnych
  tygodni ⇒ instancjuje tylko dni mieszczące się w zakresie.
- Powiel blok: kopiuje `source_days` kolejnych dni od `source_from`, każdy
  powtórzony `repeat_each` razy sekwencyjnie od `target_start`
  (d1,d1,d2,d2,d3,d3 dla 3×2 — model 2+2+2 z 01_PDF_AUDIT §6).
- **ADR-012**: `recipes/service.delete` i `catalog/service.delete` liczą
  dodatkowo wystąpienia id w payloadach szablonów (zapytanie JSONB po GIN,
  np. `payload @> '{"meals":[{"items":[{"recipe_id": X}]}]}'` lub
  `jsonb_path_exists`); >0 ⇒ 409 z nazwami szablonów w `details.used_in`.
- Historia = po prostu stare `plan_days`; „użyj ponownie" nie ma osobnego
  endpointu — to `/plan/copy` z przeszłą datą źródłową.

## Frontend

- `src/components/charts/BarChart.vue` (ADR-013): stacked SVG, słupki kcal
  per dzień tygodnia + linia celu; tokens 06_UIUX, `role="img"` + aria-label.
- `pages/tydzien/PlanTygodniaPage.vue` (widok 4, routing `/tydzien/:weekStart?`):
  - siatka 7 dni × posiłki (kolumna = dzień: data, suma kcal/cel; karty
    posiłków z miniaturami pozycji); dane z `GET /plan/days?from=&to=`;
  - **drag&drop** posiłku między dniami (przeniesienie = copy meal + delete
    źródła w jednej mutacji) — implementacja lekka (pointer events lub
    HTML5 DnD, decyzja implementującego); **alternatywa przyciskowa
    obowiązkowa**: menu ⋮ posiłku → „Przenieś do dnia…" (06 §2, mobile);
  - pasek akcji: Kopiuj dzień → daty; **Powiel blok** (dialog: od dnia,
    ile dni, powtórzenia; preset „2+2+2" jednym klikiem); Zapisz jako
    szablon (dnia — z wybranego dnia / tygodnia — z widocznego tygodnia);
    Zastosuj szablon (picker szablonów z inline create niepotrzebnym —
    szablon powstaje z planu); Zastosuj cykl (wybór cyklu + zakres dat);
    **Użyj ponownie** (kalendarz/lista dni z przeszłości → kopiuj na nowe daty);
  - `BarChart` tygodnia pod siatką; nawigacja tydzień ±1 / bieżący.
- Dialogi: `TemplateSaveDialog`, `TemplateApplyDialog`, `CycleEditorDialog`
  (lista szablonów w kolejności, drag lub strzałki), `BlockCopyDialog`,
  `ReuseHistoryDialog` — `components/domain/planning/`.
- `queryKeys` += `templates`, `cycles`; mutacje inwalidują `planDays`
  dotkniętego zakresu dat.

## Security

- Wszystko za sesją + CSRF; szablony i cykle mają wzorzec scope —
  `ScopedQuery`, cudzy PRIVATE ⇒ 404; zmiana scope/delete wł./ADMIN.
- Instancjacja/apply/copy tworzą dni WYŁĄCZNIE jako własność wykonującego
  użytkownika (owner z sesji) — nie wolno instancjować „na cudzy plan".
- Payload JSONB walidowany Pydantic przy każdym zapisie (nie przyjmujemy
  dowolnego JSON — kontrakt `v:1`); `member_profile_id` w splits walidowane
  jak w B06 (tylko własna rodzina).
- Brak nowych uploadów/tokenów; endpointy niedostępne publicznie.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE
- **Recommended**: SKILL-CALC
- **Review**: SKILL-REVIEW

## Tests

- **Unit**: budowa payloadu z dnia/tygodnia planu (struktura, pozycje,
  splits) i odwrotnie (payload → wiersze planu) — funkcje czyste w serwisie;
  rotacja cyklu (3 szablony na 5 tygodni ⇒ A,B,C,A,B; start od B);
  wyliczanie sekwencji bloku (3 dni × 2 ⇒ 6 dat docelowych).
- **Integration (obszary z ADR-012 i 02 §7)**:
  - **instancjacja kopiuje wartości, nie referencje żywe**: instancjuj
    szablon → zmień szablon (PUT payload) → plan bez zmian; zmień plan →
    szablon bez zmian;
  - **blokada usunięcia przepisu użytego w szablonie (JSONB!)**: przepis
    tylko w payloadzie day_template ⇒ DELETE /recipes/{id} → 409, nazwa
    szablonu w `used_in`; to samo dla produktu luzem w payloadzie
    i dla week_template; po usunięciu szablonu DELETE przechodzi;
  - zapytanie zliczające korzysta z indeksu GIN (asercja planu zapytania
    lub przynajmniej test istnienia indeksu w migracji);
  - kopiuj blok 2+2+2: 3 dni źródłowe ⇒ 6 dni docelowych w kolejności
    d1,d1,d2,d2,d3,d3; głęboka kopia (edycja kopii nie zmienia źródła);
  - apply cyklu na zakres: pełne i niepełny tydzień na końcu zakresu;
    `date_from` nie-poniedziałek ⇒ 422; delete szablonu użytego w cyklu ⇒ 409;
  - instancjacja tygodnia na zajęte daty dopisuje posiłki (zachowanie z B06).
- **API**: macierz uprawnień 08 §4 dla `/templates/*` i `/cycles`;
  payload spoza kontraktu ⇒ 422; anty-IDOR (cudzy szablon ⇒ 404).
- **FE (vitest)**: `BarChart` (stack, linia celu, aria-label); logika
  wyliczania dat w `BlockCopyDialog` i `CycleEditorDialog`.
- **E2E (core flow 2, 08 §3): tydzień przez szablon+cykl**: login →
  zbuduj dzień (posiłek z przepisem) → widok tygodnia → zapisz jako szablon
  dnia → zastosuj na 2 inne dni → zapisz tydzień jako szablon → utwórz cykl
  (szablon A) → zastosuj cykl na następny tydzień → siatka pokazuje
  skopiowane posiłki, `BarChart` niezerowy → przenieś posiłek między dniami
  (wariant przyciskowy — stabilniejszy niż DnD w CI).

## Acceptance Criteria

1. `task check` zielony; migracje up/down/up na kopii bazy; indeksy GIN
   istnieją na payloadach obu tabel szablonów.
2. Widok tygodnia pokazuje 7 dni × posiłki z sumami kcal/cel per dzień
   i `BarChart` tygodnia (tokens, aria-label).
3. Posiłek można przenieść między dniami drag&dropem ORAZ przyciskiem
   („Przenieś do dnia…") — oba warianty działają, mobile używa przycisku.
4. „Powiel blok" kopiuje N dni z powtórzeniem K (preset 2+2+2 jednym
   klikiem) — kolejność d1,d1,d2,d2,d3,d3; głęboka kopia.
5. Szablon dnia/tygodnia powstaje z istniejącego planu i od zera; edycja =
   nadpisanie payloadu; instancjacja tworzy kopię bez live-sync
   (testy z §Tests zielone).
6. Cykl A→B→C: apply na zakres dat instancjuje szablony rotacyjnie,
   z poprawnym startem rotacji i obsługą niepełnego tygodnia.
7. Usunięcie przepisu/produktu użytego TYLKO w payloadzie szablonu jest
   zablokowane (409, `used_in` z nazwą szablonu) — ADR-012 domknięty.
8. „Użyj ponownie": dzień/tydzień z przeszłości można skopiować na nowe
   daty z poziomu widoku tygodnia.
9. Macierz uprawnień 08 §4 zielona dla szablonów i cykli.
10. E2E „tydzień przez szablon+cykl" zielony na realnym stacku.

## Out of Scope

- Generacja zakupów z tygodnia → BATCH_10 (czyta gotowe plan_days).
- Statystyki wielotygodniowe i `TrendLine` → BATCH_13.
- Edycja relacyjna szablonu (per posiłek) — świadomie NIE (03_DB §6:
  payload nadpisywany całością); edycją jest plan + ponowny zapis szablonu.
- Współdzielenie szablonów między rodzinami, wersjonowanie szablonów — brak
  (nie ma w architekturze).
- Import/eksport szablonów → BATCH_14.

## Expected files/modules

- `backend/app/modules/planning/models.py` += DayTemplate, WeekTemplate,
  WeekCycle; `schemas.py` += kontrakt payloadu `v:1`; `service.py` +=
  templates/cycles/block; `router.py` += endpointy; ewentualnie osobny
  `templates_service.py` (decyzja implementującego, uzasadnić).
- `backend/app/modules/recipes/service.py` i `catalog/service.py` —
  rozszerzenie zliczania referencji o JSONB szablonów.
- `backend/migrations/versions/<pierwszy_wolny>_templates_and_cycles.py`.
- `backend/tests/{unit,integration,api}/planning/test_templates*`,
  `test_cycles*`, `test_block_copy*`, `tests/integration/recipes/
  test_delete_blocked_by_template*`.
- `frontend/src/pages/tydzien/PlanTygodniaPage.vue`,
  `components/charts/BarChart.vue`, `components/domain/planning/
  {TemplateSaveDialog,TemplateApplyDialog,CycleEditorDialog,BlockCopyDialog,
  ReuseHistoryDialog}.vue`, `src/lib/schemas/template.ts`, `queryKeys.ts` +=,
  `frontend/e2e/week-template-cycle.spec.ts`.
- Aktualizacje: `PROGRESS.md`, karty B10/B13/B14 (Cross-Batch), ew. 04_API.

## Implementation Notes

- Zliczanie referencji w JSONB: wybrać `jsonb_path_exists` z parametrem lub
  containment `@>` (jsonb_path_ops wspiera tylko `@>`) — sprawdzić, że
  wybrana forma używa indeksu GIN (`EXPLAIN`); wynik odnotować w Completion
  notes. To jest dług przypięty w ADR-012 — Review 2 to sprawdzi.
- Instancjacja tygodnia/cyklu robi wiele dni w JEDNEJ transakcji —
  częściowa instancjacja nie może zostać w bazie po błędzie.
- DnD: nie wprowadzać biblioteki bez potrzeby (ADR-007 duch minimalizmu) —
  pointer events wystarczą; DnD ma pełny odpowiednik przyciskowy, więc CI
  testuje przycisk, DnD pokrywa test komponentowy lub ręczna weryfikacja.
- `week_start` zawsze poniedziałek — jedna funkcja normalizująca
  współdzielona backend/frontend (frontend: helper w `lib/`).
- Payload `v:1`: pole wersji od początku — B14 (eksport) i ewentualne
  migracje payloadu będą go potrzebowały; zmiana kształtu = `v:2` +
  konwersja przy odczycie (nie robić teraz, tylko nie zamykać drogi).
- Pozostawione implementującemu (uzasadnić): dokładna forma zapytania JSONB;
  osobny plik serwisu; zachowanie `instantiate` przy zarchiwizowanym
  przepisie (sugestia: dopuścić + ostrzeżenie w odpowiedzi).

## Cross-Batch Impact

- **R2 (review)**: sprawdza granicę engine/service, ADR-012 (GIN + test),
  spójność payloadu — zostawić czytelne testy i notatki.
- **B10**: silnik zakupowy czyta plan wygenerowany też z szablonów/cykli —
  bez zmian kontraktu; zakres dat generacji często = tydzień z tego widoku.
- **B13**: `BarChart` powstał tutaj — B13 reużywa (stacked makro, zakresy).
- **B14**: eksport/import obejmie templates/cycles z payloadem `v:1` —
  dopisać do karty B14 kontrakt payloadu po implementacji.
- **B15/16**: import PDF tworzy przepisy używane potem w szablonach — bez
  wpływu na schemat; blokada usuwania już obejmie te przepisy.
- Po zakończeniu: przenieść ustalenia do kart B10/B13/B14 (00_MASTER §7).

## Implementation checklist

- [x] Migracja templates/cycles + indeksy GIN; up/down/up, jedna głowa
- [x] Kontrakt payloadu `v:1` (Pydantic) + funkcje plan↔payload + testy unit
- [x] Endpointy templates (CRUD, from-plan, instantiate) + cycles (+apply)
- [x] `/plan/copy what=block` z presetem 2+2+2
- [x] Blokada usuwania: recipes/products liczone też w JSONB (GIN, EXPLAIN)
- [x] `BarChart` + `PlanTygodniaPage` z DnD i alternatywą przyciskową
- [x] Dialogi szablonów/cykli/bloku/historii
- [x] Testy integration/api/fe; E2E week-template-cycle (napisany)
- [x] PROGRESS.md + propagacja do kart B10/B13/B14

## Verification checklist

- [x] `task check` ZIELONY W CAŁOŚCI (exit 0): migrations-check (3),
      test-unit (240), test-int (147), test-api (243), fe-test (198/19 plików),
      typecheck (mypy 116 + vue-tsc), lint, format-check (126), fe-build
- [x] Cykl migracji na realnej bazie — `test_migrations.py` (3 testy):
      `upgrade head → downgrade base → upgrade head`, head = `0009`, dokładny
      zestaw tabel z `day_templates`/`week_templates`/`week_cycles`
- [x] Test blokady usunięcia przez JSONB ZIELONY + potwierdzone użycie GIN
      (`EXPLAIN` pokazuje `ix_day_templates_payload_gin`)
- [x] Test braku live-sync (szablon↔plan w obie strony) ZIELONY
- [~] E2E tydzień przez szablon+cykl — URUCHOMIONY na realnym stacku, ale
      zablokowany na logowaniu: `E2E_ADMIN_PASSWORD` w `.env` nie zgadza się
      z hashem konta admina (szczegóły niżej). Nie jest to defekt speca ani
      kodu — to samo blokuje 4 wcześniejsze specy (dług U15)
- [ ] Ręcznie: powiel blok 2+2+2, przeniesienie DnD na desktopie, wariant
      przyciskowy na mobile — do zrobienia po naprawie konta E2E
- [x] Dokumentacja zaktualizowana (PROGRESS, karty B10/B13/B14, 03_DB §6, 04_API)
- [x] Commit `batch(07): szablony dnia i tygodnia, cykle i widok tygodnia`

## Completion notes

### Wykonane

- **Migracja `0009`** (`templates_and_cycles`): `day_templates`, `week_templates`
  (wzorzec scope + `name` + `payload JSONB`) i `week_cycles` (wzorzec scope +
  `name` + `template_ids BIGINT[]` + `start_date DATE NULL`). Typ `entity_scope`
  REUŻYTY z `0006` (`create_type=False`), `downgrade` go nie kasuje. **Indeksy
  GIN `jsonb_path_ops`** na obu payloadach. `down_revision = "0008"` (wynik
  łańcucha, nie numer z planu); jedna głowa.
- **Kontrakt payloadu `v:1`** w `planning/schemas.py`: `DayTemplatePayload`,
  `WeekTemplatePayload` + `TemplateMealPayload`/`TemplateItemPayload`/
  `TemplateSplitPayload`. `extra="forbid"`, `v` jako `Literal[1]`, Decimale przez
  `DecimalString` (do JSONB jako stringi). Walidacja przy zapisie I przy odczycie.
- **`planning/sequences.py`** — czysty plik bez I/O (ADR-008): `week_start_of`,
  `is_week_start`, `cycle_rotation_index`, `cycle_week_plan`, `block_copy_sequence`.
- **`planning/templates_service.py`** — `TemplatesService`: CRUD szablonów dnia
  i tygodnia (payload wprost albo z planu), instancjacja, CRUD cykli + `apply`,
  walidacja martwych referencji, liczniki referencji JSONB.
- **`PlanningService` zrefaktoryzowany na JEDEN mechanizm kopiowania**:
  `day_payload_from_rows` (czysta funkcja) + `day_payload_from_meals` +
  `append_day_payload`. `copy` (day/meal), `copy_block` i instancjacja szablonu
  korzystają z tego samego zapisu — wymóg karty „nie pisz drugiego mechanizmu".
- **Endpointy**: `/templates/days`, `/templates/weeks` (GET/POST/GET/PUT/DELETE +
  `POST {id}/instantiate`), `/cycles` (GET/POST/PUT/DELETE + `POST {id}/apply`),
  `/plan/copy` rozszerzone o `what="block"`.
- **Frontend**: `charts/BarChart.vue` (stacked SVG + linia celu, ADR-013),
  `pages/tydzien/PlanTygodniaPage.vue` (widok 4), pięć dialogów +
  `PlanningDialog.vue` (wspólna oprawa), `api/templates.ts`,
  `lib/schemas/template.ts`, `queryKeys += templates/cycles`, `texts.week`,
  trasa `/tydzien/:weekStart?` (podmieniony `PlaceholderPage`).

### Decyzje implementującego (karta zostawiła je do uzasadnienia)

1. **Osobny `templates_service.py`, nie rozrost `service.py`.** Agregatem jest
   tu SZABLON (encja ze scope, payload nadpisywany całością), a nie dzień;
   `service.py` miał już 1016 linii. Zapisy do planu i tak idą przez
   `PlanningService.append_day_payload`, więc nie ma drugiego mechanizmu
   kopiowania ani drugiej reguły rozstrzygania dnia.
2. **Forma zapytania JSONB: containment `@>`** (a NIE `jsonb_path_exists`).
   Powód wiążący: indeks GIN założono klasą `jsonb_path_ops`, która obsługuje
   wyłącznie `@>`, `@?` i `@@`; `jsonb_path_exists` jest funkcją, nie
   operatorem indeksowanym, więc planner zrobiłby seq scan. Zapytanie
   generowane przez SQLAlchemy: `payload @> $1::JSONB` (potwierdzone
   kompilacją dialektu i asercją `EXPLAIN` w teście integracyjnym, który
   wyłącza `enable_seqscan` na czas sprawdzenia — na pustej tabeli planner
   zawsze wybrałby seq scan, więc bez tego test nie mówiłby nic o zdolności
   zapytania do użycia indeksu).
3. **Zarchiwizowany przepis/produkt w payloadzie: DOPUSZCZONY z ostrzeżeniem**
   (sugestia karty). Nieistniejące id ⇒ 422 z listą (`details.recipe_ids` /
   `product_ids`), bo instancjacja padłaby i tak na FK RESTRICT
   `plan_meal_items` — tylko gołym 500 zamiast czytelnego komunikatu.
   Ostrzeżenia jadą w `InstantiateResponse.warnings` i UI pokazuje je zamiast
   zamykać dialog.
4. **Ilość w payloadzie jest JUŻ ZNORMALIZOWANA** (`amount` + `amount_unit` na
   osi produktu), a nie zapisana jako `quantity` + etykieta użytkownika.
   Payload odwzorowuje wiersze `plan_meal_items`, więc instancjacja jest
   przepisaniem wartości, nie ponowną konwersją. Inaczej zmiana przelicznika
   jednostki domowej po zapisaniu szablonu cicho zmieniłaby jego treść (albo
   wysadziła instancjację `UnitConversionError`).
5. **Scope dnia z instancjacji = scope SZABLONU**, właściciel = użytkownik
   z sesji. Szablon rodzinny daje dni widoczne dla rodziny (tego użytkownik
   oczekuje, wybierając „cała rodzina"), a `ownership_for_create` i tak
   waliduje, czy scope jest dla niego legalny.
6. **`start_date = NULL` w cyklu znaczy „pierwszy tydzień ZAKRESU dostaje
   pierwszy szablon"**, nie „każdy tydzień dostaje pierwszy szablon". Pierwsza
   (błędna) implementacja zwracała indeks 0 dla każdego tygodnia, czyli cykl
   bez daty startu w ogóle nie rotował; wyłapał to test jednostkowy
   `test_brak_daty_startu_zaczyna_rotacje_od_poczatku_zakresu`.
7. **Rotacja jest cykliczna także PRZED `start_date`** (Python `//` zaokrągla
   w dół, `%` zwraca nieujemne), więc „zastosuj cykl na poprzedni tydzień"
   daje ostatni szablon listy, a nie dziurę ani drugi tydzień A.
8. **Kolejność szablonów w cyklu zmienia się STRZAŁKAMI, nie drag&dropem.**
   Lista ma 2–4 pozycje, a strzałki działają identycznie na telefonie i
   z klawiatury (06_UIUX §2: DnD tylko tam, gdzie realnie szybszy). DnD jest
   tam, gdzie karta go wymaga — przy przenoszeniu posiłku między dniami.
9. **Przeniesienie posiłku = `copy` na dzień docelowy, POTEM `delete` źródła**
   (w tej kolejności, w jednej mutacji TanStack Query). Przy odwrotnej
   kolejności błąd kopiowania skasowałby posiłek bez śladu; przy tej najgorszy
   scenariusz to widoczny duplikat.
10. **`PlanningDialog.vue` (szósty, nielistowany komponent)** — wspólna oprawa
    pięciu paneli akcji: nagłówek, obszar błędu, lista ostrzeżeń, stopka
    z akcją główną i „Anuluj". Bez niego chroma i cele dotykowe byłyby
    skopiowane pięć razy.
11. **Puste dni są POMIJANE przy budowie szablonu tygodnia z planu**: szablon
    z pustą środą po prostu nie ma środy, zamiast dokładać do planu pusty dzień.
    Szablon z CAŁKOWICIE pustego dnia/tygodnia ⇒ 422 (to pomyłka użytkownika,
    nie pusty szablon).
12. **Dziura w bloku źródłowym nie jest błędem**: „powiel 3 dni" przy pustym
    środkowym dniu daje pusty dzień docelowy, nie 404 na całość.
13. **Blok czyta dni źródłowe RAZ, przed zapisami** — gdyby zakres docelowy
    nachodził na źródłowy, czytanie w pętli widziałoby już dopisane posiłki
    i lawinowo je multiplikowało.
14. **Rejestry referencji: dołożone WŁASNE findery** (`_templates_using_recipe`,
    `_templates_using_product`) przez istniejące rejestry z `recipes`/`catalog`.
    Pliki `recipes/service.py` i `catalog/service.py` NIE były zmieniane —
    rejestr jest zaprojektowanym punktem rozszerzenia i efekt jest ten sam
    (DELETE liczy teraz też payloady), więc modyfikowanie ich byłoby regresem
    względem wzorca z B04/B05.

### Odstępstwa i poprawki poza planem

- **`ServingsSplitDrawer.spec.ts` z B06 nie przechodził `vue-tsc`**
  (2x TS2339: `get(...)` zwraca wrapper BEZ `exists`). Poprawione na
  `find(...).exists()` — bez tego bramka `task check` nie mogła być zielona
  dla B07. Naprawa weszła do commita `batch(06)`, nie do tego.
- **Commit `batch(06)` nie istniał** na starcie sesji, mimo statusu `[x]`
  w PROGRESS — cała praca B06 leżała niezacommitowana w drzewie roboczym.
  Właściciel wybrał wariant „najpierw commit `batch(06)`", więc B06 dostał
  własny commit (`d6bacd7`) przed pierwszą linijką kodu B07.
- **`test_migrations.py`**: `after_upgrade` podniesione z `"0008"` na `"0009"`.
- Nazwy komponentów OpenAPI payloadu rozdzieliły się na `-Input`/`-Output`
  (Pydantic robi tak, gdy walidacja i serializacja pola różnią się typem —
  `DecimalString` przyjmuje liczbę albo string, a zwraca string). **Żaden
  istniejący komponent nie został usunięty ani przemianowany** (sprawdzone
  porównaniem zestawu nazw z `HEAD`), więc kontrakty B05/B06 są nietknięte.
  `api/templates.ts` trzyma oba aliasy i używa właściwego po właściwej stronie.

### Domknięcie bramki (druga sesja, 2026-08-21)

`task check` przeszedł **w całości, exit 0**: migrations-check (3),
test-unit (240), **test-int (147)**, **test-api (243)**, fe-test (198 w 19
plikach), typecheck (mypy 116 + vue-tsc), lint, format-check (126), fe-build.

Dwie rzeczy wyszły dopiero przy pierwszym przebiegu z realną bazą:

1. **Błąd w TEŚCIE, nie w kodzie**:
   `test_zapytanie_zliczajace_referencje_uzywa_indeksu_gin` wklejał wzorzec
   JSON wprost do `text()`, a SQLAlchemy potraktowało `:1` z `"recipe_id":1`
   jako nazwę parametru wiązanego (`A value is required for bind parameter
   '1'`). Wzorzec idzie teraz parametrem: `payload @> CAST(:pattern AS jsonb)`.
   Zapytanie PRODUKCYJNE (`.contains()`) było poprawne od początku —
   potwierdzone wcześniej kompilacją do `payload @> $1::JSONB`. **Pułapka dla
   kolejnych batchy: literał JSON w `text()` z `":<cyfra>"` staje się
   parametrem wiązanym.**
2. **Obraz kontenera `app` był przestarzały od B05** — brak `Pillow`
   (`ModuleNotFoundError: No module named 'PIL'`), więc `app` nie startował
   i stack dev był `unhealthy`. Niezależne od B07; lekarstwo to
   `task dev-detached` (`up --build -d`).

### E2E — uruchomione, zablokowane na koncie testowym

Pierwsze w historii projektu uruchomienie E2E (dług U15 z R1). Wynik:
**4 passed, 5 failed** — i wszystkie pięć padło w TYM SAMYM miejscu:
`expect(page).toHaveURL(/\/plan-dnia/)` zaraz po kliknięciu „Zaloguj",
przy czym strona zostaje na `/login`.

Diagnoza (bez ujawniania poświadczeń): konto z `E2E_ADMIN_EMAIL` **istnieje**
w bazie dev, ma rolę `admin`, `is_active = true`, `locked_until = null`
i poprawny hash argon2id — ale `verify_password(E2E_ADMIN_PASSWORD, hash)`
zwraca `valid=False`. Czyli **hasło w `.env` rozjechało się z hasłem konta**.
Potwierdza to test `błędne hasło pokazuje neutralny komunikat`, który PRZESZEDŁ
— endpoint logowania działa i po prostu odrzuca te dane.

Zielone 4 specy to te, które nie wymagają sesji (render `/login`, przekierowanie
z sekcji chronionej, neutralny komunikat błędu). Czerwone 5 to WSZYSTKIE
wymagające logowania — w tym `smoke.spec.ts` z B06 oraz `households`,
`produkty`, `recipe-inline-create` z wcześniejszych batchy. **Żaden z tych
błędów nie jest regresją B07** — to jedna wspólna przyczyna środowiskowa.

Do zrobienia przez właściciela (operacja na poświadczeniach, świadomie NIE
wykonana przez agenta): zsynchronizować hasło — albo `task create-admin`
z `FFP_ADMIN_EMAIL`/`FFP_ADMIN_PASSWORD` równymi `E2E_ADMIN_*`, albo wpisać do
`E2E_ADMIN_PASSWORD` faktyczne hasło konta. Potem `task test-e2e`.

### Wynik skilli Review (krok 11 master promptu)

**`/code-review` (poziom high) — 4 ustalenia, wszystkie NAPRAWIONE:**

1. `ReuseHistoryDialog.vue` — watch seedujący `sourceDate` nie miał `props.history`
   w źródłach, a zapytanie o historię WŁĄCZA SIĘ dopiero przy otwarciu dialogu,
   więc dane zawsze docierały po przebiegu watcha. Efekt: „Użyj ponownie" było
   trwale zablokowane komunikatem „brak historii" przy każdym pierwszym otwarciu
   (czyli acceptance criterion 8 nie działał). Naprawione rozdzieleniem na dwa
   watche: reset pól na otwarciu + wybór źródła na danych.
2. `templates_service.apply_cycle` — `_assert_references_alive` walidowało
   WSZYSTKIE szablony cyklu, nie tylko te wypadające w zakresie. Cykl [A, B, C]
   zastosowany na jeden tydzień padał 422 z powodu martwej referencji w C, którego
   ta operacja nie dotyka. Naprawione zawężeniem do `used_template_ids` z
   `week_plan` (+ test `test_apply_cyklu_ignoruje_szablony_poza_zakresem`).
3. `TemplateApplyDialog.vue` — ta sama klasa błędu co (1) dla list szablonów.
4. `CycleEditorDialog.vue` — ta sama klasa błędu dla `cycles`/`weekTemplates`
   (tryb „apply" nie miał czego wybrać).

**`/security-review` — 1 ustalenie HIGH, NAPRAWIONE:**

- **Obejście scope przez payload szablonu (IDOR na `recipe_id`).** `add_item`
  z B06 sprawdza widoczność przepisu (`_assert_recipe_available`), a
  `RecipesService.portion_values` ŚWIADOMIE nie filtruje scope (bo dzień
  rodzinny może zawierać prywatny przepis właściciela). B07 dołożył nową ścieżkę
  zapisu, która nie miała tej bramki: `POST /templates/days` z payloadem wprost
  przyjmował DOWOLNE `recipe_id`, a `instantiate` przepisywał je do
  `plan_meal_items`. Ścieżka ataku: zalogowany użytkownik wpisuje `recipe_id`
  cudzego PRYWATNEGO przepisu → instancjuje szablon na własną datę →
  `GET /plan/days` zwraca `recipe_name` i pełne wartości odżywcze cudzego
  przepisu. Iterując id dawało się zinwentaryzować prywatne przepisy całej
  instancji. Dodatkowo FK RESTRICT blokowałby wtedy właścicielowi usunięcie
  własnego przepisu.
  **Naprawa**: `_assert_references_alive` przyjmuje `user` i filtruje przepisy
  przez `ScopedQuery.visible_condition` — cudzy i nieistniejący dają IDENTYCZNY
  komunikat (endpoint nie jest oracle'em istnienia). Walidacja działa przy
  ZAPISIE payloadu (fail fast) i ponownie przy INSTANCJACJI (scope mógł się
  zmienić w międzyczasie). Produkty kanoniczne zostają na sprawdzeniu istnienia
  — katalog jest globalny i czyta go każdy zalogowany (04_API §2).
  Testy: `test_payload_nie_przyjmie_cudzego_prywatnego_przepisu`,
  `test_instancjacja_odrzuca_przepis_ktory_przestal_byc_widoczny`,
  `test_wlasny_i_rodzinny_przepis_w_payloadzie_przechodzi`.

Pozostałe kategorie bez ustaleń: zapytania JSONB są parametryzowane
(`payload @> $1::JSONB`), payload nie jest deserializowany inaczej niż przez
Pydantic z `extra="forbid"`, `member_profile_id` w rozkładzie jest filtrowany do
rodziny właściciela dnia docelowego (fail closed — profil spoza rodziny powoduje
pominięcie rozkładu, nie zapis), wszystkie endpointy są za sesją i CSRF, żadnych
nowych uploadów ani tokenów.

### Follow-upy (poza zakresem tego batcha)

1. **`task check` nie został uruchomiony w całości** — patrz „Pytania".
   Do domknięcia przez właściciela albo R2: `task dev-db` + `task check`.
2. **E2E `week-template-cycle.spec.ts` napisany, ale NIEURUCHOMIONY** — dług
   U15 z R1 rośnie o ten spec (razem ze smoke z B06).
3. **`db-seed-demo` nadal nie zna planu ani szablonów** — po B07 warto dosiać
   tydzień planu + jeden szablon dnia i tygodnia (08_TESTING §5). Przeniesione
   z follow-upów B06 (punkt 3), nadal aktualne.
4. **DnD ma tylko test ręczny.** Wariant przyciskowy pokrywa E2E; sam DnD nie
   ma testu komponentowego (jsdom nie odtwarza `DataTransfer` wiernie). Jeśli
   R2 uzna to za zbyt cienkie — kandydat na test Playwrightem z `dragTo`.
5. **`updateDayTemplate`/`updateWeekTemplate`/`updateCycle`/`deleteCycle`
   i `deleteDayTemplate` nie mają jeszcze UI** — backend i klient API są
   gotowe, ale widok tygodnia daje tylko tworzenie i stosowanie. Zarządzanie
   szablonami (lista + edycja + usuwanie) to naturalne miejsce w Ustawieniach;
   karta B07 tego nie wymagała, więc nie dokładałem ekranu.
6. **Cel kcal na `BarChart` tygodnia bierze się z pierwszego dnia, który go
   zna.** Cel jest dzienny i zwykle stały w tygodniu, ale przy celu zmienionym
   w środku tygodnia linia pokaże ten wcześniejszy. B13 (statystyki) i tak
   będzie potrzebowało celu per dzień — wtedy warto to uściślić.

### Pytania do właściciela

1. **`task check` w tej sesji NIE przeszedł w całości i nie z powodu kodu.**
   Silnik Dockera nie wstał (Docker Desktop działa, ale WSL-owa dystrybucja
   `docker-desktop` nie startowała; po ręcznym starcie `docker ps` odpowiada,
   ale `task dev-db` nie zdążył postawić baz). Uruchomione i ZIELONE:
   `migrations-check` (3), `test-unit` (240), `fe-test` (198 w 19 plikach),
   `typecheck` (mypy 116 + vue-tsc), `lint`, `format-check` (126),
   `fe-build`. NIEURUCHOMIONE: `test-int`, `test-api`
   (wymagają `TEST_DATABASE_URL`) oraz E2E. Proszę o uruchomienie
   `task dev-db && task check` na sprawnym Dockerze przed uznaniem batcha za
   DONE — testy z §Tests są napisane i to one weryfikują ADR-012 i brak
   live-sync. **Nie zgaduję ich wyniku i nie raportuję jako zielonych.**
2. Nowych decyzji-bramek nie ma; D15 i D16 pozostają OPEN w 02_DECISIONS.
   B07 dziedziczy stan faktyczny D16 (ADMIN widzi cudze encje na ścieżkach
   użytkownika) i asercjonuje go testem
   `test_admin_widzi_cudzy_szablon_na_sciezkach_uzytkownika`.
