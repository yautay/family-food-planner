<script setup lang="ts">
/**
 * Import danych z pliku eksportu — trzy kroki (karta B14 §Frontend).
 *
 * 1. **Plik** — wybór archiwum ZIP.
 * 2. **Raport DRY-RUN** — co powstanie i co koliduje. Serwer NIC jeszcze nie
 *    zapisał, i panel mówi to wprost: bez tego „Importuj" brzmi jak operacja
 *    nieodwracalna i nikt jej nie kliknie.
 * 3. **Podsumowanie** — liczby utworzonych i reużytych wpisów.
 *
 * Decyzje kolizji trzymamy w Pinia? NIE — to stan JEDNEGO otwartego panelu,
 * więc mieszka w `ref` komponentu (05_FRONTEND §1: Pinia to stan UI dzielony
 * między widokami, a nie każdy formularz). Stan serwera (raport, wynik) też nie
 * idzie do TanStack Query: to wynik MUTACJI, nie zasób, który da się odpytać
 * ponownie — paczka po zastosowaniu przestaje istnieć.
 *
 * Panel osadzony w stronie, nie modal — ten sam wzorzec, co `ShareListDialog`.
 */
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import { ApiError } from '@/api/client'
import type { Collision, CollisionAction, DryRunReport, ImportSummary } from '@/api/transfer'
import { applyImport, uploadForDryRun } from '@/api/transfer'
import { Button } from '@/components/ui/button'
import { common, transfer as texts, transferSectionLabel } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  /** Wariant administracyjny zmienia wyłącznie nagłówek — endpoint jest jeden. */
  instance?: boolean
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'imported', summary: ImportSummary): void
}>()

const queryClient = useQueryClient()

const file = ref<File | null>(null)
const report = ref<DryRunReport | null>(null)
const summary = ref<ImportSummary | null>(null)
const errorMessage = ref<string | null>(null)
/** Decyzje per kolizja, kluczowane `encja:id z pliku` — pominięta = domyślna. */
const decisions = ref<Record<string, CollisionAction>>({})

const title = computed(() => (props.instance ? texts.importInstanceTitle : texts.importTitle))
const rows = computed(() =>
  Object.entries(report.value?.to_create ?? {}).map(([entity, count]) => ({
    entity,
    label: transferSectionLabel(entity),
    count,
  })),
)
const hasSomethingToCreate = computed(() => rows.value.length > 0)

function collisionKey(collision: Collision): string {
  return `${collision.entity}:${collision.source_id}`
}

function decisionFor(collision: Collision): CollisionAction {
  return decisions.value[collisionKey(collision)] ?? collision.default
}

function setDecision(collision: Collision, action: CollisionAction): void {
  decisions.value = { ...decisions.value, [collisionKey(collision)]: action }
}

function reset(): void {
  file.value = null
  report.value = null
  summary.value = null
  errorMessage.value = null
  decisions.value = {}
}

/** Zamknięcie panelu czyści WSZYSTKO — raport cudzego pliku nie może przeciekać. */
watch(
  () => props.open,
  (open) => {
    if (!open) {
      reset()
    }
  },
)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
  report.value = null
  summary.value = null
  errorMessage.value = null
}

function reportError(error: unknown): void {
  // Komunikat z backendu jest już po polsku (04_API §1) — nie tłumaczymy go
  // drugi raz i nie pokazujemy stacktrace'u.
  errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
}

const analyze = useMutation({
  mutationFn: () => uploadForDryRun(file.value as File),
  onSuccess: (result) => {
    errorMessage.value = null
    decisions.value = {}
    report.value = result
  },
  onError: reportError,
})

const confirm = useMutation({
  mutationFn: () => {
    const current = report.value
    if (!current) {
      throw new Error('Brak raportu importu.')
    }
    return applyImport(
      current.import_id,
      current.collisions.map((collision) => ({
        entity: collision.entity,
        source_id: collision.source_id,
        action: decisionFor(collision),
      })),
    )
  },
  onSuccess: async (result) => {
    errorMessage.value = null
    summary.value = result
    report.value = null
    // Import dotyka niemal każdej encji, więc odświeżamy CAŁY cache stanu
    // serwera — wyliczanie kluczy po jednym byłoby listą do zapomnienia.
    await queryClient.invalidateQueries()
    emit('imported', result)
  },
  onError: reportError,
})

