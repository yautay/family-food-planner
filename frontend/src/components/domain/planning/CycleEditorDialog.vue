<script setup lang="ts">
/**
 * Cykl tygodni A→B→C: utworzenie/edycja + zastosowanie na zakres dat.
 *
 * KOLEJNOŚĆ listy JEST rotacją, więc kolejność musi być sterowalna. Sterujemy
 * nią STRZAŁKAMI, nie drag&dropem: lista ma 2–4 pozycje, a strzałki działają
 * identycznie na telefonie i z klawiatury (06_UIUX §2 — DnD tylko tam, gdzie
 * realnie szybszy). Ten sam szablon może wystąpić wielokrotnie („A, A, B" to
 * dwa tygodnie A, potem B).
 *
 * `date_from` przy zastosowaniu musi być poniedziałkiem — walidujemy to na
 * miejscu, żeby nie wysyłać żądania po znaną z góry odpowiedź 422.
 */
import { computed, ref, watch } from 'vue'

import type { Cycle, TemplateSummary } from '@/api/templates'
import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { addDays } from '@/lib/dates'
import { cycleApplySchema } from '@/lib/schemas/template'
import { common, week as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  cycles: Cycle[]
  weekTemplates: TemplateSummary[]
  /** Poniedziałek widocznego tygodnia — domyślny początek zakresu. */
  weekStart: string
  pending?: boolean
  error?: string | null
  warnings?: string[]
}>()

const emit = defineEmits<{
  (
    event: 'save',
    payload: {
      name: string
      scope: 'private' | 'household'
      templateIds: number[]
      startDate: string | null
    },
  ): void
  (event: 'apply', payload: { cycleId: number; dateFrom: string; dateTo: string }): void
  (event: 'close'): void
}>()

const mode = ref<'apply' | 'create'>('apply')

// --- tworzenie cyklu ---------------------------------------------------------------
const name = ref('')
const scope = ref<'private' | 'household'>('private')
const templateIds = ref<number[]>([])
const startDate = ref('')
const templateToAdd = ref<number | null>(null)

// --- zastosowanie cyklu ------------------------------------------------------------
const cycleId = ref<number | null>(null)
const dateFrom = ref(props.weekStart)
const dateTo = ref(addDays(props.weekStart, 13))

// `cycles` i `weekTemplates` są źródłami watcha — mogą dojechać PO otwarciu
// dialogu, a wtedy tryb „apply" nie miałby czego wybrać (ustalenie /code-review).
// Pola formularza tworzenia zerujemy TYLKO przy zmianie stanu otwarcia, żeby
// dociągnięcie listy nie wymazywało tego, co użytkownik już wpisał.
watch(
  () => props.open,
  (open) => {
    if (!open) {
      return
    }
    name.value = ''
    scope.value = 'private'
    templateIds.value = []
    startDate.value = props.weekStart
    dateFrom.value = props.weekStart
    dateTo.value = addDays(props.weekStart, 13)
  },
  { immediate: true },
)

watch(
  () => [props.open, props.cycles, props.weekTemplates] as const,
  ([open, cycles, weekTemplates]) => {
    if (!open) {
      return
    }
    if (!cycles.some((cycle) => cycle.id === cycleId.value)) {
      cycleId.value = cycles[0]?.id ?? null
    }
    if (!weekTemplates.some((template) => template.id === templateToAdd.value)) {
      templateToAdd.value = weekTemplates[0]?.id ?? null
    }
    mode.value = cycles.length > 0 ? 'apply' : 'create'
  },
  { immediate: true },
)

const templateName = (id: number): string =>
  props.weekTemplates.find((template) => template.id === id)?.name ?? `#${id}`

function addTemplate(): void {
  if (templateToAdd.value !== null) {
    templateIds.value = [...templateIds.value, templateToAdd.value]
  }
}

function removeAt(index: number): void {
  templateIds.value = templateIds.value.filter((_id, position) => position !== index)
}

/** Przesunięcie w liście = zmiana rotacji; `offset` to -1 (wyżej) albo 1 (niżej). */
function move(index: number, offset: -1 | 1): void {
  const target = index + offset
  if (target < 0 || target >= templateIds.value.length) {
    return
  }
  const next = [...templateIds.value]
  const [moved] = next.splice(index, 1)
  if (moved !== undefined) {
    next.splice(target, 0, moved)
  }
  templateIds.value = next
}

const createMessage = computed(() => {
  if (props.weekTemplates.length === 0) {
    return texts.cycleNeedsWeekTemplates
  }
  if (name.value.trim().length === 0) {
    return 'Podaj nazwę cyklu.'
  }
  return templateIds.value.length === 0 ? texts.cycleNeedsTemplate : null
})

const applyParsed = computed(() =>
  cycleApplySchema.safeParse({ dateFrom: dateFrom.value, dateTo: dateTo.value }),
)

const applyMessage = computed(() => {
  if (cycleId.value === null) {
    return texts.cycleEmpty
  }
  return applyParsed.value.success
    ? null
    : (applyParsed.value.error.issues[0]?.message ?? texts.datesInvalid)
})

const validationMessage = computed(() =>
  mode.value === 'create' ? createMessage.value : applyMessage.value,
)

