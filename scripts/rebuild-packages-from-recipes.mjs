import { literal } from 'sequelize'
import sequelize from '../src/db/client.js'
import models from '../src/models/index.js'

function normalizeName(value) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

const MASS_VOLUME_ALIASES = new Set([
  'mg',
  'g',
  'gram',
  'gramy',
  'dag',
  'kg',
  'kilogram',
  'kilogramy',
  'ml',
  'mililitr',
  'mililitry',
  'l',
  'litr',
  'litry',
])

await sequelize.authenticate()

const rows = await models.recipeIngredient.findAll({
  attributes: ['id', 'product_id', 'quantity', 'grams', 'unit_id'],
  include: [
    {
      model: models.unit,
      as: 'unit',
      attributes: ['id', 'name'],
      required: true,
    },
  ],
  where: {
    quantity: {
      [models.Op.gt]: 0,
    },
    grams: {
      [models.Op.gt]: 0,
    },
  },
  order: [['id', 'ASC']],
})

const conversions = new Map()
const nonPhysicalUnitIds = new Set()

for (const rowInstance of rows) {
  const row = rowInstance.get({ plain: true })
  const normalizedUnit = normalizeName(row.unit.name)

  if (MASS_VOLUME_ALIASES.has(normalizedUnit)) {
    continue
  }

  nonPhysicalUnitIds.add(row.unit.id)

  const gramsPerPackage = Number((row.grams / row.quantity).toFixed(2))
  const key = `${row.product_id}|${normalizedUnit}`

  if (!conversions.has(key)) {
    conversions.set(key, {
      productId: row.product_id,
      packageTypeName: row.unit.name,
      normalizedName: normalizedUnit,
      totalGrams: 0,
      samples: 0,
      recipeRows: [],
    })
  }

  const item = conversions.get(key)
  item.totalGrams += gramsPerPackage
  item.samples += 1
  item.recipeRows.push(row.id)
}

let mappingsUpserted = 0
let recipeRowsLinked = 0

await sequelize.transaction(async (transaction) => {
  for (const item of conversions.values()) {
    const [packageType] = await models.packageType.findOrCreate({
      where: { normalized_name: item.normalizedName },
      defaults: {
        name: item.packageTypeName,
        normalized_name: item.normalizedName,
      },
      transaction,
    })

    const averageGrams = Number((item.totalGrams / item.samples).toFixed(2))

    const existing = await models.ingredientPackageConversion.findOne({
      where: {
        product_id: item.productId,
        package_type_id: packageType.id,
      },
      transaction,
    })

    if (existing) {
      await existing.update(
        {
          grams_per_package: averageGrams,
          source: 'rebuild-from-recipes',
          samples_count: item.samples,
          updated_at: new Date().toISOString(),
        },
        { transaction },
      )
    } else {
      await models.ingredientPackageConversion.create(
        {
          product_id: item.productId,
          package_type_id: packageType.id,
          grams_per_package: averageGrams,
          source: 'rebuild-from-recipes',
          samples_count: item.samples,
        },
        { transaction },
      )
    }

    mappingsUpserted += 1

    const conversion = await models.ingredientPackageConversion.findOne({
      where: {
        product_id: item.productId,
        package_type_id: packageType.id,
      },
      attributes: ['id'],
      raw: true,
      transaction,
    })

    if (!conversion) {
      continue
    }

    for (const recipeIngredientId of item.recipeRows) {
      await models.recipeIngredient.update(
        {
          ingredient_package_conversion_id: conversion.id,
          unit_id: null,
        },
        {
          where: { id: recipeIngredientId },
          transaction,
        },
      )
      recipeRowsLinked += 1
    }
  }

  if (nonPhysicalUnitIds.size > 0) {
    await models.unit.destroy({
      where: {
        id: Array.from(nonPhysicalUnitIds),
      },
      transaction,
    })
  }
})

const physicalUnits = await models.unit.findAll({
  attributes: ['name'],
  order: [[literal('name COLLATE NOCASE'), 'ASC']],
  raw: true,
})

const inconsistentRaw = await models.ingredientPackageConversion.findAll({
  attributes: ['package_type_id', 'grams_per_package'],
  include: [
    {
      model: models.packageType,
      as: 'packageType',
      attributes: ['name'],
      required: true,
    },
  ],
  raw: true,
})

const grouped = new Map()
for (const row of inconsistentRaw) {
  const key = row.package_type_id
  if (!grouped.has(key)) {
    grouped.set(key, {
      package_type_name: row['packageType.name'],
      products_count: 0,
      min_grams: Number(row.grams_per_package),
      max_grams: Number(row.grams_per_package),
    })
  }

  const item = grouped.get(key)
  const grams = Number(row.grams_per_package)
  item.products_count += 1
  item.min_grams = Math.min(item.min_grams, grams)
  item.max_grams = Math.max(item.max_grams, grams)
}

const inconsistent = Array.from(grouped.values())
  .filter((item) => item.min_grams !== item.max_grams)
  .sort((left, right) => {
    if (right.products_count !== left.products_count) {
      return right.products_count - left.products_count
    }

    return left.package_type_name.localeCompare(right.package_type_name, 'pl')
  })

await sequelize.close()

console.log(`Package mappings upserted: ${mappingsUpserted}`)
console.log(`Recipe rows linked to mappings: ${recipeRowsLinked}`)
console.log(`Removed non-physical units: ${nonPhysicalUnitIds.size}`)
console.log(`Remaining units: ${physicalUnits.map((item) => item.name).join(', ')}`)

if (inconsistent.length > 0) {
  console.log('Non-uniform package types by ingredient:')
  for (const row of inconsistent) {
    console.log(
      `- ${row.package_type_name}: ${row.products_count} products, ${row.min_grams}-${row.max_grams} g`,
    )
  }
}
