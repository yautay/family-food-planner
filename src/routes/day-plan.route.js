import express from 'express'
import controllers from '../controllers/index.js'
import { requireAuth } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/', requireAuth, async (req, res) => {
  try {
    const dayPlans = await controllers.dayPlan.listDayPlans(req.auth.user)
    res.json(dayPlans)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id', requireAuth, async (req, res) => {
  try {
    const dayPlanId = Number(req.params.id)
    const dayPlan = await controllers.dayPlan.getDayPlanById(dayPlanId, req.auth.user)

    if (!dayPlan) {
      res.status(404).json({ error: 'Day plan not found' })
      return
    }

    res.json(dayPlan)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', requireAuth, async (req, res) => {
  try {
    const created = await controllers.dayPlan.createDayPlan(req.body, req.auth.user)
    res.status(201).json(created)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id', requireAuth, async (req, res) => {
  try {
    const dayPlanId = Number(req.params.id)
    const updated = await controllers.dayPlan.updateDayPlan(dayPlanId, req.body, req.auth.user)

    if (!updated) {
      res.status(404).json({ error: 'Day plan not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.delete('/:id', requireAuth, async (req, res) => {
  try {
    const dayPlanId = Number(req.params.id)
    const deleted = await controllers.dayPlan.deleteDayPlan(dayPlanId, req.auth.user)

    if (!deleted) {
      res.status(404).json({ error: 'Day plan not found' })
      return
    }

    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id/meals', requireAuth, async (req, res) => {
  try {
    const dayPlanId = Number(req.params.id)
    const updated = await controllers.dayPlan.replaceDayPlanMeals(
      dayPlanId,
      req.body?.meals,
      req.auth.user,
    )

    if (!updated) {
      res.status(404).json({ error: 'Day plan not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

export default apiRouter
