<script setup lang="ts">
/**
 * Dom i ustawienia: Rodzina / Moje cele / Zakupy / Dane (UX10).
 * Profile, account goals and access accounts retain their separate identities.
 *
 * Stan serwera trzyma TanStack Query (ADR-007): komponent nie kopiuje rodziny,
 * profili ani celów do własnych ref-ów. Do Pinia należy wyłącznie sesja.
 *
 * Wszystko edytuje się w miejscu (06_UIUX §2: minimum ekranów pośrednich),
 * a pusty stan uczy, co zrobić dalej (06_UIUX §3.2).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, ref, watch } from 'vue'

import { ApiError, assertSessionRequestCurrent, captureSessionRequest } from '@/api/client'
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
import PageHeader from '@/components/domain/PageHeader.vue'
import LoadingState from '@/components/domain/LoadingState.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import SettingsTabs from '@/components/domain/settings/SettingsTabs.vue'
import type { SettingsSection } from '@/components/domain/settings/SettingsTabs.vue'
import RoundConfigSection from '@/pages/zakupy/RoundConfigSection.vue'
import SklepySection from '@/components/domain/SklepySection.vue'
import TransferImportDialog from '@/components/domain/TransferImportDialog.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { isValidDecimal, normalizeDecimalInput, toDecimalInput } from '@/lib/decimal'
import { isoDate } from '@/lib/dates'
import { validNavigationDate } from '@/lib/navigation'
import { formatDecimal } from '@/lib/format'
import { statusFor, statusLabel, statusToken } from '@/lib/nutrition'
import { downloadExport } from '@/api/transfer'
import { saveBlob } from '@/lib/download'
import { useAuthStore } from '@/stores/auth'
import { captureSessionGeneration, isSessionGenerationCurrent } from '@/lib/sessionGeneration'
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
// Each protected revision owns its QueryClient and callbacks. Retired handlers
// must not mutate even local feedback after another account/household is loaded.
const pageTicket = captureSessionGeneration()
const currentSession = () => isSessionGenerationCurrent(pageTicket)
const activeSection = ref<SettingsSection>('family')
const shoppingVisited = ref(false)
function selectSection(section: SettingsSection): void {
  activeSection.value = section
  if (section === 'shopping') shoppingVisited.value = true
}
const profileSaved = ref(false)
const goalSaved = ref(false)
const thresholdsSaved = ref(false)

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
  if (!currentSession()) return
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  if (!currentSession()) return
  await queryClient.invalidateQueries({ queryKey: queryKeys.households.all })
}

// --- formularz profilu (dodawanie i edycja w miejscu) -------------------------

/** `id: null` = formularz dodawania; liczba = edycja istniejącego profilu. */
const draft = reactive({ id: null as number | null, name: '', multiplier: '1', kcalGoal: '' })
const formOpen = ref(false)

function openCreate(): void {
  profileSaved.value = false
  draft.id = null
  draft.name = ''
  draft.multiplier = '1'
  draft.kcalGoal = ''
  formOpen.value = true
  actionError.value = null
}

function openEdit(profile: MemberProfile): void {
  profileSaved.value = false
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
  onMutate: () => {
    profileSaved.value = false
    actionError.value = null
  },
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
    if (!currentSession()) return
    profileSaved.value = true
    actionError.value = null
    formOpen.value = false
    await refresh()
  },
  onError: reportError,
})

const toggleActive = useMutation({
  onMutate: () => {
    actionError.value = null
    profileSaved.value = false
  },
  mutationFn: (profile: MemberProfile) =>
    updateProfile(profile.id, { is_active: !profile.is_active }),
  onSuccess: refresh,
  onError: reportError,
})

