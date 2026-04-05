# Family Food Planner

Aplikacja web do planowania jedzenia dla rodziny, katalogowania produktow i przepisow oraz budowy list zakupowych.

## Aktualny zakres

- katalog produktow i przepisow,
- import przepisow i produktow z PDF (`tmp/*.pdf`),
- API CRUD dla przepisow (z kontrola uprawnien),
- logowanie, rejestracja, reset hasla,
- Turnstile CAPTCHA dla rejestracji i resetu hasla,
- RBAC (role + uprawnienia),
- kontekst wlasciciela przepisu,
- przepisy systemowe z importu: publiczne, tylko do odczytu,
- UI z motywami (light/dark/system) i lokalizacja PL/EN.

## Szybki start

```sh
npm install
npm run db:migrate
npm run db:import:diets
npm run dev
```

## Komendy

- `npm run dev` - frontend + backend lokalnie
- `npm run start:server` - sam backend
- `npm run db:migrate` - migracje SQL
- `npm run db:import:diets` - import PDF do katalogu
- `npm run db:setup` - migracje + import

## Wymagania

- Node.js + npm
- `pdftotext` (systemowe narzedzie CLI)

## Zmienne srodowiskowe

Skopiuj `.env.example` do `.env` i uzupelnij wartosci:

- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_FROM`
- `APP_BASE_URL`

`APP_BASE_URL` powinno wskazywac frontend (np. `http://localhost:5173`), bo tam prowadzi link resetu hasla.

## Domyslny uzytkownik

- login: `yautay`
- haslo tymczasowe: `Test123!@#`

Po pierwszym logowaniu zalecana zmiana hasla.

## Migracje i baza

### Kluczowe migracje

- `001_catalog_schema.sql`
  - `products`, `product_aliases`, `recipes`, `recipe_ingredients`
- `002_auth_rbac.sql`
  - `users`, `roles`, `permissions`, `user_roles`, `user_permissions`, `auth_sessions`, `password_reset_tokens`
- `003_recipe_acl.sql`
  - `recipes.owner_user_id`, `recipes.is_system`, `recipes.is_editable`

### Zasady dostepu do przepisow

- przepisy z `tmp` sa oznaczane jako systemowe (`is_system=1`, `is_editable=0`),
- sa widoczne dla wszystkich,
- nie mozna ich edytowac/usuwac,
- przepisy tworzone z UI maja `owner_user_id` i mozna nimi zarzadzac zgodnie z uprawnieniami.

## API

### Auth

- `GET /api/auth/captcha-config`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout` (auth)
- `GET /api/auth/me` (auth)
- `POST /api/auth/change-password` (auth)
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `GET /api/auth/access-catalog` (auth + `permissions.manage`)
- `GET /api/auth/users` (auth + `permissions.manage`)
- `PUT /api/auth/users/:id/roles` (auth + `permissions.manage`)
- `PUT /api/auth/users/:id/permissions` (auth + `permissions.manage`)

### Katalog

- `GET /api/products`
- `GET /api/products?search=<fraza>`
- `GET /api/recipes`
- `GET /api/recipes?search=<fraza>`
- `GET /api/recipes/:id`
- `GET /api/recipes/:id/ingredients`
- `POST /api/recipes` (auth + `recipes.manage`)
- `PUT /api/recipes/:id` (auth + `recipes.manage`)
- `DELETE /api/recipes/:id` (auth + `recipes.manage`)

### Istniejace CRUD

- `units`, `tags`, `ingredients`:
  - `GET` publiczny,
  - `POST/PUT/DELETE` wymaga `catalog.write`.

## Frontend

### Ekrany auth

- `/login`
- `/register`
- `/forgot-password`
- `/reset-password`
- `/account`
- `/access-control` (dla `permissions.manage`)

### Ustawienia UI

- motyw: `light`, `dark`, `system`
- lokalizacja: `PL`, `EN`

## Bezpieczenstwo

- hasla: PBKDF2 (`sha512`, iteracje)
- sesje: tokeny opaque hashowane w DB (`auth_sessions`)
- reset hasla: token jednorazowy, wygasa czasowo
- CAPTCHA: weryfikacja serwerowa Turnstile

## Ograniczenia i kolejne kroki

- dodac testy integracyjne endpointow auth i RBAC,
- dodac endpointy list zakupowych i planowania okresu,
- dodac audit log operacji administracyjnych,
- ewentualnie przeniesc z SQLite na PostgreSQL dla produkcji.
