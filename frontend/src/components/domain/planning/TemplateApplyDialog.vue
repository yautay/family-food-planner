<script setup lang="ts">
/**
 * „Zastosuj szablon" — instancjacja szablonu dnia na daty albo tygodnia na tydzień.
 *
 * Bez inline create (wyjątek od 06_UIUX §3.1 świadomy i uzasadniony): szablon
 * NIE powstaje w formularzu, tylko z planu („Zapisz jako szablon"), więc nie ma
 * czego tworzyć w miejscu. Puste stany kierują do tej właśnie akcji.
 *
 * Instancjacja DOPISUJE posiłki do dni docelowych — tak samo jak `/plan/copy`
 * (zachowanie z B06). Mówimy o tym wprost w podtytule, bo to jedyna rzecz,
 * której użytkownik może się tu nie domyślić.
 */
import { computed, ref, watch } from 'vue'

import type { TemplateSummary } from '@/api/templates'
import TemplateSourcePreview from '@/components/domain/planning/TemplateSourcePreview.vue'
import DateMultiSelect from '@/components/domain/planning/DateMultiSelect.vue'
import PlanReusePreview from '@/components/domain/planning/PlanReusePreview.vue'
import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import { Input } from '@/components/ui/input'
import { addDays, weekDayLabel } from '@/lib/dates'
import { dateListSchema, isMonday } from '@/lib/schemas/template'
import { week as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  dayTemplates: TemplateSummary[]
  weekTemplates: TemplateSummary[]
  /** Poniedziałek widocznego tygodnia — domyślny cel wariantu tygodniowego. */
  weekStart: string
  /** Dzień, na którym stał użytkownik — domyślna data wariantu dziennego. */
  selectedDate: string
  unavailable?: boolean
  loading?: boolean
  pending?: boolean
  error?: string | null
  warnings?: string[]
}>()

const emit = defineEmits<{
  (event: 'apply-day', payload: { templateId: number; dates: string[] }): void
  (event: 'apply-week', payload: { templateId: number; weekStart: string }): void
  (event: 'close'): void
}>()

const kind = ref<'day' | 'week'>('day')
const dayTemplateId = ref<number | null>(null)
const weekTemplateId = ref<number | null>(null)
const dates = ref<string[]>([])
const previewReady = ref(false)
const sourceReady = ref(false)
const weekStartValue = ref(props.weekStart)

// DWA watche z rozmysłem. Pierwszy zeruje formularz przy OTWARCIU panelu —
// gdyby robił to ten drugi, dociągnięcie listy szablonów wymazywałoby daty
// wpisane właśnie przez użytkownika.
watch(
  () => props.open,
  (open) => {
    if (open) {
      dates.value = [props.selectedDate]
      weekStartValue.value = props.weekStart
    }
  },
  { immediate: true },
)

// Drugi pilnuje WYBORU: listy szablonów mogą dojechać PO otwarciu dialogu,
// a wtedy selecty zostałyby puste i submit byłby zablokowany aż do zamknięcia
// panelu (ustalenie /code-review). Wybór użytkownika zachowujemy, gdy nadal
// istnieje na liście.
watch(
  () => [props.open, props.dayTemplates, props.weekTemplates] as const,
  ([open, dayTemplates, weekTemplates]) => {
    if (!open) {
      return
    }
    if (!dayTemplates.some((template) => template.id === dayTemplateId.value)) {
      dayTemplateId.value = dayTemplates[0]?.id ?? null
    }
    if (!weekTemplates.some((template) => template.id === weekTemplateId.value)) {
      weekTemplateId.value = weekTemplates[0]?.id ?? null
    }
    // Wariant domyślny: dzień, gdy są szablony dnia; inaczej tydzień.
    if (kind.value === 'day' && !dayTemplates.length && weekTemplates.length) kind.value = 'week'
  },
  { immediate: true },
)

const parsedDates = computed(() => dateListSchema.safeParse(dates.value.join('\n')))

const validationMessage = computed(() => {
  if (props.loading || props.unavailable) return null
  if (kind.value === 'day') {
    if (dayTemplateId.value === null) {
      return texts.templateEmpty
    }
    return parsedDates.value.success
      ? null
      : (parsedDates.value.error.issues[0]?.message ?? texts.datesInvalid)
  }
  if (weekTemplateId.value === null) {
    return texts.templateEmpty
  }
  return isMonday(weekStartValue.value) ? null : texts.mondayRequired
})

