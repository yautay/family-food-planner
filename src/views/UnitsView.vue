<template>
  <div class="units">
    <div><h1>Units</h1></div>
    <div class="unit_list">
      <div><h2>Units list</h2></div>
      <div>
        <ul>
          <li v-for="unit in units" :key="unit.id">
            {{ unit.name }}
            <button @click="showEditModal(unit)">Edit</button>
            <button @click="confirmDeleteUnit(unit)">Delete</button>
          </li>
        </ul>
      </div>
    </div>

    <div class="add_unit">
      <div><button @click="showAddModal">Add Unit</button></div>
    </div>

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>Edit Unit</h2>
        <form @submit.prevent="editUnit">
          <div>
            <label for="edit-unit-name">Unit Name:</label>
            <input type="text" id="edit-unit-name" v-model="editUnitRef.name" required />
          </div>
          <button type="submit">Update Unit</button>
        </form>
      </div>
    </div>

    <div v-if="isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>Add Unit</h2>
        <form @submit.prevent="addUnit">
          <div>
            <label for="new-unit-name">Unit Name:</label>
            <input type="text" id="new-unit-name" v-model="newUnitRef.name" required />
          </div>
          <button type="submit">Add Unit</button>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useUnitStore } from '@stores/unitStore'

export default {
  setup() {
    const unitStore = useUnitStore()
    var units = ref([])
    const isEditModalVisible = ref(false)
    const isAddModalVisible = ref(false)
    const newUnitRef = ref({ name: "" })
    const editUnitRef = ref({ id: undefined, name: "" })

    onMounted(() => {
      fetchUnits()
    })

    const fetchUnits = async () => {
      try {
        await unitStore.fetchUnits()
        units.value = unitStore.units
      } catch (error) {
        console.error('Error fetching units:', error)
      }
    }

    const showAddModal = () => {
      newUnitRef.value = { name: "" }
      isAddModalVisible.value = true
    }

    const closeAddModal = () => {
      isAddModalVisible.value = false
    }

    const addUnit = async () => {
      try {
        await unitStore.addUnit(newUnitRef.value)
        await fetchUnits()
        closeAddModal()
      } catch (error) {
        console.error('Error adding unit:', error)
      }
    }

    const showEditModal = (unit) => {
      editUnitRef.value = { id: unit.id, name: "" }
      isEditModalVisible.value = true
    }

    const closeEditModal = () => {
      isEditModalVisible.value = false
    }

    const editUnit = async () => {
      try {
        await unitStore.updateUnit(editUnitRef.value)
        await fetchUnits()
        closeEditModal()
      } catch (error) {
        console.error('Error updating unit:', error)
      }
    }

    const deleteUnit = async (unit) => {
      try {
        await unitStore.deleteUnit(unit)
        await fetchUnits()
      } catch (error) {
        console.error('Error deleting unit:', error)
      }
    }

    const confirmDeleteUnit = (unit) => {
      if (confirm(`Czy jesteś pewien że chcesz skasować jednostkę: "${unit.name}"?`)) {
        deleteUnit(unit)
      }
    }

    return {
      units,
      newUnitRef,
      editUnit,
      isEditModalVisible,
      isAddModalVisible,
      showEditModal,
      closeEditModal,
      editUnitRef,
      showAddModal,
      closeAddModal,
      addUnit,
      deleteUnit,
      confirmDeleteUnit
    }
  },
}
</script>

<style scoped>
.units {
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

li button {
  margin-left: auto;
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
