import { Op, fn, col, where } from 'sequelize'
import sequelize from '../db/client.js'
import models from '../models/index.js'
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

function isTruthyInt(value) {
  return value === 1 || value === true
}

function mapUser(row) {
  if (!row) {
    return null
  }

  return {
    id: row.id,
    username: row.username,
    email: row.email,
    is_active: isTruthyInt(row.is_active),
    must_change_password: isTruthyInt(row.must_change_password),
    created_at: row.created_at,
    updated_at: row.updated_at,
  }
}

async function getUserById(userId) {
  return models.user.findByPk(userId, { raw: true })
}

async function getUserByIdentity(identity) {
  const value = normalizeIdentity(identity)
  if (!value) {
    return null
  }

  return models.user.findOne({
    where: {
      [Op.or]: [
        where(fn('lower', col('username')), value),
        where(fn('lower', col('email')), value),
      ],
    },
    raw: true,
  })
}

async function getUserRoles(userId) {
  const roleRows = await models.userRole.findAll({
    attributes: ['role_id'],
    where: { user_id: userId },
    raw: true,
  })

  const roleIds = roleRows.map((row) => row.role_id)
  if (roleIds.length === 0) {
    return []
  }

  const roles = await models.role.findAll({
    attributes: ['name'],
    where: {
      id: {
        [Op.in]: roleIds,
      },
    },
    order: [['name', 'ASC']],
    raw: true,
  })

  return roles.map((row) => row.name)
}

async function getEffectivePermissions(userId) {
  const roleRows = await models.userRole.findAll({
    attributes: ['role_id'],
    where: { user_id: userId },
    raw: true,
  })

  const roleIds = roleRows.map((row) => row.role_id)
  const rolePermissionRows =
    roleIds.length > 0
      ? await models.rolePermission.findAll({
          attributes: ['permission_id'],
          where: {
            role_id: {
              [Op.in]: roleIds,
            },
          },
          raw: true,
        })
      : []

  const directPermissionRows = await models.userPermission.findAll({
    attributes: ['permission_id', 'allow'],
    where: { user_id: userId },
    raw: true,
  })

  const allPermissionIds = new Set(rolePermissionRows.map((row) => row.permission_id))
  for (const row of directPermissionRows) {
    allPermissionIds.add(row.permission_id)
  }

  if (allPermissionIds.size === 0) {
    return new Set()
  }

  const permissions = await models.permission.findAll({
    attributes: ['id', 'name'],
    where: {
      id: {
        [Op.in]: Array.from(allPermissionIds),
      },
    },
    raw: true,
  })

  const permissionNameById = new Map(permissions.map((row) => [row.id, row.name]))
  const effective = new Set()

  for (const row of rolePermissionRows) {
    const name = permissionNameById.get(row.permission_id)
    if (name) {
      effective.add(name)
    }
  }

  for (const row of directPermissionRows) {
    const name = permissionNameById.get(row.permission_id)
    if (!name) {
      continue
    }

    if (isTruthyInt(row.allow)) {
      effective.add(name)
    } else {
      effective.delete(name)
    }
  }

  return effective
}

async function createSession(userId) {
  const token = createOpaqueToken()
  const tokenHash = sha256Hex(token)
  const expiresAt = addDaysIso(SESSION_TTL_DAYS)

  await models.authSession.create({
    user_id: userId,
    token_hash: tokenHash,
    expires_at: expiresAt,
    last_seen_at: nowIso(),
  })

  return {
    token,
    expires_at: expiresAt,
  }
}

async function getSessionByToken(token) {
  if (!token) {
    return null
  }

  const tokenHash = sha256Hex(token)
  return models.authSession.findOne({
    where: { token_hash: tokenHash },
    include: [
      {
        model: models.user,
        as: 'user',
        required: true,
      },
    ],
  })
}

async function revokeSession(token) {
  if (!token) {
    return
  }

  await models.authSession.update(
    { revoked_at: nowIso() },
    {
      where: {
        token_hash: sha256Hex(token),
      },
    },
  )
}

