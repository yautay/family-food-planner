import express from 'express'
import controllers from '../controllers/index.js'
import { requirePermission } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const recipes = await controllers.recipe.getRecipes(
      req.query.search,
      req.auth?.user ? req.auth : null,
    )
    res.json(recipes)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/nutrition-summaries', async (req, res) => {
  try {
    const summaries = await controllers.recipe.getRecipeNutritionSummaries(
      req.auth?.user ? req.auth : null,
    )
    res.json(summaries)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id', async (req, res) => {
  try {
    const recipeId = Number(req.params.id)
    const recipe = await controllers.recipe.getRecipeById(
      recipeId,
      req.auth?.user ? req.auth : null,
    )

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
    const recipe = await controllers.recipe.getRecipeById(
      recipeId,
      req.auth?.user ? req.auth : null,
    )

    if (!recipe) {
      res.status(404).json({ error: 'Recipe not found' })
      return
    }

    const ingredients = await controllers.recipe.getRecipeIngredients(
      recipeId,
      req.auth?.user ? req.auth : null,
    )
    res.json(ingredients?.ingredients ?? [])
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id/nutrition', async (req, res) => {
  try {
    const recipeId = Number(req.params.id)
    const nutrition = await controllers.recipe.getRecipeNutrition(
      recipeId,
      req.auth?.user ? req.auth : null,
    )

    if (!nutrition) {
      res.status(404).json({ error: 'Recipe not found' })
      return
    }

    res.json(nutrition)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', requirePermission('recipes.manage'), async (req, res) => {
  try {
    const created = await controllers.recipe.createRecipe(req.body, req.auth)
    res.status(201).json(created)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id', requirePermission('recipes.manage'), async (req, res) => {
  try {
    const recipeId = Number(req.params.id)
    const updated = await controllers.recipe.updateRecipe(recipeId, req.body, req.auth)

    if (!updated) {
      res.status(404).json({ error: 'Recipe not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.delete('/:id', requirePermission('recipes.manage'), async (req, res) => {
  try {
    const recipeId = Number(req.params.id)
    const deleted = await controllers.recipe.deleteRecipe(recipeId)

    if (!deleted) {
      res.status(404).json({ error: 'Recipe not found' })
      return
    }

    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

export default apiRouter
