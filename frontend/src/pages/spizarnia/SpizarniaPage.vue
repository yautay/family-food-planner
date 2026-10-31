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
import { usePaginatedList } from '@/api/pagination'
import type { PantryItem, PantrySort } from '@/api/pantry'
import {
  createPantryItem,
  deletePantryItem,
  fetchPantryItems,
  updatePantryItem,
} from '@/api/pantry'
import type { PantryFiltersKey } from '@/api/queryKeys'
import { queryKeys } from '@/api/queryKeys'
import AmountInput from '@/components/domain/AmountInput.vue'
import ActionPanel from '@/components/domain/ActionPanel.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import ExpiryBadge from '@/components/domain/ExpiryBadge.vue'
import LoadMoreButton from '@/components/domain/LoadMoreButton.vue'
import PantryItemCard from '@/components/domain/PantryItemCard.vue'
import PantryItemRow from '@/components/domain/PantryItemRow.vue'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { decimalsEqual } from '@/lib/decimal'
import { isoDate } from '@/lib/dates'
import { EXPIRY_SOON_DAYS } from '@/lib/expiry'
import { baseUnitFor, formatAmount } from '@/lib/format'
import { common, listCount, pantry as texts } from '@/lib/texts'
import { usePantryViewStore } from '@/stores/pantryView'

/**
 * Strona większa niż domyślne 50 (`api/pagination.PAGE_SIZE`) z powodu
 * domenowego: spiżarnia to jeden inwentarz domu, przeglądany „ile mam czego",
 * a nie przeszukiwany katalog. Zmniejszenie strony DOŁOŻYŁOBY kliknięć tam,
 * gdzie dziś ich nie ma (06_UIUX §2) — B19 dokłada dosięgalność reszty,
 * nie przestawia rozmiarów stron.
 */
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

// Filtry BEZ `offset` — numer strony niesie `pageParam` (src/api/pagination.ts).
const filters = computed<PantryFiltersKey>(() => ({
  limit: PAGE_SIZE,
  q: debouncedSearch.value.trim() || undefined,
  category_id: categoryId.value ?? undefined,
  sort: sort.value,
  expires_within_days: expiringOnly.value ? EXPIRY_SOON_DAYS : undefined,
}))

const pantry = usePaginatedList({
  queryKey: computed(() => queryKeys.pantry.list(filters.value)),
  fetchPage: (page) => fetchPantryItems({ ...filters.value, ...page }),
  pageSize: PAGE_SIZE,
})

