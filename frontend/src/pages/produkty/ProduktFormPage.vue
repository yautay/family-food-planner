<script setup lang="ts">
/**
 * Formularz produktu (`/produkty/nowy`, `/produkty/:id/edytuj`) — widok 8
 * z 06_UIUX §4.
 *
 * Trzy sekcje o różnych właścicielach:
 *
 * 1. **Opis** (nazwa, kategoria, sposób liczenia, waga sztuki, trwałość) —
 *    edytuje każdy zalogowany, bo katalog jest wspólny (02_DOMAIN §3.1 pkt 3).
 * 2. **Wartości odżywcze** — wyłącznie ADMIN (08_TESTING §4). USER widzi je
 *    jako tekst; blokada w UI to wygoda, prawdą jest 403 z backendu.
 * 3. **Przeliczniki jednostek domowych** — każdy; bez nich nie da się zapisać
 *    ilości typu „2 łyżki" (ADR-005).
 *
 * Usuwanie jest ścieżką administratora i tylko dla produktu nieużywanego (D13);
 * przy 409 pokazujemy listę „Używane w:" i proponujemy archiwizację —
 * odwracalną alternatywę (ADR-012, 06_UIUX §3.3).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { ProductDetail, UnitWeight } from '@/api/catalog'
import {
  createProduct,
  createUnitWeight,
  deleteProduct,
  deleteUnitWeight,
  fetchCategories,
  fetchProduct,
  setProductArchived,
  setProductNutrition,
  updateProduct,
} from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { toDecimalInput } from '@/lib/decimal'
import { formatAmount, formatNutrient } from '@/lib/format'
import type { NutritionFormValues, ProductFormValues } from '@/lib/schemas/product'
import {
  nutritionFormSchema,
  productFormSchema,
  toApiDecimal,
  toApiText,
  unitWeightFormSchema,
} from '@/lib/schemas/product'
import { common, products as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

interface UsedIn {
  type: string
  id: number
  name: string
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const queryClient = useQueryClient()

const productId = computed(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? Number(raw) : null
})
const isEdit = computed(() => productId.value !== null)

const categories = useQuery({ queryKey: queryKeys.categories.all, queryFn: fetchCategories })

const product = useQuery({
  queryKey: computed(() => queryKeys.products.detail(productId.value ?? 0)),
  queryFn: () => fetchProduct(productId.value as number),
  enabled: computed(() => isEdit.value),
})

const detail = computed<ProductDetail | null>(() => product.data.value ?? null)

const actionError = ref<string | null>(null)
const usedIn = ref<UsedIn[]>([])

function reportError(error: unknown): void {
  usedIn.value = []
  if (error instanceof ApiError) {
    actionError.value = error.message
    const details = error.details.used_in
    if (Array.isArray(details)) {
      usedIn.value = details as UsedIn[]
    }
    return
  }
  actionError.value = common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.products.all })
}

// --- sekcja opisowa --------------------------------------------------------------

const {
  errors: productErrors,
  values: productValues,
  defineField: defineProductField,
  handleSubmit: handleProductSubmit,
  setValues: setProductValues,
  setFieldValue: setProductField,
} = useForm({
  validationSchema: toTypedSchema(productFormSchema),
  initialValues: {
    name: '',
    category_id: 0,
    measure_kind: 'mass',
    piece_weight_g: '',
    perishability_override: '',
  },
})

const [name] = defineProductField('name')
const [categoryId] = defineProductField('category_id')
const [measureKind] = defineProductField('measure_kind')
const [pieceWeight] = defineProductField('piece_weight_g')
const [perishabilityOverride] = defineProductField('perishability_override')

// --- sekcja wartości odżywczych (ADMIN) ---------------------------------------------

const {
  errors: nutritionErrors,
  defineField: defineNutritionField,
  handleSubmit: handleNutritionSubmit,
  setValues: setNutritionValues,
} = useForm({
  validationSchema: toTypedSchema(nutritionFormSchema),
  initialValues: {
    kcal_100: '',
    protein_100: '',
    fat_100: '',
    carbs_100: '',
    fiber_100: '',
    sugars_100: '',
    glycemic_index: '',
    nutrition_source: '',
  },
})

const [kcal] = defineNutritionField('kcal_100')
const [protein] = defineNutritionField('protein_100')
const [fat] = defineNutritionField('fat_100')
const [carbs] = defineNutritionField('carbs_100')
const [fiber] = defineNutritionField('fiber_100')
const [sugars] = defineNutritionField('sugars_100')
const [glycemicIndex] = defineNutritionField('glycemic_index')
const [nutritionSource] = defineNutritionField('nutrition_source')

/** Pierwsza kategoria jako domyślna — jedno kliknięcie mniej (06_UIUX §2). */
watch(
  () => categories.data.value,
  (data) => {
    const first = data?.items[0]
    if (!isEdit.value && productValues.category_id === 0 && first) {
      setProductField('category_id', first.id)
    }
  },
  { immediate: true },
)

