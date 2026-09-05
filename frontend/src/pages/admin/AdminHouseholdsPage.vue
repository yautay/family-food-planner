<script setup lang="ts">
/**
 * Administracja rodzinami (`/admin/rodziny`).
 *
 * Stan serwera trzyma TanStack Query (ADR-007). Skład rodziny zmienia się przez
 * `PUT .../members`, które podmienia całą listę — komponent wysyła zawsze pełny
 * zbiór id, a nie „dodaj/usuń jednego".
 *
 * Blokada usunięcia (409) pokazuje listę „Używane w:" z odpowiedzi serwera
 * (06_UIUX §3.3) — nie zgadujemy, co blokuje.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import type { AdminHousehold } from '@/api/adminHouseholds'
import {
  createHousehold,
  deleteHousehold,
  fetchHousehold,
  fetchHouseholds,
  renameHousehold,
  setHouseholdMembers,
} from '@/api/adminHouseholds'
import { fetchUsers } from '@/api/adminUsers'
import { ApiError } from '@/api/client'
import { PAGE_SIZE, usePaginatedList } from '@/api/pagination'
import type { AdminHouseholdsFilters } from '@/api/queryKeys'
import { queryKeys } from '@/api/queryKeys'
import LoadMoreButton from '@/components/domain/LoadMoreButton.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { adminHouseholds as texts, common, listCount } from '@/lib/texts'

interface UsedIn {
  type: string
  id: number
  name: string
}

const queryClient = useQueryClient()

// Filtry BEZ `offset` — numer strony niesie `pageParam` (src/api/pagination.ts).
const filters = computed<AdminHouseholdsFilters>(() => ({ limit: PAGE_SIZE }))
const households = usePaginatedList({
  queryKey: computed(() => queryKeys.adminHouseholds.list(filters.value)),
  fetchPage: (page) => fetchHouseholds({ ...filters.value, ...page }),
})

/**
 * Konta potrzebne do selecta przypisania — bez rodziny albo już w tej rodzinie.
 *
 * Jedna strona z sufitem serwera (200, 04_API §1), bez „pokaż więcej": to jest
 * SELECT wewnątrz formularza, a nie ekran listy. Instancja Paśnika ma kilka
 * kont; gdyby kiedyś przekroczyła 200, ten select potrzebuje szukajki, a nie
 * doładowywania (odnotowane jako follow-up B19).
 */
const usersFilters = { limit: 200, offset: 0 }
const users = useQuery({
  queryKey: queryKeys.adminUsers.list(usersFilters),
  queryFn: () => fetchUsers(usersFilters),
})

const selectedId = ref<number | null>(null)
const detail = useQuery({
  queryKey: computed(() => queryKeys.adminHouseholds.detail(selectedId.value ?? 0)),
  queryFn: () => fetchHousehold(selectedId.value as number),
  enabled: computed(() => selectedId.value !== null),
})

const actionError = ref<string | null>(null)
const usedIn = ref<UsedIn[]>([])

function reportError(error: unknown): void {
  usedIn.value = []
  if (error instanceof ApiError) {
    actionError.value = error.message
    const details = error.details.used_in
    if (Array.isArray(details)) {
      usedIn.value = details as UsedIn[]
    }
    return
  }
  actionError.value = common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.adminHouseholds.all })
  await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.all })
}

function select(household: AdminHousehold): void {
  selectedId.value = selectedId.value === household.id ? null : household.id
  actionError.value = null
  usedIn.value = []
}

// --- tworzenie i zmiana nazwy ---------------------------------------------------

const newName = ref('')
const create = useMutation({
  mutationFn: () => createHousehold(newName.value.trim()),
  onSuccess: async (created) => {
    newName.value = ''
    actionError.value = null
    usedIn.value = []
    selectedId.value = created.id
    await refresh()
  },
  onError: reportError,
})

const renamingId = ref<number | null>(null)
const renameValue = ref('')

function openRename(household: AdminHousehold): void {
  renamingId.value = renamingId.value === household.id ? null : household.id
  renameValue.value = household.name
}

const rename = useMutation({
  mutationFn: (id: number) => renameHousehold(id, renameValue.value.trim()),
  onSuccess: async () => {
    renamingId.value = null
    actionError.value = null
    await refresh()
  },
  onError: reportError,
})

