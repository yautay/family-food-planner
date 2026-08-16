# ADR-013 — Wykresy: własne prymitywy SVG, bez biblioteki wykresów

Status: ACCEPTED (2026-08-16)

## Kontekst
Potrzeby wykresowe są małe i stałe: paski postępu, donut makro, słupki
tygodnia, linia trendu (widoki 1 i 7 wizualizacji). Biblioteki wykresów
ciągną zależności i własny theming, gryzący się z tokens.

## Decyzja
Własne komponenty SVG w `src/components/charts/`: `NutritionBar`,
`DonutChart`, `BarChart` (stacked), `TrendLine`. Kolory wyłącznie
z tokens 06_UIUX; dostępność: rola img + aria-label z wartościami;
tooltips natywne dla aplikacji (shadcn Tooltip).

## Konsekwencje
+ Zero zależności, pełna kontrola stylu, komponenty testowalne vitest.
− Nowy typ wykresu = własna praca; jeśli potrzeby urosną (heatmapy,
  zoom), decyzję rewiduje nowy ADR — nie doraźny import biblioteki.
