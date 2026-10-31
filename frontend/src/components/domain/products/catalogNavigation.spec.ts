import { describe, expect, it } from 'vitest'
import { productCatalogQuery } from './catalogNavigation'

describe('powrót do biblioteki', () => {
  it('zachowuje znane filtry i głębokość stron, odrzuca redirect i niepoprawne ID', () => {
    expect(
      productCatalogQuery({
        q: '  płatki  ',
        category: '3',
        archived: '1',
        pages: '2',
        focus: '51',
        next: 'https://example.com',
        scope: 'private',
      }),
    ).toEqual({ q: 'płatki', category: '3', archived: '1', pages: '2', focus: '51' })
    expect(
      productCatalogQuery({ category: ['3'], pages: '-1', focus: '1.5', archived: 'true' }),
    ).toEqual({
      q: undefined,
      category: undefined,
      archived: undefined,
      pages: undefined,
      focus: undefined,
    })
  })
})
