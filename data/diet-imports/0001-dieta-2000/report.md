# Raport wersji 0001-dieta-2000

Źródło: plan żywieniowy ~2000 kcal, Tydzień I, poniedziałek–środa (PDF nie jest w repo; dane osobowe pominięte). Data analizy: 2026-10-03.

> Raport powstał z `spec.json` i został policzony kodem aplikacji (`normalize_amount` → `to_basis_amount` → `nutrition/engine.py`). Nie zawiera danych osobowych.

## Podsumowanie

- Przepisów: **12**, składników: **68**.
- Produktów nowych: **44**, reużytych z katalogu: **0**.
- Błędy do rozstrzygnięcia: **0**, ostrzeżenia: **9**.
- Wynik weryfikacji: **OK — można budować paczkę**.

## Decyzje właściciela

- Zatwierdzone przez właściciela: scalenie 1–5 — Oliwa z oliwek (wiersze różniące się tylko miarą), Pierś z kurczaka + Pierś z indyka → „Pierś z drobiu”, Skyr naturalny + waniliowy → „Skyr”, Mozzarella + mozzarella light → „Ser mozzarella”, Śmietana 12% + 18% → „Śmietana”.
- Zatwierdzone przez właściciela: przecier pomidorowy (passata) NIE jest scalany z pomidorem ani z „pomidorami z puszki” — osobny produkt.
- Wagi sztuk zatwierdzone: Cebula 105 g, Pomidor 160 g (kompromis wobec 150/170 g w PDF-ie).
- Wartości odżywcze to kompromis: środek zakresu źródeł internetowych; tam, gdzie źródła się rozjeżdżają, kotwicą były sumy posiłków z PDF-a. Erytrytol liczony jako 0 węglowodanów (tak liczy dietetyk).
- Oliwa z oliwek jako MASS (g), nie VOLUME jak w seedzie demo — PDF podaje gramy, a g→ml wymagałoby gęstości (ADR-005).
- Wartości scalonych produktów to średnie ważone ilościami z tego planu (drób 150:100, skyr 150:75, mozzarella 20:125, śmietana 54:100).
- Etykieta „Sztuka” przy produkcie nie-PIECE NIE przechodzi normalize_amount (szt. wymaga PIECE) — dla pieczarek, mozzarelli, piersi z drobiu, polędwicy, kiełbasy i ogórka kiszonego generator zapisuje GRAMY, a oryginał („5 x Sztuka”) trafia do note.
- Przepisy: po 1 porcji; nazwy bez kropek końcowych, pierwsza litera wielka; literówki PDF poprawione w instrukcjach (np. „DOdać”).
- Konwersja do schematu B22: pominięto pole `last_calibration` (liczone na gramach z PDF-a — zastępuje je raport policzony silnikiem aplikacji) i `verification_status` (paczka zawsze `unverified`); scalenia zapisano w `merged_from` bez wartości źródłowych (wersja sprzed narzędzia), więc skutek kcal scaleń w raporcie jest nieznany; składnikom bez ilości w PDF-ie (tylko gramy) ustawiono `pdf_qty` = gramy.

## Produkty

### Nowe

