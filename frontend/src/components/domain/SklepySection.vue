<script setup lang="ts">
/**
 * Sekcja „Sklepy" w Ustawieniach (widok 12, 06_UIUX §4) — BATCH_09.
 *
 * Osobny komponent, a nie kolejne 200 linii w `UstawieniaPage.vue`: strona
 * ustawień trzyma już rodzinę, profile, cele i progi, a sklepy mają własny
 * stan (edytowany wiersz, rozwinięty profil). Wzorzec jak `SklepySection`
 * w Expected files karty B09.
 *
 * Stan serwera żyje w TanStack Query (ADR-007) — komponent trzyma wyłącznie
 * stan UI: szkic formularza i id sklepu z rozwiniętym profilem.
 *
 * Usuwanie sklepu idzie ścieżką ADR-012: dialog z konsekwencjami, a 409
 * pokazuje listę „Używane w: …" razem z podpowiedzią archiwizacji.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'

import { fetchCategories } from '@/api/catalog'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { Store } from '@/api/stores'
import {
  createStore,
  deleteStore,
  fetchCategoryOrder,
  fetchStores,
  setCategoryOrder,
  updateStore,
} from '@/api/stores'
import StoreCategoryOrderEditor from '@/components/domain/StoreCategoryOrderEditor.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { common, stores as texts } from '@/lib/texts'

interface UsedIn {
  type: string
  id: number
  name: string
}

const queryClient = useQueryClient()

const showArchived = ref(false)
const filters = computed(() => ({ include_archived: showArchived.value }))
const storesQuery = useQuery({
  queryKey: computed(() => queryKeys.stores.list(filters.value)),
  queryFn: () => fetchStores(filters.value),
})
const categoriesQuery = useQuery({
  queryKey: queryKeys.categories.all,
  queryFn: fetchCategories,
})

const items = computed<Store[]>(() => storesQuery.data.value?.items ?? [])
const categories = computed(() => categoriesQuery.data.value?.items ?? [])

const actionError = ref<string | null>(null)
const usedIn = ref<UsedIn[]>([])
/** Sklep, którego usunięcie odbiło się 409 — trzymamy ENCJĘ, nie samo id, żeby
 *  skrót „Archiwizuj" nie musiał jej szukać w liście, która mogła się zmienić. */
const conflictStore = ref<Store | null>(null)

/** `id: null` = formularz dodawania; liczba = edycja istniejącego sklepu. */
const draft = reactive({ id: null as number | null, name: '', color: '' })
const formOpen = ref(false)
/** Sklep z rozwiniętym edytorem kolejności (jeden naraz — mniej hałasu). */
const openOrderStoreId = ref<number | null>(null)

/**
 * Komunikat błędu + lista „Używane w:" z 409.
 *
 * Nigdy nie przekazujemy tej funkcji WPROST jako `onError`: TanStack woła
 * handler z `(error, variables, …)`, więc drugi argument byłby zmiennymi
 * mutacji, a nie sklepem, o który chodzi.
 */
function reportError(error: unknown, store: Store | null = null): void {
  usedIn.value = []
  conflictStore.value = null
  if (error instanceof ApiError) {
    actionError.value = error.message
    const details = error.details.used_in
    if (Array.isArray(details) && details.length) {
      usedIn.value = details as UsedIn[]
      conflictStore.value = store
    }
    return
  }
  actionError.value = common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.stores.all })
}

function openCreate(): void {
  draft.id = null
  draft.name = ''
  draft.color = ''
  formOpen.value = true
  actionError.value = null
}

function openEdit(store: Store): void {
  draft.id = store.id
  draft.name = store.name
  draft.color = store.color ?? ''
  formOpen.value = true
  actionError.value = null
}

const nameValid = computed(() => draft.name.trim().length > 0)

const save = useMutation({
  mutationFn: () => {
    const payload = { name: draft.name.trim(), color: draft.color.trim() || null }
    return draft.id === null ? createStore(payload) : updateStore(draft.id, payload)
  },
  onSuccess: async () => {
    actionError.value = null
    formOpen.value = false
    await refresh()
  },
  onError: (error: unknown) => reportError(error),
})

const toggleArchive = useMutation({
  mutationFn: (store: Store) => updateStore(store.id, { is_archived: !store.is_archived }),
  onSuccess: async () => {
    actionError.value = null
    usedIn.value = []
    await refresh()
  },
  onError: (error: unknown) => reportError(error),
})

const remove = useMutation({
  mutationFn: (store: Store) => deleteStore(store.id),
  // Drugi argument to zmienne mutacji, czyli usunięty sklep — dzięki temu
  // zwijamy edytor kolejności TEGO sklepu, zamiast pytać o profil, którego już
  // nie ma (404 i błąd na ekranie po UDANEJ operacji).
  onSuccess: async (_result, store) => {
    actionError.value = null
    usedIn.value = []
    if (openOrderStoreId.value === store.id) {
      openOrderStoreId.value = null
    }
    await refresh()
  },
  onError: (error: unknown, store: Store) => reportError(error, store),
})

function confirmRemove(store: Store): void {
  if (window.confirm(texts.confirmDelete)) {
    remove.mutate(store)
  }
}

// --- profil kolejności kategorii ---------------------------------------------------

const orderQuery = useQuery({
  queryKey: computed(() => queryKeys.stores.categoryOrder(openOrderStoreId.value ?? 0)),
  queryFn: () => fetchCategoryOrder(openOrderStoreId.value as number),
  enabled: computed(() => openOrderStoreId.value !== null),
})

const order = computed(() => orderQuery.data.value?.items ?? [])
const orderSaved = ref(false)

