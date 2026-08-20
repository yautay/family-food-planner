<script setup lang="ts">
/**
 * Słupki tygodnia — własne SVG (ADR-013), bez bibliotek wykresów.
 *
 * Jeden słupek = jeden dzień. Słupek może być POJEDYNCZY (kcal dnia) albo
 * STACKOWANY (segmenty makro ułożone jeden na drugim) — o tym decyduje liczba
 * segmentów w danych, nie osobny props. Do tego opcjonalna linia celu.
 *
 * Skala jest wspólna dla wszystkich słupków (maksimum z sum i celu), inaczej
 * wykres kłamałby: dzień o 1200 kcal i dzień o 2400 kcal wyglądałyby tak samo.
 *
 * Wartości przychodzą jako stringi dziesiętne (ADR-008) i służą TYLKO do
 * wyliczenia geometrii — komponent nie liczy niczego domenowego. Dostępność:
 * `role="img"` + `aria-label` z wartościami wszystkich dni, bo słupki bez opisu
 * są dla czytnika ekranu puste (06_UIUX §1).
 *
 * B13 (statystyki) reużywa ten komponent na dłuższych zakresach — dlatego
 * segmenty i etykiety są w pełni sterowane z zewnątrz.
 */
import { computed } from 'vue'

import { formatDecimal } from '@/lib/format'

export interface BarSegment {
  label: string
  /** Wartość jako string dziesiętny z API. */
  value: string
  /** Klasa wypełnienia z tokens (np. `fill-primary`). */
  colorClass: string
}

export interface BarDatum {
  /** Etykieta pod słupkiem („pon", „wt"…). */
  label: string
  /** Pełny opis do `aria-label` (np. data) — etykieta bywa skrótem. */
  title?: string
  segments: BarSegment[]
  /** Czy wyróżnić słupek (np. dziś albo wybrany dzień). */
  highlighted?: boolean
}

const props = withDefaults(
  defineProps<{
    data: BarDatum[]
    /** Linia celu (string dziesiętny) — `null` gdy użytkownik nie ustawił celu. */
    target?: string | null
    /** Jednostka do opisów tekstowych. */
    unit?: string
    title?: string
    testid?: string
  }>(),
  {
    target: null,
    unit: 'kcal',
    title: 'Kalorie w tygodniu',
    testid: 'bar-chart',
  },
)

/** Geometria w jednostkach viewBox — słupki rysujemy w układzie „od dołu". */
const CHART_HEIGHT = 100
const BAR_WIDTH = 10
const BAR_GAP = 4

function toNumber(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

interface PositionedSegment extends BarSegment {
  height: number
  y: number
}

interface PositionedBar extends BarDatum {
  x: number
  total: number
  positioned: PositionedSegment[]
}

const chartWidth = computed(() => Math.max(1, props.data.length) * (BAR_WIDTH + BAR_GAP))

const totals = computed(() =>
  props.data.map((datum) =>
    datum.segments.reduce((sum, segment) => sum + toNumber(segment.value), 0),
  ),
)

/**
 * Górna granica skali: największa suma dnia ALBO cel, gdy cel jest wyżej.
 *
 * Cel wchodzi do skali celowo — inaczej linia celu wypadłaby poza wykres
 * w tygodniu, w którym użytkownik zjadł mniej niż zaplanował.
 */
const scaleMax = computed(() => {
  const highestBar = Math.max(0, ...totals.value)
  const targetValue = props.target === null ? 0 : toNumber(props.target)
  return Math.max(highestBar, targetValue, 1)
})

const bars = computed<PositionedBar[]>(() =>
  props.data.map((datum, index) => {
    let consumed = 0
    const positioned = datum.segments.map((segment) => {
      const height = (toNumber(segment.value) / scaleMax.value) * CHART_HEIGHT
      consumed += height
      return { ...segment, height, y: CHART_HEIGHT - consumed }
    })
    return {
      ...datum,
      x: index * (BAR_WIDTH + BAR_GAP),
      total: totals.value[index] ?? 0,
      positioned,
    }
  }),
)

/** Pozycja linii celu w układzie viewBox (`null`, gdy celu nie ma). */
const targetY = computed(() => {
  if (props.target === null) {
    return null
  }
  const value = toNumber(props.target)
  return value > 0 ? CHART_HEIGHT - (value / scaleMax.value) * CHART_HEIGHT : null
})

const isEmpty = computed(() => totals.value.every((total) => total <= 0))

const ariaLabel = computed(() => {
  if (isEmpty.value) {
    return `${props.title}: brak danych`
  }
  const days = bars.value
    .map((bar) => `${bar.title ?? bar.label} ${formatDecimal(String(bar.total))} ${props.unit}`)
    .join(', ')
  const goal = props.target === null ? '' : `; cel ${formatDecimal(props.target)} ${props.unit}`
  return `${props.title}: ${days}${goal}`
})
</script>

<template>
  <figure class="grid gap-2" :data-testid="testid">
    <svg
      :viewBox="`0 0 ${chartWidth} ${CHART_HEIGHT}`"
      class="h-32 w-full"
      preserveAspectRatio="none"
      role="img"
      :aria-label="ariaLabel"
    >
      <!-- Segmenty od dołu: pierwszy w danych leży najniżej. -->
      <g v-for="bar in bars" :key="bar.label">
        <rect
          class="fill-muted"
          :x="bar.x"
          y="0"
          :width="BAR_WIDTH"
          :height="CHART_HEIGHT"
          rx="2"
        />
        <rect
          v-for="segment in bar.positioned"
          :key="segment.label"
          :class="segment.colorClass"
          :x="bar.x"
          :y="segment.y"
          :width="BAR_WIDTH"
          :height="segment.height"
          rx="1"
          :data-testid="`${testid}-bar-${bar.label}-${segment.label}`"
          :data-height="Math.round(segment.height)"
        />
      </g>

      <!-- Linia celu na wierzchu słupków, żeby była czytelna także przy przekroczeniu. -->
      <line
        v-if="targetY !== null"
        class="stroke-foreground"
        x1="0"
        :x2="chartWidth"
        :y1="targetY"
        :y2="targetY"
        stroke-width="0.8"
        stroke-dasharray="2 2"
        :data-testid="`${testid}-target-line`"
        :data-y="Math.round(targetY)"
      />
    </svg>

    <figcaption class="grid gap-1">
      <ul class="flex justify-between gap-1 text-xs">
        <li
          v-for="bar in bars"
          :key="bar.label"
          class="flex-1 text-center tabular-nums"
          :class="bar.highlighted ? 'text-foreground font-semibold' : 'text-muted-foreground'"
          :data-testid="`${testid}-label-${bar.label}`"
        >
          {{ bar.label }}
        </li>
      </ul>

      <p v-if="isEmpty" class="text-muted-foreground text-sm" :data-testid="`${testid}-empty`">
        Dodaj posiłki, żeby zobaczyć rozkład tygodnia.
      </p>
    </figcaption>
  </figure>
</template>
