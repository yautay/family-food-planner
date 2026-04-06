import catalogDb from '../db/catalog.js'

function normalizeName(name) {
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

function parseNullableNumber(value) {
  if (value === '' || value === null || value === undefined) {
    return null
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeTagIds(value) {
  if (!Array.isArray(value)) {
    return []
  }

  const ids = value.map((item) => Number(item)).filter((item) => Number.isInteger(item) && item > 0)

  return Array.from(new Set(ids)).sort((left, right) => left - right)
}

function mapIngredientRow(row) {
  return {
    id: row.id,
    name: row.name,
    comment: row.comment ?? '',
    unit_id: row.unit_id,
    quantity_per_package: row.quantity_per_package,
    calories_per_100g: row.calories_per_100g,
    carbohydrates_per_100g: row.carbohydrates_per_100g,
    sugars_per_100g: row.sugars_per_100g,
    fat_per_100g: row.fat_per_100g,
    protein_per_100g: row.protein_per_100g,
    fiber_per_100g: row.fiber_per_100g,
    tag_id: row.tag_ids
      ? row.tag_ids
          .split(',')
          .map((item) => Number(item))
          .filter((item) => Number.isInteger(item) && item > 0)
      : [],
  }
}

function getIngredientById(productId) {
  const row = catalogDb
    .prepare(
      `
      SELECT
        p.id,
        p.name,
        p.comment,
        p.default_unit_id AS unit_id,
        p.quantity_per_package,
        p.calories_per_100g,
        p.carbohydrates_per_100g,
        p.sugars_per_100g,
        p.fat_per_100g,
        p.protein_per_100g,
        p.fiber_per_100g,
        GROUP_CONCAT(pt.tag_id) AS tag_ids
      FROM products p
      LEFT JOIN product_tags pt ON pt.product_id = p.id
      WHERE p.id = ?
      GROUP BY p.id
      `,
    )
    .get(productId)

  return row ? mapIngredientRow(row) : null
}

function replaceProductTags(productId, tagIds) {
  catalogDb.prepare('DELETE FROM product_tags WHERE product_id = ?').run(productId)

  const insertTag = catalogDb.prepare('INSERT INTO product_tags(product_id, tag_id) VALUES (?, ?)')
  for (const tagId of tagIds) {
    insertTag.run(productId, tagId)
  }
}

async function getIngredients() {
  const rows = catalogDb
    .prepare(
      `
      SELECT
        p.id,
        p.name,
        p.comment,
        p.default_unit_id AS unit_id,
        p.quantity_per_package,
        p.calories_per_100g,
        p.carbohydrates_per_100g,
        p.sugars_per_100g,
        p.fat_per_100g,
        p.protein_per_100g,
        p.fiber_per_100g,
        GROUP_CONCAT(pt.tag_id) AS tag_ids
      FROM products p
      LEFT JOIN product_tags pt ON pt.product_id = p.id
      GROUP BY p.id
      ORDER BY p.name COLLATE NOCASE ASC
      `,
    )
    .all()

  return rows.map(mapIngredientRow)
}

async function addIngredient(item) {
  const name = typeof item?.name === 'string' ? item.name.trim() : ''
  if (!name) {
    throw new Error('Ingredient name is required')
  }

  const normalizedName = normalizeName(name)
  const comment = typeof item?.comment === 'string' ? item.comment.trim() : ''
  const unitId = parseNullableNumber(item?.unit_id)
  if (!Number.isInteger(unitId) || unitId <= 0) {
    throw new Error('Unit is required')
  }

  const payload = {
    quantityPerPackage: parseNullableNumber(item?.quantity_per_package),
    calories: parseNullableNumber(item?.calories_per_100g),
    carbohydrates: parseNullableNumber(item?.carbohydrates_per_100g),
    sugars: parseNullableNumber(item?.sugars_per_100g),
    fat: parseNullableNumber(item?.fat_per_100g),
    protein: parseNullableNumber(item?.protein_per_100g),
    fiber: parseNullableNumber(item?.fiber_per_100g),
  }

  const tagIds = normalizeTagIds(item?.tag_id)

  const productId = catalogDb.transaction(() => {
    const existing = catalogDb
      .prepare('SELECT id FROM products WHERE normalized_name = ?')
      .get(normalizedName)

    if (existing) {
      catalogDb
        .prepare(
          `
          UPDATE products
          SET
            name = ?,
            comment = ?,
            default_unit_id = ?,
            quantity_per_package = ?,
            calories_per_100g = ?,
            carbohydrates_per_100g = ?,
            sugars_per_100g = ?,
            fat_per_100g = ?,
            protein_per_100g = ?,
            fiber_per_100g = ?,
            updated_at = CURRENT_TIMESTAMP
          WHERE id = ?
          `,
        )
        .run(
          name,
          comment,
          unitId,
          payload.quantityPerPackage,
          payload.calories,
          payload.carbohydrates,
          payload.sugars,
          payload.fat,
          payload.protein,
          payload.fiber,
          existing.id,
        )

      replaceProductTags(existing.id, tagIds)
      return existing.id
    }

    const created = catalogDb
      .prepare(
        `
        INSERT INTO products(
          name,
          normalized_name,
          default_unit_id,
          comment,
          quantity_per_package,
          calories_per_100g,
          carbohydrates_per_100g,
          sugars_per_100g,
          fat_per_100g,
          protein_per_100g,
          fiber_per_100g
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `,
      )
      .run(
        name,
        normalizedName,
        unitId,
        comment,
        payload.quantityPerPackage,
        payload.calories,
        payload.carbohydrates,
        payload.sugars,
        payload.fat,
        payload.protein,
        payload.fiber,
      )

    const newProductId = Number(created.lastInsertRowid)
    replaceProductTags(newProductId, tagIds)
    return newProductId
  })()

  return getIngredientById(productId)
}

async function updateIngredient(item) {
  const productId = Number(item?.id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient id is invalid')
  }

  const existing = catalogDb.prepare('SELECT id FROM products WHERE id = ?').get(productId)
  if (!existing) {
    return 0
  }

  const name = typeof item?.name === 'string' ? item.name.trim() : ''
  if (!name) {
    throw new Error('Ingredient name is required')
  }

  const normalizedName = normalizeName(name)
  const comment = typeof item?.comment === 'string' ? item.comment.trim() : ''
  const unitId = parseNullableNumber(item?.unit_id)
  if (!Number.isInteger(unitId) || unitId <= 0) {
    throw new Error('Unit is required')
  }

  const payload = {
    quantityPerPackage: parseNullableNumber(item?.quantity_per_package),
    calories: parseNullableNumber(item?.calories_per_100g),
    carbohydrates: parseNullableNumber(item?.carbohydrates_per_100g),
    sugars: parseNullableNumber(item?.sugars_per_100g),
    fat: parseNullableNumber(item?.fat_per_100g),
    protein: parseNullableNumber(item?.protein_per_100g),
    fiber: parseNullableNumber(item?.fiber_per_100g),
  }

  const tagIds = normalizeTagIds(item?.tag_id)

  return catalogDb.transaction(() => {
    const nameCollision = catalogDb
      .prepare('SELECT id FROM products WHERE normalized_name = ? AND id <> ?')
      .get(normalizedName, productId)

    if (nameCollision) {
      throw new Error('Ingredient with this name already exists')
    }

    const changes = catalogDb
      .prepare(
        `
        UPDATE products
        SET
          name = ?,
          normalized_name = ?,
          default_unit_id = ?,
          comment = ?,
          quantity_per_package = ?,
          calories_per_100g = ?,
          carbohydrates_per_100g = ?,
          sugars_per_100g = ?,
          fat_per_100g = ?,
          protein_per_100g = ?,
          fiber_per_100g = ?,
          updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        `,
      )
      .run(
        name,
        normalizedName,
        unitId,
        comment,
        payload.quantityPerPackage,
        payload.calories,
        payload.carbohydrates,
        payload.sugars,
        payload.fat,
        payload.protein,
        payload.fiber,
        productId,
      ).changes

    replaceProductTags(productId, tagIds)
    return changes
  })()
}

async function deleteIngredient(id) {
  const productId = Number(id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient id is invalid')
  }

  const usage = catalogDb
    .prepare('SELECT COUNT(*) AS count FROM recipe_ingredients WHERE product_id = ?')
    .get(productId)

  if ((usage?.count ?? 0) > 0) {
    throw new Error('Ingredient is used in recipes and cannot be deleted')
  }

  return catalogDb.transaction(() => {
    catalogDb.prepare('DELETE FROM product_tags WHERE product_id = ?').run(productId)
    catalogDb.prepare('DELETE FROM product_packages WHERE product_id = ?').run(productId)
    return catalogDb.prepare('DELETE FROM products WHERE id = ?').run(productId).changes
  })()
}

export default {
  getIngredients,
  addIngredient,
  updateIngredient,
  deleteIngredient,
}
