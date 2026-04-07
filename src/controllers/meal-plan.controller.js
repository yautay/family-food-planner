import catalogDb from '../db/catalog.js'

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

function getMealSlotLimit(mealPlanId) {
  const row = catalogDb
    .prepare(
      `
      SELECT COUNT(*) AS slots_count
      FROM meal_plan_meal_slots
      WHERE meal_plan_id = ?
      `,
    )
    .get(mealPlanId)

  const slotsCount = Number(row?.slots_count)
  return Number.isInteger(slotsCount) && slotsCount > 0 ? slotsCount : 0
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

function ensureDaySlotsInPlanRange(mealPlanId, startDate, endDate) {
  const dates = buildDateRange(startDate, endDate)

  catalogDb.transaction(() => {
    catalogDb
      .prepare(
        `
        DELETE FROM meal_plan_day_slots
        WHERE meal_plan_id = ? AND (planned_date < ? OR planned_date > ?)
        `,
      )
      .run(mealPlanId, startDate, endDate)

    const existingDates = new Set(
      catalogDb
        .prepare(
          `
          SELECT planned_date
          FROM meal_plan_day_slots
          WHERE meal_plan_id = ?
          `,
        )
        .all(mealPlanId)
        .map((row) => row.planned_date),
    )

    const insertDaySlot = catalogDb.prepare(
      `
      INSERT INTO meal_plan_day_slots(meal_plan_id, planned_date, day_plan_id, note)
      VALUES (?, ?, NULL, '')
      `,
    )

    for (const plannedDate of dates) {
      if (!existingDates.has(plannedDate)) {
        insertDaySlot.run(mealPlanId, plannedDate)
      }
    }
  })()
}

function insertMealPlanSlots(mealPlanId, slots) {
  const insertSlot = catalogDb.prepare(
    `
    INSERT INTO meal_plan_meal_slots(meal_plan_id, slot_name, slot_time, sort_order)
    VALUES (?, ?, ?, ?)
    `,
  )

  for (const slot of slots) {
    insertSlot.run(mealPlanId, slot.slot_name, slot.slot_time, slot.sort_order)
  }
}

function seedDefaultMealPlanSlots(mealPlanId) {
  insertMealPlanSlots(
    mealPlanId,
    DEFAULT_MEAL_SLOTS.map((slotName, index) => ({
      slot_name: slotName,
      slot_time: null,
      sort_order: index + 1,
    })),
  )
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

function getOwnedPlanById(mealPlanId, ownerUserId) {
  return catalogDb
    .prepare(
      `
      SELECT
        id,
        owner_user_id,
        name,
        start_date,
        end_date,
        note,
        portions_count,
        created_at,
        updated_at
      FROM meal_plans
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .get(mealPlanId, ownerUserId)
}

function getOwnedDayPlanById(dayPlanId, ownerUserId) {
  return catalogDb
    .prepare('SELECT id, owner_user_id, name FROM day_plans WHERE id = ? AND owner_user_id = ?')
    .get(dayPlanId, ownerUserId)
}

function getMealPlanEntries(mealPlanId) {
  return catalogDb
    .prepare(
      `
      SELECT
        e.id,
        e.meal_plan_id,
        e.planned_date,
        e.meal_slot,
        e.recipe_id,
        r.name AS recipe_name,
        e.custom_name,
        e.servings,
        e.note,
        e.created_at
      FROM meal_plan_entries e
      LEFT JOIN recipes r ON r.id = e.recipe_id
      WHERE e.meal_plan_id = ?
      ORDER BY e.planned_date ASC, e.meal_slot ASC
      `,
    )
    .all(mealPlanId)
}

function getMealPlanMealSlots(mealPlanId) {
  return catalogDb
    .prepare(
      `
      SELECT id, meal_plan_id, slot_name, slot_time, sort_order, created_at, updated_at
      FROM meal_plan_meal_slots
      WHERE meal_plan_id = ?
      ORDER BY sort_order ASC
      `,
    )
    .all(mealPlanId)
}

function getMealPlanDaySlots(mealPlanId) {
  return catalogDb
    .prepare(
      `
      SELECT
        s.id,
        s.meal_plan_id,
        s.planned_date,
        s.day_plan_id,
        d.name AS day_plan_name,
        s.note,
        s.created_at,
        s.updated_at
      FROM meal_plan_day_slots s
      LEFT JOIN day_plans d ON d.id = s.day_plan_id
      WHERE s.meal_plan_id = ?
      ORDER BY s.planned_date ASC
      `,
    )
    .all(mealPlanId)
}

function getSlotByPlanAndDate(mealPlanId, plannedDate) {
  return catalogDb
    .prepare(
      `
      SELECT id, meal_plan_id, planned_date, day_plan_id, note
      FROM meal_plan_day_slots
      WHERE meal_plan_id = ? AND planned_date = ?
      `,
    )
    .get(mealPlanId, plannedDate)
}

function ensureSlotByPlanAndDate(mealPlanId, plannedDate) {
  const existing = getSlotByPlanAndDate(mealPlanId, plannedDate)
  if (existing) {
    return existing
  }

  const result = catalogDb
    .prepare(
      `
      INSERT INTO meal_plan_day_slots(meal_plan_id, planned_date, day_plan_id, note)
      VALUES (?, ?, NULL, '')
      `,
    )
    .run(mealPlanId, plannedDate)

  return (
    getSlotByPlanAndDate(mealPlanId, plannedDate) ?? {
      id: Number(result.lastInsertRowid),
      meal_plan_id: mealPlanId,
      planned_date: plannedDate,
      day_plan_id: null,
      note: '',
    }
  )
}

function getDayPlanMealsByDayPlanIds(dayPlanIds) {
  if (dayPlanIds.length === 0) {
    return new Map()
  }

  const placeholders = dayPlanIds.map(() => '?').join(', ')
  const rows = catalogDb
    .prepare(
      `
      SELECT
        m.id,
        m.day_plan_id,
        m.recipe_id,
        r.name AS recipe_name,
        m.servings,
        m.portions,
        m.note,
        m.meal_order,
        m.created_at,
        m.updated_at
      FROM day_plan_meals m
      INNER JOIN recipes r ON r.id = m.recipe_id
      WHERE m.day_plan_id IN (${placeholders})
      ORDER BY m.day_plan_id ASC, m.meal_order ASC
      `,
    )
    .all(...dayPlanIds)

  const grouped = new Map()
  for (const row of rows) {
    if (!grouped.has(row.day_plan_id)) {
      grouped.set(row.day_plan_id, [])
    }
    grouped.get(row.day_plan_id).push({
      id: row.id,
      day_plan_id: row.day_plan_id,
      recipe_id: row.recipe_id,
      recipe_name: row.recipe_name,
      servings: row.servings,
      portions: row.portions,
      note: row.note,
      meal_order: row.meal_order,
      created_at: row.created_at,
      updated_at: row.updated_at,
    })
  }

  return grouped
}

function getDayPlanMealsForImport(dayPlanId) {
  return catalogDb
    .prepare(
      `
      SELECT recipe_id, servings, portions, note, meal_order
      FROM day_plan_meals
      WHERE day_plan_id = ?
      ORDER BY meal_order ASC
      `,
    )
    .all(dayPlanId)
}

function getCustomDaySlotMealsBySlotIds(slotIds) {
  if (slotIds.length === 0) {
    return new Map()
  }

  const placeholders = slotIds.map(() => '?').join(', ')
  const rows = catalogDb
    .prepare(
      `
      SELECT
        m.id,
        m.day_slot_id,
        m.recipe_id,
        r.name AS recipe_name,
        m.servings,
        m.portions,
        m.note,
        m.meal_order,
        m.created_at,
        m.updated_at
      FROM meal_plan_day_slot_meals m
      INNER JOIN recipes r ON r.id = m.recipe_id
      WHERE m.day_slot_id IN (${placeholders})
      ORDER BY m.day_slot_id ASC, m.meal_order ASC
      `,
    )
    .all(...slotIds)

  const grouped = new Map()
  for (const row of rows) {
    if (!grouped.has(row.day_slot_id)) {
      grouped.set(row.day_slot_id, [])
    }
    grouped.get(row.day_slot_id).push({
      id: row.id,
      day_slot_id: row.day_slot_id,
      recipe_id: row.recipe_id,
      recipe_name: row.recipe_name,
      servings: row.servings,
      portions: row.portions,
      note: row.note,
      meal_order: row.meal_order,
      created_at: row.created_at,
      updated_at: row.updated_at,
    })
  }

  return grouped
}

function buildResolvedDaySlots(plan, daySlots, mealSlots) {
  const dayPlanIds = Array.from(new Set(daySlots.map((slot) => slot.day_plan_id).filter(Boolean)))
  const slotIds = daySlots.map((slot) => slot.id)

  const groupedTemplateMeals = getDayPlanMealsByDayPlanIds(dayPlanIds)
  const groupedCustomMeals = getCustomDaySlotMealsBySlotIds(slotIds)

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

  const nutritionMap = getRecipeNutritionMap(recipeIds)

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
  return catalogDb
    .prepare(
      `
      SELECT
        p.id,
        p.owner_user_id,
        p.name,
        p.start_date,
        p.end_date,
        p.note,
        p.portions_count,
        p.created_at,
        p.updated_at,
        (
          SELECT COUNT(*)
          FROM meal_plan_entries e
          WHERE e.meal_plan_id = p.id
        ) AS entries_count,
        (
          SELECT COUNT(*)
          FROM meal_plan_day_slots s
          WHERE s.meal_plan_id = p.id
        ) AS day_slots_count
      FROM meal_plans p
      WHERE p.owner_user_id = ?
      ORDER BY p.start_date DESC, p.created_at DESC
      `,
    )
    .all(user.id)
}

async function getMealPlanById(mealPlanId, user) {
  const plan = getOwnedPlanById(mealPlanId, user.id)
  if (!plan) {
    return null
  }

  ensureDaySlotsInPlanRange(mealPlanId, plan.start_date, plan.end_date)

  const mealSlots = getMealPlanMealSlots(mealPlanId)
  const daySlotsRaw = getMealPlanDaySlots(mealPlanId)
  const resolvedDaySlots = buildResolvedDaySlots(plan, daySlotsRaw, mealSlots)

  return {
    ...plan,
    entries: getMealPlanEntries(mealPlanId),
    meal_slots: mealSlots,
    day_slots: resolvedDaySlots.daySlots,
    totals: resolvedDaySlots.totals,
  }
}

async function createMealPlan(payload, user) {
  const normalized = validateMealPlanPayload(payload)

  const result = catalogDb
    .prepare(
      `
      INSERT INTO meal_plans(owner_user_id, name, start_date, end_date, note, portions_count)
      VALUES (?, ?, ?, ?, ?, ?)
      `,
    )
    .run(
      user.id,
      normalized.name,
      normalized.start_date,
      normalized.end_date,
      normalized.note,
      normalized.portions_count,
    )

  const nextMealPlanId = Number(result.lastInsertRowid)

  catalogDb.transaction(() => {
    ensureDaySlotsInPlanRange(nextMealPlanId, normalized.start_date, normalized.end_date)

    const providedMealSlots = Array.isArray(payload?.meal_slots)
      ? normalizeMealSlotsPayload(payload.meal_slots)
      : null

    if (providedMealSlots && providedMealSlots.length > 0) {
      insertMealPlanSlots(nextMealPlanId, providedMealSlots)
    } else {
      seedDefaultMealPlanSlots(nextMealPlanId)
    }
  })()

  return getMealPlanById(nextMealPlanId, user)
}

async function updateMealPlan(mealPlanId, payload, user) {
  const existing = getOwnedPlanById(mealPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalized = validateMealPlanPayload(payload)

  catalogDb
    .prepare(
      `
      UPDATE meal_plans
      SET
        name = ?,
        start_date = ?,
        end_date = ?,
        note = ?,
        portions_count = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .run(
      normalized.name,
      normalized.start_date,
      normalized.end_date,
      normalized.note,
      normalized.portions_count,
      mealPlanId,
      user.id,
    )

  catalogDb.transaction(() => {
    ensureDaySlotsInPlanRange(mealPlanId, normalized.start_date, normalized.end_date)

    if (Array.isArray(payload?.meal_slots)) {
      const mealSlots = normalizeMealSlotsPayload(payload.meal_slots)

      catalogDb.prepare('DELETE FROM meal_plan_meal_slots WHERE meal_plan_id = ?').run(mealPlanId)
      insertMealPlanSlots(mealPlanId, mealSlots)
    }
  })()

  return getMealPlanById(mealPlanId, user)
}

async function deleteMealPlan(mealPlanId, user) {
  const deleted = catalogDb
    .prepare('DELETE FROM meal_plans WHERE id = ? AND owner_user_id = ?')
    .run(mealPlanId, user.id)

  return deleted.changes > 0
}

async function replaceMealPlanMealSlots(mealPlanId, slots, user) {
  const existing = getOwnedPlanById(mealPlanId, user.id)
  if (!existing) {
    return null
  }

  const normalizedSlots = normalizeMealSlotsPayload(slots)

  catalogDb.transaction(() => {
    catalogDb.prepare('DELETE FROM meal_plan_meal_slots WHERE meal_plan_id = ?').run(mealPlanId)
    insertMealPlanSlots(mealPlanId, normalizedSlots)

    catalogDb
      .prepare(
        'UPDATE meal_plans SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?',
      )
      .run(mealPlanId, user.id)
  })()

  return getMealPlanById(mealPlanId, user)
}

async function updateMealPlanDaySlot(mealPlanId, plannedDateRaw, payload, user) {
  const plan = getOwnedPlanById(mealPlanId, user.id)
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

  if (dayPlanId && !getOwnedDayPlanById(dayPlanId, user.id)) {
    throw new Error('day_plan_id does not belong to current user')
  }

  const slot = ensureSlotByPlanAndDate(mealPlanId, plannedDate)
  const slotLimit = getMealSlotLimit(mealPlanId)
  const importedMeals = dayPlanId
    ? normalizeDayMealsPayload(
        getDayPlanMealsForImport(dayPlanId).map((meal) => ({
          ...meal,
          servings: null,
          portions: meal.portions ?? meal.servings ?? 1,
        })),
        {
          maxMeals: slotLimit,
        },
      )
    : []

  catalogDb.transaction(() => {
    if (dayPlanId) {
      catalogDb
        .prepare(
          `
          UPDATE meal_plan_day_slots
          SET day_plan_id = NULL, note = ?, updated_at = CURRENT_TIMESTAMP
          WHERE id = ? AND meal_plan_id = ?
          `,
        )
        .run(note, slot.id, mealPlanId)

      catalogDb.prepare('DELETE FROM meal_plan_day_slot_meals WHERE day_slot_id = ?').run(slot.id)

      const insertMeal = catalogDb.prepare(
        `
        INSERT INTO meal_plan_day_slot_meals(day_slot_id, recipe_id, servings, portions, note, meal_order)
        VALUES (?, ?, ?, ?, ?, ?)
        `,
      )

      for (const meal of importedMeals) {
        insertMeal.run(
          slot.id,
          meal.recipe_id,
          meal.servings,
          meal.portions,
          meal.note,
          meal.meal_order,
        )
      }
    } else {
      catalogDb
        .prepare(
          `
          UPDATE meal_plan_day_slots
          SET day_plan_id = NULL, note = ?, updated_at = CURRENT_TIMESTAMP
          WHERE id = ? AND meal_plan_id = ?
          `,
        )
        .run(note, slot.id, mealPlanId)
    }

    catalogDb
      .prepare(
        'UPDATE meal_plans SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?',
      )
      .run(mealPlanId, user.id)
  })()

  return getMealPlanById(mealPlanId, user)
}

async function replaceMealPlanDaySlotMeals(mealPlanId, plannedDateRaw, meals, user) {
  const plan = getOwnedPlanById(mealPlanId, user.id)
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

  const slotLimit = getMealSlotLimit(mealPlanId)
  const normalizedMeals = normalizeDayMealsPayload(meals, {
    maxMeals: slotLimit,
  })
  const slot = ensureSlotByPlanAndDate(mealPlanId, plannedDate)

  catalogDb.transaction(() => {
    catalogDb
      .prepare(
        `
        UPDATE meal_plan_day_slots
        SET day_plan_id = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND meal_plan_id = ?
        `,
      )
      .run(slot.id, mealPlanId)

    catalogDb.prepare('DELETE FROM meal_plan_day_slot_meals WHERE day_slot_id = ?').run(slot.id)

    const insertMeal = catalogDb.prepare(
      `
      INSERT INTO meal_plan_day_slot_meals(day_slot_id, recipe_id, servings, portions, note, meal_order)
      VALUES (?, ?, ?, ?, ?, ?)
      `,
    )

    for (const meal of normalizedMeals) {
      insertMeal.run(
        slot.id,
        meal.recipe_id,
        meal.servings,
        meal.portions,
        meal.note,
        meal.meal_order,
      )
    }

    catalogDb
      .prepare(
        'UPDATE meal_plans SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?',
      )
      .run(mealPlanId, user.id)
  })()

  return getMealPlanById(mealPlanId, user)
}

async function replaceMealPlanEntries(mealPlanId, entries, user) {
  const plan = getOwnedPlanById(mealPlanId, user.id)
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

  catalogDb.transaction(() => {
    catalogDb.prepare('DELETE FROM meal_plan_entries WHERE meal_plan_id = ?').run(mealPlanId)

    const insertEntry = catalogDb.prepare(
      `
      INSERT INTO meal_plan_entries(meal_plan_id, planned_date, meal_slot, recipe_id, custom_name, servings, note)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      `,
    )

    for (const entry of normalizedEntries) {
      insertEntry.run(
        mealPlanId,
        entry.planned_date,
        entry.meal_slot,
        entry.recipe_id,
        entry.custom_name,
        entry.servings,
        entry.note,
      )
    }

    catalogDb
      .prepare(
        'UPDATE meal_plans SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?',
      )
      .run(mealPlanId, user.id)
  })()

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
