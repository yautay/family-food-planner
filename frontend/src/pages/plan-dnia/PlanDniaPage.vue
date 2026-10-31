<script setup lang="ts">
/**
 * Plan dnia — widok 1 wizualizacji (06_UIUX §4.1), trasa `/plan-dnia/:date?`.
 *
 * Jedzenie przed zwięzłym podsumowaniem „Cały plan”, bez porównywania rodzinnej
 * sumy z indywidualnym celem konta. Cel konkretnego posiłku pozostaje jawny.
 *
 * Stan serwera trzyma WYŁĄCZNIE TanStack Query (ADR-007) — komponent nie kopiuje
 * dnia do własnych ref-ów. Ref-y opisują tylko intencje UI (otwarty formularz,
 * wybrana pozycja, treść dialogu). Każda mutacja zwraca cały dzień, ale i tak
 * unieważniamy zakres planu i statystyki. Panel przepisu robi to sam.
 *
 * Żadna wartość odżywcza nie jest tu liczona: wszystko przychodzi z backendu
 * jako stringi dziesiętne (ADR-008), a strona tylko formatuje.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { CalendarPlus, ChevronLeft, ChevronRight, Plus } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { fetchMyProfiles } from '@/api/households'
import type { FitToTarget, PlanDay, PlanServingSplitInput } from '@/api/planning'
import {
  addItem,
  copyPlan,
  createMeal,
  deleteItem,
  deleteMeal,
  fetchPlanDays,
  fitItemToTarget,
  updateItem,
  updateMeal,
} from '@/api/planning'
import { queryKeys } from '@/api/queryKeys'
import type { Product, ProductDetail } from '@/api/catalog'
import AmountInput from '@/components/domain/AmountInput.vue'
import EmptyState from '@/components/domain/EmptyState.vue'
import MealCard from '@/components/domain/MealCard.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import ServingsSplitDrawer from '@/components/domain/ServingsSplitDrawer.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { addDays, isoDate, startOfWeek, weekDayLabel } from '@/lib/dates'
import { isValidDecimal, normalizeDecimalInput } from '@/lib/decimal'
import { formatDecimal } from '@/lib/format'
import { planNavigationContext, planNavigationTarget, validNavigationDate } from '@/lib/navigation'
import { common, plan as texts, recipes as recipeTexts } from '@/lib/texts'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

/** Data z trasy; brak parametru = dziś (najczęstszy przypadek otwarcia planu). */
const currentDate = computed(() => {
  return validNavigationDate(route.params.date) ?? isoDate(new Date())
})

/** Zakres tygodnia pobieramy JEDNYM zapytaniem — panel boczny nie ma własnego. */
const weekStart = computed(() => startOfWeek(currentDate.value))
const weekEnd = computed(() => addDays(weekStart.value, 6))
const rangeFrom = computed(() =>
  currentDate.value < weekStart.value ? currentDate.value : weekStart.value,
)
const rangeTo = computed(() =>
  currentDate.value > weekEnd.value ? currentDate.value : weekEnd.value,
)

const days = useQuery({
  queryKey: computed(() => queryKeys.planDays.range(rangeFrom.value, rangeTo.value)),
  queryFn: () => fetchPlanDays(rangeFrom.value, rangeTo.value),
})

const profilesQuery = useQuery({
  queryKey: queryKeys.households.profiles,
  queryFn: fetchMyProfiles,
})

/** Pusty dzień renderujemy lokalnie: backend zwraca tylko dni istniejące. */
const emptyDay = computed<PlanDay>(() => ({
  id: null,
  day: currentDate.value,
  title: null,
  scope: 'private',
  owner_user_id: null,
  meals: [],
  nutrition: {
    kcal: '0',
    protein_g: '0',
    fat_g: '0',
    carbs_g: '0',
    fiber_g: '0',
    sugars_g: '0',
    glycemic_load: '0',
    complete: true,
    missing: [],
  },
  goal_progress: {
    kcal: { value: '0', target: null, delta: null, status: null },
    protein_g: { value: '0', target: null, delta: null, status: null },
    fat_g: { value: '0', target: null, delta: null, status: null },
    carbs_g: { value: '0', target: null, delta: null, status: null },
  },
  goal_valid_from: null,
  created_at: null,
  updated_at: null,
}))

const day = computed<PlanDay>(
  () => days.data.value?.items.find((item) => item.day === currentDate.value) ?? emptyDay.value,
)
const profiles = computed(() => profilesQuery.data.value?.items ?? [])