async function revokeUserSessions(userId, transaction = undefined) {
  await models.authSession.update(
    { revoked_at: nowIso() },
    {
      where: {
        user_id: userId,
        revoked_at: null,
      },
      transaction,
    },
  )
}

async function removeExpiredSessions() {
  await models.authSession.destroy({
    where: {
      expires_at: {
        [Op.lte]: nowIso(),
      },
    },
  })
}

async function getAuthContextFromToken(token) {
  await removeExpiredSessions()
  const sessionInstance = await getSessionByToken(token)

  if (!sessionInstance) {
    return null
  }

  const session = sessionInstance.get({ plain: true })
  const user = mapUser(session.user)
  const currentNow = nowIso()

  if (!user || session.revoked_at || session.expires_at <= currentNow || !user.is_active) {
    return null
  }

  await models.authSession.update(
    { last_seen_at: currentNow },
    {
      where: {
        id: session.id,
      },
    },
  )

  const roles = await getUserRoles(user.id)
  const permissions = await getEffectivePermissions(user.id)

  return {
    user,
    roles,
    permissions,
  }
}

async function registerUser({ username, email, password }) {
  const normalizedUsername = typeof username === 'string' ? username.trim() : ''
  const normalizedEmail = typeof email === 'string' ? email.trim().toLowerCase() : ''

  if (!normalizedUsername || !normalizedEmail || !password) {
    throw new Error('Username, email and password are required')
  }

  const passwordHash = hashPassword(password)

  const created = await models.user.create({
    username: normalizedUsername,
    email: normalizedEmail,
    password_hash: passwordHash,
  })

  const defaultRole = await models.role.findOne({
    where: { name: 'user' },
    attributes: ['id'],
    raw: true,
  })

  if (defaultRole) {
    await models.userRole.findOrCreate({
      where: {
        user_id: created.id,
        role_id: defaultRole.id,
      },
    })
  }

  const user = await getUserById(created.id)
  return mapUser(user)
}

async function login({ identity, password }) {
  const user = await getUserByIdentity(identity)

  if (!user || !isTruthyInt(user.is_active)) {
    throw new Error('Invalid credentials')
  }

  if (!verifyPassword(password, user.password_hash)) {
    throw new Error('Invalid credentials')
  }

  const session = await createSession(user.id)
  const roles = await getUserRoles(user.id)
  const permissions = await getEffectivePermissions(user.id)

  return {
    token: session.token,
    expires_at: session.expires_at,
    user: mapUser(user),
    roles,
    permissions: Array.from(permissions).sort((left, right) => left.localeCompare(right)),
  }
}

async function changePassword({ userId, currentPassword, newPassword }) {
  const user = await getUserById(userId)

  if (!user) {
    throw new Error('User not found')
  }

  if (!verifyPassword(currentPassword, user.password_hash)) {
    throw new Error('Current password is invalid')
  }

  const newHash = hashPassword(newPassword)

  await models.user.update(
    {
      password_hash: newHash,
      must_change_password: 0,
      updated_at: nowIso(),
    },
    {
      where: { id: userId },
    },
  )

  await revokeUserSessions(userId)
}

async function createPasswordResetToken(email) {
  const normalizedEmail = typeof email === 'string' ? email.trim().toLowerCase() : ''
  const user = await models.user.findOne({
    where: where(fn('lower', col('email')), normalizedEmail),
    raw: true,
  })

  if (!user || !isTruthyInt(user.is_active)) {
    return null
  }

  const rawToken = createOpaqueToken(40)
  const tokenHash = sha256Hex(rawToken)

  await models.passwordResetToken.create({
    user_id: user.id,
    token_hash: tokenHash,
    expires_at: addMinutesIso(RESET_TTL_MINUTES),
  })

  return {
    token: rawToken,
    user: mapUser(user),
  }
}

