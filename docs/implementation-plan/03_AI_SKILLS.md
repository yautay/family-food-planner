# 03 — System skilli AI (manifest + selekcja per batch)

Ostatnia weryfikacja: **2026-08-16** · Stack referencyjny: FastAPI ~0.12x /
Pydantic 2.x / SQLAlchemy 2.0 / Vue 3.5 / Vite / Tailwind 4 / shadcn-vue /
Pinia / Playwright. Zasada nadrzędna: skille zwiększają prawdopodobieństwo
dobrych wzorców — **architektura, ADR, testy i acceptance criteria pozostają
nadrzędne**. Skill NIGDY nie nadpisuje decyzji projektu.

## 1. Hierarchia instrukcji (wiążąca dla każdej sesji)

W razie konfliktu wygrywa wyższy poziom:

1. wymagania właściciela (prompt sesji, `02_DECISIONS.md`),
2. ADR (`docs/adr/`) i dokumentacja architektury (`docs/architecture/`),
3. karta wykonywanego batcha,
4. `implementation_prompt.md` (master prompt),
5. `CLAUDE.md` (standardy repo),
6. skille (project i zewnętrzne),
7. ogólna wiedza/preferencje modelu.

Przykład zastosowania: skill sugeruje JWT/OAuth2 → ADR-003 mówi sesje
server-side → **ADR wygrywa**, a rozbieżność NIE jest zgłaszana jako problem
(to normalna sytuacja). Jeśli skill ujawnia realny błąd w ADR — ścieżka to
wpis do 02_DECISIONS/pytanie do właściciela, nie ciche odstępstwo.

## 2. Skill Assessment — co sprawdzono i werdykty

### 2.1 Katalog organizacji (claude.ai skills + plugin catalog)

Przeszukany 2026-08-16 (~30 fraz: python/fastapi/sqlalchemy/pydantic/
postgres/async/security, vue/typescript/tailwind/shadcn/pinia/forms/a11y/
mobile, playwright/component testing/docker/pwa, clean architecture/DDD/
refactoring/quality). **Wynik: 0 trafień** — brak czegokolwiek do instalacji.

### 2.2 Skille wbudowane w Claude Code (dostępne w środowisku)

| Skill | Werdykt | Uzasadnienie |
|---|---|---|
| `/code-review` | **REQUIRED (review)** | przegląd poprawności diffu przed commitem batcha i w Review batchach; nie dubluje niczego |
| `/security-review` | **REQUIRED (review)** | audyt bezpieczeństwa zmian; obowiązkowy w batchach dotykających auth/tokenów/uploadów i we WSZYSTKICH Review |
| `anthropic-skills:pdf` | **REQUIRED (B15/B16)** | poprawne wzorce pdfplumber/pypdf przy pracy nad importerem |
| `claude-api` | **REQUIRED (B16)** | aktualne id modeli, parametry i wzorce Anthropic SDK dla AI-asysty importera — bez niego model pisze integrację z pamięci |
| `skill-creator` | **RECOMMENDED (B01, R1–R4)** | poprawna struktura/triggering project skilli przy ich tworzeniu i aktualizacji |
| `/simplify` | OPTIONAL | sprzątanie po większych batchach; nie zastępuje /code-review |
| `anthropic-skills:xlsx` | OPTIONAL | doraźne analizy danych; poza pętlą implementacji |
| `nuxt-ui` | **REJECTED** | promuje inny stack komponentów (@nuxt/ui) — kolizja z ADR-007 (shadcn-vue, bez Nuxta) |
| `dataviz` | **REJECTED** | projekt ma własne prymitywy SVG i tokens (ADR-013, 06_UIUX); skill artefaktowo-wykresowy nie wnosi wartości, dokłada kontekst |
| `run`, `init`, pozostałe artifact/cowork/morning itp. | REJECTED | narzędzia sesyjne, nie instrukcje implementacyjne dla tego projektu |

### 2.3 Skille społecznościowe (marketplace'y: mcpmarket, skillsdirectory, claudeskills.info, lobehub…)

Zweryfikowano zawartość reprezentatywnych paczek (nie tylko opisy):

