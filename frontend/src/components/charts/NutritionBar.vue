<script setup lang="ts">
/**
 * Pasek wartość/cel — własne SVG, zero bibliotek wykresów (ADR-013).
 *
 * Kolor niesie status (bursztyn/zieleń/czerwień z tokens 06_UIUX §1), ale
 * NIGDY sam: obok paska stoi tekst, a cały wykres ma `role="img"` z
 * `aria-label` zawierającym wartość, cel i status słowny (06_UIUX §1 i §3.5).
 *
 * Komponent nie liczy nic domenowego: wartość, cel i status przychodzą
 * z backendu jako stringi dziesiętne (ADR-008); tu zamieniamy je na
 * PROCENT WYPEŁNIENIA, czyli czystą geometrię.
 */
import { computed } from 'vue'

import type { GoalStatus } from '@/api/planning'
import { formatDecimal } from '@/lib/format'
import { statusLabel, statusToken } from '@/lib/nutrition'

const props = withDefaults(
  defineProps<{
    /** Etykieta, np. „Kalorie" — trafia też do `aria-label`. */
    label: string
    /** Wartość bieżąca (string dziesiętny z API). */
    value: string
    /** Cel; `null` = użytkownik nie ustawił celu dla tej wartości. */
    target?: string | null
    status?: GoalStatus | null
    /** Jednostka do etykiety tekstowej (kcal, g). */
    unit?: string
    /** Pionowy wariant — mini-słupki tygodnia w panelu bocznym. */
    orientation?: 'horizontal' | 'vertical'
    testid?: string
  }>(),
  {
    target: null,
    status: null,
    unit: '',
    orientation: 'horizontal',
    testid: 'nutrition-bar',
  },
)

/** Ile procent celu wypełnia wartość (0–100 na potrzeby geometrii paska). */
const fillPercent = computed(() => {
  const value = Number.parseFloat(props.value)
  const target = props.target === null ? Number.NaN : Number.parseFloat(props.target)
  if (!Number.isFinite(value) || !Number.isFinite(target) || target <= 0) {
    return 0
  }
  return Math.min(100, Math.max(0, (value / target) * 100))
})

/** Klasa wypełnienia z tokens — bez celu pasek jest neutralny, nie „zły". */
const fillClass = computed(() => statusToken(props.status).fill)

const valueText = computed(() =>
  props.unit ? `${formatDecimal(props.value)} ${props.unit}` : formatDecimal(props.value),
)
const targetText = computed(() => {
  if (props.target === null) {
    return null
  }
  return props.unit ? `${formatDecimal(props.target)} ${props.unit}` : formatDecimal(props.target)
})

const ariaLabel = computed(() => {
  const parts = [`${props.label}: ${valueText.value}`]
  if (targetText.value !== null) {
    parts.push(`cel ${targetText.value}`)
  }
  const label = statusLabel(props.status)
  if (label) {
    parts.push(label)
  }
  return parts.join(', ')
})

const isVertical = computed(() => props.orientation === 'vertical')
</script>

<template>
  <svg
    v-if="isVertical"
    class="h-full w-full"
    viewBox="0 0 10 100"
    preserveAspectRatio="none"
    role="img"
    :aria-label="ariaLabel"
    :data-testid="testid"
  >
    <rect class="fill-muted" x="0" y="0" width="10" height="100" rx="3" />
    <rect
      :class="fillClass"
      x="0"
      :y="100 - fillPercent"
      width="10"
      :height="fillPercent"
      rx="3"
      :data-testid="`${testid}-fill`"
      :data-percent="fillPercent"
    />
  </svg>

  <svg
    v-else
    class="h-2 w-full"
    viewBox="0 0 100 8"
    preserveAspectRatio="none"
    role="img"
    :aria-label="ariaLabel"
    :data-testid="testid"
  >
    <rect class="fill-muted" x="0" y="0" width="100" height="8" rx="4" />
    <rect
      :class="fillClass"
      x="0"
      y="0"
      :width="fillPercent"
      height="8"
      rx="4"
      :data-testid="`${testid}-fill`"
      :data-percent="fillPercent"
    />
  </svg>
</template>
