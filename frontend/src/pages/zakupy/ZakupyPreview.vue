<script setup lang="ts">
/**
 * Podgląd generacji zakupów (karta B10 §Frontend).
 *
 * Cztery rzeczy, które ten ekran musi pokazać, żeby użytkownik mógł zaufać
 * liczbom:
 *
 * 1. **sekcje per tura, w turze pozycje per kategoria** — tak wygląda przejście
 *    po sklepie (02_DOMAIN §9.4),
 * 2. **resztki** przy każdej pozycji z opakowaniem (`LeftoverBadge`, §9.3),
 * 3. **co odjęliśmy ze spiżarni** — tylko gdy użytkownik o to poprosił (§8),
 * 4. **niejasności** z jasnym podziałem na blokery i ostrzeżenia; bloker
 *    wyłącza „Utwórz listy" i mówi dlaczego (06_UIUX §3.3).
 *
 * Decyzje (toggle „mam już w domu", wybór opakowania, odłożenie niejasności)
 * idą przez `POST /resolve`, który przelicza podgląd TYM SAMYM silnikiem — nie
 * ma tu żadnej lokalnej arytmetyki (ADR-008). Pozycja bez produktu sklepowego
 * dostaje inline create (`RetailProductCreateDrawer` z B09, 06_UIUX §3.1).
 */
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, ref, watch } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RetailProduct } from '@/api/retail'
import type { Generation, PreviewLine, PreviewRound } from '@/api/shopping'
import { discardGeneration, resolveGeneration } from '@/api/shopping'
import ActionArea from '@/components/domain/ActionArea.vue'
import FeedbackMessage from '@/components/domain/FeedbackMessage.vue'
import LeftoverBadge from '@/components/domain/LeftoverBadge.vue'
import RetailProductCreateDrawer from '@/components/domain/RetailProductCreateDrawer.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/lib/dates'
import { decimalsEqual } from '@/lib/decimal'
import { formatAmount } from '@/lib/format'
import { common, shopping as texts } from '@/lib/texts'

const props = defineProps<{
  generation: Generation
  finalizePending: boolean
  generatePending: boolean
  finalizeError: string | null
}>()
const emit = defineEmits<{
  finalize: []
  discarded: []
}>()

const queryClient = useQueryClient()
const actionError = ref<string | null>(null)
const retailDrawerFor = ref<PreviewLine | null>(null)
const previewHeading = ref<HTMLElement | null>(null)
watch(
  () => props.generation.id,
  async () => {
    await nextTick()
    previewHeading.value?.focus()
  },
  { immediate: true },
)

/** Aktualny stan decyzji — wysyłamy PEŁNY zbiór, bo różnica nie wyrazi odznaczenia. */
const alreadyHave = computed(() =>
  allLines.value.filter((line) => line.already_have).map((line) => line.product_id),
)
const allLines = computed(() => props.generation.rounds.flatMap((round) => round.items))
const dismissed = computed(() =>
  props.generation.issues.filter((issue) => issue.dismissed).map((issue) => issue.key),
)
/**
 * JAWNE wybory wariantów — z odpowiedzi API, nie z pozycji podglądu.
 *
 * Pozycja niesie `retail_product_id` także wtedy, gdy wariant dobrał AUTOMAT
 * (najmniejsza resztka). Gdyby ta lista powstawała z pozycji, pierwsza dowolna
 * decyzja w podglądzie odesłałaby wszystkie auto-wybory jako „wolę ten" i od tej
 * chwili dodanie mniejszego opakowania w katalogu nic by już nie zmieniło.
 */
const retailChoices = computed(() => props.generation.retail_choices)

const blockers = computed(() =>
  props.generation.issues.filter((issue) => issue.severity === 'blocker' && !issue.dismissed),
)
const isEmpty = computed(() => allLines.value.length === 0)
const busy = computed(
  () =>
    resolve.isPending.value ||
    discard.isPending.value ||
    props.finalizePending ||
    props.generatePending,
)

/** Odjęcia ze spiżarni: tylko pozycje, przy których faktycznie coś odjęto. */
const pantryLines = computed(() =>
  allLines.value.filter(
    (line) => line.from_pantry_amount !== null && !decimalsEqual(line.from_pantry_amount, '0'),
  ),
)

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: queryKeys.shopping.generation(props.generation.id),
  })
}

