<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { addDays, endOfMonth, formatDate, startOfMonth, startOfWeek } from '@/lib/dates'
import { COPY_TARGETS_LIMIT } from '@/lib/schemas/template'
import { week as texts } from '@/lib/texts'

const props = defineProps<{
  modelValue: string[]
  initialDate: string
  label?: string
  testid: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [dates: string[]] }>()
const month = ref(startOfMonth(props.initialDate))
const focused = ref(props.initialDate)
const calendar = ref<HTMLElement>()
const monthLabel = computed(() =>
  new Intl.DateTimeFormat('pl-PL', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(`${month.value}T12:00:00Z`),
  ),
)
const dates = computed(() => {
  const first = startOfWeek(month.value)
  return Array.from({ length: 42 }, (_, offset) => addDays(first, offset))
})
function changeMonth(offset: -1 | 1): void {
  month.value =
    offset === 1 ? addDays(endOfMonth(month.value), 1) : startOfMonth(addDays(month.value, -1))
  focused.value = month.value
}
function toggle(date: string): void {
  if (props.disabled) return
  const selected = props.modelValue.includes(date)
  if (!selected && props.modelValue.length >= COPY_TARGETS_LIMIT) return
  emit(
    'update:modelValue',
    selected ? props.modelValue.filter((d) => d !== date) : [...props.modelValue, date].sort(),
  )
}
async function keydown(event: KeyboardEvent, date: string): Promise<void> {
  const offsets: Record<string, number> = {
    ArrowLeft: -1,
    ArrowRight: 1,
    ArrowUp: -7,
    ArrowDown: 7,
  }
  let target: string | undefined
  if (event.key in offsets) target = addDays(date, offsets[event.key]!)
  if (event.key === 'Home') target = startOfWeek(date)
  if (event.key === 'End') target = addDays(startOfWeek(date), 6)
  if (event.key === 'PageUp' || event.key === 'PageDown') {
    changeMonth(event.key === 'PageUp' ? -1 : 1)
    target = month.value
  }
  if (!target) return
  event.preventDefault()
  focused.value = target
  month.value = startOfMonth(target)
  await nextTick()
  calendar.value?.querySelector<HTMLButtonElement>(`[data-date="${target}"]`)?.focus()
}
</script>

<template>
  <fieldset class="grid min-w-0 gap-3" :data-testid="testid" :disabled="disabled">
    <legend class="mb-2 text-sm font-medium">{{ label ?? texts.templateApplyDates }}</legend>
    <p class="text-muted-foreground text-xs">{{ texts.calendarHint }}</p>
    <div class="flex min-w-0 items-center justify-between gap-1">
      <Button
        type="button"
        variant="outline"
        class="size-11 shrink-0"
        :aria-label="texts.previousMonth"
        :data-testid="`${testid}-prev`"
        @click="changeMonth(-1)"
        ><ChevronLeft class="size-4" aria-hidden="true"
      /></Button>
      <span class="text-center text-sm font-medium capitalize" aria-live="polite">{{
        monthLabel
      }}</span>
      <Button
        type="button"
        variant="outline"
        class="size-11 shrink-0"
        :aria-label="texts.nextMonth"
        :data-testid="`${testid}-next`"
        @click="changeMonth(1)"
        ><ChevronRight class="size-4" aria-hidden="true"
      /></Button>
    </div>
    <div ref="calendar" class="grid grid-cols-7" role="group" :aria-label="monthLabel">
      <span
        v-for="labelText in ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd']"
        :key="labelText"
        class="text-muted-foreground py-2 text-center text-xs"
        aria-hidden="true"
        >{{ labelText }}</span
      >
      <button
        v-for="date in dates"
        :key="date"
        type="button"
        class="focus-visible:ring-ring min-h-11 min-w-0 rounded-md border text-sm tabular-nums focus-visible:ring-2"
        :class="
          modelValue.includes(date)
            ? 'bg-primary text-primary-foreground border-primary'
            : 'border-transparent hover:bg-muted'
        "
        :aria-label="formatDate(date)"
        :aria-pressed="modelValue.includes(date)"
        :tabindex="focused === date ? 0 : -1"
        :data-date="date"
        :data-testid="`${testid}-${date}`"
        :disabled="disabled"
        :aria-disabled="!modelValue.includes(date) && modelValue.length >= COPY_TARGETS_LIMIT"
        @focus="focused = date"
        @keydown="keydown($event, date)"
        @click="toggle(date)"
      >
        <span
          :class="
            date.slice(0, 7) !== month.slice(0, 7) && !modelValue.includes(date)
              ? 'text-muted-foreground'
              : ''
          "
          >{{ Number(date.slice(8)) }}</span
        >
      </button>
    </div>
    <p class="text-muted-foreground text-xs" aria-live="polite">
      {{ texts.selectedDates }}: {{ modelValue.length }} / {{ COPY_TARGETS_LIMIT }}
    </p>
    <ul v-if="modelValue.length" class="flex flex-wrap gap-2" :aria-label="texts.selectedDates">
      <li v-for="date in modelValue" :key="date">
        <button
          type="button"
          class="border-border hover:bg-muted min-h-11 rounded-md border px-2 text-xs tabular-nums"
          :aria-label="`${texts.removeDate} ${formatDate(date)}`"
          :data-testid="`${testid}-remove-${date}`"
          @click="toggle(date)"
        >
          {{ formatDate(date) }} ×
        </button>
      </li>
    </ul>
  </fieldset>
</template>
