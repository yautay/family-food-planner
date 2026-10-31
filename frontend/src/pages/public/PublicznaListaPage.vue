<script setup lang="ts">
/**
 * Publiczna lista zakupowa (`/l/:token`) — POZA `AppShell` i poza guardem sesji.
 *
 * Ta strona jest umową z osobą, która nie ma konta: pokazuje treść listy,
 * pozwala odhaczać i nic więcej (ADR-010). Cztery konsekwencje w kodzie:
 *
 * 1. **Własny, minimalny layout.** Nie ma sidebara, bottom-nava ani nazwy
 *    rodziny — shell ciągnąłby stan sesji i menu, których ta strona nie ma
 *    prawa pokazywać. Logo jest TEKSTOWE, bez linków w głąb aplikacji.
 * 2. **Własny klient HTTP** (`api/publicList.ts`): bez cookies i bez CSRF.
 *    Otwarcie linku na zalogowanej przeglądarce nie wysyła cudzej sesji.
 * 3. **404 i 410 to JEDEN ekran** („Ta lista zakupowa już wygasła lub została
 *    usunięta.") — nie zdradzamy, czy token kiedykolwiek istniał (karta B11,
 *    Implementation Notes pkt 5).
 * 4. **Optimistic odhaczanie + kolejka offline** (B12, ADR-009): sklep i słaby
 *    zasięg to ten sam problem u zalogowanego i u osoby z linkiem, więc obie
 *    strony dostają ten sam mechanizm. Różnica jest jedna i istotna: tutaj
 *    „lista zniknęła" (410 przy synchronizacji po powrocie sieci) jest
 *    NORMALNYM końcem — token wygasa sam z siebie, więc kolejka dla niego
 *    idzie do kosza, a strona pokazuje ten sam ekran co przy wejściu na
 *    wygasły link. Ponawianie byłoby pętlą na martwym tokenie (AC 6).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import type { PublicList, PublicListItem } from '@/api/publicList'
import {
  PublicListRequestError,
  PublicListUnavailableError,
  checkPublicListItem,
  fetchPublicList,
} from '@/api/publicList'
import { queryKeys } from '@/api/queryKeys'
import OfflineBanner from '@/components/domain/OfflineBanner.vue'
import ShoppingChecklistSection from '@/components/domain/ShoppingChecklistSection.vue'
import ShoppingItemRow from '@/components/domain/ShoppingItemRow.vue'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/dates'
import {
  OfflineStorageError,
  deleteSnapshot,
  saveSnapshot,
  targetKey,
  type QueueTarget,
} from '@/lib/offline/db'
import { hydrateFromSnapshot } from '@/lib/offline/hydrate'
import { publicList as texts } from '@/lib/texts'
import { useOfflineQueueStore } from '@/stores/offlineQueue'

const route = useRoute()
const queryClient = useQueryClient()

const token = computed(() => String(route.params.token ?? ''))
const listKey = computed(() => queryKeys.publicList.detail(token.value))

const offlineQueue = useOfflineQueueStore()
const list = useQuery({
  queryKey: listKey,
  queryFn: async () => {
    const requested = token.value
    let loaded: PublicList
    try {
      loaded = await fetchPublicList(requested)
    } catch (error) {
      if (error instanceof PublicListRequestError && error.status === 0) offlineQueue.markOffline()
      throw error
    }
    const queued = new Map(
      offlineQueue.pending
        .filter((entry) => entry.target.kind === 'public' && entry.target.token === requested)
        .map((entry) => [entry.itemId, entry.checked]),
    )
    return {
      ...loaded,
      items: loaded.items.map((item) =>
        queued.has(item.id) ? { ...item, checked: queued.get(item.id)! } : item,
      ),
    }
  },
  enabled: computed(() => token.value.length > 0),
  // Wygasły link nie naprawi się przez ponowienie — retry tylko dla błędów sieci.
  retry: (attempt, error) => !(error instanceof PublicListUnavailableError) && attempt < 1,
})

const target = computed<QueueTarget>(() => ({ kind: 'public', token: token.value }))
const pendingChanges = computed(() => offlineQueue.pendingFor(target.value))
const waitingToRetry = computed(() =>
  offlineQueue.pending.some(
    (entry) => targetKey(entry.target) === targetKey(target.value) && entry.attempts > 0,
  ),
)
const actionError = ref<string | null>(null)
const unavailableToken = ref<string | null>(null)
const changingItems = ref(new Set<string>())
const snapshotFailed = ref(false)
watch(token, () => {
  actionError.value = null
})

const detail = computed<PublicList | null>(() => {
  void list.data.value
  return queryClient.getQueryData<PublicList>(listKey.value) ?? null
})
/**
 * „Wygasła" ma dwa źródła i oba muszą prowadzić do tego samego ekranu:
 * odpowiedź na wejściu ORAZ 410 złapane przez kolejkę przy synchronizacji
 * (token mógł wygasnąć, gdy telefon był bez zasięgu — AC 6).
 */
