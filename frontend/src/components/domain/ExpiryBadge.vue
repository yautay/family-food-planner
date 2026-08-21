<script setup lang="ts">
/**
 * Plakietka daty ważności pozycji spiżarni (widok 6, 06_UIUX §4 pkt 6).
 *
 * Progi i ich uzasadnienie mieszkają w `src/lib/expiry.ts` — ten komponent
 * wyłącznie je pokazuje. Status ZAWSZE kolor + tekst (06_UIUX §1): sam kolor
 * nie jest informacją dla osoby, która go nie rozróżnia.
 */
import { computed } from 'vue'

import { formatDate, isoDate } from '@/lib/dates'
import type { ExpiryStatus } from '@/lib/expiry'
import { expiryStatus } from '@/lib/expiry'
import { pantry as texts } from '@/lib/texts'

const props = withDefaults(
  defineProps<{
    /** `YYYY-MM-DD` albo `null` — brak daty jest normalny (mąka, ryż). */
    expiryDate: string | null
    /** „Dziś" wstrzykiwane w testach; produkcyjnie data lokalna użytkownika. */
    today?: string
  }>(),
  { today: undefined },
)

const reference = computed(() => props.today ?? isoDate(new Date()))
const status = computed(() => expiryStatus(props.expiryDate, reference.value))

const label = computed(() => {
  if (props.expiryDate === null) {
    return texts.noExpiry
  }
  const date = formatDate(props.expiryDate)
  if (status.value === 'expired') {
    return `${texts.expired} · ${date}`
  }
  if (status.value === 'soon') {
    return `${texts.expiresSoon} · ${date}`
  }
  return `${texts.expiresOn} ${date}`
})

const styles: Record<ExpiryStatus, string> = {
  none: 'bg-muted text-muted-foreground',
  ok: 'bg-muted text-muted-foreground',
  soon: 'bg-warning/15 text-warning',
  expired: 'bg-destructive/15 text-destructive',
}
</script>

<template>
  <span
    class="inline-flex items-center rounded-lg px-2 py-0.5 text-xs font-medium"
    :class="styles[status]"
    :data-testid="`expiry-badge-${status}`"
  >
    {{ label }}
  </span>
</template>