const saveOrder = useMutation({
  mutationFn: (categoryIds: number[]) =>
    setCategoryOrder(openOrderStoreId.value as number, categoryIds),
  onSuccess: async () => {
    actionError.value = null
    orderSaved.value = true
    await queryClient.invalidateQueries({ queryKey: queryKeys.stores.all })
  },
  onError: (error: unknown) => reportError(error),
})

function toggleOrder(store: Store): void {
  orderSaved.value = false
  openOrderStoreId.value = openOrderStoreId.value === store.id ? null : store.id
}
</script>

<template>
  <Card class="rounded-xl" data-testid="stores-section">
    <CardHeader>
      <CardTitle>{{ texts.sectionTitle }}</CardTitle>
      <CardDescription>{{ texts.sectionSubtitle }}</CardDescription>
    </CardHeader>

    <CardContent class="grid gap-3">
      <div v-if="actionError" class="grid gap-2" role="alert" data-testid="stores-error">
        <p class="text-destructive text-sm">{{ actionError }}</p>
        <template v-if="usedIn.length">
          <p class="text-destructive text-sm font-medium">{{ texts.usedInIntro }}</p>
          <ul class="text-destructive text-sm" data-testid="stores-used-in">
            <li v-for="entry in usedIn" :key="`${entry.type}-${entry.id}`">· {{ entry.name }}</li>
          </ul>
          <Button
            v-if="conflictStore !== null"
            type="button"
            variant="outline"
            class="min-h-11 justify-self-start"
            data-testid="store-archive-instead"
            @click="toggleArchive.mutate(conflictStore)"
          >
            {{ texts.archive }}
          </Button>
        </template>
      </div>

      <label class="flex min-h-11 items-center gap-2 text-sm">
        <input v-model="showArchived" type="checkbox" data-testid="stores-show-archived" />
        {{ texts.showArchived }}
      </label>

      <p
        v-if="items.length === 0 && !storesQuery.isPending.value"
        class="text-muted-foreground text-sm"
        data-testid="stores-empty"
      >
        {{ texts.emptyState }}
      </p>

      <ul v-else class="grid gap-2" data-testid="stores-list">
        <li
          v-for="store in items"
          :key="store.id"
          class="border-border grid gap-3 rounded-lg border p-3"
          :data-testid="`store-row-${store.id}`"
        >
          <div class="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
            <div class="min-w-0">
              <p class="truncate font-medium" :data-testid="`store-name-${store.id}`">
                {{ store.name }}
              </p>
              <p class="text-muted-foreground text-sm">
                {{ store.color ? store.color : texts.colorNone }}
                <template v-if="store.is_archived">
                  <span aria-hidden="true"> · </span>{{ texts.archived }}
                </template>
              </p>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button
                variant="outline"
                class="min-h-11"
                :data-testid="`store-order-${store.id}`"
                @click="toggleOrder(store)"
              >
                {{ openOrderStoreId === store.id ? texts.orderClose : texts.orderEdit }}
              </Button>
              <Button
                variant="outline"
                class="min-h-11"
                :data-testid="`store-edit-${store.id}`"
                @click="openEdit(store)"
              >
                {{ common.edit }}
              </Button>
              <Button
                variant="outline"
                class="min-h-11"
                :disabled="toggleArchive.isPending.value"
                :data-testid="`store-archive-${store.id}`"
                @click="toggleArchive.mutate(store)"
              >
                {{ store.is_archived ? texts.restore : texts.archive }}
              </Button>
              <Button
                variant="ghost"
                class="min-h-11"
                :disabled="remove.isPending.value"
                :data-testid="`store-delete-${store.id}`"
                @click="confirmRemove(store)"
              >
                {{ common.remove }}
              </Button>
            </div>
          </div>

          <template v-if="openOrderStoreId === store.id">
            <p v-if="orderQuery.isPending.value" class="text-muted-foreground text-sm">
              {{ common.loading }}
            </p>
            <StoreCategoryOrderEditor
              v-else
              :categories="categories"
              :order="order"
              :pending="saveOrder.isPending.value"
              @save="saveOrder.mutate($event)"
            />
            <p v-if="orderSaved" class="text-secondary text-sm" data-testid="order-saved">
              {{ texts.orderSaved }}
            </p>
          </template>
        </li>
      </ul>

      <Button
        v-if="!formOpen"
        class="min-h-11 justify-self-start"
        data-testid="store-add"
        @click="openCreate()"
      >
        {{ texts.addStore }}
      </Button>

      <form
        v-else
        class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-2 md:items-end"
        data-testid="store-form"
        @submit.prevent="save.mutate()"
      >
        <div class="grid gap-2">
          <label class="text-sm font-medium" for="store-name">{{ texts.nameLabel }}</label>
          <Input id="store-name" v-model="draft.name" class="min-h-11" data-testid="store-name" />
          <p v-if="!nameValid" class="text-destructive text-xs">{{ texts.nameRequired }}</p>
        </div>

        <div class="grid gap-2">
          <label class="text-sm font-medium" for="store-color">{{ texts.colorLabel }}</label>
          <Input
            id="store-color"
            v-model="draft.color"
            class="min-h-11"
            placeholder="primary"
            data-testid="store-color"
          />
        </div>

        <div class="flex gap-2 md:col-span-2">
          <Button
            type="submit"
            class="min-h-11"
            :disabled="!nameValid || save.isPending.value"
            data-testid="store-submit"
          >
            {{ common.save }}
          </Button>
          <Button
            type="button"
            variant="ghost"
            class="min-h-11"
            data-testid="store-cancel"
            @click="formOpen = false"
          >
            {{ common.cancel }}
          </Button>
        </div>
      </form>
    </CardContent>
  </Card>
</template>
