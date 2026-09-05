import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminUsersPage from './AdminUsersPage.vue'

/** Paginacja listy kont (BATCH_19) — jeden z sześciu ekranów z ustalenia R4 P1. */

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const { fetchUsers, createUser, updateUser } = vi.hoisted(() => ({
  fetchUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
}))
vi.mock('@/api/adminUsers', () => ({ fetchUsers, createUser, updateUser }))

function user(id: number) {
  return {
    id,
    email: `konto${id}@example.com`,
    display_name: `Konto ${id}`,
    role: 'user' as const,
    is_active: true,
  }
}

const TOTAL = 60
const PAGE_SIZE = 50
const ALL = Array.from({ length: TOTAL }, (_unused, index) => user(index + 1))

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(AdminUsersPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

describe('AdminUsersPage — paginacja', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchUsers.mockImplementation(({ offset = 0, limit = PAGE_SIZE }) =>
      Promise.resolve({ items: ALL.slice(offset, offset + limit), total: TOTAL }),
    )
  })

  it('pierwsza strona pokazuje limit kont i relację do całości', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-testid^="user-row-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="users-total"]').text()).toContain('50 z 60')
  })

  it('„pokaż więcej" dowozi ostatnie konto', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="users-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="user-row-"]')).toHaveLength(TOTAL)
    expect(wrapper.get(`[data-testid="user-row-${TOTAL}"]`).text()).toContain('Konto 60')
    expect(wrapper.find('[data-testid="users-load-more"]').exists()).toBe(false)
  })

  it('zbiór mieszczący się na stronie nie dostaje przycisku', async () => {
    fetchUsers.mockResolvedValue({ items: ALL.slice(0, 2), total: 2 })

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="users-load-more"]').exists()).toBe(false)
  })
})
