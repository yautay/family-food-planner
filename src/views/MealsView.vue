<template>
  <section v-if="!isAuthenticated" class="surface-card">
    <h1>Meal planner</h1>
    <p class="muted">Ten widok wymaga logowania.</p>
    <RouterLink to="/login">Przejdz do logowania</RouterLink>
  </section>

  <section v-else class="planner-grid">
    <article class="surface-card section-stack">
      <div class="section-header">
        <h1>Planowanie okresu</h1>
        <p class="muted">Prywatne plany tylko dla zalogowanego uzytkownika.</p>
      </div>

      <div class="list-block">
        <h2>Plany</h2>
        <ul class="list">
          <li v-for="plan in mealPlans" :key="plan.id">
            <button class="link" @click="selectMealPlan(plan.id)">{{ plan.name }}</button>
            <span class="muted">{{ plan.start_date }} - {{ plan.end_date }} | {{ plan.entries_count }} pozycji</span>
          </li>
        </ul>
      </div>

      <form class="form-grid" @submit.prevent="saveMealPlan">
        <h3>{{ editingMealPlanId ? 'Edycja planu' : 'Nowy plan' }}</h3>

        <label>
          Nazwa
          <input v-model="mealPlanForm.name" required />
        </label>

        <div class="grid-two">
          <label>
            Data od
            <input v-model="mealPlanForm.start_date" type="date" required />
          </label>

          <label>
            Data do
            <input v-model="mealPlanForm.end_date" type="date" required />
          </label>
        </div>

        <label>
          Notatka
          <textarea v-model="mealPlanForm.note" rows="3"></textarea>
        </label>

        <p v-if="mealPlanMessage" class="success-message">{{ mealPlanMessage }}</p>
        <p v-if="mealPlanError" class="error-message">{{ mealPlanError }}</p>

        <div class="actions-row">
          <button class="btn-primary" type="submit">{{ editingMealPlanId ? 'Zapisz plan' : 'Dodaj plan' }}</button>
          <button type="button" @click="resetMealPlanForm">Reset</button>
          <button v-if="editingMealPlanId" type="button" @click="removeMealPlan">Usun plan</button>
        </div>
      </form>

      <div v-if="activeMealPlan" class="entries-block">
        <h3>Pozycje planu: {{ activeMealPlan.name }}</h3>
        <p class="muted">Format linii: data|slot|recipe_id|custom_name|servings|note</p>
        <p class="muted">slot: breakfast, lunch, dinner, snack</p>

        <textarea v-model="entriesText" rows="10"></textarea>

        <div class="actions-row">
          <button class="btn-primary" type="button" @click="saveEntries">Zapisz pozycje</button>
        </div>
      </div>
    </article>

    <article class="surface-card section-stack">
      <div class="section-header">
        <h1>Listy zakupowe</h1>
        <p class="muted">Lista moze byc podlaczona do planu okresu.</p>
      </div>

      <div class="list-block">
        <h2>Listy</h2>
        <ul class="list">
          <li v-for="list in shoppingLists" :key="list.id">
            <button class="link" @click="selectShoppingList(list.id)">{{ list.name }}</button>
            <span class="muted">{{ list.status }} | {{ list.checked_count }}/{{ list.items_count }}</span>
          </li>
        </ul>
      </div>

      <form class="form-grid" @submit.prevent="saveShoppingList">
        <h3>{{ editingShoppingListId ? 'Edycja listy' : 'Nowa lista' }}</h3>

        <label>
          Nazwa
          <input v-model="shoppingListForm.name" required />
        </label>

        <div class="grid-two">
          <label>
            Status
            <select v-model="shoppingListForm.status">
              <option value="open">open</option>
              <option value="archived">archived</option>
            </select>
          </label>

          <label>
            Powiazany plan
            <select v-model="shoppingListForm.meal_plan_id">
              <option value="">Brak</option>
              <option v-for="plan in mealPlans" :key="plan.id" :value="String(plan.id)">{{ plan.name }}</option>
            </select>
          </label>
        </div>

        <label>
          Notatka
          <textarea v-model="shoppingListForm.note" rows="3"></textarea>
        </label>

        <p v-if="shoppingListMessage" class="success-message">{{ shoppingListMessage }}</p>
        <p v-if="shoppingListError" class="error-message">{{ shoppingListError }}</p>

        <div class="actions-row">
          <button class="btn-primary" type="submit">{{ editingShoppingListId ? 'Zapisz liste' : 'Dodaj liste' }}</button>
          <button type="button" @click="resetShoppingListForm">Reset</button>
          <button v-if="editingShoppingListId" type="button" @click="removeShoppingList">Usun liste</button>
        </div>
      </form>

      <div v-if="activeShoppingList" class="items-block">
        <h3>Pozycje: {{ activeShoppingList.name }}</h3>

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
            <button type="button" @click="removeShoppingListItem(item.id)">Usun</button>
          </li>
        </ul>

        <form class="form-grid" @submit.prevent="addItemToShoppingList">
          <h4>Dodaj pozycje</h4>

          <label>
            Produkt z katalogu
            <select v-model="shoppingItemForm.product_id">
              <option value="">Wybierz produkt</option>
              <option v-for="product in products" :key="product.id" :value="String(product.id)">{{ product.name }}</option>
            </select>
          </label>

          <label>
            Lub nazwa reczna
            <input v-model="shoppingItemForm.custom_name" placeholder="np. Pomidor koktajlowy" />
          </label>

          <div class="grid-two">
            <label>
              Ilosc
              <input v-model="shoppingItemForm.quantity" type="number" min="0" step="0.01" />
            </label>

            <label>
              Jednostka
              <select v-model="shoppingItemForm.unit_id">
                <option value="">Brak</option>
                <option v-for="unit in units" :key="unit.id" :value="String(unit.id)">{{ unit.name }}</option>
              </select>
            </label>
          </div>

          <label>
            Notatka
            <input v-model="shoppingItemForm.note" />
          </label>

          <button class="btn-primary" type="submit">Dodaj pozycje</button>
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

