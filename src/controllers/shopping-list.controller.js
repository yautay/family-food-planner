import catalogDb from '../db/catalog.js'

const SHOPPING_LIST_STATUSES = new Set(['open', 'archived'])

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

function getOwnedMealPlanById(mealPlanId, ownerUserId) {
  return catalogDb
    .prepare('SELECT id FROM meal_plans WHERE id = ? AND owner_user_id = ?')
    .get(mealPlanId, ownerUserId)
}

function validateShoppingListPayload(payload, ownerUserId) {
  const name = normalizeText(payload?.name)
  const status = normalizeText(payload?.status).toLowerCase() || 'open'
  const note = typeof payload?.note === 'string' ? payload.note.trim() : ''
  const mealPlanId = parseOptionalInteger(payload?.meal_plan_id)

  if (!name) {
    throw new Error('Shopping list name is required')
  }

  if (!SHOPPING_LIST_STATUSES.has(status)) {
    throw new Error('status must be one of: open, archived')
  }

  if (mealPlanId && !getOwnedMealPlanById(mealPlanId, ownerUserId)) {
    throw new Error('meal_plan_id does not belong to current user')
  }

  return {
    name,
    status,
    note,
    meal_plan_id: mealPlanId,
  }
}

function normalizeItemPayload(payload) {
  const productId = parseOptionalInteger(payload?.product_id)
  const customName = normalizeText(payload?.custom_name)
  const quantity = parseOptionalNumber(payload?.quantity)
  const unitId = parseOptionalInteger(payload?.unit_id)
  const note = typeof payload?.note === 'string' ? payload.note.trim() : ''
  const checkedRaw = payload?.is_checked

  let isChecked = 0
  if (checkedRaw === true || checkedRaw === 1 || checkedRaw === '1') {
    isChecked = 1
  }

  if (!productId && !customName) {
    throw new Error('Shopping list item requires product_id or custom_name')
  }

  if (quantity !== null && quantity < 0) {
    throw new Error('quantity cannot be negative')
  }

  return {
    product_id: productId,
    custom_name: customName || null,
    quantity,
    unit_id: unitId,
    note,
    is_checked: isChecked,
  }
}

