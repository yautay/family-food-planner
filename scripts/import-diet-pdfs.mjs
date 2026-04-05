import Database from 'better-sqlite3'
import { execFileSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const tmpDir = path.join(projectRoot, 'tmp')
const databasePath = path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')

const dayHeaderRegex = /^(Poniedzialek|Wtorek|Sroda|Czwartek|Piatek|Sobota|Niedziela|Poniedzialek|Sroda)$/i

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

function looksLikeIngredientLine(line) {
  const quantityPattern = /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*x\s*([^()]+?)\s*\(([0-9]+(?:[.,][0-9]+)?)\s*g\)$/i
  const gramsOnlyPattern = /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*g$/i

  return quantityPattern.test(line) || gramsOnlyPattern.test(line)
}

function parseIngredientLine(line) {
  const quantityPattern = /^(.*?),\s*([0-9]+(?:[.,][0-9]+)?)\s*x\s*([^()]+?)\s*\(([0-9]+(?:[.,][0-9]+)?)\s*g\)$/i
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

      if (/^.+,\s*[0-9]+(?:[.,][0-9]+)?\s*x\s*[^()]+$/i.test(current) && /^\([0-9]+(?:[.,][0-9]+)?\s*g\)$/i.test(next)) {
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
    })
  }

  recipeCatalog.get(normalizedName).sourceFiles.add(sourceFile)
  return normalizedName
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
    if (!ingredient || !currentRecipeKey) {
      continue
    }

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

function tableExists(db, tableName) {
  const row = db
    .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name = ?")
    .get(tableName)

  return Boolean(row)
}

const pdfFiles = readdirSync(tmpDir)
  .filter((name) => name.toLowerCase().endsWith('.pdf'))
  .sort((left, right) => left.localeCompare(right))

if (pdfFiles.length === 0) {
  console.error('No PDF files found in tmp/.')
  process.exit(1)
}

for (const fileName of pdfFiles) {
  const filePath = path.join(tmpDir, fileName)
  parsePdf(filePath, fileName)
}

const db = new Database(databasePath)
db.pragma('foreign_keys = ON')

if (!tableExists(db, 'products') || !tableExists(db, 'recipes') || !tableExists(db, 'recipe_ingredients')) {
  console.error('Missing catalog tables. Run npm run db:migrate first.')
  db.close()
  process.exit(1)
}

const insertUnit = db.prepare('INSERT OR IGNORE INTO units(name) VALUES (?)')
const selectUnits = db.prepare('SELECT id, name FROM units')

const insertProduct = db.prepare(`
  INSERT INTO products(name, normalized_name, default_unit_id)
  VALUES (@name, @normalizedName, @defaultUnitId)
  ON CONFLICT(normalized_name)
  DO UPDATE SET
    name = excluded.name,
    default_unit_id = COALESCE(products.default_unit_id, excluded.default_unit_id),
    updated_at = CURRENT_TIMESTAMP
`)

const selectProducts = db.prepare('SELECT id, normalized_name FROM products')

const insertRecipe = db.prepare(`
  INSERT INTO recipes(name, normalized_name, source_file)
  VALUES (@name, @normalizedName, @sourceFile)
  ON CONFLICT(normalized_name)
  DO UPDATE SET
    name = excluded.name,
    source_file = excluded.source_file,
    updated_at = CURRENT_TIMESTAMP
`)

const insertSystemRecipe = db.prepare(`
  INSERT INTO recipes(name, normalized_name, source_file, owner_user_id, is_system, is_editable)
  VALUES (@name, @normalizedName, @sourceFile, NULL, 1, 0)
  ON CONFLICT(normalized_name)
  DO UPDATE SET
    name = excluded.name,
    source_file = excluded.source_file,
    owner_user_id = NULL,
    is_system = 1,
    is_editable = 0,
    updated_at = CURRENT_TIMESTAMP
`)

const selectRecipes = db.prepare('SELECT id, normalized_name FROM recipes')

const insertRecipeIngredient = db.prepare(`
  INSERT INTO recipe_ingredients(recipe_id, product_id, quantity, unit_id, grams, note, source_file)
  VALUES (@recipeId, @productId, @quantity, @unitId, @grams, @note, @sourceFile)
`)

const persistData = db.transaction(() => {
  const recipeTableInfo = db.prepare('PRAGMA table_info(recipes)').all()
  const hasRecipeAclColumns = recipeTableInfo.some((column) => column.name === 'is_system')

  if (hasRecipeAclColumns) {
    db.exec(`
      DELETE FROM recipe_ingredients
      WHERE recipe_id IN (SELECT id FROM recipes WHERE is_system = 1)
    `)
    db.exec('DELETE FROM recipes WHERE is_system = 1')
  } else {
    db.exec('DELETE FROM recipe_ingredients')
    db.exec('DELETE FROM recipes')
  }

  const allUnitKeys = new Set()
  for (const product of productCatalog.values()) {
    for (const unitKey of product.units.keys()) {
      allUnitKeys.add(unitKey)
    }
  }
  for (const relation of relationRows) {
    if (relation.unitName) {
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
    if (unitName) {
      insertUnit.run(unitName)
    }
  }

  const units = selectUnits.all()
  const unitIdByKey = new Map(units.map((row) => [normalizeKey(row.name), row.id]))

  for (const product of productCatalog.values()) {
    const defaultUnitKey = pickDefaultUnit(product)
    insertProduct.run({
      name: product.name,
      normalizedName: product.normalizedName,
      defaultUnitId: defaultUnitKey ? (unitIdByKey.get(defaultUnitKey) ?? null) : null,
    })
  }

  for (const recipe of recipeCatalog.values()) {
    const payload = {
      name: recipe.name,
      normalizedName: recipe.normalizedName,
      sourceFile: Array.from(recipe.sourceFiles).sort((left, right) => left.localeCompare(right)).join(', '),
    }

    if (hasRecipeAclColumns) {
      insertSystemRecipe.run(payload)
    } else {
      insertRecipe.run(payload)
    }
  }

  const productIdByKey = new Map(
    selectProducts.all().map((row) => [row.normalized_name, row.id]),
  )
  const recipeIdByKey = new Map(selectRecipes.all().map((row) => [row.normalized_name, row.id]))

  const relationDedup = new Set()

  for (const relation of relationRows) {
    const recipeId = recipeIdByKey.get(relation.recipeKey)
    const productId = productIdByKey.get(relation.productKey)
    const unitId = relation.unitName ? (unitIdByKey.get(normalizeKey(relation.unitName)) ?? null) : null

    if (!recipeId || !productId) {
      continue
    }

    const dedupKey = [
      recipeId,
      productId,
      relation.quantity ?? '',
      unitId ?? '',
      relation.grams ?? '',
    ].join('|')

    if (relationDedup.has(dedupKey)) {
      continue
    }
    relationDedup.add(dedupKey)

    insertRecipeIngredient.run({
      recipeId,
      productId,
      quantity: relation.quantity,
      unitId,
      grams: relation.grams,
      note: '',
      sourceFile: relation.sourceFile,
    })
  }
})

persistData()

const productCount = db.prepare('SELECT COUNT(*) AS count FROM products').get().count
const recipeCount = db.prepare('SELECT COUNT(*) AS count FROM recipes').get().count
const relationCount = db.prepare('SELECT COUNT(*) AS count FROM recipe_ingredients').get().count

db.close()

console.log(`Imported files: ${pdfFiles.length}`)
console.log(`Products in catalog: ${productCount}`)
console.log(`Recipes in catalog: ${recipeCount}`)
console.log(`Recipe ingredients in catalog: ${relationCount}`)
