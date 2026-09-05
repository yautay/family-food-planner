import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PrzepisyPage from './PrzepisyPage.vue'

/**
 * Paginacja listy przepisów (BATCH_19).
 *
 * Import ośmiu jadłospisów daje 103 dania, czyli dwie strony z okładem —
 * do BATCH_19 widać było pierwsze 50 i nic więcej.
 */

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const { fetchRecipes, fetchTags } = vi.hoisted(() => ({
  fetchRecipes: vi.fn(),
  fetchTags: vi.fn(),
}))
vi.mock('@/api/recipes', () => ({ fetchRecipes, fetchTags }))

function recipe(id: number) {
  return {
    id,
    name: `Przepis ${id}`,
    scope: 'household' as const,
    owner_user_id: 1,
    base_servings: 2,
    prep_time_min: 20,
    difficulty: 2,
    source: 'manual' as const,
    is_archived: false,
    photo_url: null,
    photo_thumb_url: null,
    tags: [],
    avg_rating: null,
    ratings_count: 0,
    my_rating: null,
    nutrition: {
      kcal: '420.0',
      protein_g: '20.0',
      fat_g: '10.0',
      carbs_g: '55.0',
      fiber_g: '6.0',
      sugars_g: '8.0',
      glycemic_load: '25.0',
      complete: true,
      missing: [],
    },
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
  }
}

const TOTAL = 103
const PAGE_SIZE = 50
const ALL = Array.from({ length: TOTAL }, (_unused, index) => recipe(index + 1))

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(PrzepisyPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

describe('PrzepisyPage — paginacja', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchTags.mockResolvedValue({ items: [], total: 0 })
    fetchRecipes.mockImplementation(({ offset = 0, limit = PAGE_SIZE }) =>
      Promise.resolve({ items: ALL.slice(offset, offset + limit), total: TOTAL }),
    )
  })

  it('pierwsza strona pokazuje limit kart i relację do całości', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-testid^="recipe-open-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="recipes-total"]').text()).toContain('50 z 103')
  })

  it('kolejne kliknięcia dochodzą do ostatniego przepisu', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="recipe-open-"]')).toHaveLength(100)

    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="recipe-open-"]')).toHaveLength(TOTAL)
    expect(wrapper.get('[data-testid="recipes-total"]').text()).toContain('103 z 103')
    expect(wrapper.find('[data-testid="recipes-load-more"]').exists()).toBe(false)
  })

  it('zbiór mieszczący się na stronie nie dostaje przycisku', async () => {
    fetchRecipes.mockResolvedValue({ items: ALL.slice(0, 5), total: 5 })

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="recipes-load-more"]').exists()).toBe(false)
  })
})