| Produkt | Kategoria | Miara | kcal/100 | Uwagi |
|---|---|---|---|---|
| Cebula | Warzywa | piece | 40 |  |
| Cukinia | Warzywa | piece | 17 |  |
| Czosnek | Warzywa | mass | 149 |  |
| Kapusta pekińska | Warzywa | mass | 16 |  |
| Papryka czerwona | Warzywa | piece | 31 |  |
| Pomidor | Warzywa | piece | 18 |  |
| Szczypiorek | Warzywa | mass | 30 |  |
| Ziemniak | Warzywa | piece | 77 |  |
| Pieczarki | Grzyby | mass | 22 |  |
| Ogórek kiszony | Przetwory, puszki i słoiki | mass | 11 |  |
| Kukurydza konserwowa | Przetwory, puszki i słoiki | mass | 81 |  |
| Przecier pomidorowy (passata) | Przetwory, puszki i słoiki | mass | 30 |  |
| Keczup | Przetwory, puszki i słoiki | mass | 100 |  |
| Majonez | Przetwory, puszki i słoiki | mass | 680 |  |
| Banan | Owoce | piece | 89 |  |
| Gruszka | Owoce | piece | 57 |  |
| Jabłko | Owoce | piece | 52 |  |
| Czarne jagody | Owoce | mass | 53 |  |
| Szpinak mrożony | Mrożonki | mass | 31 |  |
| Truskawki mrożone | Mrożonki | mass | 35 |  |
| Kiełbasa śląska | Mięso i produkty mięsne | mass | 214 |  |
| Pierś z drobiu | Mięso i produkty mięsne | mass | 108 | podobne w katalogu: Pierś z kurczaka |
| Polędwica wieprzowa | Mięso i produkty mięsne | mass | 125 |  |
| Szynka wieprzowa mielona | Mięso i produkty mięsne | mass | 131 |  |
| Wędlina wieprzowa | Mięso i produkty mięsne | mass | 120 |  |
| Jajko | Nabiał i jaja | piece | 143 |  |
| Jogurt naturalny | Nabiał i jaja | mass | 60 | podobne w katalogu: Skyr naturalny |
| Maślanka 1,5% | Nabiał i jaja | volume | 42 |  |
| Ser ricotta | Nabiał i jaja | mass | 160 |  |
| Skyr | Nabiał i jaja | mass | 70 | podobne w katalogu: Skyr naturalny |
| Śmietana | Nabiał i jaja | mass | 171 |  |
| Ser mozzarella | Nabiał i jaja | mass | 190 |  |
| Ser cheddar | Nabiał i jaja | mass | 403 |  |
| Ser camembert | Nabiał i jaja | mass | 300 |  |
| Orzechy włoskie | Orzechy i nasiona | mass | 654 |  |
| Orzechy pekan | Orzechy i nasiona | mass | 691 | podobne w katalogu: Orzechy włoskie |
| Chleb żytni | Pieczywo | mass | 235 | podobne w katalogu: Chleb żytni razowy |
| Makaron pełnoziarnisty | Makarony, ryż i kasze | mass | 352 |  |
| Mąka orkiszowa jasna | Makarony, ryż i kasze | mass | 340 | podobne w katalogu: Mąka pszenna typ 500 |
| Oliwa z oliwek | Tłuszcze | mass | 884 |  |
| Cynamon | Przyprawy i zioła | mass | 247 |  |
| Erytrytol | Inne | mass | 0 |  |
| Miód | Inne | mass | 304 |  |
| Czekolada ciemna (60-69% kakao) | Inne | mass | 520 |  |

### Reużyte z katalogu

_brak_

### Scalenia (decyzje właściciela) i ich skutek

| Produkt wynikowy | Scalone nazwy z PDF-a | Skutek kcal posiłku (po - przed) |
|---|---|---|
| Pierś z drobiu | Pierś z kurczaka, Pierś z indyka | brak wartości źródłowych w spec (wersja sprzed narzędzia) — skutek nieznany |
| Skyr | Skyr naturalny, Skyr waniliowy | brak wartości źródłowych w spec (wersja sprzed narzędzia) — skutek nieznany |
| Śmietana | Śmietana 12 % tłuszczu, Śmietana 18 % tłuszczu | brak wartości źródłowych w spec (wersja sprzed narzędzia) — skutek nieznany |
| Ser mozzarella | Ser mozzarella, Ser mozzarella light | brak wartości źródłowych w spec (wersja sprzed narzędzia) — skutek nieznany |

## Jednostki składników

Zapisane w jednostce z PDF-a: **57**, zapisane jako gramy (albo ml): **11**.

### Składniki zapisane jako gramy i dlaczego

