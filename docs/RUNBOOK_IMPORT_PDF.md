# RUNBOOK — ręczne uruchomienie stacku i import ośmiu jadłospisów

Procedura dla WŁAŚCICIELA, nie dla agenta wykonującego batch. Kroki 1–4 robi
się raz, krok 6 powtarza się osiem razy. Liczby w tabeli pochodzą z parsera
uruchomionego na plikach z `data/source_pdfs/`, nie z szacunku.

Wymagane na hoście: **Docker Desktop, uv, Node 22+, go-task**.

## 1. Napraw port bazy w `.env`

Port **5432 zajmuje kontener innego projektu** (`netqarner-dev-db`), a `.env`
celuje właśnie w niego. Baza dev tego projektu stoi na **5434**. Zmień TYLKO
numer portu w dwóch linijkach — nie przepisuj całych wartości, bo w
`DATABASE_URL` siedzą poświadczenia.

```
POSTGRES_PORT=5434
DATABASE_URL=postgresql+psycopg://…@127.0.0.1:5434/ffp
```

**Pułapka**: bez tej poprawki `task dev` zderzy się o port, a narzędzia
uruchamiane z hosta (`task create-admin`, `task db-seed-demo`,
`task db-migrate`) połączą się z CUDZĄ bazą i padną na
`password authentication failed for user "ffp"`. Komunikat nie mówi nic
o porcie, więc łatwo szukać w złym miejscu.

Alternatywa bez ruszania `.env`: `POSTGRES_PORT=5434 task dev` — ale wtedy
narzędzia hosta i tak trafiają w 5432 i operacje na bazie trzeba robić przez
`docker exec ffp-dev-app-1 …`.

## 2. Podnieś stack

```bash
cp .env.example .env   # tylko gdy .env jeszcze nie istnieje
task install
task dev
```

Pierwsze uruchomienie buduje obrazy (kilka minut). Po starcie działają:

- <http://127.0.0.1:5173> — aplikacja,
- <http://127.0.0.1:8000/api/v1/health> — backend, ma zwrócić `{"status":"ok"}`,
- `127.0.0.1:5434` — baza dev, `127.0.0.1:5433` — baza testów.

`task logs` podgląda logi, `task down` zatrzymuje wszystko.

## 3. Sprawdź, że schemat jest aktualny

```bash
task db-heads    # oczekiwane: 0015 (head) — dokładnie jedna głowa
task db-migrate  # dociąga migracje, gdy czegoś brakuje
```

Dwie głowy albo numer niższy niż `0015` znaczą, że baza jest starsza niż kod.

## 4. Załóż konto administratora i zaloguj się

Konto powstaje **tylko tą komendą** — hasła nie ma ani w repozytorium, ani
w seedzie (07_SECURITY §2). Polecenie pyta o e-mail i hasło (min. 10 znaków):

```bash
task create-admin
```

`create-admin` jest idempotentne: zajęty e-mail kończy się komunikatem, nie
awarią — na drugie konto podaj inny adres.

Wejdź na <http://127.0.0.1:5173/import>; guard przerzuci Cię na ekran
logowania i po zalogowaniu wróci tam, gdzie chciałeś.

**Limit prób**: logowanie ma 5 prób na minutę z jednego adresu. Po kilku
pomyłkach dostaniesz odmowę na minutę — to zabezpieczenie, nie awaria.

## 5. (Opcjonalnie) włącz asystę AI

Bez klucza import działa w 100% — znika tylko przycisk „Zaproponuj z AI”.
Z kluczem dostajesz propozycje dopasowań, wykrywanie duplikatów przepisów
i podpowiedź liczby porcji; **każda wymaga Twojego potwierdzenia**, AI niczego
nie zapisuje (ADR-011).

```
# .env
ANTHROPIC_API_KEY=sk-ant-…
```

```bash
docker compose --env-file .env -f docker/compose.dev.yml restart app
```

Do modelu idzie wyłącznie treść wyciągnięta z PDF-a i nazwy produktów
z katalogu — nigdy e-mail, nazwa rodziny ani cudze przepisy (decyzja D5).

## 6. Przerób osiem plików

Pliki leżą w `data/source_pdfs/`. Zacznij od `dieta.pdf`: jako jedyny ma
przepis wieloporcjowy z jawnie podaną liczbą porcji i dobrze na nim zobaczyć,
jak to wygląda.

1. Na `/import` przeciągnij plik. Job kończy jako **Sparsowany** i sam otwiera
   raport odczytu.
2. Kliknij **Przejdź do review**.
3. Na górze wybierz, **kto ma widzieć te przepisy** — raz dla całego pliku,
   nie przy każdym daniu.
