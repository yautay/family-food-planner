<script setup lang="ts">
/**
 * Minimalny formularz produktu sklepowego — create-in-context (06_UIUX §3.1).
 *
 * **KONTRAKT dla BATCH_10/11** (preview zakupów używa tego komponentu bez zmian):
 *
 * ```
 * props:  { open: boolean, canonicalProductId: number, prefillName?: string }
 * emits:  created(retailProduct: RetailProduct)   // zapisany wariant
 *         close()                                 // użytkownik anulował
 * ```
 *
 * `open` steruje widocznością tak samo jak w `ProductCreateDrawer` (B04), więc
 * rodzic nie musi znać wnętrza. Poza `canonicalProductId` komponent nie
 * potrzebuje NICZEGO: sposób liczenia produktu dociąga sam
 * (`/products/{id}` — ten sam klucz TanStack Query, którego używa karta
 * produktu, więc w praktyce trafia w cache), a z niego wynika jednostka
 * opakowania. Dzięki temu B10 może otworzyć drawer, mając w ręku wyłącznie id
 * produktu z pozycji preview.
 *
 * Jednostka opakowania jest ZAWĘŻONA do osi produktu (g dla masy, ml dla
 * objętości, szt. dla sztuk): backend odrzuci każdą inną (422), więc pokazywanie
 * jej w wyborze byłoby zapraszaniem do błędu.
 *
 * Zdjęcie jest opcjonalne i zapisuje się PO utworzeniu wariantu — upload
 * potrzebuje id, a nie chcemy zmuszać użytkownika do dwóch kroków. Nieudane
 * zdjęcie nie unieważnia zapisanego wariantu: pokazujemy komunikat, wariant
 * zostaje.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import { fetchProduct } from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RetailProduct } from '@/api/retail'
import { createRetailProduct, uploadRetailPhoto } from '@/api/retail'
import type { Store } from '@/api/stores'
import AmountInput from '@/components/domain/AmountInput.vue'
import StorePicker from '@/components/domain/StorePicker.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { baseUnitFor } from '@/lib/format'
import { common, retail as texts } from '@/lib/texts'

const props = withDefaults(
  defineProps<{
    open: boolean
    canonicalProductId: number
    prefillName?: string
  }>(),
  { prefillName: '' },
)

const emit = defineEmits<{
  (event: 'created', retailProduct: RetailProduct): void
  (event: 'close'): void
}>()

const queryClient = useQueryClient()

const product = useQuery({
  queryKey: computed(() => queryKeys.products.detail(props.canonicalProductId)),
  queryFn: () => fetchProduct(props.canonicalProductId),
  enabled: computed(() => props.open && props.canonicalProductId > 0),
})

/** Oś opakowania wynika ze sposobu liczenia produktu kanonicznego (ADR-005). */
const packageUnit = computed(() => baseUnitFor(product.data.value?.measure_kind ?? 'mass'))
/**
 * Dopóki produkt się nie doczytał, `packageUnit` zwraca fallback („g"), więc
 * zapis wysłałby złą jednostkę dla produktu liczonego w ml albo w sztukach.
 * Backend odrzuciłby go 422-ką, a użytkownik zobaczyłby błąd, którego nie
 * popełnił — dlatego zapis CZEKA na odpowiedź, zamiast zgadywać oś.
 */
const productReady = computed(() => product.data.value !== undefined)
const unitLabel = computed(() => (packageUnit.value === 'piece' ? 'szt.' : packageUnit.value))

const name = ref(props.prefillName)
const brand = ref('')
const store = ref<Store | null>(null)
const amount = ref<string | null>(null)
const amountValid = ref(false)
const pieces = ref('')
const photo = ref<File | null>(null)
const errorMessage = ref<string | null>(null)

watch(
  () => [props.open, props.prefillName] as const,
  ([open, prefill]) => {
    if (!open) {
      return
    }
    // Reset przy każdym otwarciu: bez tego kolejny wariant startowałby z marką
    // i opakowaniem POPRZEDNIEGO (U10 z review R1 dla `ProductCreateDrawer`).
    name.value = prefill
    brand.value = ''
    store.value = null
    amount.value = null
    amountValid.value = false
    pieces.value = ''
    photo.value = null
    errorMessage.value = null
  },
  { immediate: true },
)

