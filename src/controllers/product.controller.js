import catalogDb from '../db/catalog.js'

function normalizeSearch(search) {
  const value = typeof search === 'string' ? search.trim() : ''
  return value.length > 0 ? `%${value}%` : null
}

async function getProducts(search) {
  const searchValue = normalizeSearch(search)

  return catalogDb
    .prepare(
      `
      SELECT
        p.id,
        p.name,
        p.normalized_name,
        p.default_unit_id,
        u.name AS default_unit_name,
        COUNT(DISTINCT ri.recipe_id) AS recipes_count
      FROM products p
      LEFT JOIN units u ON u.id = p.default_unit_id
      LEFT JOIN recipe_ingredients ri ON ri.product_id = p.id
      WHERE (? IS NULL OR p.name LIKE ? OR p.normalized_name LIKE ?)
      GROUP BY p.id
      ORDER BY p.name COLLATE NOCASE ASC
      `,
    )
    .all(searchValue, searchValue, searchValue)
}

export default {
  getProducts,
}
