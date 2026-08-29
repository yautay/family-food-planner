# BATCH_15 — PDF_IMPORT_EXTRACTION

Klasa: PLAT · Zależności: BATCH_05 (przepisy + silnik nutrition); zalecane
wykonanie po R3 (D2: importer nie później niż po R3) · Bramki decyzji: brak
· Rozmiar: **L** (sekwencyjnie — NIE równolegle z B12–B14).

## Goal

Powstaje pierwsza połowa importera PDF: upload pliku diety, deterministyczny
parser (maszyna stanów + regexy wg wiążącego kontraktu 01_PDF_AUDIT),
staging w bazie (staged_recipes/staged_ingredients/import_issues),
auto-sugestie mapowania EXACT po normalized_name i raport parsowania.
Parser udowadnia na realnym korpusie 8 PDF-ów, że wyciąga 96 posiłków,
642 składniki i 178 nazw produktów. Ekran review i zatwierdzanie — B16.

## Context

Batch zastaje (po B05, zalecane po R3):

- `backend/app/modules/importer/` — pusty szkielet modułu (ADR-001).
- `canonical_products.normalized_name` (unique) + logika normalizacji nazw
  z B04 (trim, zbicie spacji, lowercase — 01_PDF_AUDIT §5.3).
- Storage uploadów `/data/uploads` + wzorce upload/sniffing z B04/B05
  (zdjęcia); silnik nutrition (B05) — w tym batchu NIEużywany do walidacji
  kcal (to B16), ale struktura stagingu już przygotowuje pod nią pola.
- Korpus testowy: `data/source_pdfs/` — 8 plików (`dieta.pdf`,
  `dieta (1).pdf` … `dieta (7).pdf`); referencja `data/reference/prototype.db`.
