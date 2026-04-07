<script setup>
const props = defineProps({
  totals: {
    type: Object,
    required: true,
  },
  caption: {
    type: String,
    default: '',
  },
  massOnly: {
    type: Boolean,
    default: false,
  },
  massLabel: {
    type: String,
    default: 'masa',
  },
})

function valueOf(field) {
  const value = Number(props.totals?.[field])
  return Number.isFinite(value) ? value : 0
}

function formatNumber(value) {
  return Number(value.toFixed(2)).toString()
}

function massValue() {
  const totalMass = Number(props.totals?.total_mass_grams)
  if (Number.isFinite(totalMass)) {
    return totalMass
  }

  const mass = Number(props.totals?.mass_grams)
  return Number.isFinite(mass) ? mass : 0
}

function formattedMass() {
  const grams = massValue()
  if (grams >= 1000) {
    return `${formatNumber(grams / 1000)} kg`
  }

  return `${formatNumber(grams)} g`
}
</script>

<template>
  <div class="nutrition-inline">
    <p v-if="props.caption" class="caption muted">{{ props.caption }}</p>

    <div class="chips" role="group" aria-label="Nutrition totals">
      <template v-if="props.massOnly">
        <span class="chip">{{ props.massLabel }} {{ formattedMass() }}</span>
      </template>

      <template v-else>
        <span class="chip">{{ valueOf('calories') }} kcal</span>
        <span class="chip">B {{ valueOf('protein') }} g</span>
        <span class="chip">T {{ valueOf('fat') }} g</span>
        <span class="chip">W {{ valueOf('carbohydrates') }} g</span>
        <span class="chip">{{ props.massLabel }} {{ formattedMass() }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.nutrition-inline {
  display: grid;
  gap: 0.35rem;
}

.caption {
  margin: 0;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.chip {
  border: 1px solid var(--app-border);
  border-radius: 999px;
  background: var(--app-surface-alt);
  color: var(--app-text);
  padding: 0.18rem 0.55rem;
  font-size: 0.8rem;
  font-weight: 600;
}
</style>
