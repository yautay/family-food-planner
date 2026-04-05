import { defineStore } from 'pinia'
import apiClient, { getStoredApiToken, setApiToken } from '../services/apiClient'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getStoredApiToken(),
    expiresAt: null,
    user: null,
    roles: [],
    permissions: [],
    users: [],
    accessCatalog: {
      roles: [],
      permissions: [],
    },
    initialized: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.user),
    can: (state) => (permissionName) => state.permissions.includes(permissionName),
    isAdmin: (state) => state.roles.includes('admin'),
  },
  actions: {
    applySession(payload) {
      this.token = payload.token
      this.expiresAt = payload.expires_at
      this.user = payload.user
      this.roles = payload.roles ?? []
      this.permissions = payload.permissions ?? []

      setApiToken(payload.token)
    },

    clearSession() {
      this.token = null
      this.expiresAt = null
      this.user = null
      this.roles = []
      this.permissions = []
      setApiToken(null)
    },

    async initialize() {
      if (this.initialized) {
        return
      }

      this.initialized = true

      if (!this.token) {
        return
      }

      try {
        const response = await apiClient.get('/auth/me')
        this.user = response.data.user
        this.roles = response.data.roles
        this.permissions = response.data.permissions
      } catch (_error) {
        this.clearSession()
      }
    },

    async login(identity, password) {
      const response = await apiClient.post('/auth/login', {
        identity,
        password,
      })

      this.applySession(response.data)
      return response.data
    },

    async register(payload) {
      const response = await apiClient.post('/auth/register', payload)
      this.applySession(response.data)
      return response.data
    },

    async logout() {
      if (this.token) {
        try {
          await apiClient.post('/auth/logout')
        } catch (_error) {
          // ignore network errors, clear local session anyway
        }
      }

      this.clearSession()
    },

    async changePassword(currentPassword, newPassword) {
      await apiClient.post('/auth/change-password', {
        currentPassword,
        newPassword,
      })
    },

    async forgotPassword(email, captchaToken) {
      await apiClient.post('/auth/forgot-password', {
        email,
        captcha_token: captchaToken,
      })
    },

    async resetPassword(token, newPassword) {
      await apiClient.post('/auth/reset-password', {
        token,
        newPassword,
      })
    },

    async getCaptchaConfig() {
      const response = await apiClient.get('/auth/captcha-config')
      return response.data
    },

    async fetchAccessCatalog() {
      const response = await apiClient.get('/auth/access-catalog')
      this.accessCatalog = response.data
      return response.data
    },

    async fetchUsers() {
      const response = await apiClient.get('/auth/users')
      this.users = response.data
      return response.data
    },

    async updateUserRoles(userId, roles) {
      const response = await apiClient.put(`/auth/users/${userId}/roles`, { roles })
      return response.data
    },

    async updateUserPermissions(userId, permissions) {
      const response = await apiClient.put(`/auth/users/${userId}/permissions`, {
        permissions,
      })
      return response.data
    },
  },
})
