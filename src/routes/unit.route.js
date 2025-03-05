import express from 'express'
import controllers from '../controllers/index.js'

const apiRouter = express.Router()

// Route to get all units
apiRouter.get('/', (req, res) => {
  try {
    const units = controllers.unit.getUnits()
    res.json(units)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to add a new unit
apiRouter.post('/', (req, res) => {
  try {
    const unit = req.body
    controllers.unit.addUnit(unit)
    res.status(201).json({ message: 'UnitModel added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to update a unit
apiRouter.put('/:id', (req, res) => {
  try {
    controllers.unit.updateUnit(req.body)
    res.status(200).json({ message: 'UnitModel updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to delete a unit
apiRouter.delete('/:id', (req, res) => {
  try {
    const id = req.params.id
    controllers.unit.deleteUnit(id)
    res.status(200).json({ message: 'UnitModel deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
