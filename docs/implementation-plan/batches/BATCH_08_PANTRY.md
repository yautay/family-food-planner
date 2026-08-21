# BATCH_08 — PANTRY

Klasa: SHOP · Zależności: BATCH_04 + R2 (bez bramek decyzyjnych) · Rozmiar: S/M

Równoległość: batch MOŻE iść równolegle z BATCH_09 w **osobnym git worktree**
(00_MASTER_PLAN §5). Przed startem sprawdzić listę plików wspólnych (Context
→ „Pliki wspólne z BATCH_09") i ustalić, który batch merguje się pierwszy.

## Goal

Po tym batchu rodzina prowadzi stan spiżarni: dodaje pozycje (produkt
kanoniczny, ilość w g/ml/szt., opcjonalna data ważności, lokalizacja,
notatka), zmienia ilości, zeruje i usuwa pozycje oraz przegląda spiżarnię
w dedykowanym widoku (grid/lista, filtr kategorii, sortowanie po dacie
ważności, wyróżnienie produktów bliskich przeterminowania, szukajka).
Spiżarnia jest wyłącznie STANEM domowym — odejmowanie od zakupów wykonuje
dopiero BATCH_10 i tylko za jawnym pytaniem użytkownika.

## Context

Co już istnieje (stan po R2):
- `backend/app/modules/catalog/` — produkty kanoniczne, kategorie, jednostki
  (BATCH_04); serwis wyszukiwania (trigram), wzorzec blokady usuwania (ADR-012).
  Konkrety z B04: ilości normalizuje `catalog/units.py` (`normalize_amount`
  → `NormalizedAmount(amount, unit ∈ g|ml|piece)`, `UnitConversionError` = 422),
  a pozycja spiżarni MUSI dopiąć swój licznik referencji przez
  `catalog.service.register_product_reference_finder(finder)` —
  `finder(session, product_id) -> Sequence[UsedInRef]`. Bez tego usunięcie
  używanego produktu da 409 bez listy „Używane w:" (kontrakt
  `app/core/deletion.py`).
- `backend/app/core/` — sesje, CSRF, `ScopedQuery` (mixin scope), deps,
  `deletion.py` (`UsedInRef`, `assert_deletable`, `conflict_from_integrity_error`).
- `frontend/src/components/domain/ProductPicker.vue` — command palette
  z inline create (wzorzec obowiązkowy, 05_FRONTEND §4): props `modelValue`,
  `label?`, `limit?`, `disabled?`, `debounceMs?`; emits `update:modelValue`,
  `selected(product)`.
- `frontend/src/components/domain/AmountInput.vue` — ilość + jednostka;
  `modelValue` to STRING dziesiętny (`"12.5"`), nigdy `Number`. Prezentacja
  ilości wyłącznie przez `src/lib/format.ts` (`formatAmount`: g→kg ≥1000).
- `AppShell` z nawigacją, TanStack Query + `queryKeys.ts`, klient API.

Czego ten batch NIE zastaje: tabeli `retail_products` (tworzy ją BATCH_09,
być może równolegle) — patrz Implementation Notes (FK `retail_product_id`).

Wymagane lektury przed startem:
- `docs/architecture/02_DOMAIN_MODEL.md` §3.1 (scope; spiżarnia zawsze
  HOUSEHOLD), §8 (Pantry — reguły domenowe)
- `docs/architecture/03_DATABASE_DESIGN.md` §1 (migracje), §4 (wzorzec scope),
  §7 (schemat pantry — WIĄŻĄCY)
- `docs/architecture/04_API_DESIGN.md` §1–3 (`/pantry` w mapie zasobów)
- `docs/architecture/06_UIUX_PRINCIPLES.md` §3 (wzorce), §4 pkt 6 (widok
  Spiżarnia), §5 (mobile)
- `docs/architecture/08_TESTING_STRATEGY.md` §2.5, §4 (macierz uprawnień)
- `docs/adr/ADR-012-usuwanie-archiwizacja.md`

