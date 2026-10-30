<script setup lang="ts">
/**
 * Statystyki — widok 7 wizualizacji (06_UIUX §4.7), trasa `/statystyki`.
 *
 * Układ: kontrolka zakresu (tydzień / miesiąc / własny) → zakładki
 * Kalorie / Makroskładniki → wykres słupkowy z linią celu → podsumowanie
 * (średnia dzienna / cel / delta / status słowny).
 *
 * Trzy rzeczy, które ta strona MUSI pokazywać uczciwie:
 *
 * 1. **Dzień bez planu to luka, nie zero.** Backend zwraca `has_plan: false`
 *    i `nutrition: null`; wykres rysuje wtedy przerywany obrys, a średnia
 *    dzieli się przez `days_with_plan` (Acceptance Criteria 4).
 * 2. **Cel jest historyczny.** Każdy dzień niesie własny cel, więc linia celu
 *    jest SCHODKOWA — zmianę celu w środku zakresu widać jako zmianę poziomu.
 * 3. **Niepełne dane są nazwane.** Gdy w zakresie jest dzień z produktem bez
 *    wartości, obok podsumowania stoi plakietka „Niepełne dane" z listą braków.
 *
 * Strona nie liczy niczego domenowego: wszystkie liczby przychodzą z
 * `/stats/daily` jako stringi dziesiętne (ADR-008), a tutaj są wyłącznie
 * formatowane i zamieniane na geometrię wykresu. Stan serwera trzyma TanStack
 * Query (ADR-007) — żadnej kopii w Pinia.
 */
import { useQuery } from '@tanstack/vue-query'
import { CalendarDays, Info } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { MAX_STATS_RANGE_DAYS, fetchDailyStats } from '@/api/stats'
import type { StatsDay } from '@/api/stats'
import type { GoalMetric } from '@/api/planning'
import { queryKeys } from '@/api/queryKeys'
import BarChart from '@/components/charts/BarChart.vue'
import type { BarDatum } from '@/components/charts/BarChart.vue'
import TrendLine from '@/components/charts/TrendLine.vue'
import type { TrendPoint } from '@/components/charts/TrendLine.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  addDays,
  daysBetween,
  endOfMonth,
  formatDate,
  isoDate,
  startOfMonth,
  startOfWeek,
} from '@/lib/dates'
import { sumDecimals } from '@/lib/decimal'
import { formatDecimal } from '@/lib/format'
import { navigationRange, planNavigationContext, validNavigationDate } from '@/lib/navigation'
import { statusLabel, statusToken } from '@/lib/nutrition'
import { common, recipes as recipeTexts, stats as texts } from '@/lib/texts'

type RangePreset = 'week' | 'month' | 'custom'
type StatsTab = 'kcal' | 'macros'

/** Okno średniej kroczącej — tydzień wygładza rytm „weekend inaczej niż wtorek". */
const TREND_WINDOW_DAYS = 7

const today = isoDate(new Date())
const route = useRoute()
const router = useRouter()
const initialContext = planNavigationContext(route)
const anchorDate = ref(initialContext.selectedDate)

function rangePreset(from: string, to: string): RangePreset {
  if (from === startOfWeek(from) && to === addDays(from, 6)) return 'week'
  if (from === startOfMonth(from) && to === endOfMonth(from)) return 'month'
  return 'custom'
}
const preset = ref<RangePreset>(rangePreset(initialContext.from, initialContext.to))
const activeTab = ref<StatsTab>('kcal')
/** Szkic zakresu własnego — stan UI, nie stan serwera (ADR-007). */
const customFrom = ref(initialContext.from)
const customTo = ref(initialContext.to)

const range = computed(() => {
  if (preset.value === 'week') {
    const from = startOfWeek(anchorDate.value)
    return { from, to: addDays(from, 6) }
  }
  if (preset.value === 'month') {
    return { from: startOfMonth(anchorDate.value), to: endOfMonth(anchorDate.value) }
  }
  return { from: customFrom.value, to: customTo.value }
})

