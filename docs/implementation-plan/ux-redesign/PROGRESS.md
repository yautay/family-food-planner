# Postęp przebudowy UX

Stan na 2026-10-30: UX00 (`1512a09`), UX01 (`90fd42d`) i UX02 odebrane oraz integrowane lokalnie. UX02: check590/292/443/481 PASS, dwa kolejne Linux E2E po31PASS, visual100PNG Windows, niezależny review bez otwartych ustaleń. Następna fala UX03 + UX05 z jednej podstawy. Program trwa do UX11, UX12 poza zakresem. Ograniczenia wejściowe: [BASELINE.md](BASELINE.md).

Tylko orkiestrator aktualizuje ten rejestr. Reguły stanów i dowodów: [ORCHESTRATION.md](ORCHESTRATION.md).

| Batch | Stan | Właściciel | Baza/worktree | Dowód i commit integracji |
|---|---|---|---|---|
| UX00 | ZINTEGROWANY | O + Sol fixture/offline + niezależny Sol runtime review | `9c4b066`; O: `F:/repo/family-food-planner`; osobne worktree autorów/reviewera | `1512a09`; 590/292/443/422 check PASS, E2E 20 PASS dwukrotnie, 40 PNG; BASELINE |
| UX01 | ZINTEGROWANY | Sol `ux01_design`; niezależny `ux01_review`; O runtime | `1512a09`; `C:/Users/yauta/.codex/worktrees/ux00-review/family-food-planner`; `codex/ux01-design-system` | `90fd42d`; check590/292/443/449 PASS, fullE2E24/25 PASS, 100PNG + panel/druk, review3P2 zamknięte |
| UX02 | ZINTEGROWANY | Sol `ux02_navigation`, niezależny `ux02_review`, O runtime | `90fd42d`; `C:/Users/yauta/.codex/worktrees/ux00-offline/family-food-planner`; `codex/ux02-navigation` | finalny commit `batch(UX02): uporzadkuj nawigacje i zachowaj kontekst planu`; check590/292/443/481PASS, E2E31PASSdwukrotnie, visual100PNG + menu/print, review3P2 zamknięte |
| UX03 | PLANOWANY | — | — | — |
| UX04 | PLANOWANY | — | — | — |
| UX05 | PLANOWANY | — | — | — |
| UX06 | PLANOWANY | — | — | — |
| UX07 | PLANOWANY | — | — | — |
| UX08 | PLANOWANY | — | — | — |
| UX09 | PLANOWANY | — | — | — |
| UX10 | PLANOWANY | — | — | — |
| UX11 | PLANOWANY | — | — | — |
| UX12 | POZA_ZAKRESEM | — | — | nowe zlecenie |

## Rezerwacje

| Zasób | Właściciel | Od kiedy | Zwolnienie |
|---|---|---|---|
| Dokumentacja programu/architektury/skilli i rejestry | O / cały program | 2026-10-30 | po odbiorze UX11 |
| Wspólna DB, check, migracje, seed, E2E, Taskfile i konfiguracja runtime | O / cały program | 2026-10-30 | jedna operacja naraz; po zakończeniu przebiegu |
| AppShell/spec, navigation/spec, router/spec, nowe komponenty nawigacji, texts, smoke/ux-navigation E2E | Sol `ux02_navigation` | 2026-10-30 | kandydat i odbiór UX02, bez samodzielnych DB/E2E |
| Kontekst dat/URL w PlanTygodniaPage i StatystykiPage, ewentualnie minimalnie PlanDniaPage, testy | Sol `ux02_navigation` | 2026-10-30 | wyłącznie kontrakt nawigacji; przebudowy stron nadal UX03/07/10 |
| Tokeny/UI/panel, API/OpenAPI/queryKeys, kolejka, lockfile | O do dalszych przydziałów | 2026-10-30 | nie zmieniać w UX02 bez uzgodnienia |

Rezerwacje UX00/UX01 zakończone; hash, własność i przekazania pozostają w dzienniku.

## Decyzje i ograniczenia

