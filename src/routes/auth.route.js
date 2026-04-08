import express from 'express'
import rateLimit from 'express-rate-limit'
import controllers from '../controllers/index.js'
import authService from '../services/auth.service.js'
import auditService from '../services/audit.service.js'
import { requireAuth, requirePermission } from '../middleware/auth.middleware.js'

const apiRouter = express.Router()

const authWriteLimiter = rateLimit({
  windowMs: Number(process.env.AUTH_RATE_LIMIT_WINDOW_MS ?? 10 * 60 * 1000),
  max: Number(process.env.AUTH_RATE_LIMIT_MAX ?? 30),
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { error: 'Too many authentication requests. Try again later.' },
})

const loginLimiter = rateLimit({
  windowMs: Number(process.env.AUTH_LOGIN_RATE_LIMIT_WINDOW_MS ?? 10 * 60 * 1000),
  max: Number(process.env.AUTH_LOGIN_RATE_LIMIT_MAX ?? 10),
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { error: 'Too many login attempts. Try again later.' },
})

apiRouter.get('/captcha-config', (req, res) => {
  res.json({
    turnstile_site_key: process.env.TURNSTILE_SITE_KEY ?? '',
  })
})

apiRouter.post('/register', authWriteLimiter, async (req, res) => {
  try {
    const payload = await controllers.auth.register(req.body, req.ip)
    res.status(201).json(payload)
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.post('/login', loginLimiter, async (req, res) => {
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

apiRouter.post('/forgot-password', authWriteLimiter, async (req, res) => {
  try {
    await controllers.auth.forgotPassword(req.body, req.ip)
    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.post('/reset-password', authWriteLimiter, async (req, res) => {
  try {
    await controllers.auth.resetPassword(req.body)
    res.status(204).send()
  } catch (error) {
    res.status(400).json({ error: error.message })
  }
})

apiRouter.get(
  '/access-catalog',
  requireAuth,
  requirePermission('permissions.manage'),
  async (req, res) => {
    const payload = await controllers.auth.getAccessCatalog()
    res.json(payload)
  },
)

apiRouter.get('/users', requireAuth, requirePermission('permissions.manage'), async (req, res) => {
  const users = await controllers.auth.listUsersWithPermissions()
  res.json(users)
})

apiRouter.get(
  '/audit-logs',
  requireAuth,
  requirePermission('permissions.manage'),
  async (req, res) => {
    const logs = auditService.listAuditLogs({ limit: req.query.limit })
    res.json(logs)
  },
)

apiRouter.put(
  '/users/:id/roles',
  requireAuth,
  requirePermission('permissions.manage'),
  async (req, res) => {
    try {
      const userId = Number(req.params.id)
      const profileBefore = authService.getUserProfile(userId)

      if (!profileBefore) {
        res.status(404).json({ error: 'User not found' })
        return
      }

      const profile = await controllers.auth.updateUserRoles(userId, req.body?.roles)

      if (!profile) {
        res.status(404).json({ error: 'User not found' })
        return
      }

      auditService.logEvent({
        actorUserId: req.auth.user.id,
        action: 'acl.roles.updated',
        targetType: 'user',
        targetId: userId,
        meta: {
          username: profile.user.username,
          before_roles: profileBefore.roles,
          after_roles: profile.roles,
        },
      })

      res.json(profile)
    } catch (error) {
      res.status(400).json({ error: error.message })
    }
  },
)

apiRouter.put(
  '/users/:id/permissions',
  requireAuth,
  requirePermission('permissions.manage'),
  async (req, res) => {
    try {
      const userId = Number(req.params.id)
      const profileBefore = authService.getUserProfile(userId)

      if (!profileBefore) {
        res.status(404).json({ error: 'User not found' })
        return
      }

      const profile = await controllers.auth.updateUserPermissions(userId, req.body?.permissions)

      if (!profile) {
        res.status(404).json({ error: 'User not found' })
        return
      }

      auditService.logEvent({
        actorUserId: req.auth.user.id,
        action: 'acl.permissions.updated',
        targetType: 'user',
        targetId: userId,
        meta: {
          username: profile.user.username,
          before_permissions: profileBefore.permissions,
          after_permissions: profile.permissions,
        },
      })

      res.json(profile)
    } catch (error) {
      res.status(400).json({ error: error.message })
    }
  },
)

export default apiRouter
