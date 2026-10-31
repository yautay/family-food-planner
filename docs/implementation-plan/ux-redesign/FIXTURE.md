# Powtarzalny zestaw UX00

Narzędzie `backend/scripts/ux_baseline.py` przygotowuje rzeczywiste dane przez
routery API uruchomione lokalnie (`httpx.ASGITransport(create_app(settings))`).
Korzysta z normalnych sesji, CSRF, walidacji, autoryzacji, serwisów, silników
Decimal i pipeline'u uploadów. Nie podmienia odpowiedzi dla przeglądarki.
Nie tworzy schematu bazy i nigdy nie usuwa istniejących danych.

## Środowisko i uruchomienie

Wymagane są migracje i istniejący ADMIN E2E. O rezerwuje całe środowisko na
czas seedu, `task check` i E2E; tych operacji nie uruchamiamy równolegle.
Skrypt wymusza `APP_ENV=dev|test`, PostgreSQL na `localhost`, `127.0.0.1` lub
`::1`, bazę **dokładnie** `pasnik_ux` albo `pasnik_ux_test` i brak parametrów
URL mogących nadpisać host. Nie ma opcji wyłączenia bramek.

Ignorowany lokalny `.env` zawiera normalną konfigurację aplikacji oraz
`E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD` i `UX_BASELINE_PASSWORD` (min. 12 znaków).
Ostatnie hasło służy wyłącznie czterem fikcyjnym kontom fixture; nie jest nowym
ustawieniem runtime aplikacji. Hasła nie są argumentami komendy ani częścią
manifestu. Nie używać tych kont poza izolowaną instancją.

Target Taskfile, którego właścicielem jest O:

```yaml
ux-baseline:
  dir: backend
  cmds:
    - uv run python -m scripts.ux_baseline {{.CLI_ARGS}}
```

Po rezerwacji środowiska, z korzenia repo:

```powershell
task ux-baseline -- --photo data/ux-baseline/food.jpg
# Ten sam plik i ta sama konfiguracja: drugi przebieg reużywa ID.
task ux-baseline -- --photo data/ux-baseline/food.jpg
```

Ścieżka `--photo` jest względem `backend/`. Można podać ścieżkę absolutną.
Plik, manifest i obrazy są pod `backend/data/ux-baseline/`, już ignorowanym
przez Git. Nie kopiować tam danych produkcyjnych ani prywatnych zdjęć.