const isUnavailable = computed(
  () =>
    unavailableToken.value === token.value ||
    list.error.value instanceof PublicListUnavailableError ||
    offlineQueue.isGone(target.value),
)
watch(isUnavailable, (unavailable) => {
  if (unavailable) {
    unavailableToken.value = token.value
    queryClient.removeQueries({ queryKey: listKey.value, exact: true })
    void deleteSnapshot(targetKey(target.value))
  }
})
const isOtherError = computed(
  () => list.isError.value && !isUnavailable.value && detail.value === null,
)
const items = computed(() => detail.value?.items ?? [])
const checkedCount = computed(() => items.value.filter((item) => item.checked).length)

/** Sekcje z płaskiej listy: kolejność ustalił SERWER, więc tylko grupujemy. */
const sections = computed(() => {
  const groups: { name: string; items: PublicList['items'] }[] = []
  for (const item of items.value) {
    const last = groups.at(-1)
    if (last && last.name === item.category_name) {
      last.items.push(item)
    } else {
      groups.push({ name: item.category_name, items: [item] })
    }
  }
  return groups
})

/**
 * Snapshot z IndexedDB → cache TanStack Query + nasłuch synchronizacji,
 * jak na stronie zalogowanej. Obserwujemy KLUCZ, bo token jest parametrem
 * trasy i może się zmienić bez przemontowania komponentu.
 */
watch(
  () => (token.value.length > 0 ? targetKey(target.value) : null),
  (snapshotKey, _previous, onCleanup) => {
    if (snapshotKey === null) {
      return
    }
    const key = listKey.value
    void hydrateFromSnapshot<PublicList>(queryClient, key, snapshotKey)
    onCleanup(
      offlineQueue.subscribeToSync(target.value, () => {
        void queryClient.invalidateQueries({ queryKey: key })
      }),
    )
  },
  { immediate: true },
)

watch(
  () => detail.value,
  (value) => {
    if (value && !isUnavailable.value) {
      const recipient = target.value
      void saveSnapshot(targetKey(recipient), value).then((saved) => {
        if (targetKey(recipient) === targetKey(target.value)) snapshotFailed.value = !saved
      })
    }
  },
  { immediate: true },
)

/**
 * Wyślij odhaczenie albo odłóż je do kolejki. `null` = poszło do kolejki.
 *
 * Kolejkujemy też, gdy `fetch` padł mimo `navigator.onLine === true`
 * (`PublicListRequestError` ze statusem 0) — tak wygląda sklepowe Wi-Fi, które
 * ma sygnał i nie ma internetu.
 */
