<template>
  <section class="surface-card ingredients">
    <CatalogSectionNav />

    <div class="section-header">
      <h1 class="title is-4">{{ t('ingredients.title') }}</h1>
      <p class="muted">{{ t('ingredients.nutritionBasis') }}</p>
    </div>

    <div class="toolbar-grid">
      <label>
        {{ t('catalog.searchProduct') }}
        <input v-model="search" type="text" class="input" />
      </label>

      <label>
        {{ t('common.sortBy') }}
        <select v-model="sortBy" class="input">
          <option value="name">{{ t('ingredients.name') }}</option>
          <option value="comment">{{ t('ingredients.comment') }}</option>
          <option value="unit">{{ t('ingredients.unit') }}</option>
          <option value="package">{{ t('ingredients.package') }}</option>
          <option value="quantity_per_package">{{ t('ingredients.quantityPerPackage') }}</option>
          <option value="unit_to_ml">{{ t('ingredients.unitToMl') }}</option>
          <option value="calories_per_100g">{{ t('ingredients.calories') }}</option>
          <option value="carbohydrates_per_100g">{{ t('ingredients.carbohydrates') }}</option>
          <option value="sugars_per_100g">{{ t('ingredients.sugars') }}</option>
          <option value="fat_per_100g">{{ t('ingredients.fat') }}</option>
          <option value="protein_per_100g">{{ t('ingredients.protein') }}</option>
          <option value="fiber_per_100g">{{ t('ingredients.fiber') }}</option>
          <option value="tags">{{ t('ingredients.tags') }}</option>
        </select>
      </label>

      <label>
        {{ t('common.sortOrder') }}
        <select v-model="sortDirection" class="input">
          <option value="asc">{{ t('common.sortAsc') }}</option>
          <option value="desc">{{ t('common.sortDesc') }}</option>
        </select>
      </label>
    </div>

    <div class="table-wrapper">
      <table
        v-if="filteredAndSortedIngredients.length > 0"
        class="table is-striped is-hoverable is-fullwidth is-size-7-mobile"
      >
        <thead>
          <tr>
            <th>{{ t('ingredients.name') }}</th>
            <th>{{ t('ingredients.comment') }}</th>
            <th>{{ t('ingredients.unit') }}</th>
            <th>{{ t('ingredients.package') }}</th>
            <th>{{ t('ingredients.quantityPerPackage') }}</th>
            <th>{{ t('ingredients.unitToMl') }}</th>
            <th>{{ t('ingredients.calories') }}</th>
            <th>{{ t('ingredients.carbohydrates') }}</th>
            <th>{{ t('ingredients.sugars') }}</th>
            <th>{{ t('ingredients.fat') }}</th>
            <th>{{ t('ingredients.protein') }}</th>
            <th>{{ t('ingredients.fiber') }}</th>
            <th>{{ t('ingredients.tags') }}</th>
            <th>{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ingredient in filteredAndSortedIngredients" :key="ingredient.id">
            <td>{{ ingredient.name }}</td>
            <td>{{ ingredient.comment || '-' }}</td>
            <td>{{ getUnitName(ingredient.unit_id) }}</td>
            <td>{{ ingredient.package_type_name || '-' }}</td>
            <td>{{ formatQuantityPerPackage(ingredient) }}</td>
            <td>{{ ingredient.unit_to_ml ?? '-' }}</td>
            <td>{{ ingredient.calories_per_100g ?? '-' }}</td>
            <td>{{ ingredient.carbohydrates_per_100g ?? '-' }}</td>
            <td>{{ ingredient.sugars_per_100g ?? '-' }}</td>
            <td>{{ ingredient.fat_per_100g ?? '-' }}</td>
            <td>{{ ingredient.protein_per_100g ?? '-' }}</td>
            <td>{{ ingredient.fiber_per_100g ?? '-' }}</td>
            <td>{{ getTagName(ingredient.tag_id) }}</td>
            <td>
              <template v-if="canWrite">
                <button class="button is-small" @click="showEditModal(ingredient)">
                  {{ t('common.edit') }}
                </button>
                <button class="button is-small" @click="confirmDelete(ingredient)">
                  {{ t('common.delete') }}
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>

      <p v-else class="muted">{{ t('common.noData') }}</p>
    </div>

    <div v-if="canWrite" class="add_ingredient">
      <button class="button is-primary" @click="showAddModal">
        {{ t('ingredients.addButton') }}
      </button>
    </div>
  </section>

  <div v-if="canWrite && isEditModalVisible" class="modal">
    <div class="modal-content">
      <span class="close" @click="closeEditModal">&times;</span>
      <h2>{{ t('ingredients.editTitle') }}</h2>
      <form class="form-grid" @submit.prevent="editIngredient">
        <label>
          {{ t('ingredients.name') }}
          <input type="text" v-model="editIngredientRef.name" required />
        </label>
        <label>
          {{ t('ingredients.comment') }}
          <input type="text" v-model="editIngredientRef.comment" />
        </label>
        <label>
          {{ t('ingredients.unit') }}
          <select v-model="editIngredientRef.unit_id" required>
            <option value="" disabled>{{ t('ingredients.selectUnit') }}</option>
            <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
          </select>
        </label>
        <label>
          {{ t('ingredients.package') }}
          <select v-model="editIngredientRef.package_type_id">
            <option :value="null">{{ t('ingredients.selectPackage') }}</option>
            <option v-for="pkg in packageTypes" :key="pkg.id" :value="pkg.id">
              {{ pkg.name }}
            </option>
          </select>
        </label>
        <label>
          {{ t('ingredients.quantityPerPackage') }}
          <input
            type="number"
            step="0.01"
            min="0"
            v-model="editIngredientRef.quantity_per_package"
          />
        </label>
        <label>
          {{ t('ingredients.unitToMl') }}
          <input type="number" step="0.01" min="0" v-model="editIngredientRef.unit_to_ml" />
        </label>
        <label>
          {{ t('ingredients.calories') }}
          <input type="number" step="0.01" min="0" v-model="editIngredientRef.calories_per_100g" />
        </label>
        <label>
          {{ t('ingredients.carbohydrates') }}
          <input
            type="number"
            step="0.01"
            min="0"
            v-model="editIngredientRef.carbohydrates_per_100g"
          />
        </label>
        <label>
          {{ t('ingredients.sugars') }}
          <input type="number" step="0.01" min="0" v-model="editIngredientRef.sugars_per_100g" />
        </label>
        <label>
          {{ t('ingredients.fat') }}
          <input type="number" step="0.01" min="0" v-model="editIngredientRef.fat_per_100g" />
        </label>
        <label>
          {{ t('ingredients.protein') }}
          <input type="number" step="0.01" min="0" v-model="editIngredientRef.protein_per_100g" />
        </label>
        <label>
          {{ t('ingredients.fiber') }}
          <input type="number" step="0.01" min="0" v-model="editIngredientRef.fiber_per_100g" />
        </label>

        <div>
          <p>{{ t('ingredients.tags') }}</p>
          <label v-for="tag in tags" :key="`edit-${tag.id}`" class="checkbox-line">
            <input type="checkbox" :value="tag.id" v-model="editTagRef" />
            <span>{{ tag.name }}</span>
          </label>
        </div>

        <button class="button is-primary" type="submit">{{ t('ingredients.submitEdit') }}</button>
      </form>
    </div>
  </div>

  <div v-if="canWrite && isAddModalVisible" class="modal">
    <div class="modal-content">
      <span class="close" @click="closeAddModal">&times;</span>
      <h2>{{ t('ingredients.addTitle') }}</h2>
      <form class="form-grid" @submit.prevent="addIngredient">
        <label>
          {{ t('ingredients.name') }}
          <input type="text" v-model="addIngredientRef.name" required />
        </label>
        <label>
          {{ t('ingredients.comment') }}
          <input type="text" v-model="addIngredientRef.comment" />
        </label>
        <label>
          {{ t('ingredients.unit') }}
          <select v-model="addIngredientRef.unit_id" required>
            <option value="" disabled>{{ t('ingredients.selectUnit') }}</option>
            <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
          </select>
        </label>
        <label>
          {{ t('ingredients.package') }}
          <select v-model="addIngredientRef.package_type_id">
            <option :value="null">{{ t('ingredients.selectPackage') }}</option>
            <option v-for="pkg in packageTypes" :key="pkg.id" :value="pkg.id">
              {{ pkg.name }}
            </option>
          </select>
        </label>
        <label>
          {{ t('ingredients.quantityPerPackage') }}
          <input
            type="number"
            step="0.01"
            min="0"
            v-model="addIngredientRef.quantity_per_package"
          />
        </label>
        <label>
          {{ t('ingredients.unitToMl') }}
          <input type="number" step="0.01" min="0" v-model="addIngredientRef.unit_to_ml" />
        </label>
        <label>
          {{ t('ingredients.calories') }}
          <input type="number" step="0.01" min="0" v-model="addIngredientRef.calories_per_100g" />
        </label>
        <label>
          {{ t('ingredients.carbohydrates') }}
          <input
            type="number"
            step="0.01"
            min="0"
            v-model="addIngredientRef.carbohydrates_per_100g"
          />
        </label>
        <label>
          {{ t('ingredients.sugars') }}
          <input type="number" step="0.01" min="0" v-model="addIngredientRef.sugars_per_100g" />
        </label>
        <label>
          {{ t('ingredients.fat') }}
          <input type="number" step="0.01" min="0" v-model="addIngredientRef.fat_per_100g" />
        </label>
        <label>
          {{ t('ingredients.protein') }}
          <input type="number" step="0.01" min="0" v-model="addIngredientRef.protein_per_100g" />
        </label>
        <label>
          {{ t('ingredients.fiber') }}
          <input type="number" step="0.01" min="0" v-model="addIngredientRef.fiber_per_100g" />
        </label>

        <div>
          <p>{{ t('ingredients.tags') }}</p>
          <label v-for="tag in tags" :key="`add-${tag.id}`" class="checkbox-line">
            <input type="checkbox" :value="tag.id" v-model="addTagRef" />
            <span>{{ tag.name }}</span>
          </label>
        </div>

        <button class="button is-primary" type="submit">{{ t('ingredients.submitAdd') }}</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useIngredientStore } from '@stores/ingredientsStore'
