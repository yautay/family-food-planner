# BATCH_11 — SHOPPING_LISTS_AND_SHARING

Klasa: SHOP · Zależności: BATCH_10 (bez bramek decyzyjnych) · Rozmiar: **L**

## Goal

Po tym batchu lista zakupowa jest pełnoprawnym narzędziem w sklepie:
strona listy z sekcjami per kategoria w kolejności profilu wybranego
sklepu, dużymi checkboxami (~48 px) z trwałym stanem i optimistic update,
plakietkami resztek i wyszarzonymi pozycjami „mam już w domu"; wariant
do druku; udostępnianie przez publiczny link z tokenem 256-bit (expiry,
revoke, QR, Web Share API) — publiczna strona działa bez logowania,
bez PII, z odhaczaniem; opcjonalna akcja „przyjmij zakupy do spiżarni".

## Context

Co już istnieje (stan po B10):
- Tabele `shopping_lists` + `shopping_list_items` w komplecie (03 §8),
  w tym `public_token`, `token_revoked`, `expires_at`, `checked`,
  `checked_at`, `already_have`, `leftover_amount`, `from_pantry_amount`,
  `label` (render bez słowników); finalize tworzy listy per tura.
- Placeholder route `/zakupy/listy/:id` (B10, Implementation Notes pkt 5)
  — ten batch go ZASTĘPUJE.
- Profile sklepów `store_category_order` — **DOSTARCZONE przez B09**
  (migracja `0011`). Do sortowania listy służy
  `StoresService.category_order(store_id) -> list[CategoryOrderEntry]`
  (`app/modules/catalog/stores_service.py`; `CategoryOrderEntry` to frozen
  dataclass `category_id` / `category_name` / `position`). Trzy rzeczy wiążące:
  1. Profil zawiera WYŁĄCZNIE kategorie do niego dopisane — kategorie spoza
     profilu idą na koniec wg globalnego `product_categories.position`
     (tak samo jak dla listy bez sklepu). To nie jest brak danych, to kontrakt.
  2. `position` jest ciągłe od 0 i bez duplikatów, bo PUT podmienia całą
     kolejność, a serwis liczy pozycje z indeksów listy — funkcja sortująca
     może na tym polegać.
  3. Sklep bez profilu (`items == []`) jest dozwolonym stanem, nie błędem.
- Spiżarnia (B08): akcja „przyjmij zakupy do spiżarni" woła
  `PantryService.create_item(actor=..., payload=PantryItemCreateRequest(...))`
  — B08 NIE dostarczył osobnej metody „dodaj albo zwiększ". Świadomie: reguła
  scalania (czy 500 g mąki z zakupów dolewa się do istniejącego wiersza, czy
  zakłada nowy z własną datą ważności) jest decyzją domenową PRZYJĘCIA
  ZAKUPÓW, nie spiżarni — pozycje różnią się datą ważności i lokalizacją,
  więc ślepe sumowanie zgubiłoby jedno i drugie. Ten batch albo woła
  `create_item` per odhaczona pozycja (rekomendacja: nowy wiersz = nowa
  partia), albo dokłada do `PantryService` metodę `receive_purchase(...)`
  z jawnie opisaną regułą scalania i własnymi testami. Uwaga na jednostki:
  `create_item` przyjmuje ilość na osi produktu (g/ml/szt.) i sam ustala
  `amount_unit` z `measure_kind`; ilość ujemna jest niemożliwa (422).