const targetDates = computed(() =>
  kind.value === 'day'
    ? dates.value
    : isMonday(weekStartValue.value)
      ? Array.from({ length: 7 }, (_, offset) => addDays(weekStartValue.value, offset))
      : [],
)
const sourceLabel = computed(
  () =>
    (kind.value === 'day'
      ? props.dayTemplates.find((t) => t.id === dayTemplateId.value)
      : props.weekTemplates.find((t) => t.id === weekTemplateId.value)
    )?.name ?? '',
)

const canSubmit = computed(() => validationMessage.value === null)

function submit(): void {
  if (
    !canSubmit.value ||
    !previewReady.value ||
    !sourceReady.value ||
    props.unavailable ||
    props.loading
  ) {
    return
  }
  if (kind.value === 'day' && dayTemplateId.value !== null && parsedDates.value.success) {
    emit('apply-day', { templateId: dayTemplateId.value, dates: parsedDates.value.data })
    return
  }
  if (kind.value === 'week' && weekTemplateId.value !== null) {
    emit('apply-week', { templateId: weekTemplateId.value, weekStart: weekStartValue.value })
  }
}
</script>

<template>
  <PlanningDialog
    v-slot="{ formId }"
    :open="open"
    :title="texts.templateApplyTitle"
    :subtitle="texts.templateApplySubtitle"
    :submit-label="texts.templateApplyApply"
    :submit-disabled="!canSubmit || !previewReady || !sourceReady || unavailable || loading"
    :pending="pending"
    :error="error"
    :validation-message="validationMessage"
    :warnings="warnings"
    testid="template-apply-dialog"
    @submit="submit()"
    @close="emit('close')"
  >
    <p v-if="loading" role="status" class="text-sm">{{ texts.optionsLoading }}</p>
    <fieldset class="grid gap-2">
      <legend class="text-muted-foreground text-xs">{{ texts.templateKind }}</legend>
      <div class="flex flex-wrap gap-2">
        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input
            v-model="kind"
            :form="formId"
            type="radio"
            value="day"
            data-testid="apply-kind-day"
          />
          {{ texts.templateKindDay }}
        </label>
        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input
            v-model="kind"
            :form="formId"
            type="radio"
            value="week"
            data-testid="apply-kind-week"
          />
          {{ texts.templateKindWeek }}
        </label>
      </div>
    </fieldset>

    <template v-if="kind === 'day'">
      <label class="grid gap-1 text-sm">
        {{ texts.templateApplyPick }}
        <select
          v-model="dayTemplateId"
          :form="formId"
          class="border-border bg-background min-h-11 rounded-md border px-3"
          data-testid="apply-day-template"
        >
          <option v-for="template in dayTemplates" :key="template.id" :value="template.id">
            {{ template.name }} · {{ template.summary }}
          </option>
        </select>
      </label>

      <DateMultiSelect
        v-if="open"
        v-model="dates"
        :initial-date="selectedDate"
        :disabled="pending"
        testid="apply-dates"
      />
    </template>

    <template v-else>
      <label class="grid gap-1 text-sm">
        {{ texts.templateApplyPick }}
        <select
          v-model="weekTemplateId"
          :form="formId"
          class="border-border bg-background min-h-11 rounded-md border px-3"
          data-testid="apply-week-template"
        >
          <option v-for="template in weekTemplates" :key="template.id" :value="template.id">
            {{ template.name }} · {{ template.summary }}
          </option>
        </select>
      </label>

      <label class="grid gap-1 text-sm">
        {{ texts.templateApplyWeekStart }}
        <Input
          v-model="weekStartValue"
          :form="formId"
          type="date"
          class="min-h-11"
          data-testid="apply-week-start"
        />
        <span class="text-muted-foreground text-xs">
          {{ weekDayLabel(weekStartValue) }} · {{ texts.mondayRequired }}
        </span>
      </label>
    </template>
    <PlanReusePreview
      v-if="open"
      :dates="targetDates"
      :source-label="sourceLabel"
      @ready="previewReady = $event"
    />
    <TemplateSourcePreview
      v-if="open"
      :references="
        kind === 'day'
          ? dayTemplateId
            ? [{ kind: 'day', id: dayTemplateId }]
            : []
          : weekTemplateId
            ? [{ kind: 'week', id: weekTemplateId }]
            : []
      "
      @ready="sourceReady = $event"
    />
  </PlanningDialog>
</template>