| Przepis | Produkt | W PDF-ie | Zapis | Powód |
|---|---|---|---|---|
| Skyrowe pancakes z gruszką | jajko | 1 x sztuka | 50 g | ilość x przelicznik daje 58 g, PDF podaje 50 g (odchyłka 16.0% > 10%) |
| Kiełbasa z warzywami | kielbasa | 1 x sztuka | 100 g | „sztuka” wymaga produktu mierzonego w sztukach, a Kiełbasa śląska liczymy w gramach |
| Makaron ze szpinakiem | smietana | 3 x łyżka | 54 g | ilość x przelicznik daje 66 g, PDF podaje 54 g (odchyłka 22.2% > 10%) |
| Grzanki z pieczarkami | pieczarki | 5 x sztuka | 100 g | „sztuka” wymaga produktu mierzonego w sztukach, a Pieczarki liczymy w gramach |
| Szakszuka z serem | cebula | 0,3 x sztuka | 36 g | ilość x przelicznik daje 31.5 g, PDF podaje 36 g (odchyłka -12.5% > 10%) |
| Szakszuka z serem | mozzarella | 1 x sztuka | 125 g | „sztuka” wymaga produktu mierzonego w sztukach, a Ser mozzarella liczymy w gramach |
| Polędwiczki w sosie śmietanowym | pieczarki | 3 x sztuka | 60 g | „sztuka” wymaga produktu mierzonego w sztukach, a Pieczarki liczymy w gramach |
| Polędwiczki w sosie śmietanowym | poledwica | 0,3 x sztuka | 150 g | „sztuka” wymaga produktu mierzonego w sztukach, a Polędwica wieprzowa liczymy w gramach |
| Polędwiczki w sosie śmietanowym | smietana | 4 x łyżka | 100 g | ilość x przelicznik daje 88 g, PDF podaje 100 g (odchyłka -12.0% > 10%) |
| Sałatka kebab | drob | 1 x sztuka | 150 g | „sztuka” wymaga produktu mierzonego w sztukach, a Pierś z drobiu liczymy w gramach |
| Sałatka kebab | ogorek_kis | 2 x sztuka | 120 g | „sztuka” wymaga produktu mierzonego w sztukach, a Ogórek kiszony liczymy w gramach |

### Odstępstwa wag względem PDF-a (przelicznik vs gramy z PDF-a)

| Przepis | Produkt | Ilość | Przelicznik | PDF | Odchyłka | Zapis |
|---|---|---|---|---|---|---|
| Jajka z warzywami i serem | jajko | 2 szt. | 116 g | 120 g | -3,3% | jednostka z PDF-a |
| Skyrowe pancakes z gruszką | jajko | 1 x sztuka | 58 g | 50 g | +16% | gramy |
| Skyrowe pancakes z gruszką | oliwa | 1 łyżeczka | 5,5 g | 5 g | +10% | jednostka z PDF-a |
| Kiełbasa z warzywami | oliwa | 1 łyżeczka | 5,5 g | 6 g | -8,3% | jednostka z PDF-a |
| Makaron ze szpinakiem | smietana | 3 x łyżka | 66 g | 54 g | +22,2% | gramy |
| Szakszuka z serem | jajko | 2 szt. | 116 g | 120 g | -3,3% | jednostka z PDF-a |
| Szakszuka z serem | pomidor | 1 szt. | 160 g | 170 g | -5,9% | jednostka z PDF-a |
| Szakszuka z serem | cebula | 0,3 x sztuka | 31,5 g | 36 g | -12,5% | gramy |
| Polędwiczki w sosie śmietanowym | smietana | 4 x łyżka | 88 g | 100 g | -12% | gramy |
| Polędwiczki w sosie śmietanowym | pomidor | 1 szt. | 160 g | 170 g | -5,9% | jednostka z PDF-a |
| Sałatka kebab | pomidor | 1 szt. | 160 g | 150 g | +6,7% | jednostka z PDF-a |

## Weryfikacja obliczeń silnikiem aplikacji

Progi: posiłek kcal > 10% = uwaga, > 15% = błąd; dzień kcal > 5% = błąd, makro > 10% = uwaga; lista zakupów ±5%. ŁG jest informacyjny (IG z tabel jest zbyt niepewny).

### Posiłki