const authStore = useAuthStore()
const catalogStore = useCatalogStore()
const mealPlannerStore = useMealPlannerStore()
const unitStore = useUnitStore()

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
      mealPlanMessage.value = 'Zapisano plan.'
      return
    }

    const created = await mealPlannerStore.createMealPlan(payload)
    await selectMealPlan(created.id)
    mealPlanMessage.value = 'Dodano plan.'
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? 'Nie udalo sie zapisac planu.'
  }
}

async function removeMealPlan() {
  if (!editingMealPlanId.value) {
    return
  }

  if (!confirm(`Usunac plan: ${mealPlanForm.value.name}?`)) {
    return
  }

  try {
    await mealPlannerStore.deleteMealPlan(editingMealPlanId.value)
    entriesText.value = ''
    mealPlanMessage.value = 'Plan usuniety.'
    mealPlanError.value = ''
    resetMealPlanForm(false)
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? 'Nie udalo sie usunac planu.'
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
    mealPlanMessage.value = 'Zapisano pozycje planu.'
  } catch (error) {
    mealPlanError.value = error?.response?.data?.error ?? 'Nie udalo sie zapisac pozycji planu.'
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
    meal_plan_id: shoppingListForm.value.meal_plan_id ? Number(shoppingListForm.value.meal_plan_id) : null,
  }

  try {
    if (editingShoppingListId.value) {
      const updated = await mealPlannerStore.updateShoppingList(editingShoppingListId.value, payload)
      await selectShoppingList(updated.id)
      shoppingListMessage.value = 'Zapisano liste.'
      return
    }

    const created = await mealPlannerStore.createShoppingList(payload)
    await selectShoppingList(created.id)
    shoppingListMessage.value = 'Dodano liste.'
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? 'Nie udalo sie zapisac listy.'
  }
}

async function removeShoppingList() {
  if (!editingShoppingListId.value) {
    return
  }

  if (!confirm(`Usunac liste: ${shoppingListForm.value.name}?`)) {
    return
  }

  try {
    await mealPlannerStore.deleteShoppingList(editingShoppingListId.value)
    shoppingListMessage.value = 'Lista usunieta.'
    shoppingListError.value = ''
    resetShoppingListForm(false)
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? 'Nie udalo sie usunac listy.'
  }
}

async function addItemToShoppingList() {
  if (!activeShoppingList.value) {
    return
  }

  shoppingListError.value = ''

  try {
    await mealPlannerStore.addShoppingListItem(activeShoppingList.value.id, {
      product_id: shoppingItemForm.value.product_id ? Number(shoppingItemForm.value.product_id) : null,
      custom_name: shoppingItemForm.value.custom_name || null,
      quantity: shoppingItemForm.value.quantity ? Number(shoppingItemForm.value.quantity) : null,
      unit_id: shoppingItemForm.value.unit_id ? Number(shoppingItemForm.value.unit_id) : null,
      note: shoppingItemForm.value.note,
    })

    resetShoppingItemForm()
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? 'Nie udalo sie dodac pozycji.'
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
    shoppingListError.value = error?.response?.data?.error ?? 'Nie udalo sie zmienic statusu pozycji.'
  }
}

async function removeShoppingListItem(itemId) {
  if (!activeShoppingList.value) {
    return
  }

  try {
    await mealPlannerStore.deleteShoppingListItem(activeShoppingList.value.id, itemId)
  } catch (error) {
    shoppingListError.value = error?.response?.data?.error ?? 'Nie udalo sie usunac pozycji.'
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
