<script setup lang="ts">
/**
 * „Pokaż więcej" — JEDYNY sposób doładowania kolejnej strony listy (BATCH_19).
 *
 * Para do `usePaginatedList` z `src/api/pagination.ts`. Komponent nic nie
 * pobiera: dostaje liczby i oddaje zdarzenie, więc ta sama kontrolka stoi pod
 * katalogiem, spiżarnią i ekranami ADMIN-a.
 *
 * Trzy rzeczy wynikają wprost z 06_UIUX:
 *
 * - cel dotykowy ≥44 px (§5), na telefonie przycisk jest pełnej szerokości;
 * - doładowanie to spinner NA PRZYCISKU, nie skeleton listy (§3.4) — lista już
 *   coś pokazuje i nie ma prawa zamigotać;
 * - w etykiecie stoi, ile pozycji ZOSTAŁO, żeby kliknięcie było decyzją
 *   („jeszcze 135"), a nie skokiem w ciemno.
 *
 * `failed` to nieudane DOŁADOWANIE: lista zostaje na ekranie, a komunikat siada
 * przy przycisku, bo to on jest ponowieniem. Alternatywa — pokazać błąd zamiast
 * listy — kasowała z widoku wiersze, które są w cache'u i są poprawne.
 */
import { computed } from 'vue'

import { Button } from '@/components/ui/button'
import { pagination as texts } from '@/lib/texts'

const props = defineProps<{
  /** Ile pozycji jest już na ekranie. */
  loaded: number
  /** Ile jest wszystkich po stronie serwera. */
  total: number
  /** Czy serwer ma jeszcze co dać — źródłem prawdy jest `usePaginatedList`. */
  hasMore: boolean
  loading: boolean
  /** Padło doładowanie kolejnej strony — przycisk jest ponowieniem. */
  failed?: boolean
  testid: string
}>()

const emit = defineEmits<{ (event: 'more'): void }>()

const remaining = computed(() => Math.max(props.total - props.loaded, 0))
</script>

<template>
  <div v-if="hasMore" class="grid justify-items-center gap-2">
    <p
      v-if="failed && !loading"
      class="text-destructive text-sm"
      role="alert"
      :data-testid="`${testid}-error`"
    >
      {{ texts.loadMoreFailed }}
    </p>
    <Button
      type="button"
      variant="outline"
      class="min-h-11 w-full sm:w-auto"
      :disabled="loading"
      :aria-label="`${texts.showMore} — ${texts.remaining(remaining)}`"
      :data-testid="testid"
      @click="emit('more')"
    >
      {{ loading ? texts.loadingMore : `${texts.showMore} (${remaining})` }}
    </Button>
  </div>
</template>
