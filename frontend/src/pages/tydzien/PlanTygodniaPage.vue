<script setup lang="ts">
/**
 * Plan tygodnia — widok 4 wizualizacji (06_UIUX §4.4), trasa `/tydzien/:weekStart?`.
 *
 * Układ: nagłówek z nawigacją tygodni → pasek akcji → siatka 7 dni × posiłki →
 * `BarChart` tygodnia. Na telefonie siatka schodzi do jednej kolumny; kolejność
 * treści zostaje ta sama.
 *
 * Stan serwera trzyma WYŁĄCZNIE TanStack Query (ADR-007) — strona nie kopiuje
 * dni do własnych ref-ów. Ref-y opisują tylko intencje UI (otwarty dialog,
 * przeciągany posiłek, wybrany dzień).
 *
 * **Przenoszenie posiłku** ma DWIE równoprawne drogi (06_UIUX §2, wymóg karty):
 * drag&drop (HTML5, desktop) oraz „Przenieś do dnia…" w menu ⋮ karty posiłku.
 * Wariant przyciskowy jest tym, który testuje E2E — jest stabilny w CI i jest
 * jedyną drogą na telefonie, gdzie DnD nie istnieje. Przeniesienie to `copy`
 * posiłku na dzień docelowy + `delete` źródła; robimy je w jednej mutacji, żeby
 * nie dało się zostawić duplikatu przy błędzie drugiego kroku.
 *
 * Żadna wartość odżywcza nie jest tu liczona — wszystko przychodzi z backendu
 * jako stringi dziesiętne (ADR-008), a strona tylko formatuje.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { CalendarDays, ChevronLeft, ChevronRight, Copy, Layers, Repeat, Save } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import type { PlanDay, PlanMeal } from '@/api/planning'
import { copyPlan, deleteMeal, fetchPlanDays } from '@/api/planning'
import { queryKeys } from '@/api/queryKeys'
import {
  applyCycle,
  createCycle,
  createDayTemplate,
  createWeekTemplate,
  fetchCycles,
  fetchDayTemplates,
  fetchWeekTemplates,
  instantiateDayTemplate,
  instantiateWeekTemplate,
} from '@/api/templates'
import BarChart from '@/components/charts/BarChart.vue'
import type { BarDatum } from '@/components/charts/BarChart.vue'
import BlockCopyDialog from '@/components/domain/planning/BlockCopyDialog.vue'
import CycleEditorDialog from '@/components/domain/planning/CycleEditorDialog.vue'
import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import ReuseHistoryDialog from '@/components/domain/planning/ReuseHistoryDialog.vue'
import TemplateApplyDialog from '@/components/domain/planning/TemplateApplyDialog.vue'
import TemplateSaveDialog from '@/components/domain/planning/TemplateSaveDialog.vue'
import { Button } from '@/components/ui/button'
import { addDays, isoDate, startOfWeek, weekDayLabel } from '@/lib/dates'
import { formatDecimal } from '@/lib/format'
import { statusLabel, statusToken } from '@/lib/nutrition'
import { currentWeekStart } from '@/lib/schemas/template'
import { common, plan as planTexts, recipes as recipeTexts, week as texts } from '@/lib/texts'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const DAYS_IN_WEEK = 7
/** Ile dni historii pokazuje „Użyj ponownie" — kwartał wstecz wystarcza. */
const HISTORY_DAYS = 90

/** Poniedziałek z trasy; brak parametru albo śmieci = bieżący tydzień. */
const weekStart = computed(() => {
  const raw = route.params.weekStart
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && value ? startOfWeek(value) : currentWeekStart()
})

const weekDates = computed(() =>
  Array.from({ length: DAYS_IN_WEEK }, (_unused, offset) => addDays(weekStart.value, offset)),
)
const weekEnd = computed(() => addDays(weekStart.value, DAYS_IN_WEEK - 1))
const today = computed(() => isoDate(new Date()))

/** Dzień, do którego odnoszą się akcje paska (domyślnie dziś albo poniedziałek). */
const selectedDate = ref(weekStart.value)
watch(
  weekDates,
  (dates) => {
    if (!dates.includes(selectedDate.value)) {
      selectedDate.value = dates.includes(today.value) ? today.value : (dates[0] ?? weekStart.value)
    }
  },
  { immediate: true },
)