- **FastAPI „Grade A" (jezweb, XII 2025)**: wersje aktualne (FastAPI 0.123,
  Pydantic 2.11, SQLAlchemy 2.0.30), sensowne reguły ogólne (schemas ≠
  models, async dla I/O, bez logiki w route'ach — wszystko to już mamy
  w architekturze), ALE: **auth = JWT + python-jose + passlib/bcrypt** —
  wprost sprzeczne z ADR-003 (sesje server-side + argon2id); python-jose
  ma historię CVE i wątpliwe utrzymanie. Instalacja tej instrukcji do sesji
  = aktywne ryzyko, że model „poprawi" nasz auth.
- **Vue 3 packs (vue-js-expert, vue-best-practices itd.)**: treść =
  Composition API + `<script setup>` + TS + Pinia — standardowa wiedza
  modelu; część promuje wzorce Nuxt i trzymanie danych serwera w Pinia,
  co koliduje z ADR-007 (TanStack Query).

**Werdykt zbiorczy: REJECTED.** Powody: (a) kolizje z ADR (auth, state
management), (b) brak gwarancji utrzymania/źródła (niezweryfikowane paczki
osób trzecich w projekcie z naciskiem na security = wektor złych wzorców),
(c) wartościowa część ich treści już jest w naszych docs, reszta to wiedza,
którą Opus ma. Zamiast instalacji: **project skille (§3) destylują nasze
własne, zweryfikowane kontrakty.**

## 3. Recommended Skill Stack — identyfikatory

Minimalny zestaw dla projektu. Project skille żyją w `.claude/skills/`
(wersjonowane w repo, aktualizowane przez Review batche).

| ID | Skill | Typ | Obszar |
|---|---|---|---|
| SKILL-BE | `.claude/skills/pasnik-backend` | project | Python/FastAPI/SQLAlchemy/Alembic/Pydantic/pytest — kontrakt backendu |
| SKILL-FE | `.claude/skills/pasnik-frontend` | project | Vue3/TS/Vite/Tailwind/shadcn-vue/Pinia/Query — kontrakt frontendu + UX |
| SKILL-CALC | `.claude/skills/pasnik-domain-calc` | project | silniki nutrition/shopping: Decimal, jednostki, determinizm, property-based |
| SKILL-SEC | `.claude/skills/pasnik-security` | project | sesje/CSRF/scope/tokeny publiczne/uploady/logi/sekrety |
| SKILL-REVIEW | `/code-review` (wbudowany) | builtin | przegląd poprawności diffu |
| SKILL-SECREV | `/security-review` (wbudowany) | builtin | audyt bezpieczeństwa zmian |
| SKILL-PDF | `anthropic-skills:pdf` (wbudowany) | builtin | praca z PDF (pdfplumber/pypdf) |
| SKILL-API | `claude-api` (wbudowany) | builtin | integracja z Anthropic SDK (B16) |
| SKILL-CREATOR | `skill-creator` (wbudowany) | builtin | tworzenie/aktualizacja project skilli |

## 4. Manifest — kiedy używać / kiedy nie

