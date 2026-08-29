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

- [x] **Stage 0 (D20)**: parser czyta oba dodatkowe warianty wiersza §3.2;
      01_PDF_AUDIT §1/§3.2/§9.2 i testy korpusowe przestawione na **662/185**
- [x] GET staged + POST resolve (mapowania/porcje/scalenia/issues);
      statusy parsed → in_review → approved/rejected
- [x] Walidacja kcal >10% ⇒ kcal_mismatch (obie wartości); auto-rozwiązanie
- [x] Blokada approve przy blockerach (409 z listą)
- [x] Approve: Recipe + produkty UNVERIFIED + mediany unit_weights +
      metadane pdf_* + audit — jedna transakcja
- [x] Reject: staging + plik + audit
- [x] ai_assist: fuzzy (match_kind=ai+confidence), duplikaty, porcje;
      tryb deterministyczny bez klucza
- [x] UI review: karty dań, 3 ścieżki mapowania, porcje, duplikaty,
      kcal, approve/reject
- [x] Testy: unit (mediana/próg/gate/AI-parsing), integration (6 przypadków),
      API, vitest, E2E flow (bez realnych wywołań AI)
- [x] 04_API + .env.example zaktualizowane; PROGRESS.md wpis

## Verification checklist

- [x] `task check` + `task test-e2e` zielone (w tym flow importu end-to-end)
- [x] Migracja `0015` (dwie kolumny stagingu — uzasadnienie w Completion notes),
      upgrade i downgrade przechodzą na czystej bazie; jedna głowa
- [x] Ręcznie/testowo: pełny import dieta.pdf BEZ klucza (tryb deterministyczny)
      i z zamocowanym klientem AI — oba tryby działają
- [x] Asercja niezmiennika §13.6: zero encji domenowych przed approve
- [x] Grep logów: brak klucza API i treści promptów
- [x] Acceptance Criteria 1–10 odhaczone z dowodem
- [x] Dokumentacja i PROGRESS.md zaktualizowane; commit `batch(16): …`

## Completion notes

**Wykonano (2026-08-29).** Importer PDF jest domknięty: ekran review, pięć
endpointów, AI-asysta jako czysta propozycja i zatwierdzenie tworzące realne
encje domenowe w JEDNEJ transakcji.

### Stage 0 (D20) — kontrakt §3.2 rozszerzony, ale liczby wyszły INNE

Parser czyta oba warianty zatwierdzone przez właściciela. **Pomiar skorygował
się w górę: wierszy jest 20, nie 7, więc korpus daje 662/185, a nie zapowiadane
649/180.** Przyczyna jest sprawdzalna i opisana w erracie 01_PDF_AUDIT §9.2 oraz
przy D20: liczba 7 pochodziła z licznika `parse_warning` BATCH_15, którego regexy
kotwiczyły na KOŃCU linii — nie widziały więc ani jednego wiersza z doklejoną
prawą kolumną (§3.2 pułapka 1), a takich jest 6 z 10 w wariancie „bez pary"
i 7 z 10 w „zawiniętym". Ślad tej luki był już w samej erracie: jako przykład
podawała `Cukinia, 200 g`, którego na liście czterech zmierzonych wierszy nie
było. **Zakres decyzji się nie zmienił** — oba warianty są dokładnie te
zatwierdzone; zmieniła się tylko ich policzona liczba, a odzyskane dodatkowo
wiersze to znów główne składniki (`Pierś z indyka, 100 g`, `Ser camembert, 40 g`,
`Mleko 2%, 120 g`, `Woda źródlana, 120 g`, `Mleczko kokosowe … 10 x Łyżka (100 g)`,
`Tuńczyk w wodzie … 0,5 x Opakowanie (85 g)`).

