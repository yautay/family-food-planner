import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import Database from 'better-sqlite3'

const corrections = [
  {
    id: 1,
    name: 'Cebula',
    source: 'usda:sr:generic:Onions, raw',
    nutrition: {
      calories: 40,
      carbohydrates: 9.34,
      sugars: 4.24,
      fat: 0.1,
      protein: 1.1,
      fiber: 1.7,
    },
  },
  {
    id: 8,
    name: 'Masło',
    source: 'usda:sr:generic:Butter, salted',
    nutrition: {
      calories: 717,
      carbohydrates: 0.06,
      sugars: 0.06,
      fat: 81.11,
      protein: 0.85,
      fiber: 0,
    },
  },
  {
    id: 13,
    name: 'Rzodkiewka',
    source: 'usda:sr:generic:Radishes, raw',
    nutrition: {
      calories: 16,
      carbohydrates: 3.4,
      sugars: 1.86,
      fat: 0.1,
      protein: 0.68,
      fiber: 1.6,
    },
  },
  {
    id: 17,
    name: 'Natka pietruszki',
    source: 'usda:sr:generic:Parsley, fresh',
    nutrition: {
      calories: 36,
      carbohydrates: 6.33,
      sugars: 0.85,
      fat: 0.79,
      protein: 2.97,
      fiber: 3.3,
    },
  },
  {
    id: 19,
    name: 'Maliny',
    source: 'usda:sr:generic:Raspberries, raw',
    nutrition: {
      calories: 52,
      carbohydrates: 11.94,
      sugars: 4.42,
      fat: 0.65,
      protein: 1.2,
      fiber: 6.5,
    },
  },
  {
    id: 33,
    name: 'Tymianek suszony',
    source: 'usda:sr:generic:Thyme, dried',
    nutrition: {
      calories: 276,
      carbohydrates: 63.94,
      sugars: 1.71,
      fat: 7.43,
      protein: 9.11,
      fiber: 37,
    },
  },
  {
    id: 34,
    name: 'Ziemniak',
    source: 'usda:sr:generic:Potatoes, flesh and skin, raw',
    nutrition: {
      calories: 77,
      carbohydrates: 17.58,
      sugars: 0.82,
      fat: 0.09,
      protein: 2.05,
      fiber: 2.2,
    },
  },
  {
    id: 44,
    name: 'Sok z cytryny',
    source: 'usda:fdc:167747:Lemon juice, raw',
    nutrition: {
      calories: 22,
      carbohydrates: 6.9,
      sugars: 2.5,
      fat: 0.24,
      protein: 0.35,
      fiber: 0.3,
    },
  },
  {
    id: 47,
    name: 'Sól',
    source: 'usda:sr:generic:Salt, table',
    nutrition: { calories: 0, carbohydrates: 0, sugars: 0, fat: 0, protein: 0, fiber: 0 },
  },
  {
    id: 48,
    name: 'Ogórek świeży',
    source: 'usda:sr:generic:Cucumber, with peel, raw',
    nutrition: {
      calories: 15,
      carbohydrates: 3.63,
      sugars: 1.67,
      fat: 0.11,
      protein: 0.65,
      fiber: 0.5,
    },
  },
  {
    id: 51,
    name: 'Jabłko',
    source: 'usda:sr:generic:Apples, with skin, raw',
    nutrition: {
      calories: 52,
      carbohydrates: 13.81,
      sugars: 10.39,
      fat: 0.17,
      protein: 0.26,
      fiber: 2.4,
    },
  },
  {
    id: 54,
    name: 'Cebula czerwona',
    source: 'usda:sr:generic:Onions, red, raw',
    nutrition: {
      calories: 40,
      carbohydrates: 9.11,
      sugars: 4.28,
      fat: 0.1,
      protein: 1.1,
      fiber: 1.7,
    },
  },
  {
    id: 65,
    name: 'Gruszka',
    source: 'usda:sr:generic:Pears, raw',
    nutrition: {
      calories: 57,
      carbohydrates: 15.23,
      sugars: 9.75,
      fat: 0.14,
      protein: 0.36,
      fiber: 3.1,
    },
  },
  {
    id: 75,
    name: 'Szczypiorek',
    source: 'usda:sr:generic:Chives, raw',
    nutrition: {
      calories: 30,
      carbohydrates: 4.35,
      sugars: 1.85,
      fat: 0.73,
      protein: 3.27,
      fiber: 2.5,
    },
  },
  {
    id: 90,
    name: 'Pomidor koktajlowy',
    source: 'usda:sr:generic:Tomatoes, red, ripe, raw',
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
    id: 91,
    name: 'Papryka żółta',
    source: 'usda:sr:generic:Peppers, sweet, yellow, raw',
    nutrition: { calories: 27, carbohydrates: 6.32, sugars: 5, fat: 0.21, protein: 1, fiber: 0.9 },
  },
  {
    id: 104,
    name: 'Pieprz czarny',
    source: 'usda:sr:generic:Pepper, black',
    nutrition: {
      calories: 251,
      carbohydrates: 64.81,
      sugars: 0.64,
      fat: 3.26,
      protein: 10.39,
      fiber: 25.3,
    },
  },
  {
    id: 110,
    name: 'Imbir świeży',
    source: 'usda:sr:generic:Ginger root, raw',
    nutrition: {
      calories: 80,
      carbohydrates: 17.77,
      sugars: 1.7,
      fat: 0.75,
      protein: 1.82,
      fiber: 2,
    },
  },
  {
    id: 113,
    name: 'Kolendra (liście)',
    source: 'usda:sr:generic:Coriander (cilantro) leaves, raw',
    nutrition: {
      calories: 23,
      carbohydrates: 3.67,
      sugars: 0.87,
      fat: 0.52,
      protein: 2.13,
      fiber: 2.8,
    },
  },
  {
    id: 124,
    name: 'Cebula szalotka',
    source: 'usda:sr:generic:Shallots, raw',
    nutrition: {
      calories: 72,
      carbohydrates: 16.8,
      sugars: 7.87,
      fat: 0.1,
      protein: 2.5,
      fiber: 3.2,
    },
  },
  {
    id: 132,
    name: 'Bazylia świeża',
    source: 'usda:sr:generic:Basil, fresh',
    nutrition: {
      calories: 23,
      carbohydrates: 2.65,
      sugars: 0.3,
      fat: 0.64,
      protein: 3.15,
      fiber: 1.6,
    },
  },
  {
    id: 161,
    name: 'Dynia',
    source: 'usda:sr:generic:Pumpkin, raw',
    nutrition: { calories: 26, carbohydrates: 6.5, sugars: 2.76, fat: 0.1, protein: 1, fiber: 0.5 },
  },
  {
    id: 164,
    name: 'Sok z limonki',
    source: 'usda:sr:generic:Lime juice, raw',
    nutrition: {
      calories: 25,
      carbohydrates: 8.42,
      sugars: 1.69,
      fat: 0.07,
      protein: 0.42,
      fiber: 0.4,
    },
  },
  {
    id: 167,
    name: 'Cukier',
    source: 'usda:sr:generic:Sugar, granulated',
    nutrition: { calories: 387, carbohydrates: 100, sugars: 100, fat: 0, protein: 0, fiber: 0 },
  },
  {
    id: 181,
    name: 'Bazylia suszona',
    source: 'usda:sr:generic:Basil, dried',
    nutrition: {
      calories: 233,
      carbohydrates: 47.75,
      sugars: 1.71,
      fat: 4.07,
      protein: 22.98,
      fiber: 37.7,
    },
  },
]

const databasePath = process.env.DATABASE_PATH || 'database.db'
const reportPath = 'db/manual-nutrition-second-pass-report.json'

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
