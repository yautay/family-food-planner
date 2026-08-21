<script setup lang="ts">
/**
 * Spiżarnia (`/spizarnia`, widok 6 wizualizacji).
 *
 * Stan serwera trzyma TanStack Query (ADR-007) — lista nie jest kopiowana do
 * żadnego ref-a. W Pinia siedzi wyłącznie preferencja widoku (kafelki/lista),
 * bo to stan UI, a nie dane.
 *
 * Formularz stoi na `ProductPicker` (create-in-context OBOWIĄZKOWY, 06_UIUX
 * §3.1): produktu, którego nie ma w katalogu, użytkownik dokłada bez opuszczania
 * spiżarni. Ilość podaje się na osi produktu (g/ml/szt.) — to samo, co przyjmuje
 * API; „1,5 kg" pokaże `formatAmount` przy odczycie, ale przeliczaniem jednostek
 * frontend się nie zajmuje (05_FRONTEND §7).
 *
 * Spiżarnia niczego od niczego nie odejmuje: to wyłącznie stan domowy
 * (02_DOMAIN §8). Odejmowanie przy generowaniu zakupów należy do BATCH_10.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { computed, reactive, ref } from 'vue'

import { fetchCategories } from '@/api/catalog'
import type { MeasureKind, Product, ProductDetail } from '@/api/catalog'
import { ApiError } from '@/api/client'
import type { PantryFilters, PantryItem, PantrySort } from '@/api/pantry'
import {
  createPantryItem,
  deletePantryItem,
  fetchPantryItems,
  updatePantryItem,
} from '@/api/pantry'
import { queryKeys } from '@/api/queryKeys'
import AmountInput from '@/components/domain/AmountInput.vue'
import PantryItemCard from '@/components/domain/PantryItemCard.vue'
import PantryItemRow from '@/components/domain/PantryItemRow.vue'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { isoDate } from '@/lib/dates'
import { EXPIRY_SOON_DAYS } from '@/lib/expiry'
import { baseUnitFor } from '@/lib/format'
import { common, pantry as texts } from '@/lib/texts'
import { usePantryViewStore } from '@/stores/pantryView'

const PAGE_SIZE = 100
/** Podpowiedzi lokalizacji — słownika nie ma, to wolny tekst (karta B08). */
const LOCATION_HINTS = ['szafka', 'lodówka', 'zamrażarka', 'piwnica'] as const

const queryClient = useQueryClient()
const view = usePantryViewStore()

/** „Dziś" liczone RAZ na render listy — inaczej każdy kafelek pytałby o zegar. */
const today = isoDate(new Date())

const search = ref('')
const debouncedSearch = refDebounced(search, 250)
const categoryId = ref<number | null>(null)
const sort = ref<PantrySort>('expiry')
const expiringOnly = ref(false)

const categories = useQuery({ queryKey: queryKeys.categories.all, queryFn: fetchCategories })

const filters = computed<PantryFilters>(() => ({
  limit: PAGE_SIZE,
  offset: 0,
  q: debouncedSearch.value.trim() || undefined,
  category_id: categoryId.value ?? undefined,
  sort: sort.value,
  expires_within_days: expiringOnly.value ? EXPIRY_SOON_DAYS : undefined,
}))

const pantry = useQuery({
  queryKey: computed(() => queryKeys.pantry.list(filters.value)),
  queryFn: () => fetchPantryItems(filters.value),
})

const items = computed(() => pantry.data.value?.items ?? [])
const isEmpty = computed(() => !pantry.isPending.value && items.value.length === 0)
const isFiltering = computed(
  () => debouncedSearch.value.trim().length > 0 || categoryId.value !== null || expiringOnly.value,
)

const actionError = ref<string | null>(null)

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.pantry.all })
}

// --- formularz dodania / edycji ------------------------------------------------

/**
 * `id: null` = dodawanie nowej pozycji; liczba = edycja istniejącej.
 *
 * Przy edycji produktu się NIE zmienia (inny produkt = inna pozycja), więc
 * zamiast wyłączonego pickera pokazujemy nazwę z pozycji. Dzięki temu nie
 * musimy udawać, że mamy pełny obiekt `Product` — mielibyśmy tylko trzy pola
 * z `PantryItemRead`, a rzutowanie ich na typ z `generated.ts` byłoby
 * kłamstwem, którego TypeScript już by nie sprawdził.
 */