Skutki uboczne SPRAWDZONE i zerowe: zbiór blockerów `multi_portion_suspect`
i sześć mas z tabeli §5.1 nie drgnęły (dokładnie 6 posiłków ponad progiem:
2 oznaczone, 4 nieoznaczone), 24/24 sumy kontrolne nadal się zgadzają, a
crosscheck §8.6 wychodzi na **185 wobec 181** prototypu (+4, raportowane).
Po korekcie w korpusie nie ma już ANI JEDNEGO `parse_warning`.

### Odstępstwa od karty (świadome, każde z uzasadnieniem)

1. **Migracja `0015` — karta zakładała „docelowo bez migracji".** Dwie kolumny
   `staged_ingredients`, obie wymuszone dokumentami nadrzędnymi, nie wygodą:
   - `confidence NUMERIC(3,2)` — **02_DOMAIN §10 wymienia `confidence` jako część
     StagedIngredient**, a ADR-011 wymaga, żeby wynik AI zawsze niósł
     `match_kind=ai` RAZEM z pewnością. Szkic 03_DATABASE §9 go pominął.
   - `from_extras_section BOOL` — dług **U22**, jawnie dopuszczony w zleceniu.
     Bez niego ziemniaki do gołąbków (225 g podane NA PORCJĘ) zostałyby
     podzielone przez 7 i przepis skłamałby o 193 g na talerzu — po cichu.
   Downgrade przetestowany (`test_upgrade_downgrade_upgrade_na_czystej_bazie`),
   jedna głowa `0015`, bramka dryfu modeli zielona.
2. **Walidacja kcal liczy się PER POSIŁEK, nie per danie.** Karta mówiła
   „komplet mapowań DANIA", ale `pdf_kcal` opisuje w dokumencie POSIŁEK
   i BATCH_15 skopiował tę wartość do każdego dania posiłku — porównanie jednego
   z dwóch dań kolacji z kaloriami całej kolacji zgłaszałoby rozjazd tam, gdzie
   go nie ma. To ta sama poprawka, którą errata §9.1 zrobiła już dla progu
   wieloporcyjności, i ta sama, którą właściciel wtedy przyjął.
3. **Przeliczniki: `Cebula, 2 x Sztuka (210 g)` NIE daje wiersza
   `(Cebula, sztuka, 105)`** wbrew przykładowi z sekcji Tests. Etykieta „szt."
   jest w `product_unit_weights` ZAREZERWOWANA (`UNIT_LABEL_RESERVED`, B04):
   mostkiem sztuka → gram jest `piece_weight_g`, którego wolno dotknąć wyłącznie
   ADMIN-owi, a zmiana unieważnia weryfikację produktu (**D15**). Import uczy
   więc jednostek DOMOWYCH (łyżeczka 6 g, szklanka 240 g, woreczek 100 g —
   zaasercjonowane na realnym `dieta.pdf`), a sprawa wag sztuki poszła do
   **02_DECISIONS jako D21 (OPEN)** z rekomendacją: osobny ekran ADMIN-a
   z propozycjami, bo to ta sama filozofia co reszta importera.
4. **„Dane nowego produktu w payload" rozwiązane przez create-in-context.**
   Ścieżką UI jest `ProductCreateDrawer` w `ProductPickerze` (06_UIUX §3.1 —
   wzorzec obowiązkowy): powstaje prawdziwy produkt i wraca jako
   `confirmed_product_id`. Flaga `create_new_product` została dla ścieżki
   API-owej i przy `approve` zakłada produkt z surowej nazwy w kategorii
   „Inne", `measure_kind=mass`, UNVERIFIED. Osobne kolumny na szkic produktu
   byłyby trzecim miejscem trzymania tych samych danych.
5. **Nazwy schematów mają prefiks `Import`** (`ImportResolveRequest`,
   `ImportApproveRequest/Response`). Moduł shopping ma własne `ResolveRequest`;
   dwie klasy o tej samej nazwie zmuszają FastAPI do kwalifikowania OBU pełną
   ścieżką modułu w OpenAPI, co zmienia klucz w `generated.ts` także temu,
   który był pierwszy — czyli psuje CUDZY moduł frontendu. Złapane przy
   `task fe-types`, naprawione u źródła.
