# UX11 Odbiór przebudowy

Priorytet P0 jako bramka wydania · rozmiar M · zależność wszystkie UX00–UX10.

## Cel

Potwierdzić, że zaakceptowany wygląd i uproszczone przepływy działają na rzeczywistych danych aplikacji, a wcześniejsze możliwości nie zniknęły. O prowadzi odbiór; niezależny reviewer nie jest autorem ocenianego obszaru.

## Zadania

- [x] UX11.1 Przejść mapę funkcji z UX00 i wskazać nową lokalizację każdej. Zamknąć brakujące wejścia i ślepe ścieżki.
- [x] UX11.2 Zweryfikować piony: wyszukaj przepis → zaplanuj → zamień → skopiuj; tydzień → zakres zakupów → podgląd → zapisane listy; lista → offline → powrót sieci → jawne przyjęcie do spiżarni; edycja przepisu z błędem i niezapisanymi zmianami.
- [x] UX11.3 Zebrać porównania przed/po wszystkich 11 ekranów na 390 i 1440 px oraz kontrolę przełamań 360/768/1024 px. Dodatkowo 320 px i powiększenie tekstu. Użyć tych samych powtarzalnych danych. Nie korzystać z przykładowych sukcesów makiety jako dowodu implementacji.
- [x] UX11.4 Sprawdzić klawiaturę, fokus, etykiety, kontrast, dotyk, długie nazwy, stany puste/błędne/pending, niekompletne dane i brak zdjęć. Sprawdzić publiczną listę i wydruk.
- [x] UX11.5 Wykonać pełne `task check` i `task test-e2e` na zintegrowanym drzewie z wyłączną rezerwacją środowiska. Sprawdzić build PWA/offline. Porównać rozmiar buildu z UX00, wskazać przyczynę istotnego wzrostu zamiast wymyślać procentowy próg.
- [x] UX11.6 Przejrzeć diff uprawnień, OpenAPI, wygenerowanych typów i wspólnych komponentów. Naprawy wracają do właściwego właściciela; po nich sprawdzić dotknięte przepływy. Nie dodawać UX12 w ramach odbioru.
- [x] UX11.7 Uzgodnić dokumentację architektury ze stanem faktycznym, przygotować raport odbioru i lokalne commity. Wskazać odroczenia oraz znane ograniczenia.

## Wynik

`ACCEPTANCE_REPORT.md`: macierz ekran/viewport/stan/wynik, scenariusze funkcjonalne, faktyczne komendy i wyniki, dowody wizualne, review, lista zmian kontraktów, pozostałe problemy, commity. Zrzuty przedstawiają UI bez sekretów i produkcyjnych danych.

## Warunki zamknięcia

Wszystkie karty podstawowe ZINTEGROWANE. Brak utraty danych, błędnego zakresu dostępu, niedziałającej głównej akcji, nieprawdziwego potwierdzenia ani blokującej regresji offline. Wygląd zgodny z DESIGN_SPEC, dekoracje ograniczone na telefonie i w zadaniach wymagających skupienia. Wszystkie niewykonane kontrole są jawne; karta nie jest DONE, gdy wymagana bramka pozostaje niewykonana.

Skills: Required project skills zgodnie z dotkniętymi obszarami; Review SKILL-REVIEW i SKILL-SECREV. Produkcyjny deploy, push, reset bazy i import danych właściciela nie są częścią odbioru.

## Odbiór 2026-10-31

Wynik i dokładne granice dowodu: [ACCEPTANCE_REPORT.md](../ACCEPTANCE_REPORT.md).
Mapa34/34 zachowana; niezależne review Sol kodu/domeny/bezpieczeństwa/obrazów
zamknięte zgodnie z D35. Końcowe źródło odpowiada `9ec4080`, helper O ma
SHA256 `BC7170FFDB05BD326A7A789F2EB91E3F342FC0E24A92CEC709E65884CC9774E2`.

- Check2 PASS675 unit /300 integration /460 API /903 FE; wszystkie statyki,
  build i OpenAPI PASS. Pełne E2E47PASS/11jawnych opt-in SKIP.
- Acceptance8 PASS:11ekranów na320 i CSS font200% na1024,944nazwy kontrolek,
  37Tab na każdej z320/390/1024,0zasłoniętych punktów; nie deklarujemy nativezoom.
- Finalvisual2 PASS165PNG, świeży review55głównych PNG +13ostatnich kontroli;
  wszystkie9ustaleń wizualnych P2 zamknięte. Rzeczywiste22pary11ekranów
  przed/po390/1440 i kontrola360/768/1024 zachowane w galerii.
- Zbudowane PWA basic3 i advanced4 PASS, z rzeczywistym offline restart,
  dwiema kartami, zmianą rodziny i upgrade starego workera.
- Print2PASS (setup + test): dwaPDF A4 po5stron i50całych wierszy, parser oraz
  niezależne review wszystkich10stron PASS. Root także obejrzał10stron.
- Build99wpisów/1237,18KiB wobec68/947,89KiB UX00, wzrost opisany; brak nowych
  zależności. Zastane audyty BE42/FE44 nadal niezielone i jawnie odroczone.
- 14 raportów po redakcji1pochodnegoHTML:0dokładnych sekretów/tokenowychURL,
  SHA i wyniki zachowane. Postcommit secrets-scan i pełny hash integracji:
  `backend/data/ux11-results/integration.json`.

Wszystkie czerwone przebiegi pozostają w artefaktach. Jedna lokalna integracja
UX11 obejmuje korekty i odbiór; bez pushu, deployu i danych produkcyjnych.
