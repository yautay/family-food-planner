import { Op, fn, col } from 'sequelize'
import sequelize from '../db/client.js'
import models from '../models/index.js'

const ALLOWED_MEAL_SLOTS = new Set(['breakfast', 'lunch', 'dinner', 'snack'])
const DEFAULT_MEAL_SLOTS = ['Sniadanie', 'Drugie sniadanie', 'Obiad', 'Podwieczorek', 'Kolacja']

function roundNutrition(value) {
  if (!Number.isFinite(value)) {
    return 0
  }

  return Number(value.toFixed(2))
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeDate(value) {
  const date = normalizeText(value)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return null
  }

  return date
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

function parseRequiredPositiveInteger(value, fallback = null) {
  const parsed = parseOptionalInteger(value)
  if (parsed === null) {
    if (fallback !== null) {
      return fallback
    }
    throw new Error('Expected positive integer value')
  }

  return parsed
}

function normalizeOptionalTime(value) {
  const time = normalizeText(value)
  if (!time) {
    return null
  }

  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) {
    throw new Error('slot_time must use HH:MM format')
  }

  return time
}

function normalizeMealSlotsPayload(rawSlots) {
  if (!Array.isArray(rawSlots) || rawSlots.length === 0) {
    throw new Error('At least one meal slot is required')
  }

  return rawSlots.map((rawSlot, index) => {
    const slotName = normalizeText(rawSlot?.slot_name)
    if (!slotName) {
      throw new Error('Each meal slot requires slot_name')
    }

    return {
      slot_name: slotName,
      slot_time: normalizeOptionalTime(rawSlot?.slot_time),
      sort_order: index + 1,
    }
  })
}

