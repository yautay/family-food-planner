import express from 'express'
import controllers from '../controllers/index.js'
import { requireAuth } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/', requireAuth, async (req, res) => {
  try {
    const mealPlans = await controllers.mealPlan.listMealPlans(req.auth.user)
    res.json(mealPlans)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id', requireAuth, async (req, res) => {
  try {
    const mealPlanId = Number(req.params.id)
    const mealPlan = await controllers.mealPlan.getMealPlanById(mealPlanId, req.auth.user)

    if (!mealPlan) {
      res.status(404).json({ error: 'Meal plan not found' })
      return
    }

    res.json(mealPlan)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', requireAuth, async (req, res) => {
  try {
    const created = await controllers.mealPlan.createMealPlan(req.body, req.auth.user)
    res.status(201).json(created)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id', requireAuth, async (req, res) => {
  try {
    const mealPlanId = Number(req.params.id)
    const updated = await controllers.mealPlan.updateMealPlan(mealPlanId, req.body, req.auth.user)

    if (!updated) {
      res.status(404).json({ error: 'Meal plan not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.delete('/:id', requireAuth, async (req, res) => {
  try {
    const mealPlanId = Number(req.params.id)
    const deleted = await controllers.mealPlan.deleteMealPlan(mealPlanId, req.auth.user)

    if (!deleted) {
      res.status(404).json({ error: 'Meal plan not found' })
      return
    }

    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id/entries', requireAuth, async (req, res) => {
  try {
    const mealPlanId = Number(req.params.id)
    const updated = await controllers.mealPlan.replaceMealPlanEntries(
      mealPlanId,
      req.body?.entries,
      req.auth.user,
    )

    if (!updated) {
      res.status(404).json({ error: 'Meal plan not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

export default apiRouter
