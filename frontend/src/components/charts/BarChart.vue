<script setup lang="ts">
/**
 * Słupki dni — własne SVG (ADR-013), bez bibliotek wykresów.
 *
 * Jeden słupek = jeden dzień. Słupek może być POJEDYNCZY (kcal dnia) albo
 * STACKOWANY (segmenty makro ułożone jeden na drugim) — o tym decyduje liczba
 * segmentów w danych, nie osobny props.
 *
 * Skala jest wspólna dla wszystkich słupków (maksimum z sum i celów), inaczej
 * wykres kłamałby: dzień o 1200 kcal i dzień o 2400 kcal wyglądałyby tak samo.
 *
 * Cel można podać dwojako (BATCH_13):
 *
 * - `target` na całym wykresie = JEDNA pozioma linia (tydzień z jednym celem),
 * - `target` na POJEDYNCZYM słupku = linia SCHODKOWA. Cele są historyczne
 *   (02_DOMAIN §6), więc zmiana celu w środku zakresu ma być widoczna jako
 *   zmiana poziomu, a nie wygładzona interpolacją. Dzień bez celu przerywa
 *   linię, zamiast ciągnąć ostatni znany poziom.
 *
 * Dzień bez planu (`empty: true`) to LUKA, nie zero: rysujemy przerywany obrys
 * zamiast słupka, a `aria-label` mówi „brak planu". Zerowy słupek sugerowałby,
 * że tego dnia nie zjedzono nic, co jest inną informacją.
 *
 * Wartości przychodzą jako stringi dziesiętne (ADR-008) i służą TYLKO do
 * wyliczenia geometrii — komponent nie liczy niczego domenowego. Dostępność:
 * `role="img"` + `aria-label` z wartościami wszystkich dni, bo słupki bez opisu
 * są dla czytnika ekranu puste (06_UIUX §1).
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
  /** Etykieta pod słupkiem („pon", „wt", „17.08"…). */
  label: string
  /**
   * Identyfikator słupka w `data-testid` i kluczach — domyślnie `label`.
   *
   * Osobne pole, bo etykieta MUSI być krótka (mieści się pod słupkiem), a przy
   * zakresie dłuższym niż miesiąc dzień „05" wraca kilka razy. Bez unikalnego
   * `id` powstałyby zduplikowane `data-testid`, na których strict mode
   * Playwrighta wywala się z „resolved to N elements".
   */
  id?: string
  /** Pełny opis do `aria-label` (np. data) — etykieta bywa skrótem. */
  title?: string
  segments: BarSegment[]
  /** Czy wyróżnić słupek (np. dziś albo wybrany dzień). */
  highlighted?: boolean
  /**
   * Cel TEGO dnia (string dziesiętny) — obecność pola przełącza wykres na
   * linię schodkową. `null` = ten dzień nie miał celu (linia się przerywa).
   */
  target?: string | null
  /** Dzień bez planu: luka w danych, nie zerowa wartość. */
  empty?: boolean
}

const props = withDefaults(
  defineProps<{
    data: BarDatum[]
    /** Wspólna linia celu (string dziesiętny); `null` gdy celu nie ma. */
    target?: string | null
    /** Jednostka do opisów tekstowych. */
    unit?: string
    title?: string
    /** Komunikat pod wykresem, gdy nie ma ani jednej wartości. */
    emptyText?: string
    testid?: string
  }>(),
  {
    target: null,
    unit: 'kcal',
    title: 'Kalorie w tygodniu',
    emptyText: 'Dodaj posiłki, żeby zobaczyć rozkład tygodnia.',
    testid: 'bar-chart',
  },
)

/** Geometria w jednostkach viewBox — słupki rysujemy w układzie „od dołu". */
const CHART_HEIGHT = 100
const BAR_WIDTH = 10
const BAR_GAP = 4
/** Szerokość „szuflady" jednego dnia; linia celu ciągnie się przez całą. */
const SLOT_WIDTH = BAR_WIDTH + BAR_GAP

