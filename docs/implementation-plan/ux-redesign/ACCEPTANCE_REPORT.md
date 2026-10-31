# Odbiór UX00–UX11 — Paśnik

Data: 2026-10-31. Wynik: **pozytywny odbiór UX00–UX11**. Kod aplikacji
odpowiada kandydatowi `9ec4080640ab59c34fc4f1027c6e15e01343d8a8`, z osobnym
helperem odbioru O. Baza integracji UX11: UX10 `1386ee0`.
Ten raport, karta i końcowe źródła wchodzą do jednego lokalnego commita UX11.
[Potwierdzenie integracji](../../../backend/data/ux11-results/integration.json)
zapisane po commicie podaje pełny hash i wynik postcommit secrets-scan.
UX12, push, deploy i operacje produkcyjne są poza zakresem.

## Wynik i zakres

Wdrożono kierunek „domowa książka kucharska”, cztery główne wejścia oraz
uproszczone planowanie, przepisy, zakupy, spiżarnię, bibliotekę produktów
i ustawienia. Wartości całego planu są oddzielone od celu konta i faktycznego
spożycia. Zachowano wcześniejsze funkcje, zakresy danych, Decimal/stringi,
sesje/CSRF, publiczne listy oraz prywatną i publiczną kolejkę offline.

Całość wykonano lokalnie, z osobnymi worktree i jednoznacznymi grantami
plików, najwyżej trzema aktywnymi wykonawcami Sol. O wykonywał wszystkie
operacje wspólnej bazy i E2E kolejno. Dokumentacja programu była zapisana
w bazowym commicie przed izolacją. Nie nadpisano ani nie commitowano
niepowiązanych zmian użytkownika. Szczegółowy przebieg: [PROGRESS.md](PROGRESS.md).

## Mapa zachowanych funkcji

34/34 wiersze pierwotnego [CONTRACTS.md](CONTRACTS.md) mają wskazane miejsce.
Niezależny review Sol potwierdził źródła, API i konkretne nazwy testów
w [szczegółowym rejestrze](reviews/UX11_CONTRACTS.md). Poniżej skrót.
Nazwy plików E2E odnoszą się do `frontend/e2e`; testy FE/API/integration
objęła pełna bramka. Obecność kodu i wynik rzeczywistego testu są odrębne
rodzaje dowodu — nie przedstawiamy statycznego review jako wykonania E2E.

