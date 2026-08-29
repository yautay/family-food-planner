# 01 — Audyt PDF-ów od dietetyczki

Data audytu: 2026-08-16 · Źródło: `data/source_pdfs/` (8 plików, kopie z
`github.com/yautay/family-food-planner/core_recipes`) · Narzędzie: pdfplumber
(ekstrakcja tekstu, strona po stronie).

Ten dokument jest **kontraktem wejściowym dla PDF importera** (BATCH_15/16).
Parser i ekran review mają obsługiwać DOKŁADNIE te struktury i anomalie —
nie hipotetyczne. Każda liczba poniżej została zmierzona na realnych plikach.

## 1. Inwentarz plików

| Plik | Stron | Cel kcal | Dni | Sumy dnia (kcal) |
|---|---|---|---|---|
| dieta.pdf | 10 | 2000 | Pon/Wt/Śr | 2021, 1953, 1919 |
| dieta (1).pdf | 9 | 2000 | Pon/Wt/Śr | 2078, 1992, 1977 |
| dieta (2).pdf | 9 | 2000 | Pon/Wt/Śr | 1959, 1987, 2030 |
| dieta (3).pdf | 8 | 2000 | Pon/Wt/Śr | 1970, 2049, 2036 |
| dieta (4).pdf | 8 | 2000 | Pon/Wt/Śr | 2098, 2059, 2029 |
| dieta (5).pdf | 9 | 2000 | Pon/Wt/Śr | 2158, 2020, 1953 |
| dieta (6).pdf | 8 | 2000 | Pon/Wt/Śr | 1997, 2025, 1962 |
| dieta (7).pdf | 10 | 2000 | Pon/Wt/Śr | 2044, 2054, 2095 |

Łącznie: **24 dni · 96 posiłków · 662 wiersze składników · 185 unikalnych
nazw produktów** (liczby obowiązujące od decyzji **D20**, wdrożonej w
BATCH_16 — kontrakt §3.2 objął wtedy dwa dodatkowe warianty wiersza; audyt
z 2026-08-16 liczył 642/178, patrz errata §9.2).

Każdy PDF nosi nagłówek „Tydzień 1" — **numer tygodnia jest bez znaczenia**,
to 8 niezależnych bloków 3-dniowych. `dieta (2).pdf` ma zamiast podsumowania
tygodnia **list przewodni dietetyczki** (patrz §6).

## 2. Struktura strony (layout)

1. **Strona 1** — tytułowa: dietetyk, „Plan żywieniowy", cel kcal, pacjent.
2. **Strona 2** — podsumowanie: siatka dzień × posiłek z nazwami dań + sumy
   dnia (Kcal, W, B, T, Bł, ŁG). Wyjątek: dieta (2) = list przewodni.