function getOwnedShoppingListById(shoppingListId, ownerUserId) {
  return catalogDb
    .prepare(
      `
      SELECT id, owner_user_id, meal_plan_id, name, status, note, created_at, updated_at
      FROM shopping_lists
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .get(shoppingListId, ownerUserId)
}

function getShoppingListItems(shoppingListId) {
  return catalogDb
    .prepare(
      `
      SELECT
        i.id,
        i.shopping_list_id,
        i.product_id,
        p.name AS product_name,
        i.custom_name,
        i.quantity,
        i.unit_id,
        u.name AS unit_name,
        i.is_checked,
        i.note,
        i.created_at,
        i.updated_at
      FROM shopping_list_items i
      LEFT JOIN products p ON p.id = i.product_id
      LEFT JOIN units u ON u.id = i.unit_id
      WHERE i.shopping_list_id = ?
      ORDER BY i.is_checked ASC, i.id ASC
      `,
    )
    .all(shoppingListId)
}

function getOwnedShoppingListItem(shoppingListId, itemId, ownerUserId) {
  return catalogDb
    .prepare(
      `
      SELECT i.*
      FROM shopping_list_items i
      INNER JOIN shopping_lists s ON s.id = i.shopping_list_id
      WHERE i.id = ? AND i.shopping_list_id = ? AND s.owner_user_id = ?
      `,
    )
    .get(itemId, shoppingListId, ownerUserId)
}

async function listShoppingLists(user) {
  return catalogDb
    .prepare(
      `
      SELECT
        s.id,
        s.owner_user_id,
        s.meal_plan_id,
        s.name,
        s.status,
        s.note,
        s.created_at,
        s.updated_at,
        COUNT(i.id) AS items_count,
        COALESCE(SUM(i.is_checked), 0) AS checked_count
      FROM shopping_lists s
      LEFT JOIN shopping_list_items i ON i.shopping_list_id = s.id
      WHERE s.owner_user_id = ?
      GROUP BY s.id
      ORDER BY s.created_at DESC
      `,
    )
    .all(user.id)
}

async function getShoppingListById(shoppingListId, user) {
  const shoppingList = getOwnedShoppingListById(shoppingListId, user.id)
  if (!shoppingList) {
    return null
  }

  return {
    ...shoppingList,
    items: getShoppingListItems(shoppingListId),
  }
}

async function createShoppingList(payload, user) {
  const normalized = validateShoppingListPayload(payload, user.id)

  const result = catalogDb
    .prepare(
      `
      INSERT INTO shopping_lists(owner_user_id, meal_plan_id, name, status, note)
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(user.id, normalized.meal_plan_id, normalized.name, normalized.status, normalized.note)

  return getShoppingListById(Number(result.lastInsertRowid), user)
}

async function updateShoppingList(shoppingListId, payload, user) {
  const existing = getOwnedShoppingListById(shoppingListId, user.id)
  if (!existing) {
    return null
  }

  const normalized = validateShoppingListPayload(
    {
      name: payload?.name ?? existing.name,
      status: payload?.status ?? existing.status,
      note: payload?.note ?? existing.note,
      meal_plan_id: payload?.meal_plan_id ?? existing.meal_plan_id,
    },
    user.id,
  )

  catalogDb
    .prepare(
      `
      UPDATE shopping_lists
      SET meal_plan_id = ?, name = ?, status = ?, note = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ? AND owner_user_id = ?
      `,
    )
    .run(
      normalized.meal_plan_id,
      normalized.name,
      normalized.status,
      normalized.note,
      shoppingListId,
      user.id,
    )

  return getShoppingListById(shoppingListId, user)
}

async function deleteShoppingList(shoppingListId, user) {
  const deleted = catalogDb
    .prepare('DELETE FROM shopping_lists WHERE id = ? AND owner_user_id = ?')
    .run(shoppingListId, user.id)

  return deleted.changes > 0
}

async function addShoppingListItem(shoppingListId, payload, user) {
  const shoppingList = getOwnedShoppingListById(shoppingListId, user.id)
  if (!shoppingList) {
    return null
  }

  const item = normalizeItemPayload(payload)

  catalogDb.transaction(() => {
    catalogDb
      .prepare(
        `
        INSERT INTO shopping_list_items(shopping_list_id, product_id, custom_name, quantity, unit_id, is_checked, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        `,
      )
      .run(
        shoppingListId,
        item.product_id,
        item.custom_name,
        item.quantity,
        item.unit_id,
        item.is_checked,
        item.note,
      )

    catalogDb
      .prepare('UPDATE shopping_lists SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?')
      .run(shoppingListId, user.id)
  })()

  return getShoppingListById(shoppingListId, user)
}

async function updateShoppingListItem(shoppingListId, itemId, payload, user) {
  const existing = getOwnedShoppingListItem(shoppingListId, itemId, user.id)
  if (!existing) {
    return null
  }

  const item = normalizeItemPayload({
    product_id: payload?.product_id ?? existing.product_id,
    custom_name: payload?.custom_name ?? existing.custom_name,
    quantity: payload?.quantity ?? existing.quantity,
    unit_id: payload?.unit_id ?? existing.unit_id,
    is_checked: payload?.is_checked ?? existing.is_checked,
    note: payload?.note ?? existing.note,
  })

  catalogDb.transaction(() => {
    catalogDb
      .prepare(
        `
        UPDATE shopping_list_items
        SET product_id = ?, custom_name = ?, quantity = ?, unit_id = ?, is_checked = ?, note = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND shopping_list_id = ?
        `,
      )
      .run(
        item.product_id,
        item.custom_name,
        item.quantity,
        item.unit_id,
        item.is_checked,
        item.note,
        itemId,
        shoppingListId,
      )

    catalogDb
      .prepare('UPDATE shopping_lists SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?')
      .run(shoppingListId, user.id)
  })()

  return getShoppingListById(shoppingListId, user)
}

async function deleteShoppingListItem(shoppingListId, itemId, user) {
  const existing = getOwnedShoppingListItem(shoppingListId, itemId, user.id)
  if (!existing) {
    return false
  }

  catalogDb.transaction(() => {
    catalogDb
      .prepare('DELETE FROM shopping_list_items WHERE id = ? AND shopping_list_id = ?')
      .run(itemId, shoppingListId)

    catalogDb
      .prepare('UPDATE shopping_lists SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ?')
      .run(shoppingListId, user.id)
  })()

  return true
}

export default {
  listShoppingLists,
  getShoppingListById,
  createShoppingList,
  updateShoppingList,
  deleteShoppingList,
  addShoppingListItem,
  updateShoppingListItem,
  deleteShoppingListItem,
}
