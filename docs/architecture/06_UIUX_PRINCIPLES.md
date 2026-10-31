# 06 — Zasady UI/UX

Kierunek wizualny programu UX00–UX11: „domowa książka kucharska”, zatwierdzony
w D34. Specyfikacja: `docs/implementation-plan/ux-redesign/DESIGN_SPEC.md`,
referencja 11 ekranów: `references/domowa-kuchnia.html` w tym samym katalogu.
Makieta określa wygląd; dane, obliczenia i uprawnienia wynikają z aplikacji.
UX01 wprowadza wspólne tokeny i prymitywy. Przebudowy kolejnych ekranów są
osobnymi kartami; stan wdrożenia opisuje rejestr programu.

## 1. Charakter (design direction)

Jasny, ciepły, lekko kulinarny. Dużo jasnej przestrzeni, karty z delikatnymi
cieniami, fotografie potraw, nowoczesny ale domowy. **Nie**: ciężki dashboard
enterprise, ciemny interfejs, gęste tabele.

### Tokens (Tailwind theme)

```
tło aplikacji      #FAF7EF                           --color-background
tło kart           #FFFDF8                           --color-card
akcja główna       #365E43 / hover #294B34            --color-primary
akcent wtórny      #3F6A4E                           --color-secondary
ostrzeżenie        #805C1B                           --color-warning
błąd/przekroczenie #A43F32                           --color-destructive
tekst              #293C2C główny / #626B5D pomocniczy
linie kart         #E3E4D6                           --color-border
granice pól        #858B7B                           --color-input
nawigacja          #F3F1E6                           --color-navigation
promienie          18–24 px karty / 8 px kontrolki
typografia         Inter UI; Georgia nagłówki PageHeader 32/38 px
```

Tekst pomocniczy i granice kontrolek są ciemniejsze od punktu startowego
makiety, aby zachować kontrast. Cienkie linie kart nie zastępują granic pól.
Kolory występują jako tokeny w `src/assets/tailwind.css`; tylko metadane
manifestu i HTML powtarzają wartości tła/akcji, bo nie obsługują zmiennych CSS.
Cyfry pozostają tabular-nums. Nie przenosić szeryfu do formularzy i tabel.

Wspólne prymitywy UX01: `PageHeader`, `HeaderDecoration`, `RecipeImage`,
`EmptyState`, `ErrorState`, `LoadingState`, `FeedbackMessage`, `ActionArea`,
`SummaryPanel` i `ActionPanel`.
Dekoracje są nieinteraktywne, ukryte przed czytnikiem i w druku; duży motyw
znika na wąskim ekranie. RecipeImage pokazuje rzeczywiste zdjęcie, a przy
braku lub błędzie obrazu ilustrację zastępczą bez wielkiej litery nazwy.

Statusy żywieniowe: za mało = bursztyn, prawidłowo = zieleń, za dużo =
czerwień — zawsze z tekstem/ikoną, nigdy samym kolorem.

## 2. Nadrzędna zasada UX

**Użytkownik ma zbudować tydzień i zakupy szybko, bez zaklikania się.**
Każdy projekt ekranu w batchu ocenia się pytaniem: ile kliknięć od intencji
do efektu? Preferuj: inline create (create-in-context), kopiuj/duplikuj,
sensible defaults, szablony, akcje kontekstowe na kartach, minimum ekranów
pośrednich. Drag&drop tylko tam, gdzie realnie szybszy (kolejność posiłków,
przenoszenie dania między dniami w widoku tygodnia) — zawsze z alternatywą
przyciskową (mobile/dostępność).

## 3. Wzorce obowiązkowe

1. **Create-in-context**: pisanie w pickerze produktu/przepisu/tagu/sklepu
   bez trafienia ⇒ `+ Dodaj "…"` ⇒ drawer z minimalnym formularzem ⇒ zapis
   ⇒ auto-wybór ⇒ użytkownik zostaje w przerwanym flow. Bez wyjątków.
