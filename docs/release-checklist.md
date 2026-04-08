# Release Checklist

## Delivery Status

- [x] API hardening enabled:
  - [x] Helmet + CSP (`src/app.js`)
  - [x] CORS allowlist via env (`CORS_ALLOWED_ORIGINS`)
  - [x] JSON payload limit via env (`API_JSON_BODY_LIMIT`)
  - [x] auth endpoint rate limiting (`src/routes/auth.route.js`)
- [x] Route-level validation enabled with Zod (`src/middleware/validate.middleware.js`, `src/validation/schemas.js`)
- [x] Backend runtime migrated to Sequelize ORM (`src/controllers/*.js`, `src/services/*.js`)
- [x] Legacy runtime DB adapter removed (`src/db/catalog.js` deleted)
- [x] DB maintenance/import scripts migrated to Sequelize (`scripts/*.mjs`)
- [x] `better-sqlite3` moved to dev-only usage (integration test helpers)

## Verification Status

- [x] `npm run test:unit`
- [x] `npm run test:integration`
- [x] `npm run db:migrate`

## Release Smoke (Manual)

- [ ] Auth flow:
  - [ ] register with CAPTCHA
  - [ ] login/logout
  - [ ] forgot/reset password
- [ ] Planner flow:
  - [ ] create meal plan
  - [ ] assign day slots / custom meals
  - [ ] verify portions/effective servings behavior
- [ ] Shopping flow:
  - [ ] generate list from meal plan
  - [ ] verify aggregation + custom_name entries
- [ ] ACL flow:
  - [ ] update user roles/permissions
  - [ ] verify audit log entries

## Operational Notes

- SQL migrations remain source-of-truth in `db/migrations/*.sql`.
- Migration execution now runs through Sequelize (`scripts/run-migrations.mjs`).
- SQLite is still the default datastore.
- Optional future step: PostgreSQL migration path for production scale.
