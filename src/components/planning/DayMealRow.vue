<script setup>
import NutritionTotalsInline from './NutritionTotalsInline.vue'
import SlotTimeClock from './SlotTimeClock.vue'

const props = defineProps({
  meal: {
    type: Object,
    required: true,
  },
  index: {
    type: Number,
    required: true,
  },
  isDragging: {
    type: Boolean,
    default: false,
  },
  isDropTarget: {
    type: Boolean,
    default: false,
  },
  readOnly: {
    type: Boolean,
    default: false,
  },
  editMealPortions: {
    type: Boolean,
    default: false,
  },
  defaultServings: {
    type: Number,
    default: 1,
  },
  servingsLabel: {
    type: String,
    required: true,
  },
  mealPortionsLabel: {
    type: String,
    required: true,
  },
  noteLabel: {
    type: String,
    required: true,
  },
  onePortionLabel: {
    type: String,
    required: true,
  },
  mealMassLabel: {
    type: String,
    required: true,
  },
  changeMealLabel: {
    type: String,
    required: true,
  },
  deleteLabel: {
    type: String,
    required: true,
  },
  slotLabel: {
    type: String,
    required: true,
  },
})

const emit = defineEmits([
  'update-servings',
  'update-note',
  'change-meal',
  'remove-meal',
  'dragstart',
  'dragover',
  'drop',
  'dragend',
])

function onServingsInput(value) {
  emit('update-servings', props.index, value)
}

function onNoteInput(value) {
  emit('update-note', props.index, value)
}
</script>

<template>
  <li
    class="meal-row"
    :class="{
      'is-dragging': props.isDragging,
      'is-drop-target': props.isDropTarget,
    }"
    :draggable="!props.readOnly"
    @dragstart="$emit('dragstart', props.index, $event)"
    @dragover="$emit('dragover', props.index, $event)"
    @drop="$emit('drop', props.index, $event)"
    @dragend="$emit('dragend')"
  >
    <div class="meal-row-main">
      <p class="meal-slot">
        {{ props.slotLabel }}
        <span v-if="props.meal.slot_time" class="slot-time-clock-wrap">
          <SlotTimeClock :time="props.meal.slot_time" :size="22" />
        </span>
      </p>
      <strong>{{ props.meal.recipe_name }}</strong>
      <p class="muted">
        {{ props.editMealPortions ? props.mealPortionsLabel : props.servingsLabel }}:
        {{ props.editMealPortions ? props.meal.portions : props.meal.effective_servings }}
      </p>

      <div class="nutrition-line">
        <NutritionTotalsInline :totals="props.meal.nutrition" :caption="props.onePortionLabel" />
        <p class="muted cumulative-line">
          {{ props.mealMassLabel }}: {{ props.meal.nutrition.total_mass_grams }} g
        </p>
      </div>
    </div>

    <div v-if="!props.readOnly" class="meal-row-actions">
      <label>
        {{ props.editMealPortions ? props.mealPortionsLabel : props.servingsLabel }}
        <input
          :value="props.editMealPortions ? props.meal.portions : props.meal.effective_servings"
          class="input"
          type="number"
          min="0.1"
          step="0.1"
          :placeholder="props.editMealPortions ? '1' : String(props.defaultServings)"
          @input="onServingsInput($event.target.value)"
        />
      </label>
      <label>
        {{ props.noteLabel }}
        <input
          :value="props.meal.note ?? ''"
          class="input"
          @input="onNoteInput($event.target.value)"
        />
      </label>
      <button class="button is-small" type="button" @click="$emit('change-meal', props.index)">
        {{ props.changeMealLabel }}
      </button>
      <button class="button is-small" type="button" @click="$emit('remove-meal', props.index)">
        {{ props.deleteLabel }}
      </button>
    </div>
  </li>
</template>

<style scoped>
.meal-row {
  border: 1px solid var(--app-border);
  border-radius: 0.65rem;
  padding: 0.55rem;
  display: grid;
  gap: 0.5rem;
  background: var(--app-surface);
}

.meal-row.is-dragging {
  opacity: 0.6;
  border-style: dashed;
}

.meal-row.is-drop-target {
  box-shadow: inset 0 -3px 0 color-mix(in oklab, var(--app-link), #000000 10%);
  background: color-mix(in oklab, var(--app-surface), #c9dcff 20%);
}

.meal-row-main {
  display: grid;
  gap: 0.4rem;
}

.meal-slot {
  margin: 0;
  font-size: 0.86rem;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.45rem;
  width: 100%;
}

.slot-time-clock-wrap {
  display: inline-grid;
  justify-self: end;
}

.nutrition-line {
  display: grid;
  gap: 0.3rem;
}

.cumulative-line {
  margin: 0;
}

.meal-row-actions {
  display: grid;
  gap: 0.45rem;
}

@media (min-width: 860px) {
  .meal-row-actions {
    grid-template-columns: 0.9fr 1.2fr auto auto;
    align-items: end;
  }
}
</style>
