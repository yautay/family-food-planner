/**
 * Stan sesji użytkownika — JEDYNY stan trzymany w Pinia z danych serwera
 * (05_FRONTEND §1, ADR-007). Nie wolno tu wkładać niczego więcej: listy,
 * przepisy i plany żyją w TanStack Query.
 *
 * CurrentUser nie jest utrwalany. Lokalny marker listy offline nie odtwarza
 * uwierzytelnienia; GET /auth/me pozostaje źródłem prawdy dla sesji.
 */

import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'

import type { CurrentUser, LoginPayload } from '@/api/auth'
import { fetchCurrentUser, loginRequest, logoutRequest } from '@/api/auth'
import { ApiError } from '@/api/client'
import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
  restorePrivateOfflineSession,
  subscribePrivateOfflineScope,
} from '@/lib/offline/privateSession'
import { advanceSessionGeneration, isSessionGenerationCurrent } from '@/lib/sessionGeneration'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  /** `idle` = jeszcze nie pytaliśmy serwera; guard routera musi na to poczekać. */
  const resolved = ref(false)
  /** Wyłącznie lokalna lista po błędzie transportu, bez zalogowanego konta. */
  const offlineSession = ref(false)
  let pending: Promise<void> | null = null
  let generation = 0

  onScopeDispose(
    subscribePrivateOfflineScope((scope, reason) => {
      if (scope !== null) advanceSessionGeneration()
      if (scope === null) {
        offlineSession.value = false
        // Awaria lokalnego offline nie podważa poprawnej odpowiedzi /me.
        // Logout, zmiana cookie i druga karta nadal unieważniają lot sesji.
        if (reason === 'offline-unavailable') return
        advanceSessionGeneration()
        generation += 1
        pending = null
        user.value = null
        resolved.value = false
      }
    }),
  )

  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  /**
   * Rodzina zalogowanego użytkownika (id + nazwa) albo `null`. To nadal stan
   * sesji, nie kopia danych serwera: skład rodziny i profile żyją w TanStack
   * Query (ADR-007), tutaj jest tylko tyle, ile potrzebuje nagłówek i guard.
   */
  const household = computed(() => user.value?.household ?? null)

  function commitUser(next: CurrentUser): void {
    if (
      user.value?.id !== next.id ||
      user.value?.household?.id !== next.household?.id ||
      user.value?.role !== next.role
    ) {
      advanceSessionGeneration()
    }
    user.value = next
    resolved.value = true
    offlineSession.value = false
  }

  /** Jednorazowe ustalenie sesji przy starcie aplikacji (współdzieli lot w toku). */
  async function ensureLoaded(force = false): Promise<void> {
    if (resolved.value && !force) {
      return
    }
    if (pending === null) {
      const ticket = ++generation
      const request = (async () => {
        try {
          const result = await fetchCurrentUser()
          if (ticket !== generation) return
          if (result === null) {
            clear()
            return
          }
          await confirmPrivateOfflineSession(result)
          if (ticket !== generation) return
          commitUser(result)
        } catch (error) {
          if (ticket !== generation) return
          if (user.value !== null) advanceSessionGeneration()
          user.value = null
          resolved.value = false
          offlineSession.value = false
          if (error instanceof ApiError && error.status === 0) {
            const scope = await restorePrivateOfflineSession()
            if (ticket === generation) offlineSession.value = scope !== null
            return
          }
          if (error instanceof ApiError && [401, 403, 404].includes(error.status)) clear()
          throw error
        }
      })()
      pending = request
      void request
        .finally(() => {
          if (pending === request) pending = null
        })
        .catch(() => {
          // Sam request jest awaitowany przez callera; sprzątanie nie tworzy
          // drugiego, nieobsłużonego odrzucenia Promise.
        })
    }
    await pending
  }

  async function login(payload: LoginPayload): Promise<CurrentUser> {
    clear()
    const ticket = ++generation
    const logged = await loginRequest(payload)
    if (ticket !== generation) return logged
    await confirmPrivateOfflineSession(logged)
    if (ticket !== generation) return logged
    commitUser(logged)
    return logged
  }

  async function logout(): Promise<void> {
    clear()
    await logoutRequest()
  }

  /** Czyści sesję lokalnie (wylogowanie, odpowiedź 401 z dowolnego zapytania). */
  function clear(): void {
    advanceSessionGeneration()
    generation += 1
    pending = null
    clearPrivateOfflineSession()
    user.value = null
    resolved.value = true
    offlineSession.value = false
  }

  /**
   * Podmienia dane zalogowanego konta po zapisie ustawień UI (BATCH_06).
   * To nadal stan SESJI, nie kopia listy z serwera: `PATCH /auth/me/ui-settings`
   * zwraca dokładnie ten sam kształt, co `GET /auth/me`.
   */
  function setUser(next: CurrentUser, ticket: number): boolean {
    if (!isSessionGenerationCurrent(ticket)) return false
    if (user.value?.id !== next.id || user.value?.household?.id !== next.household?.id) {
      clear()
      void confirmPrivateOfflineSession(next)
    }
    commitUser(next)
    return true
  }

  return {
    user,
    resolved,
    offlineSession,
    isAuthenticated,
    isAdmin,
    household,
    ensureLoaded,
    login,
    logout,
    clear,
    setUser,
  }
})
