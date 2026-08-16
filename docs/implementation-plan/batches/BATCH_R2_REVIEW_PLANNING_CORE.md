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

- [ ] `modules/nutrition` engine: ZERO I/O, ZERO importów ORM/sesji,
      ZERO `datetime.now()`/losowości (grep po imports + `now(`)
- [ ] `Decimal` end-to-end: wejście adaptera → silnik → serializacja;
      żadnego `float()` w torze obliczeń (grep); JSON zwraca stringi
      dziesiętne (04_API §1)
- [ ] Zaokrąglenia WYŁĄCZNIE na krawędzi (prezentacja/serializacja:
      kcal do 1, makra 0,1 g, ŁG 0,1) — kroki pośrednie bez kwantyzacji
- [ ] Wzory 02_DOMAIN §6: /100 g → składnik → przepis → porcja → mnożnik →
      posiłek → dzień; ŁG = IG × (węgle − błonnik, min 0) / 100
- [ ] Flagi completeness: brak IG/makro ⇒ suma z dostępnych + `complete:
      false` + `missing` z nazwą produktu i braku
- [ ] Property-based testy (hypothesis) ISTNIEJĄ i coś sprawdzają
      (przeczytać strategie i asserty): suma pozycji = wartość dnia,
      skalowanie liniowe mnożnika, nieujemność

### Niezmienniki 02_DOMAIN §13 — każdy przypięty testem

- [ ] §13.1 zapis ilości bez przeliczenia na g/ml niemożliwy (test odmowy)
- [ ] §13.2 zero cache'owania wartości w encjach (grep kolumn kcal/macro
      poza canonical_products; wyjątek: staging importu)
- [ ] §13.3 zmiana mnożnika zmienia spójnie kcal/makra/ŁG (test przez API)
- [ ] §13.4 przepis użyty w planie/szablonie nie do usunięcia (409 + used_in)

### JSONB szablonów i blokada usuwania

- [ ] Usunięcie przepisu zliczanego w `day_templates`/`week_templates`
      payload → 409; zapytanie po JSONB path używa indeksu GIN
      (`EXPLAIN` — potwierdzić, nie zakładać)
- [ ] Instancjacja szablonu = kopia bez live-sync; szablon z zarchiwizowanym
      przepisem ma zdefiniowane, przetestowane zachowanie

### Wydajność widoku tygodnia

- [ ] `GET /plan/days?from=&to=` (7 dni × posiłki × pozycje × nutrition):
      zmierzyć liczbę zapytań SQL (echo/licznik) — brak N+1
      (selectinload/joinedload tam, gdzie trzeba)
- [ ] Budżet: **<500 ms** na seedzie demo (`task db-seed-demo`) — pomiar
      zapisany w raporcie (narzędzie + wynik); przekroczenie = ustalenie

### Model porcji rodzinnych i UX (06_UIUX §2)

- [ ] Prosty przypadek NIE skomplikowany: „7 porcji" = jedno pole servings,
      bez wymuszania rozkładu; rozkład rodzinny opcjonalny (3×1.0+2×0.8+2×1.3)
- [ ] Suma rozkładu = servings pozycji pilnowana serwisem (test)
- [ ] UX check widoków planu: ile kliknięć od intencji do efektu (dodanie
      posiłku, kopiuj dzień, zastosuj szablon); „dopasuj porcję do celu"
      jest jawną akcją, nie automatem
- [ ] Frontend: brak kopii planu w Pinia; mutacje inwalidują query
      (przejrzeć `useXxxMutation`)

### Przygotowanie pod zakupy (B10)

- [ ] Czy z planu da się wyciągnąć: zakres dat → pozycje → ilości
      znormalizowane per produkt (z mnożnikami) — bez dodatkowej logiki
      w B10? Jeśli brakuje agregatu/serwisu — ustalenie do karty B10
      (NIE implementować tu)
- [ ] Produkty luzem w planie (PlanMealItem z product_id) niosą ilość
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

- [ ] PROGRESS (warunki R1!) + Completion notes B05–B07 przeczytane
- [ ] `task check` zielony na wejściu
- [ ] Audyt silnika: czystość, Decimal, zaokrąglenia, property-based
- [ ] Niezmienniki §13.1–13.4 zweryfikowane testami
- [ ] JSONB szablonów: blokada usuwania + GIN (EXPLAIN wykonany)
- [ ] Pomiar wydajności tygodnia na seedzie demo (wynik zapisany)
- [ ] UX check porcji rodzinnych i widoków planu (06_UIUX §2)
- [ ] Gotowość agregatów pod B10 oceniona
- [ ] `/security-review` + macierz uprawnień + audyt zależności
- [ ] Karty B08–B11 przejrzane i zaktualizowane
- [ ] Werdykt + wpis dziennika w PROGRESS.md

## Verification checklist

- [ ] `task check` zielony po naprawach
- [ ] Acceptance Criteria 1–8 odhaczone
- [ ] Każde ustalenie: naprawione / follow-up (gdzie) / decyzja OPEN
- [ ] Dokumentacja architektury zgodna ze stanem faktycznym
- [ ] Commit `batch(R2): review ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