3. **Strony dni** — sekwencyjnie Poniedziałek/Wtorek/Środa. Każdy dzień:
   4 posiłki w stałej kolejności ŚNIADANIE → OBIAD → PODWIECZOREK → KOLACJA.
   Posiłek może mieć **więcej niż jedno danie** (np. „Zupa pomidorowa z ryżem"
   + „Kanapka z wędliną" w jednej kolacji). Dzień kończy wiersz
   `SUMA DNIA Kcal: ... W: ...g B: ...g T: ...g Bł: ...g ŁG: ...`.
4. **Lista zakupów** — agregat składników 3 dni, pogrupowany w kategorie,
   **układ dwukolumnowy** (patrz §5.4).
5. **Wymienniki** — nagłówek obecny we wszystkich 8 plikach, sekcja
   **zawsze pusta** (0 wierszy z gramaturą). Importer ma ją rozpoznać
   i zignorować.

## 3. Format danych

### 3.1 Nagłówek posiłku

```
ŚNIADANIE Kcal: 468 W: 31.3 B: 17.9 T: 30.4 Bł: 9.0 ŁG: 4.3
```

Legenda (z PDF): Kcal energia, W węglowodany, B białko, T tłuszcze,
Bł błonnik, ŁG ładunek glikemiczny. Wartości W/B/T/Bł w gramach, ŁG
bezwymiarowy. **Mikroelementów brak w całym materiale.**

### 3.2 Wiersz składnika

Trzy warianty (drugi i trzeci dołożyła decyzja **D20**, wdrożenie BATCH_16):

```
A.  Nazwa produktu, ILOŚĆ x Jednostka (GRAMY g)      — 642 wiersze
B.  Nazwa produktu, GRAMY g                          — 10 wierszy
C.  Nazwa produktu, ILOŚĆ x  ⏎  Jednostka (GRAMY g)  — 10 wierszy
```

Przykłady: `Cebula, 0,3 x Sztuka (31,5 g)`, `Przecier pomidorowy, 6 x Łyżka (90 g)`
(A); `Cukinia, 200 g` (B); `Czekolada ciemna (60-69% masy kakaowej), 2 x` +
`Kostka (16 g)` (C). W wariancie C jednostka bywa w PIERWSZEJ linii
(`…, 1 x Łyżeczka` + `(5 g)`) — rozstrzyga ją zamknięta lista jednostek niżej.

- Separator dziesiętny: **przecinek**.
- W wariancie B pary ilość × jednostka NIE MA i parser jej nie zgaduje
  (`raw_qty`/`raw_unit` puste); w wariancie C zapisuje ją tylko wtedy, gdy
  jednoznacznie rozpoznał jednostkę — para jest niepodzielna.
- **Gramy są podane zawsze** (662/662 wierszy) — to gramatura jest źródłem
  prawdy dla importu; para ilość×jednostka to informacja prezentacyjna
  i materiał do nauki przeliczników per produkt.
- Jednostki występujące w materiale: Sztuka, Opakowanie, Łyżka, Łyżeczka,
  Plaster, Szklanka, Garść, Ząbek, Szczypta, Porcja, Kromka, Liść, Woreczek,
  Gałka.
- **Pułapka ekstrakcji**: pdfplumber skleja lewą kolumnę (składniki) z prawą
  (instrukcja przygotowania) w jedną linię — regex składnika musi kotwiczyć
  od początku linii i tolerować tekst po nawiasie z gramami.

### 3.3 Sekcje tekstowe posiłku

- `Przepis` — instrukcja przygotowania (prawa kolumna, tekst swobodny).
- `Komentarz` — opcjonalne uwagi dietetyczki (np. „Jeżeli danie okaże się
  zbyt duże objętościowo, proszę dać szklankę fasoli").
- `Przepis na N porcji` + `Zjedz 1 z N porcji` — oznaczenie przepisów
  wieloporcjowych (patrz §5.1).
- `Produkty` — dodatkowa lista składników POZA przepisem wieloporcjowym
  (np. ziemniaki do gołąbków), wliczona w makro posiłku.

## 4. Weryfikacja spójności (wynik pozytywny)

- **Suma kcal 4 posiłków = SUMA DNIA w 24/24 dniach** (tolerancja ±2 kcal,
  faktycznie 0 rozjazdów). Wartości w PDF są wewnętrznie spójne — importer
  może używać sumy dnia jako sumy kontrolnej parsowania.
- Wartości per posiłek są **per porcja zjadana**, nie per całość przepisu
  (dowód: gołąbki 3305 g składników / 635 kcal / „Zjedz 1 z 7 porcji").

## 5. Anomalie — wymagany ekran review

### 5.1 Przepisy wieloporcjowe (KRYTYCZNE)

Wzorzec: składniki podane na CAŁOŚĆ, makro na JEDNĄ porcję.

| Plik | Posiłek | Masa składników | Kcal | Oznaczenie |
|---|---|---|---|---|
| dieta.pdf | OBIAD (Gołąbki bez zawijania) | 3305 g | 635 | „Przepis na 7 porcji" + „Zjedz 1 z 7" |
| dieta (5).pdf | OBIAD | 1018 g | 599 | „Przepis na 2 porcji" + „Zjedz 1 z 2" |
| dieta (3).pdf | OBIAD | 828 g | 638 | **BRAK oznaczenia** |
| dieta (5).pdf | ŚNIADANIE | 946 g | 612 | **BRAK oznaczenia** |
| dieta (5).pdf | KOLACJA | 1246 g | 486 | **BRAK oznaczenia** |
| dieta (7).pdf | KOLACJA | 806 g | 554 | **BRAK oznaczenia** |

Reguła importera: jeżeli `masa składników > próg` (proponowane 800 g) i brak
jawnego „Przepis na N porcji" — **NIE zgaduj**; posiłek trafia do review
z pytaniem o liczbę porcji bazowych. Sanity-check: kcal wyliczone z produktów
kanonicznych vs kcal z PDF (rozjazd > tolerancji ⇒ issue).

### 5.2 Niespójne gramatury jednostek (22 produkty)

Ta sama para (produkt, jednostka) ma różną wagę w różnych miejscach:

| Produkt [jednostka] | Zmierzone gramatury 1 szt. |
|---|---|
| Jajko [sztuka] | 50, 60 |
| Banan [sztuka] | 120, 140 |
| Cebula [sztuka] | 105, 120 |
| Pierś z kurczaka [porcja] | 100, 200 |
| Boczek bez kości [plaster] | 10, 40 |
| Łosoś wędzony [plaster] | 20, 60 |
| Mąka pszenna typ 500 [łyżka] | 5, 12, 15 |
| Śmietana 12% [łyżka] | 18, 25 |
| … (pełna lista 22 pozycji w skrypcie audytu) | |

Konsekwencja projektowa: przelicznik jednostki domowej jest **własnością
produktu** (tabela `product_unit_weights`), uczony z próbek importu
(mediana + licznik próbek), edytowalny przez admina. Import NIGDY nie polega
na przeliczniku — zawsze bierze gramy z nawiasu.

### 5.3 Warianty nazw produktów

- Duplikaty przez białe znaki: `Serek kanapkowy ` (trailing space),
  `Ser mozzarella light `.
- Pary wymagające decyzji człowieka przy mapowaniu (część to odrębne
  produkty, część duplikaty): Skyr naturalny / Skyr naturalny pitny;
  Maliny / Maliny mrożone; Pomidor / Pomidor koktajlowy / Pomidory z puszki;
  Ser parmezan / Ser parmezan tarty; Masło / Masło klarowane / Masło
  orzechowe; Cebula / Cebula czerwona / Cebula szalotka; Makaron /
  pełnoziarnisty / ryżowy / świderki.
- Normalizacja minimalna przy imporcie: trim, zbicie spacji, lowercase do
  klucza porównania. Mapowanie na produkt kanoniczny — przez sugestię
  (dokładne dopasowanie znormalizowanej nazwy → auto-sugestia; inaczej
  fuzzy/AI propozycja) + zatwierdzenie w review.

### 5.4 Lista zakupów w PDF

Układ dwukolumnowy; naiwna ekstrakcja przeplata kolumny i psuje pary
kategoria→produkty. Dodatkowo pozycje zagregowane ułamkowo
(`Jajko 2,14 x sztuka 108,6 g` — bo 1/7 gołąbków) i zdublowane wiersze tego
samego produktu w różnych jednostkach (Orzechy włoskie: `4 x sztuka` +
`1 x garść`). **Decyzja: importer IGNORUJE strony listy zakupów** — nasza
aplikacja generuje zakupy sama z przepisów; lista z PDF nie wnosi danych,
których nie mamy lepszych.

### 5.5 Kategorie z listy zakupów (użyteczny słownik)

Kategorie stosowane przez dietetyczkę (do zasilenia słownika kategorii
zakupowych): GRZYBY, MIĘSO I PRODUKTY MIĘSNE, MROŻONKI, NABIAŁ I JAJA,
ORZECHY I NASIONA, OWOCE, PRZETWORY, PRZYPRAWY I ZIOŁA, TŁUSZCZE, WARZYWA,
ZBOŻOWE, INNE.

## 6. List przewodni dietetyczki (dieta (2).pdf, s. 2) — wymagania domenowe

Potwierdza model użycia, który aplikacja ma wspierać:

1. **Każdą dietę (blok 3-dniowy) stosuje się 2 dni pod rząd** — upraszcza
   zakupy i minimalizuje resztki; część potraw gotuje się ×2.
2. **Tydzień najlepiej zaczynać dniem owocowo-warzywnym** (dowolna liczba
   posiłków, tylko warzywa/owoce) — stąd „dzień warzywny" w modelu tygodnia.
3. Minimum 1,5 l wody dziennie (poza zakresem MVP).
4. Zakaz przypraw z glutaminianem, zakaz alkoholu (informacyjne).
5. Kolejność posiłków dowolna — potwierdza elastyczny model posiłków dnia.

## 7. Reprezentatywny przykład surowej ekstrakcji

```
OBIAD Kcal: 635 W: 71.7 B: 28.8 T: 27.8 Bł: 13.2 ŁG: 36.1
Gołąbki bez zawijania Przepis na 7 porcji
Cebula, 2 x Sztuka (210 g) Kapustę poszatkować, doprawić solą i odstawić.
Jajko, 1 x Sztuka (60 g) Po chwili odsączyć z wody. Cebulę zeszklić, dodać
Kapusta włoska, 1 x Sztuka (1500 g) do mięsa i ugotowanego ostudzonego ryżu.
[...]
Zjedz 1 z 7 porcji
Produkty
Ziemniak, 3 x Sztuka (225 g)
```

Uwaga: instrukcja (prawa kolumna) wpleciona w wiersze składników;
`Produkty` po `Zjedz 1 z N` to dodatek jednoporcjowy do posiłku.

## 8. Wnioski dla implementacji (wiążące dla BATCH_15/16)

1. Parser deterministyczny (regex + maszyna stanów sekcji) pokrywa 100%
   struktury; AI (Claude API — zgoda właściciela 2026-08-16, PDF-y nie są
   tajne) służy do: propozycji mapowania nazw, wykrywania duplikatów,
   opisu anomalii — nigdy do zapisu bez review.
2. Suma dnia i kcal posiłków = sumy kontrolne parsowania.
3. Gramatura z nawiasu = jedyne źródło ilości; pary ilość×jednostka
   zasilają `product_unit_weights` jako próbki.
4. Wartości odżywcze z PDF (per posiłek) zapisujemy jako metadane importu
   do walidacji — **prawdą aplikacji są wartości wyliczone z produktów
   kanonicznych**; rozjazd wyliczenia vs PDF ponad próg (proponowane 10%)
   ⇒ issue w review.
5. Sekcje „Lista zakupów" i „Wymienniki" — rozpoznać i pominąć.
6. Referencja do walidacji importera: `data/reference/prototype.db`
   (prototyp zaimportował te same PDF-y: 84 przepisy, 592 składniki,
   181 produktów z wartościami USDA/OpenFoodFacts). Importer nowej aplikacji
   powinien osiągnąć co najmniej tę kompletność; różnice = materiał do testów.

## 9. Errata z implementacji (BATCH_15, 2026-08-29)

Parser powstał wprost z tego dokumentu i **odtworzył wszystkie ówczesne liczby
z §1** (24 dni, 96 posiłków, 642 wiersze składników, 178 nazw produktów, 24/24
sumy kontrolne). BATCH_16 wdrożył decyzję D20 i liczby wierszy/nazw w §1 są od
tej pory inne (662/185) — pozostałe wciąż aktualne. Poniżej wyłącznie to,
czego audyt nie zapisał albo zapisał
niedokładnie — każdy punkt z pomiarem na tym samym korpusie. **Kontrakt
pozostaje wiążący**; zmiany kontraktu wymagają decyzji właściciela, nie
„ulepszenia" parsera.

### 9.1 Masa z tabeli §5.1 jest masą POSIŁKU, nie pojedynczego dania

Tabela §5.1 podaje sześć mas. Wszystkie sześć odtwarza się co do zaokrąglenia
dopiero wtedy, gdy sumować gramaturę **całego posiłku** (wszystkich jego dań)
razem z sekcją `Produkty`:

| Plik | Posiłek | §5.1 | Zmierzone (posiłek + `Produkty`) | Dań w posiłku |
|---|---|---|---|---|
| dieta.pdf | OBIAD | 3305 | 3305 | 1 |
| dieta (5).pdf | OBIAD | 1018 | 1017,5 | 2 |
| dieta (3).pdf | OBIAD | 828 | 827,5 | 1 |
| dieta (5).pdf | ŚNIADANIE | 946 | 946 | 1 |
| dieta (5).pdf | KOLACJA | 1246 | 1245,8 | 2 |
| dieta (7).pdf | KOLACJA | 806 | 806,3 | **2** |

Rozstrzygający jest ostatni wiersz: `dieta (7).pdf` KOLACJA to „Zupa krem
z dyni" (615,3 g) + „Kanapka z wędliną" (191 g). **Żadne z dań nie przekracza
progu 800 g samo**, więc reguła liczona per danie znalazłaby 3 nieoznaczone
przypadki zamiast 4 i przeczyłaby §5.1.

Jest to też jedyna spójna semantyka: `pdf_kcal` w dokumencie opisuje POSIŁEK,
więc zdanie „składniki ważą 806 g, a posiłek ma 554 kcal" jest zdaniem
o posiłku. Reguła importera brzmi zatem: **masa wszystkich dań posiłku razem
z `Produkty` > 800 g i żadne danie posiłku nie niesie „Przepis na N porcji"
⇒ issue `multi_portion_suspect` (blocker)**, wieszany na najcięższym daniu
posiłku. Daje to dokładnie 6 posiłków ponad progiem: 2 oznaczone (bez issue)
i 4 nieoznaczone (z issue).

To **odstępstwo od Implementation Notes karty BATCH_15** („masa przepisu
głównego, BEZ sekcji `Produkty`"), świadome i udokumentowane: karta w sekcjach
Tests i Acceptance Criteria wymaga dokładnie czterech przypadków z masami
z §5.1, a tych nie da się otrzymać inaczej.

### 9.2 Dwadzieścia wierszy składników poza pierwotnym wzorcem §3.2

Audyt z 2026-08-16 mówił „gramy są podane zawsze (642/642 wierszy)". To była
prawda o wierszach pasujących do JEDNEGO podanego wzorca — w korpusie jest
jeszcze **20 wierszy niosących gramaturę w innym układzie**:

| Wariant | Przykład | Wystąpień |
|---|---|---|
| B — bez pary ilość×jednostka | `Cukinia, 200 g` | 10 |
| C — zawinięty między dwie linie | `Czekolada ciemna (60-69% masy kakaowej), 2 x` + `Kostka (16 g)` | 10 |

**Wdrożenie D20 w BATCH_16 (2026-08-29) skorygowało pomiar w górę.** Karta
decyzji zapowiadała 7 wierszy (→ 649/180); realizacja zmierzyła **20** (→ **662
wiersze i 185 nazw produktów**). Rozbieżność ma jedną, sprawdzalną przyczynę:
liczba 7 pochodziła z licznika ostrzeżeń `parse_warning` BATCH_15, a jego regexy
kotwiczyły na końcu linii — nie widziały więc ani jednego wiersza, do którego
pdfplumber dokleił prawą kolumnę (§3.2 pułapka 1). Takich jest 6 z 10 w wariancie
B i 7 z 10 w wariancie C. Sam audyt nosił już ślad tej luki: jako przykład
wariantu B podawał `Cukinia, 200 g`, którego na liście czterech „zmierzonych"
wierszy nie było, bo niesie doklejone `wymieszać z serem i pokrojonym pomidorem.`.

Zakres decyzji się przez to NIE zmienił — oba warianty są dokładnie te, które
zatwierdził właściciel; zmieniła się tylko ich policzona liczba. Wiersze
odzyskane dodatkowo to m.in. `Pierś z indyka, 100 g`, `Ser camembert, 40 g`,
`Mleko 2%, 120 g`, `Woda źródlana, 120 g` (B) oraz `Mleczko kokosowe
(skondensowane), 10 x Łyżka` + `(100 g)`, `Tuńczyk w wodzie (konserwowy), 0,5 x`
+ `Opakowanie (85 g)`, `Kawa espresso (napar bez cukru), 1 x Szklanka` + `(50 g)`
(C) — a więc znowu główne składniki dań, nie dodatki.

**Reguła „nie zgaduj" obowiązuje bez zmian**: wiersz zawinięty, którego druga
połowa nie przyszła albo nie niesie rozpoznanej jednostki z §3.2, nadal zostaje
zgłoszony jako `parse_warning` z surową linią. Po wdrożeniu D20 w korpusie nie ma
już ani jednego takiego wiersza (asercja
`test_zaden_wiersz_skladnika_nie_zostaje_niesparsowany`).

Konsekwencja dla §8.6: parser widzi **185** nazw produktów wobec 181
w prototypie (różnica **+4**), więc próg kompletności z §8.6 jest spełniony
z zapasem. Test nadal RAPORTUJE różnicę, zamiast asertować równość.

### 9.3 Warianty sekcji tekstowych spoza §3.3

- **Odmiana liczebnika**: dokument pisze `Przepis na 7 porcji`, `Przepis na
  2 porcje` i `Przepis na 1 porcję`. §3.3 podawał tylko pierwszą formę; parser
  akceptuje wszystkie (`porcj\w*`).
- **`Zjedz 2 porcję`** (dieta (7).pdf, KOLACJA poniedziałku, po `Przepis na
  1 porcję`) — wariant spoza wzorca `Zjedz 1 z N porcji`. Parser rozpoznaje go
  jako sekcję (żeby nie wpadł do instrukcji), ale **nie wnioskuje z niego
  liczby porcji**: „zjedz 2 porcje przepisu jednoporcjowego" to informacja
  o wielkości posiłku, a nie o mianowniku przepisu.
- **`Produkty` występuje 3 razy**, nie raz: dieta.pdf (Ziemniak 225 g),
  dieta (5).pdf (Ziemniak 150 g) i dieta (7).pdf (Pasta warzywna 60 g). §7
  opisywał wyłącznie pierwszy przypadek.

### 9.4 Lista zakupów potrafi zająć dwie strony, drugą bez nagłówka

`dieta.pdf` (s. 8–9), `dieta (1)`, `dieta (5)` i `dieta (7)`: nagłówek
„Lista zakupów" stoi tylko na PIERWSZEJ stronie sekcji. Klasyfikacja stron
musi być więc stanowa — po napotkaniu nagłówka wszystkie kolejne strony należą
do listy zakupów aż do „Wymienniki". Bez tego druga strona wyglądałaby na
stronę dnia.

### 9.5 Nazwa dania bywa ucięta przez zawijanie kolumn

W 3 ze 103 dań tytuł zawija się między kolumnami i parser zapisuje jego pierwszą
linię: „Pizza na tortilli z szynką, pomidorkami i", „Sałatka z pieczoną
ciecierzycą i serem", „Kiełbasa z chrzanem i warzywami na". Pełne nazwy stoją
na stronie podsumowania (§2.2). Poprawienie nazwy należy do review (BATCH_16) —
parser nie zgaduje, gdzie kończy się tytuł, a gdzie zaczyna instrukcja.