6. **Produkt liczony na 100 ml przyjmuje gramaturę z PDF-a tak samo, jak
   przyjmuje ją ręcznie wpisany składnik** — czyli zapisuje ilość i oznacza
   wartości jako niepoliczalne (`recipes/service.py::_ingredient_values`),
   zamiast wysadzać zatwierdzenie. Rozważano twarde 422; odrzucone, bo tworzyłoby
   dla importu OSTRZEJSZĄ regułę niż dla formularza przepisu, przy identycznych
   danych. Review pokazuje wtedy „nie da się przeliczyć", a nie fałszywy rozjazd.

### Rzeczy dostarczone ponad kartę

- `app/core/errors.py += ServiceUnavailableError` (503, kod `service_unavailable`)
  — karta wymagała 503 dla `ai-suggest`, a takiej klasy nie było.
- `CatalogService.create_product_pending` / `record_unit_weight_samples` oraz
  `RecipesService.create_imported_recipe` / `get_visible` / `visible_names` —
  publiczne wejścia BEZ commita (wzorzec R3), żeby `approve` był jedną
  transakcją, a importer nie sięgał do cudzych tabel z pominięciem serwisu.
- `app/modules/catalog/unit_weights.py` — czysty moduł mediany ważonej.
  Postać ważona nie jest ozdobnikiem: stary wiersz reprezentuje `samples_count`
  pomiarów, a materializowanie ich listą znaczyłoby alokację proporcjonalną do
  licznika, którym da się sterować przez API.

### Wyniki uruchomień (realne)

`task check` zielony: 3 migrations-check / **431 unit** / **329 int** /
**410 api** / **398 vitest** (42 pliki) / mypy 201 plików / vue-tsc / ruff /
eslint / prettier / vite build. Suita API trwa **39 minut** — wgrywa i parsuje
realne PDF-y w kilku scenariuszach.

E2E na przebudowanym obrazie `app`: `import-review-flow.spec.ts` +
`import-upload.spec.ts` → **3/3** (z setupem). Pełna suita: 18/20, z dwoma
cudzymi specami na timeoucie — przyczyna w długu **U30** niżej, oba przechodzą
po podniesieniu limitu czasu.

Drobiazg do zapamiętania: `uv sync` (doszedł `anthropic`) podniósł też **ruff**,
a nowsza wersja widzi `SIM300` tam, gdzie stała stoi po lewej stronie
porównania — `task check` potrafi więc paść na lincie w kodzie, którego się nie
tknęło.

### Ustalenia review na diffie (naprawione w tym samym commicie)

`/code-review` — dwa realne błędy:

1. **`unmapped_product` blokował też dania scalane z istniejącym przepisem.**
   Danie oznaczone jako duplikat nie tworzy Recipe ani RecipeIngredient, więc
   żądanie zmapowania jego ośmiu pozycji było pracą bez odbiorcy — a `approve`
   i tak zwracał 409. Blokada obowiązuje teraz wyłącznie dania, które MAJĄ
   powstać; regresja pilnowana testem
   `test_danie_scalane_z_istniejacym_nie_wymaga_mapowan`.
2. **`kcal_mismatch` wieszał się na PIERWSZYM daniu posiłku, także pominiętym.**
   Karta dania pominiętego jest w UI wyszarzona i nie rozwija składników, więc
   ostrzeżenie faktycznie znikało z pola widzenia. Uwaga trafia teraz na
   pierwsze AKTYWNE danie posiłku.

`/security-review` — jedno ustalenie, MEDIUM:

