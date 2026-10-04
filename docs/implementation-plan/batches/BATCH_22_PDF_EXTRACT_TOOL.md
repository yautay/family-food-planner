# BATCH_22 — PDF_EXTRACT_TOOL

Klasa: DEVTOOL (narzędzie deweloperskie poza runtime aplikacji) · Zależności:
**B21 DONE** (przepisy `global`), B14/R4/B20 (format transferu v1, D22, D24),
B04 (`catalog.units`, `catalog.naming`), B05 (`nutrition/engine.py`) · Bramki
decyzji: **D31 — ZATWIERDZONE 2026-10-03** (narzędzie poza aplikacją, wynik =
paczka transferu); **D32** (zakres `global`) ZATWIERDZONE · Rozmiar: **L** ·
Sekwencyjnie, **PO B21**; z B18 nie koliduje (inne pliki).

## Goal

Komenda `/pdf-extract <plik.pdf>` w Claude Code wykonuje na jadłospisie
dietetyka tę samą pracę analityczną, którą 2026-10-03 wykonano ręcznie na
`dieta.pdf`:

1. wyciąga z PDF-a przepisy, składniki, miary, sumy posiłków/dni i listę zakupów;
2. zestawia produkty z tym, co **już jest** (wcześniejsze wersje w
   `data/diet-imports/`, opcjonalnie lista produktów z eksportu instancji, nazwy
   z seedu demo) i **proponuje scalenia do akceptacji** właściciela;
3. **weryfikuje obliczenia** prawdziwym kodem aplikacji (nie kopią wzorów) i
   pokazuje, które liczby odbiegają od PDF-a i o ile;
4. po zatwierdzeniu raportu generuje **paczkę transferu** (`export.json` v1 w
   ZIP-ie), którą właściciel wgrywa zwykłym importem (`/admin/dane` albo
   „Kopia danych rodziny”); przepisy mogą mieć zakres `global` (B21).

Wynik każdego przebiegu jest **wersjonowany w repo** (`data/diet-imports/NNNN-slug/`),
a kolejny przebieg używa produktów z poprzednich wersji zamiast ich
redefiniować. Aplikacja nie dostaje ani linii kodu runtime (D25/ADR-016 bez
zmian), a PDF-y nigdy nie wchodzą do gita (D27).

## Context

- **Wzorzec pracy (dogfood)**: wersja `0001` jest wynikiem analizy `dieta.pdf`
  (Tydzień I, pon–śr, 12 posiłków). Jej wynik jest już w repo:
  `data/diet-imports/0001-dieta-2000/spec.draft.json` — 44 produkty (po
  scaleniach zatwierdzonych przez właściciela), 12 przepisów, 68 składników,
  sumy z PDF-a i lista zakupów; sumy gramów po produktach zgadzają się co do
  grama z listą zakupów z PDF-a. **Ten plik jest wejściem testowym i punktem
  odniesienia B22; `spec.json` wersji 0001 ma z niego powstać (konwersja do
  schematu docelowego), nie od zera.** Decyzje właściciela są w jego polu
  `decisions` — wiążące.
- **Wnioski z ręcznej analizy, które narzędzie MUSI zakodować** (każdy to
  realny błąd, który wyszedł dopiero przy sprawdzeniu):
  1. `normalize_amount("Sztuka")` dla produktu spoza `PIECE` rzuca
     `UnitConversionError` nawet przy istniejącym przeliczniku (etykieta
     jest sprowadzana do `szt.`, a ta wymaga `PIECE`). Surowy zapis składnika
     „5 x Sztuka” pieczarek kończy się 422 przy pierwszej edycji w UI. Reguła:
     jednostka domowa nierozwiązywalna przez `normalize_amount` → gramy.
  2. Ten sam przelicznik daje inne gramy niż PDF (łyżka śmietany 54 g/3 vs
     100 g/4; jajko 50 vs 60 g; pomidor 150 vs 170 g; cebula 105 vs 120 g).
     Reguła: jeśli `ilość × przelicznik` odbiega od gramów z PDF-a ponad próg
     (domyślnie 10%), zapisz gramy (`display_unit='g'`), a „2 x łyżka” w `note`.
  3. Scalanie produktów (drób, skyr, mozzarella, śmietana) przesuwa
     wartości odżywcze — raport MUSI pokazać skutek scalenia (różnica kcal
     posiłku przed/po) obok propozycji.
  4. „Obliczenia z PDF-a” liczone na gramach z PDF-a nie dowodzą niczego o
     aplikacji — weryfikacja idzie przez `normalize_amount` →
     `to_basis_amount` → `nutrition/engine.py`.
  5. Wartości odżywcze z internetu rozjeżdżają się mocno (np. kiełbasa śląska
     176–309 kcal/100 g); kompromis = środek zakresu źródeł, a gdy źródła się
     rozjeżdżają, kotwicą są sumy z PDF-a. Raport pokazuje zakres źródeł.
  6. Erytrytol i podobne polialkohole dietetyk liczy jako 0 węglowodanów —
     bez tego kolacja z erytrytolem wychodzi +10 g węgli.
