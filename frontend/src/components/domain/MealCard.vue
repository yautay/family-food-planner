<script setup lang="ts">
/**
 * Karta posiłku w planie dnia (widok 1, 06_UIUX §4.1): nazwa, kcal wobec celu
 * posiłku, lista pozycji ze stepperem mnożnika i menu akcji.
 *
 * Karta jest prezentacją + intencjami: sama nie woła API, tylko emituje
 * zdarzenia. Dzięki temu cała logika mutacji i unieważniania cache'u siedzi
 * w `PlanDniaPage` (ADR-007), a kartę da się przetestować bez sieci.
 *
 * Menu ⋮ jest zwykłą listą przycisków, nie dropdownem na hoverze — na telefonie
 * hover nie istnieje, a cele dotykowe muszą mieć ≥44 px (06_UIUX §5).
 */
import { ChevronDown, Copy, Minus, Plus, Target, Trash2, Users } from '@lucide/vue'
import { computed, ref } from 'vue'

import type { PlanItem, PlanMeal } from '@/api/planning'
import NutritionBar from '@/components/charts/NutritionBar.vue'
import { Button } from '@/components/ui/button'
import { sumDecimals } from '@/lib/decimal'
import { formatAmount, formatDecimal } from '@/lib/format'
import { statusLabel, statusToken } from '@/lib/nutrition'
import { common, plan as texts, recipes as recipeTexts } from '@/lib/texts'

const props = defineProps<{ meal: PlanMeal; pending?: boolean }>()

const emit = defineEmits<{
  (event: 'add-item', mealId: number): void
  (event: 'edit', mealId: number): void
  (event: 'duplicate', mealId: number): void
  (event: 'remove', mealId: number): void
  (event: 'change-servings', payload: { itemId: number; servings: string }): void
  (event: 'open-split', itemId: number): void
  (event: 'fit-to-target', itemId: number): void
  (event: 'remove-item', itemId: number): void
}>()

const menuOpen = ref(false)

const statusText = computed(() => statusLabel(props.meal.kcal_status))
const statusClass = computed(() => statusToken(props.meal.kcal_status).text)

/** Krok steppera: 0,5 porcji — tyle, ile ma sens przy jedzeniu. */
const STEP = '0.5'

function step(item: PlanItem, direction: 1 | -1): void {
  const next = sumDecimals([item.servings, direction === 1 ? STEP : `-${STEP}`])
  if (next.startsWith('-') || /^0(\.0*)?$/.test(next)) {
    return
  }
  emit('change-servings', { itemId: item.id, servings: next })
}

function itemLabel(item: PlanItem): string {
  return item.recipe_name ?? item.product_name ?? texts.productItem
}

function itemAmount(item: PlanItem): string | null {
  if (item.amount === null || item.amount_unit === null) {
    return null
  }
  return formatAmount(item.amount, item.amount_unit)
}
</script>

