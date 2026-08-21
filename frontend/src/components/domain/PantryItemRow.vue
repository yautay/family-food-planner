<script setup lang="ts">
/**
 * Wiersz pozycji spiżarni (widok 6 w trybie „lista").
 *
 * Ten sam kontrakt co `PantryItemCard` (props + emits) — przełącznik widoku
 * podmienia komponent, nie logikę strony. Na telefonie wiersz układa się
 * pionowo, od `sm:` wchodzi układ kolumnowy (mobile-first, 06_UIUX §5).
 */
import { computed } from 'vue'

import type { PantryItem } from '@/api/pantry'
import ExpiryBadge from '@/components/domain/ExpiryBadge.vue'
import { Button } from '@/components/ui/button'
import { decimalsEqual } from '@/lib/decimal'
import type { AmountUnit } from '@/lib/format'
import { formatAmount } from '@/lib/format'
import { common, pantry as texts } from '@/lib/texts'

const props = defineProps<{
  item: PantryItem
  today?: string
}>()

defineEmits<{
  (event: 'edit', item: PantryItem): void
  (event: 'zero', item: PantryItem): void
  (event: 'remove', item: PantryItem): void
}>()

/** Zero: pozycja jest, ale produktu w domu nie ma. */
const isEmpty = computed(() => decimalsEqual(props.item.amount, '0'))
</script>

<template>
  <li
    class="border-border bg-card grid gap-2 rounded-xl border p-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-center"
    :data-testid="`pantry-row-${item.id}`"
  >
    <div class="min-w-0">
      <p class="truncate font-medium" :data-testid="`pantry-name-${item.id}`">
        {{ item.product_name ?? '—' }}
      </p>
      <p v-if="item.location || item.note" class="text-muted-foreground truncate text-sm">
        {{ [item.location, item.note].filter(Boolean).join(' · ') }}
      </p>
    </div>

    <p class="text-sm tabular-nums" :data-testid="`pantry-amount-${item.id}`">
      <span v-if="isEmpty" class="text-muted-foreground">{{ texts.zeroed }}</span>
      <span v-else>{{ formatAmount(item.amount, item.amount_unit as AmountUnit) }}</span>
    </p>

    <!-- Bez `data-testid` z zewnątrz: fallthrough nadpisałby testid komponentu
         (`expiry-badge-{status}`), a to on niesie informację o wyróżnieniu. -->
    <ExpiryBadge class="justify-self-start" :expiry-date="item.expiry_date" :today="today" />

    <div class="flex flex-wrap gap-2 sm:justify-end">
      <Button
        variant="outline"
        class="min-h-11"
        :data-testid="`pantry-edit-${item.id}`"
        @click="$emit('edit', item)"
      >
        {{ common.edit }}
      </Button>
      <Button
        variant="outline"
        class="min-h-11"
        :disabled="isEmpty"
        :data-testid="`pantry-zero-${item.id}`"
        @click="$emit('zero', item)"
      >
        {{ texts.zeroAmount }}
      </Button>
      <Button
        variant="outline"
        class="min-h-11"
        :data-testid="`pantry-remove-${item.id}`"
        @click="$emit('remove', item)"
      >
        {{ common.remove }}
      </Button>
    </div>
  </li>
</template>
