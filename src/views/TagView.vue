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
      <div>
        <ul class="entity-list">
          <li v-for="tag in tags" :key="tag.id">
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

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>{{ t('tags.editTitle') }}</h2>
        <form @submit.prevent="editTag" class="form-grid">
          <label for="edit-tag-name">{{ t('tags.name') }}</label>
          <input type="text" id="edit-tag-name" v-model="editTagRef.name" required />
          <button class="button is-primary" type="submit">{{ t('tags.updateButton') }}</button>
        </form>
      </div>
    </div>

    <div v-if="isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>{{ t('tags.addTitle') }}</h2>
        <form @submit.prevent="addTag" class="form-grid">
          <label for="new-tag-name">{{ t('tags.name') }}</label>
          <input type="text" id="new-tag-name" v-model="newTagRef.name" required />
          <button class="button is-primary" type="submit">{{ t('tags.addSubmit') }}</button>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useTagStore } from '@stores/tagsStore.js'
import { useAuthStore } from '@stores/authStore'
import { useI18n } from '../composables/useI18n'

const tagStore = useTagStore()
const authStore = useAuthStore()
const { t } = useI18n()

const isEditModalVisible = ref(false)
const isAddModalVisible = ref(false)
const newTagRef = ref({ name: '' })
const editTagRef = ref({ id: undefined, name: '' })

const tags = computed(() => tagStore.tags)
const canWrite = computed(() => authStore.can('catalog.write'))

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
</style>
