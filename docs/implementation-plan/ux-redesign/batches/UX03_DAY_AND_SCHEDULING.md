# UX03 Plan dnia i wspólne planowanie dania

Priorytet P0 · rozmiar L · zależność UX02 · wykonawca A; może działać równolegle z UX05.

## Cel i kontekst

Dodać lub zamienić danie z czytelną datą, posiłkiem i podziałem porcji. Kontekst: PlanDniaPage, api/planning, ServingsSplitDrawer, `lib/decimal.ts`, moduł planning, architektura 02/04/06/08, ADR-006/008. To jedyna karta podstawowego zakresu planująca rozszerzenie domenowego API.

## Zadania

Ustalenia UX00 do wykorzystania po jego odbiorze: `../CONTRACTS.md` §3–4
zamraża nazwę `RecipePlanningPanel.vue`, XOR `meal_id`/`new_meal_name`
oraz odpowiedź nowego POST `{day, meal_id, item_id}`. Zachować faktyczne
ID i serializować zmieniony dzień po ID; dodać regresję dwóch dni tej samej
daty (własny oraz jawnie edytowany przez ADMIN-a). Obecny `get_day(date)`
po mutacji może wybrać inny dzień. To ustalenie z kodu, do potwierdzenia
testem w tej karcie; bez rozszerzenia scope ani przerabiania silników.

Kontrakt prymitywu z UX01: ActionPanel udostępnia w scoped slotach
`default` i `footer-extra` obiekt `{formId}`. Natywne pola i AmountInput
wiązać `:form="formId"`; nie otaczać pickera kolejnym formularzem.
RecipePicker zachowuje własny formularz create-in-context, który nie może
wysłać zewnętrznej akcji planowania. Walidacja na żywo używa
`validationMessage`, błędy API `error`; wyłącznie te drugie przejmują fokus.

Regresja obowiązkowa częściowego składu rodziny: pozycja 2,2 porcji dla
dwóch profili po 1,1 przy trzech profilach w rodzinie pozostaje 2,2 i dwoma
wpisami po samej zamianie przepisu. Panel nie dopisuje trzeciej osoby przy
otwarciu i nie zwiększa sumy do 3,3. Fixture właśnie tak reprezentuje
„częściowy podział”; API nadal wymaga sumy podziału równej servings, a nie
nieprzypisanej reszty. Bez zmiany porcji PATCH wysyła samo recipe_id;
auto-sumowanie dotyczy jawnej edycji/wyboru rodzinnego trybu. Historyczne
i nieaktywne wpisy nie znikają przy odczycie. To doprecyzowanie zachowania
z CONTRACTS §3–4, bez nowej reguły API ani sposobu obliczeń.

- [ ] UX03.1 Przebudować dzień według makiety: jedzenie przed bilansem, pasek dat, pełne nazwy, akcja w kontekście posiłku. Oddzielić puste dane, błąd pobierania i stare dane w cache.
- [ ] UX03.2 Wyodrębnić współdzielony panel Zaplanuj z propsami: przepis, data, opcjonalny istniejący posiłek i opcjonalna pozycja do zamiany. Wynik po sukcesie zawiera rzeczywisty dzień/posiłek/pozycję; konsument odświeża właściwe klucze cache. UX04 i UX07 korzystają z tego samego komponentu.
- [ ] UX03.3 Automatycznie sumować podział rodzinny przez `sumDecimals`. Pole 0 lub świadome wyłączenie osoby pomija profil w payloadzie; pozostałe wartości dodatnie, suma dodatnia, maksima i dokładność jak w API. Nie wymagać ręcznego dopasowywania osobnej sumy. Obsłużyć użytkownika bez profili i zachować planowanie samą liczbą porcji.
- [ ] UX03.4 Zapewnić transakcyjny zapis nowego posiłku razem z pierwszym daniem. Proponowany addytywny endpoint `POST /plan/days/{date}/recipe-items`: dokładnie istniejący `meal_id` ALBO nazwa nowego posiłku, `recipe_id`, `servings`, `servings_split`. Potwierdzić nazwy w UX00; service reużywa obecne walidacje, zakresy i obliczenia. Nie tworzyć pustego posiłku po błędzie dania.
- [ ] UX03.5 Zapewnić atomową zamianę przepisu przez addytywne `recipe_id` w PATCH istniejącej pozycji typu przepis. Zachować pozycję, posiłek, porcje i podział; odrzucić niedozwoloną konwersję produktu luzem. Błąd pozostawia stare danie. Nie implementować zamiany jako DELETE, a następnie POST.
- [ ] UX03.6 Zachować istniejące operacje produktów luzem, celu posiłku, dopasowania porcji, usuwania i kopiowania; rzadkie działania w menu. Podsumowanie rodzinne nazwać „Cały plan”. Bez pewnej podstawy per osoba nie renderować „Bilans Oli” ani oceny rodzinnej sumy wobec indywidualnego celu.
- [ ] UX03.7 Dla utraconej odpowiedzi po zapisie pokazać stan niepewny i odczytać stan z serwera. Nie ponawiać w ciemno POST ani deklarować gwarancji exactly-once. Zablokować wielokrotne kliknięcia i zachować formularz po błędzie.

## Pliki i rezerwacje

Właściciel: `pages/plan-dnia/PlanDniaPage.vue`, `components/domain/MealCard.vue`, `ServingsSplitDrawer.vue` i testy, nowy komponent planowania przepisu, `api/planning.ts`, testy przepływu planu. Backend: `modules/planning/{schemas,router,service}.py` i powiązane testy. Bez zmiany silników nutrition/shopping.

Wyłączna rezerwacja: `backend/openapi.json`, `frontend/src/api/generated.ts`, niezbędne klucze planu i teksty. Generować przez `task fe-types`; nie edytować typów ręcznie. O przekazuje stabilny kontrakt UX04/UX07. Nie zakładać migracji DB; jeśli okaże się potrzebna, opisać przyczynę i wpływ przed rozszerzeniem zakresu.

## Kryteria odbioru i testy

- Z przepisu można zaplanować istniejący lub nowy posiłek jednym potwierdzeniem formularza; zamiana nie powoduje utraty starego dania przy błędzie.
- `1,1 + 1,1 + 1,1 = 3,3`; zero nie trafia do pozytywnego multiplier; brak profili, częściowy i historyczny podział nie psują ekranu.
- Zakresy prywatny/rodzinny/globalny respektowane. Cudzy posiłek i profil spoza rodziny są odrzucane. Nowe API ma pełną macierz zakresów/rol, CSRF, walidację i test rollbacku transakcji.
- Dane odżywcze nie są arbitralnie przypisywane do osoby. Niekompletne dane są nazwane.
- Vitest: formularz, podział, retry, fokus i cache; backend: kontrakt, scope, atomowość. E2E: dodaj nowy posiłek, zaplanuj, zamień, błąd, odśwież. `task check` po `task fe-types` oraz testy E2E planu.

Skills: Required SKILL-FE, SKILL-BE, SKILL-CALC, SKILL-SEC; Review SKILL-REVIEW, SKILL-SECREV. Aktualizować 02_DOMAIN tylko w zmienionej semantyce, 04_API, 05_FRONTEND, 06_UIUX i następne karty.
