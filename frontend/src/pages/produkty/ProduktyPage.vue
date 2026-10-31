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
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchCategories, fetchProducts } from '@/api/catalog'
import { PAGE_SIZE, usePaginatedList } from '@/api/pagination'
import type { ProductsFilters } from '@/api/queryKeys'
import { queryKeys } from '@/api/queryKeys'
import PageHeader from '@/components/domain/PageHeader.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import ProductCompleteness from '@/components/domain/products/ProductCompleteness.vue'
import {
  MAX_AUTOMATIC_RESTORE_PAGES,
  productCatalogQuery,
} from '@/components/domain/products/catalogNavigation'
import LoadMoreButton from '@/components/domain/LoadMoreButton.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { formatNutrient } from '@/lib/format'
import { common, listCount, products as texts } from '@/lib/texts'

const route = useRoute()
const router = useRouter()
const initial = productCatalogQuery(route.query)
const search = ref(typeof initial.q === 'string' ? initial.q : '')
const debouncedSearch = refDebounced(search, 250)
const categoryId = ref<number | null>(initial.category ? Number(initial.category) : null)
const includeArchived = ref(initial.archived === '1')

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
const isSearching = computed(
  () =>
    debouncedSearch.value.trim().length > 0 || categoryId.value !== null || includeArchived.value,
)
const returnQuery = computed(() => ({
  // Link zachowuje wpisany szkic także przed upływem debounce zapytania API.
  q: search.value.trim() || undefined,
  category: categoryId.value?.toString(),
  archived: includeArchived.value ? '1' : undefined,
  pages: String(Math.max(1, Math.ceil(products.loaded.value / PAGE_SIZE))),
}))
watch([debouncedSearch, categoryId, includeArchived], () => {
  requestedPages.value = 1
  restoredFocus = true
  void router.replace({ query: { ...returnQuery.value, pages: undefined, focus: undefined } })
})
watch(
  () => route.query,
  (query) => {
    const selected = productCatalogQuery(query)
    search.value = typeof selected.q === 'string' ? selected.q : ''
    categoryId.value = selected.category ? Number(selected.category) : null
    includeArchived.value = selected.archived === '1'
  },
)
// Zachowujemy wszystkie strony cache. Zimny powrót automatycznie pobiera tylko
// ograniczony początek; dalsze strony pozostają dostępne przez Pokaż więcej.
const requestedPages = ref(Number(initial.pages ?? 1))
const automaticLoadsRemaining = ref(MAX_AUTOMATIC_RESTORE_PAGES - 1)
const loadedPages = computed(() => Math.ceil(products.loaded.value / PAGE_SIZE))
const restorationLimited = computed(
  () =>
    !products.isPending.value &&
    !products.isLoadingMore.value &&
    products.hasMore.value &&
    loadedPages.value < requestedPages.value &&
    (loadedPages.value >= MAX_AUTOMATIC_RESTORE_PAGES || automaticLoadsRemaining.value === 0),
)
let restoredFocus = false
watch(
  [products.loaded, products.isPending, products.isLoadingMore],
  async () => {
    if (
      products.isPending.value ||
      products.isLoadingMore.value ||
      products.isError.value ||
      products.loadMoreFailed.value
    )
      return
    if (
      loadedPages.value < Math.min(requestedPages.value, MAX_AUTOMATIC_RESTORE_PAGES) &&
      products.hasMore.value &&
      automaticLoadsRemaining.value > 0
    ) {
      // Osobny licznik chroni także przy nakładających się stronach i odsiewaniu ID.
      automaticLoadsRemaining.value -= 1
      products.loadMore()
      return
    }
    if (!restoredFocus && initial.focus) {
      await nextTick()
      if (typeof requestAnimationFrame === 'function') {
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      }
      const row = document.getElementById(`product-${initial.focus}`)
      if (row && !restoredFocus) {
        restoredFocus = true
        row.scrollIntoView?.({ block: 'center' })
        row.focus({ preventScroll: true })
      }
    }
  },
  { immediate: true },
)
function loadMore(): void {
  products.loadMore()
}
</script>

