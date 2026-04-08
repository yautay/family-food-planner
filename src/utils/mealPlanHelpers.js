export function cloneMeals(meals) {
  if (!Array.isArray(meals)) {
    return []
  }

  return meals.map((meal) => ({
    recipe_id: meal.recipe_id,
    servings: meal.servings ?? null,
    portions: meal.portions ?? 1,
    note: meal.note ?? '',
  }))
}

export function cloneMealSlots(slots) {
  if (!Array.isArray(slots)) {
    return []
  }

  return slots.map((slot) => ({
    slot_name: slot.slot_name,
    slot_time: slot.slot_time ?? '',
  }))
}

export function mapImportedMeals(dayPlanMeals) {
  return dayPlanMeals.map((meal) => ({
    recipe_id: meal.recipe_id,
    servings: meal.servings ?? null,
    portions: meal.portions ?? 1,
    note: meal.note ?? '',
  }))
}

function summaryValue(totals, field) {
  const parsed = Number(totals?.[field])
  return Number.isFinite(parsed) ? Number(parsed.toFixed(2)) : 0
}

function formatMassFromGrams(value) {
  const parsed = Number(value)
  const grams = Number.isFinite(parsed) ? Number(parsed.toFixed(2)) : 0
  if (grams >= 1000) {
    return `${Number((grams / 1000).toFixed(2))} kg`
  }

  return `${grams} g`
}

export function daySummaryLineOne(totals) {
  return `kcal ${summaryValue(totals, 'calories')}`
}

export function daySummaryLineTwo(totals) {
  return `B ${summaryValue(totals, 'protein')}g | T ${summaryValue(totals, 'fat')}g | W ${summaryValue(totals, 'carbohydrates')}g`
}

export function daySummaryLineThree(totals) {
  return `M ${formatMassFromGrams(totals?.total_mass_grams)}`
}