| # | Funkcja | Miejsce i dowód |
|---|---|---|
| 1 | Dzień, poprzedni/następny/dziś, pusta data | Plan → Dzień; `ux-navigation`, `smoke`, `ux-planning`; API planowania |
| 2 | Nazwa/cel posiłku, usunięcie i duplikat | Akcje posiłku; PlanDnia/MealCard FE, API planowania |
| 3 | Przepis i mnożnik | Wspólny panel planowania i pozycja posiłku; `ux-planning`, `smoke` |
| 4 | Produkt luzem | Akcje posiłku → Dodaj produkt; FE i API planowania/konwersji |
| 5 | Podział porcji i wyczyszczenie | Panel porcji / ServingsSplitDrawer; FE, API scheduling i integration |
| 6 | Dopasowanie do celu posiłku | Menu dania → propozycja → jawne Zastosuj; FE/API/integration |
| 7 | Kopia dnia/posiłku, dopisywanie | Dzień / Uzupełnij plan; `ux-week`, `week-template-cycle` |
| 8 | Tytuł i widoczność dnia | Zachowane API i wyświetlanie tytułu; API planowania. Formularza PUT nie było przed przebudową |
| 9 | Tydzień, zakres i przejście do dnia | Plan → Tydzień, czytelna agenda; `ux-week`, `ux-navigation` |
| 10 | Przeniesienie posiłku | Dialog i zachowane DnD; `week-template-cycle` sprawdza ścieżkę przyciskową |
| 11 | Bloki, szablony i cykle | Uzupełnij plan; `week-template-cycle`, FE dialogów, API templates |
| 12 | Historia ponownego użycia | Uzupełnij plan → wcześniejsze dni; FE dialogu historii oraz API/integration kopiowania; bez dedykowanego E2E wyboru historycznego dnia |
| 13 | Katalog, AND tagów, scope, strony | Przepisy; `ux-recipes`, `paginacja`, `recipe-global`, API scope |
| 14 | Szczegół, skale i oceny | Szczegół przepisu; FE szczegółu, API receptur, `recipe-inline-create` |
| 15 | Tagi i systemowe ulubione | Filtry / uprawniony edytor; FE katalogu/edytora i API receptur; bez osobistej zakładki |
| 16 | Edytor, inline produkt i zdjęcie | Sekcje edytora; `ux-editor`, `recipe-inline-create`, API uploadów i rzeczywiste PNG zdjęcia |
| 17 | Kopia, archiwum, usunięcie i role | Szczegół/edytor; `recipe-global`, FE i API scope; regresje starych callbacków UX11 |
| 18 | Listy po reload | Zakupy → Zapisane listy; `ux-shopping-home` ze wszystkimi stronami |
| 19 | Generator, tury, jawna spiżarnia | Zakupy → zakres/podgląd; tury także Ustawienia → Zakupy; `shopping-generate`, `ux-shopping-home` |
| 20 | Checkbox, mam w domu, resztka i sklep | Lista zakupów; `ux-shopping-checklist`, `shopping-list-sharing`, API/integration list |
| 21 | Link/QR/share, odwołanie i druk | Akcje listy, publiczna lista poza shellem; `shopping-list-sharing`, FE share, opt-in print |
| 22 | Offline, reload i LWW | Prywatna/publiczna lista; `offline-lista`, zbudowane PWA basic/advanced i queue FE |
| 23 | Przyjęcie do spiżarni i usunięcie | Jawne potwierdzenie listy; `ux-shopping-checklist`, API/integration idempotencji |
| 24 | Spiżarnia: partie, filtry, widoki, strony | Spiżarnia i ActionPanel; `ux-pantry-products`, `pantry`, API scope/paginacji |
| 25 | Produkty, miary, jednostki, dane i409 | Biblioteka → cztery sekcje formularza; `produkty`, `ux-pantry-products`, API catalog |
| 26 | Warianty sklepowe i opakowania | Produkt → Warianty sklepowe; `retail-stores`, API retail |
| 27 | Sklepy i kolejność kategorii | Ustawienia → Zakupy; `retail-stores` sprawdza strzałki i trwałość przez API; DnD zachowane w komponencie |
| 28 | Profile osób, mnożniki, cele, aktywność | Ustawienia → Rodzina; `households`, `ux-settings-summary`; konta dostępu pokazane osobno |
| 29 | Historyczne cele i progi konta | Ustawienia → Moje cele; `ux-settings-summary`, FE oraz API goals |
| 30 | Statystyki do92dni i niepełne dane | Plan → Podsumowanie; `statystyki`, FE cached-empty/refetch, API stats |
| 31 | Kopia rodziny i import/scalanie | Ustawienia → Dane; `transfer`, integration roundtrip i API zakresu eksportu |
| 32 | Administracja | Cztery dotychczasowe adresy ADMIN; `households`, `produkty`, `recipe-global`, API ról oraz16PNG UX10 |
| 33 | Login, sesja, logout i powrót | Login / menu konta; `smoke`, `ux-navigation`, rzeczywiste PWA i deferred FE UX11 |
| 34 | Audyt bez starego ekranu | ADMIN-only API audytu; API testy. Nie dodano fikcyjnego `/admin/audit` |

## Piony funkcjonalne

| Pion | Rzeczywiste scenariusze |
|---|---|
| Wyszukaj → zaplanuj → zamień → skopiuj | `ux-recipes` + `ux-planning` + `ux-week`; obejmują serwerowe filtry, dalszą stronę, kontekst daty, zapis i atomową zamianę |
| Tydzień → zakres zakupów → podgląd → zapisane listy | `ux-navigation`, `week-template-cycle`, `shopping-generate`, `ux-shopping-home`; jawna spiżarnia i rzeczywiste tury |
| Lista → offline → sieć → jawna spiżarnia | `offline-lista`, `ux-shopping-checklist`, PWA; potwierdzenie synchronizacji i idempotentne przyjęcie |
| Edytor → błąd → niezapisane zmiany | `ux-editor`390/1024;422/403/409, zachowany formularz, widoczny fokus, rzeczywisty zapis i ochrona opuszczania |

