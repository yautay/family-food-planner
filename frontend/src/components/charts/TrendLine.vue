<script setup lang="ts">
/**
 * Linia trendu — własne SVG (ADR-013), bez bibliotek wykresów.
 *
 * Rysuje polilinię przez punkty z markerami w wierzchołkach. Punkt bez wartości
 * (`null`) PRZERYWA linię: średnia krocząca nie istnieje tam, gdzie nie ma
 * danych, a przeciągnięcie prostej przez lukę udawałoby pomiar, którego nie było.
 *
 * Dwa tryby renderowania — jeden komponent, bo geometria jest ta sama:
 *
 * - samodzielny (`frame` niepodany): własny `<svg>` ze skalą z własnych punktów,
 * - nakładka (`frame` podany): `<g>` w układzie współrzędnych rodzica, czyli
 *   w slocie `overlay` komponentu `BarChart` — dzięki temu trend i słupki mają
 *   JEDNĄ skalę. Dwie skale dawałyby wykres, który da się porównać tylko na oko.
 *
 * Wartości przychodzą jako stringi dziesiętne (ADR-008) i służą wyłącznie do
 * wyliczenia geometrii. Dostępność: `role="img"` + `aria-label` z wartościami
 * (06_UIUX §1) — linia bez opisu jest dla czytnika ekranu pusta.
 */
import { computed } from 'vue'

import { formatDecimal } from '@/lib/format'

export interface TrendPoint {
  /** Etykieta punktu („17.08") — trafia do `aria-label`. */
  label: string
  /** Wartość jako string dziesiętny; `null` = brak danych (przerwa w linii). */
  value: string | null
}

/** Układ współrzędnych rodzica, gdy linia jest nakładką na inny wykres. */
export interface TrendFrame {
  width: number
  height: number
  scaleMax: number
}

const props = withDefaults(
  defineProps<{
    points: TrendPoint[]
    /** Podany = tryb nakładki (`<g>` w SVG rodzica) i WSPÓLNA skala. */
    frame?: TrendFrame | null
    /** Klasa obrysu z tokens (np. `stroke-secondary`). */
    colorClass?: string
    /** Klasa wypełnienia markerów z tokens — para do `colorClass`. */
    markerClass?: string
    unit?: string
    title?: string
    testid?: string
  }>(),
  {
    frame: null,
    colorClass: 'stroke-secondary',
    markerClass: 'fill-secondary',
    unit: 'kcal',
    title: 'Średnia krocząca',
    testid: 'trend-line',
  },
)

/** Geometria trybu samodzielnego (w nakładce przychodzi z rodzica). */
const OWN_WIDTH = 100
const OWN_HEIGHT = 40

function toNumber(value: string | null): number | null {
  if (value === null) {
    return null
  }
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : null
}

const width = computed(() => props.frame?.width ?? OWN_WIDTH)
const height = computed(() => props.frame?.height ?? OWN_HEIGHT)

const values = computed(() => props.points.map((point) => toNumber(point.value)))

/** Skala pionowa: z rodzica (nakładka) albo z własnego maksimum. */
const scaleMax = computed(() => {
  if (props.frame) {
    return Math.max(props.frame.scaleMax, 1)
  }
  const highest = Math.max(0, ...values.value.map((value) => value ?? 0))
  return Math.max(highest, 1)
})

/**
 * Punkt w środku „szuflady" swojego dnia — tak samo jak słupek `BarChart`,
 * inaczej trend byłby przesunięty o pół słupka w lewo.
 */
const positioned = computed(() => {
  const slot = width.value / Math.max(1, props.points.length)
  return values.value.map((value, index) => ({
    value,
    x: slot * index + slot / 2,
    y: value === null ? null : height.value - (value / scaleMax.value) * height.value,
  }))
})

/** Nieprzerwane odcinki linii — luka kończy odcinek, a nie go przeskakuje. */
const runs = computed<string[]>(() => {
  const result: string[] = []
  let pairs: string[] = []

  const closeRun = (): void => {
    // Jeden punkt nie jest odcinkiem: polilinia z jedną parą byłaby niewidoczna,
    // dlatego samotny punkt zostaje wyłącznie markerem.
    if (pairs.length > 1) {
      result.push(pairs.join(' '))
    }
    pairs = []
  }

  positioned.value.forEach((point) => {
    if (point.y === null) {
      closeRun()
      return
    }
    pairs.push(`${point.x},${point.y}`)
  })
  closeRun()
  return result
})

const markers = computed(() =>
  positioned.value
    .map((point, index) => ({ ...point, label: props.points[index]?.label ?? '' }))
    .filter((point): point is typeof point & { y: number } => point.y !== null),
)

const hasData = computed(() => values.value.some((value) => value !== null))

const ariaLabel = computed(() => {
  if (!hasData.value) {
    return `${props.title}: brak danych`
  }
  const described = props.points
    .map((point) =>
      point.value === null
        ? `${point.label} brak danych`
        : `${point.label} ${formatDecimal(point.value)} ${props.unit}`,
    )
    .join(', ')
  return `${props.title}: ${described}`
})
</script>

<template>
  <!--
    Jeden zestaw dzieci, dwa korzenie: `<g>` w trybie nakładki (układ
    współrzędnych rodzica) i własny `<svg>` w trybie samodzielnym. Dynamiczny
    korzeń zamiast dwóch gałęzi `v-if` — inaczej geometria istniałaby w szablonie
    dwa razy i rozjechałaby się przy pierwszej zmianie.
  -->
  <component
    :is="frame ? 'g' : 'svg'"
    v-bind="
      frame
        ? {}
        : { viewBox: `0 0 ${width} ${height}`, class: 'h-16 w-full', preserveAspectRatio: 'none' }
    "
    role="img"
    :aria-label="ariaLabel"
    :data-testid="testid"
  >
    <polyline
      v-for="(run, index) in runs"
      :key="`run-${index}`"
      :class="colorClass"
      fill="none"
      :points="run"
      stroke-width="1"
      stroke-linejoin="round"
      :data-testid="`${testid}-run-${index}`"
    />
    <circle
      v-for="(marker, index) in markers"
      :key="`${marker.label}-${index}`"
      :class="markerClass"
      :cx="marker.x"
      :cy="marker.y"
      r="1.2"
      :data-testid="`${testid}-marker-${marker.label}`"
      :data-y="Math.round(marker.y)"
    />
  </component>
</template>
