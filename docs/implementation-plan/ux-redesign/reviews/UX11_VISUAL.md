> Zapis zawiera historię kolejnych snapshotów. Obowiązują końcowe sekcje na początku: „Końcowy werdykt wizualny na 9ec4080: PASS” i „Końcowy dodatek wydruku A4: PASS”. Historyczne zdania o otwartym odbiorze odnoszą się do wcześniejszych, zachowanych etapów. Finalny review obejmuje zamknięcie 9/9 P2 oraz wszystkie 10 stron PDF; dokładny zakres obrazów jest wymieniony poniżej.
# UX11 — niezależny przegląd wizualny

## Końcowy werdykt wizualny na 9ec4080: PASS

**9/9 znalezionych P2 zamkniętych; 0 otwartych P0/P1/P2/P3.** Werdykt dotyczy faktycznie obejrzanych artefaktów oraz statycznego diffu `9ec4080640ab59c34fc4f1027c6e15e01343d8a8` (bezpośredni rodzic 77e58a5). Oryginalne P2-1–P2-6 pozostają zamknięte na rzeczywistych 25 PNG acceptance-5 i statycznie niezmienionych odpowiednich plikach w 9ec. Ostatnie P2-7–P2-9 zamknięto na NOWYCH kontrolach acceptance-8 i NOWEJ macierzy final2. Ten PASS wizualny nie zastępuje końcowego pełnego gate O.

### Rzeczywiście obejrzane nowe artefakty

`F:/repo/family-food-planner/backend/data/ux-baseline/screenshots-ux11-final2/`: **55 nowych oryginalnych PNG = wszystkie 11 głównych ekranów × 360/390/768/1024/1440**. Każdy obejrzany poprzez native-width top/middle/bottom po 750 px. Dokładny ledger oryginalnych nazw, wymiarów i cropów: `ux11-visual-crops/final2-ledger.txt`; wszystkie 55 pozycji z tego pliku rzeczywiście obejrzano. Cropy `final2-{width}-{name}.png`. To odrębny przegląd final2, nie przepisany wynik 55/90 final1. Pozostałe 35 dodatkowych formularzy/zakładek obejrzanych w final1 pozostaje dowodem historycznym; nie nazywam ich nowymi final2. Nie deklaruję ręcznego obejrzenia wszystkich 165 PNG final2.

Nowy AFTER dla wszystkich 11 porównań UX00 na 390 i 1440 to final2: day-full, week, recipes, recipe-photo, recipe-editor, shopping, shopping-list, pantry, summary, products, settings. W każdym zachowano czytelność długich nazw i rozdzielenie akcji, dekoracja nie nachodzi na nagłówki. W porównaniu z wcześniej obejrzanymi rzeczywistymi BEFORE utrzymano poprawę układu telefonu, spokojną hierarchię i treści wyjaśniające plan/osobę. Wszystkie 5 szerokości mają czytelne zmienione obszary. Na 360 pasek dnia rozkłada się na 6+1, na 390 mieści 7; na 768 makro układają się 3+1. To widoczne, czytelne reflow, bez nakładania etykiet.

`F:/repo/family-food-planner/backend/data/ux11-results/png-acceptance-8/`: osobiście obejrzano **13 nowych oryginałów**: day/recipes/shopping/pantry/products × 320-text1 i 1024-text2 (10), oraz pełne `ux11-editor-keyboard-{320,390,1024}.png` (3). Cropy `acceptance8-{320,1024}-{name}.png` pokazują ciągłe fragmenty po 800 px, pierwsze 4000 px i koniec długich list; x=448..1024 przy powiększeniu, pełne x przy 320. Wszystkie rodzaje zmienionych kontrolek widoczne. Przy powiększeniu filtr kategorii i sort pokazują pełną wybraną wartość, wyszukiwanie ma czytelny początek; katalog ma pełny placeholder i osobny Nowy przepis. Daty dnia zawijają do 4+3; 4 makro mają osobne wiersze; daty Od/Do układają się pionowo i pokazują cały rok z osobną ikoną kalendarza.

Łączny ledger sesji to **282 różne oryginalne ścieżki PNG**: poprzednie 214 + 55 final2 + 13 acceptance-8. Dodatkowe cropy tych samych plików nie zwiększają licznika.

### Zamknięcie ostatnich trzech grup

| P2 | Rzeczywisty dowód po naprawie | Stan |
|---|---|---|
| P2-7 filtry | acceptance-8 320/1024 dla Products, Pantry, Recipes; final2 wszystkie 5 szerokości tych trzech ekranów. Wybrane opcje pełne, obrysy nie nachodzą, search i akcja katalogu mają miejsce. | Zamknięte |
| P2-8 dzień | acceptance-8 day 320/1024; final2 day-full wszystkie 5 szerokości. Etykiety dni i makro nie przecinają się; całe wartości widoczne. | Zamknięte |
| P2-9 daty zakupów | acceptance-8 shopping 320/1024; final2 shopping wszystkie 5 szerokości. Całe daty i kalendarze rozdzielone. | Zamknięte |

