# UX12 Rozszerzenia po przebudowie

Priorytet P2 · poza zakresem podstawowego wykonania · nie uruchamiać bez nowego zlecenia. To backlog do rozbicia na osobne karty, nie jeden duży batch implementacyjny.

## Proponowane zadania

| Zadanie | Oczekiwane zachowanie | Kontrakt potrzebny przed kodem | Dowód odbioru |
|---|---|---|---|
| UX12.1 Bilans konkretnej osoby | Wartości i cele faktycznie odnoszą się do tej osoby | Relacja konto–profil, obsługa braku/częściowego podziału, cele historyczne i zakres widoczności | Rodzina z trzema profilami; żaden brak podziału nie jest po cichu rozdzielany; dokładna arytmetyka i macierz dostępu |
| UX12.2 Zakończone zakupy | Trwałe zakończenie, historia i ewentualne ponowne otwarcie | Oddzielny stan od `expires_at`, zakres użytkownik/rodzina, zachowanie przy współdzieleniu i offline, migracja/transfer | Stan trwa po odświeżeniu; kolejka checkboxów nie gubi się; wygaśnięcie linku nie kończy zakupów |
| UX12.3 Osobiste ulubione | Własna zakładka bez edytowania przepisu globalnego | Relacja użytkownik–przepis, endpoint i uprawnienia, transfer danych użytkownika | Dwie osoby mają niezależne ulubione, treść przepisu i tagi nie zmieniają się |
| UX12.4 Trwałe szkice | Odtworzenie niezapisanej edycji po zamknięciu | Miejsce przechowania, konto/rodzina, wersja schematu, zdjęcia, konflikt ze świeższym przepisem, czyszczenie po wylogowaniu | Odtworzenie, odrzucenie i konflikt; brak pokazania szkicu innemu użytkownikowi |
| UX12.5 Przepisy ze spiżarni | Wyniki według faktycznie dostępnych składników | Dopasowanie po ID produktów i ilościach, jednostki, braki, aktualność zapasów, paginacja serwerowa | Zapas częściowy i nieprzeliczalna jednostka nie dają fałszywego „masz wszystko” |
| UX12.6 Tryb gotowania | Rzeczywiste instrukcje wybranego przepisu krok po kroku | Format kroków i migracja istniejącego tekstu, liczba porcji, wznowienie i zachowanie urządzenia | Każdy przepis pokazuje własne kroki; nie zestaw demonstracyjnych instrukcji makaronu |

Każde rozszerzenie otrzymuje własne zależności, pliki, model danych, kryteria, testy i przegląd. Rozszerzenie nie może po cichu redefiniować pojęć „zjedzone”, „zakończone”, „ulubione” czy „zapisane”. Ewentualne migracje numerować dopiero podczas wykonania na podstawie aktualnej głowy.
