# ARBEIT - kontekst do powrotu (UI/UX)

Data: 2026-04-06

## Cel rozmowy

Uzytkownik chce przebudowac UI tak, aby kazda podstrona miala wspolny:

- header z nawigacja,
- content,
- footer,

co ma dac spojnosc kolorystyczna i UX w calej aplikacji.

## Co zostalo przeskanowane

Przeskanowano frontend, router, stores, i18n, backend API i migracje DB, plus testy integracyjne i dokumentacje.

Kluczowe pliki frontend:

- `src/App.vue`
- `src/router/index.js`
- `src/assets/base.css`
- `src/assets/main.css`
- `src/views/*.vue`
- `src/stores/*.js`
- `src/i18n/messages.js`

Kluczowe pliki backend/domena:

- `src/app.js`
- `src/routes/*.js`
- `src/controllers/*.js`
- `db/migrations/*.sql`

Kontekst produktu:

- `README.md`
- `docs/acceptance-tests-local.md`
- `docs/release-checklist.md`

## Aktualny obraz aplikacji

### Stack

- Frontend: Vue 3 + Vue Router + Pinia + Bulma.
- Backend: Express + SQLite.
- API przez `/api` (proxy w Vite).

### GLOWNE moduly biznesowe

- Katalog produktow i przepisow.
- Planner posilkow (meal plans + entries).
- Listy zakupowe (w tym generator z planu).
- Auth (login/rejestracja/reset hasla) + RBAC/ACL.

### Obecny layout (najwazniejsze pod UI)

- Shell aplikacji jest zrobiony glownie w `src/App.vue`.
- Jest wspolny header/navbar + glowny content (`<RouterView />`).
- Brakuje wspolnego footera (globalnego, stalego na podstronach).

### Nawigacja i dostep

- Globalne linki: Start, Katalog, Planer, Skladniki, Ustawienia.
- Dodatkowo konto/logowanie/rejestracja + ACL dla `permissions.manage`.
- Trasy z auth guard: `/meals`, `/account`, `/access-control`.

## Ocena spojnosci UI/UX

### Co jest juz dobre

- Istnieje globalny theme switch: `light/dark/system` (`src/stores/uiStore.js`).
- Istnieje globalny language switch: `pl/en` + `useI18n`.
- Bazowe tokeny CSS sa w `src/assets/base.css`.

### Co jest niespojne

- Brak globalnego footera.
- Widoki maja rozny poziom dojrzalosci UI:
  - bardziej nowoczesne: `CatalogView`, auth views,
  - starsze i bardziej "legacy": `UnitsView`, `TagView`, `ingredientView`.
- Mieszanie jezykow i hardcoded tekstow (nie wszystko idzie przez i18n).
- Powielone style i modale w kilku widokach (units/tags/ingredients).

## Wnioski pod przebudowe

1. Najpierw wydzielic App Shell:
   - `AppHeader` (wspolny),
   - `AppFooter` (wspolny),
   - `AppLayout` (struktura: header + main + footer).
2. Ujednolicic design tokens i spacing (globalnie, nie per-view).
3. Ujednolicic patterny stron:
   - dashboard/home,
   - lista/tabela,
   - formularz/szczegoly.
4. Potem migrowac "legacy" widoki do wspolnych komponentow i stylu.
5. Domknac i18n dla stalej nawigacji i kluczowych ekranow.

## Rzeczy krytyczne dla UX (z domeny)

- ACL i role realnie wplywaja na widocznosc akcji (to musi byc czytelne w UI).
- Planner i shopping list to core flow produktu, wiec powinny dostac priorytet UX.
- Auth flow (register/forgot/reset) ma CAPTCHA i musi pozostac prosty i czytelny.

## Proponowany start jutro

Kolejnosc planowania (koncepcyjnie, bez kodu):

1. Ustalic IA (informacyjna architekture menu + priorytety nawigacji).
2. Zdefiniowac specyfikacje App Shell (header/content/footer).
3. Ustalic tokens (kolor, typografia, spacing, states).
4. Rozpisac wzorce 3 typow podstron.
5. Dopiero potem wejsc w plan implementacji krok po kroku.

## Szybkie linki do plikow (do wznowienia)

- Layout i nawigacja: `src/App.vue`, `src/router/index.js`
- Style globalne: `src/assets/base.css`
- Widoki kluczowe:
  - `src/views/HomeView.vue`
  - `src/views/CatalogView.vue`
  - `src/views/MealsView.vue`
  - `src/views/SettingsView.vue`
  - `src/views/UnitsView.vue`
  - `src/views/TagView.vue`
  - `src/views/ingredientView.vue`
- Auth i ACL:
  - `src/views/LoginView.vue`
  - `src/views/RegisterView.vue`
  - `src/views/ForgotPasswordView.vue`
  - `src/views/ResetPasswordView.vue`
  - `src/views/AccountView.vue`
  - `src/views/AccessControlView.vue`
- Kontekst domeny: `README.md`

---

## Aktualizacja po implementacji (2026-04-06)

Zrealizowano przebudowe shella aplikacji i nawigacji z naciskiem na spojny UX, i18n oraz mobile:

1. Wydzielono wspolny shell:
   - `AppLayout` (`src/components/layout/AppLayout.vue`),
   - `AppHeader` (`src/components/layout/AppHeader.vue`),
   - `AppFooter` (`src/components/layout/AppFooter.vue`).
2. Header:
   - lewa strona: nawigacja rozwijana z ikony hamburgera,
   - struktura menu: Planowanie, Katalog (z podmenu), Ustawienia,
   - podmenu Katalog: przeglad, skladniki, jednostki, opakowania, tagi, przepisy,
   - prawa strona: ikona menu uzytkownika (logowanie/rejestracja/wylogowanie + konto/ACL).
3. Footer:
   - copyright,
   - autor,
   - repozytorium,
   - wersja + codename (z `src/config/appMeta.js`).
4. Router i nowe widoki:
   - nowe trasy: `/units`, `/tags`, `/packages`, `/recipes` (+ aliasy dla legacy `/settings/units` i `/settings/tags`),
   - nowe widoki: `PackagesView`, `RecipesView`.
5. Lokalizacja:
   - rozbudowano `src/i18n/messages.js` (PL/EN) o pelne slowniki dla shella i kluczowych widokow,
   - zaktualizowano `useI18n` o interpolacje parametrow (`{{param}}`),
   - usunieto hardcoded teksty z glownego UI i formularzy.
6. Modulowosc i wspoldzielenie:
   - wydzielono konfiguracje menu (`src/config/navigation.js`),
   - dodano wspolny komponent nawigacji sekcji katalogu (`src/components/navigation/CatalogSectionNav.vue`),
   - uproszczono i ujednolicono widoki Units/Tags/Ingredients.
7. Mobile:
   - dopracowano responsywnosc globalna (`src/assets/base.css`),
   - poprawiono zachowanie list/tabel/modali na malych ekranach.
8. Testy jednostkowe:
   - `tests/unit/i18n/messages-structure.test.js` (spojnosc kluczy PL/EN),
   - `tests/unit/i18n/useI18n.test.js` (interpolacja + fallback),
   - `tests/unit/layout/app-header.test.js` (menu nav/user),
   - `tests/unit/layout/app-footer.test.js` (metadane stopki).

Walidacja lokalna:

- `npm run test:unit` ✅
- `npm run build` ✅
