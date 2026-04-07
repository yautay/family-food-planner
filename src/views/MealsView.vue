<template>
  <section v-if="!isAuthenticated" class="surface-card">
    <h1 class="title is-4">{{ t('meals.authTitle') }}</h1>
    <p class="muted">{{ t('common.requiredAuth') }}</p>
    <RouterLink to="/login">{{ t('common.goToLogin') }}</RouterLink>
  </section>

  <section v-else class="planner-layout">
    <article class="surface-card section-stack">
      <h1 class="title is-4">{{ t('meals.planningTitle') }}</h1>
      <p class="muted">{{ t('meals.planningDescription') }}</p>
    </article>

    <div class="top-grid">
      <article class="surface-card section-stack">
        <div class="section-header">
          <h2 class="title is-5">{{ t('meals.plansListTitle') }}</h2>
          <input
            v-model="mealPlanSearch"
            class="input"
            :placeholder="t('catalog.searchRecipe')"
            type="text"
          />
        </div>

        <ul class="list">
          <li
            v-for="plan in visibleMealPlans"
            :key="plan.id"
            :class="{ 'is-active-row': plan.id === selectedMealPlanId }"
          >
            <button class="link" type="button" @click="selectMealPlan(plan.id)">
              {{ plan.name }}
            </button>
            <span class="muted"
              >{{ plan.start_date }} - {{ plan.end_date }} | {{ t('meals.portionsCount') }}:
              {{ plan.portions_count }}</span
            >
          </li>
        </ul>

        <form class="form-grid" @submit.prevent="saveMealPlan">
          <h3 class="title is-5">
            {{ editingMealPlanId ? t('meals.editPlanTitle') : t('meals.newPlanTitle') }}
          </h3>

          <label>
            {{ t('meals.name') }}
            <input v-model="mealPlanForm.name" class="input" required />
          </label>

          <div class="grid-two">
            <label>
              {{ t('meals.dateFrom') }}
              <input v-model="mealPlanForm.start_date" class="input" type="date" required />
            </label>

            <label>
              {{ t('meals.dateTo') }}
              <input v-model="mealPlanForm.end_date" class="input" type="date" required />
            </label>
          </div>

          <label>
            {{ t('meals.portionsCount') }}
            <input
              v-model="mealPlanForm.portions_count"
              class="input"
              type="number"
              min="1"
              step="1"
              required
            />
          </label>

          <label>
            {{ t('meals.note') }}
            <textarea v-model="mealPlanForm.note" class="textarea" rows="3"></textarea>
          </label>

          <p v-if="mealPlanMessage" class="success-message">{{ mealPlanMessage }}</p>
          <p v-if="mealPlanError" class="error-message">{{ mealPlanError }}</p>

          <div class="actions-row">
            <button class="button is-primary" type="submit">
              {{ editingMealPlanId ? t('meals.savePlan') : t('meals.addPlan') }}
            </button>
            <button class="button" type="button" @click="resetMealPlanForm">
              {{ t('common.reset') }}
            </button>
            <button v-if="editingMealPlanId" class="button" type="button" @click="removeMealPlan">
              {{ t('meals.removePlan') }}
            </button>
          </div>
        </form>
      </article>

      <article v-if="activeMealPlan" class="surface-card section-stack">
        <h2 class="title is-5">{{ t('meals.mealSlotsTitle') }}</h2>

        <ul class="list">
          <li v-for="(slot, index) in mealSlotsDraft" :key="`slot-${index}`" class="slot-row">
            <input v-model="slot.slot_name" class="input" :placeholder="t('meals.mealSlotName')" />
            <input v-model="slot.slot_time" class="input" type="time" />
            <button
              class="button is-small"
              type="button"
              :disabled="mealSlotsDraft.length <= 1"
              @click="removeMealSlot(index)"
            >
              {{ t('common.delete') }}
            </button>
          </li>
        </ul>

        <div class="actions-row">
          <button class="button is-small" type="button" @click="addMealSlot">
            {{ t('meals.addMealSlot') }}
          </button>
          <button class="button is-primary is-small" type="button" @click="saveMealSlots">
            {{ t('meals.saveMealSlots') }}
          </button>
        </div>
      </article>
    </div>

    <article v-if="activeMealPlan" class="surface-card section-stack plan-days-block">
      <div class="block-header">
        <h2 class="title is-5">{{ t('meals.daySlotsTitle') }}</h2>
      </div>

      <div class="matrix-wrapper">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>{{ t('meals.mealSlotName') }}</th>
              <th
                v-for="daySlot in activeMealPlan.day_slots"
                :key="`head-${daySlot.planned_date}`"
                :class="{ 'is-selected-column': daySlot.planned_date === selectedDaySlotDate }"
              >
                <button
                  class="matrix-day-button"
                  type="button"
                  @click="selectDaySlot(daySlot.planned_date)"
                >
                  {{ daySlot.planned_date }}
                </button>
                <p class="matrix-day-title muted">{{ matrixDayTitle(daySlot) }}</p>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(mealSlot, rowIndex) in mealSlotRows"
              :key="`row-${mealSlot.id ?? rowIndex}`"
            >
              <th class="matrix-slot-cell">
                <div class="matrix-slot-title">
                  <strong>{{ mealSlot.slot_name }}</strong>
                  <SlotTimeClock
                    v-if="mealSlot.slot_time"
                    class="slot-clock-cell"
                    :time="mealSlot.slot_time"
                    :size="24"
                  />
                </div>
              </th>
              <td
                v-for="daySlot in activeMealPlan.day_slots"
                :key="`cell-${daySlot.planned_date}-${mealSlot.id ?? rowIndex}`"
                :class="{ 'is-selected-column': daySlot.planned_date === selectedDaySlotDate }"
              >
                <button
                  class="matrix-cell-button"
                  type="button"
                  @click="selectDaySlot(daySlot.planned_date)"
                >
                  <span>{{ matrixMealName(daySlot, rowIndex) }}</span>
                  <span v-if="matrixMealServings(daySlot, rowIndex)" class="muted">
                    {{ matrixMealServings(daySlot, rowIndex) }}
                  </span>
                </button>
              </td>
            </tr>

            <tr class="matrix-day-summary-row">
              <th class="matrix-slot-cell">{{ t('meals.dayTotalsTitle') }}</th>
              <td
                v-for="daySlot in activeMealPlan.day_slots"
                :key="`summary-${daySlot.planned_date}`"
                :class="{ 'is-selected-column': daySlot.planned_date === selectedDaySlotDate }"
              >
                <p class="matrix-day-summary-text">{{ daySummaryLineOne(daySlot.totals ?? {}) }}</p>
                <p class="matrix-day-summary-text">{{ daySummaryLineTwo(daySlot.totals ?? {}) }}</p>
                <p class="matrix-day-summary-text">
                  {{ daySummaryLineThree(daySlot.totals ?? {}) }}
                </p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="plan-break" aria-hidden="true">*</div>

      <div v-if="selectedDaySlot" class="day-slot-card is-custom-card">
        <div class="day-slot-header">
          <div class="date-meta">
            <h3 class="title is-6">{{ selectedDaySlot.planned_date }}</h3>
          </div>

          <label>
            {{ t('meals.dayTitleLabel') }}
            <input
              class="input"
              :value="daySlotTitleDraft(selectedDaySlot.planned_date)"
              :placeholder="t('meals.dayTitlePlaceholder')"
              @input="updateDaySlotTitleDraft(selectedDaySlot.planned_date, $event.target.value)"
            />
          </label>

          <label>
            {{ t('meals.importFavoriteDay') }}
            <select
              class="input"
              value=""
              @change="handleFavoriteDayImport(selectedDaySlot, $event)"
            >
              <option value="">{{ t('meals.pickFavoriteDay') }}</option>
              <option v-for="dayPlan in dayPlans" :key="dayPlan.id" :value="String(dayPlan.id)">
                {{ dayPlan.name }}
              </option>
            </select>
          </label>
        </div>

        <DayMealsBuilder
          :model-value="resolveDaySlotMeals(selectedDaySlot)"
          :recipes="recipes"
          :nutrition-summaries="recipeNutritionSummaries"
          :meal-slots="activeMealPlan.meal_slots"
          :default-servings="activeMealPlan.portions_count || 1"
          :max-meals="mealSlotLimit"
          :show-totals="false"
          :empty-label="t('meals.emptyMeals')"
          :add-button-label="t('meals.addMealToDay')"
          @update:model-value="updateDaySlotMealsDraft(selectedDaySlot.planned_date, $event)"
        />

        <NutritionTotalsInline
          :caption="t('meals.dayTotalsTitle')"
          :totals="selectedDaySlot.totals ?? {}"
          :mass-label="t('meals.massLabel')"
        />

        <div class="actions-row">
          <button
            class="button is-primary is-small"
            type="button"
            @click="saveDaySlotMeals(selectedDaySlot.planned_date)"
          >
            {{ t('meals.saveSlotMeals') }}
          </button>

          <button
            class="button is-small"
            type="button"
            @click="saveCustomDaySlotAsFavorite(selectedDaySlot)"
          >
            {{ t('meals.saveFavoriteFromSlot') }}
          </button>
        </div>
      </div>

      <div v-if="favoriteImportModal" class="modal" @click.self="closeFavoriteImportModal">
        <div class="modal-content">
          <div class="modal-header">
            <h4 class="title is-6">{{ t('meals.favoriteOverflowTitle') }}</h4>
            <button class="button is-small" type="button" @click="closeFavoriteImportModal">
              {{ t('common.close') }}
            </button>
          </div>

          <p class="muted">
            {{
              t('meals.favoriteOverflowHint', {
                name: favoriteImportModal.dayPlanName,
                selected: favoriteImportSelection.length,
                limit: favoriteImportModal.limit,
              })
            }}
          </p>

          <ul class="picker-list">
            <li v-for="(meal, index) in favoriteImportModal.meals" :key="`overflow-meal-${index}`">
              <label class="overflow-option">
                <input
                  type="checkbox"
                  :checked="favoriteImportSelection.includes(index)"
                  :disabled="
                    !favoriteImportSelection.includes(index) &&
                    favoriteImportSelection.length >= favoriteImportModal.limit
                  "
                  @change="toggleFavoriteImportSelection(index)"
                />
                <span>{{ recipeName(meal.recipe_id) }}</span>
              </label>
            </li>
          </ul>

          <div class="actions-row">
            <button class="button is-primary" type="button" @click="confirmFavoriteImportSelection">
              {{ t('meals.importSelectedMeals') }}
            </button>
            <button class="button" type="button" @click="closeFavoriteImportModal">
              {{ t('common.cancel') }}
            </button>
          </div>
        </div>
      </div>
    </article>

    <article v-if="activeMealPlan" class="surface-card section-stack totals-card">
      <h2 class="title is-5">{{ t('meals.planTotalsTitle') }}</h2>
      <NutritionTotalsInline
        :totals="activeMealPlan.totals ?? {}"
        :mass-label="t('meals.massLabel')"
      />

      <div class="actions-row">
        <button class="button" type="button" @click="generateShoppingListFromActiveMealPlan">
          {{ t('meals.generateShoppingList') }}
        </button>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useCatalogStore } from '../stores/catalogStore'