function goToWeek(value: string): void {
  void router.push({ name: 'tydzien', params: { weekStart: startOfWeek(value) } })
}

// --- dane -----------------------------------------------------------------------------

const daysQuery = useQuery({
  queryKey: computed(() => queryKeys.planDays.range(weekStart.value, weekEnd.value)),
  queryFn: () => fetchPlanDays(weekStart.value, weekEnd.value),
})

const dayTemplatesQuery = useQuery({
  queryKey: queryKeys.templates.days,
  queryFn: fetchDayTemplates,
})

const weekTemplatesQuery = useQuery({
  queryKey: queryKeys.templates.weeks,
  queryFn: fetchWeekTemplates,
})

const cyclesQuery = useQuery({ queryKey: queryKeys.cycles.all, queryFn: fetchCycles })

/** Historia dla „Użyj ponownie" — wczytywana dopiero, gdy dialog jest otwarty. */
const historyOpen = ref(false)
const historyRange = computed(() => ({
  from: addDays(today.value, -HISTORY_DAYS),
  to: addDays(today.value, -1),
}))
const historyQuery = useQuery({
  queryKey: computed(() =>
    queryKeys.planDays.range(historyRange.value.from, historyRange.value.to),
  ),
  queryFn: () => fetchPlanDays(historyRange.value.from, historyRange.value.to),
  enabled: historyOpen,
})

/** Dni tygodnia w kolejności kalendarza; brakująca data = dzień pusty. */
const days = computed<{ date: string; day: PlanDay | null }[]>(() => {
  const byDate = new Map((daysQuery.data.value?.items ?? []).map((day) => [day.day, day]))
  return weekDates.value.map((date) => ({ date, day: byDate.get(date) ?? null }))
})

const history = computed(() =>
  [...(historyQuery.data.value?.items ?? [])]
    .filter((day) => day.meals.length > 0)
    .sort((left, right) => right.day.localeCompare(left.day)),
)

/** Cel kcal z pierwszego dnia, który go zna — cel jest dzienny, więc wspólny. */
const weekTarget = computed(() => {
  for (const entry of days.value) {
    const target = entry.day?.goal_progress.kcal.target
    if (target) {
      return target
    }
  }
  return null
})

const chartData = computed<BarDatum[]>(() =>
  days.value.map((entry) => ({
    label: weekDayLabel(entry.date),
    title: `${weekDayLabel(entry.date)} ${entry.date}`,
    highlighted: entry.date === today.value,
    segments: [
      {
        label: 'kcal',
        value: entry.day?.nutrition.kcal ?? '0',
        colorClass: statusToken(entry.day?.goal_progress.kcal.status ?? null).fill,
      },
    ],
  })),
)

const isWeekEmpty = computed(() =>
  days.value.every((entry) => (entry.day?.meals.length ?? 0) === 0),
)

// --- mutacje --------------------------------------------------------------------------

const actionError = ref<string | null>(null)
const actionWarnings = ref<string[]>([])

/**
 * Unieważnia WSZYSTKIE zakresy dni: akcje tygodniowe (cykl, blok, szablon)
 * potrafią dotknąć dat spoza widocznego tygodnia, a wtedy punktowe
 * unieważnienie jednego zakresu zostawiłoby nieświeży cache pod inną trasą.
 */
async function invalidatePlan(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
}

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

function closeDialogs(): void {
  openDialog.value = null
  historyOpen.value = false
  moveMealId.value = null
  actionError.value = null
}

const copyMutation = useMutation({
  mutationFn: copyPlan,
  onSuccess: async () => {
    actionError.value = null
    await invalidatePlan()
    closeDialogs()
  },
  onError: reportError,
})

const saveDayTemplateMutation = useMutation({
  mutationFn: createDayTemplate,
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.templates.days })
    closeDialogs()
  },
  onError: reportError,
})

const saveWeekTemplateMutation = useMutation({
  mutationFn: createWeekTemplate,
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.templates.weeks })
    closeDialogs()
  },
  onError: reportError,
})

