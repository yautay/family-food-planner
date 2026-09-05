/**
 * Paginacja list — JEDNO miejsce dla wszystkich ekranów listowych (ustalenie
 * REVIEW R4, BATCH_19).
 *
 * Wzorzec: **„pokaż więcej" z rosnącym `offset`**, nie numerowane strony.
 * Aplikacja jest mobile-first (06_UIUX §5), a numerowana paginacja na telefonie
 * to cele dotykowe wielkości znaczka pocztowego; „pokaż więcej" to jeden
 * przycisk ≥44 px i doładowanie BEZ utraty tego, co użytkownik już przewinął.
 *
 * Dlaczego `useInfiniteQuery`, a nie rosnący `limit` w zwykłym `useQuery`:
 *
 * 1. **Sufit `limit` to 200** (04_API §1). Rosnący limit rozbiłby się o niego
 *    przy 201. pozycji, a 07_SECURITY nie pozwala go obchodzić — „pokaż więcej"
 *    ma zwiększać `offset`, nie `limit`.
 * 2. **Rosnący limit pobiera wszystko od nowa.** Trzecie kliknięcie ściągałoby
 *    150 pozycji, żeby pokazać 50 nowych.
 * 3. **`offset` NIE wchodzi do klucza zapytań.** W `useInfiniteQuery` jest
 *    `pageParam`, więc klucz listy zostaje taki, jak przed tym batchem, a
 *    `invalidateQueries` po mutacji nadal trafia w całą listę (pułapka opisana
 *    w karcie B19: klucz z offsetem jako dziecko klucza indeksu psuje
 *    inwalidację — ta sama, którą B11 rozwiązał rozłącznymi prefiksami).
 *
 * Świadomy kompromis paginacji po `offset`: wstawienie albo usunięcie wiersza
 * między pobraniem stron przesuwa ich granice, więc ta sama pozycja może wejść
 * na dwie strony (a inna wypaść). Duplikaty ODSIEWAMY po `id` — bez tego Vue
 * dostaje dwa węzły z tym samym `:key` i psuje patchowanie listy. Odsiew NIE
 * naprawia pominięcia; naprawia je dopiero `invalidateQueries`, po którym
 * TanStack pobiera WSZYSTKIE wczytane strony na raz. Paginacja kursorowa
 * usunęłaby problem u źródła, ale wymaga zmiany kontraktu API (04_API §1),
 * czyli decyzji właściciela, a nie „ulepszenia przy okazji".
 */

import { useInfiniteQuery } from '@tanstack/vue-query'
import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'

/** Domyślny rozmiar strony — ten sam, co domyślny `limit` serwera (04_API §1). */
export const PAGE_SIZE = 50

/** Kształt odpowiedzi listowej z 04_API §1. */
export interface PageResponse<TItem> {
  items: TItem[]
  total: number
}

export interface PaginatedList<TItem> {
  /** Wszystkie wczytane pozycje, w kolejności serwera, bez duplikatów `id`. */
  items: ComputedRef<TItem[]>
  /** Ile pozycji ma zbiór po stronie serwera (do licznika „X z Y"). */
  total: ComputedRef<number>
  /** Ile pozycji jest już na ekranie. */
  loaded: ComputedRef<number>
  hasMore: ComputedRef<boolean>
  /** Prawda TYLKO do pierwszej odpowiedzi — skeleton (06_UIUX §3.4). */
  isPending: ComputedRef<boolean>
  /**
   * Prawda TYLKO wtedy, gdy nie ma CZEGO pokazać — czyli padła PIERWSZA strona.
   *
   * Nie jest tym samym co `query.isError`: nieudane doładowanie kolejnej strony
   * też ustawia stan błędu, a wtedy ekran ma zachować wiersze, które już
   * pokazuje. Bez tego rozdzielenia jedno nieudane „pokaż więcej" kasowało
   * z widoku 50 wczytanych pozycji, podczas gdy licznik dalej mówił „50 z 60"
   * — czyli wracał dokładnie ten rozjazd liczby z widokiem, który BATCH_19
   * likwiduje (znalezione przez `/code-review` na diffie tego batcha).
   */
  isError: ComputedRef<boolean>
  /** Padło DOŁADOWANIE, ale lista stoi — komunikat idzie na przycisk. */
  loadMoreFailed: ComputedRef<boolean>
  /** Doładowanie kolejnej strony = spinner NA PRZYCISKU, nie migotanie listy. */
  isLoadingMore: ComputedRef<boolean>
  loadMore: () => void
}

export interface PaginatedListOptions<TItem> {
  /** Klucz z `queryKeys` — BEZ `offset` (patrz nagłówek pliku). */
  queryKey: MaybeRefOrGetter<readonly unknown[]>
  fetchPage: (page: { limit: number; offset: number }) => Promise<PageResponse<TItem>>
  /** Nadpisanie rozmiaru strony; ekran zmienia go tylko z powodu domenowego. */
  pageSize?: number
}

export function usePaginatedList<TItem extends { id: number }>(
  options: PaginatedListOptions<TItem>,
): PaginatedList<TItem> {
  const pageSize = options.pageSize ?? PAGE_SIZE

  const query = useInfiniteQuery({
    queryKey: computed(() => toValue(options.queryKey)),
    queryFn: ({ pageParam }) => options.fetchPage({ limit: pageSize, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage: PageResponse<TItem>, allPages: PageResponse<TItem>[]) => {
      const loaded = allPages.reduce((sum, page) => sum + page.items.length, 0)
      // Pusta strona kończy listę NIEZALEŻNIE od `total`: gdyby serwer zwrócił
      // mniej wierszy, niż obiecuje licznik (wyścig z usunięciem), warunek na
      // samym `total` kazałby pytać w kółko o ten sam offset.
      return lastPage.items.length > 0 && loaded < lastPage.total ? loaded : undefined
    },
  })

  const pages = computed<PageResponse<TItem>[]>(() => query.data.value?.pages ?? [])

  /** Pozycje po odsiewie duplikatów `id` (patrz nagłówek pliku). */
  const items = computed<TItem[]>(() => {
    const byId = new Map<number, TItem>()
    for (const page of pages.value) {
      for (const item of page.items) {
        if (!byId.has(item.id)) {
          byId.set(item.id, item)
        }
      }
    }
    return [...byId.values()]
  })

  return {
    items,
    // `total` z OSTATNIEJ pobranej strony — najświeższy licznik serwera.
    total: computed(() => pages.value.at(-1)?.total ?? 0),
    // Licznik ma zgadzać się z tym, co WIDAĆ, więc liczy pozycje po odsiewie.
    // Do `offset` idzie natomiast surowa liczba pobranych wierszy — to ona,
    // a nie liczba unikatów, mówi serwerowi, gdzie skończyła się strona.
    loaded: computed(() => items.value.length),
    hasMore: computed(() => query.hasNextPage.value),
    isPending: computed(() => query.isPending.value),
    isError: computed(() => query.isError.value && pages.value.length === 0),
    loadMoreFailed: computed(() => query.isError.value && pages.value.length > 0),
    isLoadingMore: computed(() => query.isFetchingNextPage.value),
    loadMore: () => {
      void query.fetchNextPage()
    },
  }
}
