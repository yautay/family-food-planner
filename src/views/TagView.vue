<template>
  <section class="surface-card elements">
    <div><h1 class="title is-4">Tags</h1></div>
    <div class="elements_list">
      <div><h2 class="title is-5">Tags list</h2></div>
      <div>
        <ul>
          <li v-for="tag in tags" :key="tag.id">
            <div class="element_name">{{ tag.name }}</div>
            <div v-if="canWrite" class="element_edit"><button class="button is-small" @click="showEditModal(tag)">Edit</button></div>
            <div v-if="canWrite" class="element_delete"><button class="button is-small" @click="confirmDeleteTag(tag)">Delete</button></div>
          </li>
        </ul>
      </div>
    </div>

    <div v-if="canWrite" class="add_tag">
      <div><button class="button is-primary" @click="showAddModal">Add TagModel</button></div>
    </div>

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>Edit TagModel</h2>
        <form @submit.prevent="editTag">
          <div>
            <label for="edit-tag-name">TagModel Name:</label>
            <input type="text" id="edit-tag-name" v-model="editTagRef.name" required />
          </div>
          <button class="button is-primary" type="submit">Update TagModel</button>
        </form>
      </div>
    </div>

    <div v-if="isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>Add TagModel</h2>
        <form @submit.prevent="addTag">
          <div>
            <label for="new-tag-name">TagModel Name:</label>
            <input type="text" id="new-tag-name" v-model="newTagRef.name" required />
          </div>
          <button class="button is-primary" type="submit">Add TagModel</button>
        </form>
      </div>
    </div>
  </section>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { useTagStore } from '@stores/tagsStore.js'
import { useAuthStore } from '@stores/authStore'

export default {
  setup() {
    const tagStore = useTagStore()
    const authStore = useAuthStore()
    var tags = ref([])
    const isEditModalVisible = ref(false)
    const isAddModalVisible = ref(false)
    const newTagRef = ref({ name: "" })
    const editTagRef = ref({ id: undefined, name: "" })

    onMounted(() => {
      fetchTags()
    })

    const fetchTags = async () => {
      try {
        await tagStore.fetchTags()
        tags.value = tagStore.tags
      } catch (error) {
        console.error('Error fetching tags:', error)
      }
    }

    const showAddModal = () => {
      newTagRef.value = { name: "" }
      isAddModalVisible.value = true
    }

    const closeAddModal = () => {
      isAddModalVisible.value = false
    }

    const addTag = async () => {
      try {
        await tagStore.addTag(newTagRef.value)
        await fetchTags()
        closeAddModal()
      } catch (error) {
        console.error('Error adding tag:', error)
      }
    }

    const showEditModal = (tag) => {
      editTagRef.value = { id: tag.id, name: "" }
      isEditModalVisible.value = true
    }

    const closeEditModal = () => {
      isEditModalVisible.value = false
    }

    const editTag = async () => {
      try {
        await tagStore.updateTag(editTagRef.value)
        await fetchTags()
        closeEditModal()
      } catch (error) {
        console.error('Error updating tags:', error)
      }
    }

    const deleteTag = async (tag) => {
      try {
        await tagStore.deleteTag(tag)
        await fetchTags()
      } catch (error) {
        console.error('Error deleting tags:', error)
      }
    }

    const confirmDeleteTag = (tag) => {
      if (confirm(`Czy jesteś pewien że chcesz skasować tag: "${tag.name}"?`)) {
        deleteTag(tag)
      }
    }

    return {
      tags,
      newTagRef,
      editTag,
      isEditModalVisible,
      isAddModalVisible,
      showEditModal,
      closeEditModal,
      editTagRef,
      showAddModal,
      closeAddModal,
      addTag,
      deleteTag,
      confirmDeleteTag,
      canWrite: computed(() => authStore.can('catalog.write')),
    }
  },
}
</script>

<style scoped>
.elements {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 1rem;
}

ul {
  list-style-type: none;
  padding: 0;
}

li {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.element_name {
  width: 150px;
}

.element_edit {
  width: 80px;
}

.element_delete {
  width: 100px;
}

button {
  cursor: pointer;
}

.modal {
  display: flex;
  justify-content: center;
  align-items: center;
  position: fixed;
  z-index: 1;
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
  width: 80%;
  max-width: 500px;
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
