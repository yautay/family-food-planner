import { Op, literal } from 'sequelize'
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

function parsePositiveNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function mapConversion(row) {
  if (!row) {
    return null
  }

  return {
    id: row.id,
    product_id: row.product_id,
    product_name: row.product_name ?? row.product?.name ?? null,
    package_type_id: row.package_type_id,
    package_type_name: row.package_type_name ?? row.packageType?.name ?? null,
    grams_per_package: row.grams_per_package,
    samples_count: row.samples_count,
    source: row.source,
    created_at: row.created_at,
    updated_at: row.updated_at,
  }
}

async function resolvePackageTypeId(payload) {
  const packageTypeId = Number(payload?.package_type_id)
  if (Number.isInteger(packageTypeId) && packageTypeId > 0) {
    return packageTypeId
  }

  const packageTypeName =
    typeof payload?.package_type_name === 'string' ? payload.package_type_name.trim() : ''

  if (!packageTypeName) {
    throw new Error('Package type is required')
  }

  const normalizedName = normalizeName(packageTypeName)
  const existing = await models.packageType.findOne({
    where: { normalized_name: normalizedName },
    attributes: ['id'],
    raw: true,
  })

  if (existing) {
    return existing.id
  }

  const created = await models.packageType.create({
    name: packageTypeName,
    normalized_name: normalizedName,
  })

  return created.id
}

async function getConversionById(conversionId) {
  const row = await models.ingredientPackageConversion.findByPk(conversionId, {
    include: [
      {
        model: models.product,
        as: 'product',
        attributes: ['name'],
      },
      {
        model: models.packageType,
        as: 'packageType',
        attributes: ['name'],
      },
    ],
  })

  return mapConversion(row?.get({ plain: true }))
}

async function getPackageTypes() {
  return models.packageType.findAll({
    attributes: ['id', 'name', 'normalized_name'],
    order: [[literal('name COLLATE NOCASE'), 'ASC']],
    raw: true,
  })
}

async function getPackages() {
  const rows = await models.ingredientPackageConversion.findAll({
    include: [
      {
        model: models.product,
        as: 'product',
        attributes: ['name'],
        required: true,
      },
      {
        model: models.packageType,
        as: 'packageType',
        attributes: ['name'],
        required: true,
      },
    ],
    order: [
      [literal('product.name COLLATE NOCASE'), 'ASC'],
      [literal('packageType.name COLLATE NOCASE'), 'ASC'],
    ],
  })

  return rows.map((row) => mapConversion(row.get({ plain: true })))
}

async function addPackage(payload) {
  const productId = Number(payload?.product_id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient is required')
  }

  const gramsPerPackage = parsePositiveNumber(payload?.grams_per_package)
  if (gramsPerPackage === null) {
    throw new Error('grams_per_package must be a positive number')
  }

  const packageTypeId = await resolvePackageTypeId(payload)
  const source = typeof payload?.source === 'string' ? payload.source.trim() : 'manual'

  const existing = await models.ingredientPackageConversion.findOne({
    where: {
      product_id: productId,
      package_type_id: packageTypeId,
    },
    attributes: ['id'],
    raw: true,
  })

  if (existing) {
    await models.ingredientPackageConversion.update(
      {
        grams_per_package: gramsPerPackage,
        source: source || 'manual',
        updated_at: new Date().toISOString(),
      },
      {
        where: { id: existing.id },
      },
    )

    return getConversionById(existing.id)
  }

  const created = await models.ingredientPackageConversion.create({
    product_id: productId,
    package_type_id: packageTypeId,
    grams_per_package: gramsPerPackage,
    source: source || 'manual',
    samples_count: 1,
  })

  return getConversionById(created.id)
}

async function updatePackage(payload) {
  const conversionId = Number(payload?.id)
  if (!Number.isInteger(conversionId) || conversionId <= 0) {
    throw new Error('Package mapping id is invalid')
  }

  const existing = await models.ingredientPackageConversion.findByPk(conversionId, {
    attributes: ['id'],
  })

  if (!existing) {
    return 0
  }

  const productId = Number(payload?.product_id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient is required')
  }

  const gramsPerPackage = parsePositiveNumber(payload?.grams_per_package)
  if (gramsPerPackage === null) {
    throw new Error('grams_per_package must be a positive number')
  }

  const packageTypeId = await resolvePackageTypeId(payload)
  const source = typeof payload?.source === 'string' ? payload.source.trim() : 'manual'

  const [changes] = await models.ingredientPackageConversion.update(
    {
      product_id: productId,
      package_type_id: packageTypeId,
      grams_per_package: gramsPerPackage,
      source: source || 'manual',
      updated_at: new Date().toISOString(),
    },
    {
      where: { id: conversionId },
    },
  )

  return changes
}

async function deletePackage(conversionId) {
  const id = Number(conversionId)
  if (!Number.isInteger(id) || id <= 0) {
    throw new Error('Package mapping id is invalid')
  }

  const usageCount = await models.recipeIngredient.count({
    where: {
      ingredient_package_conversion_id: id,
    },
  })

  if (usageCount > 0) {
    throw new Error('Package mapping is used in recipes and cannot be deleted')
  }

  return models.ingredientPackageConversion.destroy({
    where: { id },
  })
}

export default {
  getPackageTypes,
  getPackages,
  addPackage,
  updatePackage,
  deletePackage,
}
