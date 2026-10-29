# Specyfikacja kierunku domowa książka kucharska

Właściciel zaakceptował wygląd nowej makiety 2026-10-29. Kierunek jest ciepły, jasny, kulinarny i oszczędny w ozdobach. Implementacja ma odtworzyć hierarchię, odstępy i charakter, a nie tylko podmienić kolor przycisków.

## Referencja

Źródłowa makieta: [references/domowa-kuchnia.html](references/domowa-kuchnia.html). To fragment do podglądu w środowisku visualize, nie gotowy ekran Vue ani strona produkcyjna. Zawiera 11 ekranów, wybór telefonu/komputera i rekonstrukcję starego interfejsu. Wariant „Przed” jest rekonstrukcją z kodu, nie zrzutem działającej aplikacji.

Nie kopiować danych przykładowych, logiki liczbowej JS, stanów formularzy, komunikatów sukcesu ani uprawnień z makiety. Szczególnie nie kopiować nazw użytkowników, stałych dat i wartości odżywczych. Każdy wykonawca czyta tylko fragment odnoszący się do jego ekranu; kontrakt domenowy wynika z kodu i kart.

## Tokeny i typografia

Wartości niżej są punktem startowym z zaakceptowanej makiety. W aplikacji występują wyłącznie jako nazwane tokeny w `frontend/src/assets/tailwind.css`, nigdy jako hex rozsiany w komponentach.

| Rola | Wartość odniesienia |
|---|---|
| Tło | `#faf7ef` |
| Powierzchnia | `#fffdf8` |
| Tekst główny | `#293c2c` |
| Tekst pomocniczy | `#687061` |
| Linie podziału | `#e3e4d6` |
| Jasne podkreślenie | `#eef0e2` |
| Akcja główna | `#365e43` z jasnym tekstem |
| Dekoracja terakotowa | `#a75e43` |
| Dekoracja miodowa | `#a37a28` |
| Tło nawigacji | `#f3f1e6` |

Nagłówki strony i znak słowny: Georgia z systemowym serif fallbackiem. Pola, listy, liczby, przyciski i treść: obecny Inter. Nagłówki około 32 px na telefonie i 37–38 px na dużym ekranie; nazwy dań około 18 px, treść 14–16 px. Teksty pomocnicze nie mniej niż 12 px. Nie przenosić szeryfu do całych formularzy i tabel.

Skala odstępów: 4/8/12/16/24/32 px. Zwykłe przyciski mają mniejszy promień niż karty. Zaokrąglenie kart 16–24 px, miejscami jeden spokojnie ścięty róg. Zaokrąglone tła nie otaczają każdego wiersza ani każdego akapitu.

Kontrast tekstu i aktywnych kontrolek sprawdzić na rzeczywistych tokenach i stanach. Cel projektowy: 4,5:1 dla zwykłego tekstu, 3:1 dla dużego tekstu i istotnych granic kontrolek. Kolory dekoracji nie są automatycznie kolorami komunikatów błędu lub ostrzeżenia.

## System ozdób

- Motywy: talerz, zioła, kłos, garnek, proste produkty. Korzystać z już zainstalowanego Lucide oraz prostych powierzchni CSS. Bez nowej biblioteki ikon i bez zewnętrznych żądań o obrazki.
- Większy motyw występuje przy nagłówku dnia, tygodnia, katalogu, przepisu i spiżarni. Nie pojawia się w każdym wierszu.
- Kuchenną kratkę stosować na brzegu tła nagłówka albo niewielkim fragmencie ilustracji. Nie umieszczać wzoru za tekstem i polami.
- Na wąskim telefonie znika duży motyw talerza. Pozostają typografia, delikatne tło i mała kratka przy krawędzi.
- Karta przepisu ze zdjęciem pokazuje rzeczywiste zdjęcie. Bez zdjęcia otrzymuje pastelową ilustrację; nie wielką pierwszą literę nazwy. Ilustracja nie udaje fotografii konkretnego dania.
- Lista w sklepie, błędy, podsumowania liczbowe, logowanie i administracja mają minimalną liczbę ozdób.
- Dekoracje: `aria-hidden`, bez fokusu, bez przechwytywania kliknięć, bez zapętlonych animacji. Druk bez dekoracji. Aktywne elementy mają inne, jednoznaczne zachowanie.

## Nawigacja i układ

Główne sekcje: Plan, Przepisy, Zakupy, Spiżarnia. Plan zawiera Dzień, Tydzień, Podsumowanie. Biblioteka produktów i Dom i ustawienia są pomocnicze. Administracja jest widoczna tylko dla ADMIN-a. Na telefonie ustawienia są dostępne przez przycisk konta w nagłówku.

Zachować obecne adresy i nazwy tras, o ile zmiana nie jest konieczna. Zgrupowanie widoków nie wymaga przepisywania wszystkich URL-i. Aktywna sekcja obejmuje też szczegóły i edytory. Link publiczny `/l/:token` nadal działa bez sesji i bez rodzinnej nawigacji.

O szerokości tygodnia decyduje dostępna przestrzeń po uwzględnieniu nawigacji. Siedem kolumn tylko wtedy, gdy mieści się pełna nazwa i sterowanie. W przeciwnym razie agenda. Żadnego ściskania siedmiu kolumn pod sidebar 256 px.

## Stany i interakcje

Każdy nowy widok określa: pierwsze ładowanie, puste dane, brak wyników filtra, błąd bez cache, błąd odświeżenia z cache, mutację w toku oraz sukces. Brak planu nie może przykrywać błędu pobierania. Błąd kolejnej strony nie usuwa pobranych wyników.

Jedna dominująca akcja na obszar. Rzadkie działania mogą być w menu albo rozwinięciu, ale są dostępne także dotykiem i klawiaturą. Dane formularza zostają po błędzie. Po poprawnym zapisie użytkownik otrzymuje potwierdzenie rzeczywistej operacji.

Wspólny panel akcji pokazuje datę, posiłek i danie. Na desktopie może być drawerem; na telefonie reflow w dostępny dialog. Ograniczenie przewijania nie może odcinać formularza. Escape, zamknięcie, kolejność fokusu, powrót do wywołującego i błędy są sprawdzane. Obecne `PlanningDialog` jest panelem `role=group`: zmiana na modal wymaga pełnej obsługi dostępności, nie samego dopisania `aria-modal`.

Checkbox listy zakupów pozostaje wygodny dotykowo, w przybliżeniu 48 px obszaru trafienia; pozostałe podstawowe akcje co najmniej 44 px. Nazwy produktów zawijają się. Operacje nie wymagają gestu przeciągania: dostępna jest alternatywa przyciskowa.

## Co zachować mimo uproszczenia ekranu

Rozkład rodzinny, produkty luzem w posiłku, dowolne nazwy posiłków, ustawienia celu i dopasowanie porcji, kopiowanie dopisujące, szablony, cykle, historia operacji, skale porcji, jednostki domowe, produkty sklepowe, sklepy i ich kolejność kategorii, tagi, oceny, zakresy przepisów, zdjęcia, kopie danych, druk i udostępnianie.

Zachować paginację całego katalogu oraz rozróżnienie planu i faktycznego spożycia. Ozdoby nie mogą sugerować diagnozy zdrowotnej ani kompletności brakujących danych.