- **Transfer jako nośnik** (`backend/app/modules/transfer/`): `export.json`
  (`schema_version: 1`, `scope: "user"`), sekcje w kolejności `SECTION_ORDER`,
  ID w pliku to referencje wewnętrzne, liczby jako stringi dziesiętne (ADR-008).
  Sekcje, które paczka wypełnia: `product_categories` (po nazwie — kategorie
  istnieją z `0005`), `tags` (`śniadanie`/`obiad`/`kolacja` systemowe +
  `podwieczorek` niesystemowy), `canonical_products`, `product_unit_weights`,
  `recipes`, `recipe_ingredients`, `recipe_tags`. Import scala produkty po
  `normalized_name` i przepisy po nazwie (D22: reużyty przepis nie dostaje
  drugiego kompletu składników), a raport DRY-RUN pokazuje `to_create`.
  Właściciel i rodzina przepisów to konto importujące (`IdMap` z fallbackiem
  na aktora); `scope` w pliku jest klonowany, ale od B21 import **obcina `global`
  zawsze dla pliku `scope=user`** (także gdy wczytuje go ADMIN — **D33, OPEN**,
  rekomendacja: zostaje). `global` przeżywa wyłącznie kopia INSTANCJI
  (`scope: "instance"`, tylko ADMIN ją wczyta) i tylko dla przepisu, którego
  zmapowany właściciel (sekcja `users`, reużycie po e-mailu) ma rolę ADMIN.
- **Ścieżki i polecenia**: Taskfile jest jedynym wejściem (CLAUDE.md §3) —
  nowe targety `pdfx-*`; kod w `backend/scripts/pdf_extract/` (pakiet,
  `backend/scripts/` jest pakietem od B10), testy `unit`/`integration`.
- **Produkcja poza zasięgiem sesji AI** (CLAUDE.md §3): narzędzie niczego nie
  wgrywa; kończy na paczce, raporcie i teście importu na bazie TESTOWEJ.

Wymagane lektury: 02_DECISIONS **D31**, **D32**, **D25**, **D27**, **D11**,
**D22**, **D24**; ADR-016, ADR-004, ADR-005, ADR-008; 02_DOMAIN §4, §5, §6,
§11; 04_API §2 („Format eksportu transfer v1”); CLAUDE.md §4 (`catalog/units.py`,
`nutrition_adapter.py`, `scripts/` jako pakiet, „Dołożone w BATCH_20”),
`backend/app/modules/transfer/{serializer,importer,schemas}.py`,
`data/diet-imports/0001-dieta-2000/spec.draft.json`.

## Stages

0. **Baseline**: `task check` zielony na HEAD (po B21); `git status` czysty w
   zakresie plików batcha.
1. **Schemat `spec.json`** (`backend/scripts/pdf_extract/spec.py`, Pydantic v2,
   `extra="forbid"`): produkt (klucz, nazwa, kategoria, `measure_kind`,
   `piece_weight_g`, wartości na 100 g/ml jako stringi, IG, przeliczniki,
   `merged_from`, `nutrition_source`, zakres źródeł), przepis (dzień, posiłek,
   nazwa, instrukcja, komentarz, sumy z PDF, składniki z `pdf_qty`/`pdf_unit`/
   `pdf_grams` i decyzją zapisu), decyzje (lista tekstów), sumy dnia z PDF-a,
   lista zakupów z PDF-a. **Brak pól na dane osobowe** (imię, nazwisko, kontakt) —
   `extra="forbid"` i test, który to wymusza. Konwersja
   `spec.draft.json` (0001) → `spec.json`.