| Pozycja | kcal (silnik / PDF) | białko (silnik / PDF) | tłuszcz (silnik / PDF) | węgl. (silnik / PDF) | błonnik (silnik / PDF) | ŁG (silnik / PDF) | Status |
|---|---|---|---|---|---|---|---|
| pon: śniadanie: Jajka z warzywami i serem | 467 / 478 (-2,3%) | 27 / 28,5 (-5,3%) | 34,9 / 35,5 (-1,7%) | 11,1 / 11,9 (-6,7%) | 3,3 / 3,4 (-2,9%) | 1 / 1,2 (-16,7%) | ok |
| pon: obiad: Spaghetti | 561 / 559 (+0,4%) | 41,1 / 40,7 (+1%) | 20,2 / 20,3 (-0,5%) | 57,6 / 60,5 (-4,8%) | 8,4 / 9 (-6,7%) | 20 / 20,8 (-3,8%) | ok |
| pon: podwieczorek: Ricotta z owocami | 412 / 454 (-9,3%) | 22,1 / 23,2 (-4,7%) | 23,1 / 25,5 (-9,4%) | 26,5 / 33,8 (-21,6%) | 4,2 / 4 (+5%) | 5,5 / 5 (+10%) | ok |
| pon: kolacja: Skyrowe pancakes z gruszką | 463 / 468 (-1,1%) | 29,4 / 30,1 (-2,3%) | 11,9 / 12,4 (-4%) | 62,6 / 61,2 (+2,3%) | 6,6 / 6,6 (0%) | 28,2 / 35,2 (-19,9%) | ok |
| wt: śniadanie: Kiełbasa z warzywami | 485 / 493 (-1,6%) | 31,1 / 32,6 (-4,6%) | 35,6 / 35,9 (-0,8%) | 13,1 / 12,9 (+1,6%) | 3,9 / 4,1 (-4,9%) | 1,2 / 1,5 (-20%) | ok |
| wt: obiad: Makaron ze szpinakiem | 664 / 647 (+2,6%) | 45,2 / 45 (+0,4%) | 32,1 / 30,9 (+3,9%) | 54,3 / 53,5 (+1,5%) | 8,6 / 9 (-4,4%) | 18,8 / 18 (+4,4%) | ok |
| wt: podwieczorek: Koktajl jagodowy | 412 / 398 (+3,5%) | 14,2 / 14,3 (-0,7%) | 23,7 / 21,6 (+9,7%) | 42,3 / 40,4 (+4,7%) | 6,8 / 7 (-2,9%) | 13,1 / 14 (-6,4%) | ok |
| wt: kolacja: Grzanki z pieczarkami | 426 / 449 (-5,1%) | 24,4 / 23,9 (+2,1%) | 16,3 / 17,5 (-6,9%) | 45,7 / 50,2 (-9%) | 7,7 / 7,2 (+6,9%) | 17,2 / 16,8 (+2,4%) | ok |
| śr: śniadanie: Szakszuka z serem | 448 / 479 (-6,5%) | 44,1 / 48,4 (-8,9%) | 24,5 / 24,8 (-1,2%) | 14,4 / 16,3 (-11,7%) | 2,7 / 2,8 (-3,6%) | 1,7 / 1,6 (+6,3%) | ok |
| śr: obiad: Polędwiczki w sosie śmietanowym | 632 / 631 (+0,2%) | 47,4 / 46 (+3%) | 25,5 / 25,1 (+1,6%) | 57,6 / 57 (+1,1%) | 8,1 / 8,2 (-1,2%) | 27,9 / 26,5 (+5,3%) | ok |
| śr: podwieczorek: Jogurt z orzechami i miodem | 428 / 429 (-0,2%) | 10,5 / 9,5 (+10,5%) | 27,3 / 27,7 (-1,4%) | 42,3 / 42,6 (-0,7%) | 7 / 7 (0%) | 13,8 / 12 (+15%) | ok |
| śr: kolacja: Sałatka kebab | 485 / 491 (-1,2%) | 41,2 / 39,8 (+3,5%) | 22,5 / 24,8 (-9,3%) | 31 / 29,9 (+3,7%) | 7,7 / 6,8 (+13,2%) | 8,2 / 9,1 (-9,9%) | ok |

