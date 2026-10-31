<script setup lang="ts">
/** PUT wymienia cały przepis. Lokalny formularz nie jest trwałym szkicem. */
import { LoaderCircle, Plus, Save } from '@lucide/vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { computed, nextTick, onMounted, onScopeDispose, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'

import type { MeasureKind, Product, ProductDetail } from '@/api/catalog'
import { fetchUnitWeights } from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RecipePayload } from '@/api/recipes'
import {
  copyRecipe,
  createRecipe,
  createTag,
  deleteRecipePhoto,
  fetchRecipe,
  fetchTags,
  updateRecipe,
  uploadRecipePhoto,
} from '@/api/recipes'
import AmountInput from '@/components/domain/AmountInput.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import LoadingState from '@/components/domain/LoadingState.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { IngredientDraft, RecipeFormValues } from '@/lib/schemas/recipe'
import { ingredientDraftError, recipeFormSchema } from '@/lib/schemas/recipe'
import {
  captureSessionGeneration,
  isSessionGenerationCurrent,
  subscribeSessionGeneration,
} from '@/lib/sessionGeneration'
import { common, recipes as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'
import { catalogQuery } from './catalogNavigation'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const auth = useAuthStore()
const editor = ref<HTMLElement>()
const extrasOpen = ref(false)
const actionError = ref<string | null>(null)
const usedInNames = ref<string[]>([])
const photoError = ref<string | null>(null)
const photoMessage = ref('')
const tagError = ref<string | null>(null)
const submitted = ref(false)
const savedExit = ref(false)
const sessionEnded = ref(false)
let editorActive = true
onScopeDispose(() => {
  editorActive = false
})
const sessionTicket = captureSessionGeneration()
// Forced logout/account/household transitions must never be held by this form.
onScopeDispose(
  subscribeSessionGeneration(() => {
    sessionEnded.value = true
  }),
)
const sessionCurrent = () =>
  editorActive && !sessionEnded.value && isSessionGenerationCurrent(sessionTicket)

const recipeId = computed(() =>
  typeof route.params.id === 'string' ? Number(route.params.id) : null,
)
const isEdit = computed(() => recipeId.value !== null)
const recipe = useQuery({
  queryKey: computed(() => queryKeys.recipes.detail(recipeId.value ?? 0, '1')),
  queryFn: () => fetchRecipe(recipeId.value as number),
  enabled: computed(() => isEdit.value && !sessionEnded.value),
})
const tags = useQuery({ queryKey: queryKeys.tags.all, queryFn: fetchTags })
const globalReadOnly = computed(
  () => isEdit.value && recipe.data.value?.scope === 'global' && !auth.isAdmin,
)
const ready = computed(() => !isEdit.value || populated.value)
const initialValues: RecipeFormValues = {
  name: '',
  instructions: '',
  base_servings: '1',
  prep_time_min: '',
  difficulty: '',
  scope: 'private',
}
const { errors, values, defineField, handleSubmit, resetForm, setFieldError } = useForm({
  validationSchema: toTypedSchema(recipeFormSchema),
  initialValues,
})
const [name] = defineField('name')
const [instructions] = defineField('instructions')
const [baseServings] = defineField('base_servings')
const [prepTime] = defineField('prep_time_min')
const [difficulty] = defineField('difficulty')
const [scope] = defineField('scope')

const SYSTEM_UNITS: Record<MeasureKind, readonly string[]> = {
  mass: ['g', 'kg'],
  volume: ['ml', 'l'],
  piece: ['szt.', 'g'],
}
let nextKey = 0
const draftKey = () => `skladnik-${++nextKey}`
const ingredients = reactive<IngredientDraft[]>([])
const homeUnits = reactive<Record<number, string[]>>({})
const ingredientErrors = reactive<Record<string, string>>({})
const selectedTagIds = ref<number[]>([])
const newTagName = ref('')
const populated = ref(false)

function snapshot(): string {
  return JSON.stringify({
    ...values,
    ingredients: ingredients.map(({ product, quantity, unit, note }) => ({
      product: product?.id ?? null,
      quantity,
      unit,
      note,
    })),
    tagIds: [...selectedTagIds.value].sort((a, b) => a - b),
    newTagName: newTagName.value,
  })
}
const baseline = ref(snapshot())
const dirty = computed(
  () => ready.value && !globalReadOnly.value && sessionCurrent() && snapshot() !== baseline.value,
)
function canLeave(): boolean {
  return (
    !sessionCurrent() ||
    savedExit.value ||
    !dirty.value ||
    window.confirm('Masz niezapisane zmiany w przepisie. Opuścić edytor i je utracić?')
  )
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate((to, from) => to.params.id === from.params.id || canLeave())
function beforeUnload(event: BeforeUnloadEvent): void {
  if (!dirty.value || savedExit.value) return
  event.preventDefault()
  event.returnValue = ''
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onScopeDispose(() => window.removeEventListener('beforeunload', beforeUnload))
function clearIngredientErrors(): void {
  for (const key of Object.keys(ingredientErrors)) delete ingredientErrors[key]
}
watch(
  recipeId,
  () => {
    populated.value = false
    savedExit.value = false
    resetForm({ values: { ...initialValues } })
    ingredients.splice(0)
    selectedTagIds.value = []
    newTagName.value = ''
    submitted.value = false
    actionError.value = null
    usedInNames.value = []
    photoError.value = null
    photoMessage.value = ''
    clearIngredientErrors()
    baseline.value = snapshot()
  },
  { flush: 'sync' },
)
watch(
  () => recipe.data.value,
  (detail) => {
    if (
      !detail ||
      !isEdit.value ||
      populated.value ||
      detail.id !== recipeId.value ||
      !sessionCurrent()
    )
      return
    resetForm({
      values: {
        name: detail.name,
        instructions: detail.instructions,
        base_servings: String(detail.base_servings),
        prep_time_min: detail.prep_time_min === null ? '' : String(detail.prep_time_min),
        difficulty: detail.difficulty === null ? '' : String(detail.difficulty),
        scope: detail.scope,
      },
    })
    selectedTagIds.value = detail.tags.map((tag) => tag.id)
    ingredients.splice(
      0,
      ingredients.length,
      ...detail.ingredients.map((ingredient) => ({
        key: draftKey(),
        product: {
          id: ingredient.product_id,
          name: ingredient.product_name,
          measure_kind: ingredient.measure_kind,
        },
        quantity: ingredient.display_qty ?? ingredient.amount,
        unit: ingredient.display_unit ?? ingredient.amount_unit,
        note: ingredient.note,
      })),
    )
    for (const ingredient of detail.ingredients) void loadHomeUnits(ingredient.product_id)
    populated.value = true
    baseline.value = snapshot()
  },
  { immediate: true },
)

let pendingFocus: string | null = null
let focusFrame = 0
onScopeDispose(() => window.cancelAnimationFrame(focusFrame))
function revealFocusedControl(event: FocusEvent): void {
  window.cancelAnimationFrame(focusFrame)
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  // Wait for the browser's native Tab scrolling before measuring the sticky bar.
  focusFrame = window.requestAnimationFrame(() => {
    if (!sessionCurrent() || document.activeElement !== target || !editor.value?.contains(target))
      return
    const bar = editor.value.querySelector<HTMLElement>('[data-testid="recipe-save-bar"]')
    if (!bar || bar.contains(target)) return
    const bounds = target.getBoundingClientRect()
    const barBounds = bar.getBoundingClientRect()
    const viewportTop = window.visualViewport?.offsetTop ?? 0
    const viewportBottom = viewportTop + (window.visualViewport?.height ?? window.innerHeight)
    if (!bounds.height || barBounds.top <= viewportTop || barBounds.top >= viewportBottom) return
    const gap = 8
    const visibleBottom = barBounds.top - gap
    if (bounds.top >= viewportTop + gap && bounds.bottom <= visibleBottom) return
    window.scrollBy({
      top: (bounds.top + bounds.bottom - viewportTop - visibleBottom) / 2,
      behavior: 'instant',
    })
  })
}
async function focusTarget(selector: string): Promise<void> {
  await nextTick()
  if (!sessionCurrent()) return
  const target = editor.value?.querySelector<HTMLElement>(selector)
  const details = target?.closest('details')
  if (details) details.open = true
  if (target?.matches(':disabled')) {
    pendingFocus = selector
    return
  }
  pendingFocus = null
  target?.focus({ preventScroll: true })
  // Native focus scrolling ignores the sticky save bar and mobile navigation.
  target?.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'instant' })
}
async function addIngredient(): Promise<void> {
  if (ingredients.length >= 100) {
    actionError.value = 'Przepis może mieć do 100 składników.'
    await focusTarget('[data-testid="recipe-editor-error"]')
    return
  }
  ingredients.push({ key: draftKey(), product: null, quantity: null, unit: 'g', note: '' })
  await focusTarget(
    `[data-testid="ingredient-row-${ingredients.length - 1}"] [data-testid="picker-input"]`,
  )
}
function removeIngredient(key: string): void {
  const index = ingredients.findIndex((draft) => draft.key === key)
  if (index < 0) return
  ingredients.splice(index, 1)
  delete ingredientErrors[key]
  void focusTarget(
    `[data-testid="ingredient-remove-${Math.min(index, ingredients.length - 1)}"], [data-testid="ingredient-add"]`,
  )
}
async function loadHomeUnits(productId: number): Promise<void> {
  if (productId in homeUnits) return
  homeUnits[productId] = []
  try {
    const response = await fetchUnitWeights(productId)
    if (sessionCurrent()) homeUnits[productId] = response.items.map((weight) => weight.unit_label)
  } catch {
    /* Jednostki systemowe są nadal dostępne. */
  }
}
function onProductSelected(draft: IngredientDraft, product: Product | ProductDetail): void {
  draft.product = { id: product.id, name: product.name, measure_kind: product.measure_kind }
  draft.unit = SYSTEM_UNITS[product.measure_kind][0] as string
  delete ingredientErrors[draft.key]
  void loadHomeUnits(product.id)
}
function unitsFor(draft: IngredientDraft): readonly string[] {
  const system = SYSTEM_UNITS[draft.product?.measure_kind ?? 'mass']
  const home = draft.product ? (homeUnits[draft.product.id] ?? []) : []
  // Zachowaj także jednostkę zapisaną wcześniej, nawet jeśli przelicznik zniknął.
  return [...new Set([...system, ...home, ...(draft.unit ? [draft.unit] : [])])]
}
function ingredientMessage(draft: IngredientDraft): string | undefined {
  return (
    ingredientErrors[draft.key] ??
    (submitted.value ? ingredientDraftError(draft)?.message : undefined)
  )
}
function ingredientTarget(index: number, field: string): string {
  const row = `[data-testid="ingredient-row-${index}"]`
  if (field === 'product_id' || field === 'product')
    return `${row} [data-testid="picker-input"], ${row} [data-testid="picker-change"]`
  if (field === 'unit') return `[data-testid="ingredient-amount-${index}-unit"]`
  if (field === 'note') return `[data-testid="ingredient-note-${index}"]`
  return `[data-testid="ingredient-amount-${index}"]`
}
function toggleTag(tagId: number): void {
  selectedTagIds.value = selectedTagIds.value.includes(tagId)
    ? selectedTagIds.value.filter((id) => id !== tagId)
    : [...selectedTagIds.value, tagId]
}
const addTag = useMutation({
  onMutate: () => recipeId.value,
  mutationFn: () => createTag(newTagName.value.trim()),
  onSuccess: async (tag, _variables, sourceId) => {
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    newTagName.value = ''
    tagError.value = null
    if (!selectedTagIds.value.includes(tag.id))
      selectedTagIds.value = [...selectedTagIds.value, tag.id]
    await queryClient.invalidateQueries({ queryKey: queryKeys.tags.all })
    if (sessionCurrent() && sourceId === recipeId.value)
      void focusTarget('[data-testid="recipe-tag-new"]')
  },
  onError: (error: unknown, _variables, sourceId) => {
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    const existing =
      error instanceof ApiError && error.status === 409 ? error.details.existing : undefined
    const id =
      typeof existing === 'object' && existing !== null && 'id' in existing
        ? existing.id
        : undefined
    if (typeof id === 'number') {
      newTagName.value = ''
      tagError.value = null
      if (!selectedTagIds.value.includes(id)) selectedTagIds.value = [...selectedTagIds.value, id]
      return
    }
    tagError.value = error instanceof ApiError ? error.message : common.unexpectedError
    void focusTarget('[data-testid="recipe-tag-new"]')
  },
})

function buildPayload(form: RecipeFormValues): RecipePayload {
  return {
    name: form.name.trim(),
    instructions: form.instructions,
    base_servings: Number(form.base_servings),
    prep_time_min: form.prep_time_min === '' ? null : Number(form.prep_time_min),
    difficulty: form.difficulty === '' ? null : Number(form.difficulty),
    scope: form.scope,
    ingredients: ingredients.map((draft) => ({
      product_id: draft.product!.id,
      quantity: draft.quantity!,
      unit: draft.unit,
      note: draft.note.trim(),
    })),
    tag_ids: [...selectedTagIds.value],
  }
}
const fieldTargets: Record<keyof RecipeFormValues, string> = {
  name: 'recipe-name',
  instructions: 'recipe-instructions',
  base_servings: 'recipe-base-servings',
  prep_time_min: 'recipe-prep-time',
  difficulty: 'recipe-difficulty',
  scope: 'recipe-scope',
}
function reportSaveError(error: unknown): void {
  if (!sessionCurrent()) return
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  const references = error instanceof ApiError ? error.details.used_in : undefined
  usedInNames.value = Array.isArray(references)
    ? references.flatMap((entry: unknown) =>
        entry && typeof entry === 'object' && 'name' in entry && typeof entry.name === 'string'
          ? [entry.name]
          : [],
      )
    : []
  let target = '[data-testid="recipe-editor-error"]'
  if (error instanceof ApiError && error.status === 422) {
    const fields = error.details.fields
    if (Array.isArray(fields)) {
      for (const entry of [...fields].reverse()) {
        if (
          typeof entry !== 'object' ||
          entry === null ||
          !('field' in entry) ||
          typeof entry.field !== 'string'
        )
          continue
        const field = entry.field
        // Pydantic messages can be English; keep actionable field messages in Polish.
        if (Object.hasOwn(fieldTargets, field)) {
          const key = field as keyof RecipeFormValues
          setFieldError(key, 'Sprawdź wartość tego pola i spróbuj ponownie.')
          target = `[data-testid="${fieldTargets[key]}"]`
        }
        const match = /^ingredients\.(\d+)\.(product_id|quantity|unit|note)$/.exec(field)
        const draft = match ? ingredients[Number(match[1])] : undefined
        if (draft && match) {
          ingredientErrors[draft.key] = 'Sprawdź ten składnik: produkt, ilość, jednostkę i notatkę.'
          target = ingredientTarget(Number(match[1]), match[2]!)
        }
      }
    }
    const index = ingredients.findIndex((draft) => draft.product?.id === error.details.product_id)
    if (index >= 0) {
      ingredientErrors[ingredients[index]!.key] = error.message
      target = ingredientTarget(index, 'unit')
    }
    if (Array.isArray(error.details.product_ids)) {
      const missingIds = error.details.product_ids
      for (let row = ingredients.length - 1; row >= 0; row--) {
        const draft = ingredients[row]!
        if (missingIds.includes(draft.product?.id)) {
          ingredientErrors[draft.key] = 'Ten produkt nie jest dostępny. Wybierz inny produkt.'
          target = ingredientTarget(row, 'product')
        }
      }
    }
    if (Array.isArray(error.details.tag_ids)) {
      extrasOpen.value = true
      target = '[data-testid="recipe-tag-new"]'
    }
  }
  void focusTarget(target)
}
const save = useMutation({
  onMutate: () => recipeId.value,
  mutationFn: (form: RecipeFormValues) =>
    isEdit.value
      ? updateRecipe(recipeId.value as number, buildPayload(form))
      : createRecipe(buildPayload(form)),
  onSuccess: async (saved, _values, sourceId) => {
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    actionError.value = null
    usedInNames.value = []
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    queryClient.setQueryData(queryKeys.recipes.detail(saved.id, '1'), saved)
    savedExit.value = true
    const failure = await router.push({
      name: 'przepis-szczegol',
      params: { id: saved.id },
      query: catalogQuery(route.query),
    })
    if (failure && sessionCurrent()) {
      baseline.value = snapshot()
      savedExit.value = false
    }
  },
  onError: (error, _values, sourceId) => {
    if (sourceId === recipeId.value) reportSaveError(error)
  },
})
let validatingRecipeId: number | null = null
const validateAndSubmit = handleSubmit(
  (form) => {
    if (
      globalReadOnly.value ||
      !ready.value ||
      !sessionCurrent() ||
      busy.value ||
      validatingRecipeId !== recipeId.value
    )
      return
    actionError.value = null
    submitted.value = true
    clearIngredientErrors()
    const index = ingredients.findIndex((draft) => ingredientDraftError(draft) !== null)
    if (index >= 0) {
      actionError.value = texts.ingredientInvalid
      void focusTarget(ingredientTarget(index, ingredientDraftError(ingredients[index]!)!.field))
      return
    }
    if (selectedTagIds.value.length > 50) {
      actionError.value = 'Wybierz najwyżej 50 tagów.'
      extrasOpen.value = true
      void focusTarget('[data-testid="recipe-tag-new"]')
      return
    }
    save.mutate(form)
  },
  ({ errors: invalid }) => {
    if (!sessionCurrent() || validatingRecipeId !== recipeId.value) return
    actionError.value = 'Popraw zaznaczone pola. Wpisane dane pozostają w formularzu.'
    const field = Object.keys(fieldTargets).find(
      (key) => invalid[key as keyof RecipeFormValues],
    ) as keyof RecipeFormValues | undefined
    void focusTarget(
      field ? `[data-testid="${fieldTargets[field]}"]` : '[data-testid="recipe-editor-error"]',
    )
  },
)
function onSubmit(event: Event): void {
  event.preventDefault()
  if (globalReadOnly.value || busy.value || !ready.value || !sessionCurrent()) return
  validatingRecipeId = recipeId.value
  void validateAndSubmit(event)
}
const copy = useMutation({
  onMutate: () => recipeId.value,
  mutationFn: () => copyRecipe(recipeId.value as number),
  onSuccess: async (saved, _variables, sourceId) => {
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    queryClient.setQueryData(queryKeys.recipes.detail(saved.id, '1'), saved)
    await router.push({
      name: 'przepis-edycja',
      params: { id: saved.id },
      query: catalogQuery(route.query),
    })
  },
  onError: (error, _variables, sourceId) => {
    if (sourceId === recipeId.value) reportSaveError(error)
  },
})
function reportPhotoError(error: unknown): void {
  if (!sessionCurrent()) return
  photoError.value = error instanceof ApiError ? error.message : common.unexpectedError
  void focusTarget('[data-testid="recipe-photo-error"]')
}
const photo = useMutation({
  onMutate: () => recipeId.value,
  mutationFn: (file: File) => uploadRecipePhoto(recipeId.value as number, file),
  onSuccess: async (saved, _file, sourceId) => {
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    queryClient.setQueryData(queryKeys.recipes.detail(saved.id, '1'), saved)
    photoMessage.value = 'Zdjęcie zapisane.'
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
  },
  onError: (error, _file, sourceId) => {
    if (sourceId === recipeId.value) reportPhotoError(error)
  },
})
const removePhoto = useMutation({
  onMutate: () => recipeId.value,
  mutationFn: () => deleteRecipePhoto(recipeId.value as number),
  onSuccess: async (saved, _variables, sourceId) => {
    if (!sessionCurrent() || sourceId !== recipeId.value) return
    queryClient.setQueryData(queryKeys.recipes.detail(saved.id, '1'), saved)
    photoError.value = null
    photoMessage.value = 'Zdjęcie usunięte.'
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
  },
  onError: (error, _variables, sourceId) => {
    if (sourceId === recipeId.value) reportPhotoError(error)
  },
})
const photoBusy = computed(() => photo.isPending.value || removePhoto.isPending.value)
const busy = computed(
  () => save.isPending.value || photoBusy.value || copy.isPending.value || addTag.isPending.value,
)
const formDisabled = computed(
  () => globalReadOnly.value || busy.value || !ready.value || sessionEnded.value,
)
watch(
  formDisabled,
  (disabled) => {
    if (!disabled && pendingFocus) void focusTarget(pendingFocus)
  },
  { flush: 'post' },
)
function onRemovePhoto(): void {
  photoError.value = null
  photoMessage.value = ''
  removePhoto.mutate()
}
function onPhotoChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file && !formDisabled.value) {
    photoError.value = null
    photoMessage.value = ''
    photo.mutate(file)
  }
  input.value = ''
}
</script>

