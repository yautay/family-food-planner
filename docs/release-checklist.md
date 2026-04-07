# Release Checklist

## Delivery Status (Phases 1+2, Sprints A-D)

- [x] Phase 1 (backend testability): `createApp` extracted (`src/app.js`), bootstrap simplified (`server.js`), DB made configurable through `DATABASE_PATH` (`src/db/catalog.js`, `src/db/client.js`).
- [x] Phase 1 (tests): auth/RBAC integration tests added (`tests/integration/auth-rbac.integration.test.js`), `test:integration` script added in `package.json`.
- [x] Phase 2 (backend): shopping list generator endpoint from meal plan added (`src/routes/shopping-list.route.js`), aggregation logic + `servings` multiplier implemented (`src/controllers/shopping-list.controller.js`).
- [x] Phase 2 (tests): shopping list generator integration tests added (`tests/integration/shopping-list-generator.integration.test.js`).
- [x] Phase 2 (frontend): store action + UI button integrated (`src/stores/mealPlannerStore.js`, `src/views/MealsView.vue`).
- [x] Documentation updated continuously (`README.md`).
- [x] Planner flow migrated to custom-only day slots (live/template mode removed in planner UI and persisted data).
- [x] Favorite-day overflow selection modal added (when imported meals exceed slot count).
- [x] Drag-and-drop meal ordering added in day builder.
- [x] Day-slot clock UX added (analog icon + digital tooltip on hover/focus).
- [x] Day summary row in planner matrix updated (compact ASCII presentation).
- [x] Day titles added in planner (editable per day and visible in first matrix row).
- [x] Meal portions model added (`day_plan_meals.portions`, `meal_plan_day_slot_meals.portions`) with effective-servings formula.
- [x] Shopping-list generator updated to use effective servings from plan portions + meal portions.

## Remaining Steps

- [x] Run validation in an environment with Node/npm:
  - [x] `npm run test:integration`
  - [x] `npm run test:unit`
  - [x] `npm run build`
- [ ] Manual UI smoke test:
  - [ ] Create a meal plan.
  - [ ] Add entries with different `servings` values.
  - [ ] Generate a shopping list from the plan.
  - [ ] Verify quantity sums and `custom_name` items.
- [x] Rename import directory from `tmp/` to `core_recipes/` and update references.

## UI / CSS Status

- [x] UI has updated styling with theme support (light/dark/system).
- [x] UI uses Bulma as CSS framework.
- [x] Font: `Manrope` from Google Fonts (`src/assets/base.css`).
