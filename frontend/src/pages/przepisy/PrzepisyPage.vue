<script setup lang="ts">
/**
 * Lista przepisów (`/przepisy`, widok 2): grid kart, chipsy tagów, szukajka.
 *
 * Stan serwera trzyma TanStack Query (ADR-007); filtr tagów jest koniunkcją —
 * doklikiwanie chipsów zawęża wyniki. Szukajka jedzie na `?q=` z debounce
 * (trigram liczy baza, 04_API §1).
 */
import { useQuery } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { RecipeFilters } from '@/api/recipes'
import { fetchRecipes, fetchTags } from '@/api/recipes'
import { queryKeys } from '@/api/queryKeys'
import RecipeCard from '@/components/domain/RecipeCard.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { common, recipes as texts } from '@/lib/texts'

const PAGE_SIZE = 50

const router = useRouter()
const search = ref('')
const debouncedSearch = refDebounced(search, 250)
const selectedTagIds = ref<number[]>([])

const tags = useQuery({ queryKey: queryKeys.tags.all, queryFn: fetchTags })

const filters = computed<RecipeFilters>(() => ({
  limit: PAGE_SIZE,
  offset: 0,
  q: debouncedSearch.value.trim() || undefined,
  tag: selectedTagIds.value.length ? [...selectedTagIds.value] : undefined,
}))

const recipes = useQuery({
  queryKey: computed(() => queryKeys.recipes.list(filters.value)),
  queryFn: () => fetchRecipes(filters.value),
})

const items = computed(() => recipes.data.value?.items ?? [])
const isEmpty = computed(() => !recipes.isPending.value && items.value.length === 0)
const isFiltering = computed(
  () => debouncedSearch.value.trim().length > 0 || selectedTagIds.value.length > 0,
)

function toggleTag(tagId: number): void {
  const index = selectedTagIds.value.indexOf(tagId)
  if (index === -1) {
    selectedTagIds.value = [...selectedTagIds.value, tagId]
  } else {
    selectedTagIds.value = selectedTagIds.value.filter((id) => id !== tagId)
  }
}

function openRecipe(id: number): void {
  void router.push({ name: 'przepis-szczegol', params: { id } })
}
</script>

<template>
  <section class="grid gap-6" data-testid="przepisy-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <div class="grid gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <Input
          v-model="search"
          type="search"
          class="min-h-11 max-w-md"
          :aria-label="common.search"
          :placeholder="texts.searchPlaceholder"
          data-testid="recipes-search"
        />
        <Button
          as="router-link"
          :to="{ name: 'przepis-nowy' }"
          class="min-h-11"
          data-testid="recipes-add"
        >
          {{ texts.addRecipe }}
        </Button>
      </div>

      <!-- Chipsy tagów: filtr AND — każde kliknięcie zawęża (06_UIUX §4.2). -->
      <ul v-if="tags.data.value?.items.length" class="flex flex-wrap gap-2" aria-label="Tagi">
        <li v-for="tag in tags.data.value.items" :key="tag.id">
          <button
            type="button"
            class="min-h-11 rounded-lg border px-3 text-sm"
            :class="
              selectedTagIds.includes(tag.id)
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-card hover:bg-muted'
            "
            :aria-pressed="selectedTagIds.includes(tag.id)"
            :data-testid="`recipes-tag-${tag.id}`"
            @click="toggleTag(tag.id)"
          >
            {{ tag.name }}
          </button>
        </li>
      </ul>
    </div>

    <p class="text-muted-foreground text-sm tabular-nums" data-testid="recipes-total">
      Przepisów: {{ recipes.data.value?.total ?? 0 }}
    </p>

    <p v-if="recipes.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>
    <p v-else-if="recipes.isError.value" class="text-destructive text-sm" role="alert">
      {{ common.unexpectedError }}
    </p>
    <div v-else-if="isEmpty" class="grid justify-items-start gap-3" data-testid="recipes-empty">
      <p class="text-muted-foreground text-sm">
        {{ isFiltering ? texts.emptySearch : texts.emptyState }}
      </p>
      <Button as="router-link" :to="{ name: 'przepis-nowy' }" class="min-h-11">
        {{ texts.addRecipe }}
      </Button>
    </div>

    <ul v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="recipes-list">
      <li v-for="recipe in items" :key="recipe.id">
        <button
          type="button"
          class="focus-visible:ring-ring w-full rounded-xl text-left focus-visible:ring-2 focus-visible:outline-none"
          :aria-label="`Otwórz przepis: ${recipe.name}`"
          :data-testid="`recipe-open-${recipe.id}`"
          @click="openRecipe(recipe.id)"
        >
          <RecipeCard :recipe="recipe" />
        </button>
      </li>
    </ul>
  </section>
</template>