| Skill | Status | Obszar | Kiedy używać | Kiedy NIE używać | Uwagi |
|---|---|---|---|---|---|
| SKILL-BE | REQUIRED | backend | każdy batch dotykający `backend/**` | batch czysto FE/ops | ładowany na start sesji |
| SKILL-FE | REQUIRED | frontend | każdy batch dotykający `frontend/src/**` | batch czysto BE/ops | zawiera design tokens i wzorce UX |
| SKILL-CALC | REQUIRED | obliczenia | batche z logiką ilości/wartości/agregacji (B04–B07, B10, B13, B15) | CRUD bez obliczeń | najostrzejsze reguły projektu (Decimal!) |
| SKILL-SEC | REQUIRED | security | batche dotykające auth/scope/tokenów/uploadów/deploy (B02, B03, B11, B14, B16, B17, B18) | czysty UI bez danych wrażliwych | uzupełnia, nie zastępuje SKILL-SECREV |
| SKILL-REVIEW | REQUIRED | review | koniec KAŻDEGO batcha przed commitem + Review batche | — | krok 11 master prompta |
| SKILL-SECREV | REQUIRED | review | batche z sekcją Review Skills zawierającą SKILL-SECREV + wszystkie R1–R4 | zwykłe batche UI bez powierzchni ataku | |
| SKILL-PDF | REQUIRED | importer | B15, B16 | wszędzie indziej | |
| SKILL-API | REQUIRED | importer AI | B16 (kod wołający Anthropic API) | wszędzie indziej | id modeli/parametry zawsze z tego skilla, nie z pamięci |
| SKILL-CREATOR | RECOMMENDED | meta | B01 (tworzenie skilli), R1–R4 (aktualizacja) | implementacja funkcji | |
| /simplify | OPTIONAL | quality | po dużych batchach (B10, B16) na życzenie | zamiast /code-review | |
| paczki społecznościowe (FastAPI/Vue z marketplace'ów) | REJECTED | — | — | zawsze | kolizje z ADR-003/007, niezweryfikowane utrzymanie, dublują docs |
| `nuxt-ui`, `dataviz` | REJECTED | — | — | zawsze | inny stack / własne wykresy |

## 5. Skill Matrix per batch (sekcja „Skills" w każdej karcie)

| Batch | Required | Recommended | Review |
|---|---|---|---|
| 01 scaffold | SKILL-BE, SKILL-FE | SKILL-CREATOR | SKILL-REVIEW |
| 02 auth | SKILL-BE, SKILL-SEC | SKILL-FE | SKILL-REVIEW, SKILL-SECREV |
| 03 households | SKILL-BE, SKILL-SEC | SKILL-FE | SKILL-REVIEW, SKILL-SECREV |
| 04 produkty | SKILL-BE, SKILL-FE, SKILL-CALC | SKILL-SEC | SKILL-REVIEW |
| R1 | SKILL-REVIEW, SKILL-SECREV, SKILL-BE, SKILL-SEC | SKILL-FE, SKILL-CREATOR | — (review sam w sobie) |
| 05 przepisy+silnik | SKILL-BE, SKILL-FE, SKILL-CALC | SKILL-SEC (upload) | SKILL-REVIEW |
| 06 cele+plan dnia | SKILL-BE, SKILL-FE, SKILL-CALC | — | SKILL-REVIEW |
| 07 tydzień+szablony | SKILL-BE, SKILL-FE | SKILL-CALC | SKILL-REVIEW |
| R2 | SKILL-REVIEW, SKILL-BE, SKILL-CALC | SKILL-FE, SKILL-CREATOR | — |
| 08 spiżarnia | SKILL-BE, SKILL-FE | SKILL-CALC | SKILL-REVIEW |
| 09 retail+sklepy | SKILL-BE, SKILL-FE | — | SKILL-REVIEW |
| 10 silnik zakupów | SKILL-BE, SKILL-CALC | SKILL-FE | SKILL-REVIEW |
| 11 listy+share | SKILL-BE, SKILL-FE, SKILL-SEC | — | SKILL-REVIEW, SKILL-SECREV |
| R3 | SKILL-REVIEW, SKILL-SECREV, SKILL-BE, SKILL-FE, SKILL-CALC, SKILL-SEC | SKILL-CREATOR | — |
| 12 PWA/offline | SKILL-FE | SKILL-SEC (cache treści) | SKILL-REVIEW |
| 13 statystyki | SKILL-FE, SKILL-CALC | SKILL-BE | SKILL-REVIEW |
| 14 eksport/import | SKILL-BE, SKILL-SEC | SKILL-FE | SKILL-REVIEW, SKILL-SECREV |
| 15 PDF ekstrakcja | SKILL-BE, SKILL-PDF | SKILL-CALC | SKILL-REVIEW |
| 16 PDF review+AI | SKILL-BE, SKILL-FE, SKILL-PDF, SKILL-API | SKILL-SEC | SKILL-REVIEW, SKILL-SECREV |
| R4 | SKILL-REVIEW, SKILL-SECREV, wszystkie 4 project skille | SKILL-CREATOR | — |
| 17 hardening | SKILL-BE, SKILL-SEC | — | SKILL-REVIEW, SKILL-SECREV |
| 18 deployment | SKILL-SEC | SKILL-BE | SKILL-SECREV |

Review Skills = używane na diffie PRZED commitem batcha (nie podczas
pisania kodu). Required = ładowane na starcie sesji, po lekturze karty.

## 6. Mechanizm selekcji (jak to działa w sesji)

1. Karta batcha ma sekcję **`## Skills`** (Required / Recommended / Review)
   z identyfikatorami SKILL-*.
2. Master prompt (krok 1f) każe załadować Required przez narzędzie Skill
   (project skille: nazwa katalogu, np. `pasnik-backend`; wbudowane: ich nazwa).
3. Recommended ładuje się tylko, gdy sesja wchodzi w dany obszar.
4. Review Skills uruchamiane w kroku 11 master prompta (przed commitem).
5. **Skill niedostępny w środowisku**: nie udawaj użycia — odnotuj brak
   w Completion notes i oceń: project skille i SKILL-PDF/SKILL-API mają
   pełną treść w repo/docs (batch może iść dalej, czytając źródła wprost);
   brak SKILL-SECREV w batchu z sekcją security = STOP i pytanie do
   właściciela (świadoma zgoda na commit bez audytu).

## 7. Project-specific skills — co zawierają (i czego nie)

Zaprojektowane 4 (patrz §3). ŚWIADOMIE NIE tworzymy: „Docker skill"
(09_DEPLOYMENT wystarcza — ops robi się 2 razy, nie 20), „Pantry skill",
„Statistics skill" itp. (zwykła karta batcha wystarcza), osobnego „Vue UX
skill" (wchłonięty w SKILL-FE — jeden plik mniej do dryfu). Kryterium:
skill ma sens, gdy te same reguły obowiązują w WIELU batchach i ich
złamanie jest ciche (nie wykryje go kompilator ani test).

Skille są krótkie (≤150 linii), zawierają reguły + wskaźniki do źródeł,
NIE kopiują całych dokumentów architektury.

## 8. Polityka aktualizacji skilli

- Każdy SKILL.md ma w nagłówku: `verified: YYYY-MM-DD` oraz `stack:` (wersje).
- **Właścicielem aktualizacji są Review batche (R1–R4)**: checklista review
  zawiera „project skille zgodne z rzeczywistością repo" — po zmianie
  konwencji skill aktualizuje się w commicie review.
- Podbicie wersji frameworka (major FastAPI/Vue/Tailwind) ⇒ obowiązkowy
  re-review dotkniętego skilla PRZED kolejnym batchem z jego obszaru;
  odnotować nową datę `verified`.
- Skille wbudowane (SKILL-REVIEW/SECREV/PDF/API) aktualizuje Anthropic —
  nie wymagają naszej pielęgnacji; przy dziwnych rekomendacjach obowiązuje
  hierarchia z §1.

## 9. Quality gates — uzupełnienia wynikające z analizy

Istniejące bramki (`task check`: pytest unit/int/api + ruff + mypy +
eslint + vue-tsc + vitest + build; migracje up/down; Playwright E2E) —
bez zmian. UZUPEŁNIENIA (każde z uzasadnieniem, wdrożenie B01/B17):

| Bramka | Narzędzie | Uzasadnienie | Kiedy |
|---|---|---|---|
| `task format` / format-check w `task check` | ruff format + prettier | wiele sesji AI = dryf formatowania; formatter zeruje szum diffów między batchami | B01, każdy batch |
| jedna głowa migracji w `task check` | `alembic heads` (skrypt) | lekcja netQArnera — dwie głowy po merge'u psują wszystko po cichu | B01 |
| `task audit` | pip-audit + npm audit | aplikacja publiczna w Internecie; tanie, zautomatyzowane | R1–R4 + B17 (nie każdy batch — szum nowych CVE nie może blokować batcha UI) |
| `task secrets-scan` | gitleaks (docker) | lekcja netQArnera (sekrety w plikach śledzonych); koszt ~zero | R1–R4 + B17; zalecane przed każdym push |

ODRZUCONE: bandit (dubluje /security-review, wysoki szum), twardy próg
coverage (zachęca do gamingu; pokrycie obszarów krytycznych oceniają
Review), pre-commit hooks (tarcie w workflow agentowym — bramką jest
`task check` + DoD, nie hook).

## 10. Ryzyka systemu skilli

| Ryzyko | Mitygacja |
|---|---|
| Konflikt skill ↔ ADR | hierarchia §1 w master promptcie + skille własne pisane POD ADR-y |
| Przeładowanie kontekstu sesji | limit ≤150 linii/skill, selekcja per batch, Recommended ładowane leniwie |
| Dryf skilli względem kodu | polityka §8 (Review batche jako właściciel), data `verified` |
| Nieaktualne wzorce po upgrade frameworka | wymóg re-review przy major bump (§8) |
| Skill „utwardza" zły wzorzec | skille cytują źródło (ADR/doc) — poprawia się źródło, skill w ślad za nim |
| Overengineering (skill do wszystkiego) | kryterium §7; nowy skill wymaga wpisu tutaj z uzasadnieniem |
