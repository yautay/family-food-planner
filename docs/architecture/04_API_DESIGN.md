# 04 — Projekt API

REST pod `/api/v1`, JSON, cookie-session (ADR-003). OpenAPI generowane
przez FastAPI = kontrakt dla frontendu (typy TS generowane z OpenAPI
w tasku `task fe-types`). Ten dokument ustala konwencje i mapę zasobów;
szczegółowe schematy powstają w batchach i żyją w OpenAPI.

## 1. Konwencje

- **Błędy** — jeden kształt: `{"error": {"code": "string", "message":
  "po polsku, dla człowieka", "details": {...}}}`. Kody: `validation_error`
  (422), `not_found` (404), `forbidden` (403), `unauthorized` (401),
  `conflict` (409 — m.in. blokada usunięcia z listą użyć w `details.used_in`),
  `rate_limited` (429).
- **Paginacja** list: `?limit=` (default 50, max 200) `&offset=`;
  odpowiedź `{items, total}`. Wyszukiwanie: `?q=` (trigram po nazwie).
- **Kwoty/ilości**: stringi dziesiętne w JSON (`"12.5"`) — bez utraty
  precyzji NUMERIC; frontend używa parsera dziesiętnego, nie float, tam
  gdzie liczy (a liczy tylko prezentacyjnie).
- **Daty**: `YYYY-MM-DD`; timestampy ISO8601 UTC.
- Mutacje: POST (create), PUT (pełna podmiana), PATCH (częściowa), DELETE.
  Wszystkie niebezpieczne metody wymagają nagłówka CSRF (07_SECURITY §3).
- Wartości wyliczane (nutrition) zwracane w polu `nutrition`:
  `{kcal, protein_g, fat_g, carbs_g, fiber_g, sugars_g, glycemic_load,
  complete: bool, missing: ["produkt X: brak IG", ...]}`.

## 2. Mapa zasobów (kto: U=user zalogowany, A=admin, P=public token)

```
POST   /auth/login /auth/logout            — sesja (rate limit 5/min/IP)
GET    /auth/me                            — user + household + ustawienia UI
PATCH  /auth/me/ui-settings                — własne ustawienia UI (progi statusów, D9)
A      /admin/users, /admin/households     — CRUD kont i rodzin
U      /households/my, /households/my/profiles — rodzina + profile członków
U      /goals                              — cele żywieniowe (historia po valid_from)

U      /products                           — kanoniczne: lista/szukaj/CRUD*
A      /products/{id}/nutrition            — PUT wartości + IG (audit before/after)
A      /products/{id}/verify               — UNVERIFIED → VERIFIED (komplet wymagany)
U      /products/{id}/archive              — POST archiwizuj / DELETE przywróć
U      /products/{id}/unit-weights         — przeliczniki jednostek domowych
U      /categories, /stores, /stores/{id}/category-order
U      /retail-products                    — CRUD (?canonical_product_id=,
                                             ?store_id=, ?q=, ?include_archived=)
U      /retail-products/{id}/photo         — PUT (multipart) / DELETE zdjęcia
U      /tags

U      /recipes                            — CRUD, filtry: tag, tekst, czas,
                                             trudność, ocena, scope
U      /recipes/{id}/rating                — PUT własnej oceny
GET    /recipes/{id}?servings=2.5          — nutrition per porcja × mnożnik
U      /recipes/{id}/photo                 — POST (multipart) / DELETE zdjęcia
GET    /uploads/{path}                     — serving uploadów; POZA /api/v1,
                                             wymaga sesji (07_SECURITY §6)

U      /plan/days?from=&to=                — dni z posiłkami+pozycjami+nutrition
U      /plan/days/{date} (+meals, +items)  — CRUD; PATCH mnożników
U      /plan/items/{id}/fit-to-target      — PROPOZYCJA mnożnika (nic nie zapisuje)
U      /plan/copy                          — {source, target(s), what: day|meal|block}
                                             block: {source_from, source_days,
                                             repeat_each, target_start} — model 2+2+2
U      /templates/days /templates/weeks    — CRUD + POST {id}/instantiate
U      /cycles                             — CRUD + POST {id}/apply (rotacja A→B→C)
U      /pantry                             — CRUD pozycji, filtr ważności

U      /shopping/round-configs             — konfiguracja tur (preset seed)
U      /shopping/generate                  — POST → preview (nic nie zapisuje
                                             poza shopping_generations:preview)
U      /shopping/generations/{id}/resolve  — decyzje niejasności
U      /shopping/generations/{id}/finalize — tworzy listy per tura
U      /shopping/lists (+items PATCH check/already-have)
U      /shopping/lists/{id}/share          — POST token / DELETE revoke
P      /public/lists/{token}               — GET treść + PATCH check pozycji
                                             (rate limit, zero PII, 410 po expiry)

U      /import/pdf                         — upload → job; GET status/raport
U      /import/jobs/{id}/staged            — staged recipes+ingredients+issues
U      /import/jobs/{id}/resolve           — mapowania/porcje/decyzje
U      /import/jobs/{id}/approve|reject
U      /transfer/export                    — eksport własnych danych (JSON/ZIP)
A      /transfer/export?scope=instance     — pełny eksport instancji
A      /transfer/import                    — import z dry-run
A      /audit                              — przegląd dziennika
GET    /health                             — bez auth: {status, version}
```

