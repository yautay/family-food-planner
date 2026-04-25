import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import Database from 'better-sqlite3'

const args = process.argv.slice(2)
const options = {
  databasePath: process.env.DATABASE_PATH || 'database.db',
  delayMs: 1400,
  limit: Number.POSITIVE_INFINITY,
  minScore: 0.82,
  reportPath: 'db/nutrition-rematch-report.json',
}

for (const arg of args) {
  if (arg.startsWith('--database=')) {
    options.databasePath = arg.replace('--database=', '')
  }

  if (arg.startsWith('--delay-ms=')) {
    const parsed = Number(arg.replace('--delay-ms=', ''))
    if (Number.isFinite(parsed) && parsed >= 0) {
      options.delayMs = parsed
    }
  }

  if (arg.startsWith('--limit=')) {
    const parsed = Number(arg.replace('--limit=', ''))
    if (Number.isFinite(parsed) && parsed > 0) {
      options.limit = parsed
    }
  }

  if (arg.startsWith('--min-score=')) {
    const parsed = Number(arg.replace('--min-score=', ''))
    if (Number.isFinite(parsed) && parsed > 0) {
      options.minScore = parsed
    }
  }

  if (arg.startsWith('--report=')) {
    options.reportPath = arg.replace('--report=', '')
  }
}

const AGGRESSIVE_SOURCE_KEYWORDS = [
  'chips',
  'smoothie',
  'skyr',
  'jogurt',
  'piwo',
  'beer',
  'lunch box',
  'muesli',
  'musli',
  'pasta warzywna',
  'pad thai',
  'sauce',
  'sos',
  'kawa rozpuszczalna',
  'napoj',
  'drink',
]

const BASE_INGREDIENT_KEYWORDS = [
  'cebula',
  'czosnek',
  'pomidor',
  'pietruszka',
  'seler',
  'burak',
  'por',
  'cukinia',
  'pieczarki',
  'brokul',
  'rukola',
  'szpinak',
  'cytryna',
  'limonka',
  'jezyny',
  'maliny',
  'bob',
  'awokado',
  'ogorek',
  'papryka',
  'marchew',
  'ziemniak',
  'pomarancza',
  'jablko',
  'orzechy',
  'migdaly',
  'pestki',
  'kakao',
  'kawa espresso',
]

const SEARCH_OVERRIDES = {
  bob: ['bób', 'bob'],
  jezyny: ['jeżyny', 'blackberry'],
  limonka: ['limonka', 'lime'],
  cytryna: ['cytryna', 'lemon'],
  'seler korzen': ['seler korzeń', 'celeriac'],
  'pietruszka korzen': ['pietruszka korzeń', 'parsley root'],
  'kawa espresso napar bez cukru': ['espresso', 'kawa espresso'],
  'kakao proszek bez dodatku cukru': ['kakao', 'cocoa powder'],
}

