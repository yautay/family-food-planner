<template>
  <div class="ingredients">
    <h1>Ingredients</h1>
    <form @submit.prevent="addIngredient">
      <div>
        <label for="nazwa">Nazwa:</label>
        <input type="text" id="nazwa" v-model="ingredient.nazwa" required />
      </div>
      <div>
        <label for="komentarz">Komentarz:</label>
        <input type="text" id="komentarz" v-model="ingredient.komentarz" />
      </div>
      <div>
        <label for="unit">Unit:</label>
        <select id="unit" v-model="ingredient.unit_id" required>
          <option value="" disabled>Select a unit</option>
          <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
        </select>
      </div>
      <div>
        <label for="ilosc_w_opakowaniu">Ilość w opakowaniu:</label>
        <input type="number" id="ilosc_w_opakowaniu" v-model="ingredient.ilosc_w_opakowaniu" />
      </div>
      <div>
        <label for="kalorie">Kalorie:</label>
        <input type="number" id="kalorie" v-model="ingredient.kalorie" />
      </div>
      <div>
        <label for="weglowodany">Węglowodany:</label>
        <input type="number" id="weglowodany" v-model="ingredient.weglowodany" />
      </div>
      <div>
        <label for="cukry">Cukry:</label>
        <input type="number" id="cukry" v-model="ingredient.cukry" />
      </div>
      <div>
        <label for="tluszcz">Tłuszcz:</label>
        <input type="number" id="tluszcz" v-model="ingredient.tluszcz" />
      </div>
      <div>
        <label for="bialko">Białko:</label>
        <input type="number" id="bialko" v-model="ingredient.bialko" />
      </div>
      <div>
        <label for="blonnik">Błonnik:</label>
        <input type="number" id="blonnik" v-model="ingredient.blonnik" />
      </div>
      <div>
        <label>Tags:</label>
        <div v-for="tag in tags" :key="tag.id">
          <input type="checkbox" :value="tag.id" v-model="ingredient.tags" /> {{ tag.name }}
        </div>
      </div>
      <button type="submit">Add Ingredient</button>
    </form>
    <ul>
      <li v-for="ingredient in ingredients" :key="ingredient.id">
        {{ ingredient.nazwa }} - {{ ingredient.unit_name }}
        <button @click="editIngredient(ingredient)">Edit</button>
        <button @click="confirmDeleteIngredient(ingredient.id)">Delete</button>
      </li>
    </ul>
  </div>
</template>

<script>
import { onMounted } from 'vue'
import { useIngredientStore } from '@stores/ingredientsStore'
import { useUnitStore } from '@stores/unitsStore'
import { useTagStore } from '@stores/tagsStore'

export default {
  setup() {
    const ingredientStore = useIngredientStore()
    const unitStore = useUnitStore()
    const tagStore = useTagStore()

    onMounted(() => {
      ingredientStore.fetchIngredients()
      unitStore.fetchUnits()
      tagStore.fetchTags()
    })

    const editIngredient = (ingredient) => {
      ingredientStore.ingredient = { ...ingredient, tags: ingredient.tags.map(tag => tag.id) }
    }

    const confirmDeleteIngredient = (id) => {
      if (confirm('Are you sure you want to delete this ingredient?')) {
        ingredientStore.deleteIngredient(id)
      }
    }

    return {
      ingredient: ingredientStore.ingredient,
      ingredients: ingredientStore.ingredients,
      units: unitStore.units,
      tags: tagStore.tags,
      addIngredient: ingredientStore.addIngredient,
      editIngredient,
      confirmDeleteIngredient,
    }
  },
}
</script>

<style scoped>
.ingredients {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
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
</style>
