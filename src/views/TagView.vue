<template>
  <div class="elements">
    <div><h1>Tags</h1></div>
    <div class="elements_list">
      <div><h2>Tags list</h2></div>
      <div>
        <ul>
          <li v-for="tag in tags" :key="tag.id">
            <div class="element_name">{{ tag.name }}</div>
            <div class="element_edit"><button @click="showEditModal(tag)">Edit</button></div>
            <div class="element_delete"><button @click="confirmDeleteTag(tag)">Delete</button></div>
          </li>
        </ul>
      </div>
    </div>

    <div class="add_tag">
      <div><button @click="showAddModal">Add Tag</button></div>
    </div>

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>Edit Tag</h2>
        <form @submit.prevent="editTag">
          <div>
            <label for="edit-tag-name">Tag Name:</label>
            <input type="text" id="edit-tag-name" v-model="editTagRef.name" required />
          </div>
          <button type="submit">Update Tag</button>
        </form>
      </div>
    </div>

    <div v-if="isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>Add Tag</h2>
        <form @submit.prevent="addTag">
          <div>
            <label for="new-tag-name">Tag Name:</label>
            <input type="text" id="new-tag-name" v-model="newTagRef.name" required />
          </div>
          <button type="submit">Add Tag</button>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useTagStore } from '@stores/tagsStore.js'

export default {
  setup() {
    const tagStore = useTagStore()
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
      confirmDeleteTag
    }
  },
}
</script>

<style scoped>
.elements {
  display: flex;
  flex-direction: column;
  align-items: center;
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
  padding: 0.5rem 1rem;
  font-size: 1rem;
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
  background-color: #000000;
  padding: 20px;
  border: 1px solid #888;
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