4. Przejdź składniki. Każdy ma trzy drogi: **Potwierdź** gotową propozycję,
   wybierz produkt **wyszukiwarką**, albo **Utwórz nowy** (produkt powstanie
   dopiero przy zatwierdzeniu).
5. Gdzie ekran pyta **„Na ile porcji jest ten przepis?”** — wpisz liczbę. To
   jedyne, czego dokument nie mówi, a bez czego nie wiadomo, ile waży talerz.
6. Gdy lista blokad jest pusta — **Zatwierdź import**. Zobaczysz podsumowanie:
   ile przepisów, ile nowych produktów, ile nauczonych przeliczników.

Pytanie o porcje pojawia się **tylko w czterech miejscach w całym korpusie**
— to posiłki cięższe niż 800 g, przy których dokument nie podaje liczby porcji
(01_PDF_AUDIT §5.1).

| Plik | Dni | Dania | Składniki | Zapyta o porcje |
|---|---:|---:|---:|---|
| `dieta.pdf` | 3 | 13 | 85 | nie |
| `dieta (1).pdf` | 3 | 14 | 87 | nie |
| `dieta (2).pdf` | 3 | 12 | 68 | nie |
| `dieta (3).pdf` | 3 | 12 | 71 | **Środa · OBIAD** |
| `dieta (4).pdf` | 3 | 12 | 77 | nie |
| `dieta (5).pdf` | 3 | 14 | 92 | **Pon · ŚNIADANIE**, **Wt · KOLACJA** |
| `dieta (6).pdf` | 3 | 12 | 85 | nie |
| `dieta (7).pdf` | 3 | 14 | 97 | **Pon · KOLACJA** |
| **Razem** | **24** | **103** | **662** | **4 pytania** |

### Trzy rzeczy, które zobaczysz i które są w porządku

- **„Nie można zweryfikować — produkty bez wartości odżywczych”** przy
  kaloriach. Normalne przy pierwszym imporcie: świeżo założone produkty nie
  mają jeszcze wartości. Porównanie ruszy po kroku 7.
- **Ucięta nazwa dania** — w korpusie trzy tytuły zawijają się między kolumnami
  PDF-a i parser świadomie ich nie zgaduje (errata 01_PDF_AUDIT §9.5,
  np. „Pizza na tortilli z szynką, pomidorkami i”). Pole nazwy jest edytowalne;
  pełne brzmienie stoi na stronie podsumowania w samym PDF-ie.
- **Ten sam produkt w kilku plikach** — drugi raz dopasuje się sam, bo pierwszy
  import wprowadził go do katalogu. Im dalej, tym mniej klikania.

**Gdy „Zatwierdź” jest nieczynny**: nad przyciskiem stoi lista blokad z nazwą
dania i powodem. Dwa powody są możliwe — składnik bez wskazanego produktu albo
nierozstrzygnięta liczba porcji. Uzupełnij i przycisk odblokuje się sam.

## 7. Uzupełnij wartości nowym produktom

Produkty założone importem powstają jako **niezweryfikowane** i nie mają
kalorii ani makro (02_DOMAIN §4.9). Dopóki ich nie uzupełnisz, przepisy
pokazują ostrzeżenie „niepełne dane”, a plan dnia nie policzy sum.

Kolejka czeka na <http://127.0.0.1:5173/admin/weryfikacja>, najstarsze na
górze. Po ośmiu plikach będzie w niej rzędu stu kilkudziesięciu pozycji —
warto rozłożyć to na kilka podejść i zacząć od produktów, które wracają
najczęściej.

Wartości wpisuje się na 100 g (albo na 100 ml dla produktów płynnych). Indeks
glikemiczny jest opcjonalny — bez niego wszystko liczy się dalej, tylko ładunek
glikemiczny zostanie oznaczony jako niepełny.

## 8. Awaryjnie — reset bazy dev do czystego stanu demo

Kasuje **wszystkie** dane: importy, przepisy, plany, listy zakupowe i konta.
Zostawia schemat i seed demo. Operacje idą przez kontener, bo baza dev słucha
na 5434.

```bash
docker exec ffp-dev-app-1 alembic downgrade base
docker exec ffp-dev-app-1 alembic upgrade head
docker exec ffp-dev-app-1 python -m scripts.seed_demo   # produkty i sklepy
task create-admin                                       # konto musi wrócić…
docker exec ffp-dev-app-1 python -m scripts.seed_demo   # …bo przepisy potrzebują właściciela
```

Seed uruchamia się **dwa razy** celowo: produkty i sklepy nie mają właściciela
i wchodzą od razu, a przepisy oraz plan dnia potrzebują istniejącego konta
ADMIN.

Po resecie w `backend/data/uploads/` zostają osierocone pliki PDF — baza już
ich nie zna. Można je skasować ręcznie; katalog nie jest wersjonowany.
