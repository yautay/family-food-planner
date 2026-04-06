<template>
  <section class="surface-card elements">
    <CatalogSectionNav />

    <div>
      <h1 class="title is-4">{{ t('units.title') }}</h1>
    </div>
    <div class="elements_list">
      <div>
        <h2 class="title is-5">{{ t('units.listTitle') }}</h2>
      </div>
      <div class="toolbar-grid">
        <label>
          {{ t('catalog.searchProduct') }}
          <input v-model="search" class="input" type="text" />
        </label>
        <label>
          {{ t('common.sortOrder') }}
          <select v-model="sortDirection" class="input">
            <option value="asc">{{ t('common.sortAsc') }}</option>
            <option value="desc">{{ t('common.sortDesc') }}</option>
          </select>
        </label>
      </div>
      <div>
        <ul class="entity-list">
          <li v-for="unit in filteredAndSortedUnits" :key="unit.id">
            <div class="element_name">{{ unit.name }}</div>
            <div v-if="canWrite" class="element_edit">
              <button class="button is-small" @click="showEditModal(unit)">
                {{ t('common.edit') }}
              </button>
            </div>
            <div v-if="canWrite" class="element_delete">
              <button class="button is-small" @click="confirmDeleteUnit(unit)">
                {{ t('common.delete') }}
              </button>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <div v-if="canWrite" class="add_unit">
      <div>
        <button class="button is-primary" @click="showAddModal">{{ t('units.addButton') }}</button>
      </div>
    </div>

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>{{ t('units.editTitle') }}</h2>
        <form @submit.prevent="editUnit" class="form-grid">
          <label for="edit-unit-name">{{ t('units.name') }}</label>
          <input type="text" id="edit-unit-name" v-model="editUnitRef.name" required />
          <button class="button is-primary" type="submit">{{ t('units.updateButton') }}</button>
        </form>
      </div>
    </div>

    <div v-if="isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>{{ t('units.addTitle') }}</h2>
        <form @submit.prevent="addUnit" class="form-grid">
          <label for="new-unit-name">{{ t('units.name') }}</label>
          <input type="text" id="new-unit-name" v-model="newUnitRef.name" required />
          <button class="button is-primary" type="submit">{{ t('units.addSubmit') }}</button>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useUnitStore } from '@stores/unitsStore'
import { useAuthStore } from '@stores/authStore'
import { useI18n } from '../composables/useI18n'

const unitStore = useUnitStore()
const authStore = useAuthStore()
const { t } = useI18n()

const isEditModalVisible = ref(false)
const isAddModalVisible = ref(false)
const newUnitRef = ref({ name: '' })
const editUnitRef = ref({ id: undefined, name: '' })
const search = ref('')
const sortDirection = ref('asc')

const units = computed(() => unitStore.units)
const canWrite = computed(() => authStore.can('catalog.write'))

const filteredAndSortedUnits = computed(() => {
  const needle = search.value.trim().toLowerCase()
  const direction = sortDirection.value === 'desc' ? -1 : 1

  return [...units.value]
    .filter((unit) => unit.name.toLowerCase().includes(needle))
    .sort(
      (left, right) =>
        left.name.localeCompare(right.name, undefined, { sensitivity: 'base', numeric: true }) *
        direction,
    )
})

onMounted(async () => {
  await unitStore.fetchUnits()
})

function showAddModal() {
  newUnitRef.value = { name: '' }
  isAddModalVisible.value = true
}

function closeAddModal() {
  isAddModalVisible.value = false
}

async function addUnit() {
  await unitStore.addUnit(newUnitRef.value)
  closeAddModal()
}

function showEditModal(unit) {
  editUnitRef.value = { id: unit.id, name: unit.name }
  isEditModalVisible.value = true
}

function closeEditModal() {
  isEditModalVisible.value = false
}

async function editUnit() {
  await unitStore.updateUnit(editUnitRef.value)
  closeEditModal()
}

async function deleteUnit(unit) {
  await unitStore.deleteUnit(unit)
}

function confirmDeleteUnit(unit) {
  if (confirm(t('units.deleteConfirm', { name: unit.name }))) {
    deleteUnit(unit)
  }
}
</script>

<style scoped>
.elements {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 1rem;
}

.entity-list {
  list-style-type: none;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.entity-list li {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--app-border);
  padding-bottom: 0.45rem;
}

.element_name {
  flex: 1;
  min-width: 180px;
}

.toolbar-grid {
  display: grid;
  gap: 0.65rem;
}

button {
  cursor: pointer;
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
  width: min(500px, calc(100% - 1.5rem));
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

@media (min-width: 760px) {
  .toolbar-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
