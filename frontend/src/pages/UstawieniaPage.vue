<script setup lang="ts">
/**
 * Ustawienia użytkownika (`/ustawienia`): „Moja rodzina", „Cele żywieniowe",
 * „Sklepy" (BATCH_09), „Progi statusów" (D9) i „Kopia danych rodziny" (B14/B20).
 *
 * Stan serwera trzyma TanStack Query (ADR-007): komponent nie kopiuje rodziny,
 * profili ani celów do własnych ref-ów. Do Pinia należy wyłącznie sesja.
 *
 * Wszystko edytuje się w miejscu (06_UIUX §2: minimum ekranów pośrednich),
 * a pusty stan uczy, co zrobić dalej (06_UIUX §3.2).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'

import { ApiError } from '@/api/client'
import type { Goal } from '@/api/goals'
import {
  DEFAULT_THRESHOLDS,
  createGoal,
  deleteGoal,
  fetchGoals,
  updateThresholds,
} from '@/api/goals'
import type { MemberProfile } from '@/api/households'
import {
  createProfile,
  deleteProfile,
  fetchMyHousehold,
  fetchMyProfiles,
  updateProfile,
} from '@/api/households'
import { queryKeys } from '@/api/queryKeys'
import SklepySection from '@/components/domain/SklepySection.vue'
import TransferImportDialog from '@/components/domain/TransferImportDialog.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { isValidDecimal, normalizeDecimalInput, toDecimalInput } from '@/lib/decimal'
import { formatDecimal } from '@/lib/format'
import { statusFor, statusLabel, statusToken } from '@/lib/nutrition'
import { downloadExport } from '@/api/transfer'
import { saveBlob } from '@/lib/download'
import { useAuthStore } from '@/stores/auth'
import {
  common,
  goals as goalTexts,
  household as texts,
  transfer as transferTexts,
} from '@/lib/texts'

const MULTIPLIER_RULES = { decimalPlaces: 2, positive: true }
const KCAL_RULES = { decimalPlaces: 0, positive: true }
const MACRO_RULES = { decimalPlaces: 1, positive: true }

const queryClient = useQueryClient()
const auth = useAuthStore()

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

// --- cele żywieniowe (historia po `valid_from`) --------------------------------

const goalsQuery = useQuery({ queryKey: queryKeys.goals.all, queryFn: fetchGoals })

const goalsList = computed(() => goalsQuery.data.value?.items ?? [])
const currentGoal = computed(() => goalsQuery.data.value?.current ?? null)

const goalError = ref<string | null>(null)
const goalDraft = reactive({
  validFrom: new Date().toISOString().slice(0, 10),
  kcal: '',
  protein: '',
  fat: '',
  carbs: '',
})

const goalKcalValid = computed(() => isValidDecimal(goalDraft.kcal, KCAL_RULES))
const goalMacrosValid = computed(() =>
  [goalDraft.protein, goalDraft.fat, goalDraft.carbs].every(
    (value) => value.trim() === '' || isValidDecimal(value, MACRO_RULES),
  ),
)
const goalValid = computed(
  () => goalDraft.validFrom.length === 10 && goalKcalValid.value && goalMacrosValid.value,
)

function optionalDecimal(value: string): string | null {
  return value.trim() === '' ? null : normalizeDecimalInput(value)
}

const saveGoal = useMutation({
  mutationFn: () =>
    createGoal({
      valid_from: goalDraft.validFrom,
      kcal: normalizeDecimalInput(goalDraft.kcal),
      protein_g: optionalDecimal(goalDraft.protein),
      fat_g: optionalDecimal(goalDraft.fat),
      carbs_g: optionalDecimal(goalDraft.carbs),
    }),
  onSuccess: async () => {
    goalError.value = null
    goalDraft.kcal = ''
    goalDraft.protein = ''
    goalDraft.fat = ''
    goalDraft.carbs = ''
    await queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
    // Statusy dni liczą się z celu, więc plan musi się odświeżyć razem z nim.
    await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
  },
  onError: (error: unknown) => {
    goalError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const removeGoal = useMutation({
  mutationFn: (goal: Goal) => deleteGoal(goal.id),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
    await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
  },
  onError: (error: unknown) => {
    goalError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

function confirmGoalRemove(goal: Goal): void {
  if (window.confirm(goalTexts.confirmDelete)) {
    removeGoal.mutate(goal)
  }
}

// --- progi statusów (D9) ---------------------------------------------------------

const storedThresholds = computed(() => {
  const raw = auth.user?.ui_settings?.nutrition_thresholds
  if (typeof raw !== 'object' || raw === null) {
    return DEFAULT_THRESHOLDS
  }
  const value = raw as { low?: unknown; high?: unknown }
  return typeof value.low === 'number' && typeof value.high === 'number'
    ? { low: value.low, high: value.high }
    : DEFAULT_THRESHOLDS
})

const thresholdDraft = reactive({
  low: String(storedThresholds.value.low),
  high: String(storedThresholds.value.high),
})
const thresholdError = ref<string | null>(null)

const parsedThresholds = computed(() => ({
  low: Number.parseInt(thresholdDraft.low, 10),
  high: Number.parseInt(thresholdDraft.high, 10),
}))
const thresholdsValid = computed(() => {
  const { low, high } = parsedThresholds.value
  return Number.isInteger(low) && Number.isInteger(high) && low > 0 && low < high
})

/** Podgląd na stałym przykładzie: 1800 kcal przy celu 2000 kcal = 90% celu. */
const previewStatus = computed(() =>
  thresholdsValid.value ? statusFor(1800, 2000, parsedThresholds.value) : null,
)

