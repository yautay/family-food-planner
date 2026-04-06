// @vitest-environment node

import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import Database from 'better-sqlite3'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { hashPassword } from '../../src/lib/password.js'

const verifyTurnstileTokenMock = vi.fn(async () => ({ success: true, errors: [] }))
const sendResetPasswordEmailMock = vi.fn(async () => undefined)

vi.mock('../../src/lib/captcha.js', () => ({
  verifyTurnstileToken: verifyTurnstileTokenMock,
}))

vi.mock('../../src/lib/email.js', () => ({
  sendResetPasswordEmail: sendResetPasswordEmailMock,
}))

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '../..')

let server
let baseUrl
let databaseDir
let databasePath
let uid = 0

function nextValue(prefix) {
  uid += 1
  return `${prefix}_${Date.now()}_${uid}`
}

function runMigrations() {
  execFileSync(process.execPath, ['scripts/run-migrations.mjs'], {
    cwd: projectRoot,
    env: {
      ...process.env,
      DATABASE_PATH: databasePath,
    },
    stdio: 'pipe',
  })
}

async function api(pathname, { method = 'GET', body, token } = {}) {
  const headers = {}

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`${baseUrl}${pathname}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 204) {
    return {
      status: response.status,
      body: null,
    }
  }

  return {
    status: response.status,
    body: await response.json(),
  }
}

async function login(identity, password) {
  return api('/auth/login', {
    method: 'POST',
    body: {
      identity,
      password,
    },
  })
}

async function registerUser() {
  const username = nextValue('user')
  const email = `${username}@example.test`
  const password = 'Password123!'

  const response = await api('/auth/register', {
    method: 'POST',
    body: {
      username,
      email,
      password,
      captcha_token: 'ok',
    },
  })

  return {
    response,
    username,
    email,
    password,
  }
}

async function createAdminSession() {
  const username = nextValue('admin')
  const email = `${username}@example.test`
  const password = 'AdminPass123!'

  const db = new Database(databasePath)
  db.pragma('foreign_keys = ON')

  const userId = db.transaction(() => {
    const userResult = db
      .prepare(
        `
        INSERT INTO users(username, email, password_hash, must_change_password)
        VALUES (?, ?, ?, 0)
        `,
      )
      .run(username, email, hashPassword(password))

    const nextUserId = Number(userResult.lastInsertRowid)

    db.prepare(
      `
      INSERT OR IGNORE INTO user_roles(user_id, role_id)
      SELECT ?, id FROM roles WHERE name = 'admin'
      `,
    ).run(nextUserId)

    db.prepare(
      `
      INSERT OR IGNORE INTO user_permissions(user_id, permission_id, allow)
      SELECT ?, id, 1 FROM permissions
      WHERE name IN ('permissions.manage', 'recipes.manage', 'catalog.read', 'catalog.write')
      `,
    ).run(nextUserId)

    return nextUserId
  })()

  const assignedPermissions = db
    .prepare(
      `
      SELECT DISTINCT p.name
      FROM user_roles ur
      INNER JOIN role_permissions rp ON rp.role_id = ur.role_id
      INNER JOIN permissions p ON p.id = rp.permission_id
      WHERE ur.user_id = ?
      UNION
      SELECT p.name
      FROM user_permissions up
      INNER JOIN permissions p ON p.id = up.permission_id
      WHERE up.user_id = ? AND up.allow = 1
      ORDER BY name ASC
      `,
    )
    .all(userId, userId)
    .map((row) => row.name)

  db.close()

  if (!assignedPermissions.includes('permissions.manage')) {
    throw new Error(`Admin seed missing permissions.manage for user ${userId}`)
  }

  const adminLogin = await login(username, password)
  if (adminLogin.status !== 200) {
    throw new Error('Could not login as test admin user')
  }

  if (!adminLogin.body.permissions.includes('permissions.manage')) {
    throw new Error(`Admin login missing permissions.manage: ${JSON.stringify(adminLogin.body.permissions)}`)
  }

  return {
    userId,
    token: adminLogin.body.token,
  }
}

beforeAll(async () => {
  databaseDir = mkdtempSync(path.join(tmpdir(), 'ffp-auth-rbac-'))
  databasePath = path.join(databaseDir, 'integration.db')

  process.env.DATABASE_PATH = databasePath
  process.env.TURNSTILE_SECRET_KEY = 'test-secret'
  process.env.APP_BASE_URL = 'http://localhost:5173'

  runMigrations()

  vi.resetModules()
  const { createApp } = await import('../../src/app.js')
  const app = createApp()

  server = app.listen(0)

  await new Promise((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })

  const address = server.address()
  if (!address || typeof address === 'string') {
    throw new Error('Could not determine integration test server port')
  }

  baseUrl = `http://127.0.0.1:${address.port}/api`
})

afterAll(async () => {
  if (server) {
    await new Promise((resolve) => server.close(resolve))
  }

  if (databaseDir) {
    rmSync(databaseDir, { recursive: true, force: true })
  }
})

beforeEach(() => {
  verifyTurnstileTokenMock.mockResolvedValue({ success: true, errors: [] })
  sendResetPasswordEmailMock.mockClear()
})

