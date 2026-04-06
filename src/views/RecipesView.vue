<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useCatalogStore } from '../stores/catalogStore'
import { useI18n } from '../composables/useI18n'

const catalogStore = useCatalogStore()
const { t } = useI18n()

const search = ref('')

const recipes = computed(() => catalogStore.recipes)
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

        <div v-if="activeRecipeNutrition?.summary" class="nutrition-summary">
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
              >{{ ingredient.quantity ?? '-' }} {{ ingredient.unit_name || '' }} |
              {{ ingredient.grams ?? '-' }} g</span
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

@media (min-width: 1000px) {
  .recipes-layout {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }
}
</style>
