import express from 'express'
import controllers from '../controllers/index.js'
import { requirePermission } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/types', async (_req, res) => {
  try {
    const packageTypes = await controllers.package.getPackageTypes()
    res.json(packageTypes)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/', async (_req, res) => {
  try {
    const packages = await controllers.package.getPackages()
    res.json(packages)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', requirePermission('catalog.write'), async (req, res) => {
  try {
    const created = await controllers.package.addPackage(req.body)
    res.status(201).json(created)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id', requirePermission('catalog.write'), async (req, res) => {
  try {
    const payload = { ...req.body, id: Number(req.params.id) }
    const changes = await controllers.package.updatePackage(payload)

    if (changes === 0) {
      res.status(404).json({ error: 'Package not found' })
      return
    }

    res.status(200).json({ message: 'Package updated successfully' })
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.delete('/:id', requirePermission('catalog.write'), async (req, res) => {
  try {
    const changes = await controllers.package.deletePackage(Number(req.params.id))

    if (changes === 0) {
      res.status(404).json({ error: 'Package not found' })
      return
    }

    res.status(200).json({ message: 'Package deleted successfully' })
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

export default apiRouter