To kompozycja utrzymywanych scenariuszy E2E, nie nowy pojedynczy wizard
udający wykonanie wszystkich operacji. Testy używają rzeczywistych API
i własnych danych z dokładnym sprzątaniem albo powtarzalnego fixture UX00.

## Macierz wizualna i dostępność

[Galeria przed/po](../../../backend/data/ux11-results/visual-comparison.html)
zawiera22 pary rzeczywistych obrazów11 ekranów390/1440.
[Manifest](../../../backend/data/ux11-results/visual-comparison-manifest.json)
podaje ścieżki, wymiary i SHA256 44 oryginałów. Baseline `screenshots-before`
pozostał zachowany, łącznie z dawnymi przepełnieniami. Referencja HTML
jest kierunkiem wyglądu; nie służy jako dowód działania.

| Ekran/stany |390/1440 przed/po |360/768/1024 |320 / CSS tekst200% |
|---|---|---|---|
| Dzień: pełny, pusty, częściowy/brak podziału | Rzeczywiste PNG | Macierz final2 | Pełny dzień; etykiety dni i makro |
| Tydzień | Rzeczywiste PNG | Agenda z pełnymi nazwami | Czytelna agenda |
| Przepisy | Rzeczywiste PNG | Katalog i akcje | Filtr i nieucięte Zaplanuj |
| Szczegół przepisu | Zdjęcie, także brak zdjęcia/global | Nazwy i przygotowanie | Kontenerowy układ bez przepełnienia |
| Edytor | Podstawy i rozwinięte dodatki | Rzeczywiste składniki/zdjęcie | Podstawy; osobny naturalny Tab przez dodatki |
| Zakupy | Katalog i konfiguracja tur | Zakres i listy | Opisy/akcje osobno, pełne daty |
| Lista zakupów | Prywatna/publiczna/offline | Zwinięte i rozwinięte sekcje | Czytelne nazwy i checkboxy |
| Spiżarnia | Grid/lista/pilne zapasy | Długie nazwy i formularz | Pełne opcje filtrów |
| Podsumowanie | Luki/niekompletność/historia | Zakres, całe porcje planu | Czytelne wartości; bez oceny osoby |
| Produkty | Biblioteka i formularz | Wszystkie sekcje/miary | Pełne opcje filtrów |
| Ustawienia | Rodzina, osobno3pozostałe sekcje | Wszystkie4sekcje | Profile z akcjami poniżej treści |

Źródła: [165PNG final2](../../../backend/data/ux-baseline/screenshots-ux11-final2)
i [25PNG/metryki acceptance8](../../../backend/data/ux11-results/png-acceptance-8).
Logowanie i administracja mają dodatkowe rzeczywiste obrazy UX10.
Review wymienia dokładnie obejrzane pliki; wygenerowanie165PNG nie oznacza
automatycznie ręcznego obejrzenia każdego z nich.

`ux-acceptance.spec.ts` sprawdza22 główne stany,944 nazwy dostępne kontrolek,
geometrię tekstu/akcji/filtrów/dat oraz naturalny Tab:37 kroków na każdej
z320/390/1024, dotarcie do „Zapisz”,0 zasłoniętych punktów centralnych.
Jedna klatka synchronizuje pomiar po natywnym scrollu i scoped focusin;
nie jest timeoutem ani retry. Powiększenie to CSS root font32px na1024,
**nie natywny zoom**. Punktowy hit-test nie jest dowodem pełnej widoczności
każdego pola ani samodzielnym audytem focus ring/WCAG.

[Pomiar kontrastu](../../../backend/data/ux11-results/contrast-results.json):
35/35 nieprzezroczystych par tokenów spełnia4,5:1 dla zwykłego tekstu lub
3:1 dla granic/fokusu. To pomiar jawnych par sRGB, nie certyfikat całej
dostępności. Duże checkboxy48px i podstawowe akcje44px zachowują wcześniejsze
testy/prymitywy. Natywnych okien systemowego share i gestu DnD nie opisujemy
jako ręcznie wykonanych; alternatywy przyciskowe/klawiaturowe są sprawdzone.

## Ustalenia review i korekty UX11

Niezależne review Sol działa zgodnie z zaakceptowanym D35. Nie deklarujemy
wykonania niedostępnych builtin `/code-review` ani `/security-review`.
Reviewerzy nie są autorami ocenianego kodu.