function normalizeKey(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

function sanitizeSearchTerm(name) {
  return String(name ?? '')
    .replace(/\([^)]*\)/g, ' ')
    .replace(/[0-9]+(?:[.,][0-9]+)?\s*%/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function toNullableNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function deriveNutrition(nutriments = {}) {
  const calories =
    toNullableNumber(nutriments['energy-kcal_100g']) ??
    toNullableNumber(nutriments['energy-kcal_value']) ??
    (() => {
      const kj = toNullableNumber(nutriments.energy_100g)
      return kj === null ? null : Number((kj / 4.184).toFixed(2))
    })()

  return {
    calories,
    carbohydrates: toNullableNumber(nutriments.carbohydrates_100g),
    sugars: toNullableNumber(nutriments.sugars_100g),
    fat: toNullableNumber(nutriments.fat_100g),
    protein: toNullableNumber(nutriments.proteins_100g),
    fiber: toNullableNumber(nutriments.fiber_100g),
  }
}

function countDefinedCoreMacros(nutrition) {
  return [nutrition.calories, nutrition.carbohydrates, nutrition.fat, nutrition.protein].filter(
    (value) => value !== null,
  ).length
}

function tokenF1(productName, candidateName) {
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
  return recall > 0 && precision > 0 ? (2 * recall * precision) / (recall + precision) : 0
}

function exactnessScore(productName, candidateName) {
  const normalizedProduct = normalizeKey(productName)
  const normalizedCandidate = normalizeKey(candidateName)

  if (!normalizedProduct || !normalizedCandidate) {
    return 0
  }

  if (normalizedProduct === normalizedCandidate) {
    return 1
  }

  if (normalizedCandidate.includes(normalizedProduct)) {
    return 0.8
  }

  if (normalizedProduct.includes(normalizedCandidate)) {
    return 0.6
  }

  return 0
}

function hasAnyKeyword(value, keywords) {
  const normalized = normalizeKey(value)
  return keywords.some((keyword) => normalized.includes(normalizeKey(keyword)))
}

function energyMismatch(nutrition) {
  if (nutrition.calories === null || nutrition.calories <= 0) {
    return 0
  }

  const estimatedCalories =
    (nutrition.carbohydrates ?? 0) * 4 +
    (nutrition.protein ?? 0) * 4 +
    (nutrition.fat ?? 0) * 9 +
    (nutrition.fiber ?? 0) * 2

  return Math.abs(nutrition.calories - estimatedCalories) / Math.max(1, nutrition.calories)
}

function hasNutritionSanityProblems(nutrition) {
  if (
    [
      nutrition.calories,
      nutrition.carbohydrates,
      nutrition.sugars,
      nutrition.fat,
      nutrition.protein,
      nutrition.fiber,
    ].some((value) => value !== null && value < 0)
  ) {
    return true
  }

  if (
    nutrition.sugars !== null &&
    nutrition.carbohydrates !== null &&
    nutrition.sugars > nutrition.carbohydrates + 0.01
  ) {
    return true
  }

  return energyMismatch(nutrition) > 0.75
}

function isLikelyBaseIngredient(name) {
  return hasAnyKeyword(name, BASE_INGREDIENT_KEYWORDS)
}

function classifyForReview(product) {
  const source = String(product.nutrition_source ?? '')
  const sourceName = source.split(':').slice(2).join(':')
  const directSource =
    source.startsWith('openfoodfacts:') && !source.startsWith('openfoodfacts:tag-average:')
  const reasons = []

  if (source.startsWith('openfoodfacts:tag-average:')) {
    reasons.push('tag-average')
  }

  if (directSource) {
    const nameScore = tokenF1(product.name, sourceName)
    if (nameScore < 0.35) {
      reasons.push('low-source-name-match')
    }

    if (
      isLikelyBaseIngredient(product.name) &&
      hasAnyKeyword(sourceName, AGGRESSIVE_SOURCE_KEYWORDS)
    ) {
      reasons.push('processed-source-mismatch')
    }
  }

  const productNutrition = {
    calories: product.calories_per_100g,
    carbohydrates: product.carbohydrates_per_100g,
    sugars: product.sugars_per_100g,
    fat: product.fat_per_100g,
    protein: product.protein_per_100g,
    fiber: product.fiber_per_100g,
  }

  if (energyMismatch(productNutrition) > 0.5) {
    reasons.push('existing-energy-mismatch')
  }

  if (
    product.fiber_per_100g !== null &&
    product.carbohydrates_per_100g !== null &&
    product.fiber_per_100g > product.carbohydrates_per_100g + 0.01
  ) {
    reasons.push('fiber-over-carbs')
  }

  return reasons
}

function buildSearchTerms(productName) {
  const normalizedName = normalizeKey(productName)
  const sanitized = sanitizeSearchTerm(productName)
  const sanitizedNormalized = normalizeKey(sanitized)
  const overrideTerms =
    SEARCH_OVERRIDES[normalizedName] ?? SEARCH_OVERRIDES[sanitizedNormalized] ?? []
  const tokens = sanitizedNormalized.split(' ').filter(Boolean)

  return Array.from(
    new Set(
      [
        productName,
        sanitized,
        ...overrideTerms,
        tokens.slice(0, 2).join(' '),
        tokens.slice(0, 1).join(' '),
      ].filter((value) => value && value.length > 1),
    ),
  )
}

async function fetchSearchResults(searchTerm) {
  const url = new URL('https://world.openfoodfacts.org/cgi/search.pl')
  url.searchParams.set('search_terms', searchTerm)
  url.searchParams.set('search_simple', '1')
  url.searchParams.set('action', 'process')
  url.searchParams.set('json', '1')
  url.searchParams.set('page_size', '25')
  url.searchParams.set('fields', 'code,product_name,nutriments')

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'family-food-planner/0.1 (nutrition rematch script)',
      },
    })

    if (response.status === 429) {
      await sleep(options.delayMs * (attempt + 1))
      continue
    }

    if (!response.ok) {
      return []
    }

    const payload = await response.json()
    return Array.isArray(payload?.products) ? payload.products : []
  }

  return []
}

