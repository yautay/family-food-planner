import { Op, fn, col } from 'sequelize'
import sequelize from '../db/client.js'
import models from '../models/index.js'
import {
  normalizeText,
  parseOptionalInteger,
  parseOptionalNumber,
  roundNutrition,
} from './helpers/parsing.js'

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

    const portions = parseOptionalNumber(rawMeal?.portions)
    if (portions !== null && portions <= 0) {
      throw new Error('portions must be greater than 0')
    }

    return {
      recipe_id: recipeId,
      servings,
      portions: portions !== null ? portions : 1,
      note: typeof rawMeal?.note === 'string' ? rawMeal.note.trim() : '',
      meal_order: index + 1,
    }
  })
}

async function getOwnedDayPlanById(dayPlanId, ownerUserId, transaction = undefined) {
  return models.dayPlan.findOne({
    where: {
      id: dayPlanId,
      owner_user_id: ownerUserId,
    },
    raw: true,
    transaction,
  })
}

async function getDayPlanMeals(dayPlanId, transaction = undefined) {
  const rows = await models.dayPlanMeal.findAll({
    where: { day_plan_id: dayPlanId },
    include: [
      {
        model: models.recipe,
        as: 'recipe',
        attributes: ['name'],
        required: true,
      },
    ],
    order: [['meal_order', 'ASC']],
  })

  return rows.map((row) => {
    const plain = row.get({ plain: true })
    return {
      id: plain.id,
      day_plan_id: plain.day_plan_id,
      recipe_id: plain.recipe_id,
      recipe_name: plain.recipe?.name ?? null,
      servings: plain.servings,
      portions: plain.portions,
      note: plain.note,
      meal_order: plain.meal_order,
      created_at: plain.created_at,
      updated_at: plain.updated_at,
    }
  })
}

async function getRecipeNutritionMap(recipeIds, transaction = undefined) {
  if (!Array.isArray(recipeIds) || recipeIds.length === 0) {
    return new Map()
  }

  const uniqueRecipeIds = Array.from(
    new Set(recipeIds.filter((id) => Number.isInteger(id) && id > 0)),
  )
  if (uniqueRecipeIds.length === 0) {
    return new Map()
  }

  const rows = await models.recipeNutritionSummary.findAll({
    where: {
      recipe_id: {
        [Op.in]: uniqueRecipeIds,
      },
    },
    raw: true,
    transaction,
  })

  return new Map(rows.map((row) => [row.recipe_id, row]))
}

async function hydrateMealsWithNutrition(meals, transaction = undefined) {
  const nutritionMap = await getRecipeNutritionMap(
    meals.map((meal) => meal.recipe_id),
    transaction,
  )
  let cumulativeMass = 0

  const hydratedMeals = meals.map((meal) => {
    const recipeNutrition = nutritionMap.get(meal.recipe_id)
    const portions = parseOptionalNumber(meal.portions)
    const factor = portions !== null && portions > 0 ? portions : 1

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
      portions: roundNutrition(factor),
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
  const rows = await models.dayPlan.findAll({
    where: {
      owner_user_id: user.id,
    },
    order: [
      ['updated_at', 'DESC'],
      ['created_at', 'DESC'],
    ],
    raw: true,
  })

  if (rows.length === 0) {
    return []
  }

  const ids = rows.map((row) => row.id)
  const counts = await models.dayPlanMeal.findAll({
    attributes: ['day_plan_id', [fn('COUNT', col('id')), 'meals_count']],
    where: {
      day_plan_id: {
        [Op.in]: ids,
      },
    },
    group: ['day_plan_id'],
    raw: true,
  })

  const countByDayPlanId = new Map(
    counts.map((row) => [row.day_plan_id, Number(row.meals_count) || 0]),
  )

  return rows.map((row) => ({
    ...row,
    meals_count: countByDayPlanId.get(row.id) ?? 0,
  }))
}

async function getDayPlanById(dayPlanId, user, transaction = undefined) {
  const dayPlan = await getOwnedDayPlanById(dayPlanId, user.id, transaction)
  if (!dayPlan) {
    return null
  }

  const meals = await getDayPlanMeals(dayPlanId, transaction)
  const hydrated = await hydrateMealsWithNutrition(meals, transaction)

  return {
    ...dayPlan,
    meals: hydrated.meals,
    totals: hydrated.totals,
  }
}

async function createDayPlan(payload, user) {
  const normalized = validateDayPlanPayload(payload)

  const created = await models.dayPlan.create({
    owner_user_id: user.id,
    name: normalized.name,
    note: normalized.note,
  })

  return getDayPlanById(created.id, user)
}

async function updateDayPlan(dayPlanId, payload, user) {
  const existing = await getOwnedDayPlanById(dayPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalized = validateDayPlanPayload(payload)

  await models.dayPlan.update(
    {
      name: normalized.name,
      note: normalized.note,
      updated_at: new Date().toISOString(),
    },
    {
      where: {
        id: dayPlanId,
        owner_user_id: user.id,
      },
    },
  )

  return getDayPlanById(dayPlanId, user)
}

async function deleteDayPlan(dayPlanId, user) {
  const deleted = await models.dayPlan.destroy({
    where: {
      id: dayPlanId,
      owner_user_id: user.id,
    },
  })

  return deleted > 0
}

async function replaceDayPlanMeals(dayPlanId, meals, user) {
  const existing = await getOwnedDayPlanById(dayPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalizedMeals = normalizeDayMealsPayload(meals)

  await sequelize.transaction(async (transaction) => {
    await models.dayPlanMeal.destroy({
      where: { day_plan_id: dayPlanId },
      transaction,
    })

    if (normalizedMeals.length > 0) {
      await models.dayPlanMeal.bulkCreate(
        normalizedMeals.map((meal) => ({
          day_plan_id: dayPlanId,
          recipe_id: meal.recipe_id,
          servings: meal.servings,
          portions: meal.portions,
          note: meal.note,
          meal_order: meal.meal_order,
        })),
        { transaction },
      )
    }

    await models.dayPlan.update(
      {
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: dayPlanId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

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