const piecesValid = computed(() => {
  const raw = pieces.value.trim()
  return raw === '' || /^\d+$/.test(raw)
})
const canSubmit = computed(
  () =>
    productReady.value && name.value.trim().length > 0 && amountValid.value && piecesValid.value,
)

function onPhotoChange(event: Event): void {
  const input = event.target as HTMLInputElement
  photo.value = input.files?.[0] ?? null
}

const save = useMutation({
  mutationFn: async (): Promise<RetailProduct> => {
    const created = await createRetailProduct({
      canonical_product_id: props.canonicalProductId,
      name: name.value.trim(),
      brand: brand.value.trim() || null,
      store_id: store.value?.id ?? null,
      package_amount: amount.value as string,
      package_unit: packageUnit.value,
      pieces_per_package: pieces.value.trim() === '' ? null : Number(pieces.value.trim()),
    })
    if (!photo.value) {
      return created
    }
    try {
      return await uploadRetailPhoto(created.id, photo.value)
    } catch (error) {
      // Wariant JEST zapisany — zdjęcie to dodatek, więc nie cofamy zapisu.
      errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
      return created
    }
  },
  onSuccess: async (created) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.retailProducts.all })
    emit('created', created)
  },
  onError: (error: unknown) => {
    errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})
</script>

<template>
  <div
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-4 shadow-sm"
    role="dialog"
    aria-modal="false"
    :aria-label="texts.drawerTitle"
    data-testid="retail-create-drawer"
  >
    <header class="grid gap-1">
      <h3 class="text-base font-semibold">{{ texts.drawerTitle }}</h3>
      <p class="text-muted-foreground text-sm">{{ texts.drawerHint }}</p>
    </header>

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="retail-name">{{ texts.nameLabel }}</label>
      <Input id="retail-name" v-model="name" class="min-h-11" data-testid="retail-name" />
      <p v-if="name.trim() === ''" class="text-destructive text-xs">{{ texts.nameRequired }}</p>
    </div>

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="retail-brand">{{ texts.brandLabel }}</label>
      <Input id="retail-brand" v-model="brand" class="min-h-11" data-testid="retail-brand" />
    </div>

    <StorePicker v-model="store" :label="texts.storeLabel" />

    <AmountInput
      v-model="amount"
      :label="`${texts.packageLabel} (${unitLabel})`"
      :units="[unitLabel]"
      :unit="unitLabel"
      :decimal-places="2"
      positive
      required
      testid="retail-amount"
      @update:valid="amountValid = $event"
    />

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="retail-pieces">{{ texts.piecesLabel }}</label>
      <Input
        id="retail-pieces"
        v-model="pieces"
        inputmode="numeric"
        class="min-h-11 tabular-nums"
        :aria-invalid="!piecesValid"
        data-testid="retail-pieces"
      />
      <p class="text-xs" :class="piecesValid ? 'text-muted-foreground' : 'text-destructive'">
        {{ piecesValid ? texts.piecesHint : texts.piecesInvalid }}
      </p>
    </div>

    <div class="grid gap-2">
      <label class="text-sm font-medium" for="retail-photo">{{ texts.photoLabel }}</label>
      <input
        id="retail-photo"
        type="file"
        accept="image/*"
        class="min-h-11 text-sm"
        data-testid="retail-photo"
        @change="onPhotoChange"
      />
      <p class="text-muted-foreground text-xs">{{ texts.photoHint }}</p>
    </div>

    <p
      v-if="errorMessage"
      class="text-destructive text-sm"
      role="alert"
      data-testid="retail-drawer-error"
    >
      {{ errorMessage }}
    </p>

    <div class="flex gap-2">
      <Button
        type="button"
        class="min-h-11"
        :disabled="!canSubmit || save.isPending.value"
        data-testid="retail-submit"
        @click="save.mutate()"
      >
        {{ common.save }}
      </Button>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        data-testid="retail-cancel"
        @click="emit('close')"
      >
        {{ common.cancel }}
      </Button>
    </div>
  </div>
</template>
