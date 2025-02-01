import express from 'express'
import { getTags, addTag, updateTag, deleteTag } from '../db/tags.js'

const apiRouter = express.Router()

// Route to get all units
apiRouter.get('/', (req, res) => {
  try {
    const units = getTags()
    res.json(units)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to add a new unit
apiRouter.post('/', (req, res) => {
  try {
    const unit = req.body
    addTag(unit)
    res.status(201).json({ message: 'Tag added successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to update a unit
apiRouter.put('/:id', (req, res) => {
  try {
    updateTag(req.body)
    res.status(200).json({ message: 'Tag updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// Route to delete a unit
apiRouter.delete('/:id', (req, res) => {
  try {
    const id = req.params.id
    deleteTag(id)
    res.status(200).json({ message: 'Tag deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