2. **Indeks katalogu** (`catalog_index.py`): ładuje WSZYSTKIE
   `data/diet-imports/*/spec.json`, nazwy z `scripts/seed_demo.py` (jako
   „demo”) i opcjonalnie `--instance-export <export.json>` (eksport instancji
   ADMIN-a — produkty założone ręcznie w UI); klucz = `normalize_name` z
   `catalog/naming.py` (NIE własna funkcja). Zwraca dla każdej nazwy z nowego
   PDF-a: trafienie dokładne (reużyj), kandydatów podobnych (do propozycji
   scalenia) albo „nowy”. Konflikt definicji (ta sama nazwa, inny
   `measure_kind`) = błąd zatrzymujący, nie ciche nadpisanie.
3. **Weryfikacja** (`verify.py`): dla każdego składnika `normalize_amount` →
   `to_basis_amount`; reguła jednostek z Context pkt 1–2; sumy posiłków i dni
   przez `nutrition/engine.py` (wejście wyłącznie `ProductNutrition`); suma
   gramów per produkt vs lista zakupów z PDF-a (próg ±5%). Progi (konfigurowalne
   w `spec.json`, wartości domyślne): posiłek ±10% kcal = ostrzeżenie, ±15% =
   błąd do rozstrzygnięcia; dzień ±5% kcal; makro dnia ±10%; ŁG tylko
   informacyjnie (IG z tabel jest zbyt niepewne). Wyjście: struktura
   `VerificationReport` (czysta, bez I/O — ADR-008).
4. **Paczka** (`package.py`): `spec.json` → `export.json` v1 + ZIP; wartości
   dziesiętne jako stringi, `verification_status="unverified"`,
   `nutrition_source` z `spec.json`; ID wewnętrzne stabilne i deterministyczne
   (ten sam spec = bajtowo ta sama paczka). `--recipe-scope {household,private,global}`
   (domyślnie `household`); `global` (B21 DONE) wymaga paczki z nagłówkiem
   `scope: "instance"` i sekcją `users` z kontem ADMIN-a (`--owner-email`) jako
   właścicielem przepisów (D33) oraz adnotacji w raporcie, że wgrywa ADMIN w sekcji
   „Instancja"; paczka `scope=user` z `global` zostałaby obcięta do `household`.
   Nieznana wartość `scope` w sekcji = 422 już w DRY-RUN. Struktury sekcji budowane z `serializer.SECTIONS`/
   `section_columns` — nie przepisuj listy kolumn.
5. **Raport** (`report.py`): `report.md` — propozycje scaleń (tabela: kandydaci,
   skutek kcal), produkty reużyte vs nowe, odstępstwa wag sztuk, rozbieżności
   z PDF-em per posiłek/dzień (policzone przez silnik), składniki zapisane
   jako gramy i dlaczego, źródła wartości odżywczych z zakresem, ostrzeżenia
   (np. składniki wspomniane w instrukcji, a nieobecne na liście; puste
   instrukcje). Bez danych osobowych.
6. **Skill** (`.claude/skills/pdf-extract/SKILL.md`, frontmatter z `name`,
   `description`; wzorzec struktury — `skill-creator`): procedura z DWIEMA
   bramkami zatwierdzenia (patrz „Skill — procedura”), reguły jednostek,
   zakaz wgrywania na produkcję, zakaz kopiowania PDF-a do repo, sposób
   weryfikacji wartości w sieci (`WebSearch`, zakres źródeł, kompromis).
7. **Taskfile**: `pdfx-index`, `pdfx-verify -- <spec>`, `pdfx-package --
   <spec> [--recipe-scope …]`, `pdfx-roundtrip -- <zip>` (import na bazie
   TESTOWEJ przez `TransferService`, dwa razy, porównanie liczników).
8. **Dogfood**: uruchom `/pdf-extract` na `dieta.pdf` (plik leży poza
   gitem — `docs/dieta.pdf` albo `data/source_pdfs/`, oba w `.gitignore`);
   wynik: `data/diet-imports/0001-dieta-2000/{spec.json,report.md,export.zip}`.
   Porównaj z `spec.draft.json`: różnice liczbowe muszą mieć wyjaśnienie
   w Completion notes (silnik vs gramy z PDF-a).
9. **Dokumenty**: CLAUDE.md (nowy blok „Dołożone w BATCH_22”: komenda, katalog
   `data/diet-imports/`, zasady), `03_AI_SKILLS.md`, README (jedna sekcja:
   „Jak dodać jadłospis dietetyka”), `docs/OPERATIONS.md`/runbook importu —
   JEDEN akapit: właściciel wgrywa paczkę z `/admin/dane`, nie agent.
