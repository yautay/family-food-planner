# BATCH_13 — STATISTICS

Klasa: PLAT · Zależności: BATCH_06 (cele + plan dnia), R3 · Bramki decyzji:
brak (D9 — progi statusów — zatwierdzone do przyjęcia w B06) · Rozmiar:
**S/M** · Dozwolona równoległość: **B12 ∥ B13 ∥ B14** (osobne worktree,
kolizje — patrz Cross-Batch Impact).

## Goal

Użytkownik dostaje stronę Statystyki (`/statystyki`): zakładki
Kalorie/Makroskładniki, wybór zakresu dat (tydzień/miesiąc/własny),
stacked BarChart dni z liniami/markerami celów (celów **historycznych** wg
`valid_from`), średnie dzienne vs cel i statusy za mało/OK/za dużo. Dane
liczy nowy endpoint agregujący `/stats/daily` — silnikiem nutrition,
z planów, bez żadnego cache w DB.

## Context

Batch zastaje (po B06 + R3):

- **B12 wszedł równolegle i ZOSTAWIA ŚLADY, o które trzeba zadbać przy merge'u**
  (00_MASTER §5): (a) migracja `0013_shopping_item_received_at` — jeśli ten
  batch startował z gałęzi sprzed B12, jego „pierwszy wolny numer" też wypadł
  na `0013`; po merge'u sprawdź `task db-heads` i przy dwóch głowach zrób
  migrację scalającą PRZED `task check`; (b) `frontend/package.json` +
  lockfile — B12 dołożył `idb` i `fake-indexeddb`, konflikt rozwiązuje się
  UNIĄ zależności, po czym `npm ci` w kontenerze frontendu; (c) pola
  `received_at` (pozycja listy) i `already_received` (odpowiedź
  `accept-to-pantry`) są w `frontend/src/api/generated.ts` — po merge'u
  przepuść `task fe-types` i zacommituj wynik zamiast ręcznie sklejać diff.

- **`shopping_generations.params` (B10) ma STABILNY, wersjonowany kształt** —
  jeśli statystyki będą z niego czytać, to przez `shopping.engine.load_input`,
  nigdy przez ręczne wyciąganie kluczy z JSONB. Wersja `{"v": 1}`; niezgodna
  wersja rzuca `ShoppingParamsError` (409 z instrukcją), a nie 500. Kolumna
  trzyma WEJŚCIE generacji (plan, produkty, spiżarnia, warianty, decyzje) —
  nie wynik, więc „ile faktycznie kupiono" jest w `shopping_list_items`.

- `backend/app/modules/nutrition/` — czysty silnik (Decimal, zero I/O,
  ADR-008): wartości pozycji/posiłku/dnia, ŁG, flagi completeness.
- `backend/app/modules/planning/` — `plan_days/plan_meals/plan_meal_items`
  + serwis z `ScopedQuery`; `GET /plan/days?from=&to=` już zwraca nutrition
  per dzień (04_API §2).
- **`frontend/src/components/charts/BarChart.vue` ISTNIEJE od B07 — REUŻYJ,
  nie pisz drugiego.** Kontrakt: `data: BarDatum[]`, gdzie
  `BarDatum = {label, title?, segments: BarSegment[], highlighted?}`
  i `BarSegment = {label, value (string dziesiętny), colorClass}`; do tego
  `target?: string | null` (linia celu), `unit`, `title`, `testid`.
  Słupek jest STACKOWANY, gdy `segments` ma więcej niż jeden element — czyli
  makro stacked z karty B13 nie wymaga zmian w komponencie, tylko innych
  danych. Skala jest WSPÓLNA dla wszystkich słupków i wciąga `target`, więc
  linia celu nigdy nie wypada z kadru. Testy: `BarChart.spec.ts` (9 przypadków).
  `TrendLine` nadal do napisania w tym batchu.
