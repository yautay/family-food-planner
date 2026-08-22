<script setup lang="ts">
/**
 * Pasek stanu offline listy zakupowej (ADR-009, AC 5).
 *
 * Trzy decyzje:
 *
 * 1. **Nie pokazuje się, gdy nie ma o czym mówić.** Online i pusta kolejka =
 *    zero pikseli. Stały pasek „jesteś online" byłby szumem na widoku, który
 *    ma być czytelny jedną ręką w sklepie (06_UIUX §5).
 * 2. **Mówi, co się stanie ze zmianami, a nie tylko „brak sieci".** Osoba
 *    z koszykiem chce wiedzieć, czy odhaczenia przepadną — samo „offline" tego
 *    nie odpowiada.
 * 3. **Liczba oczekujących zmian jest TEKSTEM**, nie samą kropką ani kolorem
 *    (06_UIUX §1: status zawsze kolor + tekst).
 *
 * Nie znika z wydruku przez `print:hidden`, bo cały pasek jest stanem aplikacji,
 * a nie treścią listy (06_UIUX §6).
 */
import { computed } from 'vue'

import { offline as texts } from '@/lib/texts'

const props = defineProps<{
  offline: boolean
  pending: number
  /** Trwa właśnie wysyłka kolejki — komunikat zmienia się na „zapisuję". */
  syncing?: boolean
}>()

const visible = computed(() => props.offline || props.pending > 0 || props.syncing === true)

const message = computed(() => {
  if (props.offline) {
    return texts.banner
  }
  return props.pending > 0 || props.syncing === true ? texts.syncing : texts.synced
})
</script>

<template>
  <div
    v-if="visible"
    class="border-border bg-muted text-foreground flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-sm print:hidden"
    role="status"
    aria-live="polite"
    data-testid="offline-banner"
  >
    <span class="font-medium" data-testid="offline-banner-message">{{ message }}</span>
    <span v-if="pending > 0" class="text-muted-foreground" data-testid="offline-pending">
      {{ texts.pending(pending) }}
    </span>
  </div>
</template>
