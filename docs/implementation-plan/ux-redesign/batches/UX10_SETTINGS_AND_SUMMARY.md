# UX10 Ustawienia, podsumowanie i ekrany pomocnicze

Priorytet P1 · rozmiar M · zależność UX07 · równolegle z UX08/UX09.

## Cel

Dokończyć spójność aplikacji, zachowując poprawne znaczenie danych i operacji administracyjnych. Kontekst: UstawieniaPage, StatystykiPage, LoginPage, admin, charts, SklepySection, architektura 06/07 i ADR-013/016.

## Zadania

- [ ] UX10.1 Podzielić ustawienia na Rodzina / Moje cele / Zakupy / Dane. Rozdzielić osoby, dla których gotujemy, od kont z dostępem. Zachować dezaktywację/usuwanie profilu, cele historyczne i progi użytkownika.
- [ ] UX10.2 Umieścić sklepy i kolejność kategorii w Zakupach. Zachować alternatywę strzałkami dla przeciągania. Konfiguracja tur korzysta z komponentu UX05, bez drugiej kopii logiki.
- [ ] UX10.3 Umieścić statystyki w Podsumowaniu Planu. Zachować własne SVG, zakres do 92 dni, luki dla braku planu, historyczną linię celów, średnie i niepełne dane. Nie prezentować agregacji rodzinnego planu jako bilansu wybranej osoby.
- [ ] UX10.4 Zgodnie z kontraktem UX03 rozdzielić „wartości całego planu” od „mojego celu”. Jeśli semantyka porównania nie jest jednoznaczna, zachować odczyt historycznych danych/ustawień, ale ukryć ocenę realizacji indywidualnego celu i wyjaśnić powód. Nie wymyślać powiązania konta z profilem po imieniu.
- [ ] UX10.5 Kopia danych rodziny i administracja zachowują rzeczywisty zakres importu/eksportu i ostrzeżenia. Ujednolicić wygląd logowania/admin bez dodawania nowych metod logowania, uprawnień czy dekoracyjnego chaosu.

## Pliki

`pages/UstawieniaPage.vue`, `StatystykiPage.vue`, `LoginPage.vue`, `pages/admin/*.vue`, `components/domain/SklepySection.vue`, StoreCategoryOrderEditor, komponenty charts i ich testy. Nie zmieniać routera, auth ani transferowego API bez uzgodnienia O. `lib/texts.ts` rezerwowane sekwencyjnie. Nie dodawać bibliotek wykresów.

## Kryteria i testy

Użytkownik odnajduje każdy wcześniejszy formularz ustawień. Konto i profil osoby są jasno rozróżnione. Brak planu nie staje się zerowym spożyciem. Wykres i legenda nadal opisują właściwą jednostkę. Nie zmienia się zakres kopii danych rodziny, prawa USER/ADMIN ani identyfikatory encji przez przestawienie zakładek.

`task check`; `statystyki.spec.ts`, `retail-stores.spec.ts`, `households.spec.ts`, `transfer.spec.ts`, smoke logowania/admin. `households.spec.ts` wykonuje się w kolejności przewidzianej konfiguracją E2E; nie równolegle z tworzeniem danych innych kart. Test błędu zapisu, klawiatury i długich nazw.

Skills: Required SKILL-FE, SKILL-CALC dla statystyk, SKILL-SEC; Review SKILL-REVIEW, SKILL-SECREV. Dokumentacja: faktyczne sekcje ustawień, ograniczenie bilansu osoby i zachowana semantyka wykresów.
