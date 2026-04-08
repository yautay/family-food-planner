import { Op, literal } from 'sequelize'
import sequelize from '../db/client.js'
import models from '../models/index.js'

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
  const tagIds = Array.isArray(row?.tag_id)
    ? row.tag_id
    : Array.isArray(row?.tags)
      ? row.tags
          .map((item) => Number(item?.id))
          .filter((item) => Number.isInteger(item) && item > 0)
      : []

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
    tag_id: tagIds,
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

async function getUnitMeta(unitId, transaction = undefined) {
  if (!Number.isInteger(unitId) || unitId <= 0) {
    return null
  }

  return models.unit.findByPk(unitId, {
    attributes: ['id', 'name', 'unit_type', 'to_grams_factor', 'to_ml_factor'],
    raw: true,
    transaction,
  })
}

function normalizeUnitToMl(value, unitMeta) {
  const explicit = parsePositiveNumber(value)
  if (explicit !== null) {
    return explicit
  }

  const fromUnit = parsePositiveNumber(unitMeta?.to_ml_factor)
  return fromUnit !== null ? fromUnit : null
}

async function upsertDefaultPackageConversion(productId, payload, transaction = undefined) {
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

  const existing = await models.ingredientPackageConversion.findOne({
    where: {
      product_id: productId,
      package_type_id: packageTypeId,
    },
    attributes: ['id', 'samples_count'],
    raw: true,
    transaction,
  })

  if (existing) {
    await models.ingredientPackageConversion.update(
      {
        grams_per_package: gramsPerPackage,
        source: 'ingredient-default-package',
        samples_count: Math.max(1, Number(existing.samples_count) || 1),
        updated_at: new Date().toISOString(),
      },
      {
        where: { id: existing.id },
        transaction,
      },
    )
    return
  }

  await models.ingredientPackageConversion.create(
    {
      product_id: productId,
      package_type_id: packageTypeId,
      grams_per_package: gramsPerPackage,
      source: 'ingredient-default-package',
      samples_count: 1,
    },
    { transaction },
  )
}

async function replaceProductTags(productId, tagIds, transaction = undefined) {
  await models.productTag.destroy({ where: { product_id: productId }, transaction })

  if (tagIds.length === 0) {
    return
  }

  await models.productTag.bulkCreate(
    tagIds.map((tagId) => ({
      product_id: productId,
      tag_id: tagId,
    })),
    { transaction },
  )
}

function mapProductToIngredient(product) {
  const row = {
    id: product.id,
    name: product.name,
    comment: product.comment,
    unit_id: product.default_unit_id,
    unit_to_ml: product.unit_to_ml,
    package_type_id: product.default_package_type_id,
    package_type_name: product.defaultPackageType?.name ?? null,
    quantity_per_package: product.quantity_per_package,
    calories_per_100g: product.calories_per_100g,
    carbohydrates_per_100g: product.carbohydrates_per_100g,
    sugars_per_100g: product.sugars_per_100g,
    fat_per_100g: product.fat_per_100g,
    protein_per_100g: product.protein_per_100g,
    fiber_per_100g: product.fiber_per_100g,
    unit_to_grams_factor: product.defaultUnit?.to_grams_factor ?? null,
    tags: product.tags ?? [],
  }

  return mapIngredientRow(row)
}

async function getIngredientById(productId, transaction = undefined) {
  const product = await models.product.findByPk(productId, {
    include: [
      {
        model: models.unit,
        as: 'defaultUnit',
        attributes: ['to_grams_factor'],
        required: false,
      },
      {
        model: models.packageType,
        as: 'defaultPackageType',
        attributes: ['name'],
        required: false,
      },
      {
        model: models.tag,
        as: 'tags',
        attributes: ['id'],
        through: { attributes: [] },
        required: false,
      },
    ],
    transaction,
  })

  if (!product) {
    return null
  }

  return mapProductToIngredient(product.get({ plain: true }))
}