import { useMealPlannerStore } from '../stores/mealPlannerStore'
import { useI18n } from '../composables/useI18n'
import DayMealsBuilder from '../components/planning/DayMealsBuilder.vue'
import NutritionTotalsInline from '../components/planning/NutritionTotalsInline.vue'
import SlotTimeClock from '../components/planning/SlotTimeClock.vue'

const authStore = useAuthStore()
const catalogStore = useCatalogStore()
const mealPlannerStore = useMealPlannerStore()
const { t } = useI18n()

const editingMealPlanId = ref(null)
const mealPlanSearch = ref('')
const mealPlanMessage = ref('')
const mealPlanError = ref('')
const selectedDaySlotDate = ref(null)

const mealPlanForm = ref({
  name: '',
  start_date: '',
  end_date: '',
  portions_count: 1,
  note: '',
})

const mealSlotsDraft = ref([])
const daySlotMealsDrafts = ref({})
const daySlotTitlesDraft = ref({})
const favoriteImportModal = ref(null)
const favoriteImportSelection = ref([])

const isAuthenticated = computed(() => authStore.isAuthenticated)
const mealPlans = computed(() => mealPlannerStore.mealPlans)
const activeMealPlan = computed(() => mealPlannerStore.activeMealPlan)
const dayPlans = computed(() => mealPlannerStore.dayPlans)
const recipes = computed(() => catalogStore.recipes)
const recipeNutritionSummaries = computed(() => catalogStore.recipeNutritionSummaries)
const recipesById = computed(() => new Map(recipes.value.map((recipe) => [recipe.id, recipe])))
const selectedMealPlanId = computed(() => activeMealPlan.value?.id ?? null)
const mealSlotRows = computed(() => activeMealPlan.value?.meal_slots ?? [])
const mealSlotLimit = computed(() => {
  const slots = activeMealPlan.value?.meal_slots ?? []
  return slots.length > 0 ? slots.length : null
})
const selectedDaySlot = computed(() => {
  const slots = activeMealPlan.value?.day_slots ?? []
  if (slots.length === 0) {
    return null
  }

  return slots.find((slot) => slot.planned_date === selectedDaySlotDate.value) ?? slots[0]
})

