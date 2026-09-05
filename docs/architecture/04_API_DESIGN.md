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
U      /stats/daily?from=&to=              — agregaty dzienne: wartości, cel
                                             z dnia, statusy + średnie zakresu
                                             (max 92 dni; nic nie cache'owane)
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
                                             (`checked_at` opcjonalne: brak =
                                             czas serwera, podane = LWW)
U      /shopping/lists/{id}/share          — POST token / DELETE revoke
U      /shopping/lists/{id}/accept-to-pantry — POST: odhaczone pozycje do spiżarni
                                             (idempotentne, `received_at`)
P      /public/lists/{token}               — GET treść + PATCH check pozycji
                                             (`checked_at` jw.; rate limit,
                                             zero PII, 410 po expiry)

U      POST /import/pdf                    — upload PDF → job (multipart, 25 MB,
                                             sniffing `%PDF`); parsowanie SYNCHRONICZNE,
                                             odpowiedź 201 z `parse_report` — DOSTARCZONE w B15
U      GET  /import/jobs                   — lista własnych importów (?limit&offset)
U      GET  /import/jobs/{id}              — szczegóły + `parse_report`; cudzy job 404
U      DELETE /import/jobs/{id}            — usuwa job, staging i plik (tylko
                                             uploaded/parsed/failed; inaczej 409)
U      GET  /import/jobs/{id}/staged       — stan review: dania, składniki, uwagi,
                                             blokady, `ai_available` — DOSTARCZONE w B16
U      POST /import/jobs/{id}/resolve      — decyzje review (mapowania, porcje,
                                             scalenia, zamknięcie uwag); pierwsze
                                             wywołanie przestawia job na `in_review`
U      POST /import/jobs/{id}/ai-suggest   — propozycje AI; 503 bez klucza API,
                                             limit 10/min (ADR-011, D5)
U      POST /import/jobs/{id}/approve      — tworzy przepisy/produkty/przeliczniki;
                                             409 z `details.blockers` przy blokadach
U      POST /import/jobs/{id}/reject       — kasuje staging i plik, job → `rejected`
U      POST /transfer/export               — eksport własnych danych → ZIP
A      POST /transfer/export?scope=instance — pełny eksport instancji → ZIP
U/A    POST /transfer/import               — upload ZIP → raport DRY-RUN
U/A    POST /transfer/import/{id}/apply    — zastosowanie z decyzjami kolizji
A      /audit                              — przegląd dziennika
GET    /health                             — bez auth: {status, version}
```

\* tworzenie kanonicznego produktu: USER może (inline create, powstaje
UNVERIFIED); edycja wartości odżywczych i statusu weryfikacji: ADMIN.
**Fizyczne usunięcie produktu kanonicznego: wyłącznie ADMIN** (D13) i tylko
gdy produkt jest nieużywany — inaczej 409 z `details.used_in`. USER dostaje 403
z podpowiedzią archiwizacji. Mutacje `/categories`: ADMIN; odczyt: każdy.

### Review importu PDF (stan faktyczny, BATCH_16)

Pięć endpointów wyżej obsługuje JEDEN ekran i mają wspólne własności, których
mapa nie mieści:

1. **`resolve` i `staged` zwracają TEN SAM kształt** (`StagedJobResponse`):
   job, dania ze składnikami i uwagami, uwagi całego pliku, lista blokad
   i flaga `ai_available`. Dzięki temu każda decyzja to jedno żądanie, po
   którym UI ma komplet stanu — bez dociągania i bez liczenia czegokolwiek
   po swojej stronie.
2. **`blockers` w odpowiedzi to dokładnie to, co `approve` odesłałby w 409.**
   Jedna lista, dwa miejsca użycia — nieczynny przycisk nie może obiecywać
   czegoś innego niż serwer.
3. **Kalorie są PER POSIŁEK** (`recipes[].meal`): `pdf_kcal` w jadłospisie
   opisuje posiłek, a posiłek bywa dwudaniowy (01_PDF_AUDIT §3.1, errata §9.1).
   Pole `reason` niesie powód, dla którego wyliczenie nie było możliwe
   (brak mapowań, produkty bez wartości) — zamiast fałszywego rozjazdu.
4. **`ai-suggest` jest idempotentne i nieinwazyjne**: nadpisuje wyłącznie
   propozycje (`suggested_product_id`, `match_kind`, `confidence`) składników
   BEZ potwierdzenia. Mapowanie zatwierdzone przez człowieka jest nietykalne
   (ADR-011). Brak `ANTHROPIC_API_KEY` ⇒ **503** z kodem `service_unavailable`
   i komunikatem po polsku — to wspierany tryb pracy, nie awaria.
5. **Statusy rozstrzygnięte zamykają ścieżkę**: `resolve`/`ai-suggest`/
   `approve`/`reject` na jobie `approved` albo `rejected` dają **409**.
   `GET /staged` działa dalej — zatwierdzony staging zostaje jako metadane
   walidacyjne (03_DATABASE §12).

Scope przepisów wybiera się RAZ dla całego joba (`POST /approve` z polem
`scope`), nie per danie — piętnaście selectów na jednym ekranie nie dodałoby
niczego poza klikaniem.

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

### Statystyki dzienne (`GET /stats/daily`, stan faktyczny BATCH_13)

Endpoint jest w module `planning`, bo agregaty są POCHODNĄ planu i celów —
w bazie nie ma i nie będzie ani jednej kolumny z wynikiem (niezmiennik
02_DOMAIN §13.2). Kontrakt odpowiedzi:

- `days[]` ma element dla KAŻDEJ daty zakresu. Dzień bez planu to **luka**:
  `has_plan: false`, `nutrition: null`, wszystkie `status` na `null`. Zero kcal
  byłoby inną informacją („zjadł nic") i zaniżałoby średnią.
- **Dzień istniejący, ale bez posiłków** (po ustaleniu R3 zostaje w bazie tylko
  dzień z tytułem) liczy się jako brak planu — nie ma z czego policzyć wartości.
- `days[].goal` to cel z NAJWIĘKSZYM `valid_from <= day` razem z tą datą; UI
  rysuje z tego funkcję schodkową i niczego nie interpoluje.
- `summary.avg` to średnia dzienna z dni Z PLANEM (`days_with_plan` jako
  dzielnik) albo `null`, gdy takich dni nie ma. `summary.goal_progress` używa
  tego samego schematu `GoalMetricRead`, co kafelki planu dnia: `target` jest
  ŚREDNIĄ celów dni z planem (cel mógł się zmienić w środku zakresu), liczoną
  per pole tylko z dni, które cel tego pola miały.
- Zakres: `from <= to`, maksimum **92 dni**; przekroczenie to 422
  `validation_error`. Endpoint jest read-only, więc GET nie potrzebuje CSRF.

### Format eksportu transfer v1 (stan faktyczny BATCH_14)

Plik eksportu to **ZIP** z dwoma rodzajami wpisów — i niczym więcej (każdy inny
wpis import odrzuca, 07_SECURITY §6):

- `export.json` — nagłówek + sekcje danych,
- `photos/<ścieżka względna z bazy>` — zdjęcia przepisów i wariantów sklepowych.
  Miniatur NIE ma: import re-enkoduje oryginał tym samym pipeline'em, co upload,
  i generuje je od nowa.

Nagłówek: `{schema_version: 1, app_version, exported_at, scope: "user"|"instance"}`.
Niezgodna `schema_version` to **422** z komunikatem po polsku („Plik pochodzi
z nowszej lub innej wersji aplikacji…"), nigdy 500. Migracji formatu między
wersjami nie ma, dopóki istnieje tylko `v1`.

`data` to sekcje per tabela w **STAŁEJ KOLEJNOŚCI** (`transfer/schemas.py::SECTION_ORDER`),
która jest jednocześnie kolejnością importu — wymuszają ją FK z RESTRICT
(ustalenie REVIEW R3): słowniki → produkty kanoniczne → sklepy → warianty retail
→ konta i rodziny (tylko `instance`) → profile i cele → przepisy → plan →
szablony i cykle → spiżarnia → tury → generacje → listy → dziennik (tylko
`instance`). Test `test_referencje_wskazuja_sekcje_wczesniejsza_w_kolejnosci`
pilnuje, że żadna referencja nie wskazuje sekcji wchodzącej PÓŹNIEJ.

Trzy reguły treści:

1. **ID w pliku to referencje WEWNĘTRZNE.** Import nigdy ich nie wstawia — buduje
   mapę stary→nowy. Referencja bez pokrycia w tym samym pliku przerywa import
   (422), bo surowy identyfikator wskazałby w nowej bazie przypadkową encję.
2. **Liczby są stringami dziesiętnymi** (§1, ADR-008). Dotyczy też payloadów
   szablonów, które są JSONB — float po drodze zmieniłby ilości w przepisach.
3. **Referencje wewnątrz payloadów szablonów** (`recipe_id`, `product_id`,
   `member_profile_id`) i `week_cycles.template_ids` remapuje import, bo baza
   ich nie pilnuje. Pozycja, której nie da się przemapować, WYPADA z payloadu
   razem z ostrzeżeniem w raporcie.

**Czego w pliku nie ma i nie będzie**: `users.password_hash` (plik eksportu nie
może być materiałem do credential stuffingu — po imporcie instancji ADMIN nadaje
hasła przez `PATCH /admin/users/{id}`), `sessions`, `shopping_lists.public_token`
i `token_revoked` (żywy token dostępu bez logowania, ADR-010 — lista wraca bez
linku i udostępnia się ją ponownie), `created_at`/`updated_at` poza
`audit_entries`, `recipes.import_job_id` (job importu PDF nie jest przenoszony).

**Zakres `user`** obejmuje encje NALEŻĄCE do konta (`ScopedQuery.owned_condition`
— przynależność, nie widoczność, więc ADMIN nie dostaje tu całej instancji) plus
te wiersze słowników globalnych, do których się odwołują. Plik jest przez to
samowystarczalny, ale nie jest kopią katalogu instancji. Oceny przepisów wychodzą
wyłącznie WŁASNE — cudza ocena jest opinią konkretnej osoby i po imporcie nie ma
komu jej przypisać. `shopping_generations` wchodzą tylko w stanie `final` albo
`discarded`: `params` to wersjonowane WEJŚCIE silnika (przenoszone DOSŁOWNIE,
ustalenie R3), a generacja `preview` jest szkicem, którego finalizacja po
imporcie tworzyłaby pozycje z identyfikatorami instancji źródłowej.
`user_nutrition_goals` wychodzą w CAŁEJ historii razem z `valid_from` — bez tego
`/stats/daily` po cichu przepisałby statusy dni sprzed zmiany celu (ustalenie B13).

**DRY-RUN (`POST /transfer/import`)** zapisuje paczkę w scratchu (`uploads/transfer`,
sprzątanym po `apply` i po 24 h) i zwraca `{import_id, to_create: {sekcja: liczba},
collisions: [{entity, source_id, name, existing_id, existing_name, default}],
warnings, photos}` — **bez ani jednego zapisu w bazie**, także bez wpisu
w dzienniku. Kolizje wykrywane są po kluczu naturalnym: `normalized_name`
(produkty), `name` (kategorie, sklepy, tagi, rodziny), `code` (składniki
odżywcze), `email` (konta) oraz `name` w obrębie encji NALEŻĄCYCH do
importującego (przepisy, szablony). Kolizja e-maila i kodu składnika nie ma
wariantu „kopia" — import zawsze reużywa istniejącego wiersza i ostrzega.

**APPLY (`POST /transfer/import/{import_id}/apply`)** przyjmuje `{decisions:
[{entity, source_id, action}]}` (`use_existing` domyślnie, `create_copy` tworzy
kopię z sufiksem „(import)" i spójnym `normalized_name`) i wykonuje CAŁOŚĆ
w jednej transakcji: błąd w środku to zero zmian w bazie, a zdjęcia zapisane po
drodze są kasowane ręcznie. Paczka należy do konta, które ją wgrało — cudzy
`import_id` daje **404**, identycznie jak nieistniejący. Import zostawia wpis
`transfer.import` w dzienniku (liczby i decyzje, nigdy treść encji).

Trzy zachowania przy powtórnym imporcie WŁASNEGO pliku na to samo konto:
`plan_days` **scala się** z istniejącym dniem po `UNIQUE(owner_user_id, day)`;
wiersze niosące FAKT o encji nadrzędnej (`product_unit_weights`,
`product_nutrient_values`, `recipe_ratings`, `user_nutrition_goals`) wchodzą
`ON CONFLICT DO NOTHING`; a **zawartość wiersza REUŻYTEGO zostaje nietknięta**
(decyzja **D22**, wdrożona w REVIEW R4). Pozostałe konflikty UNIQUE kończą się
**409** z instrukcją, nie 500.

„Zawartość" znaczy sekcje-dzieci kompozycji — te, których wiersz ma w bazie FK
`ON DELETE CASCADE` do rodzica: składniki i oceny przepisu, posiłki dnia planu,
pozycje posiłku, rozkłady porcji, pozycje listy zakupowej, przeliczniki i
wartości mikro produktu. Reużyty przepis NIE dostaje drugiego kompletu
składników, a reużyty dzień planu — drugiego kompletu posiłków; bez tej reguły
pętla eksport→import podwajała je przy każdym przebiegu (zmierzone w B16:
1536 składników w daniu o trzech). Referencja do SŁOWNIKA (produkt kanoniczny,
kategoria, tag, sklep) dzieckiem NIE jest — reużycie produktu nie ma prawa
skasować składnika, który go używa. Raport DRY-RUN liczy to tak samo jak zapis,
więc `to_create` nie obiecuje wierszy, których `apply` nie utworzy.

**Czego ta reguła NIE robi**: wiersz bez klucza naturalnego (wariant sklepowy,
profil członka, pozycja spiżarni, konfiguracja tury, generacja, lista, szablon,
cykl) nie ma tożsamości, po której import mógłby go rozpoznać — drugi import
tworzy jego drugą kopię i tak ma być („utwórz kopię" to jedyna sensowna
semantyka dla wiersza, którego nie da się utożsamić). Osobną sprawą, wskazaną
przez D22 i NIEROZSTRZYGNIĘTĄ, jest to, czy scalenie dnia planu ma pozostać
milczące, czy stać się jawną decyzją przy kolizji.

## 3. Zasady autoryzacji w API

1. Wszystko poza `/health`, `/auth/login`, `/public/*` wymaga sesji.
2. Scope egzekwowany w serwisach (`ScopedQuery`), nie w routerach —
   router nie wie, czym jest household. **ADMIN widzi WSZYSTKIE encje ze scope
   także na ścieżkach użytkownika** (`ScopedQuery.visible_condition` zwraca mu
   `true()`) — decyzja właściciela **D16, zatwierdzona 2026-08-21**, zgodna
   z macierzą 08_TESTING §4, w której ADMIN ma 200 w każdym wierszu. Widoczność
   to jednak NIE to samo co prawo do zmiany REGUŁ WŁAŚCICIELSKICH: modyfikacja
   scope i usunięcie idą przez `assert_can_manage`. **Edycję TREŚCI ADMIN ma**
   (rozszerzenie D16 z 2026-09-05) — patrz 07_SECURITY §4 razem z ryzykiem,
   które właściciel przy tym świadomie przyjął.
2-bis. **Widoczność nie wybiera CELU ZAPISU** (ustalenie REVIEW R4, 2026-09-05).
   Dzień planu nie ma id w URL-u — adresuje go DATA — więc `PlanningService`
   ma jeden resolver „który dzień dla tej daty", z którego korzystał zarówno
   odczyt, jak i `PUT /plan/days/{date}`, `POST /plan/days/{date}/meals`
   i instancjacja szablonu. Przy `visible_condition` (ADMIN → `true()`)
   administrator BEZ własnego dnia na daną datę trafiał w najstarszy wiersz
   dowolnego użytkownika z dowolnej rodziny: posiłek lądował w cudzym planie,
   a `PUT` kasował tytuł i przestawiał `scope` na `private`. Od R4 resolver ma
   dwa tryby — odczyt zostaje przy `visible` (D16 bez zmian), zapis idzie po
   `owned_condition`, które dla nie-ADMIN-a jest DOKŁADNIE tym samym warunkiem,
   więc członek rodziny nadal dopisuje do wspólnego dnia (B07). Tą samą granicą
   objęte jest `demand_rows`: lista zakupowa ADMIN-a nie ma prawa powstać
   z planów cudzych rodzin — po stronie spiżarni ta zasada obowiązuje od R3.
   Test: `tests/api/planning/test_plan_api.py::test_admin_nie_dopisuje_do_cudzego_dnia_planu`.
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
   checked), expires_at. Żadnych nazwisk, emaili, id użytkowników — ani
   `received_at`: osoba z linkiem nie ma nic wiedzieć o spiżarni rodziny
   (D19, pilnuje tego asercja dokładnego zbioru kluczy w
   `tests/api/shopping/test_public_lists_api.py`).
2e. **Odhaczanie pozycji i LWW (BATCH_12, ADR-009).** PATCH pozycji — prywatny
   i publiczny — przyjmuje opcjonalne `checked_at` (ISO8601, WYMAGANA strefa
   czasowa; naiwna data to 422). Reguły, wspólne dla obu ścieżek:
   - pole pominięte = zachowanie sprzed B12, czyli znacznik z zegara serwera;
   - znacznik STARSZY niż zapisany w bazie zostawia stan bez zmian i zwraca
     **200 z aktualną pozycją** (klient przyjmuje stan serwera, nie ponawia);
   - znacznik z przyszłości ponad 5 minut jest przycinany do czasu serwera —
     inaczej telefon z rozjechanym zegarem zabetonowałby pozycję;
   - powtórka tego samego żądania NIE przesuwa znacznika (idempotencja) — na
     tym stoi ponawianie z kolejki offline po utracie odpowiedzi.
   Uprawnienia tokenu publicznego się przez to nie poszerzają: nadal da się
   zmienić wyłącznie `checked` (`extra="forbid"`).

2f. **`accept-to-pantry` jest idempotentne (BATCH_12, decyzja D19).** Do
   spiżarni wchodzą pozycje odhaczone, nie oznaczone „mam już w domu" i BEZ
   `received_at`; przyjęte dostają stempel w tej samej transakcji co wpis
   w spiżarni. Odpowiedź ma addytywne pole `already_received`. **409 ma dwa
   warianty**, bo to dwie różne sytuacje: „nic nie odhaczono" i „Te zakupy są
   już w spiżarni.". Pozycje odhaczone PÓŹNIEJ przyjmują się normalnie
   („doniosłem dwie rzeczy z torby"). `received_at` wychodzi wyłącznie
   w odpowiedzi PRYWATNEJ — patrz pkt 3.

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
