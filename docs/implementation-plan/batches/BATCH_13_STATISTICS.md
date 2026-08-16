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

- `backend/app/modules/nutrition/` — czysty silnik (Decimal, zero I/O,
  ADR-008): wartości pozycji/posiłku/dnia, ŁG, flagi completeness.
- `backend/app/modules/planning/` — `plan_days/plan_meals/plan_meal_items`
  + serwis z `ScopedQuery`; `GET /plan/days?from=&to=` już zwraca nutrition
  per dzień (04_API §2).
- `user_nutrition_goals` (03_DATABASE §2): historia celów po `valid_from`,
  `UNIQUE(user_id, valid_from)`; `users.ui_settings` JSONB — progi statusów
  (D9: domyślnie 90–110%, konfigurowalne).
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

- [ ] `stats_service.py`: agregacja + cele historyczne + luki + statusy
- [ ] Endpoint `GET /stats/daily` + schematy + limit 92 dni
- [ ] Testy unit/integration/API zielone
- [ ] `TrendLine.vue` + rozszerzenie `BarChart.vue` (linia celu, luki)
- [ ] `StatystykiPage.vue`: zakładki, zakresy, podsumowanie, statusy,
      pusty stan, plakietka „niepełne dane"
- [ ] vitest komponentów i strony
- [ ] E2E smoke statystyk
- [ ] `task fe-types` (typy z OpenAPI) wykonane
- [ ] 04_API zaktualizowane, PROGRESS.md wpis

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `task test-e2e` zielony
- [ ] Brak migracji (potwierdzić `alembic heads` = 1 głowa po merge)
- [ ] Ręcznie: zmiana celu w Ustawieniach → linia celu schodkowa w zakresie
- [ ] Ręcznie: zakres z dniami bez planu → luki, średnia bez zniekształcenia
- [ ] Acceptance Criteria 1–7 odhaczone z dowodem
- [ ] Dokumentacja i PROGRESS.md zaktualizowane; commit `batch(13): …`

## Completion notes

(wypełnia agent wykonujący)
