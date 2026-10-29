# Prompt startowy dla orkiestratora Sol

Ten tekst jest przygotowany do przyszłego uruchomienia. Samo zapisanie go nie jest poleceniem rozpoczęcia implementacji. Wklej go do sesji z wybranym modelem Sol dopiero wtedy, gdy chcesz rozpocząć przebudowę.

```text
Rozpocznij wykonanie programu przebudowy UX Paśnika opisanego w:
docs/implementation-plan/ux-redesign/README.md

Działaj jako orkiestrator. Autoryzuję implementację zakresu UX00–UX11
oraz delegowanie zadań agentom Sol zgodnie z ORCHESTRATION.md.
UX12 jest poza zleceniem. Nie wykonuj pushu ani deployu.

Najpierw przeczytaj:
1. CLAUDE.md i docs/implementation-plan/implementation_prompt.md;
2. ux-redesign/README.md, DESIGN_SPEC.md, ORCHESTRATION.md i PROGRESS.md;
3. kartę UX00 oraz wymagane w niej konteksty;
4. aktualne historyczne PROGRESS.md, 02_DECISIONS.md i 03_AI_SKILLS.md.

Potwierdź faktyczny HEAD i stan zmian użytkownika. Nie usuwaj ani nie
nadpisuj cudzej pracy. Nie zaczynaj od ponownego projektowania aplikacji.
Kierunek wizualny „domowa książka kucharska” jest zaakceptowany.
Makieta jest referencją wyglądu, nie kodem produkcyjnym ani źródłem danych.

Wykonuj kolejno fale z ORCHESTRATION.md. Uruchamiaj maksymalnie trzech
agentów roboczych; każdy ma jedną kartę, określone pliki, bazowy commit,
osobny worktree oraz kryteria odbioru. Wszyscy używają Sol wybranego dla
sesji. Nie twórz osobnych chatów użytkownika ani automatyzacji.
Jeśli narzędzia delegowania albo izolacji nie są dostępne, realizuj ten
sam plan sekwencyjnie i odnotuj zmianę sposobu wykonania.

Zachowaj reguły repo: Vue, TanStack Query, Decimal/stringi, zakresy danych,
sesje, CSRF, paginację i obecną kolejkę offline. Stare adresy mają działać.
Nie dodawaj nowego frameworka ani backendu dla samego wyglądu.
UX03 dopuszcza tylko opisane rozszerzenia kontraktu planowania.

Nie przedstawiaj wartości całego planu jako bilansu konkretnej osoby.
Nie udawaj trwałego zakończenia zakupów, osobistych ulubionych, szkiców
ani dopasowywania przepisów do spiżarni bez odpowiedniego kontraktu.
Nie pokazuj fikcyjnego sukcesu po lokalnej zmianie widoku.

Tylko jeden właściciel edytuje w danej chwili wspólny plik.
Testy korzystające ze wspólnej bazy i E2E uruchamiaj sekwencyjnie.
Przed integracją każdego batcha wymagaj testów z karty, task check,
niezależnego review i dokumentacji. Zachowaj formalne wymagania skilli
z manifestu; nie deklaruj użycia niedostępnego narzędzia.

Aktualizuj ux-redesign/PROGRESS.md po każdym przekazaniu i integracji.
Raportuj krótko: co gotowe, co trwa, bloker i następna bramka.
Kontynuuj autoryzowane, niezależne prace bez pytań o rutynowe szczegóły.
Pytaj tylko o realną decyzję spoza zakresu lub wymagany wyjątek.

Nie kończ po samym szkielecie, nowych kolorach ani uruchomieniu builda.
Zakończ po odbiorze UX11 albo opisz konkretny nierozwiązywalny bloker
wraz z wykonanym zakresem. Wynik końcowy: zmiany, dowody wizualne,
rzeczywiste wyniki testów, lokalne commity i jawne ograniczenia.
```

Wznowienie przerwanego programu:

```text
Kontynuuj autoryzowane UX00–UX11 według ux-redesign/PROGRESS.md i
ORCHESTRATION.md. Najpierw uzgodnij zapisany postęp z rzeczywistym stanem
repo, worktree i agentów. Nie restartuj ukończonych kart i nie rozszerzaj
zakresu o UX12. Zachowaj model Sol i zakaz pushu oraz deployu.
```