- `LeftoverBadge` — **ISTNIEJE** (`frontend/src/components/domain/LeftoverBadge.vue`,
  props `{ leftover: string | null, unit }`; resztka 0 ma osobny, pozytywny
  komunikat „Bez resztki"). `ShoppingItemRow` NIE powstał — B10 renderuje
  pozycje podglądu inline w `ZakupyPreview.vue`, więc wiersz listy zakupowej
  projektuje ten batch od zera.
- rate-limiter slowapi skonfigurowany dla `/auth/login` (B02).

### Stan faktyczny po B10 — sześć rzeczy wiążących dla tego batcha

1. **Kształt odpowiedzi `finalize`** (`FinalizeResponse`): `{items: [...],
   total}`, gdzie każdy element to `ShoppingListRead` = `{id, generation_id,
   name, round_name, store_id, expires_at, items: [ShoppingListItemRead]}`.
   `ShoppingListItemRead` = `{id, category_id, product_id, retail_product_id,
   label, needed_amount, amount_unit, packages_count, package_size,
   leftover_amount, already_have, from_pantry_amount, checked, position}`.
   **`public_token` NIE JEST wystawiany w żadnej odpowiedzi B10** i pilnuje tego
   test — ten batch jest pierwszym, który go generuje i zwraca.
   `name` ma format `Zakupy 07.01-13.01.2030`, `round_name` to nazwa tury
   (tekst, nie FK — lista historyczna nie zmienia treści po edycji konfiguracji
   tur), `expires_at` = moment finalizacji + 7 dni (`LIST_TTL_DAYS`).
2. **Liczniki referencji są już zarejestrowane** przez `shopping/service.py`:
   produkt kanoniczny, wariant sklepowy i SKLEP (`_lists_using_store` —
   `shopping_lists.store_id` ma SET NULL, więc bez licznika lista po cichu
   traciłaby profil sortowania). Ten batch ich NIE dokłada; jeśli dołoży nowe
   ścieżki referencji (np. lista ręczna), rozszerza istniejące funkcje.
3. **`shopping_lists.store_id` nikt jeszcze nie ustawia.** Finalize zostawia
   `NULL`, bo tura nie ma sklepu. Przypisanie sklepu do listy (i sortowanie po
   profilu) należy do tego batcha — razem z decyzją, czy sklep wybiera się przy
   finalizacji, czy na stronie listy (rekomendacja: na stronie listy, bo to
   decyzja „gdzie dziś jadę", a nie właściwość generacji).
4. **Pozycje pokryte w całości spiżarnią NIE trafiają na listę** (nie ma czego
   kupić), ale pozycje oznaczone `already_have` — owszem, z ustawioną flagą.
   Widok listy musi je pokazać inaczej (wyszarzone/odhaczone), a nie ukryć.
5. **Listy nie da się (jeszcze) USUNĄĆ** — B10 nie dał na to endpointu, a
   `DELETE /shopping/generations/{id}` jest miękki (status `discarded`) i nie
   kasuje list. **Konsekwencja dla E2E**: spec zakupów B10 pracuje na produktach
   SEEDU, bo własny produkt zablokowałby się na FK RESTRICT z pozycji listy na
   zawsze. Gdy ten batch dołoży `DELETE /shopping/lists/{id}`, warto dopisać
   `clearShoppingLists` do `e2e/cleanup.ts` PRZED `clearProducts` i wtedy specy
   zakupowe mogą wrócić do własnych danych.
6. **Trasa-zaślepka** `/zakupy/listy/:id` (nazwa trasy `zakupy-lista`) istnieje
   i jest już linkowana z podsumowania finalizacji na `/zakupy`
   (`data-testid="created-list-link-<id>"`). Ten batch podmienia WYŁĄCZNIE
   `component` w `src/router.ts` — nowego wpisu nawigacji nie dokłada.

Wymagane lektury przed startem:
- `docs/architecture/02_DOMAIN_MODEL.md` §9.4–9.5 (lista, publiczny link),
  §8 (przyjęcie zakupów do spiżarni), §13 pkt 5 (niezmiennik zero PII)
- `docs/architecture/03_DATABASE_DESIGN.md` §8, §12 (retencja — D10)
- `docs/architecture/04_API_DESIGN.md` §2–3 (`/shopping/lists`, `/public/*`)
- `docs/adr/ADR-010-publiczne-tokeny.md` (WIĄŻĄCY kontrakt tokenów)
- `docs/architecture/07_SECURITY_DESIGN.md` §5 (tokeny publiczne:
  rate limit 60/min/IP, maskowanie w logach), §3 (CSRF a publiczne PATCH-e)
- `docs/architecture/06_UIUX_PRINCIPLES.md` §4 pkt 5 (widok listy),
  §5 (mobile — widok krytyczny), §6 (druk)
- `docs/architecture/08_TESTING_STRATEGY.md` §2.9, §3 (core flow 3), §4
- `docs/implementation-plan/02_DECISIONS.md` D10 (retencja: nic nie
  usuwamy automatycznie; wygasłe listy zostają w DB — 03 §12)

## Stages

1. **Backend — listy**: odczyt/edycja list i pozycji (PATCH checked /
   already_have), sortowanie wg profilu sklepu, wybór sklepu na liście;
   rozszerzenie blokady usuwania sklepu; testy.
2. **Backend — sharing**: POST/DELETE share (token, expiry), publiczne
   GET + PATCH z rate limitem, 410, zero PII, maskowanie tokenów; testy §2.9.
3. **Backend — spiżarnia**: akcja „przyjmij zakupy do spiżarni"; testy.
4. **Frontend — strona listy**: `ListaZakupowPage` (mobile-first, druk).
5. **Frontend — udostępnianie + strona publiczna**: dialog share
   (link/QR/Web Share), `PublicznaListaPage` poza shellem.
6. **E2E + docs**: pełny core flow 3, PROGRESS.md, propagacja do B12/R3.

## Database / migrations

**Brak nowych tabel** — schemat 03 §8 w całości utworzony w B10.
Dozwolone: migracja uzupełniająca brakujący unique index na
`public_token` (jeśli B10 go nie założył) — sprawdzić przed startem;
numer = pierwszy wolny, `down_revision` = `alembic heads`.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/shopping/lists` | GET | U | listy widoczne wg scope (`?status=active\|expired`, paginacja) |
| `/api/v1/shopping/lists/{id}` | GET | U | lista + pozycje posortowane (patrz „Sortowanie") |
| `/api/v1/shopping/lists/{id}` | PATCH | U | nazwa, `store_id` (profil sortowania) |
| `/api/v1/shopping/lists/{id}` | DELETE | U | usunięcie ręczne (właściciel/ADMIN — macierz 08 §4); D10: nic nie znika automatycznie |
| `/api/v1/shopping/lists/{id}/items/{item_id}` | PATCH | U | `checked` (ustawia `checked_at` server-side), `already_have` |
| `/api/v1/shopping/lists/{id}/share` | POST | U | generuje `public_token` = `secrets.token_urlsafe(32)`; body `{expires_in_days}` (default 7 — ADR-010) ustawia `expires_at`; zwraca pełny URL `/l/{token}` |
| `/api/v1/shopping/lists/{id}/share` | DELETE | U | revoke: `token_revoked=true` |
| `/api/v1/shopping/lists/{id}/accept-to-pantry` | POST | U | z pozycji ODHACZONYCH tworzy/zwiększa pozycje spiżarni (`PantryService`); akcja jawna, jednorazowa — 02 §8 |
| `/api/v1/public/lists/{token}` | GET | P | bez auth; treść listy bez PII; 404 nieistniejący token; **410** wygasły/odwołany |
| `/api/v1/public/lists/{token}/items/{item_id}` | PATCH | P | WYŁĄCZNIE `{checked}`; te same reguły 404/410 |

Zasady:
- **Sortowanie pozycji**: sekcje per kategoria w kolejności
  `store_category_order` sklepu listy; kategorie spoza profilu — na końcu
  wg globalnego `product_categories.position`; lista bez sklepu — cała
  kolejność globalna. W sekcji: `already_have` na dole, reszta po `position`.
- **Odpowiedź publiczna** (ADR-010, 04 §3, niezmiennik 02 §13.5):
  WYŁĄCZNIE `{name, items: [{id, label, amount, unit, category_name,
  checked, leftover_amount, already_have}], expires_at}`. Żadnych
  `owner_user_id`, `household_id`, nazwisk, emaili — schemat Pydantic
  z jawną białą listą pól (nie `from_orm` pełnego modelu).
- Publiczny PATCH: wyłączony z CSRF (autoryzuje token w URL — 07 §3),
  rate limit; lookup tylko po pełnym tokenie (unique index, 07 §5).
  **Wyjątek CSRF jest już gotowy** — B02 wpisał prefiks `/api/v1/public/`
  do `CSRF_EXEMPT_PREFIXES` w `app/core/middleware.py`; router publiczny
  musi więc siedzieć dokładnie pod tym prefiksem (nic do zmiany w middleware).
  Rate limit: limiter slowapi jest w `app.state.limiter`, tworzony
  w `create_app()` i wstrzykiwany do buildera routera (wzór:
  `build_auth_router(settings, limiter)`); handler 429 w kształcie 04_API §1
  jest już zarejestrowany (`register_rate_limit_handler`).
- Rozszerzenie blokady usuwania sklepu (z B09): store referencowany przez
  `shopping_lists.store_id` → 409 z `used_in` (Cross-Batch Impact B09).
  **Mechanizm jest gotowy — trzeba go tylko użyć**: `stores_service.py`
  eksportuje `register_store_reference_finder(finder)` z sygnaturą
  `finder(session, store_id) -> Sequence[UsedInRef]`, a `delete_store` sumuje
  wyniki wszystkich zarejestrowanych liczników z własnym (warianty retail).
  Rejestracja przy imporcie modułu, wzorzec `pantry/service.py`. Bez wpisu
  usunięcie sklepu z listami skończy się 409 z PUSTĄ listą „Używane w:" —
  FK `shopping_lists.store_id` ma `SET NULL`, więc drugiej linii obrony tu
  nie ma i lista po cichu straciłaby profil sortowania.
  **Analogicznie dla pozycji list**: FK do `retail_products` wymaga
  `retail_service.register_retail_reference_finder`, inaczej 409 przy usuwaniu
  wariantu sklepowego wyjdzie bez listy użyć.

## Frontend

- **`ListaZakupowPage.vue`** (`/zakupy/listy/:id`, widok 5; zastępuje
  placeholder z B10):
  - nagłówek: nazwa, tura, wybór sklepu (select → PATCH; przesortowanie);
  - sekcje per kategoria ze **sticky nagłówkami** (mobile, 06 §5);
  - `ShoppingItemRow`: **checkbox ~48 px**, label, ilość/opakowania
    (`formatAmount`), `LeftoverBadge` („Zostanie: 150 g");
    odhaczenie = **optimistic PATCH** (rollback przy błędzie + toast);
  - pozycje `already_have`: wyszarzone, na dole swojej sekcji;
  - panel akcji: **Udostępnij**, **Drukuj** (`window.print()`),
    **Przyjmij zakupy do spiżarni** (dialog: „Doda odhaczone pozycje
    do spiżarni" + potwierdzenie), Usuń listę (dialog konsekwencji).
- **Druk** (06 §6): `@media print` — czarno-biały, checkboxy jako `☐`,
  kategorie jako nagłówki, bez nawigacji/panelu akcji/kolorów.
- **Dialog udostępniania** (`ShareListDialog.vue`): wybór ważności
  (7 dni default / 1 dzień / 30 dni / data), POST share → pełny link;
  akcje: **kopiuj link** (clipboard), **„Pokaż QR"** (desktop —
  dialog z QR renderowanym kliencko przez `qrcode` z npm, ADR-010),
  **Web Share API** (mobile, `navigator.share` z fallbackiem do kopiuj);
  gdy token aktywny: widoczny stan „Link aktywny do …" + **„Odwołaj
  link"** (ADR-010 — kontrolka zawsze widoczna przy aktywnym linku).
- **`PublicznaListaPage.vue`** (`/l/:token`) — **POZA `AppShell`**,
  poza guardem auth (05 §3): minimalny layout (logo tekstowe, nazwa
  listy, sekcje, checkboxy 48 px z PATCH bez logowania, informacja
  o ważności); **410 → przyjazny ekran „Ta lista zakupowa już wygasła
  lub została usunięta."** (dokładnie ten komunikat — ADR-010);
  404 → ten sam ekran neutralny. Zero danych rodziny na stronie.
- Composables: `useShoppingLists`, `useListItemsMutations` (optimistic
  z `checked_at`), `usePublicList` (klient bez CSRF/credentials
  dla `/public/*`).

## Security

- Token: `secrets.token_urlsafe(32)` (256 bit), unique index, lookup po
  pełnym tokenie; expiry + revoke; **410** po wygaśnięciu/odwołaniu (ADR-010).
- **Zero PII w odpowiedzi publicznej** — test asercji pól (biała lista);
  niezmiennik 02 §13.5.
- **Rate limit 60/min/IP** na `/public/*` (slowapi) — 429 `rate_limited`.
- **Maskowanie tokenów w logach**: filtr structlog — ścieżka logowana jako
  `/public/lists/***` (07 §5); tokeny nigdy w logach ani w komunikatach błędów.
- Uprawnienia tokenu: odczyt + PATCH `checked` JEDNEGO pola — nic więcej
  (próba PATCH innych pól → 422/ignorowane; test).
- share/revoke: członek rodziny listy HOUSEHOLD może (rodzina sobie ufa,
  02 §3.1); DELETE listy: właściciel/ADMIN (macierz 08 §4).
- Publiczne PATCH-e poza CSRF, mutacje zalogowane — z CSRF (07 §3).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE, SKILL-SEC
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **API — tokeny (08 §2.9 W KOMPLECIE)**:
  - `test_public_get_valid_token_returns_list`,
  - `test_public_get_expired_token_410`,
  - `test_public_get_revoked_token_410`,
  - `test_public_get_unknown_token_404`,
  - `test_public_response_has_no_pii` — asercja DOKŁADNEGO zbioru kluczy
    odpowiedzi (biała lista pól, w tym zagnieżdżone pozycje),
  - `test_public_patch_checkbox_works_and_sets_checked_at`,
  - `test_public_patch_other_fields_rejected`,
  - `test_public_rate_limit_429`,
  - `test_share_generates_43_char_urlsafe_token_and_expiry`,
  - `test_revoke_then_reshare_generates_new_token`.
- **API — listy**: macierz uprawnień 08 §4 (odczyt/edycja HOUSEHOLD,
  delete tylko właściciel/ADMIN, anty-IDOR 404); PATCH checked/already_have;
  sortowanie wg profilu sklepu (zmiana sklepu przesortowuje; kategorie
  spoza profilu na końcu); DELETE sklepu użytego w liście → 409.
- **Integration**: `accept_to_pantry` — tworzy/zwiększa pozycje spiżarni
  z odhaczonych (nieodhaczone pominięte), ilości z `packages_count ×
  package_size` (fallback `needed_amount`); stan checkboxów trwały po
  ponownym pobraniu; wygasła lista zostaje w DB (D10), tylko token
  przestaje działać.
- **Unit (backend)**: funkcja sortująca pozycje wg profilu sklepu
  (przypadki: pełny profil, częściowy, brak sklepu).
- **Frontend (vitest)**: optimistic toggle z rollbackiem; wyszarzenie
  i pozycja `already_have`; render `☐` w trybie print (snapshot klasy
  print); `ShareListDialog` — stany brak linku / aktywny / odwołany.
- **E2E (core flow 3 z 08 §3)**: generacja → jawne pytanie o spiżarnię →
  preview z resztkami → finalizacja → otwarcie listy → udostępnij →
  otwarcie `/l/{token}` w **nowym kontekście bez sesji** → odhaczenie
  pozycji bez logowania → stan widoczny po odświeżeniu u zalogowanego;
  dodatkowo: revoke → publiczna strona pokazuje ekran wygaśnięcia.

## Acceptance Criteria

1. Strona listy: sekcje per kategoria w kolejności profilu wybranego
   sklepu; zmiana sklepu na liście przesortowuje sekcje; checkboxy ~48 px
   z optimistic update i trwałym stanem (przetrwa odświeżenie).
2. Pozycje „mam już w domu" wyszarzone na dole sekcji; resztki widoczne
   jako plakietka „Zostanie: …" przy każdej pozycji z opakowaniami.
3. Wydruk (`window.print`): czarno-biały, `☐`, nagłówki kategorii,
   bez nawigacji.
4. Udostępnienie generuje link `/l/{token}` (43 znaki base64url) z wybraną
   ważnością (default 7 dni); QR i Web Share/kopiuj działają; „Odwołaj
   link" natychmiast unieważnia token.
5. Publiczna strona działa bez logowania: pokazuje listę, pozwala
   odhaczać; wygasły/odwołany token → ekran „Ta lista zakupowa już
   wygasła lub została usunięta." (410); odpowiedź publiczna nie zawiera
   żadnych danych poza treścią listy (test białej listy pól).
6. `/public/*` ma rate limit 60/min/IP; tokeny maskowane w logach.
7. „Przyjmij zakupy do spiżarni" dodaje odhaczone pozycje do spiżarni
   po jawnym potwierdzeniu; akcja opcjonalna, nic nie dzieje się w tle.
8. E2E core flow 3 zielony end-to-end na realnym stacku.
9. `task check` zielony; `alembic heads` = jedna głowa.

## Out of Scope

- Offline/PWA (IndexedDB, kolejka odhaczeń, LWW po `checked_at`,
  `/l/:token` offline) → BATCH_12 (ADR-009) — ten batch tylko persystuje
  `checked_at` server-side.
- Eksport listy do PDF (06 §4 pkt 5 — „later").
- Bulk delete starych list (D10 — rewizja przy R4).
- Edycja pozycji listy (dodawanie/zmiana ilości po finalizacji) — lista
  jest wynikiem generacji; zmiany = nowa generacja (rewizja w R3, jeśli
  potrzeba ręcznych pozycji).
- Powiadomienia o wygasających linkach.

## Expected files/modules

Nowe:
- `backend/app/modules/shopping/{public_router.py,sharing.py}` (lub
  rozszerzenie `router.py`/`service.py` — wg konwencji z B10)
- `backend/app/core/logging_filters.py` (maskowanie `/public/lists/***`,
  jeśli nie istnieje)
- `backend/tests/api/shopping/{__init__.py,test_shopping_lists_api.py}`
- `backend/tests/api/shopping/test_public_lists_api.py` (komplet §2.9)
- `backend/tests/integration/shopping/{__init__.py,test_accept_to_pantry.py}`
- `frontend/src/pages/zakupy/ListaZakupowPage.vue` (zastępuje placeholder)
- `frontend/src/pages/public/PublicznaListaPage.vue`
- `frontend/src/components/domain/{ShoppingItemRow.vue,ShareListDialog.vue}`
- `frontend/src/api/{shoppingLists.ts,publicList.ts}` (korekta R2: katalogu
  `src/composables/` w repo nie ma — wzorcem jest `src/api/<moduł>.ts`
  + `useQuery`/`useMutation` w komponencie, ADR-007)
- `frontend/src/styles/print.css` (lub `@media print` w komponencie)
- `frontend/e2e/shopping-list-sharing.spec.ts`
- zależność npm: `qrcode` (+ typy)

Zmieniane: `backend/app/main.py` (public router + rate limiter),
konfiguracja slowapi, serwis stores z B09 (rozszerzenie blokady usuwania),
`frontend/src/router.ts` (`/l/:token` poza guardem i shellem; korekta R2 — router to jeden plik, nie katalog),
`frontend/src/api/{queryKeys.ts,generated.ts}`, `backend/tests/factories.py`.

## Implementation Notes

1. Publiczny klient frontendu: `/public/*` bez cookies/CSRF — osobny
   lekki wrapper, nie rozbudowa `client.ts` o tryby warunkowe.
2. `PublicznaListaPage` importować leniwie (osobny chunk) — strona ma być
   lekka i nie ciągnąć shella; B12 zrobi ją offline-capable.
3. `checked_at` ustawiać server-side (UTC) — B12 oprze na tym LWW;
   nie przyjmować `checked_at` od klienta w tym batchu.
4. Ilości w `accept_to_pantry`: decyzja implementującego (kupione =
   `packages_count × package_size` vs `needed_amount`, jednostki retail
   piece → g przez `piece_weight_g`) — uzasadnić w Completion notes;
   duplikaty produktów w spiżarni: zwiększać istniejącą pozycję.
5. 404 vs 410 na stronie publicznej: użytkownik widzi TEN SAM neutralny
   ekran (nie ujawniamy, czy token kiedykolwiek istniał); rozróżnienie
   tylko w kodach API (testy).
6. Rate limiter: nie obejmować limitem 60/min endpointów zalogowanych;
   klucz per IP (za reverse proxy — `X-Forwarded-For` wg konfiguracji
   z B01/B17; sprawdzić middleware).
7. QR: generować z pełnego URL produkcyjnego (origin z `window.location`).

## Cross-Batch Impact

- **BATCH_12 (PWA/offline)**: lista i `/l/:token` offline; kolejka PATCH
  z LWW po `checked_at` (ADR-009) — utrzymać semantykę `checked_at`
  i `label`; zaktualizować kartę B12 o kształt odpowiedzi publicznej.
- **R3**: zweryfikuje pełny moduł shopping (B08–B11), w tym
  `/security-review` ścieżki publicznej; zgłosić w PROGRESS ewentualną
  potrzebę ręcznych pozycji listy (Out of Scope pkt 4).
- **BATCH_13**: statystyki mogą czytać historię list — wygasłe listy
  zostają w DB (D10), nie zmieniać retencji.

## Implementation checklist

- [x] Endpointy list + PATCH pozycji (checked/already_have, `checked_at`)
- [x] Sortowanie wg profilu sklepu + wybór sklepu na liście
- [x] share POST/DELETE (token, expiry, revoke) + rozszerzenie blokady sklepu
      (licznik referencji sklepu zarejestrował już B10 — ten batch dodał TEST 409)
- [x] Publiczne GET/PATCH: 404/410, zero PII (biała lista), rate limit
- [x] Maskowanie tokenów w logach (`mask_path` z B02 obejmuje `/api/v1/public/lists/*`
      — nowy `logging_filters.py` NIE był potrzebny)
- [x] `accept_to_pantry` przez `PantryService` (+ nowa metoda `receive_purchase`)
- [x] Testy API §2.9 w komplecie + macierz uprawnień + integration
- [x] `ListaZakupowPage` (sekcje, checkboxy 48 px, optimistic, resztki, already_have)
- [x] Wariant print
- [x] `ShareListDialog` (link/QR/Web Share/odwołaj)
- [x] `PublicznaListaPage` poza shellem + ekran 410
- [x] Testy frontend + E2E core flow 3
- [x] PROGRESS.md + aktualizacja karty B12

## Verification checklist

- [x] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [x] `alembic heads` = jedna głowa (BEZ nowej migracji — unique index na
      `public_token` założyła już `0012`, head zostaje `0012`)
- [x] Acceptance Criteria 1–9 sprawdzone testem albo E2E
- [x] Test białej listy pól odpowiedzi publicznej zielony
- [x] Rate limit zweryfikowany testem (429, licznik WSPÓLNY dla `/public/*`)
- [x] Log z requestu publicznego nie zawiera tokenu (sprawdzone ręcznie na logach
      kontenera `app`: ścieżka wychodzi jako `/api/v1/public/lists/***`)
- [x] E2E: odhaczenie na `/l/{token}` w kontekście bez sesji przechodzi
- [x] Dokumentacja + karta B12 zaktualizowane
- [x] Commit `batch(11): …`, `git status` czysty w zakresie batcha

## Completion notes

**Wykonane (2026-08-22).** Lista zakupowa jest narzędziem w sklepie: backend
zwraca ją POSORTOWANĄ w sekcje, publiczny link działa bez logowania i bez PII,
a zakupy da się jednym kliknięciem przyjąć do spiżarni.

Backend (bez nowej migracji — head zostaje `0012`):

- `app/modules/shopping/lists_service.py` — DRUGI serwis modułu (życie gotowej
  listy). Ścieżka publiczna ma tu własne metody bez `User` i bez `ScopedQuery`.
- `app/modules/shopping/sorting.py` — czyste funkcje kolejności sekcji
  (profil sklepu → reszta wg globalnej pozycji kategorii; `already_have` na dół).
- `app/modules/shopping/{lists_router,public_router}.py` — `/shopping/lists/*`
  oraz `/api/v1/public/lists/*` (limit 60/min/IP WSPÓLNY dla ścieżki).
- `app/core/errors.py += GoneError` (410, kod `gone`).
- `app/core/logging.py += MaskPublicTokenFilter` + `install_access_log_filter()`.
- `PantryService.receive_purchase` — przyjęcie zakupów z jawną regułą scalania.

Frontend: `ListaZakupowPage` (sekcje sticky, checkbox 48 px, optimistic toggle
z rollbackiem, `StorePicker` z create-in-context, dialogi „przyjmij do spiżarni"
i „usuń listę"), `ShoppingItemRow` (współdzielony ze stroną publiczną, w druku
`☐`), `ShareListDialog` (ważność 1/7/30 dni, kopiuj/QR/Web Share, „Odwołaj
link"), `PublicznaListaPage` (`/l/:token`, poza shellem, ekran wygaśnięcia),
`api/{shoppingLists,publicList}.ts`, `assets/print.css`, `meta.anonymous`
w routerze.

### Decyzje wykonawcze (uzasadnienia)

1. **Ilość przyjmowana do spiżarni = KUPIONA** (`packages_count * package_size`),
   a bez wariantu sklepowego `needed_amount` (karta, Implementation Notes pkt 4).
   Do domu wraca całe opakowanie, więc resztka też jest stanem domowym —
   przyjmowanie `needed_amount` zaniżałoby spiżarnię dokładnie o wyliczoną
   resztkę już przy pierwszych zakupach. Jednostek nie przeliczamy:
   `package_size` jest z definicji na osi produktu kanonicznego (niezmiennik B09).
2. **Reguła scalania duplikatów**: dolewamy do pozycji tego produktu BEZ daty
   ważności (najstarszej, gdy jest ich kilka), a gdy takiej nie ma — zakładamy
   nową. Wiersz z datą ważności to KONKRETNA partia, więc dolanie skłamałoby
   o dacie; wiersz bez daty to stan luzem. Zrealizowane jako
   `PantryService.receive_purchase` (wariant „albo" z karty §Context), z własnymi
   testami integracyjnymi — `create_item` per pozycja rozsypywałby spiżarnię na
   duplikaty przy każdych zakupach.
3. **Sklep wybiera się NA LIŚCIE** (rekomendacja z karty §Context pkt 3):
   „gdzie dziś jadę" to decyzja momentu zakupów, nie właściwość generacji.
4. **Sekcje składa SERWER** (`sections` w odpowiedzi), nie przeglądarka —
   inaczej ta sama lista miałaby inną kolejność na ekranie, na wydruku i pod
   publicznym linkiem (trzy różne implementacje tej samej reguły).
5. **`checked_at` to moment OSTATNIEJ decyzji o checkboxie, także odznaczenia.**
   Wybrane pod LWW z ADR-009 (B12 musi wiedzieć, która decyzja jest młodsza,
   a nie tylko kiedy coś odhaczono). Klient go nie przysyła.
6. **Odwołanie linku nie zeruje `public_token`** — nowy losowy token nie może
   (choćby teoretycznie) wskrzesić starego linku.
7. **`GoneError` zamiast 404 dla wygasłego tokenu**, ale z IDENTYCZNYM
   komunikatem: kod odpowiedzi jest dla API, treść dla człowieka.
8. **Limit `/public/*` jako `shared_limit`** (scope `public-lists`) —
   `limiter.limit` liczy per trasa, więc ścieżka miałaby faktycznie 120/min/IP.

### Odstępstwa od karty

- **Nowy plik `app/core/logging_filters.py` NIE powstał** (karta dopuszczała go
  warunkowo). Maskowanie ścieżki istniało od B02 w `app/core/logging.py`, więc
  brakującą warstwę (access log Uvicorna) dołożyłem tam, gdzie mieszka
  `mask_path` — osobny plik rozdzielałby jedną odpowiedzialność na dwa miejsca.
- **`frontend/src/styles/print.css` → `frontend/src/assets/print.css`** —
  katalogu `styles/` w repo nie ma, `assets/` trzyma `tailwind.css`.
- **Rozszerzenie blokady usuwania sklepu było już zrobione w B10** (licznik
  `_lists_using_store` zarejestrowany). Ten batch dołożył brakujący TEST 409
  z `used_in`, a nie kod.
- **Poza „Zmieniane": `frontend/vite.config.ts`** (`server.watch.ignored` dla
  `test-results/` i `playwright-report/`). Playwright zapisuje artefakty wewnątrz
  katalogu frontendu, czyli pod watcherem Vite, więc każdy zapis w trakcie
  przebiegu wywoływał PEŁNE przeładowanie strony i gubił stan UI (spec listy
  tracił w połowie otwarty panel udostępniania). To naprawa infrastruktury
  testowej, bez której AC 8 nie dało się spełnić — nie zmiana zachowania aplikacji.
- **Poza „Zmieniane": `frontend/src/layouts/AppShell.vue`** — nawigacja dostała
  `print:hidden` (a `main` reset paddingu w druku). Strona listy nie ma jak
  ukryć shella, pod którym jest osadzona; alternatywa (selektory po
  `data-testid` w `print.css`) byłaby krucha.

### Ustalenia review (naprawione w tym commicie)

`/code-review` (SKILL-REVIEW) i `/security-review` (SKILL-SECREV) na diffie.
Dwa ustalenia POWAŻNE, oba naprawione z testem regresyjnym:

1. **Access log Uvicorna logował PEŁNY token** (`docker compose logs app`).
   `mask_path` maskowało tylko nasz log; Uvicorn formatuje linię sam
   z `record.args`. Naprawa: `MaskPublicTokenFilter` na loggerze
   `uvicorn.access`, testy `tests/unit/test_logging.py`, weryfikacja ręczna na
   realnym stacku. To była realna droga do cudzej listy dla każdego z dostępem
   do logów — 07_SECURITY §5 wymagał tej warstwy wprost.
2. **ADMIN „przyjmując zakupy" dolewał do CUDZEJ spiżarni.**
   `receive_purchase` szukało kandydata przez `select_visible`, które dla
   ADMIN-a zwraca `true()` (D16). Naprawa: `select_own_household` (ten sam
   warunek, co `get_household_state`) + test
   `test_admin_nie_dolewa_do_cudzej_spizarni`, sprawdzony jako CZERWONY przed
   naprawą. „Co mamy w domu" jest przynależnością, nie widocznością.

Cztery ustalenia mniejsze, też naprawione: PATCH listy padał na
`MissingGreenlet` (`updated_at` z `onupdate` jest po commicie wygaszone →
`refresh`); klucz szczegółu listy był dzieckiem klucza indeksu w TanStack Query
(invalidacja kasowała świeżą odpowiedź PATCH-a); limit `/public/*` był liczony
per endpoint; śmieciowe id w URL-u dawało wieczny spinner zamiast „nie
znaleziono".

### Follow-upy (poza zakresem, do R3)

1. **`accept_to_pantry` nie jest atomowe** — każda pozycja to osobny commit
   (`receive_purchase` commituje sam, jak reszta `PantryService`). W praktyce
   nieosiągalne (produkt pozycji chroni FK RESTRICT, więc nie ma na czym paść),
   ale przy dokładaniu walidacji do tej ścieżki trzeba to wziąć pod uwagę.
2. **Akcja „przyjmij zakupy" jest powtarzalna** — nie ma kolumny „już przyjęte",
   więc jedyną ochroną jest dialog potwierdzenia. Do oceny w R3 (alternatywa:
   znacznik na liście).
3. **Specy zakupowe wciąż pracują na produktach seedu**, mimo że
   `clearShoppingLists` już istnieje (karta §Context pkt 5 dopuszczała powrót do
   własnych danych). Zmiana specu B10 nie była konieczna do AC, a `clearProducts`
   po liście działa — do zrobienia przy okazji R3.
4. Dług z B10 bez zmian: dryf modelu `pantry_items.retail_product_id`
   (`alembic check`).

### Wyniki (realne)

`task check` exit 0: migrations-check (3), test-unit (303), test-int (229),
test-api (343), fe-test (296 w 32 plikach), typecheck (mypy 164 pliki + vue-tsc),
lint, format-check, fe-build. `alembic heads` = jedna głowa (`0012`).
E2E: dwa kolejne przebiegi 15/15 z identycznym wynikiem.

Uwaga wykonawcza dla następnych sesji: PRZERWANY przebieg `task check` zostawia
w bazie testowej tabelę `scoped_notes` (fixture nie dobiega do teardownu), a ta
zależy od typu `entity_scope` — kolejny przebieg wywala wtedy 5 testów migracji
i seedu („cannot drop type entity_scope", „Nieoczekiwany zestaw tabel"). To NIE
jest regresja: wystarczy usunąć tabelę z db-test albo pozwolić dobiec pełnemu
przebiegowi (`test_scope_matrix` sprząta ją na końcu).

### Pytania do właściciela

Brak — batch nie miał decyzji-bramek, a wszystkie rozstrzygnięcia mieściły się
w rekomendacjach karty (punkty 1–3 wyżej).
