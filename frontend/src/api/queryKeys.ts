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

export interface AdminHouseholdsFilters {
  limit: number
  offset: number
  q?: string
}

export interface RecipesFilters {
  limit: number
  offset: number
  q?: string
  tag?: number[]
  prep_time_max?: number
  difficulty_max?: number
  rating_min?: number
  scope?: 'private' | 'household'
  include_archived?: boolean
}

export interface ProductsFilters {
  limit: number
  offset: number
  q?: string
  category_id?: number
  verification_status?: 'unverified' | 'verified'
  include_archived?: boolean
}

export const queryKeys = {
  planDays: {
    all: ['plan', 'days'] as const,
    /** Zakres dat — ten sam klucz obsługuje dzień (from === to) i tydzień. */
    range: (from: string, to: string) => ['plan', 'days', 'range', from, to] as const,
  },
  goals: {
    all: ['goals'] as const,
  },
  recipes: {
    all: ['recipes'] as const,
    list: (filters: RecipesFilters) => ['recipes', 'list', filters] as const,
    /** Klucz zawiera mnożnik porcji — regulacja porcji to refetch, nie mutacja. */
    detail: (id: number, servings: string) => ['recipes', 'detail', id, servings] as const,
  },
  tags: {
    all: ['tags'] as const,
  },
  products: {
    all: ['products'] as const,
    list: (filters: ProductsFilters) => ['products', 'list', filters] as const,
    detail: (id: number) => ['products', 'detail', id] as const,
    unitWeights: (id: number) => ['products', 'unit-weights', id] as const,
  },
  categories: {
    all: ['categories'] as const,
  },
  adminUsers: {
    all: ['admin', 'users'] as const,
    list: (filters: AdminUsersFilters) => ['admin', 'users', 'list', filters] as const,
  },
  adminHouseholds: {
    all: ['admin', 'households'] as const,
    list: (filters: AdminHouseholdsFilters) => ['admin', 'households', 'list', filters] as const,
    detail: (id: number) => ['admin', 'households', 'detail', id] as const,
  },
  adminAudit: {
    all: ['admin', 'audit'] as const,
  },
  households: {
    all: ['households'] as const,
    my: ['households', 'my'] as const,
    profiles: ['households', 'my', 'profiles'] as const,
  },
} as const