/** Walidacja zakresu własnego — te same reguły, co po stronie serwera (422). */
const rangeError = computed(() => {
  const { from, to } = range.value
  // Native date input da się WYCZYŚCIĆ — wtedy nie ma czego pytać serwera,
  // ale użytkownik musi wiedzieć, dlaczego wykres zniknął.
  if (!validNavigationDate(from) || !validNavigationDate(to)) {
    return texts.rangeIncomplete
  }
  if (from > to) {
    return texts.rangeReversed
  }
  return daysBetween(from, to) + 1 > MAX_STATS_RANGE_DAYS
    ? texts.rangeTooLong(MAX_STATS_RANGE_DAYS)
    : null
})

const rangeIsUsable = computed(() => rangeError.value === null)

// URL przechowuje zatwierdzony zakres. Nie zapisujemy niepełnego szkicu.
// Własne replace nie inicjalizuje ponownie formularza (ważne przy szybkim wpisywaniu).
const ownQueries = new Set<string>()
function queryKey(from: unknown, to: unknown, selectedDate: unknown): string {
  return JSON.stringify([from, to, selectedDate])
}
watch(
  () => route.fullPath,
  () => {
    const key = queryKey(route.query.from, route.query.to, route.query.selectedDate)
    if (ownQueries.delete(key)) return
    const context = planNavigationContext(route)
    anchorDate.value = context.selectedDate
    customFrom.value = context.from
    customTo.value = context.to
    preset.value = rangePreset(context.from, context.to)
  },
)
watch(range, ({ from, to }) => {
  if (!rangeIsUsable.value) return
  const selectedDate = anchorDate.value >= from && anchorDate.value <= to ? anchorDate.value : from
  // Własny replace pomija inicjalizację formularza, więc również lokalna kotwica
  // musi wskazywać dzień zapisany do URL przed kolejnym wyborem presetu.
  anchorDate.value = selectedDate
  const current = navigationRange(route.query)
  if (current?.from === from && current.to === to && route.query.selectedDate === selectedDate)
    return
  const key = queryKey(from, to, selectedDate)
  ownQueries.add(key)
  void router
    .replace({ query: { ...route.query, from, to, selectedDate } })
    .then(() => ownQueries.delete(key))
})

const stats = useQuery({
  queryKey: computed(() => queryKeys.stats.daily(range.value.from, range.value.to)),
  queryFn: () => fetchDailyStats(range.value.from, range.value.to),
  enabled: rangeIsUsable,
})

const days = computed<StatsDay[]>(() => stats.data.value?.days ?? [])
const summary = computed(() => stats.data.value?.summary ?? null)

/**
 * Etykieta słupka: dzień miesiąca wystarcza pod słupkiem, pełna data idzie do
 * `aria-label` i do `id` (miesięczny zakres powtarza „05", a `data-testid`
 * muszą zostać unikalne).
 */
function barLabel(day: string): string {
  return day.slice(8)
}

const kcalBars = computed<BarDatum[]>(() =>
  days.value.map((day) => ({
    id: day.day,
    label: barLabel(day.day),
    title: formatDate(day.day),
    highlighted: day.day === today,
    empty: !day.has_plan,
    target: day.goal?.kcal ?? null,
    segments: [
      {
        label: 'kcal',
        value: day.nutrition?.kcal ?? '0',
        colorClass: statusToken(day.status.kcal).fill,
      },
    ],
  })),
)

/** Kolory makro z tokens (06_UIUX §1) — nigdy hex w komponencie. */
const MACRO_SEGMENTS = [
  { key: 'protein_g', label: texts.macroProtein, colorClass: 'fill-secondary' },
  { key: 'fat_g', label: texts.macroFat, colorClass: 'fill-warning' },
  { key: 'carbs_g', label: texts.macroCarbs, colorClass: 'fill-primary' },
] as const

