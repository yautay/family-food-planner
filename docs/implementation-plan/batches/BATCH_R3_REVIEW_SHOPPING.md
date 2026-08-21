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

- [ ] `shopping/engine.py`: czysta funkcja — zero I/O/ORM/now()/random
      (grep importów); wejście = plan+konfig, wyjście = preview struct
- [ ] Ten sam input ⇒ identyczny output: snapshot testy istnieją;
      `shopping_generations.params` przechowuje pełne wejście generacji
      i pozwala odtworzyć preview (test regresyjny — wykonać)
- [ ] Stabilne sortowanie pozycji (brak zależności od kolejności dict/set)

### Resztki i opakowania (08_TESTING §2.6)

- [ ] `ceil(potrzeba/wielkość_opakowania)`; resztka = kupione − potrzeba;
      resztka wyeksponowana w preview i na liście („Zostanie: 150 g")
- [ ] Brak retail ⇒ pozycja w gramach (dozwolone) + podpowiedź w preview
- [ ] Wiele wariantów opakowań: wybór domyślny = najmniejsza resztka,
      remis → mniejsze opakowanie (nazwane przypadki testowe istnieją)
- [ ] Decimal w ilościach; agregacja wielu przepisów/dni → jeden produkt,
      jednostki mieszane (g+szt.+łyżka) poprawnie znormalizowane (§2.4)

### Spiżarnia w pipeline (§2.5)

- [ ] Odejmowanie WYŁĄCZNIE po jawnym pytaniu „Uwzględnić stan domowy?";
      preview pokazuje co odjęto (`from_pantry_amount`)
- [ ] Nigdy poniżej zera; pozycje retail vs kanoniczne rozróżnione
- [ ] Finalizacja listy NIE zmienia spiżarni automatycznie (02_DOMAIN §8)

### Tury (§2.7)

- [ ] Preset niedziela/środa seedowany jako konfiguracja (NIE hardcode);
      trwałe na cały zakres + świeże na okno / świeże na resztę
- [ ] `perishability` z kategorii + nadpisanie per produkt działa
- [ ] Edge: plan krótszy niż okno tury — zdefiniowane, przetestowane

### Tokeny publiczne — pełny audyt 07_SECURITY §5 (KRYTYCZNE)

- [ ] Token `token_urlsafe(32)`, unique index, lookup tylko po pełnym tokenie
- [ ] **Odpowiedź `/public/lists/{token}` bez PII**: tylko nazwa listy,
      pozycje (label, ilość, kategoria, checked), expires_at — ZERO nazwisk,
      emaili, id userów/household (przeczytać serializer, wykonać request!)
- [ ] Expiry (default 7 dni) + revoke → **410** z przyjaznym ekranem;
      nieistniejący token → 404/410 bez różnicowania informacji
- [ ] **Rate limit 60/min/IP na `/public/*`** — test lub ręczna próba
- [ ] **Maskowanie w logach**: ścieżka `/public/lists/***` — tokeny NIE
      występują w logach (grep po realnym logu z requestu!)
- [ ] Public PATCH checkboxa: wyłączony z CSRF, ale rate-limited;
      pozwala TYLKO na check/uncheck (nic więcej — sprawdzić schema)
- [ ] `/security-review` na całości zmian od R2 — OBOWIĄZKOWY, wynik w raporcie

### Mobile UX listy i print (06_UIUX §5–6)

- [ ] Checkbox ~48 px, cele dotykowe ≥44 px; sekcje sticky per kategoria
      w kolejności profilu sklepu; odhaczanie optimistic
- [ ] Wariant print: czarno-biały, ☐, kategorie jako nagłówki, bez
      nawigacji (sprawdzić realnie w przeglądarce)
- [ ] QR/link/share działają; strona `/l/:token` renderuje się bez sesji
      POZA AppShell

### Spójność stanu checkboxów

- [ ] `checked` + `checked_at` persystowane; równoległe odhaczanie
      (dwie karty/urządzenia) nie gubi stanu — zdefiniowana semantyka
      (last-write-wins per pozycja przygotowany pod ADR-009/B12)
- [ ] Odhaczenie z publicznego linku i z aplikacji widzą ten sam stan

### Ustalenia odziedziczone z R2 (2026-08-21)

- [ ] **U16 — puste `details.used_in` przy 409 usuwania rodziny.**
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
- [ ] **U17 — nie da się usunąć dnia planu.** `04_API §2` opisuje
      `/plan/days/{date}` jako CRUD, a router ma tylko GET i PUT. Wiersz
      `plan_days` powstaje implicite przy pierwszym posiłku, trzyma
      `household_id` z FK RESTRICT i nie znika po usunięciu wszystkich
      posiłków — UI pokazuje wtedy „brak planu", ale blokada rodziny zostaje
      (to najczęstsza przyczyna U16 z pustym `used_in`). Do rozstrzygnięcia
      razem z U16: albo `DELETE /plan/days/{date}` (usuwa dzień bez posiłków),
      albo automatyczne sprzątanie pustego dnia przy usunięciu ostatniego
      posiłku, albo świadoma decyzja „dni zostają" z policzeniem ich w `used_in`.
- [ ] **U15 zamknięty w R2** (E2E 10/10 w dwóch kolejnych przebiegach,
      `task secrets-scan` czysty) — sprawdzić, czy nadal jest, i czy nowe specy
      B08–B11 trzymają się konwencji: własny prefiks nazw + `beforeAll`
      /`afterAll` z `cleanupE2eData` + daty z okna 2030+ (`frontend/e2e/cleanup.ts`).
      Suita jest ŚWIADOMIE jednowątkowa (`workers: 1`) — spec zakładający
      równoległość to błąd review.

### Plan B12–B16 — przegląd

- [ ] B12 (offline): czy `label` na pozycjach wystarcza do renderu offline;
      czy PATCH checkboxa jest idempotentny (kolejka offline!); ustalenia
      do karty B12
- [ ] B15/B16 (importer) po R3 — potwierdzić kolejność wobec D2 (treść
      wchodzi importerem, nie odkładać za B17/18); jeśli baza świeci
      pustkami, rozważyć podniesienie priorytetu B15 (zmiana planu z powodem)
- [ ] B13–B14: zakresy aktualne wobec stanu repo

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

- [ ] PROGRESS (warunki R2!) + Completion notes B08–B11 przeczytane
- [ ] `task check` zielony na wejściu
- [ ] Determinizm silnika: snapshoty + odtworzenie z params
- [ ] Resztki/opakowania/agregacja: przypadki §2.4–2.6 zweryfikowane
- [ ] Spiżarnia: jawne pytanie, nigdy <0, brak auto-przyjęcia
- [ ] Tury z presetem + edge'y §2.7
- [ ] Tokeny publiczne: pełna checklista §5 realnymi requestami
- [ ] `/security-review` + macierz uprawnień + audyt zależności
- [ ] Mobile UX + print sprawdzone realnie
- [ ] Karty B12–B16 przejrzane; kolejność importera potwierdzona
- [ ] Werdykt + wpis dziennika w PROGRESS.md

## Verification checklist

- [ ] `task check` zielony po naprawach
- [ ] Acceptance Criteria 1–8 odhaczone
- [ ] Każde ustalenie: naprawione / follow-up (gdzie) / decyzja OPEN
- [ ] Dokumentacja architektury zgodna ze stanem faktycznym
- [ ] Commit `batch(R3): review ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
