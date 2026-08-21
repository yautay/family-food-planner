<script setup lang="ts">
/**
 * Plakietka resztki opakowania („Zostanie: 150 g").
 *
 * Resztka jest ZAWSZE eksponowana (02_DOMAIN §9.3): to ona odpowiada na pytanie
 * „ile mi zostanie, jak kupię całe opakowanie" i decyduje, czy warto wziąć
 * większe. Zero też pokazujemy — „Zostanie: 0 g" znaczy „opakowanie wychodzi
 * co do grama" i jest dobrą wiadomością, nie brakiem informacji.
 *
 * Kolory idą wyłącznie z tokens (06_UIUX §1), a status ma zawsze też TEKST —
 * sam kolor nie jest informacją dla osoby, która go nie rozróżnia.
 */
import { computed } from 'vue'

import { decimalsEqual } from '@/lib/decimal'
import { formatAmount, type AmountUnit } from '@/lib/format'
import { shopping as texts } from '@/lib/texts'

const props = defineProps<{
  /** Resztka jako string dziesiętny (ADR-008) albo `null`, gdy nie znamy opakowania. */
  leftover: string | null | undefined
  unit: AmountUnit
}>()

// Porównanie na TEKŚCIE, nie przez `Number`: ilości są stringami dziesiętnymi,
// a frontend ich nie zamienia na float (05_FRONTEND §7, ADR-008).
const isExact = computed(() => props.leftover != null && decimalsEqual(props.leftover, '0'))
</script>

<template>
  <span
    v-if="leftover !== null && leftover !== undefined"
    class="inline-flex items-center rounded-lg px-2 py-0.5 text-xs font-medium"
    :class="isExact ? 'bg-secondary/15 text-secondary' : 'bg-muted text-muted-foreground'"
    :data-testid="isExact ? 'leftover-badge-exact' : 'leftover-badge'"
  >
    {{ isExact ? texts.leftoverExact : `${texts.leftover} ${formatAmount(leftover, unit)}` }}
  </span>
</template>
