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
- prywatne planowanie okresu (`meal_plans`, `meal_plan_entries`),
- prywatne listy zakupowe (`shopping_lists`, `shopping_list_items`),
- audit log zmian ACL (`audit_logs`),
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
- `npm run test:integration` - testy integracyjne auth + RBAC

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
- `DATABASE_PATH` (opcjonalnie, domyslnie `database.db`)

`APP_BASE_URL` powinno wskazywac frontend (np. `http://localhost:5173`), bo tam prowadzi link resetu hasla.

`DATABASE_PATH` mozna ustawic do izolacji bazy (np. testy integracyjne).

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
- `004_meal_planning.sql`
  - `meal_plans`, `meal_plan_entries`, `shopping_lists`, `shopping_list_items`, `audit_logs`

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
- `GET /api/auth/audit-logs` (auth + `permissions.manage`)
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

### Planowanie okresu (prywatne per user)

- `GET /api/meal-plans` (auth)
- `GET /api/meal-plans/:id` (auth, tylko owner)
- `POST /api/meal-plans` (auth)
- `PUT /api/meal-plans/:id` (auth, tylko owner)
- `DELETE /api/meal-plans/:id` (auth, tylko owner)
- `PUT /api/meal-plans/:id/entries` (auth, replace-all, tylko owner)

`meal_slot` akceptuje: `breakfast`, `lunch`, `dinner`, `snack`.

### Listy zakupowe (prywatne per user)

- `GET /api/shopping-lists` (auth)
- `GET /api/shopping-lists/:id` (auth, tylko owner)
- `POST /api/shopping-lists` (auth)
- `PUT /api/shopping-lists/:id` (auth, tylko owner)
- `DELETE /api/shopping-lists/:id` (auth, tylko owner)
- `POST /api/shopping-lists/:id/items` (auth, tylko owner)
- `PUT /api/shopping-lists/:id/items/:itemId` (auth, tylko owner)
- `DELETE /api/shopping-lists/:id/items/:itemId` (auth, tylko owner)

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
- `/meals` (auth)

### Ustawienia UI

- motyw: `light`, `dark`, `system`
- lokalizacja: `PL`, `EN`

## Bezpieczenstwo

- hasla: PBKDF2 (`sha512`, iteracje)
- sesje: tokeny opaque hashowane w DB (`auth_sessions`)
- reset hasla: token jednorazowy, wygasa czasowo
- CAPTCHA: weryfikacja serwerowa Turnstile

## Testy integracyjne

- testy integracyjne uruchamiaj: `npm run test:integration`,
- suite tworzy izolowana baze SQLite przez `DATABASE_PATH`,
- Turnstile i wysylka email sa mockowane, zeby testy nie wymagaly zewnetrznych uslug.

## Ograniczenia i kolejne kroki

- dodac testy integracyjne endpointow auth i RBAC,
- rozbudowac planner o automatyczne generowanie listy zakupowej z przepisow,
- dodac wspoldzielenie planow/list na poziomie rodziny,
- ewentualnie przeniesc z SQLite na PostgreSQL dla produkcji.
