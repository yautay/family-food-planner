<template>
  <section class="catalog-layout">
    <article class="surface-card">
      <div class="section-header">
        <h1>{{ t('catalog.title') }}</h1>
      </div>

      <div class="grid-two">
        <div>
          <h2>{{ t('catalog.products') }}</h2>
          <input v-model="productSearch" class="input" :placeholder="t('catalog.searchProduct')" @input="refreshProducts" />
          <p class="muted">{{ products.length }} rekordow</p>
          <ul class="list">
            <li v-for="product in products" :key="product.id">
              <strong>{{ product.name }}</strong>
              <span class="muted">{{ product.default_unit_name || '-' }} | {{ product.recipes_count }} recipes</span>
            </li>
          </ul>
        </div>

        <div>
          <h2>{{ t('catalog.recipes') }}</h2>
          <input v-model="recipeSearch" class="input" :placeholder="t('catalog.searchRecipe')" @input="refreshRecipes" />
          <p class="muted">{{ recipes.length }} rekordow</p>
          <ul class="list">
            <li v-for="recipe in recipes" :key="recipe.id">
              <button class="link" @click="selectRecipe(recipe.id)">{{ recipe.name }}</button>
              <span class="muted">
                {{ recipe.ingredients_count }} ing.
                <template v-if="recipe.is_system === 1">| system</template>
              </span>
            </li>
          </ul>
        </div>
      </div>
    </article>

    <article v-if="activeRecipe" class="surface-card">
      <h2>{{ t('catalog.recipeIngredients') }}: {{ activeRecipe.name }}</h2>
      <p class="muted" v-if="activeRecipe.owner_username">owner: {{ activeRecipe.owner_username }}</p>
      <ul class="list">
        <li v-for="ingredient in activeRecipeIngredients" :key="ingredient.id">
          <strong>{{ ingredient.product_name }}</strong>
          <span class="muted">{{ ingredient.quantity ?? '-' }} {{ ingredient.unit_name || '' }} | {{ ingredient.grams ?? '-' }} g</span>
        </li>
      </ul>

      <div v-if="canManageRecipes && activeRecipe.is_editable === 1" class="actions-row">
        <button class="button is-primary is-small" @click="startEditActiveRecipe">Edytuj</button>
        <button class="button is-small" @click="removeActiveRecipe">Usun</button>
      </div>
    </article>

    <article v-if="canManageRecipes" class="surface-card">
      <h2>{{ editingRecipeId ? 'Edycja przepisu' : 'Nowy przepis' }}</h2>
      <form class="form-grid" @submit.prevent="saveRecipe">
        <label>
          Nazwa
          <input v-model="recipeForm.name" class="input" required />
        </label>

        <label>
          Source file
          <input v-model="recipeForm.source_file" class="input" placeholder="manual" />
        </label>

        <label>
          Skladniki (linia: nazwa|ilosc|jednostka|gramy)
          <textarea v-model="ingredientsText" class="textarea" rows="8"></textarea>
        </label>

        <p v-if="formMessage" class="success-message">{{ formMessage }}</p>
        <p v-if="formError" class="error-message">{{ formError }}</p>

        <div class="actions-row">
          <button class="button is-primary" type="submit">{{ editingRecipeId ? 'Zapisz zmiany' : 'Dodaj przepis' }}</button>
          <button class="button" type="button" @click="resetForm">Reset</button>
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

const catalogStore = useCatalogStore()
const authStore = useAuthStore()
const { t } = useI18n()

const productSearch = ref('')
const recipeSearch = ref('')
const formMessage = ref('')
const formError = ref('')
const editingRecipeId = ref(null)

const recipeForm = ref({
  name: '',
  source_file: 'manual',
})

const ingredientsText = ref('')

const products = computed(() => catalogStore.products)
const recipes = computed(() => catalogStore.recipes)
const activeRecipe = computed(() => catalogStore.activeRecipe)
const activeRecipeIngredients = computed(() => catalogStore.activeRecipeIngredients)
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
    const [productName, quantity, unitName, grams] = line.split('|').map((part) => part?.trim() ?? '')
    const quantityNumber = quantity ? Number(quantity.replace(',', '.')) : null
    const gramsNumber = grams ? Number(grams.replace(',', '.')) : null

    return {
      product_name: productName,
      quantity: Number.isFinite(quantityNumber) ? quantityNumber : null,
      unit_name: unitName || null,
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
      formMessage.value = 'Zapisano zmiany.'
    } else {
      const created = await catalogStore.createRecipe(payload)
      await selectRecipe(created.id)
      formMessage.value = 'Dodano przepis.'
    }

    await refreshRecipes()
    resetForm(false)
  } catch (error) {
    formError.value = error?.response?.data?.error ?? 'Nie udalo sie zapisac przepisu'
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
      const qty = ingredient.quantity ?? ''
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

  if (!confirm(`Usunac przepis: ${activeRecipe.value.name}?`)) {
    return
  }

  try {
    await catalogStore.deleteRecipe(activeRecipe.value.id)
    formMessage.value = 'Przepis usuniety.'
    formError.value = ''
  } catch (error) {
    formError.value = error?.response?.data?.error ?? 'Nie udalo sie usunac przepisu'
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

textarea {
  border: 1px solid var(--app-border);
  border-radius: 0.55rem;
  padding: 0.55rem 0.65rem;
  background: var(--app-surface);
  color: var(--app-text);
}
</style>
