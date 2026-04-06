<template>
  <section v-if="!isAuthenticated" class="surface-card">
    <h1 class="title is-4">{{ t('meals.authTitle') }}</h1>
    <p class="muted">{{ t('common.requiredAuth') }}</p>
    <RouterLink to="/login">{{ t('common.goToLogin') }}</RouterLink>
  </section>

  <section v-else class="planner-grid">
    <article class="surface-card section-stack">
      <div class="section-header">
        <h1 class="title is-4">{{ t('meals.planningTitle') }}</h1>
        <p class="muted">{{ t('meals.planningDescription') }}</p>
      </div>

      <div class="list-block">
        <h2 class="title is-5">{{ t('meals.plansListTitle') }}</h2>
        <ul class="list">
          <li v-for="plan in mealPlans" :key="plan.id">
            <button class="link" @click="selectMealPlan(plan.id)">{{ plan.name }}</button>
            <span class="muted"
              >{{ plan.start_date }} - {{ plan.end_date }} | {{ plan.entries_count }}
              {{ t('common.records') }}</span
            >
          </li>
        </ul>
      </div>

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

      <div v-if="activeMealPlan" class="entries-block">
        <h3 class="title is-5">{{ t('meals.entriesTitle') }}: {{ activeMealPlan.name }}</h3>
        <p class="muted">{{ t('meals.entriesFormat') }}</p>
        <p class="muted">{{ t('meals.entriesSlots') }}</p>

        <textarea v-model="entriesText" class="textarea" rows="10"></textarea>

        <div class="actions-row">
          <button class="button is-primary" type="button" @click="saveEntries">
            {{ t('meals.saveEntries') }}
          </button>
          <button class="button" type="button" @click="generateShoppingListFromActiveMealPlan">
            {{ t('meals.generateShoppingList') }}
          </button>
        </div>
      </div>
    </article>

    <article class="surface-card section-stack">
      <div class="section-header">
        <h1 class="title is-4">{{ t('meals.shoppingListsTitle') }}</h1>
        <p class="muted">{{ t('meals.shoppingListsDescription') }}</p>
      </div>

      <div class="list-block">
        <h2 class="title is-5">{{ t('meals.shoppingListListTitle') }}</h2>
        <ul class="list">
          <li v-for="list in shoppingLists" :key="list.id">
            <button class="link" @click="selectShoppingList(list.id)">{{ list.name }}</button>
            <span class="muted"
              >{{
                list.status === 'archived' ? t('common.statusArchived') : t('common.statusOpen')
              }}
              | {{ list.checked_count }}/{{ list.items_count }}</span
            >
          </li>
        </ul>
      </div>

      <form class="form-grid" @submit.prevent="saveShoppingList">
        <h3 class="title is-5">
          {{
            editingShoppingListId
              ? t('meals.editShoppingListTitle')
              : t('meals.newShoppingListTitle')
          }}
        </h3>

        <label>
          {{ t('meals.name') }}
          <input v-model="shoppingListForm.name" class="input" required />
        </label>

        <div class="grid-two">
          <label>
            {{ t('common.status') }}
            <select v-model="shoppingListForm.status" class="input">
              <option value="open">{{ t('common.statusOpen') }}</option>
              <option value="archived">{{ t('common.statusArchived') }}</option>
            </select>
          </label>

          <label>
            {{ t('meals.linkedPlan') }}
            <select v-model="shoppingListForm.meal_plan_id" class="input">
              <option value="">{{ t('meals.noLinkedPlan') }}</option>
              <option v-for="plan in mealPlans" :key="plan.id" :value="String(plan.id)">
                {{ plan.name }}
              </option>
            </select>
          </label>
        </div>

        <label>
          {{ t('meals.note') }}
          <textarea v-model="shoppingListForm.note" class="textarea" rows="3"></textarea>
        </label>

        <p v-if="shoppingListMessage" class="success-message">{{ shoppingListMessage }}</p>
        <p v-if="shoppingListError" class="error-message">{{ shoppingListError }}</p>

        <div class="actions-row">
          <button class="button is-primary" type="submit">
            {{ editingShoppingListId ? t('meals.saveList') : t('meals.addList') }}
          </button>
          <button class="button" type="button" @click="resetShoppingListForm">
            {{ t('common.reset') }}
          </button>
          <button
            v-if="editingShoppingListId"
            class="button"
            type="button"
            @click="removeShoppingList"
          >
            {{ t('meals.removeList') }}
          </button>
        </div>
      </form>

      <div v-if="activeShoppingList" class="items-block">
        <h3 class="title is-5">{{ t('meals.itemsTitle') }}: {{ activeShoppingList.name }}</h3>

        <ul class="list">
          <li v-for="item in activeShoppingList.items" :key="item.id" class="item-row">
            <label class="checkbox-line">
              <input
                :checked="item.is_checked === 1"
                type="checkbox"
                @change="toggleItemChecked(item, $event.target.checked)"
              />
              <span>{{ item.product_name || item.custom_name }}</span>
            </label>

            <span class="muted">{{ item.quantity ?? '-' }} {{ item.unit_name || '' }}</span>
            <button class="button is-small" type="button" @click="removeShoppingListItem(item.id)">
              {{ t('common.delete') }}
            </button>
          </li>
        </ul>

        <form class="form-grid" @submit.prevent="addItemToShoppingList">
          <h4 class="title is-6">{{ t('meals.addItemTitle') }}</h4>

          <label>
            {{ t('meals.productFromCatalog') }}
            <select v-model="shoppingItemForm.product_id" class="input">
              <option value="">{{ t('meals.pickProduct') }}</option>
              <option v-for="product in products" :key="product.id" :value="String(product.id)">
                {{ product.name }}
              </option>
            </select>
          </label>

          <label>
            {{ t('meals.customName') }}
            <input
              v-model="shoppingItemForm.custom_name"
              class="input"
              :placeholder="t('meals.customNamePlaceholder')"
            />
          </label>

          <div class="grid-two">
            <label>
              {{ t('meals.quantity') }}
              <input
                v-model="shoppingItemForm.quantity"
                class="input"
                type="number"
                min="0"
                step="0.01"
              />
            </label>

            <label>
              {{ t('meals.unit') }}
              <select v-model="shoppingItemForm.unit_id" class="input">
                <option value="">{{ t('meals.noUnit') }}</option>
                <option v-for="unit in units" :key="unit.id" :value="String(unit.id)">
                  {{ unit.name }}
                </option>
              </select>
            </label>
          </div>

          <label>
            {{ t('meals.note') }}
            <input v-model="shoppingItemForm.note" class="input" />
          </label>

          <button class="button is-primary" type="submit">{{ t('meals.addItem') }}</button>
        </form>
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
import { useUnitStore } from '../stores/unitsStore'
import { useI18n } from '../composables/useI18n'

