import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import routes from './routes/index.js'
import { authOptional } from './middleware/auth.middleware.js'
import { getCorsOptions, getJsonBodyLimit } from './config/security.config.js'

export function createApp() {
  const app = express()

  app.disable('x-powered-by')

  app.use(
    helmet({
      contentSecurityPolicy: {
        directives: {
          defaultSrc: ["'self'"],
          connectSrc: ["'self'", 'http://localhost:3000', 'http://127.0.0.1:3000'],
          imgSrc: ["'self'", 'data:'],
          styleSrc: ["'self'", "'unsafe-inline'"],
          scriptSrc: ["'self'"],
          objectSrc: ["'none'"],
          frameAncestors: ["'none'"],
          baseUri: ["'self'"],
          formAction: ["'self'"],
        },
      },
      crossOriginEmbedderPolicy: false,
    }),
  )

  app.use(cors(getCorsOptions()))
  app.use(express.json({ limit: getJsonBodyLimit() }))
  app.use(authOptional)

  app.use('/api/auth', routes.auth)
  app.use('/api/units', routes.units)
  app.use('/api/tags', routes.tags)
  app.use('/api/ingredients', routes.ingredients)
  app.use('/api/packages', routes.packages)
  app.use('/api/products', routes.products)
  app.use('/api/recipes', routes.recipes)
  app.use('/api/meal-plans', routes.mealPlans)
  app.use('/api/day-plans', routes.dayPlans)
  app.use('/api/shopping-lists', routes.shoppingLists)

  app.use((_req, res) => {
    res.status(404).json({ error: 'Not found' })
  })

  app.use((error, _req, res, _next) => {
    const message = typeof error?.message === 'string' ? error.message : 'Internal server error'

    if (message.includes('CORS')) {
      res.status(403).json({ error: 'Forbidden origin' })
      return
    }

    res.status(500).json({ error: 'Internal server error' })
  })

  return app
}

export default createApp
