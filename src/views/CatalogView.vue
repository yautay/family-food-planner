<template>
  <section class="catalog-layout">
    <article class="surface-card">
      <CatalogSectionNav />

      <div class="section-header">
        <h1>{{ t('catalog.title') }}</h1>
      </div>

      <div class="grid-two">
        <div>
          <h2>{{ t('catalog.products') }}</h2>
          <input
            v-model="productSearch"
            class="input"
            :placeholder="t('catalog.searchProduct')"
            @input="refreshProducts"
          />
          <div class="inline-controls">
            <select v-model="productSortBy" class="input is-small">
              <option value="name">{{ t('catalog.name') }}</option>
              <option value="default_unit_name">{{ t('ingredients.unit') }}</option>
              <option value="recipes_count">{{ t('catalog.recipesCount') }}</option>
            </select>
            <select v-model="productSortDirection" class="input is-small">
              <option value="asc">{{ t('common.sortAsc') }}</option>
              <option value="desc">{{ t('common.sortDesc') }}</option>
            </select>
          </div>
          <p class="muted">{{ products.length }} {{ t('common.records') }}</p>
          <ul class="list">
            <li v-for="product in products" :key="product.id">
              <strong>{{ product.name }}</strong>
              <span class="muted"
                >{{ product.default_unit_name || '-' }} | {{ product.recipes_count }}
                {{ t('catalog.recipesCount') }}</span
              >
            </li>
          </ul>
        </div>

        <div>
          <h2>{{ t('catalog.recipes') }}</h2>
          <input
            v-model="recipeSearch"
            class="input"
            :placeholder="t('catalog.searchRecipe')"
            @input="refreshRecipes"
          />
          <div class="inline-controls">
            <select v-model="recipeSortBy" class="input is-small">
              <option value="name">{{ t('catalog.name') }}</option>
              <option value="ingredients_count">{{ t('catalog.ingredientsCount') }}</option>
              <option value="owner_username">{{ t('catalog.owner') }}</option>
            </select>
            <select v-model="recipeSortDirection" class="input is-small">
              <option value="asc">{{ t('common.sortAsc') }}</option>
              <option value="desc">{{ t('common.sortDesc') }}</option>
            </select>
          </div>
          <p class="muted">{{ recipes.length }} {{ t('common.records') }}</p>
          <ul class="list">
            <li v-for="recipe in recipes" :key="recipe.id">
              <button class="link" @click="selectRecipe(recipe.id)">{{ recipe.name }}</button>
              <span class="muted">
                {{ recipe.ingredients_count }} {{ t('catalog.ingredientsCount') }}
                <template v-if="recipe.is_system === 1">| {{ t('catalog.system') }}</template>
              </span>
            </li>
          </ul>
        </div>
      </div>
    </article>

    <article v-if="activeRecipe" class="surface-card">
      <h2>{{ t('catalog.recipeIngredients') }}: {{ activeRecipe.name }}</h2>
      <p class="muted" v-if="activeRecipe.owner_username">
        {{ t('catalog.owner') }}: {{ activeRecipe.owner_username }}
      </p>
      <p v-if="activeRecipe.instructions" class="recipe-instructions">
        <strong>{{ t('catalog.instructions') }}:</strong> {{ activeRecipe.instructions }}
      </p>
      <div v-if="activeRecipeNutrition?.summary" class="nutrition-summary">
        <span>{{ t('catalog.nutritionSummary') }}:</span>
        <span
          >{{ t('catalog.totalMass') }}:
          {{ activeRecipeNutrition.summary.total_grams ?? 0 }} g</span
        >
        <span>{{ activeRecipeNutrition.summary.calories ?? 0 }} kcal</span>
        <span
          >{{ t('ingredients.protein') }}: {{ activeRecipeNutrition.summary.protein ?? 0 }} g</span
        >
        <span>{{ t('ingredients.fat') }}: {{ activeRecipeNutrition.summary.fat ?? 0 }} g</span>
        <span
          >{{ t('ingredients.carbohydrates') }}:
          {{ activeRecipeNutrition.summary.carbohydrates ?? 0 }} g</span
        >
        <span>{{ t('ingredients.fiber') }}: {{ activeRecipeNutrition.summary.fiber ?? 0 }} g</span>
      </div>
      <ul class="list">
        <li v-for="ingredient in activeRecipeIngredients" :key="ingredient.id">
          <strong>{{ ingredient.product_name }}</strong>
          <span class="muted"
            >{{ formatIngredientAmount(ingredient) }} | {{ ingredient.grams ?? '-' }} g</span
          >
        </li>
      </ul>

      <div v-if="canManageRecipes && activeRecipe.is_editable === 1" class="actions-row">
        <button class="button is-primary is-small" @click="startEditActiveRecipe">
          {{ t('common.edit') }}
        </button>
        <button class="button is-small" @click="removeActiveRecipe">
          {{ t('common.delete') }}
        </button>
      </div>
    </article>

    <article v-if="canManageRecipes" class="surface-card">
      <h2>{{ editingRecipeId ? t('catalog.editRecipeTitle') : t('catalog.newRecipeTitle') }}</h2>
      <form class="form-grid" @submit.prevent="saveRecipe">
        <label>
          {{ t('catalog.name') }}
          <input v-model="recipeForm.name" class="input" required />
        </label>

        <label>
          {{ t('catalog.sourceFile') }}
          <input
            v-model="recipeForm.source_file"
            class="input"
            :placeholder="t('catalog.sourceFilePlaceholder')"
          />
        </label>

        <label>
          {{ t('catalog.ingredientsInputLabel') }}
          <textarea v-model="ingredientsText" class="textarea" rows="8"></textarea>
        </label>

        <p v-if="formMessage" class="success-message">{{ formMessage }}</p>
        <p v-if="formError" class="error-message">{{ formError }}</p>

        <div class="actions-row">
          <button class="button is-primary" type="submit">
            {{ editingRecipeId ? t('catalog.saveChanges') : t('catalog.addRecipe') }}
          </button>
          <button class="button" type="button" @click="resetForm">{{ t('common.reset') }}</button>
        </div>
      </form>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useCatalogStore } from '../stores/catalogStore'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import {
  formatIngredientAmount,
  isPhysicalUnit,
  shouldHideDefaultPhysicalQuantity,
} from '../utils/ingredientAmount'
import { sortByField } from '../utils/listUtils'