const authStore = useAuthStore()
const catalogStore = useCatalogStore()
const mealPlannerStore = useMealPlannerStore()
const unitStore = useUnitStore()
const { t } = useI18n()

const editingMealPlanId = ref(null)
const editingShoppingListId = ref(null)

const mealPlanMessage = ref('')
const mealPlanError = ref('')
const shoppingListMessage = ref('')
const shoppingListError = ref('')

const entriesText = ref('')

const mealPlanForm = ref({
  name: '',
  start_date: '',
  end_date: '',
  note: '',
})

const shoppingListForm = ref({
  name: '',
  status: 'open',
  meal_plan_id: '',
  note: '',
})

const shoppingItemForm = ref({
  product_id: '',
  custom_name: '',
  quantity: '',
  unit_id: '',
  note: '',
})

const isAuthenticated = computed(() => authStore.isAuthenticated)
const mealPlans = computed(() => mealPlannerStore.mealPlans)
const activeMealPlan = computed(() => mealPlannerStore.activeMealPlan)
const shoppingLists = computed(() => mealPlannerStore.shoppingLists)
const activeShoppingList = computed(() => mealPlannerStore.activeShoppingList)
const products = computed(() => catalogStore.products)
const units = computed(() => unitStore.units)

function resetMealPlanForm(clearMessages = true) {
  editingMealPlanId.value = null
  mealPlanForm.value = {
    name: '',
    start_date: '',
    end_date: '',
    note: '',
  }

  if (clearMessages) {
    mealPlanMessage.value = ''
    mealPlanError.value = ''
  }
}

