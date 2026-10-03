<script setup lang="ts">
/**
 * Edytor przepisu (`/przepisy/nowy`, `/przepisy/:id/edytuj`).
 *
 * Składniki: `ProductPicker` (create-in-context z B04 — obowiązkowo działa
 * stąd!) + `AmountInput` (string dziesiętny, przecinek PL). Jednostki pozycji
 * = systemowe dla typu miary produktu + jego przeliczniki domowe (dociągane
 * po wyborze produktu). Tagi: multi-picker chipsów z inline create.
 *
 * PUT wymienia składniki KOMPLETEM (kontrakt B05) — edytor wysyła zawsze
 * pełną listę; walidacja frontowa to UX, prawdą jest 422 z backendu.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { MeasureKind, Product, ProductDetail } from '@/api/catalog'
import { fetchUnitWeights } from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RecipePayload } from '@/api/recipes'
import {
  createRecipe,
  createTag,
  deleteRecipePhoto,
  fetchRecipe,
  fetchTags,
  updateRecipe,
  uploadRecipePhoto,
} from '@/api/recipes'
import AmountInput from '@/components/domain/AmountInput.vue'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { IngredientDraft, RecipeFormValues } from '@/lib/schemas/recipe'
import { isIngredientDraftValid, recipeFormSchema } from '@/lib/schemas/recipe'
import { common, recipes as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const auth = useAuthStore()

const recipeId = computed(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? Number(raw) : null
})
const isEdit = computed(() => recipeId.value !== null)

const recipe = useQuery({
  queryKey: computed(() => queryKeys.recipes.detail(recipeId.value ?? 0, '1')),
  queryFn: () => fetchRecipe(recipeId.value as number),
  enabled: computed(() => isEdit.value),
})
const tags = useQuery({ queryKey: queryKeys.tags.all, queryFn: fetchTags })

const actionError = ref<string | null>(null)

/**
 * Przepis `global` (D32) edytuje wyłącznie ADMIN. Zwykły użytkownik, który wejdzie
 * tu z linku, widzi formularz tylko do odczytu z podpowiedzią — zapis i tak
 * skończyłby się 403, więc nie pozwalamy go nawet wysłać. Zakres „Wszyscy" w
 * selekcie dostaje tylko ADMIN (albo przepis, który już jest globalny).
 */
const globalReadOnly = computed(
  () => isEdit.value && recipe.data.value?.scope === 'global' && !auth.isAdmin,
)

// --- pola proste (vee-validate + zod) -------------------------------------------

const { errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: toTypedSchema(recipeFormSchema),
  initialValues: {
    name: '',
    instructions: '',
    base_servings: '1',
    prep_time_min: '',
    difficulty: '',
    scope: 'private',
  },
})

const [name] = defineField('name')
const [instructions] = defineField('instructions')
const [baseServings] = defineField('base_servings')
const [prepTime] = defineField('prep_time_min')
const [difficulty] = defineField('difficulty')
const [scope] = defineField('scope')

// --- składniki --------------------------------------------------------------------

/** Jednostki systemowe dla typu miary produktu (ADR-005). */
const SYSTEM_UNITS: Record<MeasureKind, readonly string[]> = {
  mass: ['g', 'kg'],
  volume: ['ml', 'l'],
  piece: ['szt.', 'g'],
}

let nextKey = 0
function draftKey(): string {
  nextKey += 1
  return `skladnik-${nextKey}`
}

const ingredients = reactive<IngredientDraft[]>([])
/** Przeliczniki domowe per produkt — dociągane raz po wyborze w pickerze. */
const homeUnits = reactive<Record<number, string[]>>({})

function addIngredient(): void {
  ingredients.push({ key: draftKey(), product: null, quantity: null, unit: 'g', note: '' })
}

function removeIngredient(key: string): void {
  const index = ingredients.findIndex((draft) => draft.key === key)
  if (index !== -1) {
    ingredients.splice(index, 1)
  }
}

async function loadHomeUnits(productId: number): Promise<void> {
  if (productId in homeUnits) {
    return
  }
  // Wpis od razu, PRZED await: dwa składniki z tym samym produktem nie mogą
  // odpalić dwóch równoległych, identycznych żądań.
  homeUnits[productId] = []
  try {
    const response = await fetchUnitWeights(productId)
    homeUnits[productId] = response.items.map((weight) => weight.unit_label)
  } catch {
    // Brak przeliczników nie blokuje edycji — zostają jednostki systemowe.
  }
}

