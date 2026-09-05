# BATCH_19 — FIX_LIST_PAGINATION

Klasa: FIX · Zależności: R4 (ustalenie P1) · Szacunek rozmiaru: S/M

## Goal

Każdy ekran listy pokazuje WSZYSTKIE swoje dane albo mówi wprost, że pokazuje
wycinek. Dziś API paginuje, a UI wysyła `offset: 0` ze stałym limitem i po
cichu ucina resztę — po ręcznym imporcie ośmiu jadłospisów (103 dania, 185
nazw produktów) użytkownik zobaczy 50 przepisów, 50 produktów i kolejkę
weryfikacji, z której nigdy nie da się wyjąć produktu spoza pierwszej
pięćdziesiątki alfabetycznie.

## Context

Ustalenie **REVIEW R4 (2026-09-05)**, priorytet **P1**. Stan zmierzony na kodzie:

| Ekran | Plik | Limit | Paginacja |
|---|---|---|---|
| `/produkty` | `pages/produkty/ProduktyPage.vue:35` | 50 | brak (`offset: 0`) |
| `/przepisy` | `pages/przepisy/PrzepisyPage.vue:32` | 50 | brak |
| `/spizarnia` | `pages/spizarnia/SpizarniaPage.vue:65` | 100 | brak |
| `/admin/weryfikacja` | `pages/admin/AdminWeryfikacjaPage.vue:31` | 50 | brak |
| `/admin/uzytkownicy` | `pages/admin/AdminUsersPage.vue:30` | 50 | brak |
| `/admin/rodziny` | `pages/admin/AdminHouseholdsPage.vue:42` | 50 | brak |
| `/import` | `api/pdfImport.ts:19` | 50 | brak **świadomie** (importów jest z natury mało — dług U25/U29, zostaje) |

Dwie rzeczy, przez które to nie jest kosmetyka:

1. **`/produkty` pokazuje „Produktów: {total}"** (`ProduktyPage.vue:105`) —
   czyli mówi „185" i renderuje 50. Liczba i widok kłamią razem.
