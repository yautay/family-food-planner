import { Sequelize } from 'sequelize'
import tagModel from './tag.model.js'
import unitModel from './unit.model.js'
import ingredientModel from './ingredient.model.js'
import userModel from './user.model.js'
import productModel from './product.model.js'
import recipeIngredientModel from './recipe-ingredient.model.js'
import auditLogModel from './audit-log.model.js'

const models = {}

models.tag = tagModel
models.ingredient = ingredientModel
models.unit = unitModel
models.user = userModel
models.product = productModel
models.recipeIngredient = recipeIngredientModel
models.auditLog = auditLogModel

models.product.belongsTo(models.unit, {
  foreignKey: 'default_unit_id',
  as: 'defaultUnit',
})

models.product.hasMany(models.recipeIngredient, {
  foreignKey: 'product_id',
  as: 'recipeIngredients',
})

models.recipeIngredient.belongsTo(models.product, {
  foreignKey: 'product_id',
  as: 'product',
})

models.auditLog.belongsTo(models.user, {
  foreignKey: 'actor_user_id',
  as: 'actor',
})

models.Op = Sequelize.Op

export default models