// --- usuwanie -------------------------------------------------------------------

const remove = useMutation({
  mutationFn: (id: number) => deleteHousehold(id),
  onSuccess: async () => {
    selectedId.value = null
    actionError.value = null
    usedIn.value = []
    await refresh()
  },
  onError: reportError,
})

function confirmRemove(household: AdminHousehold): void {
  if (window.confirm(texts.confirmDelete)) {
    remove.mutate(household.id)
  }
}

// --- skład rodziny ---------------------------------------------------------------

/**
 * `PUT .../members` podmienia CAŁY skład, więc wolno go wysłać dopiero, gdy
 * znamy aktualną listę członków. Dopóki `detail` się ładuje, panel składu
 * pokazuje stan ładowania — inaczej przypisanie jednego konta odpięłoby
 * wszystkie pozostałe (wysłalibyśmy listę zbudowaną z pustego `memberIds`).
 */
const membersLoaded = computed(() => detail.data.value !== undefined)
const memberIds = computed(() => (detail.data.value?.members ?? []).map((member) => member.id))

/** Konta, których nie ma jeszcze w tej rodzinie. */
const assignableUsers = computed(() =>
  (users.data.value?.items ?? []).filter((user) => !memberIds.value.includes(user.id)),
)
const userToAssign = ref<number | null>(null)

const setMembers = useMutation({
  mutationFn: (ids: number[]) => setHouseholdMembers(selectedId.value as number, ids),
  onSuccess: async () => {
    actionError.value = null
    userToAssign.value = null
    await refresh()
  },
  onError: reportError,
})

function assign(): void {
  if (userToAssign.value !== null && membersLoaded.value) {
    setMembers.mutate([...memberIds.value, userToAssign.value])
  }
}

function detach(userId: number): void {
  if (membersLoaded.value) {
    setMembers.mutate(memberIds.value.filter((id) => id !== userId))
  }
}
</script>