const instantiateDayMutation = useMutation({
  mutationFn: (input: { templateId: number; dates: string[] }) =>
    instantiateDayTemplate(input.templateId, input.dates),
  onSuccess: async (result) => {
    actionError.value = null
    // `warnings` ma w kontrakcie wartość domyślną, więc w typach jest opcjonalne.
    actionWarnings.value = result.warnings ?? []
    await invalidatePlan()
    if (actionWarnings.value.length === 0) {
      closeDialogs()
    }
  },
  onError: reportError,
})

const instantiateWeekMutation = useMutation({
  mutationFn: (input: { templateId: number; weekStart: string }) =>
    instantiateWeekTemplate(input.templateId, input.weekStart),
  onSuccess: async (result) => {
    actionError.value = null
    // `warnings` ma w kontrakcie wartość domyślną, więc w typach jest opcjonalne.
    actionWarnings.value = result.warnings ?? []
    await invalidatePlan()
    if (actionWarnings.value.length === 0) {
      closeDialogs()
    }
  },
  onError: reportError,
})

const createCycleMutation = useMutation({
  mutationFn: createCycle,
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.cycles.all })
    closeDialogs()
  },
  onError: reportError,
})

const applyCycleMutation = useMutation({
  mutationFn: (input: { cycleId: number; dateFrom: string; dateTo: string }) =>
    applyCycle(input.cycleId, { date_from: input.dateFrom, date_to: input.dateTo }),
  onSuccess: async (result) => {
    actionError.value = null
    // `warnings` ma w kontrakcie wartość domyślną, więc w typach jest opcjonalne.
    actionWarnings.value = result.warnings ?? []
    await invalidatePlan()
    if (actionWarnings.value.length === 0) {
      closeDialogs()
    }
  },
  onError: reportError,
})

/**
 * Przeniesienie posiłku: kopia do dnia docelowego, potem usunięcie źródła.
 *
 * Kolejność ma znaczenie — gdyby najpierw poszło usunięcie, błąd kopiowania
 * skasowałby posiłek bez śladu. Przy tej kolejności najgorszy scenariusz to
 * duplikat, który użytkownik widzi i może usunąć.
 */
const moveMealMutation = useMutation({
  mutationFn: async (input: { mealId: number; target: string }) => {
    await copyPlan({ what: 'meal', source_meal_id: input.mealId, target_dates: [input.target] })
    await deleteMeal(input.mealId)
  },
  onSuccess: async () => {
    actionError.value = null
    await invalidatePlan()
    closeDialogs()
  },
  onError: reportError,
})

const pending = computed(
  () =>
    copyMutation.isPending.value ||
    saveDayTemplateMutation.isPending.value ||
    saveWeekTemplateMutation.isPending.value ||
    instantiateDayMutation.isPending.value ||
    instantiateWeekMutation.isPending.value ||
    createCycleMutation.isPending.value ||
    applyCycleMutation.isPending.value ||
    moveMealMutation.isPending.value,
)

// --- dialogi --------------------------------------------------------------------------

type DialogName = 'copy-day' | 'block' | 'template-save' | 'template-apply' | 'cycle' | 'reuse'

const openDialog = ref<DialogName | null>(null)
const copyDayDates = ref('')

function open(dialog: DialogName): void {
  actionError.value = null
  actionWarnings.value = []
  openDialog.value = dialog
  historyOpen.value = dialog === 'reuse'
  if (dialog === 'copy-day') {
    copyDayDates.value = ''
  }
}

// --- przenoszenie posiłku (DnD + wariant przyciskowy) ---------------------------------

const moveMealId = ref<number | null>(null)
const moveTarget = ref('')
/** Dzień, nad którym trzymany jest przeciągany posiłek — tylko podświetlenie. */
const dragOverDate = ref<string | null>(null)
const draggedMealId = ref<number | null>(null)

function startMoveByButton(meal: PlanMeal, fromDate: string): void {
  actionError.value = null
  moveMealId.value = meal.id
  moveTarget.value = weekDates.value.find((date) => date !== fromDate) ?? fromDate
}

function confirmMove(): void {
  if (moveMealId.value !== null && moveTarget.value) {
    moveMealMutation.mutate({ mealId: moveMealId.value, target: moveTarget.value })
  }
}

function onDragStart(event: DragEvent, mealId: number): void {
  draggedMealId.value = mealId
  event.dataTransfer?.setData('text/plain', String(mealId))
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
}