Zdjęcie testowe: [Red Apple.jpg](https://commons.wikimedia.org/wiki/File:Red_Apple.jpg),
Abhijit Tembhekar, 2009, [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/).
[Oryginał pliku](https://upload.wikimedia.org/wikipedia/commons/1/15/Red_Apple.jpg)
został dostarczony lokalnie przez O; skrypt niczego nie pobiera. Źródłowy plik
pozostaje niezmieniony, a aplikacja standardowo dekoduje i ponownie koduje
upload oraz tworzy miniaturę. Fotografia przedstawia jabłko i jest wyłącznie
testem zdjęcia; nie stanowi fotografii fikcyjnej zapiekanki. Przy udostępnianiu
zrzutów zawierających zdjęcie zachować tę atrybucję i informację o zmianie
rozmiaru/kodowania przez aplikację.

## Zawartość i kontrakt dat

Prefiks: `UX00 kontrakty v1`. Konta `ux00-a1@example.com`, `ux00-a2@example.com`,
`ux00-b1@example.com`, `ux00-solo@example.com` to fikcyjne adresy w domenie
przykładowej. A1/A2 należą do Domu A, B1 do Domu B, solo nie ma rodziny.
ADMIN E2E jest operatorem i właścicielem przepisu globalnego; nie jest
przenoszony do rodziny fixture. Zwykłe E2E może więc zmieniać własną rodzinę
administratora bez odpinania profili zestawu UX00.

| Dane | Wartość |
|---|---|
| Profile A | Łucja, Michał, Żaneta, każdy mnożnik `1.10`; osobny Błażej w B |
| Produkty | 55 numerowanych nazw, masa/objętość/sztuki, pełna nutrition i jeden produkt z brakami, łyżka = `10` g |
| Przepisy | 55 widocznych dla A1, w tym prywatny, rodzinne i globalny; osobny prywatny A2 niewidoczny A1 |
| Warianty | Prawdziwe zdjęcie / brak zdjęcia, długa polska nazwa, czasy `30`/`31`/null, niepełna nutrition |
| Tagi/oceny | Własny tag i systemowy tag, oceny R1: A1=`1`, A2=`5` |
| `2029-06-04` | Bez splitu: `3.30`, `[]`; produkt luzem `1.5` łyżki, dowolna nazwa posiłku i cel `600` |
| `2029-06-05` | Częściowy split: Łucja i Michał po `1.10`, razem `2.20`; Żaneta pominięta |
| `2029-06-06` | Pełny split globalnego przepisu: trzy profile po `1.10`, razem `3.30` |
| `2029-06-10` | Prawdziwy pusty dzień: wyłącznie GET, `id=null`; żadnego PUT ani posiłku |
| Spiżarnia | 105 rozróżnialnych partii na czterech produktach; dodatnie ilości i różne daty |
| Sklepy | Dwa sklepy, odwrócona kolejność dwóch kategorii, opakowania `500` i `1000` g |
| Szablony | Dzień, dwa tygodnie, cykl A→B; bez automatycznej instancjacji |
| Zakupy | Oddzielne generacje `use_pantry=false`/jawne true, jedna tura zastępcza, dwie listy |
| Lista offline | Pozycja odhaczona/przyjęta, odhaczona/nieprzyjęta i nieodhaczona; publiczny link bez tokenu w manifeście |

To jawne przesunięcie dat specyfikacji `CONTRACTS §6` z lat 2030/2031 na
**4–10 czerwca 2029**. Istniejący setup E2E usuwa dni z lat 2030+, więc nie
może objąć tych planów. Nie korzystamy z dat ani nazw z makiety. Granica
roku, archiwalny profil/przepis, wygasła lista, wiele tur i scenariusze błędów
z §6 pozostają osobnymi scenariuszami testowymi; skrypt nie zmienia zegara
serwera ani nie obchodzi API, żeby uzyskać te stany. Ilości mają stringi
dziesiętne; nutrition oraz zakupy liczy aplikacja, nie fixture.

## Wznawianie bez resetowania

`manifest.json` jest związany z hostem/portem/nazwą bazy i SHA256 zdjęcia.
Zawiera wersję, prefiks, ID, nazwy ukończonych operacji oraz ewentualną
operację `pending`; nie zapisuje payloadów, haseł, cookies ani tokenów.
Przed każdą mutacją zapisuje atomowo `pending`, po potwierdzeniu ID i stan
ukończenia. Zwykłe ponowienie pomija potwierdzone zapisy i ponownie sprawdza
rzeczywiste odczyty, ID zbiorów, profile, splity, zdjęcie i granice dostępu.

Nie usuwać manifestu, żeby „zacząć od nowa”. Dane z prefiksem bez lokalnego
wpisu blokują setup. Zajęta data blokuje zapis bez nadpisania obcego dnia.
Przy `pending` automat zatrzymuje się: operator porównuje efekt wskazanej
operacji w izolowanej instancji i uzgadnia manifest z jej faktycznym wynikiem.
Nie wolno bez sprawdzenia kasować `pending` i ponawiać POST-a; proces mógł
zostać przerwany po commicie. Nie ma purge, resetu ani rollbacku cudzych
danych. Przywrócenie całej bazy z backupu wymaga zachowania odpowiadającego
jej manifestu. Wznowienie nie odtwarza ręcznie skasowanych encji ani nie
resetuje zmian wykonanych później w UI.

Potwierdzony przypadek pierwszego przebiegu O (2026-10-30): po 182 operacjach
upload przepisu zwrócił **HTTP 405**, ponieważ pierwotny skrypt wysłał PUT,
podczas gdy kontrakt zdjęcia przepisu wymaga **POST**. Manifest zachował
`pending="photo"` i `complete=false`. O potwierdził log HTTP 405 oraz odczyt
`current_database(), id, photo_path IS NULL`: `pasnik_ux | 13 | true`.
To dowód O, nie wykonany przez autora dodatkowy odczyt bazy. Poprawka zmienia
wyłącznie metodę na POST; pozostałe metody porównano z OpenAPI/routerami.

Rekonsyliacja dotyczy tylko tego konkretnego, jednoznacznie odrzuconego
żądania. O zachowuje kopię lokalnego manifestu, sprawdza jego bazę, ID
`recipe-0`, dokładne `pending="photo"`, brak `photo` w `done` oraz brak zdjęcia
w rzeczywistym przepisie. Dopiero wtedy może jawnie zmienić samo `pending`
na null, pozostawiając wszystkie potwierdzone operacje/ID i `complete=false`,
i wznowić poprawiony skrypt z tym samym zdjęciem. Skrypt reużyje wcześniejsze
encje i wykona poprawny POST. Nie kasuje się manifestu ani danych. Ta zgoda
nie obejmuje timeoutów, HTTP 5xx ani nieznanego wyniku innej operacji: tam
nadal wymagane jest osobne potwierdzenie faktycznego efektu zapisu.

## Korekta identyfikatorów metadanych

Historyczny `Journal.write` zapisywał `DayRead.id` także pod kluczami posiłku,
pozycji przepisu i produktu luzem. UX06 wykrył to w rzeczywistym preflight
planu: dzień 34 miał posiłek 35, podczas gdy manifest wskazywał posiłek 34.
Nowy zapis wybiera rzeczywiste identyfikatory z odpowiedzi dnia; verify
porównuje je z API. Nie zmienia to istniejących planów ani podziałów.

Wyłącznie O, z rezerwacją DB/E2E, może wykonać:

```powershell
task ux-baseline -- --photo data/ux-baseline/food.jpg --repair-manifest-identifiers
```

Tryb wymaga ukończonego manifestu, potwierdza tożsamość i rodzinę A1/A2,
czyta wszystkie trzy dni obiema sesjami i sprawdza markery, właściciela,
scope, przepisy i podziały. Dopiero po wszystkich kontrolach tworzy
niepodmienialny `manifest.identifiers.bak` i atomowo zapisuje skorygowane
ID. Zachowuje `done`, `pending` i `complete`; ponowienie jest idempotentne.
Nie służy do odtwarzania ręcznie usuniętych lub zmienionych danych.

## Prawdziwe obrazy UI

`frontend/e2e/ux-visual.spec.ts` jest opt-in: bez `UX_VISUAL=1` pomijany jest
wyłącznie ten nowy test, a wymagane testy podstawowego E2E pozostają aktywne.
Przed serią zdjęć normalne `task check` i `task test-e2e` uruchamia kolejno O.
Osobną serię visual uruchamia się bez projektu setup, który wykonuje purge:

```powershell
$env:UX_VISUAL = '1'
$env:UX_VISUAL_WIDTHS = '390,1440'
$env:E2E_BASE_URL = 'http://localhost:5173'
$env:E2E_REUSE_SERVER = '1'
task test-e2e -- --project=chromium --no-deps ux-visual.spec.ts
```

Test używa własnej pustej sesji i loguje się raz na A1 przez ekran logowania.
Sprawdza tożsamość oraz nazwę rodziny. Wykonuje rzeczywiste pełne zrzuty dnia
w czterech stanach, katalogu, szczegółów ze zdjęciem/bez/globalnego, tygodnia,
startu zakupów, listy, spiżarni, edytora, podsumowania tego samego tygodnia,
produktów i ustawień. Dodatkowo fotografuje formularz produktu, publiczną
listę i pusty ekran logowania. To obrazy obecnego UI, bez porównania z
wymyślonymi goldenami i bez ingerencji w implementację ekranów.

Zrzuty PNG: `backend/data/ux-baseline/screenshots/<szerokość>-<ekran>.png`,
także załączniki raportu Playwright. Kolejna seria nadpisuje wyłącznie te
pochodne PNG; przed porównaniem UX11 O archiwizuje baseline w lokalnym
katalogu. `UX_VISUAL_WIDTHS=320,360,390,768,1024,1440` rozszerza matrycę bez
zmiany kodu. Obrazy nie zawierają paska URL, sekretów ani otwartego dialogu
udostępniania. Konto, rodzina i adresy widoczne w ustawieniach są fikcyjne.
Trace, video i automatyczne zrzuty awarii tego speca są wyłączone.

Gotowość obrazu obejmuje udane odpowiedzi rzeczywistych zapytań ekranu oraz
wyrenderowane dane fixture: posiłki i pozycje dni, trzy posiłki tygodnia,
trzy nazwane profile i historię celu, nazwy/przelicznik produktu oraz nazwę
i składniki przepisu. Podsumowanie czeka na odpowiedź dla dokładnego zakresu
4–10 czerwca i etykietę „3 z 7 dni ma plan”. Sam kontener/lista/input nie
potwierdza ukończenia pobierania. Błąd żądania UI zatrzymuje zapis zrzutu
także wtedy, gdy ekran zachował dane w cache.

Scenariusz offline pobiera własną listę online, odłącza kontekst, zmienia jeden
checkbox przez UI, fotografuje stan, przywraca sieć, sprawdza GET serwera i
reload, po czym odtwarza pierwotny checkbox. Nie przyjmuje zakupów w trakcie
testu. Reload **bez sieci** wymaga zbudowanego PWA: Vite nie cache'uje shella;
ten spec go nie udaje. Publiczny token jest odczytywany do pamięci z API,
nie trafia do manifestu, nazwy pliku ani obrazu. Serię wykonujemy na osobnej
bazie, także gdy potrzebny jest normalny E2E.

## Weryfikacja autora

Project skills BE/FE/SEC/CALC i manifest przeczytano ze źródeł w repo.
Wbudowane `/code-review` i `/security-review` są niedostępne i nie zostały
uruchomione; O rejestruje zgodę właściciela na niezależne review agentów Sol.
Autor narzędzia nie uruchamia DB, seedu, pełnego check ani E2E bez rezerwacji.
W osobnym worktree uruchomiono `task install` (PASS, bez zmian lockfile),
`task test-unit -- tests/unit/test_ux_baseline.py` (**18 passed**),
`task typecheck` (mypy **220 plików** i vue-tsc PASS), `task lint` (ruff i
eslint PASS). Testy jednostkowe obejmują odrzucenie produkcji/zdalnej/zwykłej
bazy i override hosta, wznowienie, brak tokenu w manifeście oraz blokadę
niepotwierdzonej operacji. Nie są testem wykonanego seedu ani działającego UI.
Wyniki rzeczywistego przygotowania danych i obrazów oraz odbiór UX00 zapisuje
O w `BASELINE.md`/`PROGRESS.md`; sam skrypt i ten dokument nie oznaczają
integracji karty.