<template>
  <article
    class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm"
    :data-testid="`meal-card-${meal.id}`"
  >
    <header class="grid gap-2">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <h3 class="truncate font-medium" :data-testid="`meal-name-${meal.id}`">
            {{ meal.name }}
          </h3>
          <p class="text-muted-foreground text-sm tabular-nums">
            <span :data-testid="`meal-kcal-${meal.id}`">
              {{ formatDecimal(meal.nutrition.kcal) }} {{ recipeTexts.kcalUnit }}
            </span>
            <template v-if="meal.kcal_target">
              <span aria-hidden="true"> / </span>
              <span>{{ formatDecimal(meal.kcal_target) }}</span>
            </template>
            <template v-if="statusText">
              <span aria-hidden="true"> · </span>
              <span :class="statusClass" :data-testid="`meal-status-${meal.id}`">
                {{ statusText }}
              </span>
            </template>
          </p>
        </div>

        <Button
          type="button"
          variant="ghost"
          class="min-h-11 min-w-11"
          :aria-expanded="menuOpen"
          :aria-label="`Akcje posiłku ${meal.name}`"
          :data-testid="`meal-menu-${meal.id}`"
          @click="menuOpen = !menuOpen"
        >
          <ChevronDown class="size-4" aria-hidden="true" />
        </Button>
      </div>

      <NutritionBar
        v-if="meal.kcal_target"
        :label="`${meal.name} — kalorie`"
        :value="meal.nutrition.kcal"
        :target="meal.kcal_target"
        :status="meal.kcal_status"
        unit="kcal"
        :testid="`meal-bar-${meal.id}`"
      />
    </header>

    <div v-if="menuOpen" class="flex flex-wrap gap-2" :data-testid="`meal-actions-${meal.id}`">
      <Button
        type="button"
        variant="outline"
        class="min-h-11"
        :data-testid="`meal-edit-${meal.id}`"
        @click="emit('edit', meal.id)"
      >
        {{ common.edit }}
      </Button>
      <Button
        type="button"
        variant="outline"
        class="min-h-11"
        :disabled="pending"
        :data-testid="`meal-duplicate-${meal.id}`"
        @click="emit('duplicate', meal.id)"
      >
        <Copy class="size-4" aria-hidden="true" />
        {{ texts.duplicateMeal }}
      </Button>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :disabled="pending"
        :data-testid="`meal-remove-${meal.id}`"
        @click="emit('remove', meal.id)"
      >
        <Trash2 class="size-4" aria-hidden="true" />
        {{ texts.removeMeal }}
      </Button>
    </div>

    <p
      v-if="meal.items.length === 0"
      class="text-muted-foreground text-sm"
      :data-testid="`meal-empty-${meal.id}`"
    >
      {{ texts.mealEmpty }}
    </p>

    <ul v-else class="grid gap-2">
      <li
        v-for="item in meal.items"
        :key="item.id"
        class="border-border grid gap-2 rounded-lg border p-2"
        :data-testid="`plan-item-${item.id}`"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="flex min-w-0 items-center gap-2">
            <img
              v-if="item.recipe_photo_thumb_url"
              :src="item.recipe_photo_thumb_url"
              :alt="`Zdjęcie: ${itemLabel(item)}`"
              class="size-10 rounded-lg object-cover"
              loading="lazy"
            />
            <div class="min-w-0">
              <p class="truncate text-sm font-medium">{{ itemLabel(item) }}</p>
              <p class="text-muted-foreground text-xs tabular-nums">
                <span :data-testid="`plan-item-kcal-${item.id}`">
                  {{ formatDecimal(item.nutrition.kcal) }} {{ recipeTexts.kcalUnit }}
                </span>
                <template v-if="itemAmount(item)">
                  <span aria-hidden="true"> · </span>
                  <span>{{ itemAmount(item) }}</span>
                </template>
                <template v-if="item.servings_split.length">
                  <span aria-hidden="true"> · </span>
                  <span :data-testid="`plan-item-split-${item.id}`">
                    {{ item.servings_split.map((row) => row.member_name).join(', ') }}
                  </span>
                </template>
              </p>
            </div>
          </div>

          <div class="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              variant="outline"
              class="min-h-11 min-w-11"
              :disabled="pending"
              :aria-label="texts.decreaseServings"
              :data-testid="`plan-item-minus-${item.id}`"
              @click="step(item, -1)"
            >
              <Minus class="size-4" aria-hidden="true" />
            </Button>
            <span
              class="min-w-10 text-center text-sm tabular-nums"
              :data-testid="`plan-item-servings-${item.id}`"
            >
              {{ formatDecimal(item.servings) }}
            </span>
            <Button
              type="button"
              variant="outline"
              class="min-h-11 min-w-11"
              :disabled="pending"
              :aria-label="texts.increaseServings"
              :data-testid="`plan-item-plus-${item.id}`"
              @click="step(item, 1)"
            >
              <Plus class="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>

        <p
          v-if="!item.nutrition.complete"
          class="text-warning text-xs"
          :title="item.nutrition.missing.join(', ')"
          :data-testid="`plan-item-incomplete-${item.id}`"
        >
          {{ texts.incompleteData }}
        </p>

        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            class="min-h-11"
            :data-testid="`plan-item-split-open-${item.id}`"
            @click="emit('open-split', item.id)"
          >
            <Users class="size-4" aria-hidden="true" />
            {{ texts.splitOpen }}
          </Button>
          <Button
            v-if="meal.kcal_target"
            type="button"
            variant="ghost"
            class="min-h-11"
            :data-testid="`plan-item-fit-${item.id}`"
            @click="emit('fit-to-target', item.id)"
          >
            <Target class="size-4" aria-hidden="true" />
            {{ texts.fitToTarget }}
          </Button>
          <Button
            type="button"
            variant="ghost"
            class="min-h-11"
            :disabled="pending"
            :data-testid="`plan-item-remove-${item.id}`"
            @click="emit('remove-item', item.id)"
          >
            {{ common.remove }}
          </Button>
        </div>

        <slot name="item-extra" :item="item" />
      </li>
    </ul>

    <Button
      type="button"
      variant="outline"
      class="min-h-11 justify-self-start"
      :data-testid="`meal-add-item-${meal.id}`"
      @click="emit('add-item', meal.id)"
    >
      <Plus class="size-4" aria-hidden="true" />
      {{ texts.addItem }}
    </Button>
  </article>
</template>
