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

Łącznie: **24 dni · 96 posiłków · 642 wiersze składników · 178 unikalnych
nazw produktów**.

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

```
Nazwa produktu, ILOŚĆ x Jednostka (GRAMY g)
```

Przykłady: `Cebula, 0,3 x Sztuka (31,5 g)`, `Przecier pomidorowy, 6 x Łyżka (90 g)`.

- Separator dziesiętny: **przecinek**.
- **Gramy są podane zawsze** (642/642 wierszy) — to gramatura jest źródłem
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