async function toggleItem(payload: {
  itemId: number
  checked: boolean
  token: string
}): Promise<PublicListItem | null> {
  const recipient: QueueTarget = { kind: 'public', token: payload.token }
  if (offlineQueue.isOffline) {
    await offlineQueue.enqueue(recipient, payload.itemId, payload.checked, snapshotFor(payload))
    return null
  }
  try {
    const item = await checkPublicListItem(payload.token, payload.itemId, payload.checked)
    await offlineQueue.forget(recipient, payload.itemId)
    return item
  } catch (error) {
    if (error instanceof PublicListRequestError && error.status === 0) {
      offlineQueue.markOffline()
      await offlineQueue.enqueue(recipient, payload.itemId, payload.checked, snapshotFor(payload))
      return null
    }
    throw error
  }
}

function snapshotFor(payload: {
  token: string
  itemId: number
  checked: boolean
}): PublicList | undefined {
  const current = queryClient.getQueryData<PublicList>(queryKeys.publicList.detail(payload.token))
  return (
    current && {
      ...current,
      items: current.items.map((item) =>
        item.id === payload.itemId ? { ...item, checked: payload.checked } : item,
      ),
    }
  )
}

const toggle = useMutation({
  mutationFn: toggleItem,
  onMutate: async (payload) => {
    const key = queryKeys.publicList.detail(payload.token)
    await queryClient.cancelQueries({ queryKey: key })
    const previous = queryClient.getQueryData<PublicList>(key)
    const previousItem = previous?.items.find((item) => item.id === payload.itemId)
    if (previous) {
      queryClient.setQueryData<PublicList>(key, {
        ...previous,
        items: previous.items.map((item) =>
          item.id === payload.itemId ? { ...item, checked: payload.checked } : item,
        ),
      })
    }
    return { previousItem, key }
  },
  onError: (error, payload, context) => {
    if (error instanceof PublicListUnavailableError) {
      unavailableToken.value = payload.token
      return
    }
    if (context?.previousItem) {
      const previousItem = context.previousItem
      queryClient.setQueryData<PublicList>(
        context.key,
        (current) =>
          current && {
            ...current,
            items: current.items.map((item) => (item.id === previousItem.id ? previousItem : item)),
          },
      )
    }
    if (payload.token === token.value)
      actionError.value =
        error instanceof OfflineStorageError
          ? error.message
          : 'Nie udało się zapisać odhaczenia. Zmiana została cofnięta. Spróbuj ponownie.'
  },
  onSuccess: (item, payload) => {
    if (payload.token === token.value) actionError.value = null
    // `null` = zmiana czeka w kolejce; stan optimistic jest jedynym, jaki mamy.
    if (item === null) {
      const snapshot = snapshotFor(payload)
      if (snapshot) queryClient.setQueryData(queryKeys.publicList.detail(payload.token), snapshot)
      return
    }
    const key = queryKeys.publicList.detail(payload.token)
    const current = queryClient.getQueryData<PublicList>(key)
    if (!current) {
      return
    }
    queryClient.setQueryData<PublicList>(key, {
      ...current,
      items: current.items.map((existing) => (existing.id === item.id ? item : existing)),
    })
  },
  onSettled: (_item, _error, payload) => {
    const next = new Set(changingItems.value)
    next.delete(`${payload.token}:${payload.itemId}`)
    changingItems.value = next
  },
})

function requestToggle(payload: { itemId: number; checked: boolean }): void {
  const key = `${token.value}:${payload.itemId}`
  if (changingItems.value.has(key) || isUnavailable.value) return
  changingItems.value = new Set([...changingItems.value, key])
  toggle.mutate({ ...payload, token: token.value })
}

function printList(): void {
  window.print()
}
</script>

