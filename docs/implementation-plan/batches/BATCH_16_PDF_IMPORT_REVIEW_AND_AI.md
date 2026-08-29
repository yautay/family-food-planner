# BATCH_16 — PDF_IMPORT_REVIEW_AND_AI

Klasa: PLAT · Zależności: BATCH_15 (staging + parser), BATCH_04 (katalog,
ProductPicker) · Bramki decyzji: **D5 — ZATWIERDZONA** (2026-08-16: wolno
wysyłać treść PDF do Claude API; klucz server-side; AI tylko proponuje)
· Rozmiar: **L** (sekwencyjnie).

## Goal

Domyka importer PDF: ekran review joba (mapowanie składników, porcje,
scalanie duplikatów, walidacja kcal), AI-asysta propozycji (wyłącznie
sugestie) oraz approve tworzący prawdziwe Recipe + produkty + próbki
`product_unit_weights` + metadane walidacyjne + audit. Po tym batchu
właściciel przerabia 8 PDF-ów dietetyczki na ~90 przepisów — baza
przestaje być pusta (D2).

## Context

Batch zastaje (po B15 + B04):

- Staging kompletny (03_DATABASE §9): joby `parsed` z `parse_report`;
  `staged_recipes` (`pdf_kcal`/`pdf_macros`/`declared_servings`; pola
  `resolution`/`target_recipe_id`/`resolved_servings` puste — wypełniane
  tutaj); `staged_ingredients` (`match_kind` exact/none;
  `confirmed_product_id`/`create_new_product` puste); `import_issues`
  (`multi_portion_suspect` blocker, `parse_warning`). ENUM-y już
  zawierają wartości potrzebne w B16 — **bez migracji**.
- `backend/app/modules/importer/` — `parser.py`, `matching.py` (exact),
  `service.py`, `router.py` (upload/lista/raport); `ImportPage.vue`.
- B04: `canonical_products` + `product_unit_weights`, `ProductPicker` +
  `ProductCreateDrawer` (inline create — wzorzec obowiązkowy), produkty
  od USERA = `UNVERIFIED` (02_DOMAIN §4.9).
- B05: silnik nutrition; `recipes.source ENUM(manual,pdf_import)`,
  `recipes.import_job_id`. Audit serwis (B03/B04); `ANTHROPIC_API_KEY`
  w env (07_SECURITY §7) — może być pusty.

**Stan faktyczny po BATCH_15 (2026-08-29) — przeczytaj przed Stage 1:**

- **Ścieżki plików**: `backend/app/modules/importer/{models,parser,matching,
  schemas,service,router}.py`; migracja `0014_importer_staging.py`; front:
  `frontend/src/pages/ImportPage.vue`, `frontend/src/api/pdfImport.ts`
  (nie `import.ts` — `import` to słowo kluczowe TS), klucze
  `queryKeys.import.*`, trasa i pozycja nawigacji `import`.
- **`multi_portion_suspect` wisi na POSIŁKU, nie na daniu** (errata
  01_PDF_AUDIT §9.1): próg 800 g liczy się od masy wszystkich dań posiłku
  razem z sekcją `Produkty`, a `staged_recipe_id` issue wskazuje NAJCIĘŻSZE
  danie posiłku. Ekran review musi więc pytać o liczbę porcji w kontekście
  posiłku (dwa dania jednej kolacji mogą dzielić jedno rozstrzygnięcie).
  W korpusie: 4 blockery, dokładnie te z tabeli §5.1.
- **Sekcja `Produkty` NIE jest oznaczona w bazie.** Schemat 03_DATABASE §9
  nie ma na to kolumny, a B15 nie dokładał wariacji, więc dodatki
  jednoporcjowe (Ziemniak do gołąbków) leżą w `staged_ingredients` jak zwykłe
  składniki. **To ma znaczenie przy skalowaniu**: przepis „na 7 porcji"
  dzieli się przez 7, a ten dodatek NIE. Jeśli B16 ma to rozróżniać, potrzebna
  jest kolumna (np. `from_extras_section BOOL`) i migracja — decyzja należy do
  B16, bo dopiero on skaluje. Przypadków w korpusie: 3 (dieta, dieta 5, dieta 7).
