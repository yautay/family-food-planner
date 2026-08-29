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

export interface RetailFiltersKey {
  limit: number
  offset: number
  canonical_product_id?: number
  store_id?: number
  q?: string
  include_archived?: boolean
}

export interface StoresFiltersKey {
  include_archived?: boolean
}

export interface ShoppingListsFiltersKey {
  limit: number
  offset: number
  status?: 'active' | 'expired'
}

export interface PantryFiltersKey {
  limit: number
  offset: number
  q?: string
  category_id?: number
  sort?: 'expiry' | 'name'
  expires_within_days?: number
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
  stats: {
    all: ['stats'] as const,
    /** Zakres jest CZĘŚCIĄ klucza: zmiana presetu to refetch, nie filtr w pamięci. */
    daily: (from: string, to: string) => ['stats', 'daily', from, to] as const,
  },
  templates: {
    all: ['templates'] as const,
    days: ['templates', 'days'] as const,
    day: (id: number) => ['templates', 'days', id] as const,
    weeks: ['templates', 'weeks'] as const,
    week: (id: number) => ['templates', 'weeks', id] as const,
  },
  cycles: {
    all: ['cycles'] as const,
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
  stores: {
    all: ['stores'] as const,
    list: (filters: StoresFiltersKey) => ['stores', 'list', filters] as const,
    /** Profil sklepu: kolejność kategorii jest własnością TEGO sklepu (B09). */
    categoryOrder: (id: number) => ['stores', 'category-order', id] as const,
  },
  retailProducts: {
    all: ['retail-products'] as const,
    list: (filters: RetailFiltersKey) => ['retail-products', 'list', filters] as const,
  },
  pantry: {
    all: ['pantry'] as const,
    list: (filters: PantryFiltersKey) => ['pantry', 'list', filters] as const,
  },
  shopping: {
    all: ['shopping'] as const,
    roundConfigs: ['shopping', 'round-configs'] as const,
    /** Podgląd generacji to stan serwera: liczy go silnik z `params` (B10). */
    generation: (id: number) => ['shopping', 'generations', id] as const,
    /**
     * Gotowe listy zakupowe (B11) — sekcje składa serwer, nie przeglądarka.
     *
     * `listsIndex` i `list` mają ROZŁĄCZNE prefiksy (`index` vs `detail`)
     * z rozmysłem: klucz szczegółu `['shopping','lists', id]` byłby dzieckiem
     * klucza indeksu, więc `invalidateQueries` po zapisie na liście list
     * unieważniałby też otwarty szczegół i kasował świeżo podmienioną
     * odpowiedź PATCH-a (złapał to test zmiany sklepu).
     */
    lists: ['shopping', 'lists'] as const,
    listsIndex: ['shopping', 'lists', 'index'] as const,
    listsIndexFiltered: (filters: ShoppingListsFiltersKey) =>
      ['shopping', 'lists', 'index', filters] as const,
    list: (id: number) => ['shopping', 'lists', 'detail', id] as const,
  },
  /** Publiczna lista po tokenie — POZA sesją, więc własna gałąź kluczy. */
  publicList: {
    detail: (token: string) => ['public-list', token] as const,
  },
  /**
   * Importy PDF (BATCH_15) — lista i szczegóły joba z raportem parsowania.
   *
   * `jobs` i `job` mają ROZŁĄCZNE prefiksy (`index` vs `detail`) z tego samego
   * powodu, co listy zakupowe wyżej: klucz szczegółu `['import','jobs',id]`
   * byłby DZIECKIEM klucza listy, więc `invalidateQueries` po uploadzie
   * unieważniałby też świeżo wstawiony do cache'u raport i kazał pobierać go
   * drugi raz.
   */
  import: {
    all: ['import'] as const,
    jobs: ['import', 'jobs', 'index'] as const,
    job: (id: number) => ['import', 'jobs', 'detail', id] as const,
    staged: (id: number) => ['import', 'jobs', 'staged', id] as const,
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
