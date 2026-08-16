<script setup lang="ts">
/**
 * Ustawienia użytkownika (`/ustawienia`) — sekcja „Moja rodzina".
 *
 * Stan serwera trzyma TanStack Query (ADR-007): komponent nie kopiuje rodziny
 * ani profili do własnych ref-ów. Do Pinia należy wyłącznie sesja.
 *
 * Profile edytuje się w miejscu (06_UIUX §2: minimum ekranów pośrednich),
 * a pusty stan uczy, co zrobić dalej (06_UIUX §3.2).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'

import { ApiError } from '@/api/client'
import type { MemberProfile } from '@/api/households'
import {
  createProfile,
  deleteProfile,
  fetchMyHousehold,
  fetchMyProfiles,
  updateProfile,
} from '@/api/households'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { isValidDecimal, normalizeDecimalInput, toDecimalInput } from '@/lib/decimal'
import { common, household as texts } from '@/lib/texts'

const MULTIPLIER_RULES = { decimalPlaces: 2, positive: true }
const KCAL_RULES = { decimalPlaces: 0, positive: true }

const queryClient = useQueryClient()

const my = useQuery({ queryKey: queryKeys.households.my, queryFn: fetchMyHousehold })
const profilesQuery = useQuery({
  queryKey: queryKeys.households.profiles,
  queryFn: fetchMyProfiles,
})

const household = computed(() => my.data.value?.household ?? null)
const members = computed(() => my.data.value?.members ?? [])
const profiles = computed(() => profilesQuery.data.value?.items ?? [])

const actionError = ref<string | null>(null)

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.households.all })
}

// --- formularz profilu (dodawanie i edycja w miejscu) -------------------------

/** `id: null` = formularz dodawania; liczba = edycja istniejącego profilu. */
const draft = reactive({ id: null as number | null, name: '', multiplier: '1', kcalGoal: '' })
const formOpen = ref(false)

function openCreate(): void {
  draft.id = null
  draft.name = ''
  draft.multiplier = '1'
  draft.kcalGoal = ''
  formOpen.value = true
  actionError.value = null
}

function openEdit(profile: MemberProfile): void {
  draft.id = profile.id
  draft.name = profile.name
  draft.multiplier = toDecimalInput(profile.default_multiplier)
  draft.kcalGoal = toDecimalInput(profile.kcal_goal)
  formOpen.value = true
  actionError.value = null
}

function closeForm(): void {
  formOpen.value = false
}

const nameValid = computed(() => draft.name.trim().length > 0)
const multiplierValid = computed(() => isValidDecimal(draft.multiplier, MULTIPLIER_RULES))
const kcalGoalValid = computed(
  () => draft.kcalGoal.trim() === '' || isValidDecimal(draft.kcalGoal, KCAL_RULES),
)
const formValid = computed(() => nameValid.value && multiplierValid.value && kcalGoalValid.value)

const save = useMutation({
  mutationFn: () => {
    const payload = {
      name: draft.name.trim(),
      default_multiplier: normalizeDecimalInput(draft.multiplier),
      kcal_goal: draft.kcalGoal.trim() === '' ? null : normalizeDecimalInput(draft.kcalGoal),
    }
    return draft.id === null
      ? createProfile({ ...payload, is_active: true })
      : updateProfile(draft.id, payload)
  },
  onSuccess: async () => {
    actionError.value = null
    formOpen.value = false
    await refresh()
  },
  onError: reportError,
})

const toggleActive = useMutation({
  mutationFn: (profile: MemberProfile) =>
    updateProfile(profile.id, { is_active: !profile.is_active }),
  onSuccess: refresh,
  onError: reportError,
})

const remove = useMutation({
  mutationFn: (profile: MemberProfile) => deleteProfile(profile.id),
  onSuccess: refresh,
  onError: reportError,
})

function confirmRemove(profile: MemberProfile): void {
  if (window.confirm(texts.confirmProfileDelete)) {
    remove.mutate(profile)
  }
}
</script>

