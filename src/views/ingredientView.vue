<template>
  <div class="elements">
    <div><h1>Ingredients</h1></div>
    <div class="elements_list">
      <div><h2>Ingredients list</h2></div>
      <div>
        <ul v-if="ingredients.length > 0">
          <li v-for="ingredient in ingredients" :key="ingredient.id">
            <div class="element_name">{{ ingredient.name }}</div>
            <div class="element_edit"><button @click="showEditModal(ingredient)">Edit</button></div>
            <div class="element_delete"><button @click="confirmPop(ingredient, 'Czy jesteś pewien że chcesz skasować produkt: ')">Delete</button></div>
          </li>
        </ul>
      </div>
    </div>
  </div>


  <div class="add_ingredient">
      <div><button @click="showAddModal">Add Ingredient</button></div>
    </div>

    <div v-if="isEditModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeEditModal">&times;</span>
        <h2>Edit Ingredient</h2>
        <form @submit.prevent="editIngredient">
      <div>
        <label for="nazwa">Nazwa:</label>
        <input type="text" id="name" v-model="editIngredientRef.name" required />
      </div>
      <div>
        <label for="komentarz">Komentarz:</label>
        <input type="text" id="comment" v-model="editIngredientRef.comment" />
      </div>
      <div>
        <label for="unit">Unit:</label>
        <select id="unit_id" v-model="editIngredientRef.unit_id" required>
          <option value="" disabled>Select a unit</option>
          <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
        </select>
      </div>
      <div>
        <label for="ilosc_w_opakowaniu">Ilość w opakowaniu:</label>
        <input type="number" id="quantity_per_package" v-model="editIngredientRef.quantity_per_package" />
      </div>
      <div>
        <label for="kalorie">Kalorie:</label>
        <input type="number" id="calories_per_100g" v-model="editIngredientRef.calories_per_100g" />
      </div>
      <div>
        <label for="weglowodany">Węglowodany:</label>
        <input type="number" id="carbohydrates_per_100g" v-model="editIngredientRef.carbohydrates_per_100g" />
      </div>
      <div>
        <label for="cukry">Cukry:</label>
        <input type="number" id="sugars_per_100g" v-model="editIngredientRef.sugars_per_100g" />
      </div>
      <div>
        <label for="tluszcz">Tłuszcz:</label>
        <input type="number" id="fat_per_100g" v-model="editIngredientRef.fat_per_100g" />
      </div>
      <div>
        <label for="bialko">Białko:</label>
        <input type="number" id="protein_per_100g" v-model="editIngredientRef.protein_per_100g" />
      </div>
      <div>
        <label for="blonnik">Błonnik:</label>
        <input type="number" id="fiber_per_100g" v-model="editIngredientRef.fiber_per_100g" />
      </div>
      <div>
        <label>Tags:</label>
        <div v-for="tag in tags" :key="tag.id">
          <input type="checkbox" :id="'edit-tag-' + tag.id" :value="tag.id" v-model="tagRef" />
          <label :for="'edit-tag-' + tag.id">{{ tag.name }}</label>
        </div>
      </div>
      <button type="submit" @click="confirmPop(editIngredientRef, 'Czy jesteś pewien że chcesz edit produkt: ')">Edit Ingredient</button>
    </form>
      </div>
    </div>

    <div v-if="isAddModalVisible" class="modal">
      <div class="modal-content">
        <span class="close" @click="closeAddModal">&times;</span>
        <h2>Add Ingredient</h2>
        <form @submit.prevent="addIngredient">
      <div>
        <label for="nazwa">Nazwa:</label>
        <input type="text" id="name" v-model="addIngredientRef.name" required />
      </div>
      <div>
        <label for="komentarz">Komentarz:</label>
        <input type="text" id="comment" v-model="addIngredientRef.comment" />
      </div>
      <div>
        <label for="unit">Unit:</label>
        <select id="unit_id" v-model="addIngredientRef.unit_id" required>
          <option value="" disabled>Select a unit</option>
          <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
        </select>
      </div>
      <div>
        <label for="ilosc_w_opakowaniu">Ilość w opakowaniu:</label>
        <input type="number" id="quantity_per_package" v-model="addIngredientRef.quantity_per_package" />
      </div>
      <div>
        <label for="kalorie">Kalorie:</label>
        <input type="number" id="calories_per_100g" v-model="addIngredientRef.calories_per_100g" />
      </div>
      <div>
        <label for="weglowodany">Węglowodany:</label>
        <input type="number" id="carbohydrates_per_100g" v-model="addIngredientRef.carbohydrates_per_100g" />
      </div>
      <div>
        <label for="cukry">Cukry:</label>
        <input type="number" id="sugars_per_100g" v-model="addIngredientRef.sugars_per_100g" />
      </div>
      <div>
        <label for="tluszcz">Tłuszcz:</label>
        <input type="number" id="fat_per_100g" v-model="addIngredientRef.fat_per_100g" />
      </div>
      <div>
        <label for="bialko">Białko:</label>
        <input type="number" id="protein_per_100g" v-model="addIngredientRef.protein_per_100g" />
      </div>
      <div>
        <label for="blonnik">Błonnik:</label>
        <input type="number" id="fiber_per_100g" v-model="addIngredientRef.fiber_per_100g" />
      </div>
      <div>
        <label>Tags:</label>
        <div v-for="tag in tags" :key="tag.id">
          <input type="checkbox" :id="'add-tag-' + tag.id" :value="tag.id" v-model="tagRef" />
          <label :for="'add-tag-' + tag.id">{{ tag.name }}</label>
        </div>
      </div>
      <button type="submit">Add Ingredient</button>
    </form>
      </div>
    </div>
