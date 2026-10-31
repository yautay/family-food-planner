# Plan przebudowy Paśnika dla Sol

Status: UX00–UX11 odebrane lokalnie 2026-10-31. Wyniki i ograniczenia: [ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md), stan integracji: [PROGRESS.md](PROGRESS.md). UX12 pozostaje poza zakresem. Punkt odniesienia starego kodu: `b8020cd`; dokumentacja dostępna przed izolacją w `511a249`.

Celem jest wdrożenie zaakceptowanego kierunku „domowa książka kucharska” oraz uproszczenie planowania i zakupów. Przebudowa obejmuje 11 projektowanych ekranów, wspólną nawigację, logowanie i dopasowanie administracji. Zachowuje istniejące dane, uprawnienia, obliczenia i działanie zakupów offline.

To osobny program UX. Nie oznacza zakończenia żadnego historycznego batcha i nie uruchamia prac produkcyjnych. Numeracja UX00–UX12 nie zajmuje numerów migracji ani batchy 01–22.

## Jak korzystać z planu

1. Przeczytaj [specyfikację wyglądu i zachowania](DESIGN_SPEC.md).
2. Orkiestrator pracuje według [ORCHESTRATION.md](ORCHESTRATION.md).
3. Zadania wykonawcze są w osobnych kartach `batches/`. Jedna karta to ograniczony zakres dla świeżego kontekstu Sol.
4. [PROGRESS.md](PROGRESS.md) jest jedynym rejestrem wykonania tego programu.
5. [START_PROMPT.md](START_PROMPT.md) zawiera gotowy prompt do uruchomienia po osobnym poleceniu rozpoczęcia implementacji.

## Etapy i kolejność

Priorytety oznaczają kolejność wartości produktowej: P0 — rdzeń i warunki wydania, P1 — dalsze uproszczenia, P2 — rozszerzenia. Rozmiar S/M/L opisuje względny zakres pracy, nie obietnicę czasu.

| Etap | Batch | Wynik | Priorytet | Rozmiar | Zależności |
|---|---|---|---|---|---|
| Przygotowanie | [UX00](batches/UX00_BASELINE.md) | Mapa regresji, działające środowisko, kontrakty i dane do odbioru | P0 | S | stan repo |
| Fundament | [UX01](batches/UX01_DESIGN_SYSTEM.md) | Tokeny, typografia, dekoracje i wspólne stany | P0 | M | UX00 |
| Fundament | [UX02](batches/UX02_NAVIGATION.md) | Cztery główne sekcje i nawigacja mobilna | P0 | M | UX01 |
| Codzienna praca | [UX03](batches/UX03_DAY_AND_SCHEDULING.md) | Plan dnia i wspólny przepływ dodawania oraz zamiany dań | P0 | L | UX02 |
| Codzienna praca | [UX05](batches/UX05_SHOPPING_HOME.md) | Trwały katalog list i prostszy generator zakupów | P0 | M | UX02 |
| Codzienna praca | [UX04](batches/UX04_RECIPES.md) | Katalog i szczegóły przepisu z akcją Zaplanuj | P0 | M | UX03 |
| Codzienna praca | [UX06](batches/UX06_SHOPPING_CHECKLIST.md) | Lista w sklepie, publiczny link, druk i offline | P0 | M | UX05 |
| Planowanie tygodnia | [UX07](batches/UX07_WEEK.md) | Czytelny tydzień, kalendarz kopiowania, szablony i cykle | P1 | M | UX03, UX04, UX05, UX06 |
| Pozostałe ekrany | [UX08](batches/UX08_RECIPE_EDITOR.md) | Krótszy edytor przepisu i ochrona niezapisanych zmian | P1 | M | UX04, UX07 |
| Pozostałe ekrany | [UX09](batches/UX09_PANTRY_AND_PRODUCTS.md) | Spiżarnia i biblioteka produktów | P1 | M | UX06, UX07 |
| Pozostałe ekrany | [UX10](batches/UX10_SETTINGS_AND_SUMMARY.md) | Ustawienia, podsumowanie planu, spójne logowanie i administracja | P1 | M | UX07 |
| Odbiór całości | [UX11](batches/UX11_ACCEPTANCE.md) | Przegląd UX, regresja i dowody odbioru | P0 | M | UX08, UX09, UX10 oraz wszystkie wcześniejsze |
| Rozszerzenia | [UX12](batches/UX12_EXTENSIONS.md) | Osobne karty przyszłych funkcji | P2 | poza wydaniem | nowe zlecenie właściciela |

Pierwszy użyteczny punkt kontrolny: UX00–UX06. Wtedy użytkownik ma nowy wygląd, znajduje zapisane listy i planuje danie z przepisu. Pełna przebudowa jest gotowa dopiero po UX11. UX12 nie blokuje odbioru podstawowego zakresu.

## Co dokładnie zmienia się ekran po ekranie

