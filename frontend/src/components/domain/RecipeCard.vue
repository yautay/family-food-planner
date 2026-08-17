<script setup lang="ts">
/**
 * Karta przepisu w gridzie (widok 2, 06_UIUX §4.2): zdjęcie, czas, kcal/porcję,
 * średnia ocen i serce dla tagu systemowego „ulubione".
 *
 * Karta jest czystą prezentacją — nawigację i akcje dostarcza strona listy.
 */
import { Clock, Heart, Star } from '@lucide/vue'
import { computed } from 'vue'

import type { RecipeSummary } from '@/api/recipes'
import { formatDecimal } from '@/lib/format'
import { recipes as texts } from '@/lib/texts'

const props = defineProps<{ recipe: RecipeSummary }>()

const isFavorite = computed(() => props.recipe.tags.some((tag) => tag.name === texts.favoriteTag))
const kcalPerPortion = computed(() => formatDecimal(props.recipe.nutrition.kcal))
const avgRating = computed(() =>
  props.recipe.avg_rating === null ? null : formatDecimal(props.recipe.avg_rating),
)
const missingTooltip = computed(() => props.recipe.nutrition.missing.join(', '))
</script>

<template>
  <article
    class="border-border bg-card grid gap-2 overflow-hidden rounded-xl border shadow-sm"
    :data-testid="`recipe-card-${recipe.id}`"
  >
    <div class="bg-muted relative aspect-[4/3]">
      <img
        v-if="recipe.photo_thumb_url"
        :src="recipe.photo_thumb_url"
        :alt="`Zdjęcie: ${recipe.name}`"
        class="size-full object-cover"
        loading="lazy"
      />
      <div v-else class="text-muted-foreground grid size-full place-items-center text-sm">
        {{ recipe.name.slice(0, 1).toUpperCase() }}
      </div>
      <!-- Serce = tag systemowy „ulubione" (świadome uproszczenie domowe z karty B05). -->
      <Heart
        v-if="isFavorite"
        class="text-primary fill-primary absolute top-2 right-2 size-5"
        aria-label="Ulubiony przepis"
        :data-testid="`recipe-favorite-${recipe.id}`"
      />
    </div>

    <div class="grid gap-2 p-3 pt-1">
      <h3 class="truncate font-medium">{{ recipe.name }}</h3>

      <p class="text-muted-foreground flex flex-wrap items-center gap-3 text-sm tabular-nums">
        <span v-if="recipe.prep_time_min" class="inline-flex items-center gap-1">
          <Clock class="size-4" aria-hidden="true" />
          {{ recipe.prep_time_min }} {{ texts.minutesShort }}
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
          class="bg-muted text-muted-foreground rounded-lg px-2 py-0.5 text-xs"
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
    </div>
  </article>
</template>
