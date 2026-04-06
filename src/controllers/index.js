import tagController from './tag.controller.js'
import unitController from './unit.controller.js'
import ingredientController from './ingredient.controller.js'
import productController from './product.controller.js'
import recipeController from './recipe.controller.js'
import authController from './auth.controller.js'
import mealPlanController from './meal-plan.controller.js'
import shoppingListController from './shopping-list.controller.js'

const controllers = {}

controllers.tag = tagController
controllers.unit = unitController
controllers.ingredient = ingredientController
controllers.product = productController
controllers.recipe = recipeController
controllers.auth = authController
controllers.mealPlan = mealPlanController
controllers.shoppingList = shoppingListController

export default controllers
