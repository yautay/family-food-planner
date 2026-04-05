import express from 'express'
import controllers from '../controllers/index.js'
import { requirePermission } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const units = await controllers.unit.getUnits()
    res.json(units)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', requirePermission('catalog.write'), async (req, res) => {
  try {
    const unit = req.body
    const created = await controllers.unit.addUnit(unit)
    res.status(201).json(created)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.put('/:id', requirePermission('catalog.write'), async (req, res) => {
  try {
    const payload = { ...req.body, id: Number(req.params.id) }
    await controllers.unit.updateUnit(payload)
    res.status(200).json({ message: 'Unit updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.delete('/:id', requirePermission('catalog.write'), async (req, res) => {
  try {
    const id = Number(req.params.id)
    await controllers.unit.deleteUnit(id)
    res.status(200).json({ message: 'Unit deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
