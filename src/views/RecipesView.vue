<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useCatalogStore } from '../stores/catalogStore'
import { useI18n } from '../composables/useI18n'
import { formatIngredientAmount } from '../utils/ingredientAmount'
import { filterBySearch, sortByField } from '../utils/listUtils'

const catalogStore = useCatalogStore()
const { t } = useI18n()

const search = ref('')
const sortBy = ref('name')
const sortDirection = ref('asc')

const recipes = computed(() => {
  const filtered = filterBySearch(catalogStore.recipes, search.value, (recipe) => {
    return [recipe.name, recipe.owner_username].filter(Boolean).join(' | ')
  })

  return sortByField(filtered, sortBy.value, sortDirection.value)
})
const activeRecipe = computed(() => catalogStore.activeRecipe)
const activeRecipeIngredients = computed(() => catalogStore.activeRecipeIngredients)
const activeRecipeNutrition = computed(() => catalogStore.activeRecipeNutrition)

async function refreshRecipes() {
  await catalogStore.fetchRecipes(search.value)
}

async function selectRecipe(recipeId) {
  await catalogStore.fetchRecipeDetails(recipeId)
}

onMounted(async () => {
  await refreshRecipes()
})
</script>

<template>
  <section class="recipes-layout">
    <article class="surface-card">
      <CatalogSectionNav />

      <div class="section-header">
        <h1 class="title is-4">{{ t('recipes.title') }}</h1>
        <p class="muted">{{ t('recipes.description') }}</p>
      </div>

      <label class="search-field">
        <span>{{ t('recipes.search') }}</span>
        <input
          v-model="search"
          class="input"
          :placeholder="t('recipes.search')"
          @input="refreshRecipes"
        />
      </label>

      <div class="search-field">
        <label>
          <span>{{ t('common.sortBy') }}</span>
          <select v-model="sortBy" class="input">
            <option value="name">{{ t('catalog.name') }}</option>
            <option value="ingredients_count">{{ t('catalog.ingredientsCount') }}</option>
            <option value="owner_username">{{ t('catalog.owner') }}</option>
          </select>
        </label>
        <label>
          <span>{{ t('common.sortOrder') }}</span>
          <select v-model="sortDirection" class="input">
            <option value="asc">{{ t('common.sortAsc') }}</option>
            <option value="desc">{{ t('common.sortDesc') }}</option>
          </select>
        </label>
      </div>

      <h2 class="title is-5">{{ t('recipes.listTitle') }}</h2>
      <ul class="list">
        <li v-for="recipe in recipes" :key="recipe.id">
          <button class="link" @click="selectRecipe(recipe.id)">{{ recipe.name }}</button>
          <span class="muted"
            >{{ recipe.ingredients_count }} {{ t('catalog.ingredientsCount') }}</span
          >
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <h2 class="title is-5">{{ t('recipes.detailsTitle') }}</h2>

      <template v-if="activeRecipe">
        <p>
          <strong>{{ activeRecipe.name }}</strong>
        </p>
        <p class="muted" v-if="activeRecipe.owner_username">
          {{ t('catalog.owner') }}: {{ activeRecipe.owner_username }}
        </p>
        <p class="muted" v-if="activeRecipe.is_system === 1">{{ t('catalog.system') }}</p>
        <p v-if="activeRecipe.instructions" class="recipe-instructions">
          <strong>{{ t('catalog.instructions') }}:</strong> {{ activeRecipe.instructions }}
        </p>

        <div v-if="activeRecipeNutrition?.summary" class="nutrition-summary">
          <span
            >{{ t('catalog.totalMass') }}:
            {{ activeRecipeNutrition.summary.total_grams ?? 0 }} g</span
          >
          <span>{{ activeRecipeNutrition.summary.calories ?? 0 }} kcal</span>
          <span
            >{{ t('ingredients.protein') }}:
            {{ activeRecipeNutrition.summary.protein ?? 0 }} g</span
          >
          <span>{{ t('ingredients.fat') }}: {{ activeRecipeNutrition.summary.fat ?? 0 }} g</span>
          <span
            >{{ t('ingredients.carbohydrates') }}:
            {{ activeRecipeNutrition.summary.carbohydrates ?? 0 }} g</span
          >
          <span
            >{{ t('ingredients.fiber') }}: {{ activeRecipeNutrition.summary.fiber ?? 0 }} g</span
          >
        </div>

        <ul class="list mt-3">
          <li v-for="ingredient in activeRecipeIngredients" :key="ingredient.id">
            <strong>{{ ingredient.product_name }}</strong>
            <span class="muted"
              >{{ formatIngredientAmount(ingredient) }} | {{ ingredient.grams ?? '-' }} g</span
            >
          </li>
        </ul>
      </template>

      <p v-else class="muted">{{ t('recipes.pickRecipe') }}</p>

      <p class="mt-4">
        <RouterLink to="/catalog">{{ t('recipes.openCatalogEditor') }}</RouterLink>
      </p>
    </article>
  </section>
</template>

<style scoped>
.recipes-layout {
  display: grid;
  gap: 1rem;
}

.section-header {
  display: grid;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}

.search-field {
  display: grid;
  gap: 0.35rem;
  margin-bottom: 0.9rem;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.45rem;
}

.list li {
  border-bottom: 1px solid var(--app-border);
  padding-bottom: 0.45rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  justify-content: space-between;
}

.link {
  border: none;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
  padding: 0;
}

.nutrition-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin-top: 0.55rem;
  font-size: 0.92rem;
}

.recipe-instructions {
  margin-top: 0.5rem;
}

@media (min-width: 1000px) {
  .recipes-layout {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }
}
</style>
