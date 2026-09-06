<script setup lang="ts">
/**
 * „Powiel blok" — model 2+2+2 z listu dietetyczki.
 *
 * Dietę stosuje się 2 dni pod rząd, więc blok kopiuje kolejne dni PARAMI:
 * d1,d1,d2,d2,d3,d3. Preset „2+2+2" ustawia to jednym kliknięciem, bo to
 * najczęstszy przypadek użycia całej funkcji (06_UIUX §2 — liczy się liczba
 * kliknięć od intencji do efektu).
 *
 * Podgląd dat liczy `blockCopySequence` — ta sama funkcja, którą testuje vitest
 * i której odpowiednik (`block_copy_sequence`) liczy to na backendzie. Gdyby
 * podgląd miał własną arytmetykę, mógłby obiecać coś innego niż zapis.
 */
import { computed, ref, watch } from 'vue'

import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { weekDayLabel } from '@/lib/dates'
import {
  BLOCK_PRESET_2_2_2,
  blockCopySchema,
  blockCopySequence,
  defaultBlockForm,
} from '@/lib/schemas/template'
import { week as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  /** Dzień, na którym stał użytkownik — sensowny domyślny start bloku. */
  sourceFrom: string
  pending?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  (
    event: 'apply',
    payload: { sourceFrom: string; sourceDays: number; repeatEach: number; targetStart: string },
  ): void
  (event: 'close'): void
}>()

const form = ref(defaultBlockForm(props.sourceFrom))

watch(
  () => [props.open, props.sourceFrom] as const,
  ([open]) => {
    if (open) {
      form.value = defaultBlockForm(props.sourceFrom)
    }
  },
  { immediate: true },
)

const parsed = computed(() => blockCopySchema.safeParse(form.value))

const pairs = computed(() => {
  if (!parsed.value.success) {
    return []
  }
  const { sourceFrom, sourceDays, repeatEach, targetStart } = parsed.value.data
  return blockCopySequence(sourceFrom, sourceDays, repeatEach, targetStart)
})

const validationMessage = computed(() =>
  parsed.value.success ? null : (parsed.value.error.issues[0]?.message ?? null),
)

function applyPreset(): void {
  form.value = { ...form.value, ...BLOCK_PRESET_2_2_2 }
}

function submit(): void {
  if (parsed.value.success) {
    emit('apply', parsed.value.data)
  }
}
</script>

<template>
  <PlanningDialog
    :open="open"
    :title="texts.blockTitle"
    :subtitle="texts.blockSubtitle"
    :submit-label="texts.blockApply"
    :submit-disabled="!parsed.success"
    :pending="pending"
    :error="error ?? validationMessage"
    testid="block-copy-dialog"
    @submit="submit()"
    @close="emit('close')"
  >
    <div class="grid gap-3 sm:grid-cols-2">
      <label class="grid gap-1 text-sm">
        {{ texts.blockFrom }}
        <Input
          v-model="form.sourceFrom"
          type="date"
          class="min-h-11"
          data-testid="block-source-from"
        />
      </label>
      <label class="grid gap-1 text-sm">
        {{ texts.blockTargetStart }}
        <Input
          v-model="form.targetStart"
          type="date"
          class="min-h-11"
          data-testid="block-target-start"
        />
      </label>
      <label class="grid gap-1 text-sm">
        {{ texts.blockDays }}
        <Input
          v-model="form.sourceDays"
          type="number"
          min="1"
          max="31"
          inputmode="numeric"
          class="min-h-11 tabular-nums"
          data-testid="block-source-days"
        />
      </label>
      <label class="grid gap-1 text-sm">
        {{ texts.blockRepeat }}
        <Input
          v-model="form.repeatEach"
          type="number"
          min="1"
          max="7"
          inputmode="numeric"
          class="min-h-11 tabular-nums"
          data-testid="block-repeat-each"
        />
      </label>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        class="min-h-11"
        data-testid="block-preset-222"
        @click="applyPreset()"
      >
        {{ texts.blockPreset }}
      </Button>
      <span class="text-muted-foreground text-xs">{{ texts.blockPresetHint }}</span>
    </div>

    <!-- Podgląd: użytkownik widzi dokładnie te daty, które powstaną. -->
    <div v-if="pairs.length > 0" class="grid gap-1">
      <p class="text-muted-foreground text-xs">
        {{ texts.blockPreview }}:
        <strong data-testid="block-preview-count">{{ pairs.length }}</strong>
      </p>
      <ol class="grid gap-1 text-xs tabular-nums" data-testid="block-preview">
        <li v-for="(pair, index) in pairs" :key="`${pair.target}-${index}`" class="flex gap-2">
          <span class="text-muted-foreground">{{ weekDayLabel(pair.target) }}</span>
          <span>{{ pair.target }}</span>
          <span class="text-muted-foreground" aria-hidden="true">&larr;</span>
          <span class="text-muted-foreground">{{ pair.source }}</span>
        </li>
      </ol>
    </div>
  </PlanningDialog>
</template>
