import { describe, expect, it } from 'vitest'
import { messages } from '../../../src/i18n/messages'

function collectLeafKeys(input, parent = '') {
  return Object.entries(input).flatMap(([key, value]) => {
    const fullKey = parent ? `${parent}.${key}` : key

    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return collectLeafKeys(value, fullKey)
    }

    return [fullKey]
  })
}

describe('i18n message structure', () => {
  it('keeps matching keys for PL and EN locales', () => {
    const plKeys = collectLeafKeys(messages.pl).sort()
    const enKeys = collectLeafKeys(messages.en).sort()

    expect(plKeys).toEqual(enKeys)
  })
})
