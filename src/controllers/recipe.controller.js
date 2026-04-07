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

function parseNullableNumber(value) {
  if (value === '' || value === null || value === undefined) {
    return null
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const MASS_ALIAS_FACTORS = new Map([
  ['mg', { symbol: 'mg', gramsFactor: 0.001 }],
  ['g', { symbol: 'g', gramsFactor: 1 }],
  ['gram', { symbol: 'g', gramsFactor: 1 }],
  ['gramy', { symbol: 'g', gramsFactor: 1 }],
  ['dag', { symbol: 'dag', gramsFactor: 10 }],
  ['kg', { symbol: 'kg', gramsFactor: 1000 }],
  ['kilogram', { symbol: 'kg', gramsFactor: 1000 }],
  ['kilogramy', { symbol: 'kg', gramsFactor: 1000 }],
])

const VOLUME_ALIAS_FACTORS = new Map([
  ['ml', { symbol: 'ml', mlFactor: 1 }],
  ['mililitr', { symbol: 'ml', mlFactor: 1 }],
  ['mililitry', { symbol: 'ml', mlFactor: 1 }],
  ['l', { symbol: 'l', mlFactor: 1000 }],
  ['litr', { symbol: 'l', mlFactor: 1000 }],
  ['litry', { symbol: 'l', mlFactor: 1000 }],
])

function normalizeUnitAlias(value) {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function inferPhysicalUnitSpec(unitName) {
  const normalized = normalizeUnitAlias(unitName)

  if (MASS_ALIAS_FACTORS.has(normalized)) {
    const mass = MASS_ALIAS_FACTORS.get(normalized)
    return {
      unit_type: 'mass',
      symbol: mass.symbol,
      to_grams_factor: mass.gramsFactor,
      to_ml_factor: null,
    }
  }

  if (VOLUME_ALIAS_FACTORS.has(normalized)) {
    const volume = VOLUME_ALIAS_FACTORS.get(normalized)
    return {
      unit_type: 'volume',
      symbol: volume.symbol,
      to_grams_factor: null,
      to_ml_factor: volume.mlFactor,
    }
  }

  return null
}

function recipeSelectSql() {
  return `
    SELECT
      r.id,
      r.name,
      r.normalized_name,
      r.source_file,
      r.instructions,
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

function resolveUnit(unitName) {
  if (!unitName) {
    return null
  }

  const trimmed = String(unitName).trim()
  if (!trimmed) {
    return null
  }

  const existing = catalogDb
    .prepare('SELECT id, name, unit_type, to_grams_factor FROM units WHERE lower(name) = lower(?)')
    .get(trimmed)

  if (existing && (existing.unit_type === 'mass' || existing.unit_type === 'volume')) {
    return existing
  }

  const inferred = inferPhysicalUnitSpec(trimmed)
  if (!inferred) {
    return null
  }

  const inserted = catalogDb
    .prepare(
      `
      INSERT INTO units(name, symbol, unit_type, to_grams_factor, to_ml_factor)
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(
      trimmed,
      inferred.symbol,
      inferred.unit_type,
      inferred.to_grams_factor,
      inferred.to_ml_factor,
    )

  return {
    id: Number(inserted.lastInsertRowid),
    name: trimmed,
    unit_type: inferred.unit_type,
    to_grams_factor: inferred.to_grams_factor,
  }
}

function resolvePackageTypeId(packageTypeName) {
  if (!packageTypeName) {
    return null
  }

  const name = String(packageTypeName).trim()
  if (!name) {
    return null
  }

  const normalizedName = normalizeRecipeName(name)
  const existing = catalogDb
    .prepare('SELECT id FROM package_types WHERE normalized_name = ?')
    .get(normalizedName)

  if (existing) {
    return existing.id
  }

  const inserted = catalogDb
    .prepare('INSERT INTO package_types(name, normalized_name) VALUES (?, ?)')
    .run(name, normalizedName)

  return Number(inserted.lastInsertRowid)
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

function deriveGramsPerPackage(quantity, grams) {
  const quantityNumber = parseNullableNumber(quantity)
  const gramsNumber = parseNullableNumber(grams)

  if (gramsNumber === null) {
    return null
  }

  if (quantityNumber !== null && quantityNumber > 0) {
    return Number((gramsNumber / quantityNumber).toFixed(2))
  }

  return Number(gramsNumber.toFixed(2))
}

function resolveIngredientPackageConversion(ingredient, productId, unitMeta) {
  const conversionId = parseNullableNumber(ingredient?.ingredient_package_conversion_id)
  if (conversionId !== null) {
    const existingById = catalogDb
      .prepare('SELECT id FROM ingredient_package_conversions WHERE id = ? AND product_id = ?')
      .get(conversionId, productId)

    if (existingById) {
      return existingById.id
    }
  }

  const explicitName =
    typeof ingredient?.package_type_name === 'string' ? ingredient.package_type_name.trim() : ''

  const inferredName =
    explicitName ||
    (typeof ingredient?.unit_name === 'string' &&
    ingredient.unit_name.trim().length > 0 &&
    !unitMeta
      ? ingredient.unit_name.trim()
      : '')

  if (!inferredName) {
    return null
  }

  const packageTypeId = resolvePackageTypeId(inferredName)
  if (!packageTypeId) {
    return null
  }

  const gramsPerPackage = deriveGramsPerPackage(ingredient?.quantity, ingredient?.grams)

  const existing = catalogDb
    .prepare(
      `
      SELECT id, grams_per_package, samples_count
      FROM ingredient_package_conversions
      WHERE product_id = ? AND package_type_id = ?
      `,
    )
    .get(productId, packageTypeId)

  if (existing) {
    if (
      gramsPerPackage !== null &&
      Math.abs(existing.grams_per_package - gramsPerPackage) > 0.001
    ) {
      const nextSamples = Number(existing.samples_count) + 1
      const nextAverage = Number(
        (
          (existing.grams_per_package * existing.samples_count + gramsPerPackage) /
          nextSamples
        ).toFixed(2),
      )

      catalogDb
        .prepare(
          `
          UPDATE ingredient_package_conversions
          SET
            grams_per_package = ?,
            samples_count = ?,
            source = ?,
            updated_at = CURRENT_TIMESTAMP
          WHERE id = ?
          `,
        )
        .run(nextAverage, nextSamples, 'recipe-derived:auto-avg', existing.id)
    }

    return existing.id
  }

  if (gramsPerPackage === null) {
    return null
  }

  const inserted = catalogDb
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
    .run(productId, packageTypeId, gramsPerPackage, 'recipe-derived:first-sample', 1)

  return Number(inserted.lastInsertRowid)
}

function effectiveGramsSql() {
  return `
    COALESCE(
      ri.grams,
      CASE
        WHEN ri.quantity IS NOT NULL AND ipc.grams_per_package IS NOT NULL
          THEN ri.quantity * ipc.grams_per_package
        ELSE NULL
      END,
      CASE
        WHEN ri.quantity IS NOT NULL AND ri.package_id IS NOT NULL AND pkg.grams IS NOT NULL
          THEN ri.quantity * pkg.grams
        ELSE NULL
      END,
      CASE
        WHEN ri.quantity IS NOT NULL AND u.to_grams_factor IS NOT NULL
          THEN ri.quantity * u.to_grams_factor
        ELSE NULL
      END,
      CASE
        WHEN ri.quantity IS NOT NULL
             AND u.to_ml_factor IS NOT NULL
             AND p.unit_to_ml IS NOT NULL
             AND p.unit_to_ml > 0
             AND du.to_grams_factor IS NOT NULL
          THEN ri.quantity * u.to_ml_factor * du.to_grams_factor / p.unit_to_ml
        ELSE NULL
      END
    )
  `
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

async function getRecipeNutritionSummaries(user) {
  const access = recipeAccessWhere(user)
  const whereClause = access.sql.length > 0 ? access.sql : ''

  return catalogDb
    .prepare(
      `
      SELECT
        r.id AS recipe_id,
        r.name AS recipe_name,
        COALESCE(n.total_grams, 0) AS total_grams,
        COALESCE(n.calories, 0) AS calories,
        COALESCE(n.carbohydrates, 0) AS carbohydrates,
        COALESCE(n.sugars, 0) AS sugars,
        COALESCE(n.fat, 0) AS fat,
        COALESCE(n.protein, 0) AS protein,
        COALESCE(n.fiber, 0) AS fiber
      FROM recipes r
      LEFT JOIN recipe_nutrition_summary n ON n.recipe_id = r.id
      ${whereClause}
      ORDER BY r.name COLLATE NOCASE ASC
      `,
    )
    .all(...access.params)
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
        COALESCE(u.name, pt.name) AS unit_name,
        ri.ingredient_package_conversion_id,
        pt.name AS package_type_name,
        ipc.grams_per_package,
        ri.grams,
        ROUND(${effectiveGramsSql()}, 2) AS effective_grams,
        ri.note
      FROM recipe_ingredients ri
      INNER JOIN products p ON p.id = ri.product_id
      LEFT JOIN units u ON u.id = ri.unit_id
      LEFT JOIN units du ON du.id = p.default_unit_id
      LEFT JOIN ingredient_package_conversions ipc ON ipc.id = ri.ingredient_package_conversion_id
      LEFT JOIN package_types pt ON pt.id = ipc.package_type_id
      LEFT JOIN packages pkg ON pkg.id = ri.package_id
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

async function createRecipe(payload, user) {
  const recipeName = typeof payload?.name === 'string' ? payload.name.trim() : ''
  if (!recipeName) {
    throw new Error('Recipe name is required')
  }

  const recipeIngredients = Array.isArray(payload?.ingredients) ? payload.ingredients : []

  const recipeId = catalogDb.transaction(() => {
    const normalizedName = normalizeRecipeName(recipeName)

    const created = catalogDb
      .prepare(
        `
        INSERT INTO recipes(name, normalized_name, source_file, owner_user_id, is_system, is_editable)
        VALUES (?, ?, ?, ?, 0, 1)
        `,
      )
      .run(recipeName, normalizedName, payload?.source_file ?? null, user.id)

    const newRecipeId = Number(created.lastInsertRowid)

    for (const ingredient of recipeIngredients) {
      const productId = resolveProductId(ingredient.product_id, ingredient.product_name)
      const unitMeta = resolveUnit(ingredient.unit_name)
      const conversionId = resolveIngredientPackageConversion(ingredient, productId, unitMeta)

      catalogDb
        .prepare(
          `
          INSERT INTO recipe_ingredients(
            recipe_id,
            product_id,
            quantity,
            unit_id,
            grams,
            ingredient_package_conversion_id,
            note
          )
          VALUES (?, ?, ?, ?, ?, ?, ?)
          `,
        )
        .run(
          newRecipeId,
          productId,
          parseNullableNumber(ingredient.quantity),
          unitMeta?.id ?? null,
          parseNullableNumber(ingredient.grams),
          conversionId,
          ingredient.note ?? '',
        )
    }

    return newRecipeId
  })()

  return getRecipeById(recipeId, user)
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
      const unitMeta = resolveUnit(ingredient.unit_name)
      const conversionId = resolveIngredientPackageConversion(ingredient, productId, unitMeta)

      catalogDb
        .prepare(
          `
          INSERT INTO recipe_ingredients(
            recipe_id,
            product_id,
            quantity,
            unit_id,
            grams,
            ingredient_package_conversion_id,
            note
          )
          VALUES (?, ?, ?, ?, ?, ?, ?)
          `,
        )
        .run(
          recipeId,
          productId,
          parseNullableNumber(ingredient.quantity),
          unitMeta?.id ?? null,
          parseNullableNumber(ingredient.grams),
          conversionId,
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

async function getRecipeNutrition(recipeId, user) {
  const recipe = await getRecipeById(recipeId, user)
  if (!recipe) {
    return null
  }

  const summary =
    catalogDb.prepare('SELECT * FROM recipe_nutrition_summary WHERE recipe_id = ?').get(recipeId) ??
    null

  const items = catalogDb
    .prepare(
      `
      SELECT
        ri.id,
        p.id AS product_id,
        p.name AS product_name,
        ri.quantity,
        COALESCE(u.name, pt.name) AS unit_name,
        ri.ingredient_package_conversion_id,
        pt.name AS package_type_name,
        ipc.grams_per_package,
        ri.grams,
        ROUND(${effectiveGramsSql()}, 2) AS effective_grams,
        p.calories_per_100g,
        p.carbohydrates_per_100g,
        p.sugars_per_100g,
        p.fat_per_100g,
        p.protein_per_100g,
        p.fiber_per_100g,
        ROUND(COALESCE(${effectiveGramsSql()}, 0) * COALESCE(p.calories_per_100g, 0) / 100.0, 2) AS calories,
        ROUND(COALESCE(${effectiveGramsSql()}, 0) * COALESCE(p.carbohydrates_per_100g, 0) / 100.0, 2) AS carbohydrates,
        ROUND(COALESCE(${effectiveGramsSql()}, 0) * COALESCE(p.sugars_per_100g, 0) / 100.0, 2) AS sugars,
        ROUND(COALESCE(${effectiveGramsSql()}, 0) * COALESCE(p.fat_per_100g, 0) / 100.0, 2) AS fat,
        ROUND(COALESCE(${effectiveGramsSql()}, 0) * COALESCE(p.protein_per_100g, 0) / 100.0, 2) AS protein,
        ROUND(COALESCE(${effectiveGramsSql()}, 0) * COALESCE(p.fiber_per_100g, 0) / 100.0, 2) AS fiber
      FROM recipe_ingredients ri
      INNER JOIN products p ON p.id = ri.product_id
      LEFT JOIN units u ON u.id = ri.unit_id
      LEFT JOIN units du ON du.id = p.default_unit_id
      LEFT JOIN ingredient_package_conversions ipc ON ipc.id = ri.ingredient_package_conversion_id
      LEFT JOIN package_types pt ON pt.id = ipc.package_type_id
      LEFT JOIN packages pkg ON pkg.id = ri.package_id
      WHERE ri.recipe_id = ?
      ORDER BY p.name COLLATE NOCASE ASC
      `,
    )
    .all(recipeId)

  return {
    recipe,
    summary,
    items,
  }
}

export default {
  getRecipes,
  getRecipeNutritionSummaries,
  getRecipeById,
  getRecipeIngredients,
  getRecipeNutrition,
  createRecipe,
  updateRecipe,
  deleteRecipe,
}