const visibleMealPlans = computed(() => {
  const needle = mealPlanSearch.value.trim().toLowerCase()
  return mealPlans.value.filter((plan) => {
    if (!needle) {
      return true
    }

    return `${plan.name} ${plan.start_date} ${plan.end_date}`.toLowerCase().includes(needle)
  })
})

function cloneMeals(meals) {
  if (!Array.isArray(meals)) {
    return []
  }

  return meals.map((meal) => ({
    recipe_id: meal.recipe_id,
    servings: meal.servings ?? null,
    portions: meal.portions ?? 1,
    note: meal.note ?? '',
  }))
}

function cloneMealSlots(slots) {
  if (!Array.isArray(slots)) {
    return []
  }

  return slots.map((slot) => ({
    slot_name: slot.slot_name,
    slot_time: slot.slot_time ?? '',
  }))
}

function applyMealPlanState(plan) {
  editingMealPlanId.value = plan.id
  mealPlanForm.value = {
    name: plan.name,
    start_date: plan.start_date,
    end_date: plan.end_date,
    portions_count: plan.portions_count ?? 1,
    note: plan.note ?? '',
  }

  mealSlotsDraft.value = cloneMealSlots(plan.meal_slots)
  daySlotMealsDrafts.value = (plan.day_slots ?? []).reduce((accumulator, daySlot) => {
    return {
      ...accumulator,
      [daySlot.planned_date]: cloneMeals(daySlot.meals),
    }
  }, {})
  daySlotTitlesDraft.value = (plan.day_slots ?? []).reduce((accumulator, daySlot) => {
    return {
      ...accumulator,
      [daySlot.planned_date]: daySlot.note ?? '',
    }
  }, {})

  if ((plan.day_slots ?? []).some((slot) => slot.planned_date === selectedDaySlotDate.value)) {
    return
  }

  selectedDaySlotDate.value = plan.day_slots?.[0]?.planned_date ?? null
}

