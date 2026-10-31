<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { ChevronDown, Plus, Search } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { usePaginatedList } from '@/api/pagination'
import type { PlanDay } from '@/api/planning'
import type { RecipeScope, RecipeSummary } from '@/api/recipes'
import { fetchRecipes, fetchTags } from '@/api/recipes'
import { queryKeys } from '@/api/queryKeys'
import EmptyState from '@/components/domain/EmptyState.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import LoadMoreButton from '@/components/domain/LoadMoreButton.vue'
import LoadingState from '@/components/domain/LoadingState.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import RecipeCard from '@/components/domain/RecipeCard.vue'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { planNavigationContext, planNavigationTarget } from '@/lib/navigation'
import { common, listCount, recipes as texts } from '@/lib/texts'
import { catalogFilters, catalogQuery } from './catalogNavigation'

const route = useRoute()
const router = useRouter()
const filters = computed(() => catalogFilters(route.query))
const search = ref(filters.value.q ?? '')
const debouncedSearch = refDebounced(search, 250)
watch(
  () => route.query.q,
  () => {
    search.value = filters.value.q ?? ''
  },
)
watch(debouncedSearch, (value) => {
  // Wstecz nie może zostać nadpisane spóźnionym debounce.
  if (value !== search.value || value.trim() === (filters.value.q ?? '')) return
  updateFilters({ q: value.trim() || undefined })
})

const SCOPE_FILTERS: readonly { value: RecipeScope | undefined; label: string }[] = [
  { value: undefined, label: texts.scopeFilterAll },
  { value: 'global', label: texts.scopeLabels.global },
  { value: 'household', label: texts.scopeLabels.household },
  { value: 'private', label: texts.scopeLabels.private },
]
const tags = useQuery({ queryKey: queryKeys.tags.all, queryFn: fetchTags, retry: false })
const advancedFilterCount = computed(
  () => (filters.value.scope ? 1 : 0) + (filters.value.tag?.length ?? 0),
)
const activeFilterLabels = computed(() => [
  ...(filters.value.q ? [`Nazwa: „${filters.value.q}”`] : []),
  ...(filters.value.prep_time_max ? [texts.quickFilter] : []),
  ...(filters.value.scope ? [`Widoczność: ${texts.scopeLabels[filters.value.scope]}`] : []),
  ...(filters.value.tag ?? []).map(
    (id) => `Tag: ${tags.data.value?.items.find((tag) => tag.id === id)?.name ?? `#${id}`}`,
  ),
])
const recipes = usePaginatedList({
  queryKey: computed(() => queryKeys.recipes.list(filters.value)),
  fetchPage: (page) => fetchRecipes({ ...filters.value, ...page }),
})
const isFiltering = computed(
  () =>
    !!(
      filters.value.q ||
      filters.value.tag?.length ||
      filters.value.scope ||
      filters.value.prep_time_max
    ),
)
const selectedRecipe = ref<RecipeSummary | null>(null)
const panelOpen = ref(false)
const navigation = computed(() => planNavigationContext(route))

function updateFilters(patch: {
  q?: string
  scope?: RecipeScope
  tag?: string[]
  prep_time_max?: string
}): void {
  void router.replace({ query: { ...route.query, ...patch } })
}
function toggleTag(tagId: number): void {
  const selected = filters.value.tag ?? []
  const next = selected.includes(tagId)
    ? selected.filter((id) => id !== tagId)
    : [...selected, tagId]
  updateFilters({ tag: next.sort((a, b) => a - b).map(String) })
}
function clearFilters(): void {
  search.value = ''
  updateFilters({ q: undefined, tag: undefined, scope: undefined, prep_time_max: undefined })
}
function plan(recipe: RecipeSummary): void {
  selectedRecipe.value = recipe
  panelOpen.value = true
}
function planned({ day }: { day: PlanDay }): void {
  panelOpen.value = false
  void router.push(
    planNavigationTarget('plan-dnia', { ...navigation.value, selectedDate: day.day }),
  )
}
</script>