const catalogStore = useCatalogStore()
const authStore = useAuthStore()
const { t } = useI18n()

const productSearch = ref('')
const recipeSearch = ref('')
const productSortBy = ref('name')
const productSortDirection = ref('asc')
const recipeSortBy = ref('name')
const recipeSortDirection = ref('asc')
const formMessage = ref('')
const formError = ref('')
const editingRecipeId = ref(null)

const recipeForm = ref({
  name: '',
  source_file: 'manual',
})

const ingredientsText = ref('')

const products = computed(() => {
  return sortByField(catalogStore.products, productSortBy.value, productSortDirection.value)
})

const recipes = computed(() => {
  return sortByField(catalogStore.recipes, recipeSortBy.value, recipeSortDirection.value)
})
const activeRecipe = computed(() => catalogStore.activeRecipe)
const activeRecipeIngredients = computed(() => catalogStore.activeRecipeIngredients)
const activeRecipeNutrition = computed(() => catalogStore.activeRecipeNutrition)
const canManageRecipes = computed(() => authStore.can('recipes.manage'))

async function refreshProducts() {
  await catalogStore.fetchProducts(productSearch.value)
}

async function refreshRecipes() {
  await catalogStore.fetchRecipes(recipeSearch.value)
}

async function selectRecipe(recipeId) {
  await catalogStore.fetchRecipeDetails(recipeId)
}