<template>
  <section class="grid gap-6" data-testid="admin-households-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.createHousehold }}</CardTitle>
      </CardHeader>
      <CardContent>
        <form class="flex flex-wrap gap-2" @submit.prevent="create.mutate()">
          <Input
            v-model="newName"
            class="min-h-11 max-w-xs"
            :aria-label="texts.householdName"
            :placeholder="texts.householdName"
            data-testid="new-household-name"
          />
          <Button
            type="submit"
            class="min-h-11"
            :disabled="newName.trim().length === 0 || create.isPending.value"
            data-testid="new-household-submit"
          >
            {{ texts.createHousehold }}
          </Button>
        </form>
      </CardContent>
    </Card>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.title }}</CardTitle>
        <CardDescription>{{ texts.subtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p v-if="households.isPending.value" class="text-muted-foreground text-sm">
          {{ common.loading }}
        </p>
        <p v-else-if="households.isError.value" class="text-destructive text-sm" role="alert">
          {{ common.unexpectedError }}
        </p>
        <p
          v-else-if="households.items.value.length === 0"
          class="text-muted-foreground text-sm"
          data-testid="households-empty"
        >
          {{ texts.emptyState }}
        </p>
        <p v-else class="text-muted-foreground text-sm tabular-nums" data-testid="households-total">
          {{ texts.title }}: {{ listCount(households.loaded.value, households.total.value) }}
        </p>

        <div v-if="actionError" class="grid gap-1" role="alert" data-testid="households-error">
          <p class="text-destructive text-sm">{{ actionError }}</p>
          <ul
            v-if="usedIn.length"
            class="text-destructive text-sm"
            data-testid="households-used-in"
          >
            <li v-for="entry in usedIn" :key="`${entry.type}-${entry.id}`">· {{ entry.name }}</li>
          </ul>
        </div>

        <ul v-if="households.items.value.length" class="grid gap-2" data-testid="households-list">
          <li
            v-for="household in households.items.value"
            :key="household.id"
            class="border-border grid gap-3 rounded-lg border p-3"
            :data-testid="`household-row-${household.id}`"
          >
            <div class="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
              <div class="min-w-0">
                <p class="truncate font-medium">{{ household.name }}</p>
                <p class="text-muted-foreground text-sm tabular-nums">
                  {{ texts.membersCount }}: {{ household.members_count }}
                  <span aria-hidden="true"> · </span>
                  {{ texts.profilesCount }}: {{ household.profiles_count }}
                </p>
              </div>

              <div class="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  class="min-h-11"
                  :data-testid="`household-select-${household.id}`"
                  @click="select(household)"
                >
                  {{ texts.membersTitle }}
                </Button>
                <Button
                  variant="outline"
                  class="min-h-11"
                  :data-testid="`household-rename-${household.id}`"
                  @click="openRename(household)"
                >
                  {{ texts.rename }}
                </Button>
                <Button
                  variant="ghost"
                  class="min-h-11"
                  :disabled="remove.isPending.value"
                  :data-testid="`household-delete-${household.id}`"
                  @click="confirmRemove(household)"
                >
                  {{ common.remove }}
                </Button>
              </div>
            </div>

            <form
              v-if="renamingId === household.id"
              class="flex flex-wrap gap-2"
              @submit.prevent="rename.mutate(household.id)"
            >
              <Input
                v-model="renameValue"
                class="min-h-11 max-w-xs"
                :aria-label="texts.householdName"
                :data-testid="`household-rename-input-${household.id}`"
              />
              <Button
                type="submit"
                class="min-h-11"
                :disabled="renameValue.trim().length === 0 || rename.isPending.value"
              >
                {{ common.save }}
              </Button>
              <Button type="button" variant="ghost" class="min-h-11" @click="openRename(household)">
                {{ common.cancel }}
              </Button>
            </form>

            <div
              v-if="selectedId === household.id"
              class="border-border grid gap-3 rounded-lg border p-3"
              :data-testid="`household-members-${household.id}`"
            >
              <h2 class="text-sm font-medium">{{ texts.membersTitle }}</h2>

              <!-- Do czasu poznania składu nie pokazujemy narzędzi, które go
                   podmieniają — patrz `membersLoaded`. -->
              <p v-if="!membersLoaded" class="text-muted-foreground text-sm">
                {{ common.loading }}
              </p>

              <template v-else>
                <p
                  v-if="detail.data.value && detail.data.value.members.length === 0"
                  class="text-muted-foreground text-sm"
                >
                  {{ texts.noMembers }}
                </p>

                <ul class="grid gap-2">
                  <li
                    v-for="member in detail.data.value?.members ?? []"
                    :key="member.id"
                    class="flex flex-wrap items-center justify-between gap-2"
                    :data-testid="`household-member-${member.id}`"
                  >
                    <span class="min-w-0 truncate text-sm">
                      {{ member.display_name }} ({{ member.email }})
                    </span>
                    <Button
                      variant="outline"
                      class="min-h-11"
                      :disabled="setMembers.isPending.value"
                      :data-testid="`household-detach-${member.id}`"
                      @click="detach(member.id)"
                    >
                      {{ texts.detach }}
                    </Button>
                  </li>
                </ul>

                <form class="flex flex-wrap gap-2" @submit.prevent="assign()">
                  <label class="sr-only" :for="`assign-${household.id}`">
                    {{ texts.assignUser }}
                  </label>
                  <select
                    :id="`assign-${household.id}`"
                    v-model="userToAssign"
                    class="border-border bg-card min-h-11 max-w-xs rounded-lg border px-3 text-sm"
                    data-testid="household-assign-select"
                  >
                    <option :value="null">—</option>
                    <option v-for="user in assignableUsers" :key="user.id" :value="user.id">
                      {{ user.display_name }} ({{ user.email }})
                    </option>
                  </select>
                  <Button
                    type="submit"
                    class="min-h-11"
                    :disabled="userToAssign === null || setMembers.isPending.value"
                    data-testid="household-assign-submit"
                  >
                    {{ texts.assignUser }}
                  </Button>
                </form>
              </template>
            </div>
          </li>
        </ul>

        <LoadMoreButton
          :loaded="households.loaded.value"
          :total="households.total.value"
          :has-more="households.hasMore.value"
          :loading="households.isLoadingMore.value"
          :failed="households.loadMoreFailed.value"
          testid="households-load-more"
          @more="households.loadMore"
        />
      </CardContent>
    </Card>
  </section>
</template>
