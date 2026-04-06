import Database from 'better-sqlite3'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const databasePath = path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')

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

const db = new Database(databasePath)
db.pragma('foreign_keys = ON')

const rows = db
  .prepare(
    `
    SELECT
      ri.id AS recipe_ingredient_id,
      ri.product_id,
      ri.quantity,
      ri.grams,
      u.id AS unit_id,
      u.name AS unit_name
    FROM recipe_ingredients ri
    LEFT JOIN units u ON u.id = ri.unit_id
    WHERE u.id IS NOT NULL
      AND ri.quantity IS NOT NULL
      AND ri.quantity > 0
      AND ri.grams IS NOT NULL
      AND ri.grams > 0
    ORDER BY ri.id ASC
    `,
  )
  .all()

const insertPackageType = db.prepare(
  `
  INSERT OR IGNORE INTO package_types(name, normalized_name)
  VALUES (?, ?)
  `,
)

const selectPackageType = db.prepare('SELECT id FROM package_types WHERE normalized_name = ?')

const upsertConversion = db.prepare(
  `
  INSERT INTO ingredient_package_conversions(
    product_id,
    package_type_id,
    grams_per_package,
    source,
    samples_count
  )
  VALUES (?, ?, ?, ?, ?)
  ON CONFLICT(product_id, package_type_id)
  DO UPDATE SET
    grams_per_package = excluded.grams_per_package,
    source = excluded.source,
    samples_count = excluded.samples_count,
    updated_at = CURRENT_TIMESTAMP
  `,
)

const updateRecipeIngredientConversion = db.prepare(
  `
  UPDATE recipe_ingredients
  SET ingredient_package_conversion_id = ?
  WHERE id = ?
  `,
)

const clearRecipeIngredientUnitForPackage = db.prepare(
  `
  UPDATE recipe_ingredients
  SET unit_id = NULL
  WHERE id = ?
  `,
)

const deleteUnit = db.prepare('DELETE FROM units WHERE id = ?')

const conversions = new Map()
const nonPhysicalUnitIds = new Set()

for (const row of rows) {
  const normalizedUnit = normalizeName(row.unit_name)

  if (MASS_VOLUME_ALIASES.has(normalizedUnit)) {
    continue
  }

  nonPhysicalUnitIds.add(row.unit_id)

  const gramsPerPackage = Number((row.grams / row.quantity).toFixed(2))
  const key = `${row.product_id}|${normalizedUnit}`

  if (!conversions.has(key)) {
    conversions.set(key, {
      productId: row.product_id,
      packageTypeName: row.unit_name,
      normalizedName: normalizedUnit,
      totalGrams: 0,
      samples: 0,
      recipeRows: [],
    })
  }

  const item = conversions.get(key)
  item.totalGrams += gramsPerPackage
  item.samples += 1
  item.recipeRows.push(row.recipe_ingredient_id)
}

let mappingsUpserted = 0
let recipeRowsLinked = 0

const apply = db.transaction(() => {
  for (const item of conversions.values()) {
    insertPackageType.run(item.packageTypeName, item.normalizedName)
    const packageType = selectPackageType.get(item.normalizedName)

    if (!packageType) {
      continue
    }

    const averageGrams = Number((item.totalGrams / item.samples).toFixed(2))

    upsertConversion.run(
      item.productId,
      packageType.id,
      averageGrams,
      'rebuild-from-recipes',
      item.samples,
    )
    mappingsUpserted += 1

    const conversion = db
      .prepare(
        `
        SELECT id
        FROM ingredient_package_conversions
        WHERE product_id = ? AND package_type_id = ?
        `,
      )
      .get(item.productId, packageType.id)

    if (!conversion) {
      continue
    }

    for (const recipeIngredientId of item.recipeRows) {
      updateRecipeIngredientConversion.run(conversion.id, recipeIngredientId)
      clearRecipeIngredientUnitForPackage.run(recipeIngredientId)
      recipeRowsLinked += 1
    }
  }

  for (const unitId of nonPhysicalUnitIds) {
    deleteUnit.run(unitId)
  }
})

apply()

const physicalUnits = db
  .prepare(
    `
    SELECT name
    FROM units
    ORDER BY name COLLATE NOCASE ASC
    `,
  )
  .all()
  .map((item) => item.name)

const inconsistent = db
  .prepare(
    `
    SELECT
      pt.name AS package_type_name,
      COUNT(*) AS products_count,
      MIN(ipc.grams_per_package) AS min_grams,
      MAX(ipc.grams_per_package) AS max_grams
    FROM ingredient_package_conversions ipc
    INNER JOIN package_types pt ON pt.id = ipc.package_type_id
    GROUP BY pt.id
    HAVING MIN(ipc.grams_per_package) <> MAX(ipc.grams_per_package)
    ORDER BY products_count DESC, package_type_name COLLATE NOCASE ASC
    `,
  )
  .all()

db.close()

console.log(`Package mappings upserted: ${mappingsUpserted}`)
console.log(`Recipe rows linked to mappings: ${recipeRowsLinked}`)
console.log(`Removed non-physical units: ${nonPhysicalUnitIds.size}`)
console.log(`Remaining units: ${physicalUnits.join(', ')}`)

if (inconsistent.length > 0) {
  console.log('Non-uniform package types by ingredient:')
  for (const row of inconsistent) {
    console.log(
      `- ${row.package_type_name}: ${row.products_count} products, ${row.min_grams}-${row.max_grams} g`,
    )
  }
}
