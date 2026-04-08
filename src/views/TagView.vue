<template>
  <section class="surface-card elements">
    <CatalogSectionNav />

    <div>
      <h1 class="title is-4">{{ t('tags.title') }}</h1>
    </div>
    <div class="elements_list">
      <div>
        <h2 class="title is-5">{{ t('tags.listTitle') }}</h2>
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
          <li v-for="tag in filteredAndSortedTags" :key="tag.id">
            <div class="element_name">{{ tag.name }}</div>
            <div v-if="canWrite" class="element_edit">
              <button class="button is-small" @click="showEditModal(tag)">
                {{ t('common.edit') }}
              </button>
            </div>
            <div v-if="canWrite" class="element_delete">
              <button class="button is-small" @click="confirmDeleteTag(tag)">
                {{ t('common.delete') }}
              </button>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <div v-if="canWrite" class="add_tag">
      <div>
        <button class="button is-primary" @click="showAddModal">{{ t('tags.addButton') }}</button>
      </div>
    </div>

    <div v-if="isEditModalVisible">
      <AppModal
        :title="t('tags.editTitle')"
        :close-label="t('common.close')"
        width="500px"
        @close="closeEditModal"
      >
        <form @submit.prevent="editTag" class="form-grid">
          <label for="edit-tag-name">{{ t('tags.name') }}</label>
          <input type="text" id="edit-tag-name" v-model="editTagRef.name" required />
          <button class="button is-primary" type="submit">{{ t('tags.updateButton') }}</button>
        </form>
      </AppModal>
    </div>

    <div v-if="isAddModalVisible">
      <AppModal
        :title="t('tags.addTitle')"
        :close-label="t('common.close')"
        width="500px"
        @close="closeAddModal"
      >
        <form @submit.prevent="addTag" class="form-grid">
          <label for="new-tag-name">{{ t('tags.name') }}</label>
          <input type="text" id="new-tag-name" v-model="newTagRef.name" required />
          <button class="button is-primary" type="submit">{{ t('tags.addSubmit') }}</button>
        </form>
      </AppModal>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import AppModal from '../components/shared/AppModal.vue'
import { useTagStore } from '@stores/tagsStore.js'
import { useAuthStore } from '@stores/authStore'
import { useI18n } from '../composables/useI18n'
import { filterBySearch, sortByField } from '../utils/listUtils'

const tagStore = useTagStore()
const authStore = useAuthStore()
const { t } = useI18n()

const isEditModalVisible = ref(false)
const isAddModalVisible = ref(false)
const newTagRef = ref({ name: '' })
const editTagRef = ref({ id: undefined, name: '' })
const search = ref('')
const sortDirection = ref('asc')

const tags = computed(() => tagStore.tags)
const canWrite = computed(() => authStore.can('catalog.write'))

const filteredAndSortedTags = computed(() => {
  const filtered = filterBySearch(tags.value, search.value, (tag) => tag.name)
  return sortByField(filtered, 'name', sortDirection.value)
})

onMounted(async () => {
  await tagStore.fetchTags()
})

function showAddModal() {
  newTagRef.value = { name: '' }
  isAddModalVisible.value = true
}

function closeAddModal() {
  isAddModalVisible.value = false
}

async function addTag() {
  await tagStore.addTag(newTagRef.value)
  closeAddModal()
}

function showEditModal(tag) {
  editTagRef.value = { id: tag.id, name: tag.name }
  isEditModalVisible.value = true
}

function closeEditModal() {
  isEditModalVisible.value = false
}

async function editTag() {
  await tagStore.updateTag(editTagRef.value)
  closeEditModal()
}

async function deleteTag(tag) {
  await tagStore.deleteTag(tag)
}

function confirmDeleteTag(tag) {
  if (confirm(t('tags.deleteConfirm', { name: tag.name }))) {
    deleteTag(tag)
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

@media (min-width: 760px) {
  .toolbar-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
