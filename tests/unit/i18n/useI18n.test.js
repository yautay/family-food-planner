import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUiStore } from '../../../src/stores/uiStore'
import { useI18n } from '../../../src/composables/useI18n'

describe('useI18n', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('interpolates dynamic params', () => {
    const uiStore = useUiStore()
    uiStore.setLocale('en')

    const { t } = useI18n()
    const result = t('footer.copyright', { year: '2030' })

    expect(result).toContain('2030')
  })

  it('returns translation fallback key when missing', () => {
    const { t } = useI18n()

    expect(t('unknown.path.key')).toBe('unknown.path.key')
  })
})
