<script setup lang="ts">
/**
 * Pierścień udziałów makroskładników — własne SVG (ADR-013), bez bibliotek.
 *
 * Segmenty rysowane są obwodem okręgu (`stroke-dasharray`), więc cały wykres
 * to jeden element `circle` per segment — bez liczenia łuków i bez zależności.
 * Kolory wyłącznie przez klasy z tokens (06_UIUX §1), a `role="img"` +
 * `aria-label` niosą wartości i udziały procentowe, bo wykres bez opisu jest
 * dla czytnika ekranu pusty.
 *
 * Wartości przychodzą jako stringi dziesiętne (ADR-008) i służą TYLKO do
 * wyliczenia udziału — żadna liczba domenowa nie jest tu przeliczana.
 */
import { computed } from 'vue'

import { formatDecimal } from '@/lib/format'

export interface DonutSegment {
  label: string
  /** Wartość w gramach jako string dziesiętny z API. */
  value: string
  /** Klasa koloru obrysu z tokens (np. `stroke-primary`). */
  colorClass: string
}

const props = withDefaults(
  defineProps<{
    segments: DonutSegment[]
    /** Napis w środku pierścienia (np. kcal dnia). */
    centerValue?: string
    centerLabel?: string
    title?: string
    testid?: string
  }>(),
  {
    centerValue: undefined,
    centerLabel: undefined,
    title: 'Udział makroskładników',
    testid: 'donut-chart',
  },
)

const RADIUS = 40
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

interface ComputedSegment extends DonutSegment {
  percent: number
  dash: number
  offset: number
}

const total = computed(() =>
  props.segments.reduce((sum, segment) => {
    const value = Number.parseFloat(segment.value)
    return sum + (Number.isFinite(value) && value > 0 ? value : 0)
  }, 0),
)

const arcs = computed<ComputedSegment[]>(() => {
  if (total.value <= 0) {
    return []
  }
  let consumed = 0
  return props.segments.map((segment) => {
    const raw = Number.parseFloat(segment.value)
    const value = Number.isFinite(raw) && raw > 0 ? raw : 0
    const percent = (value / total.value) * 100
    const dash = (value / total.value) * CIRCUMFERENCE
    // Ujemny offset przesuwa start segmentu — segmenty układają się po kolei.
    const offset = -consumed
    consumed += dash
    return { ...segment, percent, dash, offset }
  })
})

const isEmpty = computed(() => arcs.value.length === 0)

const ariaLabel = computed(() => {
  if (isEmpty.value) {
    return `${props.title}: brak danych`
  }
  const parts = arcs.value.map(
    (segment) =>
      `${segment.label} ${formatDecimal(segment.value)} g (${Math.round(segment.percent)}%)`,
  )
  return `${props.title}: ${parts.join(', ')}`
})
</script>

<template>
  <figure class="grid gap-2" :data-testid="testid">
    <svg
      viewBox="0 0 100 100"
      class="mx-auto h-40 w-40 -rotate-90"
      role="img"
      :aria-label="ariaLabel"
    >
      <circle class="stroke-muted fill-none" cx="50" cy="50" :r="RADIUS" stroke-width="14" />
      <circle
        v-for="segment in arcs"
        :key="segment.label"
        :class="[segment.colorClass, 'fill-none']"
        cx="50"
        cy="50"
        :r="RADIUS"
        stroke-width="14"
        :stroke-dasharray="`${segment.dash} ${CIRCUMFERENCE - segment.dash}`"
        :stroke-dashoffset="segment.offset"
        :data-testid="`${testid}-segment-${segment.label}`"
        :data-percent="Math.round(segment.percent)"
      />
    </svg>

    <figcaption class="grid gap-1">
      <p v-if="centerValue" class="text-center font-semibold tabular-nums">
        {{ centerValue }}
        <span v-if="centerLabel" class="text-muted-foreground text-sm font-normal">
          {{ centerLabel }}
        </span>
      </p>

      <ul class="grid gap-1 text-sm">
        <li
          v-for="segment in arcs"
          :key="segment.label"
          class="flex items-center justify-between gap-2 tabular-nums"
        >
          <!-- Legenda podaje nazwę i liczbę: kolor nigdy nie jest jedynym nośnikiem. -->
          <span class="text-muted-foreground">{{ segment.label }}</span>
          <span>{{ formatDecimal(segment.value) }} g · {{ Math.round(segment.percent) }}%</span>
        </li>
      </ul>

      <p v-if="isEmpty" class="text-muted-foreground text-sm" :data-testid="`${testid}-empty`">
        Dodaj pozycje, żeby zobaczyć udział makroskładników.
      </p>
    </figcaption>
  </figure>
</template>
