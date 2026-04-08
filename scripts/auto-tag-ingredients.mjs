import { fn, col, literal } from 'sequelize'
import sequelize from '../src/db/client.js'
import models from '../src/models/index.js'

function normalize(value) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function includesAny(haystack, needles) {
  return needles.some((needle) => haystack.includes(needle))
}

const mealTagNames = new Set(['sniadanie', 'obiad', 'podwieczorek', 'kolacja'])

const tagNames = [
  'warzywo',
  'owoc',
  'mięso',
  'nabiał',
  'tłuszcze',
  'ryby',
  'zboża',
  'strączki',
  'orzechy i nasiona',
  'przyprawy',
  'napoje',
  'dodatki',
]

function classifyProduct(name) {
  const normalized = normalize(name)
  const result = new Set()

  if (
    includesAny(normalized, [
      'marchew',
      'pietruszka',
      'seler',
      'kapusta',
      'rukola',
      'salata',
      'pomidor',
      'ogorek',
      'papryka',
      'burak',
      'cebula',
      'czosnek',
      'szpinak',
      'rzodkiew',
      'cukinia',
      'brokul',
      'por',
      'ziemniak',
      'dynia',
      'fasolka',
    ])
  ) {
    result.add('warzywo')
  }

  if (
    includesAny(normalized, [
      'jablk',
      'gruszk',
      'banan',
      'malin',
      'truskawk',
      'borowk',
      'jagod',
      'cytryn',
      'limonk',
      'awokado',
      'jezyn',
      'porzeczk',
    ])
  ) {
    result.add('owoc')
  }

  if (
    includesAny(normalized, [
      'kurczak',
      'indyk',
      'wolow',
      'wieprz',
      'lopatka',
      'karkowka',
      'watrobka',
      'mieso',
      'boczek',
      'kielbasa',
      'szynka',
      'wedlin',
      'chorizo',
      'polendwica',
      'parowki',
    ])
  ) {
    result.add('mięso')
  }

  if (includesAny(normalized, ['losos', 'dorsz', 'pstrag', 'morszczuk', 'ryba'])) {
    result.add('ryby')
  }

  if (
    includesAny(normalized, [
      'mleko',
      'jogurt',
      'kefir',
      'skyr',
      'ser',
      'serek',
      'maslank',
      'smietan',
      'ricotta',
      'mozarella',
      'feta',
      'halloumi',
      'mascarpone',
      'camembert',
      'parmezan',
    ])
  ) {
    result.add('nabiał')
  }

  if (includesAny(normalized, ['oliwa', 'olej', 'maslo', 'majonez', 'smalec'])) {
    result.add('tłuszcze')
  }

  if (
    includesAny(normalized, [
      'makaron',
      'ryz',
      'kasza',
      'maka',
      'chleb',
      'bulka',
      'platki',
      'tortilla',
      'penczak',
    ])
  ) {
    result.add('zboża')
  }

  if (includesAny(normalized, ['fasola', 'ciecierzyc', 'bob', 'soczewic', 'groch'])) {
    result.add('strączki')
  }

  if (includesAny(normalized, ['orzech', 'migdal', 'pestki', 'nasiona', 'chia'])) {
    result.add('orzechy i nasiona')
  }

  if (
    includesAny(normalized, [
      'sol',
      'pieprz',
      'papryka',
      'cynamon',
      'tymianek',
      'oregano',
      'majeranek',
      'szafran',
      'chili',
      'ziola',
      'koperek',
      'natka',
      'bazylia',
      'kolendra',
      'imbir',
      'curry',
    ])
  ) {
    result.add('przyprawy')
  }

  if (includesAny(normalized, ['woda', 'kawa', 'sok'])) {
    result.add('napoje')
  }

  if (
    includesAny(normalized, [
      'sos',
      'keczup',
      'musztarda',
      'przecier',
      'passata',
      'hummus',
      'pesto',
      'ocet',
      'miod',
      'cukier',
    ])
  ) {
    result.add('dodatki')
  }

  if (result.size === 0) {
    result.add('dodatki')
  }

  return Array.from(result)
}

await sequelize.authenticate()

for (const name of tagNames) {
  await models.tag.findOrCreate({
    where: {
      name,
    },
    defaults: { name },
  })
}

const tags = await models.tag.findAll({
  attributes: ['id', 'name'],
  order: [[literal('name COLLATE NOCASE'), 'ASC']],
  raw: true,
})

const tagIdByName = new Map(tags.map((tag) => [normalize(tag.name), tag.id]))

const products = await models.product.findAll({
  attributes: ['id', 'name'],
  order: [[literal('name COLLATE NOCASE'), 'ASC']],
  raw: true,
})

await sequelize.transaction(async (transaction) => {
  await models.productTag.destroy({ where: {}, transaction })

  const rows = []
  for (const product of products) {
    const classes = classifyProduct(product.name)

    for (const className of classes) {
      const normalized = normalize(className)
      if (mealTagNames.has(normalized)) {
        continue
      }

      const tagId = tagIdByName.get(normalized)
      if (!tagId) {
        continue
      }

      rows.push({
        product_id: product.id,
        tag_id: tagId,
      })
    }
  }

  if (rows.length > 0) {
    await models.productTag.bulkCreate(rows, {
      ignoreDuplicates: true,
      transaction,
    })
  }
})

const totals = {
  products: await models.product.count(),
  tag_links: await models.productTag.count(),
}

const topTagsRaw = await models.productTag.findAll({
  attributes: ['tag_id', [fn('COUNT', col('tag_id')), 'links']],
  group: ['tag_id'],
  order: [[literal('links'), 'DESC']],
  raw: true,
})

const topTags = []
for (const item of topTagsRaw) {
  const tag = await models.tag.findByPk(item.tag_id, {
    attributes: ['name'],
    raw: true,
  })

  if (tag) {
    topTags.push({
      name: tag.name,
      links: Number(item.links) || 0,
    })
  }
}

topTags.sort((left, right) => {
  if (right.links !== left.links) {
    return right.links - left.links
  }

  return left.name.localeCompare(right.name, 'pl')
})

await sequelize.close()

console.log(`Tagged products: ${totals.products}`)
console.log(`Created tag links: ${totals.tag_links}`)
for (const item of topTags) {
  console.log(`- ${item.name}: ${item.links}`)
}