async function getIngredients() {
  const products = await models.product.findAll({
    include: [
      {
        model: models.unit,
        as: 'defaultUnit',
        attributes: ['to_grams_factor'],
        required: false,
      },
      {
        model: models.packageType,
        as: 'defaultPackageType',
        attributes: ['name'],
        required: false,
      },
      {
        model: models.tag,
        as: 'tags',
        attributes: ['id'],
        through: { attributes: [] },
        required: false,
      },
    ],
    order: [[literal('Product.name COLLATE NOCASE'), 'ASC']],
  })

  return products.map((product) => mapProductToIngredient(product.get({ plain: true })))
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

  return sequelize.transaction(async (transaction) => {
    const unitMeta = await getUnitMeta(unitId, transaction)
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
    const existing = await models.product.findOne({
      where: { normalized_name: normalizedName },
      attributes: ['id'],
      raw: true,
      transaction,
    })

    let productId

    if (existing) {
      productId = existing.id
      await models.product.update(
        {
          name,
          comment,
          default_unit_id: unitId,
          default_package_type_id: payload.packageTypeId,
          quantity_per_package: payload.quantityPerPackage,
          unit_to_ml: payload.unitToMl,
          calories_per_100g: payload.calories,
          carbohydrates_per_100g: payload.carbohydrates,
          sugars_per_100g: payload.sugars,
          fat_per_100g: payload.fat,
          protein_per_100g: payload.protein,
          fiber_per_100g: payload.fiber,
          updated_at: new Date().toISOString(),
        },
        {
          where: { id: productId },
          transaction,
        },
      )
    } else {
      const created = await models.product.create(
        {
          name,
          normalized_name: normalizedName,
          default_unit_id: unitId,
          default_package_type_id: payload.packageTypeId,
          comment,
          quantity_per_package: payload.quantityPerPackage,
          unit_to_ml: payload.unitToMl,
          calories_per_100g: payload.calories,
          carbohydrates_per_100g: payload.carbohydrates,
          sugars_per_100g: payload.sugars,
          fat_per_100g: payload.fat,
          protein_per_100g: payload.protein,
          fiber_per_100g: payload.fiber,
        },
        { transaction },
      )

      productId = created.id
    }

    await replaceProductTags(productId, tagIds, transaction)
    await upsertDefaultPackageConversion(
      productId,
      {
        packageTypeId: payload.packageTypeId,
        quantityPerPackage: payload.quantityPerPackage,
        unitMeta,
      },
      transaction,
    )

    return getIngredientById(productId, transaction)
  })
}

async function updateIngredient(item) {
  const productId = Number(item?.id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient id is invalid')
  }

  return sequelize.transaction(async (transaction) => {
    const existing = await models.product.findByPk(productId, {
      attributes: ['id'],
      transaction,
    })

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

    const unitMeta = await getUnitMeta(unitId, transaction)
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

    const nameCollision = await models.product.findOne({
      where: {
        normalized_name: normalizedName,
        id: {
          [Op.ne]: productId,
        },
      },
      attributes: ['id'],
      raw: true,
      transaction,
    })

    if (nameCollision) {
      throw new Error('Ingredient with this name already exists')
    }

    const [changes] = await models.product.update(
      {
        name,
        normalized_name: normalizedName,
        default_unit_id: unitId,
        default_package_type_id: payload.packageTypeId,
        comment,
        quantity_per_package: payload.quantityPerPackage,
        unit_to_ml: payload.unitToMl,
        calories_per_100g: payload.calories,
        carbohydrates_per_100g: payload.carbohydrates,
        sugars_per_100g: payload.sugars,
        fat_per_100g: payload.fat,
        protein_per_100g: payload.protein,
        fiber_per_100g: payload.fiber,
        updated_at: new Date().toISOString(),
      },
      {
        where: { id: productId },
        transaction,
      },
    )

    await replaceProductTags(productId, tagIds, transaction)
    await upsertDefaultPackageConversion(
      productId,
      {
        packageTypeId: payload.packageTypeId,
        quantityPerPackage: payload.quantityPerPackage,
        unitMeta,
      },
      transaction,
    )

    return changes
  })
}

async function deleteIngredient(id) {
  const productId = Number(id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient id is invalid')
  }

  const usageCount = await models.recipeIngredient.count({
    where: {
      product_id: productId,
    },
  })

  if (usageCount > 0) {
    throw new Error('Ingredient is used in recipes and cannot be deleted')
  }

  return sequelize.transaction(async (transaction) => {
    await models.productTag.destroy({
      where: { product_id: productId },
      transaction,
    })

    await models.ingredientPackageConversion.destroy({
      where: {
        product_id: productId,
        source: 'ingredient-default-package',
      },
      transaction,
    })

    await models.productPackage.destroy({
      where: { product_id: productId },
      transaction,
    })

    return models.product.destroy({
      where: { id: productId },
      transaction,
    })
  })
}

export default {
  getIngredients,
  addIngredient,
  updateIngredient,
  deleteIngredient,
}