function resetShoppingListForm(clearMessages = true) {
  editingShoppingListId.value = null
  shoppingListForm.value = {
    name: '',
    status: 'open',
    meal_plan_id: '',
    note: '',
  }

  if (clearMessages) {
    shoppingListMessage.value = ''
    shoppingListError.value = ''
  }
}

function resetShoppingItemForm() {
  shoppingItemForm.value = {
    product_id: '',
    custom_name: '',
    quantity: '',
    unit_id: '',
    note: '',
  }
}

function mapEntriesToText(entries) {
  return entries
    .map((entry) => {
      const recipeId = entry.recipe_id ?? ''
      const customName = entry.custom_name ?? ''
      const servings = entry.servings ?? ''
      const note = entry.note ?? ''
      return `${entry.planned_date}|${entry.meal_slot}|${recipeId}|${customName}|${servings}|${note}`
    })
    .join('\n')
}

function parseEntriesText() {
  return entriesText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [plannedDate, mealSlot, recipeId, customName, servings, note] = line
        .split('|')
        .map((part) => (typeof part === 'string' ? part.trim() : ''))

      const parsedRecipeId = recipeId ? Number(recipeId) : null
      const parsedServings = servings ? Number(servings.replace(',', '.')) : null

      return {
        planned_date: plannedDate,
        meal_slot: mealSlot,
        recipe_id: Number.isInteger(parsedRecipeId) ? parsedRecipeId : null,
        custom_name: customName || null,
        servings: Number.isFinite(parsedServings) ? parsedServings : null,
        note: note || '',
      }
    })
}

async function selectMealPlan(mealPlanId) {
  const plan = await mealPlannerStore.fetchMealPlan(mealPlanId)
  editingMealPlanId.value = plan.id
  mealPlanForm.value = {
    name: plan.name,
    start_date: plan.start_date,
    end_date: plan.end_date,
    note: plan.note ?? '',
  }
  entriesText.value = mapEntriesToText(plan.entries ?? [])
  mealPlanMessage.value = ''
  mealPlanError.value = ''
}

async function saveMealPlan() {
  mealPlanMessage.value = ''
  mealPlanError.value = ''

  const payload = {
    ...mealPlanForm.value,
  }

  try {
    if (editingMealPlanId.value) {
      const updated = await mealPlannerStore.updateMealPlan(editingMealPlanId.value, payload)
      await selectMealPlan(updated.id)
      mealPlanMessage.value = t('meals.planSaved')
      return
    }

    const created = await mealPlannerStore.createMealPlan(payload)
    await selectMealPlan(created.id)
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
    entriesText.value = ''
    mealPlanMessage.value = t('meals.planDeleted')
    mealPlanError.value = ''
    resetMealPlanForm(false)
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.planDeleteError')
  }
}

async function saveEntries() {
  if (!activeMealPlan.value) {
    return
  }

  mealPlanMessage.value = ''
  mealPlanError.value = ''

  try {
    const updated = await mealPlannerStore.replaceMealPlanEntries(
      activeMealPlan.value.id,
      parseEntriesText(),
    )
    entriesText.value = mapEntriesToText(updated.entries ?? [])
    mealPlanMessage.value = t('meals.entriesSaved')
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? t('meals.entriesSaveError')
  }
}

async function generateShoppingListFromActiveMealPlan() {
  if (!activeMealPlan.value) {
    return
  }

  shoppingListMessage.value = ''
  shoppingListError.value = ''

  try {
    const created = await mealPlannerStore.generateShoppingListFromMealPlan(activeMealPlan.value.id)
    await selectShoppingList(created.id)
    shoppingListMessage.value = t('meals.listGenerated')
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? t('meals.listGenerateError')
  }
}

async function selectShoppingList(shoppingListId) {
  const shoppingList = await mealPlannerStore.fetchShoppingList(shoppingListId)

  editingShoppingListId.value = shoppingList.id
  shoppingListForm.value = {
    name: shoppingList.name,
    status: shoppingList.status,
    meal_plan_id: shoppingList.meal_plan_id ? String(shoppingList.meal_plan_id) : '',
    note: shoppingList.note ?? '',
  }

  shoppingListMessage.value = ''
  shoppingListError.value = ''
}