10. **Weryfikacja**: `task check`, `task pdfx-roundtrip` na paczce 0001,
    grep prywatności (patrz AC), PROGRESS.

## Skill — procedura (treść `SKILL.md`)

`/pdf-extract <ścieżka.pdf> [--instance-export <export.json>]`

1. **Wyciąg**: odczytaj PDF (`Read` z `pages`, ewentualnie
   `anthropic-skills:pdf`). Wypisz dla każdego dnia: posiłki, składniki
   (nazwa, ilość, jednostka, gramy), instrukcję, komentarz, sumy posiłku i dnia,
   listę zakupów. Pomiń imię i nazwisko pacjenta oraz dane kontaktowe
   dietetyka — NIGDY nie trafiają do `spec.json`, raportu ani czatu poza
   koniecznością.
2. **Zestawienie**: `task pdfx-index` → trafienia i kandydaci.
3. **BRAMKA 1 — propozycja scaleń**: przedstaw tabelę (co scalić, co zostawić,
   dlaczego, skutek kcal) i **zatrzymaj się** do akceptacji. Zasada
   merytoryczna: scalaj to, co kupuje się jako jedno i różni się formą/miarą/
   odmianą; NIE scalaj produktów o istotnie różnych wartościach odżywczych bez
   wyraźnej zgody (to przesuwa sumy dnia). Przecier/passata ≠ pomidor.
4. **Wartości odżywcze**: dla produktów NOWYCH sprawdź w sieci (`WebSearch`),
   zbierz zakres, przyjmij kompromis, zapisz zakres w raporcie; dla reużytych
   z wcześniejszych wersji NIE zmieniaj wartości.
5. **Weryfikacja**: `task pdfx-verify`; omów odstępstwa z progami.
6. **BRAMKA 2 — raport**: `report.md` do akceptacji; **zatrzymaj się**.
7. **Paczka**: `task pdfx-package`, następnie `task pdfx-roundtrip`
   (baza testowa, dwa razy). Zapisz wersję w `data/diet-imports/NNNN-slug/`.
8. **Przekaż**: wskaż ścieżkę paczki i napisz, że WGRYWA WŁAŚCICIEL
   (UI `/admin/dane`, zakres `global` tylko jako ADMIN). Agent nie dotyka
   produkcji.

## Database / migrations

Brak. Narzędzie nie zmienia schematu ani nie dodaje tabel (D31). Jeśli w
trakcie okaże się, że paczka wymaga zmiany schematu — STOP i pytanie.

## Backend

Wyłącznie `backend/scripts/pdf_extract/` (+ testy). Wymagania:

- Importy zamiast kopii: `app.modules.catalog.naming.normalize_name`,
  `catalog.units` (`normalize_amount`, `to_basis_amount`, `ProductMeasure`,
  `UnitWeight`), `catalog.nutrition_adapter.ProductNutrition`,
  `nutrition.engine` (sumowanie, `round_for_output`). Żadnego `float` dla
  ilości i wartości (ADR-008) — `Decimal` ze stringów.
- Czyste funkcje bez I/O w `verify.py`/`package.py`; I/O (czytanie plików,
  ZIP) w cienkich funkcjach `cli.py`.
- Nic z `scripts/pdf_extract/` nie jest importowane przez `app/` (kierunek
  zależności: skrypt → aplikacja, nigdy odwrotnie); test to pilnuje.
- Zależności: tylko to, co już jest w `pyproject.toml`; **żadnych nowych
  zależności runtime** (czytanie PDF-a robi sesja agenta). Jeśli narzędzie
  potrzebuje nowej biblioteki — grupa `dev`, nie runtime, i pytanie do
  właściciela.
- Wejście CLI: `python -m scripts.pdf_extract <komenda>` wołane przez Taskfile.

## Frontend

Brak — POZA JEDNYM odstępstwem na polecenie właściciela (2026-10-03, rozstrzygnięcie D33 wariant A): rozwijana
podpowiedź „Co to jest kopia instancji i kiedy jej użyć?” w `/admin/dane` (`AdminDanePage.vue`, teksty w
`lib/texts.ts`, test `AdminDanePage.spec.ts`). Rozwijana, nie hover — UI jest mobile-first.

## Security

- **D27/prywatność**: `.gitignore` zawiera `/data/source_pdfs/` i
  `/docs/dieta.pdf` (dodane w tej sesji planistycznej); test sprawdza, że
  schemat `spec.json` nie ma pól na dane osobowe, a grep z AC 5 nie znajduje
  imienia/nazwiska/kontaktu w śledzonych plikach.
