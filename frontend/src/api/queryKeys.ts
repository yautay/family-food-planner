/**
 * Centralny rejestr kluczy TanStack Query (05_FRONTEND §1).
 *
 * Każdy moduł dopisuje tu swoje klucze — dzięki temu `invalidateQueries`
 * w mutacjach odwołuje się do jednego źródła prawdy, a nie do literałów
 * rozsianych po komponentach.
 */

export interface AdminUsersFilters {
  limit: number
  offset: number
  q?: string
}

export const queryKeys = {
  adminUsers: {
    all: ['admin', 'users'] as const,
    list: (filters: AdminUsersFilters) => ['admin', 'users', 'list', filters] as const,
  },
} as const