const week = computed(() =>
  Array.from({ length: 7 }, (_value, index) => {
    const date = addDays(weekStart.value, index)
    return {
      date,
      label: weekDayLabel(date),
      isCurrent: date === currentDate.value,
    }
  }),
)

async function goTo(date: string): Promise<void> {
  await router.push(
    planNavigationTarget('plan-dnia', { ...planNavigationContext(route), selectedDate: date }),
  )
}

// --- mutacje ---------------------------------------------------------------------

const actionError = ref<string | null>(null)

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  actionError.value = null
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.stats.all }),
  ])
}

const mealForm = ref<{ open: boolean; id: number | null; name: string; target: string }>({
  open: false,
  id: null,
  name: '',
  target: '',
})

function openMealForm(id: number | null): void {
  const meal = id === null ? null : day.value.meals.find((item) => item.id === id)
  mealForm.value = {
    open: true,
    id,
    name: meal?.name ?? '',
    target: meal?.kcal_target ?? '',
  }
  actionError.value = null
}

const mealNameValid = computed(
  () => mealForm.value.name.trim().length > 0 && mealForm.value.name.trim().length <= 100,
)
const mealTargetValid = computed(
  () =>
    mealForm.value.target.trim() === '' ||
    (isValidDecimal(mealForm.value.target, { decimalPlaces: 0, positive: true }) &&
      normalizeDecimalInput(mealForm.value.target).replace(/^0+/, '').length <= 5),
)

const saveMeal = useMutation({
  mutationFn: () => {
    const target =
      mealForm.value.target.trim() === '' ? null : normalizeDecimalInput(mealForm.value.target)
    if (mealForm.value.id === null) {
      return createMeal(currentDate.value, {
        name: mealForm.value.name.trim(),
        kcal_target: target,
      })
    }
    return updateMeal(mealForm.value.id, {
      name: mealForm.value.name.trim(),
      kcal_target: target,
      clear_kcal_target: target === null,
    })
  },
  onSuccess: async () => {
    mealForm.value.open = false
    await refresh()
  },
  onError: reportError,
})

const removeMeal = useMutation({
  mutationFn: (mealId: number) => deleteMeal(mealId),
  onSuccess: refresh,
  onError: reportError,
})

const duplicateMeal = useMutation({
  mutationFn: (mealId: number) =>
    copyPlan({ what: 'meal', source_meal_id: mealId, target_dates: [currentDate.value] }),
  onSuccess: refresh,
  onError: reportError,
})

const changeServings = useMutation({
  mutationFn: (payload: { itemId: number; servings: string }) =>
    updateItem(payload.itemId, { servings: payload.servings }),
  onSuccess: refresh,
  onError: reportError,
})

const removeItem = useMutation({
  mutationFn: (itemId: number) => deleteItem(itemId),
  onSuccess: refresh,
  onError: reportError,
})

/** Destrukcja zawsze z potwierdzeniem (06_UIUX §3.3) — dialog woła skrypt, nie szablon. */
function confirmRemoveMeal(mealId: number): void {
  if (window.confirm(texts.confirmMealDelete)) {
    removeMeal.mutate(mealId)
  }
}

function confirmRemoveItem(itemId: number): void {
  if (window.confirm(texts.confirmItemDelete)) {
    removeItem.mutate(itemId)
  }
}

