import express from 'express'
import controllers from '../controllers/index.js'

const apiRouter = express.Router()

// Route to get all ingredients
apiRouter.get('/', (req, res) => {
  try {
    const ingredients = controllers.ingredient.getIngredients()
    res.json(ingredients)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to add a new ingredient
apiRouter.post('/', (req, res) => {
  try {
    const ingredient = req.body
    controllers.ingredient.addIngredient(ingredient)
    res.status(201).json({ message: 'Ingredient added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to update an ingredient
apiRouter.put('/:id', (req, res) => {
  try {
    controllers.ingredient.updateIngredient(req.body)
    res.status(200).json({ message: 'Ingredient updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to delete an ingredient
apiRouter.delete('/:id', (req, res) => {
  try {
    const id = req.params.id
    controllers.ingredient.deleteIngredient(id)
    res.status(200).json({ message: 'Ingredient deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
