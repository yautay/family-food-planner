import express from 'express'
import controllers from '../controllers/index.js'
import { requireAuth } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/', requireAuth, async (req, res) => {
  try {
    const shoppingLists = await controllers.shoppingList.listShoppingLists(req.auth.user)
    res.json(shoppingLists)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.get('/:id', requireAuth, async (req, res) => {
  try {
    const shoppingListId = Number(req.params.id)
    const shoppingList = await controllers.shoppingList.getShoppingListById(
      shoppingListId,
      req.auth.user,
    )

    if (!shoppingList) {
      res.status(404).json({ error: 'Shopping list not found' })
      return
    }

    res.json(shoppingList)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

apiRouter.post('/', requireAuth, async (req, res) => {
  try {
    const created = await controllers.shoppingList.createShoppingList(req.body, req.auth.user)
    res.status(201).json(created)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id', requireAuth, async (req, res) => {
  try {
    const shoppingListId = Number(req.params.id)
    const updated = await controllers.shoppingList.updateShoppingList(
      shoppingListId,
      req.body,
      req.auth.user,
    )

    if (!updated) {
      res.status(404).json({ error: 'Shopping list not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.delete('/:id', requireAuth, async (req, res) => {
  try {
    const shoppingListId = Number(req.params.id)
    const deleted = await controllers.shoppingList.deleteShoppingList(shoppingListId, req.auth.user)

    if (!deleted) {
      res.status(404).json({ error: 'Shopping list not found' })
      return
    }

    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.post('/:id/items', requireAuth, async (req, res) => {
  try {
    const shoppingListId = Number(req.params.id)
    const updated = await controllers.shoppingList.addShoppingListItem(
      shoppingListId,
      req.body,
      req.auth.user,
    )

    if (!updated) {
      res.status(404).json({ error: 'Shopping list not found' })
      return
    }

    res.status(201).json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put('/:id/items/:itemId', requireAuth, async (req, res) => {
  try {
    const shoppingListId = Number(req.params.id)
    const itemId = Number(req.params.itemId)
    const updated = await controllers.shoppingList.updateShoppingListItem(
      shoppingListId,
      itemId,
      req.body,
      req.auth.user,
    )

    if (!updated) {
      res.status(404).json({ error: 'Shopping list or item not found' })
      return
    }

    res.json(updated)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.delete('/:id/items/:itemId', requireAuth, async (req, res) => {
  try {
    const shoppingListId = Number(req.params.id)
    const itemId = Number(req.params.itemId)
    const deleted = await controllers.shoppingList.deleteShoppingListItem(
      shoppingListId,
      itemId,
      req.auth.user,
    )

    if (!deleted) {
      res.status(404).json({ error: 'Shopping list or item not found' })
      return
    }

    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

export default apiRouter
