/**
 * Stan sesji użytkownika — JEDYNY stan trzymany w Pinia z danych serwera
 * (05_FRONTEND §1, ADR-007). Nie wolno tu wkładać niczego więcej: listy,
 * przepisy i plany żyją w TanStack Query.
 *
 * Bez persystencji w localStorage — źródłem prawdy jest cookie sesyjne,
 * a `GET /auth/me` jedyną drogą do odtworzenia stanu po odświeżeniu strony.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { CurrentUser, LoginPayload } from '@/api/auth'
import { fetchCurrentUser, loginRequest, logoutRequest } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  /** `idle` = jeszcze nie pytaliśmy serwera; guard routera musi na to poczekać. */
  const resolved = ref(false)
  let pending: Promise<void> | null = null

  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  /**
   * Rodzina zalogowanego użytkownika (id + nazwa) albo `null`. To nadal stan
   * sesji, nie kopia danych serwera: skład rodziny i profile żyją w TanStack
   * Query (ADR-007), tutaj jest tylko tyle, ile potrzebuje nagłówek i guard.
   */
  const household = computed(() => user.value?.household ?? null)

  /** Jednorazowe ustalenie sesji przy starcie aplikacji (współdzieli lot w toku). */
  async function ensureLoaded(): Promise<void> {
    if (resolved.value) {
      return
    }
    pending ??= fetchCurrentUser()
      .then((result) => {
        user.value = result
        resolved.value = true
      })
      .finally(() => {
        pending = null
      })
    await pending
  }

  async function login(payload: LoginPayload): Promise<CurrentUser> {
    const logged = await loginRequest(payload)
    user.value = logged
    resolved.value = true
    return logged
  }

  async function logout(): Promise<void> {
    try {
      await logoutRequest()
    } finally {
      clear()
    }
  }

  /** Czyści sesję lokalnie (wylogowanie, odpowiedź 401 z dowolnego zapytania). */
  function clear(): void {
    user.value = null
    resolved.value = true
  }

  /**
   * Podmienia dane zalogowanego konta po zapisie ustawień UI (BATCH_06).
   * To nadal stan SESJI, nie kopia listy z serwera: `PATCH /auth/me/ui-settings`
   * zwraca dokładnie ten sam kształt, co `GET /auth/me`.
   */
  function setUser(next: CurrentUser): void {
    user.value = next
    resolved.value = true
  }

  return {
    user,
    resolved,
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
