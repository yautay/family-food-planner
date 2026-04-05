import express from 'express'
import controllers from '../controllers/index.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const recipes = await controllers.recipe.getRecipes(req.query.search)
    res.json(recipes)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id', async (req, res) => {
  try {
    const recipeId = Number(req.params.id)
    const recipe = await controllers.recipe.getRecipeById(recipeId)

    if (!recipe) {
      res.status(404).json({ error: 'Recipe not found' })
      return
    }

    res.json(recipe)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id/ingredients', async (req, res) => {
  try {
    const recipeId = Number(req.params.id)
    const recipe = await controllers.recipe.getRecipeById(recipeId)

    if (!recipe) {
      res.status(404).json({ error: 'Recipe not found' })
      return
    }

    const ingredients = await controllers.recipe.getRecipeIngredients(recipeId)
    res.json(ingredients)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
