<script setup lang="ts">
/**
 * Wiersz składnika w review importu — TRZY ścieżki mapowania (karta B16).
 *
 * 1. **Potwierdź propozycję** jednym kliknięciem (dopasowanie dokładne z B15
 *    albo propozycja AI z jej pewnością),
 * 2. **wybierz ProductPickerem** — tym samym komponentem, co wszędzie indziej
 *    (05_FRONTEND §4: własny select produktu = błąd review),
 * 3. **„+ Utwórz nowy"** — picker ma create-in-context wbudowany, więc trzecia
 *    ścieżka to po prostu jego drawer; flaga `create_new_product` zostaje dla
 *    ścieżki API-owej, gdy ktoś rozstrzyga import bez UI.
 *
 * Komponent NICZEGO nie zapisuje: emituje decyzję, a żądanie `resolve` składa
 * strona. Dzięki temu jedna akcja użytkownika to jedno żądanie, a nie kilka.
 */
import { computed } from 'vue'

import type { Product, ProductDetail } from '@/api/catalog'
import type { StagedIngredientRead } from '@/api/pdfImport'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import { Button } from '@/components/ui/button'
import { formatAmount } from '@/lib/format'
import { importReview as texts } from '@/lib/texts'

const props = defineProps<{
  ingredient: StagedIngredientRead
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'confirm', payload: { ingredientId: number; productId: number }): void
  (event: 'create-new', ingredientId: number): void
  (event: 'clear', ingredientId: number): void
}>()

const item = computed(() => props.ingredient)

/** Produkt wybrany — kształt, którego oczekuje `ProductPicker`. */
const selected = computed<Product | null>(() =>
  item.value.confirmed_product_id === null
    ? null
    : ({
        id: item.value.confirmed_product_id,
        name: item.value.confirmed_product_name ?? '',
      } as Product),
)

/** Propozycja do potwierdzenia jednym kliknięciem — tylko gdy nic nie wybrano. */
const suggestion = computed<{ id: number; name: string } | null>(() => {
  const productId = item.value.suggested_product_id
  if (item.value.confirmed_product_id !== null || productId === null || productId === undefined) {
    return null
  }
  return { id: productId, name: item.value.suggested_product_name ?? '' }
})

/** Skąd wzięła się propozycja — człowiek ma wiedzieć, czemu ufa (ADR-011). */
const matchLabel = computed(() => {
  if (item.value.match_kind === 'exact') return texts.matchExact
  if (item.value.match_kind === 'ai') return texts.matchAi
  if (item.value.match_kind === 'fuzzy') return texts.matchFuzzy
  return ''
})

/** Ilość tak, jak stała w dokumencie: „2 x Sztuka (210 g)" albo samo „200 g". */
const rawAmount = computed(() => {
  const grams = formatAmount(item.value.grams, 'g')
  if (item.value.raw_qty === null || !item.value.raw_unit) return grams
  return `${item.value.raw_qty} x ${item.value.raw_unit} (${grams})`
})

function onPicked(product: Product | ProductDetail | null): void {
  if (product === null) emit('clear', item.value.id)
  else emit('confirm', { ingredientId: item.value.id, productId: product.id })
}
</script>

<template>
  <li class="border-border grid gap-2 rounded-lg border p-3" data-testid="staged-ingredient">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <p class="font-medium" data-testid="staged-ingredient-name">{{ item.raw_name }}</p>
      <p class="text-muted-foreground text-sm" data-testid="staged-ingredient-amount">
        {{ rawAmount }}
      </p>
    </div>

    <p v-if="item.from_extras_section" class="text-muted-foreground text-xs">
      {{ texts.fromExtras }}
    </p>

    <p
      v-if="item.create_new_product"
      class="text-primary text-sm"
      data-testid="staged-ingredient-new"
    >
      {{ texts.createNewChosen }}
    </p>

    <div
      v-else-if="suggestion"
      class="flex flex-wrap items-center gap-2"
      data-testid="staged-ingredient-suggestion"
    >
      <span class="text-sm">{{ texts.suggestion }}: „{{ suggestion.name }}”</span>
      <span class="text-muted-foreground text-xs">
        {{ matchLabel
        }}<template v-if="item.confidence">
          · {{ texts.confidence }} {{ item.confidence }}</template
        >
      </span>
      <Button
        type="button"
        class="min-h-11"
        :disabled="disabled"
        :data-testid="`staged-ingredient-confirm-${item.id}`"
        @click="emit('confirm', { ingredientId: item.id, productId: suggestion.id })"
      >
        {{ texts.confirmSuggestion }}
      </Button>
    </div>

    <div class="grid gap-2 sm:flex sm:items-end sm:gap-3">
      <div class="min-w-0 grow">
        <ProductPicker
          :model-value="selected"
          :label="texts.mappedTo"
          :disabled="disabled"
          @update:model-value="onPicked"
        />
      </div>
      <Button
        v-if="!item.create_new_product && item.confirmed_product_id === null"
        type="button"
        variant="outline"
        class="min-h-11"
        :disabled="disabled"
        :data-testid="`staged-ingredient-create-new-${item.id}`"
        @click="emit('create-new', item.id)"
      >
        {{ texts.createNew }}
      </Button>
      <Button
        v-if="item.create_new_product || item.confirmed_product_id !== null"
        type="button"
        variant="outline"
        class="min-h-11"
        :disabled="disabled"
        :data-testid="`staged-ingredient-clear-${item.id}`"
        @click="emit('clear', item.id)"
      >
        {{ texts.clearMapping }}
      </Button>
    </div>
  </li>
</template>