function scoreCandidate(product, candidateName, nutrition) {
  const nameScore = tokenF1(product.name, candidateName)
  const exactScore = exactnessScore(product.name, candidateName)
  const macroScore = countDefinedCoreMacros(nutrition) / 4
  let score = nameScore * 0.55 + exactScore * 0.3 + macroScore * 0.15

  const productIsBaseIngredient = isLikelyBaseIngredient(product.name)
  const candidateLooksProcessed = hasAnyKeyword(candidateName, AGGRESSIVE_SOURCE_KEYWORDS)
  if (productIsBaseIngredient && candidateLooksProcessed) {
    score -= 0.45
  }

  if (hasNutritionSanityProblems(nutrition)) {
    score -= 0.35
  }

  const mismatch = energyMismatch(nutrition)
  if (mismatch > 0.45) {
    score -= 0.15
  }

  return {
    score,
    nameScore,
    exactScore,
    macroScore,
    processedMismatch: productIsBaseIngredient && candidateLooksProcessed,
    mismatch,
  }
}

async function fetchBestCandidate(product) {
  const searchTerms = buildSearchTerms(product.name)
  const candidatesByCode = new Map()

  for (const searchTerm of searchTerms) {
    const candidates = await fetchSearchResults(searchTerm)
    for (const candidate of candidates) {
      const candidateName = candidate?.product_name
      const code = candidate?.code
      if (!code || typeof candidateName !== 'string' || candidateName.trim().length === 0) {
        continue
      }

      if (!candidatesByCode.has(code)) {
        candidatesByCode.set(code, candidate)
      }
    }

    if (options.delayMs > 0) {
      await sleep(options.delayMs)
    }
  }

  let best = null
  for (const candidate of candidatesByCode.values()) {
    const nutrition = deriveNutrition(candidate?.nutriments)
    if (countDefinedCoreMacros(nutrition) < 3) {
      continue
    }

    const details = scoreCandidate(product, candidate.product_name, nutrition)
    if (details.processedMismatch) {
      continue
    }

    if (hasNutritionSanityProblems(nutrition)) {
      continue
    }

    const current = {
      score: details.score,
      candidateName: candidate.product_name,
      sourceCode: candidate.code,
      nutrition,
      details,
    }

    if (!best || current.score > best.score) {
      best = current
    }
  }

  if (!best || best.score < options.minScore) {
    return null
  }

  return best
}

function shouldApplyChange(product, reviewReasons, candidate) {
  const currentSourceName = String(product.nutrition_source ?? '')
    .split(':')
    .slice(2)
    .join(':')
  const currentNameScore = currentSourceName ? tokenF1(product.name, currentSourceName) : 0
  const candidateNameScore = candidate.details.nameScore
  const currentIsTagAverage = String(product.nutrition_source ?? '').startsWith(
    'openfoodfacts:tag-average:',
  )
  const sourceChanged = currentSourceName !== candidate.candidateName

  if (!sourceChanged) {
    return false
  }

  if (currentIsTagAverage) {
    return candidate.score >= Math.max(options.minScore, 0.9) && candidateNameScore >= 0.5
  }

  if (reviewReasons.includes('processed-source-mismatch')) {
    return candidate.score >= options.minScore && candidateNameScore >= 0.5
  }

  if (reviewReasons.includes('low-source-name-match')) {
    return candidate.score >= options.minScore && candidateNameScore >= currentNameScore + 0.25
  }

  return candidate.score >= 0.9 && candidateNameScore >= Math.max(0.5, currentNameScore + 0.2)
}

function selectFallbackAverage(product, reviewReasons, tagsByProductId, tagAverages) {
  if (
    !reviewReasons.some((reason) =>
      ['processed-source-mismatch', 'low-source-name-match', 'existing-energy-mismatch'].includes(
        reason,
      ),
    )
  ) {
    return null
  }

  const productTags = tagsByProductId.get(product.id) ?? []
  let best = null

  for (const tagName of productTags) {
    const averageSet = tagAverages.get(tagName)
    if (!averageSet || hasNutritionSanityProblems(averageSet.nutrition)) {
      continue
    }

    if (!best || averageSet.samples > best.samples) {
      best = {
        tagName,
        samples: averageSet.samples,
        nutrition: averageSet.nutrition,
      }
    }
  }

  return best
}

function roundNumber(value) {
  return value === null ? null : Number(value.toFixed(2))
}

