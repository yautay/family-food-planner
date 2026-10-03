# 02 — Model domenowy

Język domeny jest polski (nazwy encji w kodzie — angielskie). Dokument
definiuje pojęcia i reguły; fizyczny schemat: `03_DATABASE_DESIGN.md`.

## 1. Mapa modułów domenowych

```
accounts     — użytkownicy, sesje, role (ADMIN/USER)
households   — rodziny, członkostwo, profile członków (skalowanie porcji)
catalog      — produkty kanoniczne, wartości odżywcze, jednostki, kategorie,
               produkty sklepowe (retail), sklepy i profile sklepów
recipes      — przepisy/dania, składniki, tagi, oceny
nutrition    — deterministyczny silnik obliczeń (kcal/makro/IG→ŁG), cele
planning     — plan dnia, plan tygodnia, szablony, cykle, historia
pantry       — spiżarnia (stan domowy)
shopping     — silnik zakupowy, tury, listy zakupowe, publiczne linki
transfer     — kopia danych rodziny i kopia instancji (ADR-016)
audit        — dziennik istotnych operacji
```

Granice modułów = granice pakietów Pythona w backendzie (ADR-001).
Moduł może czytać encje innych modułów przez serwis, nie przez „sięganie
w tabele" (import modeli dozwolony, logika biznesowa — tylko przez serwisy).

## 2. Accounts

- **User**: login (email), hasło (argon2id), rola `ADMIN` | `USER`,
  `is_active`. Konta zakłada wyłącznie ADMIN (brak samorejestracji).
- **Session**: server-side, cookie HttpOnly; wygaśnięcie przesuwne.
- ADMIN może wszystko, w szczególności: zarządza użytkownikami, rodzinami,
  produktami kanonicznymi i ich wartościami, danymi referencyjnymi,
  importem/eksportem. USER działa w swoim zakresie + zakresie rodziny.

## 3. Households (Rodzina)

