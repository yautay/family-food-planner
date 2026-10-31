# UX04 Katalog i szczegóły przepisu

Priorytet P0 · rozmiar M · zależność UX03 · równolegle z UX06 po integracji UX03/UX05.

## Cel

Użytkownik znajduje przepis, odczytuje go i planuje bez wchodzenia do edycji. Kontekst: strony przepisów, RecipeCard, api/recipes, paginacja, ADR-006 aneks i reguły zdjęć.

## Zadania

- [x] UX04.1 Wprowadzić nowe karty ze zdjęciem lub ilustracją zastępczą, pełniejszą nazwą, czasem i porcją. Działania Zaplanuj i Przepis mają czytelne etykiety.
- [x] UX04.2 Zachować serwerową paginację, scope i tagi. Dodać uzgodniony filtr „Do 30 minut” przez istniejące `prep_time_max`. Filtry i wyszukiwanie zapisać w URL, a powrót z przepisu przywraca wyniki i pozycję. Brak nowych filtrów trudności/oceny w tej karcie.
- [x] UX04.3 W szczególe pokazać tytuł, metadane, główne Zaplanuj, skalowanie porcji oraz składniki/przygotowanie równocześnie. Na telefonie układ pionowy. Zdjęcie istniejącego przepisu nadal dostępne.
- [x] UX04.4 Zintegrować panel UX03 z kartą i szczegółem. Przenieść rzeczywisty identyfikator przepisu oraz wybraną datę; sukces prowadzi do właściwego dnia.
- [x] UX04.5 Zachować ocenę, zakres i role działań Kopiuj/Edytuj/Archiwizuj/Usuń. Serce oznacza obecny tag „ulubione”. Nie zmieniać nieedytowalnego przepisu globalnego ani nie obiecywać osobistej zakładki. Edycja tagu pozostaje w uprawnionym edytorze; osobiste ulubione w UX12.

## Pliki

`pages/przepisy/PrzepisyPage.vue`, `PrzepisSzczegolPage.vue`, `components/domain/RecipeCard.vue`, ich testy; ewentualny stan UI katalogu. Nie edytować `PrzepisEdytorPage.vue` poza uzgodnionym drobnym kontraktem powrotu. Nie kopiować odpowiedzi serwera do Pinia. Zmiany wspólnych tekstów/kluczy przez O.

## Kryteria i testy

Ponad jedna strona wyników nadal jest osiągalna; filtr nie obejmuje jedynie pobranej strony. Wróć zachowuje zapytanie. Nazwa 80 znaków, brak zdjęcia i błędne zdjęcie nie rozwalają karty. Zakres globalny jest czytelny, a nieedytowalny przepis można nadal zaplanować, jeśli zezwala serwer. Składniki i wartości zmieniają się zgodnie z rzeczywistymi porcjami.

Vitest katalogu, szczegółu i kart; E2E przepisy → plan, powrót do filtra, paginacja i `recipe-global.spec.ts`. `task check`, wizualny odbiór desktop/mobile. Bez trybu gotowania i nowego modelu ulubionych.

Skills: Required SKILL-FE, SKILL-CALC przy skalowaniu, SKILL-SEC przy widoczności działań; Review SKILL-REVIEW, SKILL-SECREV gdy zmieniona powierzchnia scope/zdjęć. Dokumentacja: 06_UIUX, filtry i świadome ograniczenia.

## Odbiór wykonania — 2026-10-31

Autor Sol: b530c9c + 56307a8 + afee1a0; O dodał przekazywanie kontekstu
Plan→Przepisy i bridge starych E2E. Niezależny review Sol zgodny z D35
zamknął P2 powrotu z edytora oraz P2 hierarchii katalogu po rzeczywistych PNG.
Bez zmian API, backendu, queryKeys, silnika obliczeń i panelu UX03.

Finalny `task check DB_TEST_RUNTIME=linux`: 639 unit, 300 integration,
460 API i 597 FE PASS, typy/lint/format/build/OpenAPI PASS. Pełny Linux E2E:
41 PASS, 4 SKIP (trzy opt-in PWA należą do trwającego UX06; visual wykonany
osobno). Targeted nowego katalogu i global-role: 8 PASS. Osobny visual:
1 PASS, 125 PNG na 360/390/768/1024/1440 oraz cztery PNG panelu filtrów
z dodatnimi asercjami geometrii nad dolną nawigacją. Artefakty: lokalne,
ignorowane `backend/data/ux04-results` i `ux-baseline/screenshots-ux04`.
Baseline „before” zachowano. Nieudane przebiegi i ich przyczyny są w PROGRESS.

Scope/tagi pozostają w dostępnym zwijanym panelu; aktywne ograniczenia są
jawne także po jego zamknięciu. Edytor zachowuje allowlistę query przy obu
wyjściach; kontrakt przekazano UX08. Archiwalny szczegół nadal można planować,
ponieważ zezwala na to obecne API. `used_in` pokazuje nazwy, bez wymyślonej
daty linku. Osobiste ulubione i tryb gotowania nadal poza zakresem (UX12).

Aktualny audyt nie jest zielony: BE 42 raportowane wpisy w 3 pakietach,
FE 44 (10 high), bez zmiany lockfile. Nie wykonano builtin review, pushu,
deployu ani operacji na produkcji. Lokalny commit integracji: PROGRESS.
