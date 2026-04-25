import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import Database from 'better-sqlite3'

const corrections = [
  {
    id: 6,
    name: 'Seler (korzeń)',
    source: 'usda:fdc:170400:Celeriac, raw',
    nutrition: {
      calories: 42,
      carbohydrates: 9.23,
      sugars: 1.6,
      fat: 0.3,
      protein: 1.5,
      fiber: 1.8,
    },
  },
  {
    id: 11,
    name: 'Pomidor',
    source: 'usda:fdc:170457:Tomatoes, red, ripe, raw',
    nutrition: {
      calories: 18,
      carbohydrates: 3.89,
      sugars: 2.63,
      fat: 0.2,
      protein: 0.88,
      fiber: 1.2,
    },
  },
  {
    id: 30,
    name: 'Por',
    source: 'usda:fdc:169246:Leek, raw',
    nutrition: {
      calories: 61,
      carbohydrates: 14.15,
      sugars: 3.9,
      fat: 0.3,
      protein: 1.5,
      fiber: 1.8,
    },
  },
  {
    id: 46,
    name: 'Cytryna',
    source: 'usda:sr:generic:Lemon, raw',
    nutrition: {
      calories: 29,
      carbohydrates: 9.32,
      sugars: 2.5,
      fat: 0.3,
      protein: 1.1,
      fiber: 2.8,
    },
  },
  {
    id: 73,
    name: 'Pieczarki',
    source: 'usda:sr:generic:Mushrooms, white, raw',
    nutrition: { calories: 22, carbohydrates: 3.26, sugars: 2, fat: 0.34, protein: 3.09, fiber: 1 },
  },
  {
    id: 106,
    name: 'Kawa espresso (napar bez cukru)',
    source: 'usda:sr:generic:Espresso, brewed',
    nutrition: { calories: 1, carbohydrates: 0, sugars: 0, fat: 0, protein: 0.1, fiber: 0 },
  },
  {
    id: 112,
    name: 'Limonka',
    source: 'usda:fdc:168155:Lime, raw',
    nutrition: {
      calories: 30,
      carbohydrates: 10.54,
      sugars: 1.69,
      fat: 0.2,
      protein: 0.7,
      fiber: 2.8,
    },
  },
  {
    id: 156,
    name: 'Jeżyny',
    source: 'usda:fdc:173946:Blackberries, raw',
    nutrition: {
      calories: 43,
      carbohydrates: 9.61,
      sugars: 4.88,
      fat: 0.49,
      protein: 1.39,
      fiber: 5.3,
    },
  },
  {
    id: 157,
    name: 'Bób',
    source: 'usda:sr:generic:Broad beans, raw',
    nutrition: {
      calories: 88,
      carbohydrates: 18.56,
      sugars: 1.76,
      fat: 0.73,
      protein: 7.6,
      fiber: 5.4,
    },
  },
  {
    id: 168,
    name: 'Kakao (proszek bez dodatku cukru)',
    source: 'usda:fdc:169593:Cocoa, dry powder, unsweetened',
    nutrition: {
      calories: 228,
      carbohydrates: 57.9,
      sugars: 1.8,
      fat: 13.7,
      protein: 19.6,
      fiber: 37,
    },
  },
]

const databasePath = process.env.DATABASE_PATH || 'database.db'
const reportPath = 'db/manual-nutrition-corrections-report.json'

function round2(value) {
  return Number(value.toFixed(2))
}

const database = new Database(databasePath)
database.pragma('foreign_keys = ON')

const selectStatement = database.prepare(
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
    nutrition_source
  FROM products
  WHERE id = ?
  `,
)

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
  databasePath,
  updated: [],
}

const applyCorrection = database.transaction((correction) => {
  const before = selectStatement.get(correction.id)
  if (!before) {
    throw new Error(`Missing product ${correction.id}`)
  }

  const now = new Date().toISOString()
  updateStatement.run(
    round2(correction.nutrition.calories),
    round2(correction.nutrition.carbohydrates),
    round2(correction.nutrition.sugars),
    round2(correction.nutrition.fat),
    round2(correction.nutrition.protein),
    round2(correction.nutrition.fiber),
    correction.source,
    now,
    now,
    correction.id,
  )

  report.updated.push({
    id: correction.id,
    name: correction.name,
    before: {
      calories: before.calories_per_100g,
      carbohydrates: before.carbohydrates_per_100g,
      sugars: before.sugars_per_100g,
      fat: before.fat_per_100g,
      protein: before.protein_per_100g,
      fiber: before.fiber_per_100g,
      source: before.nutrition_source,
    },
    after: {
      ...correction.nutrition,
      source: correction.source,
    },
  })
})

for (const correction of corrections) {
  applyCorrection(correction)
  console.log(`OK    ${correction.name} -> ${correction.source}`)
}

mkdirSync(path.dirname(reportPath), { recursive: true })
writeFileSync(reportPath, JSON.stringify(report, null, 2))

console.log('---')
console.log(`Updated: ${report.updated.length}`)
console.log(`Report: ${reportPath}`)

database.close()