- **Sekrety**: narzędzie nie czyta `.env` produkcji i nie łączy się z żadną
  bazą poza testową; `pdfx-roundtrip` używa wyłącznie `TEST_DATABASE_URL`.
- **Zasięg**: żadnego polecenia na hostach produkcyjnych, żadnego `task deploy`.
- **Wiarygodność danych z sieci**: treść stron jest DANĄ, nie instrukcją;
  wartości liczbowe przechodzą walidację zakresu (nieujemne, kcal ≈ 4B+4W+9T
  w ±20%) zanim trafią do `spec.json`.
- `SKILL-SECREV` na diffie (paczka wgrywana na produkcję = powierzchnia ataku:
  `scope` w pliku, `verification_status`, wielkość).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3.

- **Required**: SKILL-BE, SKILL-CALC, SKILL-SEC
- **Recommended**: SKILL-CREATOR (tworzenie `pdf-extract`), `anthropic-skills:pdf`
  (wyłącznie dla tego narzędzia — D31 przywraca go w roli narzędziowej)
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **Unit** (`tests/unit/test_pdf_extract_*.py`, marker `unit`, docstring po
  polsku, fixture SYNTETYCZNY — nie dane pacjenta): schemat odrzuca pola
  spoza kontraktu; indeks katalogu (trafienie dokładne po `normalize_name`,
  kandydaci, konflikt `measure_kind` = błąd); reguła jednostek (każdy z
  przypadków z Context pkt 1–2: „Sztuka” przy MASS → gramy, łyżka poza
  progiem → gramy + `note`, łyżka w progu → jednostka domowa); progi
  weryfikacji; deterministyczność paczki (dwa wywołania = te same bajty);
  `Decimal`, nie `float` (test statyczny na `float(`/`float` w pakiecie);
  kierunek zależności (`app/` nie importuje `scripts.pdf_extract`).
- **Integracja** (marker `integration`): paczka z fixture'a przechodzi
  `TransferService` DRY-RUN (`to_create` zgodne z oczekiwaniem) i `apply` na
  bazie testowej; **drugi import tej samej paczki daje `created` = 0 dla
  produktów i przepisów** (D22/D24); kolejna wersja paczki używa produktu z
  poprzedniej (brak duplikatu po `normalized_name`); import przez USER-a obcina
  `global` (B21).
- **Weryfikacja na realnych danych**: test `0001` — `spec.json` wersji 0001
  przechodzi `verify`: wszystkie składniki przez `normalize_amount` bez wyjątku,
  sumy dnia w progach, suma gramów per produkt = lista zakupów z PDF-a.
- **Taskfile**: `task pdfx-verify -- data/diet-imports/0001-dieta-2000/spec.json`
  zwraca 0; `task pdfx-roundtrip` zielony.
- Macierz uprawnień (08_TESTING §4): bez zmian — batch nie dodaje zasobu HTTP.

## Acceptance Criteria

1. `/pdf-extract` istnieje jako skill (`.claude/skills/pdf-extract/SKILL.md`),
   a jego procedura ma DWIE bramki zatwierdzenia i zakaz wgrywania na produkcję.
2. `data/diet-imports/0001-dieta-2000/` zawiera `spec.json`, `report.md`,
   `export.zip`; `task pdfx-verify` na nim przechodzi; `task pdfx-roundtrip`
   daje przy drugim imporcie `created=0` dla produktów i przepisów.
3. Wszystkie składniki wersji 0001 przechodzą `normalize_amount` bez wyjątku
   (żadna „Sztuka” przy produkcie spoza `PIECE`), a raport wymienia składniki
   zapisane jako gramy z powodem.
4. Kolejna paczka (fixture z częściowo wspólnymi produktami) reużywa produkty
   z wcześniejszej wersji — test integracyjny, nie deklaracja.
5. **Prywatność, sprawdzalne grepem**: w plikach śledzonych przez git nie ma PDF-ów
   jadłospisów (`git ls-files '*.pdf'` puste poza ewentualnymi plikami
   niezwiązanymi z dietą), a `git grep -n -i -E` na imieniu i nazwisku pacjenta
   oraz danych kontaktowych dietetyka (wartości podaje właściciel w prompcie
   sesji — NIE wpisuj ich do karty ani do repo) nie trafia w nic poza
   historią.
