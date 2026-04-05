import catalogDb from '../db/catalog.js'

function normalizeSearch(search) {
  const value = typeof search === 'string' ? search.trim() : ''
  return value.length > 0 ? `%${value}%` : null
}

function normalizeRecipeName(name) {
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

function recipeSelectSql() {
  return `
    SELECT
      r.id,
      r.name,
      r.normalized_name,
      r.source_file,
      r.owner_user_id,
      r.is_system,
      r.is_editable,
      owner.username AS owner_username,
      COUNT(ri.id) AS ingredients_count
    FROM recipes r
    LEFT JOIN users owner ON owner.id = r.owner_user_id
    LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
  `
}

function recipeAccessWhere(user) {
  if (!user) {
    return {
      sql: 'WHERE (r.is_system = 1 OR r.owner_user_id IS NULL)',
      params: [],
    }
  }

  if (user.permissions.has('recipes.manage')) {
    return { sql: '', params: [] }
  }

  return {
    sql: 'WHERE (r.is_system = 1 OR r.owner_user_id IS NULL OR r.owner_user_id = ?)',
    params: [user.id],
  }
}

async function getRecipes(search, user) {
  const searchValue = normalizeSearch(search)
  const access = recipeAccessWhere(user)

  const baseWhere = access.sql.length > 0 ? `${access.sql} AND` : 'WHERE'

  return catalogDb
    .prepare(
      `
      ${recipeSelectSql()}
      ${baseWhere} (? IS NULL OR r.name LIKE ? OR r.normalized_name LIKE ?)
      GROUP BY r.id
      ORDER BY r.name COLLATE NOCASE ASC
      `,
    )
    .all(...access.params, searchValue, searchValue, searchValue)
}

async function getRecipeById(id, user) {
  const access = recipeAccessWhere(user)
  const baseWhere = access.sql.length > 0 ? `${access.sql} AND` : 'WHERE'

  return catalogDb
    .prepare(
      `
      ${recipeSelectSql()}
      ${baseWhere} r.id = ?
      GROUP BY r.id
      `,
    )
    .get(...access.params, id)
}

async function getRecipeIngredients(recipeId, user) {
  const recipe = await getRecipeById(recipeId, user)
  if (!recipe) {
    return null
  }

  const ingredients = catalogDb
    .prepare(
      `
      SELECT
        ri.id,
        ri.recipe_id,
        p.id AS product_id,
        p.name AS product_name,
        ri.quantity,
        u.name AS unit_name,
        ri.grams,
        ri.note
      FROM recipe_ingredients ri
      INNER JOIN products p ON p.id = ri.product_id
      LEFT JOIN units u ON u.id = ri.unit_id
      WHERE ri.recipe_id = ?
      ORDER BY p.name COLLATE NOCASE ASC
      `,
    )
    .all(recipeId)

  return {
    recipe,
    ingredients,
  }
}

function resolveUnitId(unitName) {
  if (!unitName) {
    return null
  }

  const unit = catalogDb.prepare('SELECT id FROM units WHERE name = ?').get(unitName)
  if (unit) {
    return unit.id
  }

  const insertResult = catalogDb.prepare('INSERT INTO units(name) VALUES (?)').run(unitName)
  return Number(insertResult.lastInsertRowid)
}

function resolveProductId(productId, productName) {
  if (productId) {
    return Number(productId)
  }

  if (!productName) {
    throw new Error('Each ingredient requires product_id or product_name')
  }

  const normalizedName = normalizeRecipeName(productName)
  const existing = catalogDb
    .prepare('SELECT id FROM products WHERE normalized_name = ?')
    .get(normalizedName)

  if (existing) {
    return existing.id
  }

  const created = catalogDb
    .prepare(
      `
      INSERT INTO products(name, normalized_name)
      VALUES (?, ?)
      `,
    )
    .run(productName, normalizedName)

  return Number(created.lastInsertRowid)
}

async function createRecipe(payload, user) {
  const recipeName = typeof payload?.name === 'string' ? payload.name.trim() : ''
  if (!recipeName) {
    throw new Error('Recipe name is required')
  }

  const recipeIngredients = Array.isArray(payload?.ingredients) ? payload.ingredients : []

  const result = catalogDb.transaction(() => {
    const normalizedName = normalizeRecipeName(recipeName)

    const created = catalogDb
      .prepare(
        `
        INSERT INTO recipes(name, normalized_name, source_file, owner_user_id, is_system, is_editable)
        VALUES (?, ?, ?, ?, 0, 1)
        `,
      )
      .run(recipeName, normalizedName, payload?.source_file ?? null, user.id)

    const recipeId = Number(created.lastInsertRowid)

    for (const ingredient of recipeIngredients) {
      const productId = resolveProductId(ingredient.product_id, ingredient.product_name)
      const unitId = resolveUnitId(ingredient.unit_name)

      catalogDb
        .prepare(
          `
          INSERT INTO recipe_ingredients(recipe_id, product_id, quantity, unit_id, grams, note)
          VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(
          recipeId,
          productId,
          ingredient.quantity ?? null,
          unitId,
          ingredient.grams ?? null,
          ingredient.note ?? '',
        )
    }

    return recipeId
  })()

  return getRecipeById(result, user)
}

async function updateRecipe(recipeId, payload, user) {
  const existing = catalogDb
    .prepare('SELECT id, is_system, is_editable FROM recipes WHERE id = ?')
    .get(recipeId)

  if (!existing) {
    return null
  }

  if (existing.is_system || !existing.is_editable) {
    throw new Error('This recipe is read-only')
  }

  const recipeName = typeof payload?.name === 'string' ? payload.name.trim() : ''
  if (!recipeName) {
    throw new Error('Recipe name is required')
  }

  const recipeIngredients = Array.isArray(payload?.ingredients) ? payload.ingredients : []

  catalogDb.transaction(() => {
    const normalizedName = normalizeRecipeName(recipeName)

    catalogDb
      .prepare(
        `
        UPDATE recipes
        SET name = ?, normalized_name = ?, source_file = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        `,
      )
      .run(recipeName, normalizedName, payload?.source_file ?? null, recipeId)

    catalogDb.prepare('DELETE FROM recipe_ingredients WHERE recipe_id = ?').run(recipeId)

    for (const ingredient of recipeIngredients) {
      const productId = resolveProductId(ingredient.product_id, ingredient.product_name)
      const unitId = resolveUnitId(ingredient.unit_name)

      catalogDb
        .prepare(
          `
          INSERT INTO recipe_ingredients(recipe_id, product_id, quantity, unit_id, grams, note)
          VALUES (?, ?, ?, ?, ?, ?)
          `,
        )
        .run(
          recipeId,
          productId,
          ingredient.quantity ?? null,
          unitId,
          ingredient.grams ?? null,
          ingredient.note ?? '',
        )
    }
  })()

  return getRecipeById(recipeId, user)
}

async function deleteRecipe(recipeId) {
  const existing = catalogDb
    .prepare('SELECT id, is_system, is_editable FROM recipes WHERE id = ?')
    .get(recipeId)

  if (!existing) {
    return null
  }

  if (existing.is_system || !existing.is_editable) {
    throw new Error('This recipe is read-only')
  }

  catalogDb.prepare('DELETE FROM recipes WHERE id = ?').run(recipeId)
  return true
}

export default {
  getRecipes,
  getRecipeById,
  getRecipeIngredients,
  createRecipe,
  updateRecipe,
  deleteRecipe,
}
