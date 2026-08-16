---
name: ffp-frontend
description: Kontrakt frontendu Family Food Planner — Vue 3 script setup + TS strict, TanStack Query vs Pinia, shadcn-vue, tokens Tailwind, wzorce UX (create-in-context, mobile-first, PL-only). Ładuj przed pracą nad plikami w frontend/src/**.
---

<!-- verified: 2026-08-16 (blueprint; B01 uzgadnia z rzeczywistym kodem)
     stack: Vue 3.5 · TypeScript strict · Vite · Tailwind 4 · shadcn-vue · Pinia · TanStack Query
     hierarchia: ADR i docs/architecture NADRZĘDNE wobec tego skilla -->

# FFP — kontrakt frontendu

## Podstawy

- Komponenty: `<script setup lang="ts">`, Composition API, TS strict —
  bez Options API, bez `any` (uzasadniony wyjątek = komentarz dlaczego).
- **Bez i18n** (D3/ADR-007): stringi po polsku wprost; teksty wielokrotnego
  użytku w `src/lib/texts.ts`. Nie dodawaj vue-i18n ani kluczy tłumaczeń.
- Typy API: generowane z OpenAPI (`task fe-types` → `src/api/generated.ts`).
  Ręczne interfejsy odpowiedzi API = błąd review.

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
- Kolory WYŁĄCZNIE z tokens (06_UIUX §1: krem #FAF6EF, curry #E07A2F,
  zieleń #3F7A5E, bursztyn/czerwień statusów). Statusy zawsze kolor+tekst,
  nigdy sam kolor.
- Ikony: lucide-vue-next. Formularze: vee-validate + zod
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
  AmountInput, kolejka offline); selektory E2E `data-testid`.
- `task fe-test`, `task typecheck` (vue-tsc), `task lint` zielone = warunek
  DoD. Build: `task check` obejmuje `vite build`.
