<script setup lang="ts">
/**
 * Ilość + jednostka (05_FRONTEND §4).
 *
 * Pole pracuje na STRINGU dziesiętnym, nie na `Number`: taki format przyjmuje
 * i zwraca API (ADR-008), a konwersja tam i z powrotem gubiłaby precyzję.
 * Użytkownik wpisuje po polsku (przecinek), `v-model` oddaje kanoniczny zapis
 * z kropką — tłumaczy to `src/lib/decimal.ts`, jedyny parser w aplikacji.
 *
 * Walidacja jest tu wyłącznie podpowiedzią UX; prawdą jest odpowiedź serwera
 * (05_FRONTEND §5). Od BATCH_05 komponent konsumują składniki przepisów,
 * spiżarnia i pozycje planu — stąd jednostki podawane z zewnątrz.
 */
import { computed, ref, watch } from 'vue'

import { Input } from '@/components/ui/input'
import { isValidDecimal, normalizeDecimalInput, toDecimalInput } from '@/lib/decimal'

const props = withDefaults(
  defineProps<{
    /** Kanoniczny string dziesiętny (`"12.5"`) albo `null`, gdy pusto. */
    modelValue: string | null
    /** Wybrana jednostka; pomijana, gdy `units` jest puste. */
    unit?: string
    /** Lista jednostek do wyboru (systemowe + domowe przeliczniki produktu). */
    units?: readonly string[]
    label?: string
    /** Liczba miejsc po przecinku wynikająca ze skali kolumny NUMERIC. */
    decimalPlaces?: number
    /** Czy wartość musi być większa od zera (ilość — tak, wartość odżywcza — nie). */
    positive?: boolean
    required?: boolean
    disabled?: boolean
    testid?: string
    hint?: string
  }>(),
  {
    unit: undefined,
    units: () => [],
    label: 'Ilość',
    decimalPlaces: 2,
    positive: true,
    required: false,
    disabled: false,
    testid: 'amount',
    hint: undefined,
  },
)

const emit = defineEmits<{
  /**
   * Wpisana wartość w kanonicznym zapisie (przecinek → kropka) albo `null` dla
   * pustego pola. UWAGA: w trakcie pisania może to być tekst niebędący liczbą —
   * o poprawności mówi `update:valid`, a ostatecznie i tak serwer (422).
   */
  (event: 'update:modelValue', value: string | null): void
  (event: 'update:unit', value: string): void
  /** Czy bieżąca zawartość pola nadaje się do wysłania (gate dla przycisku zapisu). */
  (event: 'update:valid', valid: boolean): void
}>()

/** Bufor tekstowy pola: użytkownik w trakcie pisania może mieć „12," — to nie błąd. */
const draft = ref(toDecimalInput(props.modelValue))

watch(
  () => props.modelValue,
  (value) => {
    // Nie nadpisujemy tego, co użytkownik właśnie pisze — tylko zmiany z zewnątrz.
    if (normalizeDecimalInput(draft.value) !== (value ?? '')) {
      draft.value = toDecimalInput(value)
    }
  },
)

const isEmpty = computed(() => draft.value.trim() === '')
const isValid = computed(
  () =>
    (isEmpty.value && !props.required) ||
    isValidDecimal(draft.value, {
      decimalPlaces: props.decimalPlaces,
      positive: props.positive,
    }),
)

function onInput(value: string | number): void {
  draft.value = String(value)
  const trimmed = draft.value.trim()
  emit('update:modelValue', trimmed === '' ? null : normalizeDecimalInput(trimmed))
  emit('update:valid', isValid.value)
}

const inputId = computed(() => `${props.testid}-input`)
const hasUnits = computed(() => props.units.length > 0)
</script>

<template>
  <div class="grid gap-2">
    <label class="text-sm font-medium" :for="inputId">{{ label }}</label>

    <div class="flex gap-2">
      <Input
        :id="inputId"
        :model-value="draft"
        inputmode="decimal"
        class="min-h-11 tabular-nums"
        :disabled="disabled"
        :aria-invalid="!isValid"
        :data-testid="testid"
        @update:model-value="onInput"
      />

      <select
        v-if="hasUnits"
        class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
        :value="unit"
        :disabled="disabled"
        :aria-label="`Jednostka — ${label}`"
        :data-testid="`${testid}-unit`"
        @change="emit('update:unit', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="option in units" :key="option" :value="option">{{ option }}</option>
      </select>
    </div>

    <p
      v-if="hint || !isValid"
      class="text-xs"
      :class="isValid ? 'text-muted-foreground' : 'text-destructive'"
      :data-testid="`${testid}-hint`"
    >
      {{ isValid ? hint : 'Podaj liczbę, np. 12,5.' }}
    </p>
  </div>
</template>
