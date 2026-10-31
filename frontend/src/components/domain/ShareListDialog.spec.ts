import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ShoppingListsApi from '@/api/shoppingLists'

import ShareListDialog from './ShareListDialog.vue'

/**
 * Panel udostępniania — trzy stany z karty B11 §Tests i wymóg ADR-010, żeby
 * kontrolka „Odwołaj link" była WIDOCZNA przy aktywnym linku (a nie schowana).
 *
 * Testujemy też to, co łatwo zepsuć bez zauważenia: adres w QR/schowku musi być
 * PEŁNY (origin + ścieżka), bo relatywny `/l/token` po zeskanowaniu telefonem
 * nie prowadzi nigdzie.
 */
const { shareShoppingList, revokeShoppingListShare } = vi.hoisted(() => ({
  shareShoppingList: vi.fn(),
  revokeShoppingListShare: vi.fn(),
}))

vi.mock('@/api/shoppingLists', async () => {
  const actual = await vi.importActual<typeof ShoppingListsApi>('@/api/shoppingLists')
  return { ...actual, shareShoppingList, revokeShoppingListShare }
})

function share(overrides: Record<string, unknown> = {}) {
  return {
    url: '/l/tokentokentokentokentokentokentokentoken123',
    expires_at: '2030-01-14T12:00:00Z',
    revoked: false,
    ...overrides,
  }
}

async function mountDialog(props: Record<string, unknown> = {}) {
  const wrapper = mount(ShareListDialog, {
    props: { open: true, listId: 5, share: null, ...props },
    global: { plugins: [VueQueryPlugin] },
  })
  await flushPromises()
  return wrapper
}

describe('ShareListDialog', () => {
  it('offline blokuje tworzenie i odwołanie z widocznym powodem', async () => {
    const empty = await mountDialog({ offline: true })
    expect(empty.get('[data-testid="share-create"]').attributes('disabled')).toBeDefined()
    expect(empty.get('[data-testid="share-needs-network"]').text()).toContain('wymaga połączenia')
    const active = await mountDialog({ offline: true, share: share() })
    expect(active.get('[data-testid="share-revoke"]').attributes('disabled')).toBeDefined()
    expect(shareShoppingList).not.toHaveBeenCalled()
    expect(revokeShoppingListShare).not.toHaveBeenCalled()
  })

  it('wygasły link nie jest reklamowany jako aktywny', async () => {
    const wrapper = await mountDialog({ share: share({ expires_at: '2020-01-01T00:00:00Z' }) })
    expect(wrapper.find('[data-testid="share-active"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="share-url"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="share-expired"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="share-create"]').exists()).toBe(true)
  })
  beforeEach(() => {
    vi.clearAllMocks()
    shareShoppingList.mockResolvedValue(share())
    revokeShoppingListShare.mockResolvedValue(undefined)
  })

  it('stan „brak linku": zachęta i wybór ważności z domyślnymi 7 dniami (ADR-010)', async () => {
    const wrapper = await mountDialog()

    expect(wrapper.find('[data-testid="share-none"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="share-url"]').exists()).toBe(false)
    const domyslny = wrapper.get('[data-testid="share-validity-7"]').element as HTMLInputElement
    expect(domyslny.checked).toBe(true)
  })

  it('utworzenie linku wysyła WYBRANĄ ważność, a nie domyślną', async () => {
    const wrapper = await mountDialog()

    await wrapper.get('[data-testid="share-validity-30"]').setValue()
    await wrapper.get('[data-testid="share-create"]').trigger('click')
    await flushPromises()

    expect(shareShoppingList).toHaveBeenCalledWith(5, { expires_in_days: 30 })
  })

  it('stan „aktywny": pełny URL, data ważności i WIDOCZNE odwołanie linku', async () => {
    const wrapper = await mountDialog({ share: share() })

    expect(wrapper.get('[data-testid="share-active"]').text()).toBe('Link aktywny do 14.01.2030')
    expect(wrapper.get('[data-testid="share-url"]').text()).toBe(
      `${window.location.origin}/l/tokentokentokentokentokentokentokentoken123`,
    )
    // ADR-010: kontrolka odwołania jest zawsze widoczna przy aktywnym linku.
    expect(wrapper.find('[data-testid="share-revoke"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="share-create"]').exists()).toBe(false)
  })

  it('stan „odwołany": komunikat + propozycja NOWEGO linku (stary nie wraca)', async () => {
    const wrapper = await mountDialog({ share: share({ revoked: true }) })

    expect(wrapper.find('[data-testid="share-revoked"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="share-create"]').text()).toBe('Utwórz nowy link')
    expect(wrapper.find('[data-testid="share-url"]').exists()).toBe(false)
  })

  it('odwołanie pyta o potwierdzenie i dopiero wtedy woła API', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = await mountDialog({ share: share() })

    await wrapper.get('[data-testid="share-revoke"]').trigger('click')
    expect(revokeShoppingListShare).not.toHaveBeenCalled()

    confirmSpy.mockReturnValue(true)
    await wrapper.get('[data-testid="share-revoke"]').trigger('click')
    await flushPromises()

    expect(revokeShoppingListShare).toHaveBeenCalledWith(5)
    confirmSpy.mockRestore()
  })

  it('kopiowanie wkłada do schowka PEŁNY adres', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const wrapper = await mountDialog({ share: share() })

    await wrapper.get('[data-testid="share-copy"]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(
      `${window.location.origin}/l/tokentokentokentokentokentokentokentoken123`,
    )
    expect(wrapper.find('[data-testid="share-copied"]').exists()).toBe(true)
  })

  it('systemowe „Wyślij" pokazuje się tylko tam, gdzie Web Share API istnieje', async () => {
    const bezShare = await mountDialog({ share: share() })
    expect(bezShare.find('[data-testid="share-system"]').exists()).toBe(false)

    Object.assign(navigator, { share: vi.fn().mockResolvedValue(undefined) })
    const zeShare = await mountDialog({ share: share() })
    expect(zeShare.find('[data-testid="share-system"]').exists()).toBe(true)
    // Sprzątamy: `navigator` jest wspólny dla całego pliku testowego.
    Reflect.deleteProperty(navigator, 'share')
  })

  it('zamknięty panel nie renderuje niczego', async () => {
    const wrapper = await mountDialog({ open: false, share: share() })

    expect(wrapper.find('[data-testid="share-dialog"]').exists()).toBe(false)
  })
})
