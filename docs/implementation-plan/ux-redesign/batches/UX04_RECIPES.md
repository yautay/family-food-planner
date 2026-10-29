# UX04 Katalog i szczegóły przepisu

Priorytet P0 · rozmiar M · zależność UX03 · równolegle z UX06 po integracji UX03/UX05.

## Cel

Użytkownik znajduje przepis, odczytuje go i planuje bez wchodzenia do edycji. Kontekst: strony przepisów, RecipeCard, api/recipes, paginacja, ADR-006 aneks i reguły zdjęć.

## Zadania

- [ ] UX04.1 Wprowadzić nowe karty ze zdjęciem lub ilustracją zastępczą, pełniejszą nazwą, czasem i porcją. Działania Zaplanuj i Przepis mają czytelne etykiety.
- [ ] UX04.2 Zachować serwerową paginację, scope i tagi. Dodać uzgodniony filtr „Do 30 minut” przez istniejące `prep_time_max`. Filtry i wyszukiwanie zapisać w URL, a powrót z przepisu przywraca wyniki i pozycję. Brak nowych filtrów trudności/oceny w tej karcie.
- [ ] UX04.3 W szczególe pokazać tytuł, metadane, główne Zaplanuj, skalowanie porcji oraz składniki/przygotowanie równocześnie. Na telefonie układ pionowy. Zdjęcie istniejącego przepisu nadal dostępne.
- [ ] UX04.4 Zintegrować panel UX03 z kartą i szczegółem. Przenieść rzeczywisty identyfikator przepisu oraz wybraną datę; sukces prowadzi do właściwego dnia.
- [ ] UX04.5 Zachować ocenę, zakres i role działań Kopiuj/Edytuj/Archiwizuj/Usuń. Serce oznacza obecny tag „ulubione”. Nie zmieniać nieedytowalnego przepisu globalnego ani nie obiecywać osobistej zakładki. Edycja tagu pozostaje w uprawnionym edytorze; osobiste ulubione w UX12.

## Pliki

`pages/przepisy/PrzepisyPage.vue`, `PrzepisSzczegolPage.vue`, `components/domain/RecipeCard.vue`, ich testy; ewentualny stan UI katalogu. Nie edytować `PrzepisEdytorPage.vue` poza uzgodnionym drobnym kontraktem powrotu. Nie kopiować odpowiedzi serwera do Pinia. Zmiany wspólnych tekstów/kluczy przez O.

## Kryteria i testy

Ponad jedna strona wyników nadal jest osiągalna; filtr nie obejmuje jedynie pobranej strony. Wróć zachowuje zapytanie. Nazwa 80 znaków, brak zdjęcia i błędne zdjęcie nie rozwalają karty. Zakres globalny jest czytelny, a nieedytowalny przepis można nadal zaplanować, jeśli zezwala serwer. Składniki i wartości zmieniają się zgodnie z rzeczywistymi porcjami.

Vitest katalogu, szczegółu i kart; E2E przepisy → plan, powrót do filtra, paginacja i `recipe-global.spec.ts`. `task check`, wizualny odbiór desktop/mobile. Bez trybu gotowania i nowego modelu ulubionych.

Skills: Required SKILL-FE, SKILL-CALC przy skalowaniu, SKILL-SEC przy widoczności działań; Review SKILL-REVIEW, SKILL-SECREV gdy zmieniona powierzchnia scope/zdjęć. Dokumentacja: 06_UIUX, filtry i świadome ograniczenia.
