# BATCH_R1 — REVIEW_FOUNDATIONS

Klasa: REV · Zależności: B01–B04 (wszystkie `[x]` w PROGRESS.md) · Szacunek rozmiaru: S

## Goal

Audyt fundamentów (scaffold, auth, households+scope, katalog produktów)
zanim powstanie rdzeń planowania. Review NIE dodaje feature'ów: sprawdza
zgodność implementacji z architekturą, trzymanie wzorców, security, testy
i kompletność propagacji decyzji; wolno mu skorygować plan przyszłych
batchy. **Fundamenty nie poprawiają się później tanio — każde ustalenie
blokujące musi zostać zgłoszone i rozstrzygnięte PRZED zleceniem B05.**

## Context

Po B01–B04 istnieją: monorepo (backend FastAPI + frontend Vue 3, Taskfile,
compose.dev, CLAUDE.md, cztery project skille `ffp-*`), auth (sesje server-side,
CSRF, rate limit, `create-admin`), households + scope (`ScopedQuery`,
fundament audit logu), katalog (produkty kanoniczne, jednostki, kategorie,
`ProductPicker` z create-in-context). Ten batch pierwszy raz ogląda je
jako całość w jednej sesji.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` — procedura sesji
  (sekcja „Review batche").
- `docs/implementation-plan/00_MASTER_PLAN.md` §9 (rola review), §7 (DoD),
  §8 (living documentation).
- `docs/implementation-plan/PROGRESS.md` — dziennik B01–B04 (odstępstwa!)
  oraz Completion notes w kartach `BATCH_01…04`.
- `docs/architecture/01_ARCHITECTURE_OVERVIEW.md` §2 (struktura, wzorzec
  modułu), §4 (ScopedQuery), 02_DOMAIN §3–4, 03_DATABASE §1–4,
  04_API §1–3, 05_FRONTEND §1–2 i §4, 07_SECURITY (całość), 08_TESTING §2, §4.
- `docs/implementation-plan/03_AI_SKILLS.md` — użycie `/code-review`
  i `/security-review` w review.
- ADR-002 (migracje), ADR-003 (sesje), ADR-005 (jednostki), ADR-006 (scope),
  ADR-007 (frontend), ADR-012 (usuwanie/archiwizacja).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-REVIEW, SKILL-SECREV, SKILL-BE, SKILL-SEC
- **Recommended**: SKILL-FE, SKILL-CREATOR

Review batch sam jest procesem przeglądowym — SKILL-REVIEW/SKILL-SECREV uruchamiane są na pełnym zakresie zmian od poprzedniego review, nie na diffie własnego commita.

## Stages

1. **Rekonstrukcja stanu**: PROGRESS.md + Completion notes B01–B04; lista
   odstępstw i follow-upów zgłoszonych przez batche. `task check` na
   czystym stanie — musi być zielony ZANIM zacznie się audyt.
2. **Audyt kodu vs architektura**: sekcja „Audit checklist" poniżej,
   punkt po punkcie; każde ustalenie notowane z plikiem/linią.
3. **Security**: `/security-review` na całości zmian od początku repo
   + audyt zależności (`pip-audit`, `npm audit`) + ręczna weryfikacja
   punktów z sekcji Security.
4. **Testy**: pokrycie obszarów krytycznych 08_TESTING §2 (pkt 3, 8 —
   jednostki, uprawnienia) i macierzy §4 dla KAŻDEGO zasobu z B02–B04;
   realne uruchomienie testów sesji/CSRF/rate-limitu.
5. **Analiza planu**: karty B05–B07 vs faktyczny stan repo — czy Context
   kart jest aktualny, czy zakresy nie pękły; ewentualne zmiany planu
   z udokumentowanym powodem (00_MASTER_PLAN §12).
6. **Domknięcie**: drobne naprawy (typówki, martwy kod) w commicie review;
   werdykt + lista ustaleń do PROGRESS.md; aktualizacja kart przyszłych
   batchy i dokumentów architektury; commit `batch(R1): review ...`.

## Audit checklist

Legenda: `[x]` = sprawdzone i czyste albo przekute w ustalenie (numery U/D
wg dziennika `PROGRESS.md`, wpis R1).

### Wzorzec modułu i granice

- [x] Każdy moduł trzyma `router.py → service.py → models.py`; router
      NIGDZIE nie dotyka sesji DB bezpośrednio (grep po `Session`/`db` w routerach)
      — grep `AsyncSession|get_session|session\.` po `app/modules/*/router.py`:
      zero trafień
- [x] Import między `modules/*` wyłącznie przez serwisy (modele dozwolone,
      logika — nie); grep importów krzyżowych — krzyżowo tylko
      `audit.service` (zapis dziennika) i `households.schemas.HouseholdSummary`
      w `accounts.schemas` (typ odpowiedzi, bez logiki)
- [x] Kształt błędu API = 04_API §1 we wszystkich handlerach; kody
      401/403/404/409/422/429 zgodne z konwencją — jeden punkt wyjścia
      (`core/errors.py`), handlery zarejestrowane w `create_app`, pokryte
      `tests/unit/test_errors.py` i asercjami kodów w testach API
- [x] OpenAPI kompletne; `task fe-types` generuje typy bez błędów —
      regeneracja dała ZEROWY diff (kontrakt zgodny z kodem); brak bramki
      świeżości w `task check` → **U12** (B17)

### ScopedQuery i autoryzacja

- [x] `ScopedQuery` jest JEDYNĄ ścieżką autoryzacji zasobów scope'owanych —
      żadnego ręcznego `WHERE owner_user_id` poza mixinem (grep) — dwa trafienia
      na `household_id ==` w `households/service.py` dotyczą `member_profiles`
      i składu rodziny, czyli encji BEZ kolumn scope (dozwolone wprost
      w 04_API §3 pkt 2a). Encji produkcyjnych ze scope jeszcze nie ma (B05)
- [x] Cudzy zasób → 404, nie 403 (07_SECURITY §4); testy anty-IDOR
      istnieją dla każdego zasobu B03–B04 — `test_scope_matrix.py` (pełna
      macierz na `ScopedNote`), `test_households_my.py` (cudzy profil PATCH
      i DELETE → 404, także dla ADMIN-a), katalog jest globalny, więc nie ma
      tam czego 404-ować (uprawnienia są do ZAPISU) → **D16**
- [x] `require_admin` na edycji wartości odżywczych i statusu weryfikacji;
      inline create USERA daje `UNVERIFIED` + wpis audit — `AdminUser`
      w sygnaturach `PUT /nutrition` i `POST /verify`; testy: USER → 403,
      inline create → `unverified` + `product.create` w dzienniku

### Sesje, CSRF, rate limit — przetestowane REALNIE

- [x] Cookie: HttpOnly + SameSite=Lax + Secure (prod); logout usuwa wiersz;
      TTL przesuwny działa (test, nie deklaracja) — asercje na nagłówku
      `Set-Cookie` (w tym osobny klient z `app_env=prod`), test starego cookie
      po logout → 401, test `Max-Age` przy przesunięciu TTL i test braku
      `Set-Cookie` dla świeżej sesji
- [x] CSRF double-submit: mutacja bez nagłówka → 403 (test API istnieje
      i faktycznie by wykrył regresję — sprawdzić assert) — trzy warianty
      (brak nagłówka, zły nagłówek, poprawny → 204) plus asercja, że nagłówki
      bezpieczeństwa są też na odpowiedzi 403; wyjątek `/auth/login`
      nieudokumentowany → **U6** (naprawione w 07_SECURITY §3)
- [x] Rate limit loginu 5/min/IP + backoff po 10 nieudanych: test lub
      wykonana ręcznie próba z raportem wyniku — `test_szosta_proba…` → 429
      z `rate_limited`; `test_blokada_konta…` wyłącza limiter IP i sprawdza
      DRUGI mechanizm. Blokada jest stała, nie wykładnicza → **U5**
- [x] argon2id; rehash przy logowaniu; brak haseł/tokenów w logach —
      `PasswordCheck.new_hash` + `check_needs_rehash`, `burn_password_time`
      przeciw enumeracji; logi mają request id i maskowaną ścieżkę, payloadów
      nie logują; audyt zmiany hasła zapisuje wyłącznie flagę

### Migracje i baza

- [x] `alembic heads` = 1; pełny cykl `upgrade head → downgrade base →
      upgrade head` przechodzi na czystej bazie (WYKONAĆ) — `0005 (head)`;
      cykl wykonany realnie na db-test. Na bazie Z DANYMI wywalił się →
      **U2** (naprawione + test)
- [x] Naming convention constraintów działa (downgrade nie wybucha na
      bezimiennym constraincie); NUMERIC wszędzie dla ilości (grep po Float)
      — `Base.metadata` z `naming_convention`, migracje używają `op.f(...)`,
      downgrade kasuje też typy enumowe (test); grep `Float|: float`: jedyne
      trafienie to próg trigramu w `config.py` (nie ilość, nie wartość odżywcza)
- [x] CHECK scope (03_DATABASE §4) obecny; `ON DELETE` jawne na FK —
      `scope_requires_household` w `ScopedMixin.__table_args__` z testem
      `IntegrityError`; 8/8 `ForeignKeyConstraint` w migracjach ma `ondelete`,
      wszystkie `ForeignKey` w modelach też

### Katalog i wartości odżywcze

- [x] Adapter ProductNutrition (wejście do wartości /100 g produktu) jest
      JEDYNYM miejscem odczytu wartości — nic nie sięga w kolumny modelu
      z pominięciem adaptera (przygotowanie pod silnik B05) — jedyny inny
      czytnik to schemat ODPOWIEDZI `ProductNutritionRead` (`catalog/router.py`),
      czyli prezentacja formularza admina, nie wejście obliczeń; granica
      dopisana do karty B05, żeby silnik nie dołożył drugiego czytnika
- [x] `ProductUnitWeight`: przeliczniki per produkt, mediana z próbek;
      odmowa zapisu ilości nieprzeliczalnej (02_DOMAIN §13.1) — odmowa
      działa (`UnitConversionError` → 422, testy), ale jednostka domowa
      produktu `piece` liczyła się na złej osi → **U1** (naprawione);
      `samples_count` istnieje jako pole, medianę z próbek nauczy się liczyć
      importer B15/16 (dziś każdy wpis to jedna próbka — zgodne z kartą B04);
      prezentacja przelicznika zawsze w gramach → **U9** (B05)
- [x] Blokada usuwania (409 + `details.used_in`) i `is_archived` działają
      wg ADR-012 — `core/deletion.py` + rejestr finderów (test z symulowanym
      konsumentem sprawdza dokładny kształt `used_in`), `IntegrityError`
      z commita jako druga linia obrony, archiwizacja odwracalna i wypycha
      produkt z list (test)

### Frontend

- [x] Zero kopii stanu serwera w Pinia (przejrzeć stores/*); server state
      wyłącznie TanStack Query, klucze w `queryKeys.ts` — w `src/stores/` jest
      wyłącznie `auth.ts` (sesja + `household` z `/auth/me`), bez persystencji
- [x] `ProductPicker` zgodny z 05_FRONTEND §4: brak wyniku ⇒ `+ Dodaj
      produkt "…"` ⇒ drawer ⇒ auto-wybór ⇒ powrót do flow (sprawdzić ręcznie)
      — sprawdzone lekturą + testem `pełny cykl create-in-context: brak wyniku
      → drawer → zapis → wybór` (asercje na `createProduct`, emit `selected`
      i zamknięcie drawera). **Ręcznego przeklikania NIE BYŁO — brak Dockera**
      (ten sam blocker co E2E, **U15**); przy okazji znaleziony **U10**
- [x] `client.ts`: credentials include, nagłówek CSRF, mapowanie ApiError;
      typy z `generated.ts`, zero ręcznych interfejsów odpowiedzi — potwierdzone
      lekturą i `client.spec.ts`; wszystkie moduły `src/api/*` importują
      `components` z `generated.ts`

### Kontrakt sesji AI i narzędzia

- [x] Taskfile kompletny: wszystkie targety z kart B01–B04 istnieją
      i działają; `task help` aktualny — `task --list` pokazuje 30 targetów
      (help = `task --list`, więc nie może się zdesynchronizować);
      uruchomione w tej sesji: `check`, `test-be`, `test-int`, `test-unit`,
      `db-heads`, `fe-types`, `audit`, `secrets-scan` (padł na braku Dockera)
- [x] CLAUDE.md zgodny z rzeczywistością repo (komendy, zakazy, wskaźniki);
      project skille `.claude/skills/ffp-{backend,frontend,domain-calc,security}`
      nadążają za wzorcami (ScopedQuery, Decimal, adapter wartości,
      Query/Pinia) — zaktualizować w commicie review, jeśli nie
      → **U4** (CLAUDE.md) i **U7** (wszystkie cztery skille), naprawione

## Security

- `/security-review` (skill) na całości kodu — obowiązkowy, wynik w raporcie.
- `pip-audit` + `npm audit`: podbicia zależności z podatnościami HIGH+
  wykonać w commicie review (patch-level); większe → follow-up do PROGRESS.
- Grep sekretów: `git ls-files` bez `.env`; brak kluczy/haseł w kodzie
  i testach (w tym fixture'ach).

## Tests

- `task check` zielony przed i po naprawach review.
- Weryfikacja, że testy krytyczne ISTNIEJĄ i COŚ SPRAWDZAJĄ (przejrzeć
  asserty, nie tylko nazwy): macierz uprawnień 08_TESTING §4 per zasób,
  konwersje jednostek (§2.3), sesje/CSRF/rate-limit, cykl migracji.
- Luki w pokryciu obszarów krytycznych: małe → dopisać w commicie review;
  większe → wpis do karty batcha, który obszar posiada.

## Acceptance Criteria

1. Wszystkie punkty Audit checklist odhaczone albo przekute w ustalenia
   (naprawione w review / follow-up z miejscem docelowym).
2. `/security-review` i audyt zależności wykonane; wynik opisany.
3. `task check` zielony po zmianach review.
4. Werdykt w PROGRESS.md: **PASS** (B05 może startować) / **PASS z
   warunkami** (lista) / **BLOKADA** (co musi się stać przed B05).
5. Karty B05–B07 przejrzane; korekty planu (jeśli są) wprowadzone
   do 00_MASTER_PLAN + kart z powodem w PROGRESS.
6. Project skille `ffp-*` i CLAUDE.md aktualne wobec stanu repo.
7. Commit `batch(R1): review ...` wykonany, `git status` czysty.

## Out of Scope

- Jakiekolwiek nowe feature'y i refaktoryzacje ponad drobne naprawy
  (większe → ustalenie z miejscem docelowym: karta batcha albo 02_DECISIONS).
- Zmiany architektury bez wpisu (konflikt = pytanie do właściciela).
- Silnik nutrition i przepisy → B05 (tu tylko gotowość fundamentu).

## Expected files/modules

- `docs/implementation-plan/PROGRESS.md` — werdykt + wpis dziennika.
- Ewentualnie: drobne naprawy w `backend/**`, `frontend/**`; aktualizacje
  `CLAUDE.md`, `.claude/skills/ffp-*/SKILL.md`, kart
  `BATCH_05…07`, dokumentów `docs/architecture/**`, `00_MASTER_PLAN.md`.

## Implementation Notes

- Kolejność: najpierw czytanie i audyt, naprawy na końcu — inaczej diff
  review zlewa się z ustaleniami.
- Ustalenie = plik/linia + dlaczego niezgodne + rekomendacja. Bez tego
  werdykt jest nieweryfikowalny.
- Granica „drobnej naprawy": nie zmienia kontraktu API, schematu DB ani
  zachowania widocznego dla użytkownika. Wszystko powyżej → follow-up.
- To OSTATNI tani moment na zmianę fundamentów (nazwy kolumn scope,
  kształt ScopedQuery, kontrakt błędów) — wątpliwości eskalować teraz.

## Cross-Batch Impact

- **B05–B07**: werdykt + zaktualizowane karty to bramka wejścia; ustalenia
  o adapterze nutrition wpisać do karty B05.
- **R2**: dziedziczy listę follow-upów niedomkniętych w R1 (wpis w PROGRESS).
- **Wszystkie**: zmiany w CLAUDE.md/skillu obowiązują od następnej sesji.

## Implementation checklist

- [x] PROGRESS + Completion notes B01–B04 przeczytane, lista odstępstw
      (lista wejściowa: follow-upy B01 pkt 1–2, B02 pkt 2 i 4, B03 E2E,
      B04 pkt 2–4 — każdy z nich ma w dzienniku R1 status)
- [x] `task check` zielony na wejściu (exit 0)
- [x] Audit checklist wykonana punkt po punkcie (ustalenia z plik/linia)
- [x] `/security-review` + `pip-audit` + `npm audit` wykonane
- [x] Pokrycie testami obszarów krytycznych zweryfikowane (asserty!)
- [x] Karty B05–B07 przejrzane i zaktualizowane (+ B17 jako miejsce docelowe
      trzech follow-upów)
- [x] Drobne naprawy wykonane; follow-upy rozpisane do miejsc docelowych
- [x] Project skille `ffp-*` + CLAUDE.md zaktualizowane
- [x] Werdykt + wpis dziennika w PROGRESS.md

## Verification checklist

- [x] `task check` zielony po naprawach
- [x] `alembic heads` = 1; cykl up/down/up wykonany realnie
- [x] Acceptance Criteria 1–7 odhaczone
- [x] Każde ustalenie ma status: naprawione / follow-up (gdzie) / decyzja OPEN
- [x] Commit `batch(R1): review fundamentów`, `git status` czysty

## Completion notes

Wykonano: 2026-08-16. **WERDYKT: PASS Z WARUNKAMI** — pełna lista ustaleń
(U1–U15) z plikami, liniami i statusami oraz cztery warunki startu B05 są
w dzienniku `PROGRESS.md` (wpis R1 na górze). Tu tylko to, czego dziennik
nie mówi.

### Zakres i sposób pracy

Audyt objął `0c872b4^..833b4d1` (B01–B04). Kolejność z Implementation Notes
utrzymana: najpierw lektura i uruchomienia, naprawy na końcu, więc diff
review nie zlewa się z ustaleniami. `/code-review` i `/security-review`
uruchomione na PEŁNYM zakresie zmian od początku repo (nie na diffie tego
commita) — zgodnie z sekcją Skills.

### Granica „drobnej naprawy" — jak była stosowana

W commicie review są wyłącznie zmiany, które nie ruszają kontraktu API,
schematu DB ani zachowania widocznego dla użytkownika:

- **U1** (`units.py`) — funkcja bez ANI JEDNEGO konsumenta produkcyjnego
  (grep: tylko testy), więc naprawa nie zmienia niczego, co dziś widzi
  użytkownik, a bez niej silnik B05 wystartowałby na błędnej podstawie.
- **U2** (`0005`) — zmieniony wyłącznie `downgrade()`; `upgrade()` nietknięty,
  więc migracja już zaaplikowana na dev/prod nie wymaga niczego.
- **U3** (`compose.dev.yml`) — pętla dev, nie aplikacja.
- **U4–U8** — dokumentacja, skille i karty.

Świadomie NIE naprawione w R1, choć poprawka jest jednolinijkowa: **U9**
(etykieta i jednostka przelicznika w UI) oraz **U10** (reset pól drawera) —
obie zmieniają to, co widzi użytkownik, więc idą do B05 razem z resztą pracy
nad jednostkami. **D15** (kto może zmienić `measure_kind`) to decyzja
właścicielska, nie naprawa.

### Czego NIE dało się wykonać w tym środowisku

`docker` nie jest w PATH tej sesji, więc:

- **`task secrets-scan` NIEWYKONANY** (gitleaks działa przez `docker run`).
  Substytut: `git ls-files` nie zawiera `.env` (`.gitignore`: `.env`, `*.env`,
  `!*.env.example`), grep po plikach śledzonych za wzorcami
  `password|secret|token|api_key` z wartością — zero trafień poza testowym
  `TEST_PASSWORD` i placeholderami w `.env.example`.
- **E2E NIEURUCHOMIONE** (`households.spec.ts`, `produkty.spec.ts`) — dług
  z B03/B04. Substytut: statyczna weryfikacja, że wszystkie 36 `data-testid`
  używanych w testach E2E istnieją w `frontend/src` (0 braków).
- **U3 nie został sprawdzony w kontenerze** — przetestowana lokalnie sama
  logika `sh` (pusty wolumen / bez zmian / po zmianie lockfile / po `npm ci`
  czyszczącym katalog) i parsowanie YAML-a do oczekiwanego stringa.

Te trzy pozycje NIE są odhaczone jako wykonane; wiszą jako **U15** z terminem
„przed R2".

### Uwagi proceduralne dla kolejnych review

- `tests/conftest.py` czyści tabele PRZED testem, nie po, więc po przebiegu
  `task test-api` w bazie testowej zostają wiersze ostatniego testu. To one
  ujawniły **U2** przy ręcznym `alembic downgrade base` — warto powtórzyć ten
  ruch w R2/R3 (`downgrade base` na bazie PO testach), bo sam `task check`
  tego nie łapie.
- Nowy test `test_downgrade_seedu_przechodzi_na_bazie_z_produktami` sprząta po
  sobie w `finally` — bez tego zostawiałby produkt, który wysadziłby
  `test_migrations.py`, gdyby kolejność plików się zmieniła.

### Pytania do właściciela

Dwa, oba wpisane do `02_DECISIONS.md` jako OPEN z rekomendacją: **D15**
(zmiana `measure_kind` a weryfikacja wartości) i **D16** (czy ADMIN widzi
cudze encje scope'owane na ścieżkach użytkownika — dwa dokumenty nadrzędne
mówią co innego). Żadne z nich nie blokuje startu B05, ale D16 rozstrzyga się
w kodzie właśnie w B05, bo `/recipes` to pierwsza produkcyjna encja ze scope.
