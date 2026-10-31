<script setup lang="ts">
/**
 * Wybór produktu z create-in-context — WZORZEC OBOWIĄZKOWY (05_FRONTEND §4,
 * 06_UIUX §3.1). Każde miejsce, w którym wybiera się produkt (składnik przepisu
 * B05, pozycja planu B06, spiżarnia B08, produkt sklepowy B09), używa TEGO
 * komponentu — nie własnego selecta.
 *
 * Pełny cykl bez opuszczania przerwanego zadania:
 *
 *     wpisz „cebul" → lista trafień (trigram, więc literówki też)
 *     → brak trafienia? `+ Dodaj produkt „cebula"` → drawer z minimum pól
 *     → zapis (UNVERIFIED) → auto-wybór → wracasz tam, gdzie byłeś.
 *
 * Klawiatura obsłużona wprost (↑/↓/Enter/Escape), bo bez niej wpisywanie
 * składników z klawiatury byłoby wolniejsze niż myszą.
 *
 * Komponent jest SAMODZIELNY: nie wie nic o stronie, na której stoi, a wynik
 * oddaje przez `selected`. Archiwalne produkty nie wchodzą do wyników
 * (ADR-012).
 */
import { useQuery } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { computed, ref, useId, watch } from 'vue'

import type { Product, ProductDetail } from '@/api/catalog'
import { fetchProducts } from '@/api/catalog'
import { queryKeys } from '@/api/queryKeys'
import ProductCreateDrawer from '@/components/domain/ProductCreateDrawer.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { common, productPicker as texts, products as productTexts } from '@/lib/texts'

const props = withDefaults(
  defineProps<{
    /** Aktualnie wybrany produkt (kontrolowany przez rodzica). */
    modelValue?: Product | ProductDetail | null
    label?: string
    /** Ile trafień pokazać — picker to skrót, nie przeglądarka katalogu. */
    limit?: number
    disabled?: boolean
    /** Opcjonalne ID pola; domyślnie unikalne także dla wielu składników. */
    inputId?: string
    /** Opóźnienie szukajki; testy komponentu podają 0, żeby nie czekać. */
    debounceMs?: number
  }>(),
  {
    modelValue: null,
    label: texts.label,
    limit: 8,
    disabled: false,
    inputId: undefined,
    debounceMs: 250,
  },
)
const generatedId = useId()
const inputId = computed(() => props.inputId ?? `product-picker-${generatedId}`)
const resultsId = computed(() => `${inputId.value}-results`)

const emit = defineEmits<{
  (event: 'update:modelValue', product: Product | ProductDetail | null): void
  (event: 'selected', product: Product | ProductDetail): void
}>()

const search = ref('')
/** Debounce chroni backend przed zapytaniem na każdy znak (06_UIUX §3.4). */
const debouncedSearch = refDebounced(search, props.debounceMs)
const open = ref(false)
const highlighted = ref(0)
const drawerOpen = ref(false)

const phrase = computed(() => debouncedSearch.value.trim())
const filters = computed(() => ({ limit: props.limit, offset: 0, q: phrase.value }))

const results = useQuery({
  queryKey: computed(() => queryKeys.products.list(filters.value)),
  queryFn: () => fetchProducts(filters.value),
  enabled: computed(() => open.value && phrase.value.length > 0),
})

const items = computed<Product[]>(() => results.data.value?.items ?? [])
const isSearching = computed(() => phrase.value.length > 0)
const hasResults = computed(() => items.value.length > 0)
/** Podpowiedź „dodaj" pokazujemy dopiero, gdy wiemy, że trafień nie ma. */
const canCreate = computed(
  () => isSearching.value && !hasResults.value && !results.isFetching.value,
)

watch(items, () => {
  highlighted.value = 0
})

function choose(product: Product | ProductDetail): void {
  emit('update:modelValue', product)
  emit('selected', product)
  search.value = ''
  open.value = false
  drawerOpen.value = false
}

function clear(): void {
  emit('update:modelValue', null)
  open.value = true
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    open.value = false
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (items.value.length === 0) {
      return
    }
    const step = event.key === 'ArrowDown' ? 1 : -1
    highlighted.value = (highlighted.value + step + items.value.length) % items.value.length
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    const product = items.value[highlighted.value]
    if (product) {
      choose(product)
    } else if (canCreate.value) {
      drawerOpen.value = true
    }
  }
}
</script>

<template>
  <div class="grid gap-2" data-testid="product-picker">
    <label class="text-sm font-medium" :for="inputId">{{ label }}</label>

    <!-- Stan „wybrany": pokazujemy wynik, a nie pole wyszukiwania — użytkownik
         ma widzieć, co wybrał, bez czytania pustego inputa. -->
    <div
      v-if="modelValue && !open"
      class="border-border flex min-h-11 items-center justify-between gap-2 rounded-lg border px-3"
      data-testid="picker-selected"
    >
      <span class="min-w-0 truncate text-sm">{{ modelValue.name }}</span>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :disabled="disabled"
        data-testid="picker-change"
        @click="clear()"
      >
        {{ texts.change }}
      </Button>
    </div>

    <template v-else>
      <Input
        :id="inputId"
        v-model="search"
        role="combobox"
        aria-expanded="true"
        :aria-controls="resultsId"
        :placeholder="texts.placeholder"
        :disabled="disabled"
        class="min-h-11"
        data-testid="picker-input"
        @focus="open = true"
        @keydown="onKeydown"
      />

      <ul
        v-if="isSearching"
        :id="resultsId"
        class="border-border grid gap-1 rounded-lg border p-1"
        role="listbox"
        data-testid="picker-results"
      >
        <li v-if="results.isPending.value" class="text-muted-foreground px-2 py-2 text-sm">
          {{ common.loading }}
        </li>

        <li
          v-for="(product, index) in items"
          :key="product.id"
          role="option"
          :aria-selected="index === highlighted"
        >
          <button
            type="button"
            class="hover:bg-muted flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-sm"
            :class="index === highlighted ? 'bg-muted' : ''"
            :data-testid="`picker-option-${product.id}`"
            @click="choose(product)"
          >
            <span class="min-w-0 truncate">{{ product.name }}</span>
            <span
              v-if="product.verification_status === 'unverified'"
              class="text-muted-foreground shrink-0 text-xs"
            >
              {{ productTexts.unverified }}
            </span>
          </button>
        </li>

        <li v-if="canCreate" class="grid gap-1">
          <p class="text-muted-foreground px-2 text-sm" data-testid="picker-empty">
            {{ texts.noResults }}
          </p>
          <button
            type="button"
            class="text-primary hover:bg-muted min-h-11 rounded-lg px-2 text-left text-sm font-medium"
            data-testid="picker-create"
            @click="drawerOpen = true"
          >
            {{ texts.createPrefix }} „{{ phrase }}”
          </button>
        </li>
      </ul>
    </template>

    <!-- Auto-wybór po zapisie i powrót do przerwanego flow (06_UIUX §3.1). -->
    <ProductCreateDrawer
      :open="drawerOpen"
      :prefill-name="phrase"
      @created="choose"
      @close="drawerOpen = false"
    />
  </div>
</template>
