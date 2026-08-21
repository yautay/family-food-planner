<script setup lang="ts">
/**
 * Kolejka weryfikacji produktów (`/admin/weryfikacja`).
 *
 * Produkty dodane inline przez użytkowników trafiają tu jako `UNVERIFIED`
 * (02_DOMAIN §4.9). Administrator uzupełnia wartości w formularzu produktu
 * i wraca; przycisk „Zweryfikuj" działa dopiero przy komplecie danych — bez
 * niego backend odpowie 422 i pokaże, czego brakuje.
 *
 * Najstarsze na górze: kolejka ma się opróżniać, a nie rosnąć od góry.
 * Lista korzysta z tego samego klucza zapytań co katalog (`products.list`
 * z filtrem statusu), więc jedna inwalidacja odświeża oba widoki.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import type { Product, ProductFilters } from '@/api/catalog'
import { fetchProducts, verifyProduct } from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNutrient } from '@/lib/format'
import { adminVerification as texts, common, products as productTexts } from '@/lib/texts'

const PAGE_SIZE = 50

const queryClient = useQueryClient()

const filters: ProductFilters = {
  limit: PAGE_SIZE,
  offset: 0,
  verification_status: 'unverified',
}

const queue = useQuery({
  queryKey: queryKeys.products.list(filters),
  queryFn: () => fetchProducts(filters),
})

/** Najstarsze pierwsze — API sortuje po nazwie, kolejność wieku ustawiamy tutaj. */
const items = computed<Product[]>(() =>
  [...(queue.data.value?.items ?? [])].sort((left, right) =>
    left.created_at.localeCompare(right.created_at),
  ),
)

const actionError = ref<string | null>(null)

const verify = useMutation({
  mutationFn: (product: Product) => verifyProduct(product.id),
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.products.all })
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

/** Warunki weryfikacji egzekwowane przez backend (`REQUIRED_FOR_VERIFICATION` + źródło). */
function canVerify(product: Product): boolean {
  return product.completeness.has_core_macros && Boolean(product.nutrition.nutrition_source?.trim())
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('pl-PL')
}
</script>

<template>
  <section class="grid gap-6" data-testid="admin-weryfikacja-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <p v-if="actionError" class="text-destructive text-sm" role="alert" data-testid="verify-error">
      {{ actionError }}
    </p>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ productTexts.unverified }}</CardTitle>
        <CardDescription class="tabular-nums">
          {{ queue.data.value?.total ?? 0 }}
        </CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p v-if="queue.isPending.value" class="text-muted-foreground text-sm">
          {{ common.loading }}
        </p>
        <p
          v-else-if="items.length === 0"
          class="text-muted-foreground text-sm"
          data-testid="verification-empty"
        >
          {{ texts.emptyState }}
        </p>

        <ul v-else class="grid gap-2" data-testid="verification-list">
          <li
            v-for="product in items"
            :key="product.id"
            class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-[1fr_auto] md:items-center"
            :data-testid="`verification-row-${product.id}`"
          >
            <div class="min-w-0">
              <p class="truncate font-medium">{{ product.name }}</p>
              <p class="text-muted-foreground truncate text-sm">
                {{ product.category_name }}
                <span aria-hidden="true"> · </span>
                {{ texts.addedAt }}: {{ formatDate(product.created_at) }}
              </p>
              <p class="text-sm tabular-nums">
                {{ formatNutrient(product.nutrition.kcal_100, 'kcal') }} / 100
              </p>
              <p
                v-if="!product.completeness.complete"
                class="text-warning text-xs"
                :data-testid="`verification-missing-${product.id}`"
              >
                {{ productTexts.incompleteData }}: {{ product.completeness.missing.join(', ') }}
              </p>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button as-child variant="outline" class="min-h-11">
                <RouterLink
                  :to="{ name: 'produkt-edycja', params: { id: product.id } }"
                  :data-testid="`verification-open-${product.id}`"
                >
                  {{ texts.openProduct }}
                </RouterLink>
              </Button>
              <!-- Backend wymaga do weryfikacji rdzenia makro ORAZ źródła danych
                   (422 bez któregokolwiek) — przycisk odzwierciedla oba warunki,
                   żeby nie wyglądał na klikalny i nie kończył się błędem. -->
              <Button
                type="button"
                class="min-h-11"
                :disabled="!canVerify(product) || verify.isPending.value"
                :title="productTexts.verifyHint"
                :data-testid="`verification-verify-${product.id}`"
                @click="verify.mutate(product)"
              >
                {{ productTexts.verify }}
              </Button>
            </div>
          </li>
        </ul>
      </CardContent>
    </Card>
  </section>
</template>
