<script setup lang="ts">
/**
 * Wiersz pozycji listy zakupowej — widok krytyczny mobilny (06_UIUX §5).
 *
 * Trzy decyzje, z których wynika cały ten komponent:
 *
 * 1. **Checkbox ma ~48 px** i jest głównym celem dotykowym wiersza. Cały
 *    wiersz jest `<label>`, więc obszar kliknięcia to nie tylko kwadracik —
 *    jednoręczna obsługa w sklepie nie może wymagać precyzji.
 * 2. **Wiersz nie wie, do kogo należy lista.** Dostaje ilości i emituje
 *    `toggle` — używa go zarówno strona zalogowana, jak i publiczna
 *    `/l/:token`, gdzie nie ma żadnych danych rodziny. Dzięki temu obie
 *    wyglądają identycznie, a różnią się wyłącznie tym, kto wysyła PATCH.
 * 3. **Wydruk jest wariantem TEGO wiersza**, nie osobnym szablonem: w druku
 *    checkbox zamienia się w znak `☐` (06_UIUX §6), bo pole formularza na
 *    papierze bywa niewidoczne, a kartkę odhacza się ołówkiem.
 *
 * Kolory wyłącznie z tokens (06_UIUX §1); status „mam w domu" ma też TEKST,
 * nie tylko wyszarzenie.
 */
import { computed } from 'vue'

import LeftoverBadge from '@/components/domain/LeftoverBadge.vue'
import { formatAmount, type AmountUnit } from '@/lib/format'
import { shoppingList as texts } from '@/lib/texts'

const props = defineProps<{
  itemId: number
  label: string
  amount: string
  unit: AmountUnit
  checked: boolean
  alreadyHave: boolean
  leftover?: string | null
  packagesCount?: number | null
  packageSize?: string | null
  /** Blokada podczas mutacji w locie (nie blokuje optimistic update). */
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'toggle', payload: { itemId: number; checked: boolean }): void
}>()

/** „2 x 1 kg" — pokazujemy tylko wtedy, gdy znamy opakowanie. */
const packagesLine = computed(() => {
  if (props.packagesCount == null || props.packageSize == null) {
    return null
  }
  return texts.packagesLine(props.packagesCount, formatAmount(props.packageSize, props.unit))
})
</script>

<template>
  <li
    class="border-border bg-card rounded-xl border print:rounded-none print:border-0 print:border-b print:border-black print:bg-transparent"
    :class="alreadyHave ? 'opacity-60' : ''"
    :data-testid="`shopping-item-${itemId}`"
  >
    <label class="flex min-h-14 cursor-pointer items-center gap-3 p-2 print:p-1">
      <!-- Checkbox interaktywny: ~48 px celu dotykowego (06_UIUX §5). -->
      <input
        type="checkbox"
        class="size-12 shrink-0 accent-primary print:hidden"
        :checked="checked"
        :disabled="disabled"
        :aria-label="texts.toggleAria(label)"
        :data-testid="`shopping-check-${itemId}`"
        @change="emit('toggle', { itemId, checked: !checked })"
      />
      <!-- Wariant do druku: kwadrat do odhaczenia ołówkiem (06_UIUX §6). -->
      <span class="hidden shrink-0 text-lg print:inline" aria-hidden="true">☐</span>

      <span class="grid min-w-0 flex-1 gap-0.5">
        <span
          class="truncate font-medium print:whitespace-normal"
          :class="checked ? 'line-through print:no-underline' : ''"
          :data-testid="`shopping-label-${itemId}`"
        >
          {{ label }}
        </span>
        <span
          class="text-muted-foreground flex flex-wrap items-center gap-2 text-xs print:text-black"
        >
          <span :data-testid="`shopping-amount-${itemId}`">{{ formatAmount(amount, unit) }}</span>
          <span v-if="packagesLine" :data-testid="`shopping-packages-${itemId}`">
            {{ packagesLine }}
          </span>
          <span v-if="alreadyHave" class="font-medium" :data-testid="`shopping-have-${itemId}`">
            {{ texts.alreadyHave }}
          </span>
        </span>
      </span>

      <!-- Resztka jest ZAWSZE eksponowana, gdy znamy opakowanie (02_DOMAIN §9.3). -->
      <LeftoverBadge
        v-if="packagesCount != null"
        class="shrink-0 print:hidden"
        :leftover="leftover"
        :unit="unit"
      />
    </label>
  </li>
</template>
