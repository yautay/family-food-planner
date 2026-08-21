<script setup lang="ts">
/**
 * Kafelek pozycji spiżarni (widok 6 w trybie „kafelki").
 *
 * Komponent jest bezstanowy: pokazuje pozycję i zgłasza intencję (edytuj /
 * wyzeruj / usuń). Ilość formatuje WYŁĄCZNIE `formatAmount` (05_FRONTEND §7),
 * więc 1500 g pokaże się jako „1,5 kg" bez liczenia czegokolwiek na floatach.
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
  /** „Dziś" podawane z góry — jedno źródło dla całej listy (i dla testów). */
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
    class="border-border bg-card grid gap-2 rounded-xl border p-4"
    :data-testid="`pantry-card-${item.id}`"
  >
    <div class="min-w-0">
      <p class="truncate font-medium" :data-testid="`pantry-name-${item.id}`">
        {{ item.product_name ?? '—' }}
      </p>
      <p v-if="item.category_name" class="text-muted-foreground truncate text-sm">
        {{ item.category_name }}
      </p>
    </div>

    <p class="text-sm tabular-nums" :data-testid="`pantry-amount-${item.id}`">
      <span v-if="isEmpty" class="text-muted-foreground">{{ texts.zeroed }}</span>
      <span v-else>{{ formatAmount(item.amount, item.amount_unit as AmountUnit) }}</span>
    </p>

    <!-- Bez `data-testid` z zewnątrz: fallthrough nadpisałby testid komponentu
         (`expiry-badge-{status}`), a to on niesie informację o wyróżnieniu. -->
    <ExpiryBadge class="justify-self-start" :expiry-date="item.expiry_date" :today="today" />

    <p v-if="item.location" class="text-muted-foreground text-sm">{{ item.location }}</p>
    <p v-if="item.note" class="text-muted-foreground text-sm italic">{{ item.note }}</p>

    <div class="flex flex-wrap gap-2">
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