function parseIngredientLines() {
  const lines = ingredientsText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  return lines.map((line) => {
    const [productName, quantity, unitName, grams] = line
      .split('|')
      .map((part) => part?.trim() ?? '')
    const quantityNumber = quantity ? Number(quantity.replace(',', '.')) : null
    const gramsNumber = grams ? Number(grams.replace(',', '.')) : null
    const normalizedUnitName = unitName || null
    const normalizedQuantity = Number.isFinite(quantityNumber)
      ? quantityNumber
      : !quantity && isPhysicalUnit(normalizedUnitName)
        ? 1
        : null

    return {
      product_name: productName,
      quantity: normalizedQuantity,
      unit_name: normalizedUnitName,
      grams: Number.isFinite(gramsNumber) ? gramsNumber : null,
      note: '',
    }
  })
}

async function saveRecipe() {
  formMessage.value = ''
  formError.value = ''

  try {
    const payload = {
      ...recipeForm.value,
      ingredients: parseIngredientLines(),
    }

    if (editingRecipeId.value) {
      const updated = await catalogStore.updateRecipe(editingRecipeId.value, payload)
      await selectRecipe(updated.id)
      formMessage.value = t('catalog.recipeSaved')
    } else {
      const created = await catalogStore.createRecipe(payload)
      await selectRecipe(created.id)
      formMessage.value = t('catalog.recipeAdded')
    }

    await refreshRecipes()
    resetForm(false)
  } catch (error) {
    formError.value = error?.response?.data?.error ?? t('catalog.saveError')
  }
}

function resetForm(clearMessage = true) {
  editingRecipeId.value = null
  recipeForm.value = {
    name: '',
    source_file: 'manual',
  }
  ingredientsText.value = ''

  if (clearMessage) {
    formMessage.value = ''
    formError.value = ''
  }
}

function startEditActiveRecipe() {
  if (!activeRecipe.value || activeRecipe.value.is_editable !== 1) {
    return
  }

  editingRecipeId.value = activeRecipe.value.id
  recipeForm.value = {
    name: activeRecipe.value.name,
    source_file: activeRecipe.value.source_file ?? 'manual',
  }

  ingredientsText.value = activeRecipeIngredients.value
    .map((ingredient) => {
      const qty = shouldHideDefaultPhysicalQuantity(ingredient) ? '' : (ingredient.quantity ?? '')
      const unit = ingredient.unit_name ?? ''
      const grams = ingredient.grams ?? ''
      return `${ingredient.product_name}|${qty}|${unit}|${grams}`
    })
    .join('\n')

  formMessage.value = ''
  formError.value = ''
}

async function removeActiveRecipe() {
  if (!activeRecipe.value) {
    return
  }

  if (!confirm(t('catalog.deleteConfirm', { name: activeRecipe.value.name }))) {
    return
  }

  try {
    await catalogStore.deleteRecipe(activeRecipe.value.id)
    formMessage.value = t('catalog.recipeDeleted')
    formError.value = ''
  } catch (error) {
    formError.value = error?.response?.data?.error ?? t('catalog.deleteError')
  }
}

onMounted(async () => {
  await Promise.all([refreshProducts(), refreshRecipes()])
})
</script>

<style scoped>
.catalog-layout {
  display: grid;
  gap: 1rem;
}

.section-header {
  margin-bottom: 0.8rem;
}

.inline-controls {
  display: grid;
  gap: 0.4rem;
  margin-top: 0.4rem;
}

.list {
  list-style: none;
  margin: 0.6rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.45rem;
}

.list li {
  border-bottom: 1px solid var(--app-border);
  padding-bottom: 0.4rem;
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.link {
  border: none;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
  padding: 0;
}

.actions-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.recipe-instructions {
  margin: 0.5rem 0;
}

.nutrition-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin: 0.6rem 0;
  font-size: 0.92rem;
}

textarea {
  border: 1px solid var(--app-border);
  border-radius: 0.55rem;
  padding: 0.55rem 0.65rem;
  background: var(--app-surface);
  color: var(--app-text);
}
</style>
