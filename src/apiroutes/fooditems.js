import express from 'express'
import { addFoodItem } from '../db/foodItems.js'

const apiRouter = express.Router()

// Route to add a new food item
apiRouter.post('/', (req, res) => {
  try {
    const item = req.body
    addFoodItem(item)
    res.status(201).json({ message: 'Food item added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
