<script setup lang="ts">
/**
 * Lista zakupowa (`/zakupy/listy/:id`, widok 5 wizualizacji; zastępuje zaślepkę z B10).
 *
 * To WIDOK KRYTYCZNY MOBILNY (06_UIUX §5): jedna ręka, sklep, pośpiech. Stąd
 * cztery decyzje, które trzeba czytać razem:
 *
 * 1. **Sekcje składa SERWER** (`sections` w odpowiedzi), a nie przeglądarka.
 *    Kolejność zależy od profilu sklepu i globalnych pozycji kategorii, więc
 *    liczona po stronie klienta rozjechałaby się z wydrukiem i z publicznym
 *    linkiem. Frontend tylko renderuje to, co dostał.
 * 2. **Odhaczenie jest OPTIMISTIC** (karta B11 §Frontend): checkbox reaguje
 *    natychmiast, a błąd wycofuje zmianę i mówi o tym wprost. W sklepie
 *    czekanie na odpowiedź serwera przy każdej pozycji jest nie do przyjęcia.
 * 3. **Wybór sklepu stoi na `StorePicker`** (reużycie obowiązkowe, B09) —
 *    razem z create-in-context, bo „jadę dziś do nowego sklepu" zdarza się
 *    właśnie tutaj.
 * 4. **Druk to wariant TEJ strony** (`@media print`, 06_UIUX §6), nie osobny
 *    ekran: nawigacja, panel akcji i kolory znikają, zostają nagłówki
 *    kategorii i kwadraty `☐` z `ShoppingItemRow`.
 *
 * 5. **Offline to nie tryb awaryjny, tylko normalna praca** (B12, ADR-009):
 *    treść listy leży w IndexedDB, a odhaczenia bez zasięgu idą do kolejki
 *    z własnym `checked_at`. Snapshot HYDRATUJEMY DO CACHE'U TanStack Query,
 *    a nie do osobnego ref-a — dzięki temu optimistic update, rollback i render
 *    działają offline dokładnie tym samym kodem, co online.
 *
 * Stan serwera mieszka w TanStack Query (ADR-007) — lista nie jest kopiowana
 * do żadnego ref-a; w komponencie żyje wyłącznie stan UI (otwarte panele)
 * i kolejka offline (Pinia, bo to intencje użytkownika, nie stan serwera).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
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
import ShareListDialog from '@/components/domain/ShareListDialog.vue'
import ShoppingItemRow from '@/components/domain/ShoppingItemRow.vue'
import StorePicker from '@/components/domain/StorePicker.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/lib/dates'
import { saveSnapshot, targetKey, type QueueTarget } from '@/lib/offline/db'
import { hydrateFromSnapshot } from '@/lib/offline/hydrate'
import { common, offline as offlineTexts, shoppingList as texts } from '@/lib/texts'
import { useOfflineQueueStore } from '@/stores/offlineQueue'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const listId = computed(() => Number(route.params.id))
/**
 * Id z URL-a bywa śmieciem (ktoś wpisze `/zakupy/listy/abc` z ręki).
 * Bez tego sprawdzenia zapytanie zostaje wyłączone (`enabled: false`), a to
 * w TanStack Query 5 znaczy status `pending` — strona wisiałaby na „Wczytywanie…"
 * bez końca zamiast powiedzieć, że listy nie ma.
 */
const hasValidId = computed(() => Number.isInteger(listId.value) && listId.value > 0)
const listKey = computed(() => queryKeys.shopping.list(listId.value))

const shareOpen = ref(false)
const acceptOpen = ref(false)
const deleteOpen = ref(false)
const actionError = ref<string | null>(null)
const actionInfo = ref<string | null>(null)

const list = useQuery({
  queryKey: listKey,
  queryFn: () => fetchShoppingList(listId.value),
  enabled: hasValidId,
})

const offlineQueue = useOfflineQueueStore()
const target = computed<QueueTarget>(() => ({ kind: 'list', listId: listId.value }))
const pendingChanges = computed(() => offlineQueue.pendingFor(target.value))

