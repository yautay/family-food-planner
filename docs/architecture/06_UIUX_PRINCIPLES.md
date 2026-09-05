# 06 — Zasady UI/UX

Kierunek wizualny = załączona wizualizacja koncepcyjna (9 widoków), zapisana
tu jako kontrakt słowny. Wizualizacja NIE jest pixel-perfect spec — UX można
poprawiać, charakter wizualny zachować.

## 1. Charakter (design direction)

Jasny, ciepły, lekko kulinarny. Dużo jasnej przestrzeni, karty z delikatnymi
cieniami, fotografie potraw, nowoczesny ale domowy. **Nie**: ciężki dashboard
enterprise, ciemny interfejs, gęste tabele.

### Tokens (Tailwind theme)

```
tło aplikacji      #FAF6EF  (ciepły krem)          --background
tło kart           #FFFFFF  z cieniem sm            --card
akcent główny      #E07A2F  (curry/pomarańcz)       --primary
akcent hover       #C96A26
akcent wtórny      #3F7A5E  (zieleń ziołowa — statusy OK, wykresy)
ostrzeżenie        #D9A441  (za mało / uwaga)
błąd/przekroczenie #C24C3B
tekst              #2B2620  główny · #6F675C wtórny
obramowania        #EDE5D8
promienie          rounded-xl (karty), rounded-lg (kontrolki)
typografia         Inter (UI); nagłówki font-semibold, cyfry tabular-nums
```

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
2. **Przepisy** — grid kart ze zdjęciem, czasem, kcal/porcję; filtry jako
   chipsy tagów + szukajka; serce = ulubione (tag systemowy). Filtrów czasu,
   trudności i oceny UI świadomie NIE MA, choć API je przyjmuje — rewizja
   wymaga decyzji właściciela (ustalenie B19). Lista jest paginowana wzorcem
   z §3.6 (strona 50): import ośmiu jadłospisów daje 103 dania.
3. **Przepis szczegół** — hero zdjęcie, meta (czas, trudność, typ, kcal),
   taby: Składniki / Przygotowanie / Wartości odżywcze; regulacja liczby
   porcji przelicza składniki i wartości na żywo.
4. **Plan tygodniowy** — siatka dni × posiłki (miniatury), przeciąganie/
   kopiowanie, akcje: kopiuj dzień, powiel blok, zapisz jako szablon,
   zastosuj szablon/cykl.
5. **Lista zakupów** — sekcje per kategoria w kolejności profilu sklepu,
   pozycje z dużym checkboxem, ilością i plakietką resztki; panel akcji:
   udostępnij (link/QR/systemowe share), drukuj, eksport PDF later.
   Stan po BATCH_11: sklep wybiera się NA LIŚCIE (`StorePicker` z create-in-context)
   i zmiana od razu przesortowuje sekcje; nagłówki sekcji są sticky; odhaczenie
   jest optimistic z rollbackiem i komunikatem przy błędzie; pozycje „mam już
   w domu" są wyszarzone na końcu swojej sekcji; panel akcji ma dodatkowo
   „Przyjmij zakupy do spiżarni" (dialog potwierdzenia) i „Usuń listę" (dialog
   z konsekwencjami). Eksport PDF pozostaje „later".
6. **Spiżarnia** — grid/lista z filtrem kategorii i sortowaniem po dacie
   ważności; produkty bliskie przeterminowania wyróżnione. Paginacja wzorcem
   z §3.6, ale strona jest WIĘKSZA (100): spiżarnia to inwentarz przeglądany
   „ile mam czego", a nie przeszukiwany katalog, więc mniejsza strona dołożyłaby
   kliknięć tam, gdzie ich dziś nie ma (§2).
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
8. **Edycja produktu** (lista katalogu `/produkty` — paginacja §3.6, strona 50,
   licznik „50 z 185") — formularz z kategorią, jednostkami, wartościami
   /100 g (+ IG), zdjęciem, datą ważności domyślną; sekcja przeliczników
   jednostek domowych. Stan po BATCH_09: dodatkowo sekcja **„Produkty
   sklepowe"** (warianty z półki: nazwa, marka, sklep, opakowanie, miniatura
   zdjęcia) z dodawaniem w drawerze, czyli bez opuszczania karty; sposób
   liczenia i waga sztuki są dla nie-ADMIN-a wyłączone z podpowiedzią (D15).
9. **Mobile** — patrz §5.
10. **Ustawienia → „Sklepy"** (BATCH_09, bez osobnej wizualizacji) — lista
   sklepów (nazwa, kolor, archiwum) z edycją w miejscu oraz edytor profilu:
   kolejność kategorii przestawiana **przeciąganiem ORAZ strzałkami** (§2 —
   alternatywa przyciskowa jest obowiązkowa, nie opcjonalna), zapis podmienia
   całą kolejność. Numeracja 1–9 odpowiada wizualizacjom z fazy projektu,
   dlatego nowy widok dostaje kolejny numer, a nie miejsce w środku listy.

## 5. Mobile = klient równorzędny

- Breakpointy: mobile-first; sidebar → bottom nav (Plan / Przepisy /
  Zakupy / Więcej) jak w wizualizacji 9.
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

## 7. Język interfejsu

Wyłącznie polski, forma bezosobowa lub 2. os. („Dodaj produkt"), bez
anglicyzmów tam, gdzie istnieje naturalne polskie słowo. Nazwy domenowe
spójne w całym UI: produkt (kanoniczny), produkt sklepowy, przepis, posiłek,
plan dnia, szablon, cykl, spiżarnia, tura zakupów, lista zakupowa, resztka.