watch(
  detail,
  (data) => {
    if (!data) {
      return
    }
    setProductValues({
      name: data.name,
      category_id: data.category_id,
      measure_kind: data.measure_kind,
      piece_weight_g: toDecimalInput(data.piece_weight_g),
      perishability_override: data.perishability_override ?? '',
    })
    setNutritionValues({
      kcal_100: toDecimalInput(data.nutrition.kcal_100),
      protein_100: toDecimalInput(data.nutrition.protein_100),
      fat_100: toDecimalInput(data.nutrition.fat_100),
      carbs_100: toDecimalInput(data.nutrition.carbs_100),
      fiber_100: toDecimalInput(data.nutrition.fiber_100),
      sugars_100: toDecimalInput(data.nutrition.sugars_100),
      glycemic_index: toDecimalInput(data.nutrition.glycemic_index),
      nutrition_source: data.nutrition.nutrition_source ?? '',
    })
  },
  { immediate: true },
)

const saveProduct = useMutation({
  // Wartości przychodzą z `handleSubmit`, czyli PO walidacji zod — dzięki temu
  // nie trzeba tu żadnych `as` ani domyślnych wartości „na wszelki wypadek".
  mutationFn: (values: ProductFormValues): Promise<ProductDetail> => {
    const payload = {
      name: values.name.trim(),
      category_id: values.category_id,
      measure_kind: values.measure_kind,
      piece_weight_g: values.measure_kind === 'piece' ? toApiDecimal(values.piece_weight_g) : null,
      perishability_override:
        values.perishability_override === '' ? null : values.perishability_override,
    }
    return isEdit.value ? updateProduct(productId.value as number, payload) : createProduct(payload)
  },
  onSuccess: async (saved) => {
    actionError.value = null
    await refresh()
    if (!isEdit.value) {
      // Po utworzeniu zostajemy w edycji TEGO produktu: dopiero tu są sekcje
      // wartości i przeliczników, które wymagają istniejącego id.
      await router.replace({ name: 'produkt-edycja', params: { id: saved.id } })
    }
  },
  onError: reportError,
})

const onSubmit = handleProductSubmit((values) => {
  saveProduct.mutate(values)
})

const saveNutrition = useMutation({
  mutationFn: (values: NutritionFormValues) =>
    setProductNutrition(productId.value as number, {
      kcal_100: toApiDecimal(values.kcal_100),
      protein_100: toApiDecimal(values.protein_100),
      fat_100: toApiDecimal(values.fat_100),
      carbs_100: toApiDecimal(values.carbs_100),
      fiber_100: toApiDecimal(values.fiber_100),
      sugars_100: toApiDecimal(values.sugars_100),
      glycemic_index: toApiDecimal(values.glycemic_index),
      nutrition_source: toApiText(values.nutrition_source),
    }),
  onSuccess: async () => {
    actionError.value = null
    await refresh()
  },
  onError: reportError,
})

const onSubmitNutrition = handleNutritionSubmit((values) => {
  saveNutrition.mutate(values)
})

// --- przeliczniki jednostek domowych ---------------------------------------------------

const unitDraft = ref({ unit_label: '', grams_per_unit: '', source: '' })
const unitDraftCheck = computed(() => unitWeightFormSchema.safeParse(unitDraft.value))
const unitDraftValid = computed(() => unitDraftCheck.value.success)
const unitDraftError = computed(() =>
  unitDraftCheck.value.success ? null : unitDraftCheck.value.error.issues[0]?.message,
)