function onDrop(event: DragEvent, target: string): void {
  event.preventDefault()
  dragOverDate.value = null
  const raw = event.dataTransfer?.getData('text/plain')
  const mealId = raw ? Number.parseInt(raw, 10) : draggedMealId.value
  draggedMealId.value = null
  if (mealId !== null && Number.isFinite(mealId)) {
    moveMealMutation.mutate({ mealId, target })
  }
}

// --- akcje paska ----------------------------------------------------------------------

function submitCopyDay(dates: string[]): void {
  copyMutation.mutate({
    what: 'day',
    source_date: selectedDate.value,
    target_dates: dates,
  })
}

function submitBlock(input: {
  sourceFrom: string
  sourceDays: number
  repeatEach: number
  targetStart: string
}): void {
  copyMutation.mutate({
    what: 'block',
    source_from: input.sourceFrom,
    source_days: input.sourceDays,
    repeat_each: input.repeatEach,
    target_start: input.targetStart,
    target_dates: [],
  })
}

function submitTemplateSave(input: {
  kind: 'day' | 'week'
  name: string
  scope: 'private' | 'household'
  sourceDate: string
}): void {
  if (input.kind === 'day') {
    saveDayTemplateMutation.mutate({
      name: input.name,
      scope: input.scope,
      from_date: input.sourceDate,
    })
    return
  }
  saveWeekTemplateMutation.mutate({
    name: input.name,
    scope: input.scope,
    from_week_start: weekStart.value,
  })
}

function submitReuse(input: { sourceDate: string; dates: string[] }): void {
  copyMutation.mutate({
    what: 'day',
    source_date: input.sourceDate,
    target_dates: input.dates,
  })
}

const copyDayParsedDates = computed(() =>
  copyDayDates.value
    .split(/[\n,;]/)
    .map((line) => line.trim())
    .filter(Boolean),
)
</script>

