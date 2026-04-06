import ingredientRouter from './ingredient.route.js'
import unitRoute from './unit.route.js'
import tagRoute from './tag.route.js'
import productRoute from './product.route.js'
import recipeRoute from './recipe.route.js'
import packageRoute from './package.route.js'
import authRoute from './auth.route.js'
import mealPlanRoute from './meal-plan.route.js'
import shoppingListRoute from './shopping-list.route.js'

const routes = {}

routes.ingredients = ingredientRouter
routes.units = unitRoute
routes.tags = tagRoute
routes.products = productRoute
routes.recipes = recipeRoute
routes.packages = packageRoute
routes.auth = authRoute
routes.mealPlans = mealPlanRoute
routes.shoppingLists = shoppingListRoute

export default routes