const addUnitWeight = useMutation({
  mutationFn: () =>
    createUnitWeight(productId.value as number, {
      unit_label: unitDraft.value.unit_label.trim(),
      grams_per_unit: toApiDecimal(unitDraft.value.grams_per_unit) ?? '0',
      source: toApiText(unitDraft.value.source),
      // Ręcznie wpisany przelicznik to jedna próbka; importer (B15/16) podbije
      // licznik, gdy nauczy się gramatury z wielu wystąpień (01_PDF_AUDIT §5.2).
      samples_count: 1,
    }),
  onSuccess: async () => {
    unitDraft.value = { unit_label: '', grams_per_unit: '', source: '' }
    actionError.value = null
    await refresh()
  },
  onError: reportError,
})

const removeUnitWeight = useMutation({
  mutationFn: (weight: UnitWeight) => deleteUnitWeight(productId.value as number, weight.id),
  onSuccess: refresh,
  onError: reportError,
})

// --- archiwizacja i usuwanie -------------------------------------------------------------

const toggleArchive = useMutation({
  mutationFn: (archived: boolean) => setProductArchived(productId.value as number, archived),
  onSuccess: async () => {
    actionError.value = null
    usedIn.value = []
    await refresh()
  },
  onError: reportError,
})

const remove = useMutation({
  mutationFn: () => deleteProduct(productId.value as number),
  onSuccess: async () => {
    await refresh()
    await router.push({ name: 'produkty' })
  },
  onError: reportError,
})

function confirmRemove(): void {
  if (window.confirm(texts.confirmDelete)) {
    remove.mutate()
  }
}

const basisUnit = computed(() => (productValues.measure_kind === 'volume' ? 'ml' : 'g'))
</script>