import { useUnitStore } from '@stores/unitsStore'
import { useTagStore } from '@stores/tagsStore'
import { usePackagesStore } from '../stores/packagesStore'
import { useAuthStore } from '@stores/authStore'
import { useI18n } from '../composables/useI18n'

const ingredientStore = useIngredientStore()
const unitStore = useUnitStore()
const tagStore = useTagStore()
const packagesStore = usePackagesStore()
const authStore = useAuthStore()
const { t } = useI18n()

const isEditModalVisible = ref(false)
const isAddModalVisible = ref(false)
const search = ref('')
const sortBy = ref('name')
const sortDirection = ref('asc')

const initialIngredientRef = {
  name: '',
  comment: '',
  unit_id: '',
  package_type_id: null,
  quantity_per_package: '',
  unit_to_ml: '',
  calories_per_100g: '',
  carbohydrates_per_100g: '',
  sugars_per_100g: '',
  fat_per_100g: '',
  protein_per_100g: '',
  fiber_per_100g: '',
}

const addIngredientRef = ref({ ...initialIngredientRef })
const editIngredientRef = ref({ ...initialIngredientRef, id: undefined })
const addTagRef = ref([])
const editTagRef = ref([])

const ingredients = computed(() => ingredientStore.ingredients)
const units = computed(() => unitStore.units)
const tags = computed(() => tagStore.tags)
const packageTypes = computed(() => packagesStore.packageTypes)
const canWrite = computed(() => authStore.can('catalog.write'))