/**
 * Snapshot z IndexedDB → cache TanStack Query (szczegóły: `offline/hydrate.ts`)
 * plus nasłuch synchronizacji tej listy.
 *
 * Obserwujemy KLUCZ, a nie tylko montowanie: przejście z listy na listę
 * (`/zakupy/listy/5` → `/zakupy/listy/6`) reużywa ten sam komponent, więc
 * subskrypcja założona w `onMounted` zostałaby przy poprzedniej liście i po
 * flushu unieważniałaby nie to zapytanie, co trzeba.
 */
watch(
  () => (hasValidId.value ? targetKey(target.value) : null),
  (snapshotKey, _previous, onCleanup) => {
    if (snapshotKey === null) {
      return
    }
    void hydrateFromSnapshot<ShoppingListDetail>(queryClient, listKey.value, snapshotKey)
    onCleanup(
      offlineQueue.subscribeToSync(target.value, () => {
        void queryClient.invalidateQueries({ queryKey: listKey.value })
      }),
    )
  },
  { immediate: true },
)

/**
 * Każdy KOMPLETNY stan listy w cache'u ląduje w IndexedDB.
 *
 * Zapisujemy też po optimistic update, nie tylko po odpowiedzi serwera:
 * przeładowanie strony w sklepie bez zasięgu ma pokazać pozycje odhaczone
 * przed chwilą, a nie stan sprzed wejścia do sklepu. Rollback po błędzie
 * przechodzi tą samą drogą, więc snapshot nigdy nie utrwala stanu, którego
 * użytkownik już nie widzi na ekranie.
 */
watch(
  () => list.data.value,
  (value) => {
    if (value) {
      void saveSnapshot(targetKey(target.value), value)
    }
  },
  { immediate: true },
)

// Sklepy pobieramy po to, żeby `StorePicker` dostał WYBRANY sklep jako obiekt.
// Słownik jest krótki i cache'owany pod tym samym kluczem co picker, więc to
// nie jest dodatkowe zapytanie na każde wejście (B09).
const storeFilters = computed(() => ({ include_archived: false }))
const stores = useQuery({
  queryKey: computed(() => queryKeys.stores.list(storeFilters.value)),
  queryFn: () => fetchStores(storeFilters.value),
})

const detail = computed(() => list.data.value ?? null)
const sections = computed(() => detail.value?.sections ?? [])
const items = computed(() => sections.value.flatMap((section) => section.items))
const total = computed(() => items.value.length)
const checked = computed(() => items.value.filter((item) => item.checked).length)
/**
 * Ile pozycji WEJDZIE po kliknięciu „przyjmij" (D19).
 *
 * Te same trzy warunki co w serwisie: odhaczona, nie „mam już w domu", jeszcze
 * nieprzyjęta. Liczymy je tutaj, żeby przycisk mówił prawdę PRZED kliknięciem —
 * inaczej użytkownik dowiadywałby się o „wszystko już w spiżarni" dopiero z 409.
 */
const toReceive = computed(
  () =>
    items.value.filter((item) => item.checked && !item.already_have && item.received_at === null)
      .length,
)
const hasReceived = computed(() => items.value.some((item) => item.received_at !== null))
const isExpired = computed(
  () => detail.value !== null && new Date(detail.value.expires_at).getTime() <= Date.now(),
)
const selectedStore = computed<Store | null>(() => {
  const storeId = detail.value?.store_id
  return storeId == null ? null : (stores.data.value?.items.find((s) => s.id === storeId) ?? null)
})