function resetMealPlanForm(clearMessages = true) {
  editingMealPlanId.value = null
  mealPlanForm.value = {
    name: '',
    start_date: '',
    end_date: '',
    portions_count: 1,
    note: '',
  }
  mealSlotsDraft.value = []
  daySlotMealsDrafts.value = {}
  daySlotTitlesDraft.value = {}
  favoriteImportModal.value = null
  favoriteImportSelection.value = []
  selectedDaySlotDate.value = null

  if (clearMessages) {
    mealPlanMessage.value = ''
    mealPlanError.value = ''
  }
}

async function selectMealPlan(mealPlanId) {
  const plan = await mealPlannerStore.fetchMealPlan(mealPlanId)
  applyMealPlanState(plan)
  mealPlanMessage.value = ''
  mealPlanError.value = ''
}

async function saveMealPlan() {
  mealPlanMessage.value = ''
  mealPlanError.value = ''

  const payload = {
    ...mealPlanForm.value,
    portions_count: Number(mealPlanForm.value.portions_count),
  }

  try {
    if (editingMealPlanId.value) {
      const updated = await mealPlannerStore.updateMealPlan(editingMealPlanId.value, payload)
      applyMealPlanState(updated)
      mealPlanMessage.value = t('meals.planSaved')
      return
    }

    const created = await mealPlannerStore.createMealPlan(payload)
    applyMealPlanState(created)
    mealPlanMessage.value = t('meals.planAdded')
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.planSaveError')
  }
}

