# UX00 — faktyczny punkt odniesienia

Data: 2026-10-29. **UX00 nie jest odebrane.** Wykonano audyt repo, odtworzono narzędzia i zależności oraz uruchomiono dostępne bramki. Dalszy odbiór wymaga działającego lokalnego stacku PostgreSQL/backend i konta E2E. UX01–UX11 pozostają nierozpoczęte; ich zależność UX00 nie została spełniona.

## Repo i izolacja

- HEAD wejściowy: `b8020cd67745d78772b0b40a8bf85ca4d9c0d7b1`, gałąź `master`.
- Jedyna zastana zmiana: nieśledzony `docs/implementation-plan/ux-redesign/`. Brak zastanych zmian śledzonego kodu. Nie znaleziono `AGENTS.md` w repo.
- Właściciel jawnie autoryzował zapis samej dokumentacji przed tworzeniem worktree. Commit `511a249aa570ad45f6d2569b5c07abdf94975948` zawiera tylko tę dokumentację, w tym kartę odroczonego UX12; nie uruchamia implementacji UX12.
- Gałąź programu: `codex/ux-redesign`, główny katalog `F:/repo/family-food-planner`.
- Pomocniczy audytor kontraktów: świeży agent `ux00_contracts`, model `gpt-6.1-sol`, high, bez dalszego delegowania. Osobny worktree `C:/Users/yauta/.codex/worktrees/ux00-contracts/family-food-planner` od `511a249`, wyłącznie plik `CONTRACTS.md`. Commit autora: `c7e5ead1573cb956837e645cef713818b325a7de`; przejęcie wyniku przez O nie oznacza integracji całej karty.
- Zapis `.git` i dostęp do worktree wymagały eskalacji sandboxa; rejestracja worktree jest poprawna. Bez zmiany `core.worktree`, bez resetu, czyszczenia czy przenoszenia zmian użytkownika.
- Brak pushu, deployu, poleceń produkcyjnych, migracji bazy użytkownika, seedowania i importów.

## Środowisko zastane i naprawy lokalne

| Element | Faktyczny wynik |
|---|---|
| Node | Dostępny runtime Codex: `v24.19.0`; wymaganie repo Node 22+ spełnione |
| task / uv / npm | Początkowo nieobecne w PATH; przenośne narzędzia odtworzono z oficjalnych dystrybucji |
| Narzędzia odtworzone | go-task `3.54.0`, uv `0.13.6`, npm `12.2.1`; ignorowany katalog `backend/data/ux00-tools/` |
| Python | `task install` wybrał dostępny CPython `3.14.6`, utworzył `backend/.venv`; projekt wymaga >=3.13 |
| Zależności aplikacji | `task install` exit 0; zainstalowano lockfile bez jego zmiany; frontend 728 paczek, backend 60 |
| Przeglądarka | `task e2e-install` exit 0; Chromium / Headless Shell v1234 i Winldd zainstalowane przez Playwright |
| Docker | Brak `docker` w PATH i w standardowej lokalizacji Docker Desktop; brak wykrytej usługi Docker/PostgreSQL/Podman |
| WSL | Odczyt po eskalacji kończy się `Wsl/CallMsi/Install/REGDB_E_CLASSNOTREG` („Klasa niezarejestrowana”); nie znaleziono działającej alternatywy dla stacku |
| Konfiguracja | W repo nie było i nie utworzono `.env`; brak skonfigurowanego `TEST_DATABASE_URL` i konta E2E. Nie odczytywano sekretów produkcyjnych |
| Końce linii | `core.autocrlf=true`: index LF / checkout CRLF w frontendzie. Prettier zgłosił 186 plików. Po sprawdzeniu braku zmian frontendu znormalizowano wyłącznie CRLF→LF w 190 śledzonych plikach tekstowych; zerowy diff treści, `task format-check` zielony. Ustawień Git nie zmieniano |
| Sieć/sandbox | Pobrania i cache uv wymagały eskalacji; próba pobrania w sandboxie zwróciła nieznany host, a kontrola formatowania w sandboxie błąd cache. Powtórzenia z eskalacją przeszły. Nie jest to błąd aplikacji |