Zapisy: [kontrakty i domena](reviews/UX11_CONTRACTS.md),
[bezpieczeństwo i kod](reviews/UX11_SECURITY.md),
[kontrola obrazów](reviews/UX11_VISUAL.md) oraz
[ledger końcowej macierzy](reviews/UX11_VISUAL_LEDGER.txt).

- P2 sesji: stare callbacki po invalidation mogły przestawić router nowej
  sesji. `c136ed1` dodał guardy operacji, poprawną obsługę własnych przejść
  login/logout i regresje deferred, w tym rzeczywiste App/SessionBoundary.
- Pierwsze6P2 reflow: szczegół, naturalny fokus, dekoracje, karta przepisu,
  zapisane listy i profile. `77e58a5`; kontrolowane RED oraz acceptance5GREEN,
  osobny review rzeczywistych obrazów.
- Kolejne3grupy: filtry, pasek dni/makro i daty zakupów. `9ec4080` zmienił
  tylko template/CSS pięciu stron; całe scriptblocks porównano jako identyczne.
  Rozszerzony helper odtworzył RED7 na77, następnie GREEN8 na9ec bez zmiany
  asercji. Sam brak przewijania poziomego okazał się niewystarczającym
  kryterium, dlatego dodano pomiary rzeczywistego tekstu i kontrolek.

Czerwone przebiegi1–4/6–7, pośredni GREEN5 oraz wszystkie PNG/JSON zostały
zachowane. Nie są przedstawiane jako końcowy sukces. Końcowy helper SHA256:
`BC7170FFDB05BD326A7A789F2EB91E3F342FC0E24A92CEC709E65884CC9774E2`.
Źródła aplikacji są zgodne z9ec; nowy helper jest oddzielną zmianą O.

## Końcowe bramki

Wszystkie komendy korzystają z lokalnego środowiska aktywowanego przez
`backend/data/ux00-tools/activate.ps1`. Oficjalny Playwright1.62.1 w Linux
zastępuje niestabilny transport Chromium Windows; wersji zależności ani
asercji nie zmieniano. Każdy przebieg ma jednego workera i brak ponowień.

| Komenda / kontrola | Wynik i dowód |
|---|---|
| `task check DB_TEST_RUNTIME=linux` | PASS 675 unit /300 integration /460 API /903 FE (91plików), wszystkie statyki/build/OpenAPI; `check-final-2.log` |
| `task test-e2e-linux` bez filtrów | PASS 47/11 jawnych opt-in SKIP,2,6min; `e2e-final-1.log`, w tym zależny households |
| Opt-in `UX_ACCEPTANCE=1`, chromium/no-deps | PASS 1 / 23,9s; `acceptance-8.log` |
| Opt-in `UX_VISUAL=1`, 5szerokości, chromium/no-deps | PASS 1 / 41,9s; `visual-final-2.log`,165PNG |
| `task test-pwa` | PASS 3 / 18,2s; prawdziwy cold restart prywatny/publiczny oraz izolacjaB; `pwa-final-1.log` |
| `task test-pwa-advanced` | PASS 4 / 1,7min; dwie karty, spóźnione GET, zmiana rodziny i upgrade legacy workera; `pwa-advanced-final-1.log` |
| `task test-shopping-print` i kontrola PDF | PASS 2 (setup + test),9,9s; dwa PDF po 5 stron/50 wierszy, parser i niezależne review wszystkich 10 stron PASS; `print-final-1.log` |
| `task audit`, osobno `task audit-fe` | NIEZIELONE: zastane BE42/3pakiety, FE44 (3low/31moderate/10high); logi UX11 |
| `task secrets-scan` po integracji | Wynik po utworzeniu tego commita: `integration.json` i `secrets-committed.log`; poprzedni skan UX10:140commitów/0wycieków |

Artefakty poleceń znajdują się w `backend/data/ux11-results`.
Testy scope, CSRF i tokenów są rzeczywistymi testami API w pełnej bramce;
review ich kodu nie zastępuje wyniku wykonania.