- Wygląd: zaakceptowany kierunek „domowa książka kucharska”.
- Uruchomienie: jawna autoryzacja właściciela z 2026-10-29 obejmuje cały program, agenty Sol, worktree i lokalny commit samej dokumentacji przed izolacją. Zastępuje dawną regułę „jeden batch i koniec” tylko dla UX00–UX11; bez pushu, deployu i produkcji.
- Wykonawca UX00 weryfikuje skille review dostępne w docelowej sesji Sol oraz zgodność proponowanej orkiestracji z procedurą repo.
- Historyczny bloker środowiska z 2026-10-29 rozwiązany: Docker/WSL2, lokalne bazy, konto E2E i fixture działają. Szczegóły i dawne czerwone przebiegi zachowane w BASELINE.
- Builtin `/code-review` i `/security-review` są niedostępne; nie deklarujemy ich wykonania. Zastępstwo rozstrzygnięte przez właściciela w D35 poniżej.
- **Rozstrzygnięcie 2026-10-30 / D35:** właściciel jawnie zaakceptował zastąpienie niedostępnych builtin `/code-review` i `/security-review` niezależnym review agentów Sol według architektury i `pasnik-security`, z rzeczywistymi testami scope/CSRF/tokenów i audytem zależności. Dotyczy całego UX00–UX11; nie znosi testów, niezależności autora/reviewera ani kontroli wizualnej. Poprzednia formalna blokada audytu jest rozwiązana; wyniki zawsze nazywamy review Sol.
- Bilans osoby, trwałe zakończenie zakupów, osobiste ulubione, trwałe szkice i dopasowanie spiżarni: UX12. Brak tych funkcji nie może być maskowany tekstami z makiety.

## Dziennik

2026-10-30 — UX02 odebrane na `f617e9e` + sprawdzony patch dokumentacji O. `check-final.log` PASS590/292/443/481, typy/lint/format/build/OpenAPI; PWA75/1098,26KiB. `e2e-final-2.log`31PASS i `e2e-final-3.log`31PASS, po1SKIP tylko opt-in visual wykonanego osobno:100PNG5widths. Rzeczywisty USER/login/role/API403, publiczne obie sesje, fokus/skiplink i oba menu print PASS. O i niezależny Sol reviewer obejrzeli finalne PNG; wszystkie3P2 i gotowość testu zamknięte. Kontrakt selectedDate/from/to i helpery zamrożone w CONTRACTS/arch05 dla UX03/05/07/10. Bez zmiany API, obliczeń, scope ani kolejki. Istniejący overflow i wielostronicowy druk nadal w kolejnych kartach. Jeden finalny commit UX02, potem dwa świeże Sol worktree od wspólnej bazy.

2026-10-30 — UX02 przekazanie: `89b2101`, 478 FE / typy / lint / format / build PASS, 16 plików. O: pierwsze navigation+smoke12PASS, visual1PASS100PNG5widths, PNG dzień/sekcje/publiczne/menu obejrzane również przez niezależnego Sol reviewera. Test USER zmieniony z symulowanej roli na prawdziwe konto i API403 w `7616e73`, bez zmiany konta E2E. Review znalazł 2 P2 dat, naprawione w `3a7e841` z RED3FAIL→GREEN481PASS. O + reviewer wykryli trzeci P2 druku portalu; `f617e9e` dodaje własne print:hidden oraz realne regresje obu menu. Pierwszy full Linux:29PASS/1FAILskiplink/1SKIPvisual/1notrun; trace wykazał Tab wysłany przy pustym app przed montażem SPA. Gotowość testu poprawiona bez focus/sleep/retry. Prawdziwy USER/UIguard/API403 przeszedł. O rozpoczyna pełne E2E→visual5widths→check→drugie E2E, bez innych DB/E2E; źródła zamrożone do końcowego review. Dokumentacja/helpery w niezmiennym patchu O SHA256 `3e317a1e43791b5329879821a9dda87f87c7a06c217c4b009a4b4705f6e739c4`.