const resolve = useMutation({
  mutationFn: (payload: Parameters<typeof resolveGeneration>[1]) =>
    resolveGeneration(props.generation.id, payload),
  onSuccess: (generation) => {
    actionError.value = null
    // Odpowiedź `/resolve` JEST nowym stanem serwera (ten sam silnik, ten sam
    // `params`), więc wkładamy ją do cache i NIE unieważniamy zapytania:
    // ponowny GET zwróciłby to samo, a podgląd zamigałby po drodze
    // (06_UIUX §3.4 — żadnych migających skeletonów).
    queryClient.setQueryData(queryKeys.shopping.generation(generation.id), generation)
  },
  onError: reportError,
})

function toggleAlreadyHave(line: PreviewLine): void {
  const next = line.already_have
    ? alreadyHave.value.filter((id) => id !== line.product_id)
    : [...alreadyHave.value, line.product_id]
  resolve.mutate({ already_have: next })
}

function chooseRetail(line: PreviewLine, value: string): void {
  const retailId = Number.parseInt(value, 10)
  const others = retailChoices.value.filter((choice) => choice.product_id !== line.product_id)
  resolve.mutate({
    retail_choices: [...others, { product_id: line.product_id, retail_product_id: retailId }],
  })
}

function dismissIssue(key: string): void {
  resolve.mutate({ dismissed_issues: [...dismissed.value, key] })
}

/** Po inline create wariantu od razu przypisujemy go pozycji (`/resolve`). */
function onRetailCreated(line: PreviewLine, retail: RetailProduct): void {
  retailDrawerFor.value = null
  const others = retailChoices.value.filter((choice) => choice.product_id !== line.product_id)
  resolve.mutate({
    retail_choices: [...others, { product_id: line.product_id, retail_product_id: retail.id }],
  })
}

const discard = useMutation({
  mutationFn: () => discardGeneration(props.generation.id),
  onSuccess: async () => {
    actionError.value = null
    await refresh()
    emit('discarded')
  },
  onError: reportError,
})

function confirmDiscard(): void {
  if (window.confirm(texts.confirmDiscard)) {
    discard.mutate()
  }
}

/** Pozycje tury pogrupowane po kategorii — kolejność z backendu bez zmian. */
function groupByCategory(round: PreviewRound): { name: string; items: PreviewLine[] }[] {
  const groups: { name: string; items: PreviewLine[] }[] = []
  for (const line of round.items) {
    const name = line.category_name ?? '—'
    const last = groups.at(-1)
    if (last && last.name === name) {
      last.items.push(line)
    } else {
      groups.push({ name, items: [line] })
    }
  }
  return groups
}

function rangeLabel(round: PreviewRound): string {
  if (round.date_from === null || round.date_to === null) {
    return texts.roundEmpty
  }
  return `${texts.covers}: ${formatDate(round.date_from)} – ${formatDate(round.date_to)}`
}
</script>

