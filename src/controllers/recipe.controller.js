import catalogDb from '../db/catalog.js'

function normalizeSearch(search) {
  const value = typeof search === 'string' ? search.trim() : ''
  return value.length > 0 ? `%${value}%` : null
}

async function getRecipes(search) {
  const searchValue = normalizeSearch(search)

  return catalogDb
    .prepare(
      `
      SELECT
        r.id,
        r.name,
        r.normalized_name,
        r.source_file,
        COUNT(ri.id) AS ingredients_count
      FROM recipes r
      LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
      WHERE (? IS NULL OR r.name LIKE ? OR r.normalized_name LIKE ?)
      GROUP BY r.id
      ORDER BY r.name COLLATE NOCASE ASC
      `,
    )
    .all(searchValue, searchValue, searchValue)
}

async function getRecipeById(id) {
  return catalogDb
    .prepare(
      `
      SELECT
        r.id,
        r.name,
        r.normalized_name,
        r.source_file,
        COUNT(ri.id) AS ingredients_count
      FROM recipes r
      LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id
      WHERE r.id = ?
      GROUP BY r.id
      `,
    )
    .get(id)
}

async function getRecipeIngredients(recipeId) {
  return catalogDb
    .prepare(
      `
      SELECT
        ri.id,
        ri.recipe_id,
        p.id AS product_id,
        p.name AS product_name,
        ri.quantity,
        u.name AS unit_name,
        ri.grams,
        ri.note
      FROM recipe_ingredients ri
      INNER JOIN products p ON p.id = ri.product_id
      LEFT JOIN units u ON u.id = ri.unit_id
      WHERE ri.recipe_id = ?
      ORDER BY p.name COLLATE NOCASE ASC
      `,
    )
    .all(recipeId)
}

export default {
  getRecipes,
  getRecipeById,
  getRecipeIngredients,
}
