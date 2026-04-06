import catalogDb from '../db/catalog.js'

const ALLOWED_MEAL_SLOTS = new Set(['breakfast', 'lunch', 'dinner', 'snack'])

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

function validateMealPlanPayload(payload) {
  const name = normalizeText(payload?.name)
  const startDate = normalizeDate(payload?.start_date)
  const endDate = normalizeDate(payload?.end_date)
  const note = typeof payload?.note === 'string' ? payload.note.trim() : ''

  if (!name) {
    throw new Error('Meal plan name is required')
  }

  if (!startDate || !endDate) {
    throw new Error('start_date and end_date must use YYYY-MM-DD format')
  }

  if (startDate > endDate) {
    throw new Error('start_date must be before or equal to end_date')
  }

  return {
    name,
    start_date: startDate,
    end_date: endDate,
    note,
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
      SELECT id, owner_user_id, name, start_date, end_date, note, created_at, updated_at
      FROM meal_plans
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .get(mealPlanId, ownerUserId)
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
        p.created_at,
        p.updated_at,
        COUNT(e.id) AS entries_count
      FROM meal_plans p
      LEFT JOIN meal_plan_entries e ON e.meal_plan_id = p.id
      WHERE p.owner_user_id = ?
      GROUP BY p.id
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

  return {
    ...plan,
    entries: getMealPlanEntries(mealPlanId),
  }
}

async function createMealPlan(payload, user) {
  const normalized = validateMealPlanPayload(payload)

  const result = catalogDb
    .prepare(
      `
      INSERT INTO meal_plans(owner_user_id, name, start_date, end_date, note)
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(user.id, normalized.name, normalized.start_date, normalized.end_date, normalized.note)

  return getMealPlanById(Number(result.lastInsertRowid), user)
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
      SET name = ?, start_date = ?, end_date = ?, note = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .run(
      normalized.name,
      normalized.start_date,
      normalized.end_date,
      normalized.note,
      mealPlanId,
      user.id,
    )

  return getMealPlanById(mealPlanId, user)
}

async function deleteMealPlan(mealPlanId, user) {
  const deleted = catalogDb
    .prepare('DELETE FROM meal_plans WHERE id = ? AND owner_user_id = ?')
    .run(mealPlanId, user.id)

  return deleted.changes > 0
}

async function replaceMealPlanEntries(mealPlanId, entries, user) {
  const plan = getOwnedPlanById(mealPlanId, user.id)
  if (!plan) {
    return null
  }

  const normalizedEntries = Array.isArray(entries) ? entries.map((entry) => mapEntryPayload(entry, plan)) : []

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
      .prepare('UPDATE meal_plans SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?')
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
  replaceMealPlanEntries,
}
