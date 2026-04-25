import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import Database from 'better-sqlite3'

const corrections = [
  {
    id: 4,
    name: 'Pietruszka (korzeń)',
    source: 'usda:sr:generic:Celeriac, raw',
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
    id: 23,
    name: 'Orzechy włoskie',
    source: 'usda:sr:generic:Walnuts',
    nutrition: {
      calories: 654,
      carbohydrates: 13.71,
      sugars: 2.61,
      fat: 65.21,
      protein: 15.23,
      fiber: 6.7,
    },
  },
  {
    id: 26,
    name: 'Musztarda',
    source: 'usda:sr:generic:Mustard, prepared, yellow',
    nutrition: {
      calories: 60,
      carbohydrates: 5.83,
      sugars: 0.9,
      fat: 3.34,
      protein: 3.74,
      fiber: 3.3,
    },
  },
  {
    id: 49,
    name: 'Oliwki',
    source: 'usda:sr:generic:Olives, ripe, canned',
    nutrition: {
      calories: 116,
      carbohydrates: 6.04,
      sugars: 0,
      fat: 10.9,
      protein: 0.84,
      fiber: 1.6,
    },
  },
  {
    id: 55,
    name: 'Suszone pomidory',
    source: 'usda:sr:generic:Tomatoes, sun-dried',
    nutrition: {
      calories: 258,
      carbohydrates: 55.76,
      sugars: 37.59,
      fat: 2.97,
      protein: 14.11,
      fiber: 12.3,
    },
  },
  {
    id: 56,
    name: 'Cukinia',
    source: 'usda:sr:generic:Zucchini, raw',
    nutrition: {
      calories: 17,
      carbohydrates: 3.11,
      sugars: 2.5,
      fat: 0.32,
      protein: 1.21,
      fiber: 1,
    },
  },
  {
    id: 60,
    name: 'Ser ricotta',
    source: 'usda:sr:generic:Cheese, ricotta, whole milk',
    nutrition: {
      calories: 174,
      carbohydrates: 3.04,
      sugars: 0.27,
      fat: 12.98,
      protein: 11.26,
      fiber: 0,
    },
  },
  {
    id: 63,
    name: 'Mąka orkiszowa jasna',
    source: 'usda:sr:generic:Spelt flour',
    nutrition: {
      calories: 361,
      carbohydrates: 70.19,
      sugars: 0.41,
      fat: 2.43,
      protein: 14.57,
      fiber: 10.7,
    },
  },
  {
    id: 64,
    name: 'Skyr naturalny',
    source: 'usda:sr:generic:Yogurt, Greek, plain, nonfat',
    nutrition: {
      calories: 59,
      carbohydrates: 3.6,
      sugars: 3.24,
      fat: 0.39,
      protein: 10.19,
      fiber: 0,
    },
  },
  {
    id: 69,
    name: 'Ser camembert',
    source: 'usda:sr:generic:Cheese, camembert',
    nutrition: {
      calories: 300,
      carbohydrates: 0.46,
      sugars: 0.46,
      fat: 24.26,
      protein: 19.8,
      fiber: 0,
    },
  },
  {
    id: 76,
    name: 'Ser mozzarella light',
    source: 'usda:sr:generic:Cheese, mozzarella, part skim milk',
    nutrition: {
      calories: 254,
      carbohydrates: 2.77,
      sugars: 1.13,
      fat: 15.92,
      protein: 24.26,
      fiber: 0,
    },
  },
  {
    id: 77,
    name: 'Śmietana 18 % tłuszczu',
    source: 'usda:sr:generic:Sour cream, cultured',
    nutrition: {
      calories: 193,
      carbohydrates: 4.63,
      sugars: 3.56,
      fat: 19.35,
      protein: 2.44,
      fiber: 0,
    },
  },
  {
    id: 86,
    name: 'Makaron świderki',
    source: 'usda:sr:generic:Pasta, dry',
    nutrition: {
      calories: 371,
      carbohydrates: 74.67,
      sugars: 2.67,
      fat: 1.51,
      protein: 13.04,
      fiber: 3.2,
    },
  },
  {
    id: 87,
    name: 'Czarne jagody mrożone',
    source: 'usda:sr:generic:Blueberries, frozen, unsweetened',
    nutrition: {
      calories: 57,
      carbohydrates: 14.49,
      sugars: 9.96,
      fat: 0.33,
      protein: 0.74,
      fiber: 2.4,
    },
  },
  {
    id: 97,
    name: 'Polędwica wołowa',
    source: 'usda:sr:generic:Beef tenderloin, raw',
    nutrition: { calories: 187, carbohydrates: 0, sugars: 0, fat: 12.7, protein: 19.1, fiber: 0 },
  },
  {
    id: 101,
    name: 'Ser parmezan tarty',
    source: 'usda:sr:generic:Cheese, parmesan, grated',
    nutrition: {
      calories: 431,
      carbohydrates: 4.06,
      sugars: 0.9,
      fat: 28.61,
      protein: 38.46,
      fiber: 0,
    },
  },
  {
    id: 114,
    name: 'Makaron ryżowy',
    source: 'usda:sr:generic:Rice noodles, dry',
    nutrition: {
      calories: 364,
      carbohydrates: 83.24,
      sugars: 0.31,
      fat: 0.56,
      protein: 5.95,
      fiber: 1.6,
    },
  },
  {
    id: 116,
    name: 'Makaron',
    source: 'usda:sr:generic:Pasta, dry',
    nutrition: {
      calories: 371,
      carbohydrates: 74.67,
      sugars: 2.67,
      fat: 1.51,
      protein: 13.04,
      fiber: 3.2,
    },
  },
  {
    id: 117,
    name: 'Łosoś wędzony',
    source: 'usda:sr:generic:Salmon, smoked',
    nutrition: { calories: 117, carbohydrates: 0, sugars: 0, fat: 4.32, protein: 18.28, fiber: 0 },
  },
  {
    id: 118,
    name: 'Ser niebieski',
    source: 'usda:sr:generic:Cheese, blue',
    nutrition: {
      calories: 353,
      carbohydrates: 2.34,
      sugars: 0.5,
      fat: 28.74,
      protein: 21.4,
      fiber: 0,
    },
  },
  {
    id: 121,
    name: 'Migdały',
    source: 'usda:sr:generic:Almonds',
    nutrition: {
      calories: 579,
      carbohydrates: 21.55,
      sugars: 4.35,
      fat: 49.93,
      protein: 21.15,
      fiber: 12.5,
    },
  },
  {
    id: 127,
    name: 'Czosnek mielony',
    source: 'usda:sr:generic:Garlic powder',
    nutrition: {
      calories: 331,
      carbohydrates: 72.73,
      sugars: 2.41,
      fat: 0.73,
      protein: 16.55,
      fiber: 9,
    },
  },
  {
    id: 128,
    name: 'Wątróbka z kurczaka',
    source: 'usda:sr:generic:Chicken liver, raw',
    nutrition: {
      calories: 119,
      carbohydrates: 0.73,
      sugars: 0,
      fat: 4.83,
      protein: 16.92,
      fiber: 0,
    },
  },
  {
    id: 129,
    name: 'Majeranek suszony',
    source: 'usda:sr:generic:Marjoram, dried',
    nutrition: {
      calories: 271,
      carbohydrates: 60.56,
      sugars: 4.09,
      fat: 7.04,
      protein: 12.66,
      fiber: 40.3,
    },
  },
  {
    id: 133,
    name: 'Dorsz',
    source: 'usda:sr:generic:Cod, raw',
    nutrition: { calories: 82, carbohydrates: 0, sugars: 0, fat: 0.67, protein: 17.81, fiber: 0 },
  },
  {
    id: 139,
    name: 'Ciecierzyca z puszki',
    source: 'usda:sr:generic:Chickpeas, canned, drained',
    nutrition: {
      calories: 139,
      carbohydrates: 22.52,
      sugars: 4.8,
      fat: 2.59,
      protein: 7.05,
      fiber: 7.6,
    },
  },
  {
    id: 140,
    name: 'Papryka słodka w proszku',
    source: 'usda:sr:generic:Paprika',
    nutrition: {
      calories: 282,
      carbohydrates: 53.99,
      sugars: 10.34,
      fat: 12.89,
      protein: 14.14,
      fiber: 34.9,
    },
  },
  {
    id: 154,
    name: 'Marchew baby',
    source: 'usda:sr:generic:Carrots, baby, raw',
    nutrition: {
      calories: 35,
      carbohydrates: 8.24,
      sugars: 4.74,
      fat: 0.13,
      protein: 0.64,
      fiber: 2.9,
    },
  },
  {
    id: 155,
    name: 'Porzeczki mrożone',
    source: 'usda:sr:generic:Currants, raw',
    nutrition: {
      calories: 56,
      carbohydrates: 13.8,
      sugars: 7.37,
      fat: 0.2,
      protein: 1.4,
      fiber: 4.3,
    },
  },
  {
    id: 162,
    name: 'Śmietanka 30 % tłuszczu',
    source: 'usda:sr:generic:Cream, fluid, heavy whipping',
    nutrition: {
      calories: 340,
      carbohydrates: 2.84,
      sugars: 2.66,
      fat: 36.08,
      protein: 2.84,
      fiber: 0,
    },
  },
  {
    id: 174,
    name: 'Fasola biała z puszki',
    source: 'usda:sr:generic:Beans, white, canned, drained',
    nutrition: {
      calories: 114,
      carbohydrates: 20.2,
      sugars: 0.29,
      fat: 0.35,
      protein: 7.01,
      fiber: 6.3,
    },
  },
  {
    id: 176,
    name: 'Pomidory z puszki',
    source: 'usda:sr:generic:Tomatoes, canned',
    nutrition: {
      calories: 32,
      carbohydrates: 7.29,
      sugars: 4.1,
      fat: 0.28,
      protein: 1.64,
      fiber: 2.2,
    },
  },
]

const databasePath = process.env.DATABASE_PATH || 'database.db'
const reportPath = 'db/manual-nutrition-third-pass-report.json'

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
