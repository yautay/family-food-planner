# BATCH_R1 — REVIEW_FOUNDATIONS

Klasa: REV · Zależności: B01–B04 (wszystkie `[x]` w PROGRESS.md) · Szacunek rozmiaru: S

## Goal

Audyt fundamentów (scaffold, auth, households+scope, katalog produktów)
zanim powstanie rdzeń planowania. Review NIE dodaje feature'ów: sprawdza
zgodność implementacji z architekturą, trzymanie wzorców, security, testy
i kompletność propagacji decyzji; wolno mu skorygować plan przyszłych
batchy. **Fundamenty nie poprawiają się później tanio — każde ustalenie
blokujące musi zostać zgłoszone i rozstrzygnięte PRZED zleceniem B05.**

## Context

Po B01–B04 istnieją: monorepo (backend FastAPI + frontend Vue 3, Taskfile,
compose.dev, CLAUDE.md, skill `ffp-framework`), auth (sesje server-side,
CSRF, rate limit, `create-admin`), households + scope (`ScopedQuery`,
fundament audit logu), katalog (produkty kanoniczne, jednostki, kategorie,
`ProductPicker` z create-in-context). Ten batch pierwszy raz ogląda je
jako całość w jednej sesji.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` — procedura sesji
  (sekcja „Review batche").
- `docs/implementation-plan/00_MASTER_PLAN.md` §9 (rola review), §7 (DoD),
  §8 (living documentation).
- `docs/implementation-plan/PROGRESS.md` — dziennik B01–B04 (odstępstwa!)
  oraz Completion notes w kartach `BATCH_01…04`.
- `docs/architecture/01_ARCHITECTURE_OVERVIEW.md` §2 (struktura, wzorzec
  modułu), §4 (ScopedQuery), 02_DOMAIN §3–4, 03_DATABASE §1–4,
  04_API §1–3, 05_FRONTEND §1–2 i §4, 07_SECURITY (całość), 08_TESTING §2, §4.
- `docs/implementation-plan/03_AI_SKILLS.md` — użycie `/code-review`
  i `/security-review` w review.
- ADR-002 (migracje), ADR-003 (sesje), ADR-005 (jednostki), ADR-006 (scope),
  ADR-007 (frontend), ADR-012 (usuwanie/archiwizacja).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-REVIEW, SKILL-SECREV, SKILL-BE, SKILL-SEC
- **Recommended**: SKILL-FE, SKILL-CREATOR

Review batch sam jest procesem przeglądowym — SKILL-REVIEW/SKILL-SECREV uruchamiane są na pełnym zakresie zmian od poprzedniego review, nie na diffie własnego commita.

## Stages

1. **Rekonstrukcja stanu**: PROGRESS.md + Completion notes B01–B04; lista
   odstępstw i follow-upów zgłoszonych przez batche. `task check` na
   czystym stanie — musi być zielony ZANIM zacznie się audyt.
2. **Audyt kodu vs architektura**: sekcja „Audit checklist" poniżej,
   punkt po punkcie; każde ustalenie notowane z plikiem/linią.
3. **Security**: `/security-review` na całości zmian od początku repo
   + audyt zależności (`pip-audit`, `npm audit`) + ręczna weryfikacja
   punktów z sekcji Security.
4. **Testy**: pokrycie obszarów krytycznych 08_TESTING §2 (pkt 3, 8 —
   jednostki, uprawnienia) i macierzy §4 dla KAŻDEGO zasobu z B02–B04;
   realne uruchomienie testów sesji/CSRF/rate-limitu.
5. **Analiza planu**: karty B05–B07 vs faktyczny stan repo — czy Context
   kart jest aktualny, czy zakresy nie pękły; ewentualne zmiany planu
   z udokumentowanym powodem (00_MASTER_PLAN §12).
6. **Domknięcie**: drobne naprawy (typówki, martwy kod) w commicie review;
   werdykt + lista ustaleń do PROGRESS.md; aktualizacja kart przyszłych
   batchy i dokumentów architektury; commit `batch(R1): review ...`.

## Audit checklist

### Wzorzec modułu i granice

- [ ] Każdy moduł trzyma `router.py → service.py → models.py`; router
      NIGDZIE nie dotyka sesji DB bezpośrednio (grep po `Session`/`db` w routerach)
- [ ] Import między `modules/*` wyłącznie przez serwisy (modele dozwolone,
      logika — nie); grep importów krzyżowych
- [ ] Kształt błędu API = 04_API §1 we wszystkich handlerach; kody
      401/403/404/409/422/429 zgodne z konwencją
- [ ] OpenAPI kompletne; `task fe-types` generuje typy bez błędów

### ScopedQuery i autoryzacja

- [ ] `ScopedQuery` jest JEDYNĄ ścieżką autoryzacji zasobów scope'owanych —
      żadnego ręcznego `WHERE owner_user_id` poza mixinem (grep)
- [ ] Cudzy zasób → 404, nie 403 (07_SECURITY §4); testy anty-IDOR
      istnieją dla każdego zasobu B03–B04
- [ ] `require_admin` na edycji wartości odżywczych i statusu weryfikacji;
      inline create USERA daje `UNVERIFIED` + wpis audit

### Sesje, CSRF, rate limit — przetestowane REALNIE

- [ ] Cookie: HttpOnly + SameSite=Lax + Secure (prod); logout usuwa wiersz;
      TTL przesuwny działa (test, nie deklaracja)
- [ ] CSRF double-submit: mutacja bez nagłówka → 403 (test API istnieje
      i faktycznie by wykrył regresję — sprawdzić assert)
- [ ] Rate limit loginu 5/min/IP + backoff po 10 nieudanych: test lub
      wykonana ręcznie próba z raportem wyniku
- [ ] argon2id; rehash przy logowaniu; brak haseł/tokenów w logach

### Migracje i baza

- [ ] `alembic heads` = 1; pełny cykl `upgrade head → downgrade base →
      upgrade head` przechodzi na czystej bazie (WYKONAĆ)
- [ ] Naming convention constraintów działa (downgrade nie wybucha na
      bezimiennym constraincie); NUMERIC wszędzie dla ilości (grep po Float)
- [ ] CHECK scope (03_DATABASE §4) obecny; `ON DELETE` jawne na FK

### Katalog i wartości odżywcze

- [ ] Adapter ProductNutrition (wejście do wartości /100 g produktu) jest
      JEDYNYM miejscem odczytu wartości — nic nie sięga w kolumny modelu
      z pominięciem adaptera (przygotowanie pod silnik B05)
- [ ] `ProductUnitWeight`: przeliczniki per produkt, mediana z próbek;
      odmowa zapisu ilości nieprzeliczalnej (02_DOMAIN §13.1)
- [ ] Blokada usuwania (409 + `details.used_in`) i `is_archived` działają
      wg ADR-012

### Frontend

- [ ] Zero kopii stanu serwera w Pinia (przejrzeć stores/*); server state
      wyłącznie TanStack Query, klucze w `queryKeys.ts`
- [ ] `ProductPicker` zgodny z 05_FRONTEND §4: brak wyniku ⇒ `+ Dodaj
      produkt "…"` ⇒ drawer ⇒ auto-wybór ⇒ powrót do flow (sprawdzić ręcznie)
- [ ] `client.ts`: credentials include, nagłówek CSRF, mapowanie ApiError;
      typy z `generated.ts`, zero ręcznych interfejsów odpowiedzi

### Kontrakt sesji AI i narzędzia

- [ ] Taskfile kompletny: wszystkie targety z kart B01–B04 istnieją
      i działają; `task help` aktualny
- [ ] CLAUDE.md zgodny z rzeczywistością repo (komendy, zakazy, wskaźniki);
      skill `.claude/skills/ffp-framework` nadąża za wzorcami (ScopedQuery,
      Decimal, Query/Pinia) — zaktualizować w commicie review, jeśli nie

## Security

- `/security-review` (skill) na całości kodu — obowiązkowy, wynik w raporcie.
- `pip-audit` + `npm audit`: podbicia zależności z podatnościami HIGH+
  wykonać w commicie review (patch-level); większe → follow-up do PROGRESS.
- Grep sekretów: `git ls-files` bez `.env`; brak kluczy/haseł w kodzie
  i testach (w tym fixture'ach).

## Tests

- `task check` zielony przed i po naprawach review.
- Weryfikacja, że testy krytyczne ISTNIEJĄ i COŚ SPRAWDZAJĄ (przejrzeć
  asserty, nie tylko nazwy): macierz uprawnień 08_TESTING §4 per zasób,
  konwersje jednostek (§2.3), sesje/CSRF/rate-limit, cykl migracji.
- Luki w pokryciu obszarów krytycznych: małe → dopisać w commicie review;
  większe → wpis do karty batcha, który obszar posiada.

## Acceptance Criteria

1. Wszystkie punkty Audit checklist odhaczone albo przekute w ustalenia
   (naprawione w review / follow-up z miejscem docelowym).
2. `/security-review` i audyt zależności wykonane; wynik opisany.
3. `task check` zielony po zmianach review.
4. Werdykt w PROGRESS.md: **PASS** (B05 może startować) / **PASS z
   warunkami** (lista) / **BLOKADA** (co musi się stać przed B05).
5. Karty B05–B07 przejrzane; korekty planu (jeśli są) wprowadzone
   do 00_MASTER_PLAN + kart z powodem w PROGRESS.
6. Skill ffp-framework i CLAUDE.md aktualne wobec stanu repo.
7. Commit `batch(R1): review ...` wykonany, `git status` czysty.

## Out of Scope

- Jakiekolwiek nowe feature'y i refaktoryzacje ponad drobne naprawy
  (większe → ustalenie z miejscem docelowym: karta batcha albo 02_DECISIONS).
- Zmiany architektury bez wpisu (konflikt = pytanie do właściciela).
- Silnik nutrition i przepisy → B05 (tu tylko gotowość fundamentu).

## Expected files/modules

- `docs/implementation-plan/PROGRESS.md` — werdykt + wpis dziennika.
- Ewentualnie: drobne naprawy w `backend/**`, `frontend/**`; aktualizacje
  `CLAUDE.md`, `.claude/skills/ffp-framework/SKILL.md`, kart
  `BATCH_05…07`, dokumentów `docs/architecture/**`, `00_MASTER_PLAN.md`.

## Implementation Notes

- Kolejność: najpierw czytanie i audyt, naprawy na końcu — inaczej diff
  review zlewa się z ustaleniami.
- Ustalenie = plik/linia + dlaczego niezgodne + rekomendacja. Bez tego
  werdykt jest nieweryfikowalny.
- Granica „drobnej naprawy": nie zmienia kontraktu API, schematu DB ani
  zachowania widocznego dla użytkownika. Wszystko powyżej → follow-up.
- To OSTATNI tani moment na zmianę fundamentów (nazwy kolumn scope,
  kształt ScopedQuery, kontrakt błędów) — wątpliwości eskalować teraz.

## Cross-Batch Impact

- **B05–B07**: werdykt + zaktualizowane karty to bramka wejścia; ustalenia
  o adapterze nutrition wpisać do karty B05.
- **R2**: dziedziczy listę follow-upów niedomkniętych w R1 (wpis w PROGRESS).
- **Wszystkie**: zmiany w CLAUDE.md/skillu obowiązują od następnej sesji.

## Implementation checklist

- [ ] PROGRESS + Completion notes B01–B04 przeczytane, lista odstępstw
- [ ] `task check` zielony na wejściu
- [ ] Audit checklist wykonana punkt po punkcie (ustalenia z plik/linia)
- [ ] `/security-review` + `pip-audit` + `npm audit` wykonane
- [ ] Pokrycie testami obszarów krytycznych zweryfikowane (asserty!)
- [ ] Karty B05–B07 przejrzane i zaktualizowane
- [ ] Drobne naprawy wykonane; follow-upy rozpisane do miejsc docelowych
- [ ] Skill ffp-framework + CLAUDE.md zaktualizowane (jeśli trzeba)
- [ ] Werdykt + wpis dziennika w PROGRESS.md

## Verification checklist

- [ ] `task check` zielony po naprawach
- [ ] `alembic heads` = 1; cykl up/down/up wykonany realnie
- [ ] Acceptance Criteria 1–7 odhaczone
- [ ] Każde ustalenie ma status: naprawione / follow-up (gdzie) / decyzja OPEN
- [ ] Commit `batch(R1): review ...`, `git status` czysty

## Completion notes

(wypełnia agent wykonujący)
