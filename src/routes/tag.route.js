import express from 'express'
import controllers from '../controllers/index.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const tags = await controllers.tag.getTags()
    res.json(tags)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', async (req, res) => {
  try {
    const tag = req.body
    const created = await controllers.tag.addTag(tag)
    res.status(201).json(created)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.put('/:id', async (req, res) => {
  try {
    const payload = { ...req.body, id: Number(req.params.id) }
    await controllers.tag.updateTag(payload)
    res.status(200).json({ message: 'Tag updated successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.delete('/:id', async (req, res) => {
  try {
    const id = Number(req.params.id)
    await controllers.tag.deleteTag(id)
    res.status(200).json({ message: 'Tag deleted successfully' })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