/**
 * Cel stacka makro = suma trzech celów, ale TYLKO gdy ustawione są wszystkie.
 *
 * Suma dwóch celów wobec słupka z trzech makr byłaby porównaniem, które zawsze
 * wypada na niekorzyść użytkownika — lepiej nie pokazać celu niż pokazać zły.
 */
function macroTarget(day: StatsDay): string | null {
  const targets = [day.goal?.protein_g, day.goal?.fat_g, day.goal?.carbs_g].filter(
    (target): target is string => target != null,
  )
  return targets.length === MACRO_SEGMENTS.length ? sumDecimals(targets) : null
}

const macroBars = computed<BarDatum[]>(() =>
  days.value.map((day) => ({
    id: day.day,
    label: barLabel(day.day),
    title: formatDate(day.day),
    highlighted: day.day === today,
    empty: !day.has_plan,
    target: macroTarget(day),
    segments: MACRO_SEGMENTS.map((segment) => ({
      label: segment.label,
      value: day.nutrition?.[segment.key] ?? '0',
      colorClass: segment.colorClass,
    })),
  })),
)

/**
 * Średnia krocząca sumy makr — okno 7 dni liczone WYŁĄCZNIE z dni z planem
 * w oknie (luka nie wnosi zera). Dzień bez własnych danych nie dostaje punktu.
 */
const macroTrend = computed<TrendPoint[]>(() =>
  days.value.map((day, index) => {
    if (!day.has_plan) {
      return { label: formatDate(day.day), value: null }
    }
    const window = days.value
      .slice(Math.max(0, index - TREND_WINDOW_DAYS + 1), index + 1)
      .filter((entry) => entry.nutrition !== null)
    const sums = window.map((entry) =>
      sumDecimals(MACRO_SEGMENTS.map((segment) => entry.nutrition?.[segment.key] ?? '0')),
    )
    const total = Number.parseFloat(sumDecimals(sums))
    return {
      label: formatDate(day.day),
      value: window.length > 0 ? (total / window.length).toFixed(1) : null,
    }
  }),
)

/** Trend ma sens od tygodnia danych — na krótszym zakresie to ta sama linia, co słupki. */
const showTrend = computed(() => days.value.length >= TREND_WINDOW_DAYS)

interface SummaryTile {
  key: string
  label: string
  unit: string
  metric: GoalMetric
}

const summaryTiles = computed<SummaryTile[]>(() => {
  const progress = summary.value?.goal_progress
  if (!progress) {
    return []
  }
  const tiles: SummaryTile[] =
    activeTab.value === 'kcal'
      ? [
          {
            key: 'kcal',
            label: texts.tabKcal,
            unit: recipeTexts.kcalUnit,
            metric: progress.kcal,
          },
        ]
      : [
          { key: 'protein_g', label: texts.macroProtein, unit: 'g', metric: progress.protein_g },
          { key: 'fat_g', label: texts.macroFat, unit: 'g', metric: progress.fat_g },
          { key: 'carbs_g', label: texts.macroCarbs, unit: 'g', metric: progress.carbs_g },
        ]
  return tiles
})

/** Braki danych z całego zakresu — bez duplikatów, do tooltipa plakietki. */
const missingData = computed(() => {
  const entries: string[] = []
  days.value.forEach((day) => {
    day.nutrition?.missing.forEach((entry) => {
      if (!entries.includes(entry)) {
        entries.push(entry)
      }
    })
  })
  return entries
})

const hasPlannedDays = computed(() => (summary.value?.days_with_plan ?? 0) > 0)
const hasAnyGoal = computed(() => days.value.some((day) => day.goal !== null))

const TABS: { id: StatsTab; label: string }[] = [
  { id: 'kcal', label: texts.tabKcal },
  { id: 'macros', label: texts.tabMacros },
]