<template>
  <section class="grid gap-6" data-testid="produkt-form-page">
    <header class="grid gap-2">
      <h1 class="text-2xl font-semibold">{{ isEdit ? texts.editTitle : texts.createTitle }}</h1>
      <Button
        as="router-link"
        :to="{ name: 'produkty' }"
        variant="ghost"
        class="min-h-11 justify-self-start"
        data-testid="product-back"
      >
        {{ texts.backToList }}
      </Button>
    </header>

    <div v-if="actionError" class="grid gap-2" role="alert" data-testid="product-error">
      <p class="text-destructive text-sm">{{ actionError }}</p>
      <template v-if="usedIn.length">
        <p class="text-destructive text-sm font-medium">{{ texts.usedInIntro }}</p>
        <ul class="text-destructive text-sm" data-testid="product-used-in">
          <li v-for="entry in usedIn" :key="`${entry.type}-${entry.id}`">· {{ entry.name }}</li>
        </ul>
        <Button
          type="button"
          variant="outline"
          class="min-h-11 justify-self-start"
          data-testid="product-archive-instead"
          @click="toggleArchive.mutate(true)"
        >
          {{ texts.archiveInstead }}
        </Button>
      </template>
    </div>

    <!-- Sekcja opisowa -->
    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.title }}</CardTitle>
        <CardDescription v-if="detail" data-testid="product-status">
          {{ detail.verification_status === 'verified' ? texts.verified : texts.unverified }}
          <template v-if="detail.is_archived"> · {{ texts.archived }}</template>
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form
          class="grid gap-4 md:grid-cols-2"
          novalidate
          data-testid="product-form"
          @submit="onSubmit"
        >
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="product-name">{{ texts.nameLabel }}</label>
            <Input
              id="product-name"
              v-model="name"
              class="min-h-11"
              :aria-invalid="Boolean(productErrors.name)"
              data-testid="product-name"
            />
            <p
              v-if="productErrors.name"
              class="text-destructive text-sm"
              data-testid="product-name-error"
            >
              {{ productErrors.name }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="product-category">
              {{ texts.categoryLabel }}
            </label>
            <select
              id="product-category"
              v-model="categoryId"
              class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
              data-testid="product-category"
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
            <label class="text-sm font-medium" for="product-measure">
              {{ texts.measureKindLabel }}
            </label>
            <select
              id="product-measure"
              v-model="measureKind"
              class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
              data-testid="product-measure"
            >
              <option value="mass">{{ texts.measureMass }}</option>
              <option value="volume">{{ texts.measureVolume }}</option>
              <option value="piece">{{ texts.measurePiece }}</option>
            </select>
          </div>

          <div v-if="measureKind === 'piece'" class="grid gap-2">
            <label class="text-sm font-medium" for="product-piece-weight">
              {{ texts.pieceWeightLabel }}
            </label>
            <Input
              id="product-piece-weight"
              v-model="pieceWeight"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(productErrors.piece_weight_g)"
              data-testid="product-piece-weight"
            />
            <p
              v-if="productErrors.piece_weight_g"
              class="text-destructive text-sm"
              data-testid="product-piece-weight-error"
            >
              {{ productErrors.piece_weight_g }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="product-perishability">
              {{ texts.perishabilityLabel }}
            </label>
            <select
              id="product-perishability"
              v-model="perishabilityOverride"
              class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
              data-testid="product-perishability"
            >
              <option value="">{{ texts.perishabilityFromCategory }}</option>
              <option value="fresh">{{ texts.perishabilityFresh }}</option>
              <option value="durable">{{ texts.perishabilityDurable }}</option>
            </select>
          </div>

          <div class="flex flex-wrap gap-2 md:col-span-2">
            <Button
              type="submit"
              class="min-h-11"
              :disabled="saveProduct.isPending.value"
              data-testid="product-submit"
            >
              {{ common.save }}
            </Button>
            <Button
              v-if="detail"
              type="button"
              variant="outline"
              class="min-h-11"
              :disabled="toggleArchive.isPending.value"
              data-testid="product-archive"
              @click="toggleArchive.mutate(!detail.is_archived)"
            >
              {{ detail.is_archived ? texts.restore : texts.archive }}
            </Button>
            <Button
              v-if="detail && auth.isAdmin"
              type="button"
              variant="ghost"
              class="min-h-11"
              :disabled="remove.isPending.value"
              data-testid="product-delete"
              @click="confirmRemove()"
            >
              {{ common.remove }}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <!-- Wartości odżywcze -->
    <Card v-if="detail" class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.nutritionTitle }} {{ basisUnit }}</CardTitle>
        <CardDescription v-if="!auth.isAdmin">{{ texts.nutritionAdminOnly }}</CardDescription>
        <CardDescription
          v-else-if="!detail.completeness.complete"
          class="text-warning"
          data-testid="nutrition-incomplete"
        >
          {{ texts.incompleteData }}: {{ detail.completeness.missing.join(', ') }}
        </CardDescription>
      </CardHeader>

      <CardContent>
        <!-- USER widzi wartości, ale ich nie zmienia (08_TESTING §4). -->
        <dl v-if="!auth.isAdmin" class="grid gap-3 md:grid-cols-3" data-testid="nutrition-readonly">
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.kcalLabel }}</dt>
            <dd class="text-sm tabular-nums">
              {{ formatNutrient(detail.nutrition.kcal_100, 'kcal') }}
            </dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.proteinLabel }}</dt>
            <dd class="text-sm tabular-nums">{{ formatNutrient(detail.nutrition.protein_100) }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.fatLabel }}</dt>
            <dd class="text-sm tabular-nums">{{ formatNutrient(detail.nutrition.fat_100) }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.carbsLabel }}</dt>
            <dd class="text-sm tabular-nums">{{ formatNutrient(detail.nutrition.carbs_100) }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.fiberLabel }}</dt>
            <dd class="text-sm tabular-nums">{{ formatNutrient(detail.nutrition.fiber_100) }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.sugarsLabel }}</dt>
            <dd class="text-sm tabular-nums">{{ formatNutrient(detail.nutrition.sugars_100) }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground text-sm">{{ texts.glycemicIndexLabel }}</dt>
            <dd class="text-sm tabular-nums">
              {{ formatNutrient(detail.nutrition.glycemic_index, '') }}
            </dd>
          </div>
        </dl>

        <form
          v-else
          class="grid gap-4 md:grid-cols-3"
          novalidate
          data-testid="nutrition-form"
          @submit="onSubmitNutrition"
        >
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-kcal">{{ texts.kcalLabel }}</label>
            <Input
              id="nutrition-kcal"
              v-model="kcal"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(nutritionErrors.kcal_100)"
              data-testid="nutrition-kcal"
            />
            <p v-if="nutritionErrors.kcal_100" class="text-destructive text-sm">
              {{ nutritionErrors.kcal_100 }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-protein">
              {{ texts.proteinLabel }}
            </label>
            <Input
              id="nutrition-protein"
              v-model="protein"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(nutritionErrors.protein_100)"
              data-testid="nutrition-protein"
            />
            <p v-if="nutritionErrors.protein_100" class="text-destructive text-sm">
              {{ nutritionErrors.protein_100 }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-fat">{{ texts.fatLabel }}</label>
            <Input
              id="nutrition-fat"
              v-model="fat"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(nutritionErrors.fat_100)"
              data-testid="nutrition-fat"
            />
            <p v-if="nutritionErrors.fat_100" class="text-destructive text-sm">
              {{ nutritionErrors.fat_100 }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-carbs">{{ texts.carbsLabel }}</label>
            <Input
              id="nutrition-carbs"
              v-model="carbs"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(nutritionErrors.carbs_100)"
              data-testid="nutrition-carbs"
            />
            <p v-if="nutritionErrors.carbs_100" class="text-destructive text-sm">
              {{ nutritionErrors.carbs_100 }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-fiber">{{ texts.fiberLabel }}</label>
            <Input
              id="nutrition-fiber"
              v-model="fiber"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="nutrition-fiber"
            />
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-sugars">
              {{ texts.sugarsLabel }}
            </label>
            <Input
              id="nutrition-sugars"
              v-model="sugars"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="nutrition-sugars"
            />
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="nutrition-gi">
              {{ texts.glycemicIndexLabel }}
            </label>
            <Input
              id="nutrition-gi"
              v-model="glycemicIndex"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(nutritionErrors.glycemic_index)"
              data-testid="nutrition-gi"
            />
            <p
              v-if="nutritionErrors.glycemic_index"
              class="text-destructive text-sm"
              data-testid="nutrition-gi-error"
            >
              {{ nutritionErrors.glycemic_index }}
            </p>
          </div>

          <div class="grid gap-2 md:col-span-2">
            <label class="text-sm font-medium" for="nutrition-source">
              {{ texts.nutritionSourceLabel }}
            </label>
            <Input
              id="nutrition-source"
              v-model="nutritionSource"
              class="min-h-11"
              data-testid="nutrition-source"
            />
            <p class="text-muted-foreground text-xs">{{ texts.verifyHint }}</p>
          </div>

          <div class="md:col-span-3">
            <Button
              type="submit"
              class="min-h-11"
              :disabled="saveNutrition.isPending.value"
              data-testid="nutrition-submit"
            >
              {{ common.save }}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <!-- Przeliczniki jednostek domowych -->
    <Card v-if="detail" class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.unitWeightsTitle }}</CardTitle>
        <CardDescription>{{ texts.unitWeightsSubtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p
          v-if="detail.unit_weights.length === 0"
          class="text-muted-foreground text-sm"
          data-testid="unit-weights-empty"
        >
          {{ texts.unitWeightsEmpty }}
        </p>

        <ul v-else class="grid gap-2" data-testid="unit-weights-list">
          <li
            v-for="weight in detail.unit_weights"
            :key="weight.id"
            class="border-border flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
            :data-testid="`unit-weight-${weight.id}`"
          >
            <span class="text-sm tabular-nums">
              1 {{ weight.unit_label }} = {{ formatAmount(weight.grams_per_unit, 'g') }}
            </span>
            <Button
              type="button"
              variant="ghost"
              class="min-h-11"
              :disabled="removeUnitWeight.isPending.value"
              :data-testid="`unit-weight-delete-${weight.id}`"
              @click="removeUnitWeight.mutate(weight)"
            >
              {{ common.remove }}
            </Button>
          </li>
        </ul>

        <form
          class="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end"
          data-testid="unit-weight-form"
          @submit.prevent="addUnitWeight.mutate()"
        >
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="unit-label">{{ texts.unitLabelLabel }}</label>
            <Input
              id="unit-label"
              v-model="unitDraft.unit_label"
              class="min-h-11"
              placeholder="łyżka"
              data-testid="unit-weight-label"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="unit-grams">
              {{ texts.gramsPerUnitLabel }}
            </label>
            <Input
              id="unit-grams"
              v-model="unitDraft.grams_per_unit"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="unit-weight-grams"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="unit-source">{{ texts.sourceLabel }}</label>
            <Input
              id="unit-source"
              v-model="unitDraft.source"
              class="min-h-11"
              data-testid="unit-weight-source"
            />
          </div>
          <Button
            type="submit"
            class="min-h-11"
            :disabled="!unitDraftValid || addUnitWeight.isPending.value"
            data-testid="unit-weight-submit"
          >
            {{ texts.addUnitWeight }}
          </Button>

          <p
            v-if="unitDraftError && unitDraft.unit_label !== ''"
            class="text-destructive text-sm md:col-span-4"
            data-testid="unit-weight-error"
          >
            {{ unitDraftError }}
          </p>
        </form>
      </CardContent>
    </Card>
  </section>
</template>