Narzędzia są lokalne, nie dodane do systemowego PATH ani do Git. Aby powtórzyć targety w tej sesji PowerShell:

```powershell
$env:PATH = 'F:\repo\family-food-planner\backend\data\ux00-tools;' + $env:PATH
task check
# Vite na tym hoście odpowiada pod localhost, nie pod domyślnym 127.0.0.1:
$env:E2E_BASE_URL = 'http://localhost:5173'
task test-e2e
```

`npm.cmd` i `npx.cmd` w lokalnym katalogu narzędzi odsyłają do oficjalnego npm uruchamianego przez Node. Nie zmieniają skryptów projektu. W nowym środowisku można użyć standardowo zainstalowanych task/uv/npm; przenośny katalog nie jest wersjonowany. W nowych checkoutach sprawdzić końce linii przed interpretacją błędów Prettiera.

## Rzeczywiste testy i bramki

Wszystkie testy korzystające ze wspólnego środowiska uruchamiał kolejno O. Audytor nie uruchamiał DB, E2E ani testów. Logi dostępnych osobnych targetów są lokalnie w `backend/data/ux00-results/`, ignorowane przez Git; poniższe podsumowanie jest trwałym zapisem. Pełny `task check` zachował się w transkrypcie sesji, nie w tym katalogu logów.

| Komenda | Rzeczywisty wynik |
|---|---|
| Początkowe `task check`, `task test-e2e` | Nie wystartowały: command not found; naprawiono brak task |
| `task install` | PASS, exit 0; brak diffu `backend/uv.lock` i `frontend/package-lock.json` |
| `task check` po instalacji | **FAIL**: migrations-check **3 passed**, unit **572 passed**, integration **1 passed / 291 errors**, powód fixture: brak `TEST_DATABASE_URL`. Kolejne targety tej komendy nie zostały wykonane |
| `task dev-db` | **FAIL**, exit 127: `docker`: executable file not found in PATH. Nie uruchomiono baz ani nie dotknięto istniejących danych |
| `task fe-test` | PASS: **47 plików / 409 testów**, exit 0 |
| `task typecheck` | PASS: mypy **218 plików**, vue-tsc bez błędów, exit 0 |
| `task lint` | PASS: ruff i eslint, exit 0 |
| `task format-check` | Pierwszy przebieg: FAIL (frontend CRLF); po lokalnej normalizacji PASS: ruff **237 plików**, Prettier bez uwag, exit 0 |
| `task fe-build` | PASS, exit 0; PWA precache 68 wpisów; build lokalny, bez publikacji |
| `task fe-types-check` | PASS, exit 0: OpenAPI i generated.ts zgodne z kodem |
| `task e2e-install` | PASS, exit 0 |
| `task test-e2e` z domyślnym URL | **FAIL**: timeout 60000 ms oczekiwania na Vite `127.0.0.1:5173` |
| `E2E_BASE_URL=http://localhost:5173; task test-e2e` | **FAIL**: Vite i Chromium uruchomione; **1 failed** (setup: brak E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD), **19 did not run**, workers=1. Nie wykonano logowania, purge ani zapisu danych |
| `task audit-fe` | **FAIL**, exit 201 targetu (npm exit 1): **19 alertów: 5 low, 4 moderate, 10 high**. Zastany lockfile; m.in. Vite i zod. Bez `npm audit fix` i bez aktualizacji zależności |

Nie uruchomiono osobno `task test-api`, bo blokada DB jest już ustalona; nie ma wyniku pozytywnego API ani całego check. Nie wykonano `task audit` backendu, skanu sekretów przez Docker ani niedostępnych wbudowanych skilli. Błędów infrastruktury nie zaliczamy jako PASS i nie usuwamy testów w celu uzyskania zielonego wyniku.

## Mapa funkcji, dane i kontrakty

[CONTRACTS.md](CONTRACTS.md) zawiera sprawdzoną z kodem mapę zachowanych funkcji, stabilne adresy, zakresy uprawnień, projektowany panel i jedyne rozszerzenia domenowego API dopuszczone w UX03. O przyjmuje opisane nazwy jako zamrożony kontrakt programu; implementacja i testy pozostają zadaniem UX03:

