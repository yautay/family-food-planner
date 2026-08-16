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
- `backend/app/core/` — sesje, CSRF, `ScopedQuery` (mixin scope), deps.
- `frontend/src/components/domain/ProductPicker.vue` — command palette
  z inline create (wzorzec obowiązkowy, 05_FRONTEND §4).
- `frontend/src/components/domain/AmountInput.vue` — ilość + jednostka.
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

Nowe:
- `backend/app/modules/pantry/{__init__.py,models.py,schemas.py,service.py,router.py}`
- `backend/migrations/versions/<pierwszy_wolny>_pantry_items.py`
- `backend/tests/integration/test_pantry_service.py`
- `backend/tests/api/test_pantry_api.py`
- `frontend/src/pages/spizarnia/SpizarniaPage.vue`
- `frontend/src/components/domain/{PantryItemRow.vue,PantryItemCard.vue,ExpiryBadge.vue}`
- `frontend/src/composables/usePantry.ts`
- `frontend/e2e/pantry.spec.ts`

Zmieniane (⚠ = wspólne z B09):
- ⚠ `backend/app/main.py` (router), ⚠ `backend/tests/factories.py`
- ⚠ `frontend/src/api/queryKeys.ts`, ⚠ `frontend/src/api/generated.ts` (regen)
- ⚠ `frontend/src/router/index.ts`, ⚠ `frontend/src/components/AppShell.vue`

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

- [ ] Migracja `pantry_items` (up/down/up na kopii bazy, jedna głowa)
- [ ] Modele + schematy Pydantic (amount ≥ 0, stringi dziesiętne)
- [ ] `PantryService` (scope household, walidacje, `get_household_state`)
- [ ] Router `/pantry` + rejestracja w `main.py`
- [ ] Testy integration + API (w tym macierz uprawnień, anty-IDOR)
- [ ] `SpizarniaPage` + komponenty + composables + routing + nawigacja
- [ ] Pusty stan, dialogi potwierdzeń, `formatAmount`
- [ ] Testy frontend + E2E
- [ ] PROGRESS.md + propagacja Cross-Batch Impact do kart B10/B11

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `alembic upgrade head` + `downgrade -1` + `upgrade head` przechodzi;
      `alembic heads` = 1 głowa (także po ewentualnym merge'u z B09)
- [ ] Acceptance Criteria 1–6 sprawdzone ręcznie lub testem
- [ ] Testy anty-IDOR obecne i zielone
- [ ] Dokumentacja: PROGRESS.md, karty B10/B11 zaktualizowane
- [ ] Commit `batch(08): …`, `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
