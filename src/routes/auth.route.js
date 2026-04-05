import express from 'express'
import controllers from '../controllers/index.js'
import authService from '../services/auth.service.js'
import { requireAuth, requirePermission } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

apiRouter.get('/captcha-config', (req, res) => {
  res.json({
    turnstile_site_key: process.env.TURNSTILE_SITE_KEY ?? '',
  })
})

apiRouter.post('/register', async (req, res) => {
  try {
    const payload = await controllers.auth.register(req.body, req.ip)
    res.status(201).json(payload)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.post('/login', async (req, res) => {
  try {
    const payload = await controllers.auth.login(req.body)
    res.status(200).json(payload)
  } catch (error) {
    res.status(401).json({ error: error.message })
  }
})

apiRouter.post('/logout', requireAuth, async (req, res) => {
  authService.revokeSession(req.auth.token)
  res.status(204).send()
})

apiRouter.get('/me', requireAuth, async (req, res) => {
  const payload = await controllers.auth.getProfile(req.auth.user.id)
  res.json(payload)
})

apiRouter.post('/change-password', requireAuth, async (req, res) => {
  try {
    await controllers.auth.changePassword({
      userId: req.auth.user.id,
      currentPassword: req.body?.currentPassword,
      newPassword: req.body?.newPassword,
    })
    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.post('/forgot-password', async (req, res) => {
  try {
    await controllers.auth.forgotPassword(req.body, req.ip)
    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.post('/reset-password', async (req, res) => {
  try {
    await controllers.auth.resetPassword(req.body)
    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.get('/access-catalog', requireAuth, requirePermission('permissions.manage'), async (req, res) => {
  const payload = await controllers.auth.getAccessCatalog()
  res.json(payload)
})

apiRouter.get('/users', requireAuth, requirePermission('permissions.manage'), async (req, res) => {
  const users = await controllers.auth.listUsersWithPermissions()
  res.json(users)
})

apiRouter.put('/users/:id/roles', requireAuth, requirePermission('permissions.manage'), async (req, res) => {
  try {
    const userId = Number(req.params.id)
    const profile = await controllers.auth.updateUserRoles(userId, req.body?.roles)
    res.json(profile)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.put(
  '/users/:id/permissions',
  requireAuth,
  requirePermission('permissions.manage'),
  async (req, res) => {
    try {
      const userId = Number(req.params.id)
      const profile = await controllers.auth.updateUserPermissions(userId, req.body?.permissions)
      res.json(profile)
    } catch (error) {
      res.status(400).json({ error: error.message })
    }
  },
)

export default apiRouter