<template>
  <main
    class="shopping-list bg-background text-foreground min-h-dvh"
    data-testid="public-list-page"
  >
    <div class="mx-auto grid w-full max-w-3xl gap-6 px-4 py-6">
      <header class="grid min-w-0 gap-2">
        <p class="text-muted-foreground text-xs tracking-wide uppercase print:hidden">
          {{ texts.brand }}
        </p>
        <h1
          class="font-serif text-3xl leading-tight wrap-anywhere sm:text-4xl"
          data-testid="public-list-title"
        >
          {{ isUnavailable ? texts.heading : (detail?.name ?? texts.heading) }}
        </h1>
        <p
          v-if="detail && !isUnavailable"
          class="text-muted-foreground text-sm print:hidden"
          data-testid="public-list-meta"
          aria-live="polite"
        >
          {{ texts.expiresAt(formatDate(detail.expires_at.slice(0, 10))) }} ·
          {{ texts.progress(checkedCount, items.length) }}
        </p>
      </header>
      <OfflineBanner
        v-if="!isUnavailable"
        :offline="offlineQueue.isOffline"
        :pending="pendingChanges"
        :syncing="pendingChanges > 0 && offlineQueue.flushing"
        :retrying="waitingToRetry"
        :error="offlineQueue.errorFor(target)"
      />
      <p
        v-if="snapshotFailed && !isUnavailable"
        class="text-warning text-sm print:hidden"
        role="alert"
        data-testid="public-list-storage-error"
      >
        Zapis offline jest niedostępny na tym urządzeniu. Odhaczenia wymagają działającego
        połączenia.
      </p>
      <section
        v-if="isUnavailable"
        class="border-border bg-card grid gap-2 rounded-xl border p-4"
        data-testid="public-list-unavailable"
      >
        <p class="font-medium">{{ texts.unavailable }}</p>
        <p class="text-muted-foreground text-sm">{{ texts.unavailableHint }}</p>
      </section>
      <p v-else-if="list.isPending.value" class="text-muted-foreground text-sm" role="status">
        {{ texts.loading }}
      </p>
      <section
        v-else-if="isOtherError"
        class="border-border bg-card grid gap-3 rounded-xl border p-4"
        data-testid="public-list-error"
      >
        <p class="font-medium">{{ list.error.value?.message }}</p>
        <Button
          class="justify-self-start"
          data-testid="public-list-retry"
          @click="list.refetch()"
          >{{ texts.retry }}</Button
        >
      </section>
      <template v-else>
        <p
          v-if="list.isError.value"
          class="text-warning text-sm print:hidden"
          role="alert"
          data-testid="public-list-refresh-error"
        >
          Nie udało się odświeżyć listy. Wyświetlane są ostatnio zapisane dane.
          <button class="min-h-11 underline" @click="list.refetch()">{{ texts.retry }}</button>
        </p>
        <p
          v-if="actionError"
          class="text-destructive text-sm print:hidden"
          role="alert"
          data-testid="public-list-toggle-error"
        >
          {{ actionError }}
        </p>
        <p
          v-if="items.length === 0"
          class="text-muted-foreground text-sm"
          data-testid="public-list-empty"
        >
          {{ texts.empty }}
        </p>
        <ShoppingChecklistSection
          v-for="(section, index) in sections"
          :key="`${section.name}-${index}`"
          :name="section.name"
          :items="section.items"
          :data-testid="`public-section-${index}`"
        >
          <template #item="{ item, collapsed }">
            <ShoppingItemRow
              :class="{ 'shopping-item-collapsed': collapsed }"
              :item-id="item.id"
              :label="item.label"
              :amount="item.amount"
              :unit="item.unit"
              :checked="item.checked"
              :already-have="item.already_have"
              :leftover="item.leftover_amount"
              :packages-count="item.packages_count"
              :package-size="item.package_size"
              :disabled="changingItems.has(`${token}:${item.id}`)"
              @toggle="requestToggle"
            />
          </template>
        </ShoppingChecklistSection>
        <footer class="grid gap-2 print:hidden">
          <Button
            variant="outline"
            class="justify-self-start"
            data-testid="public-list-print"
            @click="printList"
            >Drukuj</Button
          >
          <p class="text-muted-foreground text-xs">{{ texts.offlineHint }}</p>
        </footer>
      </template>
    </div>
  </main>
</template>
