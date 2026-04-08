import { execFileSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import sequelize from '../src/db/client.js'
import models from '../src/models/index.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const coreRecipesDir = path.join(projectRoot, 'core_recipes')

const dayHeaderRegex =
  /^(Poniedzialek|Wtorek|Sroda|Czwartek|Piatek|Sobota|Niedziela|Poniedzialek|Sroda)$/i

function removeDiacritics(value) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

function normalizeWhitespace(value) {
  return value.replace(/\s+/g, ' ').trim()
}

function normalizeKey(value) {
  return removeDiacritics(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

function toNumber(value) {
  return Number(value.replace(',', '.'))
}

function cleanName(value) {
  return normalizeWhitespace(value).replace(/\s+,/g, ',').replace(/\s+\./g, '.').trim()
}

function normalizeUnitAlias(value) {
  return removeDiacritics(value).toLowerCase().trim()
}

function isPhysicalUnitName(unitName) {
  const normalized = normalizeUnitAlias(unitName)
  return [
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
  ].includes(normalized)
}

function looksLikeIngredientLine(line) {
  const quantityPattern =
    /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*x\s*([^()]+?)\s*\(([0-9]+(?:[.,][0-9]+)?)\s*g\)$/i
  const gramsOnlyPattern = /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*g$/i

  return quantityPattern.test(line) || gramsOnlyPattern.test(line)
}

function parseIngredientLine(line) {
  const quantityPattern =
    /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*x\s*([^()]+?)\s*\(([0-9]+(?:[.,][0-9]+)?)\s*g\)$/i
  const gramsOnlyPattern = /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*g$/i

  const quantityMatch = line.match(quantityPattern)
  if (quantityMatch) {
    const name = cleanName(quantityMatch[1])
    const quantity = toNumber(quantityMatch[2])
    const unitName = cleanName(quantityMatch[3])
    const grams = toNumber(quantityMatch[4])

    if (!name || Number.isNaN(quantity) || Number.isNaN(grams)) {
      return null
    }

    return {
      name,
      quantity,
      unitName,
      grams,
    }
  }

  const gramsOnlyMatch = line.match(gramsOnlyPattern)
  if (gramsOnlyMatch) {
    const name = cleanName(gramsOnlyMatch[1])
    const grams = toNumber(gramsOnlyMatch[2])

    if (!name || Number.isNaN(grams)) {
      return null
    }

    return {
      name,
      quantity: null,
      unitName: null,
      grams,
    }
  }

  return null
}

function isNoiseLine(line) {
  if (!line) {
    return true
  }

  const normalized = normalizeKey(line)

  if (
    normalized.startsWith('kcal') ||
    normalized.startsWith('w ') ||
    normalized.startsWith('t ') ||
    normalized.startsWith('b ') ||
    normalized.startsWith('bl ') ||
    normalized.startsWith('lg ') ||
    normalized.startsWith('suma dnia') ||
    normalized.startsWith('zjedz ') ||
    normalized.startsWith('przepis na ') ||
    normalized === 'przepis' ||
    normalized === 'produkty' ||
    normalized === 'komentarz' ||
    normalized === 'sniadanie' ||
    normalized === 'obiad' ||
    normalized === 'podwieczorek' ||
    normalized === 'kolacja' ||
    normalized === 'lista zakupow' ||
    normalized === 'podsumowanie jadlospisu' ||
    dayHeaderRegex.test(removeDiacritics(line))
  ) {
    return true
  }

  if (/^[0-9]+\/[0-9]+$/.test(line)) {
    return true
  }

  return false
}

function looksLikeInstructionLine(line) {
  const normalized = normalizeKey(line)
  if (!normalized) {
    return true
  }

  if (normalized.length > 70) {
    return true
  }

  if (
    /\b(dodac|dodaj|podsmazyc|usmazyc|piec|upiec|ugotowac|pokroic|wymieszac|zblenderowac|przyprawic|beztluszczowo|bez tluszczu)\b/i.test(
      normalized,
    )
  ) {
    return true
  }

  if (/[,.;:]$/.test(line.trim())) {
    return true
  }

  const hasLowercaseStart = /^[a-z]/.test(removeDiacritics(line.trim()))
  if (hasLowercaseStart && normalized.split(' ').length > 3) {
    return true
  }

  return false
}

function looksLikeIngredientFragment(line) {
  if (!line) {
    return false
  }

  if (/^\([0-9]+(?:[.,][0-9]+)?\s*g\)$/i.test(line.trim())) {
    return true
  }

  if (/,[\s]*[0-9]+(?:[.,][0-9]+)?\s*x\s+/i.test(line)) {
    return true
  }

  return false
}

function mergeWrappedLines(rawLines) {
  const merged = []

  for (let index = 0; index < rawLines.length; index += 1) {
    const current = normalizeWhitespace(rawLines[index].replace(/\f/g, ''))

    if (!current) {
      continue
    }

    const nextRaw = rawLines[index + 1]
    const next = nextRaw ? normalizeWhitespace(nextRaw.replace(/\f/g, '')) : null

    if (next) {
      if (!current.includes(',') && /^\([^)]*\),\s*[0-9]+(?:[.,][0-9]+)?\s*x\s+/i.test(next)) {
        merged.push(`${current} ${next}`)
        index += 1
        continue
      }

      if (current.endsWith(',') && /^[0-9]+(?:[.,][0-9]+)?\s*x\s+/i.test(next)) {
        merged.push(`${current} ${next}`)
        index += 1
        continue
      }

      if (
        /^.+,\s*[0-9]+(?:[.,][0-9]+)?\s*x\s*[^()]+$/i.test(current) &&
        /^\([0-9]+(?:[.,][0-9]+)?\s*g\)$/i.test(next)
      ) {
        merged.push(`${current} ${next}`)
        index += 1
        continue
      }
    }

    merged.push(current)
  }

  return merged
}

function extractRecipeTitles(lines) {
  const titles = new Map()

  for (let index = 0; index < lines.length; index += 1) {
    if (normalizeKey(lines[index]) !== 'przepis') {
      continue
    }

    let cursor = index - 1
    while (cursor >= 0 && index - cursor <= 6) {
      const candidate = cleanName(lines[cursor])
      cursor -= 1

      if (isNoiseLine(candidate)) {
        continue
      }

      if (looksLikeIngredientLine(candidate)) {
        continue
      }

      if (looksLikeInstructionLine(candidate)) {
        continue
      }

      const key = normalizeKey(candidate)
      if (key) {
        titles.set(key, candidate)
      }
      break
    }
  }

  return titles
}

const productCatalog = new Map()
const recipeCatalog = new Map()
const relationRows = []

function upsertProduct(name, unitName) {
  const normalizedName = normalizeKey(name)
  if (!normalizedName) {
    return null
  }

  if (!productCatalog.has(normalizedName)) {
    productCatalog.set(normalizedName, {
      name,
      normalizedName,
      units: new Map(),
    })
  }

  if (unitName) {
    const unitKey = normalizeKey(unitName)
    const product = productCatalog.get(normalizedName)
    const currentCount = product.units.get(unitKey) ?? 0
    product.units.set(unitKey, currentCount + 1)
  }

  return normalizedName
}

function upsertRecipe(name, sourceFile) {
  const normalizedName = normalizeKey(name)
  if (!normalizedName) {
    return null
  }

  if (!recipeCatalog.has(normalizedName)) {
    recipeCatalog.set(normalizedName, {
      name,
      normalizedName,
      sourceFiles: new Set(),
      instructionLines: [],
    })
  }

  recipeCatalog.get(normalizedName).sourceFiles.add(sourceFile)
  return normalizedName
}

function appendRecipeInstruction(recipeKey, line) {
  if (!recipeKey || !recipeCatalog.has(recipeKey)) {
    return
  }

  const normalizedLine = normalizeWhitespace(line)
  if (!normalizedLine) {
    return
  }

  recipeCatalog.get(recipeKey).instructionLines.push(normalizedLine)
}

function parsePdf(filePath, fileName) {
  const text = execFileSync('pdftotext', [filePath, '-'], {
    encoding: 'utf8',
    maxBuffer: 1024 * 1024 * 32,
  })

  const rawLines = text.split('\n')
  const lines = mergeWrappedLines(rawLines)
  const recipeTitles = extractRecipeTitles(lines)

  const titleByKey = new Map(recipeTitles)

  let inDetails = false
  let currentRecipeKey = null

  for (const line of lines) {
    const normalizedLine = normalizeKey(line)

    if (normalizedLine === 'lista zakupow') {
      inDetails = false
      currentRecipeKey = null
      continue
    }

    if (dayHeaderRegex.test(removeDiacritics(line))) {
      inDetails = true
      currentRecipeKey = null
      continue
    }

    if (!inDetails) {
      continue
    }

    if (titleByKey.has(normalizedLine)) {
      currentRecipeKey = upsertRecipe(titleByKey.get(normalizedLine), fileName)
      continue
    }

    const ingredient = parseIngredientLine(line)
    if (!currentRecipeKey) {
      continue
    }

    if (ingredient) {
      const productKey = upsertProduct(ingredient.name, ingredient.unitName)
      if (!productKey) {
        continue
      }

      relationRows.push({
        recipeKey: currentRecipeKey,
        productKey,
        quantity: ingredient.quantity,
        unitName: ingredient.unitName,
        grams: ingredient.grams,
        sourceFile: fileName,
      })

      continue
    }

    if (isNoiseLine(line) || titleByKey.has(normalizedLine)) {
      continue
    }

    if (!looksLikeInstructionLine(line) || looksLikeIngredientFragment(line)) {
      continue
    }

    appendRecipeInstruction(currentRecipeKey, line)
  }
}

function pickDefaultUnit(product) {
  const units = Array.from(product.units.entries())
  if (units.length === 0) {
    return null
  }

  units.sort((left, right) => right[1] - left[1])
  return units[0][0]
}

async function tableExists(tableName) {
  try {
    await sequelize.getQueryInterface().describeTable(tableName)
    return true
  } catch {
    return false
  }
}

const pdfFiles = readdirSync(coreRecipesDir)
  .filter((name) => name.toLowerCase().endsWith('.pdf'))
  .sort((left, right) => left.localeCompare(right))

if (pdfFiles.length === 0) {
  console.error('No PDF files found in core_recipes/.')
  process.exit(1)
}

for (const fileName of pdfFiles) {
  const filePath = path.join(coreRecipesDir, fileName)
  parsePdf(filePath, fileName)
}

await sequelize.authenticate()

if (
  !(await tableExists('products')) ||
  !(await tableExists('recipes')) ||
  !(await tableExists('recipe_ingredients'))
) {
  console.error('Missing catalog tables. Run npm run db:migrate first.')
  await sequelize.close()
  process.exit(1)
}
await sequelize.transaction(async (transaction) => {
  const recipeTableInfo = await sequelize.getQueryInterface().describeTable('recipes')
  const hasRecipeAclColumns = Object.hasOwn(recipeTableInfo, 'is_system')

  if (hasRecipeAclColumns) {
    const systemRecipes = await models.recipe.findAll({
      attributes: ['id'],
      where: { is_system: 1 },
      raw: true,
      transaction,
    })

    const systemRecipeIds = systemRecipes.map((row) => row.id)
    if (systemRecipeIds.length > 0) {
      await models.recipeIngredient.destroy({
        where: {
          recipe_id: {
            [models.Op.in]: systemRecipeIds,
          },
        },
        transaction,
      })
      await models.recipe.destroy({
        where: {
          id: {
            [models.Op.in]: systemRecipeIds,
          },
        },
        transaction,
      })
    }
  } else {
    await models.recipeIngredient.destroy({ where: {}, transaction })
    await models.recipe.destroy({ where: {}, transaction })
  }

  const allUnitKeys = new Set()
  for (const product of productCatalog.values()) {
    for (const unitKey of product.units.keys()) {
      allUnitKeys.add(unitKey)
    }
  }
  for (const relation of relationRows) {
    if (relation.unitName && isPhysicalUnitName(relation.unitName)) {
      allUnitKeys.add(normalizeKey(relation.unitName))
    }
  }

  const canonicalUnitNames = new Map()
  for (const relation of relationRows) {
    if (!relation.unitName) {
      continue
    }
    const key = normalizeKey(relation.unitName)
    if (!canonicalUnitNames.has(key)) {
      canonicalUnitNames.set(key, cleanName(relation.unitName))
    }
  }

  for (const unitKey of allUnitKeys) {
    const unitName = canonicalUnitNames.get(unitKey)
    if (!unitName || !isPhysicalUnitName(unitName)) {
      continue
    }

    await models.unit.findOrCreate({
      where: { name: unitName },
      defaults: { name: unitName },
      transaction,
    })
  }

  const units = await models.unit.findAll({
    attributes: ['id', 'name'],
    raw: true,
    transaction,
  })
  const unitIdByKey = new Map(units.map((row) => [normalizeKey(row.name), row.id]))

  for (const product of productCatalog.values()) {
    const defaultUnitKey = pickDefaultUnit(product)
    const defaultUnitId = defaultUnitKey ? (unitIdByKey.get(defaultUnitKey) ?? null) : null

    const existing = await models.product.findOne({
      where: { normalized_name: product.normalizedName },
      transaction,
    })

    if (existing) {
      await existing.update(
        {
          name: product.name,
          default_unit_id: existing.default_unit_id ?? defaultUnitId,
          updated_at: new Date().toISOString(),
        },
        { transaction },
      )
    } else {
      await models.product.create(
        {
          name: product.name,
          normalized_name: product.normalizedName,
          default_unit_id: defaultUnitId,
        },
        { transaction },
      )
    }
  }

  for (const recipe of recipeCatalog.values()) {
    const uniqueInstructions = []
    const seenInstructionKeys = new Set()

    for (const line of recipe.instructionLines) {
      const key = normalizeKey(line)
      if (!key || seenInstructionKeys.has(key)) {
        continue
      }

      seenInstructionKeys.add(key)
      uniqueInstructions.push(line)
    }

    const payload = {
      name: recipe.name,
      normalized_name: recipe.normalizedName,
      source_file: Array.from(recipe.sourceFiles)
        .sort((left, right) => left.localeCompare(right))
        .join(', '),
      instructions: uniqueInstructions.join(' '),
      updated_at: new Date().toISOString(),
    }

    const existing = await models.recipe.findOne({
      where: { normalized_name: recipe.normalizedName },
      transaction,
    })

    if (existing) {
      await existing.update(
        hasRecipeAclColumns
          ? {
              ...payload,
              owner_user_id: null,
              is_system: 1,
              is_editable: 0,
            }
          : payload,
        { transaction },
      )
    } else {
      await models.recipe.create(
        hasRecipeAclColumns
          ? {
              ...payload,
              owner_user_id: null,
              is_system: 1,
              is_editable: 0,
            }
          : payload,
        { transaction },
      )
    }
  }

  const products = await models.product.findAll({
    attributes: ['id', 'normalized_name'],
    raw: true,
    transaction,
  })
  const recipes = await models.recipe.findAll({
    attributes: ['id', 'normalized_name'],
    raw: true,
    transaction,
  })

  const productIdByKey = new Map(products.map((row) => [row.normalized_name, row.id]))
  const recipeIdByKey = new Map(recipes.map((row) => [row.normalized_name, row.id]))

  const packageTypeNameByKey = new Map()
  for (const relation of relationRows) {
    if (!relation.unitName || isPhysicalUnitName(relation.unitName)) {
      continue
    }

    const normalizedName = normalizeKey(relation.unitName)
    if (packageTypeNameByKey.has(normalizedName)) {
      continue
    }

    packageTypeNameByKey.set(normalizedName, cleanName(relation.unitName))
    await models.packageType.findOrCreate({
      where: { normalized_name: normalizedName },
      defaults: {
        name: cleanName(relation.unitName),
        normalized_name: normalizedName,
      },
      transaction,
    })
  }

  const packageTypes = await models.packageType.findAll({
    attributes: ['id', 'normalized_name'],
    raw: true,
    transaction,
  })
  const packageTypeIdByKey = new Map(packageTypes.map((row) => [row.normalized_name, row.id]))

  const conversionAggregates = new Map()
  for (const relation of relationRows) {
    if (!relation.unitName || isPhysicalUnitName(relation.unitName)) {
      continue
    }

    if (
      typeof relation.quantity !== 'number' ||
      relation.quantity <= 0 ||
      typeof relation.grams !== 'number' ||
      relation.grams <= 0
    ) {
      continue
    }

    const productId = productIdByKey.get(relation.productKey)
    const packageTypeId = packageTypeIdByKey.get(normalizeKey(relation.unitName))
    if (!productId || !packageTypeId) {
      continue
    }

    const gramsPerPackage = relation.grams / relation.quantity
    const aggregateKey = `${productId}|${packageTypeId}`

    if (!conversionAggregates.has(aggregateKey)) {
      conversionAggregates.set(aggregateKey, {
        productId,
        packageTypeId,
        gramsTotal: 0,
        samples: 0,
      })
    }

    const aggregate = conversionAggregates.get(aggregateKey)
    aggregate.gramsTotal += gramsPerPackage
    aggregate.samples += 1
  }

  for (const aggregate of conversionAggregates.values()) {
    const averageGrams = Number((aggregate.gramsTotal / aggregate.samples).toFixed(2))
    const existing = await models.ingredientPackageConversion.findOne({
      where: {
        product_id: aggregate.productId,
        package_type_id: aggregate.packageTypeId,
      },
      transaction,
    })

    if (existing) {
      await existing.update(
        {
          grams_per_package: averageGrams,
          source: 'import-diet-pdfs',
          samples_count: aggregate.samples,
          updated_at: new Date().toISOString(),
        },
        { transaction },
      )
    } else {
      await models.ingredientPackageConversion.create(
        {
          product_id: aggregate.productId,
          package_type_id: aggregate.packageTypeId,
          grams_per_package: averageGrams,
          source: 'import-diet-pdfs',
          samples_count: aggregate.samples,
        },
        { transaction },
      )
    }
  }

  const allConversions = await models.ingredientPackageConversion.findAll({
    attributes: ['id', 'product_id', 'package_type_id'],
    raw: true,
    transaction,
  })

  const conversionIdByPair = new Map(
    allConversions.map((row) => [`${row.product_id}|${row.package_type_id}`, row.id]),
  )

  const importedRecipeIds = Array.from(
    new Set(relationRows.map((row) => recipeIdByKey.get(row.recipeKey))),
  ).filter((value) => Number.isInteger(value) && value > 0)

  if (importedRecipeIds.length > 0) {
    await models.recipeIngredient.destroy({
      where: {
        recipe_id: {
          [models.Op.in]: importedRecipeIds,
        },
      },
      transaction,
    })
  }

  const relationDedup = new Set()
  const ingredientRows = []

  for (const relation of relationRows) {
    const recipeId = recipeIdByKey.get(relation.recipeKey)
    const productId = productIdByKey.get(relation.productKey)
    const packageTypeId = relation.unitName
      ? !isPhysicalUnitName(relation.unitName)
        ? (packageTypeIdByKey.get(normalizeKey(relation.unitName)) ?? null)
        : null
      : null

    const ingredientPackageConversionId =
      packageTypeId && productId
        ? (conversionIdByPair.get(`${productId}|${packageTypeId}`) ?? null)
        : null

    const unitId = relation.unitName
      ? isPhysicalUnitName(relation.unitName)
        ? (unitIdByKey.get(normalizeKey(relation.unitName)) ?? null)
        : null
      : null

    if (!recipeId || !productId) {
      continue
    }

    const dedupKey = [
      recipeId,
      productId,
      relation.quantity ?? '',
      unitId ?? '',
      ingredientPackageConversionId ?? '',
      relation.grams ?? '',
    ].join('|')

    if (relationDedup.has(dedupKey)) {
      continue
    }
    relationDedup.add(dedupKey)

    ingredientRows.push({
      recipe_id: recipeId,
      product_id: productId,
      quantity: relation.quantity,
      unit_id: unitId,
      grams: relation.grams,
      ingredient_package_conversion_id: ingredientPackageConversionId,
      note: '',
      source_file: relation.sourceFile,
    })
  }

  if (ingredientRows.length > 0) {
    await models.recipeIngredient.bulkCreate(ingredientRows, { transaction })
  }
})

const productCount = await models.product.count()
const recipeCount = await models.recipe.count()
const relationCount = await models.recipeIngredient.count()

await sequelize.close()

console.log(`Imported files: ${pdfFiles.length}`)
console.log(`Products in catalog: ${productCount}`)
console.log(`Recipes in catalog: ${recipeCount}`)
console.log(`Recipe ingredients in catalog: ${relationCount}`)