describe('Auth + RBAC integration', () => {
  it('registers a user when captcha is valid', async () => {
    const { response } = await registerUser()

    expect(response.status).toBe(201)
    expect(response.body.user.username).toBeTruthy()
    expect(response.body.token).toBeTruthy()
    expect(response.body.permissions).toContain('catalog.read')
  })

  it('rejects registration when captcha fails', async () => {
    verifyTurnstileTokenMock.mockResolvedValueOnce({ success: false, errors: ['invalid-input-response'] })

    const username = nextValue('captcha_fail')
    const response = await api('/auth/register', {
      method: 'POST',
      body: {
        username,
        email: `${username}@example.test`,
        password: 'Password123!',
        captcha_token: 'bad-token',
      },
    })

    expect(response.status).toBe(400)
    expect(response.body.error).toMatch(/captcha/i)
  })

  it('supports login -> me -> logout session flow', async () => {
    const { username, password } = await registerUser()
    const loginResponse = await login(username, password)
    expect(loginResponse.status).toBe(200)

    const profile = await api('/auth/me', { token: loginResponse.body.token })
    expect(profile.status).toBe(200)
    expect(profile.body.user.username).toBe(username)

    const logoutResponse = await api('/auth/logout', {
      method: 'POST',
      token: loginResponse.body.token,
    })
    expect(logoutResponse.status).toBe(204)

    const profileAfterLogout = await api('/auth/me', { token: loginResponse.body.token })
    expect(profileAfterLogout.status).toBe(401)
  })

  it('changes password and invalidates previous sessions', async () => {
    const { response: registration, username } = await registerUser()
    const currentToken = registration.body.token

    const failed = await api('/auth/change-password', {
      method: 'POST',
      token: currentToken,
      body: {
        currentPassword: 'WrongPassword123!',
        newPassword: 'BrandNewPassword123!',
      },
    })
    expect(failed.status).toBe(400)

    const updated = await api('/auth/change-password', {
      method: 'POST',
      token: currentToken,
      body: {
        currentPassword: 'Password123!',
        newPassword: 'BrandNewPassword123!',
      },
    })
    expect(updated.status).toBe(204)

    const profileAfterPasswordChange = await api('/auth/me', { token: currentToken })
    expect(profileAfterPasswordChange.status).toBe(401)

    const relogin = await login(username, 'BrandNewPassword123!')
    expect(relogin.status).toBe(200)
  })

  it('supports forgot-password and reset-password flow', async () => {
    const { email, username } = await registerUser()

    const forgotPassword = await api('/auth/forgot-password', {
      method: 'POST',
      body: {
        email,
        captcha_token: 'ok',
      },
    })

    expect(forgotPassword.status).toBe(204)
    expect(sendResetPasswordEmailMock).toHaveBeenCalledTimes(1)

    const sentPayload = sendResetPasswordEmailMock.mock.calls[0][0]
    expect(sentPayload.username).toBe(username)

    const resetLink = new URL(sentPayload.resetLink)
    const resetToken = resetLink.searchParams.get('token')
    expect(resetToken).toBeTruthy()

    const resetPassword = await api('/auth/reset-password', {
      method: 'POST',
      body: {
        token: resetToken,
        newPassword: 'ResetPassword123!',
      },
    })
    expect(resetPassword.status).toBe(204)

    const loginWithNewPassword = await login(username, 'ResetPassword123!')
    expect(loginWithNewPassword.status).toBe(200)
  })

  it('enforces permissions for access-control endpoints and logs ACL changes', async () => {
    const noAuth = await api('/auth/access-catalog')
    expect(noAuth.status).toBe(401)

    const { response: userRegistration } = await registerUser()
    const userToken = userRegistration.body.token
    const userId = userRegistration.body.user.id

    const forbiddenForUser = await api('/auth/access-catalog', { token: userToken })
    expect(forbiddenForUser.status).toBe(403)

    const adminSession = await createAdminSession()
    const adminToken = adminSession.token

    const accessCatalog = await api('/auth/access-catalog', { token: adminToken })
    expect(accessCatalog.status, JSON.stringify(accessCatalog.body)).toBe(200)
    expect(Array.isArray(accessCatalog.body.permissions)).toBe(true)

    const usersNoPermission = await api('/auth/users', { token: userToken })
    expect(usersNoPermission.status).toBe(403)

    const usersAsAdmin = await api('/auth/users', { token: adminToken })
    expect(usersAsAdmin.status).toBe(200)
    expect(Array.isArray(usersAsAdmin.body)).toBe(true)

    const rolesUpdated = await api(`/auth/users/${userId}/roles`, {
      method: 'PUT',
      token: adminToken,
      body: {
        roles: ['user'],
      },
    })
    expect(rolesUpdated.status).toBe(200)

    const permissionsUpdated = await api(`/auth/users/${userId}/permissions`, {
      method: 'PUT',
      token: adminToken,
      body: {
        permissions: [
          {
            name: 'catalog.write',
            allow: true,
          },
        ],
      },
    })
    expect(permissionsUpdated.status).toBe(200)

    const auditNoPermission = await api('/auth/audit-logs', { token: userToken })
    expect(auditNoPermission.status).toBe(403)

    const auditLogs = await api('/auth/audit-logs', {
      token: adminToken,
    })
    expect(auditLogs.status).toBe(200)
    expect(
      auditLogs.body.some((entry) => entry.action === 'acl.roles.updated' && entry.target_id === String(userId)),
    ).toBe(true)
    expect(
      auditLogs.body.some(
        (entry) => entry.action === 'acl.permissions.updated' && entry.target_id === String(userId),
      ),
    ).toBe(true)
  })
})