function toNumber(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

interface PositionedSegment extends BarSegment {
  height: number
  y: number
}

interface PositionedBar extends BarDatum {
  /** `id` z danych albo etykieta — zawsze ustawione, więc bez `?`. */
  key: string
  x: number
  total: number
  positioned: PositionedSegment[]
}

const chartWidth = computed(() => Math.max(1, props.data.length) * SLOT_WIDTH)

/** Suma dnia; luka nie ma sumy — inaczej wciągałaby wykres w skalę bez wartości. */
const totals = computed(() =>
  props.data.map((datum) =>
    datum.empty ? 0 : datum.segments.reduce((sum, segment) => sum + toNumber(segment.value), 0),
  ),
)

/** Czy którykolwiek słupek ma własny cel — wtedy linia celu jest schodkowa. */
const hasStepTargets = computed(() => props.data.some((datum) => datum.target !== undefined))

/**
 * Górna granica skali: największa suma dnia ALBO największy cel, gdy jest wyżej.
 *
 * Cele wchodzą do skali celowo — inaczej linia celu wypadłaby poza wykres
 * w zakresie, w którym użytkownik zjadł mniej, niż zaplanował.
 */
const scaleMax = computed(() => {
  const highestBar = Math.max(0, ...totals.value)
  const targets = props.data.map((datum) => (datum.target ? toNumber(datum.target) : 0))
  const shared = props.target === null ? 0 : toNumber(props.target)
  return Math.max(highestBar, shared, 1, ...targets)
})

/** Wysokość w układzie viewBox dla wartości domenowej (0 = dół wykresu). */
function yFor(value: number): number {
  return CHART_HEIGHT - (value / scaleMax.value) * CHART_HEIGHT
}

const bars = computed<PositionedBar[]>(() =>
  props.data.map((datum, index) => {
    let consumed = 0
    const positioned = datum.empty
      ? []
      : datum.segments.map((segment) => {
          const height = (toNumber(segment.value) / scaleMax.value) * CHART_HEIGHT
          consumed += height
          return { ...segment, height, y: CHART_HEIGHT - consumed }
        })
    return {
      ...datum,
      key: datum.id ?? datum.label,
      x: index * SLOT_WIDTH,
      total: totals.value[index] ?? 0,
      positioned,
    }
  }),
)

/** Pozycja WSPÓLNEJ linii celu (`null`, gdy celu nie ma albo jest schodkowy). */
const targetY = computed(() => {
  if (props.target === null || hasStepTargets.value) {
    return null
  }
  const value = toNumber(props.target)
  return value > 0 ? yFor(value) : null
})

/**
 * Linia celu jako funkcja SCHODKOWA — jedna polilinia na każdy nieprzerwany
 * ciąg dni z celem. Przerwa (dzień bez celu) kończy ciąg: łączenie przez lukę
 * sugerowałoby cel, którego wtedy nie było.
 */
const targetSteps = computed<{ points: string; levels: number[] }[]>(() => {
  if (!hasStepTargets.value) {
    return []
  }
  const runs: { points: string; levels: number[] }[] = []
  let pairs: string[] = []
  let levels: number[] = []

  const closeRun = (): void => {
    if (pairs.length > 0) {
      runs.push({ points: pairs.join(' '), levels })
      pairs = []
      levels = []
    }
  }

  bars.value.forEach((bar) => {
    const value = bar.target ? toNumber(bar.target) : 0
    if (value <= 0) {
      closeRun()
      return
    }
    const y = yFor(value)
    pairs.push(`${bar.x},${y}`, `${bar.x + SLOT_WIDTH},${y}`)
    levels.push(Math.round(y))
  })
  closeRun()
  return runs
})

const isEmpty = computed(() => bars.value.every((bar) => bar.total <= 0))

const ariaLabel = computed(() => {
  if (isEmpty.value) {
    return `${props.title}: brak danych`
  }
  const days = bars.value
    .map((bar) => {
      const name = bar.title ?? bar.label
      if (bar.empty) {
        return `${name} brak planu`
      }
      const value = `${formatDecimal(String(bar.total))} ${props.unit}`
      // W trybie schodkowym cel jest RÓŻNY dla różnych dni, więc jedyne miejsce,
      // w którym czytnik ekranu może go usłyszeć, jest przy dniu.
      const goal =
        hasStepTargets.value && bar.target
          ? ` (cel ${formatDecimal(bar.target)} ${props.unit})`
          : ''
      return `${name} ${value}${goal}`
    })
    .join(', ')
  const goal =
    props.target === null || hasStepTargets.value
      ? ''
      : `; cel ${formatDecimal(props.target)} ${props.unit}`
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
      <g v-for="(bar, index) in bars" :key="`${bar.key}-${index}`">
        <!-- Dzień bez planu: przerywany obrys zamiast tła słupka (luka ≠ zero). -->
        <rect
          v-if="bar.empty"
          class="fill-muted/40 stroke-border"
          :x="bar.x"
          y="0"
          :width="BAR_WIDTH"
          :height="CHART_HEIGHT"
          rx="2"
          stroke-width="0.6"
          stroke-dasharray="2 2"
          :data-testid="`${testid}-gap-${bar.key}`"
        />
        <rect
          v-else
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
          :data-testid="`${testid}-bar-${bar.key}-${segment.label}`"
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
      <polyline
        v-for="(run, index) in targetSteps"
        :key="`target-${index}`"
        class="stroke-foreground"
        fill="none"
        :points="run.points"
        stroke-width="0.8"
        stroke-dasharray="2 2"
        :data-testid="`${testid}-target-step-${index}`"
        :data-levels="run.levels.join(',')"
      />

      <!--
        Nakładka rysowana W TYM SAMYM układzie współrzędnych, co słupki
        (np. `TrendLine` średniej kroczącej) — dzięki temu trend i słupki
        mają jedną skalę, a nie dwie, które da się porównać tylko na oko.
      -->
      <slot name="overlay" :width="chartWidth" :height="CHART_HEIGHT" :scale-max="scaleMax" />
    </svg>

    <figcaption class="grid gap-1">
      <ul class="flex justify-between gap-1 text-xs">
        <li
          v-for="(bar, index) in bars"
          :key="`${bar.key}-${index}`"
          class="flex-1 text-center tabular-nums"
          :class="
            bar.empty
              ? 'text-muted-foreground/60'
              : bar.highlighted
                ? 'text-foreground font-semibold'
                : 'text-muted-foreground'
          "
          :data-testid="`${testid}-label-${bar.key}`"
        >
          {{ bar.label }}
        </li>
      </ul>

      <p v-if="isEmpty" class="text-muted-foreground text-sm" :data-testid="`${testid}-empty`">
        {{ emptyText }}
      </p>
    </figcaption>
  </figure>
</template>
