import authService from '../services/auth.service.js'
import { verifyTurnstileToken } from '../lib/captcha.js'
import { sendResetPasswordEmail } from '../lib/email.js'

function ensurePasswordStrength(password) {
  const value = typeof password === 'string' ? password : ''

  if (value.length < 10) {
    throw new Error('Password must have at least 10 characters')
  }

  if (!/[A-Z]/.test(value) || !/[a-z]/.test(value) || !/[0-9]/.test(value) || !/[^A-Za-z0-9]/.test(value)) {
    throw new Error('Password must include uppercase, lowercase, number and symbol')
  }
}

async function register(payload, remoteIp) {
  const captchaCheck = await verifyTurnstileToken(payload?.captcha_token, remoteIp)
  if (!captchaCheck.success) {
    throw new Error('Captcha validation failed')
  }

  ensurePasswordStrength(payload?.password)
  const user = authService.registerUser(payload)

  const loginResult = authService.login({
    identity: payload.username,
    password: payload.password,
  })

  return {
    ...loginResult,
    user,
  }
}

async function login(payload) {
  return authService.login(payload)
}

async function changePassword(payload) {
  ensurePasswordStrength(payload?.newPassword)
  authService.changePassword(payload)
}

async function forgotPassword(payload, remoteIp) {
  const captchaCheck = await verifyTurnstileToken(payload?.captcha_token, remoteIp)
  if (!captchaCheck.success) {
    throw new Error('Captcha validation failed')
  }

  const resetToken = authService.createPasswordResetToken(payload?.email)
  if (!resetToken) {
    return
  }

  const appBaseUrl = process.env.APP_BASE_URL
  if (!appBaseUrl) {
    throw new Error('APP_BASE_URL is not configured')
  }

  const resetLink = `${appBaseUrl.replace(/\/$/, '')}/reset-password?token=${encodeURIComponent(resetToken.token)}`

  await sendResetPasswordEmail({
    to: resetToken.user.email,
    username: resetToken.user.username,
    resetLink,
  })
}

async function resetPassword(payload) {
  ensurePasswordStrength(payload?.newPassword)
  authService.resetPassword(payload)
}

async function getProfile(userId) {
  return authService.getUserProfile(userId)
}

async function listUsersWithPermissions() {
  return authService.listUsersWithPermissions()
}

async function updateUserRoles(userId, roles) {
  authService.setUserRoles(userId, roles)
  return authService.getUserProfile(userId)
}

async function updateUserPermissions(userId, permissions) {
  authService.setUserPermissions(userId, permissions)
  return authService.getUserProfile(userId)
}

async function getAccessCatalog() {
  return {
    roles: authService.getAvailableRoles(),
    permissions: authService.getAvailablePermissions(),
  }
}

export default {
  register,
  login,
  changePassword,
  forgotPassword,
  resetPassword,
  getProfile,
  listUsersWithPermissions,
  updateUserRoles,
  updateUserPermissions,
  getAccessCatalog,
}