async function removeMealPlan() {
  if (!editingMealPlanId.value) {
    return
  }

  if (!confirm(t('meals.planDeleteConfirm', { name: mealPlanForm.value.name }))) {
    return
  }

  try {
    await mealPlannerStore.deleteMealPlan(editingMealPlanId.value)
    mealPlanMessage.value = t('meals.planDeleted')
    mealPlanError.value = ''
    resetMealPlanForm(false)
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.planDeleteError')
  }
}

function addMealSlot() {
  mealSlotsDraft.value = [...mealSlotsDraft.value, { slot_name: '', slot_time: '' }]
}

function removeMealSlot(index) {
  mealSlotsDraft.value = mealSlotsDraft.value.filter((_, slotIndex) => slotIndex !== index)
}

async function saveMealSlots() {
  if (!activeMealPlan.value) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    const updated = await mealPlannerStore.replaceMealPlanMealSlots(
      activeMealPlan.value.id,
      mealSlotsDraft.value,
    )
    applyMealPlanState(updated)
    mealPlanMessage.value = t('meals.mealSlotsSaved')
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.mealSlotsSaveError')
  }
}

function resolveDaySlotMeals(daySlot) {
  return cloneMeals(daySlotMealsDrafts.value[daySlot.planned_date] ?? daySlot.meals)
}

function customDaySlotMeals(daySlot) {
  return cloneMeals(daySlotMealsDrafts.value[daySlot.planned_date] ?? daySlot.meals)
}

function updateDaySlotMealsDraft(plannedDate, meals) {
  daySlotMealsDrafts.value = {
    ...daySlotMealsDrafts.value,
    [plannedDate]: cloneMeals(meals),
  }
}

function selectDaySlot(plannedDate) {
  selectedDaySlotDate.value = plannedDate
}

function daySlotTitleDraft(plannedDate) {
  return daySlotTitlesDraft.value[plannedDate] ?? ''
}

function updateDaySlotTitleDraft(plannedDate, value) {
  daySlotTitlesDraft.value = {
    ...daySlotTitlesDraft.value,
    [plannedDate]: typeof value === 'string' ? value : '',
  }
}

function matrixDayTitle(daySlot) {
  const draftTitle = daySlotTitleDraft(daySlot.planned_date).trim()
  if (draftTitle) {
    return draftTitle
  }

  const storedTitle = typeof daySlot?.note === 'string' ? daySlot.note.trim() : ''
  return storedTitle || t('meals.dayTitleFallback')
}

function mealsForMatrix(daySlot) {
  if (!daySlot) {
    return []
  }

  const draftMeals = daySlotMealsDrafts.value[daySlot.planned_date]
  if (Array.isArray(draftMeals)) {
    return draftMeals
  }

  return Array.isArray(daySlot.meals) ? daySlot.meals : []
}

function matrixMealName(daySlot, rowIndex) {
  const meal = mealsForMatrix(daySlot)[rowIndex]
  if (!meal) {
    return '-'
  }

  return meal.recipe_name ?? recipesById.value.get(meal.recipe_id)?.name ?? `#${meal.recipe_id}`
}