// --- wspólny panel dania i zachowana ścieżka produktów luzem -----------------------
const planningOpen = ref(false)
const planningMealId = ref<number | null>(null)
const replaceItemId = ref<number | null>(null)
const planningMeal = computed(
  () => day.value.meals.find((meal) => meal.id === planningMealId.value) ?? null,
)
const replacement = computed(
  () => planningMeal.value?.items.find((item) => item.id === replaceItemId.value) ?? null,
)
const successMessage = ref<string | null>(null)
function openRecipePanel(mealId: number | null = null): void {
  planningMealId.value = mealId
  replaceItemId.value = null
  planningOpen.value = true
  successMessage.value = null
}
function openReplacement(itemId: number): void {
  planningMealId.value =
    day.value.meals.find((meal) => meal.items.some((item) => item.id === itemId))?.id ?? null
  replaceItemId.value = itemId
  planningOpen.value = true
  successMessage.value = null
}
async function recipeSaved(result: { day: PlanDay; mode: 'add' | 'replace' }): Promise<void> {
  planningOpen.value = false
  if (result.day.day !== currentDate.value) {
    await goTo(result.day.day)
    // Zmiana daty najpierw sprząta stan poprzedniego dnia, w tym jego komunikaty.
    await nextTick()
  }
  if (currentDate.value !== result.day.day) return
  successMessage.value =
    result.mode === 'add'
      ? 'Danie dodane do planu.'
      : 'Danie zamienione. Porcje zapisane zgodnie z wyborem.'
  actionError.value = null
}
const itemForm = ref<{
  open: boolean
  mealId: number | null
  product: Product | ProductDetail | null
  quantity: string | null
  unit: string
}>({ open: false, mealId: null, product: null, quantity: null, unit: 'g' })
const amountValid = ref(false)
function openItemForm(mealId: number): void {
  itemForm.value = { open: true, mealId, product: null, quantity: null, unit: 'g' }
  amountValid.value = false
  actionError.value = null
}
const itemValid = computed(() => itemForm.value.product !== null && amountValid.value)
const saveItem = useMutation({
  mutationFn: () =>
    addItem(itemForm.value.mealId as number, {
      product_id: itemForm.value.product?.id ?? 0,
      quantity: itemForm.value.quantity ?? '0',
      unit: itemForm.value.unit,
      servings: '1',
    }),
  onSuccess: async () => {
    itemForm.value.open = false
    await refresh()
  },
  onError: reportError,
})

// --- rozkład rodzinny --------------------------------------------------------------

const splitItemId = ref<number | null>(null)

const saveSplit = useMutation({
  mutationFn: (payload: { itemId: number; split: PlanServingSplitInput[]; servings: string }) =>
    updateItem(payload.itemId, {
      servings: payload.servings,
      servings_split: payload.split,
    }),
  onSuccess: async () => {
    splitItemId.value = null
    await refresh()
  },
  onError: reportError,
})

const clearSplit = useMutation({
  mutationFn: (itemId: number) => updateItem(itemId, { servings_split: [] }),
  onSuccess: async () => {
    splitItemId.value = null
    await refresh()
  },
  onError: reportError,
})

// --- dopasuj porcję do celu ---------------------------------------------------------

const proposal = ref<FitToTarget | null>(null)

const askFit = useMutation({
  mutationFn: (itemId: number) => fitItemToTarget(itemId),
  onSuccess: (result) => {
    actionError.value = null
    proposal.value = result
  },
  onError: reportError,
})

const applyFit = useMutation({
  mutationFn: (payload: { itemId: number; servings: string }) =>
    updateItem(payload.itemId, { servings: payload.servings }),
  onSuccess: async () => {
    proposal.value = null
    await refresh()
  },
  onError: reportError,
})

// --- kopiowanie dnia -----------------------------------------------------------------

const copyForm = ref<{ open: boolean; dates: string }>({ open: false, dates: '' })

const copyDay = useMutation({
  mutationFn: () =>
    copyPlan({
      what: 'day',
      source_date: currentDate.value,
      target_dates: copyForm.value.dates
        .split(/[\s,;]+/)
        .map((value) => value.trim())
        .filter((value) => value.length > 0),
    }),
  onSuccess: async () => {
    copyForm.value = { open: false, dates: '' }
    await refresh()
  },
  onError: reportError,
})

// Zmiana daty zamyka wszystko, co dotyczyło poprzedniego dnia.
watch(currentDate, () => {
  planningOpen.value = false
  successMessage.value = null
  mealForm.value.open = false
  itemForm.value.open = false
  splitItemId.value = null
  proposal.value = null
  copyForm.value = { open: false, dates: '' }
  actionError.value = null
})

const isMutating = computed(
  () =>
    saveMeal.isPending.value ||
    removeMeal.isPending.value ||
    duplicateMeal.isPending.value ||
    changeServings.isPending.value ||
    removeItem.isPending.value ||
    saveItem.isPending.value ||
    saveSplit.isPending.value ||
    clearSplit.isPending.value ||
    applyFit.isPending.value ||
    copyDay.isPending.value,
)
</script>

