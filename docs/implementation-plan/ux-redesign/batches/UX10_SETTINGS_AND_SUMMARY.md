# UX10 Ustawienia, podsumowanie i ekrany pomocnicze

Priorytet P1 · rozmiar M · zależność UX07 · równolegle z UX08/UX09.

## Cel

Dokończyć spójność aplikacji, zachowując poprawne znaczenie danych i operacji administracyjnych. Kontekst: UstawieniaPage, StatystykiPage, LoginPage, admin, charts, SklepySection, architektura 06/07 i ADR-013/016.

## Zadania

- [x] UX10.1 Podzielić ustawienia na Rodzina / Moje cele / Zakupy / Dane. Rozdzielić osoby, dla których gotujemy, od kont z dostępem. Zachować dezaktywację/usuwanie profilu, cele historyczne i progi użytkownika.
- [x] UX10.2 Umieścić sklepy i kolejność kategorii w Zakupach. Zachować alternatywę strzałkami dla przeciągania. Konfiguracja tur korzysta z komponentu UX05, bez drugiej kopii logiki.
- [x] UX10.3 Umieścić statystyki w Podsumowaniu Planu. Zachować własne SVG, zakres do 92 dni, luki dla braku planu, historyczną linię celów, średnie i niepełne dane. Nie prezentować agregacji rodzinnego planu jako bilansu wybranej osoby.
- [x] UX10.4 Zgodnie z kontraktem UX03 rozdzielić „wartości całego planu” od „mojego celu”. Jeśli semantyka porównania nie jest jednoznaczna, zachować odczyt historycznych danych/ustawień, ale ukryć ocenę realizacji indywidualnego celu i wyjaśnić powód. Nie wymyślać powiązania konta z profilem po imieniu.
- [x] UX10.5 Kopia danych rodziny i administracja zachowują rzeczywisty zakres importu/eksportu i ostrzeżenia. Ujednolicić wygląd logowania/admin bez dodawania nowych metod logowania, uprawnień czy dekoracyjnego chaosu.

## Pliki

`pages/UstawieniaPage.vue`, `StatystykiPage.vue`, `LoginPage.vue`, `pages/admin/*.vue`, `components/domain/SklepySection.vue`, StoreCategoryOrderEditor, komponenty charts i ich testy. Nie zmieniać routera, auth ani transferowego API bez uzgodnienia O. `lib/texts.ts` rezerwowane sekwencyjnie. Nie dodawać bibliotek wykresów.

## Kryteria i testy

Handoff UX06: `auth.setUser(next, ticket)` wymaga ticketu generacji pobranego
przed mutacją. Zachować ochronę spóźnionych callbacków ustawień/eksportu
oraz osobne QueryClient dla chronionych generacji. Router zachowuje bezpieczny
lokalny `next` po ponownym potwierdzeniu sesji, z ponowną kontrolą roli;
nie zastępować tego bezwarunkowym powrotem do planu. Testy wypełniające
hasło używają `e2e/secret-password.ts` i jawnego `trace: 'off'`.

Użytkownik odnajduje każdy wcześniejszy formularz ustawień. Konto i profil osoby są jasno rozróżnione. Brak planu nie staje się zerowym spożyciem. Wykres i legenda nadal opisują właściwą jednostkę. Nie zmienia się zakres kopii danych rodziny, prawa USER/ADMIN ani identyfikatory encji przez przestawienie zakładek.

`task check`; `statystyki.spec.ts`, `retail-stores.spec.ts`, `households.spec.ts`, `transfer.spec.ts`, smoke logowania/admin. `households.spec.ts` wykonuje się w kolejności przewidzianej konfiguracją E2E; nie równolegle z tworzeniem danych innych kart. Test błędu zapisu, klawiatury i długich nazw.

Skills: Required SKILL-FE, SKILL-CALC dla statystyk, SKILL-SEC; Review SKILL-REVIEW, SKILL-SECREV. Dokumentacja: faktyczne sekcje ustawień, ograniczenie bilansu osoby i zachowana semantyka wykresów.

## Odbiór 2026-10-31

Źródło autora `95d066b` (po `c59afd7`), korekta wydajności `8d709295`,
jednorazowy tekst o braku celu obowiązującego dzisiaj i helpery O.
Ustawienia zachowują wszystkie formularze i ochronę generacji sesji.
Podsumowanie rozdziela cały plan i historyczne cele konta; nie ocenia
realizacji indywidualnego celu. Refetch pokazuje błąd także przy cached-empty.

- `task check DB_TEST_RUNTIME=linux`: PASS675 unit /300 integration /
  460 API /879 FE (91plików), typy/lint/format/build/OpenAPI PASS.
  Dodatkowy wymuszony `npm run typecheck -- --force` PASS.
  PWA95wpisów/1234,00KiB. Log `backend/data/ux10-results/check-final-2.log`.
- Pełny, niezawężony `task test-e2e-linux`: PASS47/10jawnych opt-in SKIP,
  2,6min; obejmuje households, transfer, statystyki, sklepy, logowanie,
  granicę ADMIN/USER oraz nowy scenariusz ustawień390/1024.
- Visual-final1: PASS1/41,7s,165PNG na360/390/768/1024/1440,
  `backend/data/ux-baseline/screenshots-ux10-final1`. Admin-visual1:
  PASS1/2,8s,16PNG czterech ekranów390/1024, wyłącznie rzeczywiste odczyty.
  Niezależny Sol faktycznie obejrzał48końcowych PNG i13wcześniejszych,
  w tym wszystkie zmienione stany UX10 i administrację; nie deklarujemy
  ręcznego obejrzenia wszystkich165w tym review.
- Niezależny review Sol źródła, domeny, bezpieczeństwa, helperów,
  dokumentacji i obrazów: bez otwartych P0–P3, zgodnie z D35.
  Nie deklarujemy niedostępnych builtin review. Audyty zależności zachowują
  zastane alerty BE42/FE44; grafy zależności bez zmian.

Pierwszy przebieg E2E był czerwony45PASS/1FAIL/10SKIP/1niewykonany.
Włączenie households uruchomiło cały projekt chromium jako zależność.
8196–8200istniejących tur powodowało synchroniczny render ponad32tys.
przycisków i blokowało UI mimo szybkich odpowiedzi API. Izolowany probe
zachowany. Nowy test RED:8196wierszy/10,65s zamiast20; poprawka pokazuje
początkowo20tur i ręcznie kolejne, zachowując cały cache/CRUD/globalne
pozycje oraz ukrytego sąsiada. To nie wirtualizacja ani limit danych.
Pięć regresji i końcowe E2E są zielone; scenariusz sklepu trwa1,6s.
Historia użytkownika nie została usunięta ani skrócona.

Dowody i czerwone przebiegi zachowane w `backend/data/ux10-results`.
Skan pięciu raportów:0dokładnych lokalnych sekretów i tokenowych URL po
redakcji2pochodnychHTML; SHAmanifest i wyniki/załączniki zachowane.
Jedna lokalna integracja UX10; bez pushu, deployu i operacji produkcyjnych.
