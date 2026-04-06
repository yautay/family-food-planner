# Release Checklist

## Status wdrozenia (Etapy 1+2, Sprinty A-D)

- [x] Etap 1 (testability backend): `createApp` wydzielone (`src/app.js`), bootstrap uproszczony (`server.js`), DB przez `DATABASE_PATH` (`src/db/catalog.js`, `src/db/client.js`).
- [x] Etap 1 (testy): testy integracyjne auth/RBAC dodane (`tests/integration/auth-rbac.integration.test.js`), skrypt `test:integration` w `package.json`.
- [x] Etap 2 (backend): endpoint generatora listy z planu dodany (`src/routes/shopping-list.route.js`), logika agregacji + mnozenie przez `servings` (`src/controllers/shopping-list.controller.js`).
- [x] Etap 2 (testy): testy generatora listy dodane (`tests/integration/shopping-list-generator.integration.test.js`).
- [x] Etap 2 (frontend): akcja store + przycisk w UI (`src/stores/mealPlannerStore.js`, `src/views/MealsView.vue`).
- [x] Dokumentacja aktualizowana na biezaco (`README.md`).

## Do domkniecia

- [ ] Uruchomic walidacje w srodowisku z Node/npm:
  - [ ] `npm run test:integration`
  - [ ] `npm run test:unit`
  - [ ] `npm run build`
- [ ] Smoke test manualny UI:
  - [ ] Utworzyc plan posilkow.
  - [ ] Dodac wpisy z roznymi wartosciami `servings`.
  - [ ] Wygenerowac liste zakupowa z planu.
  - [ ] Zweryfikowac sumowanie ilosci i pozycje `custom_name`.
- [ ] Decyzja porzadkowa dla `tmp/`:
  - [x] Dodane do `.gitignore`.

## UI / CSS - stan

- [x] UI ma nowe style (custom CSS, zmienne, motywy light/dark/system).
- [x] UI korzysta z frameworka CSS: Bulma.
- [x] Font: `Manrope` z Google Fonts (`src/assets/base.css`).
