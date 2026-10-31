import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '@/api/auth'
import type { RecipeDetail } from '@/api/recipes'
import { useAuthStore } from '@/stores/auth'

import PrzepisEdytorPage from './PrzepisEdytorPage.vue'

/**
 * Edytor a zakres `global` (BATCH_21, D32): opcja „Wszyscy" tylko dla ADMIN-a,
 * a przepis globalny otwarty przez zwykłego użytkownika jest tylko do odczytu
 * (zapis i tak skończyłby się 403).
 */

const route = vi.hoisted(() => ({ params: {} as Record<string, string>, query: {} }))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const api = vi.hoisted(() => ({
  createRecipe: vi.fn(),
  updateRecipe: vi.fn(),
  createTag: vi.fn(),
  fetchRecipe: vi.fn(),
  fetchTags: vi.fn(),
  uploadRecipePhoto: vi.fn(),
  deleteRecipePhoto: vi.fn(),
}))
vi.mock('@/api/recipes', () => api)
vi.mock('@/api/catalog', () => ({
  fetchProducts: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchCategories: vi.fn(),
  createProduct: vi.fn(),
  fetchProduct: vi.fn(),
  fetchUnitWeights: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))

function account(role: CurrentUser['role']): CurrentUser {
  return {
    id: role === 'admin' ? 2 : 1,
    email: 'x@example.com',
    display_name: 'X',
    role,
    household: null,
    ui_settings: {},
  } as unknown as CurrentUser
}

function globalRecipe(): RecipeDetail {
  return {
    id: 5,
    name: 'Wspólny żurek',
    scope: 'global',
    owner_user_id: 2,
    base_servings: 2,
    prep_time_min: null,
    difficulty: null,
    is_archived: false,
    photo_url: null,
    photo_thumb_url: null,
    tags: [],
    avg_rating: null,
    ratings_count: 0,
    my_rating: null,
    nutrition: {
      kcal: '1',
      protein_g: '1',
      fat_g: '1',
      carbs_g: '1',
      fiber_g: '1',
      sugars_g: '1',
      glycemic_load: '1',
      complete: true,
      missing: [],
    },
    created_at: '2026-10-03T10:00:00Z',
    updated_at: '2026-10-03T10:00:00Z',
    instructions: '',
    servings: '1',
    ingredients: [],
  }
}

async function mountEditor(role: CurrentUser['role']) {
  setActivePinia(createPinia())
  useAuthStore().setUser(account(role))
  const wrapper = mount(PrzepisEdytorPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

function scopeOptions(wrapper: Awaited<ReturnType<typeof mountEditor>>): string[] {
  return wrapper
    .get('[data-testid="recipe-scope"]')
    .findAll('option')
    .map((option) => (option.element as HTMLOptionElement).value)
}

describe('PrzepisEdytorPage — zakres „Wszyscy"', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    route.params = {}
    api.fetchTags.mockResolvedValue({ items: [], total: 0 })
  })

  it('nowy przepis: opcję „Wszyscy" ma tylko ADMIN', async () => {
    expect(scopeOptions(await mountEditor('user'))).toEqual(['private', 'household'])
    expect(scopeOptions(await mountEditor('admin'))).toEqual(['private', 'household', 'global'])
  })

  it('przepis globalny otwarty przez zwykłego użytkownika jest tylko do odczytu', async () => {
    route.params = { id: '5' }
    api.fetchRecipe.mockResolvedValue(globalRecipe())

    const wrapper = await mountEditor('user')

    expect(wrapper.get('[data-testid="recipe-scope"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="recipe-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="recipe-scope-hint"]').text()).toContain(
      'Kopiuj do mojej rodziny',
    )
  })

  it('przepis globalny otwarty przez ADMIN-a da się zapisać', async () => {
    route.params = { id: '5' }
    api.fetchRecipe.mockResolvedValue(globalRecipe())

    const wrapper = await mountEditor('admin')

    expect(wrapper.get('[data-testid="recipe-scope"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="recipe-submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="recipe-scope-hint"]').text()).toContain('administrator')
  })
})
