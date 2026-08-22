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
import { computed, watch } from 'vue'
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
import ShoppingItemRow from '@/components/domain/ShoppingItemRow.vue'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/dates'
import { saveSnapshot, targetKey, type QueueTarget } from '@/lib/offline/db'
import { hydrateFromSnapshot } from '@/lib/offline/hydrate'
import { publicList as texts } from '@/lib/texts'
import { useOfflineQueueStore } from '@/stores/offlineQueue'

const route = useRoute()
const queryClient = useQueryClient()

const token = computed(() => String(route.params.token ?? ''))
const listKey = computed(() => queryKeys.publicList.detail(token.value))

const list = useQuery({
  queryKey: listKey,
  queryFn: () => fetchPublicList(token.value),
  enabled: computed(() => token.value.length > 0),
  // Wygasły link nie naprawi się przez ponowienie — retry tylko dla błędów sieci.
  retry: (attempt, error) => !(error instanceof PublicListUnavailableError) && attempt < 1,
})

const offlineQueue = useOfflineQueueStore()
const target = computed<QueueTarget>(() => ({ kind: 'public', token: token.value }))
const pendingChanges = computed(() => offlineQueue.pendingFor(target.value))

const detail = computed<PublicList | null>(() => list.data.value ?? null)
/**
 * „Wygasła" ma dwa źródła i oba muszą prowadzić do tego samego ekranu:
 * odpowiedź na wejściu ORAZ 410 złapane przez kolejkę przy synchronizacji
 * (token mógł wygasnąć, gdy telefon był bez zasięgu — AC 6).
 */
const isUnavailable = computed(
  () => list.error.value instanceof PublicListUnavailableError || offlineQueue.isGone(target.value),
)
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
    void hydrateFromSnapshot<PublicList>(queryClient, listKey.value, snapshotKey)
    onCleanup(
      offlineQueue.subscribeToSync(target.value, () => {
        void queryClient.invalidateQueries({ queryKey: listKey.value })
      }),
    )
  },
  { immediate: true },
)

watch(
  () => list.data.value,
  (value) => {
    if (value) {
      void saveSnapshot(targetKey(target.value), value)
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
}): Promise<PublicListItem | null> {
  if (offlineQueue.isOffline) {
    await offlineQueue.enqueue(target.value, payload.itemId, payload.checked)
    return null
  }
  try {
    const item = await checkPublicListItem(token.value, payload.itemId, payload.checked)
    await offlineQueue.forget(target.value, payload.itemId)
    return item
  } catch (error) {
    if (error instanceof PublicListRequestError && error.status === 0) {
      offlineQueue.markOffline()
      await offlineQueue.enqueue(target.value, payload.itemId, payload.checked)
      return null
    }
    throw error
  }
}

const toggle = useMutation({
  mutationFn: (payload: { itemId: number; checked: boolean }) => toggleItem(payload),
  onMutate: async (payload) => {
    await queryClient.cancelQueries({ queryKey: listKey.value })
    const previous = queryClient.getQueryData<PublicList>(listKey.value)
    if (previous) {
      queryClient.setQueryData<PublicList>(listKey.value, {
        ...previous,
        items: previous.items.map((item) =>
          item.id === payload.itemId ? { ...item, checked: payload.checked } : item,
        ),
      })
    }
    return { previous }
  },
  onError: (_error, _payload, context) => {
    if (context?.previous) {
      queryClient.setQueryData(listKey.value, context.previous)
    }
  },
  onSuccess: (item) => {
    // `null` = zmiana czeka w kolejce; stan optimistic jest jedynym, jaki mamy.
    if (item === null) {
      return
    }
    const current = queryClient.getQueryData<PublicList>(listKey.value)
    if (!current) {
      return
    }
    queryClient.setQueryData<PublicList>(listKey.value, {
      ...current,
      items: current.items.map((existing) => (existing.id === item.id ? item : existing)),
    })
  },
})
</script>

<template>
  <div class="bg-background text-foreground min-h-dvh" data-testid="public-list-page">
    <div class="mx-auto grid w-full max-w-2xl gap-4 px-4 py-6">
      <header class="grid gap-1">
        <p class="text-muted-foreground text-xs tracking-wide uppercase print:hidden">
          {{ texts.brand }}
        </p>
        <h1 class="text-2xl font-semibold" data-testid="public-list-title">
          {{ detail?.name ?? texts.heading }}
        </h1>
        <p
          v-if="detail"
          class="text-muted-foreground text-sm print:hidden"
          data-testid="public-list-meta"
        >
          {{ texts.expiresAt(formatDate(detail.expires_at.slice(0, 10))) }} ·
          {{ texts.progress(checkedCount, items.length) }}
        </p>
      </header>

      <OfflineBanner
        :offline="offlineQueue.isOffline"
        :pending="pendingChanges"
        :syncing="offlineQueue.flushing"
      />

      <p v-if="list.isPending.value" class="text-muted-foreground text-sm">
        {{ texts.loading }}
      </p>

      <!-- 404 i 410 → dokładnie ten sam, przyjazny ekran (ADR-010). -->
      <section
        v-else-if="isUnavailable"
        class="border-border bg-card grid gap-2 rounded-xl border p-4"
        data-testid="public-list-unavailable"
      >
        <p class="font-medium">{{ texts.unavailable }}</p>
        <p class="text-muted-foreground text-sm">{{ texts.unavailableHint }}</p>
      </section>

      <section
        v-else-if="isOtherError"
        class="border-border bg-card grid gap-2 rounded-xl border p-4"
        data-testid="public-list-error"
      >
        <p class="font-medium">{{ list.error.value?.message }}</p>
        <div>
          <Button
            type="button"
            class="min-h-11"
            data-testid="public-list-retry"
            @click="list.refetch()"
          >
            {{ texts.retry }}
          </Button>
        </div>
      </section>

      <p
        v-else-if="items.length === 0"
        class="text-muted-foreground text-sm"
        data-testid="public-list-empty"
      >
        {{ texts.empty }}
      </p>

      <template v-else>
        <section
          v-for="(section, index) in sections"
          :key="`${section.name}-${index}`"
          class="grid gap-2"
          :data-testid="`public-section-${index}`"
        >
          <h2
            class="bg-background sticky top-0 z-10 py-1 text-sm font-semibold tracking-wide uppercase print:static"
          >
            {{ section.name }}
          </h2>
          <ul class="grid gap-2">
            <ShoppingItemRow
              v-for="item in section.items"
              :key="item.id"
              :item-id="item.id"
              :label="item.label"
              :amount="item.amount"
              :unit="item.unit"
              :checked="item.checked"
              :already-have="item.already_have"
              :leftover="item.leftover_amount"
              :packages-count="item.packages_count"
              :package-size="item.package_size"
              @toggle="toggle.mutate($event)"
            />
          </ul>
        </section>

        <p class="text-muted-foreground text-xs print:hidden">{{ texts.offlineHint }}</p>
      </template>
    </div>
  </div>
</template>