const PRESETS: { id: RangePreset; label: string }[] = [
  { id: 'week', label: texts.presetWeek },
  { id: 'month', label: texts.presetMonth },
  { id: 'custom', label: texts.presetCustom },
]
</script>

<template>
  <section class="grid gap-4" data-testid="statystyki-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <!-- Zakres dat: presety + zakres własny (walidowany jak na serwerze). -->
    <section class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-muted-foreground text-sm">{{ texts.rangeLabel }}</span>
        <Button
          v-for="option in PRESETS"
          :key="option.id"
          :variant="preset === option.id ? 'default' : 'outline'"
          class="min-h-11"
          :aria-pressed="preset === option.id"
          :data-testid="`stats-preset-${option.id}`"
          @click="preset = option.id"
        >
          {{ option.label }}
        </Button>
        <p class="text-muted-foreground ml-auto text-sm tabular-nums" data-testid="stats-range">
          <CalendarDays class="mr-1 inline size-4" aria-hidden="true" />
          {{ texts.rangeSummary(formatDate(range.from), formatDate(range.to)) }}
        </p>
      </div>

      <div v-if="preset === 'custom'" class="grid gap-3 sm:grid-cols-2">
        <div class="grid gap-2">
          <label class="text-sm font-medium" for="stats-from">{{ texts.rangeFrom }}</label>
          <Input
            id="stats-from"
            v-model="customFrom"
            type="date"
            class="min-h-11 tabular-nums"
            data-testid="stats-from"
          />
        </div>
        <div class="grid gap-2">
          <label class="text-sm font-medium" for="stats-to">{{ texts.rangeTo }}</label>
          <Input
            id="stats-to"
            v-model="customTo"
            type="date"
            class="min-h-11 tabular-nums"
            data-testid="stats-to"
          />
        </div>
      </div>

      <p v-if="rangeError" class="text-destructive text-sm" role="alert" data-testid="stats-error">
        {{ rangeError }}
      </p>
    </section>

    <!-- Zakładki: ten sam wzorzec, co taby przepisu (role="tab" + aria-selected). -->
    <div class="border-border flex gap-2 border-b" role="tablist" :aria-label="texts.title">
      <button
        v-for="tab in TABS"
        :key="tab.id"
        type="button"
        class="min-h-11 border-b-2 px-3 text-sm font-medium"
        :class="
          activeTab === tab.id
            ? 'border-primary text-foreground'
            : 'text-muted-foreground border-transparent'
        "
        :aria-selected="activeTab === tab.id"
        role="tab"
        :data-testid="`stats-tab-${tab.id}`"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Zły zakres = nie pytamy serwera, więc nie udajemy też ładowania. -->
    <p
      v-if="!rangeIsUsable"
      class="text-muted-foreground text-sm"
      data-testid="stats-range-blocked"
    >
      {{ texts.rangeFix }}
    </p>

    <p v-else-if="stats.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>

    <p
      v-else-if="stats.isError.value"
      class="text-destructive text-sm"
      role="alert"
      data-testid="stats-fetch-error"
    >
      {{ common.unexpectedError }}
    </p>

    <!-- Pusty stan uczy, co zrobić (06_UIUX §3.2) — nie pokazuje zer. -->
    <section
      v-else-if="!hasPlannedDays"
      class="border-border bg-card grid gap-2 rounded-xl border p-6 text-center shadow-sm"
      data-testid="stats-empty"
    >
      <p class="font-medium">{{ texts.emptyTitle }}</p>
      <p class="text-muted-foreground text-sm">{{ texts.emptyHint }}</p>
      <div class="flex justify-center">
        <Button as-child class="min-h-11">
          <RouterLink :to="{ name: 'plan-dnia' }" data-testid="stats-go-to-plan">
            {{ texts.emptyAction }}
          </RouterLink>
        </Button>
      </div>
    </section>

    <template v-else>
      <section
        class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm"
        :data-testid="`stats-chart-${activeTab}`"
      >
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-sm font-medium">
            {{ activeTab === 'kcal' ? texts.chartKcal : texts.chartMacros }}
          </h2>
          <p class="text-muted-foreground text-xs">{{ texts.gapLegend }}</p>
        </div>

        <BarChart
          v-if="activeTab === 'kcal'"
          :data="kcalBars"
          unit="kcal"
          :title="texts.chartKcal"
          :empty-text="texts.emptyHint"
          testid="stats-kcal-chart"
        />

        <BarChart
          v-else
          :data="macroBars"
          unit="g"
          :title="texts.chartMacros"
          :empty-text="texts.emptyHint"
          testid="stats-macro-chart"
        >
          <template v-if="showTrend" #overlay="{ width, height, scaleMax }">
            <!-- Trend w układzie współrzędnych słupków: jedna skala, jedno porównanie. -->
            <TrendLine
              :points="macroTrend"
              :frame="{ width, height, scaleMax }"
              color-class="stroke-foreground"
              marker-class="fill-foreground"
              unit="g"
              :title="texts.trendTitle"
              testid="stats-macro-trend"
            />
          </template>
        </BarChart>

        <p v-if="activeTab === 'macros'" class="text-muted-foreground text-xs">
          {{ showTrend ? texts.trendHint : texts.trendTooShort }}
        </p>

        <ul v-if="activeTab === 'macros'" class="flex flex-wrap gap-3 text-xs">
          <li
            v-for="segment in MACRO_SEGMENTS"
            :key="segment.key"
            class="text-muted-foreground flex items-center gap-1"
          >
            <svg class="size-3" viewBox="0 0 10 10" aria-hidden="true">
              <rect :class="segment.colorClass" x="0" y="0" width="10" height="10" rx="2" />
            </svg>
            {{ segment.label }}
          </li>
        </ul>
      </section>

      <!-- Podsumowanie: trio wartość/cel/delta + status słowny (06_UIUX §3.5). -->
      <section class="grid gap-3" data-testid="stats-summary">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-sm font-medium">{{ texts.summaryTitle }}</h2>
          <p class="text-muted-foreground text-sm" data-testid="stats-days">
            {{ texts.summaryDays(summary?.days_with_plan ?? 0, summary?.days_in_range ?? 0) }}
          </p>
        </div>

        <p
          v-if="summary?.avg && !summary.avg.complete"
          class="text-warning flex w-fit items-center gap-1 text-sm"
          :title="texts.incompleteTooltip(missingData.join('; '))"
          data-testid="stats-incomplete"
        >
          <Info class="size-4" aria-hidden="true" />
          {{ texts.incompleteBadge }}
        </p>

        <p v-if="!hasAnyGoal" class="text-muted-foreground text-sm" data-testid="stats-no-goal">
          {{ texts.goalsMissing }}
        </p>

        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <li
            v-for="tile in summaryTiles"
            :key="tile.key"
            class="border-border bg-card grid gap-1 rounded-xl border p-3 shadow-sm"
            :data-testid="`stats-tile-${tile.key}`"
          >
            <p class="text-muted-foreground text-sm">{{ tile.label }}</p>
            <p class="text-xl font-semibold tabular-nums">
              {{ formatDecimal(tile.metric.value) }}
              <span class="text-muted-foreground text-sm font-normal">
                /
                {{
                  tile.metric.target === null ? texts.noTarget : formatDecimal(tile.metric.target)
                }}
                {{ tile.unit }}
              </span>
            </p>
            <p class="text-sm tabular-nums">
              <span v-if="tile.metric.delta !== null" class="text-muted-foreground">
                {{ formatDecimal(tile.metric.delta) }} {{ tile.unit }}
              </span>
              <span
                v-if="tile.metric.status"
                :class="statusToken(tile.metric.status).text"
                :data-testid="`stats-status-${tile.key}`"
              >
                <span aria-hidden="true"> · </span>{{ statusLabel(tile.metric.status) }}
              </span>
            </p>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>