- `RecipePlanningPanel.vue`: `open`, `recipe`, `date`, `meal`, `replaceItem`; `close()` i `saved({day, mealId, itemId, mode})` wyłącznie po potwierdzonym zapisie.
- `POST /api/v1/plan/days/{date}/recipe-items`: XOR `meal_id`/`new_meal_name`, `recipe_id`, `servings`, `servings_split`; jedna transakcja, odpowiedź 201 `{day, meal_id, item_id}` z rzeczywistymi ID.
- Addytywne `recipe_id` w PATCH pozycji przepisu; nie jest dozwolona konwersja produktu luzem ani DELETE→POST. Pozostałe pola i podział zachowują dotychczasową semantykę.
- Panel/modal korzysta z reka-ui; pełna obsługa fokusu, Escape i powrotu do wywołującego. `PlanningDialog` pozostaje kompatybilny do migracji UX07.
- Zamrożono rozróżnienie pustych danych i błędów, błędu refetch z cache, błędu kolejnej strony i niepotwierdzonego zapisu POST. Brak ślepego retry mutacji.
- Nawigacja: Plan / Przepisy / Zakupy / Spiżarnia; Dzień / Tydzień / Podsumowanie w Planie, produkty i ustawienia pomocniczo, ADMIN osobno, `/l/:token` poza sesją i AppShell. Stare nazwy tras i URL zostają.

Ryzyko do objęcia testem UX03: obecne mutacje po meal/item ID serializują `get_day(user, date)`; przy cudzym jawnym dniu ADMIN-a i własnym dniu tej samej daty resolver może zwrócić inny dzień niż zmieniony. Nowe API ma serializować faktyczny zmieniony dzień bez rozszerzania uprawnień. To ustalenie z kodu, nie odtworzony błąd runtime.

Scenariusz danych w CONTRACTS §6 jest **specyfikacją, nie wykonanym seedem**. Obejmuje pusty plan, 3 profile, split pełny/częściowy/historyczny, brak profili, zdjęcie/brak zdjęcia, długie polskie nazwy, 55 przepisów i produktów, 105 partii spiżarni, globalny przepis oraz listę offline. Nie wolno uruchamiać istniejącego szerokiego purge E2E na danych użytkownika. Bezpieczna, osobna lokalna baza i konta są warunkiem wykonania fixture i testów scenariusza.

## Dowody wizualne

**Brak zrzutów działających chronionych ekranów.** Dzień, katalog, szczegół przepisu, tydzień i zakupy nie zostały otwarte z prawdziwymi danymi. Udany build i wystartowanie serwera logowania nie zastępują kontroli tych ekranów. Nie wytwarzano atrap API, fikcyjnych sesji ani rekonstrukcji jako dowodu baseline.

Po odblokowaniu wykonać matrycę 360/390/768/1024/1440 px, z kontrolą 320 px i powiększenia, na scenariuszu CONTRACTS §6. Screenshoty lokalne w wydzielonym katalogu bez cookies, publicznych tokenów i danych osobowych. Reference `domowa-kuchnia.html`, w tym jej „Przed”, pozostaje makietą, nie pomiarem starego UI.

## Własność plików i następne przekazanie

| Fala / karta | Właściciel planowany | Wyłączność |
|---|---|---|
| UX00 | O; audyt pomocniczy Sol | O: BASELINE, PROGRESS, karta UX00, indeksy historyczne; audytor: wyłącznie CONTRACTS |
| UX01 | świeży Sol A, potem reviewer | tokens, UI, nowe wspólne domenowe komponenty i ich testy; dokumentacja architektury przez O |
| UX02 | świeży Sol A, potem reviewer | AppShell, navigation, router i testy; teksty rezerwowane jednemu autorowi |
| UX03 / UX05 | Sol A / Sol B z tego samego commita UX02 | A: plan dnia/panel/planning BE/OpenAPI/generated/queryKeys/teksty; B: Zakupy/generator bez kontraktu backendu; reviewer w wolnym slocie |
| UX04 / UX06 | Sol A / Sol B | A: katalog/szczegół/RecipeCard; B: prywatna/publiczna lista/druk; wspólne teksty i cache integruje O kolejno |
| UX07 | świeży Sol A | tydzień, dialogi kopiowania/szablonów/cykli i testy; wspólne zmiany tylko po rezerwacji |
| UX08 / UX09 / UX10 | Sol A / Sol B / Sol C | edytor / spiżarnia i produkty / ustawienia i statystyki; SklepySection wyłącznie UX10; review po zwolnieniu slotu |
| UX11 | świeży Sol A + niezależny reviewer | matryca odbioru i regresja; korekty wyłącznie według przydzielonego właściciela |

