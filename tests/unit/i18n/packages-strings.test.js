import { describe, expect, it } from 'vitest'
import { messages } from '../../../src/i18n/messages'

describe('packages i18n labels', () => {
  const requiredKeys = [
    'title',
    'description',
    'listTitle',
    'ingredientColumn',
    'typeColumn',
    'typeName',
    'gramsPerPackage',
    'samplesCount',
    'source',
    'selectIngredient',
    'manualTypeName',
    'addButton',
    'addTitle',
    'editTitle',
    'addSubmit',
    'updateButton',
    'deleteConfirm',
    'empty',
  ]

  it('defines package mapping labels for all locales', () => {
    for (const locale of ['pl', 'en']) {
      const section = messages[locale]?.packages
      expect(section).toBeTruthy()

      for (const key of requiredKeys) {
        expect(typeof section[key]).toBe('string')
        expect(section[key].length).toBeGreaterThan(0)
      }
    }
  })
})