Odczytano wszystkie 22 geometry JSON acceptance-8: docfit 22/22, zero layoutProblems. Czytelność: powiększone selecty Products/Pantry mają szerokość 397 px przy potrzebnych 331/313 px; search katalogu 448 przy potrzebnych 376; date inputy po 350 przy potrzebnych 256. Odczytano wszystkie trzy keyboard JSON: 37 kroków każdy, Save osiągnięty, covered=0/0/0, a pełne końcowe PNG pokazują przycisk zapisu. O przekazał acceptance-8 PASS 1/23,9 s i finalvisual2 PASS 1/41,9 s; nie są to testy uruchomione przez reviewera.

Metoda powiększenia to CSS root font 16→32 px, nie natywny zoom. Tab/hit-test centrum jest próbką widoczności, nie dowodem całego focus ring ani pełnym audytem WCAG. Kontrast pozostaje uprzednio odczytanym artefaktem 35 konkretnych par, nie wnioskiem ze screenshotów.

### Statyczny review 9ec4080

Odczytano cały diff wszystkich 5 plików (28 dodanych/22 usunięte linie), potwierdzono bezpośredni parent 77e58a5, czysty worktree i czysty `git diff --check`. Każdy z 5 bloków script porównany z 77 i identyczny. Filtry używają flex-wrap z bazami 18/14/20 rem, dzień intrinsic auto-fit o minimum 3/7 rem, a label daty zakupów basis 16 rem. Minimum ograniczone min(100%,…) lub min-w-0 umożliwia mały viewport; zachowano fonty, tekst, dane, akcje i test-id. Bez nowych ustaleń P0–P3. FE 903/91 oraz statyki/build PASS to wyniki autora/O, nie własne wykonanie.

Reviewer pozostaje niezależny od autorstwa. Brak runtime, bazy, przeglądarki, testów, sieci i zmian źródłowych; zapis tylko ignorowanego raportu/cropów.

## Końcowy dodatek wydruku A4: PASS

Osobiście obejrzano w całości **wszystkie 10 oryginalnych PNG** wyrenderowanych przez O w 90 dpi, po 5 stron wersji prywatnej i publicznej. Źródło: `F:/repo/family-food-planner/backend/data/ux11-results/print-pages-1/`. Dokładny ledger:

| Strona | Obejrzany prywatny PNG | Obejrzany publiczny PNG | Widoczne wiersze w każdej wersji |
|---|---|---|---|
| 1 | shopping-private-a4-1.png | shopping-public-a4-1.png | R03–R19 nieparzyste (9) |
| 2 | shopping-private-a4-2.png | shopping-public-a4-2.png | R21–R41 nieparzyste (11) |
| 3 | shopping-private-a4-3.png | shopping-public-a4-3.png | R43/R45/R47/R49/R01 oraz R02/R04/R06/R08/R10 (10) |
| 4 | shopping-private-a4-4.png | shopping-public-a4-4.png | R12–R32 parzyste (11) |
| 5 | shopping-private-a4-5.png | shopping-public-a4-5.png | R34–R50 parzyste (9) |

W obu wersjach całe długie nazwy wraz z końcami markerów i ilościami pozostają czytelne. Checkboxy, nazwy i prawa kolumna ilości są rozdzielone; poziome linie nie przecinają tekstu. Nie widać clippingu na marginesach, nakładania, przerwania wiersza między stronami ani brakującej końcówki ostatniej pozycji. Dodatkowy tekst „Mam już w domu” przy R01 mieści się w wierszu na stronie 3; nagłówek kategorii Owoce ma pod sobą pierwszą pozycję. Brak nawigacji, przycisków aplikacji, tła interfejsu i dekoracji. Różnica nagłówka/metadanych prywatnego i publicznego wydruku nie ogranicza czytelności. **0 nowych ustaleń P0/P1/P2/P3; 9/9 wcześniejszych P2 pozostaje zamkniętych.**

Odczytano istniejący `F:/repo/family-food-planner/backend/data/ux11-results/print-pdf-verification-1.json`: oba dokumenty mają po 5 stron i 50 wierszy; `a4`, `all_characters_in_page` i `each_row_start_end_same_page` są true; liczby lokalizacji na stronach to 9/11/10/11/9 w obu dokumentach. To odczyt dostarczonego artefaktu, nie samodzielne uruchomienie PDF parsera. Wynik testu print 2 PASS przekazał O; reviewer nie uruchamiał testów, renderera ani runtime.

Po tym dodatku łączny ledger przeglądu obejmuje **292 różne oryginalne ścieżki PNG: wcześniejsze 282 + 10 stron wydruków**. Dodatek nie rozszerza deklaracji pokrycia macierzy final2 poza rzeczywiście obejrzane 55 głównych ekranów.

## Historia przeglądu (wszystkie wcześniejsze ustalenia i czerwone stany zachowane)

## Aktualny skonsolidowany werdykt po final1: DO POPRAWY

Na źródle 77e58a5 + c136: **0 P0, 0 P1, 3 otwarte P2, 0 P3. Oryginalne P2-1–P2-6 zamknięte.** Otwarte są wyłącznie P2-7 (filtry), P2-8 (reflow dnia) i P2-9 (daty zakupów), opisane poniżej. Nie odkładam dalszej części widocznych kontrolek do następnego przebiegu: przegląd 22 stanów acceptance-5 i wybranych 90/165 PNG final1 został zakończony. Odbiór końcowy wymaga rzeczywistych nowych obrazów po poprawkach tych trzech ustaleń.

