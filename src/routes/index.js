import ingredientRouter from './ingredient.route.js'
import unitRoute from './unit.route.js'
import tagRoute from './tag.route.js'
import productRoute from './product.route.js'
import recipeRoute from './recipe.route.js'

const routes = {}

routes.ingredients = ingredientRouter
routes.units = unitRoute
routes.tags = tagRoute
routes.products = productRoute
routes.recipes = recipeRoute

export default routes
