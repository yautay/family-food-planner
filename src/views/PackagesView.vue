<script setup>
import { computed, onMounted } from 'vue'
import CatalogSectionNav from '../components/navigation/CatalogSectionNav.vue'
import { useIngredientStore } from '../stores/ingredientsStore'
import { useUnitStore } from '../stores/unitsStore'
import { useI18n } from '../composables/useI18n'

const ingredientStore = useIngredientStore()
const unitStore = useUnitStore()
const { t } = useI18n()

const packageRows = computed(() =>
  ingredientStore.ingredients
    .filter((ingredient) => Number(ingredient.quantity_per_package) > 0)
    .map((ingredient) => ({
      id: ingredient.id,
      name: ingredient.name,
      quantity: ingredient.quantity_per_package,
      unitName:
        unitStore.units.find((unit) => unit.id === ingredient.unit_id)?.name ??
        t('ingredients.unknown'),
    })),
)

onMounted(async () => {
  await Promise.all([ingredientStore.fetchIngredients(), unitStore.fetchUnits()])
})
</script>

<template>
  <section class="surface-card">
    <CatalogSectionNav />

    <div class="section-header">
      <h1 class="title is-4">{{ t('packages.title') }}</h1>
      <p class="muted">{{ t('packages.description') }}</p>
    </div>

    <h2 class="title is-5">{{ t('packages.listTitle') }}</h2>

    <div class="table-wrapper" v-if="packageRows.length > 0">
      <table class="table is-fullwidth is-hoverable is-striped is-size-7-mobile">
        <thead>
          <tr>
            <th>{{ t('packages.ingredientColumn') }}</th>
            <th>{{ t('packages.quantityColumn') }}</th>
            <th>{{ t('packages.unitColumn') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in packageRows" :key="row.id">
            <td>{{ row.name }}</td>
            <td>{{ row.quantity }}</td>
            <td>{{ row.unitName }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-else class="muted">{{ t('packages.empty') }}</p>
  </section>
</template>

<style scoped>
.section-header {
  display: grid;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}

.table-wrapper {
  width: 100%;
  overflow-x: auto;
}
</style>