2026-10-30 — UX01 zintegrowane w `90fd42d`, czyste drzewo O. UX02 rozpoczęte od tej bazy w świeżym Sol high `ux02_navigation`, własny czysty worktree/nowa gałąź. O przekazał stabilne prymitywy i przydzielił minimalną integrację zakresu w tygodniu/podsumowaniu, ponieważ obecne strony ignorowały część kontekstu URL. API, obliczenia, scope i układy kolejnych kart pozostają poza własnością UX02. Dokumentacja/DB/E2E pod kontrolą O. Worktree review oczyszczono przez dokładne odwrócenie własnego patcha, a następnie porównanie identycznego blobu index.html i odświeżenie indeksu bez diffu; bez resetu/clean. Następna bramka: kandydat UX02, testy, review i kontrola 390/768/1024.

2026-10-30 — UX01 odebrane. Finalny autor `258ebb0` (wcześniej e3ade07/3db3d59/559ecae) + patch O v3 SHA256 `f4ecc4cdbe5ae5fdc87ad3c988b5e36e346c04fedb6675d44daf57b22f639997`. Check PASS 590 unit / 292 integration / 443 API / 449 FE, typy/lint/format/build/OpenAPI. PWA85 wpisów1040,25KiB (UX00 68/947,89); modal Reka i nowe ikony/style, bez nowych pakietów. Windows foundation5PASS i visual100PNG na5szerokościach PASS; kontrola pending/błędu/fokusu/większego tekstu. Dwa full Linux E2E24PASS i25PASS (drugi z drukiem), każdy1SKIP wyłącznie osobno wykonanego visual. Trzy P2 zamknięte kodowo i na PNG przez niezależnego Sol reviewera, zero otwartych ustaleń. CSS druku potwierdzony na realnym PNG, bez deklarowania paginowanego wydruku listy. Artefakty backend/data/ux01-results oraz screenshots-ux01; bez nadpisania screenshots-before. Stabilny test-e2e-linux omija Windows vendor issue bez alpha/zmiany lockfile/flags, te same dane i wyłączność O. Kod i dokumentacja utrwalane jednym finalnym commitem UX01, następnie świeży Sol UX02.

2026-10-30 — UX01 poprawiony kandydat `3db3d59` po trzech P2. Trzecie ustalenie pochodzi z rzeczywistych PNG: nowe przyciski rozciągały się do ~198 px wysokości w starej siatce dnia. Autor dodał `h-fit`, regresję wymiarów/większego tekstu w realnym E2E, rozdzielił API error od live validation oraz zastosował natywne powiązanie formularza przez scoped `formId`. Pięć dialogów tygodnia i AmountInput migrowane kompatybilnie, integracja rzeczywistego RecipePickera bez zewnętrznego submitu. 449 FE / typy / lint / format / build PASS autora. O przeniósł poprawkę i uruchamia pełne E2E; reviewer dostał nowy niezmienny hash oraz patch O SHA256 `23052087eeb68da4b0d650d14ea29c99eba2479833c5bc1a9f63cadafd9b9995`. Pierwszy visual 100 PNG zachowany jako kandydat, nie odbiór.

2026-10-30 — UX01 kandydat `e3ade07`, 22 pliki, autor: 447 FE / typy / lint / format / build PASS. O przeniósł diff bez commita, dołożył metadane PWA i dokumentację. Rzeczywiste smoke/tydzień/nowa klawiatura panelu: 9 E2E PASS. Niezależny `ux01_review` (osobny worktree, niezmienny hash i patch O) znalazł dwa P2: fokus przejmowany przez walidację na żywo oraz kompozycję z formularzem RecipePickera. Autor dostał poprawki i regresje, dodatkową wyłączność na niezbędnych konsumentów `planning/**`. Bez nowych P0/P1; kontrast obliczony niezależnie poprawny. O wstrzymuje długi finalny check do zamknięcia ustaleń; visual rzeczywistych ekranów na 360/390/768/1024/1440 wykonuje oddzielnie.

2026-10-30 — UX01 rozpoczęte od `1512a09`, świeży Sol high `ux01_design`, izolowany istniejący worktree przełączony na nową gałąź po potwierdzeniu czystości. Wyłączna własność tokenów/prymitywów/UI oraz minimalnych konsumentów nagłówka dnia i zastępstwa obrazu RecipeCard. O ma konfigurację PWA, dokumentację i wszystkie DB/E2E. Stary patch review odwrócono dokładnie przez `git apply --reverse` po kontroli SHA/check; worktree review czysty na zatwierdzonej bazie. Bez resetu/clean i bez zmian użytkownika.