<template>
  <section class="grid gap-6" data-testid="ustawienia-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">Ustawienia</h1>
      <p class="text-muted-foreground text-sm">{{ texts.sectionSubtitle }}</p>
    </header>

    <p v-if="my.isPending.value" class="text-muted-foreground text-sm">{{ common.loading }}</p>

    <!-- Moja rodzina -->
    <Card v-else class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.sectionTitle }}</CardTitle>
        <CardDescription data-testid="household-name">
          {{ household ? household.name : texts.emptyHousehold }}
        </CardDescription>
      </CardHeader>

      <CardContent v-if="household" class="grid gap-2">
        <h2 class="text-sm font-medium">{{ texts.membersTitle }}</h2>
        <ul class="grid gap-2" data-testid="household-members">
          <li
            v-for="member in members"
            :key="member.id"
            class="border-border rounded-lg border p-3"
            :data-testid="`household-member-${member.id}`"
          >
            <p class="truncate font-medium">{{ member.display_name }}</p>
            <p class="text-muted-foreground truncate text-sm">{{ member.email }}</p>
          </li>
        </ul>
      </CardContent>
    </Card>

    <!-- Profile członków -->
    <Card v-if="household" class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.profilesTitle }}</CardTitle>
        <CardDescription>{{ texts.profilesSubtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p
          v-if="actionError"
          class="text-destructive text-sm"
          role="alert"
          data-testid="profiles-error"
        >
          {{ actionError }}
        </p>

        <p
          v-if="profiles.length === 0 && !profilesQuery.isPending.value"
          class="text-muted-foreground text-sm"
          data-testid="profiles-empty"
        >
          {{ texts.emptyProfiles }}
        </p>

        <ul v-else class="grid gap-2" data-testid="profiles-list">
          <li
            v-for="profile in profiles"
            :key="profile.id"
            class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-[1fr_auto] md:items-center"
            :data-testid="`profile-row-${profile.id}`"
          >
            <div class="min-w-0">
              <p class="truncate font-medium">{{ profile.name }}</p>
              <p class="text-muted-foreground text-sm tabular-nums">
                {{ texts.multiplierLabel }}: {{ toDecimalInput(profile.default_multiplier) }}
                <template v-if="profile.kcal_goal">
                  <span aria-hidden="true"> · </span>
                  {{ texts.kcalGoalLabel }}: {{ profile.kcal_goal }} kcal
                </template>
              </p>
              <p class="text-sm" :class="profile.is_active ? 'text-secondary' : 'text-destructive'">
                {{ profile.is_active ? texts.activeLabel : texts.inactiveLabel }}
              </p>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button
                variant="outline"
                class="min-h-11"
                :data-testid="`profile-edit-${profile.id}`"
                @click="openEdit(profile)"
              >
                {{ common.edit }}
              </Button>
              <Button
                variant="outline"
                class="min-h-11"
                :disabled="toggleActive.isPending.value"
                :data-testid="`profile-active-${profile.id}`"
                @click="toggleActive.mutate(profile)"
              >
                {{ profile.is_active ? texts.deactivate : texts.activate }}
              </Button>
              <Button
                variant="ghost"
                class="min-h-11"
                :disabled="remove.isPending.value"
                :data-testid="`profile-delete-${profile.id}`"
                @click="confirmRemove(profile)"
              >
                {{ common.remove }}
              </Button>
            </div>
          </li>
        </ul>

        <Button
          v-if="!formOpen"
          class="min-h-11 justify-self-start"
          data-testid="profile-add"
          @click="openCreate()"
        >
          {{ texts.addProfile }}
        </Button>

        <form
          v-else
          class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-3 md:items-end"
          data-testid="profile-form"
          @submit.prevent="save.mutate()"
        >
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="profile-name">{{ texts.nameLabel }}</label>
            <Input
              id="profile-name"
              v-model="draft.name"
              class="min-h-11"
              data-testid="profile-name"
            />
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="profile-multiplier">
              {{ texts.multiplierLabel }}
            </label>
            <Input
              id="profile-multiplier"
              v-model="draft.multiplier"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="profile-multiplier"
            />
            <p
              class="text-xs"
              :class="multiplierValid ? 'text-muted-foreground' : 'text-destructive'"
              data-testid="profile-multiplier-hint"
            >
              {{ texts.multiplierHint }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="profile-kcal">{{ texts.kcalGoalLabel }}</label>
            <Input
              id="profile-kcal"
              v-model="draft.kcalGoal"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              data-testid="profile-kcal"
            />
            <p
              class="text-xs"
              :class="kcalGoalValid ? 'text-muted-foreground' : 'text-destructive'"
              data-testid="profile-kcal-hint"
            >
              {{ texts.kcalGoalHint }}
            </p>
          </div>

          <div class="flex gap-2 md:col-span-3">
            <Button
              type="submit"
              class="min-h-11"
              :disabled="!formValid || save.isPending.value"
              data-testid="profile-submit"
            >
              {{ common.save }}
            </Button>
            <Button
              type="button"
              variant="ghost"
              class="min-h-11"
              data-testid="profile-cancel"
              @click="closeForm()"
            >
              {{ common.cancel }}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  </section>
</template>