- `user_nutrition_goals` (03_DATABASE §2): historia celów po `valid_from`,
  `UNIQUE(user_id, valid_from)`; `users.ui_settings` JSONB — progi statusów
  (D9: domyślnie 90–110%, konfigurowalne).
  **Stan faktyczny po B06 — REUŻYJ, nie pisz drugi raz:**
  `nutrition/engine.py::goal_status(value, target, thresholds)` (oba progi
  należą do przedziału „prawidłowo"; brak celu ⇒ `None`, nie `below`),
  `nutrition/types.py::thresholds_from_ui_settings(ui_settings)` (pobłażliwy
  parser JSONB z fallbackiem na 90/110) oraz
  `nutrition/service.py::goal_for_day(goals, day)` — czysta funkcja wybierająca
  cel z NAJWIĘKSZYM `valid_from <= day` nad wczytaną historią
  (`GoalsService.goals_of(user_id)` czyta ją jednym zapytaniem, więc zakres
  dat nie generuje N+1). Statusy liczy się dla użytkownika Z SESJI: cel
  i progi są własnością konta, nie dnia.
  Schemat odpowiedzi kafelka: `GoalMetricRead{value, target, delta, status}`
  w `nutrition/schemas.py` — statystyki używają tego samego kształtu.
- Frontend: `src/lib/nutrition.ts` (`statusLabel`, `statusToken`, `statusFor`)
  i `src/lib/dates.ts` (arytmetyka dat kalendarzowych) — gotowe od B06.
- `frontend/src/components/charts/` — `NutritionBar`, `DonutChart`,
  `BarChart` (stacked, słupki tygodnia z widoku planu dnia) — własne SVG
  (ADR-013). **Brak** `TrendLine` — powstaje tutaj.
- Routing: trasa `/statystyki` zarezerwowana w 05_FRONTEND §3; strona
  jeszcze nie istnieje.

Wymagane lektury: 06_UIUX §4.7 (kontrakt widoku statystyk), ADR-013,
02_DOMAIN §6 (silnik, cele, statusy, completeness), 03_DATABASE §2 i §6,
04_API §1 (konwencje: stringi dziesiętne, kształt `nutrition`),
02_DECISIONS D9, 08_TESTING §2.1–§2.2.

## Stages

1. **Serwis agregacji** — `planning/stats_service.py` (lub `stats.py`
   w planning): funkcja zwracająca dni zakresu z nutrition + celem z dnia;
   testy integracyjne zielone.
2. **Endpoint** — `GET /api/v1/stats/daily?from=&to=` + schematy; testy API
   (w tym macierz uprawnień) zielone.
3. **TrendLine + rozszerzenia charts** — komponent SVG linii/markerów celu
   nakładany na `BarChart`; vitest komponentów.
4. **Strona Statystyki** — zakładki, zakres dat, wykresy, podsumowania,
   statusy; stany puste i „niepełne dane".
5. **Testy E2E smoke + docs** — wpis w PROGRESS.md, aktualizacja 04_API
   (mapa zasobów o `/stats/daily`).

## Database / migrations

**Brak migracji.** Agregaty liczone w locie z planów + celów (twardy wymóg:
bez cache w DB — niezmiennik 02_DOMAIN §13.2). Indeksy istniejące
(`plan_days(owner_user_id, day)` unique) wystarczają dla zakresów ≤ 92 dni.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/stats/daily?from=&to=` | GET | U | agregaty dzienne zakresu dla bieżącego użytkownika |

Walidacje: `from <= to`; zakres max **92 dni** (422 `validation_error` przy
przekroczeniu); daty `YYYY-MM-DD`.

Kształt odpowiedzi (stringi dziesiętne wg 04_API §1):

```json
{
  "days": [{
    "day": "2026-08-10",
    "has_plan": true,
    "nutrition": {"kcal": "1987", "protein_g": "112.0", "fat_g": "61.3",
                  "carbs_g": "243.1", "fiber_g": "31.0", "sugars_g": "44.2",
                  "glycemic_load": "98.5", "complete": true, "missing": []},
    "goal": {"kcal": "2000", "protein_g": "120.0", "fat_g": null,
             "carbs_g": null, "valid_from": "2026-08-01"},
    "status": {"kcal": "ok"}
  }],
  "summary": {
    "days_with_plan": 6,
    "avg": {"kcal": "1954", "protein_g": "108.2", "...": "..."},
    "avg_goal": {"kcal": "2000", "...": "..."},
    "status": {"kcal": "too_low", "protein_g": "ok"}
  }
}
```

Logika serwisu (`planning` czyta cele przez serwis modułu, który nimi
zarządza — nie przez „sięganie w tabele", 02_DOMAIN §1):

- Dni **bez planu**: element z `has_plan: false`, `nutrition: null` —
  to **luka**, NIE zero; średnie w `summary` liczone wyłącznie z dni
  `has_plan: true` (dzielnik = `days_with_plan`).
- Cel dnia = rekord `user_nutrition_goals` z największym `valid_from <=
  day` (cele historyczne!); brak celu ⇒ `goal: null`, status pomijany.
- Statusy: progi z `users.ui_settings` (default 90–110%, D9):
  `too_low` (<dolny), `ok`, `too_high` (>górny). W `summary` status liczony
  ze średniej vs **średnia celów** dni z planem (cel mógł się zmienić
  w środku zakresu).
- Całość liczenia deleguje do silnika `nutrition` (czyste funkcje);
  serwis tylko pobiera dane i składa odpowiedź. Flagi
  `complete/missing` propagowane per dzień.

## Frontend

- `src/pages/StatystykiPage.vue` — trasa `/statystyki` (link już w nav):
  - kontrolka zakresu: presety **Tydzień** (bieżący pon–nd) / **Miesiąc**
    (bieżący) / **Własny** (dwa date-pickery, walidacja max 92 dni);
  - zakładki (shadcn Tabs) **Kalorie** / **Makroskładniki**;
  - Kalorie: `BarChart` — słupek kcal per dzień + linia/markery celu
    (cel per dzień — linia „schodkowa" przy zmianie celu w zakresie);
  - Makroskładniki: stacked `BarChart` (białko/tłuszcze/węglowodany,
    kolory tokens 06_UIUX) + `TrendLine` średniej kroczącej + markery
    celów makro (jeśli ustawione);
  - pasek podsumowania: średnia dzienna / cel / delta / status słowny
    z kolorem+ikoną (nigdy sam kolor — 06_UIUX §1);
  - dni bez planu: słupek pusty z delikatnym oznaczeniem „brak planu"
    (nie zero!); plakietka „niepełne dane" z tooltipem gdy `complete=false`;
  - pusty zakres (0 dni z planem): pusty stan uczący — „Brak zaplanowanych
    dni w tym zakresie" + akcja „Przejdź do planu" (06_UIUX §3.2).
- `src/components/charts/TrendLine.vue` (N) — polyline SVG + markery;
  props: punkty, kolor tokenu, aria-label z wartościami (ADR-013).
- `src/components/charts/BarChart.vue` (M) — sloty/props na nakładkę linii
  celu i `TrendLine`; luki (null) renderowane jako brak słupka.
- Dane przez TanStack Query (`queryKeys.stats.daily(from, to)`);
  bez kopii w Pinia; liczby parsowane parserem dziesiętnym (04_API §1).

## Security

- Endpoint wymaga sesji; agreguje **wyłącznie plany widoczne dla
  użytkownika** (`ScopedQuery` — private własne + household rodziny) i JEGO
  cele. Test anty-IDOR: user B nie zobaczy w agregatach dni usera A.
- Brak nowych powierzchni: bez uploadów, tokenów, mutacji (endpoint
  read-only, GET bez CSRF).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-FE, SKILL-CALC
- **Recommended**: SKILL-BE
- **Review**: SKILL-REVIEW

## Tests

- **Unit (pytest, czyste):** wybór celu wg `valid_from` (przed pierwszym
  celem / między zmianami / po ostatniej); statusy na progach 89.9/90/110/
  110.1% (granice!); średnia z lukami (3 dni planu na 7 dni zakresu ⇒
  dzielnik 3, NIE 7); zmiana celu w środku zakresu ⇒ statusy dzienne wg
  celu z dnia.
- **Integration:** agregacja z realnego planu (fabryki: 2 przepisy +
  produkt luzem, mnożniki); scope household widoczny, cudzy private — nie.
- **API:** kontrakt odpowiedzi; `from>to` i zakres >92 dni ⇒ 422; anonim
  401; macierz uprawnień 08_TESTING §4.
- **vitest (komponenty):** `TrendLine` (punkty→polyline, aria-label);
  `BarChart` z lukami i linią celu schodkową; strona — przełączanie
  zakładek i presetów zakresu (mock query).
- **E2E (smoke):** login → seed przez API (plan 3 dni + cel) → `/statystyki`
  → widoczne słupki, średnia i status; zmiana zakresu przeładowuje dane.

## Acceptance Criteria

1. `/statystyki` pokazuje zakładki Kalorie i Makroskładniki oraz zakres
   tydzień/miesiąc/własny.
2. Słupki dni odpowiadają wartościom z planu (zgodne z widokiem planu dnia
   co do 1 kcal / 0,1 g — jedno źródło: silnik nutrition).
3. Linie/markery celów odzwierciedlają cele **historyczne**: zmiana celu
   w środku zakresu widoczna jako zmiana poziomu linii.
4. Dni bez planu są lukami — nie zaniżają średnich (weryfikowalne testem
   unit i ręcznie).
5. Średnia dzienna vs cel + status za mało/OK/za dużo (progi z ustawień
   użytkownika, domyślnie 90–110%) widoczne w podsumowaniu.
6. Niekompletne dane (brak IG/makr produktu) ⇒ plakietka „niepełne dane"
   z tooltipem, wartości liczone z dostępnych.
7. `task check` zielony; endpoint w OpenAPI; typy FE wygenerowane.

## Out of Scope

- Cache agregatów w DB (zakazany — 02_DOMAIN §13.2).
- Statystyki per członek rodziny / per posiłek (FUTURE, ewentualna decyzja
  po R4).
- Eksport statystyk (CSV/PDF) — nie planowany.
- Edycja celów (istnieje w Ustawieniach z B06) i progów statusów (B06) —
  tu tylko konsumpcja.
- Wykresy ŁG — dopisać jako propozycję do 02_DECISIONS, jeśli właściciel
  zechce (rekomendacja: później, po ręcznym uzupełnieniu IG — D11).

## Expected files/modules

- `backend/app/modules/planning/stats_service.py` (N),
  `backend/app/modules/planning/schemas.py` (M — schematy stats),
  `backend/app/modules/planning/router.py` (M — `GET /stats/daily`)
- `backend/tests/unit/test_stats_aggregation.py` (N),
  `backend/tests/integration/test_stats_service.py` (N),
  `backend/tests/api/test_stats_api.py` (N)
- `frontend/src/pages/StatystykiPage.vue` (N),
  `frontend/src/components/charts/TrendLine.vue` (N),
  `frontend/src/components/charts/BarChart.vue` (M),
  `frontend/src/api/queryKeys.ts` (M), `frontend/src/router` (M — trasa)
- `frontend/src/components/charts/TrendLine.test.ts`,
  `BarChart.test.ts`, `StatystykiPage.test.ts` (N)
- `docs/architecture/04_API_DESIGN.md` (M — `/stats/daily` w mapie zasobów)

## Implementation Notes

- Cel „schodkowy": NIE interpolować między celami — cel obowiązuje od
  `valid_from` do następnej zmiany; linia celu to funkcja schodkowa.
- Uważać na strefę czasową: `day` to DATE planu, zakresy porównywać jako
  daty, nie timestampy.
- Decyzja pozostawiona implementującemu (uzasadnić w Completion notes):
  okno średniej kroczącej TrendLine (rekomendacja: 7 dni) i czy pokazywać
  ją przy zakresie < 7 dni.
- Wydajność: jeden query po plan_days+meals+items zakresu z eager load —
  nie N+1 per dzień; przy 92 dniach to nadal małe dane (skala rodzinna).
- ŁG w odpowiedzi jest (silnik go daje) — UI zakładek go nie eksponuje
  (Out of Scope), ale nie wycinać z API.

## Cross-Batch Impact

- **Ustalenie REVIEW R3 (2026-08-22)**: zakres karty POTWIERDZONY bez zmian,
  bramka R3 = PASS. Dwa doprecyzowania: (a) `docs/architecture/04_API_DESIGN.md`
  modyfikują RÓWNIEŻ B14 i R3 — konflikt jest wyłącznie dokumentacyjny (dopisanie
  wiersza do mapy zasobów), rozwiązywany unią; (b) od R3 pusty dzień planu bez
  tytułu nie zostaje w bazie (`delete_meal` go sprząta), więc zapytanie
  statystyk po zakresie dat nie musi filtrować dni-widm — dzień bez posiłków
  albo nie istnieje, albo ma tytuł nadany przez użytkownika.
- **Kolizje równoległości (B12 ∥ B13 ∥ B14)**: wspólne pliki —
  `frontend/package.json`/lockfile i `src/api/queryKeys.ts` (B13 dodaje
  klucz stats). B13 NIE dotyka `vite.config.ts`, `src/lib/offline/*` (B12)
  ani `UstawieniaPage`/`AdminPage`/modułu `transfer` (B14). Backend B13
  dotyka wyłącznie modułu `planning` — bez kolizji z B12 (shopping)
  i B14 (transfer). Merge: unia zależności w package.json.
- **R4**: dopisać do przeglądu weryfikację zgodności statusów z progami
  ustawień użytkownika (spójność z widokiem planu dnia z B06).
- **B14**: cele (`user_nutrition_goals`) są encją eksportowaną — statystyki
  po imporcie na czystej bazie muszą działać bez zmian (nic do zrobienia
  w B13, odnotować w karcie B14 jako przypadek round-trip).

## Implementation checklist

- [x] `stats_service.py`: agregacja + cele historyczne + luki + statusy
- [x] Endpoint `GET /stats/daily` + schematy + limit 92 dni
- [x] Testy unit/integration/API zielone (22 + 12 + 12)
- [x] `TrendLine.vue` + rozszerzenie `BarChart.vue` (linia celu, luki, slot)
- [x] `StatystykiPage.vue`: zakładki, zakresy, podsumowanie, statusy,
      pusty stan, plakietka „niepełne dane"
- [x] vitest komponentów i strony (`TrendLine` 10, `BarChart` 9→17,
      `StatystykiPage` 16, `dates` 6→9)
- [x] E2E smoke statystyk (`e2e/statystyki.spec.ts`)
- [x] `task fe-types` (typy z OpenAPI) wykonane
- [x] 04_API, 05_FRONTEND, 06_UIUX zaktualizowane, PROGRESS.md wpis

## Verification checklist

- [x] `task check` zielony na finalnym drzewie: migrations-check 3, unit 325,
      integration 252, api 366, fe-test 37 plików / 354 testy, mypy 169 plików,
      ruff + eslint + prettier czysto, `vite build` OK
- [x] `task test-e2e` zielony
- [x] Brak migracji (`task db-heads` = jedna głowa `0013`)
- [x] Zmiana celu w środku zakresu → linia celu schodkowa (dowód: test
      `StatystykiPage.spec.ts::linia celu jest schodkowa…` + integracyjny
      `test_cel_dzienny_pochodzi_z_daty_dnia_nie_z_dzisiaj`)
- [x] Zakres z dniami bez planu → luki, średnia bez zniekształcenia (dowód:
      `test_srednia_dzieli_przez_dni_z_planem_a_nie_przez_zakres`,
      `test_dzien_bez_planu_jest_luka_i_nie_zaniza_sredniej`, E2E „3 z 7")
- [x] Acceptance Criteria 1–7 odhaczone z dowodem (patrz Completion notes)
- [x] Dokumentacja i PROGRESS.md zaktualizowane; commit `batch(13): …`

## Completion notes

**Wykonane** (jeden pion: serwis → endpoint → wykresy → strona → E2E → docs):

- `backend/app/modules/planning/stats_service.py` (N) — `StatsService.daily`
  plus CZYSTE funkcje składania odpowiedzi (`range_dates`, `day_statuses`,
  `average_values`, `average_targets`, `summarize`, `build_daily_stats`).
  Serwis nie liczy sam nic: dni bierze z `PlanningService.list_days` (ten sam
  `ScopedQuery` i to samo rozstrzyganie dnia, co widok planu), cele z
  `GoalsService.goals_of` + `goal_for_day`, statusy z `engine.goal_status`,
  średnią przez `aggregate` + `portion_nutrition` + `round_for_output`.
  Żadnej nowej reguły domenowej ani drugiego zaokrąglania.
- `GET /api/v1/stats/daily?from=&to=` — nowy router `build_stats_router()`
  w `planning/router.py` (prefiks `/stats`, tag `planning`), zarejestrowany
  w `app/main.py`, fabryka `get_stats_service` w `core/deps.py`. Walidacje:
  `from <= to` i sufit 92 dni ⇒ 422 `validation_error` (`PlanValidationError`).
- Schematy w `planning/schemas.py`: `StatsGoalRead`, `StatsStatusRead`,
  `StatsAveragesRead`, `StatsDayRead`, `StatsSummaryRead`,
  `StatsDailyResponse`. `nutrition/types.py` dostał addytywne
  `GOAL_NUMERIC_FIELDS` (jedno źródło listy pól, które mają cel).
- Frontend: `src/api/stats.ts` (N), klucz `queryKeys.stats.daily`,
  `components/charts/TrendLine.vue` (N), rozszerzony `BarChart.vue` (cel per
  słupek = linia schodkowa, `empty` = luka, slot `overlay`, podmienialny
  `emptyText`), `pages/StatystykiPage.vue` (N), trasa `/statystyki` wskazuje
  stronę, `lib/dates.ts += startOfMonth/endOfMonth`, `lib/texts.ts += stats`.
- Testy (wszystkie napisane i URUCHOMIONE): unit 22
  (`tests/unit/planning/test_stats_aggregation.py`), integration 12
  (`tests/integration/planning/test_stats_service.py`), API 12
  (`tests/api/planning/test_stats_api.py`), vitest: `TrendLine.spec.ts` 10,
  `BarChart.spec.ts` 9→17, `StatystykiPage.spec.ts` 16, `dates.spec.ts` 6→9;
  E2E `e2e/statystyki.spec.ts` (seed przez API + zakres własny w oknie 2031).
  Pełna bramka na finalnym drzewie: 325 unit / 252 integration / 366 api /
  354 vitest, `task test-e2e` 17 passed.

**Acceptance Criteria — dowody:**

1. Zakładki i presety zakresu: `StatystykiPage.spec.ts` („pokazuje obie
   zakładki i przełącza wykres", „zmiana presetu zakresu przeładowuje dane",
   „zakres własny odsłania date-pickery…"), E2E.
2. Zgodność z widokiem planu dnia co do 1 kcal / 0,1 g:
   `test_slupki_zgadzaja_sie_z_widokiem_planu_dnia` porównuje wynik
   `StatsService` z `PlanningService.get_day` na tej samej pozycji.
3. Cele historyczne: `test_cel_dzienny_pochodzi_z_daty_dnia_nie_z_dzisiaj`
   (integration), `test_cel_dnia_to_ostatnia_zmiana_przed_ta_data` (unit),
   „linia celu jest schodkowa i przerywa się na dniu bez celu" (vitest).
4. Luki nie zaniżają średnich: `test_srednia_dzieli_przez_dni_z_planem…`,
   `test_dzien_bez_planu_jest_luka_i_nie_zaniza_sredniej`, „luka nie wchodzi
   do skali" (BarChart), E2E („3 z 7").
5. Średnia vs cel + status: `test_delta_podsumowania_to_srednia_minus_srednia_celu`,
   `test_progi_uzytkownika_decyduja_o_statusie`, „podsumowanie pokazuje trio…".
6. Plakietka „niepełne dane" z tooltipem: `test_niepelne_dane_wychodza_flaga…`
   (API), „niepełne dane dostają plakietkę z listą braków w tooltipie" (vitest).
7. `task check` zielony, `/stats/daily` w `backend/openapi.json`, typy FE
   wygenerowane przez `task fe-types` (oba pliki w commicie).

**Decyzje wykonawcze** (żadna nie wymagała właściciela):

1. **`summary` używa `goal_progress: DayGoalProgressRead` zamiast osobnych
   `avg_goal` i `status`.** Sekcja Context karty każe użyć kształtu
   `GoalMetricRead` („statystyki używają tego samego kształtu"), a szkic JSON
   w §Backend pokazywał trzy równoległe mapy. Wybrałem kontrakt z Context:
   jeden kafelek = `{value, target, delta, status}`, więc strona renderuje
   podsumowanie tą samą składnią, co plan dnia, a `avg` (pełne siedem pól
   + `complete`/`missing`) zostaje osobno, bo makro-stack potrzebuje pól bez
   celu. `days[].status` jest schematem o STAŁYM zbiorze kluczy (nie mapą
   `str → status`), żeby wygenerowany typ FE wiedział, jakie pola istnieją.
2. **Dzień istniejący, ale bez posiłków, liczy się jako brak planu.** Po R3
   zostaje w bazie tylko dzień z TYTUŁEM; nie ma z czego policzyć wartości,
   a 0 kcal zaniżyłoby średnią — czyli dokładnie to, czego zakazuje AC 4.
   Zaasercjonowane (`test_dzien_z_tytulem_bez_posilkow_nie_jest_dniem_z_planem`)
   i dopisane do 04_API.
3. **Średnia celów jest liczona PER POLE**, tylko z dni, które cel tego pola
   miały. Cel makra jest opcjonalny, więc wliczenie braku jako zera zaniżyłoby
   cel i przekłamało status; dzielnik `days_with_plan` dotyczy WARTOŚCI.
4. **Okno średniej kroczącej: 7 dni**, pokazywana od zakresu ≥ 7 dni
   (rekomendacja karty). Na krótszym zakresie linia pokrywałaby się ze
   słupkami, więc w jej miejscu stoi zdanie wyjaśniające, a nie pusty wykres.
   Trend liczy sumę makr (to samo, co wysokość słupka stacked) i pomija dni
   bez planu w oknie.
5. **Cel stacka makro = suma trzech celów tylko, gdy ustawione są wszystkie
   trzy.** Suma dwóch celów wobec słupka z trzech makr zawsze wypadałaby na
   niekorzyść użytkownika — lepiej nie pokazać celu niż pokazać zły.
6. **Zakładki to `role="tab"` + `aria-selected` na przyciskach**, nie nowy
   komponent `ui/tabs`. Karta pisała „shadcn Tabs", ale repo nie ma tego
   komponentu, a B05 rozwiązał identyczny problem tak samo
   (`PrzepisSzczegolPage.vue`) — dodanie ósmego wariantu tabów byłoby
   niespójnością, nie ulepszeniem.
7. **Nakładka celu weszła jako PROPS (`target` per słupek), a slot `overlay`
   obsługuje `TrendLine`.** Karta dopuszczała „sloty/props"; linia celu jest
   integralną częścią skali wykresu (wciąga ją `scaleMax`), więc musi ją znać
   komponent, a nie konsument slotu.
8. **Ścieżki testów poszły do podkatalogów modułu** (`tests/unit/planning/`,
   `tests/integration/planning/`, `tests/api/planning/`) zamiast płaskich
   ścieżek z „Expected files" — taka jest faktyczna konwencja repo od B06.

**Odstępstwa od karty:** poza punktami 1, 6 i 8 wyżej — dołożony
`src/api/stats.ts` (nie było go w „Expected files", ale 05_FRONTEND §2 wymaga
wywołań HTTP w `src/api/<moduł>.ts`), `src/lib/dates.ts` (helpery miesiąca —
to JEDYNE miejsce liczące na datach), `src/lib/texts.ts` (teksty PL) oraz
`e2e/cleanup.ts` (eksport `csrfHeaders`, żeby spec seedujący przez API nie
miał drugiej kopii tej funkcji). Batch NIE dodał migracji — `task db-heads`
pokazuje jedną głowę `0013` (z B12).

**Ustalenia `/code-review` (SKILL-REVIEW) — wszystkie NAPRAWIONE w tym commicie:**

1. `data-testid` słupka brał się z etykiety, a etykieta („05") powtarza się
   w zakresie dłuższym niż miesiąc ⇒ przy 92 dniach trzy elementy o tym samym
   `data-testid` i strict mode Playwrighta na nich pada. Doszło `BarDatum.id`
   (strona podaje pełną datę), testy i E2E przepisane na nowe identyfikatory.
2. W trybie schodkowym `aria-label` w ogóle nie wspominał celów — czytnik
   ekranu nie miał skąd ich wziąć, bo wspólnej linii celu wtedy nie ma. Cel
   jedzie teraz przy KAŻDYM dniu (`… 1800 kcal (cel 2000 kcal)`).
3. Wyczyszczona data zakresu (native date input na to pozwala) blokowała
   zapytanie, ale strona pokazywała „Wczytywanie…", a potem pusty stan „Brak
   zaplanowanych dni" — czyli obwiniała użytkownika o brak planu. Teraz jest
   komunikat „Podaj obie daty zakresu." + `stats-range-blocked`, z testem.
4. Markery `TrendLine` były kluczowane samą etykietą punktu (ryzyko duplikatu
   klucza przy powtarzalnych etykietach) — klucz zawiera indeks.

**Follow-upy (poza zakresem, nie naprawiane):**

1. `frontend/src/pages/PlaceholderPage.vue` nie jest już używany przez żadną
   trasę (B13 był ostatnim placeholderem). Import z `router.ts` usunięty, plik
   został — do skasowania, gdy będzie jasne, że B14–B16 go nie potrzebują.
2. `planning/service.py::_GOAL_FIELDS` (pary pól celu) dubluje wiedzę z nowego
   `nutrition/types.py::GOAL_NUMERIC_FIELDS`. Zostawione bez zmian, bo
   `service.py` nie był w zakresie tego batcha; scalić przy okazji R4.
3. Średnia krocząca `TrendLine` jest liczona na `Number` (geometria wykresu,
   jak `toNumber` w `BarChart`), nie na `Decimal`. Domenowe liczby nadal
   przychodzą z serwera; gdyby trend miał kiedyś trafić do API, policzy go
   backend.
4. Wykresy ŁG pozostają nieplanowane (Out of Scope). ŁG JEST w odpowiedzi
   `/stats/daily` (asercja `test_glikemia_jest_w_odpowiedzi…` pilnuje, żeby
   nikt go nie wyciął), więc gdy właściciel zechce, UI nie wymaga zmian API.

**Pytania do właściciela:** brak — żadna decyzja-bramka nie była potrzebna,
nic nie dopisano do 02_DECISIONS.