const draft = reactive({
  id: null as number | null,
  product: null as Product | ProductDetail | null,
  editedProduct: null as { name: string; measureKind: MeasureKind } | null,
  amount: null as string | null,
  amountValid: true,
  expiryDate: '',
  location: '',
  note: '',
})
const formOpen = ref(false)

/** Jednostka wynika z produktu (ADR-005) — użytkownik jej nie wybiera. */
const draftUnit = computed(() => {
  const measureKind = draft.editedProduct?.measureKind ?? draft.product?.measure_kind
  return measureKind === undefined ? 'g' : baseUnitFor(measureKind)
})
const unitLabel = computed(() => (draftUnit.value === 'piece' ? 'szt.' : draftUnit.value))

const isEditing = computed(() => draft.id !== null)

const formValid = computed(
  () => (isEditing.value || draft.product !== null) && draft.amount !== null && draft.amountValid,
)

function openCreate(): void {
  draft.id = null
  draft.product = null
  draft.editedProduct = null
  draft.amount = null
  draft.amountValid = true
  draft.expiryDate = ''
  draft.location = ''
  draft.note = ''
  actionError.value = null
  formOpen.value = true
}

function openEdit(item: PantryItem): void {
  draft.id = item.id
  draft.product = null
  draft.editedProduct =
    item.product_name === null || item.measure_kind === null
      ? null
      : { name: item.product_name, measureKind: item.measure_kind }
  draft.amount = item.amount
  draft.amountValid = true
  draft.expiryDate = item.expiry_date ?? ''
  draft.location = item.location ?? ''
  draft.note = item.note
  actionError.value = null
  formOpen.value = true
}

const save = useMutation({
  mutationFn: () => {
    const shared = {
      amount: draft.amount ?? '0',
      expiry_date: draft.expiryDate.trim() === '' ? null : draft.expiryDate,
      location: draft.location.trim() === '' ? null : draft.location.trim(),
      note: draft.note.trim(),
    }
    if (draft.id !== null) {
      return updatePantryItem(draft.id, shared)
    }
    return createPantryItem({ ...shared, product_id: draft.product?.id ?? 0 })
  },
  onSuccess: async () => {
    actionError.value = null
    formOpen.value = false
    await refresh()
  },
  onError: reportError,
})

const zero = useMutation({
  mutationFn: (item: PantryItem) => updatePantryItem(item.id, { amount: '0' }),
  onSuccess: refresh,
  onError: reportError,
})

const remove = useMutation({
  mutationFn: (item: PantryItem) => deletePantryItem(item.id),
  onSuccess: refresh,
  onError: reportError,
})

/** Destrukcja bezpieczna (06_UIUX §3.3): usunięcie zawsze za potwierdzeniem. */
function confirmRemove(item: PantryItem): void {
  if (window.confirm(texts.confirmDelete)) {
    remove.mutate(item)
  }
}
</script>

