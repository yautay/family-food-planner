<script setup lang="ts">
/**
 * Plan dnia — widok 1 wizualizacji (06_UIUX §4.1), trasa `/plan-dnia/:date?`.
 *
 * Układ: nagłówek z nawigacją dat → cztery kafelki wartość/cel/delta/status →
 * karty posiłków z pozycjami → panel boczny (donut makro + mini-słupki tygodnia).
 * Na telefonie panel schodzi pod listę; kolejność treści jest ta sama.
 *
 * Stan serwera trzyma WYŁĄCZNIE TanStack Query (ADR-007) — komponent nie kopiuje
 * dnia do własnych ref-ów. Ref-y opisują tylko intencje UI (otwarty formularz,
 * wybrana pozycja, treść dialogu). Każda mutacja zwraca cały dzień, ale i tak
 * unieważniamy zakres tygodnia, bo panel boczny pokazuje sąsiednie dni.
 *
 * Żadna wartość odżywcza nie jest tu liczona: wszystko przychodzi z backendu
 * jako stringi dziesiętne (ADR-008), a strona tylko formatuje.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { CalendarPlus, ChevronLeft, ChevronRight, Plus } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
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
import type { RecipeSummary } from '@/api/recipes'
import DonutChart from '@/components/charts/DonutChart.vue'
import NutritionBar from '@/components/charts/NutritionBar.vue'
import AmountInput from '@/components/domain/AmountInput.vue'
import MealCard from '@/components/domain/MealCard.vue'
import PageHeader from '@/components/domain/PageHeader.vue'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import RecipePicker from '@/components/domain/RecipePicker.vue'
import ServingsSplitDrawer from '@/components/domain/ServingsSplitDrawer.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { addDays, isoDate, startOfWeek, weekDayLabel } from '@/lib/dates'
import { isValidDecimal, normalizeDecimalInput } from '@/lib/decimal'
import { formatDecimal } from '@/lib/format'
import { statusLabel, statusToken } from '@/lib/nutrition'
import { common, plan as texts, recipes as recipeTexts } from '@/lib/texts'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

/** Data z trasy; brak parametru = dziś (najczęstszy przypadek otwarcia planu). */
const currentDate = computed(() => {
  const param = route.params.date
  const value = Array.isArray(param) ? param[0] : param
  return typeof value === 'string' && value.length > 0 ? value : isoDate(new Date())
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

const tiles = computed(() => [
  {
    key: 'kcal',
    label: texts.tileKcal,
    unit: recipeTexts.kcalUnit,
    metric: day.value.goal_progress.kcal,
  },
  {
    key: 'protein_g',
    label: texts.tileProtein,
    unit: 'g',
    metric: day.value.goal_progress.protein_g,
  },
  { key: 'fat_g', label: texts.tileFat, unit: 'g', metric: day.value.goal_progress.fat_g },
  { key: 'carbs_g', label: texts.tileCarbs, unit: 'g', metric: day.value.goal_progress.carbs_g },
])

const macroSegments = computed(() => [
  {
    label: texts.tileProtein,
    value: day.value.nutrition.protein_g,
    colorClass: 'stroke-secondary',
  },
  { label: texts.tileFat, value: day.value.nutrition.fat_g, colorClass: 'stroke-warning' },
  { label: texts.tileCarbs, value: day.value.nutrition.carbs_g, colorClass: 'stroke-primary' },
])

const week = computed(() =>
  Array.from({ length: 7 }, (_value, index) => {
    const date = addDays(weekStart.value, index)
    const entry = days.data.value?.items.find((item) => item.day === date)
    return {
      date,
      label: weekDayLabel(date),
      kcal: entry?.nutrition.kcal ?? '0',
      target: entry?.goal_progress.kcal.target ?? null,
      status: entry?.goal_progress.kcal.status ?? null,
      isCurrent: date === currentDate.value,
    }
  }),
)

function goTo(date: string): void {
  void router.push({ name: 'plan-dnia', params: { date } })
}

// --- mutacje ---------------------------------------------------------------------

const actionError = ref<string | null>(null)

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  actionError.value = null
  await queryClient.invalidateQueries({ queryKey: queryKeys.planDays.all })
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

const mealNameValid = computed(() => mealForm.value.name.trim().length > 0)
const mealTargetValid = computed(
  () =>
    mealForm.value.target.trim() === '' ||
    isValidDecimal(mealForm.value.target, { decimalPlaces: 0, positive: true }),
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

// --- dodawanie pozycji ------------------------------------------------------------

const itemForm = ref<{
  open: boolean
  mealId: number | null
  mode: 'recipe' | 'product'
  recipe: RecipeSummary | null
  product: Product | ProductDetail | null
  quantity: string | null
  unit: string
  servings: string
}>({
  open: false,
  mealId: null,
  mode: 'recipe',
  recipe: null,
  product: null,
  quantity: null,
  unit: 'g',
  servings: '1',
})

function openItemForm(mealId: number): void {
  itemForm.value = {
    open: true,
    mealId,
    mode: 'recipe',
    recipe: null,
    product: null,
    quantity: null,
    unit: 'g',
    servings: '1',
  }
  actionError.value = null
}

const itemValid = computed(() => {
  if (itemForm.value.mode === 'recipe') {
    return itemForm.value.recipe !== null
  }
  return itemForm.value.product !== null && (itemForm.value.quantity ?? '').length > 0
})

const saveItem = useMutation({
  mutationFn: () => {
    const mealId = itemForm.value.mealId as number
    if (itemForm.value.mode === 'recipe') {
      return addItem(mealId, {
        recipe_id: itemForm.value.recipe?.id ?? 0,
        servings: normalizeDecimalInput(itemForm.value.servings || '1'),
      })
    }
    // Produkt luzem ma jedną porcję: „ile" opisuje ilość, nie mnożnik.
    return addItem(mealId, {
      product_id: itemForm.value.product?.id ?? 0,
      quantity: itemForm.value.quantity ?? '0',
      unit: itemForm.value.unit,
      servings: '1',
    })
  },
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
      :title="`${texts.title} — ${currentDate}`"
      title-testid="plan-date"
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
      <p
        v-if="day.goal_valid_from === null"
        class="text-muted-foreground text-sm"
        data-testid="plan-no-goal"
      >
        {{ texts.goalsMissing }}
      </p>
    </PageHeader>

    <p v-if="actionError" class="text-destructive text-sm" role="alert" data-testid="plan-error">
      {{ actionError }}
    </p>

    <p v-if="days.isPending.value" class="text-muted-foreground text-sm">{{ common.loading }}</p>

    <template v-else>
      <!-- Kafelki: wartość / cel / delta / status słowny (06_UIUX §3.5). -->
      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="plan-tiles">
        <li
          v-for="tile in tiles"
          :key="tile.key"
          class="border-border bg-card grid gap-2 rounded-xl border p-3 shadow-sm"
          :data-testid="`plan-tile-${tile.key}`"
        >
          <p class="text-muted-foreground text-sm">{{ tile.label }}</p>
          <p class="text-xl font-semibold tabular-nums">
            {{ formatDecimal(tile.metric.value) }}
            <span class="text-muted-foreground text-sm font-normal">
              /
              {{ tile.metric.target === null ? texts.noTarget : formatDecimal(tile.metric.target) }}
              {{ tile.unit }}
            </span>
          </p>
          <NutritionBar
            :label="tile.label"
            :value="tile.metric.value"
            :target="tile.metric.target"
            :status="tile.metric.status"
            :unit="tile.unit"
            :testid="`plan-bar-${tile.key}`"
          />
          <p class="text-sm tabular-nums">
            <span v-if="tile.metric.delta !== null" class="text-muted-foreground">
              {{ formatDecimal(tile.metric.delta) }} {{ tile.unit }}
            </span>
            <span
              v-if="tile.metric.status"
              :class="statusToken(tile.metric.status).text"
              :data-testid="`plan-status-${tile.key}`"
            >
              <span aria-hidden="true"> · </span>{{ statusLabel(tile.metric.status) }}
            </span>
          </p>
        </li>
      </ul>

      <div class="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div class="grid gap-3">
          <p
            v-if="day.meals.length === 0"
            class="text-muted-foreground text-sm"
            data-testid="plan-empty"
          >
            {{ texts.emptyDay }}
          </p>

          <MealCard
            v-for="meal in day.meals"
            :key="meal.id"
            :meal="meal"
            :pending="isMutating"
            @add-item="openItemForm"
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

          <!-- Dodawanie pozycji: przepis (RecipePicker) albo produkt luzem. -->
          <form
            v-if="itemForm.open"
            class="border-border bg-card grid gap-3 rounded-xl border p-3"
            data-testid="item-form"
            @submit.prevent="saveItem.mutate()"
          >
            <div class="flex gap-2">
              <Button
                type="button"
                :variant="itemForm.mode === 'recipe' ? 'default' : 'outline'"
                class="min-h-11"
                data-testid="item-mode-recipe"
                @click="itemForm.mode = 'recipe'"
              >
                {{ recipeTexts.title }}
              </Button>
              <Button
                type="button"
                :variant="itemForm.mode === 'product' ? 'default' : 'outline'"
                class="min-h-11"
                data-testid="item-mode-product"
                @click="itemForm.mode = 'product'"
              >
                {{ texts.productItem }}
              </Button>
            </div>

            <template v-if="itemForm.mode === 'recipe'">
              <RecipePicker v-model="itemForm.recipe" />
              <div class="grid gap-2">
                <label class="text-sm font-medium" for="item-servings">
                  {{ texts.servingsLabel }}
                </label>
                <Input
                  id="item-servings"
                  v-model="itemForm.servings"
                  inputmode="decimal"
                  class="min-h-11 tabular-nums"
                  data-testid="item-servings-input"
                />
              </div>
            </template>

            <template v-else>
              <ProductPicker v-model="itemForm.product" />
              <AmountInput
                v-model="itemForm.quantity"
                :unit="itemForm.unit"
                :units="['g', 'kg', 'ml', 'l', 'szt.']"
                :decimal-places="3"
                required
                testid="item-amount"
                @update:unit="itemForm.unit = $event"
              />
            </template>

            <div class="flex gap-2">
              <Button
                type="submit"
                class="min-h-11"
                :disabled="!itemValid || saveItem.isPending.value"
                data-testid="item-submit"
              >
                {{ common.add }}
              </Button>
              <Button
                type="button"
                variant="ghost"
                class="min-h-11"
                data-testid="item-cancel"
                @click="itemForm.open = false"
              >
                {{ common.cancel }}
              </Button>
            </div>
          </form>

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

        <!-- Panel boczny: donut makro + mini-słupki tygodnia (ten sam fetch). -->
        <aside class="grid gap-4" data-testid="plan-side-panel">
          <Card class="rounded-xl">
            <CardHeader>
              <CardTitle class="text-base">{{ texts.macroTitle }}</CardTitle>
            </CardHeader>
            <CardContent>
              <DonutChart
                :segments="macroSegments"
                :center-value="formatDecimal(day.nutrition.kcal)"
                :center-label="recipeTexts.kcalUnit"
                :title="texts.macroTitle"
                testid="plan-donut"
              />
            </CardContent>
          </Card>

          <Card class="rounded-xl">
            <CardHeader>
              <CardTitle class="text-base">{{ texts.weekTitle }}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul class="grid grid-cols-7 gap-1" data-testid="plan-week">
                <li v-for="entry in week" :key="entry.date" class="grid justify-items-center gap-1">
                  <div class="h-24 w-4">
                    <NutritionBar
                      :label="`${entry.label} ${entry.date}`"
                      :value="entry.kcal"
                      :target="entry.target"
                      :status="entry.status"
                      unit="kcal"
                      orientation="vertical"
                      :testid="`week-bar-${entry.date}`"
                    />
                  </div>
                  <button
                    type="button"
                    class="min-h-11 text-xs"
                    :class="
                      entry.isCurrent ? 'text-primary font-semibold' : 'text-muted-foreground'
                    "
                    :aria-label="`Pokaż plan na ${entry.date}`"
                    :data-testid="`week-day-${entry.date}`"
                    @click="goTo(entry.date)"
                  >
                    {{ entry.label }}
                  </button>
                </li>
              </ul>
              <p class="text-muted-foreground mt-2 text-xs">{{ texts.weekSubtitle }}</p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </template>
  </section>
</template>
