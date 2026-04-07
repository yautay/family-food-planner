import catalogDb from '../db/catalog.js'

function roundNutrition(value) {
  if (!Number.isFinite(value)) {
    return 0
  }

  return Number(value.toFixed(2))
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function parseOptionalNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function parseOptionalInteger(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null
  }

  return parsed
}

function validateDayPlanPayload(payload) {
  const name = normalizeText(payload?.name)
  const note = typeof payload?.note === 'string' ? payload.note.trim() : ''

  if (!name) {
    throw new Error('Day plan name is required')
  }

  return {
    name,
    note,
  }
}

function normalizeDayMealsPayload(rawMeals) {
  if (!Array.isArray(rawMeals)) {
    throw new Error('meals must be an array')
  }

  return rawMeals.map((rawMeal, index) => {
    const recipeId = parseOptionalInteger(rawMeal?.recipe_id)
    if (!recipeId) {
      throw new Error('Each day meal requires recipe_id')
    }

    const servings = parseOptionalNumber(rawMeal?.servings)
    if (servings !== null && servings <= 0) {
      throw new Error('servings must be greater than 0')
    }

    return {
      recipe_id: recipeId,
      servings,
      note: typeof rawMeal?.note === 'string' ? rawMeal.note.trim() : '',
      meal_order: index + 1,
    }
  })
}

