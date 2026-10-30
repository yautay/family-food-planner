# Orkiestracja wykonania w Sol

Proponowany sposób uruchomienia: jeden orkiestrator Sol, maksymalnie trzy aktywne agenty robocze, bez dalszego delegowania przez wykonawców. Limit dostosować w dół do możliwości środowiska. Plan nie tworzy agentów, chatów ani automatyzacji.

Podział na ograniczone zadania, przekazywanie wyników i bramki odbioru opiera się na wzorcu z [OpenAI Docs o pracy wielu agentów](https://developers.openai.com/api/docs/guides/responses-multi-agent) i [przykładzie orkiestracji Codex](https://developers.openai.com/cookbook/examples/codex/codex_mcp_agents_sdk/building_consistent_workflows_codex_cli_agents_sdk). Układ ról i harmonogram poniżej są decyzją projektową dla tego repo, nie wymaganiem platformy. Nie trzeba instalować Agents SDK ani uruchamiać API modeli.

## Role

**D35 / 2026-10-30:** właściciel zaakceptował zastąpienie niedostępnych
builtin `/code-review` i `/security-review` niezależnym review Sol według
architektury i `pasnik-security`, z rzeczywistymi testami scope/CSRF/tokenów
i audytem zależności. Dotyczy UX00–UX11. Nie deklarować wykonania builtin
skilla; wymagania niezależności, testów i wizualnego odbioru pozostają.

| Rola | Odpowiedzialność | Ograniczenie |
|---|---|---|
| O — orkiestrator | Kolejność, przydział ścieżek, kontrakty, integracja, postęp i bramki | Nie edytuje równolegle plików oddanych wykonawcy |
| A — wykonawca pierwszej karty | Ograniczony pion funkcjonalny wraz z testami | Nie zmienia zakresu ani plików drugiego agenta |
| B — wykonawca drugiej karty | Niezależny pion w osobnym worktree | Nie „naprawia przy okazji” współdzielonych komponentów |
| C — reviewer albo trzeci wykonawca | Przegląd ukończonego diffu; w fali końcowych ekranów osobna karta | Nie ocenia własnego kodu jako niezależny reviewer |

Proponowane ustawienie Sol: wysoki poziom rozumowania dla orkiestracji, kontraktów, logiki planowania i review; średni dla ściśle opisanych zmian wyglądu. To ustawienia robocze, nie gwarancje jakości. Model i jego wariant pozostają wybrane przez właściciela; wszyscy dziedziczą ten sam Sol. Jeżeli narzędzie nie pozwala sterować poziomem, zachować ustawienie sesji.

## Harmonogram

| Fala | Slot A | Slot B | Slot C | Warunek wyjścia |
|---|---|---|---|---|
| 0 | UX00 | — | odczyt kontraktów, jeżeli potrzebny | Środowisko, zakres i konflikty dokumentacji rozpoznane |
| 1 | UX01 | — | review po ukończeniu | Ustalone komponenty i tokeny |
| 2 | UX02 | — | review nawigacji po ukończeniu | Stabilne menu, adresy i API komponentów |
| 3 | UX03 | UX05 | review pierwszej gotowej karty | Obie karty zintegrowane i zweryfikowane |
| 4 | UX04 | UX06 | review gotowych zmian | Gotowy codzienny przepływ przepis → plan → zakupy |
| 5 | UX07 | — | review kopiowania i cykli | Plan tygodnia gotowy |
| 6 | UX08 | UX09 | UX10 | Wszystkie trzy karty oddane; review przejmuje zwolniony slot |
| 7 | UX11 | korekty przypisane właścicielom | niezależny review końcowy | Zamknięty zakres podstawowy |

UX03 i UX05 zaczynają z tego samego zintegrowanego commita UX02. UX04 i UX06 zaczynają dopiero po integracji poprzedniej fali. W fali 6 nie uruchamiać czwartego agenta. Reviewer pracuje na niezmiennym diffie; późniejsze poprawki wymagają ponownego przeglądu zmienionych części.

Jeden batch oznacza jedną świeżą sesję roboczą. Orkiestrator może koordynować kolejne batchy po wyraźnym uruchomieniu całego programu. To proponowane rozszerzenie starej procedury „jeden batch i koniec” i listy dawnych par równoległych; UX00 rejestruje je w dokumentacji programu, zanim rozpocznie się równoległa implementacja. Nie zmienia to historycznych kart.

## Izolacja pracy

Każdy równoległy wykonawca ma osobny worktree od tej samej zatwierdzonej podstawy. Orkiestrator najpierw sprawdza istniejące worktree i stan użytkownika. Nazwy gałęzi zaczynają się od `codex/`, np. `codex/ux03-plan-dnia`. Jeśli izolacja jest niedostępna, wykonywać karty sekwencyjnie; współdzielony katalog nie daje automatycznie osobnych kopii plików.

Wyłącznie orkiestrator integruje do gałęzi programu. Nie robi resetu, czyszczenia ani przenoszenia niepowiązanych zmian użytkownika. Każdy wynik ma wskazany bazowy commit, listę plików i końcowy diff. Worktree zachować do odbioru, później można go zarchiwizować zgodnie z mechanizmem środowiska.

W trakcie równoległej pracy obowiązuje wyłączna rezerwacja na zmiany w:

- `frontend/src/assets/tailwind.css`, `components/ui/**`, `layouts/**`, `router.ts`, `lib/navigation.ts`;
- `frontend/src/lib/texts.ts`, `api/queryKeys.ts`;
- `frontend/src/api/generated.ts`, `backend/openapi.json`;
- lockfile, `Taskfile.yml`, konfiguracji Vite, Playwright i service workera;
- `docs/architecture/**`, `docs/adr/**`, historycznych rejestrach i `ux-redesign/PROGRESS.md`.

O udziela prawa jednemu wykonawcy na dany plik. Pozostali przekazują konkretną prośbę o zmianę kontraktu: plik, sygnatura, konsument, test. Dla UX03 rezerwacja OpenAPI i wygenerowanych typów należy do A; UX05 nie dotyka kontraktu backendu. W UX04/UX06 wspólne teksty i klucze cache integruje O kolejno. `SklepySection.vue` ma właściciela UX10; UX09 nie zmienia profili sklepu.

## Bramki i stany

`PLANOWANY → GOTOWY → W_TOKU → DO_REVIEW → ZWERYFIKOWANY → ZINTEGROWANY`.

`ZABLOKOWANY` zawiera dokładny warunek, właściciela rozwiązania i zakres pracy, który nadal może postępować. Zależności są spełnione dopiero przez ZINTEGROWANY, nie przez sam raport „skończyłem”.

- Wejście: karta i wymagane konteksty przeczytane, zależności zintegrowane, pliki zarezerwowane, brak nierozstrzygniętej decyzji dotyczącej tego zadania.
- Wykonanie: testy scenariuszy karty, właściwe stany błędów, wizualny przegląd rzeczywistego UI, brak atrap.
- Review: niezależny przegląd diffu, reguł domeny, uprawnień i UI. Nie wystarcza deklaracja autora.
- Integracja: wynik sprawdzony na połączonym drzewie, `task check`, właściwe E2E, aktualna dokumentacja i lokalny commit `batch(UXnn): opis`, bez push.

Każda karta dziedziczy reguły `CLAUDE.md`, `implementation_prompt.md` i `03_AI_SKILLS.md`, poza wyraźnie zaproponowanym nowym harmonogramem. Required project skills czytać z repo, także gdy środowisko nie ma polecenia Skill. Nie deklarować wykonania `/code-review` lub `/security-review`, jeśli narzędzie jest niedostępne. UX00 sprawdza dostępność; formalny wymóg brakującego audytu rozstrzygnąć zgodnie z manifestem przed zamknięciem właściwej karty, a nie uznawać zwykłego review za wykonany skill.

## Testy bez kolizji

`task fe-test` obecnie nie przekazuje `CLI_ARGS`; uruchamia pełny Vitest. Nie pisać polecenia, które pozornie zawęża ten target. `task test-unit`, `task test-int`, `task test-api` i `task test-e2e` przyjmują argumenty po `--`.

Tylko jeden agent naraz ma prawo używać wspólnej bazy i przeglądarkowego środowiska E2E. Rezerwacja obejmuje `task check`, testy backendu korzystające z DB, migracje, seed, E2E i operacje czyszczące. Osobny worktree nie izoluje bazy, portów ani danych. Suity E2E zachowują `workers: 1`. Nie równoleglić ich z `pdfx-roundtrip`, importami, resetami ani innymi suitami.

Każda karta kodu: `task check` oraz E2E wskazane w karcie; końcowa bramka UI: pełne `task test-e2e`. O uruchamia sprawdzenie integracyjne po połączeniu gotowych zmian; nie powtarza wszystkich testów po samym czytaniu plików. Awaria infrastruktury pozostaje awarią, nie zielonym wynikiem.

## Pakiet zlecenia dla agenta

Każdy start zawiera te informacje, zamiast samego „zrób ekran”:

```text
Model: Sol wybrany dla programu.
Karta: <ścieżka UXnn>, przeczytaj w całości.
Baza: <commit>, worktree: <bezwzględna ścieżka>.
Cel tej sesji: <jedno konkretne zachowanie użytkownika>.
Dozwolone pliki: <lista>; rezerwacje współdzielone: <lista lub brak>.
Zależności: <commity i stabilne kontrakty>.
Referencja: DESIGN_SPEC.md + właściwy ekran makiety.
Nie rozszerzaj zakresu, nie deleguj dalej, nie wykonuj deployu ani pushu.
Nie zmieniaj plików innego agenta; brakujący kontrakt zgłoś orkiestratorowi.
Zwróć wynik według formatu poniżej. Nie oznaczaj własnego wyniku jako zintegrowany.
```

## Przekazanie wyniku i wznowienie

Raport wykonawcy: identyfikatory zadań, zmienione pliki, bazowy i końcowy commit/diff, zachowanie przed/po, kryteria spełnione/niespełnione, rzeczywiste komendy i wyniki, zrzuty ekranów, zmiany API, ryzyka i wpływ na następne karty. Bez sekretów i danych produkcyjnych.

O zapisuje postęp po każdym przekazaniu. Przy wznowieniu odczytuje PROGRESS, faktyczne diffy, stan agentów/worktree i ostatnią bramkę. Nie wysyła ponownie ukończonego zadania i nie uznaje ciszy agenta za sukces. Przy problemie z kontekstem przekazuje kartę i wyniki do świeżej sesji, bez kopiowania całej historii rozmowy.

Błąd zakresu lub konflikt plików: zatrzymać zapisy wyłącznie konfliktującego wykonawcy, ustalić właściciela, uzgodnić zmianę i ponownie sprawdzić konsumentów. Problem produktowy dotyczący jednej funkcji nie blokuje niezależnych kart. Zmiana wyglądu zgodna z zaakceptowaną specyfikacją nie wymaga ponownego zatwierdzania koloru czy promienia każdego elementu.

## Odbiór programu

Gotowe oznacza: wszystkie UX00–UX11 zintegrowane, brak otwartych błędów blokujących podstawowe przepływy, testy i review z dowodami, komplet mapowania starych funkcji na nowe ekrany, porównanie wizualne oraz lista świadomie odroczonych rozszerzeń. Produkcyjny deploy nie jest kryterium tego programu.
