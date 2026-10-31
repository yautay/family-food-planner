<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import {
  fetchGeneration,
  fetchRoundConfigs,
  finalizeGeneration,
  generateShopping,
} from '@/api/shopping'
import ActionArea from '@/components/domain/ActionArea.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import FeedbackMessage from '@/components/domain/FeedbackMessage.vue'
import LoadingState from '@/components/domain/LoadingState.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import SummaryPanel from '@/components/domain/SummaryPanel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { navigationRange } from '@/lib/navigation'
import { common, shopping as texts } from '@/lib/texts'
import { useShoppingDraftStore } from '@/stores/shoppingDraft'
import RoundConfigSection from '@/pages/zakupy/RoundConfigSection.vue'
import ShoppingListsCatalog from '@/pages/zakupy/ShoppingListsCatalog.vue'
import ZakupyPreview from '@/pages/zakupy/ZakupyPreview.vue'

const queryClient = useQueryClient()
const route = useRoute()
const draft = useShoppingDraftStore()
const generatorHeading = ref<HTMLElement | null>(null)
const createdResult = ref<HTMLElement | null>(null)

// Sam zakres, także przy ponownym użyciu komponentu bez remountu.
// Niepełny/błędny query nie zastępuje szkicu i nigdy nie wysyła POST.
watch(
  () => navigationRange(route.query),
  (range, previous) => {
    if (!range || (range.from === previous?.from && range.to === previous?.to)) return
    draft.applyNavigationRange(range)
  },
  { immediate: true },
)

const configs = useQuery({ queryKey: queryKeys.shopping.roundConfigs, queryFn: fetchRoundConfigs })
const noRounds = computed(() => configs.data.value?.items.length === 0)
const allRounds = computed({
  get: () => draft.roundConfigIds === null,
  set: (all: boolean) => {
    draft.roundConfigIds = all ? null : (configs.data.value?.items.map((item) => item.id) ?? [])
  },
})
const generation = useQuery({
  queryKey: computed(() => queryKeys.shopping.generation(draft.generationId ?? 0)),
  queryFn: () => fetchGeneration(draft.generationId as number),
  enabled: computed(() => draft.generationId !== null),
})
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : common.unexpectedError
}
const generate = useMutation({
  mutationFn: () =>
    generateShopping({
      date_from: draft.dateFrom,
      date_to: draft.dateTo,
      use_pantry: draft.usePantry,
      round_config_ids: draft.roundConfigIds,
    }),
  onSuccess: (created) => {
    queryClient.setQueryData(queryKeys.shopping.generation(created.id), created)
    draft.openGeneration(created.id)
    // Zgoda dotyczy tej jednej generacji, nie kolejnego użycia formularza.
    draft.usePantry = false
  },
})
const finalize = useMutation({
  mutationFn: () => finalizeGeneration(draft.generationId as number),
  onSuccess: () => {
    draft.reset()
    generate.reset()
    void queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
  },
})
watch(
  () => finalize.isSuccess.value,
  async (success) => {
    if (!success) return
    await nextTick()
    createdResult.value?.focus()
  },
)

async function openGenerator(): Promise<void> {
  await nextTick()
  generatorHeading.value?.focus()
}
function onDiscarded(): void {
  draft.reset()
  generate.reset()
  finalize.reset()
  void openGenerator()
}
function requestPreview(): void {
  if (
    draft.rangeValid &&
    !noRounds.value &&
    configs.data.value &&
    !generate.isPending.value &&
    !finalize.isPending.value
  ) {
    // Nowe żądanie ma własny wynik: poprzednia finalizacja nie jest jego sukcesem.
    finalize.reset()
    generate.mutate()
  }
}
</script>