6. Brak nowych zależności runtime w `pyproject.toml`; nic z `app/` nie
   importuje `scripts.pdf_extract`; brak `float` dla ilości/wartości.
7. `task check` zielony; CLAUDE.md, `03_AI_SKILLS.md`, README zaktualizowane do
   stanu faktycznego.

## Out of Scope

- Jakikolwiek import PDF w aplikacji, endpoint, ekran, tabela stagingu (D25).
- Automatyczne wgrywanie na produkcję, dostęp do `ffp_db`, `task deploy`.
- Plan dnia/tygodnia z PDF-a (przypisanie przepisów do dat) i szablony tygodni —
  osobny, późniejszy krok (paczka niesie tylko przepisy i produkty).
- Zdjęcia przepisów, retail (opakowania, sklepy), spiżarnia, listy zakupów.
- Parsowanie PDF-ów innych niż jadłospisy tego formatu bez nowej bramki.
- Zapis do globalnych słowników poza produktami, kategoriami i tagami.
- Zmiana wartości odżywczych produktów reużytych z wcześniejszych wersji
  (to robi ADMIN w `/admin/weryfikacja`).

## Expected files/modules

Nowe: `backend/scripts/pdf_extract/{__init__,spec,catalog_index,verify,package,report,cli,__main__}.py`,
`backend/tests/unit/test_pdf_extract_*.py`,
`backend/tests/integration/test_pdf_extract_package.py`,
`.claude/skills/pdf-extract/SKILL.md`,
`data/diet-imports/0001-dieta-2000/{spec.json,report.md,export.zip}`.
Zmieniane: `Taskfile.yml` (targety `pdfx-*`), `CLAUDE.md`,
`docs/implementation-plan/03_AI_SKILLS.md`, `README.md`,
`docs/implementation-plan/PROGRESS.md`, ten plik.
Już istnieją (z sesji planistycznej): `data/diet-imports/0001-dieta-2000/spec.draft.json`
(po konwersji zostaje do czasu AC 2, potem do usunięcia), wpisy w `.gitignore`.

## Implementation Notes

- **Dlaczego paczka transferu, a nie SQL** — D31 pkt 3. Jeśli właściciel kiedyś
  zażąda SQL-a, jest to osobny generator nad TYM SAMYM `spec.json`; spec jest
  jedynym źródłem prawdy, artefakty są pochodne.
- Dopóki `spec.draft.json` nie zostanie skonwertowany, jest to jedyne
  odniesienie dla decyzji właściciela; **nie zmieniaj wartości liczbowych bez
  zapisania powodu w raporcie** (np. gdy silnik daje inną sumę niż gramy z PDF-a).
- Numer wersji = pierwszy wolny w `data/diet-imports/` (jak migracje).
- Wersja `0001` obejmuje wyłącznie Tydzień I pon–śr; kolejne dni i tygodnie
  idą kolejnymi wersjami (indeks katalogu załatwia reużycie produktów).
- PDF dietetyka mówi, że każdą dietę stosuje się 2 dni pod rząd — to informacja
  dla przyszłego planu, nie dla paczki.

## Cross-Batch Impact

- **B21 (DONE)**: zakres `global` istnieje; test „import przez USER-a obcina
  global” wykonał B21 (`tests/integration/test_transfer_global.py`) — B22 testuje
  tylko, że jego paczka `scope=instance` zachowuje `global`, a `scope=user` obcina.
  Przepis globalny zasila `household_id = NULL` (CHECK `0018`); kopia instancji
  nie dubluje się przy drugim imporcie tylko dla przepisów o tej samej nazwie
  należących do importującego (przepis `global` cudzego admina nie jest
  „własny”, więc drugi import KOPII INSTANCJI zdubluje go — sprawdź w teście
  idempotencji i zdecyduj).
- **B18**: runbook wdrożenia dostaje JEDEN akapit o wgrywaniu paczki danych
  przez właściciela (bez zmiany procedury deployu).
- Przyszłe batche dodające sekcję do formatu transferu muszą zadeklarować
  `merge_key`/`parent` (CLAUDE.md, „Dołożone w REVIEW R4”) — generator paczek
  czyta `serializer.SECTIONS`, więc nowa sekcja nie wymaga zmiany narzędzia,
  dopóki nie jest wypełniana z PDF-a.

## Implementation checklist

