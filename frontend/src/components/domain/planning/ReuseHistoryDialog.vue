<script setup lang="ts">
/**
 * „Użyj ponownie" — kopiowanie dnia z HISTORII na nowe daty (02_DOMAIN §7).
 *
 * Historia nie ma osobnego endpointu i mieć nie musi: to zwykłe `plan_days`
 * z przeszłości, więc akcja to `/plan/copy` z przeszłą datą źródłową. Dialog
 * pokazuje ostatnie NIEPUSTE dni, bo lista wszystkich dat byłaby kalendarzem,
 * a użytkownik szuka „tego dnia, który mi wyszedł".
 */
import { computed, ref, watch } from 'vue'

import type { PlanDay } from '@/api/planning'
import DateMultiSelect from '@/components/domain/planning/DateMultiSelect.vue'
import PlanReusePreview from '@/components/domain/planning/PlanReusePreview.vue'
import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import { weekDayLabel } from '@/lib/dates'
import { formatDecimal } from '@/lib/format'
import { dateListSchema } from '@/lib/schemas/template'
import { recipes as recipeTexts, week as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  /** Dni z przeszłości (już przefiltrowane do niepustych, najnowsze pierwsze). */
  history: PlanDay[]
  /** Domyślna data docelowa — dzień, na którym stał użytkownik. */
  selectedDate: string
  unavailable?: boolean
  loading?: boolean
  pending?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  (event: 'apply', payload: { sourceDate: string; dates: string[] }): void
  (event: 'close'): void
}>()

const sourceDate = ref<string | null>(null)
const dates = ref<string[]>([])
const previewReady = ref(false)

// Reset pól przy OTWARCIU panelu (osobno od wyboru źródła poniżej).
watch(
  () => props.open,
  (open) => {
    if (open) {
      dates.value = [props.selectedDate]
    }
  },
  { immediate: true },
)

// `history` MUSI być źródłem tego watcha: zapytanie o historię włącza się
// dopiero przy otwarciu dialogu, więc dane ZAWSZE przychodzą po pierwszym
// przebiegu. Bez tego `sourceDate` zostawałby `null` i dialog byłby na zawsze
// zablokowany komunikatem „brak historii" (ustalenie /code-review).
watch(
  () => [props.open, props.history] as const,
  ([open, history]) => {
    if (!open) {
      return
    }
    // Zachowujemy wybór użytkownika, jeśli nadal jest na liście.
    if (!history.some((day) => day.day === sourceDate.value)) {
      sourceDate.value = history[0]?.day ?? null
    }
  },
  { immediate: true },
)

const parsedDates = computed(() => dateListSchema.safeParse(dates.value.join('\n')))

const validationMessage = computed(() => {
  if (sourceDate.value === null) {
    return props.loading || props.error ? null : texts.reuseEmpty
  }
  return parsedDates.value.success
    ? null
    : (parsedDates.value.error.issues[0]?.message ?? texts.datesInvalid)
})

function label(day: PlanDay): string {
  const meals = day.meals.length
  const kcal = formatDecimal(day.nutrition.kcal)
  return `${weekDayLabel(day.day)} ${day.day} · ${meals} × posiłek · ${kcal} ${recipeTexts.kcalUnit}`
}

function submit(): void {
  if (
    validationMessage.value !== null ||
    sourceDate.value === null ||
    !previewReady.value ||
    props.pending ||
    props.loading ||
    props.unavailable
  ) {
    return
  }
  if (parsedDates.value.success) {
    emit('apply', { sourceDate: sourceDate.value, dates: parsedDates.value.data })
  }
}
</script>

<template>
  <PlanningDialog
    v-slot="{ formId }"
    :open="open"
    :title="texts.reuseTitle"
    :subtitle="texts.reuseSubtitle"
    :submit-label="texts.reuseApply"
    :submit-disabled="validationMessage !== null || !previewReady || unavailable || loading"
    :pending="pending"
    :error="error"
    :validation-message="validationMessage"
    testid="reuse-history-dialog"
    @submit="submit()"
    @close="emit('close')"
  >
    <p v-if="loading" role="status" class="text-sm">{{ texts.historyLoading }}</p>
    <label v-if="history.length > 0" class="grid gap-1 text-sm">
      {{ texts.reuseSource }}
      <select
        v-model="sourceDate"
        :form="formId"
        class="border-border bg-background min-h-11 rounded-md border px-3"
        data-testid="reuse-source"
      >
        <option v-for="day in history" :key="day.day" :value="day.day">
          {{ label(day) }}
        </option>
      </select>
    </label>

    <DateMultiSelect
      v-if="open"
      v-model="dates"
      :initial-date="selectedDate"
      :disabled="pending"
      :label="texts.reuseTargets"
      testid="reuse-dates"
    />
    <PlanReusePreview
      v-if="open && sourceDate"
      :dates="dates"
      :source-dates="[sourceDate]"
      :source-label="sourceDate"
      @ready="previewReady = $event"
    />
  </PlanningDialog>
</template>
