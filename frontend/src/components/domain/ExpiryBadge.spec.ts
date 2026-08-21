import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ExpiryBadge from './ExpiryBadge.vue'
import { EXPIRY_SOON_DAYS, expiryStatus } from '@/lib/expiry'

const TODAY = '2026-08-21'

function mountBadge(expiryDate: string | null) {
  return mount(ExpiryBadge, { props: { expiryDate, today: TODAY } })
}

describe('progi wyróżnienia daty ważności', () => {
  it('dzień po dacie to „po terminie"', () => {
    expect(expiryStatus('2026-08-20', TODAY)).toBe('expired')
  })

  it('dzisiejsza data jeszcze się nie przeterminowała', () => {
    expect(expiryStatus(TODAY, TODAY)).toBe('soon')
  })

  it('ostatni dzień progu liczy się jako „kończy się"', () => {
    expect(expiryStatus('2026-08-28', TODAY)).toBe('soon')
    expect(EXPIRY_SOON_DAYS).toBe(7)
  })

  it('dzień po progu jest już neutralny', () => {
    expect(expiryStatus('2026-08-29', TODAY)).toBe('ok')
  })

  it('brak daty to osobny stan, nie zero', () => {
    expect(expiryStatus(null, TODAY)).toBe('none')
  })
})

describe('ExpiryBadge', () => {
  it('przeterminowane pokazuje kolor I tekst (06_UIUX §1)', () => {
    const wrapper = mountBadge('2026-08-01')

    expect(wrapper.get('[data-testid="expiry-badge-expired"]').text()).toContain('Po terminie')
    expect(wrapper.get('[data-testid="expiry-badge-expired"]').classes()).toContain(
      'text-destructive',
    )
  })

  it('kończące się dostaje bursztyn i datę po polsku', () => {
    const wrapper = mountBadge('2026-08-25')

    const badge = wrapper.get('[data-testid="expiry-badge-soon"]')
    expect(badge.text()).toContain('25.08.2026')
    expect(badge.classes()).toContain('text-warning')
  })

  it('odległa data nie krzyczy kolorem', () => {
    const wrapper = mountBadge('2027-01-01')

    expect(wrapper.get('[data-testid="expiry-badge-ok"]').text()).toContain('Ważne do 01.01.2027')
  })

  it('pozycja bez daty mówi to wprost', () => {
    const wrapper = mountBadge(null)

    expect(wrapper.get('[data-testid="expiry-badge-none"]').text()).toBe('Bez daty ważności')
  })
})