### Dni

| Pozycja | kcal (silnik / PDF) | białko (silnik / PDF) | tłuszcz (silnik / PDF) | węgl. (silnik / PDF) | błonnik (silnik / PDF) | ŁG (silnik / PDF) | Status |
|---|---|---|---|---|---|---|---|
| pon | 1903 / 1959 (-2,9%) | 119,6 / 122,5 (-2,4%) | 90,1 / 93,7 (-3,8%) | 157,8 / 167,4 (-5,7%) | 22,5 / 23 (-2,2%) | 54,6 / 62,2 (-12,2%) | ok |
| wt | 1987 / 1987 (0%) | 114,9 / 115,8 (-0,8%) | 107,6 / 105,9 (+1,6%) | 155,4 / 157 (-1%) | 27 / 27,3 (-1,1%) | 50,2 / 50,3 (-0,2%) | ok |
| śr | 1993 / 2030 (-1,8%) | 143,1 / 143,7 (-0,4%) | 99,9 / 102,4 (-2,4%) | 145,3 / 145,8 (-0,3%) | 25,5 / 24,8 (+2,8%) | 51,6 / 49,2 (+4,9%) | ok |

### Lista zakupów: suma gramów produktu

| Produkt | Σ składników z PDF-a | Σ silnik | Lista PDF-a | Odchyłka silnik↔lista | Status |
|---|---|---|---|---|---|
| banan | 70 | 70 | 70 | 0% | ok |
| camembert | 40 | 40 | 40 | 0% | ok |
| cebula | 235,5 | 235,5 | 235,5 | 0% | ok |
| cheddar | 120 | 120 | 120 | 0% | ok |
| chleb | 70 | 70 | 70 | 0% | ok |
| cukinia | 300 | 300 | 300 | 0% | ok |
| cynamon | 0,3 | 0,3 | 0,3 | 0% | ok |
| czekolada | 24 | 24 | 24 | 0% | ok |
| czosnek | 10 | 10 | 10 | 0% | ok |
| drob | 250 | 250 | 250 | 0% | ok |
| erytrytol | 10 | 10 | 10 | 0% | ok |
| gruszka | 130 | 130 | 130 | 0% | ok |
| jablko | 170 | 170 | 170 | 0% | ok |
| jagody | 100 | 100 | 100 | 0% | ok |
| jajko | 290 | 282 | 290 | -2,8% | ok |
| jogurt | 180 | 180 | 180 | 0% | ok |
| kapusta | 100 | 100 | 100 | 0% | ok |
| keczup | 15 | 15 | 15 | 0% | ok |
| kielbasa | 100 | 100 | 100 | 0% | ok |
| kukurydza | 60 | 60 | 60 | 0% | ok |
| majonez | 25 | 25 | 25 | 0% | ok |
| maka_orkisz | 48 | 48 | 48 | 0% | ok |
| makaron | 120 | 120 | 120 | 0% | ok |
| maslanka | 240 | 240 | 240 | 0% | ok |
| miod | 8 | 8 | 8 | 0% | ok |
| mozzarella | 145 | 145 | 145 | 0% | ok |
| ogorek_kis | 120 | 120 | 120 | 0% | ok |
| oliwa | 41 | 41 | 41 | 0% | ok |
| orzech_wl | 30 | 30 | 30 | 0% | ok |
| papryka | 300 | 300 | 300 | 0% | ok |
| passata | 150 | 150 | 150 | 0% | ok |
| pekan | 30 | 30 | 30 | 0% | ok |
| pieczarki | 160 | 160 | 160 | 0% | ok |
| poledwica | 150 | 150 | 150 | 0% | ok |
| pomidor | 490 | 480 | 490 | -2% | ok |
| ricotta | 125 | 125 | 125 | 0% | ok |
| skyr | 225 | 225 | 225 | 0% | ok |
| smietana | 154 | 154 | 154 | 0% | ok |
| szczypiorek | 5 | 5 | 5 | 0% | ok |
| szpinak_mr | 100 | 100 | 100 | 0% | ok |
| szynka_miel | 150 | 150 | 150 | 0% | ok |
| truskawki | 100 | 100 | 100 | 0% | ok |
| wedlina | 30 | 30 | 30 | 0% | ok |
| ziemniak | 225 | 225 | 225 | 0% | ok |

