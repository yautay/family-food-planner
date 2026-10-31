<script setup lang="ts">
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { ShoppingListDetail, ShoppingListItem } from '@/api/shoppingLists'
import {
  acceptListToPantry,
  deleteShoppingList,
  fetchShoppingList,
  updateShoppingList,
  updateShoppingListItem,
} from '@/api/shoppingLists'
import type { Store } from '@/api/stores'
import { fetchStores } from '@/api/stores'
import OfflineBanner from '@/components/domain/OfflineBanner.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import ShareListDialog from '@/components/domain/ShareListDialog.vue'
import ShoppingChecklistSection from '@/components/domain/ShoppingChecklistSection.vue'
import ShoppingItemRow from '@/components/domain/ShoppingItemRow.vue'
import StorePicker from '@/components/domain/StorePicker.vue'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/dates'
import { formatAmount } from '@/lib/format'
import { OfflineStorageError, saveSnapshot, targetKey, type QueueTarget } from '@/lib/offline/db'
import { hydrateFromSnapshot } from '@/lib/offline/hydrate'
import {
  getPrivateOfflineScope,
  isPrivateOfflineScopeCurrent,
  subscribePrivateOfflineScope,
} from '@/lib/offline/privateSession'
import { common, offline as offlineTexts, shoppingList as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'
import { useOfflineQueueStore } from '@/stores/offlineQueue'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const auth = useAuthStore()
const offlineQueue = useOfflineQueueStore()
const scope = ref(getPrivateOfflineScope())
const epoch = ref(0)
const listId = computed(() => Number(route.params.id))
const hasValidId = computed(() => Number.isInteger(listId.value) && listId.value > 0)
const shareOpen = ref(false)
const acceptOpen = ref(false)
const deleteOpen = ref(false)
const actionError = ref<string | null>(null)
const actionInfo = ref<string | null>(null)
const snapshotFailed = ref(false)
const changingItems = ref(new Set<string>())

function resetActions(): void {
  shareOpen.value = false
  acceptOpen.value = false
  deleteOpen.value = false
  actionError.value = null
  actionInfo.value = null
  snapshotFailed.value = false
}
onScopeDispose(
  subscribePrivateOfflineScope((next) => {
    scope.value = next
    epoch.value += 1
    resetActions()
  }),
)
watch(
  () => JSON.stringify([auth.user?.id ?? null, auth.household?.id ?? null]),
  () => {
    epoch.value += 1
    resetActions()
  },
  { flush: 'sync' },
)
watch(listId, resetActions)

const accessAllowed = computed(
  () => auth.isAuthenticated || (auth.offlineSession && scope.value !== null),
)
function keyFor(id: number, capturedScope: string | null, capturedEpoch: number): QueryKey {
  return [...queryKeys.shopping.list(id), 'private', capturedScope ?? `online:${capturedEpoch}`]
}
const listKey = computed(() => keyFor(listId.value, scope.value, epoch.value))
const viewToken = computed(() => JSON.stringify(listKey.value))
const target = computed<QueueTarget | null>(() =>
  scope.value === null ? null : { kind: 'list', listId: listId.value, scope: scope.value },
)
type Access = {
  id: number
  scope: string | null
  epoch: number
  key: QueryKey
  token: string
  target: QueueTarget | null
}
type Toggle = { itemId: number; checked: boolean; access: Access }
function capture(): Access {
  return {
    id: listId.value,
    scope: scope.value,
    epoch: epoch.value,
    key: listKey.value,
    token: viewToken.value,
    target: target.value,
  }
}
function current(access: Access): boolean {
  return (
    access.epoch === epoch.value &&
    access.scope === scope.value &&
    accessAllowed.value &&
    (access.scope === null ? auth.isAuthenticated : isPrivateOfflineScopeCurrent(access.scope))
  )
}
class StaleAccessError extends Error {
  constructor() {
    super('Sesja listy uległa zmianie. Otwórz listę ponownie.')
  }
}
function assertCurrent(access: Access): void {
  if (!current(access)) throw new StaleAccessError()
}
function assertOnline(access: Access): void {
  assertCurrent(access)
  if (!auth.isAuthenticated || offlineQueue.isOffline)
    throw new Error('Ta operacja wymaga połączenia i potwierdzonej sesji.')
}
async function handleReadError(error: unknown, access: Access): Promise<never> {
  assertCurrent(access)
  if (error instanceof ApiError) {
    if (error.status === 0) offlineQueue.markOffline()
    if (error.status === 401) auth.clear()
    if ([404, 410].includes(error.status) && access.target)
      await offlineQueue.markGone(access.target)
  }
  throw error
}
async function fetchListWithPending(access: Access): Promise<ShoppingListDetail> {
  assertCurrent(access)
  let loaded: ShoppingListDetail
  try {
    loaded = await fetchShoppingList(access.id)
  } catch (error) {
    return handleReadError(error, access)
  }
  assertCurrent(access)
  const queued = new Map(
    offlineQueue.pending
      .filter(
        (entry) => access.target !== null && targetKey(entry.target) === targetKey(access.target),
      )
      .map((entry) => [entry.itemId, entry.checked]),
  )
  return {
    ...loaded,
    sections: loaded.sections.map((section) => ({
      ...section,
      items: section.items.map((item) =>
        queued.has(item.id) ? { ...item, checked: queued.get(item.id)! } : item,
      ),
    })),
  }
}
const list = useQuery(
  computed(() => {
    const access = capture()
    return {
      queryKey: access.key,
      queryFn: () => fetchListWithPending(access),
      enabled: hasValidId.value && accessAllowed.value,
      retry: false,
    }
  }),
)
// Czytamy cache BIEŻĄCEGO klucza: observer może przez jeden tick pamiętać
// poprzednią odpowiedź, zanim zareaguje na synchroniczną zmianę scope.
const detail = computed(() => {
  void list.data.value
  return current(capture()) && !offlineQueue.isGone(target.value)
    ? (queryClient.getQueryData<ShoppingListDetail>(listKey.value) ?? null)
    : null
})
const pendingChanges = computed(() => offlineQueue.pendingFor(target.value))
const waitingToRetry = computed(() =>
  offlineQueue.pending.some(
    (entry) =>
      target.value !== null &&
      targetKey(entry.target) === targetKey(target.value) &&
      entry.attempts > 0,
  ),
)
const checking = computed(() =>
  [...changingItems.value].some((key) => key.startsWith(`${viewToken.value}#`)),
)
const checkError = computed(() => offlineQueue.errorFor(target.value))
const storageUnavailable = computed(() => scope.value === null || snapshotFailed.value)
const awaitingChecks = computed(
  () =>
    checking.value ||
    pendingChanges.value > 0 ||
    offlineQueue.needsReconciliation(target.value) ||
    list.isFetching.value ||
    list.isError.value,
)

watch(
  () => (hasValidId.value && target.value ? targetKey(target.value) : null),
  (snapshotKey, _previous, onCleanup) => {
    if (snapshotKey === null) return
    const access = capture()
    void hydrateFromSnapshot<ShoppingListDetail>(queryClient, access.key, snapshotKey)
    onCleanup(
      offlineQueue.subscribeToSync(access.target!, () => {
        if (!current(access)) return
        if (offlineQueue.isGone(access.target))
          queryClient.removeQueries({ queryKey: access.key, exact: true })
        else void reconcileList(access)
        void queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
      }),
    )
    if (offlineQueue.needsReconciliation(access.target) && !offlineQueue.isOffline)
      void reconcileList(access)
  },
  { immediate: true },
)
watch(
  () => detail.value,
  (value) => {
    const access = capture()
    if (!value || !access.target || !current(access)) return
    void saveSnapshot(targetKey(access.target), value).then((saved) => {
      if (current(access)) snapshotFailed.value = !saved
    })
  },
  { immediate: true },
)

const storeFilters = computed(() => ({ include_archived: false }))
const stores = useQuery({
  queryKey: computed(() => queryKeys.stores.list(storeFilters.value)),
  queryFn: () => fetchStores(storeFilters.value),
  enabled: computed(() => auth.isAuthenticated && !offlineQueue.isOffline),
})
const sections = computed(() => detail.value?.sections ?? [])
const items = computed(() => sections.value.flatMap((section) => section.items))
const total = computed(() => items.value.length)
const checked = computed(() => items.value.filter((item) => item.checked).length)
const receivableItems = computed(() =>
  items.value.filter(
    (item) =>
      item.checked && !item.already_have && item.received_at === null && item.product_id !== null,
  ),
)
const toReceive = computed(() => receivableItems.value.length)
const hasReceived = computed(() => items.value.some((item) => item.received_at !== null))
const isExpired = computed(
  () => detail.value !== null && new Date(detail.value.expires_at).getTime() <= Date.now(),
)
const selectedStore = computed<Store | null>(() =>
  detail.value?.store_id == null
    ? null
    : (stores.data.value?.items.find((store) => store.id === detail.value?.store_id) ?? null),
)

async function reconcileList(access: Access): Promise<void> {
  if (!current(access) || !access.target) return
  const version = offlineQueue.reconciliationVersion(access.target)
  try {
    await queryClient.cancelQueries({ queryKey: access.key })
    assertCurrent(access)
    await queryClient.fetchQuery({
      queryKey: access.key,
      queryFn: () => fetchListWithPending(access),
      staleTime: 0,
    })
    assertCurrent(access)
    if (![...changingItems.value].some((key) => key.startsWith(`${access.token}#`)))
      offlineQueue.confirmReconciled(access.target, version)
  } catch {
    /* Nieudany/stary GET nie potwierdza rekonsyliacji. */
  }
}
function retryList(): void {
  const access = capture()
  if (access.target && offlineQueue.needsReconciliation(access.target)) void reconcileList(access)
  else void list.refetch()
}
function snapshotFor(payload: Toggle): ShoppingListDetail | undefined {
  if (!current(payload.access)) return undefined
  const previous = queryClient.getQueryData<ShoppingListDetail>(payload.access.key)
  return (
    previous && {
      ...previous,
      sections: previous.sections.map((section) => ({
        ...section,
        items: section.items.map((item) =>
          item.id === payload.itemId ? { ...item, checked: payload.checked } : item,
        ),
      })),
    }
  )
}
function reportError(error: unknown): void {
  actionInfo.value = null
  actionError.value = error instanceof Error ? error.message : common.unexpectedError
}
async function enqueue(payload: Toggle): Promise<null> {
  assertCurrent(payload.access)
  if (!payload.access.target) throw new OfflineStorageError()
  await offlineQueue.enqueue(
    payload.access.target,
    payload.itemId,
    payload.checked,
    snapshotFor(payload),
  )
  assertCurrent(payload.access)
  return null
}
async function toggleItem(payload: Toggle): Promise<ShoppingListItem | null> {
  assertCurrent(payload.access)
  if (offlineQueue.isOffline || !auth.isAuthenticated) return enqueue(payload)
  try {
    const item = await updateShoppingListItem(payload.access.id, payload.itemId, {
      checked: payload.checked,
    })
    assertCurrent(payload.access)
    if (payload.access.target) await offlineQueue.forget(payload.access.target, payload.itemId)
    assertCurrent(payload.access)
    return item
  } catch (error) {
    assertCurrent(payload.access)
    if (error instanceof ApiError && error.status === 0) {
      offlineQueue.markOffline()
      return enqueue(payload)
    }
    if (error instanceof ApiError && error.status === 401) auth.clear()
    if (error instanceof ApiError && [404, 410].includes(error.status) && payload.access.target)
      await offlineQueue.markGone(payload.access.target)
    throw error
  }
}
const toggle = useMutation({
  mutationFn: toggleItem,
  onMutate: async (payload) => {
    await queryClient.cancelQueries({ queryKey: payload.access.key })
    assertCurrent(payload.access)
    const previous = queryClient.getQueryData<ShoppingListDetail>(payload.access.key)
    const previousItem = previous?.sections
      .flatMap((section) => section.items)
      .find((item) => item.id === payload.itemId)
    const snapshot = snapshotFor(payload)
    if (snapshot) queryClient.setQueryData(payload.access.key, snapshot)
    return { previousItem }
  },
  onError: (error, payload, context) => {
    if (!current(payload.access)) return
    if (context?.previousItem) {
      const previousItem = context.previousItem
      queryClient.setQueryData<ShoppingListDetail>(
        payload.access.key,
        (value) =>
          value && {
            ...value,
            sections: value.sections.map((section) => ({
              ...section,
              items: section.items.map((item) =>
                item.id === previousItem.id ? previousItem : item,
              ),
            })),
          },
      )
    }
    reportError(error)
  },
  onSuccess: (item, payload) => {
    if (!current(payload.access)) return
    actionError.value = null
    if (item === null) {
      const snapshot = snapshotFor(payload)
      if (snapshot) queryClient.setQueryData(payload.access.key, snapshot)
      return
    }
    void queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
    queryClient.setQueryData<ShoppingListDetail>(
      payload.access.key,
      (value) =>
        value && {
          ...value,
          sections: value.sections.map((section) => ({
            ...section,
            items: section.items.map((existing) => (existing.id === item.id ? item : existing)),
          })),
        },
    )
  },
  onSettled: (_item, _error, payload) => {
    const next = new Set(changingItems.value)
    next.delete(`${payload.access.token}#${payload.itemId}`)
    changingItems.value = next
    if (
      current(payload.access) &&
      offlineQueue.needsReconciliation(payload.access.target) &&
      !offlineQueue.isOffline
    )
      void reconcileList(payload.access)
  },
})
function requestToggle(payload: { itemId: number; checked: boolean }): void {
  const access = capture()
  const key = `${access.token}#${payload.itemId}`
  if (
    !current(access) ||
    changingItems.value.has(key) ||
    accept.isPending.value ||
    changeStore.isPending.value
  )
    return
  changingItems.value = new Set([...changingItems.value, key])
  toggle.mutate({ ...payload, access })
}
const changeStore = useMutation({
  mutationFn: async ({ store, access }: { store: Store | null; access: Access }) => {
    assertOnline(access)
    const updated = await updateShoppingList(
      access.id,
      store === null ? { clear_store: true } : { store_id: store.id, clear_store: false },
    )
    assertCurrent(access)
    return updated
  },
  onSuccess: (updated, { access }) => {
    if (!current(access)) return
    actionError.value = null
    queryClient.setQueryData(access.key, updated)
    void queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
  },
  onError: (error, { access }) => {
    if (current(access)) reportError(error)
  },
})
function requestStore(store: Store | null): void {
  changeStore.mutate({ store, access: capture() })
}
const accept = useMutation({
  mutationFn: async (access: Access) => {
    assertOnline(access)
    const result = await acceptListToPantry(access.id)
    assertCurrent(access)
    return result
  },
  onSuccess: (result, access) => {
    if (!current(access)) return
    actionError.value = null
    acceptOpen.value = false
    actionInfo.value = texts.acceptDone(
      result.created,
      result.increased,
      result.skipped,
      result.already_received,
    )
    void queryClient.invalidateQueries({ queryKey: access.key })
    void queryClient.invalidateQueries({ queryKey: queryKeys.pantry.all })
    void queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
  },
  onError: (error, access) => {
    if (current(access)) {
      reportError(error)
      void queryClient.invalidateQueries({ queryKey: access.key })
    }
  },
})
function confirmAccept(): void {
  if (
    !auth.isAuthenticated ||
    offlineQueue.isOffline ||
    awaitingChecks.value ||
    checkError.value !== null ||
    toReceive.value === 0 ||
    accept.isPending.value
  )
    return
  accept.mutate(capture())
}
function receiveAmount(item: ShoppingListItem): string {
  return item.packages_count !== null && item.package_size !== null
    ? texts.packagesLine(item.packages_count, formatAmount(item.package_size, item.amount_unit))
    : formatAmount(item.needed_amount, item.amount_unit)
}
function printList(): void {
  window.print()
}
const remove = useMutation({
  mutationFn: async (access: Access) => {
    assertOnline(access)
    await deleteShoppingList(access.id)
    assertCurrent(access)
  },
  onSuccess: async (_result, access) => {
    if (!current(access)) return
    await queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
    if (current(access)) await router.push({ name: 'zakupy' })
  },
  onError: (error, access) => {
    if (current(access)) reportError(error)
  },
})
function requestRemove(): void {
  remove.mutate(capture())
}
</script>
<template>
  <section
    class="shopping-list mx-auto grid w-full max-w-3xl gap-6"
    data-testid="lista-zakupowa-page"
  >
    <p
      v-if="hasValidId && list.isPending.value && !offlineQueue.isGone(target)"
      class="text-muted-foreground text-sm"
      role="status"
    >
      {{ texts.loading }}
    </p>
    <p
      v-else-if="
        !hasValidId ||
        (list.error.value instanceof ApiError && [404, 410].includes(list.error.value.status)) ||
        offlineQueue.isGone(target)
      "
      class="text-muted-foreground text-sm"
      data-testid="lista-zakupowa-brak"
      role="alert"
    >
      {{ texts.notFound }}
    </p>
    <section
      v-else-if="detail === null"
      class="grid gap-3"
      role="alert"
      data-testid="lista-load-error"
    >
      <p>Nie udało się wczytać listy zakupów.</p>
      <Button class="justify-self-start" @click="retryList">Spróbuj ponownie</Button>
    </section>
    <template v-else>
      <PageHeader :title="detail.name" :decoration="false" title-testid="lista-nazwa">
        <template #actions>
          <Button
            variant="outline"
            class="print:hidden"
            data-testid="lista-share-open"
            :aria-expanded="shareOpen"
            aria-controls="lista-share"
            @click="shareOpen = !shareOpen"
            >{{ texts.share }}</Button
          >
          <Button
            variant="ghost"
            class="print:hidden"
            data-testid="lista-print"
            @click="printList"
            >{{ texts.print }}</Button
          >
        </template>
        <p class="text-muted-foreground text-sm">
          <span v-if="detail.round_name">{{ detail.round_name }} · </span>{{ texts.expiresAt }}
          {{ formatDate(detail.expires_at.slice(0, 10)) }}
        </p>
        <p class="mt-2 font-medium print:hidden" data-testid="lista-progress" aria-live="polite">
          {{ texts.progress(checked, total) }}
        </p>
        <p
          v-if="isExpired"
          class="text-destructive text-sm print:hidden"
          data-testid="lista-wygasla"
        >
          {{ texts.expired }}
        </p>
      </PageHeader>
      <OfflineBanner
        :offline="offlineQueue.isOffline"
        :pending="pendingChanges"
        :syncing="pendingChanges > 0 && offlineQueue.flushing"
        :retrying="waitingToRetry"
        :error="checkError"
      />
      <p
        v-if="storageUnavailable"
        class="text-warning text-sm print:hidden"
        role="alert"
        data-testid="lista-storage-error"
      >
        Zapis offline jest niedostępny na tym urządzeniu. Odhaczenia wymagają działającego
        połączenia.
      </p>
      <p
        v-if="list.isError.value"
        class="text-warning text-sm print:hidden"
        role="alert"
        data-testid="lista-refresh-error"
      >
        Nie udało się odświeżyć listy. Wyświetlane są ostatnio zapisane dane.
        <button class="min-h-11 underline" @click="retryList">Spróbuj ponownie</button>
      </p>
      <div
        v-if="offlineQueue.needsReconciliation(target) && !list.isError.value"
        class="grid justify-items-start gap-2 print:hidden"
        data-testid="lista-reconcile-needed"
      >
        <p class="text-muted-foreground text-sm">
          Przed przyjęciem do spiżarni trzeba potwierdzić aktualny stan odhaczeń.
        </p>
        <Button
          variant="outline"
          :disabled="
            offlineQueue.isOffline || list.isFetching.value || checking || pendingChanges > 0
          "
          data-testid="lista-reconcile-retry"
          @click="retryList"
        >
          {{ list.isFetching.value ? common.loading : 'Odśwież odhaczenia' }}
        </Button>
      </div>
      <div id="lista-share">
        <ShareListDialog
          :open="shareOpen"
          :list-id="listId"
          :share="detail.share"
          :offline="offlineQueue.isOffline || !auth.isAuthenticated"
          @close="shareOpen = false"
        />
      </div>
      <details class="border-border rounded-lg border p-3 print:hidden" data-testid="lista-sklep">
        <summary class="min-h-11 cursor-pointer py-3 text-sm font-medium">
          Sklep: {{ detail.store_name ?? 'Bez sklepu' }}
        </summary>
        <div class="grid gap-2 pt-3">
          <StorePicker
            :model-value="selectedStore"
            :label="texts.store"
            :disabled="
              changeStore.isPending.value ||
              !auth.isAuthenticated ||
              offlineQueue.isOffline ||
              awaitingChecks ||
              accept.isPending.value
            "
            @update:model-value="requestStore"
          />
          <p class="text-muted-foreground text-xs">
            {{
              offlineQueue.isOffline
                ? offlineTexts.storeNeedsNetwork
                : awaitingChecks
                  ? 'Najpierw zaczekaj na zapis odhaczeń.'
                  : texts.storeHint
            }}
          </p>
        </div>
      </details>
      <p
        v-if="actionError"
        class="text-destructive text-sm print:hidden"
        role="alert"
        data-testid="lista-error"
      >
        {{ actionError }}
      </p>
      <p
        v-if="actionInfo"
        class="text-secondary text-sm print:hidden"
        role="status"
        data-testid="lista-info"
      >
        {{ actionInfo }}
      </p>
      <p v-if="total === 0" class="text-muted-foreground text-sm" data-testid="lista-pusta">
        {{ texts.empty }}
      </p>
      <ShoppingChecklistSection
        v-for="section in sections"
        :key="section.category_id"
        :name="section.category_name"
        :items="section.items"
        :data-testid="`lista-sekcja-${section.category_id}`"
      >
        <template #item="{ item, collapsed }">
          <ShoppingItemRow
            :class="{ 'shopping-item-collapsed': collapsed }"
            :item-id="item.id"
            :label="item.label"
            :amount="item.needed_amount"
            :unit="item.amount_unit"
            :checked="item.checked"
            :already-have="item.already_have"
            :leftover="item.leftover_amount"
            :packages-count="item.packages_count"
            :package-size="item.package_size"
            :received="item.received_at !== null"
            :disabled="
              changingItems.has(`${viewToken}#${item.id}`) ||
              accept.isPending.value ||
              changeStore.isPending.value
            "
            @toggle="requestToggle"
          />
        </template>
      </ShoppingChecklistSection>
      <footer class="border-border grid gap-3 border-t pt-5 print:hidden" data-testid="lista-akcje">
        <Button
          class="min-h-12 w-full whitespace-normal sm:w-auto sm:justify-self-start"
          :disabled="
            toReceive === 0 ||
            !auth.isAuthenticated ||
            offlineQueue.isOffline ||
            awaitingChecks ||
            !!checkError ||
            accept.isPending.value
          "
          aria-describedby="lista-accept-hint"
          data-testid="lista-accept-open"
          @click="acceptOpen = true"
          >{{ texts.acceptToPantry }}</Button
        >
        <p
          id="lista-accept-hint"
          class="text-muted-foreground text-sm"
          data-testid="lista-accept-hint"
        >
          <template v-if="offlineQueue.isOffline">{{ offlineTexts.acceptNeedsNetwork }}</template>
          <template v-else-if="checkError">{{ checkError }}</template>
          <template v-else-if="awaitingChecks">Najpierw zaczekaj na zapis odhaczeń.</template>
          <template v-else-if="toReceive > 0">{{ texts.acceptCount(toReceive) }}</template>
          <template v-else-if="hasReceived">{{ texts.acceptAllReceived }}</template>
          <template v-else>{{ texts.acceptNothing }}</template>
        </p>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <Button as-child variant="ghost"
            ><RouterLink :to="{ name: 'zakupy' }" data-testid="lista-back">{{
              texts.backToShopping
            }}</RouterLink></Button
          >
          <Button
            variant="ghost"
            class="text-destructive"
            :disabled="offlineQueue.isOffline || !auth.isAuthenticated || awaitingChecks"
            data-testid="lista-delete-open"
            @click="deleteOpen = true"
            >{{ texts.deleteList }}</Button
          >
        </div>
      </footer>
      <section
        v-if="acceptOpen"
        class="border-border bg-card grid gap-3 rounded-xl border p-4 print:hidden"
        role="group"
        :aria-label="texts.acceptTitle"
        data-testid="accept-dialog"
      >
        <h3 class="font-semibold">{{ texts.acceptTitle }}</h3>
        <p class="text-muted-foreground text-sm">{{ texts.acceptDescription }}</p>
        <p class="text-sm font-medium" data-testid="accept-count">
          {{ texts.acceptCount(toReceive) }}
        </p>
        <ul class="grid gap-2 text-sm" data-testid="accept-items">
          <li
            v-for="item in receivableItems"
            :key="item.id"
            class="flex items-start justify-between gap-4"
          >
            <span class="min-w-0 wrap-anywhere">{{ item.label }}</span
            ><span class="shrink-0 font-medium">{{ receiveAmount(item) }}</span>
          </li>
        </ul>
        <p class="text-muted-foreground text-sm">
          Do spiżarni trafią całe kupione opakowania, razem z resztką. Produkty „mam już w domu” i
          wcześniej przyjęte są pomijane.
        </p>
        <p v-if="offlineQueue.isOffline" class="text-warning text-sm">
          {{ offlineTexts.acceptNeedsNetwork }}
        </p>
        <p v-else-if="checkError" class="text-warning text-sm">{{ checkError }}</p>
        <p v-else-if="awaitingChecks" class="text-warning text-sm">
          Najpierw zaczekaj na zapis odhaczeń.
        </p>
        <footer class="flex flex-wrap gap-2">
          <Button
            :disabled="
              accept.isPending.value ||
              offlineQueue.isOffline ||
              awaitingChecks ||
              !!checkError ||
              toReceive === 0
            "
            data-testid="accept-confirm"
            @click="confirmAccept"
            >{{ accept.isPending.value ? common.loading : texts.acceptConfirm }}</Button
          >
          <Button
            variant="ghost"
            :disabled="accept.isPending.value"
            data-testid="accept-cancel"
            @click="acceptOpen = false"
            >{{ common.cancel }}</Button
          >
        </footer>
      </section>
      <section
        v-if="deleteOpen"
        class="border-border bg-card grid gap-3 rounded-xl border p-4 print:hidden"
        role="group"
        :aria-label="texts.deleteTitle"
        data-testid="delete-dialog"
      >
        <h3 class="font-semibold">{{ texts.deleteTitle }}</h3>
        <p class="text-muted-foreground text-sm">{{ texts.deleteDescription }}</p>
        <footer class="flex flex-wrap gap-2">
          <Button
            class="bg-destructive"
            :disabled="remove.isPending.value || offlineQueue.isOffline"
            data-testid="delete-confirm"
            @click="requestRemove"
            >{{ remove.isPending.value ? common.loading : texts.deleteConfirm }}</Button
          >
          <Button
            variant="ghost"
            :disabled="remove.isPending.value"
            data-testid="delete-cancel"
            @click="deleteOpen = false"
            >{{ common.cancel }}</Button
          >
        </footer>
      </section>
    </template>
  </section>
</template>