function normalizeSearch(value) {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

const filteredAndSortedIngredients = computed(() => {
  const needle = normalizeSearch(search.value)
  const direction = sortDirection.value === 'desc' ? -1 : 1

  const filtered = ingredients.value.filter((ingredient) => {
    if (!needle) {
      return true
    }

    const searchable = [
      ingredient.name,
      ingredient.comment,
      getUnitName(ingredient.unit_id),
      ingredient.package_type_name,
      getTagName(ingredient.tag_id),
    ]
      .filter(Boolean)
      .join(' | ')

    return normalizeSearch(searchable).includes(needle)
  })

  return [...filtered].sort((left, right) => {
    let leftValue = ''
    let rightValue = ''

    if (sortBy.value === 'unit') {
      leftValue = getUnitName(left.unit_id)
      rightValue = getUnitName(right.unit_id)
    } else if (sortBy.value === 'package') {
      leftValue = left.package_type_name ?? ''
      rightValue = right.package_type_name ?? ''
    } else if (sortBy.value === 'tags') {
      leftValue = getTagName(left.tag_id)
      rightValue = getTagName(right.tag_id)
    } else {
      leftValue = left[sortBy.value] ?? ''
      rightValue = right[sortBy.value] ?? ''
    }

    const leftNumber = Number(leftValue)
    const rightNumber = Number(rightValue)
    const numbersComparable = Number.isFinite(leftNumber) && Number.isFinite(rightNumber)

    if (numbersComparable) {
      if (leftNumber === rightNumber) {
        return 0
      }
      return leftNumber > rightNumber ? direction : -direction
    }

    return (
      String(leftValue).localeCompare(String(rightValue), undefined, {
        sensitivity: 'base',
        numeric: true,
      }) * direction
    )
  })
})

onMounted(async () => {
  await Promise.all([
    unitStore.fetchUnits(),
    tagStore.fetchTags(),
    ingredientStore.fetchIngredients(),
    packagesStore.fetchPackageTypes(),
  ])
})

function normalizeNumericFields(payload) {
  const numericKeys = [
    'unit_id',
    'package_type_id',
    'quantity_per_package',
    'unit_to_ml',
    'calories_per_100g',
    'carbohydrates_per_100g',
    'sugars_per_100g',
    'fat_per_100g',
    'protein_per_100g',
    'fiber_per_100g',
  ]

  numericKeys.forEach((key) => {
    const value = payload[key]

    if (value === '' || value === null || value === undefined) {
      payload[key] = null
      return
    }

    const parsed = Number(value)
    payload[key] = Number.isFinite(parsed) ? parsed : null
  })

  return payload
}

function getUnitName(unitId) {
  const unit = units.value.find((item) => item.id === unitId)
  return unit ? unit.name : t('ingredients.unknown')
}

function getTagName(tagIds) {
  if (!Array.isArray(tagIds) || tagIds.length === 0) {
    return '-'
  }

  const names = tagIds
    .map((tagId) => tags.value.find((tag) => tag.id === tagId)?.name)
    .filter(Boolean)

  return names.length > 0 ? names.join(', ') : '-'
}

function formatQuantityPerPackage(ingredient) {
  if (ingredient.quantity_per_package === null || ingredient.quantity_per_package === undefined) {
    return '-'
  }

  return `${ingredient.quantity_per_package} ${getUnitName(ingredient.unit_id)}`
}

function showAddModal() {
  addIngredientRef.value = { ...initialIngredientRef }
  addTagRef.value = []
  isAddModalVisible.value = true
}

function closeAddModal() {
  isAddModalVisible.value = false
}

function showEditModal(ingredient) {
  editIngredientRef.value = {
    ...initialIngredientRef,
    ...ingredient,
    package_type_id: ingredient.package_type_id ?? null,
  }
  editTagRef.value = Array.isArray(ingredient.tag_id) ? [...ingredient.tag_id] : []
  isEditModalVisible.value = true
}

function closeEditModal() {
  isEditModalVisible.value = false
}

async function addIngredient() {
  const payload = normalizeNumericFields({
    ...addIngredientRef.value,
    tag_id: addTagRef.value,
  })

  await ingredientStore.addIngredient(payload)
  closeAddModal()
}

async function editIngredient() {
  const payload = normalizeNumericFields({
    ...editIngredientRef.value,
    tag_id: editTagRef.value,
  })

  await ingredientStore.updateIngredient(payload)
  closeEditModal()
}

async function deleteIngredient(ingredient) {
  await ingredientStore.deleteIngredient(ingredient)
}

function confirmDelete(ingredient) {
  if (confirm(t('ingredients.deleteConfirm', { name: ingredient.name }))) {
    deleteIngredient(ingredient)
  }
}
</script>

<style scoped>
.ingredients {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 1rem;
}

.section-header {
  display: grid;
  gap: 0.35rem;
}

.toolbar-grid {
  display: grid;
  gap: 0.65rem;
}

.table-wrapper {
  overflow-x: auto;
}

.add_ingredient {
  display: flex;
  justify-content: flex-start;
}

.modal {
  display: flex;
  justify-content: center;
  align-items: center;
  position: fixed;
  z-index: 60;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  overflow: auto;
  background-color: rgba(0, 0, 0, 0.4);
}

.modal-content {
  background-color: var(--app-surface);
  color: var(--app-text);
  padding: 20px;
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
  width: min(640px, calc(100% - 1.5rem));
}

.close {
  color: #aaa;
  float: right;
  font-size: 28px;
  font-weight: bold;
}

.close:hover,
.close:focus {
  color: black;
  text-decoration: none;
  cursor: pointer;
}

@media (min-width: 900px) {
  .toolbar-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
