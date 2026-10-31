<script setup lang="ts">
/**
 * Wybór przepisu z create-in-context — wzorzec obowiązkowy (06_UIUX §3.1),
 * zbudowany dokładnie jak `ProductPicker` z BATCH_04: te same props, te same
 * emits, ta sama obsługa klawiatury i te same nazwy `data-testid` z prefiksem
 * `recipe-picker`. Dzięki temu E2E i przyzwyczajenia użytkownika są wspólne.
 *
 * Inline create jest MINIMALNY (nazwa + porcja bazowa): w planie dnia liczy się
 * powrót do przerwanego zadania, a składniki dopisuje się później w edytorze
 * przepisu. Nowy przepis powstaje jako prywatny — udostępnienie rodzinie to
 * świadoma decyzja w edytorze, nie efekt uboczny pośpiechu.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { computed, ref, watch } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RecipeSummary } from '@/api/recipes'
import { createRecipe, fetchRecipes } from '@/api/recipes'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { common, recipePicker as texts } from '@/lib/texts'

const props = withDefaults(
  defineProps<{
    modelValue?: RecipeSummary | null
    label?: string
    limit?: number
    disabled?: boolean
    /** Opóźnienie szukajki; testy komponentu podają 0, żeby nie czekać. */
    debounceMs?: number
  }>(),
  { modelValue: null, label: texts.label, limit: 8, disabled: false, debounceMs: 250 },
)

const emit = defineEmits<{
  (event: 'update:modelValue', recipe: RecipeSummary | null): void
  (event: 'selected', recipe: RecipeSummary): void
}>()

const queryClient = useQueryClient()

const search = ref('')
const debouncedSearch = refDebounced(search, props.debounceMs)
const open = ref(false)
const highlighted = ref(0)
const drawerOpen = ref(false)
const draftServings = ref('1')
const createError = ref<string | null>(null)
const createName = ref('')

const phrase = computed(() => debouncedSearch.value.trim())
const phraseCurrent = computed(() => phrase.value === search.value.trim())
const filters = computed(() => ({ limit: props.limit, offset: 0, q: phrase.value }))

const results = useQuery({
  queryKey: computed(() => queryKeys.recipes.list(filters.value)),
  queryFn: () => fetchRecipes(filters.value),
  enabled: computed(() => open.value && phrase.value.length > 0 && phraseCurrent.value),
})

const items = computed<RecipeSummary[]>(() =>
  phraseCurrent.value ? (results.data.value?.items ?? []) : [],
)
const isSearching = computed(() => open.value && search.value.trim().length > 0)
const canCreate = computed(
  () =>
    !props.disabled &&
    isSearching.value &&
    phraseCurrent.value &&
    results.isSuccess.value &&
    items.value.length === 0 &&
    !results.isFetching.value,
)
const creationAllowed = computed(
  () => drawerOpen.value && canCreate.value && createName.value === phrase.value,
)

watch(search, () => {
  // Jawna zmiana kontekstu wyszukiwania zamyka szkic dla poprzedniej frazy.
  if (drawerOpen.value && search.value.trim() !== createName.value) drawerOpen.value = false
})

watch(items, () => {
  highlighted.value = 0
})

function choose(recipe: RecipeSummary): void {
  if (props.disabled || create.isPending.value || !phraseCurrent.value) return
  selectRecipe(recipe)
}

function selectRecipe(recipe: RecipeSummary): void {
  emit('update:modelValue', recipe)
  emit('selected', recipe)
  search.value = ''
  open.value = false
  drawerOpen.value = false
}

function clear(): void {
  if (props.disabled || create.isPending.value) return
  emit('update:modelValue', null)
  open.value = true
}

