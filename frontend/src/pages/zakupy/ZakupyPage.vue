<script setup lang="ts">
/**
 * Zakupy (`/zakupy`, karta B10 §Frontend).
 *
 * Trzy warstwy na jednym ekranie, w kolejności użycia: konfiguracja tur →
 * formularz generacji → podgląd. Mniej ekranów pośrednich = mniej kliknięć od
 * intencji do efektu (06_UIUX §2).
 *
 * **Checkbox „Uwzględnić stan domowy?" jest domyślnie ODZNACZONY i nie jest
 * zapamiętywany** (02_DOMAIN §8): spiżarnia bywa nieaktualna, więc decyzję
 * podejmuje człowiek przy każdej generacji. Store `shoppingDraft` trzyma tylko
 * stan formularza; podgląd to stan serwera i mieszka w TanStack Query (ADR-007).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { ShoppingList } from '@/api/shopping'
import { fetchGeneration, generateShopping } from '@/api/shopping'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { common, shopping as texts } from '@/lib/texts'
import { useShoppingDraftStore } from '@/stores/shoppingDraft'
import RoundConfigSection from '@/pages/zakupy/RoundConfigSection.vue'
import ZakupyPreview from '@/pages/zakupy/ZakupyPreview.vue'

const queryClient = useQueryClient()
const draft = useShoppingDraftStore()
const actionError = ref<string | null>(null)
const createdLists = ref<ShoppingList[]>([])

const generation = useQuery({
  queryKey: computed(() => queryKeys.shopping.generation(draft.generationId ?? 0)),
  queryFn: () => fetchGeneration(draft.generationId as number),
  enabled: computed(() => draft.generationId !== null),
})

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
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
    actionError.value = null
    createdLists.value = []
    // Świeży podgląd wkładamy do cache pod jego kluczem: `GET` generacji zwróci
    // to samo (liczy z `params`), więc nie ma po co pytać drugi raz.
    queryClient.setQueryData(queryKeys.shopping.generation(created.id), created)
    draft.openGeneration(created.id)
  },
  onError: reportError,
})

function onFinalized(lists: ShoppingList[]): void {
  createdLists.value = lists
  draft.reset()
}

function onDiscarded(): void {
  createdLists.value = []
  draft.reset()
}
</script>

<template>
  <section class="grid gap-6" data-testid="zakupy-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <RoundConfigSection />

    <Card class="rounded-xl" data-testid="zakupy-form">
      <CardHeader>
        <CardTitle>{{ texts.formTitle }}</CardTitle>
        <CardDescription>{{ texts.formSubtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-4">
        <div class="grid gap-3 md:grid-cols-2">
          <label class="grid gap-1 text-sm">
            {{ texts.dateFrom }}
            <Input
              v-model="draft.dateFrom"
              type="date"
              class="min-h-11"
              data-testid="zakupy-date-from"
            />
          </label>
          <label class="grid gap-1 text-sm">
            {{ texts.dateTo }}
            <Input
              v-model="draft.dateTo"
              type="date"
              class="min-h-11"
              data-testid="zakupy-date-to"
            />
          </label>
        </div>

        <!-- Jawne pytanie o spiżarnię: NIGDY nie zaznaczamy go za użytkownika. -->
        <label class="flex min-h-11 items-start gap-2 text-sm">
          <input
            v-model="draft.usePantry"
            type="checkbox"
            class="mt-0.5 size-5"
            data-testid="zakupy-use-pantry"
          />
          <span class="grid gap-0.5">
            <span class="font-medium">{{ texts.usePantryLabel }}</span>
            <span class="text-muted-foreground text-xs">{{ texts.usePantryHint }}</span>
          </span>
        </label>

        <p v-if="!draft.rangeValid" class="text-destructive text-sm" role="alert">
          {{ texts.rangeInvalid }}
        </p>

        <div>
          <Button
            class="min-h-11"
            :disabled="!draft.rangeValid || generate.isPending.value"
            data-testid="zakupy-generate"
            @click="generate.mutate()"
          >
            {{ generate.isPending.value ? texts.generating : texts.generate }}
          </Button>
        </div>

        <p
          v-if="actionError"
          class="text-destructive text-sm"
          role="alert"
          data-testid="zakupy-error"
        >
          {{ actionError }}
        </p>
      </CardContent>
    </Card>

    <p
      v-if="generation.isPending.value && draft.generationId !== null"
      class="text-muted-foreground text-sm"
    >
      {{ common.loading }}
    </p>

    <ZakupyPreview
      v-else-if="generation.data.value"
      :generation="generation.data.value"
      @finalized="onFinalized"
      @discarded="onDiscarded"
    />

    <!-- Nawigacja po finalizacji: pełna strona listy powstaje w BATCH_11, tu
         zostaje podsumowanie z linkiem do trasy-zaślepki. -->
    <Card v-if="createdLists.length > 0" class="rounded-xl" data-testid="zakupy-created-lists">
      <CardHeader>
        <CardTitle>{{ texts.createdListsTitle }}</CardTitle>
        <CardDescription>{{ texts.finalizeDone }}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul class="grid gap-2">
          <li
            v-for="list in createdLists"
            :key="list.id"
            class="border-border flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2"
            :data-testid="`created-list-${list.id}`"
          >
            <span class="grid gap-0.5">
              <span class="font-medium">{{ list.round_name ?? list.name }}</span>
              <span class="text-muted-foreground text-xs">
                {{ list.name }} · {{ texts.itemsCount(list.items.length) }}
              </span>
            </span>
            <Button as-child variant="outline" class="min-h-11">
              <RouterLink
                :to="{ name: 'zakupy-lista', params: { id: list.id } }"
                :data-testid="`created-list-link-${list.id}`"
              >
                {{ texts.openList }}
              </RouterLink>
            </Button>
          </li>
        </ul>
      </CardContent>
    </Card>
  </section>
</template>
