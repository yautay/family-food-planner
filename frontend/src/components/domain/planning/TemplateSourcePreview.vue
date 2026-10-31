<script setup lang="ts">
import { useQueries } from '@tanstack/vue-query'
import { computed, watch } from 'vue'
import { fetchProduct } from '@/api/catalog'
import { fetchRecipe } from '@/api/recipes'
import { queryKeys } from '@/api/queryKeys'
import { fetchDayTemplate, fetchWeekTemplate } from '@/api/templates'
import type { DayTemplate, WeekTemplate } from '@/api/templates'
import { Button } from '@/components/ui/button'

const props = defineProps<{ references: { kind: 'day' | 'week'; id: number }[] }>()
const emit = defineEmits<{ ready: [ready: boolean] }>()
const sources = useQueries({
  queries: computed(() =>
    props.references.map((reference) => ({
      queryKey:
        reference.kind === 'day'
          ? queryKeys.templates.day(reference.id)
          : queryKeys.templates.week(reference.id),
      queryFn: (): Promise<DayTemplate | WeekTemplate> =>
        reference.kind === 'day' ? fetchDayTemplate(reference.id) : fetchWeekTemplate(reference.id),
      retry: false,
      staleTime: 0,
    })),
  ),
})
const contents = computed(() =>
  sources.value.flatMap((q) => {
    const payload = q.data?.payload
    if (!payload) return []
    return 'days' in payload
      ? (payload.days?.map((entry) => entry.day) ?? [])
      : 'meals' in payload
        ? [payload]
        : []
  }),
)
const items = computed(() =>
  contents.value.flatMap((day) => day.meals ?? []).flatMap((meal) => meal.items ?? []),
)
const recipeIds = computed(() => [
  ...new Set(items.value.flatMap((item) => (item.recipe_id ? [item.recipe_id] : []))),
])
const productIds = computed(() => [
  ...new Set(items.value.flatMap((item) => (item.product_id ? [item.product_id] : []))),
])
const recipes = useQueries({
  queries: computed(() =>
    recipeIds.value.map((id) => ({
      queryKey: queryKeys.recipes.detail(id, '1'),
      queryFn: () => fetchRecipe(id, '1'),
      retry: false,
      staleTime: 0,
    })),
  ),
})
const products = useQueries({
  queries: computed(() =>
    productIds.value.map((id) => ({
      queryKey: queryKeys.products.detail(id),
      queryFn: () => fetchProduct(id),
      retry: false,
      staleTime: 0,
    })),
  ),
})
const loading = computed(() =>
  [...sources.value, ...recipes.value, ...products.value].some((q) => q.isPending || q.isFetching),
)
const failed = computed(() =>
  [...sources.value, ...recipes.value, ...products.value].some((q) => q.isError),
)
const ready = computed(() => props.references.length > 0 && !loading.value && !failed.value)
watch(ready, (value) => emit('ready', value), { immediate: true })
const archived = computed(() =>
  [...recipes.value, ...products.value].flatMap((q) => (q.data?.is_archived ? [q.data.name] : [])),
)
const mealNames = computed(() => [
  ...new Set(contents.value.flatMap((day) => day.meals ?? []).map((meal) => meal.name)),
])
</script>

<template>
  <section
    class="grid gap-2 text-sm"
    aria-label="Zawartość szablonu"
    data-testid="template-source-preview"
  >
    <p v-if="loading" role="status">Sprawdzamy zawartość szablonu…</p>
    <div v-else-if="failed" role="alert">
      <p>Nie udało się sprawdzić szablonu lub jego dań. Ponów odczyt przed zapisem.</p>
      <Button
        type="button"
        variant="outline"
        class="mt-2 min-h-11"
        @click="[...sources, ...recipes, ...products].forEach((q) => q.refetch())"
        >Ponów odczyt szablonu</Button
      >
    </div>
    <template v-else-if="ready">
      <p class="break-words">Posiłki w źródle: {{ mealNames.join(', ') || 'brak posiłków' }}.</p>
      <ul
        v-if="archived.length"
        class="text-warning grid gap-1"
        data-testid="template-archive-warnings"
      >
        <li v-for="name in archived" :key="name">
          Pozycja archiwalna: {{ name }}. Zostanie użyta w planie.
        </li>
      </ul>
    </template>
  </section>
</template>
