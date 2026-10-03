import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '@/api/auth'
import type { RecipeDetail } from '@/api/recipes'
import { useAuthStore } from '@/stores/auth'

import PrzepisSzczegolPage from './PrzepisSzczegolPage.vue'

/**
 * Szczegół przepisu a zakres `global` (BATCH_21, D32): „Edytuj"/„Usuń" widzi tylko
 * ADMIN, każdy może „Kopiować do mojej rodziny", a archiwizacja jest tylko dla ADMIN-a.
 * Backend i tak zwraca 403 — UI nie ma kusić akcją, która się nie uda.
 */

const routerPush = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '9' } }),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}))

const api = vi.hoisted(() => ({
  fetchRecipe: vi.fn(),
  deleteRecipe: vi.fn(),
  rateRecipe: vi.fn(),
  copyRecipe: vi.fn(),
  archiveRecipe: vi.fn(),
  unarchiveRecipe: vi.fn(),
}))
vi.mock('@/api/recipes', () => api)

function detail(overrides: Partial<RecipeDetail> = {}): RecipeDetail {
  return {
    id: 9,
    name: 'Wspólny żurek',
    scope: 'global',
    owner_user_id: 1,
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
      kcal: '420',
      protein_g: '20',
      fat_g: '10',
      carbs_g: '55',
      fiber_g: '6',
      sugars_g: '8',
      glycemic_load: '25',
      complete: true,
      missing: [],
    },
    created_at: '2026-10-03T10:00:00Z',
    updated_at: '2026-10-03T10:00:00Z',
    instructions: '',
    servings: '1',
    ingredients: [],
    ...overrides,
  }
}

function account(id: number, role: CurrentUser['role']): CurrentUser {
  return {
    id,
    email: `u${id}@example.com`,
    display_name: `Użytkownik ${id}`,
    role,
    household: null,
    ui_settings: {},
  } as unknown as CurrentUser
}

async function mountPage(role: CurrentUser['role'], userId: number, recipe: RecipeDetail) {
  setActivePinia(createPinia())
  useAuthStore().setUser(account(userId, role))
  api.fetchRecipe.mockResolvedValue(recipe)
  const wrapper = mount(PrzepisSzczegolPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

describe('PrzepisSzczegolPage — przepis globalny', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('zwykły użytkownik NIE widzi Edytuj, Usuń ani Archiwizuj, ale może skopiować', async () => {
    // Zdegradowany były admin: nadal `owner_user_id`, ale rola USER.
    const wrapper = await mountPage('user', 1, detail())

    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="recipe-copy"]').text()).toBe('Kopiuj do mojej rodziny')
    expect(wrapper.get('[data-testid="recipe-scope-badge"]').text()).toContain('Dla wszystkich')
  })

  it('ADMIN widzi Edytuj, Usuń i Archiwizuj', async () => {
    const wrapper = await mountPage('admin', 2, detail())

    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(true)
  })

  it('zarchiwizowany przepis pokazuje Przywróć zamiast Archiwizuj', async () => {
    const wrapper = await mountPage('admin', 2, detail({ is_archived: true }))

    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="recipe-unarchive"]').text()).toBe('Przywróć z archiwum')
  })

  it('kopiowanie woła API i przechodzi do nowego przepisu', async () => {
    api.copyRecipe.mockResolvedValue(detail({ id: 77, scope: 'household' }))
    const wrapper = await mountPage('user', 5, detail())

    await wrapper.get('[data-testid="recipe-copy"]').trigger('click')
    await flushPromises()

    expect(api.copyRecipe).toHaveBeenCalledWith(9)
    expect(routerPush).toHaveBeenCalledWith({ name: 'przepis-szczegol', params: { id: 77 } })
  })

  it('archiwizacja woła API', async () => {
    api.archiveRecipe.mockResolvedValue(detail({ is_archived: true }))
    const wrapper = await mountPage('admin', 2, detail())

    await wrapper.get('[data-testid="recipe-archive"]').trigger('click')
    await flushPromises()

    expect(api.archiveRecipe).toHaveBeenCalledWith(9)
  })
})

describe('PrzepisSzczegolPage — przepis rodzinny', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('własny przepis rodzinny: edycja i usunięcie bez zmian, kopiowanie niepotrzebne', async () => {
    const wrapper = await mountPage('user', 1, detail({ scope: 'household', owner_user_id: 1 }))

    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-copy"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(false)
  })

  it('cudzy przepis rodzinny: edytować może członek rodziny, usunąć nie', async () => {
    const wrapper = await mountPage('user', 2, detail({ scope: 'household', owner_user_id: 1 }))

    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(false)
  })
})