<template>
  <section class="grid gap-4" data-testid="plan-dnia-page">
    <PageHeader
      :title="currentDate === isoDate(new Date()) ? 'Dzisiaj jemy' : 'Plan posiłków'"
      title-testid="plan-heading"
      decoration="plate"
    >
      <template #actions>
        <Button
          variant="outline"
          class="min-h-11 min-w-11"
          :aria-label="texts.previousDay"
          data-testid="plan-prev-day"
          @click="goTo(addDays(currentDate, -1))"
        >
          <ChevronLeft class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="outline"
          class="min-h-11"
          data-testid="plan-today"
          @click="goTo(isoDate(new Date()))"
        >
          {{ texts.today }}
        </Button>
        <Button
          variant="outline"
          class="min-h-11 min-w-11"
          :aria-label="texts.nextDay"
          data-testid="plan-next-day"
          @click="goTo(addDays(currentDate, 1))"
        >
          <ChevronRight class="size-4" aria-hidden="true" />
        </Button>
      </template>

      <p v-if="day.title" class="text-muted-foreground text-sm">{{ day.title }}</p>
      <p class="text-muted-foreground text-sm" data-testid="plan-date">{{ currentDate }}</p>
    </PageHeader>

    <p v-if="actionError" class="text-destructive text-sm" role="alert" data-testid="plan-error">
      {{ actionError }}
    </p>

    <p v-if="successMessage" role="status" class="text-primary text-sm" data-testid="plan-success">
      {{ successMessage }}
    </p>
    <nav
      class="day-week-strip grid gap-0.5 rounded-xl bg-muted p-1"
      aria-label="Wybierz dzień tygodnia"
      data-testid="plan-week"
    >
      <button
        v-for="entry in week"
        :key="entry.date"
        type="button"
        class="grid min-h-14 min-w-11 justify-items-center rounded-lg px-1 py-2 text-sm"
        :class="
          entry.isCurrent
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-accent'
        "
        :aria-current="entry.isCurrent ? 'date' : undefined"
        :aria-label="`Pokaż plan na ${entry.date}`"
        :data-testid="`week-day-${entry.date}`"
        @click="goTo(entry.date)"
      >
        <span>{{ entry.label }}</span
        ><strong>{{ entry.date.slice(-2) }}</strong>
      </button>
    </nav>
    <p
      v-if="days.isPending.value"
      role="status"
      class="text-muted-foreground text-sm"
      data-testid="plan-loading"
    >
      {{ common.loading }}
    </p>
    <div
      v-else-if="days.isError.value && !days.data.value"
      role="alert"
      class="border-border bg-card grid gap-3 rounded-xl border p-6"
      data-testid="plan-load-error"
    >
      <h2 class="text-lg font-medium">Nie udało się pobrać planu</h2>
      <p>Nie możemy teraz sprawdzić zaplanowanych dań.</p>
      <Button variant="outline" class="justify-self-start" @click="days.refetch()"
        >Spróbuj ponownie</Button
      >
    </div>
    <template v-else-if="days.data.value">
      <div
        v-if="days.isError.value"
        role="alert"
        class="text-warning flex flex-wrap items-center gap-2 text-sm"
        data-testid="plan-refetch-error"
      >
        Nie udało się odświeżyć planu. Pokazujemy ostatnio pobrane dane.
        <Button variant="outline" @click="days.refetch()">Ponów odczyt</Button>
      </div>
      <Button
        v-if="day.meals.length"
        class="justify-self-start"
        data-testid="plan-add-recipe"
        @click="openRecipePanel()"
        ><Plus class="size-4" aria-hidden="true" />Dodaj danie</Button
      >
      <div class="grid gap-6">
        <div class="grid gap-3">
          <EmptyState
            v-if="day.meals.length === 0"
            title="Co zjemy tego dnia?"
            :description="texts.emptyDay"
            data-testid="plan-empty"
          >
            <template #action
              ><Button data-testid="plan-add-recipe" @click="openRecipePanel()"
                >Wybierz pierwsze danie</Button
              ></template
            >
          </EmptyState>

          <MealCard
            v-for="meal in day.meals"
            :key="meal.id"
            :meal="meal"
            :pending="isMutating"
            @add-item="openRecipePanel"
            @add-product="openItemForm"
            @replace-item="openReplacement"
            @edit="openMealForm"
            @duplicate="duplicateMeal.mutate($event)"
            @remove="confirmRemoveMeal"
            @change-servings="changeServings.mutate($event)"
            @open-split="splitItemId = $event"
            @fit-to-target="askFit.mutate($event)"
            @remove-item="confirmRemoveItem"
          >
            <template #item-extra="{ item }">
              <ServingsSplitDrawer
                v-if="splitItemId === item.id"
                :open="true"
                :profiles="profiles"
                :split="item.servings_split"
                :servings="item.servings"
                :pending="isMutating"
                :profiles-error="profilesQuery.isError.value"
                :profiles-pending="profilesQuery.isFetching.value"
                @retry="profilesQuery.refetch()"
                @apply="(split, servings) => saveSplit.mutate({ itemId: item.id, split, servings })"
                @clear="clearSplit.mutate(item.id)"
                @close="splitItemId = null"
              />
            </template>
          </MealCard>

          <!-- FAB „+" na mobile, zwykłe przyciski na desktopie (06_UIUX §4.1). -->
          <div class="flex flex-wrap gap-2">
            <Button class="min-h-11" data-testid="plan-add-meal" @click="openMealForm(null)">
              <Plus class="size-4" aria-hidden="true" />
              {{ texts.addMeal }}
            </Button>
            <Button
              v-if="day.meals.length > 0"
              variant="outline"
              class="min-h-11"
              data-testid="plan-copy-open"
              @click="copyForm.open = !copyForm.open"
            >
              <CalendarPlus class="size-4" aria-hidden="true" />
              {{ texts.copyDay }}
            </Button>
          </div>

          <!-- Formularz posiłku (dodawanie i edycja w miejscu — 06_UIUX §2). -->
          <form
            v-if="mealForm.open"
            class="border-border bg-card grid gap-3 rounded-xl border p-3 md:grid-cols-2 md:items-end"
            data-testid="meal-form"
            @submit.prevent="saveMeal.mutate()"
          >
            <div class="grid gap-2">
              <label class="text-sm font-medium" for="meal-name">{{ texts.mealNameLabel }}</label>
              <Input
                id="meal-name"
                v-model="mealForm.name"
                maxlength="100"
                required
                class="min-h-11"
                data-testid="meal-name-input"
              />
            </div>
            <div class="grid gap-2">
              <label class="text-sm font-medium" for="meal-target">
                {{ texts.mealTargetLabel }}
              </label>
              <Input
                id="meal-target"
                v-model="mealForm.target"
                inputmode="numeric"
                class="min-h-11 tabular-nums"
                data-testid="meal-target-input"
              />
              <p
                class="text-xs"
                :class="mealTargetValid ? 'text-muted-foreground' : 'text-destructive'"
              >
                {{ texts.mealTargetHint }}
              </p>
            </div>
            <div class="flex gap-2 md:col-span-2">
              <Button
                type="submit"
                class="min-h-11"
                :disabled="!mealNameValid || !mealTargetValid || saveMeal.isPending.value"
                data-testid="meal-submit"
              >
                {{ common.save }}
              </Button>
              <Button
                type="button"
                variant="ghost"
                class="min-h-11"
                data-testid="meal-cancel"
                @click="mealForm.open = false"
              >
                {{ common.cancel }}
              </Button>
            </div>
          </form>

          <!-- Picker ma własny formularz; form= wiąże zewnętrzną akcję bez zagnieżdżania. -->
          <div
            v-if="itemForm.open"
            class="border-border bg-card grid gap-3 rounded-xl border p-4"
            data-testid="item-form"
          >
            <h3 class="font-medium">Dodaj produkt luzem</h3>
            <form
              id="loose-item-form"
              @submit.prevent="itemValid && !saveItem.isPending.value && saveItem.mutate()"
            />
            <ProductPicker v-model="itemForm.product" :disabled="saveItem.isPending.value" />
            <AmountInput
              v-model="itemForm.quantity"
              form="loose-item-form"
              :unit="itemForm.unit"
              :units="['g', 'kg', 'ml', 'l', 'szt.']"
              :decimal-places="3"
              required
              testid="item-amount"
              @update:unit="itemForm.unit = $event"
              @update:valid="amountValid = $event"
            />
            <div class="flex gap-2">
              <Button
                type="submit"
                form="loose-item-form"
                :disabled="!itemValid || saveItem.isPending.value"
                data-testid="item-submit"
                >{{ common.add }}</Button
              >
              <Button
                type="button"
                variant="ghost"
                :disabled="saveItem.isPending.value"
                data-testid="item-cancel"
                @click="itemForm.open = false"
                >{{ common.cancel }}</Button
              >
            </div>
          </div>

          <!-- Kopiowanie dnia na inne daty (dopisuje, nie nadpisuje). -->
          <form
            v-if="copyForm.open"
            class="border-border bg-card grid gap-3 rounded-xl border p-3"
            data-testid="copy-form"
            @submit.prevent="copyDay.mutate()"
          >
            <div class="grid gap-1">
              <h3 class="text-sm font-medium">{{ texts.copyDayTitle }}</h3>
              <p class="text-muted-foreground text-xs">{{ texts.copyDaySubtitle }}</p>
            </div>
            <label class="text-sm font-medium" for="copy-dates">{{ texts.copyDayDates }}</label>
            <textarea
              id="copy-dates"
              v-model="copyForm.dates"
              rows="3"
              class="border-border bg-card min-h-11 rounded-lg border p-2 text-sm tabular-nums"
              placeholder="2026-08-19&#10;2026-08-20"
              data-testid="copy-dates"
            ></textarea>
            <div class="flex gap-2">
              <Button
                type="submit"
                class="min-h-11"
                :disabled="copyForm.dates.trim() === '' || copyDay.isPending.value"
                data-testid="copy-submit"
              >
                {{ texts.copyDayApply }}
              </Button>
              <Button
                type="button"
                variant="ghost"
                class="min-h-11"
                data-testid="copy-cancel"
                @click="copyForm.open = false"
              >
                {{ common.cancel }}
              </Button>
            </div>
          </form>

          <!-- Propozycja „dopasuj porcję do celu": zapis dopiero po Zastosuj. -->
          <div
            v-if="proposal"
            class="border-border bg-card grid gap-2 rounded-xl border p-3"
            role="dialog"
            :aria-label="texts.fitDialogTitle"
            data-testid="fit-dialog"
          >
            <h3 class="text-sm font-medium">{{ texts.fitDialogTitle }}</h3>
            <p class="text-sm tabular-nums">
              {{ texts.fitProposal }}:
              <strong data-testid="fit-proposed">
                {{ formatDecimal(proposal.proposed_servings) }}
              </strong>
            </p>
            <p class="text-muted-foreground text-sm tabular-nums">
              {{ texts.fitResult }}: {{ formatDecimal(proposal.resulting_nutrition.kcal) }}
              {{ recipeTexts.kcalUnit }} / {{ formatDecimal(proposal.target_kcal) }}
              {{ recipeTexts.kcalUnit }}
            </p>
            <div class="flex gap-2">
              <Button
                class="min-h-11"
                :disabled="applyFit.isPending.value"
                data-testid="fit-apply"
                @click="
                  applyFit.mutate({
                    itemId: proposal.item_id,
                    servings: proposal.proposed_servings,
                  })
                "
              >
                {{ texts.fitApply }}
              </Button>
              <Button
                variant="ghost"
                class="min-h-11"
                data-testid="fit-cancel"
                @click="proposal = null"
              >
                {{ common.cancel }}
              </Button>
            </div>
          </div>
        </div>

        <section
          v-if="day.meals.length"
          class="border-border bg-card grid gap-3 rounded-xl border p-4 sm:p-6"
          aria-label="Cały plan"
          data-testid="plan-summary"
        >
          <h2 class="font-medium">
            Cały plan
            <span class="text-muted-foreground text-sm font-normal">· zaplanowane jedzenie</span>
          </h2>
          <p class="text-muted-foreground text-sm">
            Suma wszystkich porcji. To wartości planu, nie bilans spożycia jednej osoby.
          </p>
          <ul class="day-summary-tiles grid gap-3" data-testid="plan-tiles">
            <li
              v-for="metric in [
                ['kcal', 'Kalorie', 'kcal'],
                ['protein_g', 'Białko', 'g'],
                ['fat_g', 'Tłuszcze', 'g'],
                ['carbs_g', 'Węglowodany', 'g'],
              ] as const"
              :key="metric[0]"
              :data-testid="`plan-tile-${metric[0]}`"
            >
              <span class="text-muted-foreground block text-xs">{{ metric[1] }}</span>
              <strong class="tabular-nums"
                >{{ formatDecimal(day.nutrition[metric[0]]) }} {{ metric[2] }}</strong
              >
            </li>
          </ul>
          <p
            v-if="!day.nutrition.complete"
            class="text-warning text-sm"
            data-testid="plan-incomplete"
          >
            Niepełne dane odżywcze: {{ day.nutrition.missing.join(', ') }}
          </p>
        </section>
      </div>
    </template>
    <RecipePlanningPanel
      :open="planningOpen"
      :recipe="null"
      :date="currentDate"
      :meal="planningMeal"
      :replace-item="replacement"
      @close="planningOpen = false"
      @saved="recipeSaved"
    />
  </section>
</template>

<style scoped>
.day-week-strip {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 3rem), 1fr));
}

.day-summary-tiles {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 7rem), 1fr));
}
</style>
