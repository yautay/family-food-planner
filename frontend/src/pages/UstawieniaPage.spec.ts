import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UstawieniaPage from './UstawieniaPage.vue'

const { fetchMyHousehold, fetchMyProfiles, createProfile, updateProfile, deleteProfile } =
  vi.hoisted(() => ({
    fetchMyHousehold: vi.fn(),
    fetchMyProfiles: vi.fn(),
    createProfile: vi.fn(),
    updateProfile: vi.fn(),
    deleteProfile: vi.fn(),
  }))

vi.mock('@/api/households', () => ({
  fetchMyHousehold,
  fetchMyProfiles,
  createProfile,
  updateProfile,
  deleteProfile,
}))

const HOUSEHOLD = { id: 1, name: 'Kowalscy' }
const MEMBER = {
  id: 10,
  email: 'anna@example.com',
  display_name: 'Anna',
  role: 'user' as const,
  is_active: true,
}
const PROFILE = {
  id: 100,
  household_id: 1,
  owner_user_id: null,
  name: 'Zosia',
  default_multiplier: '0.80',
  kcal_goal: '1400',
  is_active: true,
  created_at: '2026-08-16T10:00:00Z',
  updated_at: '2026-08-16T10:00:00Z',
}

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(UstawieniaPage, { global: { plugins: [VueQueryPlugin] } })
  await flushPromises()
  return wrapper
}

describe('UstawieniaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMyHousehold.mockResolvedValue({
      household: HOUSEHOLD,
      members: [MEMBER],
      profiles: [PROFILE],
    })
    fetchMyProfiles.mockResolvedValue({ items: [PROFILE], total: 1 })
  })

  it('pokazuje rodzinę, jej członków i profile', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="household-name"]').text()).toBe('Kowalscy')
    expect(wrapper.get('[data-testid="household-member-10"]').text()).toContain('anna@example.com')
    expect(wrapper.get('[data-testid="profile-row-100"]').text()).toContain('Zosia')
  })

  it('mnożnik pokazuje z przecinkiem dziesiętnym', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="profile-row-100"]').text()).toContain('0,80')
  })

  it('bez rodziny pokazuje stan pusty z instrukcją, bez sekcji profili', async () => {
    fetchMyHousehold.mockResolvedValue({ household: null, members: [], profiles: [] })
    fetchMyProfiles.mockResolvedValue({ items: [], total: 0 })

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="household-name"]').text()).toContain(
      'Nie należysz do rodziny',
    )
    expect(wrapper.find('[data-testid="profile-add"]').exists()).toBe(false)
  })

  it('pusta lista profili uczy, co zrobić dalej', async () => {
    fetchMyProfiles.mockResolvedValue({ items: [], total: 0 })

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="profiles-empty"]').text()).toContain('Dodaj pierwszego')
  })

  it('formularz wysyła mnożnik jako string dziesiętny z kropką', async () => {
    createProfile.mockResolvedValue(PROFILE)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-add"]').trigger('click')
    await wrapper.get('[data-testid="profile-name"]').setValue('Jaś')
    await wrapper.get('[data-testid="profile-multiplier"]').setValue('0,8')
    await wrapper.get('[data-testid="profile-kcal"]').setValue('1200')
    await wrapper.get('[data-testid="profile-form"]').trigger('submit')
    await flushPromises()

    expect(createProfile).toHaveBeenCalledWith({
      name: 'Jaś',
      default_multiplier: '0.8',
      kcal_goal: '1200',
      is_active: true,
    })
  })

  it('pusty cel kcal wysyłany jest jako null', async () => {
    createProfile.mockResolvedValue(PROFILE)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-add"]').trigger('click')
    await wrapper.get('[data-testid="profile-name"]').setValue('Jaś')
    await wrapper.get('[data-testid="profile-form"]').trigger('submit')
    await flushPromises()

    expect(createProfile).toHaveBeenCalledWith(
      expect.objectContaining({ kcal_goal: null, default_multiplier: '1' }),
    )
  })

  it.each([
    ['pusta nazwa', { name: '', multiplier: '1', kcal: '' }],
    ['mnożnik zerowy', { name: 'Jaś', multiplier: '0', kcal: '' }],
    ['mnożnik ujemny', { name: 'Jaś', multiplier: '-1', kcal: '' }],
    ['mnożnik z trzema miejscami', { name: 'Jaś', multiplier: '1,005', kcal: '' }],
    ['mnożnik nieliczbowy', { name: 'Jaś', multiplier: 'dużo', kcal: '' }],
    ['cel kcal ułamkowy', { name: 'Jaś', multiplier: '1', kcal: '1200,5' }],
    ['cel kcal zerowy', { name: 'Jaś', multiplier: '1', kcal: '0' }],
  ])('blokuje zapis: %s', async (_opis, dane) => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-add"]').trigger('click')
    await wrapper.get('[data-testid="profile-name"]').setValue(dane.name)
    await wrapper.get('[data-testid="profile-multiplier"]').setValue(dane.multiplier)
    await wrapper.get('[data-testid="profile-kcal"]').setValue(dane.kcal)

    expect(wrapper.get('[data-testid="profile-submit"]').attributes('disabled')).toBeDefined()
  })

  it('edycja wypełnia formularz wartościami profilu', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-edit-100"]').trigger('click')

    expect((wrapper.get('[data-testid="profile-name"]').element as HTMLInputElement).value).toBe(
      'Zosia',
    )
    expect(
      (wrapper.get('[data-testid="profile-multiplier"]').element as HTMLInputElement).value,
    ).toBe('0,80')
  })

  it('edycja wysyła PATCH na istniejący profil', async () => {
    updateProfile.mockResolvedValue({ ...PROFILE, name: 'Zofia' })
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-edit-100"]').trigger('click')
    await wrapper.get('[data-testid="profile-name"]').setValue('Zofia')
    await wrapper.get('[data-testid="profile-form"]').trigger('submit')
    await flushPromises()

    expect(updateProfile).toHaveBeenCalledWith(100, {
      name: 'Zofia',
      default_multiplier: '0.80',
      kcal_goal: '1400',
    })
    expect(createProfile).not.toHaveBeenCalled()
  })

  it('przełącznik aktywności odwraca bieżący stan', async () => {
    updateProfile.mockResolvedValue({ ...PROFILE, is_active: false })
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-active-100"]').trigger('click')
    await flushPromises()

    expect(updateProfile).toHaveBeenCalledWith(100, { is_active: false })
  })

  it('usunięcie profilu wymaga potwierdzenia', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-delete-100"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalled()
    expect(deleteProfile).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('potwierdzone usunięcie woła API', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    deleteProfile.mockResolvedValue(undefined)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="profile-delete-100"]').trigger('click')
    await flushPromises()

    expect(deleteProfile).toHaveBeenCalledWith(100)
    confirm.mockRestore()
  })
})
