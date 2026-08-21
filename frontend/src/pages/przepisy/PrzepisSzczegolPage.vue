<script setup lang="ts">
/**
 * Szczegóły przepisu (`/przepisy/:id`, widok 3): hero, meta, taby, ocena.
 *
 * Regulacja liczby porcji NA ŻYWO = refetch `GET /recipes/{id}?servings=`
 * z `placeholderData: keepPreviousData` — liczy backend (Decimal), frontend
 * tylko formatuje (05_FRONTEND §7). Plakietka „niepełne dane" ma tooltip
 * z listą braków (06_UIUX §3.5).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Clock, Star } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { deleteRecipe, fetchRecipe, rateRecipe } from '@/api/recipes'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { formatAmount, formatDecimal } from '@/lib/format'
import { common, recipes as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const queryClient = useQueryClient()

const recipeId = computed(() => Number(route.params.id))
/** Mnożnik porcji jako string dziesiętny — krok 0,5, minimum 0,5. */
const servings = ref('1')

const recipe = useQuery({
  queryKey: computed(() => queryKeys.recipes.detail(recipeId.value, servings.value)),
  queryFn: () => fetchRecipe(recipeId.value, servings.value),
  // Poprzednie wartości zostają na ekranie podczas przeliczania — zero migania.
  placeholderData: keepPreviousData,
})

const detail = computed(() => recipe.data.value ?? null)
const activeTab = ref<'ingredients' | 'instructions' | 'nutrition'>('ingredients')
const actionError = ref<string | null>(null)

const canManage = computed(
  () => detail.value !== null && (auth.isAdmin || detail.value.owner_user_id === auth.user?.id),
)

function changeServings(step: number): void {
  const current = Number(servings.value)
  const next = Math.min(100, Math.max(0.5, current + step))
  servings.value = String(next)
}

