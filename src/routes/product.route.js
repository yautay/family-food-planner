import express from 'express'
import controllers from '../controllers/index.js'
import { validate } from '../middleware/validate.middleware.js'
import { schemas } from '../validation/schemas.js'

const apiRouter = express.Router()

apiRouter.get('/', validate({ query: schemas.searchQuery }), async (req, res) => {
  try {
    const products = await controllers.product.getProducts(req.query.search)
    res.json(products)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

export default apiRouter
