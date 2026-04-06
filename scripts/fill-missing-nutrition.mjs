import Database from 'better-sqlite3'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const databasePath = path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')

function round2(value) {
  return Number(value.toFixed(2))
}

const db = new Database(databasePath)
db.pragma('foreign_keys = ON')

const tagAverages = db
  .prepare(
    `
    SELECT
      pt.tag_id,
      t.name AS tag_name,
      COUNT(*) AS samples,
      AVG(p.calories_per_100g) AS calories,
      AVG(p.carbohydrates_per_100g) AS carbohydrates,
      AVG(p.sugars_per_100g) AS sugars,
      AVG(p.fat_per_100g) AS fat,
      AVG(p.protein_per_100g) AS protein,
      AVG(p.fiber_per_100g) AS fiber
    FROM products p
    INNER JOIN product_tags pt ON pt.product_id = p.id
    INNER JOIN tags t ON t.id = pt.tag_id
    WHERE p.nutrition_source LIKE 'openfoodfacts:%'
      AND p.calories_per_100g IS NOT NULL
      AND p.carbohydrates_per_100g IS NOT NULL
      AND p.fat_per_100g IS NOT NULL
      AND p.protein_per_100g IS NOT NULL
    GROUP BY pt.tag_id
    HAVING COUNT(*) >= 2
    `,
  )
  .all()

const globalAverage = db
  .prepare(
    `
    SELECT
      AVG(calories_per_100g) AS calories,
      AVG(carbohydrates_per_100g) AS carbohydrates,
      AVG(sugars_per_100g) AS sugars,
      AVG(fat_per_100g) AS fat,
      AVG(protein_per_100g) AS protein,
      AVG(fiber_per_100g) AS fiber
    FROM products
    WHERE nutrition_source LIKE 'openfoodfacts:%'
      AND calories_per_100g IS NOT NULL
      AND carbohydrates_per_100g IS NOT NULL
      AND fat_per_100g IS NOT NULL
      AND protein_per_100g IS NOT NULL
    `,
  )
  .get()

const missingProducts = db
  .prepare(
    `
    SELECT
      p.id,
      p.name,
      p.calories_per_100g,
      p.carbohydrates_per_100g,
      p.sugars_per_100g,
      p.fat_per_100g,
      p.protein_per_100g,
      p.fiber_per_100g,
      GROUP_CONCAT(pt.tag_id) AS tag_ids
    FROM products p
    LEFT JOIN product_tags pt ON pt.product_id = p.id
    WHERE p.calories_per_100g IS NULL
      OR p.carbohydrates_per_100g IS NULL
      OR p.fat_per_100g IS NULL
      OR p.protein_per_100g IS NULL
    GROUP BY p.id
    ORDER BY p.name COLLATE NOCASE ASC
    `,
  )
  .all()

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

for (const product of missingProducts) {
  const tagIds = product.tag_ids
    ? product.tag_ids
        .split(',')
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0)
    : []

  let selectedAverage = null
  for (const tagId of tagIds) {
    const candidate = tagAverages.find((item) => item.tag_id === tagId)
    if (!candidate) {
      continue
    }

    if (!selectedAverage || candidate.samples > selectedAverage.samples) {
      selectedAverage = candidate
    }
  }

  const average = selectedAverage ?? globalAverage
  if (!average) {
    continue
  }

  const calories =
    product.calories_per_100g ?? (average.calories === null ? null : round2(average.calories))
  const carbohydrates =
    product.carbohydrates_per_100g ??
    (average.carbohydrates === null ? null : round2(average.carbohydrates))
  const sugars =
    product.sugars_per_100g ?? (average.sugars === null ? null : round2(average.sugars))
  const fat = product.fat_per_100g ?? (average.fat === null ? null : round2(average.fat))
  const protein =
    product.protein_per_100g ?? (average.protein === null ? null : round2(average.protein))
  const fiber = product.fiber_per_100g ?? (average.fiber === null ? null : round2(average.fiber))

  if (calories === null || carbohydrates === null || fat === null || protein === null) {
    continue
  }

  const source = selectedAverage
    ? `openfoodfacts:tag-average:${selectedAverage.tag_name}`
    : 'openfoodfacts:global-average'

  updateProduct.run(calories, carbohydrates, sugars, fat, protein, fiber, source, product.id)
  updated += 1
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

console.log(`Filled products from averages: ${updated}`)
console.log(`Coverage after fill: ${coverage.complete}/${coverage.total}`)