function matrixMealServings(daySlot, rowIndex) {
  const meal = mealsForMatrix(daySlot)[rowIndex]
  if (!meal) {
    return ''
  }

  const parsed = Number(meal.servings)
  const planPortions =
    Number(activeMealPlan.value?.portions_count) > 0 ? activeMealPlan.value.portions_count : 1
  const mealPortions = Number(meal.portions)
  const normalizedMealPortions =
    Number.isFinite(mealPortions) && mealPortions > 0 ? mealPortions : 1
  const effectiveServings =
    Number.isFinite(parsed) && parsed > 0 ? parsed : planPortions * normalizedMealPortions

  return `${t('meals.servingsLabel')}: ${effectiveServings}`
}

function summaryValue(totals, field) {
  const parsed = Number(totals?.[field])
  return Number.isFinite(parsed) ? Number(parsed.toFixed(2)) : 0
}

function formatMassFromGrams(value) {
  const parsed = Number(value)
  const grams = Number.isFinite(parsed) ? Number(parsed.toFixed(2)) : 0
  if (grams >= 1000) {
    return `${Number((grams / 1000).toFixed(2))} kg`
  }

  return `${grams} g`
}

function daySummaryLineOne(totals) {
  return `kcal ${summaryValue(totals, 'calories')}`
}

function daySummaryLineTwo(totals) {
  return `B ${summaryValue(totals, 'protein')}g | T ${summaryValue(totals, 'fat')}g | W ${summaryValue(totals, 'carbohydrates')}g`
}

function daySummaryLineThree(totals) {
  return `M ${formatMassFromGrams(totals?.total_mass_grams)}`
}

function recipeName(recipeId) {
  return recipesById.value.get(recipeId)?.name ?? `#${recipeId}`
}

function closeFavoriteImportModal() {
  favoriteImportModal.value = null
  favoriteImportSelection.value = []
}

function toggleFavoriteImportSelection(index) {
  if (!favoriteImportModal.value) {
    return
  }

  if (favoriteImportSelection.value.includes(index)) {
    favoriteImportSelection.value = favoriteImportSelection.value.filter((item) => item !== index)
    return
  }

  if (favoriteImportSelection.value.length >= favoriteImportModal.value.limit) {
    return
  }

  favoriteImportSelection.value = [...favoriteImportSelection.value, index].sort((a, b) => a - b)
}

function mapImportedMeals(dayPlanMeals) {
  return dayPlanMeals.map((meal) => ({
    recipe_id: meal.recipe_id,
    servings: meal.servings ?? null,
    portions: meal.portions ?? 1,
    note: meal.note ?? '',
  }))
}

async function importMealsIntoDaySlot(plannedDate, meals, dayPlanName) {
  if (!activeMealPlan.value) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    const updatedMeals = await mealPlannerStore.replaceMealPlanDaySlotMeals(
      activeMealPlan.value.id,
      plannedDate,
      meals,
    )

    const preferredTitle = daySlotTitleDraft(plannedDate).trim() || String(dayPlanName ?? '').trim()
    const savedTitle = String(
      updatedMeals.day_slots?.find((slot) => slot.planned_date === plannedDate)?.note ?? '',
    ).trim()

    const updated =
      preferredTitle === savedTitle
        ? updatedMeals
        : await mealPlannerStore.updateMealPlanDaySlot(activeMealPlan.value.id, plannedDate, {
            day_plan_id: null,
            note: preferredTitle,
          })

    applyMealPlanState(updated)
    selectedDaySlotDate.value = plannedDate
    mealPlanMessage.value = t('meals.favoriteImportedToCustom', { name: dayPlanName })
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.favoriteImportError')
  }
}

