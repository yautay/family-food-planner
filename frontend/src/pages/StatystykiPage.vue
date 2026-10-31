<script setup lang="ts">
/** Whole-plan values and historical account goals are separate readouts.
 * Missing days remain gaps; API progress ratings are intentionally not rendered.
 */
import { useQuery } from '@tanstack/vue-query'
import { CalendarDays, Info } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { MAX_STATS_RANGE_DAYS, fetchDailyStats } from '@/api/stats'
import type { StatsDay } from '@/api/stats'
import { queryKeys } from '@/api/queryKeys'
import ErrorState from '@/components/domain/ErrorState.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
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
        colorClass: 'fill-primary',
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

// Whole-plan averages and account targets have different scopes. API personal
// progress ratings must not judge the sum of everybody's planned portions.
const summaryTiles = computed(() => {
  const avg = summary.value?.avg
  if (!avg) return []
  return activeTab.value === 'kcal'
    ? [{ key: 'kcal', label: texts.tabKcal, unit: recipeTexts.kcalUnit, value: avg.kcal }]
    : MACRO_SEGMENTS.map((segment) => ({
        key: segment.key,
        label: segment.label,
        unit: 'g',
        value: avg[segment.key],
      }))
})
const goalHistory = computed(() => days.value.filter((day) => day.goal !== null))
const accountAverages = computed(() => {
  const progress = summary.value?.goal_progress
  if (!progress) return []
  return [
    { label: texts.tabKcal, value: progress.kcal.target, unit: 'kcal' },
    { label: texts.macroProtein, value: progress.protein_g.target, unit: 'g' },
    { label: texts.macroFat, value: progress.fat_g.target, unit: 'g' },
    { label: texts.macroCarbs, value: progress.carbs_g.target, unit: 'g' },
  ]
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
  <section class="grid min-w-0 gap-6" data-testid="statystyki-page">
    <PageHeader
      title="Podsumowanie planu"
      description="Wartości wszystkich porcji w planie. Brak planu jest luką, a nie zerowym spożyciem."
    />
    <p class="text-muted-foreground text-sm leading-relaxed" data-testid="stats-semantics">
      Podsumowanie opisuje cały plan, nie potwierdza zjedzenia posiłków. Wartości obejmują wszystkie
      porcje, a cel należy do Twojego konta. Dlatego nie oceniamy tutaj realizacji indywidualnego
      celu.
    </p>

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

    <!-- Two ordinary toggle buttons; both are reachable with Tab. -->
    <div class="border-border flex gap-2 border-b" role="group" aria-label="Wartości planu">
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
        :aria-pressed="activeTab === tab.id"
        :data-testid="`stats-tab-${tab.id}`"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Refetch can fail after either an empty or populated successful read. -->
    <ErrorState
      v-if="rangeIsUsable && stats.data.value && stats.isError.value"
      title="Nie udało się odświeżyć podsumowania"
      message="Poniżej pozostają ostatnio odczytane dane."
      :pending="stats.isFetching.value"
      @retry="stats.refetch()"
    />

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

    <ErrorState
      v-else-if="stats.isError.value && !stats.data.value"
      :message="common.unexpectedError"
      :pending="stats.isFetching.value"
      data-testid="stats-fetch-error"
      @retry="stats.refetch()"
    />

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
            {{
              activeTab === 'kcal'
                ? 'Kalorie całego planu na dzień'
                : 'Makroskładniki całego planu na dzień'
            }}
          </h2>
          <p class="text-muted-foreground text-xs">{{ texts.gapLegend }}</p>
        </div>

        <BarChart
          v-if="activeTab === 'kcal'"
          :data="kcalBars"
          unit="kcal"
          :title="'Kalorie całego planu na dzień'"
          target-label="historyczny cel konta, odczyt archiwalny"
          empty-text="Zaplanowane wartości są zerowe lub niepełne. Sprawdź dane składników."
          testid="stats-kcal-chart"
        />

        <BarChart
          v-else
          :data="macroBars"
          unit="g"
          :title="'Makroskładniki całego planu na dzień'"
          target-label="suma historycznych celów makro konta, odczyt archiwalny"
          empty-text="Zaplanowane wartości są zerowe lub niepełne. Sprawdź dane składników."
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

        <p class="text-muted-foreground text-sm" data-testid="stats-goal-legend">
          Słupki: wartości całego planu. Przerywana linia: historyczny cel Twojego konta (dla makro
          suma trzech celów, gdy wszystkie są ustawione). To odczyt archiwalny, nie ocena planu ani
          bilansu osoby.
        </p>
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

      <!-- Whole-plan averages are deliberately separate from account goal history. -->
      <section class="grid gap-3" data-testid="stats-summary">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-sm font-medium">Średnie dzienne całego planu</h2>
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
          Brak historycznych celów konta w tym zakresie. Wartości planu pozostają dostępne.
        </p>

        <p class="text-muted-foreground text-sm">
          Średnia uwzględnia wyłącznie dni z planem. Dni bez planu nie wnoszą zera.
        </p>
        <details v-if="missingData.length" class="text-sm" data-testid="stats-missing-details">
          <summary class="min-h-11 cursor-pointer py-3 font-medium">
            Pokaż braki wartości odżywczych
          </summary>
          <ul class="grid gap-1 text-muted-foreground">
            <li v-for="entry in missingData" :key="entry" class="[overflow-wrap:anywhere]">
              {{ entry }}
            </li>
          </ul>
        </details>
        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <li
            v-for="tile in summaryTiles"
            :key="tile.key"
            class="border-border bg-card grid gap-1 rounded-xl border p-3 shadow-sm"
            :data-testid="`stats-tile-${tile.key}`"
          >
            <p class="text-muted-foreground text-sm">{{ tile.label }}</p>
            <p class="text-xl font-semibold tabular-nums">
              {{ formatDecimal(tile.value) }}
              <span class="text-muted-foreground text-sm font-normal">{{ tile.unit }}</span>
            </p>
          </li>
        </ul>
      </section>
    </template>
    <section
      v-if="rangeIsUsable && !stats.isPending.value && stats.data.value && hasAnyGoal"
      class="border-border bg-card grid min-w-0 gap-3 rounded-2xl border p-4"
      data-testid="stats-account-history"
    >
      <h2 class="font-medium">Historyczne cele konta</h2>
      <p class="text-muted-foreground text-sm">
        Zapisane cele konta są niezależne od sumy wszystkich porcji planu. Ich historia jest
        dostępna również w Ustawieniach → Moje cele.
      </p>
      <p v-if="!hasPlannedDays" class="text-muted-foreground text-sm">
        Brak dni z planem — nie wyliczono średnich celów.
      </p>
      <template v-else>
        <p class="text-muted-foreground text-sm">
          Średnie historycznych celów dla dni z planem; każde pole uwzględnia tylko dni, w których
          było ustawione:
        </p>
        <ul class="flex flex-wrap gap-x-6 gap-y-2 text-sm" data-testid="stats-account-averages">
          <li v-for="metric in accountAverages" :key="metric.label">
            {{ metric.label }}:
            {{
              metric.value === null
                ? texts.noTarget
                : `${formatDecimal(metric.value)} ${metric.unit}`
            }}
          </li>
        </ul>
      </template>
      <details data-testid="stats-goal-history">
        <summary class="min-h-11 cursor-pointer py-3 text-sm font-medium">
          Pokaż cel konta obowiązujący w każdym dniu
        </summary>
        <ul class="grid gap-2 text-sm tabular-nums">
          <li
            v-for="entry in goalHistory"
            :key="entry.day"
            class="border-border border-t pt-2 [overflow-wrap:anywhere]"
          >
            {{ formatDate(entry.day) }} — {{ formatDecimal(entry.goal!.kcal) }} kcal
            <span class="text-muted-foreground"
              >(cel od {{ formatDate(entry.goal!.valid_from) }})</span
            >
            <span v-if="entry.goal?.protein_g != null">
              · B {{ formatDecimal(entry.goal.protein_g) }} g</span
            >
            <span v-if="entry.goal?.fat_g != null">
              · T {{ formatDecimal(entry.goal.fat_g) }} g</span
            >
            <span v-if="entry.goal?.carbs_g != null">
              · W {{ formatDecimal(entry.goal.carbs_g) }} g</span
            >
          </li>
        </ul>
      </details>
    </section>
  </section>
</template>