async function resetPassword({ token, newPassword }) {
  const tokenHash = sha256Hex(token)
  const resetToken = await models.passwordResetToken.findOne({
    where: {
      token_hash: tokenHash,
    },
    raw: true,
  })

  if (!resetToken || resetToken.used_at || resetToken.expires_at <= nowIso()) {
    throw new Error('Reset token is invalid or expired')
  }

  const newHash = hashPassword(newPassword)
  const usedAt = nowIso()

  await sequelize.transaction(async (transaction) => {
    await models.user.update(
      {
        password_hash: newHash,
        must_change_password: 0,
        updated_at: usedAt,
      },
      {
        where: { id: resetToken.user_id },
        transaction,
      },
    )

    await models.passwordResetToken.update(
      {
        used_at: usedAt,
      },
      {
        where: { id: resetToken.id },
        transaction,
      },
    )

    await revokeUserSessions(resetToken.user_id, transaction)
  })
}

async function getUserProfile(userId) {
  const user = mapUser(await getUserById(userId))
  if (!user) {
    return null
  }

  const roles = await getUserRoles(userId)
  const permissions = Array.from(await getEffectivePermissions(userId)).sort((left, right) =>
    left.localeCompare(right),
  )

  return {
    user,
    roles,
    permissions,
  }
}

async function listUsersWithPermissions() {
  const users = await models.user.findAll({
    attributes: [
      'id',
      'username',
      'email',
      'is_active',
      'must_change_password',
      'created_at',
      'updated_at',
    ],
    order: [['username', 'ASC']],
    raw: true,
  })

  return Promise.all(
    users.map(async (row) => {
      const user = mapUser(row)
      return {
        ...user,
        roles: await getUserRoles(row.id),
        permissions: Array.from(await getEffectivePermissions(row.id)).sort((left, right) =>
          left.localeCompare(right),
        ),
      }
    }),
  )
}

async function setUserRoles(userId, roleNames) {
  const names = Array.isArray(roleNames)
    ? Array.from(
        new Set(
          roleNames
            .map((value) => (typeof value === 'string' ? value.trim() : ''))
            .filter((value) => value.length > 0),
        ),
      )
    : []

  const roles =
    names.length > 0
      ? await models.role.findAll({
          attributes: ['id'],
          where: {
            name: {
              [Op.in]: names,
            },
          },
          raw: true,
        })
      : []

  await sequelize.transaction(async (transaction) => {
    await models.userRole.destroy({ where: { user_id: userId }, transaction })

    if (roles.length > 0) {
      await models.userRole.bulkCreate(
        roles.map((role) => ({
          user_id: userId,
          role_id: role.id,
        })),
        { transaction },
      )
    }
  })
}

async function setUserPermissions(userId, permissions) {
  const values = Array.isArray(permissions) ? permissions : []

  const normalizedPermissions = values
    .map((permission) => {
      if (typeof permission === 'string') {
        return {
          name: permission.trim(),
          allow: true,
        }
      }

      return {
        name: typeof permission?.name === 'string' ? permission.name.trim() : '',
        allow: permission?.allow !== false,
      }
    })
    .filter((permission) => permission.name.length > 0)

  const uniqueNames = Array.from(
    new Set(normalizedPermissions.map((permission) => permission.name)),
  )

  const permissionsByName =
    uniqueNames.length > 0
      ? await models.permission.findAll({
          attributes: ['id', 'name'],
          where: {
            name: {
              [Op.in]: uniqueNames,
            },
          },
          raw: true,
        })
      : []

  const idByName = new Map(permissionsByName.map((permission) => [permission.name, permission.id]))

  await sequelize.transaction(async (transaction) => {
    await models.userPermission.destroy({ where: { user_id: userId }, transaction })

    const rows = normalizedPermissions
      .map((permission) => {
        const permissionId = idByName.get(permission.name)
        if (!permissionId) {
          return null
        }

        return {
          user_id: userId,
          permission_id: permissionId,
          allow: permission.allow ? 1 : 0,
        }
      })
      .filter(Boolean)

    if (rows.length > 0) {
      await models.userPermission.bulkCreate(rows, { transaction })
    }
  })
}

async function getAvailableRoles() {
  return models.role.findAll({
    attributes: ['name', 'description'],
    order: [['name', 'ASC']],
    raw: true,
  })
}

async function getAvailablePermissions() {
  return models.permission.findAll({
    attributes: ['name', 'description'],
    order: [['name', 'ASC']],
    raw: true,
  })
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
