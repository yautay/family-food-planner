<script setup lang="ts">
/**
 * Wspólna oprawa paneli akcji widoku tygodnia (06_UIUX §2).
 *
 * To panel osadzony w stronie, nie modal: na telefonie modal zabiera cały ekran
 * i odcina kontekst („na który dzień właściwie kopiuję?"), a widok tygodnia jest
 * z definicji o kontekście. Ten sam wzorzec, co `ServingsSplitDrawer` z B06.
 *
 * Sam nie trzyma stanu formularza — dostarcza nagłówek, obszar błędu, stopkę
 * z akcją główną i „Anuluj". Dzięki temu pięć dialogów szablonów/cykli/bloku
 * ma identyczną chromę i identyczne cele dotykowe (≥44 px, 06_UIUX §5).
 */
import { Button } from '@/components/ui/button'
import { common } from '@/lib/texts'

// Propsy używa wyłącznie szablon, więc nie wiążemy ich do zmiennej.
withDefaults(
  defineProps<{
    open: boolean
    title: string
    subtitle?: string
    /** Etykieta akcji głównej. */
    submitLabel: string
    /** Blokada akcji głównej (niepoprawny formularz). */
    submitDisabled?: boolean
    pending?: boolean
    /** Komunikat błędu z serwera (ApiError.message) — `null` gdy brak. */
    error?: string | null
    /** Ostrzeżenia miękkie z odpowiedzi (np. archiwalny przepis w szablonie). */
    warnings?: string[]
    testid: string
  }>(),
  {
    subtitle: undefined,
    submitDisabled: false,
    pending: false,
    error: null,
    warnings: () => [],
  },
)

const emit = defineEmits<{
  (event: 'submit'): void
  (event: 'close'): void
}>()
</script>

<template>
  <section
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm"
    role="group"
    :aria-label="title"
    :data-testid="testid"
  >
    <header class="grid gap-1">
      <h3 class="text-sm font-medium">{{ title }}</h3>
      <p v-if="subtitle" class="text-muted-foreground text-xs">{{ subtitle }}</p>
    </header>

    <slot />

    <p v-if="error" class="text-destructive text-sm" role="alert" :data-testid="`${testid}-error`">
      {{ error }}
    </p>

    <ul
      v-if="warnings.length > 0"
      class="text-warning grid gap-1 text-sm"
      :data-testid="`${testid}-warnings`"
    >
      <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
    </ul>

    <footer class="flex flex-wrap gap-2">
      <Button
        type="button"
        class="min-h-11"
        :disabled="submitDisabled || pending"
        :data-testid="`${testid}-submit`"
        @click="emit('submit')"
      >
        {{ pending ? common.loading : submitLabel }}
      </Button>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :data-testid="`${testid}-cancel`"
        @click="emit('close')"
      >
        {{ common.cancel }}
      </Button>
      <slot name="footer-extra" />
    </footer>
  </section>
</template>
