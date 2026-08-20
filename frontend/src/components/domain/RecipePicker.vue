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

const phrase = computed(() => debouncedSearch.value.trim())
const filters = computed(() => ({ limit: props.limit, offset: 0, q: phrase.value }))

const results = useQuery({
  queryKey: computed(() => queryKeys.recipes.list(filters.value)),
  queryFn: () => fetchRecipes(filters.value),
  enabled: computed(() => open.value && phrase.value.length > 0),
})

const items = computed<RecipeSummary[]>(() => results.data.value?.items ?? [])
const isSearching = computed(() => phrase.value.length > 0)
const canCreate = computed(
  () => isSearching.value && items.value.length === 0 && !results.isFetching.value,
)

watch(items, () => {
  highlighted.value = 0
})

function choose(recipe: RecipeSummary): void {
  emit('update:modelValue', recipe)
  emit('selected', recipe)
  search.value = ''
  open.value = false
  drawerOpen.value = false
}

function clear(): void {
  emit('update:modelValue', null)
  open.value = true
}

const create = useMutation({
  mutationFn: () =>
    createRecipe({
      name: phrase.value,
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
    choose(recipe)
  },
  onError: (error: unknown) => {
    createError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

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
    const recipe = items.value[highlighted.value]
    if (recipe) {
      choose(recipe)
    } else if (canCreate.value) {
      drawerOpen.value = true
    }
  }
}
</script>

<template>
  <div class="grid gap-2" data-testid="recipe-picker">
    <label class="text-sm font-medium" for="recipe-picker-input">{{ label }}</label>

    <div
      v-if="modelValue && !open"
      class="border-border flex min-h-11 items-center justify-between gap-2 rounded-lg border px-3"
      data-testid="recipe-picker-selected"
    >
      <span class="min-w-0 truncate text-sm">{{ modelValue.name }}</span>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :disabled="disabled"
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
        aria-expanded="true"
        aria-controls="recipe-picker-results"
        :placeholder="texts.placeholder"
        :disabled="disabled"
        class="min-h-11"
        data-testid="recipe-picker-input"
        @focus="open = true"
        @keydown="onKeydown"
      />

      <ul
        v-if="isSearching"
        id="recipe-picker-results"
        class="border-border grid gap-1 rounded-lg border p-1"
        role="listbox"
        data-testid="recipe-picker-results"
      >
        <li v-if="results.isPending.value" class="text-muted-foreground px-2 py-2 text-sm">
          {{ common.loading }}
        </li>

        <li
          v-for="(recipe, index) in items"
          :key="recipe.id"
          role="option"
          :aria-selected="index === highlighted"
        >
          <button
            type="button"
            class="hover:bg-muted flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-sm"
            :class="index === highlighted ? 'bg-muted' : ''"
            :data-testid="`recipe-picker-option-${recipe.id}`"
            @click="choose(recipe)"
          >
            <span class="min-w-0 truncate">{{ recipe.name }}</span>
            <span class="text-muted-foreground shrink-0 text-xs tabular-nums">
              {{ recipe.nutrition.kcal }} kcal
            </span>
          </button>
        </li>

        <li v-if="canCreate" class="grid gap-1">
          <p class="text-muted-foreground px-2 text-sm" data-testid="recipe-picker-empty">
            {{ texts.noResults }}
          </p>
          <button
            type="button"
            class="text-primary hover:bg-muted min-h-11 rounded-lg px-2 text-left text-sm font-medium"
            data-testid="recipe-picker-create"
            @click="drawerOpen = true"
          >
            {{ texts.createPrefix }} „{{ phrase }}”
          </button>
        </li>
      </ul>
    </template>

    <!-- Minimalny drawer inline create: nazwa (z pickera) + porcja bazowa. -->
    <form
      v-if="drawerOpen"
      class="border-border grid gap-3 rounded-lg border p-3"
      data-testid="recipe-create-drawer"
      @submit.prevent="create.mutate()"
    >
      <div class="grid gap-1">
        <h3 class="text-sm font-medium">{{ texts.drawerTitle }}</h3>
        <p class="text-muted-foreground text-xs">{{ texts.drawerHint }}</p>
      </div>

      <p class="text-sm">
        <span class="text-muted-foreground">Nazwa:</span>
        <span class="font-medium"> {{ phrase }}</span>
      </p>

      <div class="grid gap-2">
        <label class="text-sm font-medium" for="recipe-create-servings">
          Porcje (na ile porcji jest przepis)
        </label>
        <Input
          id="recipe-create-servings"
          v-model="draftServings"
          inputmode="numeric"
          class="min-h-11 tabular-nums"
          data-testid="recipe-create-servings"
        />
      </div>

      <p v-if="createError" class="text-destructive text-sm" role="alert">{{ createError }}</p>

      <div class="flex gap-2">
        <Button
          type="submit"
          class="min-h-11"
          :disabled="create.isPending.value || phrase.length === 0"
          data-testid="recipe-create-submit"
        >
          {{ common.save }}
        </Button>
        <Button
          type="button"
          variant="ghost"
          class="min-h-11"
          data-testid="recipe-create-cancel"
          @click="drawerOpen = false"
        >
          {{ common.cancel }}
        </Button>
      </div>
    </form>
  </div>
</template>
