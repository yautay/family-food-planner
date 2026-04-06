<script setup>
import { computed, onMounted, ref } from 'vue'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { usePackagesStore } from '../stores/packagesStore'
import { useIngredientStore } from '../stores/ingredientsStore'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const packagesStore = usePackagesStore()
const ingredientStore = useIngredientStore()
const authStore = useAuthStore()
const { t } = useI18n()

const isEditModalVisible = ref(false)
const isAddModalVisible = ref(false)
const search = ref('')
const sortBy = ref('product_name')
const sortDirection = ref('asc')

const initialPayload = {
  product_id: '',
  package_type_id: '',
  package_type_name: '',
  grams_per_package: '',
  source: 'manual',
}

const addRef = ref({ ...initialPayload })
const editRef = ref({ ...initialPayload, id: undefined })

const packageRows = computed(() => packagesStore.packages)
const packageTypes = computed(() => packagesStore.packageTypes)
const ingredients = computed(() => ingredientStore.ingredients)
const canWrite = computed(() => authStore.can('catalog.write'))

const filteredAndSortedRows = computed(() => {
  const needle = search.value.trim().toLowerCase()
  const direction = sortDirection.value === 'desc' ? -1 : 1

  const filtered = packageRows.value.filter((row) => {
    if (!needle) {
      return true
    }

    const searchable = [row.product_name, row.package_type_name, row.source]
      .filter(Boolean)
      .join(' | ')
      .toLowerCase()

    return searchable.includes(needle)
  })

  return [...filtered].sort((left, right) => {
    const leftValue = left[sortBy.value] ?? ''
    const rightValue = right[sortBy.value] ?? ''

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

function normalizePayload(payload) {
  const toNullableNumber = (value) => {
    if (value === '' || value === null || value === undefined) {
      return null
    }

    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  return {
    ...payload,
    product_id: toNullableNumber(payload.product_id),
    package_type_id: toNullableNumber(payload.package_type_id),
    grams_per_package: toNullableNumber(payload.grams_per_package),
    package_type_name:
      typeof payload.package_type_name === 'string' ? payload.package_type_name.trim() : '',
    source: typeof payload.source === 'string' ? payload.source.trim() : 'manual',
  }
}

function showAddModal() {
  addRef.value = { ...initialPayload }
  isAddModalVisible.value = true
}

function closeAddModal() {
  isAddModalVisible.value = false
}

function showEditModal(row) {
  editRef.value = {
    id: row.id,
    product_id: row.product_id,
    package_type_id: row.package_type_id,
    package_type_name: row.package_type_name,
    grams_per_package: row.grams_per_package,
    source: row.source || 'manual',
  }
  isEditModalVisible.value = true
}

function closeEditModal() {
  isEditModalVisible.value = false
}

async function addMapping() {
  await packagesStore.addPackage(normalizePayload(addRef.value))
  await packagesStore.fetchPackageTypes()
  closeAddModal()
}

async function editMapping() {
  await packagesStore.updatePackage(normalizePayload(editRef.value))
  await packagesStore.fetchPackageTypes()
  closeEditModal()
}

async function deleteMapping(row) {
  await packagesStore.deletePackage(row)
}

function confirmDelete(row) {
  const label = `${row.product_name} / ${row.package_type_name}`
  if (confirm(t('packages.deleteConfirm', { name: label }))) {
    deleteMapping(row)
  }
}

onMounted(async () => {
  await Promise.all([
    packagesStore.fetchPackages(),
    packagesStore.fetchPackageTypes(),
    ingredientStore.fetchIngredients(),
  ])
})
</script>

<template>
  <section class="surface-card elements">
    <CatalogSectionNav />

    <div class="section-header">
      <h1 class="title is-4">{{ t('packages.title') }}</h1>
      <p class="muted">{{ t('packages.description') }}</p>
    </div>

    <h2 class="title is-5">{{ t('packages.listTitle') }}</h2>

    <div class="toolbar-grid">
      <label>
        {{ t('catalog.searchProduct') }}
        <input v-model="search" type="text" class="input" />
      </label>

      <label>
        {{ t('common.sortBy') }}
        <select v-model="sortBy" class="input">
          <option value="product_name">{{ t('packages.ingredientColumn') }}</option>
          <option value="package_type_name">{{ t('packages.typeColumn') }}</option>
          <option value="grams_per_package">{{ t('packages.gramsPerPackage') }}</option>
          <option value="samples_count">{{ t('packages.samplesCount') }}</option>
          <option value="source">{{ t('packages.source') }}</option>
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

    <div class="table-wrapper" v-if="filteredAndSortedRows.length > 0">
      <table class="table is-fullwidth is-hoverable is-striped is-size-7-mobile">
        <thead>
          <tr>
            <th>{{ t('packages.ingredientColumn') }}</th>
            <th>{{ t('packages.typeColumn') }}</th>
            <th>{{ t('packages.gramsPerPackage') }}</th>
            <th>{{ t('packages.samplesCount') }}</th>
            <th>{{ t('packages.source') }}</th>
            <th v-if="canWrite">{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredAndSortedRows" :key="row.id">
            <td>{{ row.product_name }}</td>
            <td>{{ row.package_type_name }}</td>
            <td>{{ row.grams_per_package }}</td>
            <td>{{ row.samples_count }}</td>
            <td>{{ row.source || '-' }}</td>
            <td v-if="canWrite" class="actions-cell">
              <button class="button is-small" @click="showEditModal(row)">
                {{ t('common.edit') }}
              </button>
              <button class="button is-small" @click="confirmDelete(row)">
                {{ t('common.delete') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-else class="muted">{{ t('packages.empty') }}</p>

    <div v-if="canWrite" class="actions-row">
      <button class="button is-primary" @click="showAddModal">{{ t('packages.addButton') }}</button>
    </div>

    <div v-if="canWrite && isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>{{ t('packages.addTitle') }}</h2>

        <form class="form-grid" @submit.prevent="addMapping">
          <label>
            {{ t('packages.ingredientColumn') }}
            <select v-model="addRef.product_id" required>
              <option value="" disabled>{{ t('packages.selectIngredient') }}</option>
              <option v-for="ingredient in ingredients" :key="ingredient.id" :value="ingredient.id">
                {{ ingredient.name }}
              </option>
            </select>
          </label>

          <label>
            {{ t('packages.typeColumn') }}
            <select v-model="addRef.package_type_id">
              <option value="">{{ t('packages.manualTypeName') }}</option>
              <option v-for="item in packageTypes" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
            </select>
          </label>

          <label v-if="!addRef.package_type_id">
            {{ t('packages.typeName') }}
            <input type="text" v-model="addRef.package_type_name" required />
          </label>

          <label>
            {{ t('packages.gramsPerPackage') }}
            <input
              type="number"
              step="0.01"
              min="0.01"
              v-model="addRef.grams_per_package"
              required
            />
          </label>

          <label>
            {{ t('packages.source') }}
            <input type="text" v-model="addRef.source" />
          </label>

          <button class="button is-primary" type="submit">{{ t('packages.addSubmit') }}</button>
        </form>
      </div>
    </div>

    <div v-if="canWrite && isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>{{ t('packages.editTitle') }}</h2>

        <form class="form-grid" @submit.prevent="editMapping">
          <label>
            {{ t('packages.ingredientColumn') }}
            <select v-model="editRef.product_id" required>
              <option value="" disabled>{{ t('packages.selectIngredient') }}</option>
              <option v-for="ingredient in ingredients" :key="ingredient.id" :value="ingredient.id">
                {{ ingredient.name }}
              </option>
            </select>
          </label>

          <label>
            {{ t('packages.typeColumn') }}
            <select v-model="editRef.package_type_id">
              <option value="">{{ t('packages.manualTypeName') }}</option>
              <option v-for="item in packageTypes" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
            </select>
          </label>

          <label v-if="!editRef.package_type_id">
            {{ t('packages.typeName') }}
            <input type="text" v-model="editRef.package_type_name" required />
          </label>

          <label>
            {{ t('packages.gramsPerPackage') }}
            <input
              type="number"
              step="0.01"
              min="0.01"
              v-model="editRef.grams_per_package"
              required
            />
          </label>

          <label>
            {{ t('packages.source') }}
            <input type="text" v-model="editRef.source" />
          </label>

          <button class="button is-primary" type="submit">{{ t('packages.updateButton') }}</button>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.elements {
  display: grid;
  gap: 0.9rem;
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
  width: 100%;
  overflow-x: auto;
}

.actions-row {
  display: flex;
  justify-content: flex-start;
}

.actions-cell {
  display: flex;
  gap: 0.35rem;
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
  width: min(560px, calc(100% - 1.5rem));
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
