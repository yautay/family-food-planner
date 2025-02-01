<template>
  <div class="ingredients">
    <h1>Ingredients</h1>
    <form @submit.prevent="addIngredient">
      <div>
        <label for="name">Name:</label>
        <input type="text" id="name" v-model="ingredient.name" required />
      </div>
      <div>
        <label for="comment">Comment:</label>
        <input type="text" id="comment" v-model="ingredient.comment" />
      </div>
      <div>
        <label for="unit">Unit:</label>
        <select id="unit" v-model="ingredient.unit_id" required>
          <option value="" disabled>Select a unit</option>
          <option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
        </select>
      </div>
      <div>
        <label for="quantity_per_package">Quantity per Package:</label>
        <input type="number" id="quantity_per_package" v-model="ingredient.quantity_per_package" />
      </div>
      <div>
        <label for="calories">Calories:</label>
        <input type="number" id="calories" v-model="ingredient.calories" />
      </div>
      <div>
        <label for="carbohydrates">Carbohydrates:</label>
        <input type="number" id="carbohydrates" v-model="ingredient.carbohydrates" />
      </div>
      <div>
        <label for="sugars">Sugars:</label>
        <input type="number" id="sugars" v-model="ingredient.sugars" />
      </div>
      <div>
        <label for="fat">Fat:</label>
        <input type="number" id="fat" v-model="ingredient.fat" />
      </div>
      <div>
        <label for="protein">Protein:</label>
        <input type="number" id="protein" v-model="ingredient.protein" />
      </div>
      <div>
        <label for="fiber">Fiber:</label>
        <input type="number" id="fiber" v-model="ingredient.fiber" />
      </div>
      <div>
        <label for="g">G:</label>
        <input type="number" id="g" v-model="ingredient.g" />
      </div>
      <button type="submit">Add Ingredient</button>
    </form>
  </div>
</template>

<script>
import { onMounted } from 'vue'
import { useIngredientStore } from '@/stores/ingredientStore'
import { useUnitStore } from '@/stores/unitStore'

export default {
  setup() {
    const ingredientStore = useIngredientStore()
    const unitStore = useUnitStore()

    onMounted(() => {
      unitStore.fetchUnits()
    })
    return {
      ingredient: ingredientStore.ingredient,
      units: unitStore.units,
      addIngredient: ingredientStore.addIngredient,
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

.manage-units {
  display: flex;
  gap: 1rem;
}
</style>
