import catalogDb from '../db/catalog.js'
import { hashPassword, verifyPassword } from '../lib/password.js'
import { createOpaqueToken, sha256Hex } from '../lib/token.js'

const SESSION_TTL_DAYS = 30
const RESET_TTL_MINUTES = 30

function nowIso() {
  return new Date().toISOString()
}

function addDaysIso(days) {
  const value = new Date()
  value.setDate(value.getDate() + days)
  return value.toISOString()
}

function addMinutesIso(minutes) {
  const value = new Date()
  value.setMinutes(value.getMinutes() + minutes)
  return value.toISOString()
}

function normalizeIdentity(identity) {
  return typeof identity === 'string' ? identity.trim().toLowerCase() : ''
}

function mapUser(row) {
  if (!row) {
    return null
  }

  return {
    id: row.id,
    username: row.username,
    email: row.email,
    is_active: row.is_active === 1,
    must_change_password: row.must_change_password === 1,
    created_at: row.created_at,
    updated_at: row.updated_at,
  }
}

function getUserById(userId) {
  return catalogDb.prepare('SELECT * FROM users WHERE id = ?').get(userId)
}

function getUserByIdentity(identity) {
  const value = normalizeIdentity(identity)
  return catalogDb
    .prepare('SELECT * FROM users WHERE lower(username) = ? OR lower(email) = ?')
    .get(value, value)
}

function getEffectivePermissions(userId) {
  const rolePermissions = catalogDb
    .prepare(
      `
      SELECT DISTINCT p.name
      FROM user_roles ur
      INNER JOIN role_permissions rp ON rp.role_id = ur.role_id
      INNER JOIN permissions p ON p.id = rp.permission_id
      WHERE ur.user_id = ?
      `,
    )
    .all(userId)
    .map((row) => row.name)

  const directPermissions = catalogDb
    .prepare(
      `
      SELECT p.name, up.allow
      FROM user_permissions up
      INNER JOIN permissions p ON p.id = up.permission_id
      WHERE up.user_id = ?
      `,
    )
    .all(userId)

  const permissions = new Set(rolePermissions)

  for (const permission of directPermissions) {
    if (permission.allow === 1) {
      permissions.add(permission.name)
    } else {
      permissions.delete(permission.name)
    }
  }

  return permissions
}

function getUserRoles(userId) {
  return catalogDb
    .prepare(
      `
      SELECT r.name
      FROM user_roles ur
      INNER JOIN roles r ON r.id = ur.role_id
      WHERE ur.user_id = ?
      ORDER BY r.name ASC
      `,
    )
    .all(userId)
    .map((row) => row.name)
}

function createSession(userId) {
  const token = createOpaqueToken()
  const tokenHash = sha256Hex(token)
  const expiresAt = addDaysIso(SESSION_TTL_DAYS)

  catalogDb
    .prepare(
      `
      INSERT INTO auth_sessions(user_id, token_hash, expires_at, last_seen_at)
      VALUES (?, ?, ?, ?)
      `,
    )
    .run(userId, tokenHash, expiresAt, nowIso())

  return {
    token,
    expires_at: expiresAt,
  }
}

function getSessionByToken(token) {
  if (!token) {
    return null
  }

  const tokenHash = sha256Hex(token)
  return catalogDb
    .prepare(
      `
      SELECT s.*, u.username, u.email, u.is_active, u.must_change_password, u.created_at, u.updated_at
      FROM auth_sessions s
      INNER JOIN users u ON u.id = s.user_id
      WHERE s.token_hash = ?
      `,
    )
    .get(tokenHash)
}

function revokeSession(token) {
  if (!token) {
    return
  }

  catalogDb
    .prepare('UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ?')
    .run(nowIso(), sha256Hex(token))
}

function revokeUserSessions(userId) {
  catalogDb
    .prepare('UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL')
    .run(nowIso(), userId)
}

function removeExpiredSessions() {
  catalogDb.prepare('DELETE FROM auth_sessions WHERE expires_at <= ?').run(nowIso())
}

function getAuthContextFromToken(token) {
  removeExpiredSessions()
  const session = getSessionByToken(token)
  if (!session) {
    return null
  }

  if (session.revoked_at || session.expires_at <= nowIso() || session.is_active !== 1) {
    return null
  }

  catalogDb
    .prepare('UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?')
    .run(nowIso(), session.id)

  const user = mapUser(session)
  const roles = getUserRoles(user.id)
  const permissions = getEffectivePermissions(user.id)

  return {
    user,
    roles,
    permissions,
  }
}

function registerUser({ username, email, password }) {
  const normalizedUsername = typeof username === 'string' ? username.trim() : ''
  const normalizedEmail = typeof email === 'string' ? email.trim().toLowerCase() : ''

  if (!normalizedUsername || !normalizedEmail || !password) {
    throw new Error('Username, email and password are required')
  }

  const passwordHash = hashPassword(password)

  const result = catalogDb
    .prepare(
      `
      INSERT INTO users(username, email, password_hash)
      VALUES (?, ?, ?)
      `,
    )
    .run(normalizedUsername, normalizedEmail, passwordHash)

  const userId = Number(result.lastInsertRowid)

  catalogDb
    .prepare(
      `
      INSERT OR IGNORE INTO user_roles(user_id, role_id)
      SELECT ?, id FROM roles WHERE name = 'user'
      `,
    )
    .run(userId)

  return mapUser(getUserById(userId))
}

