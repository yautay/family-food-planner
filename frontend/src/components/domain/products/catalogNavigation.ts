import type { LocationQuery, LocationQueryRaw } from 'vue-router'

/** Budżet odtworzenia po zimnym wejściu, nie limit katalogu ani ręcznej paginacji. */
export const MAX_AUTOMATIC_RESTORE_PAGES = 3

/** Kontekst biblioteki: wyłącznie znane filtry i numery pozycji, bez redirect URL. */
export function productCatalogQuery(query: LocationQuery = {}): LocationQueryRaw {
  const positiveId = (value: unknown): string | undefined =>
    typeof value === 'string' && /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value))
      ? value
      : undefined
  return {
    q: typeof query.q === 'string' ? query.q.trim().slice(0, 200) || undefined : undefined,
    category: positiveId(query.category),
    archived: query.archived === '1' ? '1' : undefined,
    pages: positiveId(query.pages),
    focus: positiveId(query.focus),
  }
}
