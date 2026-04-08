import { Op, col, fn, literal } from 'sequelize'
import models from '../models/index.js'

function normalizeSearch(search) {
  const value = typeof search === 'string' ? search.trim() : ''
  return value.length > 0 ? `%${value}%` : null
}

async function getProducts(search) {
  const searchValue = normalizeSearch(search)
  const where = searchValue
    ? {
        [Op.or]: [
          { name: { [Op.like]: searchValue } },
          { normalized_name: { [Op.like]: searchValue } },
        ],
      }
    : undefined

  return models.product.findAll({
    attributes: [
      'id',
      'name',
      'normalized_name',
      'default_unit_id',
      [col('defaultUnit.name'), 'default_unit_name'],
      [fn('COUNT', fn('DISTINCT', col('recipeIngredients.recipe_id'))), 'recipes_count'],
    ],
    include: [
      {
        model: models.unit,
        as: 'defaultUnit',
        attributes: [],
        required: false,
      },
      {
        model: models.recipeIngredient,
        as: 'recipeIngredients',
        attributes: [],
        required: false,
      },
    ],
    where,
    group: ['Product.id', 'defaultUnit.id'],
    order: [[literal('Product.name COLLATE NOCASE'), 'ASC']],
    raw: true,
    subQuery: false,
  })
}

export default {
  getProducts,
}
