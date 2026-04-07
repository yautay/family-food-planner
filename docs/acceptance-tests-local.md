# Lokalna instrukcja testow akceptacyjnych

Ten dokument opisuje szybkie postawienie projektu lokalnie pod testy akceptacyjne
(manualne i automatyczne).

## 1. Wymagania

- Linux/macOS/WSL + `git`
- Node.js 22 (zalecane przez `nvm`)
- `npm`
- opcjonalnie: `pdftotext` (jesli chcesz importowac PDF do katalogu)

## 2. Konfiguracja Node 22

Jesli nie masz Node 22, wykonaj:

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22
nvm alias default 22
node -v
npm -v
```

## 3. Instalacja projektu

W katalogu repo:

```bash
npm ci
cp .env.example .env
```

Uwaga:

- bez poprawnych danych SMTP i Turnstile nie przetestujesz w pelni scenariuszy
  `register` i `forgot/reset password`,
- pozostale scenariusze akceptacyjne (logowanie, planner, listy zakupowe, RBAC)
  mozna uruchomic na koncie domyslnym.

## 4. Przygotowanie bazy danych

Opcja szybka (z aktualnego stanu repo):

```bash
npm run db:migrate
```

Opcja pelna (migracje + import PDF z `core_recipes/*.pdf`):

```bash
npm run db:setup
```

## 5. Uruchomienie aplikacji lokalnie

```bash
npm run dev
```

Domyslnie:

- frontend: `http://localhost:5173`
- backend API: `http://localhost:3000`

Jesli port `3000` jest zajety, uruchom:

```bash
PORT=3001 npm run dev
```

## 6. Konto testowe (seed)

Po migracjach dostepne jest konto:

- login: `yautay`
- haslo tymczasowe: `Test123!@#`

## 7. Minimalny scenariusz testow akceptacyjnych (manual)

1. Zaloguj sie jako `yautay`.
2. Wejdz na `Catalog` i sprawdz, ze lista produktow i przepisow sie laduje.
3. Wejdz na `Meals` i utworz plan (np. tydzien).
4. W sekcji dnia wczytaj ulubiony dzien i zapisz jako custom.
5. Dla jednego posilku ustaw `porcje posilku` (w ulubionym dniu) oraz sprawdz w plannerze wartosc efektywnych porcji.
6. Uzyj `Generuj liste zakupowa z planu`.
7. Zweryfikuj, ze:
   - ilosci skladnikow sa zsumowane,
   - ilosci sa przemnozone przez effective servings (`servings` override albo `portions_count * portions`),
   - wpis custom trafil na liste jako `custom_name`.
8. Wejdz na `Access control` i sprawdz podglad ACL/audit logs.

## 8. Testy automatyczne (lokalnie)

Unit:

```bash
npm run test:unit
```

Integracyjne:

```bash
npm run test:integration
```

## 9. Najczestsze problemy

1. `npm ci` zwraca blad lockfile
   - upewnij sie, ze masz aktualny branch,
   - uruchom ponownie `npm ci` po `git pull`.

2. `SyntaxError` przy starcie Vitest (np. optional chaining)
   - zwykle oznacza stary Node,
   - przelacz na Node 22: `nvm use 22`.

3. `better-sqlite3 ... compiled against a different Node.js version`
   - zaleznosci byly budowane pod inna wersje Node,
   - wykonaj:

```bash
rm -rf node_modules
npm ci
```

4. Blad SQL typu `table shopping_lists has no column named note`
   - baza jest nie po aktualnych migracjach,
   - uruchom: `npm run db:migrate`.

5. Widok planowania pokazuje tylko pierwszy blok lub API zwraca blad kolumny `portions`
   - migracje nie zostaly odpalone po pullu,
   - uruchom: `npm run db:migrate` i zrestartuj backend.