<template>
  <div class="grid gap-4" data-testid="plan-tygodnia-page">
    <header class="grid gap-2">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 class="text-xl font-semibold">{{ texts.title }}</h1>
          <p class="text-muted-foreground text-sm tabular-nums">
            {{ texts.weekOf }} {{ weekStart }}
          </p>
        </div>

        <nav class="flex items-center gap-1" :aria-label="texts.title">
          <Button
            type="button"
            variant="outline"
            class="min-h-11 min-w-11"
            :aria-label="texts.previousWeek"
            data-testid="week-prev"
            @click="goToWeek(addDays(weekStart, -7))"
          >
            <ChevronLeft class="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11"
            data-testid="week-today"
            @click="goToWeek(today)"
          >
            {{ texts.currentWeek }}
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11 min-w-11"
            :aria-label="texts.nextWeek"
            data-testid="week-next"
            @click="goToWeek(addDays(weekStart, 7))"
          >
            <ChevronRight class="size-4" aria-hidden="true" />
          </Button>
        </nav>
      </div>

      <!-- Pasek akcji: wszystko, co robi się na tygodniu, w jednym miejscu. -->
      <div class="flex flex-wrap gap-2" data-testid="week-actions">
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="action-copy-day"
          @click="open('copy-day')"
        >
          <Copy class="size-4" aria-hidden="true" />
          {{ texts.copyDay }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="action-block"
          @click="open('block')"
        >
          <Layers class="size-4" aria-hidden="true" />
          {{ texts.duplicateBlock }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="action-template-save"
          @click="open('template-save')"
        >
          <Save class="size-4" aria-hidden="true" />
          {{ texts.saveAsTemplate }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="action-template-apply"
          @click="open('template-apply')"
        >
          {{ texts.applyTemplate }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="action-cycle"
          @click="open('cycle')"
        >
          <Repeat class="size-4" aria-hidden="true" />
          {{ texts.applyCycle }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="action-reuse"
          @click="open('reuse')"
        >
          <CalendarDays class="size-4" aria-hidden="true" />
          {{ texts.reuse }}
        </Button>
      </div>
    </header>

    <!-- Kopiuj dzień: prosty panel bez osobnego komponentu (jedno pole). -->
    <PlanningDialog
      :open="openDialog === 'copy-day'"
      :title="planTexts.copyDayTitle"
      :subtitle="planTexts.copyDaySubtitle"
      :submit-label="planTexts.copyDayApply"
      :submit-disabled="copyDayParsedDates.length === 0"
      :pending="pending"
      :error="actionError"
      testid="copy-day-dialog"
      @submit="submitCopyDay(copyDayParsedDates)"
      @close="closeDialogs()"
    >
      <p class="text-muted-foreground text-xs tabular-nums">
        {{ texts.templateSourceDay }}: <strong>{{ selectedDate }}</strong>
      </p>
      <label class="grid gap-1 text-sm">
        {{ planTexts.copyDayDates }}
        <textarea
          v-model="copyDayDates"
          rows="3"
          class="border-border bg-background rounded-md border px-3 py-2 tabular-nums"
          data-testid="copy-day-dates"
        ></textarea>
        <span class="text-muted-foreground text-xs">{{ texts.datesHint }}</span>
      </label>
    </PlanningDialog>

    <BlockCopyDialog
      :open="openDialog === 'block'"
      :source-from="selectedDate"
      :pending="pending"
      :error="actionError"
      @apply="submitBlock"
      @close="closeDialogs()"
    />

    <TemplateSaveDialog
      :open="openDialog === 'template-save'"
      :week-dates="weekDates"
      :selected-date="selectedDate"
      :pending="pending"
      :error="actionError"
      @apply="submitTemplateSave"
      @close="closeDialogs()"
    />

    <TemplateApplyDialog
      :open="openDialog === 'template-apply'"
      :day-templates="dayTemplatesQuery.data.value?.items ?? []"
      :week-templates="weekTemplatesQuery.data.value?.items ?? []"
      :week-start="weekStart"
      :selected-date="selectedDate"
      :pending="pending"
      :error="actionError"
      :warnings="actionWarnings"
      @apply-day="instantiateDayMutation.mutate($event)"
      @apply-week="instantiateWeekMutation.mutate($event)"
      @close="closeDialogs()"
    />

    <CycleEditorDialog
      :open="openDialog === 'cycle'"
      :cycles="cyclesQuery.data.value?.items ?? []"
      :week-templates="weekTemplatesQuery.data.value?.items ?? []"
      :week-start="weekStart"
      :pending="pending"
      :error="actionError"
      :warnings="actionWarnings"
      @save="
        createCycleMutation.mutate({
          name: $event.name,
          scope: $event.scope,
          template_ids: $event.templateIds,
          start_date: $event.startDate,
        })
      "
      @apply="applyCycleMutation.mutate($event)"
      @close="closeDialogs()"
    />

    <ReuseHistoryDialog
      :open="openDialog === 'reuse'"
      :history="history"
      :selected-date="selectedDate"
      :pending="pending"
      :error="actionError"
      @apply="submitReuse"
      @close="closeDialogs()"
    />

    <!-- Wariant PRZYCISKOWY przenoszenia posiłku (obowiązkowy, 06_UIUX §2). -->
    <PlanningDialog
      :open="moveMealId !== null"
      :title="texts.moveMealTitle"
      :subtitle="texts.moveMealSubtitle"
      :submit-label="texts.moveMealApply"
      :pending="pending"
      :error="actionError"
      testid="move-meal-dialog"
      @submit="confirmMove()"
      @close="closeDialogs()"
    >
      <label class="grid gap-1 text-sm">
        {{ texts.moveMealTarget }}
        <select
          v-model="moveTarget"
          class="border-border bg-background min-h-11 rounded-md border px-3"
          data-testid="move-meal-target"
        >
          <option v-for="date in weekDates" :key="date" :value="date">
            {{ weekDayLabel(date) }} · {{ date }}
          </option>
        </select>
      </label>
    </PlanningDialog>

    <p v-if="daysQuery.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>

    <p v-else-if="isWeekEmpty" class="text-muted-foreground text-sm" data-testid="week-empty">
      {{ texts.emptyWeek }}
    </p>

    <!-- Siatka: kolumna = dzień. Mobile-first — jedna kolumna, od `md` siedem. -->
    <ol class="grid gap-3 md:grid-cols-7" data-testid="week-grid">
      <li
        v-for="entry in days"
        :key="entry.date"
        class="border-border bg-card grid content-start gap-2 rounded-xl border p-2"
        :class="[
          entry.date === selectedDate ? 'ring-primary ring-2' : '',
          dragOverDate === entry.date ? 'border-primary bg-muted' : '',
        ]"
        :data-testid="`week-day-${entry.date}`"
        @dragover.prevent="dragOverDate = entry.date"
        @dragleave="dragOverDate = null"
        @drop="onDrop($event, entry.date)"
      >
        <header class="grid gap-1">
          <button
            type="button"
            class="text-left"
            :aria-label="`${texts.openDay} ${entry.date}`"
            :data-testid="`week-day-select-${entry.date}`"
            @click="selectedDate = entry.date"
          >
            <span class="text-sm font-medium" :class="entry.date === today ? 'text-primary' : ''">
              {{ weekDayLabel(entry.date) }}
            </span>
            <span class="text-muted-foreground block text-xs tabular-nums">{{ entry.date }}</span>
          </button>

          <p class="text-xs tabular-nums">
            <span :data-testid="`week-day-kcal-${entry.date}`">
              {{ formatDecimal(entry.day?.nutrition.kcal ?? '0') }} {{ recipeTexts.kcalUnit }}
            </span>
            <template v-if="entry.day?.goal_progress.kcal.target">
              <span aria-hidden="true"> / </span>
              <span class="text-muted-foreground">
                {{ formatDecimal(entry.day.goal_progress.kcal.target) }}
              </span>
            </template>
          </p>
          <p
            v-if="entry.day && statusLabel(entry.day.goal_progress.kcal.status)"
            class="text-xs"
            :class="statusToken(entry.day.goal_progress.kcal.status).text"
          >
            {{ statusLabel(entry.day.goal_progress.kcal.status) }}
          </p>
        </header>

        <p
          v-if="(entry.day?.meals.length ?? 0) === 0"
          class="text-muted-foreground text-xs"
          :data-testid="`week-day-empty-${entry.date}`"
        >
          {{ texts.dayEmpty }}
        </p>

        <ul v-else class="grid gap-2">
          <li
            v-for="meal in entry.day?.meals ?? []"
            :key="meal.id"
            class="border-border grid gap-1 rounded-lg border p-2"
            draggable="true"
            :data-testid="`week-meal-${meal.id}`"
            @dragstart="onDragStart($event, meal.id)"
            @dragend="draggedMealId = null"
          >
            <p class="truncate text-xs font-medium">{{ meal.name }}</p>
            <p class="text-muted-foreground text-xs tabular-nums">
              {{ formatDecimal(meal.nutrition.kcal) }} {{ recipeTexts.kcalUnit }}
            </p>

            <!-- Miniatury pozycji posiłku (widok 4: „karty posiłków z miniaturami"). -->
            <ul v-if="meal.items.length > 0" class="flex flex-wrap gap-1">
              <li v-for="item in meal.items" :key="item.id">
                <img
                  v-if="item.recipe_photo_thumb_url"
                  :src="item.recipe_photo_thumb_url"
                  :alt="item.recipe_name ?? planTexts.productItem"
                  class="size-8 rounded object-cover"
                  loading="lazy"
                />
                <span
                  v-else
                  class="bg-muted text-muted-foreground grid size-8 place-items-center rounded text-[10px]"
                  :title="item.recipe_name ?? item.product_name ?? planTexts.productItem"
                >
                  {{ (item.recipe_name ?? item.product_name ?? '?').slice(0, 2) }}
                </span>
              </li>
            </ul>

            <Button
              type="button"
              variant="ghost"
              class="min-h-11 justify-start text-xs"
              :data-testid="`week-meal-move-${meal.id}`"
              @click="startMoveByButton(meal, entry.date)"
            >
              {{ texts.moveMeal }}
            </Button>
          </li>
        </ul>

        <RouterLink
          class="text-primary min-h-11 text-xs underline underline-offset-2"
          :to="{ name: 'plan-dnia', params: { date: entry.date } }"
          :data-testid="`week-day-open-${entry.date}`"
        >
          {{ texts.openDay }}
        </RouterLink>
      </li>
    </ol>

    <section class="border-border bg-card grid gap-2 rounded-xl border p-3">
      <h2 class="text-sm font-medium">{{ texts.chartTitle }}</h2>
      <BarChart
        :data="chartData"
        :target="weekTarget"
        unit="kcal"
        :title="texts.chartTitle"
        testid="week-bar-chart"
      />
    </section>
  </div>
</template>