- **Household**: nazwa; tworzy i przypisuje ADMIN.
- Użytkownik należy do **maksymalnie jednej** rodziny (upraszczające
  założenie domowe; zmiana wymagałaby rewizji scope'ów — ADR-006).
- **MemberProfile** (profil członka rodziny): imię, opcjonalne powiązanie
  z kontem User (profil może istnieć bez konta — np. dzieci), domyślny
  mnożnik porcji (np. 0.8), opcjonalny dzienny cel kcal. Używany przez
  skalowanie rodzinne i cele.

### 3.1 Zakres widoczności (scope)

Encje współdzielne (Recipe, DayPlan/WeekPlan, szablony, listy zakupowe,
spiżarnia) mają scope:

- `PRIVATE` — widzi tylko właściciel (owner_user_id),
- `HOUSEHOLD` — widzą wszyscy członkowie rodziny właściciela,
- `GLOBAL` — **wyłącznie przepisy** (D32, ADR-006 aneks): widzi go każdy zalogowany
  użytkownik każdej rodziny, a zarządza nim tylko ADMIN. Pozostałe encje mają
  dwa zakresy powyżej.

Reguły:

1. Spiżarnia jest **zawsze HOUSEHOLD** (jeden stan domowy na rodzinę);
   użytkownik bez rodziny ma spiżarnię osobistą (household „wirtualny" nie
   istnieje — pantry wisi wtedy na userze; szczegół w 03).
2. Odczyt HOUSEHOLD: każdy członek. Edycja HOUSEHOLD: każdy członek
   (rodzina sobie ufa; audit log rejestruje kto zmienił). Zmiana scope'u
   i usunięcie: właściciel lub ADMIN.
   **Wyjątek — spiżarnia (D17, 2026-08-21): pozycję `PantryItem` usuwa KAŻDY
   członek rodziny.** Encja „zawsze household" (§3.1 pkt 1) nie ma scope'u do
   zmiany, a „kto dodał" jest przy niej informacją, nie przywilejem: skoro
   każdy członek może pozycję wyzerować (`amount = 0`), blokowanie mu
   usunięcia wiersza byłoby pozorną ochroną. Granica bez zmian: pozycja
   z cudzej rodziny to 404, nie 403.
3. Produkty kanoniczne, kategorie, jednostki, sklepy — **globalne**
   (wspólny słownik instancji), edycja wartości odżywczych tylko ADMIN;
   dodanie nowego produktu (inline create) może wykonać USER — produkt
   dostaje status weryfikacji `UNVERIFIED` (§4.9).
4. Produkty sklepowe (retail) — globalne, edytowalne przez USER.
5. **Przepis `GLOBAL` (D32)**: nie należy do rodziny (`household_id` NULL); odczyt —
   każdy zalogowany (lista, wyszukiwarka, picker planu, szczegół); tworzenie, edycja
   treści i zdjęcia, zmiana zakresu z/na `GLOBAL`, archiwizacja i usunięcie — wyłącznie
   ADMIN (403 dla USER-a, sprawdzane po ROLI, nie po `owner_user_id`). Użytkownik może
   „skopiować do mojej rodziny” — dostaje własny, edytowalny przepis (składniki, tagi,
   własny plik zdjęcia, bez ocen). Plany, szablony, cykle i listy zakupów używają
   przepisu globalnego bezpośrednio. Obniżenie zakresu, gdy używają go inne rodziny, to
   409; zużyty przepis wycofuje się archiwizacją (nie znika z istniejących planów).

## 4. Catalog

### 4.1 CanonicalProduct (produkt kanoniczny)

Fundament systemu. Pola: nazwa, nazwa znormalizowana (unikat), kategoria
zakupowa, bazowy typ miary (`MASS` | `VOLUME` | `PIECE`), wartości odżywcze
**na 100 g** (dla VOLUME: na 100 ml; dla PIECE: na 100 g + obowiązkowa waga
sztuki): kcal, białko, tłuszcz, węglowodany, błonnik, cukry — oraz
**indeks glikemiczny (IG, 0–110, opcjonalny)**. Metadane wiarygodności:
`nutrition_source` (tekst, np. `usda:...`, `producent:etykieta`, `manual`),
`verified_at`, `verification_status` (`UNVERIFIED` | `VERIFIED`), `is_archived`.

- Każdy przepis używający cebuli wskazuje TEN SAM produkt kanoniczny.
- Wartości odżywcze edytuje wyłącznie ADMIN; edycja trafia do audit logu.
- AI może proponować wartości/mapowania — nigdy nie zapisuje bez człowieka.

### 4.2 Jednostki i normalizacja

- Jednostki systemowe: `g`, `kg`, `ml`, `l`, `szt.`, `opak.` UI przyjmuje
  wygodne, wewnętrznie wszystko normalizowane do **g** (masa), **ml**
  (objętość), **szt.** (sztuki, z wagą sztuki produktu → gramy).
- **ProductUnitWeight** (jednostka domowa produktu): para (produkt,
  etykieta jednostki np. „łyżka", „garść", „plaster", „opakowanie") →
  gramy na 1 jednostkę + `source` + `samples_count`. Pomiar na realnych
  jadłospisach (BATCH_04) dowiódł, że gramatura jednostki jest własnością
  produktu i bywa niespójna (łyżka mąki: 5, 12 albo 15 g), więc uniwersalnej
  tabeli przeliczników nie ma. `samples_count` mówi, ile pomiarów stoi za
  medianą; od BATCH_20 podbija go wyłącznie formularz produktu — mechanizm
  uczenia się z importu odszedł razem z importerem PDF (D25).
- Prezentacja: ≥1000 g → wyświetlaj w kg (formatter frontendowy, dane
  zawsze w g/ml).

### 4.3 Kategorie zakupowe

Słownik globalny (seed z jadłospisów dietetyczki + nabiał/pieczywo/suche/
makarony-ryż-kasze/puszki-słoiki wg wymagań). Produkt ma dokładnie jedną
kategorię. Kategorie porządkowane per sklep (§4.5).

### 4.4 RetailProduct (produkt sklepowy)

Konkretny produkt z półki: nazwa, marka, opcjonalny sklep, wielkość
opakowania (gramy/ml/sztuki w opakowaniu), zdjęcie, powiązanie
z CanonicalProduct (wymagane). Np. kanoniczny „Jogurt naturalny" ↔ retail
„Pilos Jogurt naturalny 400 g". Używany przez silnik zakupowy do doboru
opakowań i wyliczania resztek.

### 4.5 Store i StoreProfile

- **Store**: nazwa (Biedronka, Lidl…) + opcjonalny kolor. Stan faktyczny po
  BATCH_09: kolor jest ETYKIETĄ tokenu z palety UI (06_UIUX §1), a nie wartością
  hex — motyw musi dać się zmienić bez migracji danych. **Logo NIE istnieje**:
  wymagałoby drugiego pipeline'u uploadu dla obrazka o zupełnie innym reżimie
  (przezroczystość, skala), a wartości UX nie wnosi ponad kolor i nazwę.
  Sklep ma też `is_archived` — usuwanie idzie wzorcem ADR-012 (409 z listą użyć,
  archiwizacja jako odwracalna alternatywa).
- Profil sklepu = uporządkowana lista kategorii zakupowych (kolejność
  fizycznego przejścia po sklepie), PODMIENIANA W CAŁOŚCI
  (`PUT /stores/{id}/category-order` z listą `category_id`). Kategorie spoza
  listy są poza profilem — silnik listy (B11) umieści je na końcu. Lista
  zakupowa sortowana wg profilu wybranego sklepu.

### 4.6 Usuwanie i archiwizacja (ADR-012)

- Fizyczne usunięcie dozwolone tylko, gdy encja nie jest nigdzie użyta
  (sprawdzenie referencji w serwisie). Jeśli użyta — HTTP 409 z czytelną
  listą „gdzie użyto" (nazwa przepisu/planu/listy).
- Alternatywa: `is_archived` — znika z wyszukiwarek i list wyboru,
  pozostaje w danych historycznych.

### 4.9 Cykl weryfikacji produktu

`UNVERIFIED` (utworzony inline przez USERA lub wniesiony kopią danych) → ADMIN uzupełnia/
sprawdza wartości → `VERIFIED`. Widoki liczące żywienie pokazują ostrzeżenie,
gdy w wyliczeniu biorą udział produkty UNVERIFIED lub bez kompletu wartości.

## 5. Recipes

- **Recipe (danie/przepis)**: nazwa, scope + właściciel, składniki,
  instrukcja (tekst), **porcja bazowa** (`base_servings`, int ≥1 — na ile
  porcji jest przepis), tagi, opcjonalny czas przygotowania (min),
  opcjonalna trudność 1–10, zdjęcie, `is_archived`.
- **RecipeIngredient**: produkt kanoniczny + ilość wpisana (liczba,
  etykieta jednostki) + **ilość znormalizowana w gramach/ml** (przeliczona
  przy zapisie — zapis odrzucany, jeśli nie da się jednoznacznie przeliczyć)
  + opcjonalna notatka („może być z puszki").
- **Tag**: słownik globalny, płaski; przypisanie N:M. Seed: śniadanie,
  obiad, kolacja, szybkie, warzywne, do lunchboxa, do zamrożenia, dzieci
  lubią. Filtrowanie list przepisów po tagach = wymaganie twarde.
- **Rating**: ocena 1–5 na parę (przepis, user), średnia widoczna na karcie —
  dla przepisu `GLOBAL` liczona ze WSZYSTKICH rodzin (UI nie pokazuje, czyje to
  oceny). Bez komentarzy/socialu.
- Wartości odżywcze przepisu NIE są przechowywane — zawsze wyliczane
  (silnik §6) per **1 porcja bazowa** = suma(składniki)/base_servings.

## 6. Nutrition (silnik obliczeń) — serce systemu, ADR-008

Czyste funkcje, `Decimal`, zero I/O, 100% pokrycia testami:

```
wartości_składnika(g, produkt)   = g/100 × wartości_100g produktu
wartości_przepisu(przepis)       = Σ składników (na całość)
wartości_porcji(przepis)         = całość / base_servings
wartości_pozycji_planu(pozycja)  = wartości_porcji × mnożnik_porcji
ŁG_składnika                     = IG_produktu × węglowodany_przyswajalne_g / 100
                                   (węglowodany_przyswajalne = węglowodany − błonnik, min 0)
wartości_posiłku/dnia            = Σ pozycji
```

- Brak IG produktu ⇒ ŁG posiłka oznaczony jako „niepełny" (suma z dostępnych
  + flaga completeness). To samo dla brakujących makro.
- Zaokrąglenia: kcal do 1, makra do 0,1 g, ŁG do 0,1 — wyłącznie na wyjściu
  (prezentacja/serializacja), nigdy w krokach pośrednich.
- **Cele**: `UserNutritionGoal` — dzienny cel kcal + opcjonalnie makra
  (g lub % energii), obowiązuje od daty (historia celów zachowana, statystyki
  liczą wg celu z dnia). Cel per posiłek: pole `kcal_target` na posiłku planu
  (i w szablonach dnia). Cel ≠ porcja: mnożnik porcji zmienia wartości,
  akcja „dopasuj porcję do celu" (jawna) proponuje mnożnik = target/kcal_porcji.
- Wskaźniki UI: aktualna wartość / cel / różnica / status
  (za mało · prawidłowo · za dużo; progi: <90% / 90–110% / >110% celu —
  konfigurowalne w ustawieniach użytkownika).

## 7. Planning

- **PlanDay**: data + właściciel/scope. Dowolna liczba posiłków.
- **PlanMeal**: nazwa (śniadanie, II śniadanie, obiad…), pozycja, opcjonalny
  `kcal_target`.
- **PlanMealItem**: przepis LUB produkt luzem (np. „Skyr 330 g")
  + **mnożnik porcji** (`servings` Decimal, domyślnie 1.0)
  + opcjonalny rozkład rodzinny: lista par (MemberProfile, mnożnik),
  wtedy `servings` = suma rozkładu. Prosty przypadek „7 porcji" = servings 7
  bez rozkładu. Zaawansowany: 2×1.0 + 2×0.8 + 2×1.3 ⇒ servings 6.2
  (BATCH_06 poprawił tu literówkę „3×1.0", która dawała 7.2 — reguła
  „suma rozkładu = servings" bez zmian, egzekwuje ją serwis planning).
- Szybkie akcje domenowe: kopiuj dzień → data/daty, kopiuj posiłek, powiel
  blok N dni (model 2+2+2 z listu dietetyczki).
- **DayTemplate / WeekTemplate**: zamrożona kopia struktury (bez dat);
  tworzone z istniejącego dnia/tygodnia lub od zera. Instancjacja = kopia
  do planu (bez live-sync).
- **WeekCycle**: uporządkowana lista WeekTemplate (A→B→C→A…) + data startu;
  akcja „zastosuj cykl na zakres dat".
- **Historia**: plany trwają bezterminowo; akcja „użyj ponownie" kopiuje
  dzień/tydzień z historii na nowe daty.

## 8. Pantry (spiżarnia)

- **PantryItem**: produkt kanoniczny (lub retail), ilość w g/ml/szt.,
  opcjonalna data ważności, opcjonalna lokalizacja (szafka/lodówka/
  zamrażarka), notatka. Operacje: dodaj / zmień ilość / wyzeruj / usuń.
- Stan bywa nieaktualny ⇒ **generator zakupów zawsze jawnie pyta**
  „Uwzględnić stan domowy?" i pokazuje w preview, co odjął. Nigdy nie
  odejmuje w tle.
- Po utworzeniu listy zakupów spiżarnia NIE jest automatycznie zwiększana
  (zakupy ≠ dostawa); opcjonalna akcja „przyjmij zakupy do spiżarni"
  z odhaczonych pozycji — świadoma, jednym kliknięciem.

## 9. Shopping

### 9.1 Pipeline (deterministyczny, ADR-008)

```
PLAN(zakres dat, osoby) → porcje → przepisy → składniki → normalizacja(g/ml)
→ agregacja per produkt → [spiżarnia? – jawne pytanie] → „mam już w domu"
→ podział na tury → dobór opakowań retail → PREVIEW (niejasności!)
→ zatwierdzenie → finalne listy (per tura)
```

### 9.2 ShoppingRound (tura) i harmonogram

- Konfiguracja per rodzina: lista tur, każda z: nazwa, dzień zakupów,
  zakres dni planu, filtr trwałości (świeże/trwałe/wszystko).
- Produkt ma flagę `perishability` (`FRESH` | `DURABLE`) na kategorii
  z możliwością nadpisania per produkt.
- Preset domyślny (z wymagań, NIE hardcode): Tura 1 (niedziela): trwałe na
  cały zakres + świeże na pierwsze 4 dni; Tura 2 (środa): świeże na resztę.

Stan faktyczny (BATCH_10, `modules/shopping/engine.py`) — jak z tej konfiguracji
powstaje podział:

- Tury konsumują zakres dat PO KOLEI (wg `position`), dwoma niezależnymi
  kursorami: trwałych i świeżych. `covers_days` przesuwa kursor trwałych,
  `fresh_days` (albo `covers_days`, gdy nie podano) kursor świeżych. Preset
  wychodzi z tego wprost: niedziela bierze trwałe na 7 dni i świeże na 4, środa
  domyka świeże na dni 5–7.
- **Ostatnie niepuste okno każdego rodzaju sięga do `date_to`.** Zakres szerszy
  niż suma okien nie może gubić dni: cicha utrata pozycji z listy jest gorsza
  niż tura kupująca o dwa dni więcej.
- Gdy ŻADNA tura nie kupuje danego rodzaju (np. wszystkie są `fresh_only`,
  a plan ma produkty trwałe), rodzaj przypada pierwszej turze — zapotrzebowanie
  musi mieć gdzie trafić.
- `shopping_weekday` (0 = poniedziałek, jak `date.weekday()`) NIE bierze udziału
  w podziale: służy do policzenia sugerowanego DNIA ZAKUPÓW, cofając się od
  początku okna tury do najbliższego takiego dnia tygodnia (nigdy w przód).
- Tura z pustym oknem zostaje w podglądzie jako pusta sekcja — „w środę nie ma
  po co jechać" jest informacją, nie błędem.

### 9.3 Opakowania i resztki

Dla pozycji z wybranym produktem retail: liczba opakowań =
`ceil(potrzeba/wielkość_opakowania)`, resztka = kupione − potrzeba,
**resztka zawsze wyeksponowana** („Zostanie: 150 g"). Brak retail = pozycja
w gramach (dozwolone); preview podpowiada dodanie produktu retail.
Bez automatycznych zamienników składników (out of scope).

Stan faktyczny (BATCH_10):

- Zapotrzebowanie i opakowania liczą się na osi PRZECHOWYWANIA produktu
  (`base_unit`: masa → g, objętość → ml, sztuki → szt.), więc opakowanie jajek
  ma 10 szt., a nie 600 g. Sprowadzeniem ilości na tę oś zajmuje się
  `catalog/units.py::to_base_amount` — jedyne miejsce, które dzieli przez
  `piece_weight_g`.
- Wybór wariantu bez decyzji użytkownika: najmniejsza resztka, remis →
  mniejsze opakowanie, drugi remis → mniejsze id (determinizm, ADR-008).
  Warianty ARCHIWALNE nie są proponowane.
- Pozycja oznaczona „mam już w domu" zostaje widoczna, ale opakowań się dla niej
  nie liczy i nie zgłasza braku wariantu — nic nie kupujemy.
- Pozycja w całości pokryta spiżarnią zostaje w PODGLĄDZIE (żeby było widać, co
  odjęto), ale nie wchodzi na finalną listę — nie ma czego kupić.

### 9.4 ShoppingList

Obiekt bazodanowy: pozycje (produkt, ilość, kategoria, tura, stan checkboxa,
`already_have`, resztka), `created_at`, `expires_at` (domyślnie +7 dni),
tura, sklep (profil sortowania), **publiczny token** (opcjonalny).
Stan checkboxów trwały (persystowany, synchronizowany z offline — ADR-009).

**Lista jest w CAŁOŚCI wynikiem generacji — pozycji nie dopisuje się ręcznie**
(decyzja właściciela **D18**, 2026-08-22). Każda pozycja ma produkt kanoniczny,
kategorię i (gdy jest wariant) opakowanie, a z tych trzech rzeczy żyją sekcje
sortowane profilem sklepu, plakietka resztki i przyjęcie zakupów do spiżarni.
Pozycja dopisana „luźnym tekstem" wypadałaby ze wszystkich trzech. Brakującą
rzecz dopisuje się do PLANU i generuje turę ponownie.

**Przyjęcie zakupów jest znaczone PER POZYCJA** (decyzja właściciela **D19**,
2026-08-22): pozycja raz przyjęta do spiżarni nie zostanie przyjęta drugi raz,
a pozycje odhaczone później dają się przyjąć normalnie. Znacznik na LIŚCIE
(„lista przyjęta") był rozważany i odrzucony — blokowałby uzasadniony przypadek
„doniosłem jeszcze dwie rzeczy z torby".

### 9.5 Publiczny link (ADR-010)

Token `secrets.token_urlsafe(32)` (256 bitów), unikat, w URL ścieżkowym;
uprawnienia: odczyt + odhaczanie (nic więcej); wygasa z listą; odwoływalny;
rate limit na endpointach publicznych; zero danych użytkownika/rodziny
w odpowiedzi (tylko treść listy). Po wygaśnięciu przyjazny ekran
„Ta lista zakupowa już wygasła lub została usunięta."

## 10. (wycofane) Importer PDF

Moduł importu jadłospisów PDF ze staging area, review i zatwierdzaniem
istniał w B15/B16 i został **usunięty w całości** decyzją właściciela **D25**
(BATCH_20, ADR-016). Numer sekcji zostaje pusty, żeby odwołania „02_DOMAIN §11"
w kartach i ADR-ach nadal wskazywały to, co wskazywały. Treść wniesiona
importerem — przepisy, produkty, przeliczniki jednostek — jest normalnymi
encjami i została w bazie.

## 11. Kopia danych rodziny i kopia instancji (transfer)

Jedyny import i eksport aplikacji (ADR-016).

- **Kopia danych rodziny** (`scope=user`, każdy zalogowany): JSON ze wszystkimi
  encjami, do których konto ma prawo, + ZIP ze zdjęciami. Zakres to
  `ScopedQuery.owned_condition` (**D26**): encje WŁASNE członka (także
  `private`) + encje rodziny o `scope=household` (także cudze) + spiżarnia
  rodziny + profile członków + własne cele i oceny + te wiersze słowników
  globalnych, do których to wskazuje. **Nie wchodzą**: prywatne encje innych
  członków ani ich cele i oceny (ADR-006 — prywatność obowiązuje wewnątrz
  rodziny).
- **Kopia instancji** (`scope=instance`, ADMIN): dodatkowo konta, rodziny
  i dziennik. Tylko ona odtwarza przypisanie danych do KONT.
- **Wczytanie SCALA**: walidacja wersji + raport DRY-RUN (co powstanie,
  co koliduje, o czym ostrzegamy) → zastosowanie w jednej transakcji.
  Dane należą do użytkownika — pełne odzyskanie bez SaaS.
- **„Użyj istniejącego" znaczy „nie ruszaj"** (D22, wdrożone w REVIEW R4):
  import reużywający wiersz pomija jego sekcje-dzieci, więc reużyty przepis nie
  dostaje drugiego kompletu składników ani reużyty dzień planu drugiego kompletu
  posiłków. Kryterium „dziecka" jest sprawdzalne w bazie: FK `ON DELETE CASCADE`
  do rodzica (ADR-012).
- **Raport mówi prawdę o scalaniu** (D24 + dług U21, BATCH_20): dzień planu
  scalany po `UNIQUE(owner_user_id, day)` dostaje zbiorcze ostrzeżenie („3 dni
  planu zostaną scalone…"), a `to_create` liczy wyłącznie wiersze, których
  `apply` naprawdę utworzy — sekcje idempotentne (`ON CONFLICT DO NOTHING`)
  i wiersze scalane są z niego wyłączone.
- **Przepisy `GLOBAL` w transferze** (D32): plik rodziny (`scope=user`) nigdy ich nie
  niesie jako globalnych — przepisy globalne wskazane przez plany i szablony konta
  dołączają się jako kopie rodziny, a import obcina `global` do `household`/`private`
  (ręcznie edytowany plik nie daje USER-owi przepisu dla wszystkich rodzin). Kopia
  instancji zachowuje `global`, o ile zmapowany właściciel jest ADMIN-em.
- **Po wczytaniu wszystko należy do konta, które wczytało** (D26): plik rodziny
  nie niesie sekcji `users`, więc przepis współdomownika dostaje nowego
  właściciela, choć zostaje widoczny dla rodziny przez `scope=household`.
  UI mówi to wprost przed kliknięciem.
- Granice i szczegóły formatu: 04_API §2, sekcja „Format eksportu transfer v1".

## 12. Audit

AuditEntry: kto, kiedy, operacja, encja, skrót zmiany (JSON before/after
dla wartości odżywczych). Zakres: zmiany nutrition data, weryfikacja
produktów, operacje admina na kontach i rodzinach, pobranie i wczytanie
kopii danych. Bez rozbudowy enterprise.

## 13. Niezmienniki systemowe (do pilnowania testami)

1. Każda ilość składnika ma jednoznaczną reprezentację w g/ml — zapis bez
   przeliczenia jest niemożliwy.
2. Wartości żywieniowe nigdy nie są cache'owane w encjach domenowych —
   liczy je silnik z jednego źródła przy każdym odczycie.
3. Zmiana mnożnika porcji w planie zmienia WSZYSTKO spójnie (kcal, makra,
   ŁG, agregaty zakupowe) — bo wszystko jest wyliczane z jednego źródła.
4. Produkt użyty w jakiejkolwiek encji nie może zostać fizycznie usunięty.
5. Publiczny endpoint listy nie zwraca żadnych danych poza treścią listy.
6. Wczytanie kopii danych niczego nie zapisuje przed potwierdzeniem raportu
   DRY-RUN, a samo zastosowanie idzie w JEDNEJ transakcji.