- **7 wierszy składników nie jest sparsowanych** i wraca jako `parse_warning`
  z surową linią (errata §9.2). **Decyzja D20 ZATWIERDZONA 2026-08-29: rozszerzyć
  kontrakt §3.2 o oba warianty — TO JEST ROBOTA TEGO BATCHA** (patrz Stage 0
  niżej). Nie jest to „ulepszenie parsera na zapas": właściciel rozstrzygnął,
  a bez tego przepisy z importu byłyby po cichu uboższe o główne składniki
  (`Kapusta włoska, 200 g`, `Makaron pełnoziarnisty, 60 g`, `Kefir, 330 g`,
  `Passata, 150 g`, 3× czekolada).
- **3 ze 103 nazw dań są ucięte** przez zawijanie kolumn (errata §9.5). Pełne
  nazwy stoją na stronie podsumowania PDF-a; ekran review i tak pozwala nazwę
  poprawić, ale warto o tym wiedzieć przy wykrywaniu duplikatów.
- **Statusy**: B15 zostawia joby w `parsed`; `in_review` ustawia dopiero B16.
  Usuwanie joba działa dla `uploaded`/`parsed`/`failed` (inaczej 409) —
  `reject` z tego batcha musi więc przestawić status, a nie kasować przez
  `DELETE /import/jobs/{id}`.
- **Liczniki referencji już są**: `importer/service.py` rejestruje
  `_staging_using_product` i `_staging_using_recipe`. Nowa tabela albo nowe FK
  w B16 = nowy licznik w tym samym batchu (R3).
- **Endpointy review NIE istnieją** i pilnuje tego test
  `tests/api/test_import_api.py::test_endpointy_review_jeszcze_nie_istnieja` —
  po dołożeniu ich w B16 ten test trzeba USUNĄĆ (nie osłabić).

Wymagane lektury: **ADR-011**, 01_PDF_AUDIT §5 i §8, 03_DATABASE §9,
02_DOMAIN §10 i §13.6, 04_API §2, 02_DECISIONS D5, 08_TESTING §2.10 i §3
(E2E flow 4), 06_UIUX §3 (create-in-context, destrukcja bezpieczna).

## Stages

0. **Rozszerzenie kontraktu §3.2 (decyzja D20, ZATWIERDZONA 2026-08-29)** —
   parser czyta dwa dodatkowe warianty wiersza składnika: bez pary
   ilość + jednostka (`Cukinia, 200 g` → `raw_qty`/`raw_unit` puste, `grams`
   z liczby) i zawinięty między dwie linie (`…, 2 x` + `Kostka (16 g)`).
   Robić PRZED resztą batcha: zmienia dane wejściowe każdego kolejnego etapu.
   Cztery rzeczy do wykonania razem ze zmianą parsera, inaczej bramka padnie:
   (a) **01_PDF_AUDIT §1 i §9.2** — liczby rosną na **649 wierszy / 180 nazw**;
   (b) `tests/integration/test_pdf_corpus.py` — `EXPECTED_INGREDIENT_ROWS`,
   `EXPECTED_PRODUCT_NAMES` i `test_niesparsowane_wiersze_skladnikow_sa_
   zgloszone_a_nie_zgadniete` PRZESTAWIĆ na nowe liczby (nie osłabiać);
   (c) `tests/unit/test_pdf_parser.py::test_linia_wygladajaca_na_skladnik_ale_
   niezgodna_z_kontraktem_daje_ostrzezenie` opisuje zachowanie, które ta decyzja
   zmienia — przepisać z „ostrzega" na „parsuje", zostawiając ostrzeżenie dla
   linii, które NADAL nie pasują do kontraktu;
   (d) crosscheck §8.6 zbliży się do 181 nazw prototypu — różnicę raportować
   jak dotąd, nie zamieniać na twardą asercję równości.
1. **Endpoint staged + resolve** — `GET /import/jobs/{id}/staged`,
   `POST .../resolve` (mapowania, porcje, scalanie); status `in_review`.
2. **Walidacja kcal** — wyliczone silnikiem vs `pdf_kcal`; rozjazd >10%
   ⇒ issue `kcal_mismatch` z obiema wartościami.
3. **Approve/Reject** — approve: transakcja tworząca Recipe + produkty +
   próbki unit_weights + audit; reject: kasuje staging i plik.
4. **AI-asysta** — `ai_assist.py`: fuzzy mapowania, duplikaty między
   jobami, sugestia porcji; brak klucza = tryb deterministyczny.
