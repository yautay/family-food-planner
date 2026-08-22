# BATCH_R3 — REVIEW_SHOPPING

Klasa: REV · Zależności: B08–B11 (wszystkie `[x]` w PROGRESS.md; R2 zamknięty) · Szacunek rozmiaru: S/M

## Goal

Audyt pionu zakupowego: spiżarnia, retail/sklepy, silnik zakupowy, listy
z publicznym udostępnianiem. Review NIE dodaje feature'ów — sprawdza
determinizm silnika, poprawność resztek/opakowań/tur, a przede wszystkim
**pełny audyt bezpieczeństwa publicznych tokenów** (pierwsza powierzchnia
dostępna bez logowania!). Ocenia też gotowość planu B12–B16 i potwierdza
kolejność importera po R3.

## Context

Po B08–B11 istnieją: `pantry` (stan domowy), `catalog` rozszerzony o
retail/sklepy/profile kolejności kategorii, `shopping` (engine.py czysty +
service.py + tury + generacje + listy + publiczne tokeny). Frontend:
spiżarnia, zakupy (konfig tur, generacja, preview), lista zakupowa
(mobile + print) i publiczna strona `/l/:token` bez auth. Aplikacja jest
od tego momentu „używalna na co dzień" (00_MASTER_PLAN §5).

### Gdzie szukać po B11 (stan faktyczny, 2026-08-21)

- Ścieżka publiczna: `app/modules/shopping/public_router.py` (router pod
  `/api/v1/public/`, limit 60/min/IP, walidacja kształtu tokenu) + metody
  `public_list` / `public_check_item` w `app/modules/shopping/lists_service.py`.
  Biała lista pól: `PublicListRead` / `PublicListItemRead` w `schemas.py`.
- Kolejność sekcji listy: czysty `app/modules/shopping/sorting.py`
  (unit: `tests/unit/shopping/test_list_sorting.py`).
- 410: `GoneError` w `app/core/errors.py`; komunikat 404 i 410 jest CELOWO
  identyczny (ADR-010) — to nie przeoczenie.
- Przyjęcie zakupów: `ShoppingListsService.accept_to_pantry` +
  `PantryService.receive_purchase` (reguła scalania: dolewamy do pozycji BEZ
  daty ważności; ilość = kupione opakowania, nie potrzeba).
- Testy: `tests/api/shopping/test_public_lists_api.py`,
  `tests/api/shopping/test_shopping_lists_api.py`,
  `tests/integration/shopping/test_accept_to_pantry.py`,
  E2E `frontend/e2e/shopping-list-sharing.spec.ts`.

Do rozstrzygnięcia w tym review (zgłoszone przez B11):

- **Ręczne pozycje listy** (Out of Scope B11 pkt 4) — czy są potrzebne; dziś
  lista jest wyłącznie wynikiem generacji.
- **`accept_to_pantry` można wywołać wielokrotnie** — nie ma kolumny „już
  przyjęte", więc ochroną jest dialog potwierdzenia w UI. Ocenić, czy to
  wystarcza (alternatywa: znacznik na liście).