const create = useMutation({
  mutationFn: () =>
    createRecipe({
      name: createName.value,
      base_servings: Number.parseInt(draftServings.value, 10) || 1,
      instructions: '',
      // Nowy przepis jest PRYWATNY; udostępnienie rodzinie to świadoma decyzja
      // w edytorze, nie efekt uboczny pośpiechu przy planowaniu dnia.
      scope: 'private',
    }),
  onSuccess: async (recipe) => {
    createError.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    // Auto-wybór i powrót do przerwanego flow (06_UIUX §3.1).
    selectRecipe(recipe)
  },
  onError: (error: unknown) => {
    createError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

function openCreate(): void {
  if (!canCreate.value || create.isPending.value) return
  createName.value = phrase.value
  createError.value = null
  drawerOpen.value = true
}

function submitCreate(): void {
  if (creationAllowed.value && !create.isPending.value) create.mutate()
}

function onKeydown(event: KeyboardEvent): void {
  if (props.disabled || create.isPending.value) return
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
    const recipe = items.value[highlighted.value]
    if (recipe) {
      choose(recipe)
    } else if (canCreate.value) {
      openCreate()
    }
  }
}
</script>

<template>
  <div class="grid min-w-0 max-w-full grid-cols-1 gap-2" data-testid="recipe-picker">
    <label class="text-sm font-medium" for="recipe-picker-input">{{ label }}</label>

    <div
      v-if="modelValue && !open"
      class="border-border flex min-h-11 min-w-0 max-w-full items-center justify-between gap-2 rounded-lg border px-3"
      data-testid="recipe-picker-selected"
    >
      <span class="min-w-0 flex-1 text-sm break-words whitespace-normal">{{
        modelValue.name
      }}</span>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :disabled="disabled || create.isPending.value"
        data-testid="recipe-picker-change"
        @click="clear()"
      >
        {{ texts.change }}
      </Button>
    </div>

    <template v-else>
      <Input
        id="recipe-picker-input"
        v-model="search"
        role="combobox"
        :aria-expanded="isSearching"
        aria-controls="recipe-picker-results"
        :placeholder="texts.placeholder"
        :disabled="disabled || create.isPending.value"
        class="min-h-11 w-full min-w-0 max-w-full"
        data-testid="recipe-picker-input"
        @focus="open = true"
        @keydown="onKeydown"
      />

      <ul
        v-if="isSearching"
        id="recipe-picker-results"
        class="border-border grid min-w-0 max-w-full grid-cols-1 gap-1 rounded-lg border p-1"
        role="listbox"
        data-testid="recipe-picker-results"
      >
        <li
          v-if="!phraseCurrent || results.isPending.value"
          class="text-muted-foreground px-2 py-2 text-sm"
          role="status"
          data-testid="recipe-picker-loading"
        >
          {{ common.loading }}
        </li>

        <li
          v-if="phraseCurrent && results.isError.value"
          class="text-destructive grid gap-2 px-2 py-2 text-sm"
          role="alert"
          :data-testid="results.data.value ? 'recipe-picker-refetch-error' : 'recipe-picker-error'"
        >
          {{
            results.data.value
              ? 'Nie udało się odświeżyć przepisów. Pokazujemy ostatnio pobrane wyniki.'
              : 'Nie udało się pobrać przepisów. Nie możemy teraz potwierdzić wyników wyszukiwania.'
          }}
          <Button
            type="button"
            variant="outline"
            :disabled="results.isFetching.value || disabled"
            data-testid="recipe-picker-retry"
            @click="results.refetch()"
            >Ponów wyszukiwanie</Button
          >
        </li>

        <li
          v-for="(recipe, index) in items"
          :key="recipe.id"
          class="min-w-0"
          role="option"
          :aria-selected="index === highlighted"
        >
          <button
            type="button"
            class="hover:bg-muted flex min-h-11 w-full min-w-0 max-w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-sm"
            :class="index === highlighted ? 'bg-muted' : ''"
            :disabled="disabled || create.isPending.value"
            :data-testid="`recipe-picker-option-${recipe.id}`"
            @click="choose(recipe)"
          >
            <span class="min-w-0 flex-1 break-words whitespace-normal">{{ recipe.name }}</span>
            <span class="text-muted-foreground shrink-0 text-xs tabular-nums">
              {{ recipe.nutrition.kcal }} kcal
            </span>
          </button>
        </li>

        <li v-if="canCreate" class="grid min-w-0 grid-cols-1 gap-1">
          <p class="text-muted-foreground px-2 text-sm" data-testid="recipe-picker-empty">
            {{ texts.noResults }}
          </p>
          <button
            type="button"
            class="text-primary hover:bg-muted min-h-11 min-w-0 max-w-full rounded-lg px-2 text-left text-sm font-medium break-words whitespace-normal"
            data-testid="recipe-picker-create"
            @click="openCreate"
          >
            {{ texts.createPrefix }} „{{ phrase }}”
          </button>
        </li>
      </ul>
    </template>

    <!-- Minimalny drawer inline create: nazwa (z pickera) + porcja bazowa. -->
    <form
      v-if="drawerOpen"
      class="border-border grid min-w-0 max-w-full grid-cols-1 gap-3 rounded-lg border p-3"
      data-testid="recipe-create-drawer"
      @submit.prevent="submitCreate"
    >
      <div class="grid gap-1">
        <h3 class="text-sm font-medium">{{ texts.drawerTitle }}</h3>
        <p class="text-muted-foreground text-xs">{{ texts.drawerHint }}</p>
      </div>

      <p class="min-w-0 text-sm break-words">
        <span class="text-muted-foreground">Nazwa:</span>
        <span class="font-medium break-words"> {{ createName }}</span>
      </p>

      <div class="grid min-w-0 grid-cols-1 gap-2">
        <label class="text-sm font-medium" for="recipe-create-servings">
          Porcje (na ile porcji jest przepis)
        </label>
        <Input
          id="recipe-create-servings"
          v-model="draftServings"
          :disabled="create.isPending.value"
          inputmode="numeric"
          class="min-h-11 w-full min-w-0 max-w-full tabular-nums"
          data-testid="recipe-create-servings"
        />
      </div>

      <p v-if="createError" class="text-destructive min-w-0 text-sm break-words" role="alert">
        {{ createError }}
      </p>

      <div class="flex gap-2">
        <Button
          type="submit"
          class="min-h-11"
          :disabled="create.isPending.value || !creationAllowed"
          data-testid="recipe-create-submit"
        >
          {{ common.save }}
        </Button>
        <Button
          type="button"
          variant="ghost"
          class="min-h-11"
          data-testid="recipe-create-cancel"
          :disabled="create.isPending.value"
          @click="drawerOpen = false"
        >
          {{ common.cancel }}
        </Button>
      </div>
    </form>
  </div>
</template>