Źródło nowej zwykłej macierzy: `F:/repo/family-food-planner/backend/data/ux-baseline/screenshots-ux11-final1/`. Obejrzano 11 głównych ekranów na każdej z 360/390/768/1024/1440 (55 PNG), oraz login, product-form, recipe-editor-expanded, settings-data, settings-goals, settings-shopping i shopping-round-settings na każdej z tych szerokości (35 PNG). Razem **90 oryginałów final1**, nie wszystkie 165. Każdy widziany przez bezstratny crop o oryginalnej szerokości: top/middle/bottom po 750 px. Dokładny ledger nazw, wymiarów i pozycji cropów: `ux11-visual-crops/final1-ledger.txt`; wszystkie 90 zapisanych w nim pozycji faktycznie obejrzano. Dodatkowo obejrzano ciągłe cropy y=0/800/1600/2400, 390 i 1024, dla product-form, recipe-editor-expanded, settings-goals, settings-shopping, shopping-round-settings i pantry (`final1-controls-*`).

Przy 390 i 1440 porównanie każdego z 11 ekranów odnosi się teraz do NOWEGO final1 po zmianach PageHeader i wcześniej rzeczywiście obejrzanych BEFORE UX00. W nowej macierzy zwykłej: nagłówki i dekoracje oddzielone; detal składa się pionowo w węższym obszarze; pełne akcje kart i profili; pola zwykłych formularzy czytelne. Zachowane długie nazwy, ciepła paleta, krótka główna akcja w danym obszarze i uczciwa semantyka całego planu. Widoczne na 1024 przycięte wybrane opcje kategorii/sortowania produktów i spiżarni są tym samym P2-7, nie nowym czwartym problemem. Nie stwierdzono innych ustaleń P0–P3 w faktycznie widzianych fragmentach final1.

W acceptance-5 ponownie obejrzano wszystkie 11 stanów 320 przez ciągłe cropy po 800 px (pierwsze 3200 px i końcowe 800 px długich powtarzalnych list) oraz wszystkie 11 stanów powiększonych przez ciągłe cropy obszaru treści x448..1024 (`acceptance5-controls-{nazwa}.png`). Obejmują one wszystkie rodzaje widocznych kontrolek: daty i przełączniki planu, filtry, akcje kart i paginację, porcje, oceny, pola/selektory/textarea edytora, zakres zakupów i checkboxy, akcje pozycji listy oraz profile i zakładki. Przy 320 brak dodatkowego problemu; search katalogu skrócony jest objawem P2-7. Pojedynczy input długiej nazwy ma przewijalną jednowierszową wartość — samo niewidzenie jej całej naraz nie jest osobnym ustaleniem. Przy powiększeniu daty i selecty wymagają natomiast czytelności bieżącej wartości bez ikony na tekście.

Łączny ledger tej sesji: **214 różnych oryginalnych ścieżek PNG** (124 wcześniej + 90 final1). Dodatkowe cropy tych samych plików nie zwiększają liczby oryginałów. Nie uruchamiano aplikacji, testów, bazy ani przeglądarki. CSS root font 16→32 px jest metodą powiększenia tekstu, nie natywnym zoomem. Artefakt klawiatury 37 Tab × 3 szerokości z covered=0 potwierdza próbkę centrum kontrolek, nie pełną certyfikację focus ring/WCAG.

### P2-8 — dzień zachowuje za wiele kolumn przy większym tekście (otwarte)

`F:/repo/family-food-planner/backend/data/ux11-results/png-acceptance-5/ux11-day-1024-text2.png`: w pasku siedmiu dni (y≈1000) napisy nachodzą na sąsiednie komórki i zielone pole aktywnego dnia; w podsumowaniu całego planu (y≈3150) etykieta „Tłuszcze” nakłada się na „Węglowodany”. Dokładny bezstratny dowód: `ux11-visual-crops/acceptance5-controls-day.png`, druga kolumna górna i druga kolumna drugiego rzędu. Obszar głównej treści po sidebarze ma tylko około 448 px, a siatki pozostają 7- i 4-kolumnowe. Źródło w 77e58a5: `frontend/src/pages/plan-dnia/PlanDniaPage.vue:451` (`min-[360px]:grid-cols-7`) i `:777` (`sm:grid-cols-4`). Przy 320 i zwykłych pięciu szerokościach makro pozostają czytelne. Naprawa powinna rozłożyć te dwie grupy zależnie od dostępnej przestrzeni, bez zmniejszania tekstu/utraty etykiet.

### P2-9 — zakres zakupów ucina daty przy większym tekście (otwarte)

`F:/repo/family-food-planner/backend/data/ux11-results/png-acceptance-5/ux11-shopping-1024-text2.png`, y≈2400: kontrolki „Od” i „Do” w dwu kolumnach mają około 162 px każda. Widać jedynie `10/26…` i `11/01…`, rok znika, a ikona kalendarza wchodzi na wartość. Bezstratny dowód: `ux11-visual-crops/acceptance5-controls-shopping.png`, lewa kolumna drugiego rzędu. Źródło w 77e58a5: `frontend/src/pages/zakupy/ZakupyPage.vue:190` (`md:grid-cols-2`), natywne date inputy `:195` i `:205`. Przy 320 pola układają się pionowo i pokazują pełne daty, zwykła macierz także pokazuje daty czytelnie. Potrzebny reflow z minimalną dostępną szerokością daty i jej natywnej ikony.

## Historia przeglądu (poniższe stany zachowane chronologicznie)

