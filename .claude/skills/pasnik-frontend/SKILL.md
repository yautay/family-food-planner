---
name: pasnik-frontend
description: Kontrakt frontendu Paśnika — Vue 3 script setup + TS strict, TanStack Query vs Pinia, shadcn-vue, tokens Tailwind, wzorce UX (create-in-context, mobile-first, PL-only). Ładuj przed pracą nad plikami w frontend/src/**.
---

<!-- verified: 2026-08-21 (REVIEW R2 — uzgodnione z kodem po B05–B07)
     stack: Vue 3.5 · TypeScript 5.9 strict · Vite 8 · Tailwind 4.3 · shadcn-vue
            (reka-ui) · Pinia 4 · vue-router 5 · TanStack Query 5 · vitest 4
            · Playwright 1.62 · vite-plugin-pwa 1.3 · @lucide/vue · zod 3
     hierarchia: ADR i docs/architecture NADRZĘDNE wobec tego skilla -->

# Paśnik — kontrakt frontendu

## Co już stoi (BATCH_01–07)

`src/main.ts` (Pinia + VueQueryPlugin + router) · `src/router.ts` z guardem ·
`src/layouts/AppShell.vue` (sidebar + bottom-nav) · `src/lib/navigation.ts`
(jeden wpis = oba menu) · `src/pages/LoginPage.vue` (vee-validate + zod) ·
`src/stores/auth.ts` (JEDYNY store — sesja) · `src/api/{client.ts,queryKeys.ts,
generated.ts}` + moduły `auth/adminUsers/households/adminHouseholds/catalog` ·
`src/components/ui/{button,card,input}` · `src/lib/{utils,texts,decimal,format}.ts` ·
`src/assets/tailwind.css` (tokens). Alias `@/` → `src/`.

**Komponenty domenowe z B04 są OBOWIĄZKOWE do reużycia** (własny picker albo
select produktu w kolejnym batchu = błąd review):
`components/domain/ProductPicker.vue` (props `modelValue`/`label`/`limit`/
`disabled`/`debounceMs`, emits `update:modelValue` i `selected`; testid
`picker-input`, `picker-option-{id}`, `picker-create`, `picker-selected`),
`ProductCreateDrawer.vue` (create-in-context + obsługa 409 `details.existing`),
`AmountInput.vue` (`modelValue` to STRING dziesiętny; emituje też
`update:valid`). Strony: `pages/produkty/*`, `pages/UstawieniaPage.vue`,
`pages/admin/*`. Batch domenowy PODMIENIA `component` istniejącej trasy
z `PlaceholderPage`, nie dokłada nowego wpisu nawigacji.

**Dołożone w B05–B07 (też do reużycia, nie do przepisania):**
`components/domain/RecipePicker.vue` (powtarza kontrakt `ProductPickera`
z prefiksem testid `recipe-picker-`; uwaga: `recipe-picker-create` tylko
OTWIERA drawer, wybór następuje po `recipe-create-submit`) ·
`MealCard.vue`, `RecipeCard.vue`, `ServingsSplitDrawer.vue` ·
`components/domain/planning/*` (pięć dialogów + wspólny `PlanningDialog`) ·
`components/charts/{NutritionBar,DonutChart,BarChart}.vue` (własne SVG,
ADR-013 — `BarChart` jest STACKOWANY, gdy `segments` ma >1 element, i wciąga
`target` do skali; B13 go reużywa) · strony `pages/przepisy/*`,
`pages/plan-dnia/PlanDniaPage.vue`, `pages/tydzien/PlanTygodniaPage.vue` ·
`src/api/{recipes,goals,planning,templates}.ts` ·
`src/lib/{dates,nutrition}.ts` + `decimal.ts` z `sumDecimals`/`decimalsEqual`.
Katalogu `src/composables/` NIE MA i nie trzeba go tworzyć — wzorcem jest
`src/api/<moduł>.ts` + `useQuery`/`useMutation` wołane w komponencie.

## Podstawy

- Komponenty: `<script setup lang="ts">`, Composition API, TS strict —
  bez Options API, bez `any` (uzasadniony wyjątek = komentarz dlaczego).
- **Bez i18n** (D3/ADR-007): stringi po polsku wprost; teksty wielokrotnego
  użytku w `src/lib/texts.ts`. Nie dodawaj vue-i18n ani kluczy tłumaczeń.
- Typy API: generowane z OpenAPI (`task fe-types` → `backend/openapi.json`
  → `src/api/generated.ts`; oba pliki commitowane). Ręczne interfejsy
  odpowiedzi API = błąd review.
- Wywołania HTTP wyłącznie przez `apiFetch` z `src/api/client.ts` (rzuca
  `ApiError` ze `status`/`code`/`details`); gołego `fetch` w komponentach
  nie ma.

## Stan (ADR-007) — reguła najczęściej łamana przez modele

- **Stan serwera = TanStack Query** (klucze w `src/api/queryKeys.ts`,
  mutacje z jawnym `invalidateQueries`, optimistic tylko tam, gdzie karta
  batcha każe).
- **Pinia = tylko stan UI**: sesja (authStore), kolejka offline, szkice.
  Kopiowanie odpowiedzi API do store = błąd blokujący review.

## Komponenty i styl

- shadcn-vue w `components/ui/` — modyfikacje przez tokens, nie fork logiki.
  Domenowe w `components/domain/`, wykresy własne SVG w `components/charts/`
  (ADR-013 — ŻADNEJ biblioteki wykresów).
- **Przycisk nawigujący = LINK.** `<Button as-child>` + zagnieżdżony
  `<RouterLink :to="…" :data-testid="…">`. `as="router-link"` renderuje
  NIEZNANY TAG, nie link: reka-ui `Primitive` woła `h(props.as, …)`, a string
  jest dla `h()` nazwą elementu, nie komponentem — efekt to goły tekst bez
  `href`, bez nawigacji i bez roli `link` dla czytnika ekranu. Ustalenie R2:
  tak było w 9 miejscach z B04/B05, wyłapało to dopiero E2E. Strażnik:
  `src/components/ui/button/Button.spec.ts` (test na `<a href>` + skan źródeł).
- Kolory WYŁĄCZNIE przez klasy semantyczne z tokens zdefiniowanych
  w `src/assets/tailwind.css` (`bg-background`, `text-muted-foreground`,
  `bg-primary`, `border-border`…). Wartość hex w komponencie = błąd review.
  Paleta 06_UIUX §1: krem #FAF6EF, curry #E07A2F, zieleń #3F7A5E,
  bursztyn #D9A441, czerwień #C24C3B. Statusy zawsze kolor+tekst.
- Ikony: `@lucide/vue` (następca lucide-vue-next, którego shadcn-vue już
  nie używa). Formularze: vee-validate + zod
  (`src/lib/schemas/*`), komunikaty PL; 422 mapowane na pola.
- Ilości formatowane TYLKO przez `formatAmount` (g→kg ≥1000, przecinek);
  frontend nie liczy wartości domenowych na floatach — liczy backend.

## Wzorce UX obowiązkowe (06_UIUX §2–3)

1. **Create-in-context**: każdy picker (produkt/przepis/tag/sklep) przy
   braku wyniku pokazuje `+ Dodaj "…"` → drawer z minimalnym formularzem →
   zapis → auto-wybór → użytkownik wraca do przerwanego flow. Bez wyjątków.
2. Liczy się liczba kliknięć od intencji do efektu — nowy ekran pośredni
   wymaga uzasadnienia w Completion notes.
3. Puste stany: 1 zdanie + primary action. Destrukcja: dialog z
   konsekwencjami; 409 → lista „Używane w: …" z linkami.
4. Skeleton do PIERWSZEJ zakończonej odpowiedzi, potem nigdy (żadnego
   migania przy refetchu); mutacja = spinner na przycisku.
5. Wartości żywieniowe: trio wartość/cel/delta + status słowny; niepełne
   dane = plakietka z tooltipem czego brakuje.

## Mobile-first i dostępność

- Style pisane mobile-first (bazowe = telefon, `md:`/`lg:` rozszerzają).
  Bottom-nav mobile / sidebar desktop (AppShell). Cele dotykowe ≥44 px,
  checkbox listy zakupów ~48 px.
- Każdy interaktywny element bez tekstu ma `aria-label`; focus ring
  widoczny; drag&drop ZAWSZE z alternatywą przyciskową.

## Testy i jakość

- vitest dla composables/komponentów krytycznych (ProductPicker,
  AmountInput, kolejka offline). Pliki `*.spec.ts` OBOK testowanego modułu
  (`src/**/*.spec.ts` — inne lokalizacje nie są zbierane).
- E2E w `frontend/e2e/`, selektory `data-testid`; `task test-e2e`
  (jednorazowo `task e2e-install`). E2E NIE wchodzi do `task check`.
- **Izolacja danych E2E (08_TESTING §3.1, ustalenie R2)**: suita jedzie na
  bazie dev i jednym koncie, więc jest JEDNOWĄTKOWA (`workers: 1`) i loguje
  się RAZ (projekt `setup` + `storageState`). Nowy spec: własny prefiks nazw
  `E2E <obszar>`, `cleanupE2eData` w `beforeAll` I `afterAll` (afterAll biegnie
  też po failu), daty planu z lat 2030+. Nie łataj asercji, gdy przebieg pada
  na danych poprzedniego — sprzątaj. Kryterium: DWA kolejne przebiegi z tym
  samym wynikiem.
- `task check` obejmuje: fe-test, typecheck (vue-tsc), lint (eslint),
  format-check (prettier) i `vite build` — wszystkie muszą być zielone (DoD).