function normalizeDayMealsPayload(rawMeals, options = {}) {
  if (!Array.isArray(rawMeals)) {
    throw new Error('meals must be an array')
  }

  const maxMeals =
    Number.isInteger(options.maxMeals) && options.maxMeals > 0 ? options.maxMeals : null
  if (maxMeals !== null && rawMeals.length > maxMeals) {
    throw new Error(`A day can include up to ${maxMeals} meals`)
  }

  return rawMeals.map((rawMeal, index) => {
    const recipeId = parseRequiredPositiveInteger(rawMeal?.recipe_id)
    const servings = parseOptionalNumber(rawMeal?.servings)
    const portions = parseOptionalNumber(rawMeal?.portions)

    if (servings !== null && servings <= 0) {
      throw new Error('servings must be greater than 0')
    }

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

async function getMealSlotLimit(mealPlanId, transaction = undefined) {
  return models.mealPlanMealSlot.count({
    where: { meal_plan_id: mealPlanId },
    transaction,
  })
}

function buildDateRange(startDate, endDate) {
  const dates = []
  const current = new Date(`${startDate}T00:00:00.000Z`)
  const end = new Date(`${endDate}T00:00:00.000Z`)

  while (current.getTime() <= end.getTime()) {
    dates.push(current.toISOString().slice(0, 10))
    current.setUTCDate(current.getUTCDate() + 1)
  }

  return dates
}

async function ensureDaySlotsInPlanRange(mealPlanId, startDate, endDate, transaction = undefined) {
  const dates = buildDateRange(startDate, endDate)

  await models.mealPlanDaySlot.destroy({
    where: {
      meal_plan_id: mealPlanId,
      [Op.or]: [{ planned_date: { [Op.lt]: startDate } }, { planned_date: { [Op.gt]: endDate } }],
    },
    transaction,
  })

  const existingRows = await models.mealPlanDaySlot.findAll({
    attributes: ['planned_date'],
    where: { meal_plan_id: mealPlanId },
    raw: true,
    transaction,
  })

  const existingDates = new Set(existingRows.map((row) => row.planned_date))
  const missingDates = dates.filter((plannedDate) => !existingDates.has(plannedDate))

  if (missingDates.length > 0) {
    await models.mealPlanDaySlot.bulkCreate(
      missingDates.map((plannedDate) => ({
        meal_plan_id: mealPlanId,
        planned_date: plannedDate,
        day_plan_id: null,
        note: '',
      })),
      { transaction },
    )
  }
}

async function insertMealPlanSlots(mealPlanId, slots, transaction = undefined) {
  if (!Array.isArray(slots) || slots.length === 0) {
    return
  }

  await models.mealPlanMealSlot.bulkCreate(
    slots.map((slot) => ({
      meal_plan_id: mealPlanId,
      slot_name: slot.slot_name,
      slot_time: slot.slot_time,
      sort_order: slot.sort_order,
    })),
    { transaction },
  )
}

async function seedDefaultMealPlanSlots(mealPlanId, transaction = undefined) {
  await insertMealPlanSlots(
    mealPlanId,
    DEFAULT_MEAL_SLOTS.map((slotName, index) => ({
      slot_name: slotName,
      slot_time: null,
      sort_order: index + 1,
    })),
    transaction,
  )
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

function resolveMealPortions(portionsValue) {
  const portions = parseOptionalNumber(portionsValue)
  return portions !== null && portions > 0 ? portions : 1
}

function resolveEffectiveServings(servingsValue, planPortions = 1, mealPortionsValue = 1) {
  const servings = parseOptionalNumber(servingsValue)
  if (servings !== null && servings > 0) {
    return servings
  }

  const normalizedPlanPortions =
    Number.isFinite(planPortions) && planPortions > 0 ? planPortions : 1
  return normalizedPlanPortions * resolveMealPortions(mealPortionsValue)
}

function hydrateMealsWithNutrition(meals, nutritionMap, mealSlots, defaultServings) {
  let cumulativeMass = 0

  return meals.map((meal, index) => {
    const recipeNutrition = nutritionMap.get(meal.recipe_id)
    const portions = resolveMealPortions(meal.portions)
    const effectiveServings = resolveEffectiveServings(meal.servings, defaultServings, portions)

    const nutrition = {
      calories: roundNutrition(recipeNutrition?.calories ?? 0),
      carbohydrates: roundNutrition(recipeNutrition?.carbohydrates ?? 0),
      sugars: roundNutrition(recipeNutrition?.sugars ?? 0),
      fat: roundNutrition(recipeNutrition?.fat ?? 0),
      protein: roundNutrition(recipeNutrition?.protein ?? 0),
      fiber: roundNutrition(recipeNutrition?.fiber ?? 0),
      mass_grams: roundNutrition(recipeNutrition?.total_grams ?? 0),
      total_mass_grams: roundNutrition((recipeNutrition?.total_grams ?? 0) * effectiveServings),
    }

    cumulativeMass += nutrition.total_mass_grams
    const mappedSlot = mealSlots[index] ?? null

    return {
      ...meal,
      portions: roundNutrition(portions),
      effective_servings: roundNutrition(effectiveServings),
      planned_slot_name: mappedSlot?.slot_name ?? null,
      planned_slot_time: mappedSlot?.slot_time ?? null,
      nutrition,
      cumulative_mass_grams: roundNutrition(cumulativeMass),
    }
  })
}

function summarizeMeals(meals) {
  return meals.reduce(
    (accumulator, meal) => ({
      calories: roundNutrition(accumulator.calories + (meal.nutrition?.calories ?? 0)),
      carbohydrates: roundNutrition(
        accumulator.carbohydrates + (meal.nutrition?.carbohydrates ?? 0),
      ),
      sugars: roundNutrition(accumulator.sugars + (meal.nutrition?.sugars ?? 0)),
      fat: roundNutrition(accumulator.fat + (meal.nutrition?.fat ?? 0)),
      protein: roundNutrition(accumulator.protein + (meal.nutrition?.protein ?? 0)),
      fiber: roundNutrition(accumulator.fiber + (meal.nutrition?.fiber ?? 0)),
      total_mass_grams: roundNutrition(
        accumulator.total_mass_grams + (meal.nutrition?.total_mass_grams ?? 0),
      ),
    }),
    {
      calories: 0,
      carbohydrates: 0,
      sugars: 0,
      fat: 0,
      protein: 0,
      fiber: 0,
      total_mass_grams: 0,
    },
  )
}

function validateMealPlanPayload(payload) {
  const name = normalizeText(payload?.name)
  const startDate = normalizeDate(payload?.start_date)
  const endDate = normalizeDate(payload?.end_date)
  const note = typeof payload?.note === 'string' ? payload.note.trim() : ''
  const portionsCount = parseOptionalInteger(payload?.portions_count) ?? 1

  if (!name) {
    throw new Error('Meal plan name is required')
  }

  if (!startDate || !endDate) {
    throw new Error('start_date and end_date must use YYYY-MM-DD format')
  }

  if (startDate > endDate) {
    throw new Error('start_date must be before or equal to end_date')
  }

  if (!Number.isInteger(portionsCount) || portionsCount <= 0) {
    throw new Error('portions_count must be a positive integer')
  }

  return {
    name,
    start_date: startDate,
    end_date: endDate,
    note,
    portions_count: portionsCount,
  }
}

function mapEntryPayload(rawEntry, plan) {
  const plannedDate = normalizeDate(rawEntry?.planned_date)
  if (!plannedDate) {
    throw new Error('Each entry requires planned_date in YYYY-MM-DD format')
  }

  if (plannedDate < plan.start_date || plannedDate > plan.end_date) {
    throw new Error('planned_date must be within meal plan date range')
  }

  const mealSlot = normalizeText(rawEntry?.meal_slot).toLowerCase()
  if (!ALLOWED_MEAL_SLOTS.has(mealSlot)) {
    throw new Error('meal_slot must be one of: breakfast, lunch, dinner, snack')
  }

  const recipeId = parseOptionalInteger(rawEntry?.recipe_id)
  const customName = normalizeText(rawEntry?.custom_name)

  if (!recipeId && !customName) {
    throw new Error('Each entry requires recipe_id or custom_name')
  }

  const servings = parseOptionalNumber(rawEntry?.servings)
  if (servings !== null && servings <= 0) {
    throw new Error('servings must be greater than 0')
  }

  return {
    planned_date: plannedDate,
    meal_slot: mealSlot,
    recipe_id: recipeId,
    custom_name: customName || null,
    servings,
    note: typeof rawEntry?.note === 'string' ? rawEntry.note.trim() : '',
  }
}

async function getOwnedPlanById(mealPlanId, ownerUserId, transaction = undefined) {
  return models.mealPlan.findOne({
    where: {
      id: mealPlanId,
      owner_user_id: ownerUserId,
    },
    raw: true,
    transaction,
  })
}

async function getOwnedDayPlanById(dayPlanId, ownerUserId, transaction = undefined) {
  return models.dayPlan.findOne({
    where: {
      id: dayPlanId,
      owner_user_id: ownerUserId,
    },
    attributes: ['id', 'owner_user_id', 'name'],
    raw: true,
    transaction,
  })
}

async function getMealPlanEntries(mealPlanId, transaction = undefined) {
  const rows = await models.mealPlanEntry.findAll({
    where: { meal_plan_id: mealPlanId },
    include: [
      {
        model: models.recipe,
        as: 'recipe',
        attributes: ['name'],
        required: false,
      },
    ],
    order: [
      ['planned_date', 'ASC'],
      ['meal_slot', 'ASC'],
    ],
    transaction,
  })

  return rows.map((row) => {
    const plain = row.get({ plain: true })
    return {
      id: plain.id,
      meal_plan_id: plain.meal_plan_id,
      planned_date: plain.planned_date,
      meal_slot: plain.meal_slot,
      recipe_id: plain.recipe_id,
      recipe_name: plain.recipe?.name ?? null,
      custom_name: plain.custom_name,
      servings: plain.servings,
      note: plain.note,
      created_at: plain.created_at,
    }
  })
}

async function getMealPlanMealSlots(mealPlanId, transaction = undefined) {
  return models.mealPlanMealSlot.findAll({
    where: { meal_plan_id: mealPlanId },
    order: [['sort_order', 'ASC']],
    raw: true,
    transaction,
  })
}

async function getMealPlanDaySlots(mealPlanId, transaction = undefined) {
  const rows = await models.mealPlanDaySlot.findAll({
    where: { meal_plan_id: mealPlanId },
    include: [
      {
        model: models.dayPlan,
        as: 'dayPlan',
        attributes: ['name'],
        required: false,
      },
    ],
    order: [['planned_date', 'ASC']],
    transaction,
  })

  return rows.map((row) => {
    const plain = row.get({ plain: true })
    return {
      id: plain.id,
      meal_plan_id: plain.meal_plan_id,
      planned_date: plain.planned_date,
      day_plan_id: plain.day_plan_id,
      day_plan_name: plain.dayPlan?.name ?? null,
      note: plain.note,
      created_at: plain.created_at,
      updated_at: plain.updated_at,
    }
  })
}

async function getSlotByPlanAndDate(mealPlanId, plannedDate, transaction = undefined) {
  return models.mealPlanDaySlot.findOne({
    where: {
      meal_plan_id: mealPlanId,
      planned_date: plannedDate,
    },
    raw: true,
    transaction,
  })
}

async function ensureSlotByPlanAndDate(mealPlanId, plannedDate, transaction = undefined) {
  const existing = await getSlotByPlanAndDate(mealPlanId, plannedDate, transaction)
  if (existing) {
    return existing
  }

  const created = await models.mealPlanDaySlot.create(
    {
      meal_plan_id: mealPlanId,
      planned_date: plannedDate,
      day_plan_id: null,
      note: '',
    },
    { transaction },
  )

  return created.get({ plain: true })
}

async function getDayPlanMealsByDayPlanIds(dayPlanIds, transaction = undefined) {
  if (dayPlanIds.length === 0) {
    return new Map()
  }

  const rows = await models.dayPlanMeal.findAll({
    where: {
      day_plan_id: {
        [Op.in]: dayPlanIds,
      },
    },
    include: [
      {
        model: models.recipe,
        as: 'recipe',
        attributes: ['name'],
        required: true,
      },
    ],
    order: [
      ['day_plan_id', 'ASC'],
      ['meal_order', 'ASC'],
    ],
    transaction,
  })

  const grouped = new Map()
  for (const row of rows) {
    const plain = row.get({ plain: true })
    if (!grouped.has(plain.day_plan_id)) {
      grouped.set(plain.day_plan_id, [])
    }

    grouped.get(plain.day_plan_id).push({
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
    })
  }

  return grouped
}

async function getDayPlanMealsForImport(dayPlanId, transaction = undefined) {
  return models.dayPlanMeal.findAll({
    attributes: ['recipe_id', 'servings', 'portions', 'note', 'meal_order'],
    where: { day_plan_id: dayPlanId },
    order: [['meal_order', 'ASC']],
    raw: true,
    transaction,
  })
}

async function getCustomDaySlotMealsBySlotIds(slotIds, transaction = undefined) {
  if (slotIds.length === 0) {
    return new Map()
  }

  const rows = await models.mealPlanDaySlotMeal.findAll({
    where: {
      day_slot_id: {
        [Op.in]: slotIds,
      },
    },
    include: [
      {
        model: models.recipe,
        as: 'recipe',
        attributes: ['name'],
        required: true,
      },
    ],
    order: [
      ['day_slot_id', 'ASC'],
      ['meal_order', 'ASC'],
    ],
    transaction,
  })

  const grouped = new Map()
  for (const row of rows) {
    const plain = row.get({ plain: true })
    if (!grouped.has(plain.day_slot_id)) {
      grouped.set(plain.day_slot_id, [])
    }

    grouped.get(plain.day_slot_id).push({
      id: plain.id,
      day_slot_id: plain.day_slot_id,
      recipe_id: plain.recipe_id,
      recipe_name: plain.recipe?.name ?? null,
      servings: plain.servings,
      portions: plain.portions,
      note: plain.note,
      meal_order: plain.meal_order,
      created_at: plain.created_at,
      updated_at: plain.updated_at,
    })
  }

  return grouped
}

async function buildResolvedDaySlots(plan, daySlots, mealSlots, transaction = undefined) {
  const dayPlanIds = Array.from(new Set(daySlots.map((slot) => slot.day_plan_id).filter(Boolean)))
  const slotIds = daySlots.map((slot) => slot.id)

  const groupedTemplateMeals = await getDayPlanMealsByDayPlanIds(dayPlanIds, transaction)
  const groupedCustomMeals = await getCustomDaySlotMealsBySlotIds(slotIds, transaction)

  const recipeIds = []
  for (const meals of groupedTemplateMeals.values()) {
    for (const meal of meals) {
      recipeIds.push(meal.recipe_id)
    }
  }
  for (const meals of groupedCustomMeals.values()) {
    for (const meal of meals) {
      recipeIds.push(meal.recipe_id)
    }
  }

  const nutritionMap = await getRecipeNutritionMap(recipeIds, transaction)

  const slots = daySlots.map((slot) => {
    const sourceMeals = slot.day_plan_id
      ? (groupedTemplateMeals.get(slot.day_plan_id) ?? [])
      : (groupedCustomMeals.get(slot.id) ?? [])

    const meals = hydrateMealsWithNutrition(
      sourceMeals,
      nutritionMap,
      mealSlots,
      plan.portions_count,
    )
    const totals = summarizeMeals(meals)

    return {
      ...slot,
      source_type: meals.length > 0 ? 'custom' : 'empty',
      meals,
      totals,
    }
  })

  return {
    daySlots: slots,
    totals: slots.reduce(
      (accumulator, slot) => ({
        calories: roundNutrition(accumulator.calories + (slot.totals?.calories ?? 0)),
        carbohydrates: roundNutrition(
          accumulator.carbohydrates + (slot.totals?.carbohydrates ?? 0),
        ),
        sugars: roundNutrition(accumulator.sugars + (slot.totals?.sugars ?? 0)),
        fat: roundNutrition(accumulator.fat + (slot.totals?.fat ?? 0)),
        protein: roundNutrition(accumulator.protein + (slot.totals?.protein ?? 0)),
        fiber: roundNutrition(accumulator.fiber + (slot.totals?.fiber ?? 0)),
        total_mass_grams: roundNutrition(
          accumulator.total_mass_grams + (slot.totals?.total_mass_grams ?? 0),
        ),
      }),
      {
        calories: 0,
        carbohydrates: 0,
        sugars: 0,
        fat: 0,
        protein: 0,
        fiber: 0,
        total_mass_grams: 0,
      },
    ),
  }
}

async function listMealPlans(user) {
  const plans = await models.mealPlan.findAll({
    where: { owner_user_id: user.id },
    order: [
      ['start_date', 'DESC'],
      ['created_at', 'DESC'],
    ],
    raw: true,
  })

  if (plans.length === 0) {
    return []
  }

  const planIds = plans.map((plan) => plan.id)

  const entryCounts = await models.mealPlanEntry.findAll({
    attributes: ['meal_plan_id', [fn('COUNT', col('id')), 'entries_count']],
    where: {
      meal_plan_id: {
        [Op.in]: planIds,
      },
    },
    group: ['meal_plan_id'],
    raw: true,
  })

  const daySlotCounts = await models.mealPlanDaySlot.findAll({
    attributes: ['meal_plan_id', [fn('COUNT', col('id')), 'day_slots_count']],
    where: {
      meal_plan_id: {
        [Op.in]: planIds,
      },
    },
    group: ['meal_plan_id'],
    raw: true,
  })

  const entryCountByPlan = new Map(
    entryCounts.map((row) => [row.meal_plan_id, Number(row.entries_count) || 0]),
  )
  const daySlotCountByPlan = new Map(
    daySlotCounts.map((row) => [row.meal_plan_id, Number(row.day_slots_count) || 0]),
  )

  return plans.map((plan) => ({
    ...plan,
    entries_count: entryCountByPlan.get(plan.id) ?? 0,
    day_slots_count: daySlotCountByPlan.get(plan.id) ?? 0,
  }))
}

async function getMealPlanById(mealPlanId, user, transaction = undefined) {
  const plan = await getOwnedPlanById(mealPlanId, user.id, transaction)
  if (!plan) {
    return null
  }

  await ensureDaySlotsInPlanRange(mealPlanId, plan.start_date, plan.end_date, transaction)

  const mealSlots = await getMealPlanMealSlots(mealPlanId, transaction)
  const daySlotsRaw = await getMealPlanDaySlots(mealPlanId, transaction)
  const resolvedDaySlots = await buildResolvedDaySlots(plan, daySlotsRaw, mealSlots, transaction)

  return {
    ...plan,
    entries: await getMealPlanEntries(mealPlanId, transaction),
    meal_slots: mealSlots,
    day_slots: resolvedDaySlots.daySlots,
    totals: resolvedDaySlots.totals,
  }
}

async function createMealPlan(payload, user) {
  const normalized = validateMealPlanPayload(payload)

  const nextMealPlanId = await sequelize.transaction(async (transaction) => {
    const created = await models.mealPlan.create(
      {
        owner_user_id: user.id,
        name: normalized.name,
        start_date: normalized.start_date,
        end_date: normalized.end_date,
        note: normalized.note,
        portions_count: normalized.portions_count,
      },
      { transaction },
    )

    await ensureDaySlotsInPlanRange(
      created.id,
      normalized.start_date,
      normalized.end_date,
      transaction,
    )

    const providedMealSlots = Array.isArray(payload?.meal_slots)
      ? normalizeMealSlotsPayload(payload.meal_slots)
      : null

    if (providedMealSlots && providedMealSlots.length > 0) {
      await insertMealPlanSlots(created.id, providedMealSlots, transaction)
    } else {
      await seedDefaultMealPlanSlots(created.id, transaction)
    }

    return created.id
  })

  return getMealPlanById(nextMealPlanId, user)
}

async function updateMealPlan(mealPlanId, payload, user) {
  const existing = await getOwnedPlanById(mealPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalized = validateMealPlanPayload(payload)

  await sequelize.transaction(async (transaction) => {
    await models.mealPlan.update(
      {
        name: normalized.name,
        start_date: normalized.start_date,
        end_date: normalized.end_date,
        note: normalized.note,
        portions_count: normalized.portions_count,
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: mealPlanId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )

    await ensureDaySlotsInPlanRange(
      mealPlanId,
      normalized.start_date,
      normalized.end_date,
      transaction,
    )

    if (Array.isArray(payload?.meal_slots)) {
      const mealSlots = normalizeMealSlotsPayload(payload.meal_slots)

      await models.mealPlanMealSlot.destroy({
        where: { meal_plan_id: mealPlanId },
        transaction,
      })
      await insertMealPlanSlots(mealPlanId, mealSlots, transaction)
    }
  })

  return getMealPlanById(mealPlanId, user)
}

async function deleteMealPlan(mealPlanId, user) {
  const deleted = await models.mealPlan.destroy({
    where: {
      id: mealPlanId,
      owner_user_id: user.id,
    },
  })

  return deleted > 0
}

async function replaceMealPlanMealSlots(mealPlanId, slots, user) {
  const existing = await getOwnedPlanById(mealPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalizedSlots = normalizeMealSlotsPayload(slots)

  await sequelize.transaction(async (transaction) => {
    await models.mealPlanMealSlot.destroy({
      where: { meal_plan_id: mealPlanId },
      transaction,
    })
    await insertMealPlanSlots(mealPlanId, normalizedSlots, transaction)

    await models.mealPlan.update(
      { updated_at: new Date().toISOString() },
      {
        where: {
          id: mealPlanId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return getMealPlanById(mealPlanId, user)
}

async function updateMealPlanDaySlot(mealPlanId, plannedDateRaw, payload, user) {
  const plan = await getOwnedPlanById(mealPlanId, user.id)
  if (!plan) {
    return null
  }

  const plannedDate = normalizeDate(plannedDateRaw)
  if (!plannedDate) {
    throw new Error('planned_date must use YYYY-MM-DD format')
  }

  if (plannedDate < plan.start_date || plannedDate > plan.end_date) {
    throw new Error('planned_date must be within meal plan date range')
  }

  const dayPlanId = parseOptionalInteger(payload?.day_plan_id)
  const note = typeof payload?.note === 'string' ? payload.note.trim() : ''

  if (dayPlanId && !(await getOwnedDayPlanById(dayPlanId, user.id))) {
    throw new Error('day_plan_id does not belong to current user')
  }

  await sequelize.transaction(async (transaction) => {
    const slot = await ensureSlotByPlanAndDate(mealPlanId, plannedDate, transaction)
    const slotLimit = await getMealSlotLimit(mealPlanId, transaction)

    const importedMeals = dayPlanId
      ? normalizeDayMealsPayload(
          (await getDayPlanMealsForImport(dayPlanId, transaction)).map((meal) => ({
            ...meal,
            servings: null,
            portions: meal.portions ?? meal.servings ?? 1,
          })),
          {
            maxMeals: slotLimit,
          },
        )
      : []

    await models.mealPlanDaySlot.update(
      {
        day_plan_id: null,
        note,
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: slot.id,
          meal_plan_id: mealPlanId,
        },
        transaction,
      },
    )

    if (dayPlanId) {
      await models.mealPlanDaySlotMeal.destroy({
        where: { day_slot_id: slot.id },
        transaction,
      })

      if (importedMeals.length > 0) {
        await models.mealPlanDaySlotMeal.bulkCreate(
          importedMeals.map((meal) => ({
            day_slot_id: slot.id,
            recipe_id: meal.recipe_id,
            servings: meal.servings,
            portions: meal.portions,
            note: meal.note,
            meal_order: meal.meal_order,
          })),
          { transaction },
        )
      }
    }

    await models.mealPlan.update(
      {
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: mealPlanId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return getMealPlanById(mealPlanId, user)
}

async function replaceMealPlanDaySlotMeals(mealPlanId, plannedDateRaw, meals, user) {
  const plan = await getOwnedPlanById(mealPlanId, user.id)
  if (!plan) {
    return null
  }

  const plannedDate = normalizeDate(plannedDateRaw)
  if (!plannedDate) {
    throw new Error('planned_date must use YYYY-MM-DD format')
  }

  if (plannedDate < plan.start_date || plannedDate > plan.end_date) {
    throw new Error('planned_date must be within meal plan date range')
  }

  await sequelize.transaction(async (transaction) => {
    const slotLimit = await getMealSlotLimit(mealPlanId, transaction)
    const normalizedMeals = normalizeDayMealsPayload(meals, {
      maxMeals: slotLimit,
    })
    const slot = await ensureSlotByPlanAndDate(mealPlanId, plannedDate, transaction)

    await models.mealPlanDaySlot.update(
      {
        day_plan_id: null,
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: slot.id,
          meal_plan_id: mealPlanId,
        },
        transaction,
      },
    )

    await models.mealPlanDaySlotMeal.destroy({
      where: { day_slot_id: slot.id },
      transaction,
    })

    if (normalizedMeals.length > 0) {
      await models.mealPlanDaySlotMeal.bulkCreate(
        normalizedMeals.map((meal) => ({
          day_slot_id: slot.id,
          recipe_id: meal.recipe_id,
          servings: meal.servings,
          portions: meal.portions,
          note: meal.note,
          meal_order: meal.meal_order,
        })),
        { transaction },
      )
    }

    await models.mealPlan.update(
      {
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: mealPlanId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return getMealPlanById(mealPlanId, user)
}

async function replaceMealPlanEntries(mealPlanId, entries, user) {
  const plan = await getOwnedPlanById(mealPlanId, user.id)
  if (!plan) {
    return null
  }

  const normalizedEntries = Array.isArray(entries)
    ? entries.map((entry) => mapEntryPayload(entry, plan))
    : []

  const duplicateGuard = new Set()
  for (const entry of normalizedEntries) {
    const key = `${entry.planned_date}:${entry.meal_slot}`
    if (duplicateGuard.has(key)) {
      throw new Error(`Duplicate meal_slot for date ${entry.planned_date}`)
    }
    duplicateGuard.add(key)
  }

  await sequelize.transaction(async (transaction) => {
    await models.mealPlanEntry.destroy({
      where: { meal_plan_id: mealPlanId },
      transaction,
    })

    if (normalizedEntries.length > 0) {
      await models.mealPlanEntry.bulkCreate(
        normalizedEntries.map((entry) => ({
          meal_plan_id: mealPlanId,
          planned_date: entry.planned_date,
          meal_slot: entry.meal_slot,
          recipe_id: entry.recipe_id,
          custom_name: entry.custom_name,
          servings: entry.servings,
          note: entry.note,
        })),
        { transaction },
      )
    }

    await models.mealPlan.update(
      {
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: mealPlanId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return getMealPlanById(mealPlanId, user)
}

export default {
  listMealPlans,
  getMealPlanById,
  createMealPlan,
  updateMealPlan,
  deleteMealPlan,
  replaceMealPlanMealSlots,
  updateMealPlanDaySlot,
  replaceMealPlanDaySlotMeals,
  replaceMealPlanEntries,
}
