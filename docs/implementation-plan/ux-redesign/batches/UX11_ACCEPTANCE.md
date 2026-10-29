# UX11 Odbiór przebudowy

Priorytet P0 jako bramka wydania · rozmiar M · zależność wszystkie UX00–UX10.

## Cel

Potwierdzić, że zaakceptowany wygląd i uproszczone przepływy działają na rzeczywistych danych aplikacji, a wcześniejsze możliwości nie zniknęły. O prowadzi odbiór; niezależny reviewer nie jest autorem ocenianego obszaru.

## Zadania

- [ ] UX11.1 Przejść mapę funkcji z UX00 i wskazać nową lokalizację każdej. Zamknąć brakujące wejścia i ślepe ścieżki.
- [ ] UX11.2 Zweryfikować piony: wyszukaj przepis → zaplanuj → zamień → skopiuj; tydzień → zakres zakupów → podgląd → zapisane listy; lista → offline → powrót sieci → jawne przyjęcie do spiżarni; edycja przepisu z błędem i niezapisanymi zmianami.
- [ ] UX11.3 Zebrać porównania przed/po wszystkich 11 ekranów na 390 i 1440 px oraz kontrolę przełamań 360/768/1024 px. Dodatkowo 320 px i powiększenie tekstu. Użyć tych samych powtarzalnych danych. Nie korzystać z przykładowych sukcesów makiety jako dowodu implementacji.
- [ ] UX11.4 Sprawdzić klawiaturę, fokus, etykiety, kontrast, dotyk, długie nazwy, stany puste/błędne/pending, niekompletne dane i brak zdjęć. Sprawdzić publiczną listę i wydruk.
- [ ] UX11.5 Wykonać pełne `task check` i `task test-e2e` na zintegrowanym drzewie z wyłączną rezerwacją środowiska. Sprawdzić build PWA/offline. Porównać rozmiar buildu z UX00, wskazać przyczynę istotnego wzrostu zamiast wymyślać procentowy próg.
- [ ] UX11.6 Przejrzeć diff uprawnień, OpenAPI, wygenerowanych typów i wspólnych komponentów. Naprawy wracają do właściwego właściciela; po nich sprawdzić dotknięte przepływy. Nie dodawać UX12 w ramach odbioru.
- [ ] UX11.7 Uzgodnić dokumentację architektury ze stanem faktycznym, przygotować raport odbioru i lokalne commity. Wskazać odroczenia oraz znane ograniczenia.

## Wynik

`ACCEPTANCE_REPORT.md`: macierz ekran/viewport/stan/wynik, scenariusze funkcjonalne, faktyczne komendy i wyniki, dowody wizualne, review, lista zmian kontraktów, pozostałe problemy, commity. Zrzuty przedstawiają UI bez sekretów i produkcyjnych danych.

## Warunki zamknięcia

Wszystkie karty podstawowe ZINTEGROWANE. Brak utraty danych, błędnego zakresu dostępu, niedziałającej głównej akcji, nieprawdziwego potwierdzenia ani blokującej regresji offline. Wygląd zgodny z DESIGN_SPEC, dekoracje ograniczone na telefonie i w zadaniach wymagających skupienia. Wszystkie niewykonane kontrole są jawne; karta nie jest DONE, gdy wymagana bramka pozostaje niewykonana.

Skills: Required project skills zgodnie z dotkniętymi obszarami; Review SKILL-REVIEW i SKILL-SECREV. Produkcyjny deploy, push, reset bazy i import danych właściciela nie są częścią odbioru.