const remove = useMutation({
  onMutate: () => {
    actionError.value = null
    profileSaved.value = false
  },
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
  validFrom: isoDate(new Date()),
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
  () => validNavigationDate(goalDraft.validFrom) && goalKcalValid.value && goalMacrosValid.value,
)

function optionalDecimal(value: string): string | null {
  return value.trim() === '' ? null : normalizeDecimalInput(value)
}

const saveGoal = useMutation({
  onMutate: () => {
    goalSaved.value = false
    goalError.value = null
  },
  mutationFn: () =>
    createGoal({
      valid_from: goalDraft.validFrom,
      kcal: normalizeDecimalInput(goalDraft.kcal),
      protein_g: optionalDecimal(goalDraft.protein),
      fat_g: optionalDecimal(goalDraft.fat),
      carbs_g: optionalDecimal(goalDraft.carbs),
    }),
  onSuccess: async () => {
    if (!currentSession()) return
    goalSaved.value = true
    goalError.value = null
    goalDraft.kcal = ''
    goalDraft.protein = ''
    goalDraft.fat = ''
    goalDraft.carbs = ''
    await queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
    // Statusy dni liczą się z celu, więc plan musi się odświeżyć razem z nim.
    await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
    if (currentSession()) await queryClient.invalidateQueries({ queryKey: queryKeys.stats.all })
  },
  onError: (error: unknown) => {
    if (!currentSession()) return
    goalError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const removeGoal = useMutation({
  onMutate: () => {
    goalError.value = null
    goalSaved.value = false
  },
  mutationFn: (goal: Goal) => deleteGoal(goal.id),
  onSuccess: async () => {
    if (!currentSession()) return
    await queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
    await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
    if (currentSession()) await queryClient.invalidateQueries({ queryKey: queryKeys.stats.all })
  },
  onError: (error: unknown) => {
    if (!currentSession()) return
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
watch(
  () => [thresholdDraft.low, thresholdDraft.high],
  () => {
    thresholdsSaved.value = false
  },
)

const parsedThresholds = computed(() => ({
  low: /^\d+$/.test(thresholdDraft.low) ? Number(thresholdDraft.low) : NaN,
  high: /^\d+$/.test(thresholdDraft.high) ? Number(thresholdDraft.high) : NaN,
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
  onMutate: () => {
    transferError.value = null
    exportedFilename.value = null
    return { sessionTicket: captureSessionRequest() }
  },
  mutationFn: () => downloadExport('user'),
  onSuccess: (file, _variables, context) => {
    if (!context || !currentSession()) return
    assertSessionRequestCurrent(context.sessionTicket)
    transferError.value = null
    exportedFilename.value = file.filename
    saveBlob(file.blob, file.filename)
  },
  onError: (error: unknown) => {
    if (!currentSession()) return
    transferError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const saveThresholds = useMutation({
  onMutate: () => {
    thresholdsSaved.value = false
    thresholdError.value = null
    return { sessionTicket: captureSessionGeneration() }
  },
  mutationFn: () => updateThresholds(parsedThresholds.value),
  onSuccess: async (user, _variables, context) => {
    if (!context || !auth.setUser(user, context.sessionTicket)) return
    thresholdError.value = null
    thresholdsSaved.value = true
    await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
    if (currentSession()) await queryClient.invalidateQueries({ queryKey: queryKeys.stats.all })
  },
  onError: (error: unknown) => {
    if (!currentSession()) return
    thresholdError.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})
</script>

<template>
  <section class="grid gap-6" data-testid="ustawienia-page">
    <PageHeader
      title="Dom i ustawienia"
      description="Osoby, dla których gotujesz, cele konta i organizacja zakupów."
    />
    <SettingsTabs :model-value="activeSection" @update:model-value="selectSection" />

    <section
      v-show="activeSection === 'family'"
      id="settings-panel-family"
      role="tabpanel"
      aria-labelledby="settings-tab-family"
      tabindex="0"
      class="grid min-w-0 gap-6"
    >
      <LoadingState v-if="my.isPending.value" />
      <ErrorState
        v-else-if="my.isError.value && !my.data.value"
        title="Nie udało się odczytać rodziny"
        :message="common.unexpectedError"
        :pending="my.isFetching.value"
        @retry="my.refetch()"
      />
      <!-- Moja rodzina -->
      <Card v-else class="rounded-2xl">
        <CardHeader>
          <CardTitle>{{ texts.sectionTitle }}</CardTitle>
          <CardDescription class="[overflow-wrap:anywhere]" data-testid="household-name">
            {{ household ? household.name : texts.emptyHousehold }}
          </CardDescription>
        </CardHeader>

        <CardContent v-if="household" class="grid gap-2">
          <h2 class="text-sm font-medium">Konta z dostępem do rodziny</h2>
          <p class="text-muted-foreground text-sm">
            To osoby logujące się do Paśnika. Kontami i przypisaniem do rodziny zarządza
            administrator.
          </p>
          <ul class="grid gap-2" data-testid="household-members">
            <li
              v-for="member in members"
              :key="member.id"
              class="border-border rounded-lg border p-3"
              :data-testid="`household-member-${member.id}`"
            >
              <p class="font-medium [overflow-wrap:anywhere]">{{ member.display_name }}</p>
              <p class="text-muted-foreground text-sm [overflow-wrap:anywhere]">
                {{ member.email }}
              </p>
            </li>
          </ul>
        </CardContent>
      </Card>

      <ErrorState
        v-if="my.isError.value && my.data.value"
        message="Nie udało się odświeżyć rodziny. Pozostają ostatnio odczytane dane."
        :pending="my.isFetching.value"
        @retry="my.refetch()"
      />
      <!-- Profile członków -->
      <Card v-if="household" class="rounded-2xl">
        <CardHeader>
          <CardTitle>Osoby, dla których gotujemy</CardTitle>
          <CardDescription
            >Profile służą do podziału porcji. Nie są kontami i nie dają dostępu do aplikacji. Cel
            profilu to osobne ustawienie od celu Twojego konta.</CardDescription
          >
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
            v-if="profileSaved"
            role="status"
            class="text-primary text-sm"
            data-testid="profile-saved"
          >
            Profil zapisany.
          </p>
          <ErrorState
            v-if="profilesQuery.isError.value && profilesQuery.data.value"
            message="Nie udało się odświeżyć profili. Pozostają ostatnio odczytane dane."
            :pending="profilesQuery.isFetching.value"
            @retry="profilesQuery.refetch()"
          />
          <LoadingState v-if="profilesQuery.isPending.value" />
          <ErrorState
            v-else-if="profilesQuery.isError.value && !profilesQuery.data.value"
            title="Nie udało się odczytać profili"
            :message="common.unexpectedError"
            :pending="profilesQuery.isFetching.value"
            @retry="profilesQuery.refetch()"
          />
          <p
            v-else-if="profiles.length === 0"
            class="text-muted-foreground text-sm"
            data-testid="profiles-empty"
          >
            {{ texts.emptyProfiles }}
          </p>

          <ul v-else class="grid gap-2" data-testid="profiles-list">
            <li
              v-for="profile in profiles"
              :key="profile.id"
              class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
              :data-testid="`profile-row-${profile.id}`"
            >
              <div class="min-w-0">
                <p class="font-medium [overflow-wrap:anywhere]">{{ profile.name }}</p>
                <p class="text-muted-foreground text-sm tabular-nums">
                  {{ texts.multiplierLabel }}: {{ toDecimalInput(profile.default_multiplier) }}
                  <template v-if="profile.kcal_goal">
                    <span aria-hidden="true"> · </span>
                    {{ texts.kcalGoalLabel }}: {{ profile.kcal_goal }} kcal
                  </template>
                </p>
                <p
                  class="text-sm"
                  :class="profile.is_active ? 'text-secondary' : 'text-destructive'"
                >
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
            @submit.prevent="formValid && !save.isPending.value && save.mutate()"
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
              <label class="text-sm font-medium" for="profile-kcal">{{
                texts.kcalGoalLabel
              }}</label>
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
                {{ save.isPending.value ? 'Zapisywanie…' : common.save }}
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
    <section
      v-show="activeSection === 'goals'"
      id="settings-panel-goals"
      role="tabpanel"
      aria-labelledby="settings-tab-goals"
      tabindex="0"
      class="grid min-w-0 gap-6"
    >
      <p class="text-muted-foreground text-sm" data-testid="goals-semantics">
        Te cele i progi należą do Twojego konta. Nie są przypisane do profilu osoby. Podsumowanie
        całego planu nie ocenia realizacji indywidualnego celu.
      </p>
      <!-- Cele żywieniowe (02_DOMAIN §6): historia zostaje, nic nie znika samo (D10). -->
      <Card class="rounded-2xl">
        <CardHeader>
          <CardTitle>Moje cele żywieniowe</CardTitle>
          <CardDescription>{{ goalTexts.sectionSubtitle }}</CardDescription>
        </CardHeader>

        <CardContent class="grid gap-3">
          <p
            v-if="goalError"
            class="text-destructive text-sm"
            role="alert"
            data-testid="goals-error"
          >
            {{ goalError }}
          </p>

          <LoadingState v-if="goalsQuery.isPending.value" />
          <ErrorState
            v-else-if="goalsQuery.isError.value"
            title="Nie udało się odczytać celów"
            :message="common.unexpectedError"
            :pending="goalsQuery.isFetching.value"
            @retry="goalsQuery.refetch()"
          />
          <p v-if="goalSaved" role="status" class="text-primary text-sm" data-testid="goal-saved">
            Cel zapisany w historii.
          </p>
          <p v-if="currentGoal" class="text-sm tabular-nums" data-testid="goal-current">
            {{ goalTexts.currentGoal }}: <strong>{{ formatDecimal(currentGoal.kcal) }} kcal</strong>
            <span class="text-muted-foreground"> (od {{ currentGoal.valid_from }})</span>
          </p>
          <p
            v-else-if="!goalsQuery.isPending.value && !goalsQuery.isError.value"
            class="text-muted-foreground text-sm"
            data-testid="goals-empty"
          >
            Brak celu konta obowiązującego dzisiaj. Możesz dodać cel z wybraną datą rozpoczęcia.
          </p>

          <form
            class="border-border grid gap-3 rounded-lg border p-3 xl:grid-cols-5 sm:grid-cols-2 md:items-end"
            data-testid="goal-form"
            @submit.prevent="goalValid && !saveGoal.isPending.value && saveGoal.mutate()"
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

            <div class="xl:col-span-5 sm:col-span-2">
              <Button
                type="submit"
                class="min-h-11"
                :disabled="!goalValid || saveGoal.isPending.value"
                data-testid="goal-submit"
              >
                {{ saveGoal.isPending.value ? 'Zapisywanie…' : goalTexts.addGoal }}
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
                class="border-border grid gap-2 rounded-lg border p-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
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

      <!-- Progi statusów żywieniowych (D9: domyślnie 90–110% celu). -->
      <Card class="rounded-2xl">
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
            @submit.prevent="
              thresholdsValid && !saveThresholds.isPending.value && saveThresholds.mutate()
            "
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
              {{ saveThresholds.isPending.value ? 'Zapisywanie…' : common.save }}
            </Button>
          </form>

          <p
            class="text-xs"
            :class="thresholdsValid ? 'text-muted-foreground' : 'text-destructive'"
          >
            {{ goalTexts.thresholdsHint }}
          </p>

          <p
            v-if="thresholdsSaved"
            role="status"
            class="text-primary text-sm"
            data-testid="thresholds-saved"
          >
            Progi konta zapisane.
          </p>
          <p class="text-muted-foreground text-sm">
            Progi zachowują ustawienia konta. Przykład poniżej nie jest oceną Twojego planu ani
            spożycia.
          </p>
          <!-- Podgląd uczy, co robi zmiana, zanim użytkownik ją zapisze. -->
          <p v-if="previewStatus" class="text-sm" data-testid="thresholds-preview">
            {{ goalTexts.thresholdsPreview }}
            <strong :class="statusToken(previewStatus).text">{{
              statusLabel(previewStatus)
            }}</strong>
          </p>
        </CardContent>
      </Card>
    </section>
    <section
      v-show="activeSection === 'shopping'"
      id="settings-panel-shopping"
      role="tabpanel"
      aria-labelledby="settings-tab-shopping"
      tabindex="0"
      class="grid min-w-0 gap-6"
    >
      <template v-if="shoppingVisited">
        <!-- Sklepy i profile kolejności kategorii (BATCH_09) — sekcja własnego komponentu. -->
        <SklepySection />

        <RoundConfigSection />
      </template>
    </section>
    <section
      v-show="activeSection === 'data'"
      id="settings-panel-data"
      role="tabpanel"
      aria-labelledby="settings-tab-data"
      tabindex="0"
      class="grid min-w-0 gap-6"
    >
      <!-- Kopia danych rodziny (B14, nazwa z D25): pobranie i wczytanie ze scaleniem. -->
      <Card class="rounded-2xl">
        <CardHeader>
          <CardTitle>{{ transferTexts.sectionTitle }}</CardTitle>
          <CardDescription>{{ transferTexts.sectionSubtitle }}</CardDescription>
          <p class="text-muted-foreground text-sm" data-testid="transfer-scope">
            Kopia zawiera Twoje dane prywatne i wspólne dane rodziny, spiżarnię, profile oraz Twoje
            cele i oceny. Nie zawiera prywatnych danych, celów ani ocen innych kont. Wczytanie scala
            dane; podgląd pokaże kolizje przed zatwierdzeniem.
          </p>
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
                exportData.isPending.value
                  ? transferTexts.exportPending
                  : transferTexts.exportButton
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
    </section>
  </section>
</template>
