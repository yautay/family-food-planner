import ingredientRouter from './ingredient.route.js'
import unitRoute from './unit.route.js'
import tagRoute from './tag.route.js'

const routes = {}

routes.ingredients = ingredientRouter
routes.units = unitRoute
routes.tags = tagRoute

export default routes