2026-10-30 — dodatkowy `task secrets-scan` po finalnym commicie UX00: PASS, 56 commitów / 7,80 MB, zero wycieków (`secrets-ux00-committed-20261030.log`).

2026-10-30 — UX00 odebrane: `check-ux00-accepted-20261030.log` PASS po całym diffie; dwa kolejne pełne E2E 20/20, osobny visual PASS. Niezależny Sol review kodu i PNG bez otwartych ustaleń. Skille repo użyte; zamiennik builtin zgodny z D35. Fixture, guardy, dokumentacja, proxy zdjęć i wąskie naprawy offline utrwalane w jednym finalnym commicie UX00. Wszystkie rezerwacje autorów/reviewera UX00 zwolnione; O zachowuje dokumentację i wyłączną kontrolę DB/E2E dla następnej fali. Alerty zależności jawne, brak pushu/deployu/produkcji. Następna bramka: świeży Sol UX01 na zatwierdzonej bazie.

2026-10-30 — check `check-ux00-final` PASS (3 migrations, 590 unit, 292 integration, 443 API, 422 FE oraz typy/lint/format/build/OpenAPI). Fixture wymagał dwóch korekt starych E2E zależnych od pierwszej strony: wyszukania własnego produktu spiżarni i przejścia przez Pokaż więcej przy weryfikacji. Wszystkie dotychczasowe asercje zachowane, niezależny review bez ustaleń. Kolejny fail przeglądarki dotyczył pobrania modułu bootstrapu (`ERR_NO_BUFFER_SPACE`), przyczyna nieustalona, bez zmiany kodu sieci. Następnie dwa kolejne pełne E2E: `paginated-2` 20 PASS / 1 SKIP i `paginated-3` 20 PASS / 1 SKIP. Opt-in visual wykonany osobno, jego skip w zwykłej suicie jest zamierzony. Końcowy `check-ux00-accepted` po zmianach testów trwa. Niezależny reviewer obejrzał PNG, zamknął wszystkie ustalenia kodu; czeka na finalną bramkę i metadane.

2026-10-30 — oddano fixture `53db15d` i poprawkę `07c29b4` (POST zdjęcia, prawdziwe dane przed screenshotami); O wykonał i ponowił: 318 operacji, 311 ID, complete=true, pending=null, bez duplikacji/resetu. Po ujawnionym braku proxy zdjęć w Vite dodano `/uploads` do tego samego backendu. Visual E2E PASS, 40 PNG 390/1440 zachowane w `backend/data/ux-baseline/screenshots-before`, obejrzane przez O; stare przepełnienia mobilne są dowodem wejściowym do UX02–UX10. Dwa reprodukowalne fail E2E publicznego offline zdiagnozowano deterministycznie: autor `ux00_offline_diagnosis` oddał `9e2c5e3` (pobudka flush) i `d5d7ca6` (atomowe potwierdzenie wersji tego samego klucza), 13 nowych regresji, 422 FE PASS. Reviewer zamknął trzy P2 fixture/kolejki, proxy bez ustaleń; niezależny przegląd PNG trwa. Pierwszy check na nowym systemowym Node26: backend572/292/443 PASS, frontend394/409; Node24.22.1 daje409/409 bez zmiany testów. Końcowy check z nowym fixture i poprawkami oraz dwa pełne E2E w toku. Audit BE42 alerty/3pakiety z ostrzeżeniem uv, FE19(10high), secrets-scanPASS52commity; lockfile bez zmian. UX00 nadal nieodebrane.

2026-10-30 — wznowienie po jawnym poleceniu właściciela. Uzgodniono czyste główne drzewo i worktree na `9c4b066`. Docker Engine 29.9.2 / WSL2 odpowiadają; brak zastanych kontenerów i wolumenów na lokalnym kontekście desktop-linux. Utworzono ignorowany `.env` z losowymi lokalnymi sekretami dla baz `pasnik_ux` i `pasnik_ux_test`; żadnych haseł w raporcie/Git. O uruchamia `task dev-detached`. Świeży Sol `ux00_fixture` w istniejącym osobnym worktree przygotowuje powtarzalne dane i opt-in screenshoty; nie ma prawa do samodzielnych DB/E2E. Właściciel zaakceptował niezależne review Sol zamiast builtin (D35). Następna bramka: migracje/konto, pełne check i E2E, wykonany fixture, rzeczywiste screenshoty i review UX00.