const rate = useMutation({
  mutationFn: (rating: number) => rateRecipe(recipeId.value, rating),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const remove = useMutation({
  mutationFn: () => deleteRecipe(recipeId.value),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    await router.push({ name: 'przepisy' })
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

function confirmRemove(): void {
  if (window.confirm(texts.confirmDelete)) {
    remove.mutate()
  }
}

const nutritionRows = computed(() => {
  if (!detail.value) {
    return []
  }
  const nutrition = detail.value.nutrition
  return [
    { label: 'Kalorie', value: `${formatDecimal(nutrition.kcal)} kcal` },
    { label: 'Białko', value: `${formatDecimal(nutrition.protein_g)} g` },
    { label: 'Tłuszcz', value: `${formatDecimal(nutrition.fat_g)} g` },
    { label: 'Węglowodany', value: `${formatDecimal(nutrition.carbs_g)} g` },
    { label: 'Błonnik', value: `${formatDecimal(nutrition.fiber_g)} g` },
    { label: 'Cukry', value: `${formatDecimal(nutrition.sugars_g)} g` },
    { label: texts.glycemicLoadLabel, value: formatDecimal(nutrition.glycemic_load) },
  ]
})

const TABS = [
  { id: 'ingredients', label: texts.tabIngredients },
  { id: 'instructions', label: texts.tabInstructions },
  { id: 'nutrition', label: texts.tabNutrition },
] as const
</script>

<template>
  <section class="grid gap-6" data-testid="przepis-szczegol-page">
    <p v-if="recipe.isPending.value" class="text-muted-foreground text-sm">
      {{ common.loading }}
    </p>
    <p v-else-if="recipe.isError.value" class="text-destructive text-sm" role="alert">
      {{ common.unexpectedError }}
    </p>

    <template v-else-if="detail">
      <header class="grid gap-3">
        <Button as-child variant="ghost" class="min-h-11 justify-self-start">
          <RouterLink :to="{ name: 'przepisy' }" data-testid="recipe-back">
            {{ texts.backToList }}
          </RouterLink>
        </Button>

        <div v-if="detail.photo_url" class="overflow-hidden rounded-xl">
          <img
            :src="detail.photo_url"
            :alt="`Zdjęcie: ${detail.name}`"
            class="max-h-80 w-full object-cover"
          />
        </div>

        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="grid gap-1">
            <h1 class="text-2xl font-semibold" data-testid="recipe-name">{{ detail.name }}</h1>
            <p class="text-muted-foreground flex flex-wrap items-center gap-3 text-sm tabular-nums">
              <span v-if="detail.prep_time_min" class="inline-flex items-center gap-1">
                <Clock class="size-4" aria-hidden="true" />
                {{ detail.prep_time_min }} {{ texts.minutesShort }}
              </span>
              <span v-if="detail.difficulty"
                >{{ texts.difficultyLabel }}: {{ detail.difficulty }}/10</span
              >
              <span v-if="detail.avg_rating" class="inline-flex items-center gap-1">
                <Star class="text-warning fill-warning size-4" aria-hidden="true" />
                {{ formatDecimal(detail.avg_rating) }} ({{ detail.ratings_count }})
              </span>
              <span v-else>{{ texts.noRatings }}</span>
            </p>
            <ul v-if="detail.tags.length" class="flex flex-wrap gap-1" aria-label="Tagi">
              <li
                v-for="tag in detail.tags"
                :key="tag.id"
                class="bg-muted text-muted-foreground rounded-lg px-2 py-0.5 text-xs"
              >
                {{ tag.name }}
              </li>
            </ul>
          </div>

          <div class="flex gap-2">
            <Button as-child variant="outline" class="min-h-11">
              <RouterLink
                :to="{ name: 'przepis-edycja', params: { id: detail.id } }"
                data-testid="recipe-edit"
              >
                {{ common.edit }}
              </RouterLink>
            </Button>
            <Button
              v-if="canManage"
              type="button"
              variant="ghost"
              class="min-h-11"
              :disabled="remove.isPending.value"
              data-testid="recipe-delete"
              @click="confirmRemove()"
            >
              {{ common.remove }}
            </Button>
          </div>
        </div>

        <p v-if="actionError" class="text-destructive text-sm" role="alert">{{ actionError }}</p>

        <!-- Plakietka „niepełne dane" z tooltipem czego brakuje (06_UIUX §3.5). -->
        <p
          v-if="!detail.nutrition.complete"
          class="bg-warning/15 text-warning justify-self-start rounded-lg px-3 py-1 text-sm"
          :title="detail.nutrition.missing.join(', ')"
          data-testid="recipe-incomplete"
        >
          {{ texts.incompleteData }}: {{ detail.nutrition.missing.join(', ') }}
        </p>

        <!-- Regulacja liczby porcji — przelicza składniki i wartości na żywo. -->
        <div class="border-border flex items-center gap-3 rounded-xl border p-3">
          <span class="text-sm font-medium">{{ texts.servingsLabel }}</span>
          <Button
            type="button"
            variant="outline"
            class="min-h-11 min-w-11"
            aria-label="Mniej porcji"
            data-testid="servings-decrease"
            @click="changeServings(-0.5)"
          >
            −
          </Button>
          <span
            class="min-w-10 text-center text-lg font-semibold tabular-nums"
            data-testid="servings-value"
          >
            {{ formatDecimal(servings) }}
          </span>
          <Button
            type="button"
            variant="outline"
            class="min-h-11 min-w-11"
            aria-label="Więcej porcji"
            data-testid="servings-increase"
            @click="changeServings(0.5)"
          >
            +
          </Button>
          <span v-if="recipe.isFetching.value" class="text-muted-foreground text-xs">
            {{ common.loading }}
          </span>
        </div>
      </header>

      <nav class="border-border flex gap-1 border-b" aria-label="Sekcje przepisu">
        <button
          v-for="tab in TABS"
          :key="tab.id"
          type="button"
          class="min-h-11 rounded-t-lg px-4 text-sm font-medium"
          :class="
            activeTab === tab.id
              ? 'border-border bg-card border border-b-0'
              : 'text-muted-foreground hover:bg-muted'
          "
          :aria-selected="activeTab === tab.id"
          role="tab"
          :data-testid="`recipe-tab-${tab.id}`"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </nav>

      <div v-if="activeTab === 'ingredients'" class="grid gap-2" data-testid="recipe-ingredients">
        <p v-if="!detail.ingredients.length" class="text-muted-foreground text-sm">
          {{ texts.ingredientsEmpty }}
        </p>
        <ul v-else class="grid gap-2">
          <li
            v-for="ingredient in detail.ingredients"
            :key="ingredient.id"
            class="border-border flex items-center justify-between gap-2 rounded-lg border p-3"
            :data-testid="`recipe-ingredient-${ingredient.id}`"
          >
            <span class="min-w-0 truncate text-sm">
              {{ ingredient.product_name }}
              <span v-if="ingredient.note" class="text-muted-foreground">
                · {{ ingredient.note }}</span
              >
            </span>
            <span class="shrink-0 text-sm font-medium tabular-nums">
              {{ formatAmount(ingredient.scaled_amount, ingredient.amount_unit) }}
            </span>
          </li>
        </ul>
      </div>

      <div
        v-else-if="activeTab === 'instructions'"
        class="grid gap-2"
        data-testid="recipe-instructions"
      >
        <p v-if="!detail.instructions" class="text-muted-foreground text-sm">
          {{ texts.instructionsEmpty }}
        </p>
        <p v-else class="text-sm whitespace-pre-line">{{ detail.instructions }}</p>
      </div>

      <div v-else class="grid gap-3" data-testid="recipe-nutrition">
        <dl class="grid gap-2 md:grid-cols-2">
          <div
            v-for="row in nutritionRows"
            :key="row.label"
            class="border-border flex items-center justify-between rounded-lg border p-3"
          >
            <dt class="text-muted-foreground text-sm">{{ row.label }}</dt>
            <dd class="text-sm font-medium tabular-nums" :data-testid="`nutrition-${row.label}`">
              {{ row.value }}
            </dd>
          </div>
        </dl>
      </div>

      <!-- Ocena 1-5: własna gwiazdka, średnia liczy się na nowo (upsert). -->
      <div class="border-border grid gap-2 rounded-xl border p-3">
        <span class="text-sm font-medium">{{ texts.ratingLabel }}</span>
        <div class="flex gap-1" role="radiogroup" :aria-label="texts.ratingLabel">
          <button
            v-for="value in [1, 2, 3, 4, 5]"
            :key="value"
            type="button"
            class="min-h-11 min-w-11 rounded-lg"
            role="radio"
            :aria-checked="detail.my_rating === value"
            :aria-label="`Ocena ${value} na 5`"
            :disabled="rate.isPending.value"
            :data-testid="`recipe-rate-${value}`"
            @click="rate.mutate(value)"
          >
            <Star
              class="mx-auto size-6"
              :class="
                detail.my_rating !== null && value <= detail.my_rating
                  ? 'text-warning fill-warning'
                  : 'text-muted-foreground'
              "
              aria-hidden="true"
            />
          </button>
        </div>
      </div>
    </template>
  </section>
</template>
