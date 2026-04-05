# family_meal_planner

Aplikacja do planowania jedzenia i zakupow dla wielu domownikow.

## Co zostalo poprawione

- Usuniety krytyczny problem niszczenia danych przy starcie serwera (`force: true`).
- Naprawione inicjalizowanie Sequelize i modele (bez cyklicznych importow).
- Endpointy API (`units`, `tags`, `ingredients`) dzialaja asynchronicznie i poprawnie czekaja na zapytania do DB.
- Dodany system migracji SQLite oparty o pliki SQL.
- Dodany katalog produktow i dan:
  - `products`
  - `product_aliases`
  - `recipes`
  - `recipe_ingredients`
- Dodany importer PDF (`tmp/*.pdf`) do automatycznego zasilania bazy produktami i daniami.

## Architektura

- Frontend: Vue 3 + Vite + Pinia (`src/views`, `src/stores`)
- Backend API: Express (`server.js`, `src/routes`, `src/controllers`)
- DB runtime: SQLite + Sequelize (istniejace API)
- Migracje i import danych: `better-sqlite3` + skrypty w `scripts/`

## Struktura katalogow

- `src/` - kod aplikacji frontend/backend
- `db/migrations/` - migracje SQL
- `scripts/run-migrations.mjs` - runner migracji
- `scripts/import-diet-pdfs.mjs` - importer diet z PDF
- `tmp/` - pliki PDF z dietami

## Schemat danych (katalog produktow i dan)

Migracja `db/migrations/001_catalog_schema.sql` tworzy:

- `products` - unikalny katalog produktow
- `product_aliases` - aliasy nazw produktow
- `recipes` - katalog dan
- `recipe_ingredients` - sklad dan (ilosc, jednostka, gramy)

Uzywane sa tez istniejace `units` (jednostki).

## Wymagania

- Node.js + npm
- Narzedzie systemowe `pdftotext` (wykorzystywane przez importer)

## Uruchomienie

```sh
npm install
```

### Development

```sh
npm run dev
```

### Start backendu

```sh
npm run start:server
```

## Migracje i import danych

### 1) Migracje

```sh
npm run db:migrate
```

### 2) Import PDF -> produkty + dania

```sh
npm run db:import:diets
```

### 3) Pelny setup DB

```sh
npm run db:setup
```

`db:setup` uruchamia migracje i import w kolejnosci.

## Endpointy API

### Katalog produktow

- `GET /api/products`
- `GET /api/products?search=<fraza>`

Przyklad odpowiedzi:

```json
[
  {
    "id": 1,
    "name": "Cebula",
    "normalized_name": "cebula",
    "default_unit_id": 2,
    "default_unit_name": "Sztuka",
    "recipes_count": 12
  }
]
```

### Katalog dan

- `GET /api/recipes`
- `GET /api/recipes?search=<fraza>`
- `GET /api/recipes/:id`
- `GET /api/recipes/:id/ingredients`

Przyklad odpowiedzi skladnikow dania:

```json
[
  {
    "id": 10,
    "recipe_id": 4,
    "product_id": 2,
    "product_name": "Papryka czerwona",
    "quantity": 0.5,
    "unit_name": "Sztuka",
    "grams": 115,
    "note": ""
  }
]
```

## Uwagi o imporcie PDF

- Importer czyta wszystkie `*.pdf` z katalogu `tmp/`.
- Dane sa normalizowane (nazwy produktow i dan).
- Receptury (`recipe_ingredients`) sa odswiezane przy kazdym imporcie.
- Produkty pozostaja w katalogu i sa uzupelniane/updatowane.

## Dalsze kroki (rekomendowane)

- Dodac walidacje requestow i testy integracyjne API.
- Dodac modul generowania list zakupowych z wybranych dan i okresu.
- Dodac auth (logowanie/rejestracja, role i uprawnienia, reset hasla).
