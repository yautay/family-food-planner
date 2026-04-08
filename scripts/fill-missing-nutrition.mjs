import { Op } from 'sequelize'
import sequelize from '../src/db/client.js'
import models from '../src/models/index.js'

function round2(value) {
  return Number(value.toFixed(2))
}

function average(values) {
  if (values.length === 0) {
    return null
  }

  return values.reduce((accumulator, value) => accumulator + value, 0) / values.length
}

await sequelize.authenticate()

const sourceProducts = await models.product.findAll({
  attributes: [
    'id',
    'calories_per_100g',
    'carbohydrates_per_100g',
    'sugars_per_100g',
    'fat_per_100g',
    'protein_per_100g',
    'fiber_per_100g',
  ],
  where: {
    nutrition_source: {
      [Op.like]: 'openfoodfacts:%',
    },
    calories_per_100g: {
      [Op.not]: null,
    },
    carbohydrates_per_100g: {
      [Op.not]: null,
    },
    fat_per_100g: {
      [Op.not]: null,
    },
    protein_per_100g: {
      [Op.not]: null,
    },
  },
  include: [
    {
      model: models.tag,
      as: 'tags',
      attributes: ['id', 'name'],
      through: { attributes: [] },
      required: false,
    },
  ],
})

const tagAccumulator = new Map()

for (const productRow of sourceProducts) {
  const product = productRow.get({ plain: true })
  for (const tag of product.tags ?? []) {
    if (!tagAccumulator.has(tag.id)) {
      tagAccumulator.set(tag.id, {
        tag_name: tag.name,
        samples: 0,
        calories: [],
        carbohydrates: [],
        sugars: [],
        fat: [],
        protein: [],
        fiber: [],
      })
    }

    const aggregate = tagAccumulator.get(tag.id)
    aggregate.samples += 1
    aggregate.calories.push(product.calories_per_100g)
    aggregate.carbohydrates.push(product.carbohydrates_per_100g)
    if (product.sugars_per_100g !== null) {
      aggregate.sugars.push(product.sugars_per_100g)
    }
    aggregate.fat.push(product.fat_per_100g)
    aggregate.protein.push(product.protein_per_100g)
    if (product.fiber_per_100g !== null) {
      aggregate.fiber.push(product.fiber_per_100g)
    }
  }
}

const tagAverages = new Map()
for (const [tagId, aggregate] of tagAccumulator.entries()) {
  if (aggregate.samples < 2) {
    continue
  }

  tagAverages.set(tagId, {
    tag_name: aggregate.tag_name,
    samples: aggregate.samples,
    calories: average(aggregate.calories),
    carbohydrates: average(aggregate.carbohydrates),
    sugars: average(aggregate.sugars),
    fat: average(aggregate.fat),
    protein: average(aggregate.protein),
    fiber: average(aggregate.fiber),
  })
}

const globalAverage = {
  calories: average(sourceProducts.map((item) => item.calories_per_100g)),
  carbohydrates: average(sourceProducts.map((item) => item.carbohydrates_per_100g)),
  sugars: average(
    sourceProducts.map((item) => item.sugars_per_100g).filter((value) => value !== null),
  ),
  fat: average(sourceProducts.map((item) => item.fat_per_100g)),
  protein: average(sourceProducts.map((item) => item.protein_per_100g)),
  fiber: average(
    sourceProducts.map((item) => item.fiber_per_100g).filter((value) => value !== null),
  ),
}

const missingProducts = await models.product.findAll({
  where: {
    [Op.or]: [
      { calories_per_100g: null },
      { carbohydrates_per_100g: null },
      { fat_per_100g: null },
      { protein_per_100g: null },
    ],
  },
  include: [
    {
      model: models.tag,
      as: 'tags',
      attributes: ['id'],
      through: { attributes: [] },
      required: false,
    },
  ],
  order: [['name', 'ASC']],
})

let updated = 0

for (const productRow of missingProducts) {
  const product = productRow.get({ plain: true })
  const tagIds = (product.tags ?? []).map((tag) => tag.id)

  let selectedAverage = null
  for (const tagId of tagIds) {
    const candidate = tagAverages.get(tagId)
    if (!candidate) {
      continue
    }

    if (!selectedAverage || candidate.samples > selectedAverage.samples) {
      selectedAverage = candidate
    }
  }

  const averageSet = selectedAverage ?? globalAverage
  if (!averageSet) {
    continue
  }

  const calories =
    product.calories_per_100g ?? (averageSet.calories === null ? null : round2(averageSet.calories))
  const carbohydrates =
    product.carbohydrates_per_100g ??
    (averageSet.carbohydrates === null ? null : round2(averageSet.carbohydrates))
  const sugars =
    product.sugars_per_100g ?? (averageSet.sugars === null ? null : round2(averageSet.sugars))
  const fat = product.fat_per_100g ?? (averageSet.fat === null ? null : round2(averageSet.fat))
  const protein =
    product.protein_per_100g ?? (averageSet.protein === null ? null : round2(averageSet.protein))
  const fiber =
    product.fiber_per_100g ?? (averageSet.fiber === null ? null : round2(averageSet.fiber))

  if (calories === null || carbohydrates === null || fat === null || protein === null) {
    continue
  }

  const source = selectedAverage
    ? `openfoodfacts:tag-average:${selectedAverage.tag_name}`
    : 'openfoodfacts:global-average'

  await models.product.update(
    {
      calories_per_100g: calories,
      carbohydrates_per_100g: carbohydrates,
      sugars_per_100g: sugars,
      fat_per_100g: fat,
      protein_per_100g: protein,
      fiber_per_100g: fiber,
      nutrition_source: source,
      nutrition_updated_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      where: { id: product.id },
    },
  )

  updated += 1
}

const coverage = {
  total: await models.product.count(),
  complete: await models.product.count({
    where: {
      calories_per_100g: { [Op.not]: null },
      carbohydrates_per_100g: { [Op.not]: null },
      fat_per_100g: { [Op.not]: null },
      protein_per_100g: { [Op.not]: null },
    },
  }),
}

await sequelize.close()

console.log(`Filled products from averages: ${updated}`)
console.log(`Coverage after fill: ${coverage.complete}/${coverage.total}`)