// --- Kopia danych rodziny: pobranie i wczytanie (B14, D25/D26) ------------------

const transferOpen = ref(false)
const transferError = ref<string | null>(null)
const exportedFilename = ref<string | null>(null)

const exportData = useMutation({
  mutationFn: () => downloadExport('user'),
  onSuccess: (file) => {
    transferError.value = null
    exportedFilename.value = file.filename
    saveBlob(file.blob, file.filename)
  },
  onError: (error: unknown) => {
    transferError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const saveThresholds = useMutation({
  mutationFn: () => updateThresholds(parsedThresholds.value),
  onSuccess: async (user) => {
    thresholdError.value = null
    auth.setUser(user)
    await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
  },
  onError: (error: unknown) => {
    thresholdError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})
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

    <!-- Cele żywieniowe (02_DOMAIN §6): historia zostaje, nic nie znika samo (D10). -->
    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ goalTexts.sectionTitle }}</CardTitle>
        <CardDescription>{{ goalTexts.sectionSubtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p v-if="goalError" class="text-destructive text-sm" role="alert" data-testid="goals-error">
          {{ goalError }}
        </p>

        <p v-if="currentGoal" class="text-sm tabular-nums" data-testid="goal-current">
          {{ goalTexts.currentGoal }}: <strong>{{ formatDecimal(currentGoal.kcal) }} kcal</strong>
          <span class="text-muted-foreground"> (od {{ currentGoal.valid_from }})</span>
        </p>
        <p
          v-else-if="!goalsQuery.isPending.value"
          class="text-muted-foreground text-sm"
          data-testid="goals-empty"
        >
          {{ goalTexts.emptyState }}
        </p>

        <form
          class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-5 md:items-end"
          data-testid="goal-form"
          @submit.prevent="saveGoal.mutate()"
        >
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="goal-valid-from">
              {{ goalTexts.validFromLabel }}
            </label>
            <Input
              id="goal-valid-from"
              v-model="goalDraft.validFrom"
              type="date"
              class="min-h-11 tabular-nums"
              data-testid="goal-valid-from"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="goal-kcal">{{ goalTexts.kcalLabel }}</label>
            <Input
              id="goal-kcal"
              v-model="goalDraft.kcal"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              :aria-invalid="!goalKcalValid"
              data-testid="goal-kcal"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="goal-protein">
              {{ goalTexts.proteinLabel }}
            </label>
            <Input
              id="goal-protein"
              v-model="goalDraft.protein"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="goal-protein"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="goal-fat">{{ goalTexts.fatLabel }}</label>
            <Input
              id="goal-fat"
              v-model="goalDraft.fat"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="goal-fat"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="goal-carbs">{{ goalTexts.carbsLabel }}</label>
            <Input
              id="goal-carbs"
              v-model="goalDraft.carbs"
              inputmode="decimal"
              class="min-h-11 tabular-nums"
              data-testid="goal-carbs"
            />
          </div>

          <div class="md:col-span-5">
            <Button
              type="submit"
              class="min-h-11"
              :disabled="!goalValid || saveGoal.isPending.value"
              data-testid="goal-submit"
            >
              {{ goalTexts.addGoal }}
            </Button>
            <span
              v-if="!goalKcalValid && goalDraft.kcal !== ''"
              class="text-destructive ml-2 text-xs"
            >
              {{ goalTexts.kcalRequired }}
            </span>
          </div>
        </form>

        <template v-if="goalsList.length">
          <h3 class="text-sm font-medium">{{ goalTexts.historyTitle }}</h3>
          <ul class="grid gap-2" data-testid="goals-list">
            <li
              v-for="goal in goalsList"
              :key="goal.id"
              class="border-border grid gap-2 rounded-lg border p-3 md:grid-cols-[1fr_auto] md:items-center"
              :data-testid="`goal-row-${goal.id}`"
            >
              <div class="min-w-0 text-sm tabular-nums">
                <p class="font-medium">
                  od {{ goal.valid_from }} · {{ formatDecimal(goal.kcal) }} kcal
                </p>
                <p class="text-muted-foreground">
                  <span v-if="goal.protein_g">B {{ formatDecimal(goal.protein_g) }} g</span>
                  <span v-if="goal.fat_g"> · T {{ formatDecimal(goal.fat_g) }} g</span>
                  <span v-if="goal.carbs_g"> · W {{ formatDecimal(goal.carbs_g) }} g</span>
                </p>
              </div>
              <Button
                variant="ghost"
                class="min-h-11"
                :disabled="removeGoal.isPending.value"
                :data-testid="`goal-delete-${goal.id}`"
                @click="confirmGoalRemove(goal)"
              >
                {{ common.remove }}
              </Button>
            </li>
          </ul>
        </template>
      </CardContent>
    </Card>

    <!-- Sklepy i profile kolejności kategorii (BATCH_09) — sekcja własnego komponentu. -->
    <SklepySection />

    <!-- Kopia danych rodziny (B14, nazwa z D25): pobranie i wczytanie ze scaleniem. -->
    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ transferTexts.sectionTitle }}</CardTitle>
        <CardDescription>{{ transferTexts.sectionSubtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p
          v-if="transferError"
          class="text-destructive text-sm"
          role="alert"
          data-testid="transfer-error"
        >
          {{ transferError }}
        </p>

        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            class="min-h-11"
            :disabled="exportData.isPending.value"
            data-testid="transfer-export"
            @click="exportData.mutate()"
          >
            {{
              exportData.isPending.value ? transferTexts.exportPending : transferTexts.exportButton
            }}
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11"
            data-testid="transfer-import-open"
            @click="transferOpen = !transferOpen"
          >
            {{ transferTexts.importButton }}
          </Button>
        </div>

        <p class="text-muted-foreground text-xs">{{ transferTexts.exportHint }}</p>
        <p class="text-muted-foreground text-xs" data-testid="transfer-ownership">
          {{ transferTexts.ownershipNote }}
        </p>
        <p v-if="exportedFilename" class="text-sm" data-testid="transfer-export-done">
          {{ transferTexts.exportDone(exportedFilename) }}
        </p>

        <TransferImportDialog :open="transferOpen" @close="transferOpen = false" />
      </CardContent>
    </Card>

    <!-- Progi statusów żywieniowych (D9: domyślnie 90–110% celu). -->
    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ goalTexts.thresholdsTitle }}</CardTitle>
        <CardDescription>{{ goalTexts.thresholdsSubtitle }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p
          v-if="thresholdError"
          class="text-destructive text-sm"
          role="alert"
          data-testid="thresholds-error"
        >
          {{ thresholdError }}
        </p>

        <form
          class="grid gap-3 md:grid-cols-3 md:items-end"
          data-testid="thresholds-form"
          @submit.prevent="saveThresholds.mutate()"
        >
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="threshold-low">
              {{ goalTexts.thresholdLow }}
            </label>
            <Input
              id="threshold-low"
              v-model="thresholdDraft.low"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              :aria-invalid="!thresholdsValid"
              data-testid="threshold-low"
            />
          </div>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="threshold-high">
              {{ goalTexts.thresholdHigh }}
            </label>
            <Input
              id="threshold-high"
              v-model="thresholdDraft.high"
              inputmode="numeric"
              class="min-h-11 tabular-nums"
              :aria-invalid="!thresholdsValid"
              data-testid="threshold-high"
            />
          </div>
          <Button
            type="submit"
            class="min-h-11"
            :disabled="!thresholdsValid || saveThresholds.isPending.value"
            data-testid="thresholds-submit"
          >
            {{ common.save }}
          </Button>
        </form>

        <p class="text-xs" :class="thresholdsValid ? 'text-muted-foreground' : 'text-destructive'">
          {{ goalTexts.thresholdsHint }}
        </p>

        <!-- Podgląd uczy, co robi zmiana, zanim użytkownik ją zapisze. -->
        <p v-if="previewStatus" class="text-sm" data-testid="thresholds-preview">
          {{ goalTexts.thresholdsPreview }}
          <strong :class="statusToken(previewStatus).text">{{ statusLabel(previewStatus) }}</strong>
        </p>
      </CardContent>
    </Card>
  </section>
</template>
