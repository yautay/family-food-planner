<script setup lang="ts">
/**
 * Administracja kontami (`/admin/uzytkownicy`).
 *
 * Stan serwera trzyma TanStack Query — komponent nie kopiuje listy kont do
 * własnego ref-a (ADR-007). Formularz tworzenia jest na stronie, bez ekranu
 * pośredniego (06_UIUX §2: mniej kliknięć od intencji do efektu).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'

import type { AdminUser, AdminUserUpdate } from '@/api/adminUsers'
import { createUser, fetchUsers, updateUser } from '@/api/adminUsers'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { admin as texts, common } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

const PAGE_SIZE = 50
const MIN_PASSWORD_LENGTH = 10

const auth = useAuthStore()
const queryClient = useQueryClient()

const search = ref('')
const appliedSearch = ref('')
const filters = computed(() => ({ limit: PAGE_SIZE, offset: 0, q: appliedSearch.value }))

const users = useQuery({
  queryKey: computed(() => queryKeys.adminUsers.list(filters.value)),
  queryFn: () => fetchUsers(filters.value),
})

const actionError = ref<string | null>(null)

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.all })
}

// --- tworzenie konta ---------------------------------------------------------

const form = reactive({ email: '', display_name: '', password: '', role: 'user' as const })
const formError = ref<string | null>(null)

const create = useMutation({
  mutationFn: () =>
    createUser({
      email: form.email.trim(),
      display_name: form.display_name.trim(),
      password: form.password,
      role: form.role,
      is_active: true,
    }),
  onSuccess: async () => {
    form.email = ''
    form.display_name = ''
    form.password = ''
    formError.value = null
    await refresh()
  },
  onError: (error: unknown) => {
    formError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const formValid = computed(
  () =>
    form.email.trim().length > 0 &&
    form.display_name.trim().length > 0 &&
    form.password.length >= MIN_PASSWORD_LENGTH,
)

// --- edycja konta ------------------------------------------------------------

const update = useMutation({
  mutationFn: ({ id, payload }: { id: number; payload: AdminUserUpdate }) =>
    updateUser(id, payload),
  onSuccess: async () => {
    actionError.value = null
    await refresh()
  },
  onError: reportError,
})

/** Konto, dla którego otwarty jest formularz zmiany hasła. */
const passwordFor = ref<number | null>(null)
const newPassword = ref('')

function toggleRole(user: AdminUser): void {
  update.mutate({ id: user.id, payload: { role: user.role === 'admin' ? 'user' : 'admin' } })
}

function toggleActive(user: AdminUser): void {
  update.mutate({ id: user.id, payload: { is_active: !user.is_active } })
}

function openPasswordForm(userId: number): void {
  passwordFor.value = passwordFor.value === userId ? null : userId
  newPassword.value = ''
}

function submitPassword(userId: number): void {
  update.mutate(
    { id: userId, payload: { password: newPassword.value } },
    {
      onSuccess: () => {
        passwordFor.value = null
        newPassword.value = ''
      },
    },
  )
}

const isSelf = (user: AdminUser): boolean => user.id === auth.user?.id
</script>

