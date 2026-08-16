# ADR-007 — shadcn-vue + TanStack Query; Pinia tylko dla stanu UI; bez i18n

Status: ACCEPTED (2026-08-16)

## Kontekst
Wymagane: Vue 3 + TS + Vite + Tailwind + Pinia, bez Nuxta; preferencja
właściciela: shadcn-vue (charakter zgodny z wizualizacją). Aplikacja PL-only
(decyzja właściciela 2026-08-16).

## Decyzja
- Komponenty: shadcn-vue (reka-ui) generowane do `components/ui`,
  theming przez tokens z 06_UIUX; ikony lucide-vue-next.
- Stan serwera wyłącznie w TanStack Query (cache, invalidation, optimistic);
  Pinia tylko UI state (auth, kolejka offline, szkice). Zakaz kopiowania
  odpowiedzi API do stores.
- Formularze: vee-validate + zod. Typy API generowane z OpenAPI.
- Bez warstwy i18n — stringi PL w komponentach; teksty wielokrotnego użytku
  w `src/lib/texts.ts`.

## Konsekwencje
+ Mniej boilerplate'u w każdym batchu UI (netQArner płaci i18n ×3);
  spójny wygląd z wizualizacją bez walki z gotową biblioteką.
− Ewentualna przyszła wielojęzyczność = osobny, duży refaktor (świadomie
  zaakceptowane — aplikacja domowa).

## Uwaga implementacyjna (2026-08-16, BATCH_01 — nie zmienia decyzji)
Paczka `lucide-vue-next` została przez autorów zdeprecjonowana na rzecz
`@lucide/vue` i to jej używa dzisiejsze shadcn-vue. Biblioteka ikon pozostaje
ta sama (lucide) — zmienia się wyłącznie nazwa pakietu npm. W repo jest
`@lucide/vue`.
