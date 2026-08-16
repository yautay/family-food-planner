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

## 4. Widoki kluczowe (mapowanie wizualizacji)

1. **Plan dnia** — nagłówek z datą i 4 kafelkami (Kalorie/Białko/Tłuszcze/
   Węglowodany: wartość/cel + pasek), lista posiłków (karta: miniatura,
   nazwa, kcal, menu ⋮: edytuj/duplikuj/przenieś/usuń/dopasuj porcję do
   celu), panel boczny: donut makro + słupki tygodnia, FAB „+" dodaje
   posiłek/pozycję.
2. **Przepisy** — grid kart ze zdjęciem, czasem, kcal/porcję; filtry jako
   chipsy tagów + szukajka; serce = ulubione (tag systemowy).
3. **Przepis szczegół** — hero zdjęcie, meta (czas, trudność, typ, kcal),
   taby: Składniki / Przygotowanie / Wartości odżywcze; regulacja liczby
   porcji przelicza składniki i wartości na żywo.
4. **Plan tygodniowy** — siatka dni × posiłki (miniatury), przeciąganie/
   kopiowanie, akcje: kopiuj dzień, powiel blok, zapisz jako szablon,
   zastosuj szablon/cykl.
5. **Lista zakupów** — sekcje per kategoria w kolejności profilu sklepu,
   pozycje z dużym checkboxem, ilością i plakietką resztki; panel akcji:
   udostępnij (link/QR/systemowe share), drukuj, eksport PDF later.
6. **Spiżarnia** — grid/lista z filtrem kategorii i sortowaniem po dacie
   ważności; produkty bliskie przeterminowania wyróżnione.
7. **Statystyki** — zakładki Kalorie/Makroskładniki; słupki stacked
   tydzień/zakres, linie celów; średnie dzienne vs cele.
8. **Edycja produktu** — formularz z kategorią, jednostkami, wartościami
   /100 g (+ IG), zdjęciem, datą ważności domyślną; sekcja przeliczników
   jednostek domowych.
9. **Mobile** — patrz §5.

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

## 7. Język interfejsu

Wyłącznie polski, forma bezosobowa lub 2. os. („Dodaj produkt"), bez
anglicyzmów tam, gdzie istnieje naturalne polskie słowo. Nazwy domenowe
spójne w całym UI: produkt (kanoniczny), produkt sklepowy, przepis, posiłek,
plan dnia, szablon, cykl, spiżarnia, tura zakupów, lista zakupowa, resztka.