function reportError(error: unknown): void {
  actionInfo.value = null
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

/**
 * Wyślij odhaczenie albo odłóż je do kolejki (ADR-009).
 *
 * Zwraca `null`, gdy zmiana poszła do kolejki — wtedy nie ma czym podmienić
 * pozycji w cache'u i zostaje stan optimistic.
 *
 * Kolejkujemy w DWÓCH sytuacjach, nie w jednej: gdy przeglądarka wie, że jest
 * offline, ORAZ gdy żądanie padło na sieci mimo `navigator.onLine === true`
 * (Wi-Fi w sklepie, które łapie sygnał, ale nie przepuszcza ruchu — to jest
 * właśnie ten przypadek, dla którego cały ten mechanizm powstał).
 *
 * `checked_at` wysyła TYLKO kolejka. Tutaj, online, czas serwera JEST czasem
 * decyzji, więc doklejanie znacznika klienta dokładałoby zależność od jego
 * zegara bez żadnego zysku.
 */
async function toggleItem(payload: {
  itemId: number
  checked: boolean
}): Promise<ShoppingListItem | null> {
  if (offlineQueue.isOffline) {
    await offlineQueue.enqueue(target.value, payload.itemId, payload.checked)
    return null
  }
  try {
    const item = await updateShoppingListItem(listId.value, payload.itemId, {
      checked: payload.checked,
    })
    // Zapis online unieważnia starszy wpis tej pozycji: bez tego poszedłby po
    // odzyskaniu sieci i tak (przegrywając LWW), zjadając limit 60/min bez celu.
    await offlineQueue.forget(target.value, payload.itemId)
    return item
  } catch (error) {
    if (error instanceof ApiError && error.status === 0) {
      offlineQueue.markOffline()
      await offlineQueue.enqueue(target.value, payload.itemId, payload.checked)
      return null
    }
    throw error
  }
}

/**
 * Optimistic toggle pozycji (karta B11 §Frontend).
 *
 * Podmieniamy pozycję w cache PRZED żądaniem, a przy błędzie wracamy do
 * zapamiętanego stanu i pokazujemy komunikat. Świadomie NIE invalidujemy
 * całej listy po sukcesie: odpowiedź PATCH-a zawiera już aktualną pozycję,
 * a refetch całej listy w sklepie oznaczałby przeskok scrolla przy każdym
 * odhaczeniu.
 */
const toggle = useMutation({
  mutationFn: (payload: { itemId: number; checked: boolean }) => toggleItem(payload),
  onMutate: async (payload) => {
    await queryClient.cancelQueries({ queryKey: listKey.value })
    const previous = queryClient.getQueryData<ShoppingListDetail>(listKey.value)
    if (previous) {
      queryClient.setQueryData<ShoppingListDetail>(listKey.value, {
        ...previous,
        sections: previous.sections.map((section) => ({
          ...section,
          items: section.items.map((item) =>
            item.id === payload.itemId ? { ...item, checked: payload.checked } : item,
          ),
        })),
      })
    }
    return { previous }
  },
  onError: (error, _payload, context) => {
    if (context?.previous) {
      queryClient.setQueryData(listKey.value, context.previous)
    }
    reportError(error)
  },
  onSuccess: (item) => {
    actionError.value = null
    // `null` = odhaczenie poszło do kolejki offline. Stan optimistic jest wtedy
    // JEDYNYM, jaki mamy — i ma zostać, bo serwer go dopiero zobaczy.
    if (item === null) {
      return
    }
    const current = queryClient.getQueryData<ShoppingListDetail>(listKey.value)
    if (!current) {
      return
    }
    queryClient.setQueryData<ShoppingListDetail>(listKey.value, {
      ...current,
      sections: current.sections.map((section) => ({
        ...section,
        items: section.items.map((existing) => (existing.id === item.id ? item : existing)),
      })),
    })
  },
})

/** Zmiana sklepu = nowy profil sortowania, więc odpowiedź podmienia CAŁĄ listę. */
const changeStore = useMutation({
  // `clear_store` podajemy ZAWSZE: w OpenAPI pole ma domyślną wartość, ale
  // generator typów zostawia je wymaganym, a i tak czytelniej jest wprost
  // powiedzieć „odpinam sklep" niż „nie ustawiam sklepu".
  mutationFn: (store: Store | null) =>
    updateShoppingList(
      listId.value,
      store === null ? { clear_store: true } : { store_id: store.id, clear_store: false },
    ),
  onSuccess: (updated) => {
    actionError.value = null
    queryClient.setQueryData(listKey.value, updated)
    void queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
  },
  onError: reportError,
})

const accept = useMutation({
  mutationFn: () => acceptListToPantry(listId.value),
  onSuccess: (result) => {
    actionError.value = null
    acceptOpen.value = false
    actionInfo.value = texts.acceptDone(
      result.created,
      result.increased,
      result.skipped,
      result.already_received,
    )
    // Pozycje dostały `received_at` — lista musi to pokazać, więc pobieramy ją
    // na nowo (znacznik nie da się policzyć na kliencie).
    void queryClient.invalidateQueries({ queryKey: listKey.value })
    void queryClient.invalidateQueries({ queryKey: queryKeys.pantry.all })
  },
  onError: reportError,
})

/**
 * Druk: `window.print()` wołane z metody, a nie z szablonu.
 *
 * Szablon Vue nie widzi `window` (dozwolone globalne to `Math`, `Date`…), więc
 * wywołanie `window.print()` wprost w `@click` byłoby cichym błędem w czasie
 * działania — przycisk „Drukuj" nie robiłby nic.
 */
function printList(): void {
  window.print()
}

const remove = useMutation({
  mutationFn: () => deleteShoppingList(listId.value),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
    await router.push({ name: 'zakupy' })
  },
  onError: reportError,
})
</script>

