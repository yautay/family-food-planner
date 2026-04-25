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

    const userId = Number(userResult.lastInsertRowid)

    db.prepare(
      `
      INSERT OR IGNORE INTO user_roles(user_id, role_id)
      SELECT ?, id FROM roles WHERE name = 'admin'
      `,
    ).run(userId)

    db.prepare(
      `
      INSERT OR IGNORE INTO user_permissions(user_id, permission_id, allow)
      SELECT ?, id, 1 FROM permissions
      WHERE name IN ('permissions.manage', 'recipes.manage', 'catalog.read', 'catalog.write')
      `,
    ).run(userId)

    return userId
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

  if (!assignedPermissions.includes('recipes.manage')) {
    throw new Error(`Admin seed missing recipes.manage for user ${userId}`)
  }

  const adminLogin = await login(username, password)
  if (adminLogin.status !== 200) {
    throw new Error('Could not login as test admin user')
  }

  if (!adminLogin.body.permissions.includes('recipes.manage')) {
    throw new Error(
      `Admin login missing recipes.manage: ${JSON.stringify(adminLogin.body.permissions)}`,
    )
  }

  return {
    token: adminLogin.body.token,
  }
}

beforeAll(async () => {
  databaseDir = mkdtempSync(path.join(tmpdir(), 'ffp-shopping-generator-'))
  databasePath = path.join(databaseDir, 'integration.db')

  process.env.DATABASE_PATH = databasePath
  process.env.TURNSTILE_ENABLED = 'true'
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

describe('Shopping list generator endpoint', () => {
  it('requires authentication', async () => {
    const response = await api('/shopping-lists/from-meal-plan/1', {
      method: 'POST',
    })

    expect(response.status).toBe(401)
  })

  it('returns 404 when meal plan belongs to another user', async () => {
    const ownerUser = await registerUser()
    expect(ownerUser.response.status).toBe(201)

    const createdMealPlan = await api('/meal-plans', {
      method: 'POST',
      token: ownerUser.response.body.token,
      body: {
        name: nextValue('Owner plan'),
        start_date: '2026-04-01',
        end_date: '2026-04-07',
        note: '',
      },
    })
    expect(createdMealPlan.status).toBe(201)

    const outsiderUser = await registerUser()
    expect(outsiderUser.response.status).toBe(201)

    const generationAttempt = await api(
      `/shopping-lists/from-meal-plan/${createdMealPlan.body.id}`,
      {
        method: 'POST',
        token: outsiderUser.response.body.token,
      },
    )

    expect(generationAttempt.status).toBe(404)
  })

  it('creates a shopping list aggregated from plan entries and servings', async () => {
    const adminSession = await createAdminSession()
    const adminToken = adminSession.token

    const recipe = await api('/recipes', {
      method: 'POST',
      token: adminToken,
      body: {
        name: nextValue('Recipe'),
        source_file: 'manual',
        ingredients: [
          {
            product_name: nextValue('Pomidor'),
            quantity: 2,
            unit_name: 'szt',
            grams: null,
            note: '',
          },
          {
            product_name: nextValue('Ogorek'),
            quantity: 1,
            unit_name: 'szt',
            grams: null,
            note: '',
          },
        ],
      },
    })

    expect(recipe.status, JSON.stringify(recipe.body)).toBe(201)

    const mealPlan = await api('/meal-plans', {
      method: 'POST',
      token: adminToken,
      body: {
        name: nextValue('Plan tygodnia'),
        start_date: '2026-04-01',
        end_date: '2026-04-07',
        note: '',
      },
    })

    expect(mealPlan.status).toBe(201)

    const entries = await api(`/meal-plans/${mealPlan.body.id}/entries`, {
      method: 'PUT',
      token: adminToken,
      body: {
        entries: [
          {
            planned_date: '2026-04-01',
            meal_slot: 'breakfast',
            recipe_id: recipe.body.id,
            custom_name: null,
            servings: 2,
            note: '',
          },
          {
            planned_date: '2026-04-02',
            meal_slot: 'lunch',
            recipe_id: recipe.body.id,
            custom_name: null,
            servings: 1.5,
            note: '',
          },
          {
            planned_date: '2026-04-03',
            meal_slot: 'dinner',
            recipe_id: null,
            custom_name: 'Woda',
            servings: null,
            note: '',
          },
        ],
      },
    })

    expect(entries.status).toBe(200)

    const generated = await api(`/shopping-lists/from-meal-plan/${mealPlan.body.id}`, {
      method: 'POST',
      token: adminToken,
      body: {
        name: 'Zakupy testowe',
      },
    })

    expect(generated.status, JSON.stringify(generated.body)).toBe(201)
    expect(generated.body.meal_plan_id).toBe(mealPlan.body.id)
    expect(generated.body.name).toBe('Zakupy testowe')

    const pomidorItem = generated.body.items.find((item) => item.product_name?.includes('Pomidor'))
    const ogorekItem = generated.body.items.find((item) => item.product_name?.includes('Ogorek'))
    const customItem = generated.body.items.find((item) => item.custom_name === 'Woda')

    expect(pomidorItem).toBeTruthy()
    expect(pomidorItem.quantity).toBeCloseTo(7)
    expect(ogorekItem).toBeTruthy()
    expect(ogorekItem.quantity).toBeCloseTo(3.5)
    expect(customItem).toBeTruthy()
    expect(customItem.quantity).toBeNull()
  })
})
