import tagController from './tag.controller.js'
import unitController from './unit.controller.js'
import ingredientController from './ingredient.controller.js'
import productController from './product.controller.js'
import recipeController from './recipe.controller.js'

const controllers = {}

controllers.tag = tagController
controllers.unit = unitController
controllers.ingredient = ingredientController
controllers.product = productController
controllers.recipe = recipeController

export default controllers
