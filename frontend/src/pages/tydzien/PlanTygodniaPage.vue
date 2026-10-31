<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import type { PlanDay, PlanMeal, PlanItem } from '@/api/planning'
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
import PageHeader from '@/components/domain/PageHeader.vue'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import DateMultiSelect from '@/components/domain/planning/DateMultiSelect.vue'
import PlanReusePreview from '@/components/domain/planning/PlanReusePreview.vue'
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
import { planNavigationContext, planNavigationTarget, validNavigationDate } from '@/lib/navigation'
import { currentWeekStart, dateListSchema } from '@/lib/schemas/template'
import { common, plan as planTexts, recipes as recipeTexts, week as texts } from '@/lib/texts'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const DAYS_IN_WEEK = 7
/** Ile dni historii pokazuje „Użyj ponownie" — kwartał wstecz wystarcza. */
const HISTORY_DAYS = 90

/** Poniedziałek z trasy; brak parametru albo śmieci = bieżący tydzień. */
const weekStart = computed(() => {
  const value = validNavigationDate(route.params.weekStart)
  return value ? startOfWeek(value) : currentWeekStart()
})

const weekDates = computed(() =>
  Array.from({ length: DAYS_IN_WEEK }, (_unused, offset) => addDays(weekStart.value, offset)),
)
const weekEnd = computed(() => addDays(weekStart.value, DAYS_IN_WEEK - 1))
const today = computed(() => isoDate(new Date()))

/** Dzień, do którego odnoszą się akcje paska (domyślnie dziś albo poniedziałek). */
const selectedDate = computed({
  get: () => planNavigationContext(route).selectedDate,
  set: (date: string) => {
    if (date === selectedDate.value || !weekDates.value.includes(date)) return
    void router.replace({
      query: { ...route.query, selectedDate: date, from: weekStart.value, to: weekEnd.value },
    })
  },
})

function goToWeek(value: string, selectedDateOverride?: string): void {
  const from = startOfWeek(value)
  const offset = weekDates.value.indexOf(selectedDate.value)
  // Tylko przycisk bieżącego tygodnia jawnie wskazuje dziś. Strzałki zawsze
  // zachowują offset, również gdy docelowy poniedziałek wypada dzisiaj.
  const date = selectedDateOverride ?? addDays(from, Math.max(0, offset))
  void router.push(
    planNavigationTarget('tydzien', { selectedDate: date, from, to: addDays(from, 6) }),
  )
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

const chartData = computed<BarDatum[]>(() =>
  days.value.map((entry) => ({
    label: weekDayLabel(entry.date),
    title: `${weekDayLabel(entry.date)} ${entry.date}`,
    highlighted: entry.date === today.value,
    empty: !entry.day?.meals.length,
    segments: [
      {
        label: 'kcal',
        value: entry.day?.nutrition.kcal ?? '0',
        colorClass: 'fill-primary',
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
const resultDates = ref<string[] | null>(null)
const successMessage = ref<string | null>(null)

function completed(dates: string[] = []): void {
  resultDates.value = dates
  successMessage.value = texts.completed
  closeDialogs()
}

const planningOpen = ref(false)
const planningDate = ref(selectedDate.value)
const planningMeal = ref<PlanMeal | null>(null)
const replacement = ref<PlanItem | null>(null)
function planDish(date: string, meal: PlanMeal | null = null, item: PlanItem | null = null): void {
  planningDate.value = date
  planningMeal.value = meal
  replacement.value = item
  planningOpen.value = true
}
function retryOptions(): void {
  void dayTemplatesQuery.refetch()
  void weekTemplatesQuery.refetch()
  void cyclesQuery.refetch()
}
function recipeSaved({ day }: { day: PlanDay }): void {
  planningOpen.value = false
  successMessage.value = texts.completed
  resultDates.value = [day.day]
  actionWarnings.value = []
}
function recipeTarget(id: number, date: string) {
  return {
    name: 'przepis-szczegol',
    params: { id },
    query: { returnTo: 'week', selectedDate: date, from: weekStart.value, to: weekEnd.value },
  }
}

/**
 * Unieważnia WSZYSTKIE zakresy dni: akcje tygodniowe (cykl, blok, szablon)
 * potrafią dotknąć dat spoza widocznego tygodnia, a wtedy punktowe
 * unieważnienie jednego zakresu zostawiłoby nieświeży cache pod inną trasą.
 */
async function invalidatePlan(): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.stats.all }),
  ])
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
  onSuccess: async (result) => {
    actionError.value = null
    await invalidatePlan()
    completed(result.items.map((day) => day.day))
  },
  onError: reportError,
})

const saveDayTemplateMutation = useMutation({
  mutationFn: createDayTemplate,
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.templates.days })
    completed()
  },
  onError: reportError,
})

