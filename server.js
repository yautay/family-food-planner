// server.js
import express from 'express'
import cors from 'cors'
import { addFoodItem, getUnits, addUnit, updateUnit, deleteUnit } from './src/db.js'

const app = express()
const port = 3000

app.use(cors())
app.use(express.json())

// Route to get all units
app.get('/api/units', (req, res) => {
  try {
    const units = getUnits()
    res.json(units)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to add a new unit
app.post('/api/units', (req, res) => {
  try {
    const unit = req.body
    addUnit(unit)
    res.status(201).json({ message: 'Unit added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to update a unit
app.put('/api/units/:id', (req, res) => {
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
app.delete('/api/units/:id', (req, res) => {
  try {
    const id = req.params.id
    deleteUnit(id)
    res.status(200).json({ message: 'Unit deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to add a new food item
app.post('/api/food-items', (req, res) => {
  try {
    const item = req.body
    addFoodItem(item)
    res.status(201).json({ message: 'Food item added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`)
})
