import Database from 'better-sqlite3'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const databasePath = path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')

const args = process.argv.slice(2)
const options = {
  limit: Number.POSITIVE_INFINITY,
  overwrite: false,
  delayMs: 250,
  minScore: 0.2,
  forceFillMissing: false,
}

for (const arg of args) {
  if (arg.startsWith('--limit=')) {
    const parsed = Number(arg.replace('--limit=', ''))
    if (Number.isFinite(parsed) && parsed > 0) {
      options.limit = parsed
    }
  }

  if (arg === '--overwrite') {
    options.overwrite = true
  }

  if (arg.startsWith('--delay-ms=')) {
    const parsed = Number(arg.replace('--delay-ms=', ''))
    if (Number.isFinite(parsed) && parsed >= 0) {
      options.delayMs = parsed
    }
  }

  if (arg.startsWith('--min-score=')) {
    const parsed = Number(arg.replace('--min-score=', ''))
    if (Number.isFinite(parsed) && parsed >= 0) {
      options.minScore = parsed
    }
  }

  if (arg === '--force-fill-missing') {
    options.forceFillMissing = true
  }
}

function normalizeKey(value) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

function toNullableNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function sanitizeSearchTerm(name) {
  return name
    .replace(/\([^)]*\)/g, ' ')
    .replace(/[0-9]+(?:[.,][0-9]+)?\s*%/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function getCandidatesFromNutriments(nutriments = {}) {
  const calories =
    toNullableNumber(nutriments['energy-kcal_100g']) ??
    toNullableNumber(nutriments['energy-kcal_value']) ??
    (() => {
      const kj = toNullableNumber(nutriments.energy_100g)
      return kj === null ? null : Number((kj / 4.184).toFixed(2))
    })()

  const carbohydrates = toNullableNumber(nutriments.carbohydrates_100g)
  const sugars = toNullableNumber(nutriments.sugars_100g)
  const fat = toNullableNumber(nutriments.fat_100g)
  const protein = toNullableNumber(nutriments.proteins_100g)
  const fiber = toNullableNumber(nutriments.fiber_100g)

  return {
    calories,
    carbohydrates,
    sugars,
    fat,
    protein,
    fiber,
  }
}

function countDefinedCoreMacros(nutrition) {
  const core = [nutrition.calories, nutrition.carbohydrates, nutrition.fat, nutrition.protein]
  return core.filter((value) => value !== null).length
}

function scoreMatch(productName, candidateName, nutrition) {
  const sourceTokens = new Set(normalizeKey(productName).split(' ').filter(Boolean))
  const candidateTokens = new Set(normalizeKey(candidateName).split(' ').filter(Boolean))

  let tokenOverlap = 0
  for (const token of sourceTokens) {
    if (candidateTokens.has(token)) {
      tokenOverlap += 1
    }
  }

  const recall = sourceTokens.size > 0 ? tokenOverlap / sourceTokens.size : 0
  const precision = candidateTokens.size > 0 ? tokenOverlap / candidateTokens.size : 0
  const overlapF1 =
    recall > 0 && precision > 0 ? (2 * recall * precision) / (recall + precision) : 0
  const macroScore = countDefinedCoreMacros(nutrition) / 4

  return overlapF1 * 0.75 + macroScore * 0.25
}

async function fetchBestNutritionForProduct(productName) {
  const normalizedName = normalizeKey(productName)
  const normalizedTokens = normalizedName.split(' ').filter(Boolean)

  const searchTerms = Array.from(
    new Set(
      [
        productName,
        sanitizeSearchTerm(productName),
        normalizedTokens.slice(0, 1).join(' '),
        normalizedTokens.slice(0, 2).join(' '),
      ].filter((value) => value.length > 1),
    ),
  )

  let best = null

  for (const searchTerm of searchTerms) {
    const url = new URL('https://world.openfoodfacts.org/cgi/search.pl')
    url.searchParams.set('search_terms', searchTerm)
    url.searchParams.set('search_simple', '1')
    url.searchParams.set('action', 'process')
    url.searchParams.set('json', '1')
    url.searchParams.set('page_size', '25')
    url.searchParams.set('fields', 'code,product_name,nutriments')

    const response = await fetch(url, {
      headers: {
        'User-Agent': 'family-food-planner/0.1 (nutrition enrichment script)',
      },
    })

    if (!response.ok) {
      continue
    }

    const payload = await response.json()
    const products = Array.isArray(payload?.products) ? payload.products : []

    for (const candidate of products) {
      const candidateName = candidate?.product_name
      if (typeof candidateName !== 'string' || candidateName.trim().length === 0) {
        continue
      }

      const nutrition = getCandidatesFromNutriments(candidate?.nutriments)
      if (countDefinedCoreMacros(nutrition) < 1) {
        continue
      }

      const score = scoreMatch(productName, candidateName, nutrition)

      if (!best || score > best.score) {
        best = {
          score,
          candidateName,
          nutrition,
          sourceCode: candidate?.code ?? null,
        }
      }
    }
  }

  if (!best || best.score < options.minScore) {
    return null
  }

  return best
}

const db = new Database(databasePath)
db.pragma('foreign_keys = ON')

const baseQuery = options.overwrite
  ? `
    SELECT id, name
    FROM products
    ORDER BY name COLLATE NOCASE ASC
  `
  : `
    SELECT id, name
    FROM products
    WHERE calories_per_100g IS NULL
      OR carbohydrates_per_100g IS NULL
      OR fat_per_100g IS NULL
      OR protein_per_100g IS NULL
    ORDER BY name COLLATE NOCASE ASC
  `

const products = db.prepare(baseQuery).all().slice(0, options.limit)

const updateProduct = db.prepare(
  `
  UPDATE products
  SET
    calories_per_100g = ?,
    carbohydrates_per_100g = ?,
    sugars_per_100g = ?,
    fat_per_100g = ?,
    protein_per_100g = ?,
    fiber_per_100g = ?,
    nutrition_source = ?,
    nutrition_updated_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
  WHERE id = ?
  `,
)

let updated = 0
let skipped = 0
let failed = 0

console.log(`Products queued: ${products.length}`)

for (const product of products) {
  try {
    const best = await fetchBestNutritionForProduct(product.name)

    if (!best) {
      skipped += 1
      console.log(`SKIP  ${product.name}`)
      if (options.delayMs > 0) {
        await sleep(options.delayMs)
      }
      continue
    }

    const source = best.sourceCode
      ? `openfoodfacts:${best.sourceCode}:${best.candidateName}`
      : `openfoodfacts:${best.candidateName}`

    const calories =
      best.nutrition.calories ?? (options.forceFillMissing ? 0 : best.nutrition.calories)
    const carbohydrates =
      best.nutrition.carbohydrates ?? (options.forceFillMissing ? 0 : best.nutrition.carbohydrates)
    const sugars = best.nutrition.sugars ?? (options.forceFillMissing ? 0 : best.nutrition.sugars)
    const fat = best.nutrition.fat ?? (options.forceFillMissing ? 0 : best.nutrition.fat)
    const protein =
      best.nutrition.protein ?? (options.forceFillMissing ? 0 : best.nutrition.protein)
    const fiber = best.nutrition.fiber ?? (options.forceFillMissing ? 0 : best.nutrition.fiber)

    updateProduct.run(calories, carbohydrates, sugars, fat, protein, fiber, source, product.id)

    updated += 1
    console.log(`OK    ${product.name} -> ${best.candidateName} (score: ${best.score.toFixed(2)})`)
  } catch (error) {
    failed += 1
    console.log(`ERR   ${product.name}: ${error.message}`)
  }

  if (options.delayMs > 0) {
    await sleep(options.delayMs)
  }
}

const coverage = db
  .prepare(
    `
    SELECT
      COUNT(*) AS total,
      SUM(
        CASE
          WHEN calories_per_100g IS NOT NULL
               AND carbohydrates_per_100g IS NOT NULL
               AND fat_per_100g IS NOT NULL
               AND protein_per_100g IS NOT NULL
            THEN 1
          ELSE 0
        END
      ) AS complete
    FROM products
    `,
  )
  .get()

db.close()

console.log('---')
console.log(`Updated: ${updated}`)
console.log(`Skipped: ${skipped}`)
console.log(`Failed: ${failed}`)
console.log(`Coverage: ${coverage.complete}/${coverage.total}`)
