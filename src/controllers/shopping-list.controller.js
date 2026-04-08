import { Op, fn, col } from 'sequelize'
import sequelize from '../db/client.js'
import models from '../models/index.js'

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

async function getOwnedMealPlanById(mealPlanId, ownerUserId) {
  return models.mealPlan.findOne({
    where: {
      id: mealPlanId,
      owner_user_id: ownerUserId,
    },
    attributes: ['id'],
    raw: true,
  })
}

async function getOwnedMealPlanForGeneration(mealPlanId, ownerUserId) {
  return models.mealPlan.findOne({
    where: {
      id: mealPlanId,
      owner_user_id: ownerUserId,
    },
    attributes: ['id', 'name', 'portions_count'],
    raw: true,
  })
}

async function validateShoppingListPayload(payload, ownerUserId) {
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

  if (mealPlanId && !(await getOwnedMealPlanById(mealPlanId, ownerUserId))) {
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

async function getOwnedShoppingListById(shoppingListId, ownerUserId) {
  return models.shoppingList.findOne({
    where: {
      id: shoppingListId,
      owner_user_id: ownerUserId,
    },
    raw: true,
  })
}

async function getShoppingListItems(shoppingListId) {
  const rows = await models.shoppingListItem.findAll({
    where: { shopping_list_id: shoppingListId },
    include: [
      {
        model: models.product,
        as: 'product',
        attributes: ['name'],
        required: false,
      },
      {
        model: models.unit,
        as: 'unit',
        attributes: ['name'],
        required: false,
      },
    ],
    order: [
      ['is_checked', 'ASC'],
      ['id', 'ASC'],
    ],
  })

  return rows.map((row) => {
    const plain = row.get({ plain: true })
    return {
      id: plain.id,
      shopping_list_id: plain.shopping_list_id,
      product_id: plain.product_id,
      product_name: plain.product?.name ?? null,
      custom_name: plain.custom_name,
      quantity: plain.quantity,
      unit_id: plain.unit_id,
      unit_name: plain.unit?.name ?? null,
      is_checked: plain.is_checked,
      note: plain.note,
      created_at: plain.created_at,
      updated_at: plain.updated_at,
    }
  })
}

async function getOwnedShoppingListItem(shoppingListId, itemId, ownerUserId) {
  return models.shoppingListItem.findOne({
    where: {
      id: itemId,
      shopping_list_id: shoppingListId,
    },
    include: [
      {
        model: models.shoppingList,
        as: 'shoppingList',
        attributes: ['id', 'owner_user_id'],
        where: { owner_user_id: ownerUserId },
        required: true,
      },
    ],
    raw: true,
  })
}

function mergeGeneratedItem(targetMap, row) {
  if (!row.recipe_id) {
    const customName = normalizeText(row.entry_custom_name)
    if (!customName) {
      return
    }

    const key = `custom:${customName.toLowerCase()}`
    if (!targetMap.has(key)) {
      targetMap.set(key, {
        product_id: null,
        custom_name: customName,
        quantity: null,
        unit_id: null,
        note: '',
        is_checked: 0,
        has_quantity: false,
      })
    }

    return
  }

  if (!row.product_id) {
    return
  }

  const servings = parseOptionalNumber(row.servings)
  const portionsCount = parseOptionalNumber(row.portions_count)
  const mealPortions = parseOptionalNumber(row.meal_portions)
  const defaultMultiplier =
    (portionsCount !== null && portionsCount > 0 ? portionsCount : 1) *
    (mealPortions !== null && mealPortions > 0 ? mealPortions : 1)
  const mealMultiplier = servings !== null && servings > 0 ? servings : defaultMultiplier
  const quantity = parseOptionalNumber(row.quantity)
  const scaledQuantity = quantity === null ? null : quantity * mealMultiplier
  const key = `product:${row.product_id}:unit:${row.unit_id ?? 'none'}`

  if (!targetMap.has(key)) {
    targetMap.set(key, {
      product_id: row.product_id,
      custom_name: null,
      quantity: 0,
      unit_id: row.unit_id ?? null,
      note: '',
      is_checked: 0,
      has_quantity: false,
    })
  }

  if (scaledQuantity !== null) {
    const existing = targetMap.get(key)
    existing.quantity += scaledQuantity
    existing.has_quantity = true
  }
}

async function getRecipeIngredientRows(recipeIds) {
  if (!Array.isArray(recipeIds) || recipeIds.length === 0) {
    return []
  }

  const rows = await models.recipeIngredient.findAll({
    where: {
      recipe_id: {
        [Op.in]: recipeIds,
      },
    },
    include: [
      {
        model: models.product,
        as: 'product',
        attributes: ['default_unit_id'],
        required: false,
      },
    ],
    order: [['id', 'ASC']],
  })

  return rows.map((row) => {
    const plain = row.get({ plain: true })
    return {
      recipe_id: plain.recipe_id,
      product_id: plain.product_id,
      quantity: plain.quantity,
      unit_id: plain.unit_id ?? plain.product?.default_unit_id ?? null,
    }
  })
}

async function buildGeneratedItems(mealPlanId, portionsCount = 1) {
  const legacyEntries = await models.mealPlanEntry.findAll({
    where: { meal_plan_id: mealPlanId },
    order: [['id', 'ASC']],
    raw: true,
  })

  const templateSlots = await models.mealPlanDaySlot.findAll({
    where: {
      meal_plan_id: mealPlanId,
      day_plan_id: {
        [Op.not]: null,
      },
    },
    order: [['planned_date', 'ASC']],
    raw: true,
  })

  const customSlots = await models.mealPlanDaySlot.findAll({
    where: {
      meal_plan_id: mealPlanId,
      day_plan_id: null,
    },
    order: [['planned_date', 'ASC']],
    raw: true,
  })

  const dayPlanIds = Array.from(
    new Set(templateSlots.map((slot) => slot.day_plan_id).filter(Boolean)),
  )
  const dayPlanMeals =
    dayPlanIds.length > 0
      ? await models.dayPlanMeal.findAll({
          where: {
            day_plan_id: {
              [Op.in]: dayPlanIds,
            },
          },
          order: [['meal_order', 'ASC']],
          raw: true,
        })
      : []

  const customSlotIds = customSlots.map((slot) => slot.id)
  const customSlotMeals =
    customSlotIds.length > 0
      ? await models.mealPlanDaySlotMeal.findAll({
          where: {
            day_slot_id: {
              [Op.in]: customSlotIds,
            },
          },
          order: [
            ['day_slot_id', 'ASC'],
            ['meal_order', 'ASC'],
          ],
          raw: true,
        })
      : []

  const allRecipeIds = Array.from(
    new Set(
      [
        ...legacyEntries.map((entry) => entry.recipe_id),
        ...dayPlanMeals.map((meal) => meal.recipe_id),
        ...customSlotMeals.map((meal) => meal.recipe_id),
      ].filter((id) => Number.isInteger(id) && id > 0),
    ),
  )

  const ingredientRows = await getRecipeIngredientRows(allRecipeIds)
  const ingredientsByRecipeId = new Map()

  for (const row of ingredientRows) {
    if (!ingredientsByRecipeId.has(row.recipe_id)) {
      ingredientsByRecipeId.set(row.recipe_id, [])
    }

    ingredientsByRecipeId.get(row.recipe_id).push(row)
  }

  const mealsByDayPlanId = new Map()
  for (const meal of dayPlanMeals) {
    if (!mealsByDayPlanId.has(meal.day_plan_id)) {
      mealsByDayPlanId.set(meal.day_plan_id, [])
    }
    mealsByDayPlanId.get(meal.day_plan_id).push(meal)
  }

  const mealsByDaySlotId = new Map()
  for (const meal of customSlotMeals) {
    if (!mealsByDaySlotId.has(meal.day_slot_id)) {
      mealsByDaySlotId.set(meal.day_slot_id, [])
    }
    mealsByDaySlotId.get(meal.day_slot_id).push(meal)
  }

  const generatedItems = new Map()

  for (const entry of legacyEntries) {
    if (!entry.recipe_id) {
      mergeGeneratedItem(generatedItems, {
        recipe_id: null,
        entry_custom_name: entry.custom_name,
      })
      continue
    }

    const ingredients = ingredientsByRecipeId.get(entry.recipe_id) ?? []
    for (const ingredient of ingredients) {
      mergeGeneratedItem(generatedItems, {
        recipe_id: entry.recipe_id,
        entry_custom_name: null,
        servings: entry.servings,
        portions_count: portionsCount,
        meal_portions: 1,
        product_id: ingredient.product_id,
        quantity: ingredient.quantity,
        unit_id: ingredient.unit_id,
      })
    }
  }

  for (const slot of templateSlots) {
    const meals = mealsByDayPlanId.get(slot.day_plan_id) ?? []
    for (const meal of meals) {
      const ingredients = ingredientsByRecipeId.get(meal.recipe_id) ?? []
      for (const ingredient of ingredients) {
        mergeGeneratedItem(generatedItems, {
          recipe_id: meal.recipe_id,
          entry_custom_name: null,
          servings: meal.servings,
          portions_count: portionsCount,
          meal_portions: meal.portions,
          product_id: ingredient.product_id,
          quantity: ingredient.quantity,
          unit_id: ingredient.unit_id,
        })
      }
    }
  }

  for (const slot of customSlots) {
    const meals = mealsByDaySlotId.get(slot.id) ?? []
    for (const meal of meals) {
      const ingredients = ingredientsByRecipeId.get(meal.recipe_id) ?? []
      for (const ingredient of ingredients) {
        mergeGeneratedItem(generatedItems, {
          recipe_id: meal.recipe_id,
          entry_custom_name: null,
          servings: meal.servings,
          portions_count: portionsCount,
          meal_portions: meal.portions,
          product_id: ingredient.product_id,
          quantity: ingredient.quantity,
          unit_id: ingredient.unit_id,
        })
      }
    }
  }

  return Array.from(generatedItems.values()).map((item) => ({
    product_id: item.product_id,
    custom_name: item.custom_name,
    quantity: item.has_quantity ? item.quantity : null,
    unit_id: item.unit_id,
    note: item.note,
    is_checked: item.is_checked,
  }))
}

async function listShoppingLists(user) {
  const rows = await models.shoppingList.findAll({
    where: {
      owner_user_id: user.id,
    },
    order: [['created_at', 'DESC']],
    raw: true,
  })

  if (rows.length === 0) {
    return []
  }

  const ids = rows.map((row) => row.id)
  const statsRows = await models.shoppingListItem.findAll({
    attributes: [
      'shopping_list_id',
      [fn('COUNT', col('id')), 'items_count'],
      [fn('COALESCE', fn('SUM', col('is_checked')), 0), 'checked_count'],
    ],
    where: {
      shopping_list_id: {
        [Op.in]: ids,
      },
    },
    group: ['shopping_list_id'],
    raw: true,
  })

  const statsById = new Map(
    statsRows.map((row) => [
      row.shopping_list_id,
      {
        items_count: Number(row.items_count) || 0,
        checked_count: Number(row.checked_count) || 0,
      },
    ]),
  )

  return rows.map((row) => ({
    ...row,
    items_count: statsById.get(row.id)?.items_count ?? 0,
    checked_count: statsById.get(row.id)?.checked_count ?? 0,
  }))
}

async function getShoppingListById(shoppingListId, user) {
  const shoppingList = await getOwnedShoppingListById(shoppingListId, user.id)
  if (!shoppingList) {
    return null
  }

  return {
    ...shoppingList,
    items: await getShoppingListItems(shoppingListId),
  }
}

async function createShoppingList(payload, user) {
  const normalized = await validateShoppingListPayload(payload, user.id)

  const created = await models.shoppingList.create({
    owner_user_id: user.id,
    meal_plan_id: normalized.meal_plan_id,
    name: normalized.name,
    status: normalized.status,
    note: normalized.note,
  })

  return getShoppingListById(created.id, user)
}

async function updateShoppingList(shoppingListId, payload, user) {
  const existing = await getOwnedShoppingListById(shoppingListId, user.id)
  if (!existing) {
    return null
  }

  const normalized = await validateShoppingListPayload(
    {
      name: payload?.name ?? existing.name,
      status: payload?.status ?? existing.status,
      note: payload?.note ?? existing.note,
      meal_plan_id: payload?.meal_plan_id ?? existing.meal_plan_id,
    },
    user.id,
  )

  await models.shoppingList.update(
    {
      meal_plan_id: normalized.meal_plan_id,
      name: normalized.name,
      status: normalized.status,
      note: normalized.note,
      updated_at: new Date().toISOString(),
    },
    {
      where: {
        id: shoppingListId,
        owner_user_id: user.id,
      },
    },
  )

  return getShoppingListById(shoppingListId, user)
}

async function deleteShoppingList(shoppingListId, user) {
  const deleted = await models.shoppingList.destroy({
    where: {
      id: shoppingListId,
      owner_user_id: user.id,
    },
  })

  return deleted > 0
}

async function addShoppingListItem(shoppingListId, payload, user) {
  const shoppingList = await getOwnedShoppingListById(shoppingListId, user.id)
  if (!shoppingList) {
    return null
  }

  const item = normalizeItemPayload(payload)

  await sequelize.transaction(async (transaction) => {
    await models.shoppingListItem.create(
      {
        shopping_list_id: shoppingListId,
        product_id: item.product_id,
        custom_name: item.custom_name,
        quantity: item.quantity,
        unit_id: item.unit_id,
        is_checked: item.is_checked,
        note: item.note,
      },
      { transaction },
    )

    await models.shoppingList.update(
      { updated_at: new Date().toISOString() },
      {
        where: {
          id: shoppingListId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return getShoppingListById(shoppingListId, user)
}

async function updateShoppingListItem(shoppingListId, itemId, payload, user) {
  const existing = await getOwnedShoppingListItem(shoppingListId, itemId, user.id)
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

  await sequelize.transaction(async (transaction) => {
    await models.shoppingListItem.update(
      {
        product_id: item.product_id,
        custom_name: item.custom_name,
        quantity: item.quantity,
        unit_id: item.unit_id,
        is_checked: item.is_checked,
        note: item.note,
        updated_at: new Date().toISOString(),
      },
      {
        where: {
          id: itemId,
          shopping_list_id: shoppingListId,
        },
        transaction,
      },
    )

    await models.shoppingList.update(
      { updated_at: new Date().toISOString() },
      {
        where: {
          id: shoppingListId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return getShoppingListById(shoppingListId, user)
}

async function deleteShoppingListItem(shoppingListId, itemId, user) {
  const existing = await getOwnedShoppingListItem(shoppingListId, itemId, user.id)
  if (!existing) {
    return false
  }

  await sequelize.transaction(async (transaction) => {
    await models.shoppingListItem.destroy({
      where: {
        id: itemId,
        shopping_list_id: shoppingListId,
      },
      transaction,
    })

    await models.shoppingList.update(
      { updated_at: new Date().toISOString() },
      {
        where: {
          id: shoppingListId,
          owner_user_id: user.id,
        },
        transaction,
      },
    )
  })

  return true
}

async function generateShoppingListFromMealPlan(mealPlanId, payload, user) {
  const mealPlan = await getOwnedMealPlanForGeneration(mealPlanId, user.id)
  if (!mealPlan) {
    return null
  }

  const providedName = normalizeText(payload?.name)
  const shoppingListName = providedName || `Zakupy: ${mealPlan.name}`
  const generatedItems = await buildGeneratedItems(mealPlanId, mealPlan.portions_count ?? 1)

  const shoppingListId = await sequelize.transaction(async (transaction) => {
    const created = await models.shoppingList.create(
      {
        owner_user_id: user.id,
        meal_plan_id: mealPlan.id,
        name: shoppingListName,
        status: 'open',
        note: 'Wygenerowano z planu okresu',
      },
      { transaction },
    )

    if (generatedItems.length > 0) {
      await models.shoppingListItem.bulkCreate(
        generatedItems.map((item) => ({
          shopping_list_id: created.id,
          product_id: item.product_id,
          custom_name: item.custom_name,
          quantity: item.quantity,
          unit_id: item.unit_id,
          is_checked: item.is_checked,
          note: item.note,
        })),
        { transaction },
      )
    }

    return created.id
  })

  return getShoppingListById(shoppingListId, user)
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
  generateShoppingListFromMealPlan,
}
