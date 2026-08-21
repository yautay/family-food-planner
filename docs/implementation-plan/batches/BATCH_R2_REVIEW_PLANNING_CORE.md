# BATCH_R2 — REVIEW_PLANNING_CORE

Klasa: REV · Zależności: B05–B07 (wszystkie `[x]` w PROGRESS.md; R1 zamknięty) · Szacunek rozmiaru: S

## Goal

Audyt rdzenia planowania: silnik nutrition, przepisy, cele, plan dnia,
tydzień/szablony/cykle. Review NIE dodaje feature'ów — sprawdza czystość
i poprawność silnika (serce systemu, ADR-008), niezmienniki domenowe,
wydajność widoku tygodnia i to, czy agregaty planu wystarczą silnikowi
zakupowemu B10. Wolno mu skorygować plan batchy SHOP z udokumentowanym
powodem.

## Context

Po B05–B07 istnieją: moduł `recipes` (przepisy, składniki znormalizowane,
tagi, oceny), `nutrition` (czysty silnik + cele), `planning` (plan dnia,
posiłki, pozycje z mnożnikami i rozkładem rodzinnym, szablony JSONB,
cykle, kopiowanie). Frontend: plan dnia, tydzień, przepisy. To pierwszy
moment, w którym wyliczenia kcal/makro/ŁG działają end-to-end.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` (sekcja Review)
  + `00_MASTER_PLAN.md` §9, §7–8.
- `docs/implementation-plan/PROGRESS.md` — werdykt R1 (niedomknięte
  follow-upy!) + dziennik i Completion notes B05–B07.
- `docs/architecture/02_DOMAIN_MODEL.md` §5–7 i **§13 (niezmienniki —
  kręgosłup tego audytu)**; 03_DATABASE §5–6 (w tym JSONB szablonów
  i blokada usuwania); 04_API §1 (stringi dziesiętne!), §2 (plan/templates);
  05_FRONTEND §1, §4; 06_UIUX §2 (zasada „bez zaklikania") i §4.1/4.4;
  08_TESTING §2.1–2.3; 07_SECURITY §4.
- `docs/implementation-plan/03_AI_SKILLS.md` — `/code-review`,
  `/security-review` w review.
- ADR-004 (model wartości), ADR-005 (jednostki), ADR-008 (czyste silniki,
  Decimal), ADR-012 (usuwanie).

### Ustalenia WEJŚCIOWE zaparkowane dla R2 (decyzja właściciela, 2026-08-21)

Trzy sprawy znalezione przy domykaniu B07 — **żadna nie jest błędem w kodzie
domenowym**, wszystkie mają dowód, więc R2 nie musi ich odkrywać od nowa.
Właściciel świadomie odłożył je tutaj, zamiast naprawiać w B07.

1. **Martwe przyciski nawigacyjne (UX + dostępność, B04/B05).**
   `Button as="router-link"` renderuje SAM TEKST — ani `<button>`, ani `<a>`.
   Przycisk jest nieklikalny i niewidoczny dla czytnika ekranu jako element
   interaktywny. Dowód: snapshot ARIA Playwrighta ze strony produktów pokazuje
   `- text: Dodaj produkt` tam, gdzie menu ma `- link "Produkty": /url: /produkty`.
   **Skala: 9 wystąpień w 6 plikach** — `pages/produkty/{ProduktyPage,
   ProduktFormPage}.vue`, `pages/przepisy/{PrzepisyPage,PrzepisSzczegolPage,
   PrzepisEdytorPage}.vue`, `pages/admin/AdminWeryfikacjaPage.vue`.
   Przyczyna: reka-ui `Primitive` dostaje `as` jako STRING `'router-link'`
   i traktuje go jak nazwę tagu, zamiast rozwiązać komponent.
   Rekomendacja: `:as="RouterLink"` (referencja komponentu) albo kanoniczne
   `as-child` z zagnieżdżonym `<RouterLink>`; do tego test vitest asercjujący,
   że renderuje się `<a>` z `href` — inaczej regres wróci niezauważony.
   Blokuje `produkty.spec.ts` i `recipe-inline-create.spec.ts`.
   **B07 jest wolny od tego błędu** — `PlanTygodniaPage` używa `<RouterLink>`
   wprost, więc wzorzec do naśladowania jest już w repo.

2. **Brak izolacji danych testowych E2E (dług U15).** Specy używają STAŁYCH dat
   (`2031-03-05` w smoke, `2032-03-01` w week-template-cycle) i nie sprzątają po
   sobie, więc kolejny przebieg pada na danych poprzedniego. Dwa zaobserwowane
   objawy: (a) `plan-empty` nie jest już pusty, (b) szukajka **trigramowa**
   przepisów znajduje „Zupa E2E <stamp>" z wcześniejszych przebiegów i ukrywa
   opcję „+ Dodaj", więc inline create staje się nieosiągalny. To NIE jest
   problem asercji — łatanie ich po jednej leczy objawy. Potrzebny teardown per
   spec albo reset bazy przed przebiegiem E2E (08_TESTING §5).

3. **Wspólne konto E2E + równoległość.** `households.spec.ts` przepisuje admina
   do nowej rodziny, gdy inne specy tworzą jako TEN SAM admin encje ze scope.
   Te dostają `household_id` tej rodziny — `ScopedQuery.ownership_for_create`
   zapisuje `household_id` także dla scope PRIVATE (świadomie, ADR-006) — więc
   sprzątające `DELETE /admin/households/{id}` kończy się 409 i spec pada.
   Kod zachowuje się POPRAWNIE (jest druga linia obrony na `IntegrityError`,
   `households/service.py::delete_household`), więc to problem projektu testów.
   **Obserwacja przy okazji, warta oceny w tym audycie**: w tej ścieżce
   `details.used_in` jest PUSTE, więc użytkownik widzi „rodzina nie jest pusta"
   bez informacji, co ją blokuje. B07 powiększył zbiór blokad o trzy tabele
   (`day_templates`, `week_templates`, `week_cycles` — wszystkie z
   `household_id` ON DELETE RESTRICT). Rozważyć policzenie referencji także dla
   encji ze scope, albo świadome przyjęcie tego ograniczenia z uzasadnieniem.

Stan E2E na wejściu do R2: **5 z 10 zielonych** (`setup` + 4 specy). Naprawione
w commicie `test(e2e)`: kolizja z limitem `/auth/login` (5/min/IP vs osiem
logowań na sześciu workerach — teraz jedno logowanie i `storageState`), zły
przepływ inline create przepisu w smoke i week-template-cycle
(`recipe-picker-create` tylko OTWIERA drawer, brakowało `recipe-create-submit`)
oraz asercja słupka `BarChart` (`<rect height=0>` ma zerowy bounding box, więc
`toBeVisible()` zawodzi na dniu bez posiłków — liczy się `data-height`).

**D15 i D16 pozostają OPEN w `02_DECISIONS`** — kod już podjął decyzję za
właściciela (B05 wdrożył D15, B06 i B07 zaasercjonowały stan faktyczny D16
testami). R2 powinien to rozstrzygnąć albo jawnie eskalować w werdykcie.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-REVIEW, SKILL-BE, SKILL-CALC
- **Recommended**: SKILL-FE, SKILL-CREATOR

Review batch sam jest procesem przeglądowym — SKILL-REVIEW/SKILL-SECREV uruchamiane są na pełnym zakresie zmian od poprzedniego review, nie na diffie własnego commita.

## Stages

1. **Rekonstrukcja stanu**: PROGRESS (w tym warunki z R1) + Completion
   notes B05–B07; `task check` zielony na wejściu.
2. **Audyt silnika nutrition**: czystość, Decimal, zaokrąglenia,
   property-based — sekcja Audit checklist.
3. **Audyt domeny i danych**: niezmienniki §13, JSONB szablonów, model
   porcji; pomiar wydajności widoku tygodnia na seedzie demo.
4. **Security + testy**: `/security-review` na zmianach od R1; macierz
   uprawnień nowych zasobów; audyt zależności (pip-audit/npm audit).
5. **Analiza planu SHOP**: karty B08–B11 vs stan repo; czy agregaty planu
   wystarczą silnikowi B10; korekty planu z powodem.
6. **Domknięcie**: drobne naprawy w commicie review; werdykt do
   PROGRESS.md; aktualizacja kart/dokumentów; commit `batch(R2): review ...`.

## Audit checklist

### Silnik nutrition — czystość i poprawność (ADR-008)

- [x] `modules/nutrition` engine: ZERO I/O, ZERO importów ORM/sesji,
      ZERO `datetime.now()`/losowości (grep po imports + `now(`)
- [x] `Decimal` end-to-end: wejście adaptera → silnik → serializacja;
      żadnego `float()` w torze obliczeń (grep); JSON zwraca stringi
      dziesiętne (04_API §1)
- [x] Zaokrąglenia WYŁĄCZNIE na krawędzi (prezentacja/serializacja:
      kcal do 1, makra 0,1 g, ŁG 0,1) — kroki pośrednie bez kwantyzacji
- [x] Wzory 02_DOMAIN §6: /100 g → składnik → przepis → porcja → mnożnik →
      posiłek → dzień; ŁG = IG × (węgle − błonnik, min 0) / 100
- [x] Flagi completeness: brak IG/makro ⇒ suma z dostępnych + `complete:
      false` + `missing` z nazwą produktu i braku
- [x] Property-based testy (hypothesis) ISTNIEJĄ i coś sprawdzają
      (przeczytać strategie i asserty): suma pozycji = wartość dnia,
      skalowanie liniowe mnożnika, nieujemność

### Niezmienniki 02_DOMAIN §13 — każdy przypięty testem

- [x] §13.1 zapis ilości bez przeliczenia na g/ml niemożliwy (test odmowy)
- [x] §13.2 zero cache'owania wartości w encjach (grep kolumn kcal/macro
      poza canonical_products; wyjątek: staging importu)
- [x] §13.3 zmiana mnożnika zmienia spójnie kcal/makra/ŁG (test przez API)
- [x] §13.4 przepis użyty w planie/szablonie nie do usunięcia (409 + used_in)

### JSONB szablonów i blokada usuwania

- [x] Usunięcie przepisu zliczanego w `day_templates`/`week_templates`
      payload → 409; zapytanie po JSONB path używa indeksu GIN
      (`EXPLAIN` — potwierdzić, nie zakładać)
- [x] Instancjacja szablonu = kopia bez live-sync; szablon z zarchiwizowanym
      przepisem ma zdefiniowane, przetestowane zachowanie

### Wydajność widoku tygodnia

- [x] `GET /plan/days?from=&to=` (7 dni × posiłki × pozycje × nutrition):
      zmierzyć liczbę zapytań SQL (echo/licznik) — brak N+1
      (selectinload/joinedload tam, gdzie trzeba)
- [x] Budżet: **<500 ms** na seedzie demo (`task db-seed-demo`) — pomiar
      zapisany w raporcie (narzędzie + wynik); przekroczenie = ustalenie

### Model porcji rodzinnych i UX (06_UIUX §2)

- [x] Prosty przypadek NIE skomplikowany: „7 porcji" = jedno pole servings,
      bez wymuszania rozkładu; rozkład rodzinny opcjonalny (3×1.0+2×0.8+2×1.3)
- [x] Suma rozkładu = servings pozycji pilnowana serwisem (test)
- [x] UX check widoków planu: ile kliknięć od intencji do efektu (dodanie
      posiłku, kopiuj dzień, zastosuj szablon); „dopasuj porcję do celu"
      jest jawną akcją, nie automatem
- [x] Frontend: brak kopii planu w Pinia; mutacje inwalidują query
      (przejrzeć `useXxxMutation`)

### Ustalenia zaparkowane z B07 (patrz Context)

- [x] Martwe `Button as="router-link"` — naprawione (9 wystąpień) + test
      asercjujący `<a>` z `href`; potwierdzić, że `produkty.spec.ts`
      i `recipe-inline-create.spec.ts` przechodzą
- [x] Izolacja danych E2E — teardown albo reset bazy; potwierdzić, że DWA
      kolejne przebiegi suity dają ten sam wynik (to jest właściwy test tej
      naprawy, nie jednorazowe zielone)
- [x] `households.spec.ts` nie koliduje z równoległymi specami na wspólnym
      koncie; ocenić puste `used_in` przy 409 usuwania rodziny
- [x] Werdykt dla U15: E2E zielone i powtarzalne, albo dług przechodzi do R3
      z jawnym uzasadnieniem

### Przygotowanie pod zakupy (B10)

- [x] Czy z planu da się wyciągnąć: zakres dat → pozycje → ilości
      znormalizowane per produkt (z mnożnikami) — bez dodatkowej logiki
      w B10? Jeśli brakuje agregatu/serwisu — ustalenie do karty B10
      (NIE implementować tu)
- [x] Produkty luzem w planie (PlanMealItem z product_id) niosą ilość
      w g/ml — agregowalne tak samo jak składniki przepisów

## Security

- `/security-review` na zmianach od R1 (diff zakresu B05–B07) — obowiązkowy.
- Macierz uprawnień 08_TESTING §4 dla nowych zasobów: recipes, ratings,
  goals, plan, templates, cycles — testy anty-IDOR istnieją i przechodzą.
- `pip-audit` + `npm audit`; podbicia patch-level w commicie review.

## Tests

- `task check` zielony przed i po naprawach.
- Obszary krytyczne 08_TESTING §2.1–2.3 pokryte realnymi testami
  (nutrition, servings, konwersje) — przejrzeć asserty, nie nazwy.
- E2E: smoke + flow „przepis z inline create → wartości per porcja"
  i „tydzień: kopiuj dzień, szablon, cykl" (08_TESTING §3) istnieją
  i przechodzą.
- Luki: małe dopisać w review; większe → wpis do karty właściwego batcha.

## Acceptance Criteria

1. Audit checklist w całości odhaczona albo przekuta w ustalenia
   (plik/linia + rekomendacja + miejsce docelowe).
2. Pomiar wydajności tygodnia wykonany i zapisany (zapytania + czas);
   werdykt wobec budżetu <500 ms.
3. Property-based testy silnika zweryfikowane merytorycznie.
4. `/security-review` + audyt zależności wykonane; wynik opisany.
5. `task check` zielony po zmianach review.
6. Werdykt w PROGRESS.md: PASS / PASS z warunkami / BLOKADA dla B08–B09.
7. Karty B08–B11 zaktualizowane (w tym gotowość agregatów dla B10).
8. Commit `batch(R2): review ...` wykonany, `git status` czysty.

## Out of Scope

- Silnik zakupowy, spiżarnia, retail → B08–B10 (tu tylko gotowość wejścia).
- Optymalizacje wydajności ponad naprawę N+1 (cache'owanie wartości
  ZAKAZANE niezmiennikiem §13.2 — nie „naprawiać" wydajności cachem!).
- Nowe feature'y i refaktoryzacje ponad drobne naprawy.

## Expected files/modules

- `docs/implementation-plan/PROGRESS.md` — werdykt + wpis dziennika.
- Ewentualnie: drobne naprawy `backend/**`/`frontend/**`; aktualizacje
  kart `BATCH_08…11`, `docs/architecture/**`, `00_MASTER_PLAN.md`,
  `.claude/skills/ffp-framework/SKILL.md`, `CLAUDE.md`.

## Implementation Notes

- Pomiar N+1: włączyć echo SQLAlchemy albo licznik zapytań w fixture;
  liczbę zapytań i czas wpisać do raportu — „wydaje się szybkie" nie jest
  wynikiem.
- Silnik nutrition to serce systemu: znalezione tu błędy wyliczeń mają
  priorytet nad wszystkim innym; błąd wzoru = BLOKADA, nie follow-up.
- Sprawdzić progi statusów (D9: 90–110%, konfigurowalne) — zgodność
  implementacji B06 z decyzją.
- Follow-upy R1 niedomknięte: zweryfikować status każdego; przeterminowane
  eskalować w werdykcie.

## Cross-Batch Impact

- **B08–B09**: werdykt = bramka wejścia (mogą iść równolegle — sprawdzić
  brak kolizji plików w ich kartach przed dopuszczeniem).
- **B10**: ustalenia o agregatach planu wpisać do karty (sekcja Context).
- **B13**: statystyki liczą wg celu z dnia (historia celów) — potwierdzić,
  że model B06 to umożliwia; jeśli nie, zaktualizować kartę B13.
- **R3**: dziedziczy niedomknięte follow-upy (wpis w PROGRESS).

## Implementation checklist

- [x] PROGRESS (warunki R1!) + Completion notes B05–B07 przeczytane
- [x] `task check` zielony na wejściu
- [x] Audyt silnika: czystość, Decimal, zaokrąglenia, property-based
- [x] Niezmienniki §13.1–13.4 zweryfikowane testami
- [x] JSONB szablonów: blokada usuwania + GIN (EXPLAIN wykonany)
- [x] Pomiar wydajności tygodnia na seedzie demo (wynik zapisany)
- [x] UX check porcji rodzinnych i widoków planu (06_UIUX §2)
- [x] Gotowość agregatów pod B10 oceniona
- [x] `/security-review` + macierz uprawnień + audyt zależności
- [x] Trzy ustalenia zaparkowane z B07 (Context) rozstrzygnięte
- [x] D15/D16 rozstrzygnięte albo eskalowane w werdykcie
- [x] Karty B08–B11 przejrzane i zaktualizowane
- [x] Werdykt + wpis dziennika w PROGRESS.md

## Verification checklist

- [x] `task check` zielony po naprawach
- [x] Acceptance Criteria 1–8 odhaczone
- [x] Każde ustalenie: naprawione / follow-up (gdzie) / decyzja OPEN
- [x] Dokumentacja architektury zgodna ze stanem faktycznym
- [x] Commit `batch(R2): review ...`, `git status` czysty

## Completion notes

**Werdykt: PASS.** B08 i B09 mogą startować, także równolegle (kolizje plików
sprawdzone i skorygowane w obu kartach). Bez warunków blokujących. Pełny opis
audytu i wyniki uruchomień: PROGRESS.md, wpis „2026-08-21 — REVIEW R2".

### Wykonane

- **Stage 1** — `task check` zielony na wejściu POTWIERDZONY realnie (exit 0,
  ~40 min: 3 migrations-check / 242 unit / 147 int / 243 api / 198 vitest /
  mypy 117 plików / vue-tsc / ruff / eslint / format 127 / vite build).
- **Stage 2** — silnik nutrition czysty i poprawny, bez ustaleń. Property-based
  testy przeczytane merytorycznie (strategie + asserty), nie tylko po nazwach.
- **Stage 3** — niezmienniki §13.1–13.4 każdy z testem; `EXPLAIN` na containment
  JSONB potwierdza użycie indeksu GIN; pomiar wydajności tygodnia wykonany
  i zapisany (10 zapytań SQL na 112 pozycji, 100–177 ms przez HTTP).
- **Stage 4** — `/security-review` na całym zakresie od R1: ZERO ustaleń.
  `task audit` czysty, `task secrets-scan` doprowadzony do stanu używalnego
  i czysty. Macierz uprawnień sprawdzona per nowy zasób.
- **Stage 5** — karty B08–B11 przejrzane; B10 dostał sekcję o gotowości
  agregatów (5 ustaleń wiążących) i o brakach seedu demo.
- **Stage 6** — trzy zaparkowane ustalenia z B07 rozstrzygnięte, E2E 10/10
  w dwóch kolejnych przebiegach, werdykt i propagacja w PROGRESS.

### Odstępstwa od karty

1. **Pomiar wydajności NIE na seedzie demo.** Karta wymaga budżetu <500 ms „na
   seedzie demo", ale seed nie zawiera ani jednego dnia planu (ustalenie U18),
   więc pomiar na nim mierzyłby pusty tydzień. Zamiast tego test seeduje
   realistycznie gruby tydzień (7 dni × 4 posiłki × 4 pozycje = 112 pozycji,
   przepisy po 5 składników, rozkłady rodzinne) i mierzy oba poziomy: serwis
   i HTTP. Budżet spełniony z zapasem; brak seedu zgłoszony jako U18 do B10.
2. **Naprawa wykroczyła poza „typówki i martwy kod"** w trzech miejscach, bo
   karta wprost ich żąda albo bez nich nie da się spełnić Acceptance Criteria:
   9 przycisków nawigacyjnych + test (Audit checklist), helper sprzątający E2E
   + jednowątkowość suity (kryterium „dwa przebiegi"), `.gitleaks.toml`
   (warunek 4 werdyktu R1 — bez tego `task secrets-scan` zwracał exit 1 na
   czystym repo i nie dawał się użyć jako bramka).
3. **Dwie zmiany infrastrukturalne poza literalnym zakresem**, obie addytywne
   i uzasadnione: `{{.CLI_ARGS}}` w targetach pytest (bez tego nie da się
   zawęzić przebiegu ani odczytać pomiaru bez wołania gołego pytesta) oraz
   dołożenie pozycji z produktem do `week-template-cycle.spec.ts` (asercja
   słupka `BarChart` była niespełnialna na planie o zerowych kaloriach).
4. **`used_in` przy usuwaniu rodziny — ocenione, NIE naprawione.** Karta prosi
   o ocenę („rozważyć albo świadomie przyjąć z uzasadnieniem"). Właściwym
   rozwiązaniem jest rejestr finderów w `households/service.py` (wzorzec
   z katalogu i przepisów), a zakładanie go teraz, gdy B08–B11 dołożą cztery
   kolejne tabele ze scope, znaczyłoby robić to dwa razy. Przekazane jako U16
   do R3 razem z powiązanym U17 (brak `DELETE /plan/days/{date}`).

### Decyzje

- **D15 i D16 ESKALOWANE, nie rozstrzygnięte.** Review nie zastępuje właściciela
  (hierarchia 03_AI_SKILLS §1), a przy D16 konflikt jest między dokumentami
  NADRZĘDNYMI wobec review (08_TESTING §4 vs 04_API §3 + 07_SECURITY §4).
  Do 02_DECISIONS dopisany stan po R2 i rekomendacja: **D16 rozstrzygnąć przed
  B08**, bo koszt odwrócenia rośnie z każdą nową encją ze scope (dziś 5, po
  B08–B11 dziewięć).
- **Suita E2E jest jednowątkowa z rozmysłem** (`workers: 1`). Determinizm ma tu
  pierwszeństwo nad kilkudziesięcioma sekundami: specy dzielą jedną bazę, jedno
  konto i globalny katalog, a szukajki są trigramowe, więc równoległość
  produkowała czerwone przebiegi bez winy aplikacji. Reguła spisana
  w 08_TESTING §3.1 i w skillu `ffp-frontend`.
- **Purge danych E2E działa tylko przeciw localhostowi** (bramka `baseURL`
  z `/security-review`) — funkcja kasuje szeroko i na koncie ADMIN-a.

### Follow-upy

- **U16 → karta R3**: rejestr referencji dla `delete_household` (puste `used_in`).
- **U17 → karta R3**: brak `DELETE /plan/days/{date}` (04_API §2 mówi „CRUD");
  pusty wiersz dnia zostaje na zawsze i blokuje usunięcie rodziny.
- **U18 → karta B10 + 08_TESTING §5**: seed demo ma wyłącznie katalog; snapshoty
  silnika zakupowego na seedzie wymagają najpierw jego rozszerzenia.
- **Obserwacja → B17**: pierwsze żądanie `GET /plan/days` w świeżym procesie
  ~1,5 s (budowanie schematów Pydantica), kolejne 100–180 ms.
- Follow-upy R1 sprawdzone: U9/U10/U11 domknięte w B05, U12/U13/U14 nadal
  w karcie B17 (nie przeterminowane — B17 jeszcze nie startował), **U15
  ZAMKNIĘTY w tym batchu**.

### Pytania do właściciela

1. ~~**D16 — czy ADMIN widzi cudze encje ze scope na ścieżkach użytkownika?**~~
   **ODPOWIEDŹ WŁAŚCICIELA (2026-08-21): TAK.** Decyzja zamknięta w tej samej
   sesji: 02_DECISIONS → „Zatwierdzone", kod bez zmian, doprecyzowane granice
   wyjątku w 04_API §3 pkt 2/2a i 07_SECURITY §4. B08 nie ma już tej bramki.
2. **D15 — czy zmianę `measure_kind` zastrzec dla ADMIN-a?** Reszta
   rekomendacji jest już wdrożona i potwierdzona.