2. **`/admin/weryfikacja` sortuje po stronie KLIENTA.** API sortuje po
   `name`, strona bierze pierwsze 50 i dopiero je układa po `created_at`
   („najstarsze na górze", `AdminWeryfikacjaPage.vue:42`). Przy 185
   produktach UNVERIFIED z importu kolejka pokaże pięćdziesiątkę wybraną
   ALFABETYCZNIE i nigdy nie dojdzie do reszty — a to jest dokładnie ekran,
   na którym właściciel ma spędzić czas zaraz po imporcie (runbook
   `docs/RUNBOOK_IMPORT_PDF.md`).

Czego NIE ma w dokumentach: 06_UIUX §4 nie opisuje paginacji dla żadnego
widoku, więc wzorzec trzeba USTALIĆ w tym batchu i dopisać do 06_UIUX.

Wymagane lektury przed startem:

- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §3 (akapit „Stan faktyczny
  po REVIEW R4" — tam jest lista ekranów) i §7.
- `docs/architecture/06_UIUX_PRINCIPLES.md` §2 (liczba kliknięć), §4 (widoki
  2, 6, 8), §5 (mobile ≥44 px).
- `docs/architecture/04_API_DESIGN.md` §1 (kontrakt `?limit=&offset=` →
  `{items,total}`, sufit 200).
- `CLAUDE.md` §5 + skill `pasnik-frontend` (TanStack Query, zakaz kopiowania
  stanu serwera do Pinii).

## Stages

1. **Wzorzec**: jeden komponent listy „pokaż więcej" (albo composable) +
   decyzja, czy to `useInfiniteQuery`, czy rosnący `limit`. Uzasadnienie
   w Completion notes — to jest decyzja pozostawiona implementującemu.
2. **Ekrany katalogowe**: `/produkty`, `/przepisy`, `/spizarnia`.
3. **Ekrany ADMIN-a**: `/admin/weryfikacja` (tu dodatkowo: sortowanie
   przenosi się na SERWER albo znika deklaracja „najstarsze na górze"),
   `/admin/uzytkownicy`, `/admin/rodziny`.
4. **Testy**: vitest per ekran + jeden E2E na `/produkty` z liczbą pozycji
   przekraczającą stronę.
5. **Docs**: 06_UIUX (nowy wzorzec), 05_FRONTEND §3 (skreślenie akapitu
   „Stan faktyczny po REVIEW R4"), PROGRESS.

## Database / migrations

Brak. Batch nie dotyka schematu — API już paginuje.

## Backend

Brak zmian wymaganych. **Jedyny kandydat do sprawdzenia**: czy
`GET /products?verification_status=unverified` ma sens sortować po
`created_at` (kolejka ma się opróżniać od najstarszych). Jeśli tak —
parametr sortowania w `catalog/service.py::list_products` zamiast
sortowania w przeglądarce; wtedy dochodzi test API.

## Frontend

- Wspólny wzorzec „pokaż więcej" (cel dotykowy ≥44 px, `data-testid`).
- Licznik pokazuje relację widocznych do wszystkich („50 z 185"), nie samo
  `total` — inaczej wraca dzisiejszy problem w łagodniejszej formie.
- Skeleton wyłącznie do PIERWSZEJ odpowiedzi (06_UIUX §3.4); doładowanie
  kolejnej strony to spinner na przycisku, nie migotanie listy.

## Security

Batch nie dotyka autoryzacji. Jedyna granica do utrzymania: `limit` jest
walidowany po stronie serwera (sufit 200, 04_API §1) i UI nie może go obejść
— „pokaż więcej" zwiększa `offset`, nie `limit` ponad sufit.

## Skills

- **Required**: SKILL-FE, SKILL-REVIEW
- **Recommended**: SKILL-BE (gdy dojdzie sortowanie po stronie serwera)
- **Review**: SKILL-REVIEW (`/code-review` na diffie)

## Tests

- vitest: dla każdego przerobionego ekranu — pierwsza strona, klik „pokaż
  więcej", brak przycisku gdy `items.length === total`.
- API (jeśli dojdzie sortowanie): kolejność `created_at` i macierz uprawnień
  bez zmian.
- E2E: `/produkty` z liczbą produktów > strona — po kliknięciu widać pozycję,
  której na pierwszej stronie nie było. Prefiks `E2E paginacja`,
  `cleanupE2eData` w `beforeAll` i `afterAll` (08_TESTING §3.1).

## Acceptance Criteria

1. Na każdym ekranie z tabeli w §Context da się dojść do OSTATNIEJ pozycji.
2. `/produkty` nie pokazuje liczby, której nie da się osiągnąć — licznik mówi
   „widoczne z wszystkich".
3. `/admin/weryfikacja` pokazuje kolejkę w deklarowanej kolejności NA CAŁYM
   zbiorze, nie w obrębie pobranej strony.
4. `task check` zielony; E2E zielone w DWÓCH kolejnych przebiegach.
5. 06_UIUX opisuje przyjęty wzorzec; akapit „Stan faktyczny po REVIEW R4"
   w 05_FRONTEND §3 skreślony jako nieaktualny.

## Out of Scope

- Filtry `prep_time_max` / `difficulty_max` / `rating_min` w UI przepisów —
  API je ma, 06_UIUX §4 widok 2 ich NIE chce (chipsy tagów + szukajka).
  Rewizja wymaga decyzji właściciela, nie „ulepszenia" przy okazji.
- Paginacja listy importów (U25/U29) — świadomie zostaje.
- Wirtualizacja list, nieskończone przewijanie sterowane scrollem.

## Expected files/modules

`frontend/src/components/domain/*` (nowy wzorzec) · `pages/produkty/ProduktyPage.vue`
· `pages/przepisy/PrzepisyPage.vue` · `pages/spizarnia/SpizarniaPage.vue`
· `pages/admin/{AdminWeryfikacjaPage,AdminUsersPage,AdminHouseholdsPage}.vue`
· `frontend/e2e/*` · `docs/architecture/{05_FRONTEND_ARCHITECTURE,06_UIUX_PRINCIPLES}.md`
· ewentualnie `backend/app/modules/catalog/{service,router}.py` + testy API.

## Implementation Notes

- Wzorzec wybiera implementujący, ale ma go UZASADNIĆ. Rekomendacja R4:
  **„pokaż więcej" z rosnącym `offset`**, nie numerowane strony — aplikacja
  jest mobile-first (06_UIUX §5), a numerowana paginacja na telefonie to
  cele dotykowe wielkości znaczka pocztowego.
- `queryKeys` już przyjmują filtry jako część klucza — dołożenie `offset`
  nie wymaga zmiany konwencji, ale UWAGA: klucz z `offset` psuje
  invalidację po mutacji, jeśli zrobić go dzieckiem klucza indeksu
  (ta sama pułapka, co w B11 z kluczem szczegółu listy).
- Nie kopiuj doładowanych stron do Pinii (ADR-007) — od tego jest
  `useInfiniteQuery` albo pojedyncze zapytanie z rosnącym `limit`.

## Cross-Batch Impact

- **B18**: bramka — batch ma być zamknięty przed wdrożeniem produkcyjnym
  (właściciel importuje jadłospisy PRZED albo ZARAZ po wdrożeniu i wtedy to
  uderza). B17 może iść niezależnie, w dowolnej kolejności.
- **00_MASTER_PLAN §3**: nowy wiersz w liście batchy.

## Implementation checklist

- [ ] Wzorzec „pokaż więcej" wybrany i uzasadniony
- [ ] Sześć ekranów z tabeli §Context przerobionych
- [ ] `/admin/weryfikacja`: sortowanie rozstrzygnięte (serwer albo skreślona
      deklaracja)
- [ ] Licznik „widoczne z wszystkich" na `/produkty` i `/przepisy`
- [ ] vitest per ekran + E2E paginacji
- [ ] 06_UIUX i 05_FRONTEND zaktualizowane

## Verification checklist

- [ ] `task check` zielony
- [ ] E2E dwa kolejne przebiegi z tym samym wynikiem
- [ ] Acceptance Criteria 1–5 odhaczone
- [ ] Commit `batch(19): ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
