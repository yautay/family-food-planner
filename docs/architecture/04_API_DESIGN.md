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
U      /plan/days/{date}                   — GET + PUT (tytuł, widoczność);
                                             DELETE świadomie NIE ISTNIEJE —
                                             patrz „Cykl życia dnia planu"
U      /plan/days/{date}/meals, /plan/meals/{id}, /plan/items/{id}
                                           — POST|PATCH|DELETE posiłków i pozycji
U      /plan/items/{id}/fit-to-target      — PROPOZYCJA mnożnika (nic nie zapisuje)
U      /plan/copy                          — {source, target(s), what: day|meal|block}
                                             block: {source_from, source_days,
                                             repeat_each, target_start} — model 2+2+2
U      /templates/days /templates/weeks    — CRUD + POST {id}/instantiate
U      /cycles                             — CRUD + POST {id}/apply (rotacja A→B→C)
U      /pantry                             — CRUD pozycji, filtr ważności

U      /shopping/round-configs             — konfiguracja tur (preset seed);
                                             PATCH|DELETE /{id}
U      /shopping/generate                  — POST → preview (nic nie zapisuje
                                             poza shopping_generations:preview)
U      /shopping/generations/{id}          — GET odtwarza preview z params;
                                             DELETE = miękkie odrzucenie
U      /shopping/generations/{id}/resolve  — decyzje niejasności
U      /shopping/generations/{id}/finalize — tworzy listy per tura
U      /shopping/lists                     — GET listy (?status=active|expired,
                                             paginacja); GET|PATCH|DELETE /{id}
                                             (PATCH: nazwa i sklep = profil
                                             sortowania sekcji)
U      /shopping/lists/{id}/items/{item_id} — PATCH `checked` / `already_have`
                                             (`checked_at` ustawia serwer)
U      /shopping/lists/{id}/share          — POST token / DELETE revoke
U      /shopping/lists/{id}/accept-to-pantry — POST: odhaczone pozycje do spiżarni
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

### Cykl życia dnia planu (stan faktyczny, ustalenie REVIEW R3)

Dzień planu NIE jest zasobem tworzonym i usuwanym wprost:

- wiersz `plan_days` powstaje **implicite** przy pierwszym posiłku
  (`POST /plan/days/{date}/meals`) albo jawnie przez `PUT /plan/days/{date}`,
  gdy użytkownik nadaje dniowi tytuł lub zmienia widoczność,
- `GET /plan/days/{date}` dla daty bez planu zwraca **pusty dzień, nie 404** —
  interfejs nie musi wiedzieć, czy wiersz istnieje,
- usunięcie ostatniego posiłku **sprząta pusty dzień bez tytułu**
  (`PlanningService.delete_meal`). Dzień z tytułem zostaje, bo tytuł jest jawną
  decyzją użytkownika. Bez tego sprzątania niewidzialny wiersz trzymał
  `household_id` z FK RESTRICT i blokował usunięcie rodziny (dług U17 z R2),
- `DELETE /plan/days/{date}` świadomie **nie istnieje**: nie ma go co usuwać
  poza tytułem, a ten zdejmuje `PUT` z `title: null`.

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
2c-ter. **Zakupy: podgląd nie jest zasobem, tylko WYNIKIEM** (BATCH_10).
   `POST /shopping/generate` zapisuje wyłącznie `shopping_generations`
   (`status=preview`, pełne wejście silnika w `params`) i zwraca policzony
   podgląd; `GET /shopping/generations/{id}` liczy go PONOWNIE z `params`, więc
   jest deterministyczny i nie zależy od tego, czy plan zmienił się w
   międzyczasie. `POST …/resolve` zmienia w `params` wyłącznie decyzje
   użytkownika (`already_have`, wybór wariantu, odłożone niejasności) i odświeża
   katalog wariantów sklepowych — pole pominięte zostaje bez zmian, pole podane
   ZASTĘPUJE cały zbiór. `POST …/finalize` tworzy listy per tura i przestawia
   status na `final`; nierozstrzygnięty bloker daje 409 z powodami w
   `details.issues`. `DELETE …/{id}` jest MIĘKKIE (status `discarded`, D10);
   generacji `final` nie da się ani odrzucić, ani zmienić (409).
   `use_pantry` domyślnie `false` — stan domowy odejmujemy wyłącznie na jawne
   życzenie (02_DOMAIN §8). Konwencja `shopping_weekday`: **0 = poniedziałek**,
   6 = niedziela (jak `date.weekday()`), `null` = tura bez ustalonego dnia.
   `GET /shopping/round-configs` przy PUSTEJ konfiguracji zasiewa edytowalny
   preset z 02_DOMAIN §9.2 (seed danych, nie hardcode).
