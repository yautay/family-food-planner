# UX00 Przygotowanie przebudowy

Priorytet P0 · rozmiar S · właściciel O · bez zmian zachowania aplikacji.

## Cel i kontekst

Przygotować sprawdzalny punkt odniesienia. Przeczytać README, DESIGN_SPEC, ORCHESTRATION programu, `CLAUDE.md`, historyczny prompt, rejestry postępu i decyzji, architekturę 05/06/08 oraz manifest skilli. Nie wymagać wdrożenia BATCH_18 do lokalnej pracy nad UI.

## Zadania

- [ ] UX00.1 Sprawdzić HEAD, zmiany użytkownika, Taskfile, wersje i działanie lokalnego środowiska. Uruchomić `task check` oraz bazowe `task test-e2e` po sprawdzeniu wskazania bazy. Zapisać rzeczywiste awarie zastane.
- [ ] UX00.2 Zrobić mapę obecnych funkcji i ich nowych miejsc. Uwzględnić produkty luzem, arbitralne posiłki, porcje i ich dopasowanie, tagi i oceny, role, szablony/cykle, historię, sklepy, druk, udostępnianie i kopie danych.
- [ ] UX00.3 Przygotować powtarzalne dane dev/test: pusty plan, rodzina z trzema profilami, plan bez podziału porcji, częściowy podział, zdjęcie/brak zdjęcia, długie polskie nazwy, ponad jedną stronę wyników, lista offline i przepis globalny. Nie importować danych produkcyjnych ani resetować istniejącej bazy użytkownika.
- [ ] UX00.4 Zapisać zrzuty obecnego UI dla dnia, katalogu, przepisu, tygodnia i zakupów na telefonie oraz desktopie. Jeżeli uruchomienie jest zablokowane, jawnie oddzielić dowody z kodu od zrzutów.
- [ ] UX00.5 Przed kodem zamrozić kontrakt wspólnego panelu, zachowanie nawigacji, reguły braku danych i proponowane rozszerzenia UX03. Zanotować odstępstwa makiety opisane w README.
- [ ] UX00.6 Sprawdzić dostępność Required/Review skills. Zarejestrować nowy program, harmonogram i zatwierdzony kierunek w dokumentacji jako plan, bez twierdzenia, że stary wygląd już został zastąpiony. Zmianę dawnej decyzji o braku filtrów czasu ująć jawnie jako planowany filtr „Do 30 minut”, nie przemilczać jej.

## Pliki i wynik

Właściciel: `docs/implementation-plan/ux-redesign/**`; planowane dopiski do `00_MASTER_PLAN.md`, `02_DECISIONS.md` i historycznego `PROGRESS.md` wyłącznie jako indeks nowego programu. Nie odhaczać starych batchy. Dane testowe i zrzuty trafiają do wydzielonej lokalizacji testowej; rozszerzenie seedu tylko jeśli potrzebne i bez ingerencji w dane użytkownika.

Wynik: `BASELINE.md`, mapa zachowanych funkcji, lista kontraktów i mapa własności plików. Nowy numer decyzji dobiera się z aktualnego rejestru, bez rezerwowania numeru w tym planie.

## Kryteria odbioru

Każda projektowana akcja ma odpowiednik istniejący, zaplanowane rozszerzenie albo jawne odroczenie. Znane są ograniczenia środowiska, testów i audytów. Reviewer potrafi odtworzyć dane i odróżnić awarie zastane od regresji. Następne karty nie wymagają historii tej rozmowy.

## Skills i weryfikacja

Required: manifest i odpowiednie project skills przy zmianie testów/seedów. Review: SKILL-REVIEW; SKILL-SEC/SKILL-SECREV, jeżeli przygotowanie dotknęło mechanizmów dostępu. Zwykły odczyt kodu nie wymaga rozszerzania zakresu o audyt produkcji.

Notatki końcowe: wykonane zadania, baza, wyniki komend, zakres danych testowych, odstępstwa, dostępność skilli, kontrakty gotowe dla UX01.
