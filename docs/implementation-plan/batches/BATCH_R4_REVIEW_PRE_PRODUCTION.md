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
- ADR-001…014 — zgodność stanu faktycznego z każdym ACCEPTED.

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

- [ ] `/security-review` na CAŁYM kodzie (nie diffie) — wynik w raporcie;
      HIGH naprawione albo NO-GO
- [ ] Nagłówki (07 §3): nosniff, Referrer-Policy, X-Frame-Options DENY,
      CSP bez zewnętrznych źródeł — sprawdzić realnym responsem
- [ ] Uploady (07 §6): limity 10/25 MB, MIME sniffing po treści, losowe
      nazwy poza web-rootem, serwowanie z autoryzacją, re-enkodowanie
      Pillow (EXIF strip), pdfplumber w try/except z limitem czasu
- [ ] **Sekrety w repo — grep**: `git log -p`-poziom nie wymagany, ale
      `git ls-files` + grep po wzorcach (key, secret, password, token,
      BEGIN PRIVATE, sk-ant) po całym repo, także testach i docs
- [ ] `ANTHROPIC_API_KEY` wyłącznie server-side (grep frontendu);
      klucz nieobecny w logach i odpowiedziach API
- [ ] Tokeny publiczne: ponowna szybka weryfikacja §5 (PII, rate limit,
      maskowanie) — regresje od R3
- [ ] Sesje/CSRF/rate-limit: testy nadal realne; macierz uprawnień §4
      kompletna dla WSZYSTKICH zasobów (wyrywkowo uruchomić)
- [ ] `pip-audit` + `npm audit` — zero known HIGH+ przed produkcją

### Wydajność kluczowych widoków (seed demo)

- [ ] Pomiary z liczbą zapytań SQL i czasem: plan dnia, tydzień (<500 ms,
      budżet z R2), lista przepisów z filtrami, generacja zakupów, lista
      zakupowa, statystyki zakresu — tabela wyników w raporcie
- [ ] Brak N+1 w żadnym z powyższych; indeksy używane (EXPLAIN wyrywkowo)

### Backup logiczny i własność danych (moduł transfer)

- [ ] Eksport → czysta instancja → import: odtwarza WSZYSTKO? (produkty,
      przeliczniki, przepisy, plany, szablony, spiżarnia, listy, zdjęcia,
      cele, profile) — wykonać round-trip realnie i porównać
- [ ] Dry-run raport importu rzetelny; wersja schematu w eksporcie
- [ ] Braki w zakresie eksportu = ustalenie BLOKUJĄCE (backup „ludzki"
      z 09_DEPLOYMENT §3 na tym polega)

### Acceptance criteria batchy 01–16 — wyrywkowo

- [ ] Z KAŻDEGO batcha 01–16 wybrać min. 2 AC i zweryfikować ręcznie
      lub istniejącym testem; wynik per batch w raporcie
- [ ] Odstępstwa zgłoszone w Completion notes — czy obiecane follow-upy
      faktycznie wykonano (przekrojowa kontrola długu programu)

### Dług techniczny

- [ ] Grep TODO/FIXME/HACK/XXX po repo + workaroundy z dzienników →
      JEDNA lista z priorytetami (P1 przed prod / P2 po wdrożeniu / P3 nice)
- [ ] P1 → batch naprawczy albo sekcja „Ustalenia R4" w karcie B17;
      P2/P3 → PROGRESS jako rejestr długu

### Dokumentacja i decyzje

- [ ] `docs/architecture/01…09` vs kod — każdy dokument potwierdzony
      albo zaktualizowany do stanu faktycznego
- [ ] ADR-001…014: żaden nie jest martwy/łamany; naruszenia = ustalenie
- [ ] Skill `ffp-framework` + CLAUDE.md aktualne
- [ ] D10 (retencja): rewizja zapowiedziana przy R4 — ocenić i zapisać
      rekomendację właścicielowi
- [ ] **D6/D7 nadal OPEN?** → jawne przypomnienie właścicielowi w raporcie
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

- [ ] PROGRESS + Completion notes 01–16 + follow-upy R1–R3 przeczytane
- [ ] `task check` + pełne e2e zielone na wejściu
- [ ] `/security-review` full + nagłówki + uploady + grep sekretów
- [ ] `pip-audit` + `npm audit` bez HIGH
- [ ] Pomiary wydajności wykonane (tabela)
- [ ] Round-trip eksport→import wykonany i porównany
- [ ] AC batchy 01–16 zweryfikowane wyrywkowo (min. 2 per batch)
- [ ] Dług zebrany i spriorytetyzowany (P1/P2/P3)
- [ ] Architektura + ADR + skill + CLAUDE.md zaktualizowane
- [ ] D6/D7 — przypomnienie właścicielowi zapisane
- [ ] „Ustalenia R4 do wykonania" wpisane do karty B17
- [ ] Werdykt GO/NO-GO + wpis dziennika w PROGRESS.md

## Verification checklist

- [ ] `task check` zielony po naprawach
- [ ] Acceptance Criteria 1–9 odhaczone
- [ ] Batche naprawcze (jeśli są) mają komplet sekcji szablonu §6
- [ ] Każde ustalenie: naprawione / P1→B17 / P2-P3→rejestr / decyzja OPEN
- [ ] Commit `batch(R4): review ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