const saveWeekTemplateMutation = useMutation({
  mutationFn: createWeekTemplate,
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.templates.weeks })
    completed()
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
    completed(result.items.map((day) => day.day))
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
    completed(result.items.map((day) => day.day))
  },
  onError: reportError,
})

const createCycleMutation = useMutation({
  mutationFn: createCycle,
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.cycles.all })
    completed()
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
    completed(result.items.map((day) => day.day))
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
    try {
      await deleteMeal(input.mealId)
    } catch {
      throw new Error(texts.movePartial)
    }
  },
  onSuccess: async () => {
    actionError.value = null
    await invalidatePlan()
    completed()
  },
  onError: async (error) => {
    await invalidatePlan()
    closeDialogs()
    actionError.value =
      error instanceof Error && error.message === texts.movePartial
        ? error.message
        : 'Nie udało się potwierdzić przeniesienia. Sprawdź oba dni przed kolejną próbą.'
  },
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
const copyDayDates = ref<string[]>([])
const copyPreviewReady = ref(false)
const reuseExpanded = ref(false)

function open(dialog: DialogName): void {
  actionError.value = null
  actionWarnings.value = []
  resultDates.value = null
  successMessage.value = null
  openDialog.value = dialog
  historyOpen.value = dialog === 'reuse'
  if (dialog === 'copy-day') {
    copyDayDates.value = []
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
  if (!pending.value && moveMealId.value !== null && moveTarget.value) {
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
  const sourceDate = days.value.find((entry) =>
    entry.day?.meals.some((meal) => meal.id === mealId),
  )?.date
  if (
    !pending.value &&
    sourceDate !== undefined &&
    sourceDate !== target &&
    mealId !== null &&
    Number.isFinite(mealId)
  ) {
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

const copyDayParsedDates = computed(() => dateListSchema.safeParse(copyDayDates.value.join('\n')))
</script>

<template>
  <div class="week-page grid min-w-0 gap-6" data-testid="plan-tygodnia-page">
    <PageHeader :title="texts.title" :description="`${weekStart} – ${weekEnd}`" decoration="wheat">
      <template #actions>
        <Button as-child
          ><RouterLink
            :to="planNavigationTarget('zakupy', { selectedDate, from: weekStart, to: weekEnd })"
            data-testid="week-shopping"
            >{{ texts.shopping }}</RouterLink
          ></Button
        >
      </template>
    </PageHeader>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <nav class="flex flex-wrap items-center gap-1" :aria-label="texts.title">
        <Button
          type="button"
          variant="outline"
          class="size-11"
          :aria-label="texts.previousWeek"
          data-testid="week-prev"
          @click="goToWeek(addDays(weekStart, -7))"
          ><ChevronLeft class="size-4" aria-hidden="true"
        /></Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="week-today"
          @click="goToWeek(today, today)"
          >{{ texts.currentWeek }}</Button
        >
        <Button
          type="button"
          variant="outline"
          class="size-11"
          :aria-label="texts.nextWeek"
          data-testid="week-next"
          @click="goToWeek(addDays(weekStart, 7))"
          ><ChevronRight class="size-4" aria-hidden="true"
        /></Button>
      </nav>
      <Button
        type="button"
        variant="outline"
        class="min-h-11"
        :aria-expanded="reuseExpanded"
        aria-controls="week-reuse-actions"
        data-testid="week-complete"
        @click="reuseExpanded = !reuseExpanded"
        >{{ texts.completePlan }}</Button
      >
    </div>
    <section
      v-if="reuseExpanded"
      id="week-reuse-actions"
      class="border-border bg-card grid gap-3 rounded-xl border p-4"
      data-testid="week-actions"
    >
      <p class="text-muted-foreground text-sm">{{ texts.appendNotice }}</p>
      <label class="grid gap-1 text-sm"
        >{{ texts.templateSourceDay }}
        <select
          v-model="selectedDate"
          class="border-border bg-background min-h-11 min-w-0 rounded-md border px-3"
          data-testid="week-source-date"
        >
          <option v-for="date in weekDates" :key="date" :value="date">
            {{ weekDayLabel(date) }} · {{ date }}
          </option>
        </select>
      </label>
      <div class="flex flex-wrap gap-2">
        <Button
          v-for="action in [
            ['copy-day', texts.copyDay, 'copy-day'],
            ['block', texts.duplicateBlock, 'block'],
            ['template-apply', texts.applyTemplate, 'template-apply'],
            ['cycle', texts.applyCycle, 'cycle'],
            ['reuse', texts.reuse, 'reuse'],
            ['template-save', texts.saveAsTemplate, 'template-save'],
          ] as const"
          :key="action[0]"
          type="button"
          variant="outline"
          class="min-h-11 whitespace-normal"
          :data-testid="`action-${action[2]}`"
          :disabled="daysQuery.isPending.value || !daysQuery.data.value"
          @click="open(action[0])"
          >{{ action[1] }}</Button
        >
      </div>
      <p
        v-if="
          dayTemplatesQuery.isPending.value ||
          weekTemplatesQuery.isPending.value ||
          cyclesQuery.isPending.value
        "
        role="status"
        class="text-sm"
      >
        {{ texts.optionsLoading }}
      </p>
      <div
        v-if="
          dayTemplatesQuery.isError.value ||
          weekTemplatesQuery.isError.value ||
          cyclesQuery.isError.value
        "
        role="alert"
        class="text-destructive text-sm"
      >
        <p>{{ texts.optionsError }}</p>
        <Button type="button" variant="outline" class="mt-2 min-h-11" @click="retryOptions()">{{
          texts.retry
        }}</Button>
      </div>
    </section>
    <section
      v-if="successMessage"
      class="border-border bg-card grid gap-2 rounded-xl border p-4"
      role="status"
      data-testid="week-result"
    >
      <p>{{ successMessage }}</p>
      <p v-if="resultDates?.length" class="text-sm break-words">
        {{ texts.resultDates }}: {{ resultDates.join(', ') }}
      </p>
      <ul v-if="actionWarnings.length" class="text-warning grid gap-1 text-sm">
        <li v-for="warning in actionWarnings" :key="warning">{{ warning }}</li>
      </ul>
    </section>
    <p
      v-if="actionError && !openDialog && moveMealId === null"
      role="alert"
      class="text-destructive break-words"
      data-testid="week-action-error"
    >
      {{ actionError }}
    </p>
    <p v-if="daysQuery.isPending.value" role="status" class="text-muted-foreground">
      {{ common.loading }}
    </p>
    <div
      v-else-if="daysQuery.isError.value && !daysQuery.data.value"
      role="alert"
      data-testid="week-load-error"
    >
      <p>{{ texts.loadError }}</p>
      <Button type="button" variant="outline" class="mt-3 min-h-11" @click="daysQuery.refetch()">{{
        texts.retry
      }}</Button>
    </div>
    <template v-else>
      <div v-if="daysQuery.isError.value" role="alert" data-testid="week-refresh-error">
        <p>{{ texts.refreshError }}</p>
        <Button
          type="button"
          variant="outline"
          class="mt-2 min-h-11"
          @click="daysQuery.refetch()"
          >{{ texts.retry }}</Button
        >
      </div>
      <p v-if="isWeekEmpty" class="text-muted-foreground text-sm" data-testid="week-empty">
        {{ texts.emptyWeek }}
      </p>
      <ol class="week-agenda grid min-w-0 gap-4" data-testid="week-grid">
        <li
          v-for="entry in days"
          :key="entry.date"
          class="week-day border-border bg-card grid min-w-0 content-start gap-4 rounded-2xl border p-4"
          :class="[
            entry.date === selectedDate ? 'ring-primary ring-2' : '',
            dragOverDate === entry.date ? 'border-primary bg-muted' : '',
          ]"
          :data-testid="`week-day-${entry.date}`"
          @dragover.prevent="dragOverDate = entry.date"
          @dragleave="dragOverDate = null"
          @drop="onDrop($event, entry.date)"
        >
          <header class="grid content-start gap-1">
            <button
              type="button"
              class="focus-visible:ring-ring min-h-11 rounded text-left focus-visible:ring-2"
              :aria-label="`Wybierz dzień ${entry.date}`"
              :aria-pressed="selectedDate === entry.date"
              :data-testid="`week-day-select-${entry.date}`"
              @click="selectedDate = entry.date"
            >
              <span
                class="text-lg font-semibold"
                :class="entry.date === today ? 'text-primary' : ''"
                >{{ weekDayLabel(entry.date) }}</span
              ><span class="text-muted-foreground block text-xs tabular-nums">{{
                entry.date
              }}</span>
            </button>
            <span v-if="entry.date === today" class="text-primary text-xs">Dzisiaj</span>
            <p
              v-if="entry.day?.meals.length"
              class="text-muted-foreground text-xs tabular-nums"
              :data-testid="`week-day-kcal-${entry.date}`"
            >
              {{ formatDecimal(entry.day.nutrition.kcal) }} {{ recipeTexts.kcalUnit }} · cały plan
            </p>
            <p v-if="entry.day && !entry.day.nutrition.complete" class="text-warning text-xs">
              {{ texts.incompleteNutrition }}
            </p>
            <RouterLink
              class="text-primary flex min-h-11 items-center text-xs underline underline-offset-2"
              :to="
                planNavigationTarget('plan-dnia', {
                  selectedDate: entry.date,
                  from: weekStart,
                  to: weekEnd,
                })
              "
              :data-testid="`week-day-open-${entry.date}`"
              >{{ texts.openDay }}</RouterLink
            >
          </header>
          <div class="grid min-w-0 content-start gap-3">
            <p
              v-if="!entry.day?.meals.length"
              class="text-muted-foreground text-sm"
              :data-testid="`week-day-empty-${entry.date}`"
            >
              {{ texts.dayEmpty }}
            </p>
            <ul v-else class="week-meals grid min-w-0 gap-4">
              <li
                v-for="meal in entry.day.meals"
                :key="meal.id"
                class="grid min-w-0 content-start gap-2"
                :draggable="!pending"
                :data-testid="`week-meal-${meal.id}`"
                @dragstart="onDragStart($event, meal.id)"
                @dragend="draggedMealId = null"
              >
                <h2 class="text-muted-foreground text-sm font-medium break-words">
                  {{ meal.name }}
                </h2>
                <p v-if="!meal.items.length" class="text-muted-foreground text-sm">
                  Brak dań w posiłku
                </p>
                <ul class="grid min-w-0 gap-2">
                  <li v-for="item in meal.items" :key="item.id" class="grid min-w-0 gap-1">
                    <RouterLink
                      v-if="item.recipe_id"
                      class="text-primary flex min-h-11 items-center gap-2 text-base leading-relaxed underline-offset-2 hover:underline"
                      :to="recipeTarget(item.recipe_id, entry.date)"
                      :data-testid="`week-recipe-${item.id}`"
                      ><img
                        v-if="item.recipe_photo_thumb_url"
                        :src="item.recipe_photo_thumb_url"
                        alt=""
                        class="size-10 shrink-0 rounded object-cover"
                        loading="lazy"
                      /><span class="min-w-0 break-words">{{ item.recipe_name }}</span></RouterLink
                    >
                    <p v-else class="text-base break-words">
                      {{ item.product_name ?? planTexts.productItem }}
                    </p>
                    <Button
                      v-if="item.recipe_id"
                      type="button"
                      variant="ghost"
                      class="min-h-11 justify-self-start"
                      :aria-label="`${texts.replaceDish}: ${item.recipe_name}`"
                      :data-testid="`week-replace-${item.id}`"
                      @click="planDish(entry.date, meal, item)"
                      >{{ texts.replaceDish }}</Button
                    >
                  </li>
                </ul>
                <div class="flex min-w-0 flex-wrap gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    class="min-h-11 whitespace-normal"
                    :data-testid="`week-meal-add-${meal.id}`"
                    :aria-label="`${texts.addToMeal}: ${meal.name}, ${entry.date}`"
                    @click="planDish(entry.date, meal)"
                    >{{ texts.addToMeal }}</Button
                  >
                  <Button
                    type="button"
                    variant="ghost"
                    class="min-h-11 whitespace-normal"
                    :disabled="pending"
                    :data-testid="`week-meal-move-${meal.id}`"
                    @click="startMoveByButton(meal, entry.date)"
                    >{{ texts.moveMeal }}</Button
                  >
                </div>
              </li>
            </ul>
            <Button
              type="button"
              variant="outline"
              class="min-h-11 justify-self-start whitespace-normal"
              :data-testid="`week-add-${entry.date}`"
              :aria-label="`${texts.newMealWithDish}: ${entry.date}`"
              @click="planDish(entry.date)"
              >{{ texts.newMealWithDish }}</Button
            >
            <details
              v-if="
                entry.day && !entry.day.nutrition.complete && entry.day.nutrition.missing.length
              "
              class="text-warning min-w-0 text-sm"
              :data-testid="`week-nutrition-details-${entry.date}`"
            >
              <summary
                class="focus-visible:ring-ring min-h-11 cursor-pointer rounded py-3 focus-visible:ring-2"
              >
                Braki danych odżywczych ({{ entry.day.nutrition.missing.length }})
              </summary>
              <ul
                class="text-muted-foreground grid list-disc gap-2 pl-5 text-xs leading-relaxed break-words"
                :data-testid="`week-nutrition-missing-${entry.date}`"
              >
                <li v-for="(missing, index) in entry.day.nutrition.missing" :key="index">
                  {{ missing }}
                </li>
              </ul>
            </details>
          </div>
        </li>
      </ol>
      <section class="border-border bg-card grid gap-3 rounded-2xl border p-4">
        <h2 class="text-base font-medium">{{ texts.chartTitle }}</h2>
        <p class="text-muted-foreground text-xs">{{ texts.wholePlan }}</p>
        <BarChart
          :data="chartData"
          unit="kcal"
          :title="texts.chartTitle"
          :empty-text="isWeekEmpty ? undefined : texts.zeroEnergyPlan"
          testid="week-bar-chart"
        />
      </section>
    </template>
    <RecipePlanningPanel
      :open="planningOpen"
      :recipe="null"
      :date="planningDate"
      :meal="planningMeal"
      :replace-item="replacement"
      @close="planningOpen = false"
      @saved="recipeSaved"
    />
    <PlanningDialog
      :open="openDialog === 'copy-day'"
      :title="planTexts.copyDayTitle"
      :subtitle="texts.appendNotice"
      :submit-label="planTexts.copyDayApply"
      :submit-disabled="!copyDayParsedDates.success || !copyPreviewReady"
      :pending="pending"
      :error="actionError"
      testid="copy-day-dialog"
      @submit="submitCopyDay(copyDayDates)"
      @close="closeDialogs()"
    >
      <template v-if="openDialog === 'copy-day'"
        ><DateMultiSelect
          v-model="copyDayDates"
          :initial-date="selectedDate"
          testid="copy-day-dates"
          :disabled="pending" /><PlanReusePreview
          :dates="copyDayDates"
          :source-dates="[selectedDate]"
          :source-label="selectedDate"
          @ready="copyPreviewReady = $event"
      /></template>
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
      :loading="dayTemplatesQuery.isPending.value || weekTemplatesQuery.isPending.value"
      :unavailable="dayTemplatesQuery.isError.value || weekTemplatesQuery.isError.value"
      :day-templates="dayTemplatesQuery.data.value?.items ?? []"
      :week-templates="weekTemplatesQuery.data.value?.items ?? []"
      :week-start="weekStart"
      :selected-date="selectedDate"
      :pending="pending"
      :error="
        actionError ??
        (dayTemplatesQuery.isError.value || weekTemplatesQuery.isError.value
          ? texts.optionsError
          : null)
      "
      :warnings="actionWarnings"
      @apply-day="instantiateDayMutation.mutate($event)"
      @apply-week="instantiateWeekMutation.mutate($event)"
      @close="closeDialogs()"
    />
    <CycleEditorDialog
      :open="openDialog === 'cycle'"
      :loading="
        cyclesQuery.isPending.value ||
        cyclesQuery.isFetching.value ||
        weekTemplatesQuery.isPending.value ||
        weekTemplatesQuery.isFetching.value
      "
      :unavailable="cyclesQuery.isError.value || weekTemplatesQuery.isError.value"
      :cycles="cyclesQuery.data.value?.items ?? []"
      :week-templates="weekTemplatesQuery.data.value?.items ?? []"
      :week-start="weekStart"
      :pending="pending"
      :error="
        actionError ??
        (cyclesQuery.isError.value || weekTemplatesQuery.isError.value ? texts.optionsError : null)
      "
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
      :loading="historyQuery.isPending.value"
      :unavailable="historyQuery.isError.value"
      :error="actionError ?? (historyQuery.isError.value ? texts.historyError : null)"
      @apply="submitReuse"
      @close="closeDialogs()"
    />
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
      <template #default="{ formId }"
        ><label class="grid gap-1 text-sm"
          >{{ texts.moveMealTarget
          }}<select
            v-model="moveTarget"
            :form="formId"
            class="border-border bg-background min-h-11 rounded-md border px-3"
            data-testid="move-meal-target"
          >
            <option
              v-for="date in weekDates.filter(
                (d) =>
                  !days
                    .find((entry) => entry.date === d)
                    ?.day?.meals.some((meal) => meal.id === moveMealId),
              )"
              :key="date"
              :value="date"
            >
              {{ weekDayLabel(date) }} · {{ date }}
            </option>
          </select></label
        ></template
      >
    </PlanningDialog>
  </div>
</template>

<style scoped>
.week-page {
  container-type: inline-size;
}
@container (min-width: 36rem) {
  .week-day {
    grid-template-columns: 9rem minmax(0, 1fr);
  }
  .week-meals {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
  }
}
@container (min-width: 84rem) {
  .week-agenda {
    grid-template-columns: repeat(7, minmax(0, 1fr));
  }
  .week-day {
    grid-template-columns: minmax(0, 1fr);
  }
  .week-meals {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
