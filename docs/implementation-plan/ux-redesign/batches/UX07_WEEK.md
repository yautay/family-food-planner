# UX07 Tydzień i ponowne użycie planu

Priorytet P1 · rozmiar M · zależności UX03, UX04, UX05, UX06.

## Cel

Użytkownik widzi dania w tygodniu i wykorzystuje istniejące plany bez ręcznego wpisywania dat. Kontekst: PlanTygodniaPage, `components/domain/planning/**`, api/templates, api/planning, lib/dates, architektura 02/06.

## Zadania

- [ ] UX07.1 Wprowadzić responsywną agendę; siedem kolumn tylko przy odpowiedniej dostępnej szerokości. Pokazywać nazwy dań i stan pustego slotu, nie same inicjały.
- [ ] UX07.2 Reużyć panel UX03 dla dodawania/zamiany i zachować datę/posiłek przy wejściu z tygodnia. Zachować dotychczasowe przenoszenie i obsługę klawiaturą bez wymuszania drag-and-drop.
- [ ] UX07.3 Zastąpić pole wielowierszowe dat kalendarzem wielokrotnego wyboru; pokazać źródło, cele i informację o dopisywaniu. Kopiowanie nie usuwa istniejących posiłków.
- [ ] UX07.4 Uporządkować „Uzupełnij plan”: kopia, blok, szablon i cykl. Przed zapisem pokazać zakres, istniejące dane, rzeczywiste ostrzeżenia oraz wynik. Zachować zapis szablonu i historię ponownego użycia.
- [ ] UX07.5 „Zrób listę zakupów” przekazuje wyświetlany zakres do UX05. Przejście do przepisu i powrót nie resetuje tygodnia.

## Pliki

`pages/tydzien/PlanTygodniaPage.vue`, `components/domain/planning/{BlockCopyDialog,CycleEditorDialog,ReuseHistoryDialog,TemplateApplyDialog,TemplateSaveDialog,PlanningDialog}.vue`, związane testy. UX03 jest właścicielem wspólnego planowania pojedynczego dania; zmiany jego kontraktu przez O. Brak nowych reguł kopiowania i cykli w backendzie.

## Kryteria i testy

Przy 768/1024 px nie występują siedem nieczytelnych kolumn obok sidebaru. Tydzień przechodzący przez koniec miesiąca i roku, wiele dni docelowych, dzień z istniejącymi posiłkami, pusty dzień źródłowy, archiwalny przepis w szablonie oraz błąd API mają poprawny rezultat. Całość działa klawiaturą i na 360 px. Zakresy dat wyliczać istniejącymi funkcjami, z uwzględnieniem lokalnego dnia, nie UTC przesuwającym datę.

`task check`; rozszerzyć `week-template-cycle.spec.ts` i testy paneli o wybór dat, zachowanie istniejących dań i przejście do zakupów. Nie zmieniać testów na sprawdzanie wyłącznie liczby przycisków.

Skills: Required SKILL-FE; SKILL-CALC jeśli ruszane są ilości; Review SKILL-REVIEW. Dokumentacja: responsywny tydzień, nowe wejścia do kopiowania, zachowane semantyki i lista dostępnych operacji.