To mapa przyszłych przydziałów, nie uruchomione zadania. Maksymalnie trzech agentów roboczych, wszyscy Sol. Każda karta dostaje świeży kontekst i osobny worktree od odebranej podstawy. Wszystkie rezerwacje aktywne zapisuje wyłącznie O w PROGRESS. DB/E2E/check i operacje importu/seedowania nie są równoleglone.

## Skille, ograniczenia i bramka wznowienia

Manifest `03_AI_SKILLS.md` oraz required project skills są dostępne jako pliki w repo; ich bezpośrednia lektura jest dozwolona przez manifest. Zewnętrzne `/code-review` i `/security-review` nie są dostępne w narzędziach tej sesji. Niezależny przegląd Sol nie jest deklarowany jako wykonanie żadnego z nich.

Manifest §6 pkt 5 wymaga: „brak SKILL-SECREV w batchu z sekcją security = STOP i pytanie do właściciela (świadoma zgoda na commit bez audytu)”. Dla UX03/UX06/UX10/UX11 ta kwestia musi zostać rozstrzygnięta przed zamknięciem właściwej karty: udostępnienie audytu albo jawna zgoda właściciela na wyjątek. Obecny UX00 nie zmienia mechanizmów dostępu. Cały program nie ma domyślnego zwolnienia z formalnego audytu.

Warunki wznowienia, bez cofania gotowych ustaleń:

1. Udostępnić działający, odrębny lokalny stack zgodny z repo (Docker Desktop / backend Linux / PostgreSQL), bez produkcji. Instalacja/naprawa WSL i wirtualizacji hosta nie jest wykonywana w tej sesji; zdiagnozowano jej błąd systemowy.
2. Dopiero po identyfikacji bezpiecznych lokalnych DB utworzyć ignorowany `.env`, ustawić testowy URL, uruchomić właściwe migracje i utworzyć własne konto E2E przez targety repo. Nie wpisywać haseł do dokumentów i nie resetować istniejącej bazy.
3. Wykonać fixture UX00, pełne `task check`, bazowe `task test-e2e` z localhost i rzeczywiste zrzuty. Następnie niezależny review i odbiór UX00.
4. Rozpocząć UX01 dopiero po integracji UX00; kontynuować fale do UX11 zgodnie z autoryzacją właściciela. UX12, push, deploy i produkcja nadal poza zakresem.

Alerty zależności są osobnym, zastanym ograniczeniem do oceny; nie wykonano automatycznego upgrade ani nie uznano ich za regresję programu UX. Dokumentacja wyglądu w architekturze opisuje nadal stary działający kod; nowy kierunek i filtr „Do 30 minut” są planem zatwierdzonym przez właściciela, nie wdrożeniem.

## Niezależny review częściowego wyniku

Reviewer `ux00_review` (świeży Sol high) sprawdził osobny worktree od `511a249`
z nałożonym niezmiennym patchem 62289 bajtów, SHA256
`874df2a4797cc39543c30370e03a8c83d9858448a1e120b8ac37662506af6708`.
Werdykt: **brak ustaleń P0–P3**. Odczyt kodu potwierdził mapowanie,
ograniczony zakres API i ryzyko serializacji dnia; logi potwierdziły osobne
bramki i awarie E2E. Liczby pełnego check są dowodem z transkryptu O,
nie niezależnie powtórzonym przebiegiem reviewera. Reviewer nie zmieniał
kodu i nie uruchamiał DB/testów. To review dokumentacji, nie odbiór UX00,
kontrola wizualna ani wykonanie niedostępnego builtin skilla.