\* tworzenie kanonicznego produktu: USER może (inline create, powstaje
UNVERIFIED); edycja wartości odżywczych i statusu weryfikacji: ADMIN.
**Fizyczne usunięcie produktu kanonicznego: wyłącznie ADMIN** (D13) i tylko
gdy produkt jest nieużywany — inaczej 409 z `details.used_in`. USER dostaje 403
z podpowiedzią archiwizacji. Mutacje `/categories`: ADMIN; odczyt: każdy.

## 3. Zasady autoryzacji w API

1. Wszystko poza `/health`, `/auth/login`, `/public/*` wymaga sesji.
2. Scope egzekwowany w serwisach (`ScopedQuery`), nie w routerach —
   router nie wie, czym jest household. **ADMIN widzi WSZYSTKIE encje ze scope
   także na ścieżkach użytkownika** (`ScopedQuery.visible_condition` zwraca mu
   `true()`) — decyzja właściciela **D16, zatwierdzona 2026-08-21**, zgodna
   z macierzą 08_TESTING §4, w której ADMIN ma 200 w każdym wierszu. Widoczność
   to jednak NIE to samo co prawo do zmiany: modyfikacja scope i usunięcie idą
   przez `assert_can_manage`, więc reguły właścicielskie zostają w mocy.
2a. Zasoby należące do rodziny bez kolumn scope (`member_profiles`) filtruje
   się porównaniem `household_id`; cudze i nieistniejące dają identyczne 404.
   `ScopedQuery` obowiązuje encje z kolumnami wzorca 03_DATABASE §4.
   **Tu ADMIN NIE jest wyjątkiem — i to nie jest niespójność z D16.** `/households/my`
   znaczy dosłownie „moja rodzina", więc pokazanie w niej cudzego profilu nie
   miałoby sensu; do cudzych rodzin ADMIN ma `/admin/households/*`. Granica jest
   więc taka: encja ze `ScopedMixin` (widoczność z własności i scope) → ADMIN
   widzi wszystko; zasób zaadresowany przez MOJĄ rodzinę → ADMIN widzi swoją.
   Test pilnujący tej granicy:
   `tests/api/test_households_my.py::test_admin_nie_dostaje_wyjatku_na_sciezce_uzytkownika`.
2b. Stan „użytkownik bez rodziny" jest legalny: `/households/my` zwraca 200
   z `household: null`, a nie 404. Operacje wymagające rodziny (utworzenie
   profilu, nadanie `scope=household`) kończą się 409 z instrukcją.
2c. Zasoby ZAGNIEŻDŻONE w encji ze scope (posiłki i pozycje planu) nie mają
   własnego scope — widoczność dziedziczą po rodzicu, a serwis sprawdza CAŁY
   łańcuch (`item → meal → day → warunek scope`), nie samo istnienie id.
   Cudze zagnieżdżone id daje 404, identycznie jak nieistniejące (BATCH_06).
2c-bis. Szablony i cykle to encje ze scope: cudzy PRYWATNY szablon daje 404
   także na AKCJACH (`instantiate`, `apply`), nie tylko na odczycie. Instancjacja
   i apply tworzą dni WYŁĄCZNIE jako własność wykonującego użytkownika (owner
   z sesji) — nie da się instancjować „na cudzy plan" (BATCH_07).
2d. Data bez zapisanego planu to 200 z pustym dniem (`id: null`), nie 404:
   otwarcie kalendarza na wolnej dacie jest normalną sytuacją, a nie błędem.
   Ten sam wyjątek NIE dotyczy pojedynczych encji (przepis, produkt) — tam
   brak zasobu pozostaje 404 (BATCH_06).
3. `/public/lists/{token}`: lookup wyłącznie po pełnym tokenie (unique
   index), `410 Gone` po wygaśnięciu/odwołaniu z przyjaznym komunikatem,
   odpowiedź zawiera tylko: nazwę listy, pozycje (label, ilość, kategoria,
   checked), expires_at. Żadnych nazwisk, emaili, id użytkowników.

## 4. Wersjonowanie i kompatybilność

Prefiks `/api/v1` stały; zmiany łamiące w obrębie MVP dozwolone do
Review 4 (aplikacja bez użytkowników zewnętrznych), po wdrożeniu
produkcyjnym — polityka addytywna. OpenAPI diff sprawdzany w Review.