<template>
  <section class="grid min-w-0 gap-4" data-testid="zakupy-preview">
    <header class="flex flex-wrap items-center justify-between gap-2">
      <div class="grid gap-0.5">
        <h2
          ref="previewHeading"
          tabindex="-1"
          class="text-xl font-semibold"
          data-testid="preview-title"
        >
          {{ texts.previewTitle }}
        </h2>
        <p class="text-muted-foreground text-sm">
          {{ formatDate(generation.date_from) }} – {{ formatDate(generation.date_to) }}
        </p>
      </div>
      <ActionArea label="Zapisanie podglądu">
        <Button
          class="min-h-11"
          :disabled="blockers.length > 0 || isEmpty || busy"
          :title="blockers.length > 0 ? texts.finalizeBlocked : undefined"
          data-testid="preview-finalize"
          :aria-busy="finalizePending"
          @click="emit('finalize')"
        >
          {{ finalizePending ? texts.finalizing : texts.finalize }}
        </Button>
        <Button
          variant="outline"
          class="min-h-11"
          data-testid="preview-discard"
          :disabled="busy"
          @click="confirmDiscard()"
        >
          {{ texts.discard }}
        </Button>
      </ActionArea>
    </header>

    <p
      v-if="blockers.length > 0"
      class="text-destructive text-sm"
      role="alert"
      data-testid="preview-blocked"
    >
      {{ texts.finalizeBlocked }}
    </p>
    <p
      v-if="actionError || finalizeError"
      class="text-destructive text-sm"
      role="alert"
      data-testid="preview-error"
    >
      {{ finalizeError ?? actionError }}
    </p>
    <FeedbackMessage
      v-if="resolve.isPending.value"
      message="Zapisywanie decyzji i przeliczanie podglądu…"
    />

    <p v-if="isEmpty" class="text-muted-foreground text-sm" data-testid="preview-empty">
      {{ texts.previewEmpty }}
    </p>

    <Card class="rounded-2xl" data-testid="preview-issues">
      <CardHeader>
        <CardTitle>{{ texts.issuesTitle }}</CardTitle>
        <CardDescription>{{ texts.issuesSubtitle }}</CardDescription>
      </CardHeader>
      <CardContent>
        <p
          v-if="generation.issues.length === 0"
          class="text-muted-foreground text-sm"
          data-testid="preview-issues-empty"
        >
          {{ texts.issuesEmpty }}
        </p>
        <ul v-else class="grid gap-2">
          <li
            v-for="issue in generation.issues"
            :key="issue.key"
            class="border-border grid gap-1 rounded-lg border px-3 py-2"
            :data-testid="`preview-issue-${issue.kind}`"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="rounded-lg px-2 py-0.5 text-xs font-medium"
                :class="
                  issue.severity === 'blocker'
                    ? 'bg-destructive/15 text-destructive'
                    : 'bg-warning/15 text-warning'
                "
              >
                {{ issue.severity === 'blocker' ? texts.issueBlocker : texts.issueWarning }}
              </span>
              <span
                v-if="issue.dismissed"
                class="bg-muted text-muted-foreground rounded-lg px-2 py-0.5 text-xs font-medium"
              >
                {{ texts.dismissedIssue }}
              </span>
            </div>
            <p class="text-sm">{{ issue.message }}</p>
            <div v-if="!issue.dismissed && issue.severity === 'blocker'">
              <Button
                variant="outline"
                class="min-h-11"
                :data-testid="`preview-dismiss-${issue.kind}`"
                :disabled="busy"
                @click="dismissIssue(issue.key)"
              >
                {{ texts.dismissIssue }}
              </Button>
            </div>
          </li>
        </ul>
      </CardContent>
    </Card>

    <Card
      v-for="round in generation.rounds"
      :key="round.key"
      class="rounded-2xl"
      :data-testid="`preview-round-${round.key}`"
    >
      <CardHeader>
        <CardTitle class="flex flex-wrap items-center gap-2">
          <span>{{ round.name }}</span>
          <span
            v-if="round.shopping_date !== null"
            class="bg-muted text-muted-foreground rounded-lg px-2 py-0.5 text-xs font-medium"
          >
            {{ texts.shoppingDay }}: {{ formatDate(round.shopping_date) }}
          </span>
        </CardTitle>
        <CardDescription>{{ rangeLabel(round) }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p
          v-if="round.items.length === 0"
          class="text-muted-foreground text-sm"
          :data-testid="`preview-round-empty-${round.key}`"
        >
          {{ texts.roundEmpty }}
        </p>

        <div
          v-for="group in groupByCategory(round)"
          :key="`${round.key}-${group.name}`"
          class="grid gap-2"
        >
          <h3 class="text-muted-foreground text-xs font-semibold break-words uppercase">
            {{ group.name }}
          </h3>

          <ul class="grid gap-2">
            <li
              v-for="line in group.items"
              :key="`${round.key}-${line.product_id}`"
              class="border-border grid min-w-0 gap-3 border-b py-4 last:border-0"
              :class="line.already_have ? 'opacity-60' : ''"
              :data-testid="`preview-item-${line.product_id}`"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="min-w-0 font-medium break-words">{{ line.label }}</span>
                <span class="tabular-nums" :data-testid="`preview-needed-${line.product_id}`">
                  {{ texts.needed }}: {{ formatAmount(line.needed_amount, line.amount_unit) }}
                </span>
              </div>

              <div class="flex flex-wrap items-center gap-2 text-sm">
                <span
                  v-if="line.packages_count !== null"
                  class="tabular-nums"
                  :data-testid="`preview-packages-${line.product_id}`"
                >
                  {{ texts.packages }}: {{ line.packages_count }} ×
                  {{ formatAmount(line.package_amount, line.amount_unit) }}
                </span>
                <LeftoverBadge :leftover="line.leftover_amount" :unit="line.amount_unit" />
                <span
                  v-if="
                    line.from_pantry_amount !== null && !decimalsEqual(line.from_pantry_amount, '0')
                  "
                  class="bg-secondary/15 text-secondary rounded-lg px-2 py-0.5 text-xs font-medium"
                  :data-testid="`preview-from-pantry-${line.product_id}`"
                >
                  {{ texts.fromPantry }}:
                  {{ formatAmount(line.from_pantry_amount, line.amount_unit) }}
                </span>
                <span
                  v-if="line.already_have"
                  class="bg-muted text-muted-foreground rounded-lg px-2 py-0.5 text-xs font-medium"
                  :data-testid="`preview-already-have-${line.product_id}`"
                >
                  {{ texts.alreadyHaveShort }}
                </span>
              </div>

              <div class="flex flex-wrap items-center gap-2">
                <label
                  v-if="line.retail_options.length > 0"
                  class="grid w-full min-w-0 gap-1 text-xs sm:w-auto sm:max-w-full"
                >
                  {{ texts.chooseRetail }}
                  <select
                    class="border-border bg-card min-h-11 w-full min-w-0 max-w-full rounded-lg border px-3 text-sm"
                    :value="line.retail_product_id === null ? '' : String(line.retail_product_id)"
                    :disabled="busy"
                    :data-testid="`preview-retail-select-${line.product_id}`"
                    @change="chooseRetail(line, ($event.target as HTMLSelectElement).value)"
                  >
                    <option
                      v-for="option in line.retail_options"
                      :key="option.retail_product_id"
                      :value="String(option.retail_product_id)"
                    >
                      {{ option.label }}{{ option.store_name ? ` · ${option.store_name}` : '' }} ({{
                        formatAmount(option.package_amount, line.amount_unit)
                      }})
                    </option>
                  </select>
                </label>

                <template v-else>
                  <span class="text-muted-foreground text-xs">{{ texts.noRetail }}</span>
                  <Button
                    variant="outline"
                    class="min-h-11"
                    :data-testid="`preview-add-retail-${line.product_id}`"
                    :disabled="busy"
                    @click="retailDrawerFor = line"
                  >
                    + {{ texts.addRetail }}
                  </Button>
                </template>

                <label class="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    class="size-5"
                    :checked="line.already_have"
                    :disabled="busy"
                    :data-testid="`preview-toggle-have-${line.product_id}`"
                    @change="toggleAlreadyHave(line)"
                  />
                  {{ texts.alreadyHave }}
                </label>
              </div>
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>

    <!-- Panel odjęć: TYLKO gdy użytkownik zgodził się uwzględnić spiżarnię. -->
    <Card v-if="generation.use_pantry" class="rounded-2xl" data-testid="preview-pantry-panel">
      <CardHeader>
        <CardTitle>{{ texts.fromPantryTitle }}</CardTitle>
        <CardDescription>{{ texts.fromPantrySubtitle }}</CardDescription>
      </CardHeader>
      <CardContent>
        <p v-if="pantryLines.length === 0" class="text-muted-foreground text-sm">
          {{ texts.fromPantryEmpty }}
        </p>
        <ul v-else class="grid gap-1 text-sm">
          <li
            v-for="line in pantryLines"
            :key="`pantry-${line.round_key}-${line.product_id}`"
            class="flex flex-wrap items-center justify-between gap-2"
          >
            <span>{{ line.label }}</span>
            <span class="tabular-nums">
              {{ formatAmount(line.from_pantry_amount, line.amount_unit) }}
            </span>
          </li>
        </ul>
      </CardContent>
    </Card>

    <RetailProductCreateDrawer
      v-if="retailDrawerFor !== null"
      :open="true"
      :canonical-product-id="retailDrawerFor.product_id"
      :prefill-name="retailDrawerFor.label"
      @created="(retail) => onRetailCreated(retailDrawerFor as PreviewLine, retail)"
      @close="retailDrawerFor = null"
    />
  </section>
</template>