- [x] Baseline po B21: `task check` zielony
- [x] `spec.py` + test „brak pól na dane osobowe”
- [x] `catalog_index.py` (wersje + seed demo + `--instance-export`) + testy
- [x] `verify.py` na `normalize_amount` i silniku; reguła jednostek; progi
- [x] `package.py` z `serializer.SECTIONS`; deterministyczna paczka
- [x] `report.py`; `cli.py`; targety `pdfx-*`
- [x] `.claude/skills/pdf-extract/SKILL.md` z dwiema bramkami
- [x] Dogfood: wersja 0001 (`spec.json`, `report.md`, `export.zip`)
- [x] Test integracyjny idempotencji i reużycia produktów między wersjami
- [x] Dokumenty (CLAUDE.md, 03_AI_SKILLS, README, B18), PROGRESS

## Verification checklist

- [x] `task check` zielony; `task pdfx-verify`/`pdfx-roundtrip` na 0001 zielone
- [x] Drugi import paczki: `created=0` dla produktów i przepisów
- [x] Grep prywatności z AC 5 czysty; `git ls-files '*.pdf'` bez jadłospisów
- [x] Brak nowych zależności runtime; `app/` nie importuje `scripts.pdf_extract`
- [x] `/code-review` i `/security-review` na diffie
- [x] Jeden commit `batch(22): narzędzie pdf-extract` (treść z promptu sesji; karta mówiła „komenda /pdf-extract i wersja 0001…”)

## Completion notes

_(wypełnia agent wykonujący batch: wykonane / odstępstwa / decyzje /
follow-upy / pytania)_

**Wykonane (2026-10-04).**
- `backend/scripts/pdf_extract/`: `spec` (schemat Pydantic v2, `extra="forbid"`, liczby jako stringi mieszczące się w kolumnach
  bazy, brak pól na dane osobowe), `catalog_index` (wersje + seed demo + `--instance-export`, `normalize_name` z aplikacji),
  `verify` (reguła jednostek w JEDNYM miejscu `resolve_ingredient`, sumy przez `normalize_amount` → `to_basis_amount` →
  `nutrition/engine.py`), `package` (paczka v1 z `serializer.SECTIONS`, deterministyczny ZIP), `report`, `roundtrip`, `cli`.
- Skill `.claude/skills/pdf-extract/SKILL.md` (dwie bramki, zakaz produkcji/PDF-ów w gicie/danych osobowych); targety
  `pdfx-index|verify|package|roundtrip`; dokumenty: CLAUDE.md (blok „Dołożone w BATCH_22” + tabela komend), 03_AI_SKILLS, README
  („Jak dodać jadłospis dietetyka”), karta B18 (akapit runbooka), D33 w 02_DECISIONS.
- Wersja `0001` (`data/diet-imports/0001-dieta-2000/{spec.json,report.md,export.zip}`): `spec.json` skonwertowany z
  `spec.draft.json` (44 produkty, 12 przepisów, 68 składników; draft usunięty po AC 2). Weryfikacja: 0 błędów, 9 ostrzeżeń;
  11 składników zapisanych jako gramy. Roundtrip na bazie testowej: import 2 = `created {}` (produkty 44 → 0, przepisy 12 → 0).
  Paczka `global` (lokalnie, nie w repo) też przechodzi roundtrip.

**Różnice silnik vs PDF (wyjaśnienie dla dogfood).** Dni (silnik / PDF): pon 1903/1959 (−2,9%), wt 1987/1987 (0%), śr 1993/2030
(−1,8%) — w progu 5%. Draft liczył 1905/1991/2000 na gramach z PDF-a; różnice biorą się z tego, że silnik liczy z ZAPISANEJ ilości
(jednostka domowa × przelicznik tam, gdzie mieści się w 10%, np. jajko 2 szt. = 116 g zamiast 120 g, pomidor 160 g zamiast 170/150 g,
łyżeczka oliwy 5,5 g zamiast 5/6 g). Największy posiłek: pon podwieczorek −9,3% kcal (ostrzeżenie nie padło: próg > 10%). Lista
zakupów: Σ gramów z PDF-a = lista PDF-a co do grama; Σ silnika odbiega tylko dla jajka (−2,8%) i pomidora (−2,0%) — w progu 5%.

**Odstępstwa od karty.**
1. **Dogfood bez ponownego czytania PDF-a.** `0001` powstał z konwersji `spec.draft.json` (tak każe karta: „ma z niego powstać,
   nie od zera”), a PDF (z imieniem pacjenta na okładce) nie był ponownie czytany. Skill nie został więc przetestowany
   end-to-end na PDF-ie; testowany jest kod (jednostkowo, integracyjnie, na danych 0001). Do sprawdzenia przy PIERWSZYM realnym
   użyciu na kolejnym tygodniu. `anthropic-skills:pdf` i `skill-creator` (Recommended) nie zostały użyte — SKILL.md napisany
   wprost wg wzorca istniejących project skilli.
