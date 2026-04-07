<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useAuthStore } from '../stores/authStore'
import { useCatalogStore } from '../stores/catalogStore'
import { useMealPlannerStore } from '../stores/mealPlannerStore'
import { useI18n } from '../composables/useI18n'
import DayMealsBuilder from '../components/planning/DayMealsBuilder.vue'

const authStore = useAuthStore()
const catalogStore = useCatalogStore()
const mealPlannerStore = useMealPlannerStore()
const { t } = useI18n()

const editingDayPlanId = ref(null)
const dayPlanSearch = ref('')
const dayPlanMessage = ref('')
const dayPlanError = ref('')

const dayPlanForm = ref({
  name: '',
  note: '',
})

const dayPlanMealsDraft = ref([])

const isAuthenticated = computed(() => authStore.isAuthenticated)
const dayPlans = computed(() => mealPlannerStore.dayPlans)
const activeDayPlan = computed(() => mealPlannerStore.activeDayPlan)
const recipes = computed(() => catalogStore.recipes)
const recipeNutritionSummaries = computed(() => catalogStore.recipeNutritionSummaries)
const selectedDayPlanId = computed(() => activeDayPlan.value?.id ?? null)

const visibleDayPlans = computed(() => {
  const needle = dayPlanSearch.value.trim().toLowerCase()
  return dayPlans.value.filter((dayPlan) => {
    if (!needle) {
      return true
    }

    return `${dayPlan.name} ${dayPlan.note}`.toLowerCase().includes(needle)
  })
})

function cloneMeals(meals) {
  if (!Array.isArray(meals)) {
    return []
  }

  return meals.map((meal) => ({
    recipe_id: meal.recipe_id,
    servings: meal.servings ?? null,
    note: meal.note ?? '',
  }))
}

function applyDayPlanState(dayPlan) {
  editingDayPlanId.value = dayPlan.id
  dayPlanForm.value = {
    name: dayPlan.name,
    note: dayPlan.note ?? '',
  }
  dayPlanMealsDraft.value = cloneMeals(dayPlan.meals)
}

function resetDayPlanForm(clearMessages = true) {
  editingDayPlanId.value = null
  dayPlanForm.value = {
    name: '',
    note: '',
  }
  dayPlanMealsDraft.value = []

  if (clearMessages) {
    dayPlanMessage.value = ''
    dayPlanError.value = ''
  }
}

async function selectDayPlan(dayPlanId) {
  const dayPlan = await mealPlannerStore.fetchDayPlan(dayPlanId)
  applyDayPlanState(dayPlan)
  dayPlanMessage.value = ''
  dayPlanError.value = ''
}

async function saveDayPlan() {
  dayPlanMessage.value = ''
  dayPlanError.value = ''

  const payload = {
    ...dayPlanForm.value,
  }

  try {
    if (editingDayPlanId.value) {
      const updated = await mealPlannerStore.updateDayPlan(editingDayPlanId.value, payload)
      applyDayPlanState(updated)
      dayPlanMessage.value = t('meals.dayPlanSaved')
      return
    }

    const created = await mealPlannerStore.createDayPlan(payload)
    applyDayPlanState(created)
    dayPlanMessage.value = t('meals.dayPlanAdded')
  } catch (error) {
    dayPlanError.value = error?.response?.data?.error ?? t('meals.dayPlanSaveError')
  }
}

async function removeDayPlan() {
  if (!editingDayPlanId.value) {
    return
  }

  if (!confirm(t('meals.dayPlanDeleteConfirm', { name: dayPlanForm.value.name }))) {
    return
  }

  try {
    await mealPlannerStore.deleteDayPlan(editingDayPlanId.value)
    dayPlanMessage.value = t('meals.dayPlanDeleted')
    dayPlanError.value = ''
    resetDayPlanForm(false)
  } catch (error) {
    dayPlanError.value = error?.response?.data?.error ?? t('meals.dayPlanDeleteError')
  }
}