<template>
  <section
    ref="editor"
    class="recipe-editor grid min-w-0 gap-6"
    data-testid="przepis-edytor-page"
    @focusin="revealFocusedControl"
  >
    <PageHeader
      :title="isEdit ? texts.editTitle : texts.createTitle"
      description="Zapisz składniki i sposób przygotowania swojego dania."
      eyebrow="Rodzinna książka kucharska"
    >
      <template #actions>
        <Button as-child variant="ghost" class="min-h-11 justify-self-start">
          <RouterLink
            :to="{ name: 'przepisy', query: catalogQuery(route.query) }"
            data-testid="recipe-editor-back"
            >{{ texts.backToList }}</RouterLink
          >
        </Button>
      </template>
    </PageHeader>
    <LoadingState
      v-if="isEdit && recipe.isPending.value"
      label="Wczytywanie przepisu…"
      data-testid="recipe-editor-loading"
    />
    <ErrorState
      v-else-if="isEdit && recipe.isError.value && !recipe.data.value"
      :message="
        recipe.error.value instanceof ApiError ? recipe.error.value.message : common.unexpectedError
      "
      :pending="recipe.isFetching.value"
      data-testid="recipe-editor-load-error"
      @retry="recipe.refetch()"
    />
    <template v-if="ready && !sessionEnded">
      <ErrorState
        v-if="isEdit && recipe.isError.value && recipe.data.value"
        compact
        title="Nie udało się odświeżyć przepisu"
        message="Twoje zmiany są zachowane. Spróbuj odświeżyć dane ponownie."
        :pending="recipe.isFetching.value"
        @retry="recipe.refetch()"
      />
      <section
        v-if="globalReadOnly"
        class="border-border bg-muted grid gap-3 rounded-xl border p-4"
        data-testid="recipe-read-only"
      >
        <h2 class="font-semibold">Przepis tylko do odczytu</h2>
        <p class="text-sm">{{ texts.globalReadOnlyHint }}</p>
        <Button
          class="justify-self-start"
          :disabled="copy.isPending.value"
          data-testid="recipe-editor-copy"
          @click="copy.mutate()"
        >
          <LoaderCircle
            v-if="copy.isPending.value"
            class="size-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
          {{ copy.isPending.value ? texts.copying : texts.copyToMyHousehold }}
        </Button>
      </section>
      <p
        v-if="actionError"
        tabindex="-1"
        class="text-destructive border-destructive/30 rounded-lg border p-3 text-sm"
        role="alert"
        data-testid="recipe-editor-error"
      >
        {{ actionError }}
      </p>
      <div
        v-if="usedInNames.length"
        class="text-destructive text-sm"
        data-testid="recipe-editor-used-in"
      >
        <p>{{ texts.usedInIntro }}</p>
        <ul class="list-inside list-disc">
          <li v-for="(referenceName, index) in usedInNames" :key="index" class="break-words">
            {{ referenceName }}
          </li>
        </ul>
      </div>
      <!-- Sibling form avoids nesting the independent create-in-context forms. -->
      <form id="recipe-editor-form" novalidate data-testid="recipe-form" @submit="onSubmit" />
      <fieldset :disabled="formDisabled" class="grid min-w-0 gap-8" :aria-busy="busy">
        <legend class="sr-only">Dane przepisu</legend>
        <section class="grid min-w-0 gap-4" aria-labelledby="recipe-basics-title">
          <h2 id="recipe-basics-title" class="text-lg font-semibold">Nazwa i porcje</h2>
          <div class="grid min-w-0 gap-2">
            <label class="text-sm font-medium" for="recipe-name">{{ texts.nameLabel }}</label>
            <Input
              id="recipe-name"
              v-model="name"
              form="recipe-editor-form"
              class="min-h-11"
              :disabled="formDisabled"
              :aria-invalid="Boolean(errors.name)"
              :aria-describedby="errors.name ? 'recipe-name-error' : undefined"
              data-testid="recipe-name"
            />
            <p
              v-if="errors.name"
              id="recipe-name-error"
              class="text-destructive text-sm"
              data-testid="recipe-name-error"
            >
              {{ errors.name }}
            </p>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="grid gap-2">
              <label class="text-sm font-medium" for="recipe-servings">{{
                texts.baseServingsLabel
              }}</label>
              <Input
                id="recipe-servings"
                v-model="baseServings"
                form="recipe-editor-form"
                inputmode="numeric"
                class="min-h-11 tabular-nums"
                :disabled="formDisabled"
                :aria-invalid="Boolean(errors.base_servings)"
                :aria-describedby="errors.base_servings ? 'recipe-servings-error' : undefined"
                data-testid="recipe-base-servings"
              />
              <p
                v-if="errors.base_servings"
                id="recipe-servings-error"
                class="text-destructive text-sm"
              >
                {{ errors.base_servings }}
              </p>
            </div>
            <div class="grid gap-2">
              <label class="text-sm font-medium" for="recipe-prep-time">{{
                texts.prepTimeLabel
              }}</label>
              <Input
                id="recipe-prep-time"
                v-model="prepTime"
                form="recipe-editor-form"
                inputmode="numeric"
                class="min-h-11 tabular-nums"
                :disabled="formDisabled"
                :aria-invalid="Boolean(errors.prep_time_min)"
                :aria-describedby="errors.prep_time_min ? 'recipe-prep-error' : undefined"
                data-testid="recipe-prep-time"
              />
              <p
                v-if="errors.prep_time_min"
                id="recipe-prep-error"
                class="text-destructive text-sm"
              >
                {{ errors.prep_time_min }}
              </p>
            </div>
          </div>
        </section>
        <section
          class="border-border grid min-w-0 gap-4 border-t pt-6"
          aria-labelledby="recipe-ingredients-title"
        >
          <h2 id="recipe-ingredients-title" class="text-lg font-semibold">
            {{ texts.ingredientsTitle }}
          </h2>
          <p
            v-if="!ingredients.length"
            class="text-muted-foreground text-sm"
            data-testid="ingredients-empty"
          >
            {{ texts.ingredientsEmpty }}
          </p>
          <div
            v-for="(draft, index) in ingredients"
            :key="draft.key"
            class="border-border grid min-w-0 gap-3 border-b pb-5"
            :data-testid="`ingredient-row-${index}`"
            @input="delete ingredientErrors[draft.key]"
            @change="delete ingredientErrors[draft.key]"
          >
            <ProductPicker
              :model-value="draft.product as never"
              :label="`Produkt — składnik ${index + 1}`"
              :disabled="formDisabled"
              @selected="(product) => onProductSelected(draft, product)"
              @update:model-value="
                (product) => {
                  if (product === null) draft.product = null
                }
              "
            />
            <div class="grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <AmountInput
                :model-value="draft.quantity"
                form="recipe-editor-form"
                :unit="draft.unit"
                :units="unitsFor(draft)"
                :decimal-places="3"
                :disabled="formDisabled"
                required
                :testid="`ingredient-amount-${index}`"
                @update:model-value="(value) => (draft.quantity = value)"
                @update:unit="(value) => (draft.unit = value)"
              />
              <Button
                type="button"
                variant="ghost"
                class="min-h-11 justify-self-start"
                :disabled="formDisabled"
                :aria-label="`Usuń składnik ${index + 1}`"
                :data-testid="`ingredient-remove-${index}`"
                @click="removeIngredient(draft.key)"
                >{{ common.remove }}</Button
              >
            </div>
            <div class="grid gap-2">
              <label class="text-muted-foreground text-sm" :for="`ingredient-note-${index}`">{{
                texts.noteLabel
              }}</label>
              <Input
                :id="`ingredient-note-${index}`"
                v-model="draft.note"
                form="recipe-editor-form"
                class="min-h-11"
                :disabled="formDisabled"
                :data-testid="`ingredient-note-${index}`"
              />
            </div>
            <p
              v-if="ingredientMessage(draft)"
              class="text-destructive text-sm"
              :data-testid="`ingredient-error-${index}`"
            >
              {{ ingredientMessage(draft) }}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            class="min-h-11 justify-self-start"
            :disabled="formDisabled"
            data-testid="ingredient-add"
            @click="addIngredient()"
            ><Plus class="size-4" aria-hidden="true" />{{ texts.addIngredient }}</Button
          >
        </section>
        <section class="grid min-w-0 gap-3" aria-labelledby="recipe-preparation-title">
          <h2 id="recipe-preparation-title" class="text-lg font-semibold">Przygotowanie</h2>
          <label class="text-sm font-medium" for="recipe-instructions">{{
            texts.instructionsLabel
          }}</label>
          <textarea
            id="recipe-instructions"
            v-model="instructions"
            form="recipe-editor-form"
            rows="7"
            class="border-border bg-card w-full min-w-0 rounded-lg border px-3 py-2 text-base leading-relaxed"
            :disabled="formDisabled"
            :aria-invalid="Boolean(errors.instructions)"
            :aria-describedby="errors.instructions ? 'recipe-instructions-error' : undefined"
            data-testid="recipe-instructions"
          />
          <p
            v-if="errors.instructions"
            id="recipe-instructions-error"
            class="text-destructive text-sm"
          >
            {{ errors.instructions }}
          </p>
        </section>
        <details
          :open="extrasOpen"
          class="border-border min-w-0 border-t pt-2"
          data-testid="recipe-extras"
          @toggle="extrasOpen = ($event.target as HTMLDetailsElement).open"
        >
          <summary
            class="focus-visible:ring-ring flex min-h-11 cursor-pointer items-center rounded-md text-sm font-semibold focus-visible:ring-2 focus-visible:outline-none"
          >
            Dodatkowe: widoczność, trudność, tagi i zdjęcie
          </summary>
          <div class="grid min-w-0 gap-6 pt-4">
            <div class="grid gap-4 sm:grid-cols-2">
              <div class="grid gap-2">
                <label class="text-sm font-medium" for="recipe-scope">{{ texts.scopeLabel }}</label>
                <select
                  id="recipe-scope"
                  v-model="scope"
                  form="recipe-editor-form"
                  class="border-border bg-card min-h-11 w-full min-w-0 rounded-lg border px-3 text-base"
                  :disabled="formDisabled"
                  :aria-invalid="Boolean(errors.scope)"
                  :aria-describedby="errors.scope ? 'recipe-scope-error' : undefined"
                  data-testid="recipe-scope"
                >
                  <option value="private">{{ texts.scopePrivate }}</option>
                  <option value="household">{{ texts.scopeHousehold }}</option>
                  <option v-if="auth.isAdmin || scope === 'global'" value="global">
                    {{ texts.scopeGlobal }}
                  </option>
                </select>
                <p
                  v-if="scope === 'global'"
                  class="text-muted-foreground text-sm"
                  data-testid="recipe-scope-hint"
                >
                  {{ globalReadOnly ? texts.globalReadOnlyHint : texts.scopeGlobalHint }}
                </p>
                <p v-if="errors.scope" id="recipe-scope-error" class="text-destructive text-sm">
                  {{ errors.scope }}
                </p>
              </div>
              <div class="grid gap-2">
                <label class="text-sm font-medium" for="recipe-difficulty"
                  >{{ texts.difficultyLabel }} (1–10)</label
                >
                <Input
                  id="recipe-difficulty"
                  v-model="difficulty"
                  form="recipe-editor-form"
                  inputmode="numeric"
                  class="min-h-11 tabular-nums"
                  :disabled="formDisabled"
                  :aria-invalid="Boolean(errors.difficulty)"
                  :aria-describedby="errors.difficulty ? 'recipe-difficulty-error' : undefined"
                  data-testid="recipe-difficulty"
                />
                <p
                  v-if="errors.difficulty"
                  id="recipe-difficulty-error"
                  class="text-destructive text-sm"
                >
                  {{ errors.difficulty }}
                </p>
              </div>
            </div>
            <section class="grid gap-3" aria-labelledby="recipe-tags-title">
              <h3 id="recipe-tags-title" class="font-semibold">{{ texts.tagsTitle }}</h3>
              <p v-if="tags.isPending.value" class="text-muted-foreground text-sm">
                Wczytywanie tagów…
              </p>
              <ErrorState
                v-else-if="tags.isError.value"
                compact
                message="Nie udało się pobrać tagów. Wybrane tagi pozostają zapisane w formularzu."
                :pending="tags.isFetching.value"
                @retry="tags.refetch()"
              />
              <ul class="flex flex-wrap gap-2" aria-label="Tagi">
                <li
                  v-for="tag in tags.data.value?.items ?? []"
                  :key="tag.id"
                  class="min-w-0 max-w-full"
                >
                  <button
                    type="button"
                    class="min-h-11 max-w-full rounded-lg border px-3 text-sm break-words"
                    :class="
                      selectedTagIds.includes(tag.id)
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border bg-card hover:bg-muted'
                    "
                    :disabled="formDisabled"
                    :aria-pressed="selectedTagIds.includes(tag.id)"
                    :data-testid="`recipe-tag-${tag.id}`"
                    @click="toggleTag(tag.id)"
                  >
                    {{ tag.name }}
                  </button>
                </li>
              </ul>
              <div class="flex min-w-0 flex-wrap gap-2">
                <Input
                  v-model="newTagName"
                  class="min-h-11 w-full sm:max-w-xs"
                  :disabled="formDisabled"
                  :placeholder="texts.tagCreatePlaceholder"
                  :aria-label="texts.addTag"
                  data-testid="recipe-tag-new"
                  @keydown.enter.prevent="
                    () => {
                      if (newTagName.trim() && !formDisabled) addTag.mutate()
                    }
                  "
                />
                <Button
                  type="button"
                  variant="outline"
                  class="min-h-11"
                  :disabled="!newTagName.trim() || formDisabled"
                  data-testid="recipe-tag-create"
                  @click="addTag.mutate()"
                  ><LoaderCircle
                    v-if="addTag.isPending.value"
                    class="size-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />{{ texts.addTag }}</Button
                >
              </div>
              <p
                v-if="tagError"
                role="alert"
                class="text-destructive text-sm"
                data-testid="recipe-tag-error"
              >
                {{ tagError }}
              </p>
            </section>
            <section class="grid gap-3" aria-labelledby="recipe-photo-title" :aria-busy="photoBusy">
              <h3 id="recipe-photo-title" class="font-semibold">{{ texts.photoTitle }}</h3>
              <p class="text-muted-foreground text-sm">
                {{ isEdit ? texts.photoHint : texts.photoSaveFirst }}
              </p>
              <template v-if="isEdit">
                <img
                  v-if="recipe.data.value?.photo_thumb_url"
                  :src="recipe.data.value.photo_thumb_url"
                  :alt="`Zdjęcie: ${recipe.data.value.name}`"
                  class="max-h-48 max-w-full justify-self-start rounded-lg object-cover"
                  data-testid="recipe-photo-preview"
                />
                <p v-else class="text-muted-foreground text-sm" data-testid="recipe-photo-empty">
                  Ten przepis nie ma zdjęcia.
                </p>
                <div class="flex flex-wrap items-center gap-2">
                  <label
                    class="border-border bg-card hover:bg-muted focus-within:ring-ring inline-flex min-h-11 cursor-pointer items-center rounded-lg border px-3 text-sm focus-within:ring-2"
                    :class="formDisabled && 'cursor-default opacity-50'"
                  >
                    {{ recipe.data.value?.photo_url ? 'Zmień zdjęcie' : 'Dodaj zdjęcie' }}
                    <input
                      type="file"
                      accept="image/*"
                      class="sr-only"
                      :disabled="formDisabled"
                      data-testid="recipe-photo-input"
                      @change="onPhotoChange"
                    />
                  </label>
                  <Button
                    v-if="recipe.data.value?.photo_url"
                    type="button"
                    variant="ghost"
                    class="min-h-11"
                    :disabled="formDisabled"
                    data-testid="recipe-photo-remove"
                    @click="onRemovePhoto"
                    >{{ texts.photoRemove }}</Button
                  >
                </div>
                <p
                  v-if="photoBusy"
                  role="status"
                  class="text-muted-foreground flex items-center gap-2 text-sm"
                  data-testid="recipe-photo-pending"
                >
                  <LoaderCircle
                    class="size-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />{{ photo.isPending.value ? 'Przesyłanie zdjęcia…' : 'Usuwanie zdjęcia…' }}
                </p>
                <p
                  v-if="photoError"
                  tabindex="-1"
                  role="alert"
                  class="text-destructive text-sm"
                  data-testid="recipe-photo-error"
                >
                  {{ photoError }}
                </p>
                <p
                  v-if="photoMessage"
                  role="status"
                  class="text-primary text-sm"
                  data-testid="recipe-photo-success"
                >
                  {{ photoMessage }}
                </p>
              </template>
            </section>
          </div>
        </details>
      </fieldset>
      <div
        class="border-border bg-card sticky bottom-20 z-10 flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border p-3 shadow-sm md:bottom-4"
        data-testid="recipe-save-bar"
      >
        <p role="status" class="text-muted-foreground text-sm" data-testid="recipe-dirty-status">
          {{
            globalReadOnly
              ? 'Tylko do odczytu'
              : dirty
                ? 'Masz niezapisane zmiany'
                : 'Brak niezapisanych zmian'
          }}
        </p>
        <Button
          type="submit"
          form="recipe-editor-form"
          class="min-h-11"
          :disabled="formDisabled"
          data-testid="recipe-submit"
          ><LoaderCircle
            v-if="save.isPending.value"
            class="size-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          /><Save v-else class="size-4" aria-hidden="true" />{{
            save.isPending.value ? 'Zapisywanie…' : common.save
          }}</Button
        >
      </div>
      <p class="text-muted-foreground text-xs">
        Zmiany zachowasz po wybraniu „Zapisz”. Formularz nie zapisuje szkicu po zamknięciu
        przeglądarki.
      </p>
    </template>
  </section>
</template>

<style scoped>
/* Pełne nazwy w edytorze; wspólny kontrakt pickera pozostaje bez zmian. */
.recipe-editor :deep([data-testid='picker-selected'] > span),
.recipe-editor :deep([data-testid^='picker-option-'] > span:first-child) {
  white-space: normal;
  overflow-wrap: anywhere;
  overflow: visible;
}
.recipe-editor :deep([data-testid='product-picker']),
.recipe-editor :deep(input) {
  min-width: 0;
}
.recipe-editor :deep([data-testid^='ingredient-amount-'][data-testid$='-unit']) {
  flex-shrink: 0;
  min-width: 0;
  max-width: 50%;
}
</style>