function getOwnedDayPlanById(dayPlanId, ownerUserId) {
  return catalogDb
    .prepare(
      `
      SELECT id, owner_user_id, name, note, created_at, updated_at
      FROM day_plans
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .get(dayPlanId, ownerUserId)
}

function getDayPlanMeals(dayPlanId) {
  return catalogDb
    .prepare(
      `
      SELECT
        m.id,
        m.day_plan_id,
        m.recipe_id,
        r.name AS recipe_name,
        m.servings,
        m.note,
        m.meal_order,
        m.created_at,
        m.updated_at
      FROM day_plan_meals m
      INNER JOIN recipes r ON r.id = m.recipe_id
      WHERE m.day_plan_id = ?
      ORDER BY m.meal_order ASC
      `,
    )
    .all(dayPlanId)
}

function getRecipeNutritionMap(recipeIds) {
  if (!Array.isArray(recipeIds) || recipeIds.length === 0) {
    return new Map()
  }

  const uniqueRecipeIds = Array.from(
    new Set(recipeIds.filter((id) => Number.isInteger(id) && id > 0)),
  )
  if (uniqueRecipeIds.length === 0) {
    return new Map()
  }

  const placeholders = uniqueRecipeIds.map(() => '?').join(', ')
  const rows = catalogDb
    .prepare(
      `
      SELECT
        recipe_id,
        total_grams,
        calories,
        carbohydrates,
        sugars,
        fat,
        protein,
        fiber
      FROM recipe_nutrition_summary
      WHERE recipe_id IN (${placeholders})
      `,
    )
    .all(...uniqueRecipeIds)

  return new Map(rows.map((row) => [row.recipe_id, row]))
}

function hydrateMealsWithNutrition(meals) {
  const nutritionMap = getRecipeNutritionMap(meals.map((meal) => meal.recipe_id))
  let cumulativeMass = 0

  const hydratedMeals = meals.map((meal) => {
    const recipeNutrition = nutritionMap.get(meal.recipe_id)
    const servings = parseOptionalNumber(meal.servings)
    const factor = servings !== null && servings > 0 ? servings : 1

    const nutrition = {
      calories: roundNutrition((recipeNutrition?.calories ?? 0) * factor),
      carbohydrates: roundNutrition((recipeNutrition?.carbohydrates ?? 0) * factor),
      sugars: roundNutrition((recipeNutrition?.sugars ?? 0) * factor),
      fat: roundNutrition((recipeNutrition?.fat ?? 0) * factor),
      protein: roundNutrition((recipeNutrition?.protein ?? 0) * factor),
      fiber: roundNutrition((recipeNutrition?.fiber ?? 0) * factor),
      mass_grams: roundNutrition((recipeNutrition?.total_grams ?? 0) * factor),
    }

    cumulativeMass += nutrition.mass_grams

    return {
      ...meal,
      nutrition,
      cumulative_mass_grams: roundNutrition(cumulativeMass),
    }
  })

  const totals = hydratedMeals.reduce(
    (accumulator, meal) => ({
      calories: roundNutrition(accumulator.calories + meal.nutrition.calories),
      carbohydrates: roundNutrition(accumulator.carbohydrates + meal.nutrition.carbohydrates),
      sugars: roundNutrition(accumulator.sugars + meal.nutrition.sugars),
      fat: roundNutrition(accumulator.fat + meal.nutrition.fat),
      protein: roundNutrition(accumulator.protein + meal.nutrition.protein),
      fiber: roundNutrition(accumulator.fiber + meal.nutrition.fiber),
      mass_grams: roundNutrition(accumulator.mass_grams + meal.nutrition.mass_grams),
    }),
    {
      calories: 0,
      carbohydrates: 0,
      sugars: 0,
      fat: 0,
      protein: 0,
      fiber: 0,
      mass_grams: 0,
    },
  )

  return {
    meals: hydratedMeals,
    totals,
  }
}

async function listDayPlans(user) {
  return catalogDb
    .prepare(
      `
      SELECT
        d.id,
        d.owner_user_id,
        d.name,
        d.note,
        d.created_at,
        d.updated_at,
        (
          SELECT COUNT(*)
          FROM day_plan_meals m
          WHERE m.day_plan_id = d.id
        ) AS meals_count
      FROM day_plans d
      WHERE d.owner_user_id = ?
      ORDER BY d.updated_at DESC, d.created_at DESC
      `,
    )
    .all(user.id)
}

async function getDayPlanById(dayPlanId, user) {
  const dayPlan = getOwnedDayPlanById(dayPlanId, user.id)
  if (!dayPlan) {
    return null
  }

  const hydrated = hydrateMealsWithNutrition(getDayPlanMeals(dayPlanId))

  return {
    ...dayPlan,
    meals: hydrated.meals,
    totals: hydrated.totals,
  }
}

async function createDayPlan(payload, user) {
  const normalized = validateDayPlanPayload(payload)

  const result = catalogDb
    .prepare(
      `
      INSERT INTO day_plans(owner_user_id, name, note)
      VALUES (?, ?, ?)
      `,
    )
    .run(user.id, normalized.name, normalized.note)

  return getDayPlanById(Number(result.lastInsertRowid), user)
}

async function updateDayPlan(dayPlanId, payload, user) {
  const existing = getOwnedDayPlanById(dayPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalized = validateDayPlanPayload(payload)

  catalogDb
    .prepare(
      `
      UPDATE day_plans
      SET name = ?, note = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .run(normalized.name, normalized.note, dayPlanId, user.id)

  return getDayPlanById(dayPlanId, user)
}

async function deleteDayPlan(dayPlanId, user) {
  const deleted = catalogDb
    .prepare('DELETE FROM day_plans WHERE id = ? AND owner_user_id = ?')
    .run(dayPlanId, user.id)

  return deleted.changes > 0
}

async function replaceDayPlanMeals(dayPlanId, meals, user) {
  const existing = getOwnedDayPlanById(dayPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalizedMeals = normalizeDayMealsPayload(meals)

  catalogDb.transaction(() => {
    catalogDb.prepare('DELETE FROM day_plan_meals WHERE day_plan_id = ?').run(dayPlanId)

    const insertMeal = catalogDb.prepare(
      `
      INSERT INTO day_plan_meals(day_plan_id, recipe_id, servings, note, meal_order)
      VALUES (?, ?, ?, ?, ?)
      `,
    )

    for (const meal of normalizedMeals) {
      insertMeal.run(dayPlanId, meal.recipe_id, meal.servings, meal.note, meal.meal_order)
    }

    catalogDb
      .prepare(
        'UPDATE day_plans SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?',
      )
      .run(dayPlanId, user.id)
  })()

  return getDayPlanById(dayPlanId, user)
}

export default {
  listDayPlans,
  getDayPlanById,
  createDayPlan,
  updateDayPlan,
  deleteDayPlan,
  replaceDayPlanMeals,
}
