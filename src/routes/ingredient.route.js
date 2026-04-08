import express from 'express'
import controllers from '../controllers/index.js'
import { requirePermission } from '../middleware/auth.middleware.js'
import { validate } from '../middleware/validate.middleware.js'
import { schemas } from '../validation/schemas.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const ingredients = await controllers.ingredient.getIngredients()
    res.json(ingredients)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post(
  '/',
  requirePermission('catalog.write'),
  validate({ body: schemas.ingredientBody }),
  async (req, res) => {
    try {
      const ingredient = req.body
      const created = await controllers.ingredient.addIngredient(ingredient)
      res.status(201).json(created)
    } catch (error) {
      res.status(500).json({ error: error.message })
    }
  },
)

apiRouter.put(
  '/:id',
  requirePermission('catalog.write'),
  validate({ params: schemas.idParams, body: schemas.ingredientBody }),
  async (req, res) => {
    try {
      const payload = { ...req.body, id: Number(req.params.id) }
      await controllers.ingredient.updateIngredient(payload)
      res.status(200).json({ message: 'Ingredient updated successfully' })
    } catch (error) {
      res.status(500).json({ error: error.message })
    }
  },
)

apiRouter.delete(
  '/:id',
  requirePermission('catalog.write'),
  validate({ params: schemas.idParams }),
  async (req, res) => {
    try {
      const id = Number(req.params.id)
      await controllers.ingredient.deleteIngredient(id)
      res.status(200).json({ message: 'Ingredient deleted successfully' })
    } catch (error) {
      res.status(500).json({ error: error.message })
    }
  },
)

export default apiRouter