function login({ identity, password }) {
  const user = getUserByIdentity(identity)

  if (!user || user.is_active !== 1) {
    throw new Error('Invalid credentials')
  }

  if (!verifyPassword(password, user.password_hash)) {
    throw new Error('Invalid credentials')
  }

  const session = createSession(user.id)
  const roles = getUserRoles(user.id)
  const permissions = getEffectivePermissions(user.id)

  return {
    token: session.token,
    expires_at: session.expires_at,
    user: mapUser(user),
    roles,
    permissions: Array.from(permissions).sort((left, right) => left.localeCompare(right)),
  }
}

function changePassword({ userId, currentPassword, newPassword }) {
  const user = getUserById(userId)

  if (!user) {
    throw new Error('User not found')
  }

  if (!verifyPassword(currentPassword, user.password_hash)) {
    throw new Error('Current password is invalid')
  }

  const newHash = hashPassword(newPassword)

  catalogDb
    .prepare(
      `
      UPDATE users
      SET password_hash = ?, must_change_password = 0, updated_at = ?
      WHERE id = ?
      `,
    )
    .run(newHash, nowIso(), userId)

  revokeUserSessions(userId)
}

function createPasswordResetToken(email) {
  const normalizedEmail = typeof email === 'string' ? email.trim().toLowerCase() : ''
  const user = catalogDb.prepare('SELECT * FROM users WHERE lower(email) = ?').get(normalizedEmail)

  if (!user || user.is_active !== 1) {
    return null
  }

  const rawToken = createOpaqueToken(40)
  const tokenHash = sha256Hex(rawToken)

  catalogDb
    .prepare(
      `
      INSERT INTO password_reset_tokens(user_id, token_hash, expires_at)
      VALUES (?, ?, ?)
      `,
    )
    .run(user.id, tokenHash, addMinutesIso(RESET_TTL_MINUTES))

  return {
    token: rawToken,
    user: mapUser(user),
  }
}

function resetPassword({ token, newPassword }) {
  const tokenHash = sha256Hex(token)
  const resetToken = catalogDb
    .prepare(
      `
      SELECT *
      FROM password_reset_tokens
      WHERE token_hash = ?
      `,
    )
    .get(tokenHash)

  if (!resetToken || resetToken.used_at || resetToken.expires_at <= nowIso()) {
    throw new Error('Reset token is invalid or expired')
  }

  const newHash = hashPassword(newPassword)

  catalogDb.transaction(() => {
    catalogDb
      .prepare('UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?')
      .run(newHash, nowIso(), resetToken.user_id)

    catalogDb
      .prepare('UPDATE password_reset_tokens SET used_at = ? WHERE id = ?')
      .run(nowIso(), resetToken.id)

    revokeUserSessions(resetToken.user_id)
  })()
}

function getUserProfile(userId) {
  const user = mapUser(getUserById(userId))
  if (!user) {
    return null
  }

  const roles = getUserRoles(userId)
  const permissions = Array.from(getEffectivePermissions(userId)).sort((left, right) =>
    left.localeCompare(right),
  )

  return {
    user,
    roles,
    permissions,
  }
}

function listUsersWithPermissions() {
  const users = catalogDb
    .prepare('SELECT id, username, email, is_active, must_change_password, created_at, updated_at FROM users ORDER BY username COLLATE NOCASE ASC')
    .all()

  return users.map((row) => {
    const user = mapUser(row)
    return {
      ...user,
      roles: getUserRoles(row.id),
      permissions: Array.from(getEffectivePermissions(row.id)).sort((left, right) =>
        left.localeCompare(right),
      ),
    }
  })
}

function setUserRoles(userId, roleNames) {
  const names = Array.isArray(roleNames) ? roleNames : []

  catalogDb.transaction(() => {
    catalogDb.prepare('DELETE FROM user_roles WHERE user_id = ?').run(userId)

    for (const roleName of names) {
      catalogDb
        .prepare(
          `
          INSERT OR IGNORE INTO user_roles(user_id, role_id)
          SELECT ?, id FROM roles WHERE name = ?
          `,
        )
        .run(userId, roleName)
    }
  })()
}

function setUserPermissions(userId, permissions) {
  const values = Array.isArray(permissions) ? permissions : []

  catalogDb.transaction(() => {
    catalogDb.prepare('DELETE FROM user_permissions WHERE user_id = ?').run(userId)

    for (const permission of values) {
      if (!permission?.name) {
        continue
      }

      catalogDb
        .prepare(
          `
          INSERT OR IGNORE INTO user_permissions(user_id, permission_id, allow)
          SELECT ?, id, ? FROM permissions WHERE name = ?
          `,
        )
        .run(userId, permission.allow === false ? 0 : 1, permission.name)
    }
  })()
}

function getAvailableRoles() {
  return catalogDb.prepare('SELECT name, description FROM roles ORDER BY name ASC').all()
}

function getAvailablePermissions() {
  return catalogDb
    .prepare('SELECT name, description FROM permissions ORDER BY name ASC')
    .all()
}

export default {
  registerUser,
  login,
  changePassword,
  createPasswordResetToken,
  resetPassword,
  getUserProfile,
  getAuthContextFromToken,
  revokeSession,
  listUsersWithPermissions,
  setUserRoles,
  setUserPermissions,
  getAvailableRoles,
  getAvailablePermissions,
}