const items = pantry.items
// Odrębny wycinek serwerowego filtra, nigdy licznik całej spiżarni.
const urgentFilters = {
  limit: 3,
  offset: 0,
  sort: 'expiry' as const,
  expires_within_days: EXPIRY_SOON_DAYS,
}
const urgent = useQuery({
  queryKey: queryKeys.pantry.list(urgentFilters),
  queryFn: () => fetchPantryItems(urgentFilters),
})
const urgentItems = computed(() =>
  (urgent.data.value?.items ?? []).filter((item) => !decimalsEqual(item.amount, '0')),
)
const savedMessage = ref('')
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
  savedMessage.value = ''
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
  savedMessage.value = ''
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
    savedMessage.value = 'Zapas zapisany.'
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
  <section class="grid min-w-0 gap-4" data-testid="spizarnia-page">
    <PageHeader
      :title="texts.title"
      description="Najpierw sprawdź to, co już masz w domu."
      decoration="wheat"
    >
      <template #actions
        ><Button data-testid="pantry-add" @click="openCreate()"
          >+ {{ texts.addItem }}</Button
        ></template
      >
    </PageHeader>
    <section
      class="border-warning/30 bg-warning/5 grid min-w-0 gap-3 rounded-xl border p-4"
      aria-labelledby="pantry-urgent-title"
      data-testid="pantry-use-first"
    >
      <h2 id="pantry-urgent-title" class="font-semibold">Wykorzystaj najpierw</h2>
      <p class="text-muted-foreground text-sm">
        Wycinek partii z zapisanym terminem do 7 dni, także po terminie. Sprawdź etykietę i stan
        produktu.
      </p>
      <p v-if="urgent.isPending.value" class="text-muted-foreground text-sm">
        {{ common.loading }}
      </p>
      <ErrorState
        v-else-if="urgent.isError.value && !urgent.data.value"
        compact
        message="Nie udało się pobrać partii z bliskim terminem."
        @retry="urgent.refetch()"
      />
      <template v-else>
        <p v-if="urgent.isError.value" role="alert" class="text-destructive text-sm">
          Nie udało się odświeżyć podglądu. Pokazujemy ostatnio pobrane dane.
        </p>
        <p v-if="!urgentItems.length" class="text-muted-foreground text-sm">
          {{
            urgent.data.value?.total === 0
              ? 'Brak partii w tym filtrze. Pozycje bez daty nie są nim objęte.'
              : 'W pobranym wycinku nie ma zapasów z dodatnią ilością. Sprawdź listę z filtrem terminu.'
          }}
        </p>
        <ul v-else class="grid min-w-0 gap-3">
          <li
            v-for="item in urgentItems"
            :key="item.id"
            class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"
            :data-testid="`pantry-urgent-${item.id}`"
          >
            <span
              class="w-full min-w-0 basis-full text-sm font-medium break-words sm:w-auto sm:flex-1 sm:basis-0"
              :data-testid="`pantry-urgent-name-${item.id}`"
              >{{ item.product_name }}</span
            >
            <span class="text-sm tabular-nums">{{
              formatAmount(item.amount, item.amount_unit)
            }}</span>
            <ExpiryBadge :expiry-date="item.expiry_date" :today="today" />
          </li>
        </ul>
      </template>
      <Button
        variant="outline"
        class="justify-self-start whitespace-normal text-left"
        data-testid="pantry-show-expiring"
        @click="expiringOnly = true"
        >Zastosuj filtr terminu do listy</Button
      >
    </section>

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
          data-testid="pantry-search"
        />

        <select
          v-model="categoryId"
          class="border-border bg-card min-h-11 min-w-0 flex-[1_1_14rem] rounded-lg border px-3 text-sm"
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
          class="border-border bg-card min-h-11 min-w-0 flex-[1_1_14rem] rounded-lg border px-3 text-sm"
          :aria-label="texts.sortLabel"
          data-testid="pantry-sort"
        >
          <option value="expiry">{{ texts.sortByExpiry }}</option>
          <option value="name">{{ texts.sortByName }}</option>
        </select>

        <label class="flex min-h-11 min-w-0 basis-full items-center gap-2 text-sm">
          <input
            v-model="expiringOnly"
            type="checkbox"
            class="size-5 shrink-0"
            data-testid="pantry-expiring-only"
          />
          {{ texts.expiringOnly }}
        </label>
      </CardContent>
    </Card>

    <div class="flex flex-wrap items-center justify-between gap-2">
      <!-- Relacja widocznych do wszystkich, nie samo `total` (ustalenie R4). -->
      <p class="text-muted-foreground text-sm tabular-nums" data-testid="pantry-total">
        {{ texts.itemsTotal }} {{ listCount(pantry.loaded.value, pantry.total.value) }}
      </p>

      <div class="flex flex-wrap items-center gap-2">
        <div class="flex gap-1" role="group" :aria-label="texts.viewLabel">
          <Button
            :variant="view.mode === 'grid' ? 'default' : 'outline'"
            class="min-h-11"
            :aria-pressed="view.mode === 'grid'"
            data-testid="pantry-view-grid"
            @click="view.setMode('grid')"
          >
            {{ texts.viewGrid }}
          </Button>
          <Button
            :variant="view.mode === 'list' ? 'default' : 'outline'"
            class="min-h-11"
            :aria-pressed="view.mode === 'list'"
            data-testid="pantry-view-list"
            @click="view.setMode('list')"
          >
            {{ texts.viewList }}
          </Button>
        </div>
      </div>
    </div>

    <ActionPanel
      :open="formOpen"
      :title="isEditing ? 'Zmień zapas' : texts.addItem"
      :submit-label="common.save"
      :submit-disabled="!formValid"
      :pending="save.isPending.value"
      :error="actionError"
      testid="pantry"
      @submit="save.mutate()"
      @close="formOpen = false"
    >
      <template #default="{ formId }">
        <div class="grid min-w-0 gap-4" data-testid="pantry-form">
          <!-- Edycja: produkt tylko do odczytu (zmiana produktu = inna pozycja). -->
          <p v-if="isEditing" class="text-sm break-words" data-testid="pantry-edited-product">
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
            :form="formId"
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
              :form="formId"
              data-testid="pantry-expiry-input"
            />
          </label>

          <p class="text-muted-foreground text-xs">
            Brak daty oznacza brak zapisanej informacji o terminie.
          </p>
          <label class="grid min-w-0 gap-1 text-sm">
            {{ texts.locationLabel }}
            <Input
              v-model="draft.location"
              list="pantry-location-hints"
              class="min-h-11"
              :placeholder="texts.locationHint"
              :form="formId"
              data-testid="pantry-location-input"
            />
            <datalist id="pantry-location-hints">
              <option v-for="hint in LOCATION_HINTS" :key="hint" :value="hint" />
            </datalist>
          </label>

          <label class="grid gap-1 text-sm">
            {{ texts.noteLabel }}
            <Input
              v-model="draft.note"
              class="min-h-11"
              :form="formId"
              data-testid="pantry-note-input"
            />
          </label>
        </div>
      </template>
    </ActionPanel>
    <p v-if="savedMessage" role="status" class="text-primary text-sm" data-testid="pantry-saved">
      {{ savedMessage }}
    </p>
    <p
      v-if="actionError && !formOpen"
      role="alert"
      class="text-destructive text-sm"
      data-testid="pantry-error"
    >
      {{ actionError }}
    </p>
    <ErrorState
      v-if="pantry.refreshFailed.value"
      compact
      message="Nie udało się odświeżyć zapasów. Pokazujemy ostatnio pobrane dane."
      @retry="pantry.refresh()"
    />

    <p v-if="pantry.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>
    <ErrorState
      v-else-if="pantry.isError.value"
      :message="common.unexpectedError"
      @retry="pantry.refresh()"
    />

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

    <LoadMoreButton
      :loaded="pantry.loaded.value"
      :total="pantry.total.value"
      :has-more="pantry.hasMore.value"
      :loading="pantry.isLoadingMore.value"
      :failed="pantry.loadMoreFailed.value"
      testid="pantry-load-more"
      @more="pantry.loadMore"
    />
  </section>
</template>
