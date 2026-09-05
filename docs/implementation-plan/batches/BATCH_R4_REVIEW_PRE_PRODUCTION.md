# BATCH_R4 — REVIEW_PRE_PRODUCTION

Klasa: REV · Zależności: B01–B16 (wszystkie `[x]` w PROGRESS.md; R1–R3 zamknięte) · Szacunek rozmiaru: M

## Goal

Pełny audyt przedprodukcyjny całej aplikacji przed fazą PROD (B17–B18).
Review NIE dodaje feature'ów — wydaje werdykt **GO/NO-GO** dla wdrożenia:
bezpieczeństwo całości, wydajność, kompletność backupu logicznego,
zebrany i spriorytetyzowany dług techniczny, wyrywkowa weryfikacja
acceptance criteria WSZYSTKICH batchy, aktualność dokumentacji. Ma prawo
utworzyć batche naprawcze (wg szablonu 00_MASTER_PLAN §6) i wpisać je do
planu przed B17.

## Context

Po B01–B16 aplikacja jest funkcjonalnie kompletna: fundamenty, rdzeń
planowania, pion zakupowy, PWA/offline, statystyki, eksport/import,
importer PDF z asystą AI. Nie istnieje jeszcze nic produkcyjnego
(compose.prod, backup, runbooki — to B17/B18). To ostatni moment na
znalezienie problemów, zanim aplikacja wyjdzie do Internetu.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` (sekcja Review)
  + `00_MASTER_PLAN.md` §9, §7–8, §10 (ryzyka — odhaczyć mitigacje).
- `docs/implementation-plan/PROGRESS.md` — CAŁY dziennik + warunki R1–R3;
  Completion notes wszystkich batchy (lista odstępstw programu).
- `docs/implementation-plan/02_DECISIONS.md` — **stan D6 i D7 (bramki
  B18!)** oraz D10 (retencja — rewizja przy R4 zapowiedziana).
- CAŁA architektura `docs/architecture/01…09` — audyt aktualności vs kod;
  **09_DEPLOYMENT jest WIĄŻĄCY dla oceny gotowości do B17/B18**.
- `docs/implementation-plan/03_AI_SKILLS.md` — `/security-review` full
  + `/code-review` w tym review.
- **ADR-001…015** — zgodność stanu faktycznego z każdym ACCEPTED.
  (Karta mówiła „001…014"; ADR-015 „async SQLAlchemy + psycopg" istnieje
  w repo od BATCH_01 i też podlega audytowi — poprawione w R4.)

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-REVIEW, SKILL-SECREV, SKILL-BE, SKILL-FE, SKILL-CALC, SKILL-SEC
- **Recommended**: SKILL-CREATOR

Review batch sam jest procesem przeglądowym — SKILL-REVIEW/SKILL-SECREV uruchamiane są na pełnym zakresie zmian od poprzedniego review, nie na diffie własnego commita.

## Stages

1. **Rekonstrukcja stanu**: PROGRESS + Completion notes B01–B16 +
   follow-upy R1–R3; `task check` zielony na wejściu.
2. **Audyt bezpieczeństwa całości**: `/security-review` full + sekcja
   Audit checklist (nagłówki, uploady, sekrety, tokeny).
3. **Wydajność**: pomiary kluczowych widoków na seedzie demo.
4. **Kompletność danych**: backup logiczny (eksport→import odtwarza
   wszystko?), migracje, retencja (D10).
5. **Weryfikacja wyrywkowa AC**: acceptance criteria batchy 01–16 —
   próbka z każdego batcha wykonana ręcznie/testem.
6. **Dług i dokumentacja**: zebrany dług z priorytetami; architektura
   i ADR vs kod; skill/CLAUDE.md.
7. **Werdykt GO/NO-GO**: do PROGRESS.md; ewentualne batche naprawcze
   utworzone wg szablonu i wpisane do planu; konkretne ustalenia dla B17
   wpisane do sekcji „Ustalenia R4 do wykonania" karty BATCH_17;
   przypomnienie właścicielowi o D6/D7; commit `batch(R4): review ...`.

## Audit checklist

### Bezpieczeństwo całości (07_SECURITY — pełny przegląd)

- [x] `/security-review` na CAŁYM kodzie (nie diffie) → cztery równoległe przebiegi (core+auth, moduły domenowe, zakupy+transfer+importer, frontend). JEDNO ustalenie powyżej progu: resolver dnia planu — NAPRAWIONE w tym commicie. Zero otwartych HIGH. — wynik w raporcie;
      HIGH naprawione albo NO-GO
- [x] Nagłówki (07 §3) → sprawdzone realnym `curl` na 200, 404 i na ścieżce publicznej: nosniff, `same-origin`, `DENY`, CSP bez zewnętrznych źródeł. Brak `base-uri`/`form-action` → B17 pkt 2.: nosniff, Referrer-Policy, X-Frame-Options DENY,
      CSP bez zewnętrznych źródeł — sprawdzić realnym responsem
- [x] Uploady (07 §6) → `core/uploads.py`: 10 MB, `Pillow.verify()`, re-encode bez `exif=`, `uuid4().hex`, `PRIVATE_SUBDIRS`, `is_relative_to(root)` PO `.resolve()`; serving przez endpoint z `CurrentUser`, nie StaticFiles. PDF: 25 MB, `%PDF`, `run_in_threadpool` pod `asyncio.wait_for`.: limity 10/25 MB, MIME sniffing po treści, losowe
      nazwy poza web-rootem, serwowanie z autoryzacją, re-enkodowanie
      Pillow (EXIF strip), pdfplumber w try/except z limitem czasu
- [x] **Sekrety w repo — grep** → `git ls-files` + grep po `sk-ant-`/`BEGIN PRIVATE KEY`/`AKIA…`: dwa trafienia, oba placeholdery (`sk-ant-test-nieprawdziwy` w teście, `sk-ant-…` w runbooku). `task secrets-scan`: „no leaks found" (33 commity, 6,07 MB).: `git log -p`-poziom nie wymagany, ale
      `git ls-files` + grep po wzorcach (key, secret, password, token,
      BEGIN PRIVATE, sk-ant) po całym repo, także testach i docs
- [x] `ANTHROPIC_API_KEY` wyłącznie server-side → zero trafień w `frontend/src` i w zbudowanym bundlu. `build_*_prompt` przeczytane wzrokiem: wychodzą surowe nazwy z PDF-a, nazwy dań, treść przygotowania i nazwy produktów GLOBALNEGO katalogu. Fix z B16 (`owned_names`, nie `visible_condition`) potwierdzony na miejscu. (grep frontendu);
      klucz nieobecny w logach i odpowiedziach API. **Stan po B16**: front
      dostaje wyłącznie `ai_available: bool`, a granica danych wysyłanych do
      modelu (D5) ma JEDNO miejsce w kodzie — `importer/ai_assist.py`,
      funkcje `build_*_prompt`. Przejrzeć je wzrokiem: to tam wchodziłby
      przypadkowy wyciek e-maila albo nazwy rodziny
- [x] Tokeny publiczne: ponowna szybka weryfikacja §5 → bez regresji od R3: token 43 znaki, odpowiedź dokładnie `{name, expires_at, items}` + 10 pól pozycji, `received_at` NIEOBECNE, 422/404/410 z identycznym komunikatem, 54×200 + 16×429 na wspólnym liczniku, `***` w OBU warstwach logu. (PII, rate limit,
      maskowanie) — regresje od R3
- [x] Sesje/CSRF/rate-limit: testy nadal realne → mutacja bez nagłówka → realny 403; 24 pliki testów API pokrywają każdy prefiks z mapy zasobów 04_API §2.; macierz uprawnień §4
      kompletna dla WSZYSTKICH zasobów (wyrywkowo uruchomić)
- [x] `pip-audit` + `npm audit` — zero known HIGH+ → pip-audit czysty; `npm audit` miał JEDNO HIGH (`fast-uri` 3.1.5, dev-only przez `vite-plugin-pwa → workbox-build → ajv`) — podbite do 3.1.7, oba czyste. przed produkcją

### Wydajność kluczowych widoków (seed demo)

- [x] Pomiary z liczbą zapytań SQL i czasem → tabela w PROGRESS. Budżet <500 ms spełniony z zapasem ×10 (najwolniejszy widok: generacja zakupów, 55 ms).: plan dnia, tydzień (<500 ms,
      budżet z R2), lista przepisów z filtrami, generacja zakupów, lista
      zakupowa, statystyki zakresu — tabela wyników w raporcie
- [x] Brak N+1 w żadnym z powyższych → plan tygodnia 11 zapytań = plan dnia 11; statystyki 92 dni 12 = statystyki 7 dni 12. `EXPLAIN` potwierdza użycie `ix_day_templates_payload_gin` (`@>`) oraz obu indeksów trigramowych.; indeksy używane (EXPLAIN wyrywkowo)

### Spójność statystyk z planem dnia (ustalenie B13, 2026-08-22)

- [x] Ten sam dzień w `/plan-dnia` i w `/statystyki` → ZERO rozjazdów na 7 dniach × 7 polach; statusy identyczne. pokazuje TE SAME
      liczby (kcal do 1, makra do 0,1 g) — jedno źródło to silnik nutrition,
      więc rozjazd znaczy, że któryś widok liczy po swojemu
- [x] Statusy w statystykach respektują progi → oba widoki liczą przez `engine.goal_status` z `thresholds_from_ui_settings`; jedno źródło, brak drugiej implementacji progów. z `users.ui_settings`
      (D9, domyślnie 90–110%): zmiana progów w Ustawieniach zmienia status
      w OBU widokach tak samo
- [x] Zmiana celu w środku zakresu → cele 2000 (od 01.08) i 2200 (od 28.08) dały `target` = (2000×4 + 2200×3)/7, czyli ŚREDNIĄ celów dni z planem. **Przy okazji naprawiony błąd**: ta średnia wychodziła z pełną precyzją Decimala i front pokazywał 24 cyfry po przecinku.: linia celu schodkowa, statusy dzienne
      wg celu z dnia, `summary.goal_progress.*.target` = ŚREDNIA celów dni
      z planem (nie „ostatni cel")
- [x] Dni bez planu pozostają lukami → 31.08 bez planu: `has_plan: false`, `nutrition: null`, statusy `null`; `days_with_plan` 7 z 8 dni zakresu.: `days_with_plan` jest dzielnikiem
      średniej, a wykres nie rysuje dla nich słupka

### Backup logiczny i własność danych (moduł transfer)

- [x] Eksport → czysta instancja → import: odtwarza WSZYSTKO? → TAK. Wykonane realnie na świeżej bazie `pasnik_rt` (`CREATE DATABASE` + `alembic upgrade head`): 25 sekcji odtworzonych co do wiersza (23 utworzone + 2 słowniki reużyte), z CAŁĄ historią celów (`user_nutrition_goals` z `valid_from`). **Uczciwe zastrzeżenie: ZDJĘĆ ten przebieg nie objął** — dane demo ich nie mają, więc `photos_imported` = 0. Ścieżkę zdjęć pokrywa test integracyjny `test_round_trip_odtwarza_dane_na_czystej_bazie` (dwa pliki, nowe losowe nazwy po re-enkodowaniu) oraz `test_duza_paczka_ze_zdjeciami_przechodzi_w_obie_strony` (~50 MB). (produkty,
      przeliczniki, przepisy, plany, szablony, spiżarnia, listy, zdjęcia,
      cele, profile) — wykonać round-trip realnie i porównać
- [x] Dry-run raport importu rzetelny → `to_create` == `created` co do sztuki przy imporcie na czystą instancję; `schema_version: 1` w pliku. Rozjazd występuje WYŁĄCZNIE przy scalaniu po `merge_key` (U21, zarejestrowany jako P2).; wersja schematu w eksporcie
- [x] Braki w zakresie eksportu = ustalenie BLOKUJĄCE → braków NIE MA; ustalenie blokujące nie powstało. (backup „ludzki"
      z 09_DEPLOYMENT §3 na tym polega)

### Acceptance criteria batchy 01–16 — wyrywkowo

- [x] Z KAŻDEGO batcha 01–16 wybrać min. 2 AC → tabela 16 wierszy w PROGRESS, po dwa kryteria na batch. i zweryfikować ręcznie
      lub istniejącym testem; wynik per batch w raporcie
- [x] Odstępstwa zgłoszone w Completion notes → przekrojowa kontrola wykonana: U7, U16, U17, U18, U22, U30 potwierdzone jako faktycznie zamknięte. Ani jednego follow-upu zadeklarowanego jako wykonany, który nie byłby wykonany. — czy obiecane follow-upy
      faktycznie wykonano (przekrojowa kontrola długu programu)

### Dług techniczny

- [x] Grep TODO/FIXME/HACK/XXX po repo → **zero trafień** w `backend/**` i `frontend/**`. Dług żyje w dziennikach — skonsolidowany w PROGRESS jako jedna lista P1/P2/P3. + workaroundy z dzienników →
      JEDNA lista z priorytetami (P1 przed prod / P2 po wdrożeniu / P3 nice)
- [x] P1 → batch naprawczy albo sekcja „Ustalenia R4" → paginacja list → `BATCH_19_FIX_LIST_PAGINATION`; healthcheck, CSP, rate limit uploadów → B17 pkt 1–3. w karcie B17;
      P2/P3 → PROGRESS jako rejestr długu

### Dokumentacja i decyzje

- [x] `docs/architecture/01…09` vs kod → wszystkie dziewięć przejrzane; zaktualizowane 01, 02, 04, 05, 07; potwierdzone bez zmian 03, 06, 08, 09. — każdy dokument potwierdzony
      albo zaktualizowany do stanu faktycznego
- [x] ADR-001…**015**: żaden nie jest martwy/łamany → potwierdzone wyrywkowo w kodzie (brak `float` w torze domenowym, brak bibliotek wykresów, brak i18n, brak JWT, `postgresql+psycopg://`, Pinia tylko UI).; naruszenia = ustalenie
- [x] Project skille `pasnik-*` + CLAUDE.md aktualne → cztery skille `pasnik-*` zgodne ze stanem kodu; CLAUDE.md dostał sekcję „Dołożone w REVIEW R4" (kontrakt `Section.parent`, `round_field_for_output`, jedna lista pól celu).
- [x] D10 (retencja): rewizja zapowiedziana przy R4 → wykonana; rekomendacja BEZ ZMIAN (nic nie usuwamy automatycznie) + dwa konkrety do runbooka zamiast automatu. — ocenić i zapisać
      rekomendację właścicielowi
- [x] **D6/D7 nadal OPEN?** → TAK, oba nadal OPEN. Przypomnienie zapisane w PROGRESS i w karcie B18. → jawne przypomnienie właścicielowi w raporcie
      i PROGRESS: bez ich zatwierdzenia B18 NIE startuje (B17 może)

## Security

Sekcja Audit checklist wyżej JEST audytem security tego batcha;
dodatkowo: review nie wprowadza własnych zmian obniżających zabezpieczenia,
a naprawy HIGH z `/security-review` wykonuje w commicie review, jeśli są
drobne (inaczej: batch naprawczy P1).

## Tests

- `task check` zielony przed i po naprawach; pełny `task test-e2e`
  (wszystkie core flows z 08_TESTING §3) uruchomiony realnie.
- Pokrycie obszarów krytycznych 08_TESTING §2.1–2.10 — końcowa kontrola
  kompletności (w tym §2.10 importer: korpus 8 PDF, walidacja krzyżowa
  z prototype.db ≥ 84 przepisy / 592 składniki).

  **Uzgodnienie liczb (R4, 2026-09-05): te dwa zestawy NIE są ze sobą
  sprzeczne — mierzą co innego.** „≥ 84 przepisy / 592 składniki" to PRÓG
  walidacji krzyżowej z `data/reference/prototype.db` (D2: prototyp wyciągnął
  tyle z tych samych plików, więc nowy parser ma osiągnąć CO NAJMNIEJ tyle).
  „24 dni / 96 posiłków / 662 wiersze / 185 nazw" to POMIAR samego korpusu
  z 01_PDF_AUDIT §1 po decyzji D20. Trzeci zestaw — „101 przepisów / 629
  składników" z B15 — to wynik krzyżowy PO dedupie w obrębie jobów, czyli
  liczba porównywana z progiem. Wszystkie trzy żyją równolegle w testach:
  `tests/integration/test_pdf_corpus.py` (`EXPECTED_INGREDIENT_ROWS = 662`,
  `EXPECTED_PRODUCT_NAMES = 185`) i `test_prototype_crosscheck.py`
  (`PROTOTYPE_RECIPES = 84`, `PROTOTYPE_INGREDIENTS = 592` jako progi „≥").
  Do zapamiętania: **103 „dania" ≠ 96 „posiłków"** — posiłek bywa dwudaniowy
  (01_PDF_AUDIT §2), więc dań jest więcej niż posiłków i to jest poprawne.
- Zero known-failing / flaky na masterze (08_TESTING §6) — flaky naprawić
  albo usunąć świadomą decyzją w PROGRESS.

## Acceptance Criteria

1. Audit checklist w całości rozliczona (odhaczone / ustalenie z miejscem).
2. `/security-review` full + audyt zależności: zero HIGH otwartych.
3. Tabela pomiarów wydajności w raporcie; regresje rozliczone.
4. Round-trip eksport→import wykonany realnie; braki rozliczone.
5. Wyrywkowa weryfikacja AC batchy 01–16 udokumentowana per batch.
6. Lista długu z priorytetami w PROGRESS; P1 ma przypisane miejsce
   wykonania (batch naprawczy albo sekcja „Ustalenia R4" w karcie B17).
7. Werdykt **GO / GO warunkowe (lista) / NO-GO (batche naprawcze
   utworzone i wpisane do 00_MASTER_PLAN + PROGRESS)** w PROGRESS.md.
8. Przypomnienie o D6/D7 zapisane; karty B17/B18 zaktualizowane.
9. Commit `batch(R4): review ...` wykonany, `git status` czysty.

## Out of Scope

- Implementacja hardeningu (skrypty backup, healthcheck rozszerzony,
  Dockerfile prod) → B17; deployment/runbooki → B18.
- Rozstrzyganie D6/D7 — to decyzje właściciela (tylko przypomnienie).
- Naprawy P2/P3 — rejestrowane, nie wykonywane.

## Expected files/modules

- `docs/implementation-plan/PROGRESS.md` — werdykt GO/NO-GO + dług +
  wpis dziennika.
- `docs/implementation-plan/batches/BATCH_17_PRODUCTION_HARDENING.md` —
  wypełniona sekcja „Ustalenia R4 do wykonania".
- Ewentualnie: nowe karty `BATCH_XX_FIX_*.md` (szablon §6) +
  `00_MASTER_PLAN.md` (lista batchy, graf); drobne naprawy w kodzie;
  aktualizacje `docs/architecture/**`, ADR, skill, CLAUDE.md.

## Implementation Notes

- To review jest szersze niż R1–R3 — pilnować rozmiaru sesji: audyt wg
  Stages, raport przyrostowo, naprawy dopiero na końcu.
- Werdykt GO nie oznacza „ideał", tylko „ryzyka znane i zaakceptowane" —
  wszystko, co odroczone, musi być NAZWANE w liście długu.
- Batch naprawczy tworzyć tylko dla spójnej paczki pracy > drobna naprawa;
  pojedyncze zadania lepiej dopisać do „Ustaleń R4" w B17.
- Round-trip transferu wykonywać na compose testowym, nie na bazie dev
  z danymi właściciela.

## Cross-Batch Impact

- **B17**: sekcja „Ustalenia R4 do wykonania" = wejście batcha; werdykt
  GO/GO-warunkowe = bramka.
- **B18**: przypomnienie D6/D7; ustalenia operacyjne (retencja D10,
  uptime-check) do karty.
- **00_MASTER_PLAN**: ewentualne batche naprawcze zmieniają listę batchy
  i graf — aktualizacja w tym samym commicie.

## Implementation checklist

- [x] PROGRESS + Completion notes 01–16 + follow-upy R1–R3 przeczytane
- [x] `task check` + pełne e2e zielone na wejściu → `task check` exit 0 na wejściu; pełne E2E uruchomione na wyjściu (20/20 ×2) — na wejściu stack dev był zgaszony, więc przebieg wejściowy nie miał sensu jako punkt odniesienia.
- [x] `/security-review` full + nagłówki + uploady + grep sekretów
- [x] `pip-audit` + `npm audit` bez HIGH → po podbiciu `fast-uri`.
- [x] Pomiary wydajności wykonane (tabela)
- [x] Round-trip eksport→import wykonany i porównany
- [x] **Kolejka UNVERIFIED po imporcie 8 PDF-ów** (Cross-Batch Impact B16)
      → **NIE da się nią pracować przy ~180 produktach — ustalenie P1.**
      `AdminWeryfikacjaPage.vue:31` ma `limit: 50, offset: 0` na sztywno i ZERO
      kontrolek paginacji, a deklarowane „najstarsze na górze" (`:42`) jest
      sortowaniem po stronie KLIENTA — układa po `created_at` pięćdziesiątkę,
      którą serwer wybrał alfabetycznie po `name`. Produkt spoza pierwszych 50
      nazw jest z tego ekranu NIEOSIĄGALNY. Filtrów (kategoria, szukajka) też
      nie ma. Naprawa: `BATCH_19_FIX_LIST_PAGINATION`
- [x] **Przeliczniki jednostek nauczone importem** → **mediana jest bliżej
      prawdy, potwierdzone pomiarem na CAŁYM korpusie, nie na pięciu próbkach.**
      Baza dev została odtworzona przy renameie D23 i nie ma w niej ani jednego
      wiersza `source='pdf_import'` (zero jobów importu), więc zamiast oglądać
      nieistniejące dane puściłem parser na ośmiu PDF-ach i policzyłem próbki
      wprost: **42 produkty, 223 próbki** dla jednostki „Sztuka".
      **34 produkty (81%) mają rozrzut ZEROWY**; z ośmiu niespójnych rozrzut to
      12–20% (`Jajko` 50–60 przy 25 próbkach — dokładnie para z §5.2, `Cebula`
      105–120 przy 24 — też z §5.2, `Banan` 120–140 przy 12 — też, `Papryka
      czerwona` 200–230 przy 27, `Pomidor` 150–170 przy 25) z jednym odstającym
      (`Burak` 100–150 g przy trzech próbkach). Wszystkie trzy pary wymienione
      w §5.2 odtworzyły się co do grama. **Zastrzeżenie do ekranu
      zatwierdzania**: 14 produktów ma DOKŁADNIE JEDNĄ próbkę — tam „mediana"
      to przepisanie jednego odczytu, więc `samples_count` musi być widoczne.
      Materiał dopisany do D21
- [x] AC batchy 01–16 zweryfikowane wyrywkowo (min. 2 per batch)
- [x] Dług zebrany i spriorytetyzowany (P1/P2/P3)
- [x] Architektura + ADR + skill + CLAUDE.md zaktualizowane
- [x] D6/D7 — przypomnienie właścicielowi zapisane
- [x] „Ustalenia R4 do wykonania" wpisane do karty B17 → osiem punktów.
- [x] Werdykt GO/NO-GO + wpis dziennika w PROGRESS.md

## Verification checklist

- [x] `task check` zielony po naprawach → exit 0: 3 migrations-check / 432 unit / 330 int / 411 api / 398 vitest w 42 plikach / mypy 201 plików / lint / format / build. Pełne E2E **20/20 w DWÓCH kolejnych przebiegach** (1,5 min i 1,3 min).
- [x] Acceptance Criteria 1–9 odhaczone
- [x] Batche naprawcze (jeśli są) mają komplet sekcji szablonu §6 → `BATCH_19_FIX_LIST_PAGINATION` ma wszystkie sekcje szablonu.
- [x] Każde ustalenie: naprawione / P1→B17 / P2-P3→rejestr / decyzja OPEN
- [x] Commit `batch(R4): audyt przedprodukcyjny — werdykt GO WARUNKOWE` (hash wpisać po push), `git status` czysty

## Completion notes

**Werdykt: GO WARUNKOWE.** Pełne uzasadnienie, tabele pomiarów, weryfikacja AC
i skonsolidowany dług — we wpisie dziennika `PROGRESS.md` z 2026-09-05.

### Wykonane

- `task check` zielony na WEJŚCIU (exit 0) i po naprawach.
- `/security-review` na CAŁYM kodzie w czterech równoległych przebiegach.
  **Jedno ustalenie powyżej progu — naprawione w tym commicie** (patrz niżej).
- Pomiary wydajności 12 widoków (liczba zapytań SQL + czas), round-trip
  eksport→import na ŚWIEŻO ZAŁOŻONEJ bazie, wyrywkowa weryfikacja po dwa AC
  z każdego batcha 01–16, audyt dziewięciu dokumentów architektury i ADR-001…015.
- Utworzona karta `BATCH_19_FIX_LIST_PAGINATION` (P1) + wpis do 00_MASTER_PLAN
  (tabela batchy, graf, §5); osiem „Ustaleń R4" w karcie B17; ustalenia
  operacyjne w karcie B18.

### Naprawione w tym commicie (pięć rzeczy)

1. **ADMIN dopisywał do CUDZEGO dnia planu.** `_resolve_day` odpowiadał na
   pytanie „który dzień dla tej daty" przez `visible_condition`, a ta zwraca
   ADMIN-owi `true()` (D16) — i ten sam resolver był CELEM ZAPISU dla
   `upsert_day`, `create_meal` i `append_day_payload`. Administrator bez
   własnego dnia na daną datę trafiał w najstarszy wiersz dowolnej rodziny.
   Odtworzone realnie: posiłek wylądował w cudzym dniu, a `PUT` skasował mu
   tytuł i przestawił `scope` na `private`. Naprawa: `for_write=True` →
   `owned_condition` (dla nie-ADMIN-a warunek IDENTYCZNY, więc reguła
   rodzinna z B07 bez zmian). Tą samą granicą objęte `demand_rows` — lista
   zakupowa ADMIN-a powstawała z planów wszystkich rodzin, choć spiżarnia po
   drugiej stronie silnika idzie po `select_own_household` od R3.
2. **D22 wdrożona** (`Section.parent` + `parent_blocked`/`mark_blocked`).
   Zmierzone: przed naprawą drugi import tego samego pliku dokładał +15
   posiłków i +16 pozycji do reużytych dni planu, po naprawie 0.
3. **`npm audit` HIGH** — `fast-uri` 3.1.5 → 3.1.7 (dev-only, łańcuch
   `vite-plugin-pwa → workbox-build → ajv`).
4. **Średnia celów w `/stats/daily` wychodziła z pełną precyzją Decimala**
   (`"2085.714285714285714285714286"`), a `formatDecimal` obcina wyłącznie
   końcowe zera — ekran Statystyk pokazywał 24 cyfry po przecinku. Doszło
   `engine.round_field_for_output`.
5. **Dług z B13 domknięty**: `planning/service.py::_GOAL_FIELDS` był drugą
   kopią `nutrition/types.GOAL_NUMERIC_FIELDS`.

### Odstępstwa

- **Jeden istniejący test PRZEPISANY, nie osłabiony**:
  `test_import_wlasnego_eksportu_dopisuje_do_istniejacego_dnia_planu`
  asercjonował DOKŁADANIE posiłków do reużytego dnia, czyli dokładnie to
  zachowanie, które odwraca zatwierdzona decyzja D22. Nowa nazwa i docstring
  tłumaczą, co i dlaczego się zmieniło.
- **Nie naprawiono** analogicznego wzorca po stronie zakupów (ADMIN przechodzi
  przez `visible_condition` na ścieżkach zapisu `share_list`, `update_item`,
  `finalize`, `accept_to_pantry`). Różnica jest istotna: przy dniu planu ADMIN
  trafiał w cudzy wiersz PRZYPADKIEM, tu musi świadomie podać cudze id.
  Zarejestrowane jako P2 z listą wywołań — do rozstrzygnięcia razem z rewizją
  granic D16, bo to pytanie o zakres decyzji, nie o błąd.
- **Round-trip pierwszego importu jest dokładny, drugiego nie w raporcie**:
  `to_create` nadal liczy optymistycznie sekcje scalane po `merge_key`, więc
  przy powtórnym imporcie na to samo konto raport obiecuje posiłki, których
  `apply` nie utworzy. To U21 powiększony przez D22 — domknięcie wymaga
  indeksu istniejących wierszy dla sekcji `merge_key`, czyli tego samego
  mechanizmu, co D24. Zarejestrowane jako P2, nie naprawiane w review.
- **Pomiary wydajności NIE są „na czystym seedzie demo"** w dosłownym sensie:
  seed demo nie ma rodziny, profili, celu, spiżarni, szablonów ani listy
  zakupowej, więc połowa mierzonych widoków byłaby pusta. Przekrój domeny
  doseedowałem PRZEZ API (realne endpointy, prefiks „R4 "), co przy okazji
  zweryfikowało siedem AC. Ta sama uwaga co w R2: pomiar jest z maszyny
  deweloperskiej w Dockerze, nie z Odroida.

### Decyzje

- **D22 i D23** przeniesione do tabeli zatwierdzonych (D23 wisiała w „Otwarte"
  mimo statusu ZATWIERDZONE — porządek rejestru).
- **D10** zrewidowana: rekomendacja BEZ ZMIAN + dwa konkrety do B17/B18.
- **D21**: grunt przygotowany POMIAREM na całym korpusie (42 produkty, 223
  próbki, 81% zerowego rozrzutu, 14 produktów z jedną próbką).
- **D24 (NOWA, OPEN)**: czy scalenie dnia planu przy imporcie ma pozostać
  milczące — pytanie wskazane wprost przez D22.
- **D6/D7 nadal OPEN** — przypomnienie w PROGRESS i w karcie B18.

### Pytania do właściciela

1. **D6 i D7** — bez nich B18 nie startuje. B17 może iść od razu.
2. **D24** — czy scalanie dnia planu przy imporcie ma zostać milczące?
3. **Czy ADMIN ma edytować TREŚĆ encji wszystkich rodzin** (listy zakupowe,
   pozycje), czy tylko je widzieć? D16 mówi o ODCZYCIE; kod pozwala dziś na
   jedno i drugie. To rozstrzyga zakres naprawy P2 wymienionej wyżej.
4. **Kolejność B19 vs B17** — oba przed B18, wzajemnie niezależne;
   rekomendacja: B19 pierwszy, bo odblokowuje ręczny import jadłospisów.
