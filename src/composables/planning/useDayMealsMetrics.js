import { computed } from 'vue'

function resolveMealPortionsValue(portionsValue) {
  const portions = Number(portionsValue)
  if (Number.isFinite(portions) && portions > 0) {
    return portions
  }

  return 1
}

function resolveEffectiveServings(servingsValue, portionsValue, defaultServings, editMealPortions) {
  const servings = Number(servingsValue)
  if (Number.isFinite(servings) && servings > 0) {
    return servings
  }

  const mealPortions = resolveMealPortionsValue(portionsValue)
  const planPortions = defaultServings > 0 ? defaultServings : 1

  if (editMealPortions) {
    return mealPortions
  }

  return planPortions * mealPortions
}

export function useDayMealsMetrics(props) {
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

  const mealsWithMetrics = computed(() => {
    return props.modelValue.map((meal, index) => {
      const recipe = recipesById.value.get(meal.recipe_id)
      const nutritionSummary = nutritionByRecipeId.value.get(meal.recipe_id)
      const mealPortions = resolveMealPortionsValue(meal.portions)
      const effectiveServings = resolveEffectiveServings(
        meal.servings,
        meal.portions,
        props.defaultServings,
        props.editMealPortions,
      )

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
        portions: mealPortions,
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
        carbohydrates: Number(
          (accumulator.carbohydrates + meal.nutrition.carbohydrates).toFixed(2),
        ),
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

  return {
    mealLimit,
    isAtMealLimit,
    mealsWithMetrics,
    totals,
  }
}