## Stan po acceptance-5 — 6 zamkniętych P2, 1 otwarte P2

Oryginalne P2-1–P2-6 zamknięto po rzeczywistej kontroli 25 PNG w `F:/repo/family-food-planner/backend/data/ux11-results/png-acceptance-5/`, na zintegrowanym 77e58a5 + c136. Obejrzano wszystkie 22 stany przez własne bezstratne top/middle/bottom (`ux11-visual-crops/acceptance5-{320,1024}-{nazwa}.png`) oraz 3 pełne końcowe obrazy `ux11-editor-keyboard-{320,390,1024}.png`. Dodatkowo szczegółowy crop przepisu y=2850..4050 potwierdził czytelne nazwy/ilości i Przygotowanie poniżej składników; crop ustawień y=2050..3050 i całe widoczne profile potwierdzają tekst nad akcjami. Katalog ma pełne przyciski Zaplanuj w jednej kolumnie, zapisane listy przycisk pod opisem, a wszystkie sześć ozdobnych nagłówków nie ma motywu na tekście. Łącznie ledger osiągnął 124 różne oryginalne PNG (99 wcześniejszych + 25 acceptance-5).

Odczytane JSON: 22/22 dokumenty mieszczą viewport, 944 sprawdzonych nazw dostępnych, zero zgłoszonych layoutProblems; 37 naturalnych kroków Tab na każdej z 320/390/1024, wszystkie docierają do Save, covered=0/0/0 zamiast wcześniejszych 12/10/13. Obejrzenie końcowych PNG potwierdza widoczny przycisk zapisu. Jest to próbka widoczności centralnego punktu i widocznego UI, nie pełna certyfikacja widoczności całego focus ring ani WCAG. Metoda nadal powiększa CSS root font do 32 px, nie używa natywnego zoomu. Wynik rzeczywistego harnessu przekazany przez O: acceptance-5 1 PASS / 23,1 s, wcześniejszy acceptance-4 RED na źródle przed poprawką; ten reviewer nie uruchamiał runtime.

### P2-7 — wiersze filtrów nie reflowują przy większym tekście (otwarte)

Samo docfit oraz sprawdzona nazwa dostępna nie wykrywają utraty widocznej treści kontrolki. `ux11-products-1024-text2.png` w acceptance-5 przy y≈730 pokazuje pole wyszukiwania i select kategorii zwężone do około 50 px: ich obrysy nachodzą na siebie, wartość/placeholder pozostają niewidoczne obok „Pokaż archiwalne”. `ux11-pantry-1024-text2.png` przy y≈1320 pokazuje selecty kategorii/sortowania szerokości około 76 px, gdzie z bieżącego opisu widać jedynie fragment pierwszej litery i strzałkę. W katalogu przepisów search jest zwężony przez sąsiedni Nowy przepis do około 150 px z ikoną i jedną literą. Czytelne własne cropy: `acceptance5-products-detail-y650.png` (y650..1900), `acceptance5-pantry-detail-y800.png` (y800..2300); katalog widoczny w top-cropie.

Źródła w kandydacie 77e58a5: `frontend/src/pages/produkty/ProduktyPage.vue:154` i `frontend/src/pages/spizarnia/SpizarniaPage.vue:312` wymuszają kilka kolumn przez `lg:grid-cols` według viewportu, mimo wąskiej przestrzeni po sidebarze/paddingach; `frontend/src/pages/przepisy/PrzepisyPage.vue:119` utrzymuje search i akcję w jednym niezawijanym flex. O potwierdził jeden wspólny P2 czytelności filtrów i przekazał wąską korektę trzech szablonów. Brak nowych P0/P1/P3. Końcowy odbiór pozostaje otwarty; trwa skonsolidowana kontrola formularzy i nowej macierzy pięciu szerokości.

## Aktualizacja formalnego UX11 — acceptance-2

O potwierdził formalną bazę `1386ee0771ee2255a10a3d1775d2c9ef96f2ebe7` ze źródłami identycznymi z wejściowym snapshotem. Późniejszy session-effects fix `c136` został osobno odebrany i według przekazania nie zmienia szablonów/CSS. Własny worktree review pozostał bez zmian źródeł.

**Bieżący werdykt: DO POPRAWY — 6 otwartych P2, 0 P0/P1/P3.** Poniższy przygotowawczy PASS pozostaje historycznym wynikiem macierzy bez powiększenia. Nowe kontrole wykryły problemy, których samo dopasowanie szerokości dokumentu nie ujawnia.