5. **UI review** — ekran review joba (mapowanie, porcje, duplikaty,
   issues, blokada approve); flow end-to-end od uploadu.
6. **Testy + docs** — round-trip dieta.pdf, mock AI, E2E; PROGRESS.md,
   04_API o szczegóły endpointów.

## Database / migrations

**Docelowo bez migracji** — B15 utworzył pełny schemat z kompletnymi
ENUM-ami. Migracja korygująca dozwolona TYLKO przy odstępstwie B15
(sprawdzić jego Completion notes); numer = pierwszy wolny, down testowany.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/import/jobs/{id}/staged` | GET | U | staged recipes + ingredients + issues + propozycje AI |
| `/api/v1/import/jobs/{id}/resolve` | POST | U | zapis decyzji: mapowania / porcje / scalenia / rozstrzygnięcia issues |
| `/api/v1/import/jobs/{id}/ai-suggest` | POST | U | uruchom AI: fuzzy mapowania + duplikaty + porcje (idempotentne; 503 gdy brak klucza — patrz niżej) |
| `/api/v1/import/jobs/{id}/approve` | POST | U | zatwierdzenie → tworzy encje domenowe; 409 przy blockerach |
| `/api/v1/import/jobs/{id}/reject` | POST | U | odrzucenie → usuwa staging i plik PDF |

`importer/review_service.py`:

- **Resolve** (przyrostowo, wielokrotnie): per składnik —
  `confirmed_product_id` (potwierdzenie sugestii lub wybór z pickera) ALBO
  `create_new_product=true` (dane nowego produktu w payload); per danie —
  `resolved_servings` (rozstrzygnięcie `multi_portion_suspect`, int ≥1)
  i `resolution`: `create` (default) / `merge_into_existing` +
  `target_recipe_id` / `skip`; rozstrzygnięcia issues (`resolution`,
  `resolved_at`). Pierwszy resolve przełącza job `parsed → in_review`.
- **Walidacja kcal** (po każdym resolve, gdy komplet mapowań dania):
  kcal per porcja = silnik nutrition / `resolved_servings ??
  declared_servings ?? 1`; `|wyliczone − pdf_kcal|/pdf_kcal > 0.10` ⇒
  issue `kcal_mismatch` (warning) z `details: {computed, pdf, delta_pct}`;
  poprawa mapowania poniżej progu ⇒ issue auto-rozwiązane.
- **Blokada approve**: nierozwiązany issue `blocker`
  (`multi_portion_suspect` bez `resolved_servings`; `unmapped_product` —
  składnik bez `confirmed_product_id` i bez `create_new_product`) ⇒ 409
  z listą blokad w `details`.
- **Approve** (jedna transakcja): nowe produkty z `create_new_product`
  (UNVERIFIED, wartości uzupełnia ADMIN — 02_DOMAIN §4.9); per danie
  `create`: Recipe (`source=pdf_import`, `import_job_id`, `base_servings =
  resolved_servings ?? declared_servings ?? 1`, instructions+comment,
  scope wybrany przy approve) + RecipeIngredient z gramami
  (display_qty/display_unit z raw); `merge_into_existing` ⇒ bez nowego
  Recipe; **próbki `product_unit_weights`** z par ilość×jednostka×gramy —
  mediana per (produkt, unit_label), `samples_count`, `source="pdf_import"`
  (istniejąca para ⇒ mediana z połączonych próbek, patrz Implementation
  Notes); `pdf_kcal`/`pdf_macros` zostają w stagingu jako metadane
  walidacyjne (staging zatwierdzonego joba NIE jest kasowany — 03_DATABASE
  §12); audit (`import.approve`, liczby); status `approved`.
- **Reject**: DELETE staging (kaskady) + plik z dysku + audit → `rejected`.

`importer/ai_assist.py` (ADR-011, D5):

- anthropic SDK, klucz i model z env (`ANTHROPIC_API_KEY`); **brak klucza
  ⇒ tryb deterministyczny**: `ai-suggest` zwraca 503 z komunikatem PL,
  UI chowa przyciski AI; reszta flow działa w 100%.
- Zadania (wyłącznie propozycje — nigdy zapis do danych domenowych):
  1. **fuzzy mapowania**: niezmapowane raw_names + kandydaci z katalogu →
     propozycje zapisywane do `suggested_product_id` + `match_kind=ai`
     + `confidence` (0–1) — wymagają potwierdzenia w review;
  2. **duplikaty między jobami**: nazwy staged vs istniejące Recipe
     i staged innych jobów ⇒ issue `duplicate_recipe` (warning)
     z kandydatem scalenia;
  3. **sugestia porcji** z treści instrukcji („około 21 szt" itp.) —
     TYLKO podpowiedź w `details` issue `multi_portion_suspect`;
     nigdy auto-ustawienie `resolved_servings`.
- Wywołania z limitem czasu i budżetem tokenów; wynik walidowany Pydantic —
  odpowiedź niezgodna ze schematem = zignorowana propozycja, nie 500.

## Frontend

- `src/pages/ImportReviewPage.vue` (`/import/jobs/:id/review`; wejście
  z listy jobów przy statusie `parsed`/`in_review`):
  - nagłówek: plik, postęp (zmapowane/wszystkie, issues), „Zaproponuj
    z AI" (tylko gdy asysta dostępna), Zatwierdź (disabled + tooltip
    z listą blockerów), Odrzuć (dialog konsekwencji);
  - lista staged dań pogrupowana dzień/posiłek; karta dania: nazwa,
    pdf_kcal vs kcal wyliczone (obie wartości + delta%, plakietka przy
    `kcal_mismatch`), badge issues;
  - wiersz składnika: raw_name + ilość/gramy + 3 ścieżki mapowania —
    potwierdź sugestię exact/ai (z confidence) jednym kliknięciem /
    **ProductPicker** / „+ Utwórz nowy" inline (`ProductCreateDrawer`,
    create-in-context 06_UIUX §3.1; UNVERIFIED przy approve);
  - porcje: przy `multi_portion_suspect` pole „Na ile porcji jest ten
    przepis?" + ewentualna sugestia oznaczona jako „propozycja AI";
  - duplikaty: porównanie obok siebie + „Scal z istniejącym"
    (`merge_into_existing`) / „To osobny przepis";
  - zapis decyzji przyrostowy (resolve po każdej akcji, optimistic);
  - po approve: podsumowanie utworzonych encji + link do katalogu przepisów.
- `ImportPage.vue` (M): „Przejdź do review" przy `parsed`/`in_review`;
  statusy `approved`/`rejected` z podsumowaniem.

## Security

- D5/ADR-011: do Claude API idzie WYŁĄCZNIE treść z PDF + nazwy produktów
  z katalogu — nigdy dane użytkowników/rodzin; klucz wyłącznie server-side
  (env), nieobecny w odpowiedziach API i logach.
- AI nie ma ścieżki zapisu: wyniki tylko w `suggested_*`/`details`
  stagingu; match_kind=ai bez `confirmed_product_id` NIE przechodzi approve.
- Approve/reject tylko właściciel joba lub ADMIN (cudzy job = 404);
  mutacje za CSRF; reject faktycznie usuwa plik z dysku (test).
- Niezmiennik 02_DOMAIN §13.6 pilnowany testem: przed approve zero zmian
  w recipes/canonical_products/product_unit_weights.
- Rate limit na `ai-suggest` (koszt API) — np. 10/min/user.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE, SKILL-PDF, SKILL-API
- **Recommended**: SKILL-SEC
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **Unit:** mediana `grams_per_unit` (parzysta/nieparzysta liczba próbek,
  łączenie z istniejącym rekordem); próg kcal (9.9% bez issue, 10.1%
  z issue); macierz blokady approve (blocker × unmapped ×
  create_new_product); parsowanie odpowiedzi AI (schemat uszkodzony ⇒
  propozycja odrzucona).
- **Integration:**
  1. **nic przed approve**: pełny resolve → liczniki recipes/products/
     unit_weights bez zmian; dopiero approve tworzy (08_TESTING §2.10);
  2. **approve happy path** (dieta.pdf): gołąbki → Recipe
     `base_servings=7`, `source=pdf_import`, `import_job_id` ustawione,
     kcal per porcja z silnika ≈ 635 (tolerancja mapowań testowych),
     sekcja Produkty (ziemniaki) wliczona;
  3. unit_weights: `Cebula, 2 x Sztuka (210 g)` → (Cebula, sztuka, 105);
     wiele próbek ⇒ mediana; konflikt z istniejącą wagą ⇒ nowa mediana;
  4. `merge_into_existing` nie tworzy duplikatu Recipe;
  5. reject usuwa staging (kaskady) i plik z dysku; audit ma wpisy
     approve i reject;
  6. approve przy nierozwiązanym blockerze ⇒ 409 z listą, zero zapisów.
- **AI (mock — ZERO realnych wywołań API w testach):** klient anthropic
  mockowany; fuzzy zapisuje match_kind=ai + confidence; brak klucza ⇒
  503 i flow ręczny działa; sugestia porcji tylko w details issue.
- **API:** macierz uprawnień (cudzy job 404; anonim 401); resolve
  waliduje `resolved_servings ≥ 1`.
- **vitest:** karta dania (obie wartości kcal przy mismatch), wiersz
  składnika (3 ścieżki), blokada przycisku Zatwierdź z tooltipem.
- **E2E (flow 4 z 08_TESTING §3):** upload `dieta.pdf` → review →
  potwierdzenie mapowań (seed katalogu przez API) → gołąbki: 7 porcji →
  zatwierdzenie → przepis „Gołąbki bez zawijania" w katalogu z poprawnymi
  wartościami per porcja. Env testowy bez klucza (tryb deterministyczny).

## Acceptance Criteria

1. Review pokazuje staged dania joba z issues, stanem mapowań i kcal
   wyliczone vs PDF przy każdym zmapowanym daniu.
2. Składnik: potwierdź sugestię / wybierz ProductPickerem / utwórz nowy
   inline (UNVERIFIED przy approve).
3. `multi_portion_suspect` rozstrzygalny podaniem liczby porcji;
   `duplicate_recipe` — scaleniem lub odrzuceniem propozycji.
4. Rozjazd kcal >10% ⇒ issue `kcal_mismatch` z obiema wartościami w UI.
5. Approve zablokowany (409 + czytelna lista) przy blockerach; przed
   approve ŻADNA encja domenowa nie powstaje.
6. Approve tworzy: Recipe (source=pdf_import, import_job_id, poprawne
   base_servings), produkty UNVERIFIED, próbki product_unit_weights
   (mediana), audit; pdf_kcal/pdf_macros zachowane jako metadane.
7. Reject usuwa staging i plik PDF; wpis audit.
8. AI: fuzzy z match_kind=ai+confidence, duplikaty między jobami,
   sugestia porcji — wyłącznie propozycje; brak klucza = pełnosprawny
   tryb deterministyczny.
9. E2E: pełny flow dieta.pdf → review (gołąbki 7 porcji) → przepis
   z poprawnymi wartościami per porcja; testy z mockiem AI.
10. `task check` zielony.

## Out of Scope

- AI proponujące wartości odżywcze nowych produktów — FUTURE (dopisać
  propozycję do 02_DECISIONS).
- Edycja treści przepisu w review (poprawki po imporcie — edycja z B05).
- Inne formaty PDF niż korpus dietetyczki (nowy audyt = nowy kontrakt).
- Automatyczne planowanie z diet (plan buduje się narzędziami B06/B07).
- Batch processing wielu jobów jednym approve.

## Expected files/modules

- `backend/app/modules/importer/review_service.py`, `ai_assist.py` (N);
  `matching.py`, `service.py`, `schemas.py`, `router.py` (M —
  staged/resolve/ai-suggest/approve/reject)
- `backend/app/core/config.py` (M — `ANTHROPIC_API_KEY`, model, limity),
  `.env.example` (M)
- `backend/tests/unit/test_unit_weights_median.py`, `test_kcal_validation.py`,
  `test_approve_gate.py`, `test_ai_parsing.py` (N);
  `backend/tests/integration/test_import_review_flow.py`,
  `test_import_approve.py` (N); `backend/tests/api/test_import_review_api.py` (N)
- `frontend/src/pages/ImportReviewPage.vue`,
  `src/components/domain/StagedRecipeCard.vue`, `StagedIngredientRow.vue` (N);
  `ImportPage.vue`, `src/api/queryKeys.ts`, router (M)
- `frontend/e2e/import-review-flow.spec.ts` (N)
- `docs/architecture/04_API_DESIGN.md` (M — endpointy review)

## Implementation Notes

- **Mediana z połączonych próbek**: tabela trzyma tylko medianę
  i samples_count. Aproksymacja: stara mediana × samples_count + nowe
  próbki → mediana całości (udokumentować w kodzie); alternatywa (tabela
  próbek) = zmiana schematu ⇒ wpis w 02_DECISIONS. Wpisów
  `source='manual'` NIE nadpisywać (admin wygrywa).
- Kolejność: resolve/approve BEZ AI najpierw (etapy 1–3, pełny flow
  ręczny); AI jako nakładka (etap 4) — wartość batcha bezpieczna przy
  problemach z API.
- Walidacja kcal tylko gdy wszystkie zmapowane produkty dania mają
  komplet wartości; inaczej „nie można zweryfikować (produkty bez
  wartości)" zamiast fałszywego mismatchu (nowe UNVERIFIED są bez wartości).
- Prompt AI: few-shot z parami z 01_PDF_AUDIT §5.3 (Skyr/Skyr pitny,
  Maliny/mrożone…); wymuszać JSON (tool use), temperatura niska.
- Scope przepisów: jeden select dla całego joba przy approve (default
  household, jeśli user ma rodzinę) — nie per danie.
- `dieta (3).pdf` OBIAD 828 g = realny test progu — NIE podnosić 800 g,
  żeby „naprawić" issue (kontrakt §5.1).

## Cross-Batch Impact

- **R4**: przegląd jakości danych po imporcie 8 plików (UNVERIFIED do
  uzupełnienia przez ADMIN — praca właściciela); `/security-review`
  obejmuje ai_assist (klucz, wycieki).
- **B14 (transfer)**: przepisy `source=pdf_import` eksportują się
  z `import_job_id=null`; staging nie podlega eksportowi.
- **B17 (hardening)**: `ANTHROPIC_API_KEY` w prod env `chmod 600`; dopisać
  do checklisty B17 weryfikację, że klucz nie występuje w logach.
- **B04/ADMIN**: rośnie kolejka weryfikacji UNVERIFIED — jeśli widok
  weryfikacji w Adminie jej nie udźwignie, follow-up w PROGRESS.
- **Ustalenie REVIEW R3 (2026-08-22)**: kolejność B15 → B16 po B12/B13/B14
  potwierdzona (uzasadnienie w karcie B15), z warunkiem twardym „przed
  B17/B18" z D2. Przepisy wnoszone importerem dostają `household_id` przez
  `ownership_for_create`, więc od razu wchodzą do rejestru liczników
  referencji do rodziny (R3) — masowy import robi z rodziny encję
  nieusuwalną i tak ma być, ale komunikat 409 pokaże wtedy pierwsze 20 nazw
  (`USED_IN_LIMIT`), nie wszystkie.

## Implementation checklist

- [ ] GET staged + POST resolve (mapowania/porcje/scalenia/issues);
      statusy parsed → in_review → approved/rejected
- [ ] Walidacja kcal >10% ⇒ kcal_mismatch (obie wartości); auto-rozwiązanie
- [ ] Blokada approve przy blockerach (409 z listą)
- [ ] Approve: Recipe + produkty UNVERIFIED + mediany unit_weights +
      metadane pdf_* + audit — jedna transakcja
- [ ] Reject: staging + plik + audit
- [ ] ai_assist: fuzzy (match_kind=ai+confidence), duplikaty, porcje;
      tryb deterministyczny bez klucza
- [ ] UI review: karty dań, 3 ścieżki mapowania, porcje, duplikaty,
      kcal, approve/reject
- [ ] Testy: unit (mediana/próg/gate/AI-parsing), integration (6 przypadków),
      API, vitest, E2E flow (bez realnych wywołań AI)
- [ ] 04_API + .env.example zaktualizowane; PROGRESS.md wpis

## Verification checklist

- [ ] `task check` + `task test-e2e` zielone (w tym flow importu end-to-end)
- [ ] Bez migracji (lub korygująca z testem down); jedna głowa
- [ ] Ręcznie: pełny import dieta.pdf z kluczem AI (jeśli dostępny)
      i bez klucza — oba tryby działają
- [ ] Asercja niezmiennika §13.6: zero encji domenowych przed approve
- [ ] Grep logów: brak klucza API i treści promptów
- [ ] Acceptance Criteria 1–10 odhaczone z dowodem
- [ ] Dokumentacja i PROGRESS.md zaktualizowane; commit `batch(16): …`

## Completion notes

(wypełnia agent wykonujący)
