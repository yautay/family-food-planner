# 05 — Architektura frontendu

Vue 3 (Composition API, `<script setup lang="ts">`), TypeScript strict,
Vite, Tailwind CSS 4, shadcn-vue, Pinia, TanStack Query, vue-router.
Bez Nuxta, bez i18n (UI wyłącznie PL).

## 1. Podział odpowiedzialności stanu (ADR-007)

- **TanStack Query** = cały stan serwera (fetch, cache, invalidation,
  optimistic updates). Klucze zapytań centralnie w `src/api/queryKeys.ts`.
- **Pinia** = wyłącznie stan UI/klienta: sesja użytkownika (`authStore`),
  stan szkicu generacji zakupów, kolejka offline checkboxów, preferencje
  widoku. Store NIE trzyma kopii danych serwera.
- Mutacje przez composables `useXxxMutation` z jawnym `invalidateQueries`.

## 2. Warstwa API

`src/api/client.ts` — fetch wrapper: credentials include, nagłówek CSRF
z cookie, mapowanie kształtu błędu (04_API §1) na `ApiError`, toast dla
błędów nieobsłużonych lokalnie. Typy: generowane z OpenAPI
(`task fe-types` → `src/api/generated.ts`) — ręcznych interfejsów dla
odpowiedzi API nie piszemy.

## 3. Routing i strony (zgodnie z wizualizacją UI)

```
/                     → redirect /plan-dnia
/plan-dnia/:date?     PlanDniaPage        (widok 1 wizualizacji)
/tydzien/:weekStart?  PlanTygodniaPage    (widok 4)
/przepisy, /przepisy/:id, /przepisy/:id/edytuj   (widoki 2–3)
/produkty, /produkty/nowy, /produkty/:id/edytuj   (widok 8)
/spizarnia            SpizarniaPage       (widok 6)
/zakupy               ZakupyPage — konfig tur + generacja + preview
/zakupy/listy/:id     ListaZakupowPage    (widok 5; wariant print)
/statystyki           StatystykiPage      (widok 7)
/ustawienia           UstawieniaPage      (cele, profile rodziny, sklepy, konto)
/admin/*              AdminPage (użytkownicy, rodziny, weryfikacja produktów,
                      audit, import/eksport)
/login
/l/:token             PublicznaListaPage  — POZA shellem aplikacji, bez auth
```

Guard: brak sesji → `/login` (poza `/l/:token`). Layout: `AppShell`
(sidebar desktop / bottom-nav mobile — patrz 06_UIUX).

## 4. Komponenty

- `src/components/ui/*` — wygenerowane shadcn-vue (button, card, dialog,
  drawer, input, select, tabs, badge, checkbox, tooltip, sheet, command…).
  Modyfikacje tylko przez tailwind theme tokens, nie fork logiki.
- `src/components/domain/*` — domenowe, m.in.:
  - `ProductPicker` — command palette z wyszukiwaniem; brak wyniku ⇒
    pozycja `+ Dodaj produkt "cebula"` otwierająca `ProductCreateDrawer`
    (create-in-context; po zapisie auto-wybór i powrót do edycji) — wzorzec
    obowiązkowy wszędzie, gdzie wybiera się produkt/przepis/tag/sklep.
    Stan faktyczny (BATCH_04, `components/domain/ProductPicker.vue`):
    props `modelValue: Product | ProductDetail | null`, `label?`, `limit?`
    (domyślnie 8), `disabled?`, `debounceMs?` (250; testy podają 0);
    emits `update:modelValue` i `selected(product)`. Obsługa klawiatury
    (↑/↓/Enter/Escape) i `data-testid` (`picker-input`, `picker-option-{id}`,
    `picker-create`, `picker-selected`) są częścią kontraktu — konsumenci
    (B05/B06/B08/B09) opierają na nich E2E.
  - `StorePicker` (BATCH_09, `components/domain/StorePicker.vue`) — ten sam
    wzorzec dla sklepów, z prefiksem testid `store-picker-`. Dwie świadome
    różnice wobec `ProductPicker`: lista sklepów przychodzi w CAŁOŚCI jednym
    zapytaniem i filtruje się po stronie klienta (słownik ma kilka pozycji,
    więc debounce byłby opóźnieniem bez powodu), a wśród opcji jest jawna
    pozycja „Bez sklepu" (`store-picker-none`) — wariant retail bez sklepu to
    dozwolony stan (03_DATABASE §3). Props `modelValue: Store | null`,
    `label?`, `disabled?`; emits `update:modelValue` i `selected(store)`.
  - `RetailProductCreateDrawer` (BATCH_09) — KONTRAKT dla B10/B11: props
    `{ open: boolean, canonicalProductId: number, prefillName?: string }`,
    emits `created(retailProduct)` i `close()`. Poza id produktu nie wymaga
    niczego: sposób liczenia dociąga z `/products/{id}`, a z niego wynika
    ZAWĘŻONA jednostka opakowania (g / ml / szt.).
  - `StoreCategoryOrderEditor` (BATCH_09) — kolejność kategorii w sklepie:
    natywne HTML5 DnD **plus obowiązkowe strzałki** góra/dół (06_UIUX §2).
    Komponent trzyma szkic i oddaje wynik zdarzeniem `save(categoryIds)` —
    zapis (PUT całej kolejności) należy do rodzica. Biblioteki DnD świadomie
    NIE MA: lista jest jednokolumnowa i krótka, więc trzy handlery zdarzeń
    kosztują mniej niż zależność do utrzymania.
  - `NutritionBar` / `NutritionRing` — wskaźniki wartość/cel/status.
  - `MacroSummary`, `MealCard`, `RecipeCard`, `ShoppingItemRow`
    (duży checkbox ≥44px), `LeftoverBadge` („Zostanie: 150 g").
  - `AmountInput` — ilość + jednostka, walidacja dziesiętna z przecinkiem.
- Wykresy: `src/components/charts/*` — własne SVG (ADR-013): `BarChart`
  (słupki tygodnia), `DonutChart` (makro), `TrendLine` (statystyki).

## 5. Formularze i walidacja

vee-validate + zod: schematy w `src/lib/schemas/*` odzwierciedlają reguły
backendu (min/max, wymagalność); komunikaty PL. Walidacja frontowa to UX —
prawdą jest walidacja serwera (422 mapowane na pola formularza).

## 6. PWA i offline (ADR-009)

- vite-plugin-pwa: manifest (ikony, PL, standalone), Workbox precache
  shella; strategie: `NetworkFirst` dla `/api/*` list zakupowych,
  `CacheFirst` dla statyków.
- Offline listy zakupowej: otwarta lista zapisywana do IndexedDB (idb);
  odhaczenia offline trafiają do kolejki i po odzyskaniu sieci PATCH-ują
  serwer (last-write-wins per pozycja; konflikt = wygrywa późniejszy
  `checked_at`). Wskaźnik trybu offline w UI listy.
- Publiczna strona `/l/:token` również działa offline po pierwszym
  otwarciu (ten sam mechanizm).

## 7. Konwencje jakości

- `vue-tsc --noEmit` i eslint (flat config, vue+ts) zielone = warunek DoD
  każdego batcha; vitest dla logiki composables/komponentów krytycznych.
- Dostępność: każdy interaktywny element ma etykietę (aria-label gdy brak
  tekstu); focus states Tailwind ring; kontrast wg 06_UIUX tokens.
- Formatowanie ilości: helper `formatAmount` (g→kg powyżej 1000, przecinek
  dziesiętny PL) — jedyne miejsce formatowania ilości w aplikacji.