Przegląd źródłowy, domenowy, kontraktowy, bezpieczeństwa i wizualny Sol
zakończono bez otwartych ustaleń P0–P3 dotyczących programu. Zastane alerty
zależności pozostają jawnie otwarte. Czternaście pochodnych raportów HTML
sprawdzono pod kątem czterech dokładnych lokalnych sekretów i tokenowych URL:
0 dopasowań po redakcji 1 HTML z zachowaniem wyników, załączników i SHA przed/po.
Nie jest to deklaracja uniwersalnego skanowania każdego formatu artefaktu.
Wydruki i zrzuty przedstawiają wyłącznie lokalne dane testowe.

## Kontrakty i rozmiar buildu

UX03 wprowadził wąskie rozszerzenia atomowego utworzenia posiłku z pierwszym
daniem i atomowej zamiany przepisu, z rzeczywistym ID dnia, walidacją scope,
Decimal/stringów i podziału porcji. OpenAPI i wygenerowane typy są zgodne.
Nie zmieniono semantyki dopisującego kopiowania ani sekwencyjnego move
copy→delete. UI odczytuje trwały indeks list i istniejące dane; nie dodano
fikcyjnego stanu ukończenia zakupów ani powiązania konta z profilem po imieniu.

Końcowy build:99 wpisów precache/1237,18 KiB wobec UX00
68 wpisów/947,89 KiB: +289,29 KiB (+30,52%).
[Porównanie logów](../../../backend/data/ux11-results/build-comparison.json):
JS 45→69 plików,657,33→935,74kB; CSS 1→8,32,77→49,74kB;
fonty 7 plików/218,48 kB bez zmiany. Te sumy Vite są zaokrąglone i podane
w dziesiętnych kB, a precache w KiB. Nie dodano zależności, manifesty
i lockfile mają pusty diff wobec b802. Wzrost obejmuje własne panele
planowania/reuse, nawigację i stany UI, izolację/cache/offline/bootstrap
oraz wydzielone chunki/CSS. Nazwy chunków mogą się przemieszczać;
porównanie nie przypisuje każdej różnicy pliku do nowego kodu i nie wymyśla
procentowego progu akceptacji.

## Jawne ograniczenia i odroczenia

- Zastane audyty zależności nie są zielone: backend42wpisy dotyczą3pakietów,
  w tym zduplikowane certifi (41unikalnych par); frontend44, w tym10high.
  Program nie zmienił grafów zależności ani nie wykonał automatycznych upgrade.
  Odbiór UX nie jest zgodą na wdrożenie produkcyjne.
- Move nadal składa się z copy i delete; błąd drugiego kroku może pozostawić
  kopię, co UI wyjaśnia. Duży cykl ma stronicowany podgląd, nie obcięty payload.
- Tydzień w aktualnym AppShell używa agendy, także na desktopie. Nie twierdzimy,
  że przetestowano7kolumn, które wymagałyby84rem dostępnej treści.
- Konfiguracje tur mają progresywny DOM20wierszy, cały cache i ręczne odkrywanie
  pozostałych. To nie wirtualizacja ani ograniczenie historii.
- Zdjęcia zapisują się od razu jako osobna operacja istniejącego przepisu;
  ostrzeżenie niezapisanych zmian nie jest trwałym szkicem/autosave.
- UX12 pozostaje poza zakresem: bilans konkretnej osoby, trwałe zakończenie
  zakupów, osobiste ulubione, trwałe szkice/tryb gotowania i silnik dopasowania
  przepisów do spiżarni. Teksty nie udają istnienia tych funkcji.
- Przegląd obejmuje jawnie wymienione viewporty/stany i Chromium Linux.
  Brak deklaracji native zoom, certyfikacji WCAG, ręcznego dialogu share,
  natywnego focus recovery systemu lub testów wszystkich przeglądarek/urządzeń.

## Lokalne integracje

| Batch | Commit |
|---|---|
| UX00 | `1512a09` |
| UX01 | `90fd42d` |
| UX02 | `fd0b6cc` |
| UX03 | `3cde3c6` |
| UX04 | `9acdf99` |
| UX05 | `964fc71` |
| UX06 | `42e5f1f` |
| UX07 | `4c21455` |
| UX08 | `9921127` |
| UX09 | `ef1e033` |
| UX10 | `1386ee0` |
| UX11 | Ten commit `batch(UX11): odbiór przebudowy i końcowe korekty UX`; pełny hash w `integration.json` |

Bez pushu, deployu, resetu danych użytkownika i importu danych właściciela.