</template>

<script>
import { onMounted, ref } from 'vue'
import { useIngredientStore } from '@stores/ingredientsStore'
import { useUnitStore } from '@stores/unitsStore'
import { useTagStore } from '@stores/tagsStore'

export default {
  setup() {
    const ingredientStore = useIngredientStore()
    const unitStore = useUnitStore()
    const tagStore = useTagStore()
    const ingredients = ref([])
    const units = ref([])
    const tags = ref([])
    const isEditModalVisible = ref(false)
    const isAddModalVisible = ref(false)
    const initialIngredientRef = {
      name: '',
      comment: '',
      unit_id: '',
      quantity_per_package: '',
      calories_per_100g: '',
      carbohydrates_per_100g: '',
      sugars_per_100g: '',
      fat_per_100g: '',
      protein_per_100g: '',
      fiber_per_100g: '',
      tags: [],
    }
    const addIngredientRef = ref({ ...initialIngredientRef })
    const editIngredientRef = ref({ ...initialIngredientRef })
    const tagRef = ref([])

    const fetchData = async (fetchUnits = true, fetchTags = true, fetchIngredients = true) => {
      if (fetchUnits) { try {
        await unitStore.fetchUnits()
        units.value = unitStore.units
      } catch (error) {
        console.error('Error fetching units:', error)
      }}
      if (fetchTags) { try {
        await tagStore.fetchTags()
        tags.value = tagStore.tags
        console.log(tags)
      } catch (error) {
        console.error('Error fetching tags:', error)
      }}
      if (fetchIngredients) { try {
        await ingredientStore.fetchIngredients()
        ingredients.value = ingredientStore.ingredients
      } catch (error) {
        console.error('Error fetching ingredients:', error)
      }}
    }

    onMounted( () => {fetchData(true, true, true)} )

    const showAddModal = () => {
      addIngredientRef.value = { name: "" }
      isAddModalVisible.value = true
    }

    const closeAddModal = () => {
      isAddModalVisible.value = false
    }

    const showEditModal = (ingredient) => {
      editIngredientRef.value = { ...ingredient }
      isEditModalVisible.value = true
    }

    const closeEditModal = () => {
      isEditModalVisible.value = false
    }

    const resetRefs = () => {
      addIngredientRef.value = { ...initialIngredientRef }
      editIngredientRef.value = { ...initialIngredientRef }
      tagRef.value = []
    }

    const addIngredient = async () => {
      try {
        addIngredientRef.value.tags = tagRef.value
        await ingredientStore.addIngredient(addIngredientRef)
        closeAddModal()
        resetRefs()
        await fetchData(true, false, false)
      } catch (error) {
        console.error('Error adding ingredient:', error)
      }
    }

    const editIngredient = async () => {
      try {
        editIngredientRef.value.tags = tagRef.value
        await ingredientStore.editIngredient(editIngredientRef)
        closeAddModal()
        resetRefs()
        await fetchData(true, false, false)
      } catch (error) {
        console.error('Error adding ingredient:', error)
      }
    }

    const deleteIndegrient = async (indegrient) => {
      try {
        await ingredientStore.deleteIngredient(indegrient)
        await fetchData()
      } catch (error) {
        console.error('Error deleting unit:', error)
      }
    }

    const confirmPop = (ingredient, text) => {
      if (confirm(text + ingredient.name + '?')) {
        deleteIndegrient(ingredient)
      }
    }


    return {
      ingredients,
      units,
      tags,
      addIngredientRef,
      editIngredientRef,
      addIngredient,
      editIngredient,
      isEditModalVisible,
      isAddModalVisible,
      showEditModal,
      closeEditModal,
      showAddModal,
      closeAddModal,
      deleteIndegrient,
      confirmPop,
      tagRef,
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

form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

label {
  font-weight: bold;
}

input,
select {
  padding: 0.5rem;
  font-size: 1rem;
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