- Mapa API rezerwuje `U /import/pdf`, `GET /import/jobs/...` (04_API §2).
- **Format transfer v1 ISTNIEJE (BATCH_14, 04_API „Format eksportu transfer v1")**
  — konsekwencje dla tego batcha: (a) encje stagingu (`import_jobs`,
  `staged_recipes`, `staged_ingredients`, `import_issues`) **NIE wchodzą** do
  eksportu v1 (staging to proces, nie dane domenowe), (b) przepisy
  `source=pdf_import` eksportują się normalnie, ale `recipes.import_job_id`
  w pliku jest `null` (job nie jest przenoszony) — to stan faktyczny, nie do
  „naprawienia" w B15, (c) **każda NOWA encja domenowa wymaga rozszerzenia
  serializera** (`transfer/serializer.py::SECTIONS` + `SECTION_ORDER`), a decyzję,
  czy staging kiedykolwiek ma tam wejść, podejmuje R4. (d) Migracja B15 dopina FK
  `recipes.import_job_id → import_jobs.id`; ta kolumna MUSI dostać `ForeignKey`
  w modelu w tym samym commicie (bramka dryfu modeli z R3).

Wymagane lektury (OBOWIĄZKOWO przed kodem): **01_PDF_AUDIT w całości —
to wiążący kontrakt tego batcha**; ADR-011; 03_DATABASE §9 (schemat
stagingu — dokładnie ten, bez wariacji) i §11 (storage); 02_DOMAIN §10;
07_SECURITY §6 (uploady); 08_TESTING §2.10.

## Stages

1. **Migracja stagingu** — 4 tabele wg 03_DATABASE §9; up/down testowane.
2. **Upload** — `POST /import/pdf`: limit 25 MB, sniffing `%PDF`, losowa
   nazwa, sha256, job `uploaded`.
3. **Ekstrakcja + klasyfikacja stron** — pdfplumber per strona: tytułowa /
   podsumowanie (lub list przewodni) / dzień / lista zakupów (POMIŃ) /
   wymienniki (POMIŃ).
4. **Parser posiłków** — maszyna stanów stron dni: nagłówki z makro,
   wiersze składników, sekcje tekstowe, suma kontrolna dnia; unit testy
   regexów zielone.
5. **Staging + issues + sugestie EXACT** — zapis do tabel, issues,
   mapowanie exact po normalized_name, `parse_report` JSONB, status `parsed`.
6. **UI** — upload, lista jobów, podgląd raportu parsowania.
7. **Testy korpusowe** — liczby z 01_PDF_AUDIT §1 jako asercje, anomalie
   §5.1 jako nazwane przypadki, walidacja krzyżowa z prototype.db (§8.6).
8. **Docs** — PROGRESS.md; odkrycia parsera → errata w 01_PDF_AUDIT
   (z pomiarem; kontrakt pozostaje wiążący).

## Database / migrations

Jedna migracja — cztery tabele DOKŁADNIE wg 03_DATABASE §9 (bez wariacji):
`import_jobs` (status ENUM uploaded/parsed/in_review/approved/rejected/
failed, parse_report JSONB, file_sha256), `staged_recipes` (day_label,
meal_label, instructions, comment, declared_servings, pdf_kcal, pdf_macros
JSONB W/B/T/Bł/ŁG; pola resolution/target_recipe_id/resolved_servings
wypełnia dopiero B16), `staged_ingredients` (raw_name/raw_qty/raw_unit/
grams, suggested_product_id, match_kind ENUM exact/fuzzy/ai/none,
confirmed_product_id, create_new_product), `import_issues` (kind ENUM —
wszystkie 6 wartości, severity ENUM blocker/warning, details JSONB).
ENUM-y od razu KOMPLETNE (także wartości używane dopiero w B16) — bez
migracji łamiącej. Numer = pierwszy wolny; `down_revision` z `alembic
heads`; `upgrade head` + `downgrade -1` + `upgrade head` na kopii bazy.

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/import/pdf` | POST | U | upload PDF → job (multipart; 25 MB; sniffing) |
| `/api/v1/import/jobs` | GET | U | lista jobów użytkownika (status, daty, liczby z raportu) |
| `/api/v1/import/jobs/{id}` | GET | U | szczegóły + `parse_report` |
| `/api/v1/import/jobs/{id}` | DELETE | U | usunięcie joba w stanie uploaded/parsed/failed (kasuje plik i staging) |

Parsowanie synchronicznie w request upload (8–10 stron = sekundy) —
w try/except z limitem czasu (07_SECURITY §6); wyjątek ⇒ status `failed`
+ `error`, plik zostaje do diagnozy.

`modules/importer/parser.py` — **czyste funkcje, bez I/O** (testowalne na
tekstach; 08_TESTING §1: parser w unit): wejście = strony tekstu
z pdfplumber, wyjście = struktury dataclass.

- **Klasyfikacja stron** (01_PDF_AUDIT §2): tytułowa (s. 1), podsumowanie
  LUB list przewodni (s. 2 — `dieta (2).pdf`!), strony dni
  (Poniedziałek/Wtorek/Środa), „Lista zakupów" — POMIŃ (układ dwukolumnowy
  nienadający się do ekstrakcji, §5.4), „Wymienniki" — POMIŃ (zawsze puste,
  §2.5). Nagłówek „Tydzień 1" ignorowany (bez znaczenia, §1).
- **Maszyna stanów w dniu**: stany OCZEKUJE_POSIŁKU → NAGŁÓWEK →
  SKŁADNIKI/SEKCJE → SUMA_DNIA. Posiłki w stałej kolejności ŚNIADANIE →
  OBIAD → PODWIECZOREK → KOLACJA; posiłek może mieć **>1 danie** (§2.3) —
  każde danie = osobny staged_recipe (name = nazwa dania, meal_label =
  posiłek, day_label = dzień + indeks pliku).
- **Regex nagłówka posiłku** (§3.1):
  `^(ŚNIADANIE|OBIAD|PODWIECZOREK|KOLACJA)\s+Kcal:\s*([\d.,]+)\s+W:\s*([\d.,]+)\s+B:\s*([\d.,]+)\s+T:\s*([\d.,]+)\s+Bł:\s*([\d.,]+)\s+ŁG:\s*([\d.,]+)`
  — kcal/makra do `pdf_kcal`/`pdf_macros`.
- **Regex wiersza składnika** (§3.2): kotwiczony od początku linii,
  `^(?P<name>.+?),\s*(?P<qty>\d+(?:,\d+)?)\s*x\s*(?P<unit>\S+)\s*\((?P<grams>\d+(?:,\d+)?)\s*g\)` +
  **tolerancja doklejonego tekstu instrukcji po nawiasie** (pdfplumber
  skleja kolumny — §3.2 pułapka); przecinek dziesiętny → Decimal;
  jednostki spotykane: Sztuka, Opakowanie, Łyżka, Łyżeczka, Plaster,
  Szklanka, Garść, Ząbek, Szczypta, Porcja, Kromka, Liść, Woreczek, Gałka.
  **Gramy z nawiasu = jedyne źródło ilości** (§8.3).
- **Sekcje tekstowe** (§3.3): `Przepis` (instrukcja — zbierana z prawej
  kolumny/reszty linii), `Komentarz`, `Przepis na N porcji` →
  `declared_servings=N`, `Zjedz 1 z N porcji` (potwierdzenie N),
  `Produkty` — DODATKOWE składniki poza przepisem wieloporcjowym,
  dołączane do dania posiłku (wliczone w makro — §3.3/§7).
- **Suma kontrolna dnia** (§4): `SUMA DNIA Kcal: …` — suma pdf_kcal
  4 posiłków musi = sumie dnia ±2 kcal; rozjazd ⇒ issue `parse_warning`
  (severity warning, details: oczekiwane/otrzymane) — sygnał błędu parsera.
- **Issues tego batcha**: `multi_portion_suspect` (severity **blocker**) —
  suma gramów składników dania > **800 g** i brak `declared_servings`
  (§5.1: 4 nieoznaczone przypadki w korpusie!); `parse_warning` (warning) —
  niesparsowana linia w sekcji składników, rozjazd sumy dnia, nieoczekiwana
  struktura. Pozostałe kind-y — B16.
- **Sugestie EXACT** (`importer/matching.py`): normalizacja raw_name (trim,
  zbicie spacji, lowercase — §5.3, ta sama funkcja co B04!) → dokładne
  trafienie w `canonical_products.normalized_name` ⇒
  `suggested_product_id` + `match_kind=exact`; brak ⇒ `match_kind=none`.
  **Bez AI i bez fuzzy w tym batchu** (B16).
- **`parse_report` JSONB**: `{pages: {total, days, skipped_shopping,
  skipped_exchanges}, days: N, meals: N, staged_recipes: N, ingredients: N,
  issues: {blocker: N, warning: N}, match: {exact: N, none: N},
  day_checksums: [{day, expected, computed, ok}]}`.

## Frontend

- `src/pages/ImportPage.vue` (trasa `/import`, link w nav „Więcej"/sidebar):
  - strefa uploadu (drag&drop + wybór pliku; walidacja rozszerzenia
    i rozmiaru po stronie klienta jako UX, prawda = serwer);
  - lista jobów: plik, data, status (badge PL: Wgrany/Sparsowany/
    W review/Zatwierdzony/Odrzucony/Błąd), liczby z raportu; puste stany
    uczące (06_UIUX §3.2);
  - podgląd raportu parsowania (drawer/sekcja): liczby posiłków/składników,
    issues z podziałem blocker/warning, sumy kontrolne dni (OK/rozjazd),
    procent zmapowanych exact. **Bez ekranu review** — przy jobie
    `parsed` informacja „Review i zatwierdzanie — wkrótce (kolejny etap)".
  - usunięcie joba = dialog z konsekwencjami (06_UIUX §3.3).
- `queryKeys.import.*`; mutacja uploadu z paskiem postępu.

## Security

- Upload wg 07_SECURITY §6: limit **25 MB** (413 przy przekroczeniu),
  sniffing nagłówka `%PDF` po treści (nie po rozszerzeniu/MIME), zapis pod
  `uuid4().hex + ".pdf"` na bind mount poza web-rootem, oryginalna nazwa
  tylko w `import_jobs.filename`; sha256 pliku zapisywany (deduplikacja
  informacyjna — ten sam plik = warning w raporcie, nie blokada).
- pdfplumber w try/except z limitem czasu; PDF nigdy nie renderowany
  server-side poza pdfplumber.
- Joby widoczne tylko dla właściciela (`owner_user_id`) i ADMIN — cudzy
  job = 404 (test anty-IDOR).
- Żadnych wywołań zewnętrznych (AI dopiero w B16) — parser w pełni offline.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-PDF
- **Recommended**: SKILL-CALC
- **Review**: SKILL-REVIEW

## Tests

- **Unit (parser, bez DB — na wyciętych tekstach):** regex nagłówka
  posiłku (wartości z §3.1: `ŚNIADANIE Kcal: 468 W: 31.3 …`); regex
  składnika: `Cebula, 0,3 x Sztuka (31,5 g)` → Decimal("31.5"),
  `Przecier pomidorowy, 6 x Łyżka (90 g)`; linia sklejona z instrukcją
  (przykład §7: `Cebula, 2 x Sztuka (210 g) Kapustę poszatkować…`) →
  składnik + reszta do instrukcji; sekcje `Przepis na 7 porcji`/`Zjedz 1
  z 7 porcji`/`Produkty` (przykład §7 w całości jako fixture); suma
  kontrolna dnia; klasyfikacja stron (lista zakupów/wymienniki pominięte).
- **Korpus (integration, realne pliki `data/source_pdfs/`) — asercje
  liczb z 01_PDF_AUDIT §1:**
  - 8 jobów parsuje się bez `failed`; łącznie **24 dni**, **96 posiłków**;
  - łącznie **642 wiersze składników** (642/642 z gramaturą);
  - **178 unikalnych znormalizowanych nazw** produktów;
  - sumy kontrolne: **24/24 dni** zgodne ±2 kcal (§4);
  - per plik: sumy dni = wartości z tabeli §1 (np. dieta.pdf: 2021, 1953,
    1919);
  - `dieta (2).pdf`: strona 2 (list przewodni) nie generuje posiłków ani
    błędu.
- **Anomalie §5.1 jako nazwane przypadki:**
  - `test_golabki_multi_portion_declared` — dieta.pdf OBIAD: 3305 g,
    pdf_kcal 635, `declared_servings=7`, BEZ issue;
  - `test_dieta5_obiad_declared_2` — 1018 g, `declared_servings=2`;
  - `test_multi_portion_suspect_unmarked` — 4 nieoznaczone przypadki:
    dieta (3) OBIAD 828 g/638, dieta (5) ŚNIADANIE 946 g/612 i KOLACJA
    1246 g/486, dieta (7) KOLACJA 806 g/554 — każdy z issue blocker;
  - `test_golabki_produkty_section` — `Produkty` (Ziemniak 225 g)
    dołączone do dania (§7).
- **Walidacja krzyżowa z `data/reference/prototype.db` (§8.6):** po
  sparsowaniu 8 jobów — liczba przepisów **zdeduplikowanych po
  znormalizowanej nazwie w obrębie jobów ≥ 84** i składników w tych
  przepisach **≥ 592**; różnice raportowane w output testu (materiał
  porównawczy, nie failure jeśli ≥).
- **API:** upload happy path; nie-PDF (sniffing) ⇒ 422; >25 MB ⇒ 413;
  cudzy job ⇒ 404; DELETE kasuje plik i staging; parsowanie nie tworzy
  ŻADNEJ encji domenowej (asercja liczników — niezmiennik 02_DOMAIN §13.6).
- **vitest:** lista jobów (statusy PL), render raportu parsowania.
- **E2E:** login → upload `dieta.pdf` → job `parsed` → raport widoczny
  (12 posiłków; gołąbki oznaczone „na 7 porcji" ⇒ bez blockera).

## Acceptance Criteria

1. Upload PDF (≤25 MB, sniffing) tworzy job i parsuje synchronicznie;
   błąd parsowania ⇒ status `failed` z komunikatem, nie 500.
2. Korpus 8 plików: 96 posiłków, 642 składniki, 178 nazw, 24/24 sumy
   kontrolne — potwierdzone testami na realnych plikach.
3. Strony „Lista zakupów" i „Wymienniki" pomijane; list przewodni
   `dieta (2).pdf` nie psuje parsowania.
4. Dania >800 g bez „Przepis na N porcji" dostają issue
   `multi_portion_suspect` (blocker) — dokładnie 4 przypadki w korpusie.
5. Składniki z nazwą istniejącą w katalogu dostają `match_kind=exact`
   + `suggested_product_id`; reszta `none`. Zero wywołań AI.
6. `parse_report` zawiera liczby: posiłki/składniki/issues/sumy dni.
7. Nic nie trafia do encji domenowych (recipes/products) — tylko staging.
8. UI: upload, lista jobów ze statusami, podgląd raportu.
9. Walidacja krzyżowa: ≥84 przepisy (dedup po nazwie) / ≥592 składniki
   względem prototype.db.
10. Migracja odwracalna; `task check` zielony.

## Out of Scope

- Ekran review, rozstrzyganie porcji/mapowań, approve/reject → **B16**
  (endpointy `resolve/approve/reject` NIE powstają tutaj).
- AI (fuzzy mapowania, duplikaty, sugestie porcji) → B16 (ADR-011).
- Walidacja kcal wyliczone vs PDF (`kcal_mismatch`) → B16 (wymaga mapowań).
- Zasilenie `product_unit_weights` próbkami → B16 (przy approve).
- Import listy zakupów z PDF — świadomie NIGDY (decyzja §5.4).

## Expected files/modules

- `backend/migrations/versions/<pierwszy_wolny>_importer_staging.py` (N)
- `backend/app/modules/importer/models.py`, `schemas.py`, `parser.py`
  (czysty), `matching.py` (exact), `service.py` (upload/parsowanie/staging),
  `router.py` (N)
- `backend/app/core/config.py` (M — limit PDF), `main.py` (M — router)
- `backend/tests/unit/test_pdf_parser.py`,
  `backend/tests/integration/test_pdf_corpus.py` (realne pliki!),
  `test_prototype_crosscheck.py`, `backend/tests/api/test_import_api.py` (N)
- `frontend/src/pages/ImportPage.vue` (N), `src/api/queryKeys.ts` (M),
  nawigacja (M)
- `frontend/e2e/import-upload.spec.ts` (N)

## Implementation Notes

- **Kontrakt > pomysłowość**: każde odstępstwo od 01_PDF_AUDIT (np. nowy
  wzorzec linii) → najpierw pomiar, potem errata + wpis PROGRESS. Nie
  „ulepszać" regexów na zapas.
- Testy korpusowe pisać RÓWNOLEGLE z parserem (TDD po liczbach z §1).
- Dedup do walidacji krzyżowej (§8.6): po znormalizowanej nazwie dania
  W OBRĘBIE zaparsowanych jobów — scalanie fizyczne to B16.
- Prawa kolumna: tekst po dopasowanym składniku dokleja się do bufora
  instrukcji dania — czytelność do review wystarczy, perfekcyjny skład
  nie jest celem.
- Masa do progu 800 g = suma `grams` składników przepisu głównego, BEZ
  sekcji `Produkty` (to dodatek jednoporcjowy — §7); odstępstwo wymaga
  erraty w 01_PDF_AUDIT.
- `prototype.db` czytać sqlite3 read-only w teście, schemat introspekcją —
  NIE kopiować z niego danych (D2!).
- Status `in_review` ustawia dopiero B16 — tu joby kończą na `parsed`.

## Cross-Batch Impact

- **B16** zależy 1:1 od tego batcha: schemat stagingu (ENUM-y kompletne!),
  `parser.py`/`matching.py` jako fundament, joby `parsed` jako wejście.
  Po zakończeniu B15 zaktualizować sekcję Context karty B16 o faktyczne
  ścieżki plików i ewentualne odstępstwa.
- **B14 (transfer)**: staging NIE wchodzi do eksportu v1; przepisy
  `source=pdf_import` (powstaną w B16) eksportują się z `import_job_id=null`.
- **R4**: przegląd jakości parsera (flaki testów korpusowych?) i decyzja
  o ewentualnym imporcie kolejnych formatów PDF (nowy audyt = nowy kontrakt).
- Kategorie z §5.5 były seedem w B04 — różnice wyrównać (wpis w PROGRESS).
- **Ustalenie REVIEW R3 (2026-08-22) — kolejność POTWIERDZONA, bez zmiany
  planu.** B15 startuje po B12/B13/B14 (D2: „nie później niż po R3", nie
  „natychmiast po R3”), bo trzy batche równoległe są krótsze i nie wchodzą
  w moduł `recipes`, a odkładanie ich za importer zablokowałoby jedyną
  dozwoloną równoległość planu (00_MASTER §5). **Warunek twardy: B15 i B16
  wchodzą PRZED B17/B18** — baza ma dziś 15 produktów demo i zero przepisów
  poza seedem, więc bez importera nie ma czego chronić w produkcji.
  Podniesienie priorytetu B15 do równoległości z B12/B13 ODRZUCONE: B15
  dokłada migrację stagingu i dotyka `recipes`, a B14 remapuje referencje
  w payloadach — dwie migracje w równoległych worktree łamią zasadę „jedna
  głowa po merge'u".
- **Dwie bramki wykonawcze dołożone w R3**, które dotyczą każdej nowej tabeli
  tego batcha: wpis licznika referencji do rodziny (jeśli tabela ma
  `household_id` — `households.service.register_household_reference_finder`)
  oraz `ForeignKey` W MODELU dla każdej kolumny, której constraint dopina
  migracja (bramka dryfu `test_modele_nie_dryfuja_od_schematu_po_migracjach`).
  Uwaga wprost dla tego batcha: `recipes.import_job_id` czeka na `import_jobs`
  z B15 BEZ constraintu — migracja B15, która go dopina, MUSI w tym samym
  commicie uzupełnić model `Recipe`, inaczej bramka dryfu zaświeci czerwono
  (to dokładnie ten sam dług, który R3 domknął dla `pantry_items`).

## Implementation checklist

- [ ] Migracja stagingu (pełne ENUM-y) + up/down na kopii bazy
- [ ] Upload: limit 25 MB, sniffing `%PDF`, losowa nazwa, sha256
- [ ] Klasyfikacja stron (tytułowa/podsumowanie/list/dni/zakupy/wymienniki)
- [ ] Maszyna stanów: nagłówki posiłków + makra → pdf_kcal/pdf_macros
- [ ] Regex składnika: przecinek dziesiętny + tolerancja sklejonej instrukcji
- [ ] Sekcje: Przepis / Komentarz / Przepis na N / Zjedz 1 z N / Produkty
- [ ] Suma kontrolna dnia ±2 kcal → parse_warning przy rozjeździe
- [ ] Issue multi_portion_suspect (>800 g bez oznaczenia, blocker)
- [ ] Matching EXACT (wspólna normalizacja z B04) + parse_report JSONB
- [ ] UI: upload + lista jobów + raport
- [ ] Testy: unit regexy, korpus (96/642/178/24), anomalie §5.1, crosscheck
      prototype.db (≥84/≥592), API, vitest, E2E
- [ ] PROGRESS.md + aktualizacja Context karty B16

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] Testy korpusowe na 8 realnych plikach zielone (nie mocki!)
- [ ] `alembic upgrade head` + `downgrade -1` + `upgrade head` przechodzi;
      jedna głowa
- [ ] Ręcznie: upload dieta.pdf → raport z liczbami zgodnymi z audytem
- [ ] Asercja niezmiennika: zero nowych recipes/canonical_products po
      uploadzie i parsowaniu
- [ ] Acceptance Criteria 1–10 odhaczone z dowodem
- [ ] Dokumentacja i PROGRESS.md zaktualizowane; commit `batch(15): …`

## Completion notes

(wypełnia agent wykonujący)