<template>
  <section class="grid gap-6" data-testid="admin-users-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.usersTitle }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.usersSubtitle }}</p>
    </header>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.createUser }}</CardTitle>
        <CardDescription>{{ texts.passwordHint }}</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="grid gap-3 md:grid-cols-4 md:items-end" @submit.prevent="create.mutate()">
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="new-email">Adres e-mail</label>
            <Input
              id="new-email"
              v-model="form.email"
              type="email"
              autocomplete="off"
              class="min-h-11"
              data-testid="new-user-email"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="new-name">Nazwa wyświetlana</label>
            <Input
              id="new-name"
              v-model="form.display_name"
              class="min-h-11"
              data-testid="new-user-name"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="new-password">Hasło</label>
            <Input
              id="new-password"
              v-model="form.password"
              type="password"
              autocomplete="new-password"
              class="min-h-11"
              data-testid="new-user-password"
            />
          </div>
          <Button
            type="submit"
            class="min-h-11"
            :disabled="!formValid || create.isPending.value"
            data-testid="new-user-submit"
          >
            {{ texts.createUser }}
          </Button>

          <p
            v-if="formError"
            class="text-destructive text-sm md:col-span-4"
            role="alert"
            data-testid="new-user-error"
          >
            {{ formError }}
          </p>
        </form>
      </CardContent>
    </Card>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.usersTitle }}</CardTitle>
        <CardDescription>
          <form class="flex gap-2 pt-2" @submit.prevent="appliedSearch = search">
            <Input
              v-model="search"
              class="min-h-11 max-w-xs"
              :placeholder="common.search"
              aria-label="Szukaj konta"
              data-testid="users-search"
            />
            <Button type="submit" variant="outline" class="min-h-11">{{ common.search }}</Button>
          </form>
        </CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p v-if="users.isPending.value" class="text-muted-foreground text-sm">
          {{ common.loading }}
        </p>
        <p v-else-if="users.isError.value" class="text-destructive text-sm" role="alert">
          {{ common.unexpectedError }}
        </p>
        <p v-else-if="users.data.value?.items.length === 0" class="text-muted-foreground text-sm">
          {{ texts.emptyState }}
        </p>

        <p
          v-if="actionError"
          class="text-destructive text-sm"
          role="alert"
          data-testid="users-error"
        >
          {{ actionError }}
        </p>

        <ul v-if="users.data.value" class="grid gap-2" data-testid="users-list">
          <li
            v-for="user in users.data.value.items"
            :key="user.id"
            class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-[1fr_auto] md:items-center"
            :data-testid="`user-row-${user.id}`"
          >
            <div class="min-w-0">
              <p class="truncate font-medium">{{ user.display_name }}</p>
              <p class="text-muted-foreground truncate text-sm">{{ user.email }}</p>
              <p class="text-sm">
                <span>{{ user.role === 'admin' ? texts.roleAdmin : texts.roleUser }}</span>
                <span aria-hidden="true"> · </span>
                <span :class="user.is_active ? 'text-secondary' : 'text-destructive'">
                  {{ user.is_active ? texts.active : texts.inactive }}
                </span>
              </p>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button
                variant="outline"
                class="min-h-11"
                :disabled="isSelf(user) || update.isPending.value"
                :data-testid="`user-role-${user.id}`"
                @click="toggleRole(user)"
              >
                {{ user.role === 'admin' ? texts.demote : texts.promote }}
              </Button>
              <Button
                variant="outline"
                class="min-h-11"
                :disabled="isSelf(user) || update.isPending.value"
                :data-testid="`user-active-${user.id}`"
                @click="toggleActive(user)"
              >
                {{ user.is_active ? texts.deactivate : texts.activate }}
              </Button>
              <Button
                variant="ghost"
                class="min-h-11"
                :data-testid="`user-password-${user.id}`"
                @click="openPasswordForm(user.id)"
              >
                {{ texts.resetPassword }}
              </Button>
            </div>

            <form
              v-if="passwordFor === user.id"
              class="flex flex-wrap gap-2 md:col-span-2"
              @submit.prevent="submitPassword(user.id)"
            >
              <Input
                v-model="newPassword"
                type="password"
                autocomplete="new-password"
                class="min-h-11 max-w-xs"
                :aria-label="`Nowe hasło dla ${user.email}`"
                :data-testid="`user-new-password-${user.id}`"
              />
              <Button
                type="submit"
                class="min-h-11"
                :disabled="newPassword.length < MIN_PASSWORD_LENGTH || update.isPending.value"
              >
                {{ common.save }}
              </Button>
              <Button
                type="button"
                variant="ghost"
                class="min-h-11"
                @click="openPasswordForm(user.id)"
              >
                {{ common.cancel }}
              </Button>
            </form>
          </li>
        </ul>
      </CardContent>
    </Card>
  </section>
</template>
