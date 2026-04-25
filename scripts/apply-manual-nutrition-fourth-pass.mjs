import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import Database from 'better-sqlite3'

const corrections = [
  {
    id: 9,
    name: 'Wędlina z piersi indyka',
    source: 'usda:sr:generic:Turkey breast deli meat',
    nutrition: {
      calories: 104,
      carbohydrates: 2.29,
      sugars: 0.71,
      fat: 1.66,
      protein: 17.07,
      fiber: 0,
    },
  },
  {
    id: 18,
    name: 'Polędwica wieprzowa',
    source: 'usda:sr:generic:Pork tenderloin, raw',
    nutrition: { calories: 120, carbohydrates: 0, sugars: 0, fat: 3.45, protein: 21.2, fiber: 0 },
  },
  {
    id: 22,
    name: 'Maślanka (1,5% tłuszczu)',
    source: 'usda:sr:generic:Buttermilk, lowfat',
    nutrition: {
      calories: 40,
      carbohydrates: 4.79,
      sugars: 4.79,
      fat: 0.88,
      protein: 3.31,
      fiber: 0,
    },
  },
  {
    id: 57,
    name: 'Szynka wieprzowa mielona',
    source: 'usda:sr:generic:Ground pork, raw',
    nutrition: { calories: 263, carbohydrates: 0, sugars: 0, fat: 21.19, protein: 16.88, fiber: 0 },
  },
  {
    id: 62,
    name: 'Skyr waniliowy',
    source: 'usda:sr:generic:Greek yogurt, vanilla, nonfat',
    nutrition: {
      calories: 84,
      carbohydrates: 11.5,
      sugars: 10.3,
      fat: 0.2,
      protein: 10.3,
      fiber: 0,
    },
  },
  {
    id: 74,
    name: 'Wędlina wieprzowa',
    source: 'usda:sr:generic:Ham, sliced, deli',
    nutrition: {
      calories: 147,
      carbohydrates: 3.72,
      sugars: 0.63,
      fat: 5.53,
      protein: 20.93,
      fiber: 0,
    },
  },
  {
    id: 96,
    name: 'Sałata masłowa',
    source: 'usda:sr:generic:Lettuce, butterhead, raw',
    nutrition: {
      calories: 13,
      carbohydrates: 2.23,
      sugars: 0.78,
      fat: 0.22,
      protein: 1.35,
      fiber: 1.1,
    },
  },
  {
    id: 103,
    name: 'Ser żółty',
    source: 'usda:sr:generic:Cheese, gouda',
    nutrition: {
      calories: 356,
      carbohydrates: 2.22,
      sugars: 2.22,
      fat: 27.44,
      protein: 24.94,
      fiber: 0,
    },
  },
  {
    id: 131,
    name: 'Papryka ostra w proszku',
    source: 'usda:sr:generic:Pepper, red or cayenne',
    nutrition: {
      calories: 318,
      carbohydrates: 56.63,
      sugars: 10.34,
      fat: 17.27,
      protein: 12.01,
      fiber: 27.2,
    },
  },
  {
    id: 141,
    name: 'Papryczka chili suszona',
    source: 'usda:sr:generic:Peppers, hot chili, dried',
    nutrition: {
      calories: 282,
      carbohydrates: 49.7,
      sugars: 7.19,
      fat: 14.28,
      protein: 12.01,
      fiber: 34.8,
    },
  },
  {
    id: 144,
    name: 'Chorizo wieprzowo-wołowe',
    source: 'usda:sr:generic:Chorizo',
    nutrition: {
      calories: 455,
      carbohydrates: 1.86,
      sugars: 0,
      fat: 38.27,
      protein: 24.1,
      fiber: 0,
    },
  },
  {
    id: 145,
    name: 'Szafran',
    source: 'usda:sr:generic:Saffron',
    nutrition: {
      calories: 310,
      carbohydrates: 65.37,
      sugars: 0,
      fat: 5.85,
      protein: 11.43,
      fiber: 3.9,
    },
  },
  {
    id: 160,
    name: 'Mięso z indyka',
    source: 'usda:sr:generic:Turkey meat, raw',
    nutrition: { calories: 161, carbohydrates: 0, sugars: 0, fat: 7.39, protein: 21.96, fiber: 0 },
  },
  {
    id: 163,
    name: 'Pieprz cayenne',
    source: 'usda:sr:generic:Pepper, red or cayenne',
    nutrition: {
      calories: 318,
      carbohydrates: 56.63,
      sugars: 10.34,
      fat: 17.27,
      protein: 12.01,
      fiber: 27.2,
    },
  },
  {
    id: 170,
    name: 'Karkówka wieprzowa',
    source: 'usda:sr:generic:Pork shoulder, raw',
    nutrition: { calories: 221, carbohydrates: 0, sugars: 0, fat: 17.44, protein: 16.3, fiber: 0 },
  },
  {
    id: 179,
    name: 'Papryczka chili czerwona',
    source: 'usda:sr:generic:Peppers, hot chili, red, raw',
    nutrition: {
      calories: 40,
      carbohydrates: 8.81,
      sugars: 5.3,
      fat: 0.44,
      protein: 1.87,
      fiber: 1.5,
    },
  },
  {
    id: 180,
    name: 'Łopatka wieprzowa',
    source: 'usda:sr:generic:Pork shoulder, raw',
    nutrition: { calories: 221, carbohydrates: 0, sugars: 0, fat: 17.44, protein: 16.3, fiber: 0 },
  },
]

const databasePath = process.env.DATABASE_PATH || 'database.db'
const reportPath = 'db/manual-nutrition-fourth-pass-report.json'

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