2d. Data bez zapisanego planu to 200 z pustym dniem (`id: null`), nie 404:
   otwarcie kalendarza na wolnej dacie jest normalną sytuacją, a nie błędem.
   Ten sam wyjątek NIE dotyczy pojedynczych encji (przepis, produkt) — tam
   brak zasobu pozostaje 404 (BATCH_06).
3. `/public/lists/{token}`: lookup wyłącznie po pełnym tokenie (unique
   index), `410 Gone` po wygaśnięciu/odwołaniu z przyjaznym komunikatem,
   odpowiedź zawiera tylko: nazwę listy, pozycje (label, ilość, kategoria,
   checked), expires_at. Żadnych nazwisk, emaili, id użytkowników.
3a. **Stan faktyczny po BATCH_11** — pięć rzeczy wiążących dla kolejnych
   endpointów publicznych:
   - **404 i 410 mają IDENTYCZNĄ treść** („Ta lista zakupowa już wygasła lub
     została usunięta." — ADR-010). Rozróżnienie zostaje w KODZIE odpowiedzi
     dla API; użytkownik nie dowiaduje się, czy token kiedykolwiek istniał.
     Kod `gone` (410) doszedł do `STATUS_TO_CODE` w `app/core/errors.py`
     razem z wyjątkiem `GoneError`.
   - Token w ścieżce jest walidowany kształtem (43 znaki base64url), więc skaner
     dostaje 422 PRZED zapytaniem do bazy.
   - Odpowiedź publiczna to jawna BIAŁA LISTA pól (`PublicListRead` /
     `PublicListItemRead`, bez `from_attributes`): `{name, expires_at,
     items: [{id, label, amount, unit, category_name, checked, leftover_amount,
     already_have, packages_count, package_size}]}`. Dokładny zbiór kluczy
     asercjonuje `tests/api/shopping/test_public_lists_api.py::test_public_response_has_no_pii`.
   - Publiczny PATCH przyjmuje WYŁĄCZNIE `{checked}` (`extra="forbid"`), więc
     każde inne pole to 422, a nie ciche pominięcie.
   - Rate limit 60/min/IP WSPÓLNY dla całej ścieżki publicznej
     (`limiter.shared_limit`, scope `public-lists`) — nie per endpoint; limiter
     jest wstrzykiwany do buildera routera z `create_app` (jak w `/auth`).
3b. **Sortowanie pozycji listy zakupowej robi SERWER** (BATCH_11).
   `GET /shopping/lists/{id}` zwraca `sections` — sekcje per kategoria już
   w kolejności przejścia po sklepie: najpierw kategorie z profilu sklepu
   (`store_category_order`, B09) w jego kolejności, potem pozostałe wg globalnego
   `product_categories.position`; w sekcji pozycje `already_have` na końcu.
   Frontend tej kolejności NIE liczy — inaczej ta sama lista wyglądałaby inaczej
   na ekranie, na wydruku i pod publicznym linkiem. Sklep przypisuje się PATCH-em
   listy (`store_id` / `clear_store`), a nie przy finalizacji generacji.

## 4. Wersjonowanie i kompatybilność

Prefiks `/api/v1` stały; zmiany łamiące w obrębie MVP dozwolone do
Review 4 (aplikacja bez użytkowników zewnętrznych), po wdrożeniu
produkcyjnym — polityka addytywna. OpenAPI diff sprawdzany w Review.
