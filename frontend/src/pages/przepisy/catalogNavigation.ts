import type { LocationQuery, LocationQueryRaw, Router } from 'vue-router'

import type { RecipesFilters } from '@/api/queryKeys'
import { PAGE_SIZE } from '@/api/pagination'

/** URL opisuje cały zbiór serwera, nigdy tylko pobraną stronę. */
export function catalogFilters(query: LocationQuery): RecipesFilters {
  const rawTags = Array.isArray(query.tag) ? query.tag : [query.tag]
  const tag = [
    ...new Set(
      rawTags
        .filter((id): id is string => typeof id === 'string')
        .filter((id) => /^[1-9]\d*$/.test(id))
        .map(Number)
        .filter(Number.isSafeInteger),
    ),
  ].sort((a, b) => a - b)
  return {
    limit: PAGE_SIZE,
    q: typeof query.q === 'string' ? query.q.trim().slice(0, 200) || undefined : undefined,
    tag: tag.length ? tag : undefined,
    scope:
      query.scope === 'global' || query.scope === 'household' || query.scope === 'private'
        ? query.scope
        : undefined,
    prep_time_max: query.prep_time_max === '30' ? 30 : undefined,
  }
}

/** Wyłącznie znane filtry i kalendarzowy kontekst UX02, bez adresu przekierowania. */
export function catalogQuery(query: LocationQuery): LocationQueryRaw {
  const filters = catalogFilters(query)
  return {
    q: filters.q,
    tag: filters.tag?.map(String),
    scope: filters.scope,
    prep_time_max: filters.prep_time_max ? '30' : undefined,
    selectedDate: query.selectedDate,
    from: query.from,
    to: query.to,
  }
}

/** Wstecz wykorzystuje savedPosition zamrożonego scrollBehavior UX02. */
export function returnToCatalog(event: MouseEvent, router: Router, query: LocationQuery): void {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const target = router.resolve({ name: 'przepisy', query: catalogQuery(query) })
  const back = router.options.history.state.back
  const previous = typeof back === 'string' ? router.resolve(back) : null
  if (
    previous?.name === 'przepisy' &&
    router.resolve({ name: 'przepisy', query: catalogQuery(previous.query) }).fullPath ===
      target.fullPath
  ) {
    event.preventDefault()
    router.back()
  }
}