async function handleFavoriteDayImport(daySlot, event) {
  if (!activeMealPlan.value) {
    return
  }

  const nextValue = String(event?.target?.value ?? '')
  if (event?.target) {
    event.target.value = ''
  }

  const dayPlanId = Number(nextValue)
  if (!Number.isInteger(dayPlanId) || dayPlanId <= 0) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    const dayPlan = await mealPlannerStore.fetchDayPlan(dayPlanId)
    const importedMeals = mapImportedMeals(dayPlan?.meals ?? [])
    const limit = mealSlotLimit.value ?? importedMeals.length

    if (importedMeals.length > limit) {
      favoriteImportModal.value = {
        plannedDate: daySlot.planned_date,
        dayPlanName: dayPlan?.name ?? t('meals.dayTitleFallback'),
        meals: importedMeals,
        limit,
      }
      favoriteImportSelection.value = importedMeals.map((_, index) => index).slice(0, limit)
      selectedDaySlotDate.value = daySlot.planned_date
      return
    }

    await importMealsIntoDaySlot(daySlot.planned_date, importedMeals, dayPlan?.name ?? '')
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.favoriteImportError')
  }
}

async function confirmFavoriteImportSelection() {
  if (!favoriteImportModal.value) {
    return
  }

  if (favoriteImportSelection.value.length === 0) {
    mealPlanError.value = t('meals.favoriteOverflowEmptySelection')
    return
  }

  const selectedMeals = favoriteImportSelection.value
    .sort((a, b) => a - b)
    .map((index) => favoriteImportModal.value.meals[index])
    .filter(Boolean)

  const plannedDate = favoriteImportModal.value.plannedDate
  const dayPlanName = favoriteImportModal.value.dayPlanName
  closeFavoriteImportModal()
  await importMealsIntoDaySlot(plannedDate, selectedMeals, dayPlanName)
}

async function saveDaySlotMeals(plannedDate) {
  if (!activeMealPlan.value) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    const updatedMeals = await mealPlannerStore.replaceMealPlanDaySlotMeals(
      activeMealPlan.value.id,
      plannedDate,
      daySlotMealsDrafts.value[plannedDate] ?? [],
    )

    const nextTitle = daySlotTitleDraft(plannedDate).trim()
    const savedTitle = String(
      updatedMeals.day_slots?.find((slot) => slot.planned_date === plannedDate)?.note ?? '',
    ).trim()

    const updated =
      nextTitle === savedTitle
        ? updatedMeals
        : await mealPlannerStore.updateMealPlanDaySlot(activeMealPlan.value.id, plannedDate, {
            day_plan_id: null,
            note: nextTitle,
          })

    applyMealPlanState(updated)
    mealPlanMessage.value = t('meals.slotMealsSaved')
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.slotMealsSaveError')
  }
}

async function saveCustomDaySlotAsFavorite(daySlot) {
  const meals = customDaySlotMeals(daySlot)
  if (meals.length === 0) {
    mealPlanError.value = t('meals.favoriteFromSlotEmptyError')
    mealPlanMessage.value = ''
    return
  }

  const defaultName = `${mealPlanForm.value.name} ${daySlot.planned_date}`
  const enteredName = prompt(t('meals.favoriteNamePrompt'), defaultName)
  const name = typeof enteredName === 'string' ? enteredName.trim() : ''

  if (!name) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    const created = await mealPlannerStore.createDayPlan({
      name,
      note: t('meals.favoriteSourceNote', {
        plan: mealPlanForm.value.name,
        date: daySlot.planned_date,
      }),
    })

    await mealPlannerStore.replaceDayPlanMeals(created.id, meals)
    await mealPlannerStore.fetchDayPlans()

    mealPlanMessage.value = t('meals.favoriteSavedFromSlot', { name: created.name })
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.favoriteSaveError')
  }
}

async function generateShoppingListFromActiveMealPlan() {
  if (!activeMealPlan.value) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    await mealPlannerStore.generateShoppingListFromMealPlan(activeMealPlan.value.id)
    mealPlanMessage.value = t('meals.listGenerated')
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.listGenerateError')
  }
}

onMounted(async () => {
  if (!isAuthenticated.value) {
    return
  }

  await Promise.all([
    mealPlannerStore.fetchMealPlans(),
    mealPlannerStore.fetchDayPlans(),
    catalogStore.fetchRecipes(),
    catalogStore.fetchRecipeNutritionSummaries(),
  ])

  if (mealPlans.value.length > 0) {
    await selectMealPlan(mealPlans.value[0].id)
  }
})
</script>

