<script setup lang="ts">
/**
 * Minimalny formularz nowego produktu — druga połowa wzorca create-in-context
 * (06_UIUX §3.1, 05_FRONTEND §4).
 *
 * Zasada: użytkownik jest w środku innego zadania (dodaje składnik do przepisu),
 * więc pytamy o absolutne minimum — nazwę, kategorię i sposób liczenia. Wartości
 * odżywcze uzupełni administrator, a produkt trafia do kolejki jako UNVERIFIED
 * (02_DOMAIN §4.9). Po zapisie emitujemy gotowy produkt i znikamy.
 *
 * Duplikat nazwy (409) nie jest tu porażką: backend odsyła w `details.existing`
 * produkt, który już jest w katalogu, więc proponujemy go wybrać zamiast
 * zostawiać użytkownika z komunikatem o błędzie.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import type { ProductDetail } from '@/api/catalog'
import { createProduct, fetchCategories, fetchProduct } from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { isValidDecimal, normalizeDecimalInput } from '@/lib/decimal'
import { common, products as texts, productPicker as pickerTexts } from '@/lib/texts'

const props = withDefaults(defineProps<{ open: boolean; prefillName?: string }>(), {
  prefillName: '',
})

const emit = defineEmits<{
  (event: 'created', product: ProductDetail): void
  (event: 'close'): void
}>()

const queryClient = useQueryClient()

const categories = useQuery({
  queryKey: queryKeys.categories.all,
  queryFn: fetchCategories,
  enabled: computed(() => props.open),
})

const name = ref(props.prefillName)
const categoryId = ref<number | null>(null)
const measureKind = ref<'mass' | 'volume' | 'piece'>('mass')
const pieceWeight = ref('')
const errorMessage = ref<string | null>(null)
/** Produkt zaproponowany przez backend przy 409 — „ten już jest, wziąć go?". */
const existingId = ref<number | null>(null)

watch(
  () => [props.open, props.prefillName] as const,
  ([open, prefill]) => {
    if (open) {
      name.value = prefill
      errorMessage.value = null
      existingId.value = null
    }
  },
  { immediate: true },
)

// Pierwsza kategoria jako sensowny domyślny wybór — jedno kliknięcie mniej
// (06_UIUX §2), a użytkownik i tak widzi pole i może je zmienić.
watch(
  () => categories.data.value,
  (data) => {
    const first = data?.items[0]
    if (categoryId.value === null && first) {
      categoryId.value = first.id
    }
  },
  { immediate: true },
)

const pieceWeightValid = computed(
  () =>
    measureKind.value !== 'piece' ||
    isValidDecimal(pieceWeight.value, { decimalPlaces: 2, positive: true }),
)
const canSubmit = computed(
  () => name.value.trim().length > 0 && categoryId.value !== null && pieceWeightValid.value,
)

const save = useMutation({
  mutationFn: () =>
    createProduct({
      name: name.value.trim(),
      category_id: categoryId.value as number,
      measure_kind: measureKind.value,
      piece_weight_g:
        measureKind.value === 'piece' ? normalizeDecimalInput(pieceWeight.value) : null,
    }),
  onSuccess: async (product) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.products.all })
    emit('created', product)
  },
  onError: (error: unknown) => {
    existingId.value = null
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      const existing = error.details.existing
      if (error.status === 409 && existing && typeof existing === 'object') {
        const id = (existing as { id?: unknown }).id
        if (typeof id === 'number') {
          existingId.value = id
        }
      }
      return
    }
    errorMessage.value = common.unexpectedError
  },
})

/** „Wybierz istniejący" — dociągamy pełny produkt, żeby emit miał ten sam kształt. */
const useExisting = useMutation({
  mutationFn: () => fetchProduct(existingId.value as number),
  onSuccess: (product) => emit('created', product),
  onError: () => {
    errorMessage.value = common.unexpectedError
  },
})
</script>

<template>
  <div
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-4 shadow-sm"
    role="dialog"
    aria-modal="false"
    :aria-label="pickerTexts.drawerTitle"
    data-testid="product-create-drawer"
  >
    <header class="grid gap-1">
      <h2 class="text-base font-semibold">{{ pickerTexts.drawerTitle }}</h2>
      <p class="text-muted-foreground text-sm">{{ pickerTexts.drawerHint }}</p>
    </header>

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="drawer-name">{{ texts.nameLabel }}</label>
      <Input id="drawer-name" v-model="name" class="min-h-11" data-testid="drawer-product-name" />
    </div>

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="drawer-category">{{ texts.categoryLabel }}</label>
      <select
        id="drawer-category"
        v-model="categoryId"
        class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
        data-testid="drawer-product-category"
      >
        <option
          v-for="category in categories.data.value?.items ?? []"
          :key="category.id"
          :value="category.id"
        >
          {{ category.name }}
        </option>
      </select>
    </div>

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="drawer-measure">{{ texts.measureKindLabel }}</label>
      <select
        id="drawer-measure"
        v-model="measureKind"
        class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
        data-testid="drawer-product-measure"
      >
        <option value="mass">{{ texts.measureMass }}</option>
        <option value="volume">{{ texts.measureVolume }}</option>
        <option value="piece">{{ texts.measurePiece }}</option>
      </select>
    </div>

    <div v-if="measureKind === 'piece'" class="grid gap-2">
      <label class="text-sm font-medium" for="drawer-piece-weight">
        {{ texts.pieceWeightLabel }}
      </label>
      <Input
        id="drawer-piece-weight"
        v-model="pieceWeight"
        inputmode="decimal"
        class="min-h-11 tabular-nums"
        :aria-invalid="!pieceWeightValid"
        data-testid="drawer-product-piece-weight"
      />
    </div>

    <div v-if="errorMessage" class="grid gap-2" role="alert" data-testid="drawer-error">
      <p class="text-destructive text-sm">{{ errorMessage }}</p>
      <Button
        v-if="existingId !== null"
        type="button"
        variant="outline"
        class="min-h-11 justify-self-start"
        data-testid="drawer-use-existing"
        @click="useExisting.mutate()"
      >
        Wybierz istniejący produkt
      </Button>
    </div>

    <div class="flex gap-2">
      <Button
        type="button"
        class="min-h-11"
        :disabled="!canSubmit || save.isPending.value"
        data-testid="drawer-submit"
        @click="save.mutate()"
      >
        {{ common.save }}
      </Button>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        data-testid="drawer-cancel"
        @click="emit('close')"
      >
        {{ common.cancel }}
      </Button>
    </div>
  </div>
</template>
