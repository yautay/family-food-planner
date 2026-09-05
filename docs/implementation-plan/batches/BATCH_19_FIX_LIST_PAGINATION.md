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

- [x] Wzorzec „pokaż więcej" wybrany i uzasadniony
- [x] Sześć ekranów z tabeli §Context przerobionych
- [x] `/admin/weryfikacja`: sortowanie rozstrzygnięte (SERWER — `?sort=created_at`)
- [x] Licznik „widoczne z wszystkich" na `/produkty` i `/przepisy` (oraz na
      pozostałych czterech ekranach)
- [x] vitest per ekran + E2E paginacji
- [x] 06_UIUX i 05_FRONTEND zaktualizowane (plus 04_API §1 — konwencja `?sort=`)

## Verification checklist

- [x] `task check` zielony
- [x] E2E dwa kolejne przebiegi z tym samym wynikiem
- [x] Acceptance Criteria 1–5 odhaczone
- [x] Commit `batch(19): ...`, `git status` czysty

## Completion notes

### Wzorzec i jego uzasadnienie (decyzja pozostawiona implementującemu)

**Przyjęte: „pokaż więcej" z rosnącym `offset`, zrealizowane na
`useInfiniteQuery`.** Jeden composable `frontend/src/api/pagination.ts`
(`usePaginatedList`) + jeden komponent `components/domain/LoadMoreButton.vue`,
potem sześć użyć — wzorzec NIE jest skopiowany do sześciu plików.

