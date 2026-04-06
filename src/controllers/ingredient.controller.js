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

function parsePositiveNumber(value) {
  const parsed = parseNullableNumber(value)
  if (parsed === null || parsed <= 0) {
    return null
  }

  return parsed
}

function normalizeTagIds(value) {
  if (!Array.isArray(value)) {
    return []
  }

  const ids = value.map((item) => Number(item)).filter((item) => Number.isInteger(item) && item > 0)
  return Array.from(new Set(ids)).sort((left, right) => left - right)
}

function calculatePer100ml(valuePer100g, row) {
  const nutrient = parseNullableNumber(valuePer100g)
  const unitToMl = parsePositiveNumber(row?.unit_to_ml)
  const gramsPerUnit = parsePositiveNumber(row?.unit_to_grams_factor)

  if (nutrient === null || unitToMl === null || gramsPerUnit === null) {
    return null
  }

  return Number(((nutrient * gramsPerUnit) / unitToMl).toFixed(2))
}

function mapIngredientRow(row) {
  const mapped = {
    id: row.id,
    name: row.name,
    comment: row.comment ?? '',
    unit_id: row.unit_id,
    unit_to_ml: row.unit_to_ml,
    package_type_id: row.package_type_id,
    package_type_name: row.package_type_name ?? null,
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

  return {
    ...mapped,
    calories_per_100ml: calculatePer100ml(mapped.calories_per_100g, row),
    carbohydrates_per_100ml: calculatePer100ml(mapped.carbohydrates_per_100g, row),
    sugars_per_100ml: calculatePer100ml(mapped.sugars_per_100g, row),
    fat_per_100ml: calculatePer100ml(mapped.fat_per_100g, row),
    protein_per_100ml: calculatePer100ml(mapped.protein_per_100g, row),
    fiber_per_100ml: calculatePer100ml(mapped.fiber_per_100g, row),
  }
}

function getUnitMeta(unitId) {
  if (!Number.isInteger(unitId) || unitId <= 0) {
    return null
  }

  return catalogDb
    .prepare(
      `
      SELECT id, name, unit_type, to_grams_factor, to_ml_factor
      FROM units
      WHERE id = ?
      `,
    )
    .get(unitId)
}

function normalizeUnitToMl(value, unitMeta) {
  const explicit = parsePositiveNumber(value)
  if (explicit !== null) {
    return explicit
  }

  const fromUnit = parsePositiveNumber(unitMeta?.to_ml_factor)
  return fromUnit !== null ? fromUnit : null
}

function upsertDefaultPackageConversion(productId, payload) {
  const packageTypeId = Number(payload?.packageTypeId)
  const quantityPerPackage = parsePositiveNumber(payload?.quantityPerPackage)
  const unitMeta = payload?.unitMeta ?? null

  if (!Number.isInteger(packageTypeId) || packageTypeId <= 0 || quantityPerPackage === null) {
    return
  }

  const gramsPerUnit = parsePositiveNumber(unitMeta?.to_grams_factor)
  if (gramsPerUnit === null) {
    return
  }

  const gramsPerPackage = Number((quantityPerPackage * gramsPerUnit).toFixed(2))

  const existing = catalogDb
    .prepare(
      `
      SELECT id
      FROM ingredient_package_conversions
      WHERE product_id = ? AND package_type_id = ?
      `,
    )
    .get(productId, packageTypeId)

  if (existing) {
    catalogDb
      .prepare(
        `
        UPDATE ingredient_package_conversions
        SET
          grams_per_package = ?,
          source = ?,
          samples_count = CASE WHEN samples_count < 1 THEN 1 ELSE samples_count END,
          updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        `,
      )
      .run(gramsPerPackage, 'ingredient-default-package', existing.id)
    return
  }

  catalogDb
    .prepare(
      `
      INSERT INTO ingredient_package_conversions(
        product_id,
        package_type_id,
        grams_per_package,
        source,
        samples_count
      )
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(productId, packageTypeId, gramsPerPackage, 'ingredient-default-package', 1)
}

function replaceProductTags(productId, tagIds) {
  catalogDb.prepare('DELETE FROM product_tags WHERE product_id = ?').run(productId)

  const insertTag = catalogDb.prepare('INSERT INTO product_tags(product_id, tag_id) VALUES (?, ?)')
  for (const tagId of tagIds) {
    insertTag.run(productId, tagId)
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
        p.unit_to_ml,
        p.default_package_type_id AS package_type_id,
        dpt.name AS package_type_name,
        p.quantity_per_package,
        p.calories_per_100g,
        p.carbohydrates_per_100g,
        p.sugars_per_100g,
        p.fat_per_100g,
        p.protein_per_100g,
        p.fiber_per_100g,
        u.to_grams_factor AS unit_to_grams_factor,
        GROUP_CONCAT(pt.tag_id) AS tag_ids
      FROM products p
      LEFT JOIN units u ON u.id = p.default_unit_id
      LEFT JOIN package_types dpt ON dpt.id = p.default_package_type_id
      LEFT JOIN product_tags pt ON pt.product_id = p.id
      WHERE p.id = ?
      GROUP BY p.id
      `,
    )
    .get(productId)

  return row ? mapIngredientRow(row) : null
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
        p.unit_to_ml,
        p.default_package_type_id AS package_type_id,
        dpt.name AS package_type_name,
        p.quantity_per_package,
        p.calories_per_100g,
        p.carbohydrates_per_100g,
        p.sugars_per_100g,
        p.fat_per_100g,
        p.protein_per_100g,
        p.fiber_per_100g,
        u.to_grams_factor AS unit_to_grams_factor,
        GROUP_CONCAT(pt.tag_id) AS tag_ids
      FROM products p
      LEFT JOIN units u ON u.id = p.default_unit_id
      LEFT JOIN package_types dpt ON dpt.id = p.default_package_type_id
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

  const unitMeta = getUnitMeta(unitId)
  if (!unitMeta) {
    throw new Error('Unit is invalid')
  }

  const payload = {
    packageTypeId: parseNullableNumber(item?.package_type_id),
    quantityPerPackage: parseNullableNumber(item?.quantity_per_package),
    unitToMl: normalizeUnitToMl(item?.unit_to_ml, unitMeta),
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
            default_package_type_id = ?,
            quantity_per_package = ?,
            unit_to_ml = ?,
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
          payload.packageTypeId,
          payload.quantityPerPackage,
          payload.unitToMl,
          payload.calories,
          payload.carbohydrates,
          payload.sugars,
          payload.fat,
          payload.protein,
          payload.fiber,
          existing.id,
        )

      replaceProductTags(existing.id, tagIds)
      upsertDefaultPackageConversion(existing.id, {
        packageTypeId: payload.packageTypeId,
        quantityPerPackage: payload.quantityPerPackage,
        unitMeta,
      })
      return existing.id
    }

    const created = catalogDb
      .prepare(
        `
        INSERT INTO products(
          name,
          normalized_name,
          default_unit_id,
          default_package_type_id,
          comment,
          quantity_per_package,
          unit_to_ml,
          calories_per_100g,
          carbohydrates_per_100g,
          sugars_per_100g,
          fat_per_100g,
          protein_per_100g,
          fiber_per_100g
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `,
      )
      .run(
        name,
        normalizedName,
        unitId,
        payload.packageTypeId,
        comment,
        payload.quantityPerPackage,
        payload.unitToMl,
        payload.calories,
        payload.carbohydrates,
        payload.sugars,
        payload.fat,
        payload.protein,
        payload.fiber,
      )

    const newProductId = Number(created.lastInsertRowid)
    replaceProductTags(newProductId, tagIds)
    upsertDefaultPackageConversion(newProductId, {
      packageTypeId: payload.packageTypeId,
      quantityPerPackage: payload.quantityPerPackage,
      unitMeta,
    })
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

  const unitMeta = getUnitMeta(unitId)
  if (!unitMeta) {
    throw new Error('Unit is invalid')
  }

  const payload = {
    packageTypeId: parseNullableNumber(item?.package_type_id),
    quantityPerPackage: parseNullableNumber(item?.quantity_per_package),
    unitToMl: normalizeUnitToMl(item?.unit_to_ml, unitMeta),
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
          default_package_type_id = ?,
          comment = ?,
          quantity_per_package = ?,
          unit_to_ml = ?,
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
        payload.packageTypeId,
        comment,
        payload.quantityPerPackage,
        payload.unitToMl,
        payload.calories,
        payload.carbohydrates,
        payload.sugars,
        payload.fat,
        payload.protein,
        payload.fiber,
        productId,
      ).changes

    replaceProductTags(productId, tagIds)
    upsertDefaultPackageConversion(productId, {
      packageTypeId: payload.packageTypeId,
      quantityPerPackage: payload.quantityPerPackage,
      unitMeta,
    })

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
    catalogDb
      .prepare('DELETE FROM ingredient_package_conversions WHERE product_id = ? AND source = ?')
      .run(productId, 'ingredient-default-package')
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
