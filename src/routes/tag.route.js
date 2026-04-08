import express from 'express'
import controllers from '../controllers/index.js'
import { requirePermission } from '../middleware/auth.middleware.js'
import { validate } from '../middleware/validate.middleware.js'
import { schemas } from '../validation/schemas.js'

const apiRouter = express.Router()

apiRouter.get('/', async (req, res) => {
  try {
    const tags = await controllers.tag.getTags()
    res.json(tags)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post(
  '/',
  requirePermission('catalog.write'),
  validate({ body: schemas.nameBody }),
  async (req, res) => {
    try {
      const tag = req.body
      const created = await controllers.tag.addTag(tag)
      res.status(201).json(created)
    } catch (error) {
      res.status(500).json({ error: error.message })
    }
  },
)

apiRouter.put(
  '/:id',
  requirePermission('catalog.write'),
  validate({ params: schemas.idParams, body: schemas.nameBody }),
  async (req, res) => {
    try {
      const payload = { ...req.body, id: Number(req.params.id) }
      await controllers.tag.updateTag(payload)
      res.status(200).json({ message: 'Tag updated successfully' })
    } catch (error) {
      res.status(500).json({ error: error.message })
    }
  },
)

apiRouter.delete(
  '/:id',
  requirePermission('catalog.write'),
  validate({ params: schemas.idParams }),
  async (req, res) => {
    try {
      const id = Number(req.params.id)
      await controllers.tag.deleteTag(id)
      res.status(200).json({ message: 'Tag deleted successfully' })
    } catch (error) {
      res.status(500).json({ error: error.message })
    }
  },
)

export default apiRouter