<template>
  <section class="grid gap-4" data-testid="lista-zakupowa-page">
    <p v-if="hasValidId && list.isPending.value" class="text-muted-foreground text-sm">
      {{ texts.loading }}
    </p>

    <p
      v-else-if="!hasValidId || detail === null"
      class="text-muted-foreground text-sm"
      data-testid="lista-zakupowa-brak"
    >
      {{ texts.notFound }}
    </p>

    <template v-else>
      <header class="grid gap-2 print:gap-1">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h1 class="text-2xl font-semibold" data-testid="lista-nazwa">{{ detail.name }}</h1>
          <p class="text-muted-foreground text-sm print:hidden" data-testid="lista-progress">
            {{ texts.progress(checked, total) }}
          </p>
        </div>
        <p class="text-muted-foreground text-sm">
          <span v-if="detail.round_name">{{ detail.round_name }} · </span>
          {{ texts.expiresAt }} {{ formatDate(detail.expires_at.slice(0, 10)) }}
        </p>
        <p
          v-if="isExpired"
          class="text-destructive text-sm print:hidden"
          data-testid="lista-wygasla"
        >
          {{ texts.expired }}
        </p>
      </header>

      <OfflineBanner
        :offline="offlineQueue.isOffline"
        :pending="pendingChanges"
        :syncing="offlineQueue.flushing"
      />

      <!-- Wybór sklepu: profil decyduje o kolejności sekcji (AC 1).
           Offline WYŁĄCZONY: kolejność sekcji składa serwer z profilu sklepu
           (ustalenie R3), a przeglądarka nie zna `store_category_order` — nie
           umiałaby pokazać skutku tej zmiany, więc nie wchodzi ona do kolejki. -->
      <Card class="rounded-xl print:hidden" data-testid="lista-sklep">
        <CardContent class="grid gap-2 pt-4">
          <StorePicker
            :model-value="selectedStore"
            :label="texts.store"
            :disabled="changeStore.isPending.value || offlineQueue.isOffline"
            @update:model-value="changeStore.mutate($event)"
          />
          <p class="text-muted-foreground text-xs">
            {{ offlineQueue.isOffline ? offlineTexts.storeNeedsNetwork : texts.storeHint }}
          </p>
        </CardContent>
      </Card>

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

      <!-- Sekcje w kolejności od serwera; nagłówki sticky na telefonie (06_UIUX §5). -->
      <section
        v-for="section in sections"
        :key="section.category_id"
        class="grid gap-2"
        :data-testid="`lista-sekcja-${section.category_id}`"
      >
        <h2
          class="bg-background sticky top-0 z-10 py-1 text-sm font-semibold tracking-wide uppercase print:static print:normal-case"
        >
          {{ section.category_name }}
        </h2>
        <ul class="grid gap-2 print:gap-0">
          <ShoppingItemRow
            v-for="item in section.items"
            :key="item.id"
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
            @toggle="toggle.mutate($event)"
          />
        </ul>
      </section>

      <!-- Panel akcji: poza wydrukiem (06_UIUX §6). -->
      <Card class="rounded-xl print:hidden" data-testid="lista-akcje">
        <CardHeader>
          <CardTitle class="text-base">{{ texts.title }}</CardTitle>
        </CardHeader>
        <CardContent class="flex flex-wrap gap-2">
          <Button
            type="button"
            class="min-h-11"
            data-testid="lista-share-open"
            @click="shareOpen = !shareOpen"
          >
            {{ texts.share }}
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11"
            data-testid="lista-print"
            @click="printList()"
          >
            {{ texts.print }}
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11"
            :disabled="toReceive === 0 || offlineQueue.isOffline"
            data-testid="lista-accept-open"
            @click="acceptOpen = true"
          >
            {{ texts.acceptToPantry }}
          </Button>
          <Button
            type="button"
            variant="ghost"
            class="text-destructive min-h-11"
            data-testid="lista-delete-open"
            @click="deleteOpen = true"
          >
            {{ texts.deleteList }}
          </Button>
          <Button as-child variant="ghost" class="min-h-11">
            <RouterLink :to="{ name: 'zakupy' }" data-testid="lista-back">
              {{ texts.backToShopping }}
            </RouterLink>
          </Button>
        </CardContent>
      </Card>

      <!-- Podpowiedź mówi, DLACZEGO przycisk jest nieaktywny — trzy różne
           powody, trzy różne komunikaty (06_UIUX §3). -->
      <p class="text-muted-foreground text-xs print:hidden" data-testid="lista-accept-hint">
        <template v-if="offlineQueue.isOffline">{{ offlineTexts.acceptNeedsNetwork }}</template>
        <template v-else-if="toReceive > 0">{{ texts.acceptCount(toReceive) }}</template>
        <template v-else-if="hasReceived">{{ texts.acceptAllReceived }}</template>
        <template v-else>{{ texts.acceptNothing }}</template>
      </p>

      <ShareListDialog
        :open="shareOpen"
        :list-id="listId"
        :share="detail.share"
        @close="shareOpen = false"
      />

      <!-- Przyjęcie zakupów: JAWNE potwierdzenie, nigdy w tle (02_DOMAIN §8). -->
      <section
        v-if="acceptOpen"
        class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm print:hidden"
        role="group"
        :aria-label="texts.acceptTitle"
        data-testid="accept-dialog"
      >
        <h3 class="text-sm font-medium">{{ texts.acceptTitle }}</h3>
        <p class="text-muted-foreground text-xs">{{ texts.acceptDescription }}</p>
        <p class="text-xs font-medium" data-testid="accept-count">
          {{ texts.acceptCount(toReceive) }}
        </p>
        <footer class="flex flex-wrap gap-2">
          <Button
            type="button"
            class="min-h-11"
            :disabled="accept.isPending.value"
            data-testid="accept-confirm"
            @click="accept.mutate()"
          >
            {{ accept.isPending.value ? common.loading : texts.acceptConfirm }}
          </Button>
          <Button
            type="button"
            variant="ghost"
            class="min-h-11"
            data-testid="accept-cancel"
            @click="acceptOpen = false"
          >
            {{ common.cancel }}
          </Button>
        </footer>
      </section>

      <!-- Destrukcja z konsekwencjami wypisanymi wprost (06_UIUX §3.3). -->
      <section
        v-if="deleteOpen"
        class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm print:hidden"
        role="group"
        :aria-label="texts.deleteTitle"
        data-testid="delete-dialog"
      >
        <h3 class="text-sm font-medium">{{ texts.deleteTitle }}</h3>
        <p class="text-muted-foreground text-xs">{{ texts.deleteDescription }}</p>
        <footer class="flex flex-wrap gap-2">
          <Button
            type="button"
            class="bg-destructive min-h-11"
            :disabled="remove.isPending.value"
            data-testid="delete-confirm"
            @click="remove.mutate()"
          >
            {{ remove.isPending.value ? common.loading : texts.deleteConfirm }}
          </Button>
          <Button
            type="button"
            variant="ghost"
            class="min-h-11"
            data-testid="delete-cancel"
            @click="deleteOpen = false"
          >
            {{ common.cancel }}
          </Button>
        </footer>
      </section>
    </template>
  </section>
</template>