async function saveDayPlanMeals() {
  if (!activeDayPlan.value) {
    return
  }

  dayPlanMessage.value = ''
  dayPlanError.value = ''

  try {
    const updated = await mealPlannerStore.replaceDayPlanMeals(
      activeDayPlan.value.id,
      dayPlanMealsDraft.value,
    )
    applyDayPlanState(updated)
    dayPlanMessage.value = t('meals.dayPlanMealsSaved')
  } catch (error) {
    dayPlanError.value = error?.response?.data?.error ?? t('meals.dayPlanMealsSaveError')
  }
}

onMounted(async () => {
  if (!isAuthenticated.value) {
    return
  }

  await Promise.all([
    mealPlannerStore.fetchDayPlans(),
    catalogStore.fetchRecipes(),
    catalogStore.fetchRecipeNutritionSummaries(),
  ])

  if (dayPlans.value.length > 0) {
    await selectDayPlan(dayPlans.value[0].id)
  }
})
</script>

<template>
  <section v-if="!isAuthenticated" class="surface-card">
    <h1 class="title is-4">{{ t('meals.dayPlansListTitle') }}</h1>
    <p class="muted">{{ t('common.requiredAuth') }}</p>
    <RouterLink to="/login">{{ t('common.goToLogin') }}</RouterLink>
  </section>

  <section v-else class="surface-card favorite-days-layout">
    <CatalogSectionNav />

    <article class="section-stack">
      <div class="section-header">
        <h1 class="title is-4">{{ t('meals.dayPlansListTitle') }}</h1>
        <input
          v-model="dayPlanSearch"
          class="input"
          :placeholder="t('catalog.searchRecipe')"
          type="text"
        />
      </div>

      <ul class="list">
        <li
          v-for="dayPlan in visibleDayPlans"
          :key="dayPlan.id"
          :class="{ 'is-active-row': dayPlan.id === selectedDayPlanId }"
        >
          <button class="link" type="button" @click="selectDayPlan(dayPlan.id)">
            {{ dayPlan.name }}
          </button>
          <span class="muted">{{ dayPlan.meals_count }} {{ t('meals.itemsTitle') }}</span>
        </li>
      </ul>

      <form class="form-grid" @submit.prevent="saveDayPlan">
        <h2 class="title is-5">
          {{ editingDayPlanId ? t('meals.editDayPlanTitle') : t('meals.newDayPlanTitle') }}
        </h2>

        <label>
          {{ t('meals.name') }}
          <input v-model="dayPlanForm.name" class="input" required />
        </label>

        <label>
          {{ t('meals.note') }}
          <textarea v-model="dayPlanForm.note" class="textarea" rows="3"></textarea>
        </label>

        <p v-if="dayPlanMessage" class="success-message">{{ dayPlanMessage }}</p>
        <p v-if="dayPlanError" class="error-message">{{ dayPlanError }}</p>

        <div class="actions-row">
          <button class="button is-primary" type="submit">
            {{ editingDayPlanId ? t('meals.saveDayPlan') : t('meals.addDayPlan') }}
          </button>
          <button class="button" type="button" @click="resetDayPlanForm">
            {{ t('common.reset') }}
          </button>
          <button v-if="editingDayPlanId" class="button" type="button" @click="removeDayPlan">
            {{ t('meals.removeDayPlan') }}
          </button>
        </div>
      </form>
    </article>

    <article v-if="activeDayPlan" class="section-stack favorite-editor">
      <h2 class="title is-5">{{ t('meals.dayPlanMealsTitle') }}: {{ activeDayPlan.name }}</h2>
      <p class="muted">{{ t('meals.favoriteLiveHint') }}</p>

      <DayMealsBuilder
        v-model="dayPlanMealsDraft"
        :recipes="recipes"
        :nutrition-summaries="recipeNutritionSummaries"
        :default-servings="1"
        :empty-label="t('meals.emptyMeals')"
        :add-button-label="t('meals.addMealToDay')"
      />

      <div class="actions-row">
        <button class="button is-primary" type="button" @click="saveDayPlanMeals">
          {{ t('meals.saveDayPlanMeals') }}
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.favorite-days-layout {
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

.favorite-editor {
  border-top: 1px solid var(--app-border);
  padding-top: 0.8rem;
}
</style>
