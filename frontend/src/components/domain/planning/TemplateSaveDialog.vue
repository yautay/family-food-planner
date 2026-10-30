<script setup lang="ts">
/**
 * „Zapisz jako szablon" — z DNIA albo z całego widocznego TYGODNIA.
 *
 * Szablon powstaje z planu, nie z pustego formularza (03_DATABASE §6: payload
 * jest zamrożoną kopią struktury). Dlatego dialog nie ma edytora posiłków —
 * pyta tylko o nazwę, widoczność i źródło. Edycją szablonu jest plan plus
 * ponowny zapis.
 */
import { computed, ref, watch } from 'vue'

import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import { Input } from '@/components/ui/input'
import { weekDayLabel } from '@/lib/dates'
import { week as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  /** Dni widocznego tygodnia (7 dat ISO) — źródło dla wariantu „dzień". */
  weekDates: string[]
  /** Dzień, na którym stał użytkownik. */
  selectedDate: string
  pending?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  (
    event: 'apply',
    payload: {
      kind: 'day' | 'week'
      name: string
      scope: 'private' | 'household'
      sourceDate: string
    },
  ): void
  (event: 'close'): void
}>()

const kind = ref<'day' | 'week'>('day')
const name = ref('')
const scope = ref<'private' | 'household'>('private')
const sourceDate = ref(props.selectedDate)

watch(
  () => [props.open, props.selectedDate] as const,
  ([open, selected]) => {
    if (open) {
      kind.value = 'day'
      name.value = ''
      scope.value = 'private'
      sourceDate.value = selected
    }
  },
  { immediate: true },
)

const trimmedName = computed(() => name.value.trim())
const canSubmit = computed(() => trimmedName.value.length > 0)

function submit(): void {
  if (!canSubmit.value) {
    return
  }
  emit('apply', {
    kind: kind.value,
    name: trimmedName.value,
    scope: scope.value,
    sourceDate: sourceDate.value,
  })
}
</script>

<template>
  <PlanningDialog
    v-slot="{ formId }"
    :open="open"
    :title="texts.templateSaveTitle"
    :subtitle="texts.templateSaveSubtitle"
    :submit-label="texts.templateSaveApply"
    :submit-disabled="!canSubmit"
    :pending="pending"
    :error="error"
    testid="template-save-dialog"
    @submit="submit()"
    @close="emit('close')"
  >
    <fieldset class="grid gap-2">
      <legend class="text-muted-foreground text-xs">{{ texts.templateKind }}</legend>
      <div class="flex flex-wrap gap-2">
        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input
            v-model="kind"
            :form="formId"
            type="radio"
            value="day"
            data-testid="template-kind-day"
          />
          {{ texts.templateKindDay }}
        </label>
        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input
            v-model="kind"
            :form="formId"
            type="radio"
            value="week"
            data-testid="template-kind-week"
          />
          {{ texts.templateKindWeek }}
        </label>
      </div>
    </fieldset>

    <label v-if="kind === 'day'" class="grid gap-1 text-sm">
      {{ texts.templateSourceDay }}
      <select
        v-model="sourceDate"
        :form="formId"
        class="border-border bg-background min-h-11 rounded-md border px-3"
        data-testid="template-source-day"
      >
        <option v-for="date in weekDates" :key="date" :value="date">
          {{ weekDayLabel(date) }} · {{ date }}
        </option>
      </select>
    </label>

    <label class="grid gap-1 text-sm">
      {{ texts.templateName }}
      <Input
        v-model="name"
        :form="formId"
        class="min-h-11"
        maxlength="200"
        :placeholder="kind === 'day' ? 'np. Dzień warzywny' : 'np. Tydzień bazowy'"
        data-testid="template-name"
      />
    </label>

    <label class="grid gap-1 text-sm">
      {{ texts.templateScope }}
      <select
        v-model="scope"
        :form="formId"
        class="border-border bg-background min-h-11 rounded-md border px-3"
        data-testid="template-scope"
      >
        <option value="private">{{ texts.templateScopePrivate }}</option>
        <option value="household">{{ texts.templateScopeHousehold }}</option>
      </select>
    </label>
  </PlanningDialog>
</template>