function submit(): void {
  if (validationMessage.value !== null) {
    return
  }
  if (mode.value === 'create') {
    emit('save', {
      name: name.value.trim(),
      scope: scope.value,
      templateIds: templateIds.value,
      startDate: startDate.value || null,
    })
    return
  }
  if (cycleId.value !== null && applyParsed.value.success) {
    emit('apply', { cycleId: cycleId.value, ...applyParsed.value.data })
  }
}
</script>

<template>
  <PlanningDialog
    :open="open"
    :title="mode === 'create' ? texts.cycleTitle : texts.cycleApplyTitle"
    :subtitle="texts.cycleSubtitle"
    :submit-label="mode === 'create' ? texts.cycleSave : texts.cycleApplyApply"
    :submit-disabled="validationMessage !== null"
    :pending="pending"
    :error="error ?? validationMessage"
    :warnings="warnings"
    testid="cycle-editor-dialog"
    @submit="submit()"
    @close="emit('close')"
  >
    <div class="flex flex-wrap gap-2">
      <label class="flex min-h-11 items-center gap-2 text-sm">
        <input v-model="mode" type="radio" value="apply" data-testid="cycle-mode-apply" />
        {{ texts.cycleApplyApply }}
      </label>
      <label class="flex min-h-11 items-center gap-2 text-sm">
        <input v-model="mode" type="radio" value="create" data-testid="cycle-mode-create" />
        {{ common.add }}
      </label>
    </div>

    <template v-if="mode === 'apply'">
      <label class="grid gap-1 text-sm">
        {{ texts.cycleApplyPick }}
        <select
          v-model="cycleId"
          class="border-border bg-background min-h-11 rounded-md border px-3"
          data-testid="cycle-pick"
        >
          <option v-for="cycle in cycles" :key="cycle.id" :value="cycle.id">
            {{ cycle.name }} · {{ cycle.template_names.filter(Boolean).join(' → ') }}
          </option>
        </select>
      </label>

      <div class="grid gap-3 sm:grid-cols-2">
        <label class="grid gap-1 text-sm">
          {{ texts.cycleApplyFrom }}
          <Input v-model="dateFrom" type="date" class="min-h-11" data-testid="cycle-date-from" />
        </label>
        <label class="grid gap-1 text-sm">
          {{ texts.cycleApplyTo }}
          <Input v-model="dateTo" type="date" class="min-h-11" data-testid="cycle-date-to" />
        </label>
      </div>
    </template>

    <template v-else>
      <label class="grid gap-1 text-sm">
        {{ texts.cycleName }}
        <Input v-model="name" class="min-h-11" maxlength="200" data-testid="cycle-name" />
      </label>

      <div class="grid gap-2">
        <p class="text-muted-foreground text-xs">{{ texts.cycleTemplates }}</p>
        <ol v-if="templateIds.length > 0" class="grid gap-2" data-testid="cycle-template-list">
          <li
            v-for="(id, index) in templateIds"
            :key="`${id}-${index}`"
            class="border-border flex items-center gap-2 rounded-lg border p-2"
          >
            <span class="text-muted-foreground w-6 text-center text-sm tabular-nums">
              {{ index + 1 }}.
            </span>
            <span class="min-w-0 flex-1 truncate text-sm">{{ templateName(id) }}</span>
            <Button
              type="button"
              variant="ghost"
              class="min-h-11 min-w-11"
              :aria-label="texts.cycleMoveUp"
              :disabled="index === 0"
              :data-testid="`cycle-up-${index}`"
              @click="move(index, -1)"
            >
              &uarr;
            </Button>
            <Button
              type="button"
              variant="ghost"
              class="min-h-11 min-w-11"
              :aria-label="texts.cycleMoveDown"
              :disabled="index === templateIds.length - 1"
              :data-testid="`cycle-down-${index}`"
              @click="move(index, 1)"
            >
              &darr;
            </Button>
            <Button
              type="button"
              variant="ghost"
              class="min-h-11 min-w-11"
              :aria-label="texts.cycleRemoveTemplate"
              :data-testid="`cycle-remove-${index}`"
              @click="removeAt(index)"
            >
              &times;
            </Button>
          </li>
        </ol>

        <div v-if="weekTemplates.length > 0" class="flex flex-wrap items-end gap-2">
          <select
            v-model="templateToAdd"
            class="border-border bg-background min-h-11 flex-1 rounded-md border px-3"
            :aria-label="texts.cycleAddTemplate"
            data-testid="cycle-template-to-add"
          >
            <option v-for="template in weekTemplates" :key="template.id" :value="template.id">
              {{ template.name }}
            </option>
          </select>
          <Button
            type="button"
            variant="outline"
            class="min-h-11"
            data-testid="cycle-add-template"
            @click="addTemplate()"
          >
            {{ texts.cycleAddTemplate }}
          </Button>
        </div>
      </div>

      <label class="grid gap-1 text-sm">
        {{ texts.cycleStartDate }}
        <Input v-model="startDate" type="date" class="min-h-11" data-testid="cycle-start-date" />
        <span class="text-muted-foreground text-xs">{{ texts.cycleStartHint }}</span>
      </label>

      <label class="grid gap-1 text-sm">
        {{ texts.templateScope }}
        <select
          v-model="scope"
          class="border-border bg-background min-h-11 rounded-md border px-3"
          data-testid="cycle-scope"
        >
          <option value="private">{{ texts.templateScopePrivate }}</option>
          <option value="household">{{ texts.templateScopeHousehold }}</option>
        </select>
      </label>
    </template>
  </PlanningDialog>
</template>