## Źródła wartości odżywczych

Wszystkie produkty z paczki wchodzą jako `unverified` - ADMIN weryfikuje je w `/admin/weryfikacja` (D11, D31).

| Źródło | Zakres źródeł | Produkty |
|---|---|---|
| kompromis: tabele internetowe (środek zakresu źródeł) + sumy posiłków z PDF jako kotwica; do weryfikacji | brak zapisanego rozrzutu | Cebula, Cukinia, Czosnek, Kapusta pekińska, Papryka czerwona, Pomidor, Szczypiorek, Ziemniak, Pieczarki, Ogórek kiszony, Kukurydza konserwowa, Przecier pomidorowy (passata), Keczup, Majonez, Banan, Gruszka, Jabłko, Czarne jagody, Szpinak mrożony, Truskawki mrożone, Kiełbasa śląska, Pierś z drobiu, Polędwica wieprzowa, Szynka wieprzowa mielona, Wędlina wieprzowa, Jajko, Jogurt naturalny, Maślanka 1,5%, Ser ricotta, Skyr, Śmietana, Ser mozzarella, Ser cheddar, Ser camembert, Orzechy włoskie, Orzechy pekan, Chleb żytni, Makaron pełnoziarnisty, Mąka orkiszowa jasna, Oliwa z oliwek, Cynamon, Erytrytol, Miód, Czekolada ciemna (60-69% kakao) |

## Ostrzeżenia i błędy

| Poziom | Kod | Dotyczy | Opis |
|---|---|---|---|
| uwaga | catalog | katalog | Seed demo ma inną miarę: „Cebula” ma miarę piece, a demo definiuje ją jako mass. NIE importuj paczki do bazy z seedem demo (produkt zostałby reużyty z demo). |
| uwaga | catalog | katalog | Seed demo ma inną miarę: „Pomidor” ma miarę piece, a demo definiuje ją jako mass. NIE importuj paczki do bazy z seedem demo (produkt zostałby reużyty z demo). |
| uwaga | catalog | katalog | Seed demo ma inną miarę: „Oliwa z oliwek” ma miarę mass, a demo definiuje ją jako volume. NIE importuj paczki do bazy z seedem demo (produkt zostałby reużyty z demo). |
| uwaga | mentioned_not_listed | Spaghetti | Instrukcja wspomina „Pomidor”, a składnika nie ma na liście. |
| uwaga | mentioned_not_listed | Makaron ze szpinakiem | Instrukcja wspomina „Czosnek”, a składnika nie ma na liście. |
| uwaga | empty_instructions | Koktajl jagodowy | Przepis ma pustą instrukcję. |
| uwaga | mentioned_not_listed | Grzanki z pieczarkami | Instrukcja wspomina „Czosnek”, a składnika nie ma na liście. |
| uwaga | mentioned_not_listed | Grzanki z pieczarkami | Instrukcja wspomina „Szynka wieprzowa mielona”, a składnika nie ma na liście. |
| uwaga | mentioned_not_listed | Jogurt z orzechami i miodem | Instrukcja wspomina „Orzechy włoskie”, a składnika nie ma na liście. |

## Wgrywanie paczki (robi właściciel, nie agent)

Paczka ma zakres `user`; przepisy wejdą jako `household` konta wczytującego. Wgrywa się ją w Ustawieniach („Kopia danych rodziny”) albo w `/admin/dane`.

Produkty trafiają jako `unverified`; powtórne wczytanie tej samej paczki niczego nie dubluje (produkty po nazwie, przepisy po nazwie — D22).
