<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../../composables/useI18n'
import NutritionTotalsInline from './NutritionTotalsInline.vue'
import SlotTimeClock from './SlotTimeClock.vue'

const props = defineProps({
  modelValue: {
    type: Array,
    required: true,
  },
  recipes: {
    type: Array,
    default: () => [],
  },
  nutritionSummaries: {
    type: Array,
    default: () => [],
  },
  mealSlots: {
    type: Array,
    default: () => [],
  },
  defaultServings: {
    type: Number,
    default: 1,
  },
  readOnly: {
    type: Boolean,
    default: false,
  },
  emptyLabel: {
    type: String,
    default: 'Brak posilkow.',
  },
  addButtonLabel: {
    type: String,
    default: 'Dodaj posilek',
  },
  maxMeals: {
    type: Number,
    default: null,
  },
  showTotals: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const isPickerOpen = ref(false)
const pickerTargetIndex = ref(null)
const pickerSearch = ref('')
const draggingIndex = ref(null)

const mealLimit = computed(() => {
  const parsed = Number(props.maxMeals)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
})

const isAtMealLimit = computed(() => {
  return mealLimit.value !== null && props.modelValue.length >= mealLimit.value
})

const recipesById = computed(() => {
  const pairs = props.recipes.map((recipe) => [recipe.id, recipe])
  return new Map(pairs)
})

const nutritionByRecipeId = computed(() => {
  const pairs = props.nutritionSummaries.map((summary) => [summary.recipe_id, summary])
  return new Map(pairs)
})

const filteredRecipes = computed(() => {
  const needle = pickerSearch.value.trim().toLowerCase()
  if (!needle) {
    return props.recipes
  }

  return props.recipes.filter((recipe) => recipe.name.toLowerCase().includes(needle))
})

function resolveEffectiveServings(servingsValue) {
  const servings = Number(servingsValue)
  if (Number.isFinite(servings) && servings > 0) {
    return servings
  }

  return props.defaultServings > 0 ? props.defaultServings : 1
}

const mealsWithMetrics = computed(() => {
  return props.modelValue.map((meal, index) => {
    const recipe = recipesById.value.get(meal.recipe_id)
    const nutritionSummary = nutritionByRecipeId.value.get(meal.recipe_id)
    const effectiveServings = resolveEffectiveServings(meal.servings)

    const nutrition = {
      calories: Number((nutritionSummary?.calories ?? 0).toFixed(2)),
      carbohydrates: Number((nutritionSummary?.carbohydrates ?? 0).toFixed(2)),
      fat: Number((nutritionSummary?.fat ?? 0).toFixed(2)),
      protein: Number((nutritionSummary?.protein ?? 0).toFixed(2)),
      mass_grams: Number((nutritionSummary?.total_grams ?? 0).toFixed(2)),
      total_mass_grams: Number(
        ((nutritionSummary?.total_grams ?? 0) * effectiveServings).toFixed(2),
      ),
    }

    const slot = props.mealSlots[index] ?? null

    return {
      ...meal,
      slot_name: slot?.slot_name ?? null,
      slot_time: slot?.slot_time ?? null,
      effective_servings: effectiveServings,
      recipe_name: recipe?.name ?? `#${meal.recipe_id}`,
      nutrition,
    }
  })
})

const totals = computed(() => {
  return mealsWithMetrics.value.reduce(
    (accumulator, meal) => ({
      calories: Number((accumulator.calories + meal.nutrition.calories).toFixed(2)),
      carbohydrates: Number((accumulator.carbohydrates + meal.nutrition.carbohydrates).toFixed(2)),
      fat: Number((accumulator.fat + meal.nutrition.fat).toFixed(2)),
      protein: Number((accumulator.protein + meal.nutrition.protein).toFixed(2)),
      total_mass_grams: Number(
        (accumulator.total_mass_grams + meal.nutrition.total_mass_grams).toFixed(2),
      ),
    }),
    {
      calories: 0,
      carbohydrates: 0,
      fat: 0,
      protein: 0,
      total_mass_grams: 0,
    },
  )
})

function openRecipePicker(targetIndex = null) {
  if (targetIndex === null && isAtMealLimit.value) {
    return
  }

  pickerTargetIndex.value = targetIndex
  pickerSearch.value = ''
  isPickerOpen.value = true
}

function closeRecipePicker() {
  isPickerOpen.value = false
  pickerTargetIndex.value = null
  pickerSearch.value = ''
}

function emitMeals(nextMeals) {
  emit('update:modelValue', nextMeals)
}

function selectRecipe(recipeId) {
  const nextMeals = props.modelValue.map((meal) => ({ ...meal }))

  if (pickerTargetIndex.value === null) {
    if (isAtMealLimit.value) {
      closeRecipePicker()
      return
    }

    nextMeals.push({
      recipe_id: recipeId,
      servings: null,
      note: '',
    })
  } else {
    const targetMeal = nextMeals[pickerTargetIndex.value]
    if (!targetMeal) {
      closeRecipePicker()
      return
    }

    targetMeal.recipe_id = recipeId
  }

  emitMeals(nextMeals)
  closeRecipePicker()
}

function updateMealServings(index, value) {
  const nextMeals = props.modelValue.map((meal) => ({ ...meal }))
  const parsed = Number(value)
  nextMeals[index].servings = Number.isFinite(parsed) && parsed > 0 ? parsed : null
  emitMeals(nextMeals)
}

function updateMealNote(index, value) {
  const nextMeals = props.modelValue.map((meal) => ({ ...meal }))
  nextMeals[index].note = value
  emitMeals(nextMeals)
}

function removeMeal(index) {
  const nextMeals = props.modelValue.filter((_, targetIndex) => targetIndex !== index)
  emitMeals(nextMeals)
}

function startMealDrag(index, event) {
  if (props.readOnly) {
    return
  }

  draggingIndex.value = index
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

function allowMealDrop(event) {
  if (props.readOnly) {
    return
  }

  event.preventDefault()
  if (event?.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

function dropMeal(index, event) {
  if (props.readOnly) {
    return
  }

  event.preventDefault()
  const fromIndex = draggingIndex.value
  if (!Number.isInteger(fromIndex) || fromIndex === index) {
    draggingIndex.value = null
    return
  }

  const nextMeals = props.modelValue.map((meal) => ({ ...meal }))
  const [movedMeal] = nextMeals.splice(fromIndex, 1)
  if (!movedMeal) {
    draggingIndex.value = null
    return
  }

  nextMeals.splice(index, 0, movedMeal)
  emitMeals(nextMeals)
  draggingIndex.value = null
}

function endMealDrag() {
  draggingIndex.value = null
}

function slotLabel(meal, index) {
  if (meal.slot_name) {
    return meal.slot_name
  }

  return `${t('meals.mealLabel')} ${index + 1}`
}
</script>

<template>
  <div class="day-builder">
    <ul v-if="mealsWithMetrics.length > 0" class="meal-list">
      <li
        v-for="(meal, index) in mealsWithMetrics"
        :key="`${meal.recipe_id}-${index}`"
        class="meal-row"
        :class="{ 'is-dragging': draggingIndex === index }"
        :draggable="!props.readOnly"
        @dragstart="startMealDrag(index, $event)"
        @dragover="allowMealDrop($event)"
        @drop="dropMeal(index, $event)"
        @dragend="endMealDrag"
      >
        <div class="meal-row-main">
          <p class="meal-slot">
            {{ slotLabel(meal, index) }}
            <span v-if="meal.slot_time" class="slot-time-clock-wrap">
              <SlotTimeClock :time="meal.slot_time" :size="22" />
            </span>
          </p>
          <strong>{{ meal.recipe_name }}</strong>
          <p class="muted">{{ t('meals.servingsLabel') }}: {{ meal.effective_servings }}</p>

          <div class="nutrition-line">
            <NutritionTotalsInline :totals="meal.nutrition" :caption="t('meals.onePortionLabel')" />
            <p class="muted cumulative-line">
              {{ t('meals.mealMassLabel') }}: {{ meal.nutrition.total_mass_grams }} g
            </p>
          </div>
        </div>

        <div v-if="!props.readOnly" class="meal-row-actions">
          <label>
            {{ t('meals.servingsLabel') }}
            <input
              :value="meal.effective_servings"
              class="input"
              type="number"
              min="0.1"
              step="0.1"
              :placeholder="String(props.defaultServings)"
              @input="updateMealServings(index, $event.target.value)"
            />
          </label>
          <label>
            {{ t('meals.note') }}
            <input
              :value="meal.note ?? ''"
              class="input"
              @input="updateMealNote(index, $event.target.value)"
            />
          </label>
          <button class="button is-small" type="button" @click="openRecipePicker(index)">
            {{ t('meals.changeMeal') }}
          </button>
          <button class="button is-small" type="button" @click="removeMeal(index)">
            {{ t('common.delete') }}
          </button>
        </div>
      </li>
    </ul>

    <p v-else class="muted">{{ props.emptyLabel }}</p>

    <NutritionTotalsInline
      v-if="props.showTotals"
      :caption="t('meals.totalsLabel')"
      :totals="totals"
      :mass-label="t('meals.massLabel')"
    />

    <p v-if="mealLimit !== null && isAtMealLimit" class="muted">
      {{ t('meals.maxMealsReached', { count: mealLimit }) }}
    </p>

    <button
      v-if="!props.readOnly"
      class="button is-primary is-small"
      type="button"
      :disabled="isAtMealLimit"
      @click="openRecipePicker()"
    >
      {{ props.addButtonLabel }}
    </button>

    <div v-if="isPickerOpen" class="modal" @click.self="closeRecipePicker">
      <div class="modal-content">
        <div class="modal-header">
          <h4 class="title is-6">{{ t('meals.recipePickerTitle') }}</h4>
          <button class="button is-small" type="button" @click="closeRecipePicker">
            {{ t('common.close') }}
          </button>
        </div>

        <input
          v-model="pickerSearch"
          class="input"
          :placeholder="t('catalog.searchRecipe')"
          type="text"
        />

        <ul class="picker-list">
          <li v-for="recipe in filteredRecipes" :key="recipe.id">
            <button class="link" type="button" @click="selectRecipe(recipe.id)">
              {{ recipe.name }}
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.day-builder {
  display: grid;
  gap: 0.55rem;
}

.meal-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.meal-row {
  border: 1px solid var(--app-border);
  border-radius: 0.65rem;
  padding: 0.55rem;
  display: grid;
  gap: 0.5rem;
  background: var(--app-surface);
}

.meal-row.is-dragging {
  opacity: 0.6;
  border-style: dashed;
}

.meal-row-main {
  display: grid;
  gap: 0.4rem;
}

.meal-slot {
  margin: 0;
  font-size: 0.86rem;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.45rem;
  width: 100%;
}

.slot-time-clock-wrap {
  display: inline-grid;
  justify-self: end;
}

.nutrition-line {
  display: grid;
  gap: 0.3rem;
}

.cumulative-line {
  margin: 0;
}

.meal-row-actions {
  display: grid;
  gap: 0.45rem;
}

.modal {
  display: flex;
  justify-content: center;
  align-items: center;
  position: fixed;
  inset: 0;
  z-index: 70;
  background-color: rgba(0, 0, 0, 0.42);
}

.modal-content {
  width: min(720px, calc(100% - 1.25rem));
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
  padding: 0.75rem;
  display: grid;
  gap: 0.55rem;
  max-height: calc(100vh - 3rem);
  overflow: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.35rem;
}

.link {
  border: none;
  padding: 0;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
}

@media (min-width: 860px) {
  .meal-row-actions {
    grid-template-columns: 0.9fr 1.2fr auto auto;
    align-items: end;
  }
}
</style>