2026-10-29 — niezależny review Sol `ux00_review`, świeży kontekst high, osobny worktree `C:/Users/yauta/.codex/worktrees/ux00-review/family-food-planner` od `511a249`. Sprawdzono niezmienny patch 62289 B, SHA256 `874df2a4797cc39543c30370e03a8c83d9858448a1e120b8ac37662506af6708`, kod źródłowy i lokalne logi. **Brak ustaleń P0–P3.** Reviewer potwierdził ograniczony zakres kontraktów i uczciwy zapis częściowych wyników. Liczby pełnego check pochodzą z transkryptu O, jawnie oddzielone od logów. Review dotyczy dokumentacji, nie uruchomionego UI, i nie wykonuje `/code-review` ani `/security-review`. Po review dopisano wyłącznie metadane tego wyniku. Checkpoint lokalny nie zamyka UX00. Pytanie o dostępne lokalne środowisko przekazano właścicielowi; niezależne prace UX00 zakończone na ten moment, dalsze fale czekają na jego odbiór.

2026-10-29 — przekazanie audytu Sol `ux00_contracts`: baza `511a249`, commit autora `c7e5ead`, tylko `CONTRACTS.md`; mapa 33 obszarów, projektowany panel i atomowe kontrakty UX03 oraz specyfikacja fixture. O przyjął kontrakt i przekazał ustalenie o odpowiedzi dnia po ID do karty UX03. Faktyczne bramki: 3 migrations + 572 unit + 409 Vitest PASS; typy/lint/build/OpenAPI PASS; format PASS po lokalnym CRLF→LF bez diffu kodu. `task check` FAIL: integration 1 passed / 291 errors, brak TEST_DATABASE_URL. E2E z localhost: 1 failed (brak konta), 19 did not run; wcześniejszy URL 127.0.0.1 miał timeout. `task dev-db`: brak docker. `task audit-fe`: 19 zastanych alertów (10 high), bez zmian lockfile. Nie ma runtime fixture ani zrzutów chronionych ekranów. UX00 ZABLOKOWANY, UX01–UX11 nadal PLANOWANE. DB/E2E zwolnione. Dowody i warunek wznowienia: BASELINE.

2026-10-29 — rozpoczęto UX00. HEAD wejściowy `b8020cd`; jedyne zastane zmiany: nieśledzony katalog dokumentacji tego programu. Dokumentację zapisano osobno w `511a249` przed utworzeniem worktree. Gałąź programu: `codex/ux-redesign`. Agent Sol `ux00_contracts` ma osobny worktree i wyłączność na `CONTRACTS.md`. Pierwsze próby `task check` i `task test-e2e` wykazały brak `task`; przenośne task/uv/npm odtworzono lokalnie w ignorowanym `backend/data/ux00-tools`, `task install` zakończył się powodzeniem. Trwa rzeczywisty `task check`; dostępności Dockera/DB nie potwierdzono. Brak builtin `/code-review` i `/security-review` w tej sesji; niezależne review Sol jest jawnie osobnym mechanizmem.

2026-10-29 — przygotowano 12 kart podstawowego programu UX00–UX11, kartę rozszerzeń UX12, specyfikację wyglądu, zasady orkiestracji i prompt. Kod aplikacji niezmieniony. Wyniki testów z wcześniejszych historycznych batchy nie są wynikami tego programu.

## Szablon wpisu po przekazaniu

```text
Data / batch / zadania:
Stan i właściciel:
Baza, worktree, commit/diff:
Spełnione kryteria:
Komendy, wyniki i niewykonane sprawdzenia:
Review i zrzuty ekranów:
Zmiany kontraktów oraz dokumentacji:
Blokery / następne zadanie / zwolnione rezerwacje:
```
