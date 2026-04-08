<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../../composables/useI18n'
import { useDayMealsMetrics } from '../../composables/planning/useDayMealsMetrics'
import { useMealDragDrop } from '../../composables/planning/useMealDragDrop'
import DayMealRow from './DayMealRow.vue'
import NutritionTotalsInline from './NutritionTotalsInline.vue'
import RecipePickerModal from './RecipePickerModal.vue'

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
  editMealPortions: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const isPickerOpen = ref(false)
const pickerTargetIndex = ref(null)
const pickerSearch = ref('')

const { mealLimit, isAtMealLimit, mealsWithMetrics, totals } = useDayMealsMetrics(props)

const filteredRecipes = computed(() => {
  const needle = pickerSearch.value.trim().toLowerCase()
  if (!needle) {
    return props.recipes
  }

  return props.recipes.filter((recipe) => recipe.name.toLowerCase().includes(needle))
})

function emitMeals(nextMeals) {
  emit('update:modelValue', nextMeals)
}

function mapMealsClone() {
  return props.modelValue.map((meal) => ({ ...meal }))
}

const { draggingIndex, dropTargetIndex, startMealDrag, allowMealDrop, dropMeal, endMealDrag } =
  useMealDragDrop({
    isReadOnly: () => props.readOnly,
    getMeals: mapMealsClone,
    emitMeals,
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

function selectRecipe(recipeId) {
  const nextMeals = mapMealsClone()

  if (pickerTargetIndex.value === null) {
    if (isAtMealLimit.value) {
      closeRecipePicker()
      return
    }

    nextMeals.push({
      recipe_id: recipeId,
      servings: null,
      portions: 1,
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
  const nextMeals = mapMealsClone()
  const parsed = Number(value)
  if (props.editMealPortions) {
    nextMeals[index].portions = Number.isFinite(parsed) && parsed > 0 ? parsed : 1
  } else {
    nextMeals[index].servings = Number.isFinite(parsed) && parsed > 0 ? parsed : null
  }

  emitMeals(nextMeals)
}

function updateMealNote(index, value) {
  const nextMeals = mapMealsClone()
  nextMeals[index].note = value
  emitMeals(nextMeals)
}

function removeMeal(index) {
  const nextMeals = props.modelValue.filter((_, targetIndex) => targetIndex !== index)
  emitMeals(nextMeals)
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
      <DayMealRow
        v-for="(meal, index) in mealsWithMetrics"
        :key="`${meal.recipe_id}-${index}`"
        :meal="meal"
        :index="index"
        :is-dragging="draggingIndex === index"
        :is-drop-target="dropTargetIndex === index && draggingIndex !== index"
        :read-only="props.readOnly"
        :edit-meal-portions="props.editMealPortions"
        :default-servings="props.defaultServings"
        :servings-label="t('meals.servingsLabel')"
        :meal-portions-label="t('meals.mealPortionsLabel')"
        :note-label="t('meals.note')"
        :one-portion-label="t('meals.onePortionLabel')"
        :meal-mass-label="t('meals.mealMassLabel')"
        :change-meal-label="t('meals.changeMeal')"
        :delete-label="t('common.delete')"
        :slot-label="slotLabel(meal, index)"
        @update-servings="updateMealServings"
        @update-note="updateMealNote"
        @change-meal="openRecipePicker"
        @remove-meal="removeMeal"
        @dragstart="startMealDrag"
        @dragover="allowMealDrop"
        @drop="dropMeal"
        @dragend="endMealDrag"
      />
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

    <RecipePickerModal
      :visible="isPickerOpen"
      :search-value="pickerSearch"
      :recipes="filteredRecipes"
      :title="t('meals.recipePickerTitle')"
      :close-label="t('common.close')"
      :search-placeholder="t('catalog.searchRecipe')"
      @close="closeRecipePicker"
      @select-recipe="selectRecipe"
      @update:search-value="pickerSearch = $event"
    />
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
</style>