<template>
  <section class="grid min-w-0 gap-3 sm:gap-4" data-testid="przepisy-page">
    <PageHeader
      title="Co ugotujesz?"
      description="Twoja rodzinna książka kucharska."
      decoration="herbs"
      class="!py-4"
    />

    <div class="grid min-w-0 gap-3">
      <div class="flex min-w-0 items-end gap-2">
        <label class="grid min-w-0 max-w-xl flex-1 gap-2 text-sm font-medium">
          Szukaj przepisu
          <span class="relative">
            <Search
              class="text-muted-foreground pointer-events-none absolute top-3 left-3 size-5"
              aria-hidden="true"
            />
            <Input
              v-model="search"
              type="search"
              maxlength="200"
              class="min-h-11 pl-10"
              :placeholder="texts.searchPlaceholder"
              data-testid="recipes-search"
            />
          </span>
        </label>
        <Button as-child variant="outline">
          <RouterLink
            :to="{ name: 'przepis-nowy', query: catalogQuery(route.query) }"
            data-testid="recipes-add"
          >
            <Plus class="size-4" aria-hidden="true" />
            {{ texts.createTitle }}
          </RouterLink>
        </Button>
      </div>

      <div class="flex flex-wrap items-start gap-2">
        <Button
          type="button"
          :variant="filters.prep_time_max ? 'default' : 'outline'"
          :aria-pressed="!!filters.prep_time_max"
          data-testid="recipes-quick"
          @click="updateFilters({ prep_time_max: filters.prep_time_max ? undefined : '30' })"
        >
          {{ texts.quickFilter }}
        </Button>
        <details class="group min-w-0 open:basis-full" data-testid="recipes-filters">
          <summary
            class="border-input bg-card focus-visible:ring-ring flex min-h-11 max-w-full cursor-pointer list-none flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium break-words focus-visible:ring-3 focus-visible:outline-none [&::-webkit-details-marker]:hidden"
            data-testid="recipes-filters-toggle"
          >
            Pozostałe filtry<span v-if="advancedFilterCount">({{ advancedFilterCount }})</span>
            <ChevronDown
              class="ml-auto size-4 shrink-0 transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <div class="border-border mt-3 grid gap-3 border-l-2 pl-3">
            <ul class="flex flex-wrap gap-2" :aria-label="texts.scopeFilterLabel">
              <li v-for="option in SCOPE_FILTERS" :key="option.value ?? 'all'">
                <Button
                  type="button"
                  :variant="filters.scope === option.value ? 'default' : 'outline'"
                  :aria-pressed="filters.scope === option.value"
                  :data-testid="`recipes-scope-${option.value ?? 'all'}`"
                  @click="updateFilters({ scope: option.value })"
                  >{{ option.label }}</Button
                >
              </li>
            </ul>
            <ErrorState
              v-if="tags.isError.value"
              compact
              title="Nie udało się odświeżyć tagów"
              message="Wybrane filtry nadal obowiązują. Spróbuj ponownie pobrać tagi."
              :pending="tags.isFetching.value"
              data-testid="recipes-tags-error"
              @retry="tags.refetch()"
            />
            <ul
              v-if="tags.data.value?.items.length"
              class="flex flex-wrap gap-2"
              aria-label="Tagi — przepis musi mieć wszystkie wybrane"
            >
              <li v-for="tag in tags.data.value.items" :key="tag.id" class="min-w-0 max-w-full">
                <Button
                  type="button"
                  class="h-auto max-w-full py-2 whitespace-normal"
                  :variant="filters.tag?.includes(tag.id) ? 'default' : 'outline'"
                  :aria-pressed="!!filters.tag?.includes(tag.id)"
                  :data-testid="`recipes-tag-${tag.id}`"
                  @click="toggleTag(tag.id)"
                >
                  <span class="break-words">{{ tag.name }}</span>
                </Button>
              </li>
            </ul>
          </div>
        </details>
        <Button
          v-if="isFiltering"
          type="button"
          variant="ghost"
          data-testid="recipes-clear"
          @click="clearFilters"
        >
          Wyczyść filtry
        </Button>
      </div>
      <p
        v-if="isFiltering"
        class="text-muted-foreground text-sm leading-relaxed break-words"
        role="status"
        data-testid="recipes-active-filters"
      >
        Aktywne filtry ({{ activeFilterLabels.length }}): {{ activeFilterLabels.join(' · ') }}
      </p>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-2">
      <p
        class="text-muted-foreground text-sm tabular-nums"
        data-testid="recipes-total"
        role="status"
      >
        Przepisów: {{ listCount(recipes.loaded.value, recipes.total.value) }}
      </p>
      <Button
        type="button"
        variant="ghost"
        :disabled="recipes.isPending.value || recipes.isRefreshing.value"
        data-testid="recipes-refresh"
        @click="recipes.refresh"
      >
        {{ recipes.isRefreshing.value ? 'Odświeżanie…' : 'Odśwież' }}
      </Button>
    </div>

    <LoadingState v-if="recipes.isPending.value" :label="common.loading" />
    <ErrorState
      v-else-if="recipes.isError.value"
      message="Nie udało się pobrać przepisów. Spróbuj ponownie."
      :pending="recipes.isRefreshing.value"
      data-testid="recipes-error"
      @retry="recipes.refresh"
    />
    <template v-else>
      <ErrorState
        v-if="recipes.refreshFailed.value"
        compact
        title="Nie udało się odświeżyć przepisów"
        message="Nadal widzisz ostatnio pobrane wyniki. Spróbuj ponownie."
        :pending="recipes.isRefreshing.value"
        data-testid="recipes-refresh-error"
        @retry="recipes.refresh"
      />
      <EmptyState
        v-if="!recipes.items.value.length"
        :title="isFiltering ? 'Brak wyników' : 'Twoja książka kucharska'"
        :description="isFiltering ? texts.emptySearch : texts.emptyState"
        data-testid="recipes-empty"
      >
        <template #action>
          <Button v-if="isFiltering" type="button" variant="outline" @click="clearFilters"
            >Wyczyść filtry</Button
          >
          <Button as-child>
            <RouterLink
              :to="{ name: 'przepis-nowy', query: catalogQuery(route.query) }"
              data-testid="recipes-empty-add"
              >{{ texts.addRecipe }}</RouterLink
            >
          </Button>
        </template>
      </EmptyState>
      <ul
        v-else
        class="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-3"
        data-testid="recipes-list"
      >
        <li v-for="recipe in recipes.items.value" :key="recipe.id" class="min-w-0">
          <RecipeCard
            :recipe="recipe"
            :to="{
              name: 'przepis-szczegol',
              params: { id: recipe.id },
              query: catalogQuery(route.query),
            }"
            @plan="plan"
          />
        </li>
      </ul>
      <LoadMoreButton
        :loaded="recipes.loaded.value"
        :total="recipes.total.value"
        :has-more="recipes.hasMore.value"
        :loading="recipes.isLoadingMore.value"
        :failed="recipes.nextPageFailed.value"
        testid="recipes-load-more"
        @more="recipes.loadMore"
      />
    </template>

    <RecipePlanningPanel
      :open="panelOpen"
      :recipe="selectedRecipe"
      :date="navigation.selectedDate"
      @close="panelOpen = false"
      @saved="planned"
    />
  </section>
</template>
