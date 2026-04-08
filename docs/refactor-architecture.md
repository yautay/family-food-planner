# Refactor Architecture Guide

## Frontend module boundaries

- `src/components/planning`: UI blocks for meal-day planning flows.
- `src/composables/planning`: planning-specific state helpers (metrics, drag and drop).
- `src/components/shared`: reusable primitives shared across views.
- `src/utils`: framework-agnostic transformation helpers (sorting, formatting, cloning).
- `src/components/layout/header`: isolated header menu panels.

## Backend/module boundaries

- `src/controllers/helpers`: parsing and normalization used by multiple controllers.
- `src/services/mealPlannerApi.js`: API adapter used by `mealPlannerStore`.
- Controllers stay focused on request orchestration and domain flow.

## Size targets

- Vue views: up to 350 LOC.
- Vue components: up to 250 LOC.
- Stores/controllers: up to 300 LOC where feasible.

## Refactor checklist

- Keep domain logic in composables or utilities when reused by multiple screens.
- Keep modal layout and filtering behavior in shared primitives.
- Keep duplicated parser/normalizer functions in shared backend helpers.
- Keep each commit scoped to one domain slice for safer rollback.
