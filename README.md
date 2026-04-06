# Family Food Planner

[![Unit Tests](https://github.com/yautay/family-food-planner/actions/workflows/unit-tests.yml/badge.svg?branch=master)](https://github.com/yautay/family-food-planner/actions/workflows/unit-tests.yml)
[![Integration Tests](https://github.com/yautay/family-food-planner/actions/workflows/integration-tests.yml/badge.svg?branch=master)](https://github.com/yautay/family-food-planner/actions/workflows/integration-tests.yml)
[![Project Status](https://img.shields.io/badge/status-in%20dev-orange)](https://github.com/yautay/family-food-planner/blob/master/docs/release-checklist.md)
[![Progress](https://img.shields.io/badge/progress-95%25-yellow)](https://github.com/yautay/family-food-planner/blob/master/docs/release-checklist.md)
[![Last Commit](https://img.shields.io/github/last-commit/yautay/family-food-planner)](https://github.com/yautay/family-food-planner/commits/master)

A web app for family meal planning, recipe/product catalog management, and shopping list generation.

## Current Scope

- product and recipe catalog,
- PDF import of recipes/products from `core_recipes/*.pdf`,
- recipe CRUD API with permission checks,
- login, registration, and password reset,
- Turnstile CAPTCHA for registration and password reset,
- RBAC (roles + permissions),
- recipe ownership context,
- imported system recipes are public and read-only,
- private period planning (`meal_plans`, `meal_plan_entries`),
- private shopping lists (`shopping_lists`, `shopping_list_items`),
- shopping list generation from meal plans (ingredient aggregation + `servings` multiplier),
- ACL audit logs (`audit_logs`),
- themed UI (light/dark/system), PL/EN localization,
- Bulma-based UI styling (global styles + form/navigation components).

## Quick Start

```sh
npm install
npm run db:migrate
npm run db:import:diets
npm run dev
```

## Commands

- `npm run dev` - frontend + backend locally
- `npm run start:server` - backend only
- `npm run db:migrate` - run SQL migrations
- `npm run db:import:diets` - import PDFs into catalog
- `npm run db:setup` - migrations + PDF import
- `npm run test:unit` - unit-test suite (excludes integration tests)
- `npm run test:integration` - auth + RBAC + shopping-list generator integration tests

## Additional Docs

- local acceptance testing guide: `docs/acceptance-tests-local.md`
- release checklist: `docs/release-checklist.md`

## Requirements

- Node.js + npm
- `pdftotext` (system CLI tool)

## Environment Variables

Copy `.env.example` to `.env` and fill in values:

- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_FROM`
- `APP_BASE_URL`
- `DATABASE_PATH` (optional, default: `database.db`)

`APP_BASE_URL` should point to the frontend app (for example: `http://localhost:5173`) because password-reset links are generated with that base URL.

`DATABASE_PATH` can be set to isolate the database (for example for integration tests).

## Default User

- login: `yautay`
- temporary password: `Test123!@#`

Changing the password after first login is recommended.

## Migrations and Database

### Key Migrations

- `001_catalog_schema.sql`
  - `products`, `product_aliases`, `recipes`, `recipe_ingredients`
- `002_auth_rbac.sql`
  - `users`, `roles`, `permissions`, `user_roles`, `user_permissions`, `auth_sessions`, `password_reset_tokens`
- `003_recipe_acl.sql`
  - `recipes.owner_user_id`, `recipes.is_system`, `recipes.is_editable`
- `004_meal_planning.sql`
  - `meal_plans`, `meal_plan_entries`, `shopping_lists`, `shopping_list_items`, `audit_logs`

### Recipe Access Rules

- recipes imported from `core_recipes` are marked as system recipes (`is_system=1`, `is_editable=0`),
- they are visible to all users,
- they cannot be edited or deleted,
- recipes created from UI are owner-bound (`owner_user_id`) and managed according to permissions.

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

### Catalog

- `GET /api/products`
- `GET /api/products?search=<query>`
- `GET /api/recipes`
- `GET /api/recipes?search=<query>`
- `GET /api/recipes/:id`
- `GET /api/recipes/:id/ingredients`
- `POST /api/recipes` (auth + `recipes.manage`)
- `PUT /api/recipes/:id` (auth + `recipes.manage`)
- `DELETE /api/recipes/:id` (auth + `recipes.manage`)

### Meal Planning (private per user)

- `GET /api/meal-plans` (auth)
- `GET /api/meal-plans/:id` (auth, owner only)
- `POST /api/meal-plans` (auth)
- `PUT /api/meal-plans/:id` (auth, owner only)
- `DELETE /api/meal-plans/:id` (auth, owner only)
- `PUT /api/meal-plans/:id/entries` (auth, replace-all, owner only)

`meal_slot` accepts: `breakfast`, `lunch`, `dinner`, `snack`.

### Shopping Lists (private per user)

- `GET /api/shopping-lists` (auth)
- `GET /api/shopping-lists/:id` (auth, owner only)
- `POST /api/shopping-lists` (auth)
- `PUT /api/shopping-lists/:id` (auth, owner only)
- `DELETE /api/shopping-lists/:id` (auth, owner only)
- `POST /api/shopping-lists/:id/items` (auth, owner only)
- `PUT /api/shopping-lists/:id/items/:itemId` (auth, owner only)
- `DELETE /api/shopping-lists/:id/items/:itemId` (auth, owner only)
- `POST /api/shopping-lists/from-meal-plan/:mealPlanId` (auth, meal-plan owner only)

Shopping-list generator behavior:

- aggregates recipe ingredients from meal-plan entries,
- multiplies ingredient quantities by `servings` for each entry,
- groups output by product and unit,
- includes non-recipe entries as `custom_name` shopping items.

### Existing CRUD

- `units`, `tags`, `ingredients`:
  - `GET` is public,
  - `POST/PUT/DELETE` requires `catalog.write`.

## Frontend

### Auth Screens

- `/login`
- `/register`
- `/forgot-password`
- `/reset-password`
- `/account`
- `/access-control` (for `permissions.manage`)
- `/meals` (auth)

### UI Settings

- theme: `light`, `dark`, `system`
- language: `PL`, `EN`

## Security

- passwords: PBKDF2 (`sha512`, iterations)
- sessions: opaque tokens hashed in DB (`auth_sessions`)
- password reset: single-use token with expiration
- CAPTCHA: server-side Turnstile verification

## Integration Tests

- run integration tests with: `npm run test:integration`,
- suite creates an isolated SQLite DB via `DATABASE_PATH`,
- Turnstile and email sending are mocked to avoid external dependencies,
- covered areas: auth, RBAC, and shopping-list generation endpoint.

## Limitations and Next Steps

- extend shopping-list generation with advanced normalization/merging rules,
- add family-level sharing for plans/lists,
- consider migration from SQLite to PostgreSQL for production.
