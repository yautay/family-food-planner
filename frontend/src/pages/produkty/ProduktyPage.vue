<script setup lang="ts">
/**
 * Katalog produktów (`/produkty`, widok 8 wizualizacji).
 *
 * Stan serwera trzyma TanStack Query (ADR-007) — lista nie jest kopiowana do
 * żadnego ref-a. Szukajka jedzie na `?q=` z debounce, bo trigram liczy baza;
 * filtrowanie po stronie klienta rozjechałoby się z paginacją.
 *
 * Archiwalne produkty są domyślnie schowane (ADR-012) — przełącznik pokazuje je
 * z plakietką, żeby było widać, dlaczego nie ma ich w pickerach.
 */
import { useQuery } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { computed, ref } from 'vue'

import { fetchCategories, fetchProducts } from '@/api/catalog'
import { PAGE_SIZE, usePaginatedList } from '@/api/pagination'
import type { ProductsFilters } from '@/api/queryKeys'
import { queryKeys } from '@/api/queryKeys'
import LoadMoreButton from '@/components/domain/LoadMoreButton.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { formatNutrient } from '@/lib/format'
import { common, listCount, products as texts } from '@/lib/texts'

const search = ref('')
const debouncedSearch = refDebounced(search, 250)
const categoryId = ref<number | null>(null)
const includeArchived = ref(false)

const categories = useQuery({ queryKey: queryKeys.categories.all, queryFn: fetchCategories })

// Filtry BEZ `offset` — numer strony niesie `pageParam` (src/api/pagination.ts).
const filters = computed<ProductsFilters>(() => ({
  limit: PAGE_SIZE,
  q: debouncedSearch.value.trim() || undefined,
  category_id: categoryId.value ?? undefined,
  include_archived: includeArchived.value,
}))

const products = usePaginatedList({
  queryKey: computed(() => queryKeys.products.list(filters.value)),
  fetchPage: (page) => fetchProducts({ ...filters.value, ...page }),
})

const items = products.items
const isEmpty = computed(() => !products.isPending.value && items.value.length === 0)
const isSearching = computed(() => debouncedSearch.value.trim().length > 0)
</script>

<template>
  <section class="grid gap-6" data-testid="produkty-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ common.search }}</CardTitle>
        <CardDescription>{{ texts.searchPlaceholder }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3 md:grid-cols-[2fr_1fr_auto] md:items-center">
        <Input
          v-model="search"
          type="search"
          class="min-h-11"
          :aria-label="common.search"
          :placeholder="texts.searchPlaceholder"
          data-testid="products-search"
        />

        <select
          v-model="categoryId"
          class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
          :aria-label="texts.categoryLabel"
          data-testid="products-category-filter"
        >
          <option :value="null">{{ texts.allCategories }}</option>
          <option
            v-for="category in categories.data.value?.items ?? []"
            :key="category.id"
            :value="category.id"
          >
            {{ category.name }}
          </option>
        </select>

        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input
            v-model="includeArchived"
            type="checkbox"
            class="size-5"
            data-testid="products-include-archived"
          />
          {{ texts.showArchived }}
        </label>
      </CardContent>
    </Card>

    <div class="flex flex-wrap items-center justify-between gap-2">
      <!-- Relacja widocznych do wszystkich, nie samo `total`: ekran pisał
           „Produktów: 185" i renderował 50 (ustalenie R4, BATCH_19). -->
      <p class="text-muted-foreground text-sm tabular-nums" data-testid="products-total">
        Produktów: {{ listCount(products.loaded.value, products.total.value) }}
      </p>
      <Button as-child class="min-h-11">
        <RouterLink :to="{ name: 'produkt-nowy' }" data-testid="products-add">
          {{ texts.addProduct }}
        </RouterLink>
      </Button>
    </div>

    <p v-if="products.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>
    <p v-else-if="products.isError.value" class="text-destructive text-sm" role="alert">
      {{ common.unexpectedError }}
    </p>
    <p v-else-if="isEmpty" class="text-muted-foreground text-sm" data-testid="products-empty">
      {{ isSearching ? texts.emptySearch : texts.emptyState }}
    </p>

    <ul v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="products-list">
      <li
        v-for="product in items"
        :key="product.id"
        class="border-border bg-card grid gap-2 rounded-xl border p-4"
        :data-testid="`product-card-${product.id}`"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate font-medium">{{ product.name }}</p>
            <p class="text-muted-foreground truncate text-sm">{{ product.category_name }}</p>
          </div>

          <div class="flex shrink-0 flex-col items-end gap-1">
            <!-- Status zawsze kolor + tekst, nigdy sam kolor (06_UIUX §1). -->
            <span
              class="rounded-lg px-2 py-0.5 text-xs font-medium"
              :class="
                product.verification_status === 'verified'
                  ? 'bg-secondary/15 text-secondary'
                  : 'bg-warning/15 text-warning'
              "
              :data-testid="`product-status-${product.id}`"
            >
              {{ product.verification_status === 'verified' ? texts.verified : texts.unverified }}
            </span>
            <span
              v-if="product.is_archived"
              class="text-muted-foreground text-xs"
              :data-testid="`product-archived-${product.id}`"
            >
              {{ texts.archived }}
            </span>
          </div>
        </div>

        <p class="text-sm tabular-nums">
          {{ formatNutrient(product.nutrition.kcal_100, 'kcal') }}
          <span class="text-muted-foreground"
            >/ 100 {{ product.measure_kind === 'volume' ? 'ml' : 'g' }}</span
          >
        </p>

        <p
          v-if="!product.completeness.complete"
          class="text-warning text-xs"
          :title="product.completeness.missing.join(', ')"
          :data-testid="`product-incomplete-${product.id}`"
        >
          {{ texts.incompleteData }}
        </p>

        <Button as-child variant="outline" class="min-h-11 justify-self-start">
          <RouterLink
            :to="{ name: 'produkt-edycja', params: { id: product.id } }"
            :data-testid="`product-edit-${product.id}`"
          >
            {{ common.edit }}
          </RouterLink>
        </Button>
      </li>
    </ul>

    <LoadMoreButton
      :loaded="products.loaded.value"
      :total="products.total.value"
      :has-more="products.hasMore.value"
      :loading="products.isLoadingMore.value"
      :failed="products.loadMoreFailed.value"
      testid="products-load-more"
      @more="products.loadMore"
    />
  </section>
</template>