2. **Puste stany uczą**: każdy pusty widok ma 1 zdanie + primary action
   (np. spiżarnia: „Dodaj pierwszy produkt").
3. **Destrukcja bezpieczna**: usunięcie = dialog z konsekwencjami; blokada
   usunięcia (409) pokazuje listę „Używane w: …" z linkami.
4. **Stany ładowania**: skeleton do pierwszej zakończonej odpowiedzi, potem
   nigdy migających skeletonów (lekcja netQArnera); mutacje = spinner na
   przycisku, nie blokada całej strony.
5. **Liczby żywieniowe**: zawsze trio wartość/cel/delta + status słowny;
   niepełne dane (brak IG itp.) = wyraźna plakietka „niepełne dane" z
   tooltipem czego brakuje.

### 3.6 Paginacja list (BATCH_19)

Ekran listy pokazuje WSZYSTKIE swoje dane albo mówi wprost, że pokazuje
wycinek — i daje dojść do ostatniej pozycji. Obowiązujący wzorzec:

1. **„Pokaż więcej" z rosnącym `offset`, nigdy numerowane strony.** Aplikacja
   jest mobile-first (§5), a numerowana paginacja na telefonie to cele dotykowe
   wielkości znaczka pocztowego; jeden przycisk pełnej szerokości ≥44 px mieści
   się w obsłudze jednoręcznej. Doładowanie NIE gubi tego, co użytkownik już
   przewinął, więc nie kosztuje kliknięć na powrót (§2).
2. **Licznik podaje relację, nie sumę**: „Produktów: 50 z 185". Samo `total`
   jest gorsze niż brak liczby — ekran mówił „185" i renderował 50, czyli
   liczba i widok kłamały razem (ustalenie R4).
3. **Przycisk znika, gdy nie ma czego dowieźć.** Koniec listy musi być widoczny;
   przycisk, który nic nie robi, jest zaproszeniem do klikania w próżnię.
4. **Skeleton tylko do PIERWSZEJ odpowiedzi** (§3.4). Doładowanie kolejnej
   strony to spinner NA PRZYCISKU — lista już coś pokazuje i nie ma prawa
   zamigotać.
5. **Porządek listy ustala SERWER.** Ekran, który obiecuje kolejność
   („najstarsze na górze"), zamawia ją parametrem zapytania; sortowanie
   pobranej strony w przeglądarce układa wycinek wybrany innym kryterium i przy
   zbiorze większym niż strona część danych staje się nieosiągalna.
6. **`limit` rośnie tylko do sufitu serwera (200, 04_API §1) — „pokaż więcej"
   zwiększa `offset`.** UI nie obchodzi walidacji `limit`.
7. **Nieudane DOŁADOWANIE nie kasuje tego, co już widać.** Komunikat siada przy
   przycisku (on jest ponowieniem), a wiersze z cache'u zostają — są poprawne.
   Błąd zamiast listy wolno pokazać tylko wtedy, gdy padła PIERWSZA strona,
   czyli gdy naprawdę nie ma czego pokazać. Inaczej jedno nieudane kliknięcie
   robi z ekranu to samo kłamstwo, które ten wzorzec likwiduje: licznik mówi
   „50 z 60", a widok jest pusty (ustalenie `/code-review` w B19).

Wirtualizacji list i nieskończonego przewijania sterowanego scrollem świadomie
NIE MA: przewijanie bez końca zabiera stopkę i orientację „ile jeszcze zostało",
a wirtualizacja to koszt złożoności przy zbiorach rzędu setek pozycji.
Realizacja: `src/api/pagination.ts` + `components/domain/LoadMoreButton.vue`
(05_FRONTEND §3).

## 4. Widoki kluczowe (mapowanie wizualizacji)

1. **Plan dnia** — nagłówek z datą i 4 kafelkami (Kalorie/Białko/Tłuszcze/
   Węglowodany: wartość/cel + pasek), lista posiłków (karta: miniatura,
   nazwa, kcal, menu ⋮: edytuj/duplikuj/przenieś/usuń/dopasuj porcję do
   celu), panel boczny: donut makro + słupki tygodnia, FAB „+" dodaje
   posiłek/pozycję.
2. **Przepisy (UX04)** — karty ze zdjęciem lub RecipeImage, pełną nazwą,
   czasem i porcjami; osobne działania „Zaplanuj” i „Przepis”. Wyszukiwanie,
   tagi, scope i „Do 30 minut” filtrują cały katalog na serwerze. Query URL
   przechowuje `q`, powtarzane `tag`, `scope`, `prep_time_max=30`; powrót ze
   szczegółu przywraca wyniki i scroll. Paginacja nadal po 50. Serce oznacza
   istniejący tag „ulubione”, bez osobistej zakładki. Filtry trudności/oceny
   pozostają poza kartą; uzgodniony UX04 zastępuje ograniczenie czasu z B19.
   Zakresy i tagi są w domyślnie zwiniętym „Pozostałe filtry”; poza panelem
   pozostają opis wszystkich aktywnych ograniczeń oraz „Wyczyść filtry”.
   Szybki filtr czasu jest dostępny bez rozwijania. Karty mają kompaktową
   ilustrację, a rzeczywiste zdjęcie mieści się w obrazie bez obcinania dania.
   Pierwszy długi tytuł i Zaplanuj są sprawdzane względem dolnej nawigacji.
3. **Przepis szczegół (UX04)** — zdjęcie, tytuł, metadane i „Zaplanuj”.
   Składniki i przygotowanie są widoczne równocześnie, na telefonie pionowo.
   Regulacja porcji korzysta z odpowiedzi serwera; błąd zachowuje ostatnio
   potwierdzony wynik tego samego przepisu. Wartości odżywcze pozostają jawne.
   Karta i szczegół otwierają wspólny panel UX03; po zapisie przechodzą do
   rzeczywistego `day.day`. Role oceny/kopiowania/edycji/archiwizacji/usunięcia
   pozostają zgodne z API. `used_in` pokazuje nazwy, ponieważ odpowiedź nie
   gwarantuje daty potrzebnej do poprawnego linku dnia.
   **Edytor (UX08)**: nazwa/porcje/czas → składniki → przygotowanie;
   widoczność, trudność, tagi i zdjęcie w jawnym rozwinięciu. Pełne nazwy
   składników zawijają się, ilość pozostaje stringiem z parsera dziesiętnego.
   Pasek „Zapisz” pokazuje stan niezapisanych zmian. Ochrona opuszczenia
   pozwala zostać, błędy zachowują szkic i kierują widoczny fokus do pola.
   Nie obiecujemy odtworzenia szkicu po awarii lub zamknięciu przeglądarki.
4. **Plan tygodniowy (UX07)** — responsywna agenda z pełnymi nazwami dań,
   pustymi dniami i zaznaczonym dniem. Przy aktualnym ograniczeniu szerokości
   AppShell agenda pozostaje także na desktopie; siedem kolumn wymaga
   dostępnych 84rem treści. „Dodaj do posiłku” zachowuje istniejący posiłek,
   „Nowy posiłek z daniem” tworzy kolejny. Dodawanie i zamiana używają panelu
   UX03. Przenoszenie ma dialog z datą, bez wymuszania przeciągania.
   „Uzupełnij plan” zawiera kopiowanie dnia/bloku, zapis i zastosowanie
   szablonu, cykle oraz historię. Kalendarz pozwala wybrać wiele dat także
   klawiaturą i przez granicę roku. Podgląd rozróżnia źródło, widoczne cele
   i dopisywanie; błąd odczytu blokuje zastosowanie. Archiwalne odniesienia
   zachowują ostrzeżenia serwera. Wykres opisuje cały plan, bez oceny celu
   osoby; zero energii przy istniejących posiłkach nie oznacza pustego planu.
   Przy dacie pozostaje zwięzły status niekompletności. Wszystkie szczegóły
   braków są w jawnym natywnym rozwinięciu za daniami, poza kolumną daty.
5. **Lista zakupów** — sekcje per kategoria w kolejności profilu sklepu,
   pozycje z dużym checkboxem, ilością i plakietką resztki; panel akcji:
   udostępnij (link/QR/systemowe share), drukuj, zapis do PDF later.
   Stan po BATCH_11: sklep wybiera się NA LIŚCIE (`StorePicker` z create-in-context)
   i zmiana od razu przesortowuje sekcje; nagłówki sekcji są sticky; odhaczenie
   jest optimistic z rollbackiem i komunikatem przy błędzie; pozycje „mam już
   w domu" są wyszarzone na końcu swojej sekcji; panel akcji ma dodatkowo
   „Przyjmij zakupy do spiżarni" (dialog potwierdzenia) i „Usuń listę" (dialog
   z konsekwencjami). Zapis listy do PDF pozostaje „later".
6. **Spiżarnia (UX09)** — pełne nazwy, ilości i terminy w zachowanych
   widokach grid/lista; filtry i sortowanie serwerowe, strona100. Dodanie
   i edycja używają ActionPanel, pozostawiając listę, pobrane strony, filtry
   i powrót fokusu. „Wykorzystaj najpierw” to jawny wycinek osobnego zapytania
   terminu do7dni (także po terminie), maksymalnie3niezerowe partie, bez
   globalnego licznika. Na telefonie nazwa zajmuje cały wiersz, ilość i termin
   kolejny. Przycisk nakłada filtr terminu, zachowując kategorię/szukanie.
   „Brak daty” oznacza brak informacji; etykieta „Termin” nie obiecuje
   bezpieczeństwa produktu. Ilości korzystają z dotychczasowego parsera.
7. **Statystyki** — zakładki Kalorie/Makroskładniki; słupki stacked
   tydzień/zakres, linie celów; średnie dzienne vs cele.
   Stan po BATCH_13: zakres jako presety **Tydzień / Miesiąc / Własny** (dwa
   date-pickery, sufit 92 dni walidowany tak jak na serwerze); linia celu jest
   **schodkowa** (cele historyczne — bez interpolacji), a dzień bez planu to
   **luka** (przerywany obrys, „brak planu" w `aria-label`), nie zerowy słupek,
   bo średnia dzieli się przez dni Z PLANEM. Zakładka makro dokłada legendę
   składników i **średnią kroczącą (7 dni)** jako nakładkę w tej samej skali;
   przy zakresie krótszym niż 7 dni w jej miejscu stoi zdanie wyjaśniające.
   Podsumowanie to znane trio wartość/cel/delta + status słowny; przy dniu
   z niepełnymi danymi dochodzi plakietka „Niepełne dane" z listą braków,
   a zakres bez planu dostaje pusty stan z akcją „Przejdź do planu".
   Wykresy ŁG świadomie NIE MA (ŁG jest w odpowiedzi API, ale nie w UI).
8. **Produkty (UX09)** — wspólna biblioteka wszystkich rodzin, pełne nazwy
   i paginacja50. Formularz ma sekcje Nazwa i miara / Wartości odżywcze /
   Jednostki domowe / Warianty sklepowe, z zachowanym osobnym zapisem.
   Pozostają kategoria, przydatność, IG, źródła danych, przeliczniki oraz
   warianty z nazwą/marką/sklepem/opakowaniem/zdjęciem i create-in-context.
   D13/D15 i409 used_in nadal określają dostępność zmian/usunięcia/miary/wagi.
   Niekompletność widzą także USER-y: krótki status i natywne rozwinięcie
   wszystkich oryginalnych komunikatów serwera, bez parsowania ich treści.
   Odtwarzanie katalogu zachowuje filtry, rzeczywiste strony i fokus;
   budżet automatyczny nie ogranicza ręcznego „Pokaż więcej”.
9. **Mobile** — patrz §5.
10. **Ustawienia → „Sklepy"** (BATCH_09, bez osobnej wizualizacji) — lista
   sklepów (nazwa, kolor, archiwum) z edycją w miejscu oraz edytor profilu:
   kolejność kategorii przestawiana **przeciąganiem ORAZ strzałkami** (§2 —
   alternatywa przyciskowa jest obowiązkowa, nie opcjonalna), zapis podmienia
   całą kolejność. Numeracja 1–9 odpowiada wizualizacjom z fazy projektu,
   dlatego nowy widok dostaje kolejny numer, a nie miejsce w środku listy.

## 5. Mobile = klient równorzędny

UX03: dzień pokazuje najpierw posiłki i pełne nazwy dań, potem
„Cały plan”. „Dzisiaj jemy” dotyczy lokalnej bieżącej daty; inny dzień ma
nagłówek „Plan posiłków”. Pasek dat zachowuje podnawigację UX02. Dodanie
i zamiana korzystają ze wspólnego panelu z jawną datą, posiłkiem i porcjami.
Produkty luzem, cel posiłku, dopasowanie, kopiowanie i usuwanie pozostają
w kontekście posiłku/pozycji. Wartości całego planu nie są oceną realizacji
indywidualnego celu. Podział dwóch profili po 1,1 przy trzech osobach zostaje
2,2 po samej zamianie dania; brakujące dane i historyczne wpisy są jawne.

UX05: Zakupy zaczynają się od trwałego katalogu „Zapisane listy”,
z licznikiem pobranych wierszy i „Pokaż więcej list”. „Ostatnia lista”
oznacza kolejność serwera, a ważność linku nie oznacza ukończenia zakupów.
Generator jest poniżej katalogu; przycisk „Nowa lista z planu” przenosi
fokus do jego nagłówka. Zakres i jawna zgoda na spiżarnię poprzedzają
podgląd, konfiguracja tur jest domyślnie zwinięta. Podgląd i zapisane listy
otrzymują fokus po zakończeniu odpowiedniej operacji. Błąd pozostawia
zakres i dostępny podgląd; sukces finalizacji pokazuje każdą utworzoną turę.

UX06: sekcje checklisty zachowują kolejność serwera. Długie nazwy zawijają
się, ilość ma osobne miejsce, pole checkboxa ma48px. Kupione pozycje są
domyślnie zwinięte per kategoria; „mam już w domu” pozostaje osobnym stanem.
Wiersze pozostają w DOM dla rozwinięcia i druku, który pokazuje wszystkie.
Udostępnij/Drukuj są na górze, sklep w rozwinięciu. Potwierdzenie przyjęcia
podaje rzeczywiste nazwy i ilości, jest niedostępne offline i przed udanym
potwierdzeniem checkboxów po synchronizacji. Sama pusta kolejka nie dowodzi
sukcesu LWW. Trwałe odrzucenie zmiany ma błąd również przy pending=0.
Publiczna lista używa tych samych wierszy i własnego klienta bez sesji/CSRF;
odwołany lub wygasły link usuwa treść z widoku. Brak trwałego „Zakończ zakupy”.

- UX02: mobile-first; sidebar od md, cztery dolne wejścia Plan / Przepisy /
  Zakupy / Spiżarnia na telefonie. Dzień / Tydzień / Podsumowanie są
  podnawigacją Planu. Biblioteka produktów jest pomocnicza, Dom i ustawienia
  oraz administracja są w menu konta, dostępnym również w nagłówku telefonu.
  Administracja widoczna wyłącznie dla ADMIN-a. Stare URL-e nadal działają.
- Main ma min-w-0 i dolny odstęp 96 px + safe-area; przyciski nawigacji
  mieszczą się przy 360 px. Nie maskować przepełnień stron przez globalne
  overflow-hidden/clip. Układy poszczególnych ekranów mają własne karty.
- Nawigacja ścieżki przenosi fokus do treści, zmiana query/filtra go zachowuje.
  Skiplink jest pierwszym wejściem klawiatury. Menu konta działa dotykiem,
  klawiaturą i przez Escape, z widocznym fokusem i zawijanym opisem osoby.
  Portalowane menu ma własne print:hidden: ukrycie sidebara/nagłówka
  nie obejmuje portalu do body. Treść strony pozostaje widoczna w druku.
- Cele dotykowe ≥44 px; checkbox listy zakupów ~48 px.
- Lista zakupów to widok krytyczny mobilny: jednoręczna obsługa, sekcje
  sticky, odhaczanie natychmiastowe (optimistic), działa offline (05 §6),
  otwierana z QR/linku bez logowania (publiczny token).
- PWA: instalowalna, ikona, splash, standalone.

## 6. Desktop i druk

Widok listy zakupów ma wariant print (`@media print`): czarno-biały,
checkboxy jako ☐, kategorie jako nagłówki, bez nawigacji; przycisk
„Drukuj" = `window.print()`.

Stan faktyczny po BATCH_11: reguły druku żyją w `src/assets/print.css`
(importowanym w `main.ts`), bo elementy do ukrycia — sidebar, bottom-nav,
nagłówek mobilny — należą do `AppShell`, a strona listy nie ma jak zabrać
nawigacji, pod którą jest osadzona. Wszystko siedzi w `@media print`, więc na
ekranie ten plik nic nie zmienia. Znak `☐` rysuje `ShoppingItemRow` (checkbox
przeglądarki dostaje `print:hidden`), a pozycje mają `break-inside: avoid`,
żeby wiersz nie łamał się między stronami.

UX06 wymusza widoczność zwiniętych kupionych wierszy w druku; cały wiersz
ma break-inside:avoid, nazwy i ilości zachowują osobne kolumny. Odbiór obejmuje
rzeczywiste strony A4 długiej listy prywatnej i publicznej, a nie sam kolor CSS.

## 7. Język interfejsu

Wyłącznie polski, forma bezosobowa lub 2. os. („Dodaj produkt"), bez
anglicyzmów tam, gdzie istnieje naturalne polskie słowo. Nazwy domenowe
spójne w całym UI: produkt (kanoniczny), produkt sklepowy, przepis, posiłek,
plan dnia, szablon, cykl, spiżarnia, tura zakupów, lista zakupowa, resztka.
