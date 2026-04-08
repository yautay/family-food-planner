import { Op, fn, col, where, literal } from 'sequelize'
import sequelize from '../db/client.js'
import models from '../models/index.js'

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

function round2(value) {
  if (!Number.isFinite(value)) {
    return 0
  }

  return Number(value.toFixed(2))
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

function hasPermission(user, permissionName) {
  if (!user?.permissions) {
    return false
  }

  if (typeof user.permissions.has === 'function') {
    return user.permissions.has(permissionName)
  }

  if (Array.isArray(user.permissions)) {
    return user.permissions.includes(permissionName)
  }

  return false
}

function recipeAccessWhere(user) {
  if (!user) {
    return {
      [Op.or]: [{ is_system: 1 }, { owner_user_id: null }],
    }
  }

  if (hasPermission(user, 'recipes.manage')) {
    return {}
  }

  return {
    [Op.or]: [{ is_system: 1 }, { owner_user_id: null }, { owner_user_id: user.id }],
  }
}

async function resolveUnit(unitName, transaction = undefined) {
  if (!unitName) {
    return null
  }

  const trimmed = String(unitName).trim()
  if (!trimmed) {
    return null
  }

  const existing = await models.unit.findOne({
    where: where(fn('lower', col('name')), trimmed.toLowerCase()),
    raw: true,
    transaction,
  })

  if (existing && (existing.unit_type === 'mass' || existing.unit_type === 'volume')) {
    return existing
  }

  const inferred = inferPhysicalUnitSpec(trimmed)
  if (!inferred) {
    return null
  }

  const inserted = await models.unit.create(
    {
      name: trimmed,
      symbol: inferred.symbol,
      unit_type: inferred.unit_type,
      to_grams_factor: inferred.to_grams_factor,
      to_ml_factor: inferred.to_ml_factor,
    },
    { transaction },
  )

  return inserted.get({ plain: true })
}

async function resolvePackageTypeId(packageTypeName, transaction = undefined) {
  if (!packageTypeName) {
    return null
  }

  const name = String(packageTypeName).trim()
  if (!name) {
    return null
  }

  const normalizedName = normalizeRecipeName(name)
  const existing = await models.packageType.findOne({
    where: { normalized_name: normalizedName },
    attributes: ['id'],
    raw: true,
    transaction,
  })

  if (existing) {
    return existing.id
  }

  const inserted = await models.packageType.create(
    {
      name,
      normalized_name: normalizedName,
    },
    { transaction },
  )

  return inserted.id
}

async function resolveProductId(productId, productName, transaction = undefined) {
  if (productId) {
    return Number(productId)
  }

  if (!productName) {
    throw new Error('Each ingredient requires product_id or product_name')
  }

  const normalizedName = normalizeRecipeName(productName)
  const existing = await models.product.findOne({
    where: { normalized_name: normalizedName },
    attributes: ['id'],
    raw: true,
    transaction,
  })

  if (existing) {
    return existing.id
  }

  const created = await models.product.create(
    {
      name: productName,
      normalized_name: normalizedName,
    },
    { transaction },
  )

  return created.id
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

async function resolveIngredientPackageConversion(
  ingredient,
  productId,
  unitMeta,
  transaction = undefined,
) {
  const conversionId = parseNullableNumber(ingredient?.ingredient_package_conversion_id)
  if (conversionId !== null) {
    const existingById = await models.ingredientPackageConversion.findOne({
      where: {
        id: conversionId,
        product_id: productId,
      },
      attributes: ['id'],
      raw: true,
      transaction,
    })

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

  const packageTypeId = await resolvePackageTypeId(inferredName, transaction)
  if (!packageTypeId) {
    return null
  }

  const gramsPerPackage = deriveGramsPerPackage(ingredient?.quantity, ingredient?.grams)

  const existing = await models.ingredientPackageConversion.findOne({
    where: {
      product_id: productId,
      package_type_id: packageTypeId,
    },
    attributes: ['id', 'grams_per_package', 'samples_count'],
    raw: true,
    transaction,
  })

  if (existing) {
    if (
      gramsPerPackage !== null &&
      Math.abs(Number(existing.grams_per_package) - Number(gramsPerPackage)) > 0.001
    ) {
      const existingSamples = Number(existing.samples_count) || 0
      const nextSamples = existingSamples + 1
      const nextAverage = Number(
        (
          (Number(existing.grams_per_package) * existingSamples + gramsPerPackage) /
          nextSamples
        ).toFixed(2),
      )

      await models.ingredientPackageConversion.update(
        {
          grams_per_package: nextAverage,
          samples_count: nextSamples,
          source: 'recipe-derived:auto-avg',
          updated_at: new Date().toISOString(),
        },
        {
          where: { id: existing.id },
          transaction,
        },
      )
    }

    return existing.id
  }

  if (gramsPerPackage === null) {
    return null
  }

  const inserted = await models.ingredientPackageConversion.create(
    {
      product_id: productId,
      package_type_id: packageTypeId,
      grams_per_package: gramsPerPackage,
      source: 'recipe-derived:first-sample',
      samples_count: 1,
    },
    { transaction },
  )

  return inserted.id
}

function computeEffectiveGrams(ingredient) {
  const grams = parseNullableNumber(ingredient.grams)
  if (grams !== null) {
    return grams
  }

  const quantity = parseNullableNumber(ingredient.quantity)
  if (quantity === null) {
    return null
  }

  const conversionGrams = parseNullableNumber(
    ingredient.ingredientPackageConversion?.grams_per_package,
  )
  if (conversionGrams !== null) {
    return quantity * conversionGrams
  }

  const packageGrams = parseNullableNumber(ingredient.legacyPackage?.grams)
  if (packageGrams !== null) {
    return quantity * packageGrams
  }

  const unitToGrams = parseNullableNumber(ingredient.unit?.to_grams_factor)
  if (unitToGrams !== null) {
    return quantity * unitToGrams
  }

  const unitToMl = parseNullableNumber(ingredient.unit?.to_ml_factor)
  const productUnitToMl = parsePositiveNumber(ingredient.product?.unit_to_ml)
  const defaultUnitToGrams = parseNullableNumber(ingredient.product?.defaultUnit?.to_grams_factor)

  if (
    unitToMl !== null &&
    productUnitToMl !== null &&
    productUnitToMl > 0 &&
    defaultUnitToGrams !== null
  ) {
    return (quantity * unitToMl * defaultUnitToGrams) / productUnitToMl
  }

  return null
}

function parsePositiveNumber(value) {
  const parsed = parseNullableNumber(value)
  if (parsed === null || parsed <= 0) {
    return null
  }

  return parsed
}

async function getRecipeIngredientRows(recipeId) {
  const rows = await models.recipeIngredient.findAll({
    where: { recipe_id: recipeId },
    include: [
      {
        model: models.product,
        as: 'product',
        required: true,
        attributes: [
          'id',
          'name',
          'unit_to_ml',
          'calories_per_100g',
          'carbohydrates_per_100g',
          'sugars_per_100g',
          'fat_per_100g',
          'protein_per_100g',
          'fiber_per_100g',
        ],
        include: [
          {
            model: models.unit,
            as: 'defaultUnit',
            attributes: ['to_grams_factor'],
            required: false,
          },
        ],
      },
      {
        model: models.unit,
        as: 'unit',
        attributes: ['name', 'to_grams_factor', 'to_ml_factor'],
        required: false,
      },
      {
        model: models.ingredientPackageConversion,
        as: 'ingredientPackageConversion',
        attributes: ['id', 'grams_per_package'],
        required: false,
        include: [
          {
            model: models.packageType,
            as: 'packageType',
            attributes: ['name'],
            required: false,
          },
        ],
      },
      {
        model: models.package,
        as: 'legacyPackage',
        attributes: ['grams'],
        required: false,
      },
    ],
    order: [[literal('product.name COLLATE NOCASE'), 'ASC']],
  })

  return rows.map((row) => row.get({ plain: true }))
}

async function getRecipes(search, user) {
  const searchValue = normalizeSearch(search)
  const whereAccess = recipeAccessWhere(user)

  const whereClause = searchValue
    ? {
        [Op.and]: [
          whereAccess,
          {
            [Op.or]: [
              { name: { [Op.like]: searchValue } },
              { normalized_name: { [Op.like]: searchValue } },
            ],
          },
        ],
      }
    : whereAccess

  const recipes = await models.recipe.findAll({
    where: whereClause,
    include: [
      {
        model: models.user,
        as: 'owner',
        attributes: ['username'],
        required: false,
      },
    ],
    order: [[literal('Recipe.name COLLATE NOCASE'), 'ASC']],
  })

  const plainRecipes = recipes.map((recipe) => recipe.get({ plain: true }))
  const recipeIds = plainRecipes.map((recipe) => recipe.id)
  const counts =
    recipeIds.length > 0
      ? await models.recipeIngredient.findAll({
          attributes: ['recipe_id', [fn('COUNT', col('id')), 'ingredients_count']],
          where: {
            recipe_id: {
              [Op.in]: recipeIds,
            },
          },
          group: ['recipe_id'],
          raw: true,
        })
      : []

  const countByRecipe = new Map(
    counts.map((row) => [row.recipe_id, Number(row.ingredients_count) || 0]),
  )

  return plainRecipes.map((recipe) => ({
    id: recipe.id,
    name: recipe.name,
    normalized_name: recipe.normalized_name,
    source_file: recipe.source_file,
    instructions: recipe.instructions,
    owner_user_id: recipe.owner_user_id,
    is_system: recipe.is_system,
    is_editable: recipe.is_editable,
    owner_username: recipe.owner?.username ?? null,
    ingredients_count: countByRecipe.get(recipe.id) ?? 0,
  }))
}

async function getRecipeNutritionSummaries(user) {
  const recipes = await getRecipes(null, user)
  if (recipes.length === 0) {
    return []
  }

  const ids = recipes.map((recipe) => recipe.id)
  const summaries = await models.recipeNutritionSummary.findAll({
    where: {
      recipe_id: {
        [Op.in]: ids,
      },
    },
    raw: true,
  })

  const summaryByRecipeId = new Map(summaries.map((summary) => [summary.recipe_id, summary]))

  return recipes.map((recipe) => {
    const summary = summaryByRecipeId.get(recipe.id)
    return {
      recipe_id: recipe.id,
      recipe_name: recipe.name,
      total_grams: summary?.total_grams ?? 0,
      calories: summary?.calories ?? 0,
      carbohydrates: summary?.carbohydrates ?? 0,
      sugars: summary?.sugars ?? 0,
      fat: summary?.fat ?? 0,
      protein: summary?.protein ?? 0,
      fiber: summary?.fiber ?? 0,
    }
  })
}

async function getRecipeById(id, user) {
  const whereAccess = recipeAccessWhere(user)
  const recipe = await models.recipe.findOne({
    where: {
      [Op.and]: [whereAccess, { id }],
    },
    include: [
      {
        model: models.user,
        as: 'owner',
        attributes: ['username'],
        required: false,
      },
    ],
  })

  if (!recipe) {
    return null
  }

  const plain = recipe.get({ plain: true })
  const ingredientsCount = await models.recipeIngredient.count({
    where: { recipe_id: id },
  })

  return {
    id: plain.id,
    name: plain.name,
    normalized_name: plain.normalized_name,
    source_file: plain.source_file,
    instructions: plain.instructions,
    owner_user_id: plain.owner_user_id,
    is_system: plain.is_system,
    is_editable: plain.is_editable,
    owner_username: plain.owner?.username ?? null,
    ingredients_count: ingredientsCount,
  }
}

async function getRecipeIngredients(recipeId, user) {
  const recipe = await getRecipeById(recipeId, user)
  if (!recipe) {
    return null
  }

  const ingredientRows = await getRecipeIngredientRows(recipeId)

  const ingredients = ingredientRows.map((ingredient) => {
    const effectiveGrams = computeEffectiveGrams(ingredient)

    return {
      id: ingredient.id,
      recipe_id: ingredient.recipe_id,
      product_id: ingredient.product.id,
      product_name: ingredient.product.name,
      quantity: ingredient.quantity,
      unit_name:
        ingredient.unit?.name ?? ingredient.ingredientPackageConversion?.packageType?.name ?? null,
      ingredient_package_conversion_id: ingredient.ingredient_package_conversion_id,
      package_type_name: ingredient.ingredientPackageConversion?.packageType?.name ?? null,
      grams_per_package: ingredient.ingredientPackageConversion?.grams_per_package ?? null,
      grams: ingredient.grams,
      effective_grams: effectiveGrams === null ? null : round2(effectiveGrams),
      note: ingredient.note,
    }
  })

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

  const recipeId = await sequelize.transaction(async (transaction) => {
    const normalizedName = normalizeRecipeName(recipeName)

    const created = await models.recipe.create(
      {
        name: recipeName,
        normalized_name: normalizedName,
        source_file: payload?.source_file ?? null,
        instructions: typeof payload?.instructions === 'string' ? payload.instructions.trim() : '',
        owner_user_id: user.id,
        is_system: 0,
        is_editable: 1,
      },
      { transaction },
    )

    for (const ingredient of recipeIngredients) {
      const productId = await resolveProductId(
        ingredient.product_id,
        ingredient.product_name,
        transaction,
      )
      const unitMeta = await resolveUnit(ingredient.unit_name, transaction)
      const conversionId = await resolveIngredientPackageConversion(
        ingredient,
        productId,
        unitMeta,
        transaction,
      )

      await models.recipeIngredient.create(
        {
          recipe_id: created.id,
          product_id: productId,
          quantity: parseNullableNumber(ingredient.quantity),
          unit_id: unitMeta?.id ?? null,
          grams: parseNullableNumber(ingredient.grams),
          ingredient_package_conversion_id: conversionId,
          note: ingredient.note ?? '',
        },
        { transaction },
      )
    }

    return created.id
  })

  return getRecipeById(recipeId, user)
}

async function updateRecipe(recipeId, payload, user) {
  const existing = await models.recipe.findByPk(recipeId, {
    attributes: ['id', 'is_system', 'is_editable'],
    raw: true,
  })

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

  await sequelize.transaction(async (transaction) => {
    const normalizedName = normalizeRecipeName(recipeName)

    await models.recipe.update(
      {
        name: recipeName,
        normalized_name: normalizedName,
        source_file: payload?.source_file ?? null,
        instructions: typeof payload?.instructions === 'string' ? payload.instructions.trim() : '',
        updated_at: new Date().toISOString(),
      },
      {
        where: { id: recipeId },
        transaction,
      },
    )

    await models.recipeIngredient.destroy({
      where: { recipe_id: recipeId },
      transaction,
    })

    for (const ingredient of recipeIngredients) {
      const productId = await resolveProductId(
        ingredient.product_id,
        ingredient.product_name,
        transaction,
      )
      const unitMeta = await resolveUnit(ingredient.unit_name, transaction)
      const conversionId = await resolveIngredientPackageConversion(
        ingredient,
        productId,
        unitMeta,
        transaction,
      )

      await models.recipeIngredient.create(
        {
          recipe_id: recipeId,
          product_id: productId,
          quantity: parseNullableNumber(ingredient.quantity),
          unit_id: unitMeta?.id ?? null,
          grams: parseNullableNumber(ingredient.grams),
          ingredient_package_conversion_id: conversionId,
          note: ingredient.note ?? '',
        },
        { transaction },
      )
    }
  })

  return getRecipeById(recipeId, user)
}

async function deleteRecipe(recipeId) {
  const existing = await models.recipe.findByPk(recipeId, {
    attributes: ['id', 'is_system', 'is_editable'],
    raw: true,
  })

  if (!existing) {
    return null
  }

  if (existing.is_system || !existing.is_editable) {
    throw new Error('This recipe is read-only')
  }

  await models.recipe.destroy({
    where: { id: recipeId },
  })

  return true
}

async function getRecipeNutrition(recipeId, user) {
  const recipe = await getRecipeById(recipeId, user)
  if (!recipe) {
    return null
  }

  const summary =
    (await models.recipeNutritionSummary.findOne({
      where: { recipe_id: recipeId },
      raw: true,
    })) ?? null

  const ingredientRows = await getRecipeIngredientRows(recipeId)
  const items = ingredientRows.map((ingredient) => {
    const effectiveGrams = computeEffectiveGrams(ingredient)
    const gramsForMath = effectiveGrams ?? 0
    const product = ingredient.product

    return {
      id: ingredient.id,
      product_id: product.id,
      product_name: product.name,
      quantity: ingredient.quantity,
      unit_name:
        ingredient.unit?.name ?? ingredient.ingredientPackageConversion?.packageType?.name ?? null,
      ingredient_package_conversion_id: ingredient.ingredient_package_conversion_id,
      package_type_name: ingredient.ingredientPackageConversion?.packageType?.name ?? null,
      grams_per_package: ingredient.ingredientPackageConversion?.grams_per_package ?? null,
      grams: ingredient.grams,
      effective_grams: effectiveGrams === null ? null : round2(effectiveGrams),
      calories_per_100g: product.calories_per_100g,
      carbohydrates_per_100g: product.carbohydrates_per_100g,
      sugars_per_100g: product.sugars_per_100g,
      fat_per_100g: product.fat_per_100g,
      protein_per_100g: product.protein_per_100g,
      fiber_per_100g: product.fiber_per_100g,
      calories: round2((gramsForMath * (product.calories_per_100g ?? 0)) / 100),
      carbohydrates: round2((gramsForMath * (product.carbohydrates_per_100g ?? 0)) / 100),
      sugars: round2((gramsForMath * (product.sugars_per_100g ?? 0)) / 100),
      fat: round2((gramsForMath * (product.fat_per_100g ?? 0)) / 100),
      protein: round2((gramsForMath * (product.protein_per_100g ?? 0)) / 100),
      fiber: round2((gramsForMath * (product.fiber_per_100g ?? 0)) / 100),
    }
  })

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