function average(values) {
  if (values.length === 0) {
    return null
  }

  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function isStableAverageSource(product) {
  const source = String(product.nutrition_source ?? '')
  if (!source.startsWith('openfoodfacts:') || source.startsWith('openfoodfacts:tag-average:')) {
    return false
  }

  if (classifyForReview(product).length > 0) {
    return false
  }

  const sourceName = source.split(':').slice(2).join(':')
  return tokenF1(product.name, sourceName) >= 0.6
}

const database = new Database(options.databasePath)
database.pragma('foreign_keys = ON')

const productRows = database
  .prepare(
    `
    SELECT
      id,
      name,
      calories_per_100g,
      carbohydrates_per_100g,
      sugars_per_100g,
      fat_per_100g,
      protein_per_100g,
      fiber_per_100g,
      nutrition_source,
      nutrition_updated_at
    FROM products
    ORDER BY id ASC
    `,
  )
  .all()

const stableSourceProducts = productRows.filter(isStableAverageSource)

const tagRows = database
  .prepare(
    `
    SELECT pt.product_id, t.name AS tag_name
    FROM product_tags pt
    INNER JOIN tags t ON t.id = pt.tag_id
    ORDER BY pt.product_id ASC, t.name ASC
    `,
  )
  .all()

const tagsByProductId = new Map()
for (const row of tagRows) {
  if (!tagsByProductId.has(row.product_id)) {
    tagsByProductId.set(row.product_id, [])
  }

  tagsByProductId.get(row.product_id).push(row.tag_name)
}

const stableProductsById = new Map(stableSourceProducts.map((product) => [product.id, product]))
const tagAccumulator = new Map()
for (const row of tagRows) {
  const product = stableProductsById.get(row.product_id)
  if (!product) {
    continue
  }

  if (!tagAccumulator.has(row.tag_name)) {
    tagAccumulator.set(row.tag_name, {
      samples: 0,
      calories: [],
      carbohydrates: [],
      sugars: [],
      fat: [],
      protein: [],
      fiber: [],
    })
  }

  const bucket = tagAccumulator.get(row.tag_name)
  bucket.samples += 1
  bucket.calories.push(product.calories_per_100g)
  bucket.carbohydrates.push(product.carbohydrates_per_100g)
  if (product.sugars_per_100g !== null) {
    bucket.sugars.push(product.sugars_per_100g)
  }
  bucket.fat.push(product.fat_per_100g)
  bucket.protein.push(product.protein_per_100g)
  if (product.fiber_per_100g !== null) {
    bucket.fiber.push(product.fiber_per_100g)
  }
}

const tagAverages = new Map()
for (const [tagName, bucket] of tagAccumulator.entries()) {
  if (bucket.samples < 2) {
    continue
  }

  tagAverages.set(tagName, {
    samples: bucket.samples,
    nutrition: {
      calories: average(bucket.calories),
      carbohydrates: average(bucket.carbohydrates),
      sugars: average(bucket.sugars),
      fat: average(bucket.fat),
      protein: average(bucket.protein),
      fiber: average(bucket.fiber),
    },
  })
}

const targets = []
for (const product of productRows) {
  const reasons = classifyForReview(product)
  if (reasons.length > 0) {
    targets.push({ product, reasons })
  }
}

const limitedTargets = Number.isFinite(options.limit) ? targets.slice(0, options.limit) : targets

const updateStatement = database.prepare(
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
    nutrition_updated_at = ?,
    updated_at = ?
  WHERE id = ?
  `,
)

const report = {
  generatedAt: new Date().toISOString(),
  options,
  reviewed: limitedTargets.length,
  updated: [],
  skipped: [],
}

const applyChange = database.transaction((product, candidate) => {
  const now = new Date().toISOString()
  const source = candidate.sourceCode.startsWith('tag-average:')
    ? `openfoodfacts:${candidate.sourceCode}`
    : `openfoodfacts:${candidate.sourceCode}:${candidate.candidateName}`

  updateStatement.run(
    roundNumber(candidate.nutrition.calories),
    roundNumber(candidate.nutrition.carbohydrates),
    roundNumber(candidate.nutrition.sugars),
    roundNumber(candidate.nutrition.fat),
    roundNumber(candidate.nutrition.protein),
    roundNumber(candidate.nutrition.fiber),
    source,
    now,
    now,
    product.id,
  )
})

console.log(`Targets queued: ${limitedTargets.length}`)

for (const entry of limitedTargets) {
  const { product, reasons } = entry

  try {
    const candidate = await fetchBestCandidate(product)
    if (!candidate) {
      const fallbackAverage = selectFallbackAverage(product, reasons, tagsByProductId, tagAverages)
      if (
        fallbackAverage &&
        product.nutrition_source !== `openfoodfacts:tag-average:${fallbackAverage.tagName}`
      ) {
        applyChange(product, {
          sourceCode: `tag-average:${fallbackAverage.tagName}`,
          candidateName: fallbackAverage.tagName,
          nutrition: fallbackAverage.nutrition,
        })
        report.updated.push({
          id: product.id,
          name: product.name,
          reasons,
          before: {
            calories: product.calories_per_100g,
            carbohydrates: product.carbohydrates_per_100g,
            sugars: product.sugars_per_100g,
            fat: product.fat_per_100g,
            protein: product.protein_per_100g,
            fiber: product.fiber_per_100g,
            source: product.nutrition_source,
          },
          after: {
            calories: roundNumber(fallbackAverage.nutrition.calories),
            carbohydrates: roundNumber(fallbackAverage.nutrition.carbohydrates),
            sugars: roundNumber(fallbackAverage.nutrition.sugars),
            fat: roundNumber(fallbackAverage.nutrition.fat),
            protein: roundNumber(fallbackAverage.nutrition.protein),
            fiber: roundNumber(fallbackAverage.nutrition.fiber),
            source: `openfoodfacts:tag-average:${fallbackAverage.tagName}`,
          },
          score: null,
          nameScore: null,
          exactScore: null,
          fallbackSamples: fallbackAverage.samples,
        })
        console.log(`OK    ${product.name} -> tag-average:${fallbackAverage.tagName} (fallback)`)
        continue
      }

      report.skipped.push({
        id: product.id,
        name: product.name,
        reasons,
        status: 'no-safe-match',
      })
      console.log(`SKIP  ${product.name} -> no safe match`)
      continue
    }

    if (!shouldApplyChange(product, reasons, candidate)) {
      report.skipped.push({
        id: product.id,
        name: product.name,
        reasons,
        status: 'confidence-too-low',
        candidate: {
          source: `openfoodfacts:${candidate.sourceCode}:${candidate.candidateName}`,
          score: Number(candidate.score.toFixed(3)),
          nameScore: Number(candidate.details.nameScore.toFixed(3)),
        },
      })
      console.log(
        `SKIP  ${product.name} -> ${candidate.candidateName} (score: ${candidate.score.toFixed(2)})`,
      )
      continue
    }

    applyChange(product, candidate)
    report.updated.push({
      id: product.id,
      name: product.name,
      reasons,
      before: {
        calories: product.calories_per_100g,
        carbohydrates: product.carbohydrates_per_100g,
        sugars: product.sugars_per_100g,
        fat: product.fat_per_100g,
        protein: product.protein_per_100g,
        fiber: product.fiber_per_100g,
        source: product.nutrition_source,
      },
      after: {
        calories: roundNumber(candidate.nutrition.calories),
        carbohydrates: roundNumber(candidate.nutrition.carbohydrates),
        sugars: roundNumber(candidate.nutrition.sugars),
        fat: roundNumber(candidate.nutrition.fat),
        protein: roundNumber(candidate.nutrition.protein),
        fiber: roundNumber(candidate.nutrition.fiber),
        source: `openfoodfacts:${candidate.sourceCode}:${candidate.candidateName}`,
      },
      score: Number(candidate.score.toFixed(3)),
      nameScore: Number(candidate.details.nameScore.toFixed(3)),
      exactScore: Number(candidate.details.exactScore.toFixed(3)),
    })
    console.log(
      `OK    ${product.name} -> ${candidate.candidateName} (score: ${candidate.score.toFixed(2)})`,
    )
  } catch (error) {
    report.skipped.push({
      id: product.id,
      name: product.name,
      reasons,
      status: 'error',
      error: error.message,
    })
    console.log(`ERR   ${product.name}: ${error.message}`)
  }
}

const reportDirectory = path.dirname(options.reportPath)
mkdirSync(reportDirectory, { recursive: true })
writeFileSync(options.reportPath, JSON.stringify(report, null, 2))

console.log('---')
console.log(`Updated: ${report.updated.length}`)
console.log(`Skipped: ${report.skipped.length}`)
console.log(`Report: ${options.reportPath}`)

database.close()
