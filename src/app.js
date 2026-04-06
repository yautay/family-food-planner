import express from 'express'
import cors from 'cors'
import routes from './routes/index.js'
import { authOptional } from './middleware/auth.middleware.js'

export function createApp() {
  const app = express()

  app.use(cors())
  app.use(express.json())
  app.use(authOptional)

  app.use('/api/auth', routes.auth)
  app.use('/api/units', routes.units)
  app.use('/api/tags', routes.tags)
  app.use('/api/ingredients', routes.ingredients)
  app.use('/api/packages', routes.packages)
  app.use('/api/products', routes.products)
  app.use('/api/recipes', routes.recipes)
  app.use('/api/meal-plans', routes.mealPlans)
  app.use('/api/shopping-lists', routes.shoppingLists)

  return app
}

export default createApp