- Dług z B10: dryf modelu `pantry_items.retail_product_id` (`alembic check`).

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` (sekcja Review)
  + `00_MASTER_PLAN.md` §9, §7–8.
- `docs/implementation-plan/PROGRESS.md` — warunki R2 + dziennik
  i Completion notes B08–B11.
- `docs/architecture/02_DOMAIN_MODEL.md` §8–9 i §13.5;
  03_DATABASE §7–8 (w tym `shopping_generations.params`!);
  04_API §2–3 (`/public/*`); **07_SECURITY §5 (WIĄŻĄCY dla audytu
  tokenów) + §3 (wyjątek CSRF dla public PATCH)**;
  08_TESTING §2.4–2.7, §2.9 i §3 (flow zakupowy E2E);
  05_FRONTEND §6 (offline — jeszcze NIE wdrożone, ocena gotowości);
  06_UIUX §5 (mobile lista = widok krytyczny), §6 (print).
- `docs/implementation-plan/03_AI_SKILLS.md` — `/security-review`
  OBOWIĄZKOWY w tym review.
- ADR-008 (czysty silnik), ADR-009 (offline — pod ocenę B12),
  ADR-010 (publiczne tokeny), ADR-011 (importer — pod potwierdzenie
  kolejności B15/B16).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-REVIEW, SKILL-SECREV, SKILL-BE, SKILL-FE, SKILL-CALC, SKILL-SEC
- **Recommended**: SKILL-CREATOR

Review batch sam jest procesem przeglądowym — SKILL-REVIEW/SKILL-SECREV uruchamiane są na pełnym zakresie zmian od poprzedniego review, nie na diffie własnego commita.

## Stages

1. **Rekonstrukcja stanu**: PROGRESS (warunki R2) + Completion notes
   B08–B11; `task check` zielony na wejściu.
2. **Audyt silnika zakupowego**: determinizm, resztki/opakowania, tury,
   spiżarnia — sekcja Audit checklist.
3. **Audyt security tokenów publicznych**: pełna checklista 07_SECURITY §5
   + `/security-review` na zmianach od R2 (obowiązkowo).
4. **Audyt UX**: mobile lista (cele dotykowe, sticky sekcje, optimistic
   check), wariant print, spójność stanu checkboxów.
5. **Analiza planu B12–B16**: gotowość offline (B12), kolejność importera
   (B15/B16 po R3 — potwierdzić wobec D2), zakresy B13–B14; korekty planu
   z powodem.
6. **Domknięcie**: drobne naprawy; werdykt do PROGRESS.md; aktualizacja
   kart/dokumentów; commit `batch(R3): review ...`.

## Audit checklist

### Determinizm silnika (ADR-008)

- [x] `shopping/engine.py`: czysta funkcja — zero I/O/ORM/now()/random
      (grep importów); wejście = plan+konfig, wyjście = preview struct
- [x] Ten sam input ⇒ identyczny output: snapshot testy istnieją;
      `shopping_generations.params` przechowuje pełne wejście generacji
      i pozwala odtworzyć preview (test regresyjny — wykonać)
- [x] Stabilne sortowanie pozycji (brak zależności od kolejności dict/set)

### Resztki i opakowania (08_TESTING §2.6)

- [x] `ceil(potrzeba/wielkość_opakowania)`; resztka = kupione − potrzeba;
      resztka wyeksponowana w preview i na liście („Zostanie: 150 g")
- [x] Brak retail ⇒ pozycja w gramach (dozwolone) + podpowiedź w preview
- [x] Wiele wariantów opakowań: wybór domyślny = najmniejsza resztka,
      remis → mniejsze opakowanie (nazwane przypadki testowe istnieją)
- [x] Decimal w ilościach; agregacja wielu przepisów/dni → jeden produkt,
      jednostki mieszane (g+szt.+łyżka) poprawnie znormalizowane (§2.4)

### Spiżarnia w pipeline (§2.5)

- [x] Odejmowanie WYŁĄCZNIE po jawnym pytaniu „Uwzględnić stan domowy?";
      preview pokazuje co odjęto (`from_pantry_amount`)
- [x] Nigdy poniżej zera; pozycje retail vs kanoniczne rozróżnione
- [x] Finalizacja listy NIE zmienia spiżarni automatycznie (02_DOMAIN §8)

### Tury (§2.7)

- [x] Preset niedziela/środa seedowany jako konfiguracja (NIE hardcode);
      trwałe na cały zakres + świeże na okno / świeże na resztę
- [x] `perishability` z kategorii + nadpisanie per produkt działa
- [x] Edge: plan krótszy niż okno tury — zdefiniowane, przetestowane

### Tokeny publiczne — pełny audyt 07_SECURITY §5 (KRYTYCZNE)

- [x] Token `token_urlsafe(32)`, unique index, lookup tylko po pełnym tokenie
- [x] **Odpowiedź `/public/lists/{token}` bez PII**: tylko nazwa listy,
      pozycje (label, ilość, kategoria, checked), expires_at — ZERO nazwisk,
      emaili, id userów/household (przeczytać serializer, wykonać request!)
- [x] Expiry (default 7 dni) + revoke → **410** z przyjaznym ekranem;
      nieistniejący token → 404/410 bez różnicowania informacji
- [x] **Rate limit 60/min/IP na `/public/*`** — test lub ręczna próba
- [x] **Maskowanie w logach**: ścieżka `/public/lists/***` — tokeny NIE
      występują w logach (grep po realnym logu z requestu!)
- [x] Public PATCH checkboxa: wyłączony z CSRF, ale rate-limited;
      pozwala TYLKO na check/uncheck (nic więcej — sprawdzić schema)
- [x] `/security-review` na całości zmian od R2 — OBOWIĄZKOWY, wynik w raporcie

### Mobile UX listy i print (06_UIUX §5–6)

- [x] Checkbox ~48 px, cele dotykowe ≥44 px; sekcje sticky per kategoria
      w kolejności profilu sklepu; odhaczanie optimistic
- [x] Wariant print: czarno-biały, ☐, kategorie jako nagłówki, bez
      nawigacji (sprawdzić realnie w przeglądarce)
- [x] QR/link/share działają; strona `/l/:token` renderuje się bez sesji
      POZA AppShell

### Spójność stanu checkboxów

- [x] `checked` + `checked_at` persystowane; równoległe odhaczanie
      (dwie karty/urządzenia) nie gubi stanu — zdefiniowana semantyka
      (last-write-wins per pozycja przygotowany pod ADR-009/B12)
- [x] Odhaczenie z publicznego linku i z aplikacji widzą ten sam stan

### Ustalenia odziedziczone z R2 (2026-08-21)

- [x] **U16 — puste `details.used_in` przy 409 usuwania rodziny.**
      `households/service.py::delete_household` liczy referencje tylko dla
      `users` i `member_profiles`; encje ze scope (dziś `recipes`, `plan_days`,
      `day_templates`, `week_templates`, `week_cycles`, po B08–B11 także
      spiżarnia, generacje i listy) blokują usunięcie przez FK RESTRICT
      i lądują w drugiej linii obrony (`IntegrityError` → 409 z `used_in: []`).
      Zachowanie jest POPRAWNE (409, nie 500), ale ADMIN nie dowiaduje się,
      co blokuje. R2 świadomie tego nie naprawiał: właściwym rozwiązaniem jest
      REJESTR finderów po stronie `households/service.py` (wzorzec
      `register_product_reference_finder` / `register_recipe_reference_finder`),
      a zakładanie go, gdy za chwilę dochodzą kolejne cztery tabele ze scope,
      znaczyłoby robić to dwa razy. Ten batch zastaje pełny zbiór konsumentów —
      albo zakłada rejestr, albo świadomie przyjmuje ograniczenie z pisemnym
      uzasadnieniem i domyka U16.
- [x] **U17 — nie da się usunąć dnia planu.** `04_API §2` opisuje
      `/plan/days/{date}` jako CRUD, a router ma tylko GET i PUT. Wiersz
      `plan_days` powstaje implicite przy pierwszym posiłku, trzyma
      `household_id` z FK RESTRICT i nie znika po usunięciu wszystkich
      posiłków — UI pokazuje wtedy „brak planu", ale blokada rodziny zostaje
      (to najczęstsza przyczyna U16 z pustym `used_in`). Do rozstrzygnięcia
      razem z U16: albo `DELETE /plan/days/{date}` (usuwa dzień bez posiłków),
      albo automatyczne sprzątanie pustego dnia przy usunięciu ostatniego
      posiłku, albo świadoma decyzja „dni zostają" z policzeniem ich w `used_in`.
- [x] **U15 zamknięty w R2** (E2E 10/10 w dwóch kolejnych przebiegach,
      `task secrets-scan` czysty) — sprawdzić, czy nadal jest, i czy nowe specy
      B08–B11 trzymają się konwencji: własny prefiks nazw + `beforeAll`
      /`afterAll` z `cleanupE2eData` + daty z okna 2030+ (`frontend/e2e/cleanup.ts`).
      Suita jest ŚWIADOMIE jednowątkowa (`workers: 1`) — spec zakładający
      równoległość to błąd review.

### Plan B12–B16 — przegląd

- [x] B12 (offline): czy `label` na pozycjach wystarcza do renderu offline;
      czy PATCH checkboxa jest idempotentny (kolejka offline!); ustalenia
      do karty B12
- [x] B15/B16 (importer) po R3 — potwierdzić kolejność wobec D2 (treść
      wchodzi importerem, nie odkładać za B17/18); jeśli baza świeci
      pustkami, rozważyć podniesienie priorytetu B15 (zmiana planu z powodem)
- [x] B13–B14: zakresy aktualne wobec stanu repo

## Security

- `/security-review` — obowiązkowy (największa nowa powierzchnia ataku
  programu: endpointy bez auth).
- Macierz uprawnień 08_TESTING §4 dla pantry/retail/stores/shopping
  (w tym wiersz „publiczna lista (token)" = 200 dla wszystkich).
- `pip-audit` + `npm audit`; patch-level w commicie review.
- Grep sekretów i tokenów w fixture'ach/logach testowych.

## Tests

- `task check` zielony przed i po naprawach.
- Obszary krytyczne 08_TESTING §2.4–2.7 i §2.9 pokryte (przejrzeć asserty).
- E2E flow 3 z 08_TESTING §3: generacja → pytanie o spiżarnię → preview
  z resztkami → finalizacja → publiczny link → odhaczenie bez logowania —
  istnieje i przechodzi.
- Luki: małe dopisać w review; większe → karta właściwego batcha.

## Acceptance Criteria

1. Audit checklist odhaczona albo przekuta w ustalenia (plik/linia +
   rekomendacja + miejsce docelowe).
2. Audyt tokenów publicznych: KAŻDY punkt 07_SECURITY §5 zweryfikowany
   realnym requestem/testem, wynik opisany w raporcie.
3. `/security-review` wykonany; ustalenia HIGH naprawione albo BLOKADA.
4. Determinizm silnika potwierdzony snapshotami + odtworzeniem generacji
   z `params`.
5. `task check` zielony po zmianach review.
6. Werdykt w PROGRESS.md: PASS / PASS z warunkami / BLOKADA dla B12–B14.
7. Karty B12–B16 zaktualizowane; kolejność importera potwierdzona
   (albo zmieniona z powodem w PROGRESS + 00_MASTER_PLAN).
8. Commit `batch(R3): review ...` wykonany, `git status` czysty.

## Out of Scope

- Offline/PWA → B12 (tu tylko ocena gotowości podstaw).
- Importer PDF → B15/B16 (tu tylko potwierdzenie kolejności).
- Nowe feature'y; optymalizacje ponad drobne naprawy.

## Expected files/modules

- `docs/implementation-plan/PROGRESS.md` — werdykt + wpis dziennika.
- Ewentualnie: drobne naprawy `backend/**`/`frontend/**`; aktualizacje
  kart `BATCH_12…16`, `docs/architecture/**`, `00_MASTER_PLAN.md`,
  `.claude/skills/ffp-framework/SKILL.md`, `CLAUDE.md`.

## Implementation Notes

- Audyt tokenów robić na działającej aplikacji (compose dev + seed):
  realne requesty curl/httpx na `/public/*`, w tym wygasły i odwołany
  token — nie ufać samym testom.
- PII w odpowiedzi publicznej to znany wzorzec wycieku — przejrzeć
  serializery pod kątem pól dołączanych relacyjnie (owner, household).
- Mobile UX sprawdzić w realnym viewporcie (devtools 390 px) + wydruk
  do PDF; wynik opisać, nie deklarować.
- Werdykt tego review otwiera trzy batche równoległe (B12∥B13∥B14) —
  sprawdzić brak kolizji plików między ich kartami PRZED dopuszczeniem.

## Cross-Batch Impact

- **B12**: ustalenia offline (idempotencja PATCH, label, LWW) do karty.
- **B13/B14**: werdykt = bramka; korekty zakresów do kart.
- **B15/B16**: potwierdzona (lub zmieniona) kolejność w 00_MASTER_PLAN.
- **R4**: dziedziczy niedomknięte follow-upy; wyniki audytu tokenów
  stanowią punkt odniesienia pełnego audytu przedprodukcyjnego.

## Implementation checklist

- [x] PROGRESS (warunki R2!) + Completion notes B08–B11 przeczytane
- [x] `task check` zielony na wejściu
- [x] Determinizm silnika: snapshoty + odtworzenie z params
- [x] Resztki/opakowania/agregacja: przypadki §2.4–2.6 zweryfikowane
- [x] Spiżarnia: jawne pytanie, nigdy <0, brak auto-przyjęcia
- [x] Tury z presetem + edge'y §2.7
- [x] Tokeny publiczne: pełna checklista §5 realnymi requestami
- [x] `/security-review` + macierz uprawnień + audyt zależności
- [x] Mobile UX + print sprawdzone realnie
- [x] Karty B12–B16 przejrzane; kolejność importera potwierdzona
- [x] Werdykt + wpis dziennika w PROGRESS.md

## Verification checklist

- [x] `task check` zielony po naprawach
- [x] Acceptance Criteria 1–8 odhaczone
- [x] Każde ustalenie: naprawione / follow-up (gdzie) / decyzja OPEN
- [x] Dokumentacja architektury zgodna ze stanem faktycznym
- [x] Commit `batch(R3): review ...`, `git status` czysty

## Completion notes

**WERDYKT: PASS — B12, B13 i B14 mogą startować (także równolegle).**
Wykonane 2026-08-22. Pełny werdykt z liczbami: dziennik `PROGRESS.md` (wpis na
górze). Tutaj to, co karta wymaga wprost: wykonane / odstępstwa / decyzje /
follow-upy / pytania.

### Wykonane

- **Rekonstrukcja stanu**: `task check` zielony na WEJŚCIU (exit 0), przeczytane
  warunki R2 + Completion notes B08–B11 + statusy zależności (wszystkie `[x]`).
- **Audyt silnika** (ADR-008): czystość potwierdzona gerpem importów (zero ORM
  poza enumem `Perishability`, zero zegara, zero losowości, zero `float`
  w torze), determinizm potwierdzony DWOMA drogami — testem odtworzenia
  z `params` i realnie: `POST /generate` + dwa `GET /generations/{id}` bajt
  w bajt identyczne. Opakowania, resztki, agregacja, tury i spiżarnia sprawdzone
  na realnych danych seedu (liczby w PROGRESS), przypadki brzegowe §2.4–2.7
  mają nazwane testy (`test_engine_packages.py`, `test_engine_rounds.py`,
  `test_engine_pantry.py`, `test_engine_properties.py`).
- **Audyt tokenów publicznych**: KAŻDY punkt 07_SECURITY §5 zweryfikowany
  realnym requestem na działającym stacku (200/410/410/404/422, biała lista pól
  bez PII, 429 po 60 żądaniach na WSPÓLNYM liczniku, `***` w obu warstwach
  logów sprawdzone grepem po `docker logs`, PATCH tylko `checked`, cudza
  pozycja 404, PATCH idempotentny).
- **Audyt UX**: mobile 375 px i wydruk sprawdzone W PRZEGLĄDARCE (pomiary
  DOM + PDF z emulacją mediów `print`), QR/link/odwołanie sprawdzone w realnym
  UI. Wyniki i liczby w PROGRESS.
- **Analiza planu B12–B16**: kolejność importera potwierdzona, kolizje plików
  w trójce równoległej sprawdzone PRZED dopuszczeniem, karty B12–B16
  zaktualizowane ustaleniami.
- **Naprawy** (sześć, wszystkie z testem): rejestr liczników referencji do
  rodziny (U16), sprzątanie pustego dnia planu (U17), `ForeignKey` na
  `pantry_items.retail_product_id` + BRAMKA dryfu modeli w `task check`,
  atomowe `accept_to_pantry`, „mam już w domu" nie wchodzi do spiżarni,
  wydruk faktycznie czarno-biały.

### Odstępstwa od karty

1. **`/security-review` i `/code-review` uruchomione, ale ANALIZĘ WYKONAŁ
   agent sesji, nie subagenty.** Oba skille żądają rozdzielenia pracy na
   równoległe pod-zadania (`Agent`), a prompt sesji tego wprost zabrania
   („Do not call the AgentTool unless the user requested it"). Zgodnie
   z hierarchią 03_AI_SKILLS §1 (właściciel > skill) instrukcje skilla wykonane
   zostały jednoprocesowo: pełne przejście po zakresie od R2 z checklistą
   kategorii skilla. Wynik w sekcji „Wyniki review skilli" niżej.
2. **U17 rozstrzygnięty trzecim wariantem, nie pierwszym z karty.** Karta
   dawała trzy opcje (`DELETE /plan/days/{date}` / automatyczne sprzątanie /
   „dni zostają" z policzeniem w `used_in`). Wybrane: **automatyczne sprzątanie
   pustego dnia + policzenie pozostałych w `used_in`**. Uzasadnienie: nowy
   endpoint bez UI nie rozwiązałby problemu użytkownika (nikt by go nie
   zawołał), a przesłanka „04_API opisuje CRUD" okazała się skrótem w tabeli
   mapy zasobów, nie kontraktem — doprecyzowane w 04_API §2.
3. **Dwie naprawy poza literalną listą karty**, obie w audytowanym obszarze
   i obie z testem: atomowość `accept_to_pantry` (karta kazała OCENIĆ
   powtarzalność, ocena odsłoniła też brak transakcyjności) oraz „mam już
   w domu" wchodzące do spiżarni po odhaczeniu. Zakres „drobne naprawy"
   z sekcji Review master prompta.
4. **`print.css` i `texts.ts` to zmiany frontendu w batchu review** — obie
   jednolinijkowe konsekwencje ustaleń audytu UX (kolor wydruku, pokazanie
   liczby pominiętych pozycji).

### Decyzje podjęte w review

- **404 vs 410 na ścieżce publicznej ZOSTAJE** (różne statusy, identyczny
  komunikat). Uzasadnienie i granice dopisane do 07_SECURITY §5 pkt 8 — to nie
  przeoczenie i nie wolno tego „naprawiać" po cichu.
- **`DELETE /plan/days/{date}` nie powstanie**; cykl życia dnia planu opisany
  w 04_API §2.
- **Sprzątanie pustego dnia nie dotyczy dnia z tytułem ani ze scope
  `household`** — jedno i drugie to jawna decyzja użytkownika.
- **Kolejność B12 ∥ B13 ∥ B14 → B15 → B16 potwierdzona** (uzasadnienie
  w 00_MASTER_PLAN §5 i karcie B15); warunek D2 czytany jako „przed B17/B18".

### Follow-upy (z miejscem docelowym)

- **D18 (ręczne pozycje listy)** i **D19 (znacznik „już przyjęte")** — OPEN
  w 02_DECISIONS z rekomendacją; oba do rozstrzygnięcia PRZED Stage 5 karty
  B12 (wpisane do jej sekcji Context).
- **Kolejka offline vs limit 60/min/IP** i **sekcje składane przez serwer** —
  ustalenia 2 i 3 w karcie B12; wymagają backoffu na 429 i decyzji, czy zmiana
  sklepu wchodzi do kolejki.
- **Wydruk częściowo odhaczonej listy** pokazuje wszystkie pozycje jako `☐`
  (06_UIUX §6 mówi „checkboxy jako ☐", więc kod jest zgodny z dokumentem).
  Obserwacja dla R4: kartka wydrukowana W TRAKCIE zakupów nie pokazuje, co już
  kupione. Zmiana wymaga korekty 06_UIUX §6, nie samego komponentu.
- **`Perishability` (enum domenowy) mieszka w `catalog/models.py`**, więc czysty
  silnik importuje moduł ORM po samą wartość enumową. Zero wpływu na
  determinizm, ale przeniesienie enumu do modułu bez SQLAlchemy byłoby
  czystsze — kandydat na sprzątanie w R4 (dziś wymagałoby ruszenia migracji
  i importów pół domeny, więc świadomie zostawione).
- **`shopping_lists.expires_at` służy ZARAZEM za ważność listy i ważność
  linku** (ADR-010 tak mówi), więc udostępnienie na 365 dni wydłuża życie samej
  listy i wpływa na filtr `?status=expired`. Zachowanie zgodne z ADR —
  obserwacja dla R4 przy przeglądzie retencji (D10).

### Wyniki review skilli

- **`/security-review` (SKILL-SECREV) na zakresie od R2: ZERO ustaleń HIGH
  i MEDIUM.** Przejrzane wektory: (a) ścieżka publiczna bez sesji — autoryzacja
  wyłącznie pełnym tokenem, brak `ScopedQuery` w metodach publicznych jest
  zamierzony i bezpieczny, bo lookup idzie po unique index; (b) IDOR na
  pozycjach listy — `_item_or_404` filtruje po `list_id`, sprawdzone realnym
  requestem (pozycja innej listy = 404); (c) wyciek PII w serializerze —
  `PublicListRead` jest jawną białą listą bez `from_attributes`, test
  asercjonuje DOKŁADNY zbiór kluczy, realna odpowiedź przeskanowana; (d) SQL
  injection — zero konkatenacji i zero `text()` z danymi użytkownika w torze
  zapytań (szukajka trigramowa wiąże frazę parametrem), token odsiewany wzorcem
  przed bazą; (e) XSS — zero `v-html`/`innerHTML` w `frontend/src`; (f) path
  traversal w uploadach zdjęć wariantów sklepowych — jedyne wejście to
  `core/uploads.py` (losowa nazwa, sniffing Pillow, re-encode), serving przez
  endpoint z sesją; (g) obejście scope w `resolve` — decyzje walidowane wobec
  `params` generacji (`UNKNOWN_PRODUCT_IN_DECISION`, wariant musi należeć do
  swojego produktu); (h) CSRF — wyjątek dotyczy dokładnie prefiksu
  `/api/v1/public/`, mutacja bez nagłówka to 403 (sprawdzone realnie na
  `POST /shopping/lists/{id}/share`); (i) higiena logów — token nie wychodzi
  w żadnej z dwóch warstw. Sklepy i warianty retail są edytowalne przez
  KAŻDEGO zalogowanego świadomie (słownik globalny, 02_DOMAIN §3.1 pkt 3–4) —
  to nie ustalenie. `task audit` i `task secrets-scan` czyste.
- **`/code-review` (SKILL-REVIEW) na zakresie od R2 + własny diff review:
  trzy ustalenia, wszystkie NAPRAWIONE w tym commicie** — (1) odhaczona pozycja
  „mam już w domu" wchodziła do spiżarni jako zakup; (2) `receive_purchase`
  commitowało per pozycja, więc przyjęcie listy nie było atomowe; (3) po
  przejściu na `flush` pierwsza wersja poprawki zwracała encję z mapy
  tożsamości, gubiąc SKALĘ kolumny NUMERIC (pułapka opisana w nocie 5 karty
  B08) — przywrócone `_view()` z `populate_existing`. Do tego dwie korekty
  higieniczne we własnym diffie: kolejność importów (ruff I001) i EN DASH
  w literale (RUF001).

### Pytania do właściciela

**D18** (ręczne pozycje listy) i **D19** (znacznik „już przyjęte") — wpisane do
02_DECISIONS jako OPEN z rekomendacją i uzasadnieniem. Żadna z nich nie blokuje
startu B12/B13/B14; D18 i D19 trzeba rozstrzygnąć przed Stage 5 karty B12.
