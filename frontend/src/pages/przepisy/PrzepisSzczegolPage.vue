<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { CalendarPlus, Clock, Heart, LoaderCircle, Star } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  archiveRecipe,
  copyRecipe,
  deleteRecipe,
  fetchRecipe,
  rateRecipe,
  unarchiveRecipe,
} from '@/api/recipes'
import type { RecipeDetail } from '@/api/recipes'
import type { PlanDay } from '@/api/planning'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import ErrorState from '@/components/domain/ErrorState.vue'
import FeedbackMessage from '@/components/domain/FeedbackMessage.vue'
import LoadingState from '@/components/domain/LoadingState.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import RecipeImage from '@/components/domain/RecipeImage.vue'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import { Button } from '@/components/ui/button'
import { decimalsEqual, sumDecimals } from '@/lib/decimal'
import { formatAmount, formatDecimal } from '@/lib/format'
import { planNavigationContext, planNavigationTarget } from '@/lib/navigation'
import { common, recipes as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'
import { catalogQuery, returnToCatalog } from './catalogNavigation'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const queryClient = useQueryClient()
const recipeId = computed(() => Number(route.params.id))
const servings = ref('1')
const actionError = ref<string | null>(null)
const actionSuccess = ref<string | null>(null)
const usedInNames = ref<string[]>([])
const panelOpen = ref(false)
// Pamiętamy wyłącznie klucz ostatniego potwierdzonego odczytu; dane zostają w Query.
const confirmedKey = ref<readonly unknown[] | null>(null)
watch(recipeId, () => {
  servings.value = '1'
  actionError.value = null
  actionSuccess.value = null
  usedInNames.value = []
  panelOpen.value = false
  confirmedKey.value = null
})

const recipe = useQuery({
  queryKey: computed(() => queryKeys.recipes.detail(recipeId.value, servings.value)),
  queryFn: () => fetchRecipe(recipeId.value, servings.value),
  // Skalowanie zachowuje poprzedni wynik tego samego przepisu, nigdy innego ID.
  placeholderData: (previous) => (previous?.id === recipeId.value ? previous : undefined),
  retry: false,
})
watch(
  recipe.data,
  (data) => {
    if (data && !recipe.isPlaceholderData.value && data.id === recipeId.value)
      confirmedKey.value = queryKeys.recipes.detail(recipeId.value, servings.value)
  },
  { immediate: true },
)
const detail = computed(
  () =>
    recipe.data.value ??
    (confirmedKey.value ? queryClient.getQueryData<RecipeDetail>(confirmedKey.value) : null) ??
    null,
)
const isGlobal = computed(() => detail.value?.scope === 'global')
const ratingDraft = ref<number | null>(null)
watch(
  () => detail.value?.my_rating,
  (rating) => {
    ratingDraft.value = rating ?? null
  },
  { immediate: true },
)
const canEdit = computed(() => detail.value !== null && (!isGlobal.value || auth.isAdmin))
const canManage = computed(
  () =>
    detail.value !== null &&
    (auth.isAdmin || (!isGlobal.value && detail.value.owner_user_id === auth.user?.id)),
)
const canCopy = computed(
  () => detail.value !== null && (isGlobal.value || detail.value.owner_user_id !== auth.user?.id),
)
const isFavorite = computed(() => detail.value?.tags.some((tag) => tag.name === texts.favoriteTag))
const navigation = computed(() => planNavigationContext(route))

function clearAction(): void {
  actionError.value = null
  actionSuccess.value = null
  usedInNames.value = []
}
function reportError(error: unknown): void {
  actionSuccess.value = null
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
  const references: unknown = error instanceof ApiError ? error.details.used_in : null
  usedInNames.value = Array.isArray(references)
    ? references.flatMap((entry: unknown) => {
        if (entry && typeof entry === 'object' && 'name' in entry && typeof entry.name === 'string')
          return [entry.name]
        return []
      })
    : []
}
function changeServings(step: '0.5' | '-0.5'): void {
  if (
    (step === '-0.5' && decimalsEqual(servings.value, '0.5')) ||
    (step === '0.5' && decimalsEqual(servings.value, '100'))
  )
    return
  servings.value = sumDecimals([servings.value, step])
}

const rate = useMutation({
  mutationFn: (rating: number) => rateRecipe(recipeId.value, rating),
  onMutate: clearAction,
  onSuccess: async (saved) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    ratingDraft.value = saved.my_rating
    actionSuccess.value = 'Ocena została zapisana.'
  },
  onError: (error) => {
    ratingDraft.value = detail.value?.my_rating ?? null
    reportError(error)
  },
})
const remove = useMutation({
  mutationFn: () => deleteRecipe(recipeId.value),
  onMutate: clearAction,
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    await router.push({ name: 'przepisy', query: catalogQuery(route.query) })
  },
  onError: reportError,
})
const copy = useMutation({
  mutationFn: () => copyRecipe(recipeId.value),
  onMutate: clearAction,
  onSuccess: async (copied) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    queryClient.setQueryData(queryKeys.recipes.detail(copied.id, '1'), copied)
    await router.push({
      name: 'przepis-szczegol',
      params: { id: copied.id },
      query: catalogQuery(route.query),
    })
    actionSuccess.value = 'Utworzono własną kopię przepisu.'
  },
  onError: reportError,
})
const toggleArchive = useMutation({
  mutationFn: () =>
    detail.value?.is_archived ? unarchiveRecipe(recipeId.value) : archiveRecipe(recipeId.value),
  onMutate: clearAction,
  onSuccess: async (updated) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    actionSuccess.value = updated.is_archived
      ? 'Przepis został zarchiwizowany.'
      : 'Przepis został przywrócony z archiwum.'
  },
  onError: reportError,
})
const actionPending = computed(
  () =>
    rate.isPending.value ||
    remove.isPending.value ||
    copy.isPending.value ||
    toggleArchive.isPending.value,
)
function confirmRemove(): void {
  if (window.confirm(texts.confirmDelete)) remove.mutate()
}
function backToList(event: MouseEvent, navigate: (event: MouseEvent) => unknown): void {
  returnToCatalog(event, router, route.query)
  if (!event.defaultPrevented) void navigate(event)
}
function planned({ day }: { day: PlanDay }): void {
  panelOpen.value = false
  void router.push(
    planNavigationTarget('plan-dnia', { ...navigation.value, selectedDate: day.day }),
  )
}
const nutritionRows = computed(() => {
  if (!detail.value) return []
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
</script>

<template>
  <section class="grid min-w-0 gap-6" data-testid="przepis-szczegol-page">
    <RouterLink
      v-slot="{ href, navigate }"
      :to="{ name: 'przepisy', query: catalogQuery(route.query) }"
      custom
    >
      <Button as-child variant="ghost" class="justify-self-start">
        <a :href="href" data-testid="recipe-back" @click="backToList($event, navigate)">
          {{ texts.backToList }}
        </a>
      </Button>
    </RouterLink>

    <LoadingState v-if="recipe.isPending.value && !detail" :label="common.loading" />
    <ErrorState
      v-else-if="recipe.isError.value && !detail"
      message="Nie udało się pobrać przepisu. Spróbuj ponownie."
      :pending="recipe.isFetching.value"
      data-testid="recipe-error"
      @retry="recipe.refetch()"
    />

    <template v-if="detail">
      <PageHeader
        :title="detail.name"
        :eyebrow="texts.scopeLabels[detail.scope]"
        title-testid="recipe-name"
        decoration="pot"
      >
        <p class="text-muted-foreground text-sm" data-testid="recipe-scope-badge">
          {{ texts.scopeLabels[detail.scope] }}
          <span v-if="detail.is_archived"> · {{ texts.archived }}</span>
        </p>
        <div
          class="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 text-sm tabular-nums"
        >
          <span v-if="detail.prep_time_min !== null" class="inline-flex items-center gap-1">
            <Clock class="size-4" aria-hidden="true" />{{ detail.prep_time_min }}
            {{ texts.minutesShort }}
          </span>
          <span>Z przepisu: {{ detail.base_servings }} porcji</span>
          <span v-if="detail.difficulty"
            >{{ texts.difficultyLabel }}: {{ detail.difficulty }}/10</span
          >
          <span
            v-if="detail.avg_rating !== null"
            class="inline-flex items-center gap-1"
            :aria-label="texts.avgRatingLabel"
          >
            <Star class="text-warning fill-warning size-4" aria-hidden="true" />
            {{ formatDecimal(detail.avg_rating) }} ({{ detail.ratings_count }})
          </span>
          <span v-else>{{ texts.noRatings }}</span>
        </div>
        <ul v-if="detail.tags.length" class="flex flex-wrap gap-2" aria-label="Tagi">
          <li
            v-for="tag in detail.tags"
            :key="tag.id"
            class="bg-card text-muted-foreground inline-flex max-w-full items-center gap-1 rounded-lg px-2 py-1 text-xs break-words"
          >
            <Heart
              v-if="tag.name === texts.favoriteTag"
              class="text-primary fill-primary size-3 shrink-0"
              aria-hidden="true"
            />
            {{ tag.name }}
          </li>
        </ul>
        <template #actions>
          <Button type="button" data-testid="recipe-plan" @click="panelOpen = true">
            <CalendarPlus class="size-4" aria-hidden="true" /> {{ texts.planAction }}
          </Button>
          <Button v-if="canEdit" as-child variant="outline">
            <RouterLink
              :to="{
                name: 'przepis-edycja',
                params: { id: detail.id },
                query: catalogQuery(route.query),
              }"
              data-testid="recipe-edit"
              >{{ common.edit }}</RouterLink
            >
          </Button>
          <Button
            v-if="canCopy"
            type="button"
            variant="outline"
            class="h-auto py-2 whitespace-normal"
            :disabled="actionPending"
            data-testid="recipe-copy"
            @click="copy.mutate()"
          >
            <LoaderCircle
              v-if="copy.isPending.value"
              class="size-4 animate-spin motion-reduce:animate-none"
              aria-hidden="true"
            />
            {{ copy.isPending.value ? texts.copying : texts.copyToMyHousehold }}
          </Button>
        </template>
      </PageHeader>

      <p
        v-if="isGlobal && !auth.isAdmin"
        class="text-muted-foreground text-sm"
        data-testid="recipe-read-only"
      >
        {{ texts.globalReadOnlyHint }}
      </p>
      <p
        v-if="isFavorite"
        class="text-muted-foreground flex items-center gap-2 text-sm"
        data-testid="recipe-favorite-tag"
      >
        <Heart class="text-primary fill-primary size-4" aria-hidden="true" />
        {{ texts.favoriteTagLabel }}
      </p>
      <p
        v-if="actionError"
        class="text-destructive text-sm"
        role="alert"
        data-testid="recipe-action-error"
      >
        {{ actionError }}
      </p>
      <div v-if="usedInNames.length" class="text-destructive text-sm" data-testid="recipe-used-in">
        <p>{{ texts.usedInIntro }}</p>
        <ul class="list-inside list-disc">
          <li v-for="name in usedInNames" :key="name" class="break-words">{{ name }}</li>
        </ul>
      </div>
      <FeedbackMessage
        v-if="actionSuccess"
        :message="actionSuccess"
        tone="success"
        data-testid="recipe-success"
      />
      <ErrorState
        v-if="recipe.isError.value || (recipe.isPlaceholderData.value && !recipe.isFetching.value)"
        compact
        title="Nie udało się przeliczyć lub odświeżyć przepisu"
        message="Poniżej są ostatnio potwierdzone dane. Ponów odczyt, aby zobaczyć aktualne wartości."
        :pending="recipe.isFetching.value"
        data-testid="recipe-refresh-error"
        @retry="recipe.refetch()"
      />

      <div v-if="detail.photo_url" class="max-w-2xl overflow-hidden rounded-2xl">
        <RecipeImage
          :src="detail.photo_url"
          :alt="`Zdjęcie: ${detail.name}`"
          class="!aspect-[16/7]"
          loading="eager"
        />
      </div>

      <div class="bg-muted flex flex-wrap items-center gap-3 rounded-xl p-4">
        <span class="text-sm font-semibold">{{ texts.servingsLabel }}</span>
        <div class="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            class="min-w-11"
            aria-label="Mniej porcji"
            :disabled="decimalsEqual(servings, '0.5')"
            data-testid="servings-decrease"
            @click="changeServings('-0.5')"
            >−</Button
          >
          <span
            class="min-w-10 text-center text-lg font-semibold tabular-nums"
            data-testid="servings-value"
            >{{ formatDecimal(servings) }}</span
          >
          <Button
            type="button"
            variant="outline"
            class="min-w-11"
            aria-label="Więcej porcji"
            :disabled="decimalsEqual(servings, '100')"
            data-testid="servings-increase"
            @click="changeServings('0.5')"
            >+</Button
          >
        </div>
        <span
          v-if="recipe.isFetching.value"
          class="text-muted-foreground inline-flex items-center gap-2 text-sm"
          role="status"
        >
          <LoaderCircle class="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          Przeliczanie…
        </span>
        <p class="text-muted-foreground basis-full text-sm" data-testid="recipe-scaled-for">
          Składniki i wartości dla {{ formatDecimal(detail.servings) }} porcji.
        </p>
      </div>

      <p
        v-if="!detail.nutrition.complete"
        class="bg-warning/15 text-warning rounded-lg px-3 py-2 text-sm break-words"
        :title="detail.nutrition.missing.join(', ')"
        data-testid="recipe-incomplete"
      >
        {{ texts.incompleteData }}: {{ detail.nutrition.missing.join(', ') }}
      </p>

      <div class="grid min-w-0 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        <section
          class="grid min-w-0 gap-4"
          aria-labelledby="ingredients-heading"
          data-testid="recipe-ingredients"
        >
          <h2 id="ingredients-heading" class="text-xl font-semibold">{{ texts.tabIngredients }}</h2>
          <p v-if="!detail.ingredients.length" class="text-muted-foreground text-sm">
            {{ texts.ingredientsEmpty }}
          </p>
          <ul v-else class="divide-border divide-y">
            <li
              v-for="ingredient in detail.ingredients"
              :key="ingredient.id"
              class="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 py-3"
              :data-testid="`recipe-ingredient-${ingredient.id}`"
            >
              <span class="min-w-0 text-sm leading-relaxed break-words"
                >{{ ingredient.product_name }}
                <span v-if="ingredient.note" class="text-muted-foreground">
                  · {{ ingredient.note }}</span
                >
              </span>
              <span
                class="max-w-28 text-right text-sm leading-relaxed font-medium break-words tabular-nums"
                >{{ formatAmount(ingredient.scaled_amount, ingredient.amount_unit) }}</span
              >
            </li>
          </ul>
        </section>
        <section
          class="grid min-w-0 gap-4"
          aria-labelledby="instructions-heading"
          data-testid="recipe-instructions"
        >
          <h2 id="instructions-heading" class="text-xl font-semibold">
            {{ texts.tabInstructions }}
          </h2>
          <p
            class="text-sm leading-relaxed break-words whitespace-pre-line"
            :class="!detail.instructions && 'text-muted-foreground'"
          >
            {{ detail.instructions || texts.instructionsEmpty }}
          </p>
        </section>
      </div>

      <details class="border-border rounded-xl border p-4" data-testid="recipe-nutrition">
        <summary
          class="focus-visible:ring-ring flex min-h-11 cursor-pointer items-center text-sm font-semibold focus-visible:ring-2"
        >
          {{ texts.tabNutrition }} i kompletność danych
        </summary>
        <p class="text-muted-foreground py-3 text-sm">
          Wartości dla {{ formatDecimal(detail.servings) }} porcji.
          {{ detail.nutrition.complete ? 'Dane kompletne.' : texts.incompleteData }}
        </p>
        <dl class="grid gap-2 sm:grid-cols-2">
          <div
            v-for="row in nutritionRows"
            :key="row.label"
            class="border-border flex flex-wrap items-center justify-between gap-2 border-b py-3"
          >
            <dt class="text-muted-foreground text-sm">{{ row.label }}</dt>
            <dd class="text-sm font-medium tabular-nums" :data-testid="`nutrition-${row.label}`">
              {{ row.value }}
            </dd>
          </div>
        </dl>
      </details>

      <fieldset :disabled="actionPending" class="border-border grid min-w-0 gap-2 border-t pt-4">
        <legend class="text-sm font-semibold">{{ texts.ratingLabel }}</legend>
        <div class="flex flex-wrap gap-1">
          <label v-for="value in [1, 2, 3, 4, 5]" :key="value" class="relative">
            <input
              v-model="ratingDraft"
              type="radio"
              name="recipe-rating"
              class="peer sr-only"
              :value="value"
              :aria-label="`Ocena ${value} na 5`"
              :data-testid="`recipe-rate-${value}`"
              @change="rate.mutate(value)"
            />
            <span
              class="peer-focus-visible:ring-ring flex min-h-11 min-w-11 items-center justify-center rounded-lg peer-focus-visible:ring-2 peer-disabled:opacity-50"
            >
              <Star
                class="size-6"
                :class="
                  detail.my_rating !== null && value <= detail.my_rating
                    ? 'text-warning fill-warning'
                    : 'text-muted-foreground'
                "
                aria-hidden="true"
              />
            </span>
          </label>
          <LoaderCircle
            v-if="rate.isPending.value"
            class="my-auto size-4 animate-spin motion-reduce:animate-none"
            aria-label="Zapisywanie oceny"
          />
        </div>
      </fieldset>

      <div
        v-if="auth.isAdmin || canManage"
        class="border-border flex flex-wrap gap-2 border-t pt-4"
      >
        <Button
          v-if="auth.isAdmin"
          type="button"
          variant="ghost"
          :disabled="actionPending"
          :data-testid="detail.is_archived ? 'recipe-unarchive' : 'recipe-archive'"
          @click="toggleArchive.mutate()"
        >
          <LoaderCircle
            v-if="toggleArchive.isPending.value"
            class="size-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
          {{ detail.is_archived ? texts.unarchiveAction : texts.archiveAction }}
        </Button>
        <Button
          v-if="canManage"
          type="button"
          variant="ghost"
          :disabled="actionPending"
          data-testid="recipe-delete"
          @click="confirmRemove()"
        >
          <LoaderCircle
            v-if="remove.isPending.value"
            class="size-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
          {{ common.remove }}
        </Button>
      </div>
    </template>
    <RecipePlanningPanel
      :open="panelOpen"
      :recipe="detail"
      :date="navigation.selectedDate"
      @close="panelOpen = false"
      @saved="planned"
    />
  </section>
</template>