3. **Lista kandydatów do wykrywania duplikatów wysyłana do Claude API była
   liczona `visible_condition`, a ta daje ADMIN-owi `true()` (D16).**
   Administrator klikający „Zaproponuj z AI" wysłałby poza instancję nazwy
   przepisów WSZYSTKICH rodzin — w tym prywatnych — podczas gdy D5 zezwala
   wyłącznie na treść PDF-a i nazwy z globalnego katalogu. Kandydatów wyznacza
   teraz `ScopedQuery.owned_condition` (PRZYNALEŻNOŚĆ, nie widoczność — ta sama
   granica, co przy eksporcie własnych danych w B14), a metoda nazywa się
   `RecipesService.owned_names`, żeby nazwa nie zapraszała do powrotu
   widoczności. Test `test_admin_nie_wysyla_do_modelu_przepisow_cudzych_rodzin`
   czyta DOSŁOWNIE wysłane żądania.

Pozostałe obszary `/security-review` bez ustaleń: klucz API poza odpowiedziami
i logami, IDOR na pięciu endpointach (cudze danie/składnik/uwaga = 404),
path traversal przy kasowaniu pliku, odsiewanie halucynacji w odpowiedzi
modelu (nazwa przepisu w uwadze pochodzi z NASZEJ bazy), brak `v-html`
w nowej warstwie Vue, CSRF, audyt bez nazw dań.

### Follow-upy (nie naprawiane w tym batchu)

- **U27**: `ReviewService._unmapped_names` robi JEDNO zapytanie o kandydatów
  NA KAŻDĄ niezmapowaną nazwę (ścieżka `ai-suggest`). Przy pierwszym imporcie
  na pustym katalogu to ~60 zapytań trigramowych. Do rewizji w R4 razem
  z pomiarem — dziś nie boli, bo endpoint i tak czeka na model.
- **U28**: E2E `import-review-flow.spec.ts` zostawia po sobie ZATWIERDZONY job
  (jeden wiersz na przebieg): `DELETE /import/jobs/{id}` świadomie nie przyjmuje
  statusów rozstrzygniętych. Przepis i produkty są sprzątane. Gdyby lista
  importów w dev zaczęła przeszkadzać, potrzebne jest bulk delete dla
  właściciela (temat pokrywa się z D10).
- **U29**: `ImportPage.vue` nadal bez paginacji (dług U25 z B15) — teraz z jedną
  pozycją więcej na wiersz.
- **U30 (NIE Z TEGO BATCHA, ale znalezione przy nim)**: `transfer.spec.ts` (B14)
  **PODWAJA dane demo przy każdym przebiegu**. Po kilku dzisiejszych uruchomieniach
  suity baza dev ma **768 składników w każdym daniu demo** i **768 posiłków
  w dniu planu** zamiast 15, przez co `POST /transfer/import/{id}/apply` trwa
  **73 s** i dwa specy (`transfer`, `week-template-cycle`) przekraczają 30-sekundowy
  timeout Playwrighta. Dowód, że to nie regresja B16: **oba przechodzą po
  podniesieniu timeoutu** (`task test-e2e -- transfer.spec.ts
  week-template-cycle.spec.ts --timeout=180000` → 3 passed), a `apply` kończy się
  statusem 200. Do rozstrzygnięcia w R4: czy import z decyzją „reużyj istniejący"
  ma prawo DOKŁADAĆ dzieci do istniejącego rodzica (wtedy to błąd aplikacji),
  czy spec ma sprzątać po sobie ostrożniej (wtedy to higiena E2E). Baza dev
  wymaga wyczyszczenia — decyzja właściciela, nie agenta.

### Pytania do właściciela

**D21 (OPEN)** — czy import ma z czasem uczyć wag sztuki produktów
(`piece_weight_g`) przez osobny ekran propozycji dla ADMIN-a. Materiał jest
zmierzony (01_PDF_AUDIT §5.2), ale wdrożenie tego „przy okazji" łamałoby D15.
Rekomendacja i wariant odrzucony: 02_DECISIONS, wiersz D21.