Pliki wspólne z BATCH_09 (sprawdzić kolizje PRZED startem, rozwiązać przy merge'u):
- `backend/app/main.py` — rejestracja routera (oba batche dopisują router),
- `backend/migrations/versions/` — łańcuch `down_revision`; po merge'u
  `alembic heads` musi zwracać JEDNĄ głowę (00_MASTER_PLAN §5),
- `frontend/src/api/queryKeys.ts`, `frontend/src/api/generated.ts`
  (regeneracja `task fe-types` po merge'u),
- `frontend/src/router/*` i `AppShell` (B08 dodaje pozycję „Spiżarnia"),
- `backend/tests/factories.py`.
Reguła: batch mergowany JAKO DRUGI wykonuje rekoncyliację (down_revision,
regeneracja typów, konflikt w main.py) i uruchamia `task check` po merge'u.

## Stages

1. **DB**: migracja `pantry_items` wg 03_DATABASE §7; `upgrade head` +
   `downgrade -1` + `upgrade head` przechodzi na kopii bazy.
2. **Backend**: moduł `pantry` (models → schemas → service → router);
   scope „zawsze household"; walidacje ilości i jednostek; testy int+api zielone.
3. **Frontend**: `SpizarniaPage` (widok 6) + komponenty + composables;
   wpięcie do routera i nawigacji; pusty stan uczący.
4. **Testy**: komplet z sekcji Tests; `task check` zielony.
5. **Docs**: PROGRESS.md, Cross-Batch Impact przeniesiony do kart B10/B11.

## Database / migrations

Dokładnie schemat z 03_DATABASE §7 (plus konwencjonalne `created_at`/
`updated_at` — 03 §0):

```sql
pantry_items (id, household_id FK NULL, owner_user_id FK,  -- scope: zawsze household
       product_id FK→canonical_products RESTRICT NULL,
       retail_product_id FK RESTRICT NULL,
       amount NUMERIC(10,3), amount_unit ENUM(g,ml,piece),
       expiry_date DATE NULL, location TEXT NULL, note TEXT DEFAULT '',
       CHECK (product_id IS NOT NULL) OR (retail_product_id IS NOT NULL))
```

- Numer migracji = **pierwszy wolny** w `backend/migrations/versions/`
  w chwili implementacji; `down_revision` = wynik `alembic heads` (03 §1).
- Kolumna `retail_product_id` istnieje **od tego batcha** (wymóg planu),
  ale constraint FK zależy od istnienia `retail_products` — patrz
  Implementation Notes pkt 1.
- Brak CHECK-a `amount >= 0` w 03 → nieujemność egzekwowana serwisem
  i schematem Pydantic (NIE dodawać własnego CHECK bez aktualizacji 03).

## Backend

Moduł `backend/app/modules/pantry/` (wzorzec router → service → models).

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/pantry` | GET | U | lista; `?q=`, `?category_id=`, `?sort=expiry\|name`, `?expires_within_days=`, paginacja `limit/offset` (04 §1) |
| `/api/v1/pantry` | POST | U | dodanie pozycji |
| `/api/v1/pantry/{id}` | PATCH | U | zmiana ilości/ważności/lokalizacji/notatki; **wyzerowanie = `{"amount": "0"}`** (wiersz zostaje) |
| `/api/v1/pantry/{id}` | DELETE | U | usunięcie pozycji |

Serwis `PantryService`:
- Scope: spiżarnia **zawsze HOUSEHOLD** (02 §3.1 pkt 1) — zapis z
  `household_id` = rodzina użytkownika; użytkownik bez rodziny:
  `household_id NULL`, pozycja wisi na `owner_user_id` (03 §2, §7).
  Widoczność: `household_id = :user_household_id OR (household_id IS NULL
  AND owner_user_id = :uid)`. Obcy household → 404 (07_SECURITY §4).
- Walidacje (422 z komunikatem PL): `amount >= 0` (nigdy ujemna);
  `amount_unit` zgodna z `measure_kind` produktu (`piece` tylko dla
  produktów `measure_kind=piece` — analogicznie do recipes, 03 §5);
  co najmniej jedno z `product_id`/`retail_product_id` (odbicie CHECK);
  `retail_product_id` walidowany tylko, gdy tabela retail istnieje.
- Metoda dla przyszłych batchy: `get_household_state(user) ->
  list[PantryStateItem]` — pozycje ze znormalizowanymi ilościami (g/ml/szt.),
  konsumowana przez silnik zakupowy w B10 i akcję „przyjmij zakupy" w B11.

Ilości w JSON jako stringi dziesiętne (`"250.0"`) — konwencja 04 §1.

## Frontend

- `frontend/src/pages/spizarnia/SpizarniaPage.vue` — route `/spizarnia`
  (widok 6 z 06_UIUX §4): przełącznik grid/lista (preferencja widoku
  w Pinia — 05 §1), filtr kategorii (chipsy), sortowanie po dacie ważności
  (domyślne; pozycje bez daty na końcu), szukajka (`?q=`), przycisk
  „+ Dodaj produkt" otwierający formularz z `ProductPicker` (inline create
  obowiązkowy — 06 §3 pkt 1).
- Komponenty: `PantryItemRow.vue` / `PantryItemCard.vue` (nazwa, ilość
  przez `formatAmount`, data ważności, lokalizacja, akcje: zmień/wyzeruj/
  usuń), `ExpiryBadge.vue` (bliskie przeterminowania — bursztyn,
  przeterminowane — czerwień; zawsze kolor + tekst, 06 §1).
- Composables: `usePantryQuery`, `usePantryMutations` (TanStack Query,
  jawny `invalidateQueries`; klucze w `queryKeys.ts`).
- Formularz dodania/edycji: `AmountInput` (przecinek dziesiętny PL),
  jednostka zawężona do `measure_kind` produktu, data ważności opcjonalna,
  lokalizacja jako tekst z podpowiedziami (szafka/lodówka/zamrażarka).
- Pusty stan: „Twoja spiżarnia jest pusta." + primary action
  „Dodaj pierwszy produkt" (06 §3 pkt 2).
- Nawigacja: pozycja „Spiżarnia" w sidebarze; mobile — w zakładce „Więcej".
- Destrukcja bezpieczna: usunięcie pozycji = dialog potwierdzenia (06 §3 pkt 3).

## Security

- Wszystkie endpointy za sesją + CSRF na mutacjach (07 §2–3).
- Scope household egzekwowany w serwisie (`ScopedQuery`), nie w routerze;
  cudza pozycja = 404, nie 403 (07 §4).
- Testy anty-IDOR obowiązkowe: user z innej rodziny nie odczyta/nie zmieni
  pozycji (macierz 08 §4).
- Brak uploadów, tokenów publicznych i operacji admin-only w tym batchu.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE
- **Recommended**: SKILL-CALC
- **Review**: SKILL-REVIEW

## Tests

- **Integration** (`task test-int`):
  - CRUD pełny; wyzerowanie zostawia wiersz z `amount=0`;
  - CHECK „co najmniej jeden z product/retail" (naruszenie → błąd);
  - scope: członek rodziny widzi i edytuje; user bez rodziny ma spiżarnię
    osobistą; migracja up/down/up.
- **API** (`task test-api`):
  - macierz uprawnień 08 §4 dla zasobu HOUSEHOLD (anonim 401, obcy 404,
    członek 200 odczyt+edycja);
  - `amount < 0` → 422 (nigdy ilość ujemna — obszar krytyczny 08 §2.5);
  - `amount_unit=piece` dla produktu `mass` → 422;
  - sortowanie po `expiry_date` (NULL na końcu), filtr kategorii, `?q=`,
    `expires_within_days`.
- **Frontend** (`task fe-test`): `ExpiryBadge` (progi wyróżnienia),
  render listy z sortowaniem, formularz dodania (walidacja ilości).
- **E2E** (Playwright): dodanie pozycji przez `ProductPicker` z inline
  create nowego produktu → pozycja widoczna na liście; wyzerowanie.

## Acceptance Criteria

1. Członek rodziny dodaje pozycję spiżarni (produkt kanoniczny, ilość,
   opcjonalna data ważności/lokalizacja/notatka) i widzi ją natychmiast.
2. Zmiana ilości, wyzerowanie (pozycja zostaje z 0) i usunięcie działają;
   ilość ujemna jest niemożliwa do zapisania (422).
3. Spiżarnia jest wspólna dla rodziny: drugi członek widzi i edytuje te
   same pozycje; użytkownik z innej rodziny dostaje 404.
4. Widok `/spizarnia`: filtr kategorii, szukajka, sortowanie po dacie
   ważności, wyróżnienie pozycji bliskich przeterminowania, grid/lista.
5. Żaden mechanizm nie odejmuje spiżarni od czegokolwiek automatycznie —
   w kodzie nie istnieje takie wywołanie (to zakres B10).
6. `alembic heads` = jedna głowa; migracja odwracalna; `task check` zielony.

## Out of Scope

- Odejmowanie spiżarni od zakupów i pytanie „Uwzględnić stan domowy?" → BATCH_10.
- Akcja „przyjmij zakupy do spiżarni" → BATCH_11 (02_DOMAIN §8).
- UI wyboru produktu retail w spiżarni → po BATCH_09 (kolumna już istnieje;
  drobne rozszerzenie formularza wykona B10 albo R3 wg stanu merge'ów).
- Powiadomienia o przeterminowaniu (brak w planie MVP).
- Słownik lokalizacji (zostaje wolny tekst z podpowiedziami).

## Expected files/modules

> **Korekta ścieżek — review R2 (2026-08-21).** Ta lista powstała przed B04,
> więc kilka ścieżek nie istnieje w repo. Stan FAKTYCZNY: router to
> `frontend/src/router.ts` (nie `router/index.ts`), shell to
> `frontend/src/layouts/AppShell.vue` (nie `components/AppShell.vue`),
> a katalogu `frontend/src/composables/` **nie ma i nie trzeba go tworzyć** —
> od B04 wzorcem jest `src/api/<moduł>.ts` (funkcje HTTP) + `useQuery`
> /`useMutation` wołane wprost w komponencie, z kluczami z
> `src/api/queryKeys.ts` (ADR-007, 05_FRONTEND §1). Testy backendu też mają
> nową strukturę: katalog per moduł, czyli
> `backend/tests/{integration,api}/pantry/test_*.py` z `__init__.py`
> (wzorzec z B05–B07). Nawigacja: `/spizarnia` ma już wpis w
> `src/lib/navigation.ts` i trasę z `PlaceholderPage` — batch PODMIENIA
> `component` istniejącej trasy, nie dokłada nowej pozycji (CLAUDE.md §5).

Nowe:
- `backend/app/modules/pantry/{__init__.py,models.py,schemas.py,service.py,router.py}`
- `backend/migrations/versions/<pierwszy_wolny>_pantry_items.py`
- `backend/tests/integration/pantry/{__init__.py,test_pantry_service.py}`
- `backend/tests/api/pantry/{__init__.py,test_pantry_api.py}`
- `frontend/src/pages/spizarnia/SpizarniaPage.vue`
- `frontend/src/components/domain/{PantryItemRow.vue,PantryItemCard.vue,ExpiryBadge.vue}`
- `frontend/src/api/pantry.ts`
- `frontend/e2e/pantry.spec.ts`

Zmieniane (⚠ = wspólne z B09):
- ⚠ `backend/app/main.py` (router), ⚠ `backend/app/models.py` (rejestr modeli),
  ⚠ `backend/tests/conftest.py` (`DB_TABLES`),
  ⚠ `backend/tests/integration/test_migrations.py` (`EXPECTED_TABLES`),
  ⚠ `backend/tests/factories.py`
- ⚠ `frontend/src/api/queryKeys.ts`, ⚠ `frontend/src/api/generated.ts` (regen)
- ⚠ `frontend/src/router.ts` (podmiana `component` trasy `/spizarnia`)

## Implementation Notes

1. **FK `retail_product_id` przy pracy równoległej z B09**: jeśli w chwili
   pisania migracji `retail_products` już istnieje na gałęzi bazowej —
   pełny `FK RESTRICT`. Jeśli NIE (B08 merguje się pierwszy) — utworzyć
   kolumnę `BIGINT NULL` **bez constraintu FK**, a batch mergowany jako
   drugi dodaje constraint w migracji rekoncyliacyjnej; fakt odnotować
   w PROGRESS.md i w Completion notes obu batchy.
2. Próg „bliskie przeterminowania" nie jest zdefiniowany w architekturze —
   decyzja implementującego (rekomendacja: ≤7 dni bursztyn, po dacie
   czerwień) z uzasadnieniem w Completion notes.
3. Nieujemność ilości: tylko warstwa serwisu/Pydantic (03 §7 nie definiuje
   CHECK) — nie rozszerzać schematu na własną rękę.
4. Kolejność: DB → serwis z testami int → API → UI. Widok 6 jest prosty —
   nie przeinżynierować (06 §2: minimum kliknięć).

## Cross-Batch Impact

- **BATCH_10**: konsumuje `PantryService.get_household_state()` (parametr
  `use_pantry` silnika); jeśli sygnatura/kształt danych odbiegnie od karty
  B10 — zaktualizować `BATCH_10_SHOPPING_ENGINE.md` (sekcja Context).
- **BATCH_11**: akcja „przyjmij zakupy do spiżarni" woła serwis pantry
  (dodanie/zwiększenie pozycji) — udokumentować metodę w Completion notes.
- **BATCH_09/R3**: jeśli FK odroczony (nota 1) — dopisać zadanie
  rekoncyliacji do PROGRESS.md i karty batcha mergowanego jako drugi.

## Implementation checklist

- [x] Migracja `pantry_items` (up/down/up na kopii bazy, jedna głowa)
- [x] Modele + schematy Pydantic (amount ≥ 0, stringi dziesiętne)
- [x] `PantryService` (scope household, walidacje, `get_household_state`)
- [x] Router `/pantry` + rejestracja w `main.py`
- [x] Testy integration + API (w tym macierz uprawnień, anty-IDOR)
- [x] `SpizarniaPage` + komponenty + routing + nawigacja (composables NIE —
      wzorcem od B04 jest `src/api/<moduł>.ts` + `useQuery` w komponencie)
- [x] Pusty stan, dialogi potwierdzeń, `formatAmount`
- [x] Testy frontend + E2E
- [x] PROGRESS.md + propagacja Cross-Batch Impact do kart B09/B10/B11

## Verification checklist

- [x] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [x] `alembic upgrade head` + `downgrade -1` + `upgrade head` przechodzi;
      `alembic heads` = 1 głowa (`0010`)
- [x] Acceptance Criteria 1–6 sprawdzone testem (mapowanie w Completion notes)
- [x] Testy anty-IDOR obecne i zielone
- [x] Dokumentacja: PROGRESS.md, 03_DATABASE §4/§7, karty B09/B10/B11
- [x] Commit `batch(08): …`, `git status` czysty w zakresie batcha

## Completion notes

### Co weszło

**Backend.** Moduł `app/modules/pantry/` (models → schemas → service → router)
+ migracja `0010_pantry_items` (`down_revision = 0009`, jedna głowa).
Endpointy `GET/POST /api/v1/pantry`, `PATCH/DELETE /api/v1/pantry/{id}` wg mapy
04_API §2. Serwis rejestruje licznik referencji katalogu
(`_pantry_using_product`, `type="pantry_item"`), więc `DELETE /products/{id}`
używanego w spiżarni daje 409 z czytelną listą „Używane w:".

**Wariant scope „zawsze household".** Do `app/core/scope.py` doszły
`HouseholdScopedMixin` + `HouseholdScopedQuery` — dokładnie ten wariant, który
zapowiadał docstring modułu od B03. `ScopedMixin` NIE dał się użyć: jego CHECK
(`scope <> 'household' OR household_id IS NOT NULL`) zabraniałby wiersza
„household bez rodziny", a to jest wymagany przypadek spiżarni użytkownika bez
rodziny. Warunek widoczności jest inny niż w `ScopedQuery` i to jest celowe:

```sql
household_id = :user_household_id OR (household_id IS NULL AND owner_user_id = :uid)
```

Samo `owner_user_id = :uid` NIE wystarcza — po odejściu z rodziny wpis zostaje
przy rodzinie, bo spiżarnia to jeden stan domu, a nie prywatna notatka (test
`test_odejscie_z_rodziny_zabiera_dostep_do_jej_spizarni`). ADMIN dostaje
`true()` jak w `ScopedQuery` (D16) i jest to zaasercjonowane w macierzy.

**Frontend.** `/spizarnia` (podmiana `component` istniejącej trasy),
`SpizarniaPage.vue`, `PantryItemCard.vue` / `PantryItemRow.vue` (identyczny
kontrakt props/emits — przełącznik widoku podmienia komponent, nie logikę),
`ExpiryBadge.vue`, `src/api/pantry.ts`, `src/lib/expiry.ts`, store UI
`src/stores/pantryView.ts` (preferencja kafelki/lista w localStorage).
Formularz stoi na `ProductPicker` + `AmountInput` (create-in-context działa
end-to-end — pilnuje tego `e2e/pantry.spec.ts`).

**Sprzątanie E2E.** `e2e/cleanup.ts` dostał `clearPantry` wpięte w
`cleanupE2eData` I `purgeE2eLeftovers` **przed** `clearProducts` — pozycja
spiżarni trzyma produkt FK RESTRICT, więc bez tego pierwszy przebieg z pantry
zablokowałby usuwanie produktów E2E 409-ką (dokładnie ten dług, który R2
zamykał dla przepisów).

### Mapowanie Acceptance Criteria na testy

| AC | Dowód |
|---|---|
| 1 (dodanie i natychmiastowa widoczność) | `test_pelny_cykl_zycia_pozycji`, `test_dodanie_pozycji_zwraca_dane_produktu`, E2E `pantry.spec.ts` |
| 2 (zmiana / wyzerowanie / usunięcie; brak ilości ujemnej) | `test_pelny_cykl_zycia_pozycji`, `test_wyzerowanie_zostawia_pozycje`, `test_ilosc_ujemna_to_422`, `test_czlonek_rodziny_usuwa_cudza_pozycje` (D17) |
| 3 (spiżarnia wspólna; obca rodzina 404) | `test_spizarnia_jest_wspolna_dla_rodziny`, `test_obcy_uzytkownik_dostaje_404` |
| 4 (widok: filtry, szukajka, sortowanie, wyróżnienie, grid/lista) | `test_lista_sortuje_filtruje_i_szuka`, `SpizarniaPage.spec.ts`, `ExpiryBadge.spec.ts` |
| 5 (nic nie odejmuje spiżarni automatycznie) | w kodzie nie ma wywołania odejmującego — `get_household_state` jest tylko CZYTANE i nie ma konsumenta w tym batchu; `grep -r get_household_state backend/app` daje wyłącznie definicję |
| 6 (jedna głowa, migracja odwracalna, `task check`) | `test_upgrade_downgrade_upgrade_na_czystej_bazie` (head = `0010`), `task check` |

### Decyzje implementacyjne

1. **Próg „bliskie przeterminowania" (nota 2 karty): ≤ 7 dni bursztyn, po
   dacie czerwień.** Uzasadnienie: siedem dni to horyzont jednego cyklu
   zakupowego (preset tur z 02_DOMAIN §9.2 — niedziela + środa), więc „kończy
   się" znaczy operacyjnie „nie doczeka następnych zakupów". Stała
   `EXPIRY_SOON_DAYS` w `src/lib/expiry.ts` jest też progiem filtra „tylko
   kończące się" (`?expires_within_days=7`), więc plakietka i filtr nie mogą
   się rozjechać. Filtr obejmuje TAKŻE pozycje już przeterminowane — filtr
   pilności, który chowa to, co zepsuło się wczoraj, byłby odwrotnością
   pilności.
2. **Ilość wchodzi na osi produktu (g/ml/szt.), nie w dowolnej jednostce
   domowej.** Karta wymaga `{"amount": "0"}` jako wyzerowania, a
   `normalize_amount` z definicji odrzuca ilości ≤ 0 (02_DOMAIN §13.1) — te
   dwie rzeczy nie dają się pogodzić w jednym polu. Spiżarnia to KOREKTA STANU
   („zostało 250 g"), nie zapis przepisu („2 łyżki"), więc przyjmujemy
   `amount` + opcjonalny `amount_unit` walidowany względem `measure_kind`
   (pominięty = oś produktu). Konsekwencja UX: w formularzu nie ma wyboru
   kg/l — użytkownik wpisuje gramy, a `formatAmount` i tak pokazuje „1,5 kg"
   przy odczycie. To jest odczytanie karty „jednostka zawężona do
   `measure_kind` produktu" w najprostszy możliwy sposób (nota 4: nie
   przeinżynierować).
3. **`retail_product_id` bez API.** Kolumna i CHECK istnieją wg planu, ale
   `PantryItemCreateRequest` wymaga `product_id` i nie przyjmuje produktu
   sklepowego: bez tabeli `retail_products` nie da się zwalidować odwołania,
   a przyjęcie niesprawdzonego id wpuściłoby do bazy wiszące referencje.
   Odczyt jest już przygotowany (LEFT JOIN, `product_name: null` — test
   `test_pozycja_tylko_z_produktem_sklepowym_przechodzi`).
4. **`get_household_state` NIE korzysta z wyjątku D16.** Widoczność listy
   `/pantry` daje ADMIN-owi `true()` (i tak ma być — macierz 08_TESTING §4), ale
   stan domowy dla silnika zakupowego liczy się z `select_own_household`, czyli
   BEZ tego wyjątku. Inaczej lista zakupów administratora odjęłaby spiżarnie
   wszystkich rodzin w instancji — cichy, trudny do zauważenia błąd w B10.
   Granica jest ta sama, co dla `/households/my` (04_API §3 pkt 2a): zasób
   zaadresowany „moją rodziną" pokazuje ADMIN-owi jego rodzinę. Pilnuje tego
   `test_stan_domowy_admina_to_JEGO_dom_a_nie_wszystkie_rodziny`.
5. **Bez audytu.** `audit_entries` obejmuje wg 02_DOMAIN §12 wartości
   odżywcze, weryfikację, import i operacje admina — nie stan spiżarni. Zgodnie
   z tym, co robią `recipes` i `planning` (też nie audytują), pantry nie
   zapisuje wpisów. Jeśli właściciel chce śledzić „kto zmienił ilość", to
   osobna decyzja i osobny batch.

### Odstępstwa od karty

- **Composables (`usePantryQuery`, `usePantryMutations`) NIE powstały.** Karta
  je wymienia, ale jej własna korekta R2 (sekcja „Expected files") mówi wprost,
  że katalogu `src/composables/` nie ma i nie trzeba go tworzyć — wzorcem od
  B04 jest `src/api/<moduł>.ts` + `useQuery`/`useMutation` w komponencie.
  Poszedłem za korektą R2.
- **Usunięcie pozycji: każdy członek rodziny (D17 ZATWIERDZONE 2026-08-21).**
  Pierwsza wersja szła za 02_DOMAIN §3.1 pkt 2 i macierzą 08_TESTING §4
  („usunięcie: właściciel lub ADMIN"), czyli dawała członkowi rodziny 403;
  agent zgłosił to jako D17 z rekomendacją „zostawić". **Właściciel rozstrzygnął
  odwrotnie** i to jest stan wdrożony: `delete_item` nie ma bramki
  właścicielskiej, a `HouseholdScopedQuery` nie ma `assert_can_manage` w ogóle —
  encja „zawsze household" nie ma reguły właścicielskiej, bo nie ma też scope'u
  do zmiany. Wyjątek dopisany do **02_DOMAIN §3.1 pkt 2** i **08_TESTING §4**,
  żeby dokumenty nie kłamały. Granica bez zmian: cudza rodzina = 404.
- **`PantryItemCreateRequest.product_id` wymagane** — patrz decyzja 3 wyżej.
  Walidacja „co najmniej jedno z product/retail" jest w bazie (CHECK, test
  `test_check_wymaga_produktu_kanonicznego_albo_sklepowego`), a nie w serwisie,
  bo przez API drugiego wariantu nie da się dziś wprowadzić.

### Review (`/code-review`, xhigh) — 10 ustaleń

**Naprawione w tym commicie (6):**

1. `PantryService.get_item()` nie miało konsumenta (API nie ma `GET /pantry/{id}`) —
   metoda usunięta, a test anty-IDOR przepięty na ścieżki, które FAKTYCZNIE
   istnieją (`update_item` i `delete_item` na cudzej pozycji + na nieistniejącym
   id, z asercją, że wiersz przeżył).
2. `await session.refresh(item)` przed `_view()` w `create_item`/`update_item` —
   jedno zapytanie za dużo na każdą mutację. **Uwaga, pułapka warta zapamiętania
   przez kolejne batche**: samo usunięcie `refresh` NIE wystarcza i `task check`
   to złapał (3 czerwone testy API: `amount` wracało jako `"0"` zamiast
   `"0.000"`). Sesja ma `expire_on_commit=False`, więc po commicie w mapie
   tożsamości siedzi encja z wartościami sprzed zapisu, a kolejny SELECT
   zwraca TĘ SAMĄ instancję zamiast wiersza z bazy — odpowiedź gubi skalę
   kolumny NUMERIC(10,3). Rozwiązanie: `_view()` czyta z
   `.execution_options(populate_existing=True)` (ten sam wzorzec, co
   `RecipesService.list_recipes`), czyli jedno zapytanie ZAMIAST dwóch i
   wartości z bazy. Serwis, który po zapisie zwraca ilości NUMERIC, musi zrobić
   jedno z dwojga: `refresh` albo `populate_existing`.
3. Te same dwa `outerjoin` w `_visible()` i `_view()` — wyciągnięte do
   `_with_product(statement)`, żeby join retail z B09 dokładało się w jednym
   miejscu i lista nie rozjechała się ze szczegółem.
4. `openEdit` rzutował trzypolowy literał na `Product` z `generated.ts`
   (`as Product`) — kłamstwo typu, którego TS już nie sprawdza. Edycja nie
   zmienia produktu, więc zamiast wyłączonego pickera pokazuje teraz nazwę
   produktu tylko do odczytu (`pantry-edited-product`), a draft trzyma
   `{ name, measureKind }` bez żadnego rzutowania. Nowy test:
   „edycja pokazuje produkt tylko do odczytu i zapisuje PATCH-em".
5. `PantryItemRead` miał `ConfigDict(from_attributes=True)`, choć router składa
   go polami — `model_validate(item)` i tak by się wysypało na `product_name`.
   Flaga usunięta, docstring tłumaczy dlaczego.
6. `isEmpty` jako funkcja wołana dwa razy w szablonie → `computed` (oba
   komponenty pozycji).

**Przyjęte świadomie, NIE naprawione (4)** — z uzasadnieniem:

7. **`HouseholdScopedQuery` powiela ~40 z 82 linii `ScopedQuery`** (`__init__`,
   `select_visible`, `get_or_404`, `assert_can_manage`). Wspólna baza wymagałaby
   przebudowy `ScopedQuery` — kodu fundamentu z B03, z którego korzystają
   recipes, planning i szablony — a bound `ScopedT: ScopedMixin` trzeba by
   rozluźnić, bo `PantryItem` nie ma kolumny `scope`. To realny dług
   (poprawka w jednym bliźniaku nie trafi do drugiego), ale refaktor fundamentu
   jest poza zakresem tego batcha. **Follow-up do R3** — oba docstringi
   wskazują teraz na siebie nawzajem, żeby rozjazd był widoczny.
8. **`PantryItemCard.vue` i `PantryItemRow.vue` są niemal identyczne** (różnią
   się układem i tym, czy lokalizacja i notatka idą osobno, czy razem). Jeden
   komponent z propsem `variant` byłby prostszy, ale karta batcha wymienia oba
   pliki wprost w „Expected files" — nie zmieniam kontraktu karty na własną
   rękę. Do rozważenia w R3.
9. **„Dziś" liczone raz przy montowaniu strony** (`const today = isoDate(new Date())`),
   więc karta PWA zostawiona otwarta przez noc pokazuje wczorajsze progi
   plakietek do czasu przeładowania. Naprawa wymaga tykającego źródła czasu —
   nowy mechanizm, nie poprawka; do R3 albo do B12 (PWA), które i tak dotknie
   cyklu życia aplikacji.
10. **`date.today()` w routerze to strefa serwera, progi na froncie to strefa
    przeglądarki.** Kontener nie ustawia `TZ`, więc między północą a 2:00 czasu
    polskiego filtr `expires_within_days` widzi inny dzień niż plakietki.
    Ten sam wzorzec ma już `nutrition/router.py` (ustalenie R2: „czas wchodzi
    parametrem"), więc to dług CAŁEJ aplikacji, a nie wpadka B08 — rozstrzygnąć
    globalnie w R3 (albo ustawić `TZ` w compose, albo przyjmować datę klienta).

### Follow-upy (poza zakresem tego batcha)

1. **B09 (albo R3): FK `pantry_items.retail_product_id` → `retail_products`
   RESTRICT.** B08 zmergował się pierwszy, więc constraint dopina batch drugi —
   instrukcja z gotowym `op.create_foreign_key` jest w karcie B09 §Context.
2. **Rozszerzenie formularza spiżarni o produkt sklepowy** — po B09
   (karta B08 §Out of Scope: B10 albo R3).
3. **Paginacja widoku spiżarni.** Strona pobiera 100 pozycji (`limit`) i nie ma
   przycisku „więcej" — tak samo jak `ProduktyPage` (50). Przy realnej
   spiżarni to wystarcza, ale to dług do rozstrzygnięcia w R3 razem z resztą
   list.
4. **Filtr „tylko kończące się" jest zero-jedynkowy** (7 dni). Jeśli właściciel
   zechce wybór horyzontu (3/7/14 dni), API już to potrafi
   (`?expires_within_days=`) — brakuje tylko kontrolki.

### Pytania do właściciela

- **D17 — ZAMKNIĘTE 2026-08-21: usuwa KAŻDY CZŁONEK RODZINY.** Właściciel
  odrzucił rekomendację agenta („zostawić autora wpisu") na rzecz spójności
  domenowej: spiżarnia jest jednym stanem domowym, więc „kto dodał" jest
  informacją, a nie przywilejem. Wdrożone w tym samym commicie razem
  z wyjątkami w 02_DOMAIN §3.1 pkt 2 i 08_TESTING §4. Innych pytań nie ma.
