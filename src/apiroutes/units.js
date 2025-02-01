import express from 'express'
import { getUnits, addUnit, updateUnit, deleteUnit } from '@/src/db/units.js'

const apiRouter = express.Router()

// Route to get all units
apiRouter.get('/', (req, res) => {
  try {
    const units = getUnits()
    res.json(units)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to add a new unit
apiRouter.post('/', (req, res) => {
  try {
    const unit = req.body
    addUnit(unit)
    res.status(201).json({ message: 'Unit added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to update a unit
apiRouter.put('/:id', (req, res) => {
  try {
    const id = req.params.id
    const unit = req.body
    updateUnit(id, unit)
    res.status(200).json({ message: 'Unit updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to delete a unit
apiRouter.delete('/:id', (req, res) => {
  try {
    const id = req.params.id
    deleteUnit(id)
    res.status(200).json({ message: 'Unit deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
