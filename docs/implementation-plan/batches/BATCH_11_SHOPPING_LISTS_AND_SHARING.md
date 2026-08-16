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
- Profile sklepów `store_category_order` (B09); `PantryService` (B08) —
  metoda dodawania/zwiększania pozycji (Completion notes B08).
- `LeftoverBadge`, `ShoppingItemRow` (jeśli powstał w B10 — sprawdzić),
  rate-limiter slowapi skonfigurowany dla `/auth/login` (B02).

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
- Rozszerzenie blokady usuwania sklepu (z B09): store referencowany przez
  `shopping_lists.store_id` → 409 z `used_in` (Cross-Batch Impact B09).

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
- `backend/tests/api/test_shopping_lists_api.py`
- `backend/tests/api/test_public_lists_api.py` (komplet §2.9)
- `backend/tests/integration/test_accept_to_pantry.py`
- `frontend/src/pages/zakupy/ListaZakupowPage.vue` (zastępuje placeholder)
- `frontend/src/pages/public/PublicznaListaPage.vue`
- `frontend/src/components/domain/{ShoppingItemRow.vue,ShareListDialog.vue}`
- `frontend/src/composables/{useShoppingLists.ts,usePublicList.ts}`
- `frontend/src/styles/print.css` (lub `@media print` w komponencie)
- `frontend/e2e/shopping-list-sharing.spec.ts`
- zależność npm: `qrcode` (+ typy)

Zmieniane: `backend/app/main.py` (public router + rate limiter),
konfiguracja slowapi, serwis stores z B09 (rozszerzenie blokady usuwania),
`frontend/src/router/index.ts` (`/l/:token` poza guardem i shellem),
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

- [ ] Endpointy list + PATCH pozycji (checked/already_have, `checked_at`)
- [ ] Sortowanie wg profilu sklepu + wybór sklepu na liście
- [ ] share POST/DELETE (token, expiry, revoke) + rozszerzenie blokady sklepu
- [ ] Publiczne GET/PATCH: 404/410, zero PII (biała lista), rate limit
- [ ] Maskowanie tokenów w logach
- [ ] `accept_to_pantry` przez `PantryService`
- [ ] Testy API §2.9 w komplecie + macierz uprawnień + integration
- [ ] `ListaZakupowPage` (sekcje, checkboxy 48 px, optimistic, resztki, already_have)
- [ ] Wariant print
- [ ] `ShareListDialog` (link/QR/Web Share/odwołaj)
- [ ] `PublicznaListaPage` poza shellem + ekran 410
- [ ] Testy frontend + E2E core flow 3
- [ ] PROGRESS.md + aktualizacja karty B12

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `alembic heads` = jedna głowa (migracje tylko jeśli dotyczy)
- [ ] Acceptance Criteria 1–9 sprawdzone ręcznie lub testem
- [ ] Test białej listy pól odpowiedzi publicznej zielony
- [ ] Rate limit zweryfikowany testem (429)
- [ ] Log z requestu publicznego nie zawiera tokenu (sprawdzone ręcznie)
- [ ] E2E: odhaczenie na `/l/{token}` w kontekście bez sesji przechodzi
- [ ] Dokumentacja + karta B12 zaktualizowane
- [ ] Commit `batch(11): …`, `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