async function saveShoppingList() {
  shoppingListMessage.value = ''
  shoppingListError.value = ''

  const payload = {
    ...shoppingListForm.value,
    meal_plan_id: shoppingListForm.value.meal_plan_id
      ? Number(shoppingListForm.value.meal_plan_id)
      : null,
  }

  try {
    if (editingShoppingListId.value) {
      const updated = await mealPlannerStore.updateShoppingList(
        editingShoppingListId.value,
        payload,
      )
      await selectShoppingList(updated.id)
      shoppingListMessage.value = t('meals.listSaved')
      return
    }

    const created = await mealPlannerStore.createShoppingList(payload)
    await selectShoppingList(created.id)
    shoppingListMessage.value = t('meals.listAdded')
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? t('meals.listSaveError')
  }
}

async function removeShoppingList() {
  if (!editingShoppingListId.value) {
    return
  }

  if (!confirm(t('meals.listDeleteConfirm', { name: shoppingListForm.value.name }))) {
    return
  }

  try {
    await mealPlannerStore.deleteShoppingList(editingShoppingListId.value)
    shoppingListMessage.value = t('meals.listDeleted')
    shoppingListError.value = ''
    resetShoppingListForm(false)
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? t('meals.listDeleteError')
  }
}

async function addItemToShoppingList() {
  if (!activeShoppingList.value) {
    return
  }

  shoppingListError.value = ''

  try {
    await mealPlannerStore.addShoppingListItem(activeShoppingList.value.id, {
      product_id: shoppingItemForm.value.product_id
        ? Number(shoppingItemForm.value.product_id)
        : null,
      custom_name: shoppingItemForm.value.custom_name || null,
      quantity: shoppingItemForm.value.quantity ? Number(shoppingItemForm.value.quantity) : null,
      unit_id: shoppingItemForm.value.unit_id ? Number(shoppingItemForm.value.unit_id) : null,
      note: shoppingItemForm.value.note,
    })

    resetShoppingItemForm()
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? t('meals.itemAddError')
  }
}

async function toggleItemChecked(item, checked) {
  if (!activeShoppingList.value) {
    return
  }

  try {
    await mealPlannerStore.updateShoppingListItem(activeShoppingList.value.id, item.id, {
      is_checked: checked,
    })
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? t('meals.itemToggleError')
  }
}

async function removeShoppingListItem(itemId) {
  if (!activeShoppingList.value) {
    return
  }

  try {
    await mealPlannerStore.deleteShoppingListItem(activeShoppingList.value.id, itemId)
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? t('meals.itemDeleteError')
  }
}

onMounted(async () => {
  if (!isAuthenticated.value) {
    return
  }

  await Promise.all([
    mealPlannerStore.fetchMealPlans(),
    mealPlannerStore.fetchShoppingLists(),
    catalogStore.fetchProducts(),
    unitStore.fetchUnits(),
  ])

  if (mealPlans.value.length > 0) {
    await selectMealPlan(mealPlans.value[0].id)
  }

  if (shoppingLists.value.length > 0) {
    await selectShoppingList(shoppingLists.value[0].id)
  }
})
</script>

<style scoped>
.planner-grid {
  display: grid;
  gap: 1rem;
}

.section-stack {
  display: grid;
  gap: 1rem;
}

.section-header {
  display: grid;
  gap: 0.35rem;
}

.list-block {
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
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.6rem;
  border-bottom: 1px solid var(--app-border);
  padding-bottom: 0.45rem;
}

.link {
  border: none;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
  padding: 0;
}

.actions-row {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.entries-block,
.items-block {
  display: grid;
  gap: 0.65rem;
}

.item-row {
  align-items: center;
}

textarea {
  border: 1px solid var(--app-border);
  border-radius: 0.55rem;
  padding: 0.55rem 0.65rem;
  background: var(--app-surface);
  color: var(--app-text);
}

@media (min-width: 1100px) {
  .planner-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }
}
</style>