Rekomendacja R4 („pokaż więcej", nie numerowane strony) przyjęta bez zmian:
aplikacja jest mobile-first (06_UIUX §5), a numerowana paginacja na telefonie to
cele dotykowe wielkości znaczka pocztowego. Doładowanie nie gubi tego, co
użytkownik przewinął, więc nie kosztuje kliknięć na powrót (06_UIUX §2).

**Dlaczego `useInfiniteQuery`, a nie zwykłe `useQuery` z rosnącym `limit`** —
trzy powody, każdy sam wystarczający:

1. **Sufit `limit` to 200** (04_API §1). Rosnący limit rozbiłby się o niego przy
   201. pozycji, a §Security tej karty wprost zabrania obchodzenia sufitu.
2. **Rosnący limit pobiera wszystko od nowa.** Trzecie kliknięcie ściągałoby 150
   pozycji, żeby pokazać 50 nowych.
3. **`offset` NIE wchodzi do klucza zapytań** — niesie go `pageParam`. To omija
   pułapkę z §Implementation Notes: klucz z offsetem tworzyłby osobny wpis
   cache'u per strona, więc `invalidateQueries` po mutacji odświeżałby jedną
   z nich, a reszta zostawałaby nieaktualna. Klucz listy jest DOKŁADNIE ten sam
   co przed batchem, więc żadna istniejąca inwalidacja nie wymagała zmiany.
   Konsekwencja: `offset` w interfejsach filtrów w `queryKeys.ts` jest teraz
   OPCJONALNY (podają go tylko pickery, które biorą jedną krótką stronę).

Rozmiary stron zostały jak były (`/spizarnia` 100, pozostałe 50). Batch dokłada
DOSIĘGALNOŚĆ, nie przestawia stron; zmniejszenie strony spiżarni dołożyłoby
kliknięć tam, gdzie ich dziś nie ma (06_UIUX §2).

### Sortowanie kolejki weryfikacji — rozstrzygnięte na SERWER

Karta dawała wybór: parametr sortowania albo skreślenie deklaracji „najstarsze
na górze". Wybrany serwer, bo `/admin/weryfikacja` to ekran, na którym
właściciel uzupełnia wartości odżywcze zaraz po imporcie — kolejność „od
najstarszych" jest tam funkcją, nie ozdobą.

Doszło: `ProductSort` (`StrEnum`, wzorzec `PantrySort`), parametr `sort`
w `GET /products` i w `CatalogService.list_products`, porządek
`(created_at, id)`. `id` domyka porządek, bo `created_at` nadaje `now()`
TRANSAKCJI — wiersze utworzone jednym żądaniem mają identyczny znacznik i bez
tie-breakera kolejność stron nie byłaby stabilna między zapytaniami. Przy
podanym `?q=` prefiks similarity zostaje pierwszy (wzorzec
`pantry.service._ordering`).

**Zmierzone na żywym stacku, nie z lektury kodu** (68 pozycji w kolejce bazy
dev: 8 istniejących + 60 zaseedowanych przez API): stara ścieżka — serwer
sortuje po `name`, strona układa pobraną pięćdziesiątkę po `created_at` — nie
pokazywała na pierwszej stronie ANI najstarszego realnego produktu („Oliwa
z oliwek"), ANI ostatniego z zaimportowanej sześćdziesiątki. Po naprawie
pierwsza strona zaczyna się od najstarszego, a druga (offset=50) dowozi
pozostałe 18. Dane testowe usunięte po sprawdzeniu — baza dev wróciła do stanu
wejściowego (8 niezweryfikowanych, zero śladów `B19%`).

### Ustalenia `/code-review` (poziom high) — 3 znalezione, 3 naprawione

1. **Nieudane doładowanie kasowało wiersze, które już były na ekranie**
   (`pagination.ts`). `isError` wystawiał stan błędu CAŁEGO `useInfiniteQuery`,
   a ten zapala się także po nieudanym `fetchNextPage`. Odtworzone probem: po
   padnięciu drugiej strony liczba kart spadała z 50 na 0 i znikał
   `products-list`, a licznik dalej mówił „50 z 60" — czyli wracał ten sam
   rozjazd liczby z widokiem, po który ten batch istnieje. Naprawa: `isError`
   tylko przy `pages.length === 0`, nowy `loadMoreFailed` (lista zostaje,
   komunikat siada przy przycisku, bo on jest ponowieniem). Reguła dopisana do
   **06_UIUX §3.6 pkt 7**. Testy: dwa przypadki w `ProduktyPage.spec.ts` + dwa
   w `LoadMoreButton.spec.ts`.
2. **Paginacja po `offset` mogła wyrenderować ten sam wiersz dwa razy**
   (`pagination.ts`). Zmiana zbioru między pobraniem stron przesuwa ich granice,
   więc pozycja wchodzi na dwie strony, a dwa węzły z tym samym `:key` psują
   patchowanie listy w Vue. Naprawa: odsiew po `id`
   (`TItem extends { id: number }`), `loaded` liczony PO odsiewie (licznik ma
   zgadzać się z tym, co widać), `offset` dalej z surowej liczby pobranych
   wierszy. Odsiew nie naprawia POMINIĘCIA wiersza — to robi
   `invalidateQueries`, po którym TanStack pobiera wszystkie wczytane strony na
   raz; kompromis opisany w nagłówku pliku i w 05_FRONTEND §3.
3. **Kolejność importów w `catalog/service.py`** łamała regułę isort i wywaliłaby
   `lint-be`. Naprawione `ruff check --fix` + `ruff format`.

### Odstępstwa od karty

- **Poza literą karty (na plus)**: licznik „widoczne z wszystkich" dostały
  WSZYSTKIE sześć ekranów, nie tylko `/produkty` i `/przepisy` — na
  `/admin/uzytkownicy` i `/admin/rodziny` licznika nie było wcale, a bez niego
  „pokaż więcej" nie mówi, ile jeszcze zostało.
- **Poza literą karty (wymuszone)**: `e2e/cleanup.ts` dostał `clearCategories`.
  Spec paginacji potrzebuje WŁASNEJ kategorii, bo filtr kategorii daje porządek
  deterministyczny, którego szukajka trigramowa nie gwarantuje; bez sprzątania
  kategoria zostawałaby w słowniku GLOBALNYM, widocznym na wszystkich ekranach.
  Idzie PO `clearProducts` (FK z 409).
- **Dokumentacja szersza niż §Stages**: doszła konwencja `?sort=` w **04_API
  §1** (porządek listy należy do serwera). Bez tego wpisu następny ekran
  z obiecaną kolejnością powtórzyłby błąd `/admin/weryfikacja`.
- Filtrów czasu/trudności/oceny w `/przepisy` NIE dodano (§Out of Scope, reguła
  1 briefu) — dopisane w 06_UIUX §4 widok 2 jako świadomy brak wymagający
  decyzji właściciela.
- Migracji nie było — batch nie tyka schematu, jedna głowa `0015` bez zmian.

### Follow-up (nowy, poza zakresem tego batcha)

Select przypisania konta na `/admin/rodziny` (`usersFilters = { limit: 200 }`)
bierze jedną stronę z sufitem serwera, bez „pokaż więcej". To kontrolka
formularza, nie ekran listy, więc przy instancji powyżej 200 kont potrzebuje
SZUKAJKI (jak `ProductPicker`), a nie doładowywania. Dziś bezprzedmiotowe —
instancja ma kilka kont.
