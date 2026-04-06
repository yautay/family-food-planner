import express from 'express'
import cors from 'cors'
import routes from './src/routes/index.js'
import { initDatabase } from './src/db/sequelize.js'
import { authOptional } from './src/middleware/auth.middleware.js'

const app = express()
const port = 3000

app.use(cors())
app.use(express.json())
app.use(authOptional)

app.use('/api/auth', routes.auth)
app.use('/api/units', routes.units)
app.use('/api/tags', routes.tags)
app.use('/api/ingredients', routes.ingredients)
app.use('/api/products', routes.products)
app.use('/api/recipes', routes.recipes)
app.use('/api/meal-plans', routes.mealPlans)

async function startServer() {
  await initDatabase()

  app.listen(port, () => {
    console.log(`Server is running on http://localhost:${port}`)
  })
}

startServer().catch((error) => {
  console.error('Server startup failed:', error)
  process.exit(1)
})