const summaryCreated = computed(() =>
  Object.entries(summary.value?.created ?? {}).map(([entity, count]) => ({
    label: transferSectionLabel(entity),
    count,
  })),
)
const summaryReused = computed(() =>
  Object.entries(summary.value?.reused ?? {}).map(([entity, count]) => ({
    label: transferSectionLabel(entity),
    count,
  })),
)
</script>

<template>
  <section
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm"
    role="group"
    :aria-label="title"
    data-testid="transfer-import-dialog"
  >
    <header class="grid gap-1">
      <h3 class="text-sm font-medium">{{ title }}</h3>
      <p class="text-muted-foreground text-xs">{{ texts.reportSubtitle }}</p>
    </header>

    <p
      v-if="errorMessage"
      class="text-destructive text-sm"
      role="alert"
      data-testid="transfer-import-error"
    >
      {{ errorMessage }}
    </p>

    <!-- Krok 1: wybór pliku -->
    <div v-if="!report && !summary" class="grid gap-2" data-testid="transfer-step-file">
      <label class="text-sm font-medium" for="transfer-file">{{ texts.fileLabel }}</label>
      <input
        id="transfer-file"
        type="file"
        accept=".zip,application/zip"
        class="border-border min-h-11 rounded-lg border px-3 py-2 text-sm"
        data-testid="transfer-file"
        @change="onFileChange"
      />
      <p class="text-muted-foreground text-xs">{{ texts.fileHint }}</p>
      <div class="flex flex-wrap gap-2">
        <Button
          type="button"
          class="min-h-11"
          :disabled="!file || analyze.isPending.value"
          data-testid="transfer-analyze"
          @click="analyze.mutate()"
        >
          {{ analyze.isPending.value ? texts.analyzing : texts.analyze }}
        </Button>
        <Button
          type="button"
          variant="ghost"
          class="min-h-11"
          data-testid="transfer-cancel"
          @click="emit('close')"
        >
          {{ common.cancel }}
        </Button>
      </div>
    </div>

    <!-- Krok 2: raport dry-run -->
    <div v-else-if="report" class="grid gap-3" data-testid="transfer-step-report">
      <p class="text-muted-foreground text-xs" data-testid="transfer-report-meta">
        {{ texts.reportFrom(report.app_version || '—', report.exported_at.slice(0, 10)) }}
      </p>

      <h4 class="text-sm font-medium">{{ texts.reportTitle }}</h4>
      <p
        v-if="!hasSomethingToCreate"
        class="text-muted-foreground text-sm"
        data-testid="transfer-report-empty"
      >
        {{ texts.reportEmpty }}
      </p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm" data-testid="transfer-report-table">
          <thead>
            <tr class="text-muted-foreground text-left">
              <th class="py-1 font-medium">{{ texts.columnEntity }}</th>
              <th class="py-1 text-right font-medium">{{ texts.columnNew }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.entity"
              class="border-border border-t"
              :data-testid="`transfer-row-${row.entity}`"
            >
              <td class="py-1">{{ row.label }}</td>
              <td class="py-1 text-right tabular-nums">{{ row.count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-muted-foreground text-xs">{{ texts.photos(report.photos) }}</p>

      <template v-if="report.collisions.length">
        <h4 class="text-sm font-medium">{{ texts.collisionsTitle }}</h4>
        <p class="text-muted-foreground text-xs">{{ texts.collisionsSubtitle }}</p>
        <ul class="grid gap-2" data-testid="transfer-collisions">
          <li
            v-for="collision in report.collisions"
            :key="`${collision.entity}:${collision.source_id}`"
            class="border-border grid gap-2 rounded-lg border p-2 md:grid-cols-[1fr_auto] md:items-center"
            :data-testid="`transfer-collision-${collision.entity}-${collision.source_id}`"
          >
            <div class="min-w-0">
              <p class="truncate text-sm font-medium">{{ collision.name }}</p>
              <p class="text-muted-foreground truncate text-xs">
                {{ transferSectionLabel(collision.entity) }}
              </p>
            </div>
            <div class="flex gap-2">
              <Button
                type="button"
                :variant="decisionFor(collision) === 'use_existing' ? 'default' : 'outline'"
                class="min-h-11"
                :aria-pressed="decisionFor(collision) === 'use_existing'"
                :aria-label="texts.collisionAria(collision.name)"
                :data-testid="`transfer-use-existing-${collision.entity}-${collision.source_id}`"
                @click="setDecision(collision, 'use_existing')"
              >
                {{ texts.useExisting }}
              </Button>
              <Button
                type="button"
                :variant="decisionFor(collision) === 'create_copy' ? 'default' : 'outline'"
                class="min-h-11"
                :aria-pressed="decisionFor(collision) === 'create_copy'"
                :data-testid="`transfer-create-copy-${collision.entity}-${collision.source_id}`"
                @click="setDecision(collision, 'create_copy')"
              >
                {{ texts.createCopy }}
              </Button>
            </div>
          </li>
        </ul>
      </template>

      <template v-if="report.warnings.length">
        <h4 class="text-sm font-medium">{{ texts.warningsTitle }}</h4>
        <ul class="text-muted-foreground grid gap-1 text-xs" data-testid="transfer-warnings">
          <li v-for="(warning, index) in report.warnings" :key="index">{{ warning }}</li>
        </ul>
      </template>

      <div class="flex flex-wrap gap-2">
        <Button
          type="button"
          class="min-h-11"
          :disabled="confirm.isPending.value"
          data-testid="transfer-confirm"
          @click="confirm.mutate()"
        >
          {{ confirm.isPending.value ? texts.applying : texts.confirm }}
        </Button>
        <Button
          type="button"
          variant="ghost"
          class="min-h-11"
          data-testid="transfer-back"
          @click="reset()"
        >
          {{ texts.back }}
        </Button>
      </div>
    </div>

    <!-- Krok 3: podsumowanie -->
    <div v-else class="grid gap-2" data-testid="transfer-step-summary">
      <h4 class="text-sm font-medium">{{ texts.summaryTitle }}</h4>
      <p
        v-if="!summaryCreated.length"
        class="text-muted-foreground text-sm"
        data-testid="transfer-summary-empty"
      >
        {{ texts.summaryNothing }}
      </p>
      <template v-else>
        <p class="text-sm font-medium">{{ texts.summaryCreated }}</p>
        <ul class="text-muted-foreground grid gap-1 text-sm" data-testid="transfer-summary-created">
          <li v-for="row in summaryCreated" :key="row.label" class="tabular-nums">
            {{ row.label }}: {{ row.count }}
          </li>
        </ul>
      </template>
      <template v-if="summaryReused.length">
        <p class="text-sm font-medium">{{ texts.summaryReused }}</p>
        <ul class="text-muted-foreground grid gap-1 text-sm" data-testid="transfer-summary-reused">
          <li v-for="row in summaryReused" :key="row.label" class="tabular-nums">
            {{ row.label }}: {{ row.count }}
          </li>
        </ul>
      </template>
      <p class="text-muted-foreground text-xs">
        {{ texts.summaryPhotos(summary?.photos_imported ?? 0) }}
      </p>
      <ul
        v-if="summary?.warnings.length"
        class="text-muted-foreground grid gap-1 text-xs"
        data-testid="transfer-summary-warnings"
      >
        <li v-for="(warning, index) in summary.warnings" :key="index">{{ warning }}</li>
      </ul>
      <div>
        <Button type="button" class="min-h-11" data-testid="transfer-close" @click="emit('close')">
          {{ texts.close }}
        </Button>
      </div>
    </div>
  </section>
</template>
