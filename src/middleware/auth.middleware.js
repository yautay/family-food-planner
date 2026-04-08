import authService from '../services/auth.service.js'

function extractBearerToken(authorizationHeader) {
  if (!authorizationHeader || typeof authorizationHeader !== 'string') {
    return null
  }

  const [scheme, token] = authorizationHeader.split(' ')
  if (scheme?.toLowerCase() !== 'bearer' || !token) {
    return null
  }

  return token.trim()
}

export async function authOptional(req, _res, next) {
  try {
    const token = extractBearerToken(req.headers.authorization)
    const context = await authService.getAuthContextFromToken(token)

    if (context) {
      req.auth = {
        token,
        user: context.user,
        roles: context.roles,
        permissions: context.permissions,
      }
    } else {
      req.auth = null
    }

    next()
  } catch (error) {
    next(error)
  }
}

export function requireAuth(req, res, next) {
  if (!req.auth?.user) {
    res.status(401).json({ error: 'Authentication required' })
    return
  }

  next()
}

export function requirePermission(permissionName) {
  return (req, res, next) => {
    if (!req.auth?.user) {
      res.status(401).json({ error: 'Authentication required' })
      return
    }

    if (!req.auth.permissions?.has(permissionName)) {
      res.status(403).json({ error: `Missing permission: ${permissionName}` })
      return
    }

    next()
  }
}