Dowody: `F:/repo/family-food-planner/backend/data/ux11-results/png-acceptance-2/`. Obejrzano wszystkie 22 pliki `ux11-{day,week,recipes,recipe,editor,shopping,list,pantry,summary,products,settings}-{320-text1,1024-text2}.png` poprzez natywne top/middle/bottom po 800 px. Cropy własne: `ux11-visual-crops/acceptance2-{320,1024}-{nazwa}.png`, y=0, max(0,(H−800)//2), max(0,H−800). Dodatkowo bezpośrednio obejrzano `ux11-recipe-1024-text2.png`, `ux11-obscured-320-3.png` i `ux11-obscured-1024-18.png`. Łączny ledger tej sesji obejmuje teraz 99 różnych oryginalnych PNG: poprzednie 75 plus 22 stany i 2 osobne viewporty fokusu.

To powiększenie CSS głównego fontu 16→32 px przy viewport 1024, nie natywny zoom przeglądarki. Odczytano wszystkie 22 geometry JSON oraz keyboard JSON dla 320/390/1024. Wszystkie 11 dokumentów 320 ma szerokość 320; przy powiększeniu detal przepisu ma 1036 zamiast 1024. Inne dokumenty mają 1024, lecz część zawartości jest zasłonięta albo ucięta wewnątrz. Geometria listy zgłasza elementy zwiniętego `store-picker`; z tych wpisów nie wyprowadzam błędu widocznego UI.

### P2-1 — szczegół przepisu nie reflowuje przy większym tekście

`ux11-recipe-1024-text2.png`: dwie kolumny zostają w wąskiej przestrzeni po sidebarze. Nazwy składników mają około 50 px i rozpadają się na krótkie fragmenty; nagłówek „Przygotowanie” przechodzi poza viewport. JSON potwierdza dokument 1036 px i prawą granicę nagłówka 1035,65625 przy viewport 1024. Źródło: `frontend/src/pages/przepisy/PrzepisSzczegolPage.vue:418` używa breakpointu viewportu `lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]`, a wiersz składnika `:432` zachowuje nazwę i ilość w dwóch kolumnach. Potrzebny reflow zależny od realnej przestrzeni przy powiększeniu.

### P2-2 — naturalny Tab w edytorze prowadzi za pasek zapisu/nawigację

`ux11-obscured-320-3.png` pokazuje `picker-change` na y=771,30–815,30 w całości za paskiem Zapisz. `ux11-obscured-1024-18.png` pokazuje `ingredient-add` na y=856,44–900,44 zasłonięty dolnym paskiem. Keyboard JSON ma po 37 kroków, dociera do `recipe-submit`, lecz odnotowuje 12/10/13 zasłoniętych punktów centralnych na 320/390/1024. Obejrzane obrazy niezależnie potwierdzają dwie konkretne kolizje. Źródło: `frontend/src/pages/przepisy/PrzepisEdytorPage.vue:1050` sticky save bar; istniejąca obsługa błędnego pola nie zabezpiecza całego naturalnego Tab. Pomiar centrum jest próbką, a nie dowodem pełnej widoczności pozostałych kontrolek ani pełną oceną WCAG.

### P2-3 — wspólna dekoracja nachodzi na większy tekst

`ux11-recipes-1024-text2.png` pokazuje talerz i zioła na napisie „Co ugotujesz?” i opisie. Takie nakładanie występuje też w day/week/recipe/pantry/products, szczególnie na długich nagłówkach i opisach. To widoczny problem mimo dokumentu 1024 px. Źródła: `frontend/src/components/domain/PageHeader.vue:53` oraz `HeaderDecoration.vue:10`, gdzie dekoracja pozostaje widoczna według `sm:block` przy root font 32 px. Potrzebna izolacja lub ukrycie dekoracji przy małej dostępnej przestrzeni.

### P2-4 — katalog ucina główną akcję Zaplanuj przy powiększeniu

`ux11-recipes-1024-text2.png`, dolny crop y=48781: karty pozostają w dwóch kolumnach x≈512–720 i 752–960; zielone przyciski nie mieszczą ikony i napisu „Zaplanuj”, który zostaje ucięty przez granicę karty. Nazwy łamią się również wewnątrz krótkich słów. Źródła: `frontend/src/pages/przepisy/PrzepisyPage.vue:289` (`md:grid-cols-2` według viewportu), `frontend/src/components/domain/RecipeCard.vue:45` (`overflow-hidden`) i `:116` (obszar akcji). Samo docfit nie sprawdza tej utraty treści. Potrzebna jedna kolumna lub inny reflow akcji przy tej przestrzeni.

### P2-5 — zapisane listy nakładają przycisk na opis sklepu

`ux11-shopping-1024-text2.png`, środkowy crop y=1415: przycisk „Otwórz listę” drugiej karty zachodzi na nazwę sklepu i opis. Długi tytuł i szczegóły zostają w bardzo wąskiej kolumnie obok przycisku. Źródło: `frontend/src/pages/zakupy/ShoppingListsCatalog.vue:82` przełącza grid na poziomy flex przez `sm:flex`, a przycisk `:105` jest shrink-0. Przy większym tekście potrzebna kompozycja pionowa zależna od dostępnej szerokości.

### P2-6 — ustawienia zasłaniają opis profilu akcjami

`ux11-settings-1024-text2.png`, środkowy crop y=1936 i dolny y=3873: imiona Łucja/Żaneta rozpadają się do około jednego znaku w wierszu, a Edytuj/Dezaktywuj/Usuń nakładają się na mnożnik i cel. Źródło: `frontend/src/pages/UstawieniaPage.vue:478` wymusza `md:grid-cols-[minmax(0,1fr)_auto]`, mimo bardzo małej szerokości po sidebarze i paddingach; akcje `:499` zajmują szerokość auto. Potrzebne pionowe akcje pod treścią lub kontenerowy próg reflow.

Poza tymi ustaleniami wszystkie pozostałe obejrzane fragmenty 320 i powiększonej macierzy nie ujawniły nowego problemu. To nie deklaracja, że całość 10 powiększonych ekranów jest poprawna wyłącznie dlatego, że dokument mieści 1024 px.

Odczytano także `contrast-results.json`: 35/35 wskazanych nieprzezroczystych semantycznych par spełnia zapisane progi. Jest to wynik artefaktu O dla konkretnych par, nie własny pomiar ze screenshotów ani kompletny audyt dostępności.

Naprawy wymagają ponownych faktycznych kontroli 320/32 px, Tab i zmienionych ekranów. Końcowa macierz 165 obrazów oraz finalny odbiór nadal przed nami. Żadnych źródeł nie zmieniono w tym review.

### Statyczny przegląd poprawki 77e58a5

Odczytano cały niezmienny commit `77e58a545d28a19834b922a1e266103c22c55d6a` w czystym worktree `C:/Users/yauta/.codex/worktrees/ux11-reflow-focus/family-food-planner`. Rodzic potwierdzony osobiście: `c136ed177e115f6d10dc9b432e5754c5bbf50108`. Cały diff obejmuje dokładnie 7 plików, 137 dodanych/16 usuniętych linii. `git diff --check 77e58a5^ 77e58a5` bez uwag. Reviewer nie uruchamiał runtime ani testów; podane przez autora FE 903/91 oraz typy/lint/format/build pozostają wynikami autora.

**Ocena statyczna: wszystkie 6 P2 otrzymało adekwatną poprawkę źródłową; brak nowych ustaleń P0–P3 w tym diffie. Wizualne zamknięcie wszystkich 6 pozostaje otwarte.**

| Ustalenie | Zmiana i ocena statyczna |
|---|---|
| P2-1 detal | `PrzepisSzczegolPage.vue:611` tworzy kontener inline-size, a dwie kolumny pojawiają się dopiero przy 48 rem dostępnej przestrzeni. Wąski obszar przy root 32 px pozostanie jedną kolumną. |
| P2-2 fokus | `PrzepisEdytorPage.vue:221` mierzy faktycznie aktywny element po jednej klatce natywnego scrollowania. Handler `:597` działa tylko w edytorze, pomija sam save bar, sprawdza sessionCurrent/activeElement/contains, anuluje poprzednią klatkę i sprząta ją przy dispose. Dostosowuje wyłącznie scroll, bez zmiany fokusu albo mutacji danych. Trzy regresje sprawdzają odsłonięcie, brak zbędnego przewijania i ignorowanie nieaktualnego fokusu. |
| P2-3 nagłówki | `PageHeader.vue:59` tworzy nazwany kontener, a `:63` ukrywa dekorację poniżej 36 rem realnej przestrzeni; wewnętrzny grid zyskuje min-w-0. Nie zmienia źródła treści ani akcji. |
| P2-4 katalog | `PrzepisyPage.vue:323` zastępuje kolumny zależne od viewportu przez auto-fill z minimum min(100%,18rem); przy powiększeniu karta uzyska pełny wiersz zamiast wąskiej połowy. |
| P2-5 listy | `ShoppingListsCatalog.vue:82` używa zawijającego flex, a treść `:85` ma basis-80/flex-1/min-w-0. Przycisk może przejść pod opis zamiast narzucać wąską kolumnę. |
| P2-6 profile | `UstawieniaPage.vue:478` zastępuje grid auto-kolumną przez flex-wrap, treść `:481` ma basis-64, a grupa akcji min-w-0/flex-wrap. Pozwala przenieść działania pod pełną treść. |

Diff nie zmienia skryptów poza lokalnym handlerem widoczności fokusu w edytorze. W szczególności nie zmienia mutacji, treści formularza, guardów sesji ani API. Osobny security reviewer ocenia zachowanie guardów c136. Po integracji wymagane są nowe obrazy i geometria dla powiększonego tekstu, naturalne Tab 320/390/1024 i końcowa macierz, zanim oznaczymy problemy jako zamknięte.

2026-10-31. Reviewer Sol nie jest autorem ocenianego kodu. Praca tylko na istniejących źródłach i artefaktach; bez DB, E2E, przeglądarki, testów i sieci. Zapis wyłącznie w tym ignorowanym pliku i `backend/data/ux11-visual-crops/` własnego worktree.

**Werdykt przygotowania: brak nowych ustaleń P0–P3 (0/0/0/0).** Obejrzano 44 oryginalne PNG tworzące 22 pary wszystkich 11 ekranów na 390 i 1440 px, 15 kontroli przełamań, 10 dodatkowych stanów oraz 6 historycznych obrazów błędów UX08: razem 75 różnych plików źródłowych. Końcowy odbiór UX11 nadal czeka na 320 px, 200% tekstu oraz potwierdzenie finalnego HEAD przez O.

## Kontekst

- Worktree: `C:/Users/yauta/.codex/worktrees/ux11-visual/family-food-planner`; detached HEAD `ef1e03305862519b8773aa1aec91db34128cd633` (odebrane UX09), z zachowanym wejściowym patchem UX10.
- Wejście: `F:/repo/family-food-planner/backend/data/ux10-results/code-snapshot-prep.patch`. SHA256 odczytane osobiście: `8FE475B172DC112ACFD0248657DF7AA5F75F5B9C5F4ECEFF1B47A0A6EAFD6DC9`.
- BEFORE: `F:/repo/family-food-planner/backend/data/ux-baseline/screenshots-before/`.
- AFTER: `F:/repo/family-food-planner/backend/data/ux-baseline/screenshots-ux10-final1/`.
- O przekazał rzeczywiste screenshoty tego samego fixture UX00. Rozpoznano te same nazwy UX00, daty 2029-06-04–10, profile i zdjęcie jabłka. Reviewer nie odtwarzał fixture ani nie wykonywał screenshotów.
- Przeczytano `CLAUDE.md`, `.claude/skills/pasnik-frontend/SKILL.md`, `DESIGN_SPEC.md`, `ORCHESTRATION.md`, `BASELINE.md`, aktualny stan/rezerwacje/wpisy `PROGRESS.md`, kartę UX11 oraz funkcje wszystkich 11 ekranów `references/domowa-kuchnia.html`. Makieta pozostaje wyłącznie kierunkiem; jej „Przed” nie jest dowodem starego UI.
- D35: niezależny review Sol; nie deklarowano wykonania builtin `/code-review` ani `/security-review`.

## Macierz ekranów

PASS oznacza brak problemu w faktycznie obejrzanych fragmentach PNG, nie potwierdzenie zachowania aplikacji.

| Referencja | Nazwa pliku `{viewport}-{nazwa}.png` | 390 | 1440 | Obserwacja |
|---|---|---|---|---|
| day | day-full | PASS | PASS | Pełna nazwa dania przed bilansem; mobilny układ mieści viewport. |
| week | week | PASS | PASS | Czytelna agenda zamiast siedmiu ściśniętych kolumn; nazwy i akcje zawijają się. |
| recipes | recipes | PASS | PASS | Kompaktowe grafiki zastępcze, prawdziwe zdjęcie, zwinięte filtry i pełne nazwy. |
| recipe | recipe-photo | PASS | PASS | Wyraźne Zaplanuj; pełne składniki i ilości; dwie kolumny desktop, jedna telefon. |
| editor | recipe-editor | PASS | PASS | Najpierw składniki i kroki; dodatki zwinięte; jednostki g/ml/szt. czytelne. |
| shopping | shopping | PASS | PASS | Zapisane listy pierwsze, generator oddzielony, tury w rozwinięciu. |
| list | shopping-list | PASS | PASS | Pełne nazwy; kupione zwinięte; jednoznaczne przyjęcie do spiżarni. |
| pantry | pantry | PASS | PASS | Pełne nazwy kart; jawny wycinek terminów i brak partii; akcje mieszczą się. |
| stats | summary | PASS | PASS | Cały plan, luki dni i historyczne cele opisane jawnie; bez dużych dekoracji. |
| products | products | PASS | PASS | Spokojne wiersze; pełne nazwy; tekst statusu; brak dawnego poszerzenia strony. |
| settings | settings | PASS | PASS | Cztery sekcje; osobno konta i osoby; akcje profili zawijane. |

Widoczny kierunek odpowiada DESIGN_SPEC: kremowe powierzchnie, szeryfowe nagłówki i bezszeryfowa treść, zielona hierarchia działań, cztery główne sekcje i ograniczone duże dekoracje na telefonie. Lista, edytor i liczby mają oszczędne ozdoby. Katalog korzysta ze zdjęcia oraz ilustracji przy jego braku. Agenda desktop nie ściska siedmiu kolumn pod nawigacją. Nie użyto makietowych fikcyjnych osobistych bilansów, zakończenia zakupów ani zapisu szkicu jako dowodu implementacji.

Pomocniczo odczytane źródła: `frontend/src/components/domain/PageHeader.vue:34` (font-serif i break-words), `:50` (kratka aria-hidden/pointer-events-none), `frontend/src/assets/tailwind.css:67` (Inter i Georgia), `frontend/src/components/domain/RecipeCard.vue:65` (pełna zawijana nazwa), `frontend/src/pages/tydzien/PlanTygodniaPage.vue:958` i `:966` (progi kontenera 36/84 rem). Nie ma findings wymagających wskazania błędnej linii.

## Kontrole przełamań i stanów

Obejrzano wszystkie 15 oryginałów AFTER: `360/768/1024` × `day-full/week/recipes/shopping-list/recipe-editor`. PASS widocznego układu. Artefakty `ux11-visual-crops/control-{viewport}-{nazwa}.png` zawierają bezstratne top/middle/bottom po 800 px: y=0, max(0,(H−800)//2), max(0,H−800). Nazwy i akcje mieszczą się; jednostki nie są ucięte. Katalog 768 ma akcje przeniesione do osobnych wierszy.

Dodatkowe 10 oryginałów AFTER obejrzano bezpośrednio w całości: `390-day-empty.png`, `390-day-partial.png`, `390-day-no-split.png`, `390-recipe-no-photo.png`, `390-shopping-offline.png`, `390-shopping-public.png`, `390-shopping-list-expanded.png`, `390-settings-goals.png`, `390-settings-shopping.png`, `390-settings-data.png`. PASS widocznego układu: jawny pusty dzień, pełne nazwy i ostrzeżenia, publiczna lista bez rodzinnej nawigacji, offline z jedną oczekującą zmianą oraz opisem wyłączenia przyjęcia, rozwinięte kupione i wszystkie sekcje ustawień. Z PNG nie wnioskuję o faktycznej synchronizacji ani uprawnieniach.

Osobno obejrzano 6 historycznych obrazów `F:/repo/family-food-planner/backend/data/ux08-results/png-targeted-3/editor-error-{403,409,422}-{390,1024}.png` w całości. Kontrolowany błąd i wpisane dane są widoczne; przy 422 pole trudności jest ponad paskiem zapisu. To istniejący dowód UX08 z kontrolowanymi odpowiedziami testu, nie nowy runtime UX11. Nie stwierdzono problemu wizualnego; nie deklaruję na tej podstawie poprawnego sterowania fokusem.

## Granice wyniku

- PNG nie potwierdzają klawiatury, kolejności/powrotu fokusu, czytnika ekranu, liczbowego kontrastu, rzeczywistego obszaru dotyku, druku ani synchronizacji offline. Te kontrole należą do źródeł/pomiarów/testów O.
- Nie zadeklarowano kontroli niewysłanych 320/200%, nowych pending/load/error UX11 ani druków. Końcowy odbiór pozostaje otwarty do dostarczenia wymaganych dowodów i finalnego HEAD.
- Nie zmieniono źródeł, śledzonej dokumentacji, danych fixture ani wejściowego patcha. Bez DB, resetu, pushu, deployu i UX12.

## Ledger 44 oryginałów

Każdy wpis oznacza obejrzenie obu źródłowych PNG przez bezstratny crop PIL, bez zmiany pikseli UI. Granice y są w pikselach oryginału. Mobilne `comparison.png` zawiera trzy kolumny (top/middle/bottom), dwa wiersze (BEFORE/AFTER). Desktop ma osobne `top/middle/bottom.png` po dwa wiersze. Szare tło i opis są poza screenshotem. Długie katalogi i spiżarnia mają próbkowany przegląd top/middle/bottom; nie twierdzę, że przeczytano każdy ze 100 wierszy.

|Viewport / screen|BEFORE size|BEFORE y|AFTER size|AFTER y|Viewed crop|
|---|---|---|---|---|---|
|390/day-full|699x1849|0..900, 474..1374, 949..1849|390x1559|0..900, 329..1229, 659..1559|390-day-full-comparison.png|
|390/week|390x2255|0..900, 677..1577, 1355..2255|390x3397|0..900, 1248..2148, 2497..3397|390-week-comparison.png|
|390/recipes|390x23877|0..900, 11488..12388, 22977..23877|390x20975|0..900, 10037..10937, 20075..20975|390-recipes-comparison.png|
|390/recipe-photo|616x1316|0..900, 208..1108, 416..1316|390x1891|0..900, 495..1395, 991..1891|390-recipe-photo-comparison.png|
|390/recipe-editor|738x2907|0..900, 1003..1903, 2007..2907|390x2456|0..900, 778..1678, 1556..2456|390-recipe-editor-comparison.png|
|390/shopping|390x1183|0..900, 141..1041, 283..1183|390x1478|0..900, 289..1189, 578..1478|390-shopping-comparison.png|
|390/shopping-list|390x1113|0..900, 106..1006, 213..1113|390x965|0..900, 32..932, 65..965|390-shopping-list-comparison.png|
|390/pantry|390x26169|0..900, 12634..13534, 25269..26169|390x28887|0..900, 13993..14893, 27987..28887|390-pantry-comparison.png|
|390/summary|390x1064|0..900, 82..982, 164..1064|390x1905|0..900, 502..1402, 1005..1905|390-summary-comparison.png|
|390/products|759x9257|0..900, 4178..5078, 8357..9257|390x10577|0..900, 4838..5738, 9677..10577|390-products-comparison.png|
|390/settings|390x3961|0..900, 1530..2430, 3061..3961|390x1554|0..900, 327..1227, 654..1554|390-settings-comparison.png|
|1440/day-full|1440x942|0..780, 162..942|1440x1151|0..780, 371..1151|1440-day-full-{top,bottom}.png|
|1440/week|1440x900|0..780, 60..840, 120..900|1440x2260|0..780, 740..1520, 1480..2260|1440-week-{top,middle,bottom}.png|
|1440/recipes|1440x7857|0..780, 3538..4318, 7077..7857|1440x8113|0..780, 3666..4446, 7333..8113|1440-recipes-{top,middle,bottom}.png|
|1440/recipe-photo|1440x1167|0..780, 193..973, 387..1167|1440x1551|0..780, 385..1165, 771..1551|1440-recipe-photo-{top,middle,bottom}.png|
|1440/recipe-editor|1440x2182|0..780, 701..1481, 1402..2182|1440x1987|0..780, 603..1383, 1207..1987|1440-recipe-editor-{top,middle,bottom}.png|
|1440/shopping|1440x900|0..780, 120..900|1440x1093|0..780, 313..1093|1440-shopping-{top,bottom}.png|
|1440/shopping-list|1440x900|0..780, 120..900|1440x900|0..780, 120..900|1440-shopping-list-{top,bottom}.png|
|1440/pantry|1440x9136|0..780, 4178..4958, 8356..9136|1440x11056|0..780, 5138..5918, 10276..11056|1440-pantry-{top,middle,bottom}.png|
|1440/summary|1440x900|0..780, 120..900|1440x1307|0..780, 527..1307|1440-summary-{top,bottom}.png|
|1440/products|1683x3406|0..780, 1313..2093, 2626..3406|1440x6326|0..780, 2773..3553, 5546..6326|1440-products-{top,middle,bottom}.png|
|1440/settings|1440x2360|0..780, 790..1570, 1580..2360|1440x1049|0..780, 134..914, 269..1049|1440-settings-{top,middle,bottom}.png|