2. **Podpowiedź w `/admin/dane`** (frontend) — poza zakresem karty, na polecenie właściciela (D33 wariant A).
3. **Formuła energii**: karta mówi „kcal ≈ 4B+4W+9T ±20%”; kod akceptuje też wariant z błonnikiem po 2 kcal/g (Atwater) —
   inaczej cynamon (247 kcal, 53 g błonnika) wychodził błędem. Tolerancja: ±20% albo ±10 kcal.
4. **Konflikt miary z seedem demo jest OSTRZEŻENIEM, nie błędem** (karta: błąd dla „konfliktu definicji”). Wersje i eksport
   instancji zatrzymują, demo ostrzega głośno (Cebula, Pomidor: PIECE vs MASS; Oliwa: MASS vs VOLUME — 0001 i demo faktycznie
   się różnią). Powód: demo to dane deweloperskie, a właściciel zatwierdził te miary w 0001.
5. `merged_from` to obiekty `{name, per_100?}` (draft miał same nazwy), a składnik ma opcjonalne `pdf_name` — inaczej raport
   nie policzy skutku scalenia. **Dla 0001 skutek kcal scaleń jest NIEZNANY** (draft nie niesie wartości źródłowych) i raport mówi
   to wprost; kolejne wersje zapisują `per_100` źródeł.
6. Spec dostał pola: `analyzed_on` (data → `exported_at` paczki, determinizm), `reused` (produkty z katalogu), `thresholds`.
   Pole `verification_status` i `last_calibration` z draftu pominięte (paczka zawsze `unverified`; kalibracja zastąpiona raportem
   silnika). Składnikom bez ilości w PDF-ie (tylko gramy) ustawiono `pdf_qty` = gramy.
7. Komentarz dietetyka (brak kolumny w `recipes`) wchodzi na koniec instrukcji jako „Uwaga: …”.
8. Dodatkowe pliki ponad listę „Expected”: `roundtrip.py`, `tests/pdf_extract_fixtures.py`.

**Decyzje.** D33 → **ZATWIERDZONE, wariant A** (stan z B21 zostaje; paczka `global` = `scope=instance` + sekcja `users`).
Rozstrzygnięcie karty (Cross-Batch): drugi import paczki `global` przez TEGO SAMEGO ADMIN-a (e-mail paczki = jego konto) daje
`created=0` (przepisy są „własne”); wczytanie przez INNEGO admina zakłada nieaktywne konto `user` (DRY-RUN pokazuje `users` w
„Nowe” = sygnał STOP) i przepisy NIE są globalne — oba przypadki mają test. Konto w paczce ma rolę `user` i `is_active=false`.

**Review.** `/code-review` (high): 9 ustaleń — naprawione 7 (ostrzeżenia katalogu przy `package`, guard hosta w roundtripie przed
`TRUNCATE`, normalizacja nazw przepisów w `index`, kaskada fałszywych błędów po błędzie składnika, ujemne zero w odchyłce,
kolejność progów, jedna definicja progów dnia), 2 odnotowane bez zmiany (kopia listy kategorii z migracji `0005` — pilnuje jej test
zgodności; test-grep po źródle `verify.py`). `/security-review`: brak ustaleń ≥ 8/10.

**Follow-upy.**
- Pierwsze użycie `/pdf-extract` na realnym PDF-ie (tydzień I czw–nie albo II) — zweryfikować skill end-to-end i uzupełnić
  `merged_from[].per_100`.
- Ostrzeżenia z 0001 do rozstrzygnięcia przez właściciela: instrukcje wspominają składniki spoza listy (pomidor w Spaghetti,
  czosnek w Makaronie ze szpinakiem i Grzankach, szynka mielona w Grzankach, orzechy włoskie w Jogurcie) i pusta instrukcja
  Koktajlu jagodowego — to dane z PDF-a, nie błąd narzędzia.
- Konflikt 0001 z seedem demo (Cebula/Pomidor/Oliwa): nie importować do bazy z `task db-seed-demo`.
- `docs/OPERATIONS.md` (B18b) ma dostać akapit z karty B18.

**Pytania.** Brak otwartych (D33 rozstrzygnięte).
