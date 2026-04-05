import express from 'express'
import controllers from '../controllers/index.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const ingredients = await controllers.ingredient.getIngredients()
    res.json(ingredients)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', async (req, res) => {
  try {
    const ingredient = req.body
    const created = await controllers.ingredient.addIngredient(ingredient)
    res.status(201).json(created)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.put('/:id', async (req, res) => {
  try {
    const payload = { ...req.body, id: Number(req.params.id) }
    await controllers.ingredient.updateIngredient(payload)
    res.status(200).json({ message: 'Ingredient updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.delete('/:id', async (req, res) => {
  try {
    const id = Number(req.params.id)
    await controllers.ingredient.deleteIngredient(id)
    res.status(200).json({ message: 'Ingredient deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