<style scoped>
.planner-layout {
  display: grid;
  gap: 1rem;
}

.top-grid {
  display: grid;
  gap: 1rem;
}

.section-stack {
  display: grid;
  gap: 0.75rem;
}

.section-header {
  display: grid;
  gap: 0.5rem;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.45rem;
}

.list li {
  border-bottom: 1px solid var(--app-border);
  padding-bottom: 0.45rem;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.55rem;
}

.is-active-row {
  border-bottom-color: var(--app-accent);
}

.link {
  border: none;
  padding: 0;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.slot-row {
  display: grid;
  gap: 0.45rem;
}

.plan-days-block {
  margin-top: 1.2rem;
  gap: 1rem;
}

.block-header {
  margin-bottom: 0.3rem;
}

.plan-break {
  border-top: 2px dashed var(--app-border);
  text-align: center;
  line-height: 1;
  font-size: 1.15rem;
  color: var(--app-muted);
  margin: 0.15rem 0;
  padding-top: 0.4rem;
}

.matrix-wrapper {
  overflow-x: auto;
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
}

.matrix-table {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
}

.matrix-table th,
.matrix-table td {
  border-bottom: 1px solid var(--app-border);
  border-right: 1px solid var(--app-border);
  padding: 0.45rem;
  vertical-align: top;
}

.matrix-table th:last-child,
.matrix-table td:last-child {
  border-right: none;
}

.matrix-table thead th {
  background: var(--app-surface-alt);
}

.matrix-day-button {
  border: none;
  padding: 0;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
  font-weight: 700;
}

.matrix-day-title {
  margin: 0.15rem 0 0;
  font-size: 0.78rem;
  line-height: 1.2;
}

.matrix-slot-cell {
  display: grid;
  gap: 0.2rem;
  min-width: 170px;
}

.matrix-slot-title {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.45rem;
  width: 100%;
}

.slot-clock-cell {
  justify-self: end;
}

.matrix-day-summary-row th,
.matrix-day-summary-row td {
  background: color-mix(in oklab, var(--app-surface-alt), #ffffff 35%);
}

.matrix-day-summary-text {
  margin: 0;
  font-family: 'Courier Prime', 'Courier New', monospace;
  font-size: 0.75rem;
  letter-spacing: 0.02em;
  line-height: 1.25;
  white-space: nowrap;
}

.matrix-cell-button {
  width: 100%;
  border: 1px solid var(--app-border);
  border-radius: 0.6rem;
  background: var(--app-surface);
  color: var(--app-text);
  padding: 0.35rem 0.45rem;
  display: grid;
  gap: 0.2rem;
  text-align: left;
  cursor: pointer;
}

.is-selected-column {
  background: rgba(47, 95, 190, 0.08);
}

.day-slot-card {
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
  padding: 0.65rem;
  display: grid;
  gap: 0.65rem;
  background: linear-gradient(180deg, var(--app-surface) 0%, var(--app-surface-alt) 100%);
}

.is-custom-card {
  border-left: 4px solid #2f5fbe;
}

.day-slot-header {
  display: grid;
  gap: 0.5rem;
}

.date-meta {
  display: grid;
  gap: 0.35rem;
}

.modal {
  display: flex;
  justify-content: center;
  align-items: center;
  position: fixed;
  inset: 0;
  z-index: 70;
  background-color: rgba(0, 0, 0, 0.42);
}

.modal-content {
  width: min(720px, calc(100% - 1.25rem));
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
  padding: 0.75rem;
  display: grid;
  gap: 0.55rem;
  max-height: calc(100vh - 3rem);
  overflow: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.35rem;
}

.overflow-option {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.totals-card {
  margin-top: 1rem;
}

@media (min-width: 960px) {
  .slot-row {
    grid-template-columns: 1.2fr 0.9fr auto;
    align-items: center;
  }

  .day-slot-header {
    grid-template-columns: 1fr 1.3fr;
    align-items: start;
  }
}

@media (min-width: 1200px) {
  .top-grid {
    grid-template-columns: 1fr 1fr;
    align-items: start;
  }
}
</style>