<template>
  <section class="grid gap-6" data-testid="spizarnia-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ common.search }}</CardTitle>
        <CardDescription>{{ texts.searchPlaceholder }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3 md:grid-cols-[2fr_1fr_1fr] md:items-center">
        <Input
          v-model="search"
          type="search"
          class="min-h-11"
          :aria-label="common.search"
          :placeholder="texts.searchPlaceholder"
          data-testid="pantry-search"
        />

        <select
          v-model="categoryId"
          class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
          :aria-label="texts.categoryLabel"
          data-testid="pantry-category-filter"
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

        <select
          v-model="sort"
          class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
          :aria-label="texts.sortLabel"
          data-testid="pantry-sort"
        >
          <option value="expiry">{{ texts.sortByExpiry }}</option>
          <option value="name">{{ texts.sortByName }}</option>
        </select>

        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input
            v-model="expiringOnly"
            type="checkbox"
            class="size-5"
            data-testid="pantry-expiring-only"
          />
          {{ texts.expiringOnly }}
        </label>
      </CardContent>
    </Card>

    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-muted-foreground text-sm tabular-nums" data-testid="pantry-total">
        {{ texts.itemsTotal }} {{ pantry.data.value?.total ?? 0 }}
      </p>

      <div class="flex flex-wrap items-center gap-2">
        <div class="flex gap-1" role="group" :aria-label="texts.viewLabel">
          <Button
            :variant="view.mode === 'grid' ? 'default' : 'outline'"
            class="min-h-11"
            data-testid="pantry-view-grid"
            @click="view.setMode('grid')"
          >
            {{ texts.viewGrid }}
          </Button>
          <Button
            :variant="view.mode === 'list' ? 'default' : 'outline'"
            class="min-h-11"
            data-testid="pantry-view-list"
            @click="view.setMode('list')"
          >
            {{ texts.viewList }}
          </Button>
        </div>

        <Button class="min-h-11" data-testid="pantry-add" @click="openCreate()">
          + {{ texts.addItem }}
        </Button>
      </div>
    </div>

    <Card v-if="formOpen" class="rounded-xl" data-testid="pantry-form">
      <CardHeader>
        <CardTitle>{{ isEditing ? common.edit : texts.addItem }}</CardTitle>
      </CardHeader>

      <CardContent class="grid gap-4">
        <!-- Edycja: produkt tylko do odczytu (zmiana produktu = inna pozycja). -->
        <p v-if="isEditing" class="text-sm" data-testid="pantry-edited-product">
          <span class="text-muted-foreground">{{ texts.productLabel }}:</span>
          {{ draft.editedProduct?.name ?? '—' }}
        </p>
        <ProductPicker v-else v-model="draft.product" :label="texts.productLabel" />

        <AmountInput
          v-model="draft.amount"
          :label="`${texts.amountLabel} (${unitLabel})`"
          :decimal-places="3"
          :positive="false"
          required
          testid="pantry-amount"
          :hint="texts.amountRequired"
          @update:valid="draft.amountValid = $event"
        />

        <label class="grid gap-1 text-sm">
          {{ texts.expiryLabel }}
          <Input
            v-model="draft.expiryDate"
            type="date"
            class="min-h-11"
            data-testid="pantry-expiry-input"
          />
        </label>

        <label class="grid gap-1 text-sm">
          {{ texts.locationLabel }}
          <Input
            v-model="draft.location"
            list="pantry-location-hints"
            class="min-h-11"
            :placeholder="texts.locationHint"
            data-testid="pantry-location-input"
          />
          <datalist id="pantry-location-hints">
            <option v-for="hint in LOCATION_HINTS" :key="hint" :value="hint" />
          </datalist>
        </label>

        <label class="grid gap-1 text-sm">
          {{ texts.noteLabel }}
          <Input v-model="draft.note" class="min-h-11" data-testid="pantry-note-input" />
        </label>

        <div class="flex flex-wrap gap-2">
          <Button
            class="min-h-11"
            :disabled="!formValid || save.isPending.value"
            data-testid="pantry-submit"
            @click="save.mutate()"
          >
            {{ save.isPending.value ? common.loading : common.save }}
          </Button>
          <Button
            variant="outline"
            class="min-h-11"
            data-testid="pantry-cancel"
            @click="formOpen = false"
          >
            {{ common.cancel }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <p v-if="actionError" class="text-destructive text-sm" role="alert" data-testid="pantry-error">
      {{ actionError }}
    </p>

    <p v-if="pantry.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>
    <p v-else-if="pantry.isError.value" class="text-destructive text-sm" role="alert">
      {{ common.unexpectedError }}
    </p>

    <!-- Pusty stan uczy: jedno zdanie + akcja główna (06_UIUX §3.2). -->
    <div v-else-if="isEmpty" class="grid justify-items-start gap-3" data-testid="pantry-empty">
      <p class="text-muted-foreground text-sm">
        {{ isFiltering ? texts.emptySearch : texts.emptyState }}
      </p>
      <Button
        v-if="!isFiltering"
        class="min-h-11"
        data-testid="pantry-add-first"
        @click="openCreate()"
      >
        {{ texts.addFirstItem }}
      </Button>
    </div>

    <ul
      v-else-if="view.mode === 'grid'"
      class="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
      data-testid="pantry-list"
    >
      <PantryItemCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :today="today"
        @edit="openEdit"
        @zero="zero.mutate"
        @remove="confirmRemove"
      />
    </ul>

    <ul v-else class="grid gap-2" data-testid="pantry-list">
      <PantryItemRow
        v-for="item in items"
        :key="item.id"
        :item="item"
        :today="today"
        @edit="openEdit"
        @zero="zero.mutate"
        @remove="confirmRemove"
      />
    </ul>
  </section>
</template>
