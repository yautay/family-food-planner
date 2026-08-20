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

- [ ] Migracja templates/cycles + indeksy GIN; up/down/up, jedna głowa
- [ ] Kontrakt payloadu `v:1` (Pydantic) + funkcje plan↔payload + testy unit
- [ ] Endpointy templates (CRUD, from-plan, instantiate) + cycles (+apply)
- [ ] `/plan/copy what=block` z presetem 2+2+2
- [ ] Blokada usuwania: recipes/products liczone też w JSONB (GIN, EXPLAIN)
- [ ] `BarChart` + `PlanTygodniaPage` z DnD i alternatywą przyciskową
- [ ] Dialogi szablonów/cykli/bloku/historii
- [ ] Testy integration/api/fe; E2E week-template-cycle
- [ ] PROGRESS.md + propagacja do kart B10/B13/B14

## Verification checklist

- [ ] `task check` zielony — wynik REALNY
- [ ] `alembic upgrade head && downgrade -1 && upgrade head` na kopii bazy
- [ ] Test blokady usunięcia przez JSONB zielony + potwierdzone użycie GIN
- [ ] Test braku live-sync (szablon↔plan w obie strony) zielony
- [ ] E2E tydzień przez szablon+cykl zielony na compose
- [ ] Ręcznie: powiel blok 2+2+2, przeniesienie DnD na desktopie, wariant
      przyciskowy na mobile; acceptance criteria 1–10 odhaczone
- [ ] Dokumentacja zaktualizowana (PROGRESS, karty B10/B13/B14, ew. 04_API)
- [ ] Commit `batch(07): <opis>`; `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
