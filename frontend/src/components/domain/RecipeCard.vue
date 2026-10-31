<script setup lang="ts">
/**
 * Karta przepisu w gridzie (widok 2, 06_UIUX §4.2): zdjęcie, czas, kcal/porcję,
 * średnia ocen i serce dla tagu systemowego „ulubione".
 *
 * Karta jest czystą prezentacją — nawigację i akcje dostarcza strona listy.
 */
import { ArrowUpRight, CalendarPlus, Clock, Heart, Star, Users } from '@lucide/vue'
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import type { RecipeSummary } from '@/api/recipes'
import RecipeImage from '@/components/domain/RecipeImage.vue'
import { Button } from '@/components/ui/button'
import { formatDecimal } from '@/lib/format'
import { recipes as texts } from '@/lib/texts'

const props = defineProps<{ recipe: RecipeSummary; to?: RouteLocationRaw }>()
const emit = defineEmits<{ plan: [recipe: RecipeSummary] }>()

const isFavorite = computed(() => props.recipe.tags.some((tag) => tag.name === texts.favoriteTag))
const kcalPerPortion = computed(() => formatDecimal(props.recipe.nutrition.kcal))
const avgRating = computed(() =>
  props.recipe.avg_rating === null ? null : formatDecimal(props.recipe.avg_rating),
)
const missingTooltip = computed(() => props.recipe.nutrition.missing.join(', '))

/**
 * Odznaka zakresu (D32): nazwy przepisów mogą się powtarzać, więc kopia i jej
 * oryginał wyglądałyby na liście identycznie. Status zawsze kolor + tekst.
 */
const SCOPE_BADGE_CLASSES = {
  global: 'bg-primary/15 text-primary',
  household: 'bg-muted text-muted-foreground',
  private: 'border-border text-muted-foreground border',
} as const
const scopeBadge = computed(() => ({
  label: texts.scopeLabels[props.recipe.scope],
  classes: SCOPE_BADGE_CLASSES[props.recipe.scope],
}))
</script>

<template>
  <article
    class="border-border bg-card flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border shadow-sm"
    :data-testid="`recipe-card-${recipe.id}`"
  >
    <RecipeImage
      :src="recipe.photo_thumb_url ?? recipe.photo_url"
      :alt="`Zdjęcie: ${recipe.name}`"
      class="!aspect-auto"
      :class="recipe.photo_thumb_url || recipe.photo_url ? 'h-32 [&_img]:object-contain' : 'h-18'"
    >
      <!-- Serce = tag systemowy „ulubione" (świadome uproszczenie domowe z karty B05). -->
      <Heart
        v-if="isFavorite"
        class="text-primary fill-primary bg-card absolute top-3 right-3 size-9 rounded-full p-2"
        role="img"
        :aria-label="texts.favoriteTagLabel"
        :data-testid="`recipe-favorite-${recipe.id}`"
      />
    </RecipeImage>

    <div class="flex min-w-0 flex-1 flex-col gap-2 p-3 sm:gap-3 sm:p-5">
      <h2 class="text-lg leading-snug font-semibold break-words">{{ recipe.name }}</h2>
      <p
        class="justify-self-start rounded-lg px-2 py-0.5 text-xs"
        :class="scopeBadge.classes"
        :data-testid="`recipe-scope-badge-${recipe.id}`"
      >
        {{ scopeBadge.label }}
      </p>

      <p class="text-muted-foreground flex flex-wrap items-center gap-3 text-sm tabular-nums">
        <span v-if="recipe.prep_time_min !== null" class="inline-flex items-center gap-1">
          <Clock class="size-4" aria-hidden="true" />
          {{ recipe.prep_time_min }} {{ texts.minutesShort }}
        </span>
        <span class="inline-flex items-center gap-1">
          <Users class="size-4" aria-hidden="true" />
          {{ recipe.base_servings }} porcji bazowych
        </span>
        <span :data-testid="`recipe-kcal-${recipe.id}`">
          {{ kcalPerPortion }} {{ texts.kcalUnit }} {{ texts.perPortion }}
        </span>
        <span
          v-if="avgRating"
          class="inline-flex items-center gap-1"
          :aria-label="texts.avgRatingLabel"
        >
          <Star class="text-warning fill-warning size-4" aria-hidden="true" />
          {{ avgRating }}
        </span>
      </p>

      <ul v-if="recipe.tags.length" class="flex flex-wrap gap-1" aria-label="Tagi">
        <li
          v-for="tag in recipe.tags"
          :key="tag.id"
          class="bg-muted text-muted-foreground min-w-0 max-w-full rounded-lg px-2 py-0.5 text-xs break-words"
        >
          {{ tag.name }}
        </li>
      </ul>

      <!-- Status zawsze kolor + tekst, nigdy sam kolor (06_UIUX §1). -->
      <p
        v-if="!recipe.nutrition.complete"
        class="text-warning text-xs"
        :title="missingTooltip"
        :data-testid="`recipe-incomplete-${recipe.id}`"
      >
        {{ texts.incompleteData }}
      </p>
      <p v-if="recipe.is_archived" class="text-muted-foreground text-xs">{{ texts.archived }}</p>
      <div class="mt-auto flex flex-wrap items-center gap-2 pt-1">
        <Button
          type="button"
          :aria-label="`Zaplanuj: ${recipe.name}`"
          :data-testid="`recipe-plan-${recipe.id}`"
          @click="emit('plan', recipe)"
        >
          <CalendarPlus class="size-4" aria-hidden="true" />
          {{ texts.planAction }}
        </Button>
        <Button as-child variant="ghost">
          <RouterLink
            :to="to ?? { name: 'przepis-szczegol', params: { id: recipe.id } }"
            :aria-label="`Przepis: ${recipe.name}`"
            :data-testid="`recipe-open-${recipe.id}`"
          >
            {{ texts.detailAction }}
            <ArrowUpRight class="size-4" aria-hidden="true" />
          </RouterLink>
        </Button>
      </div>
    </div>
  </article>
</template>