<template>
  <section class="grid min-w-0 gap-4" data-testid="produkty-page">
    <PageHeader
      title="Biblioteka produktów"
      description="Wspólny katalog składników i ich danych. Zmiany są widoczne dla wszystkich rodzin."
      decoration="wheat"
    />

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ common.search }}</CardTitle>
        <CardDescription>{{ texts.searchPlaceholder }}</CardDescription>
      </CardHeader>

      <CardContent class="flex min-w-0 flex-wrap items-center gap-3">
        <Input
          v-model="search"
          type="search"
          class="min-h-11 flex-[2_1_18rem]"
          :aria-label="common.search"
          :placeholder="texts.searchPlaceholder"
          maxlength="200"
          data-testid="products-search"
        />

        <select
          v-model="categoryId"
          class="border-border bg-card min-h-11 min-w-0 flex-[1_1_14rem] rounded-lg border px-3 text-sm"
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

        <label class="flex min-h-11 min-w-0 max-w-full items-center gap-2 text-sm">
          <input
            v-model="includeArchived"
            type="checkbox"
            class="size-5 shrink-0"
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
        <RouterLink :to="{ name: 'produkt-nowy', query: returnQuery }" data-testid="products-add">
          {{ texts.addProduct }}
        </RouterLink>
      </Button>
    </div>

    <p v-if="products.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>
    <ErrorState
      v-else-if="products.isError.value"
      :message="common.unexpectedError"
      @retry="products.refresh()"
    />
    <p v-else-if="isEmpty" class="text-muted-foreground text-sm" data-testid="products-empty">
      {{ isSearching ? texts.emptySearch : texts.emptyState }}
    </p>

    <ul v-else class="grid min-w-0 gap-0" data-testid="products-list">
      <li
        v-for="product in items"
        :id="`product-${product.id}`"
        :key="product.id"
        class="border-border grid min-w-0 gap-2 border-b py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center"
        tabindex="-1"
        :data-testid="`product-card-${product.id}`"
      >
        <div class="flex min-w-0 flex-wrap items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="font-medium break-words">{{ product.name }}</p>
            <p class="text-muted-foreground text-sm break-words">{{ product.category_name }}</p>
          </div>

          <div class="flex flex-wrap items-start gap-1">
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

        <p class="min-w-0 text-sm tabular-nums break-words">
          {{ formatNutrient(product.nutrition.kcal_100, 'kcal') }}
          <span class="text-muted-foreground"
            >/ 100 {{ product.measure_kind === 'volume' ? 'ml' : 'g' }}</span
          >
        </p>

        <ProductCompleteness
          v-if="!product.completeness.complete"
          :missing="product.completeness.missing"
          :testid="`product-incomplete-${product.id}`"
        />

        <Button
          as-child
          variant="outline"
          class="min-h-11 justify-self-start lg:col-start-2 lg:row-span-3 lg:row-start-1"
        >
          <RouterLink
            :to="{
              name: 'produkt-edycja',
              params: { id: product.id },
              query: { ...returnQuery, focus: String(product.id) },
            }"
            :data-testid="`product-edit-${product.id}`"
          >
            {{ common.edit }}
          </RouterLink>
        </Button>
      </li>
    </ul>

    <ErrorState
      v-if="products.refreshFailed.value"
      compact
      message="Nie udało się odświeżyć biblioteki. Pokazujemy ostatnio pobrane dane."
      @retry="products.refresh()"
    />
    <p
      v-if="restorationLimited"
      class="text-muted-foreground text-sm"
      role="status"
      data-testid="products-restore-limited"
    >
      Przywrócono część poprzednich wyników. Wybierz „Pokaż więcej”, aby wrócić do dalszych pozycji.
    </p>
    <LoadMoreButton
      :loaded="products.loaded.value"
      :total="products.total.value"
      :has-more="products.hasMore.value"
      :loading="products.isLoadingMore.value"
      :failed="products.loadMoreFailed.value"
      testid="products-load-more"
      @more="loadMore"
    />
  </section>
</template>
