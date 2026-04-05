<template>
  <div class="catalog-page">
    <h1>Katalog produktow i dan</h1>

    <section class="panel">
      <div class="panel-header">
        <h2>Produkty</h2>
        <input v-model="productSearch" placeholder="Szukaj produktu" @input="refreshProducts" />
      </div>
      <p class="meta">Liczba produktow: {{ products.length }}</p>
      <ul class="list">
        <li v-for="product in products" :key="product.id">
          <span class="title">{{ product.name }}</span>
          <span class="hint">
            domyslna jednostka: {{ product.default_unit_name || '-' }}, uzyty w daniach: {{ product.recipes_count }}
          </span>
        </li>
      </ul>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>Dania</h2>
        <input v-model="recipeSearch" placeholder="Szukaj dania" @input="refreshRecipes" />
      </div>
      <p class="meta">Liczba dan: {{ recipes.length }}</p>
      <ul class="list">
        <li v-for="recipe in recipes" :key="recipe.id">
          <button class="link" @click="selectRecipe(recipe.id)">{{ recipe.name }}</button>
          <span class="hint">skladniki: {{ recipe.ingredients_count }}</span>
        </li>
      </ul>
    </section>

    <section v-if="activeRecipe" class="panel">
      <h2>Sklad dania: {{ activeRecipe.name }}</h2>
      <ul class="list">
        <li v-for="ingredient in activeRecipeIngredients" :key="ingredient.id">
          <span class="title">{{ ingredient.product_name }}</span>
          <span class="hint">
            ilosc: {{ ingredient.quantity ?? '-' }} {{ ingredient.unit_name || '' }}, masa: {{ ingredient.grams }} g
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script>
import { onMounted, ref, computed } from 'vue'
import { useCatalogStore } from '@stores/catalogStore'

export default {
  setup() {
    const catalogStore = useCatalogStore()
    const productSearch = ref('')
    const recipeSearch = ref('')

    const refreshProducts = async () => {
      await catalogStore.fetchProducts(productSearch.value)
    }

    const refreshRecipes = async () => {
      await catalogStore.fetchRecipes(recipeSearch.value)
    }

    const selectRecipe = async (recipeId) => {
      await catalogStore.fetchRecipeDetails(recipeId)
    }

    onMounted(async () => {
      await Promise.all([refreshProducts(), refreshRecipes()])
    })

    return {
      productSearch,
      recipeSearch,
      refreshProducts,
      refreshRecipes,
      selectRecipe,
      products: computed(() => catalogStore.products),
      recipes: computed(() => catalogStore.recipes),
      activeRecipe: computed(() => catalogStore.activeRecipe),
      activeRecipeIngredients: computed(() => catalogStore.activeRecipeIngredients),
    }
  },
}
</script>

<style scoped>
.catalog-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
}

.panel {
  border: 1px solid #d5d5d5;
  border-radius: 0.5rem;
  padding: 1rem;
  background: #ffffff;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.panel-header input {
  min-width: 240px;
  padding: 0.5rem;
}

.meta {
  margin: 0.5rem 0;
  color: #4a4a4a;
}

.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.title {
  font-weight: 600;
}

.hint {
  margin-left: 0.5rem;
  color: #4a4a4a;
}

.link {
  border: none;
  background: transparent;
  color: #0d63b8;
  cursor: pointer;
  padding: 0;
  font-size: 1rem;
}

@media (max-width: 700px) {
  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-header input {
    width: 100%;
    min-width: 0;
  }
}
</style>