<template>
  <section class="grid min-w-0 gap-8" data-testid="zakupy-page">
    <PageHeader
      :title="texts.title"
      description="Wszystkie listy w jednym miejscu. Zakupy przygotujesz z wybranych dni planu."
    >
      <template #actions>
        <Button variant="outline" data-testid="zakupy-new-list" @click="openGenerator()">{{
          texts.newListFromPlan
        }}</Button>
      </template>
    </PageHeader>

    <ShoppingListsCatalog @create="openGenerator()" />

    <!-- Wynik jest danymi mutacji TanStack Query, nigdy lokalną kopią list. -->
    <div
      v-if="finalize.data.value"
      ref="createdResult"
      tabindex="-1"
      data-testid="zakupy-created-lists"
    >
      <SummaryPanel
        title="Listy są zapisane"
        description="Możesz otworzyć każdą turę. Listy znajdziesz także w katalogu powyżej."
      >
        <FeedbackMessage tone="success" :message="texts.finalizeDone" />
        <ul class="grid gap-3">
          <li
            v-for="list in finalize.data.value.items"
            :key="list.id"
            class="flex min-w-0 flex-wrap items-center justify-between gap-3"
            :data-testid="`created-list-${list.id}`"
          >
            <div class="grid min-w-0 gap-1">
              <span class="font-medium break-words">{{ list.round_name ?? list.name }}</span>
              <span class="text-muted-foreground text-sm break-words"
                >{{ list.name }} · {{ texts.itemsCount(list.items.length) }}</span
              >
            </div>
            <Button as-child variant="outline">
              <RouterLink
                :to="{ name: 'zakupy-lista', params: { id: list.id } }"
                :data-testid="`created-list-link-${list.id}`"
                >{{ texts.openList }}</RouterLink
              >
            </Button>
          </li>
        </ul>
      </SummaryPanel>
    </div>

    <section
      class="border-border bg-card grid min-w-0 gap-6 rounded-2xl border p-4 sm:p-6"
      data-testid="zakupy-generator"
      aria-labelledby="generator-title"
    >
      <header class="grid gap-2">
        <p class="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          1. Zakres → 2. Podgląd → 3. Zapisane listy
        </p>
        <h2 id="generator-title" ref="generatorHeading" tabindex="-1" class="text-xl font-semibold">
          {{ texts.newListFromPlan }}
        </h2>
        <p class="text-muted-foreground text-sm">
          Wybierz dni planu. Przed utworzeniem list sprawdzisz produkty, opakowania i przewidywane
          resztki.
        </p>
      </header>

      <form class="grid gap-4" data-testid="zakupy-form" @submit.prevent="requestPreview()">
        <div class="flex min-w-0 flex-wrap gap-3">
          <label class="grid min-w-0 flex-1 basis-64 gap-1 text-sm"
            >{{ texts.dateFrom }}
            <Input
              v-model="draft.dateFrom"
              type="date"
              required
              data-testid="zakupy-date-from"
              :disabled="generate.isPending.value || finalize.isPending.value"
            />
          </label>
          <label class="grid min-w-0 flex-1 basis-64 gap-1 text-sm"
            >{{ texts.dateTo }}
            <Input
              v-model="draft.dateTo"
              type="date"
              required
              data-testid="zakupy-date-to"
              :disabled="generate.isPending.value || finalize.isPending.value"
            />
          </label>
        </div>
        <label class="flex min-h-11 items-start gap-3 text-sm">
          <input
            v-model="draft.usePantry"
            type="checkbox"
            class="mt-0.5 size-5 shrink-0"
            data-testid="zakupy-use-pantry"
            :disabled="generate.isPending.value || finalize.isPending.value"
          />
          <span class="grid gap-1"
            ><span class="font-medium">{{ texts.usePantryLabel }}</span
            ><span class="text-muted-foreground text-xs">{{ texts.usePantryHint }}</span></span
          >
        </label>
        <p v-if="!draft.rangeValid" class="text-destructive text-sm" role="alert">
          {{ texts.rangeInvalid }}
        </p>
        <ErrorState
          v-if="configs.isError.value && !configs.data.value"
          message="Nie udało się wczytać tur zakupów. Ponów wczytywanie przed przygotowaniem podglądu."
          :pending="configs.isFetching.value"
          @retry="configs.refetch()"
        />
        <p
          v-if="noRounds"
          class="text-warning text-sm"
          role="status"
          data-testid="zakupy-no-rounds"
        >
          Dodaj pierwszą turę w sekcji „Podział zakupów i tury” poniżej, aby przygotować listę.
        </p>
        <ActionArea label="Przygotowanie podglądu">
          <Button
            type="submit"
            :variant="generation.data.value ? 'outline' : 'default'"
            :disabled="
              !draft.rangeValid ||
              !configs.data.value ||
              noRounds ||
              generate.isPending.value ||
              finalize.isPending.value
            "
            :aria-busy="generate.isPending.value"
            data-testid="zakupy-generate"
            >{{ generate.isPending.value ? texts.generating : texts.generate }}</Button
          >
        </ActionArea>
        <p
          v-if="generate.isError.value"
          class="text-destructive text-sm"
          role="alert"
          data-testid="zakupy-error"
        >
          {{ errorMessage(generate.error.value) }}
        </p>
      </form>

      <!-- Ta sama konfiguracja, którą UX10 może później osadzić w ustawieniach. -->
      <details
        :open="noRounds"
        class="border-border border-t pt-4"
        data-testid="zakupy-round-settings"
      >
        <summary class="min-h-11 cursor-pointer py-3 text-sm font-medium">
          Podział zakupów i tury<span v-if="configs.data.value">
            ({{ configs.data.value.items.length }})</span
          >
        </summary>
        <fieldset v-if="configs.data.value && !noRounds" class="mb-4 grid gap-2">
          <legend class="mb-2 text-sm font-medium">Tury dla tego podglądu</legend>
          <label class="flex min-h-11 items-center gap-3 text-sm"
            ><input
              v-model="allRounds"
              type="checkbox"
              class="size-5"
              data-testid="round-selection-all"
              :disabled="generate.isPending.value || finalize.isPending.value"
            />Wszystkie skonfigurowane tury</label
          >
          <template v-if="draft.roundConfigIds !== null">
            <label
              v-for="config in configs.data.value.items"
              :key="config.id"
              class="flex min-h-11 items-center gap-3 text-sm"
              ><input
                v-model="draft.roundConfigIds"
                type="checkbox"
                :value="config.id"
                class="size-5"
                :data-testid="`round-selection-${config.id}`"
                :disabled="generate.isPending.value || finalize.isPending.value"
              />{{ config.name }}</label
            >
            <p v-if="draft.roundConfigIds.length === 0" class="text-muted-foreground text-sm">
              Bez zaznaczonych tur powstanie jedna lista bez podziału.
            </p>
          </template>
        </fieldset>
        <RoundConfigSection />
      </details>

      <LoadingState
        v-if="generation.isPending.value && draft.generationId !== null"
        label="Wczytywanie podglądu zakupów…"
      />
      <ErrorState
        v-else-if="
          generation.isError.value && !generation.data.value && draft.generationId !== null
        "
        message="Nie udało się wczytać podglądu. Zakres dat pozostaje wybrany."
        :pending="generation.isFetching.value"
        @retry="generation.refetch()"
      />
      <template v-if="generation.data.value && draft.generationId !== null">
        <FeedbackMessage
          v-if="
            generation.data.value.date_from !== draft.dateFrom ||
            generation.data.value.date_to !== draft.dateTo
          "
          tone="warning"
          message="Podgląd dotyczy poprzedniego zakresu widocznego poniżej. Aby uwzględnić zmienione daty, ponownie pokaż podgląd zakupów."
          data-testid="preview-range-changed"
        />
        <ErrorState
          v-if="generation.isRefetchError.value"
          compact
          message="Nie udało się odświeżyć podglądu. Pokazujemy ostatnio wczytane dane."
          :pending="generation.isFetching.value"
          @retry="generation.refetch()"
        />
        <ZakupyPreview
          :generation="generation.data.value"
          :finalize-pending="finalize.isPending.value"
          :finalize-error="finalize.isError.value ? errorMessage(finalize.error.value) : null"
          :generate-pending="generate.isPending.value"
          @finalize="finalize.mutate()"
          @discarded="onDiscarded"
        />
      </template>
    </section>
  </section>
</template>