| Ekran | Wygląd | Zachowanie | Karta |
|---|---|---|---|
| Plan dnia | Nagłówek z motywem talerza, pasek dat, czytelne wiersze dań, mniejszy bilans | Dodaj/Zamień w kontekście posiłku; liczba porcji z podziału rodzinnego; osobny stan błędu | UX03 |
| Plan tygodnia | Agenda na wąskich ekranach, pełna siatka dopiero przy odpowiedniej szerokości | Wybór dat zamiast ręcznego wpisywania; podgląd kopiowania i zastosowania szablonu | UX07 |
| Katalog przepisów | Zdjęcia, jeśli istnieją; ilustracyjne zastępstwo bez zdjęcia; pełniejsze tytuły | Filtry w URL, powrót do wyników, Zaplanuj bez otwierania edytora | UX04 |
| Szczegóły przepisu | Nagłówek książki kucharskiej; składniki i przygotowanie obok siebie lub pionowo | Zaplanuj, przelicz porcje, zachowaj ocenianie i działania wynikające z uprawnień | UX04 |
| Edytor przepisu | Sekcje Nazwa i porcje / Składniki / Przygotowanie / Dodatkowe | Walidacja przy polach, produkt tworzony w kontekście, ostrzeżenie przed utratą zmian | UX08 |
| Zakupy start | Zapisane listy na górze, wyraźna akcja tworzenia, konfiguracja niżej | Odświeżenie nie gubi list; zakres → podgląd → utworzenie | UX05 |
| Lista w sklepie | Długie nazwy, duże pola wyboru, ilości po prawej, minimum ozdób | Natychmiastowe odhaczanie, komunikat synchronizacji, jawne przyjęcie do spiżarni | UX06 |
| Spiżarnia | Zwięzłe wiersze i wyróżnienie produktów do szybkiego zużycia | Filtry i ilości dostępne bez gubienia pozycji na liście | UX09 |
| Podsumowanie | Zakładka Planu, spokojniejsze wykresy i jasna legenda | Zachowanie luk, historycznych celów i informacji o brakach; bez pozornego bilansu osoby | UX10 |
| Produkty | Biblioteka pomocnicza, czytelne sekcje formularza | Dostęp z przepisów i ustawień; zachowane jednostki, warianty sklepowe i ograniczenia zmian | UX09 |
| Ustawienia | Rodzina / Moje cele / Zakupy / Dane | Rozdzielenie osób, dla których gotujemy, od kont mających dostęp | UX10 |

## Różnice między makietą a zakresem wykonania

Makieta określa wygląd i kierunek interakcji. Zawiera przykładowe dane i uproszczone działania. Nie wolno przenosić jej skryptu, przykładowych wartości ani fikcyjnych potwierdzeń do aplikacji.

| Obszar | Ustalenie na podstawie kodu | Sposób realizacji |
|---|---|---|
| Bilans Oli | `DayRead.nutrition` i `goal_progress` dotyczą obecnej agregacji dnia; nie ma jednoznacznego kontraktu bilansu profilu osoby | UX03/UX10 pokazują wyraźnie wartości całego planu. Nie zestawiają rodzinnej sumy z celem Oli. Bilans osoby to osobny kontrakt UX12 |
| Zakończenie zakupów | `ShoppingListStatus` ma `active/expired`, a model nie ma `completed_at`. Wygaśnięcie nie jest ukończeniem | UX05/UX06 używają prawdziwych liczników, zapisanych list i dostępnych stanów. Bez fikcyjnego „Zakończono”. Trwałe zakończenie i archiwum: UX12 |
| Zamiana dania | `ItemUpdateRequest` nie przyjmuje nowego `recipe_id` | UX03 dodaje wąskie, transakcyjne rozszerzenie kontraktu; bez sekwencji usuń → dodaj |
| Nowy posiłek z daniem | `createMeal` i `addItem` to oddzielne wywołania | UX03 przewiduje pojedynczą transakcję dla nowego posiłku wraz z pierwszym daniem |
| Ulubione | Serce oznacza systemowy tag przepisu, nie osobistą zakładkę użytkownika | UX04 zachowuje tę semantykę. Nie pozwala zwykłemu użytkownikowi zmieniać przepisu globalnego przez serce |
| 0 porcji osoby | API oczekuje dodatnich mnożników w przekazanym podziale | UI może pokazać 0 jako „nie je”; zapis pomija taki profil. Suma pozostałych musi być dodatnia |
| Gotowanie krok po kroku i szkice | W makiecie były przykładami rozszerzeń | UX08 zabezpiecza opuszczanie formularza; prawdziwe trwałe szkice i tryb gotowania pozostają w UX12 |
| Przepisy ze spiżarni | W makiecie filtr był przykładem, nie silnikiem dopasowania składników | UX09 nie dodaje przycisku udającego tę funkcję; kontrakt wyszukiwania zostaje w UX12 |

## Stałe wymagania odbioru

- Wszystkie obecne funkcje mają wskazane nowe miejsce; upraszczanie oznacza zmianę hierarchii, a nie ciche usuwanie funkcji.
- Dane serwera pozostają w TanStack Query; obliczenia ilości korzystają z Decimal/stringów i istniejących funkcji.
- Rozdział rodzin, przepisy prywatne i globalne, role, CSRF i publiczny dostęp do samej listy pozostają skuteczne.
- Generowanie zakupów nie odejmuje spiżarni bez jawnej decyzji. Przyjęcie zakupów jest oddzielną, świadomą i idempotentną akcją.
- Zakupy offline zachowują kolejkę, kolejność serwera, odzyskanie po odświeżeniu i reguły konfliktów.
- Rzeczywisty interfejs jest sprawdzony na szerokościach 360, 390, 768, 1024 i 1440 px; przy 320 px oraz powiększeniu tekstu nie traci działań.
- Każdy batch kodu ma prawdziwy wynik `task check`, odpowiednie E2E, przegląd i dokumentację. Brak uruchomionego sprawdzenia nie jest wynikiem pozytywnym.

## Granice zlecenia

Nie zmieniamy frameworka, systemu sesji, silników żywienia i zakupów ani modelu uprawnień. Nie instalujemy platformy do orkiestracji ani API modelu wewnątrz Paśnika. Nie wykonujemy deployu, pushu ani operacji na produkcji. BATCH_18 i historyczne programy pozostają poza zakresem.

Proponowana orkiestracja jest opisana dla Sol dostępnego w środowisku wykonania; nie przełącza modelu tej rozmowy. Wariant roboczy: `gpt-6.1-sol`, jeśli to wybrany przez właściciela wariant Sol. Wszystkie role używają tego samego modelu.