function onProductSelected(draft: IngredientDraft, product: Product | ProductDetail): void {
  draft.product = { id: product.id, name: product.name, measure_kind: product.measure_kind }
  draft.unit = SYSTEM_UNITS[product.measure_kind][0] as string
  void loadHomeUnits(product.id)
}

function unitsFor(draft: IngredientDraft): readonly string[] {
  if (!draft.product) {
    return SYSTEM_UNITS.mass
  }
  const system = SYSTEM_UNITS[draft.product.measure_kind]
  const home = homeUnits[draft.product.id] ?? []
  return [...system, ...home.filter((label) => !system.includes(label))]
}

const ingredientsValid = computed(() => ingredients.every(isIngredientDraftValid))

// --- tagi ---------------------------------------------------------------------------

const selectedTagIds = ref<number[]>([])
const newTagName = ref('')

function toggleTag(tagId: number): void {
  selectedTagIds.value = selectedTagIds.value.includes(tagId)
    ? selectedTagIds.value.filter((id) => id !== tagId)
    : [...selectedTagIds.value, tagId]
}

const addTag = useMutation({
  mutationFn: () => createTag(newTagName.value.trim()),
  onSuccess: async (tag) => {
    newTagName.value = ''
    await queryClient.invalidateQueries({ queryKey: queryKeys.tags.all })
    if (!selectedTagIds.value.includes(tag.id)) {
      selectedTagIds.value = [...selectedTagIds.value, tag.id]
    }
  },
  onError: (error: unknown) => {
    // 409 = tag już istnieje — wybieramy go zamiast pokazywać błąd (create-in-context).
    if (error instanceof ApiError && error.status === 409) {
      const existing = error.details.existing
      const id = (existing as { id?: unknown } | undefined)?.id
      if (typeof id === 'number') {
        newTagName.value = ''
        if (!selectedTagIds.value.includes(id)) {
          selectedTagIds.value = [...selectedTagIds.value, id]
        }
        return
      }
    }
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

// --- wypełnienie formularza w trybie edycji --------------------------------------------

/** Formularz wypełnia się z serwera dokładnie RAZ — kolejny refetch (np. po
 *  uploadzie zdjęcia, który invaliduje `recipes.all`, albo po powrocie fokusa
 *  okna) nie może nadpisać niezapisanych edycji użytkownika. */
const populated = ref(false)

watch(
  () => recipe.data.value,
  (detail) => {
    if (!detail || populated.value) {
      return
    }
    populated.value = true
    setValues({
      name: detail.name,
      instructions: detail.instructions,
      base_servings: String(detail.base_servings),
      prep_time_min: detail.prep_time_min === null ? '' : String(detail.prep_time_min),
      difficulty: detail.difficulty === null ? '' : String(detail.difficulty),
      scope: detail.scope,
    })
    selectedTagIds.value = detail.tags.map((tag) => tag.id)
    ingredients.splice(0, ingredients.length)
    for (const ingredient of detail.ingredients) {
      ingredients.push({
        key: draftKey(),
        product: {
          id: ingredient.product_id,
          name: ingredient.product_name,
          measure_kind: ingredient.measure_kind,
        },
        // Preferujemy zapis użytkownika; postać znormalizowana jest zapasem.
        quantity: ingredient.display_qty ?? ingredient.amount,
        unit: ingredient.display_unit ?? ingredient.amount_unit,
        note: ingredient.note,
      })
      void loadHomeUnits(ingredient.product_id)
    }
  },
  { immediate: true },
)

// --- zapis -------------------------------------------------------------------------

function buildPayload(values: RecipeFormValues): RecipePayload {
  return {
    name: values.name.trim(),
    instructions: values.instructions,
    base_servings: Number(values.base_servings),
    prep_time_min: values.prep_time_min === '' ? null : Number(values.prep_time_min),
    difficulty: values.difficulty === '' ? null : Number(values.difficulty),
    scope: values.scope,
    ingredients: ingredients.map((draft) => ({
      product_id: (draft.product as { id: number }).id,
      quantity: draft.quantity as string,
      unit: draft.unit,
      note: draft.note.trim(),
    })),
    tag_ids: [...selectedTagIds.value],
  }
}

const save = useMutation({
  mutationFn: (values: RecipeFormValues) => {
    const payload = buildPayload(values)
    return isEdit.value ? updateRecipe(recipeId.value as number, payload) : createRecipe(payload)
  },
  onSuccess: async (saved) => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    // Odpowiedź zapisu to gotowy detail (servings=1) — zasiewamy cache, żeby
    // strona szczegółów nie pobierała drugi raz tego, co już mamy.
    queryClient.setQueryData(queryKeys.recipes.detail(saved.id, '1'), saved)
    await router.push({ name: 'przepis-szczegol', params: { id: saved.id } })
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const onSubmit = handleSubmit((values) => {
  if (!ingredientsValid.value) {
    actionError.value = texts.ingredientInvalid
    return
  }
  save.mutate(values)
})

// --- zdjęcie (tylko edycja — wymaga istniejącego id) -------------------------------------

const photo = useMutation({
  mutationFn: (file: File) => uploadRecipePhoto(recipeId.value as number, file),
  onSuccess: async () => {
    actionError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const removePhoto = useMutation({
  mutationFn: () => deleteRecipePhoto(recipeId.value as number),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

function onPhotoChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    photo.mutate(file)
  }
  input.value = ''
}
</script>

<template>
  <section class="grid gap-6" data-testid="przepis-edytor-page">
    <header class="grid gap-2">
      <h1 class="text-2xl font-semibold">{{ isEdit ? texts.editTitle : texts.createTitle }}</h1>
      <Button as-child variant="ghost" class="min-h-11 justify-self-start">
        <RouterLink :to="{ name: 'przepisy' }" data-testid="recipe-editor-back">
          {{ texts.backToList }}
        </RouterLink>
      </Button>
    </header>

    <p
      v-if="actionError"
      class="text-destructive text-sm"
      role="alert"
      data-testid="recipe-editor-error"
    >
      {{ actionError }}
    </p>

    <form class="grid gap-6" novalidate data-testid="recipe-form" @submit="onSubmit">
      <Card class="rounded-xl">
        <CardHeader>
          <CardTitle>{{ texts.title }}</CardTitle>
        </CardHeader>
        <CardContent class="grid gap-4 md:grid-cols-2">
          <div class="grid gap-2 md:col-span-2">
            <label class="text-sm font-medium" for="recipe-name">{{ texts.nameLabel }}</label>
            <Input
              id="recipe-name"
              v-model="name"
              class="min-h-11"
              :aria-invalid="Boolean(errors.name)"
              data-testid="recipe-name"
            />
            <p v-if="errors.name" class="text-destructive text-sm" data-testid="recipe-name-error">
              {{ errors.name }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="recipe-servings">
              {{ texts.baseServingsLabel }}
            </label>
            <Input
              id="recipe-servings"
              v-model="baseServings"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(errors.base_servings)"
              data-testid="recipe-base-servings"
            />
            <p v-if="errors.base_servings" class="text-destructive text-sm">
              {{ errors.base_servings }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="recipe-prep-time">
              {{ texts.prepTimeLabel }}
            </label>
            <Input
              id="recipe-prep-time"
              v-model="prepTime"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(errors.prep_time_min)"
              data-testid="recipe-prep-time"
            />
            <p v-if="errors.prep_time_min" class="text-destructive text-sm">
              {{ errors.prep_time_min }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="recipe-difficulty">
              {{ texts.difficultyLabel }} (1-10)
            </label>
            <Input
              id="recipe-difficulty"
              v-model="difficulty"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              :aria-invalid="Boolean(errors.difficulty)"
              data-testid="recipe-difficulty"
            />
            <p v-if="errors.difficulty" class="text-destructive text-sm">{{ errors.difficulty }}</p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="recipe-scope">{{ texts.scopeLabel }}</label>
            <select
              id="recipe-scope"
              v-model="scope"
              class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
              :disabled="globalReadOnly"
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
          </div>

          <div class="grid gap-2 md:col-span-2">
            <label class="text-sm font-medium" for="recipe-instructions">
              {{ texts.instructionsLabel }}
            </label>
            <textarea
              id="recipe-instructions"
              v-model="instructions"
              rows="6"
              class="border-border bg-card rounded-lg border px-3 py-2 text-sm"
              data-testid="recipe-instructions"
            ></textarea>
          </div>
        </CardContent>
      </Card>

      <!-- Składniki: ProductPicker (inline create!) + AmountInput -->
      <Card class="rounded-xl">
        <CardHeader>
          <CardTitle>{{ texts.ingredientsTitle }}</CardTitle>
        </CardHeader>
        <CardContent class="grid gap-4">
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
            class="border-border grid gap-3 rounded-lg border p-3"
            :data-testid="`ingredient-row-${index}`"
          >
            <ProductPicker
              :model-value="draft.product as never"
              @selected="(product) => onProductSelected(draft, product)"
              @update:model-value="
                (product) => {
                  if (product === null) {
                    draft.product = null
                  }
                }
              "
            />
            <div class="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <AmountInput
                :model-value="draft.quantity"
                :unit="draft.unit"
                :units="unitsFor(draft)"
                :decimal-places="3"
                required
                :testid="`ingredient-amount-${index}`"
                @update:model-value="(value) => (draft.quantity = value)"
                @update:unit="(value) => (draft.unit = value)"
              />
              <div class="grid gap-2">
                <label class="text-sm font-medium" :for="`ingredient-note-${index}`">
                  {{ texts.noteLabel }}
                </label>
                <Input
                  :id="`ingredient-note-${index}`"
                  v-model="draft.note"
                  class="min-h-11"
                  :data-testid="`ingredient-note-${index}`"
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                class="min-h-11"
                :aria-label="`Usuń składnik ${index + 1}`"
                :data-testid="`ingredient-remove-${index}`"
                @click="removeIngredient(draft.key)"
              >
                {{ common.remove }}
              </Button>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            class="min-h-11 justify-self-start"
            data-testid="ingredient-add"
            @click="addIngredient()"
          >
            {{ texts.addIngredient }}
          </Button>
        </CardContent>
      </Card>

      <!-- Tagi: chipsy + inline create (06_UIUX §3.1 — wzorzec bez wyjątków). -->
      <Card class="rounded-xl">
        <CardHeader>
          <CardTitle>{{ texts.tagsTitle }}</CardTitle>
        </CardHeader>
        <CardContent class="grid gap-3">
          <ul class="flex flex-wrap gap-2" aria-label="Tagi">
            <li v-for="tag in tags.data.value?.items ?? []" :key="tag.id">
              <button
                type="button"
                class="min-h-11 rounded-lg border px-3 text-sm"
                :class="
                  selectedTagIds.includes(tag.id)
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-card hover:bg-muted'
                "
                :aria-pressed="selectedTagIds.includes(tag.id)"
                :data-testid="`recipe-tag-${tag.id}`"
                @click="toggleTag(tag.id)"
              >
                {{ tag.name }}
              </button>
            </li>
          </ul>
          <div class="flex gap-2">
            <Input
              v-model="newTagName"
              class="min-h-11 max-w-xs"
              :placeholder="texts.tagCreatePlaceholder"
              :aria-label="texts.addTag"
              data-testid="recipe-tag-new"
            />
            <Button
              type="button"
              variant="outline"
              class="min-h-11"
              :disabled="!newTagName.trim() || addTag.isPending.value"
              data-testid="recipe-tag-create"
              @click="addTag.mutate()"
            >
              {{ texts.addTag }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <!-- Zdjęcie: pipeline uploadu 07_SECURITY §6; wymaga zapisanego przepisu. -->
      <Card class="rounded-xl">
        <CardHeader>
          <CardTitle>{{ texts.photoTitle }}</CardTitle>
          <CardDescription>
            {{ isEdit ? texts.photoHint : texts.photoSaveFirst }}
          </CardDescription>
        </CardHeader>
        <CardContent v-if="isEdit" class="grid gap-3">
          <img
            v-if="recipe.data.value?.photo_thumb_url"
            :src="recipe.data.value.photo_thumb_url"
            :alt="`Zdjęcie: ${recipe.data.value.name}`"
            class="max-h-48 justify-self-start rounded-lg object-cover"
            data-testid="recipe-photo-preview"
          />
          <div class="flex flex-wrap items-center gap-2">
            <label
              class="border-border bg-card hover:bg-muted inline-flex min-h-11 cursor-pointer items-center rounded-lg border px-3 text-sm"
            >
              {{ common.add }}
              <input
                type="file"
                accept="image/*"
                class="sr-only"
                :disabled="globalReadOnly"
                data-testid="recipe-photo-input"
                @change="onPhotoChange"
              />
            </label>
            <Button
              v-if="recipe.data.value?.photo_url"
              type="button"
              variant="ghost"
              class="min-h-11"
              :disabled="removePhoto.isPending.value"
              data-testid="recipe-photo-remove"
              @click="removePhoto.mutate()"
            >
              {{ texts.photoRemove }}
            </Button>
            <span v-if="photo.isPending.value" class="text-muted-foreground text-sm">
              {{ common.loading }}
            </span>
          </div>
        </CardContent>
      </Card>

      <Button
        type="submit"
        class="min-h-11 justify-self-start"
        :disabled="save.isPending.value || globalReadOnly"
        data-testid="recipe-submit"
      >
        {{ common.save }}
      </Button>
    </form>
  </section>
</template>
