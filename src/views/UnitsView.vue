<template>
  <div class="units">
    <div><h1>Units</h1></div>
    <div class="unit_list">
      <div><h2>Units list</h2></div>
      <div>
        <li v-for="unit in units" :key="unit.id">
          {{ unit.name }}
          <button @click="editUnit(unit)">Edit</button>
          <button @click="deleteUnit(unit)">Delete</button>
        </li>
      </div>
    </div>

    <div class="add_unit">
      <div><button @click="showAddModal">Add Unit</button></div>
    </div>

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>Edit Unit</h2>
        <form @submit.prevent="updateUnit">
          <div>
            <label for="edit-unit-name">Unit Name:</label>
            <input type="text" id="edit-unit-name" v-model="editUnit.name" required />
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
            <input type="text" id="new-unit-name" v-model="newUnit.name" required />
          </div>
          <button type="submit">Add Unit</button>
        </form>
      </div>
    </div>

  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useUnitStore } from '@/stores/unitStore'

export default {
  setup() {
    const unitStore = useUnitStore()
    const isEditModalVisible = ref(false)
    const isAddModalVisible = ref(false)

    onMounted(() => {
      unitStore.fetchUnits()
    })

    const showEditModal = (unit) => {
      unitStore.setEditUnit(unit)
      isEditModalVisible.value = true
    }

    const closeEditModal = () => {
      isEditModalVisible.value = false
    }

    const updateUnit = async () => {
      await unitStore.updateUnit()
      closeEditModal()
    }

    const showAddModal = () => {
      isAddModalVisible.value = true
    }

    const closeAddModal = () => {
      isAddModalVisible.value = false
    }

    const addUnit = async () => {
      console.log("dodaję unit")
      await unitStore.addUnit()
      unitStore.fetchUnits()
      closeAddModal()
    }

    return {
      units: unitStore.units,
      newUnit: unitStore.addUnit,
      editUnit: unitStore.editUnit,
      isEditModalVisible,
      isAddModalVisible,
      showEditModal,
      closeEditModal,
      updateUnit,
      showAddModal,
      closeAddModal,
      addUnit,
      deleteUnit: unitStore.deleteUnit,
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
  background-color: #fefefe;
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
