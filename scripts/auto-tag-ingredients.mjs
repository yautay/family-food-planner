import Database from 'better-sqlite3'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')
const databasePath = path.resolve(projectRoot, process.env.DATABASE_PATH ?? 'database.db')

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

const db = new Database(databasePath)
db.pragma('foreign_keys = ON')

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

const ensureTag = db.prepare('INSERT OR IGNORE INTO tags(name) VALUES (?)')
for (const name of tagNames) {
  ensureTag.run(name)
}

const tags = db.prepare('SELECT id, name FROM tags ORDER BY name COLLATE NOCASE ASC').all()
const tagIdByName = new Map(tags.map((tag) => [normalize(tag.name), tag.id]))

const products = db.prepare('SELECT id, name FROM products ORDER BY name COLLATE NOCASE ASC').all()

const deleteProductTags = db.prepare('DELETE FROM product_tags')
const insertProductTag = db.prepare(
  'INSERT OR IGNORE INTO product_tags(product_id, tag_id) VALUES (?, ?)',
)

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

db.transaction(() => {
  deleteProductTags.run()

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

      insertProductTag.run(product.id, tagId)
    }
  }
})()

const totals = db
  .prepare(
    `
    SELECT
      COUNT(*) AS products,
      (SELECT COUNT(*) FROM product_tags) AS tag_links
    FROM products
    `,
  )
  .get()

const topTags = db
  .prepare(
    `
    SELECT t.name, COUNT(*) AS links
    FROM product_tags pt
    INNER JOIN tags t ON t.id = pt.tag_id
    GROUP BY t.id
    ORDER BY links DESC, t.name COLLATE NOCASE ASC
    `,
  )
  .all()

db.close()

console.log(`Tagged products: ${totals.products}`)
console.log(`Created tag links: ${totals.tag_links}`)
for (const item of topTags) {
  console.log(`- ${item.name}: ${item.links}`)
}
