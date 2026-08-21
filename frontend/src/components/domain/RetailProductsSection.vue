<script setup lang="ts">
/**
 * Sekcja „Produkty sklepowe" na karcie produktu kanonicznego (widok 8, B09).
 *
 * Warianty retail są własnością produktu kanonicznego, więc mieszkają na jego
 * karcie — użytkownik nie idzie do osobnego ekranu, żeby dopisać „Pilos Jogurt
 * naturalny 400 g" do jogurtu (06_UIUX §2: minimum ekranów pośrednich).
 * Dodawanie odbywa się w drawerze, czyli bez opuszczania karty (AC 5).
 *
 * Komponent jest wydzielony z `ProduktFormPage.vue`, bo strona ma już trzy
 * sekcje o różnych właścicielach; tutaj cały stan to jeden `ref` (otwarty
 * drawer), a dane serwera trzyma TanStack Query (ADR-007).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RetailProduct } from '@/api/retail'
import { deleteRetailProduct, fetchRetailProducts, updateRetailProduct } from '@/api/retail'
import RetailProductCreateDrawer from '@/components/domain/RetailProductCreateDrawer.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatAmount } from '@/lib/format'
import { common, retail as texts } from '@/lib/texts'

interface UsedIn {
  type: string
  id: number
  name: string
}

const props = defineProps<{ productId: number }>()

const queryClient = useQueryClient()

const drawerOpen = ref(false)
const actionError = ref<string | null>(null)
const usedIn = ref<UsedIn[]>([])
/** Wariant, którego usunięcie odbiło się 409 — ENCJA, nie id (patrz `SklepySection`). */
const conflictItem = ref<RetailProduct | null>(null)

const filters = computed(() => ({
  limit: 50,
  offset: 0,
  canonical_product_id: props.productId,
  include_archived: true,
}))
const variants = useQuery({
  queryKey: computed(() => queryKeys.retailProducts.list(filters.value)),
  queryFn: () => fetchRetailProducts(filters.value),
  enabled: computed(() => props.productId > 0),
})

const items = computed<RetailProduct[]>(() => variants.data.value?.items ?? [])

/**
 * Komunikat błędu + lista „Używane w:" z 409.
 *
 * Nigdy nie przekazujemy tej funkcji WPROST jako `onError`: TanStack woła
 * handler z `(error, variables, …)`, więc drugi argument byłby zmiennymi
 * mutacji, a nie wariantem, o który chodzi.
 */
function reportError(error: unknown, item: RetailProduct | null = null): void {
  usedIn.value = []
  conflictItem.value = null
  if (error instanceof ApiError) {
    actionError.value = error.message
    const details = error.details.used_in
    if (Array.isArray(details) && details.length) {
      usedIn.value = details as UsedIn[]
      conflictItem.value = item
    }
    return
  }
  actionError.value = common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.retailProducts.all })
}

const toggleArchive = useMutation({
  mutationFn: (item: RetailProduct) =>
    updateRetailProduct(item.id, { is_archived: !item.is_archived }),
  onSuccess: async () => {
    actionError.value = null
    usedIn.value = []
    await refresh()
  },
  onError: (error: unknown) => reportError(error),
})

const remove = useMutation({
  mutationFn: (item: RetailProduct) => deleteRetailProduct(item.id),
  onSuccess: async () => {
    actionError.value = null
    usedIn.value = []
    await refresh()
  },
  onError: (error: unknown, item: RetailProduct) => reportError(error, item),
})

function confirmRemove(item: RetailProduct): void {
  if (window.confirm(texts.confirmDelete)) {
    remove.mutate(item)
  }
}

async function onCreated(): Promise<void> {
  drawerOpen.value = false
  actionError.value = null
  await refresh()
}

/** Opis opakowania: „400 g", „1,5 kg", „10 szt. (10 w opakowaniu)". */
function packageLabel(item: RetailProduct): string {
  const base = formatAmount(item.package_amount, item.package_unit)
  return item.pieces_per_package === null
    ? base
    : `${base} · ${item.pieces_per_package} ${texts.piecesLabel.toLocaleLowerCase('pl-PL')}`
}
</script>

<template>
  <Card class="rounded-xl" data-testid="retail-section">
    <CardHeader>
      <CardTitle>{{ texts.sectionTitle }}</CardTitle>
      <CardDescription>{{ texts.sectionSubtitle }}</CardDescription>
    </CardHeader>

    <CardContent class="grid gap-3">
      <div v-if="actionError" class="grid gap-2" role="alert" data-testid="retail-error">
        <p class="text-destructive text-sm">{{ actionError }}</p>
        <template v-if="usedIn.length">
          <p class="text-destructive text-sm font-medium">{{ texts.usedInIntro }}</p>
          <ul class="text-destructive text-sm" data-testid="retail-used-in">
            <li v-for="entry in usedIn" :key="`${entry.type}-${entry.id}`">· {{ entry.name }}</li>
          </ul>
          <Button
            v-if="conflictItem !== null"
            type="button"
            variant="outline"
            class="min-h-11 justify-self-start"
            data-testid="retail-archive-instead"
            @click="toggleArchive.mutate(conflictItem)"
          >
            {{ texts.archive }}
          </Button>
        </template>
      </div>

      <p
        v-if="items.length === 0 && !variants.isPending.value"
        class="text-muted-foreground text-sm"
        data-testid="retail-empty"
      >
        {{ texts.emptyState }}
      </p>

      <ul v-else class="grid gap-2" data-testid="retail-list">
        <li
          v-for="item in items"
          :key="item.id"
          class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-[auto_1fr_auto] md:items-center"
          :data-testid="`retail-row-${item.id}`"
        >
          <img
            v-if="item.photo_thumb_url"
            :src="item.photo_thumb_url"
            :alt="item.name"
            class="h-12 w-12 rounded-lg object-cover"
            :data-testid="`retail-thumb-${item.id}`"
          />
          <span v-else class="bg-muted h-12 w-12 rounded-lg" aria-hidden="true" />

          <div class="min-w-0">
            <p class="truncate font-medium" :data-testid="`retail-name-${item.id}`">
              {{ item.name }}
            </p>
            <p class="text-muted-foreground text-sm tabular-nums">
              <span :data-testid="`retail-package-${item.id}`">{{ packageLabel(item) }}</span>
              <template v-if="item.brand">
                <span aria-hidden="true"> · </span>{{ item.brand }}
              </template>
              <span aria-hidden="true"> · </span>
              {{ item.store_name ?? texts.noStore }}
              <template v-if="item.is_archived">
                <span aria-hidden="true"> · </span>{{ texts.archived }}
              </template>
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <Button
              variant="outline"
              class="min-h-11"
              :disabled="toggleArchive.isPending.value"
              :data-testid="`retail-archive-${item.id}`"
              @click="toggleArchive.mutate(item)"
            >
              {{ item.is_archived ? texts.restore : texts.archive }}
            </Button>
            <Button
              variant="ghost"
              class="min-h-11"
              :disabled="remove.isPending.value"
              :data-testid="`retail-delete-${item.id}`"
              @click="confirmRemove(item)"
            >
              {{ common.remove }}
            </Button>
          </div>
        </li>
      </ul>

      <Button
        v-if="!drawerOpen"
        class="min-h-11 justify-self-start"
        data-testid="retail-add"
        @click="drawerOpen = true"
      >
        {{ texts.addProduct }}
      </Button>

      <RetailProductCreateDrawer
        :open="drawerOpen"
        :canonical-product-id="productId"
        @created="onCreated"
        @close="drawerOpen = false"
      />
    </CardContent>
  </Card>
</template>
